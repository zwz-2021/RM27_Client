"""AT-021: independent wire samples and console -> MQTT -> normal Qt window.

Uses temporary listeners and leaves the user's default simulator untouched.
--browser-handoff keeps the final window and console alive for a real browser
form check; it prints the URL and waits for browser-done in its evidence folder.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime
import json
import logging
import socket
import sys
import time
import traceback
import uuid

from amqtt.broker import Broker
import requests
import socketio
import uvicorn

from check_hevc_decode import json_file
from check_mqtt_receive import ROOT, TOPICS, require
from check_udp_receive import exclusive_udp, open_window
from simulator.server.app import create_app
from simulator.server.main import build_parser
from simulator.tools.smoke_test import check_stopped

# Transcribed from fixed communication PDF63-64, independently of generated pb2.
FIELDS = ('power_manager', 'rfid', 'light_strip', 'small_shooter', 'big_shooter',
          'uwb', 'armor', 'video_transmission', 'capacitor', 'main_controller', 'modular_42mm')
GROUND = set(FIELDS[:10]) - {'small_shooter'}
INFANTRY = set(FIELDS[:10]) - {'big_shooter'}
AERIAL = {'power_manager', 'video_transmission', 'main_controller'}


def literal(values):
    # All defined field tags/values fit in a single varint byte. No schema used.
    return bytes(part for number, name in enumerate(FIELDS, 1) if values.get(name) is not None
                 for part in (number << 3, values[name]))


@asynccontextmanager
async def console_service(mqtt_port):
    with socket.socket() as listener, requests.Session() as http:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        args = build_parser().parse_args(['--web-host', '127.0.0.1', '--web-port', str(port),
                '--mqtt-host', '127.0.0.1', '--mqtt-port', str(mqtt_port), '--current-robot-id', '1'])
        app = create_app(args)
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        http.trust_env = False
        console = socketio.Client(reconnection=False, request_timeout=3, http_session=http)
        try:
            async with asyncio.timeout(12):
                while not server.started:
                    if serving.done():
                        await serving
                    await asyncio.sleep(.05)
            await asyncio.to_thread(console.connect, url, transports=['websocket'], wait_timeout=5)

            async def command(name, ok=True, **values):
                reply = await asyncio.to_thread(console.call, 'referee_command',
                                               {'command': name, **values}, timeout=5)
                require(isinstance(reply, dict) and bool(reply.get('ok')) == ok,
                        f'Unexpected console response to {name}: {reply}')
                return reply

            async def state():
                response = await asyncio.to_thread(http.get, url + '/api/state', timeout=3)
                response.raise_for_status()
                return response.json()

            yield url, command, state
        finally:
            if console.connected:
                await asyncio.to_thread(console.disconnect)
            server.should_exit = True
            await asyncio.wait_for(serving, 15)
        runtime = app.fastapi_app.state.simulator
        for component in (runtime.state_manager, runtime.mqtt_publisher,
                          runtime.video_streamer, runtime.industrial_camera_streamer):
            check_stopped(component)
        require(runtime.video_streamer.sock.fileno() == -1, 'Simulator UDP resource leaked')


def displayed(values, applicable, permission=False):
    patterns = {}
    for field in FIELDS:
        value = values.get(field)
        if field == 'modular_42mm':
            word = ('：未收到$' if value is None else
                    ('：未拥有安装权限（0）$' if value == 0 else '：拥有安装权限（1）$')) if permission else '：不适用'
        elif field not in applicable:
            word = '：不适用'
        else:
            word = '：未收到$' if value is None else (
                '：离线（0）$' if value == 0 else '：在线（1）$' if value == 1 else '：安装不规范，视为离线（2）$')
        patterns['module_' + field] = word
    return patterns


async def wire_match(packets, client_id, payload, since):
    deadline = time.monotonic() + 5
    while True:
        rows = [row for row in packets[since:] if row['kind'] == 'broker-publish'
                and row['clientId'] == str(client_id) and row['topic'] == 'RobotModuleStatus'
                and row['hex'] == payload.hex()]
        if rows:
            return rows[-1]
        require(time.monotonic() < deadline, f'Wire sample missing: {payload.hex()}')
        await asyncio.sleep(.05)


async def verify(configuration, evidence, browser_handoff):
    broker = Broker({'listeners': {'default': {'type': 'tcp', 'bind': '127.0.0.1:0'}},
        'plugins': {'amqtt.plugins.authentication.AnonymousAuthPlugin': {'allow_anonymous': True},
                    'check_mqtt_receive.RecoveryPacketLog': {}}})
    results = []
    connections = 0
    async with AsyncExitStack() as services:
        await broker.start()
        services.push_async_callback(broker.shutdown)
        mqtt_port = broker._servers['default'].instance.sockets[0].getsockname()[1]
        packets = broker.plugins_manager.get_plugin('RecoveryPacketLog').packets
        url, command, state = await services.enter_async_context(console_service(mqtt_port))
        await command('set_robot_module_publishing', enabled=False)
        for robot_id, applicable, permission in ((1, GROUND, True), (3, INFANTRY, False), (6, AERIAL, False)):
            await command('set_current_robot', robot_id=robot_id)
            await command('send_robot_module_status', **dict.fromkeys(FIELDS))
            folder = evidence / str(robot_id)
            folder.mkdir()
            title = 'RM27 module ' + uuid.uuid4().hex
            with exclusive_udp(0) as reservation:
                udp_port = reservation.getsockname()[1]
            config = folder / 'infantry.json'
            json_file(config, {'mode': 'simulation', 'seat': 'infantry',
                'window': {'title': title, 'width': 1160, 'height': 900},
                'mqtt': {'host': '127.0.0.1', 'port': mqtt_port, 'robotId': robot_id},
                'video': {'bindAddress': '127.0.0.1', 'port': udp_port}})
            async with open_window(config, title, configuration) as window:
                connections += 1
                await window.observe('connected without module sample', connectionValue='^六类订阅就绪$',
                                     identityValue=rf'ID {robot_id} ·', moduleStatus='尚未收到|未收到')
                await command('set_robot_module_publishing', enabled=True)
                await window.observe('present message with all optional fields missing',
                                     **displayed({}, applicable, permission))
                for value in (0, 1, 2):
                    values = dict.fromkeys(FIELDS, value)
                    values['modular_42mm'] = value % 2
                    start = len(packets)
                    await command('send_robot_module_status', **values)
                    await window.observe(f'ID {robot_id}: all module fields {value}',
                                         **displayed(values, applicable, permission))
                    await wire_match(packets, robot_id, literal(values), start)
                # Alternating values detect swapped fields and copied armour status.
                mixed = {name: index % 3 for index, name in enumerate(FIELDS)}
                mixed['modular_42mm'] = 1
                start = len(packets)
                await command('send_robot_module_status', **mixed)
                await window.observe('distinct independent fields', **displayed(mixed, applicable, permission))
                await wire_match(packets, robot_id, literal(mixed), start)
                if robot_id == 1:
                    # All known fields are validated before replacing any saved state.
                    for field in FIELDS:
                        invalid = dict(mixed, **{field: 2 if field == 'modular_42mm' else 3})
                        await command('send_robot_module_status', ok=False, **invalid)
                    await window.observe('invalid console values preserve last complete sample',
                                         **displayed(mixed, applicable, permission))
                    await command('set_robot_module_publishing', enabled=False)
                    # Client rejects malformed/out-of-range messages as a whole.
                    for payload, reason in ((b'\x58\x02', '42mm 安装权限必须为 0 或 1'),
                                            (b'\x08\x03', '模块状态必须为 0、1 或 2'),
                                            (b'\x08', 'Protobuf 负载不完整或格式错误')):
                        await broker.internal_message_broadcast('RobotModuleStatus', payload, qos=1)
                        await window.observe('invalid MQTT sample rejected: ' + payload.hex(),
                                             diagnosticLabel='RobotModuleStatus.*坏包.*' + reason,
                                             **displayed(mixed, applicable, permission))
                    await window.observe('only module topic becomes stale', moduleStatus='已过期',
                                         connectionValue='^六类订阅就绪$', identityValue='ID 1 ·')
                    current = await state()
                    await command('set_basic_robot_values', robot_index=current['robotIds'].index(1), health=321)
                    await window.observe('MQTT dynamic continues while modules are stale', healthValue='^321$',
                                         moduleStatus='已过期')
                    await command('set_robot_module_publishing', enabled=True)
                    await window.observe('fresh module sample recovers', **displayed(mixed, applicable, permission))
                    await command('set_current_robot', robot_id=103)
                    await window.observe('mismatching identity clears robot-relative module data',
                                         moduleStatus='身份|未收到', healthValue='^—$')
                    await command('set_current_robot', robot_id=1)
                    await window.observe('matching identity and per-robot values recover',
                                         **displayed(mixed, applicable, permission))
                await window.action('stopButton')
                await window.observe('stop clears module state', connectionValue='^已停止$',
                                     moduleStatus='尚未收到|未收到|已停止')
                await command('set_robot_module_publishing', enabled=False)
                await window.action('startButton')
                connections += 1
                await window.observe('reopen waits for new module data', connectionValue='^六类订阅就绪$',
                                     moduleStatus='尚未收到|未收到')
                await command('set_robot_module_publishing', enabled=True)
                await window.observe('reopen accepts new sample', **displayed(mixed, applicable, permission))
                if browser_handoff and robot_id == 3:
                    json_file(evidence / 'browser-ready.json', {'url': url, 'title': title,
                              'instruction': 'Set power_manager=2, rfid=0, armor=1 and save through the browser.'})
                    print('Browser handoff: ' + url + ' (see browser-ready.json)', flush=True)
                    async with asyncio.timeout(600):
                        while not (evidence / 'browser-done').exists():
                            await asyncio.sleep(.3)
                    mixed.update(power_manager=2, rfid=0, armor=1)
                    await window.observe('real browser form reaches normal Qt window',
                                         **displayed(mixed, applicable, permission))
                    await wire_match(packets, robot_id, literal(mixed), 0)
                    results.append('real browser form -> MQTT literal sample -> normal Qt window')
                results.append(f'ID {robot_id}: missing/0/1/2/distinct values, applicability, stop/reopen')
            with exclusive_udp(udp_port):
                pass
            await command('set_robot_module_publishing', enabled=False)
    clients = [row for row in packets if row.get('clientId') in ('1', '3', '6')]
    json_file(evidence / 'broker-packets.json', packets)
    topics = [tuple(pair) for row in clients if row['kind'] == 'subscribe' for pair in row['topics']]
    require(sorted(topics) == sorted([(topic, 1) for topic in TOPICS] * connections),
            'Missing, extra, repeated or wrong-QoS subscriptions')
    require(not any(row['kind'] == 'client-publish' for row in clients), 'Read-only Qt published business data')
    return {'checks': results, 'connections': connections, 'clientBusinessPublishes': 0,
            'scope': 'local simulator/AMQTT and normal Qt; official hardware not verified'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration', choices=('Debug', 'Release'), default='Debug')
    parser.add_argument('--browser-handoff', action='store_true')
    args = parser.parse_args()
    directory = ROOT / 'logs' / datetime.now().strftime('check-module-%Y%m%d-%H%M%S-%f')
    directory.mkdir(parents=True)
    print(f'Module evidence: {directory}', flush=True)
    logging.basicConfig(level=logging.ERROR)
    result = {'passed': False, 'configuration': args.configuration, 'entry': 'scripts/run.ps1'}
    try:
        result.update(asyncio.run(verify(args.configuration, directory, args.browser_handoff)))
        result['passed'] = True
        print('PASS: module wire, console, Qt state, applicability and lifecycle.')
    except Exception:
        result['error'] = traceback.format_exc()
        print(result['error'], file=sys.stderr)
    json_file(directory / 'summary.json', result)
    raise SystemExit(0 if result['passed'] else 1)
