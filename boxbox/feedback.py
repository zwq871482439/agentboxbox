# -*- coding: utf-8 -*-
"""首领验收反馈 → 打工猫的说明（0.3 旁路；自动改 harness 不在这条路上）。

首领 review 时可以多给一句 feedback（哪里偏了 + 下次怎么约束）。设置里的开关打开时，核心把它记进
data/feedback/<工位>.json；之后派给这只猫的每张卡，member.md 渲染完在末尾接一段标注区块：

    <!-- harness-feedback -->
    首领之前验收时给你的约束（新的在下面）：
    - 20261023-004：……
    <!-- /harness-feedback -->

member.md 模板本身一个字不动（所有打工猫共用一份），只多这一段。长度硬控：
  - 单条 ≤ ITEM_MAX 字（多了截断）；
  - 整段 ≤ settings.member_feedback_max_chars 字、≤ MAX_LINES 行；超了从最旧的开始挤掉，记一条事件写挤掉几条。
开关默认关；关着时 add() 什么都不记、block() 返回空串，行为不变。仅标准库。
"""
from __future__ import annotations

import json
import re

from . import config, i18n
from .store import now_iso

ITEM_MAX = 120
MAX_LINES = 40
BEGIN = "<!-- harness-feedback -->"
END = "<!-- /harness-feedback -->"
HEAD = "feedback.head"


def enabled() -> bool:
    return bool(config.settings().get("member_feedback"))


def max_chars() -> int:
    try:
        return max(ITEM_MAX, int(config.settings().get("member_feedback_max_chars") or 800))
    except (TypeError, ValueError):
        return 800


def _path(station: str):
    safe = re.sub(r'[\\/:*?"<>|]', "_", station) or "_"
    return config.DATA / "feedback" / ("%s.json" % safe)


def items(station: str) -> list[dict]:
    try:
        data = json.loads(_path(station).read_text(encoding="utf-8"))
        return [x for x in data if isinstance(x, dict) and x.get("text")] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _clean(text: str) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return t if len(t) <= ITEM_MAX else t[: ITEM_MAX - 1] + "…"


def _line(it: dict, lang: str | None = None) -> str:
    return i18n.t("feedback.line", lang, at=str(it.get("at") or "")[5:10], tid=it.get("task_id") or "",
                  text=it.get("text") or "")


def _render(its: list[dict], lang: str | None = None) -> str:
    return "\n".join([BEGIN, i18n.t(HEAD, lang)] + [_line(x, lang) for x in its] + [END])


def _fits(its: list[dict], lang: str | None = None) -> bool:
    body = [_line(x, lang) for x in its]
    return len(body) + 2 <= MAX_LINES and len("\n".join([i18n.t(HEAD, lang)] + body)) <= max_chars()


def add(station: str, text: str, task_id: str = "", store=None, lang: str | None = None) -> dict:
    """记一条反馈。返回 {"recorded": bool, "dropped": 挤掉几条, "why": 没记的原因}。"""
    if not enabled():
        return {"recorded": False, "dropped": 0, "why": "off"}
    t = _clean(text)
    if not station or not t:
        return {"recorded": False, "dropped": 0, "why": "empty"}
    its = items(station) + [{"at": now_iso(), "task_id": task_id or "", "text": t}]
    dropped = 0
    while len(its) > 1 and not _fits(its, lang):      # 最新那条总留着（单条已经 ≤ ITEM_MAX）
        its.pop(0)
        dropped += 1
    p = _path(station)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(its, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    if store is not None:
        store.event("feedback", i18n.t("ev.feedback", sid=station)
                    + (i18n.t("ev.feedback.dropped", n=dropped) if dropped else ""),
                    station, task_id or None, data={"dropped": dropped})
    return {"recorded": True, "dropped": dropped, "why": ""}


def block(station: str, lang: str | None = None) -> str:
    """接在 member.md 渲染结果后面的那段；开关关着或没有反馈时是空串。"""
    if not enabled():
        return ""
    its = items(station)
    return ("\n\n" + _render(its, lang) + "\n") if its else ""
