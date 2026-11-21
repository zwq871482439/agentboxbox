"""在干活的帮手此刻的动作：只读当前运行记录的尾部，不启动进程。"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib

TAIL_BYTES = 512 * 1024
ACTION_LIMIT = 30
_KINDS = {
    "read": "read", "grep": "read", "find": "read", "ls": "read",
    "write": "edit", "edit": "edit", "bash": "bash",
}


def follow(d, station_id: str) -> dict:
    """当前帮手的实时跟随数据；一句话状态与看板共用同一行。"""
    row = next((item for item in d.board() if item.get("id") == station_id), None)
    if row is None:
        return {"status_line": "", "actions": []}
    out = {"status_line": row["status_line"], "actions": []}
    runs = [run for run in d.store.open_runs() if run.get("station") == station_id]
    if not runs:
        return out
    run = runs[-1]
    actions, usage = _read_run(run)
    ledger = d.store.ledger_for_runs([run["run_id"]])
    if ledger:
        usage = {"in": sum(_int(item.get("tok_in")) for item in ledger),
                 "out": sum(_int(item.get("tok_out")) for item in ledger)}
    else:
        out["tokens_partial"] = True
    out.update(minutes=row.get("minutes"), tokens=usage, actions=actions[-ACTION_LIMIT:])
    return out


def _read_run(run: dict) -> tuple[list[dict], dict]:
    actions = []
    usage = {"in": 0, "out": 0}
    for ev in _tail_events(str(run.get("log_path") or "")):
        etype = ev.get("type")
        if etype == "tool_execution_start":
            kind = _KINDS.get(str(ev.get("toolName") or "").lower())
            if kind:
                actions.append({"at": _at(ev, None, run), "kind": kind, "target": _target(ev.get("args"))})
        elif etype == "message_end":
            message = ev.get("message")
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            raw = message.get("usage")
            if isinstance(raw, dict):
                usage["in"] += _int(raw.get("input"))
                usage["out"] += _int(raw.get("output"))
            if _is_thinking(message.get("content")):
                actions.append({"at": _at(ev, message, run), "kind": "think", "target": ""})
    return actions, usage


def _tail_events(path: str):
    """最多读文件尾部 512 KB；开头不完整的 JSON 行直接跳过。"""
    if not path:
        return
    try:
        with pathlib.Path(path).open("rb") as fh:
            fh.seek(0, 2)
            start = max(0, fh.tell() - TAIL_BYTES)
            fh.seek(start)
            raw = fh.read()
    except OSError:
        return
    lines = raw.splitlines()
    if start and lines:
        lines = lines[1:]
    for line in lines:
        try:
            ev = json.loads(line.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        if isinstance(ev, dict):
            yield ev


def _target(args) -> str:
    if isinstance(args, dict):
        value = next((args.get(key) for key in ("command", "cmd", "path", "file_path")
                      if isinstance(args.get(key), str) and args.get(key).strip()), "")
        if not value:
            try:
                value = json.dumps(args, ensure_ascii=False)
            except (TypeError, ValueError):
                value = ""
    else:
        value = args if isinstance(args, str) else ""
    return " ".join(value.split())[:120]


def _is_thinking(content) -> bool:
    """没有工具调用的文字或思考消息，才算一次「在想」。"""
    if isinstance(content, str):
        return bool(content.strip())
    if not isinstance(content, list):
        return False
    if any(isinstance(block, dict) and block.get("type") == "toolCall" for block in content):
        return False
    return any(isinstance(block, dict) and block.get("type") in ("text", "thinking")
               and str(block.get("text") or block.get("thinking") or "").strip() for block in content)


def _at(ev: dict, message: dict | None, run: dict) -> str:
    raw = ev.get("timestamp") or (message or {}).get("timestamp") or run.get("last_activity") or run.get("started") or ""
    if isinstance(raw, (int, float)):
        seconds = raw / 1000 if raw > 10_000_000_000 else raw
        return _dt.datetime.fromtimestamp(seconds).astimezone().isoformat()
    return str(raw)


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
