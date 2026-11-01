# -*- coding: utf-8 -*-
"""办公室场景的触发信号（核心这一半）：全员空闲从什么时候开始、庆祝 / 复盘的邀请、站会事件、邀请的点 / 关。

画面（哪只猫做什么动作）由办公室画布那张卡做；这里只算「什么时候该演哪个场景」：
- idle_since：所有打工猫都没有 dispatched / running 的卡的起点（最后一张卡结束的时间），从库里算，重启不丢
- invites：完成庆祝（单卡验收通过）/ 收工庆祝（同一个 goal ≥ 2 张全部通过）/ 事故复盘（失败或打回满 2 轮），
  只留最近 24 小时、没被用户点过 / 关掉的，最多 3 条；一批全完成时只出收工庆祝
- standup：同一个 goal 在 10 分钟内派第 2 张卡时记一条事件（第 3、4 张并进同一条）；没开工 / 撤掉的卡不算，猫去重，只剩一只猫就不开
- ack：用户点了（play）或关掉（dismiss）某条邀请 → 记进库 + 记一条动态，之后 feed 里不再出
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re

from . import i18n
from .store import Store, now_iso

STANDUP_WINDOW_MIN = 10   # 同一个 goal 多少分钟内派 ≥ 2 张卡算一批（开站会）
INVITE_MAX = 3            # 邀请最多同时挂几条
INVITE_WINDOW_H = 24      # 邀请只看最近多少小时
ACKS_KEY = "scene_acks"   # 点过 / 关掉的邀请记在 kv 里（boxbox.db），重启不丢

KIND_NAMES = {"celebrate": "celebrate", "wrapup": "wrapup", "postmortem": "postmortem"}


def norm_goal(goal) -> str:
    """同一个 goal 的比对口径：压掉多余空白。"""
    return re.sub(r"\s+", " ", str(goal or "")).strip()


def goal_hash(goal: str) -> str:
    """收工庆祝的 id 用 goal 的短哈希（同一个 goal 只出一次）。"""
    return hashlib.sha1(norm_goal(goal).encode("utf-8")).hexdigest()[:8]


def _cutoff(hours: float) -> str:
    return (_dt.datetime.now().astimezone() - _dt.timedelta(hours=hours)).isoformat(timespec="seconds")


def _goal_of(t: dict) -> str:
    return norm_goal((t.get("card") or {}).get("goal"))


# ---- idle_since：全员空闲的起点 ----
def idle_since(store: Store) -> str | None:
    """所有打工猫都没有 dispatched / running 的卡 → 从什么时候开始闲：
    最后一张卡结束的时间（优先取这次运行的 ended，其次卡的 delivered_at，再退 updated_at）；
    从来没卡就取核心启动时间；有猫在干活返回 None。全部从库里算，核心重启后照样得出。"""
    if store.list_tasks(state="dispatched,running"):
        return None
    run_end = store.runs_ended_by_task()
    ends = []
    for t in store.list_tasks(limit=1000):
        if t.get("state") == "queued":
            continue                      # 排队的卡还没开工：这只猫本来就没在干活，也不算「结束」
        ends.append(run_end.get(t["id"]) or t.get("delivered_at") or t.get("updated_at"))
    ends = [e for e in ends if e]
    return max(ends) if ends else core_started(store)


def core_started(store: Store) -> str | None:
    """核心启动时间：优先最近一条 core_start 事件，退回 Dispatcher 起动时写的 kv。"""
    for e in store.events(300):
        if e.get("kind") == "core_start":
            return e.get("ts") or None
    return store.kv_get("core_started_at")


# ---- 邀请：celebrate / wrapup / postmortem ----
def _eligible(store: Store, now: str | None = None) -> list[dict]:
    """此刻满足条件的全部邀请（不看用户点没点过），按时间新→旧排。
    同一张卡、同一个 goal 的 id 是定死的，天然只出一次；一批（同一个 goal ≥ 2 张）全部验收通过时只出收工庆祝。"""
    now = now or now_iso()
    cutoff = _cutoff(INVITE_WINDOW_H)
    tasks = store.list_tasks(limit=1000)
    runs_of_task = store.runs_ended_by_task()   # 有运行记录的卡才算真跑过（没开工的不请复盘）
    by_goal: dict[str, list[dict]] = {}
    for t in tasks:
        g = _goal_of(t)
        if g:
            by_goal.setdefault(g, []).append(t)
    out: list[dict] = []
    # 收工庆祝：同一个 goal ≥ 2 张、全部验收通过
    wrapped_goals = set()
    for g, batch in by_goal.items():
        if len(batch) >= 2 and all(t.get("state") == "done" for t in batch):
            wrapped_goals.add(g)
            when = max(t.get("done_at") or "" for t in batch)
            if when >= cutoff:
                out.append({"id": "wrapup:" + goal_hash(g), "kind": "wrapup", "goal": g,
                            "task_ids": sorted(t["id"] for t in batch), "ts": when})
    # 完成庆祝：单张卡验收通过；它所在的批已经全完成时不单出（那批只出收工庆祝）
    for t in tasks:
        if t.get("state") != "done":
            continue
        when = t.get("done_at") or ""
        if when < cutoff or _goal_of(t) in wrapped_goals:
            continue
        out.append({"id": "celebrate:" + t["id"], "kind": "celebrate", "task_id": t["id"],
                    "title": t.get("title") or "", "ts": when})
    # 事故复盘：一张卡真跑过而没跑成（失败），或打回到顶（打回待定，round 就是打回的轮数）。
    # 「没开工」（state=failed 但 runs 表里一条记录都没有，开工前就被拦下）和「中断」的不算：
    # 猫压根没干过活，没什么好复盘的，首领在待办里重派或撤掉就行。
    for t in tasks:
        why = _postmortem_why(t)
        if not why:
            continue
        if why == "failed" and not runs_of_task.get(t["id"]):
            continue                     # 没开工：没跑过，不请复盘
        when = t.get("updated_at") or ""
        if when >= cutoff:
            out.append({"id": "postmortem:" + t["id"], "kind": "postmortem", "task_id": t["id"],
                        "title": t.get("title") or "", "why": _why_text(why), "ts": when})
    out.sort(key=lambda i: i["ts"], reverse=True)
    return out


def _why_text(why: str) -> str:
    """复盘邀请的原因：给用户看的那句（按当前语言）。"""
    if why == "failed":
        return i18n.t("office.scene.why_failed")
    if why.startswith("returned:"):
        return i18n.t("office.scene.why_returned", n=why.split(":", 1)[1])
    return why


def _standup_text(n: int, stations: list[str]) -> str:
    """站会那句话：几个工位被同一个目标凑到一块儿了。"""
    join = i18n.t("office.names_join")
    return i18n.t("office.standup", n=n, stations=join.join(stations))


def _postmortem_why(t: dict) -> str | None:
    """什么情况下出复盘邀请：失败（真跑过才算，见 _eligible 里的过滤）或打回满轮。"""
    if t.get("state") == "failed":
        return "failed"
    if t.get("state") == "returned":
        return "returned:%d" % max(1, int(t.get("round") or 1))
    return None


def invites(store: Store, now: str | None = None) -> list[dict]:
    """feed 里挂出来的邀请：满足条件、没被点过 / 关掉、最近 24 小时，最多 3 条。"""
    acked = store.kv_get(ACKS_KEY, {}) or {}
    return [i for i in _eligible(store, now) if i["id"] not in acked][:INVITE_MAX]


def compute(store: Store, settings: dict | None = None) -> dict:
    """office feed 的 scenes 块。scene_bubbles 关掉（默认开）时 invites 给空列表——场景本身画布照演，只是首领不冒邀请气泡。"""
    enabled = bool((settings or {}).get("scene_bubbles", True))
    return {"enabled": enabled, "idle_since": idle_since(store), "invites": invites(store) if enabled else []}


# ---- 邀请的点 / 关 ----
def ack(store: Store, invite_id: str, action: str) -> dict:
    """用户点了（play）或关掉（dismiss）一条邀请：记进 kv（重启不丢）+ 记一条动态；之后 feed 里不再出。
    id 不认识（不在最近 24 小时满足条件的邀请里）→ ok=False，HTTP 那层回 404。"""
    inv = next((i for i in _eligible(store) if i.get("id") == invite_id), None)
    if inv is None:
        return {"ok": False, "code": "unknown_invite", "text": i18n.t("office.scene.unknown", id=invite_id)}
    acks = store.kv_get(ACKS_KEY, {}) or {}
    acks[invite_id] = {"action": action, "ts": now_iso()}
    store.kv_set(ACKS_KEY, acks)
    kind = str(inv.get("kind") or "")
    name = i18n.t("office.scene." + KIND_NAMES.get(kind, kind))
    subject = inv.get("title") or inv.get("goal") or invite_id
    verb = "office.scene.played" if action == "play" else "office.scene.dismissed"
    store.event("scene_play" if action == "play" else "scene_dismiss", i18n.t(verb, name=name, subject=subject),
                data={"id": invite_id, "action": action, "kind": kind})
    return {"ok": True, "id": invite_id, "action": action}


# ---- 站会：同一个 goal 在 10 分钟内派 ≥ 2 张卡 ----
def counts_for_standup(store: Store, t: dict) -> bool:
    """这张卡算不算「这批里真派出去了」：撤掉 / 取消的不算；没开工（failed 且 runs 表里一条记录都没有）也不算。
    判断写法跟 facades/http.py 里 _event_line 判「没开工」那句一样：not store.runs_for_task(tid)。"""
    if t.get("state") == "cancelled":
        return False
    if t.get("state") == "failed" and not store.runs_for_task(str(t.get("id") or "")):
        return False
    return True


def note_assign(store: Store, task_id: str, station_id: str, goal) -> None:
    """派活后叫一次：同一个 goal 10 分钟内已经派过别的卡 → 记 / 并一条 standup 事件（带这批的猫和卡）。
    单张卡不出（照旧只是 assign）；第 3、4 张并进同一条，不再出新的。
    没开工（开工前被拦下）和撤掉 / 取消的卡不算「派过」；猫去重（同一只猫不数两次）；
    去重后只剩一只猫、或者只剩一张卡，就不开站会。"""
    g = norm_goal(goal)
    if not g:
        return
    cutoff = _cutoff(STANDUP_WINDOW_MIN / 60.0)
    peers = [t for t in store.list_tasks(limit=500)
             if t["id"] != task_id and (t.get("created_at") or "") >= cutoff and _goal_of(t) == g]
    peers = [t for t in peers if counts_for_standup(store, t)]      # 没开工 / 撤掉的卡不算
    if not peers:
        return
    stations = list(dict.fromkeys([t["assignee"] for t in peers] + [station_id]))   # 猫去重
    task_ids = list(dict.fromkeys([t["id"] for t in peers] + [task_id]))
    if len(stations) < 2 or len(task_ids) < 2:                       # 只剩一只猫 / 一张卡：不开站会
        return
    for e in store.events(200):                     # 这一批已经开过站会 → 并进去
        if e.get("kind") != "standup" or (e.get("ts") or "") < cutoff:
            continue
        try:
            data = json.loads(e.get("json") or "{}")
        except ValueError:
            continue
        if not isinstance(data, dict) or norm_goal(data.get("goal")) != g:
            continue
        kept = []                                   # 那批里没开工 / 撤掉的卡也不算数
        for old_id in [str(x) for x in (data.get("task_ids") or [])]:
            old_t = store.get_task(old_id)
            if old_t is not None and counts_for_standup(store, old_t):
                kept.append((old_id, old_t.get("assignee")))
        merged_ids = list(dict.fromkeys([i for i, _ in kept] + task_ids))
        merged_sts = list(dict.fromkeys([a for _, a in kept if a] + stations))
        store.event_update(e["id"], _standup_text(len(merged_ids), merged_sts),
                           {"goal": g, "stations": merged_sts, "task_ids": merged_ids})
        return
    store.event("standup", _standup_text(len(task_ids), stations),
                station_id, task_id, data={"goal": g, "stations": stations, "task_ids": task_ids})
