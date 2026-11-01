"""文件交换档：定时任务工位不靠 MCP，只读一个文件。

data/exchange/<工位>/current.md 只有核心写、只覆盖、永远一张卡：
卡头用一行 HTML 注释记着这张卡（<!-- task: <id> round: <n> -->），没活时写 <!-- idle -->。
每次覆盖前把上一版归档到 data/tasks/<上一张卡 id>/exchange/round-<n>.md，
每次写入都记进 store.exchange_log（action ∈ wrote_card / wrote_idle …）。

安全：member 只往 seen.txt 写一行时间（记号），current.md 只读不写；核心只认 data/tasks/<已知任务 id>/ 下的
report.md 和 DONE，别的文件一律不读。
"""
from __future__ import annotations

import re
import shutil

from . import config, i18n

MARK_RE = re.compile(r"<!-- task: (\d{8}-\d{3}) round: (\d+) -->")
IDLE_MARK = "<!-- idle -->"
WROTE_CARD = "wrote_card"
WROTE_IDLE = "wrote_idle"

PROMPT_MAX_CHARS = 12000      # 一次贴进定时任务的正文上限（超了就不派这张卡）


def exchange_dir(station_id: str):
    """data/exchange/<工位>/，不存在就建。"""
    d = config.DATA / "exchange" / station_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def current_path(station_id: str):
    return exchange_dir(station_id) / "current.md"


def seen_path(station_id: str):
    """打工猫每次被叫起来写的记号文件：盒子靠它的修改时间知道定时任务来过了。"""
    return exchange_dir(station_id) / "seen.txt"


def render_card(task_id: str, round: int, cwd, report_path, prompt_text: str, lang: str | None = None) -> str:
    """current.md 的卡版正文：标记行 + 卡头（标签一行一个）+ 一行分隔 + prompt.txt 原文。"""
    lg = lang or i18n.lang()
    lines = [
        "<!-- task: %s round: %d -->" % (task_id, int(round or 1)),
        i18n.t("ex.task_id", lg, task_id=task_id),
        i18n.t("ex.round", lg, round=int(round or 1)),
        i18n.t("ex.cwd", lg, cwd=cwd),
        i18n.t("ex.report", lg, path=report_path),
        i18n.t("ex.done", lg, path=config.DATA / "tasks" / task_id / "DONE"),
        "",
        "---",
        "",
        prompt_text or "",
    ]
    return "\n".join(lines) + "\n"


def render_idle(next_hhmm: str, lang: str | None = None) -> str:
    """current.md 的没活版正文。"""
    lg = lang or i18n.lang()
    return "%s\n%s\n" % (IDLE_MARK, i18n.t("ex.idle", lg, at=next_hhmm))


def read_marker(text: str):
    """(task_id, round) 或 None（没卡 / idle）。"""
    m = MARK_RE.search(text[:300])
    return (m.group(1), int(m.group(2))) if m else None


def write_current(store, station_id: str, text: str, task_id: str | None = None, round: int | None = None) -> None:
    """整文件覆盖写 current.md。写之前把上一版归档到对应卡目录，最后记一条 exchange_log。"""
    p = current_path(station_id)
    try:
        old = p.read_text(encoding="utf-8") if p.exists() else ""
    except OSError:
        old = ""
    mark = read_marker(old)
    if mark:  # 上一版是一张卡 → 抄到 data/tasks/<id>/exchange/round-<n>.md
        old_id, old_round = mark
        try:
            arc = config.DATA / "tasks" / old_id / "exchange"
            arc.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, arc / ("round-%d.md" % old_round))
        except OSError:
            pass  # 归档失败不拦着派卡
    p.write_text(text, encoding="utf-8")
    store.exchange_add(station_id, task_id, round, WROTE_CARD if task_id else WROTE_IDLE,
                       len(text.encode("utf-8")))


def report_summary(text: str, limit: int = 200) -> str:
    """report.md 里「## 做了什么」（英文模板是 What was done）下的第一段；标题行自带内容就用标题行；没有就取前 200 字。"""
    if not text:
        return ""
    m = re.search(r"(?mi)^##\s*(?:做了什么|What was done)\s*[：:]?\s*(.*)$", text)
    if m and m.group(1).strip():
        return m.group(1).strip()
    if m:
        sec = text[m.end():]
        nxt = re.search(r"(?m)^##\s", sec)
        if nxt:
            sec = sec[: nxt.start()]
        for para in re.split(r"\n\s*\n", sec):
            if para.strip():
                return re.sub(r"\s+", " ", para.strip())
    return text.strip()[:limit]


def next_hhmm(every_min: int) -> str:
    """现在 + every_min 分钟，写成 HH:MM（文件档「下次几点再来」用）。"""
    import datetime as _dt

    t = _dt.datetime.now().astimezone() + _dt.timedelta(minutes=int(every_min or 30))
    return t.strftime("%H:%M")


def is_file_mode(station_def: dict | None) -> bool:
    """该工位是不是文件档：定时任务工位（runner=scheduled）一律走文件交换，老工位没写 exchange 也算。"""
    return bool(station_def) and station_def.get("runner") == "scheduled"
