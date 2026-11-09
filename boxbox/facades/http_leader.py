"""首领那边：事件行、上岗话、等着回话。"""
from __future__ import annotations

import datetime as _dt
import json
import re
import threading
import time

from .. import config, connectors, fail_why, i18n
from .http_const import LEADER_EVENT_KINDS, LEADER_EVENT_MAX, WAIT_DEFAULT_S, WAIT_MAX_S


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
        # 做到一半退出的别再说「没跑成」，那句读起来像没开工
        if data.get("half"):
            phrase = fail_why.headline(lg, data.get("exit"), data.get("turns"), data.get("dur_s"))
            return i18n.t("leader.event.half", lg, head=head, phrase=phrase, tail=tail)
        no_run = bool(tid) and not store.runs_for_task(tid)
        why = i18n.t("leader.event.never_started", lg) if no_run else i18n.t("leader.event.not_run", lg)
        return "%s %s %s" % (head, why, tail)
    if kind == "interrupted":
        return i18n.t("leader.event.interrupted", lg, head=head, tail=tail)
    if kind == "review":
        if _is_accepted(data, text):
            return ""                       # 别人验收过了：不是首领要管的事
        return _return_line(lg, head, tail, data, t)
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
def _return_line(lg: str, head: str, tail: str, data: dict, t: dict | None) -> str:
    """打回的摘要按卡的去向写：已开工是已重派，排上队是已排队，只有进了待办才是等你定。
    老事件没记落地时，用卡现在的状态补，别把已经重派的也写成等你定。"""
    landed = str(data.get("landed") or "")
    state = str((t or {}).get("state") or "")
    if not landed:
        if data.get("verdict") == "return_max" or state == "returned":
            landed = "pending"
        elif state == "queued":
            landed = "queued"
        elif data.get("verdict") == "return" or state in ("dispatched", "running"):
            landed = "redispatched"
        else:
            landed = "pending"
    sid = str(data.get("to") or (t or {}).get("assignee") or "")
    n = data.get("round")
    if n is None:
        n = (t or {}).get("round") or ""
    if landed == "queued":
        return i18n.t("leader.event.returned_queued", lg, head=head, tail=tail, sid=sid, n=n)
    if landed == "redispatched":
        return i18n.t("leader.event.returned_go", lg, head=head, tail=tail, sid=sid, n=n)
    return i18n.t("leader.event.returned", lg, head=head, tail=tail)
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
def _for_this_leader(d, ev: dict, leader: str) -> bool:
    """这事是不是这个首领该看的。猫歇着 / 回来谁都看得到；
    带卡号的只给派这张卡的首领。别的首领扫过也不算它读走（游标是各记各的）。"""
    kind = str(ev.get("kind") or "")
    if kind in ("rest_out", "rest_back"):
        return True
    tid = str(ev.get("task_id") or "")
    if tid:
        t = d.store.get_task(tid) if d is not None else None
        disp = str((t or {}).get("dispatcher") or "")
        return not disp or disp == leader
    if kind == "interrupted_handoff":
        station = str(ev.get("station") or "")
        return not station or station == leader or not config.is_leader(station)
    return True


def _leader_events(d, station: str, after: int) -> tuple[list[str], int]:
    """(after 之后)首领要管的新事件 → (一行一条, 读到哪一条了)。
    不是这个首领的卡也把序号往前拨：不然下次还得重扫，而它本来就不该看。"""
    evs = d.store.events_after(after, LEADER_EVENT_KINDS, limit=200)
    lines: list[str] = []
    last = int(after)
    for ev in evs:
        last = int(ev.get("id") or last)
        if not _for_this_leader(d, ev, station):
            continue
        ln = _event_line(d, ev, station)
        if ln:
            lines.append(ln)
            if len(lines) >= LEADER_EVENT_MAX:
                break
    return lines, last
def _leader_seen_key(station: str) -> str:
    return "leader_seen:" + station


# 这次回话准备带给首领的事件。字节写进连接之后才落库；写失败或客户端取消就放回去。
_held = threading.local()
_cancel_lock = threading.Lock()
_cancels: dict[tuple[str, str], threading.Event] = {}


def _cancelled() -> bool:
    ev = getattr(_held, "cancel", None)
    return bool(ev is not None and ev.is_set())


def arm_cancel(station: str, req_id) -> None:
    """记下这次工具调用的请求号，另一条连接上的取消通知才能喊停它。"""
    if req_id is None or not station:
        return
    prev = getattr(_held, "cancel_key", None)
    already = _cancelled()
    ev = threading.Event()
    if already:
        ev.set()
    key = (str(station), str(req_id))
    with _cancel_lock:
        if prev and prev != key:
            _cancels.pop(prev, None)
        _cancels[key] = ev
    _held.cancel = ev
    _held.cancel_key = key


def note_cancelled(station: str, req_id) -> None:
    """客户端取消了这次请求：正在等的那一趟别把事件标成读过。"""
    if req_id is None or not station:
        return
    with _cancel_lock:
        ev = _cancels.get((str(station), str(req_id)))
    if ev is not None:
        ev.set()


def _clear_cancel() -> None:
    key = getattr(_held, "cancel_key", None)
    if key:
        with _cancel_lock:
            _cancels.pop(key, None)
    _held.cancel = None
    _held.cancel_key = None


def _hold_seen(station: str, last: int) -> None:
    cur = getattr(_held, "last", None)
    if cur is None or int(last) > int(cur):
        _held.station = station
        _held.last = int(last)


def drop_held() -> None:
    _held.last = None
    _held.station = None


def begin_delivery() -> None:
    """走 HTTP 的回话先别落已读：写进连接成功才算送到。"""
    _held.defer = True


def release_delivery(store, ok: bool) -> None:
    """ok 且没被取消才推进已读。序号只往前走，不把别的请求已经记下的退回去。"""
    last = getattr(_held, "last", None)
    station = getattr(_held, "station", None)
    cancelled = _cancelled()
    drop_held()
    _clear_cancel()
    _held.defer = False
    if not ok or cancelled or last is None or not station or store is None:
        return
    key = _leader_seen_key(station)
    cur = store.kv_get(key)
    try:
        cur_n = int(cur) if cur is not None else 0
    except (TypeError, ValueError):
        cur_n = 0
    if int(last) > cur_n:
        store.kv_set(key, int(last))


def finish_delivery(store) -> None:
    """进程内直接拿到回话（没有连接可断）就算送到了。HTTP 那条等写完再记。"""
    if getattr(_held, "defer", False):
        return
    release_delivery(store, True)


def _seen_floor(store, station: str) -> int:
    """从这个序号之后才算新的。第一次来先记下当前最后一条，历史不倒出来。
    同一次回话里已经准备送出去的，接着往下看，免得同一条给两遍。"""
    key = _leader_seen_key(station)
    after = store.kv_get(key)
    if after is None:
        after = store.last_event_id()
        store.kv_set(key, after)
    after = int(after)
    if getattr(_held, "station", None) == station and getattr(_held, "last", None) is not None:
        after = max(after, int(_held.last))
    return after


def _leader_new(d, station: str) -> list[str]:
    """首领这次读到的「上次以来出了什么」。序号先记在这次回话上，字节写出去才落库。"""
    if _cancelled():
        drop_held()
        return []
    store = d.store
    after = _seen_floor(store, station)
    lines, last = _leader_events(d, station, after)
    if last != after:
        _hold_seen(station, last)
    return lines


def _parse_timeout(args: dict) -> tuple[int, int | None]:
    """(实际等待秒数, 被压下来的原值)。没写或写坏了用默认，超过上限按上限并带回原值。"""
    try:
        raw = int((args or {}).get("timeout_s") or WAIT_DEFAULT_S)
    except (TypeError, ValueError):
        raw = WAIT_DEFAULT_S
    if raw > WAIT_MAX_S:
        return WAIT_MAX_S, raw
    return max(1, raw), None


def _cap_note(d, station: str, asked: int | None) -> str:
    if asked is None:
        return ""
    lg = d.lang_of(station) if hasattr(d, "lang_of") else i18n.lang()
    return i18n.t("leader.wait_capped", lg, n=asked, cap=WAIT_MAX_S)


def _with_note(out: dict, d, station: str, asked: int | None) -> dict:
    note = _cap_note(d, station, asked)
    if note:
        out["note"] = note
    return out


def _none_out(d, station: str, asked: int | None) -> dict:
    lg = d.lang_of(station) if hasattr(d, "lang_of") else i18n.lang()
    return _with_note({"ok": True, "code": "none", "text": i18n.t("leader.no_news", lg)}, d, station, asked)


def _wait_slice(seconds: float) -> bool:
    """等一小段。客户端取消了就立刻返回 False，别把这一秒睡完。"""
    ev = getattr(_held, "cancel", None)
    if ev is None:
        time.sleep(seconds)
        return True
    return not ev.wait(seconds)


def _wait_for_update(d, station: str, args: dict) -> dict:
    """挂着等猫猫交回：每 1 秒查一次（不长时间占数据库锁），一有动静就立刻回。
    默认 45 秒，最多 100（给 Cursor 留出收回话的时间），最少 1。"""
    timeout, asked = _parse_timeout(args)
    store = d.store
    after = _seen_floor(store, station)
    deadline = time.time() + timeout
    while True:
        if _cancelled():
            drop_held()
            return _none_out(d, station, asked)
        lines, last = _leader_events(d, station, after)
        after = last
        if lines:
            if _cancelled():
                drop_held()
                return _none_out(d, station, asked)
            _hold_seen(station, last)
            return _with_note({"ok": True, "code": "update", "events": lines}, d, station, asked)
        if time.time() >= deadline:
            return _none_out(d, station, asked)
        if not _wait_slice(1):
            drop_held()
            return _none_out(d, station, asked)


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
