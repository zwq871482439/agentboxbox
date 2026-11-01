"""子进程跟着核心走。

Windows：核心第一次起子进程时建一个 Job Object，设 JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE，
每个 Pi 进程（打工的一次性进程、首领的 RPC 会话）起来后立刻放进去。核心不管是正常退出、
崩溃还是被任务管理器结束，句柄一关，组里的进程（连同它们再起的子进程）都会被系统结束，
不会再有孤儿 node 占着 data 目录。

kill_tree()：正常退出时主动结束一个进程及其子进程。
orphans()：找上次留下的、命令行里带着本 data 目录的 node / pi 进程（自检用）。
仅标准库。非 Windows 上 assign() 什么都不做（POSIX 子进程跟着会话走，kill_tree 用进程组）。
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading

IS_WIN = sys.platform.startswith("win")
_lock = threading.Lock()
_job = None          # Windows job handle，整个核心进程只建一个，故意不关（关了就会杀掉组里的进程）


def _create_job():
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                      "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class EXTENDED(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW")
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):  # 9 = ExtendedLimitInformation
        raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
    return job


def assign(proc: subprocess.Popen) -> bool:
    """把刚起的子进程放进核心的 Job。失败只返回 False（不能因为这个把派活搞挂）。"""
    global _job
    if not IS_WIN or proc is None:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        with _lock:
            if _job is None:
                _job = _create_job()
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        return bool(k32.AssignProcessToJobObject(_job, int(proc._handle)))  # noqa: SLF001 - Popen 的进程句柄
    except Exception:  # noqa: BLE001
        return False


def popen_kwargs() -> dict:
    """POSIX 上让子进程自成一个进程组，kill_tree 才能连孙进程一起结束。"""
    return {} if IS_WIN else {"start_new_session": True}


def pid_alive(pid) -> bool:
    """这个进程号还在吗？（运行器丢了进程表时，靠 runs 表里的 pid 判断 Pi 进程是不是还在干活）
    Windows 走 OpenProcess + GetExitCodeProcess；POSIX 走 os.kill(pid, 0)。只用标准库。"""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if not IS_WIN:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    try:
        k32.GetExitCodeProcess(h, ctypes.byref(code))
        return code.value == 259                        # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def kill_tree(proc: subprocess.Popen, timeout: float = 5.0) -> None:
    """结束一个进程和它的所有子进程，等它真的退出。"""
    if proc is None or proc.poll() is not None:
        return
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            pass


def orphans(data_dir) -> list[dict]:
    """命令行里带着 data_dir 的 node / pi 进程（上次核心没收拾掉的）。只在 Windows 上查。"""
    if not IS_WIN:
        return []
    needle = str(data_dir).lower()
    # 只要父进程已经不在的：在跑的核心自己的打工进程父进程还活着，不算孤儿
    ps = ("$all = @{}; Get-Process | ForEach-Object { $all[$_.Id] = 1 }; "
          "Get-CimInstance Win32_Process -Filter \"Name='node.exe' OR Name='pi.exe'\" | "
          "Where-Object { -not $all.ContainsKey([int]$_.ParentProcessId) } | "
          "ForEach-Object { '{0}`t{1}' -f $_.ProcessId, $_.CommandLine }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                             timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.stdout.decode("utf-8", "replace").splitlines():
        pid, _, cmd = line.partition("\t")
        if pid.strip().isdigit() and needle in cmd.lower() and int(pid) != os.getpid():
            rows.append({"pid": int(pid), "cmd": cmd.strip()})
    return rows
