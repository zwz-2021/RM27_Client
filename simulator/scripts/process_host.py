"""Run an upstream module with Windows child-process ownership.

When this process exits, its Windows job closes and only its own descendants
(including FFmpeg) are terminated. No process enumeration or name-based killing
is needed. On other platforms the module runs normally.
"""

import ctypes
from ctypes import wintypes
import os
import json
from pathlib import Path
import runpy
import subprocess
import sys

_job_handle = None


def _spawn(request_path):
    request = json.loads(Path(request_path).read_text(encoding="utf-8-sig"))
    with open(request["stdout"], "wb") as output, open(request["stderr"], "wb") as error:
        process = subprocess.Popen(
            [sys.executable, "-u", "-m", "simulator.scripts.process_host", *request["arguments"]],
            cwd=request["cwd"], stdin=subprocess.DEVNULL, stdout=output, stderr=error,
            close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    # No inheritable caller pipe survives in the detached host. In particular,
    # a PowerShell invocation captured by an IDE/test can return immediately.
    print(json.dumps({"pid": process.pid}), flush=True)


def _own_windows_children():
    global _job_handle
    if os.name != "nt":
        return

    class BasicLimits(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t),
                    ("max_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                               ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.basic.flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())
    # The handle is deliberately held until OS process teardown. It is never
    # inherited by FFmpeg, so terminating this host releases the entire job.
    _job_handle = handle


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m simulator.scripts.process_host MODULE [arguments]")
    if sys.argv[1] == "--spawn":
        if len(sys.argv) != 3:
            raise SystemExit("--spawn requires a JSON request path")
        _spawn(sys.argv[2])
        return
    _own_windows_children()
    record = os.getenv("RM_SIM_HOST_RECORD")
    if record:
        Path(record).write_text(json.dumps({
            "pid": os.getpid(), "instanceId": os.getenv("RM_SIM_INSTANCE_ID", ""),
        }), encoding="utf-8")
    module = sys.argv.pop(1)
    runpy.run_module(module, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
