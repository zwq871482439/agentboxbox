"""PyInstaller entry point for the single-file boxbox.exe (工作计划 4.5).

    pwsh packaging/build_exe.ps1      ->  dist/boxbox.exe   (built --noconsole: double-click never shows a cmd window)

Double-click = tray shell (core in-process, window opens). `boxbox.exe serve|mcp|doctor|...` from a terminal = the same
CLI as `python -m boxbox`: being a windowed exe we have no console of our own, so attach to the parent terminal's.
"""
import sys


def _attach_parent_console() -> None:
    """Windowed exe started from a terminal: reuse that terminal for stdout/stderr (stdin stays as given)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        if not ctypes.windll.kernel32.AttachConsole(-1):      # ATTACH_PARENT_PROCESS; fails when double-clicked
            return
        for name, mode in (("stdout", "w"), ("stderr", "w")):
            try:
                setattr(sys, name, open("CONOUT$", mode, encoding="utf-8", errors="replace", buffering=1))
            except OSError:
                pass
        if sys.stdin is None or getattr(sys.stdin, "closed", False):
            try:
                sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
            except OSError:
                pass
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    if sys.argv[1:] and "mcp" not in sys.argv[1:3]:          # mcp talks over the pipes the client gave us: never touch them
        _attach_parent_console()
    from boxbox.facades.cli import main
    sys.exit(main())
