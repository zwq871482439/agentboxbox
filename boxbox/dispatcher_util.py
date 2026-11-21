"""派卡用到的几个小工具函数。"""
from __future__ import annotations

import datetime as _dt
import functools
import json
import os
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


def _mins_since(iso, default=0.0) -> float | None:
    """距现在多少分钟；时间读不出来（没给 / 格式不对）就返回 default。"""
    if not iso:
        return default
    try:
        return (_dt.datetime.now().astimezone() - _dt.datetime.fromisoformat(str(iso))).total_seconds() / 60
    except (TypeError, ValueError):
        return default


def _elapsed(started, now=None) -> float | None:
    """ISO 时间 → 到现在过了多少秒；时间读不出来返回 None。没带时区的按本地时间算。"""
    if not started:
        return None
    try:
        start = _dt.datetime.fromisoformat(str(started))
    except (TypeError, ValueError):
        return None
    ref = now or _dt.datetime.now().astimezone()
    if start.tzinfo is None:
        start = start.replace(tzinfo=ref.tzinfo)
    return (ref - start).total_seconds()


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
                           encoding="utf-8", errors="replace", timeout=10, shell=False,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    out = (p.stdout or "").strip()
    return out if p.returncode == 0 and len(out) >= 7 else None


# 同一个目录是不是仓库、属于哪个仓库几乎不变；派卡在调度锁里对每张开着的卡都要问一次 git，
# 按 cwd 记住结果免得整个调度陪着等（变了最多少一条撞车提醒）
@functools.lru_cache(maxsize=256)
def _git_repo_info(cwd) -> tuple[str, str, str] | None:
    """(仓库的公共 git 目录, 工作树根, cwd 相对根的前缀)；不是仓库就 None。
    worktree 共用一个公共 git 目录，靠它认出「同一个仓库」，哪怕两张卡在两个 worktree 里。"""
    if not cwd:
        return None
    try:
        p = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--git-common-dir", "--show-toplevel", "--show-prefix"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, shell=False,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    lines = [ln.strip() for ln in (p.stdout or "").splitlines()]
    if len(lines) < 3 or not lines[0] or not lines[1]:
        return None
    common, top, prefix = lines[0], lines[1], lines[2]
    if not os.path.isabs(common):
        common = os.path.join(str(cwd), common)
    common = os.path.normcase(os.path.normpath(os.path.abspath(common)))
    top = os.path.normcase(os.path.normpath(os.path.abspath(top)))
    return common, top, prefix.replace("\\", "/")


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
