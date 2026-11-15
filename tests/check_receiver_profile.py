"""Exercise a personal profile through the normal Windows launcher, its Qt window and an isolated broker."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack
from datetime import datetime
import json
import socket
import subprocess
import sys
import traceback
import uuid

from amqtt.broker import Broker
from check_mqtt_receive import ROOT, TOPICS, require


async def exercise_window(phase, configuration, config, title, broker, services):
    evidence = config.parent
    command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
               str(ROOT / "tests" / "check_receiver_window.ps1"), "-ConfigFile", str(config),
               "-WindowTitle", title, "-Phase", phase, "-Configuration", configuration]
    with (evidence / f"{phase}-driver.log").open("wb") as log:
        driver = await asyncio.create_subprocess_exec(*command, cwd=ROOT, stdout=log,
                                                     stderr=subprocess.STDOUT,
                                                     creationflags=subprocess.CREATE_NO_WINDOW)
        while driver.returncode is None:
            # Independent, unretained Protobuf samples. The test broker feeds the
            # originally selected ID until the reopened UI observes a mismatch.
            if (evidence / "stop-test-broker.flag").exists():
                await services.aclose()
                subscribers = set()
            else:
                subscribers = {session.client_id for slots in broker.subscriptions.values()
                               for session, _ in slots}
            waiting_for_mismatch = phase == "reopen" and not (evidence / "allow-matching-data.flag").exists()
            if subscribers:
                is_blue = subscribers == {"103"} and not waiting_for_mismatch
                for topic, payload in (
                    ("RobotStaticStatus", "20 67 28 03" if is_blue else "20 03 28 03"),
                    ("RobotDynamicStatus", "08 c2 02" if is_blue else "08 c1 02"),
                    ("GameStatus", "30 0a"),
                    ("GlobalLogisticsStatus", "10 2a"),
                    ("GlobalUnitStatus", "5a 08 01 02 03 04 05 06 07 08 62 06 01 02 03 04 05 06"),
                ):
                    await broker.internal_message_broadcast(topic, bytes.fromhex(payload), qos=1)
            try:
                await asyncio.wait_for(driver.wait(), timeout=0.20)
            except TimeoutError:
                continue
        require(driver.returncode == 0, f"Product window check failed; see {log.name}")


async def verify(configuration, evidence):
    broker = Broker({
        "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:0"}},
        "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
                    "check_mqtt_receive.RecoveryPacketLog": {}},
    })
    await broker.start()
    packets = broker.plugins_manager.get_plugin("RecoveryPacketLog").packets
    services = AsyncExitStack()
    services.push_async_callback(broker.shutdown)
    try:
        port = broker._servers["default"].instance.sockets[0].getsockname()[1]
        # The saved infantry seat also starts a video receiver. Keep it off the default UDP port.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            video_port = probe.getsockname()[1]
        title = "RM27 profile test " + uuid.uuid4().hex
        legacy = {"mode": "simulation", "window": {"title": title, "width": 800, "height": 600},
                  "logging": {"directory": "relative-logs"}, "simulation": {"intervalMs": 735},
                  "video": {"bindAddress": "127.0.0.1", "port": video_port},
                  "mqtt": {"host": "127.0.0.1", "port": port, "robotId": 3, "connectTimeoutMs": 1800}}
        config = evidence / "personal.json"
        config.write_text(json.dumps(legacy, indent=2), encoding="utf-8")
        for phase in ("save", "reopen"):
            await exercise_window(phase, configuration, config, title, broker, services)
            saved = json.loads(config.read_text(encoding="utf-8"))
            expected = {**legacy, "seat": "infantry", "mqtt": {**legacy["mqtt"], "robotId": 103}}
            require(saved == expected, "Saved profile changed fields beyond the seat and robot ID")
    finally:
        await services.aclose()
        (evidence / "broker-packets.json").write_text(json.dumps(packets, indent=2), encoding="utf-8")

    sessions = []
    for row in packets:
        if row["kind"] == "connect":
            sessions.append([row])
        else:
            require(sessions and row["clientId"] == sessions[-1][0]["clientId"],
                    "Unexpected client ID or unattributed packet")
            sessions[-1].append(row)
    require([rows[0]["clientId"] for rows in sessions] == ["3", "3", "103", "103"],
            "Expected legacy, failed-save restart, saved profile and reopened profile CONNECTs")
    counts = []
    for rows in sessions:
        topics = [pair for row in rows if row["kind"] == "subscribe" for pair in row["topics"]]
        require(sorted(topics) == sorted((topic, 1) for topic in TOPICS), "Expected five exact subscriptions")
        require({r["topic"] for r in rows if r["kind"] == "broker-publish"} == TOPICS,
                "Broker did not deliver all five messages")
        require(not any(r["kind"] == "client-publish" for r in rows), "Client sent a business PUBLISH")
        acks = sum(r["kind"] == "client-puback" for r in rows)
        require(acks > 0, "Client sent no acknowledgements")
        counts.append({"clientId": rows[0]["clientId"], "subscriptions": len(topics),
                       "clientPuback": acks, "clientPublish": 0})
    with socket.socket() as check:
        check.settimeout(2)
        require(check.connect_ex(("127.0.0.1", port)) != 0, "Test broker still accepts connections")
    pids = []
    for phase in ("save", "reopen"):
        records = (evidence / f"{phase}-window.jsonl").read_text(encoding="utf-8").splitlines()
        closed = json.loads(records[-1])
        require(closed["observation"] == "closed", "Missing normal window shutdown")
        pids.append(closed["productPid"])
    return {"connections": counts, "closedProductPids": pids, "releasedPort": port}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", choices=("Debug", "Release"), default="Debug")
    args = parser.parse_args()
    evidence = ROOT / "logs" / ("check-profile-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    evidence.mkdir(parents=True)
    result = {"passed": False, "entry": "scripts/run.ps1 -SkipBuild -ConfigFile",
              "configuration": args.configuration}
    print(f"Profile evidence: {evidence}", flush=True)
    try:
        result.update(asyncio.run(verify(args.configuration, evidence)))
        result["passed"] = True
    except Exception:
        result["error"] = traceback.format_exc()
        print(result["error"], file=sys.stderr)
    (evidence / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
