"""首领那边：事件行、上岗话、等着回话。"""
from __future__ import annotations

import datetime as _dt
import json
import re
import time

from .. import connectors, i18n
from .http_const import LEADER_EVENT_KINDS, LEADER_EVENT_MAX


def _hhmm(ts) -> str:
    try:
        return _dt.datetime.fromisoformat(str(ts)).strftime("%H:%M")
    except (TypeError, ValueError):
        return ""
def _event_line(d, ev: dict, leader: str) -> str:
    """一条事件 → 给首领看的一行：工位 时间 出了什么 卡号（标题）。
    只写这些：不带回报正文、不带任何 key。按这个首领自己的语言出（英文上岗的拿英文）。"""
    store = d.store
    lg = d.lang_of(leader) if hasattr(d, "lang_of") else i18n.lang()
    kind = str(ev.get("kind") or "")
    station = str(ev.get("station") or "")
    tid = str(ev.get("task_id") or "")
    t = store.get_task(tid) if tid else None
    title = str((t or {}).get("title") or "")
    head = ("%s %s" % (station, _hhmm(ev.get("ts")))).strip()
    tail = i18n.t("leader.event.tail", lg, tid=tid, title=title) if tid else ""
    text = str(ev.get("text") or "")
    data = _event_data(ev)
    if kind == "rest_out":
        return i18n.t("leader.event.rest_out", lg, sid=station, word=_rest_word(data, lg))
    if kind == "rest_back":
        return i18n.t("leader.event.rest_back", lg, sid=station, tid=str(data.get("task_id") or ""))
    if kind == "interrupted_handoff":
        return i18n.t("leader.event.handoff", lg, n=data.get("n") or 0)
    if kind == "reviewing":
        return i18n.t("leader.event.reviewing", lg, head=head, tail=tail)
    if kind == "failed":
        why = i18n.t("leader.event.never_started", lg) if (tid and not store.runs_for_task(tid))             else i18n.t("leader.event.not_run", lg)
        return "%s %s %s" % (head, why, tail)
    if kind == "interrupted":
        return i18n.t("leader.event.interrupted", lg, head=head, tail=tail)
    if kind == "review":
        if _is_accepted(data, text):
            return ""                       # 别人验收过了：不是首领要管的事
        return i18n.t("leader.event.returned", lg, head=head, tail=tail)
    if kind == "report":
        if data.get("status") == "blocked" or "报卡住" in text:
            return i18n.t("leader.event.stuck", lg, head=head, tail=tail)
        if data.get("status") == "issue" or "报有问题" in text:
            return i18n.t("leader.event.issue", lg, head=head, tail=tail)
        return ""                           # 报完成 / 心跳：不吵首领（交回另有 reviewing 事件）
    if kind == "post":
        if str(data.get("to") or "") != leader:
            return ""                       # 给别人的留言
        return i18n.t("leader.event.note", lg, head=head)
    return ""
def _event_data(ev: dict) -> dict:
    """事件里带的结构化数据（json 列）。读不出来就当空的。"""
    try:
        data = json.loads(ev.get("json") or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
def _is_accepted(data: dict, text: str) -> bool:
    """这条 review 事件是「验收通过」还是「打回」：先看结构化标记，再看老数据的文字。"""
    v = str(data.get("verdict") or "")
    if v:
        return v == "accept"
    return "验收通过" in text or "approved" in text
def _rest_word(data: dict, lg: str) -> str:
    """歇着那句「出去玩了…」：按事件里记的原因和回来的时间，用这个首领的语言重说一遍。"""
    reason = str(data.get("reason") or "")
    hint = str(data.get("hint") or "")
    why = i18n.t("rest.reason." + reason, lg) if reason else ""
    when = _rest_when(hint, lg)
    return i18n.t("rest.word", lg, when=when, why=why)
def _rest_when(hint: str, lg: str) -> str:
    hint = str(hint or "")
    if not hint:
        return i18n.t("rest.when.later", lg)
    if re.match(r"^\d{1,2}:\d{2}$", hint):
        return i18n.t("rest.when.hhmms", lg, t=hint)
    m = re.match(r"^(\d+)\s*(?:分钟后|分钟|min|minutes?)$", hint)
    if m:
        return i18n.t("rest.when.minutes", lg, t=m.group(1))
    return i18n.t("rest.when.minutes", lg, t=hint)
def _leader_events(d, station: str, after: int) -> tuple[list[str], int]:
    """(after 之后)首领要管的新事件 → (一行一条, 读到哪一条了)。"""
    evs = d.store.events_after(after, LEADER_EVENT_KINDS, limit=200)
    lines: list[str] = []
    last = int(after)
    for ev in evs:
        ln = _event_line(d, ev, station)
        last = int(ev.get("id") or last)
        if ln:
            lines.append(ln)
            if len(lines) >= LEADER_EVENT_MAX:
                break
    return lines, last
def _leader_seen_key(station: str) -> str:
    return "leader_seen:" + station
def _leader_new(d, station: str) -> list[str]:
    """首领这次读到的「上次以来出了什么」；读完把序号推进到最后一条，下次不重复。
    第一次来（kv 里没序号）从 last_event_id 开始：不把历史全倒出来。"""
    store = d.store
    key = _leader_seen_key(station)
    after = store.kv_get(key)
    if after is None:
        after = store.last_event_id()
        store.kv_set(key, after)
    after = int(after)
    lines, last = _leader_events(d, station, after)
    if last != after:
        store.kv_set(key, last)
    return lines
def _wait_for_update(d, station: str, args: dict) -> dict:
    """挂着等猫猫交回：每 1 秒查一次（不长时间占数据库锁），一有动静就立刻回。
    默认 45 秒，最多 120，最少 1。"""
    try:
        timeout = int(args.get("timeout_s") or 45)
    except (TypeError, ValueError):
        timeout = 45
    timeout = max(1, min(120, timeout))
    store = d.store
    key = _leader_seen_key(station)
    after = store.kv_get(key)
    if after is None:
        after = store.last_event_id()
        store.kv_set(key, after)
    after = int(after)
    deadline = time.time() + timeout
    while True:
        lines, last = _leader_events(d, station, after)
        after = last
        if lines:
            store.kv_set(key, last)
            return {"ok": True, "code": "update", "events": lines}
        if time.time() >= deadline:
            return {"ok": True, "code": "none", "text": i18n.t("leader.no_news", d.lang_of(station))}
        time.sleep(1)


def hire_prompt(sid: str, role: str, core_url: str, lang: str = "zh") -> str:
    """贴进客户端会话的开工话，只有连上盒子之前用得到的 4 句（首句讲身份）。
    其余规则不再放这里：get_briefing 的正文（templates/leader.md）给全量，之后每次工具回话里的
    _boxbox.rules / http_tips 持续提醒。不能假设客户端已经连上 boxbox 的 MCP：要写清地址、
    没有工具时怎么按 HTTP 调、连不上怎么办。
    lang="en" 给英文版（同样 4 句），给英文的客户端用。"""
    url = connectors.mcp_url(sid, core_url)
    # 盒子没开时用户先贴这段话，首领拿不到 get_briefing 全量规则，会自己动手干活——所以派卡规则必须在贴出去的话里
    lg = lang if lang in ("zh", "en") else "zh"
    who = i18n.t("leader.hire.who." + ("leader" if role == "leader" else "member"), lg)
    dispatch = i18n.t("leader.hire.dispatch", lg) if role == "leader" else ""
    lines = [
        i18n.t("leader.hire.line1", lg, who=who, sid=sid, url=url),
        i18n.t("leader.hire.line2", lg, dispatch=dispatch),
        i18n.t("leader.hire.line3", lg),
        i18n.t("leader.hire.line4", lg),
    ]
    return "\n".join(lines)
