"""核心工具分发：页面 / 首领用到的几个接口和它们的校验。"""
from __future__ import annotations

import datetime as _dt
import re

from .. import __version__, config, i18n, tasks, tmpdir
from ..store import now_iso
from .http_const import _HHMM, ROLE_ALIASES, RUNNING_STATES, SETTINGS_BOOLS, SETTINGS_INTS, TOOLS
from .http_leader import _leader_new, _wait_for_update


class Core:
    """Glue between facades and the dispatcher; every tool goes through call."""

    def __init__(self, dispatcher):
        self.d = dispatcher

    def call(self, tool: str, station: str, args: dict, transport: str = "") -> dict:
        d = self.d
        args = args or {}
        lg = d.lang_of(station) if hasattr(d, "lang_of") else i18n.lang()
        if tool not in TOOLS:
            return {"ok": False, "code": "unknown_tool", "text": i18n.t("tool.unknown", lg, name=tool)}
        st = config.station(station) if station else None
        if station and st is None:
            # 工位改过名而客户端里的连接设置还是旧名字：直接说清楚，不让一个没登记的名字混进动态和看板
            names = i18n.t("list.sep", lg).join(s["id"] for s in config.stations()) or i18n.t("api.no_station_yet", lg)
            return {"ok": False, "code": "unknown_station",
                    "text": i18n.t("tool.unknown_station", lg, sid=station, names=names)}
        role = (st or {}).get("role", "member")
        if role == "leader":
            # 首领每个工具调用都算「最近活动」：看板 / 办公室那行跟着走，沉默提醒不会误报
            d.touch_leader(station)
        if tool == "get_briefing":
            # 第一次握手：这个工位从没来过 → 记 first_seen + 发事件；任何角色都记。
            # 先记再出简报：简报里附的看板才会把它自己写成「在岗」而不是「没连上」
            if not ((d.store.station_states().get(station) or {}).get("first_seen")):
                d.store.station_touch(station, first_seen=now_iso())
                d.store.event("handshake_ok", i18n.t("ev.handshake_ok", lg, sid=station), station)
            out = d.briefing(station)
        elif tool == "get_board":
            out = {"ok": True, "board": d.board()}
        elif tool == "get_todo":
            if role != "leader":
                return {"ok": False, "code": "forbidden", "text": i18n.t("tool.leader_only", lg, tool="get_todo")}
            out = dict(ok=True, **d.todo())
        elif tool == "get_task":
            tid = str(args.get("task_id") or args.get("id") or "")
            if not tasks.TASK_ID_RE.match(tid):
                return {"ok": False, "code": "bad_task_id", "text": i18n.t("tool.bad_task_id", lg)}
            t = d.store.get_task(tid)
            if t is None:
                return {"ok": False, "code": "bad_task_id", "text": i18n.t("tool.no_task", lg)}
            if role != "leader" and t["assignee"] != station:
                return {"ok": False, "code": "forbidden", "text": i18n.t("tool.own_card_only", lg)}
            out = {"ok": True, "task": _task_view(d.store, t, d)}
        elif tool == "assign":
            if role != "leader":
                return {"ok": False, "code": "forbidden", "text": i18n.t("tool.leader_only", lg, tool="assign")}
            out = d.assign(str(args.get("station") or ""), args.get("card") or {}, station)
        elif tool == "review":
            out = d.review(str(args.get("task_id") or ""), str(args.get("verdict") or ""), str(args.get("note") or ""), station,
                           feedback=str(args.get("feedback") or ""))
        elif tool == "resolve":
            out = d.resolve(str(args.get("task_id") or ""), str(args.get("action") or ""), str(args.get("note") or ""), station)
        elif tool == "report":
            out = d.report(str(args.get("task_id") or ""), str(args.get("status") or ""), str(args.get("summary") or ""), station)
        elif tool == "post":
            to = str(args.get("to") or "")
            if not to or not config.station(to):
                return {"ok": False, "code": "station_unknown", "text": i18n.t("tool.no_receiver", lg)}
            d.store.post_message(station, to, str(args.get("text") or ""))
            d.store.event("post", i18n.t("ev.post", lg, by=station, to=to), station, data={"to": to})
            out = {"ok": True, "text": i18n.t("tool.posted", lg)}
        elif tool == "wait_for_update":
            if role != "leader":
                return {"ok": False, "code": "forbidden", "text": i18n.t("tool.leader_only", lg, tool="wait_for_update")}
            out = _wait_for_update(d, station, args)
        else:  # read_inbox
            out = {"ok": True, "messages": d.store.read_inbox(station)}
        n = d.nudge()
        if role == "leader":
            # 上岗话瘦身到 4 句以后，首领的规则靠每次工具回话里的 _boxbox 持续提醒（打工猫不带）。
            # 经 /mcp 按地址连上来的（没发 initialize 的 HTTP 兜底）多带 http_tips，
            # 第一次 get_briefing 问一次「要不要加进连接设置」，之后不再问。stdio MCP 那条路不带这些。
            box = {"rules": i18n.t("leader.rules", lg)}
            if transport == "http":
                box["http_tips"] = http_tips(lg)
                if tool == "get_briefing":
                    kv = d.store.kv_get("mcp_asked") or {}
                    if station and not kv.get(station):
                        box["mcp_hint"] = i18n.t("leader.mcp_hint", lg)
                        kv[station] = now_iso()
                        d.store.kv_set("mcp_asked", kv)
            if n:
                box["nudge"] = n
            evs = _leader_new(d, station)
            if evs:
                box["events"] = evs
            out["_boxbox"] = box
        elif n:
            out["_boxbox"] = {"nudge": n}
        return out
def normalize_role(role):
    """TeamLeader / 首领 → leader，Team Member / 打工猫 → member；认不出的原样返回（交给校验报错）。"""
    if isinstance(role, str):
        return ROLE_ALIASES.get(role.strip().lower(), role)
    return role
def _as_int(v):
    """整数或写成整数的字符串 → int；布尔、小数、别的字都不算。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str) and re.fullmatch(r"\s*-?\d+\s*", v):
        return int(v)
    return None
def settings_patch(body: dict, cur: dict, lang: str | None = None) -> tuple[dict, list[str]]:
    """校验 POST /api/settings 的改动，返回（要写进去的键值, 错误）。有错就一个都不写。"""
    errs: list[str] = []
    out: dict = {}
    for k, v in body.items():
        if k not in config.SETTINGS_DEFAULTS:
            continue
        if k in SETTINGS_INTS:
            lo, hi = SETTINGS_INTS[k]
            n = _as_int(v)
            if n is None or n < lo or (hi is not None and n > hi):
                errs.append(i18n.t("api.set_int", lang, key=k,
                                    range=(("%d–%d" % (lo, hi)) if hi else (">= %d" % lo))))
            else:
                out[k] = n
        elif k in SETTINGS_BOOLS:
            if not isinstance(v, bool):
                errs.append(i18n.t("api.set_bool", lang, key=k))
            else:
                out[k] = v
        elif k == "office_theme_times":
            if not isinstance(v, dict) or any(t not in ("dawn", "day", "dusk", "night") for t in v):
                errs.append(i18n.t("api.set_theme_keys", lang))
            elif any(not isinstance(x, str) or not _HHMM.match(x) for x in v.values()):
                errs.append(i18n.t("api.set_theme_time", lang))
            else:
                out[k] = dict(cur.get(k) or {}, **v)             # 只改给了的那几个时间点
        elif k == "onboard":
            if not isinstance(v, dict):
                errs.append(i18n.t("api.set_onboard", lang))
            else:
                out[k] = v
        elif k == "ui_lang":
            if v not in ("zh", "en"):
                errs.append(i18n.t("api.set_lang", lang))
            else:
                out[k] = v
        else:
            out[k] = v
    return out, errs
def http_tips(lang: str | None = None) -> str:
    r"""HTTP 首领的细节（临时文件放程序目录 tmp\leader，不是系统临时目录，也别进用户的项目目录）。"""
    return i18n.t("leader.http_tips", lang, tmp=tmpdir.leader_tmp())
def _task_view(store, t: dict, d=None) -> dict:
    v = {k: t.get(k) for k in ("id", "title", "kind", "assignee", "state", "round", "dispatcher", "created_at", "updated_at",
                                 "delivered_at", "done_at", "returned_reason")}
    v["interrupt_reason"] = t.get("returned_reason") if t.get("state") == "interrupted" else None
    v["card"] = t.get("card")
    v["wait_reason"] = (t.get("card") or {}).get("wait_reason")   # 排队原因（等这只猫腾出手 / 等接口 / 等歇着的猫回来）
    v["wait_text"] = (d.queue_text(t) if d is not None else "")   # 排队写清楚等谁（看板 / 待办 / 办公室同一句）
    v["runs"] = [{k: r.get(k) for k in ("run_id", "attempt", "runner", "pid", "started", "ended", "exit", "status",
                                        "commits", "tokens_json")} for r in store.runs_for_task(t["id"])]
    v["tokens"] = store.tokens_for_task(t["id"])
    v["report"] = tasks.read_report(t["id"])
    try:
        v["review_md"] = (tasks.card_dir(t["id"]) / "review.md").read_text(encoding="utf-8")
    except OSError:
        v["review_md"] = ""
    v["events"] = store.events(50, task_id=t["id"])
    return v
def _onboard_state(d) -> dict:
    """Onboard 当前该显示第几步（docs/onboard-v0.2.md §3）：不存向导状态，全部从数据推导。
    step 0 = 进办公室（日常首页）。"""
    stations = config.stations()
    leader = next((s for s in stations if s.get("role") == "leader"), None)
    first_seen = ((d.store.station_states().get(leader["id"]) or {}).get("first_seen")) if leader else None
    no_leader = leader is None
    leader_unshaken = bool(leader) and not first_seen
    no_member = not any(s.get("role") == "member" for s in stations)
    skipped_member = bool(config.settings().get("skipped_member"))
    step = 1 if no_leader else (4 if leader_unshaken else (6 if no_member and not skipped_member else 0))
    link = (d.store.kv_get("station_link") or {}).get(leader["id"]) if leader else None
    return {"step": step, "no_leader": no_leader, "leader_unshaken": leader_unshaken,
            "no_member": no_member, "skipped_member": skipped_member,
            "leader": leader["id"] if leader else None,
            "leader_link": link}           # mcp = 客户端里 MCP 连上了；http = 走的那段话里的兜底（MCP 没连上）
def _meta(d) -> dict:
    store = d.store
    open_tasks = store.list_tasks(state=",".join(tasks.OPEN_STATES))
    running = [t for t in open_tasks if t["state"] in ("dispatched", "running")]
    today = now_iso()[:10]
    done_today = [t for t in store.list_tasks(state="done", limit=500) if (t.get("done_at") or "").startswith(today)]
    # 顶栏「成功率」：近 7 天收尾的卡里，完成 ÷（完成 + 真跑挂了）；没有收尾的卡就是 None（页面显示「—」）
    # 算真跑完的：没开工（failed 且 runs 表里没有运行记录）不算失败；中断 / 撤掉的本来就不在 done,failed 里
    since = (_dt.datetime.now() - _dt.timedelta(days=7)).isoformat(timespec="seconds")
    closed = [t for t in store.list_tasks(state="done,failed", limit=1000) if (t.get("updated_at") or "") >= since]
    counted = [t for t in closed if t["state"] == "done" or store.runs_for_task(t["id"])]
    ok_n = sum(1 for t in counted if t["state"] == "done")
    from .. import alerts
    return {"version": 2, "now": now_iso(), "running": len(running), "open": len(open_tasks), "done_today": len(done_today),
            "success_7d": {"done": ok_n, "failed": len(counted) - ok_n,
                           "rate": round(ok_n / len(counted), 3) if counted else None},
            "alerts": alerts.compute(d),   # 全站提醒唯一出口：页面 / 托盘 / 办公室只读这里
            "badge": store.kv_get("badge") or {}, "leader": config.leader_id(),
            "leader_last_seen": d.leader_last_seen, "data": str(config.DATA), "app_version": __version__}
def running_task_ids(store) -> list[str]:
    """还在跑（或还能接着跑）的卡号。"""
    rows = store.list_tasks(state=RUNNING_STATES, limit=1000)
    return [str(r.get("id")) for r in rows if r.get("id")]
