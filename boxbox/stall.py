"""在跑的卡是不是卡住了。

只看有没有新输出、跑了多久，不看命令写的是什么（盒子不认识 CI，也不认 pytest）。
三种只提醒：命令好久没输出、模型好久没回、好久不调用工具。
单条命令到了硬上限由调度器停掉整次运行，这里只判断。
"""
from __future__ import annotations

import datetime as _dt
import json

from . import config, i18n, procjob

PROGRESS_COLS = ("last_tool", "last_tool_at", "last_tool_cmd", "last_tool_out",
                 "last_output_at", "last_model_at", "last_tool_end_at", "tool_open")

RUN_VIEW_KEYS = ("run_id", "attempt", "runner", "pid", "started", "ended", "exit", "status",
                 "commits", "tokens_json", "last_tool", "last_tool_at", "last_tool_cmd",
                 "last_tool_out", "last_model_at")

_OPEN = ("1", "true", "True")
_KINDS = ("quiet", "model", "notool")
_CMD_KEYS = ("command", "cmd", "path", "file_path")


def limits() -> dict:
    """四个时长，单位秒。设置里缺了或写坏了就用默认。"""
    s = config.settings()

    def n(key: str, default: int) -> int:
        try:
            v = int(s.get(key, default))
        except (TypeError, ValueError):
            v = default
        return max(1, v)

    return {"quiet": n("stall_cmd_s", 600), "model": n("stall_model_s", 600),
            "notool": n("stall_notool_s", 900), "hard": n("cmd_hard_s", 1800)}


def feed(state: dict | None, ev: dict, now: str) -> dict:
    """一条 Pi 事件 → 最近一次动静。时间由调用方盖上（解析器自己不算钟）。"""
    st = dict(state or {})
    if not isinstance(ev, dict):
        return st
    et = ev.get("type")
    if et == "message_update":
        st["last_model_at"] = now
        return st
    if et == "message_end":
        _message_end(st, ev.get("message"), now)
        return st
    if et == "tool_execution_start":
        _open_tool(st, ev.get("toolName"), ev.get("args"), now)
        return st
    if et == "tool_execution_update":
        _output(st, ev.get("partialResult"), now)
        return st
    if et == "tool_execution_end":
        _output(st, ev.get("result"), now)
        st["tool_open"] = ""
        st["last_tool_end_at"] = now
        if ev.get("toolName") and not st.get("last_tool"):
            st["last_tool"] = str(ev.get("toolName"))[:40]
        return st
    return st


def judge(run: dict, now: _dt.datetime | None = None) -> dict | None:
    """这一轮现在算哪种。返回 {kind, since, age_s, kill}；没事返回 None。

    命令还开着：先看硬上限（到了就杀整次），再看有没有新输出。
    命令没开着：模型好久没回优先；模型还在说话但好久不调用工具，另算一种。
    """
    if str(run.get("runner") or "") == "scheduled":
        return None
    now = now or _dt.datetime.now().astimezone()
    lim = limits()
    started = str(run.get("started") or "")
    if str(run.get("tool_open") or "") in _OPEN:
        start = str(run.get("last_tool_at") or started)
        out_at = str(run.get("last_output_at") or start)
        age_hard = _age(start, now)
        if age_hard is not None and age_hard >= lim["hard"]:
            return {"kind": "hard", "since": start, "age_s": age_hard, "kill": True}
        age_q = _age(out_at, now)
        if age_q is not None and age_q >= lim["quiet"]:
            return {"kind": "quiet", "since": out_at, "age_s": age_q, "kill": False}
        return None
    model_since = _latest(run.get("last_model_at"), run.get("last_tool_end_at"), started)
    age_m = _age(model_since, now)
    if model_since and age_m is not None and age_m >= lim["model"]:
        return {"kind": "model", "since": model_since, "age_s": age_m, "kill": False}
    if not run.get("last_model_at"):
        return None
    spoke = _age(str(run.get("last_model_at")), now)
    spin_since = _latest(run.get("last_tool_end_at"), run.get("last_tool_at"), started)
    age_spin = _age(spin_since, now)
    if spoke is not None and spoke < lim["model"] and spin_since and age_spin is not None and age_spin >= lim["notool"]:
        return {"kind": "notool", "since": spin_since, "age_s": age_spin, "kill": False}
    return None


def consider(d, run: dict) -> None:
    """看门狗每拍调用：该提醒就记一条（同一次运行同一种、同一次静默只记一条），到硬上限就停。"""
    if str(run.get("runner") or "") == "scheduled":
        return
    t = d.store.get_task(run.get("task_id"))
    if t is None or t.get("state") not in ("dispatched", "running"):
        return
    decision = judge(run)
    if decision is None:
        if run.get("stall_kind"):
            d.store.update_run(run["run_id"], stall_kind="", stall_since="")
        return
    if decision["kill"]:
        d.fail_overtime(run, hard_why(run, decision, d.lang()))
        return
    if run.get("stall_kind") == decision["kind"] and run.get("stall_since") == decision["since"]:
        return
    d.store.update_run(run["run_id"], stall_kind=decision["kind"], stall_since=decision["since"])
    shown = dict(run, stall_kind=decision["kind"], stall_since=decision["since"])
    text = explain(shown, d.lang())
    d.store.event("maybe_stuck", text, run.get("station"), run.get("task_id"),
                  data={"kind": decision["kind"], "since": decision["since"]})


def explain(run: dict, lang: str) -> str:
    """待办 / 事件里那句：哪一种、最近一次动静、底下还活着的子进程。"""
    kind = str(run.get("stall_kind") or "")
    dur = _dur_since(str(run.get("stall_since") or ""), lang)
    cmd = str(run.get("last_tool_cmd") or "—")
    head = i18n.t("stall." + kind, lang, dur=dur, cmd=cmd) if kind in _KINDS else kind
    recent = i18n.t("stall.recent", lang, tool=str(run.get("last_tool") or "—"),
                    at=_hhmm(str(run.get("last_tool_at") or "")), cmd=cmd,
                    line=str(run.get("last_tool_out") or "—"))
    return i18n.t("stall.report", lang, head=head, recent=recent, kids=_kids(run, lang))


def hard_why(run: dict, decision: dict, lang: str) -> str:
    cmd = str(run.get("last_tool_cmd") or run.get("last_tool") or "").strip()
    cmd = cmd or i18n.t("stall.cmd_unknown", lang)
    return i18n.t("stall.hard", lang, cmd=cmd, dur=human_dur(decision.get("age_s") or 0, lang))


def board_word(run: dict | None, lang: str) -> tuple[str, str] | None:
    if not run or not run.get("stall_kind"):
        return None
    return i18n.t("board.word.stuck", lang, dur=_dur_since(str(run.get("stall_since") or ""), lang)), "stuck"


def activity_view(run: dict | None) -> dict | None:
    """工位详情里那一块：最近一次工具和模型输出。没有动静就空。"""
    if not run:
        return None
    if not any(run.get(k) for k in ("last_tool", "last_tool_at", "last_model_at", "last_tool_out")):
        return None
    return {"tool": run.get("last_tool") or "", "started_at": run.get("last_tool_at") or "",
            "command": run.get("last_tool_cmd") or "", "last_line": run.get("last_tool_out") or "",
            "model_at": run.get("last_model_at") or "", "output_at": run.get("last_output_at") or ""}


def human_dur(seconds, lang: str) -> str:
    seconds = int(seconds or 0)
    if seconds >= 60:
        return i18n.t("stall.dur_min", lang, n=seconds // 60)
    return i18n.t("stall.dur_sec", lang, n=max(1, seconds))


def _dur_since(iso: str, lang: str) -> str:
    now = _dt.datetime.now().astimezone()
    age = _age(iso, now)
    return human_dur(0 if age is None else max(0, age), lang)


def _kids(run: dict, lang: str) -> str:
    rows = procjob.children(run.get("pid"))
    if not rows:
        return i18n.t("stall.no_kids", lang)
    bits = [i18n.t("stall.kid", lang, name=row.get("name") or "?", cmd=str(row.get("cmd") or "")[:100],
                   age=human_dur(row.get("age_s") or 0, lang)) for row in rows[:5]]
    return i18n.t("stall.kids", lang, kids=i18n.t("stall.kid_sep", lang).join(bits))


def _message_end(st: dict, message, now: str) -> None:
    if not isinstance(message, dict):
        return
    role = message.get("role")
    if role == "assistant":
        st["last_model_at"] = now
        calls = [b for b in (message.get("content") or []) if isinstance(b, dict) and b.get("type") == "toolCall"]
        if calls:
            last = calls[-1]
            _open_tool(st, last.get("name"), last.get("arguments"), now)
        elif st.get("tool_open") in _OPEN:
            # 模型已经接着说话，上一条命令算结束（没有单独的结束事件时的兜底）
            st["tool_open"] = ""
            st["last_tool_end_at"] = now
        return
    if role == "toolResult":
        _output(st, message.get("content"), now)
        st["tool_open"] = ""
        st["last_tool_end_at"] = now


def _open_tool(st: dict, name, args, now: str) -> None:
    st["last_tool"] = (str(name or "").strip() or "tool")[:40]
    st["last_tool_cmd"] = _cmd(args)[:120]
    st["last_tool_at"] = now
    st["last_output_at"] = now
    st["last_tool_out"] = ""
    st["tool_open"] = "1"


def _output(st: dict, obj, now: str) -> None:
    line = _last_line(obj)
    if line:
        st["last_tool_out"] = line
    st["last_output_at"] = now


def _cmd(args) -> str:
    if isinstance(args, dict):
        for k in _CMD_KEYS:
            v = args.get(k)
            if isinstance(v, str) and v.strip():
                return _one(v)
        try:
            return _one(json.dumps(args, ensure_ascii=False))
        except (TypeError, ValueError):
            return ""
    if isinstance(args, str):
        return _one(args)
    return ""


def _one(text: str) -> str:
    return " ".join(str(text).split())


def _last_line(obj) -> str:
    lines = [ln.strip() for ln in _text(obj).splitlines() if ln.strip()]
    return lines[-1][:200] if lines else ""


def _text(obj) -> str:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        if isinstance(obj.get("text"), str):
            return obj["text"]
        if "content" in obj:
            return _text(obj.get("content"))
        if "output" in obj:
            return _text(obj.get("output"))
    if isinstance(obj, list):
        return "".join(_text(x) for x in obj)
    return ""


def _age(iso, now: _dt.datetime) -> float | None:
    if not iso:
        return None
    try:
        start = _dt.datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=now.tzinfo)
    return (now - start).total_seconds()


def _latest(*isos) -> str:
    best = ""
    for raw in isos:
        text = str(raw or "")
        if text > best:
            best = text
    return best


def _hhmm(iso: str) -> str:
    if "T" in iso and len(iso) >= 16:
        return iso[11:16]
    return iso or "—"
