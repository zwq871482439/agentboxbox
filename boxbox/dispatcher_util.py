"""派卡用到的几个小工具函数。"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import subprocess

from . import config, i18n
from .dispatcher_const import RESUME_AT, RESUME_SESSION


def _st_lang(st: dict) -> str:
    """这个工位说的语言：上岗时用它那套话招的，没记就用界面语言。"""
    v = str((st or {}).get("lang") or "").strip().lower()
    return v if v in i18n.LANGS else i18n.lang()


def _who(by: str, lang: str) -> str:
    """动态里写谁拍的板：用户在看板上点的写「你」，别的照工位名写。"""
    return i18n.t("who.you", lang) if by == "user" else by


def _runner_mode(st: dict) -> str:
    """这个工位的运行器是什么类型（和 make_runner 对得上）：once / scheduled / 空（没有运行器）。"""
    if st.get("role") == "leader":
        return "leader"
    if st.get("runner") == "scheduled":
        return "scheduled"
    if st.get("runner") == "once" and st.get("client") == "pi":
        return "once"
    return ""


def _every_min(st: dict) -> int:
    try:
        return int((st.get("runner_args") or {}).get("every_min") or 30)
    except (TypeError, ValueError):
        return 30


def _mins_since(iso) -> float:
    if not iso:
        return 0.0
    try:
        return (_dt.datetime.now().astimezone() - _dt.datetime.fromisoformat(str(iso))).total_seconds() / 60
    except (TypeError, ValueError):
        return 0.0


def _default_workdir(station_id: str):
    """工位没登记工作目录、卡上也没写时的落脚处：data/work/<工位>，第一次用时建好。"""
    p = config.DATA / "work" / station_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _git_head(cwd) -> str | None:
    """HEAD of the worktree at cwd, or None (no git / not a repo / no cwd). argv only, never a shell."""
    if not cwd:
        return None
    try:
        p = subprocess.run(["git", "-C", str(cwd), "rev-parse", "HEAD"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10, shell=False)
    except (OSError, subprocess.SubprocessError):
        return None
    out = (p.stdout or "").strip()
    return out if p.returncode == 0 and len(out) >= 7 else None


def _hhmm(ts) -> str:
    """ISO 时间 → HH:MM（给用户看的中断时刻）。"""
    try:
        return _dt.datetime.fromisoformat(str(ts)).strftime("%H:%M")
    except (TypeError, ValueError):
        return ""


def _session_usable(sess_dir) -> bool:
    """上一次那轮的对话记录还能不能接着做？
    目录不在 / 目录是空的 / 最新的记录解析不了 → 都不能，从头开始。"""
    d = pathlib.Path(str(sess_dir or ""))
    try:
        if not d.is_dir():
            return False
        files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return False
    if not files:
        return False
    for f in files:
        try:
            lines = [ln for ln in f.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        except OSError:
            continue
        if not lines:
            continue
        try:
            json.loads(lines[0])
        except ValueError:
            return False
        return True
    return False


def _prepare_resume(card: dict) -> tuple[dict, bool]:
    """卡上有没有能接着做的对话记录？→ (卡, 能不能续跑)。
    不能续跑就把续跑信息抹掉，并在卡上注明「上次的对话记录找不到，从头开始」。"""
    card = dict(card or {})
    sess = str(card.get(RESUME_SESSION) or "").strip()
    if not sess:
        return card, False
    ok = _session_usable(sess)
    if ok:
        return card, True
    card.pop(RESUME_SESSION, None)
    card[RESUME_AT] = ""
    card["resume_note"] = i18n.t("why.no_session")
    return card, False
