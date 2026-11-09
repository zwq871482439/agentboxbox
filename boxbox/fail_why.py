"""做到一半退出时，把断在哪写成待办能看的一句。

一个工具都没调过的不走这里：那种还是「没跑成」，调用方照旧写。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import re

from . import classify, i18n, runlog, stall

MAX_REASON = 800
# 一层目录里文件太多就不再数：避免对着大目录把收尾拖住
OUT_CAP = 500
_CMD_MAX = 120
_LINE_MAX = 200
_ERR_MAX = 300
_BARE_EXIT = re.compile(r"^(退出码 \d+|exit code \d+)$", re.I)


def for_failure(run: dict, res, card: dict, lang: str, station: str) -> dict | None:
    """调过工具才返回 {reason, event, data}。没调过返回 None。"""
    if not _used(run, res):
        return None
    turns = _turns(res, run)
    dur_s = _elapsed(run.get("started"))
    phrase = headline(lang, getattr(res, "exit", None), turns, dur_s)
    reason = _assemble(run, res, card, lang, phrase)
    data: dict = {"half": True, "exit": int(getattr(res, "exit", None) or 0)}
    if turns is not None:
        data["turns"] = turns
    if dur_s is not None:
        data["dur_s"] = dur_s
    return {"reason": reason, "event": i18n.t("ev.failed.half", lang, sid=station, phrase=phrase), "data": data}


def headline(lang: str, exit_code, turns, dur_s) -> str:
    """「跑到一半退出了（退出码 1，36 轮、11 分钟）」这一句。轮数、用时缺了就省掉。"""
    dur = ""
    if dur_s is not None and dur_s != "":
        try:
            dur = stall.human_dur(int(dur_s), lang)
        except (TypeError, ValueError):
            dur = ""
    n = _as_int(turns)
    if n is not None and dur:
        bits = i18n.t("fail.bits.both", lang, turns=n, dur=dur)
    elif n is not None:
        bits = i18n.t("fail.bits.turns", lang, turns=n)
    elif dur:
        bits = i18n.t("fail.bits.dur", lang, dur=dur)
    else:
        bits = ""
    code = exit_code if exit_code is not None and exit_code != "" else 1
    return i18n.t("fail.half", lang, exit=code, bits=bits)


def _assemble(run, res, card, lang, phrase) -> str:
    parts = [phrase]
    at = _latest_hhmm(run)
    if at:
        parts.append(i18n.t("fail.last_at", lang, at=at))
    tool = _tool_sentence(run, lang)
    if tool:
        parts.append(tool)
    lines = _stderr_lines(run, res)
    err = _model_error(res, lines)
    if err:
        parts.append(i18n.t("fail.model", lang, err=err))
    # 太长时从末尾截：产出目录那句放在报错输出前面，截掉的是后面的输出
    out = _output_sentence(card, lang)
    if out:
        parts.append(out)
    if lines:
        parts.append(i18n.t("fail.stderr", lang, lines=i18n.t("fail.line_sep", lang).join(lines)))
    text = classify.mask(i18n.t("fail.sep", lang).join(parts))
    return text[:MAX_REASON]


def _used(run, res) -> bool:
    try:
        n = int(getattr(res, "n_tools", None) or 0)
    except (TypeError, ValueError):
        n = 0
    if n > 0:
        return True
    return bool(str((run or {}).get("last_tool") or "").strip())


def _turns(res, run) -> int | None:
    tok = getattr(res, "tokens", None)
    if not isinstance(tok, dict):
        raw = (run or {}).get("tokens_json")
        if not raw:
            return None
        try:
            tok = json.loads(raw)
        except (TypeError, ValueError):
            return None
    if not isinstance(tok, dict) or "turns" not in tok:
        return None
    return _as_int(tok.get("turns"))


def _as_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _elapsed(started) -> int | None:
    if not started:
        return None
    try:
        start = _dt.datetime.fromisoformat(str(started))
    except ValueError:
        return None
    now = _dt.datetime.now().astimezone()
    if start.tzinfo is None:
        start = start.replace(tzinfo=now.tzinfo)
    return max(0, int((now - start).total_seconds()))


def _latest_hhmm(run) -> str:
    best = ""
    for key in ("last_model_at", "last_tool_at", "last_output_at", "last_activity"):
        raw = str((run or {}).get(key) or "")
        if raw > best:
            best = raw
    return _hhmm(best) if best else ""


def _hhmm(ts) -> str:
    try:
        return _dt.datetime.fromisoformat(str(ts)).strftime("%H:%M")
    except (TypeError, ValueError):
        return ""


def _tool_sentence(run, lang) -> str:
    tool = str((run or {}).get("last_tool") or "").strip()
    cmd = classify.mask(" ".join(str((run or {}).get("last_tool_cmd") or "").split()))[:_CMD_MAX]
    lines = [ln.strip() for ln in str((run or {}).get("last_tool_out") or "").splitlines() if ln.strip()]
    line = classify.mask(lines[-1] if lines else "")[:_LINE_MAX]
    if not (tool or cmd or line):
        return ""
    return i18n.t("fail.last_tool", lang, tool=tool or i18n.t("fail.tool_unknown", lang),
                   cmd=cmd or "—", line=line or "—")


def _model_error(res, stderr_lines: list[str]) -> str:
    err = classify.mask(str(getattr(res, "error", "") or "").strip())
    if not err or _BARE_EXIT.match(err):
        return ""
    # 和报错输出同一句就不再单列：那是进程输出，不是模型自己的报错
    if err in stderr_lines:
        return ""
    return err[:_ERR_MAX]


def _stderr_lines(run, res) -> list[str]:
    raw = str(getattr(res, "stderr", "") or "")
    if not raw.strip():
        raw = _log_stderr(str((run or {}).get("log_path") or ""))
    lines = []
    for ln in raw.splitlines():
        text = ln.strip()
        if text:
            lines.append(classify.mask(text)[:_LINE_MAX])
    return lines[-5:]


def _log_stderr(path: str) -> str:
    """运行日志里 pi 写下的 stderr。进程记录已经丢掉时，只剩这份。"""
    text = runlog.read_text(path)            # 已经压成 .gz 的也读得到
    if not text:
        return ""
    out = []
    for ln in text.splitlines():
        if ln.startswith("[stderr]"):
            out.append(ln[len("[stderr]"):].lstrip())
    return "\n".join(out)


def _output_sentence(card, lang) -> str:
    eo = (card or {}).get("expected_output") if isinstance(card, dict) else None
    if not isinstance(eo, dict):
        return ""
    rel = str(eo.get("path") or "").strip()
    if not rel:
        return ""
    n, newest, over = _count_dir(_out_dir(rel, str(card.get("cwd") or "")))
    if over:
        return i18n.t("fail.out_over", lang)
    if n > 0 and newest is not None:
        return i18n.t("fail.out_n", lang, n=n, at=_mtime_hhmm(newest))
    return i18n.t("fail.out_count", lang, n=n)


def _out_dir(rel: str, cwd: str) -> pathlib.Path | None:
    p = pathlib.Path(rel)
    if not p.is_absolute():
        if not cwd:
            return None
        p = pathlib.Path(cwd) / rel
    try:
        # 路径自己是联接时不跟进去，只看它旁边的那一层
        if p.is_symlink():
            parent = p.parent
            if parent.is_dir() and not parent.is_symlink():
                return parent
            return None
        if p.is_dir():
            return p
    except OSError:
        return None
    parent = p.parent
    try:
        if parent.is_dir() and not parent.is_symlink():
            return parent
    except OSError:
        return None
    return None


def _count_dir(folder: pathlib.Path | None):
    """只数这一层的文件（联接算一个，不跟进去）。超过上限就停。"""
    if folder is None:
        return 0, None, False
    try:
        if (not folder.is_dir()) or folder.is_symlink():
            return 0, None, False
    except OSError:
        return 0, None, False
    n = 0
    newest = None
    try:
        with os.scandir(folder) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    continue
                if not (entry.is_file(follow_symlinks=False) or entry.is_symlink()):
                    continue
                n += 1
                if n > OUT_CAP:
                    return OUT_CAP, None, True
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if newest is None or st.st_mtime > newest:
                    newest = st.st_mtime
    except OSError:
        return 0, None, False
    return n, newest, False


def _mtime_hhmm(mtime: float) -> str:
    try:
        return _dt.datetime.fromtimestamp(mtime).astimezone().strftime("%H:%M")
    except (OSError, OverflowError, ValueError):
        return ""
