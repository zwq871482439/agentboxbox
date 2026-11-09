# -*- coding: utf-8 -*-
"""办公室视图数据适配：核心 v2 的四份数据 → boxbox.office/1（工作计划 1.12）。

office/office.html 要的是 schema boxbox.office/1（样例 office/sample.json），
核心 v2 给的是 /api/meta、/api/stations 的 stations、/api/todo、/api/tokens，形状不同。

build() 是纯函数：不读文件、不碰网络、不抛异常，字段缺失一律走默认值，
派活人（facades 里接 /api/office 的那位）拿到 meta/board/todo/tokens 直接调用即可。

文字按当前语言出（lang 给 None 就是设置里的 ui_lang）：状态词、待办词、跑多久了，
都走 boxbox.i18n 的词表。比较状态一律用代码（word_code / kind_code），不认文字。
"""
from __future__ import annotations

import datetime as _dt
import json
import re

from . import i18n, looks

# 状态词走《文案规范》第 2 节，页面和看板同词表；英文在 i18n_data/office.py 里。

ACCENTS = ["#ffb347", "#5aa9ff", "#b48cff", "#ff7eb6", "#8fd18f", "#ffd166"]  # leader 固定第 1 个
SKIN_CATS = [2, 3, 4, 5, 6]  # leader 1，其余按出现顺序循环

# todo 的 kind_code，按严重度排（跟 dispatcher_board.todo 的 order 一致）
TODO_KINDS = ["blocked", "reviewing", "returned", "interrupted", "unstarted", "failed", "queued"]
# 看板这些词本身就是状态词，画布直接用；别的（比如首领的「在岗」）换成规范里的词
KNOWN_WORD_CODES = {"running", "running_queue", "idle", "off", "off_queue", "wait_sched",
                     "on_duty_sched", "sched_late", "not_connected", "rest", "stuck", "config"}
# 老数据只有中文 kind 时按它反查代码
LEGACY_KIND_CODES = {
    "待验收": "reviewing", "卡住": "blocked", "打回待定": "returned", "中断": "interrupted",
    "没开工": "unstarted", "失败": "failed", "排队": "queued",
}


def _lg(lang: str | None) -> str:
    return lang if lang in ("zh", "en") else i18n.lang()


def _ok_pct(meta: dict):
    """顶栏「成功率」那个数（/api/meta 的 success_7d.rate）换成百分数；没数据返回 None，不报 100%。"""
    rate = ((meta or {}).get("success_7d") or {}).get("rate")
    return round(rate * 100, 1) if isinstance(rate, (int, float)) else None


def minutes_ago(iso: str | None, now_iso: str, lang: str | None = None) -> str:
    """「3 分钟前」；iso 为 None 返回「从未」；解析不出来返回「未知」。"""
    lg = _lg(lang)
    if not iso:
        return i18n.t("office.never", lg)
    try:
        then = _dt.datetime.fromisoformat(str(iso))
        now = _dt.datetime.fromisoformat(str(now_iso))
    except (TypeError, ValueError):
        return i18n.t("office.unknown", lg)
    if then.tzinfo is None and now.tzinfo is not None:
        then = then.replace(tzinfo=now.tzinfo)
    mins = int((now - then).total_seconds() // 60)
    return i18n.t("office.minutes_ago", lg, n=max(0, mins))


def _num(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _model_of(row: dict, stations_def: list[dict] | None) -> str:
    """name/model 都用这个：工位定义里有 pi.model 就用它，没有退回 client。"""
    sid = row.get("id")
    for st in stations_def or []:
        if isinstance(st, dict) and st.get("id") == sid:
            pi = st.get("pi")
            if isinstance(pi, dict) and pi.get("model"):
                return str(pi["model"])
    return str(row.get("client") or "")


def _kind_code(item: dict) -> str:
    """待办那一条的代码：有 kind_code 就用它，老数据按中文反查。"""
    code = str(item.get("kind_code") or "")
    if code:
        return code
    return LEGACY_KIND_CODES.get(str(item.get("kind") or ""), "")


DRAWER_ITEMS_MAX = 20


def _drawer_items(todo: dict) -> list[dict]:
    """办公室「首领待办」抽屉里一条一条的明细：哪种事、哪张卡、从什么时候、为什么、哪只猫。
    点标题去看板：拍板（通过 / 打回 / 再派一次 / 撤掉）的按钮在看板上。"""
    out = []
    for it in (todo.get("items") or [])[:DRAWER_ITEMS_MAX]:
        if not isinstance(it, dict):
            continue
        out.append({"kind": str(it.get("kind") or ""), "title": str(it.get("title") or it.get("task_id") or ""),
                    "since": it.get("since") or "", "why": str(it.get("reason") or ""),
                    "source": str(it.get("station") or ""), "url": "/board"})
    return out


def _todo_by_station(todo: dict) -> dict:
    """{工位: [(kind_code, who), ...]}，按 TODO_KINDS 的严重度排。who 缺省按 leader 算（老核心没这个字段）。
    同工位更早的失败不再报二级（alerts 里拦了），所以这里每只猫顶多一张没处理的卡。"""
    out: dict = {}
    for it in (todo.get("items") or []):
        if not isinstance(it, dict):
            continue
        code = _kind_code(it)
        if code in ("failed", "interrupted") and it.get("latest") is False:
            continue                     # 旧卡：只留在首领待办，不进猫的状态
        sid = it.get("station")
        who = "user" if it.get("who") == "user" else "leader"
        if sid:
            out.setdefault(str(sid), []).append((code, who))
    for kinds in out.values():
        kinds.sort(key=lambda kw: (0 if kw[1] == "user" else 1, TODO_KINDS.index(kw[0]) if kw[0] in TODO_KINDS else 9))
    return out


def _tokens_by_station(tokens: dict) -> dict:
    return {str(r.get("station")): r for r in (tokens.get("stations") or []) if isinstance(r, dict) and r.get("station")}


# 有用量接口、核心能实测 token 的客户端；其它（Cursor 这种人在客户端里贴的）一律「不计」
TOKEN_CLIENTS = ("pi", "zcode", "claude-code", "codex")

# 画布上写的接活方式只有三种：首领手动开会话、打工猫用 API key 自动跑、会话模式
OFFICE_RUNNERS = ("manual", "once", "scheduled")


def _tok_of(row: dict, tk: dict, lang: str | None = None) -> dict:
    """办公室抽屉里的「实测 token」：有账本行就给数字（命中率 = 缓存读 / (输入 + 缓存读)），
    没有接口的工位给 na，页面写「无数据（不计）」而不是一排 0。"""
    if tk:
        cin, cr = _num(tk.get("tok_in")), _num(tk.get("tok_cr"))
        hit = int(round(cr * 100.0 / (cin + cr))) if (cin + cr) > 0 else 0
        return {"today": {"in": cin, "out": _num(tk.get("tok_out")), "cr": cr, "calls": _num(tk.get("runs")), "hit": hit}}
    if str(row.get("client") or "") in TOKEN_CLIENTS:
        return {"today": {"in": 0, "out": 0, "cr": 0, "calls": 0, "hit": 0}}
    return {"na": i18n.t("office.tok_na", _lg(lang), client=row.get("client") or "this client")}


def _quota_window_word(name: str, lang: str) -> str:
    """窗口名 → 给用户看的说法。认识的窗口翻词表，不认识的原样写。"""
    if name in ("h5", "week", "month"):
        return i18n.t("office.quota.window." + name, lang)
    return name


def _reset_passed(reset, now_iso: str) -> bool:
    """这个窗口的重置时间已经过了 → 旧数不算数，丢掉。解析不出来就当没过。"""
    if not reset:
        return False
    try:
        then = _dt.datetime.fromisoformat(str(reset))
        now = _dt.datetime.fromisoformat(str(now_iso))
    except (TypeError, ValueError):
        return False
    if then.tzinfo is None and now.tzinfo is not None:
        then = then.replace(tzinfo=now.tzinfo)
    return then <= now


def _quota_fields(mode: str, res, now_iso: str, lang: str) -> dict:
    """查余量的结果 → 猫头顶血条那几个字段。

    取已用最多的那个窗口（最卡脖子的）：画布按它画条，剩下的窗口用户自己看抽屉。
    没开查余量 / 没查过 / 查失败 / 窗口都过期了 → 画布不画（quota_mode=off）。"""
    off = {"quota_mode": "off", "quota_used_pct": None, "quota_left_pct": None,
           "quota_slot": "", "quota_source": i18n.t("office.quota_source", lang), "quota_reset": ""}
    if mode == "off" or not isinstance(res, dict) or not res.get("ok"):
        return off
    if not now_iso:
        now_iso = _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()
    windows = res.get("windows")
    if not isinstance(windows, dict):
        return off
    best = None
    for name, w in windows.items():
        if not isinstance(w, dict):
            continue
        try:
            pct = float(w.get("pct"))
        except (TypeError, ValueError):
            continue
        reset = str(w.get("reset") or "")
        if _reset_passed(reset, now_iso):
            continue
        if best is None or pct > best[1]:
            best = (str(name), pct, reset)
    if best is None:
        return off
    name, pct, reset = best
    used = round(pct)
    return {"quota_mode": mode, "quota_used_pct": used, "quota_left_pct": max(0, 100 - used),
            "quota_slot": _quota_window_word(name, lang),
            "quota_source": i18n.t("office.quota_source_plan", lang),
            "quota_reset": reset}


def _alert_maps(alerts: list | None) -> tuple[dict, dict, bool]:
    """meta.alerts（boxbox.alerts 算好的唯一一份）→ 每个工位头上的符号。级别不在这里重算。
    返回 (lvl1 {工位: alert}, lvl2 {工位: [kind, ...]}, leader_quiet)。"""
    lvl1: dict = {}
    lvl2: dict = {}
    quiet = False
    for a in alerts or []:
        if not isinstance(a, dict):
            continue
        if a.get("kind") == "leader_quiet":
            quiet = True
        sid = str(a.get("station") or "")
        if not sid:
            continue
        if a.get("level") == 1:
            lvl1.setdefault(sid, a)
        elif a.get("level") == 2:
            kind = str(a.get("kind") or "")
            lvl2.setdefault(sid, []).append(LEGACY_KIND_CODES.get(kind, kind))
    return lvl1, lvl2, quiet


def _state_of(row: dict, lvl1: dict, lvl2: dict) -> str:
    """v2 状态 → 页面 state，级别只看 meta.alerts（首领沉默不再由这里判断）。
    首领永不落 you（头上不冒符号）：它没反应由别的猫围过去冒 ? 表示；
    第 1 级 → you（头上 !）；第 2 级失败 / 中断 → fail（×），卡住 / 打回待定 / 等首领验收 → arch（…）。
    没开工（最新一张卡开工前被拦下）→ idle（等的样子，状态词写「没开工」），不是出错的样子。"""
    if not row.get("enabled", True):
        return "off"
    if row.get("role") == "leader":
        return "arch"
    if str(row.get("word_code") or "") == "config":
        return "config"          # 配置有问题：状态词用看板那句，不当成闲着
    if str(row.get("word_code") or "") in ("running", "running_queue", "stuck"):
        return "run"
    if row.get("rest"):        # 歇着：出去玩了，等的样子，不是出错
        return "rest"
    sid = str(row.get("id") or "")
    if sid in lvl1:
        return "you"
    kinds = lvl2.get(sid, [])
    if any(k in ("failed", "interrupted") for k in kinds):
        return "fail"
    if "unstarted" in kinds:
        return "idle"
    if kinds:
        return "arch"
    return "idle"


def _event_data(ev: dict) -> dict:
    """事件里带的结构化数据（json 列）；读不出来就当空的。"""
    data = ev.get("json")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            data = None
    return data if isinstance(data, dict) else {}


def office_events(rows: list, assignee_of: dict | None = None) -> list[dict]:
    """events 表的最近几十行 → 办公室画布要看的那几种「发生了什么」（开会和丢信分开）：
    - assign      首领第一次把一张卡交给工位 → 开会（首领和这只猫进会议室）
    - redispatch  同一张卡打回再派（第 n 轮）→ 丢信（信封飞过去，不开会）
    - post        工位之间留言 → 丢信
    - delivered / done  交活 / 完成（画布已有抱文件进会议室的动作，这里只是透传）
    - standup     同一个 goal 10 分钟内派出第 2 张卡（派活站会）：带这批的猫和卡，核心在派活时记的事件
    每条：{id, ts, kind, station(收信 / 被派的那只猫), from(发信方), task_id, round}。
    页面只看 id 大于上次见过的，所以 id 必须单调。"""
    assignee_of = assignee_of or {}
    out = []
    for e in rows or []:
        if not isinstance(e, dict):
            continue
        kind = str(e.get("kind") or "")
        tid = e.get("task_id")
        station = e.get("station")
        data = _event_data(e)
        item = None
        if kind == "assign":
            item = {"kind": "assign", "station": station, "from": None}
        elif kind == "standup":
            item = {"kind": "standup", "station": station, "from": None,
                    "goal": data.get("goal") or "", "stations": [str(x) for x in (data.get("stations") or [])],
                    "task_ids": [str(x) for x in (data.get("task_ids") or [])]}
        elif kind == "review" and str(data.get("verdict") or "") in ("return", "return_max"):
            to = assignee_of.get(tid) or data.get("to")
            if to:
                item = {"kind": "redispatch", "station": to, "from": station}
        elif kind == "post":
            to = data.get("to")
            if not to:
                parts = str(e.get("text") or "").split("→")
                to = parts[1].strip() if len(parts) == 2 else None
            if to:
                item = {"kind": "post", "station": to, "from": station}
        elif kind in ("delivered", "done"):
            item = {"kind": kind, "station": station, "from": None}
        if item is None:
            continue
        rnd = data.get("round")
        if rnd is None:
            m = re.search(r"第 (\d+) 轮", str(e.get("text") or ""))
            rnd = int(m.group(1)) if m else None
        item.update(id=_num(e.get("id")), ts=e.get("ts") or "", task_id=tid, round=rnd)
        out.append(item)
    out.sort(key=lambda x: x["id"])
    return out


def build(meta: dict, board: list[dict], todo: dict, tokens: dict, stations_def: list[dict] | None = None,
          events: list[dict] | None = None, scenes: dict | None = None,
          pending_open: list[str] | None = None, lang: str | None = None,
          quotas: dict | None = None) -> dict:
    """核心 v2 的 /api/meta、stations、todo、tokens → 一份 boxbox.office/1。
    events（office_events() 的结果）给了就原样放进 feed.events，画布按它决定开会 / 丢信；没给就不放这个键（老行为）。
    scenes（boxbox.scenes.compute 的结果）给了就放进 feed.scenes：全员空闲的起点 + 首领的庆祝 / 复盘邀请。
    工位配置里写了 look（猫 + 配饰）的，清洗后放进 channel.look（王冠只给首领）；没有 look 的老工位照老规矩轮流分猫。
    pending_open 里的工位（第 6 条：刚招、还在开箱）标成 channel.pending_open：画布先别画它，等开箱动画演完再出来。
    quotas 是查余量的结果 {工位: 结果}（结果形状见 boxbox.quota）；工位没开查余量就没这个键，画布不画血条。
    lang 给 None 就是设置里的当前语言。"""
    lg = _lg(lang)
    meta = meta if isinstance(meta, dict) else {}
    todo = todo if isinstance(todo, dict) else {}
    tokens = tokens if isinstance(tokens, dict) else {}
    now = meta.get("now") or ""
    lvl1, lvl2, leader_quiet = _alert_maps(meta.get("alerts"))
    kinds_by_station = _todo_by_station(todo)
    tok_by_station = _tokens_by_station(tokens)
    look_by_station = {str(s.get("id")): s.get("look") for s in stations_def or [] if isinstance(s, dict)}
    mode_by_station = {str(s.get("id")): str((s.get("quota") or {}).get("mode") or "off")
                        for s in stations_def or [] if isinstance(s, dict)}
    quotas = quotas if isinstance(quotas, dict) else {}
    pending_ids = {str(x) for x in (pending_open or [])}

    channels = []
    cat_i = 0
    for i, row in enumerate(board or []):
        if not isinstance(row, dict):
            continue
        sid = str(row.get("id") or "")
        lead = row.get("role") == "leader"
        kinds = kinds_by_station.get(sid, [])
        state = _state_of(row, lvl1, lvl2)
        if state == "rest":
            # 歇着：出去玩了，预计 01:54 回来（额度用完）
            state_word = str(row.get("word") or "") or i18n.t("office.state.rest", lg)
        elif state in ("fail", "you", "arch") and kinds:
            # 卡住 / 待验收 / 打回待定 / 失败，是给人看的原话
            state_word = i18n.t("office.todo." + kinds[0][0], lg) if kinds[0][0] else i18n.t("office.state." + state, lg)
        elif state == "idle" and kinds and kinds[0][0] == "unstarted":
            state_word = i18n.t("office.state.unstarted", lg)     # 等的样子，但状态词写清楚是没开工
        else:
            # board.word 能当状态词就原样用（「在岗」这种不是状态词，换成规范里的词）
            state_word = str(row.get("word") or "")
            if str(row.get("word_code") or "") not in KNOWN_WORD_CODES:
                state_word = i18n.t("office.state." + state, lg)
        tk = tok_by_station.get(sid) or {}
        if lead:
            accent, cat = ACCENTS[0], 1
        else:
            accent, cat = ACCENTS[i % len(ACCENTS)], SKIN_CATS[cat_i % len(SKIN_CATS)]
            cat_i += 1
        runner = str(row.get("runner") or "")
        ch = {
            "id": sid,
            "slot": row.get("slot") or "",      # 固定 7 个工位：画布按它放猫（首领 leader，打工猫 A–F）
            "role": "lead" if lead else "member",
            "label": (i18n.t("office.leader_label", lg, sid=sid) if lead else sid),
            "name": _model_of(row, stations_def),
            "cat_name": sid,   # 猫脚下画的名字 = 工位名（上岗时用户起的，比如「猫猫首领」）；name 是型号 / 客户端
            "model": _model_of(row, stations_def),
            "channel": i18n.t("office.runner." + runner, lg) if runner in OFFICE_RUNNERS else "",
            "route": row.get("runner"),
            "accent": accent,
            "state": state,
            "state_word": state_word,
            "state_sub": str(row.get("client") or ""),
            # 余量血条：调用方按额度账户填好的同一份结果，没查到就 off，画布不画
            **_quota_fields(mode_by_station.get(sid, "off"), quotas.get(sid), now, lg),
            "task_d": str(row.get("title") or ""),
            "tool": "",               # v2 暂无「最后用的工具」
            "queue": _num(row.get("queue") if row.get("queue") is not None else row.get("open")),   # 优先用 dispatcher 算好的：排队不含正在跑的那张
            "queue_items": [str(x) for x in (row.get("queue_texts") or [])],   # 排队写清楚等谁
            "rest": row.get("rest") or None,                                # 歇着：画布拿去画小钟
            "scheduled_late": bool(row.get("scheduled_late")),   # 定时任务超 2×every_min 没来
            "last_scheduled_at": row.get("last_scheduled_at") or None,
            "last": minutes_ago(row.get("last_seen"), now, lg),
            "tok": _tok_of(row, tk, lg),
            "skin": {"cat": cat},
            "pending_open": sid in pending_ids,   # 第 6 条：刚招、还在开箱 → 画布先不画它
        }
        if sid in look_by_station:            # 工位配了固定装扮就交给画布按它画；清洗掉不认识的槽位 / 配饰
            lk = looks.normalize(look_by_station[sid], lead)
            if lk:
                ch["look"] = lk
        channels.append(ch)

    counts = {k: 0 for k in TODO_KINDS}
    for it in (todo.get("items") or []):
        if not isinstance(it, dict):
            continue
        code = _kind_code(it)
        if code in counts:
            counts[code] += 1
    detail = i18n.t("office.todo_join", lg).join("%s %d" % (i18n.t("office.todo." + k, lg), counts[k])
                                                 for k in TODO_KINDS if counts[k])
    user_n = _num(todo.get("user_count"))

    out = {
        "schema": "boxbox.office/1",
        "fetched": now,
        "_note": "由 boxbox 核心 v2 的 /api/meta /api/stations /api/todo /api/tokens 拼出",
        "strip": {
            "calls_today": sum(_num(r.get("runs")) for r in (tokens.get("stations") or []) if isinstance(r, dict)),
            "ok_pct": _ok_pct(meta),   # 和顶栏同一个口径（近 7 天收尾的卡）；没有收尾的卡就是 None，页面显示「–」
            "running": _num(meta.get("running")),
            "total": len(board or []),
        },
        # arch = 首领的待办（和工位之间的事）；user_count 单独给出，页面只把这部分叫「等你」
        "arch": {"count": _num(todo.get("count")), "user_count": user_n,
                 "summary": i18n.t("office.arch_summary", lg, n=_num(todo.get("count")),
                                    detail=detail or i18n.t("office.arch_none", lg))
                            + (i18n.t("office.arch_user", lg, n=user_n) if user_n else ""),
                 "items": _drawer_items(todo)},
        # 画布只读这两样——提示条 / 头上符号按 alerts，首领没反应时别的猫围过去按 leader_quiet
        "alerts": [a for a in (meta.get("alerts") or []) if isinstance(a, dict)],
        "leader_quiet": leader_quiet,
        "leader": meta.get("leader"),
        "channels": channels,
        "background": [],             # v2 还没有后台通道
    }
    if events is not None:
        out["events"] = [e for e in events if isinstance(e, dict)]
    if scenes is not None:
        out["scenes"] = scenes if isinstance(scenes, dict) else {}
    return out
