# -*- coding: utf-8 -*-
"""全站提醒唯一出口：一套分级，只在这一个函数里算。

页面（顶栏 / 动态 / 看板）、托盘、办公室都不许自己再算级别，一律读 /api/meta 里的 alerts。
compute(dispatcher) -> list[dict]，每条：
    {"level": 1|2, "kind": ..., "station": 工位名, "task_id": ..., "title": 卡标题,
     "text": 说给用户的话, "action": 用户该做什么（第 2 级为空）, "action_id": 可选，如 "summon"}

第 1 级「要你处理」（只有用户能做的事）：
    review_user      验收人是用户的卡 → 去看板点「通过」或「打回」
    scheduled_late   定时任务没按时来 → 去客户端里看看定时任务还在不在
    leader_quiet     首领自己有待办，且 ≥ wake_min 分钟没来调工具（首领调什么工具都算它来过）→ 复制一段话叫它回来
    leader_shared    两个对话在交替用同一个首领 → 去工位页再加一个首领，待办和验收才分得开
第 2 级「首领在处理」：todo 里 who=leader 的（失败 / 卡住 / 打回待定 / 等首领验收），无 action。
第 3 级「普通」（开工、完成、派活、开会）不进 alerts。
"""
from __future__ import annotations

import datetime as _dt

from . import config, i18n, leader_sessions

# 第 2 级的说法：todo 的 kind_code → 「A猫 的卡…了，首领在处理」（没开工 = 开工前被拦下，不算失败）
LEVEL2_KEYS = {"failed": "failed", "blocked": "blocked", "returned": "returned",
               "reviewing": "reviewing", "interrupted": "interrupted", "unstarted": "unstarted",
               "maybe_stuck": "maybe_stuck"}


def _mins_since(iso) -> float | None:
    """距现在多少分钟；没给 / 解析不出来返回 None（= 从没来过，按沉默算）。"""
    if not iso:
        return None
    try:
        return (_dt.datetime.now().astimezone() - _dt.datetime.fromisoformat(str(iso))).total_seconds() / 60
    except (TypeError, ValueError):
        return None


def compute(dispatcher) -> list[dict]:
    d = dispatcher
    lg = d.lang() if hasattr(d, "lang") else i18n.lang()
    items = [it for it in (d.todo().get("items") or []) if isinstance(it, dict)]
    out: list[dict] = []
    for it in items:
        station = str(it.get("station") or "")
        title = str(it.get("title") or "")
        kind = str(it.get("kind_code") or it.get("kind") or "")
        if it.get("who") == "user":
            out.append({"level": 1, "kind": "review_user", "station": station, "task_id": it.get("task_id"),
                        "title": title, "text": i18n.t("alert.review_user", lg, title=title),
                        "action": i18n.t("alert.review_user.action", lg)})
        else:
            # 同工位有更新的卡：这张旧失败 / 旧中断不出第 2 级，免得猫的样子一直滑不掉
            if kind in ("failed", "interrupted") and it.get("latest") is False:
                continue
            how = i18n.t("alert.level2." + kind, lg) if kind in LEVEL2_KEYS else kind
            out.append({"level": 2, "kind": kind, "station": station, "task_id": it.get("task_id"),
                        "title": title, "text": i18n.t("alert.leader_handling", lg, station=station, how=how),
                        "action": ""})
    bads = d.config_bads() if hasattr(d, "config_bads") else {}
    for sid, entry in (bads or {}).items():
        why = str((entry or {}).get("why") or "")
        out.append({"level": 1, "kind": "config_bad", "station": str(sid), "task_id": None, "title": "",
                    "text": i18n.t("alert.config_bad", lg, station=sid, why=why),
                    "action": i18n.t("alert.config_bad.action", lg)})
    for b in d.board():
        if isinstance(b, dict) and b.get("scheduled_late"):
            out.append({"level": 1, "kind": "scheduled_late", "station": str(b.get("id") or ""), "task_id": None,
                        "title": "", "text": i18n.t("alert.scheduled_late", lg, station=b.get("id")),
                        "action": i18n.t("alert.scheduled_late.action", lg)})
    # 每个首领只按自己派的卡算沉默。主首领的「来过」仍是全局 leader_last_seen（只有一个首领时和原来一样）
    wake = int(config.settings().get("wake_min", 30))
    primary = config.leader_id()
    states = d.store.station_states() if hasattr(d, "store") else {}
    for leader in config.leader_ids():
        leader_n = sum(1 for it in items if it.get("who") != "user"
                       and (str(it.get("dispatcher") or "") or primary) == leader)
        if leader_n <= 0:                             # 这个首领没有待办时不算它没反应
            continue
        if leader == primary:
            silent = _mins_since(d.leader_last_seen)
        else:
            silent = _mins_since((states.get(leader) or {}).get("last_seen"))
        if silent is None or silent >= wake:
            out.append({"level": 1, "kind": "leader_quiet", "station": leader, "task_id": None, "title": "",
                        "text": i18n.t("alert.leader_quiet", lg),
                        "action": i18n.t("alert.leader_quiet.action", lg), "action_id": "summon"})
    for leader in config.leader_ids():
        if leader_sessions.shared(d, leader):
            out.append({"level": 1, "kind": "leader_shared", "station": leader, "task_id": None, "title": "",
                        "text": i18n.t("alert.leader_shared", lg, station=leader),
                        "action": i18n.t("alert.leader_shared.action", lg), "action_id": "add_leader"})
    order = {"config_bad": 0, "review_user": 1, "leader_shared": 1, "scheduled_late": 2, "leader_quiet": 3}
    out.sort(key=lambda a: (a["level"], order.get(a["kind"], 9)))
    return out


def leader_quiet(alerts: list[dict]) -> bool:
    return any(isinstance(a, dict) and a.get("kind") == "leader_quiet" for a in alerts or [])
