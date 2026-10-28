"""Run Windows lifecycle safety checks without Docker or external processes."""

import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest


SIMULATOR_ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


@contextmanager
def mqtt_listener(valid=True):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.1)
    stop = threading.Event()

    def accept_connections():
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with connection:
                connection.settimeout(2)
                try:
                    request = connection.recv(128)
                    if request:
                        connection.sendall(b"\x20\x02\x00\x00" if valid else b"HTTP")
                except OSError:
                    pass

    worker = threading.Thread(target=accept_connections, daemon=True)
    worker.start()
    try:
        yield listener.getsockname()[1]
    finally:
        stop.set()
        listener.close()
        worker.join(3)


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell lifecycle tests require Windows")
class WindowsLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rm27 script safety ")
        self.repository = Path(self.temporary.name)
        self.simulator = self.repository / "simulator"
        shutil.copytree(SIMULATOR_ROOT / "scripts", self.simulator / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(SIMULATOR_ROOT / "docker-compose.yml", self.simulator / "docker-compose.yml")
        (self.simulator / "__init__.py").write_text("", encoding="utf-8")
        (self.simulator / ".runtime").mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def run_ps(self, source, timeout=25):
        encoded = base64.b64encode(source.encode("utf-16le")).decode("ascii")
        completed = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-EncodedCommand", encoded], cwd=self.repository, capture_output=True,
            text=True, errors="replace", timeout=timeout,
        )
        return completed

    def common(self):
        return ". " + literal(self.simulator / "scripts/common.ps1") + "\n"

    def test_only_an_mqtt_connack_counts_as_a_broker(self):
        with mqtt_listener(valid=True) as valid, mqtt_listener(valid=False) as invalid:
            result = self.run_ps(self.common() + f"""
if (-not (Test-MqttBroker '127.0.0.1' {valid})) {{ throw 'Valid MQTT rejected' }}
if (Test-MqttBroker '127.0.0.1' {invalid}) {{ throw 'Plain TCP was mistaken for MQTT' }}
""")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_reused_broker_is_not_owned_or_stopped(self):
        with mqtt_listener() as port:
            start = self.run_ps("& " + literal(self.simulator / "scripts/start.ps1") +
                                f" -BrokerOnly -MqttPort {port}\n")
            self.assertEqual(0, start.returncode, start.stdout + start.stderr)
            state = json.loads((self.simulator / ".runtime/state.json").read_text(encoding="utf-8-sig"))
            self.assertIsNone(state["broker"])
            self.assertEqual([], state["processes"])
            stop = self.run_ps("& " + literal(self.simulator / "scripts/stop.ps1") + "\n")
            self.assertEqual(0, stop.returncode, stop.stdout + stop.stderr)
            probe = self.run_ps(self.common() + f"if (-not (Test-MqttBroker '127.0.0.1' {port})) {{ throw 'Broker was stopped' }}")
            self.assertEqual(0, probe.returncode, probe.stdout + probe.stderr)

    def test_occupied_web_port_keeps_its_owner(self):
        with socket.socket() as owner:
            owner.bind(("127.0.0.1", 0))
            owner.listen()
            port = owner.getsockname()[1]
            result = self.run_ps(self.common() + f"Assert-WebPortFree {port}")
            self.assertNotEqual(0, result.returncode)
            self.assertIn("occupied", result.stdout + result.stderr)
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                accepted, _ = owner.accept()
                accepted.close()

    def test_stale_pid_record_cannot_terminate_a_foreign_process(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            state = {"version": 1, "root": str(self.simulator), "broker": None,
                     "processes": [{"role": "video", "pid": process.pid,
                                    "startTicks": "0", "executable": sys.executable}]}
            (self.simulator / ".runtime/state.json").write_text(json.dumps(state), encoding="utf-8")
            result = self.run_ps("& " + literal(self.simulator / "scripts/stop.ps1") + "\n")
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIsNone(process.poll(), "Stale record terminated a foreign process")
        finally:
            process.terminate()
            process.wait(timeout=5)

    def test_non_mqtt_port_owner_is_not_replaced_by_compose(self):
        with mqtt_listener(valid=False) as port:
            result = self.run_ps("""
function global:docker { throw 'Docker must not be invoked for an occupied non-MQTT port' }
""" + "& " + literal(self.simulator / "scripts/start.ps1") + f" -BrokerOnly -MqttPort {port}\n")
            self.assertNotEqual(0, result.returncode)
            self.assertIn("MQTT port", result.stdout + result.stderr)
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                pass

    def test_running_compose_broker_is_not_recreated_for_another_port(self):
        with socket.socket() as unused:
            unused.bind(("127.0.0.1", 0))
            port = unused.getsockname()[1]
        up_log = self.simulator / ".runtime/unexpected-up.txt"
        result = self.run_ps(self.common() + """
function global:docker {
    if ($args[0] -eq 'inspect') {
        @{Id='existing-id'; Config=@{Labels=@{'com.docker.compose.project'='rm27-simulator';
            'com.docker.compose.service'='broker'; 'com.docker.compose.project.config_files'=$script:ComposeFile}};
            State=@{Running=$true}} | ConvertTo-Json -Depth 6 -Compress
    } elseif ($args -contains 'ps') { 'existing-id' }
    elseif ($args -contains 'up') { 'wrong' | Set-Content -LiteralPath UP_LOG }
    $global:LASTEXITCODE = 0
}
""".replace("UP_LOG", literal(up_log)) + "& " + literal(self.simulator / "scripts/start.ps1") + f" -BrokerOnly -MqttPort {port}\n")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("already running", result.stdout + result.stderr)
        self.assertFalse(up_log.exists(), "A running unowned broker was recreated")

    def test_stopped_owned_broker_is_not_claimed_after_manual_restart(self):
        with mqtt_listener() as port:
            source = self.common() + """
$state = Read-SimulatorState
$state.broker = [pscustomobject]@{id='owned-id'}
Write-SimulatorState $state
$global:stopCount = 0
function global:docker {
    if ($args[0] -eq 'inspect') {
        @{Id='owned-id'; Config=@{Labels=@{'com.docker.compose.project'='rm27-simulator';
            'com.docker.compose.service'='broker'; 'com.docker.compose.project.config_files'=$script:ComposeFile}};
            State=@{Running=$true}} | ConvertTo-Json -Depth 6 -Compress
    } elseif ($args[0] -eq 'stop') { $global:stopCount++ }
    $global:LASTEXITCODE = 0
}
""" + "& " + literal(self.simulator / "scripts/stop.ps1") + "\n" + """
if ($null -ne (Read-SimulatorState).broker) { throw 'Stopped broker retained stale ownership' }
""" + "& " + literal(self.simulator / "scripts/start.ps1") + f" -BrokerOnly -MqttPort {port}\n" + \
                "& " + literal(self.simulator / "scripts/stop.ps1") + "\n" + """
if ($global:stopCount -ne 1) { throw 'Reused manually restarted broker was stopped' }
"""
            result = self.run_ps(source)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_unavailable_docker_preserves_unconfirmed_broker_ownership(self):
        source = self.common() + """
$state = Read-SimulatorState
$state.broker = [pscustomobject]@{id='unconfirmed-owned-id'}
Write-SimulatorState $state
function global:docker { $global:LASTEXITCODE = 1 }
""" + "& " + literal(self.simulator / "scripts/stop.ps1") + "\n"
        result = self.run_ps(source)
        self.assertNotEqual(0, result.returncode)
        state = json.loads((self.simulator / ".runtime/state.json").read_text(encoding="utf-8-sig"))
        self.assertEqual("unconfirmed-owned-id", state["broker"]["id"])
        self.assertIn("ownership record must be retained", result.stdout + result.stderr)

    def test_failed_start_rollback_preserves_a_process_that_could_not_stop(self):
        with socket.socket() as available:
            available.bind(("127.0.0.1", 0))
            web_port = available.getsockname()[1]
        server = self.simulator / "server"
        server.mkdir()
        (server / "__init__.py").write_text("", encoding="utf-8")
        (server / "main.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
        video = self.simulator / "video.mp4"
        video.write_bytes(b"fixture")
        common = self.simulator / "scripts/common.ps1"
        common.write_text(common.read_text(encoding="utf-8") + "\n" + f"$script:VenvPython = {literal(sys.executable)}\n" + """
function Start-OwnedPython([string]$Role, [string[]]$Arguments, [string]$InstanceId, [string]$ShutdownToken, [int]$WebPort) {
    if ($Role -eq 'video') { throw 'Simulated video startup failure' }
    $script:FakeInstance = $InstanceId
    return [pscustomobject]@{role='server'; pid=54321; startTicks='123'; executable=$script:VenvPython;
        instanceId=$InstanceId; shutdownToken=$ShutdownToken; webPort=$WebPort; stdout='fake'; stderr='fake'}
}
function Get-OwnedProcess($Record) { return [pscustomobject]@{Id=$Record.pid} }
function Get-SimulatorHealth([int]$Port) { return [pscustomobject]@{status='ok'; instanceId=$script:FakeInstance} }
function Stop-OwnedProcess($Record) { throw 'Simulated access denied stopping owned process' }
""", encoding="utf-8")
        with mqtt_listener() as port:
            result = self.run_ps("function global:ffmpeg {}\n& " +
                                literal(self.simulator / "scripts/start.ps1") +
                                f" -MqttPort {port} -WebPort {web_port} -VideoFile " + literal(video) + "\n")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Simulated video startup failure", result.stdout + result.stderr)
        state = json.loads((self.simulator / ".runtime/state.json").read_text(encoding="utf-8-sig"))
        self.assertEqual([54321], [record["pid"] for record in state["processes"]])

    def test_container_ownership_requires_id_and_compose_labels(self):
        compose_file = str(self.simulator / "docker-compose.yml")
        source = self.common() + """
$script:stopped = @()
$script:matching = $false
function global:docker {
    if ($args[0] -eq 'inspect') {
        $labels = @{'com.docker.compose.project'='somebody-else'; 'com.docker.compose.service'='broker';
            'com.docker.compose.project.config_files'=$script:ComposeFile}
        if ($script:matching) { $labels['com.docker.compose.project'] = 'rm27-simulator' }
        @{Id='exact-id'; Config=@{Labels=$labels}; State=@{Running=$true}} | ConvertTo-Json -Depth 6 -Compress
    } elseif ($args[0] -eq 'stop') { $script:stopped += $args[-1] }
    $global:LASTEXITCODE = 0
}
$record = [pscustomobject]@{id='exact-id'}
Stop-OwnedBroker $record
if ($script:stopped.Count -ne 0) { throw 'Mismatched container stopped' }
$script:matching = $true
Stop-OwnedBroker $record
if ($script:stopped.Count -ne 1 -or $script:stopped[0] -ne 'exact-id') { throw 'Exact owned container not stopped' }
"""
        result = self.run_ps(source)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_process_host_quotes_arguments_and_reclaims_only_its_descendants(self):
        tools = self.simulator / "tools"
        tools.mkdir()
        (tools / "__init__.py").write_text("", encoding="utf-8")
        output = self.simulator / ".runtime/probe.json"
        (tools / "probe_args.py").write_text(
            "import json,subprocess,sys,time\nfrom pathlib import Path\n"
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n"
            f"Path({str(output)!r}).write_text(json.dumps({{'arguments':sys.argv[1:],'child':child.pid}}))\n"
            "time.sleep(30)\n", encoding="utf-8")
        result = self.run_ps(self.common() + f"""
$script:VenvPython = {literal(sys.executable)}
$record = Start-OwnedPython -Role 'video' -Arguments @('simulator.tools.probe_args','space in argument','quote"inside','tail\') -InstanceId 'test' -ShutdownToken '' -WebPort 0
try {{
    for ($i=0; $i -lt 50 -and -not (Test-Path -LiteralPath {literal(output)}); $i++) {{ Start-Sleep -Milliseconds 100 }}
    if (-not (Test-Path -LiteralPath {literal(output)})) {{ throw ('Probe did not start: ' + (Get-Content $record.stderr -Raw)) }}
    $probe = Get-Content -LiteralPath {literal(output)} -Raw | ConvertFrom-Json
    if ($probe.arguments[0] -ne 'space in argument' -or $probe.arguments[1] -ne 'quote"inside' -or $probe.arguments[2] -ne 'tail\') {{ throw 'Native argument quoting changed data' }}
    Stop-OwnedProcess $record
    Start-Sleep -Milliseconds 300
    if (Get-Process -Id ([int]$probe.child) -ErrorAction SilentlyContinue) {{ throw 'Owned child process survived Windows job closure' }}
}} finally {{ Stop-OwnedProcess $record }}
""")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
