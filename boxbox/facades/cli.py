"""CLI facade (headless members and humans): same tools as MCP, over HTTP to the core.

  python -m boxbox serve [--port 8878]
  python -m boxbox mcp --station A [--core URL]
  python -m boxbox report --task 20261021-001 --status done --summary "..." [--station A]
  python -m boxbox task 20261021-001
  python -m boxbox board | todo
  python -m boxbox wait [--timeout 600] [--station 猫猫首领] [--port 8878]
  python -m boxbox assign --station A --card card.json [--by 架构师]
  python -m boxbox doctor [--json] [--no-core]
  python -m boxbox tray [--show] [--port 8878]
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

from .. import connectors, i18n
from .http_const import WAIT_MAX_S
from .mcp_stdio import _get, _post

_CLI_LANG = [None]        # 命令行自己的语言：--lang 给的，或跟核心走


def _core(a) -> str:
    # `--core` is global, but `mcp --station X --core URL` (the form written into mcp.json) must work too.
    return a.core or getattr(a, "core_sub", None) or os.environ.get("BOXBOX_CORE") or "http://127.0.0.1:%s" % os.environ.get("BOXBOX_PORT", "8878")


def _station(a) -> str:
    return a.station or os.environ.get("BOXBOX_STATION") or ""


def _print(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")


def _h(key: str) -> str:
    """命令行帮助文字：跟着 --lang 走（没给就看系统语言）。"""
    return i18n.t(key, _CLI_LANG[0])


def _argv_lang(argv) -> str | None:
    """从命令行参数里先把 --lang 挑出来（帮助文字要在解析之前就知道语言）。"""
    for i, a in enumerate(argv or []):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1] if argv[i + 1] in ("zh", "en") else None
        if a.startswith("--lang="):
            return a.split("=", 1)[1] if a.split("=", 1)[1] in ("zh", "en") else None
    return None


def _rpc_call(url: str, name: str, args: dict, timeout: float) -> dict:
    """按 /mcp 的 JSON-RPC 调一个工具，拿回工具自己的回话。"""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        msg = json.loads(r.read().decode("utf-8"))
    text = ((msg.get("result") or {}).get("content") or [{}])[0].get("text") or "{}"
    return json.loads(text)


def _lang(core: str) -> str | None:
    """语言：不记得的话跟核心那份走（核心没开就算系统语言）。"""
    try:
        return str(_get(core, "/api/meta").get("lang") or "") or None
    except Exception:  # noqa: BLE001 - 连不上核心就用本地语言
        return None


def _cmd_wait(core: str, a, lg: str | None = None) -> int:
    """等猫猫交回卡：连本机核心，每轮调一次 wait_for_update（每次最多 100 秒，给客户端留出收回话的时间）。
    有新动静就一行一行打印，退出码 0；等不到打印「没新消息」，退出码 2；核心连不上退出码 3。"""
    station = a.station or os.environ.get("BOXBOX_STATION") or i18n.t("cli.default_station", lg)
    url = connectors.mcp_url(station, core)
    total = max(1, int(a.timeout or 600))
    deadline = time.time() + total
    while True:
        left = int(deadline - time.time())
        if left <= 0:
            break
        chunk = max(1, min(WAIT_MAX_S, left))
        try:
            res = _rpc_call(url, "wait_for_update", {"timeout_s": chunk}, timeout=chunk + 15)
        except Exception as e:  # noqa: BLE001 - 连不上就是核心没开
            if isinstance(e, socket.timeout) or (isinstance(e, urllib.error.URLError) and isinstance(e.reason, socket.timeout)):
                sys.stdout.write(i18n.t("cli.no_news", lg))     # 核心在，只是慢：算没等到
                return 2
            sys.stdout.write(i18n.t("cli.core_down", lg, core=core, err=e))
            return 3
        if res.get("code") == "update":
            for ln in res.get("events") or []:
                sys.stdout.write(str(ln) + "\n")
            return 0
        if res.get("ok") is False:
            sys.stdout.write("%s" % ((res.get("text") or i18n.t("cli.wait_nothing", lg)) + chr(10)))
            return 1
        # code=none：还没动静，接着等
    sys.stdout.write(i18n.t("cli.no_news", lg))
    return 2


def main(argv=None) -> int:
    # 无窗口的 exe 不是从终端起的（后台启动、计划任务）：没有控制台，stdout / stderr 是 None，
    # 一写就崩、弹「Unhandled exception」。先接到空设备上；托盘模式之后会换成 tray.log
    if sys.stdout is None or sys.stderr is None:
        devnull = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = sys.stdout or devnull
        sys.stderr = sys.stderr or devnull
    for s in (sys.stdout, sys.stderr):          # Chinese text on a GBK console (Windows) -> force UTF-8
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if argv is None:
        argv = sys.argv[1:]
    if not argv and getattr(sys, "frozen", False):   # double-clicked boxbox.exe -> tray shell with the window open (4.5)
        argv = ["tray", "--show"]
    _CLI_LANG[0] = _argv_lang(argv)
    ap = argparse.ArgumentParser(prog="boxbox")
    ap.add_argument("--core", default=None, help=_h("cli.help.core"))
    ap.add_argument("--lang", default=None, choices=["zh", "en"], help=_h("cli.help.lang"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("serve", help=_h("cli.help.serve"))
    p.add_argument("--port", type=int, default=None, help=_h("cli.help.port"))

    p = sub.add_parser("mcp", help=_h("cli.help.mcp"))
    p.add_argument("--station", required=True, help=_h("cli.help.station"))
    p.add_argument("--core", dest="core_sub", default=None, help=_h("cli.help.core_sub"))
    p.add_argument("--log", default=None, help=_h("cli.help.log"))

    p = sub.add_parser("report", help=_h("cli.help.report"))
    p.add_argument("--task", required=True, help=_h("cli.help.task"))
    p.add_argument("--status", required=True, choices=["heartbeat", "done", "blocked", "issue"], help=_h("cli.help.status"))
    p.add_argument("--summary", default="", help=_h("cli.help.summary"))
    p.add_argument("--station", default=None, help=_h("cli.help.station"))

    p = sub.add_parser("task", help=_h("cli.help.task"))
    p.add_argument("task_id")
    p.add_argument("--station", default=None, help=_h("cli.help.station"))

    p = sub.add_parser("board", help=_h("cli.help.board"))
    p = sub.add_parser("todo", help=_h("cli.help.todo"))
    p.add_argument("--station", default=None, help=_h("cli.help.station"))

    p = sub.add_parser("wait", help=_h("cli.help.wait"))
    p.add_argument("--timeout", type=int, default=600, help=_h("cli.help.timeout"))
    p.add_argument("--station", default=None, help=_h("cli.help.station"))
    p.add_argument("--port", type=int, default=None, help=_h("cli.help.port"))

    p = sub.add_parser("assign", help=_h("cli.help.assign"))
    p.add_argument("--station", required=True, help=_h("cli.help.station"))
    p.add_argument("--card", required=True, help=_h("cli.help.card"))
    p.add_argument("--by", default=None, help=_h("cli.help.by"))

    p = sub.add_parser("review", help=_h("cli.help.review"))
    p.add_argument("--task", required=True, help=_h("cli.help.task"))
    p.add_argument("--verdict", required=True, choices=["accept", "return"], help=_h("cli.help.verdict"))
    p.add_argument("--note", default="", help=_h("cli.help.note"))
    p.add_argument("--station", default=None, help=_h("cli.help.station"))

    p = sub.add_parser("doctor", help=_h("cli.help.doctor"))
    p.add_argument("--json", action="store_true", help=_h("cli.help.json"))
    p.add_argument("--no-core", action="store_true", help=_h("cli.help.no_core"))

    p = sub.add_parser("tray", help=_h("cli.help.tray"))
    p.add_argument("--show", action="store_true", help=_h("cli.help.show"))
    p.add_argument("--port", type=int, default=None, help=_h("cli.help.port"))

    a = ap.parse_args(argv)

    if a.cmd == "serve":
        from .. import app
        return app.serve(port=a.port)
    if a.cmd == "tray":
        from .. import tray
        return tray.main(show=a.show, port=a.port)
    if a.cmd == "doctor":
        from .. import config as _cfg
        from .. import doctor
        checks = doctor.run(core_url=None if a.no_core else _core(a), project_dir=_cfg.project_dir(), lang=a.lang)
        if a.json:
            _print({"checks": [c.__dict__ for c in checks], "summary": doctor.summary(checks)})
        else:
            sys.stdout.write(doctor.diagnostics_text(checks, extra={"core": _core(a), "data": str(_cfg.DATA)}, lang=a.lang) + "\n")
        return 1 if doctor.summary(checks)["red"] else 0
    if a.cmd == "mcp":
        from . import mcp_stdio
        args = ["--station", a.station, "--core", _core(a)]
        if a.log:
            args += ["--log", a.log]
        return mcp_stdio.main(args)
    if a.cmd == "wait":
        core = ("http://127.0.0.1:%d" % a.port) if a.port else _core(a)
        return _cmd_wait(core, a, a.lang or _lang(core))

    core = _core(a)
    try:
        if a.cmd == "report":
            st = _station(a) or os.environ.get("BOXBOX_STATION", "")
            _print(_post(core, "/rpc/report", {"station": st, "args": {"task_id": a.task, "status": a.status, "summary": a.summary}}))
        elif a.cmd == "task":
            _print(_post(core, "/rpc/get_task", {"station": _station(a), "args": {"task_id": a.task_id}}))
        elif a.cmd == "board":
            _print(_get(core, "/api/stations"))
        elif a.cmd == "todo":
            _print(_get(core, "/api/todo"))
        elif a.cmd == "assign":
            with open(a.card, encoding="utf-8") as f:
                card = json.load(f)
            by = a.by or _get(core, "/api/meta").get("leader") or ""
            _print(_post(core, "/rpc/assign", {"station": by, "args": {"station": a.station, "card": card}}, timeout=90))
        elif a.cmd == "review":
            by = _station(a) or _get(core, "/api/meta").get("leader") or ""
            _print(_post(core, "/rpc/review", {"station": by, "args": {"task_id": a.task, "verdict": a.verdict, "note": a.note}}, timeout=90))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(i18n.t("cli.core_unreachable", a.lang or _lang(core), core=core, err=e))
        return 2
    return 0
