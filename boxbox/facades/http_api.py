"""页面和静态文件之外的接口：/api/* 和 /rpc/*。"""
from __future__ import annotations

import re
import threading
import urllib.parse

from .. import __version__, config, connectors, efficiency, i18n, pi_catalog, pi_config, providers, quota, runlog, scenes, tmpdir, tokens
from ..store import now_iso
from .http_const import (
    COPY_DECOR,
    COPY_SKIP,
)
from .http_core import _meta, _onboard_state, _task_view, normalize_role, running_task_ids, settings_patch
from .http_stations import _copy_name, _is_git_repo, _make_worktree, _running_cards, _station_detail, _station_errors, _summon


def handle_get(h, u, q):
    """GET 的 /api/* 路由。"""
    d = h.core.d
    store = d.store
    core_url = "http://127.0.0.1:%d" % h.server.server_port
    try:
            if u.path == "/api/stations":
                return h._json({"stations": d.board()})
            if u.path == "/api/stations/detail":                # 工位详情（查看详情抽屉）：完整配置（不含 key）+ 连接 + 调度记录 + 余量
                detail, code = _station_detail(d, (q.get("id") or [""])[0])
                return h._json(detail, code)
            if u.path == "/api/tasks":
                return h._json({"tasks": [{k: t.get(k) for k in ("id", "title", "kind", "assignee", "state", "round", "dispatcher", "created_at", "updated_at")}
                                             | {"wait_reason": (t.get("card") or {}).get("wait_reason"),   # 排队原因（等这只猫腾出手 / 等接口）
                                                "wait_text": d.wait_text(t)}   # 只有真在排队才写，跟卡详情同一句
                                             for t in store.list_tasks(state=(q.get("state") or [None])[0], limit=int((q.get("limit") or ["200"])[0]))]})
            m = re.match(r"^/api/tasks/(\d{8}-\d{3})$", u.path)
            if m:
                t = store.get_task(m.group(1))
                return h._json({"task": _task_view(store, t, d)} if t else {"error": "not found"}, 200 if t else 404)
            if u.path == "/api/todo":
                return h._json(d.todo())
            if u.path == "/api/interrupted":                # 上次退出 / 崩溃时中断的卡（这批还没问过用户）
                cards = d.interrupted_cards()
                return h._json({"cards": cards, "count": len(cards)})
            if u.path in ("/api/calls", "/api/timeline"):
                return h._json({"runs": store.recent_runs(int((q.get("limit") or ["50"])[0])), "events": store.events(int((q.get("limit") or ["100"])[0]))})
            if u.path == "/api/tokens":
                return h._json(tokens.summary(store, days=int((q.get("days") or ["7"])[0]), lang=i18n.lang()))
            if u.path == "/api/efficiency":
                return h._json(efficiency.report(store, days=(q.get("days") or ["7"])[0]))
            if u.path == "/api/providers":                  # 服务商清单（models.dev 快照）；lite=1 只要元信息
                if (q.get("lite") or ["0"])[0] in ("1", "true"):
                    return h._json(providers.meta())
                return h._json(providers.list_doc())
            if u.path == "/api/settings":
                return h._json(config.settings())
            if u.path == "/api/tmp":                            # 临时文件占多大
                return h._json({"bytes": tmpdir.size_bytes()})
            if u.path == "/api/data":                           # data\ 占多大，其中运行记录多少；正在整理没有
                return h._json(runlog.usage())
            if u.path == "/api/onboard/state":                  # 首页 / Onboard 都用它推导当前步骤
                return h._json(_onboard_state(d))
            if u.path == "/api/onboard/progress":                # 上岗进度（§5）：刷新、关掉后接着走
                return h._json(dict(ok=True, **config.onboard_progress()))
            if u.path == "/api/stations_def":
                return h._json({"stations": config.stations()})
            m = re.match(r"^/api/exchange/([^/]+)/log$", u.path)
            if m:                                              # 文件档工位的交换记录（onboard v0.2 §6）
                sid = urllib.parse.unquote(m.group(1))
                if config.station(sid) is None:
                    return h._json({"ok": False, "code": "station_unknown",
                                    "text": i18n.t("api.station_unknown", i18n.lang(), sid=sid)}, 404)
                return h._json({"station": sid, "items": store.exchange_log(sid, 20)})
            if u.path == "/api/health":
                return h._json({"ok": True, "now": now_iso(), "app_version": __version__})
            if u.path == "/api/doctor":
                from .. import doctor
                core_url = "http://127.0.0.1:%d" % h.server.server_port
                lg = i18n.lang()
                checks = doctor.run(core_url=core_url, project_dir=config.project_dir(),
                                    leader_client=d.leader_client(), lang=lg)
                sm = doctor.summary(checks)
                out = {"checks": [c.__dict__ for c in checks], "summary": sm}
                if (q.get("text") or ["0"])[0] in ("1", "true"):
                    out["text"] = doctor.diagnostics_text(checks, lang=lg,
                                                          extra={"core": core_url, "data": str(config.DATA)})
                return h._json(out)
            if u.path == "/api/connectors":
                sid = (q.get("station") or [""])[0]
                out = []
                for key, entry in connectors.load().items():
                    item = dict(entry, client=key)
                    if sid:
                        try:
                            item["status"] = connectors.status(key, project_dir=config.project_dir())
                        except Exception as e:  # noqa: BLE001
                            item["status"] = {"error": str(e)}
                    out.append(item)
                return h._json({"clients": out, "project_dir": config.project_dir(), "core": core_url})
            if u.path == "/api/connectors/check":
                # 等首领报到时的排查：只读看一眼 Cursor 是不是把 boxbox 关了（不列、不写别的软件的配置）
                sid = (q.get("station") or [""])[0]
                return h._json({"ok": True, "cursor_disabled": connectors.cursor_boxbox_disabled(),
                                   "mcp_url": connectors.mcp_url(sid, core_url) if sid else ""})
            if u.path == "/api/connectors/snippet":
                client = (q.get("client") or [""])[0]
                sid = (q.get("station") or [""])[0]
                if client not in connectors.load() or not sid:
                    return h._json({"ok": False, "code": "bad_args", "text": i18n.t("api.need_client_station", i18n.lang())}, 400)
                entry = connectors.load()[client]
                return h._json({"ok": True, "client": client, "snippet": connectors.snippet(client, sid, core_url),
                                   "format": entry.get("format"), "config_path": entry.get("config_path"),
                                   "mcp_menu_hint": connectors.hint_text(client, "menu", i18n.lang())})
            m = re.match(r"^/api/summon/(.+)$", u.path)
            if m:
                st = config.station(urllib.parse.unquote(m.group(1)))
                if st is None:
                    return h._json({"ok": False, "code": "station_unknown"}, 404)
                lang = (q.get("lang") or [i18n.lang()])[0]
                return h._json(dict(ok=True, **_summon(st, core_url, "en" if lang == "en" else "zh")))
            if u.path == "/api/pi/check":
                st = config.station((q.get("station") or [""])[0])
                if st is None or st.get("client") != "pi":
                    return h._json({"ok": False, "code": "station_unknown",
                                "text": i18n.t("api.not_pi", i18n.lang())}, 404)
                from ..runners.pi import PiOnceRunner
                runner = PiOnceRunner(st)
                # 默认真发一句最短的话（填错的 key 也会显示「连上了」）；live=0 只做本地检查（工位抽屉刷新用）
                live = (q.get("live") or ["1"])[0] not in ("0", "false")
                state, reason = runner.live_check() if live else runner.preflight()
                rec = {"state": state, "text": reason, "checked_at": now_iso()}   # 工位抽屉要显示最近一次检测时间
                h.core.d.store.kv_set("picheck:" + st["id"], rec)
                return h._json({"ok": state == "ok", **rec, "provider": pi_config.provider_name(st["id"]),
                                   "host": pi_config.host_of(st.get("pi") or {})})
            if u.path == "/api/office":
                try:
                    from .. import office_feed
                except ImportError:
                    return h._json({"error": i18n.t("api.office_feed_missing", i18n.lang())}, 404)
                meta = _meta(d)
                rows = store.events(40)
                assignee_of = {}
                for e in rows:
                    tid = e.get("task_id")
                    if tid and tid not in assignee_of:
                        t = store.get_task(tid)
                        assignee_of[tid] = t["assignee"] if t else None
                pend = config.pending_open_station()      # 第 6 条：刚招、还在开箱的工位（办公室先不画）
                stations_def = config.stations()
                quotas = {}
                for st in stations_def:
                    sid = str(st.get("id") or "")
                    if not sid or str((st.get("quota") or {}).get("mode") or "off") == "off":
                        continue
                    res = quota.read(store, st)
                    if isinstance(res, dict):
                        quotas[sid] = res
                feed = office_feed.build(meta, d.board(), d.todo(), tokens.summary(store, days=1, lang=i18n.lang()),
                                         stations_def,
                                         events=office_feed.office_events(rows, assignee_of),
                                         scenes=scenes.compute(store, config.settings()),
                                         pending_open=[pend] if pend else [],
                                         quotas=quotas)
                return h._json(feed)
            return h._json({"error": "not found"}, 404)
    except Exception as e:  # noqa: BLE001
        return h._json({"error": str(e)}, 500)


def handle_post(h, u, body):
    """POST 的 /api/* 和 /rpc/* 路由。"""
    try:
        if u.path == "/api/shutdown":                    # 核心自己收工：和托盘「退出」同一条路，就是 app.stop
            stop = getattr(h.server, "on_stop", None)    # 只有 app.start 起的核心挂得上
            if stop is None:
                return h._json({"ok": False, "code": "no_stopper",
                                "text": i18n.t("api.no_stopper", i18n.lang())}, 409)
            # 先把话回给调用方，隔半秒再收：app.stop 会把这个连接和数据库一起关掉
            h._json({"ok": True, "text": i18n.t("api.stopping", i18n.lang())})
            threading.Timer(0.5, stop).start()
            return None
        if u.path == "/api/window/show":                 # 又双击了一次 exe：叫已经开着的那个把窗口弹出来，不起第二个
            show = getattr(h.server, "on_show", None)    # 只有托盘起的核心挂得上（serve 起的没有窗口）
            if show is None:
                return h._json({"ok": False, "code": "no_window"}, 409)
            threading.Thread(target=show, name="boxbox-show", daemon=True).start()
            return h._json({"ok": True})
        m = re.match(r"^/api/tasks/(\d{8}-\d{3})/decide$", u.path)
        if m:                                            # 用户在看板上替首领拍板：通过 / 打回 / 再派一次 / 撤掉
            d, act = h.core.d, str(body.get("action") or "")
            note = str(body.get("note") or "").strip() or i18n.t("ev.by_user.note", i18n.lang())
            if act in ("accept", "return"):
                return h._json(d.review(m.group(1), act, note, "user"))
            if act in ("redispatch", "cancel"):
                return h._json(d.resolve(m.group(1), act, note, "user"))
            return h._json({"ok": False, "code": "bad_action", "text": i18n.t("api.bad_action", i18n.lang())}, 400)
        m = re.match(r"^/rpc/([a-z_]+)$", u.path)
        if m:
            sid = str(body.get("station") or "")
            # stdio 那条路：桥把客户端报的 clientInfo 一起带过来，核心照样归类记下
            info = (body.get("client_info") or {}) if isinstance(body.get("client_info"), dict) else {}
            if sid and info.get("name"):
                h._note_client(sid, [{"method": "initialize",
                                         "params": {"clientInfo": {"name": info.get("name")}}}], True)
            from .http_leader import begin_delivery
            begin_delivery()          # stdio 桥这条也一样：写进它的连接成功才算送到
            return h._json(h.core.call(m.group(1), sid, body.get("args") or {}))
        if u.path == "/mcp":                                  # MCP over HTTP：客户端配置里只写 url，不再起子进程占着 exe
            return h._mcp(body, (urllib.parse.parse_qs(u.query).get("station") or [""])[0])
        if u.path == "/api/scenes/ack":                      # –场景邀请的点 / 关：记进库 + 记动态，之后 feed 不再出
            action = str(body.get("action") or "")
            if action not in ("play", "dismiss"):
                return h._json({"ok": False, "code": "bad_action",
                                "text": i18n.t("api.bad_action", i18n.lang())}, 400)
            r = scenes.ack(h.core.d.store, str(body.get("id") or ""), action)
            return h._json(r, 200 if r.get("ok") else 404)
        if u.path == "/api/tmp/clean":                      # 立刻清临时文件（在跑的卡不动）
            running = running_task_ids(h.core.d.store)
            skipped = tmpdir.count_running(running)
            removed = tmpdir.clean(0, running)
            return h._json({"removed": removed, "skipped": skipped})
        if u.path == "/api/data/clean":                     # 结束的卡的运行记录：不等天数，现在就压（到天数的删）
            started = runlog.sweep_in_background(h.core.d.store, force_gzip=True)
            return h._json({"ok": True, "started": started, "cleaning": True})
        if u.path == "/api/import_old":                     # 设置页「从旧版导入」：换进旧版的猫、设置和卡
            from .. import import_old
            raw = body.get("path") if isinstance(body, dict) else ""
            out = import_old.import_from(h.core.d, raw if isinstance(raw, str) else "")
            return h._json(out, 200 if out.get("ok") else 400)
        if u.path == "/api/interrupted/resume":             # 「全部接着做」：接着上次的对话继续
            d = h.core.d
            ids = [str(i) for i in (body.get("ids") or []) if i]
            if body.get("all"):
                ids = [c["task_id"] for c in d.interrupted_cards()]
            return h._json(d.resume_interrupted(ids))
        if u.path == "/api/interrupted/dismiss":             # 「先不管」/「交给首领决定」
            d = h.core.d
            ids = [str(i) for i in (body.get("ids") or []) if i]
            if body.get("all"):
                ids = [c["task_id"] for c in d.interrupted_cards()]
            return h._json(d.dismiss_interrupted(ids, to_leader=bool(body.get("to_leader"))))
        if u.path == "/api/settings":
            s = config.settings()
            patch, errs = settings_patch(body, s, i18n.lang())
            if errs:
                return h._json({"ok": False, "code": "settings_invalid",
                                "text": i18n.t("api.settings_invalid", i18n.lang(), errs="; ".join(errs)), "errors": errs}, 400)
            s.update(patch)
            config.save_settings(s)
            return h._json(s)
        if u.path == "/api/stations_def":
            items = body.get("stations")
            if not isinstance(items, list):
                return h._json({"ok": False, "code": "bad_json"}, 400)
            config.save_stations(items)
            h.core.d.drop_idle_runners()   # 丢掉没在跑进程的运行器：在跑的卡不能误伤
            return h._json({"ok": True, "stations": config.stations()})
        if u.path == "/api/stations":                       # upsert one station (onboarding / settings)
            st = body.get("station") if isinstance(body.get("station"), dict) else body
            add_leader = bool(st.get("add_leader"))           # 工位页「再加一个首领」才带；上岗是换掉主首领
            st = {k: v for k, v in st.items() if k != "add_leader"}
            st = dict(st, role=normalize_role(st.get("role")))
            errs = _station_errors(st)
            if errs:
                return h._json({"ok": False, "code": "station_invalid",
                                "text": i18n.t("api.settings_invalid", i18n.lang(), errs="; ".join(errs)), "errors": errs}, 400)
            st = dict(st)
            st.setdefault("enabled", True)
            st.setdefault("quota", {"mode": "off"})
            if isinstance(st.get("pi"), dict):
                # 密钥只从 data/secrets.json 来、地址只认 base_url：这两个老字段存下来只会误导
                st["pi"] = {k: v for k, v in st["pi"].items() if k not in ("api_key_env", "host")}
            cur = config.stations()
            items = [s for s in cur if s.get("id") != st["id"]]
            old = next((s for s in cur if s.get("id") == st["id"]), None)     # 已有的猫不挪位置
            # 放回原来的位置：主首领是列表里第一个首领，改个样子不能把它挪到后面、让别的首领顶上来
            at = next((i for i, s in enumerate(cur) if s.get("id") == st["id"]), None)
            st = pi_catalog.keep_compat(old, st)          # 只改名字 / 样子：之前自动打开的兼容开关留着
            if st.get("role") == "leader":
                # 名字撞上打工猫就拒掉，不能把猫改成首领（接活方式对不上）
                if old is not None and old.get("role") != "leader":
                    return h._json({"ok": False, "code": "name_taken",
                                    "text": i18n.t("api.err_name_taken", i18n.lang(), sid=st.get("id"))}, 400)
                primary = config.leader_id()
                if old is None and not add_leader and primary and primary != st["id"]:
                    # 上岗时给首领换了名字：换掉主首领，不是再多一个（多一个首领只走「再加一个首领」）
                    at = next(i for i, s in enumerate(items) if s.get("id") == primary)
                    items.pop(at)
                    config.set_secret(primary, None)
                    h.core.d.runners.pop(primary, None)
                st["slot"] = config.LEADER_SLOT
            elif old is not None:
                st["slot"] = old.get("slot")
            else:                                              # 新猫：A→F 里第一个空位
                given = str(st.get("slot") or "")
                slot = given if given in config.SLOTS else config.next_slot(items)
                if slot is None:
                    return h._json({"ok": False, "code": "slots_full", "text": i18n.t("api.slots_full", i18n.lang())}, 400)
                st["slot"] = slot
            if at is None:
                items.append(st)
            else:
                items.insert(at, st)
            config.save_stations(items)
            # 重新打开一只猫：清掉它的歇着状态，排队的卡接着干
            if old is not None and not old.get("enabled", True) and st.get("enabled", True):
                h.core.d.clear_resting(st["id"])
                h.core.d.start_ready_queued()
            # 配置保存过了（哪怕只改了名字）：配置有问题的标记清掉，排队的卡用新配置开工
            if old is not None:
                h.core.d.release_config_bad(st["id"])
            h.core.d.drop_idle_runners()   # 丢掉没在跑进程的运行器：在跑的卡不能误伤
            return h._json({"ok": True, "station": st, "stations": config.stations()})
        if u.path == "/api/stations/copy":                     # 复制一只打工猫（工牌上的「复制」）
            sid = str(body.get("id") or "")
            src = config.station(sid)
            if src is None:
                return h._json({"ok": False, "code": "station_unknown",
                                "text": i18n.t("api.station_unknown", i18n.lang(), sid=sid)}, 404)
            if src.get("role") == "leader":
                return h._json({"ok": False, "code": "leader_no_copy",
                                "text": i18n.t("api.leader_no_copy", i18n.lang())}, 400)
            items = config.stations()
            slot = config.next_slot(items)
            if slot is None:
                return h._json({"ok": False, "code": "slots_full", "text": i18n.t("api.slots_full", i18n.lang())}, 400)
            new_id = _copy_name(str(src.get("id") or ""), items)
            st = {k: v for k, v in src.items() if k not in COPY_SKIP and k not in COPY_DECOR}
            # 复制出来的猫不共用原猫的工作目录：原目录是 git 仓库就在旁边建一个 worktree（分支 bx/<新工位>），
            # 建不了 / 没设目录 / 不是 git 仓库 → 新猫不设 cwd，派活时自动用 data/work/<新工位>，也不共用
            lg = i18n.lang()
            src_cwd = str(src.get("cwd") or "").strip()
            copy_note = ""
            if src_cwd and _is_git_repo(src_cwd):
                wt, why = _make_worktree(src_cwd, new_id)
                if wt:
                    st["cwd"], st["cwd_from"] = wt, src_cwd
                    copy_note = i18n.t("api.copy_note_wt", lg, path=wt, sid=new_id)
                else:
                    copy_note = i18n.t("api.copy_note_wt_fail", lg, why=why, sid=sid)
            elif src_cwd:
                copy_note = i18n.t("api.copy_note_nogit", lg, sid=sid)
            else:
                copy_note = i18n.t("api.copy_note_nodir", lg, sid=sid)
            st.update(id=new_id, role="member", slot=slot, enabled=src.get("enabled", True))
            items.append(st)
            config.save_stations(items)
            key = config.get_secret(sid)                       # API key 一起给新工位
            if key:
                config.set_secret(new_id, key)
            h.core.d.store.event("station_copy", i18n.t("api.station_copied", lg, src=sid, dst=new_id, slot=slot, note=copy_note), new_id)
            return h._json({"ok": True, "station": st, "stations": config.stations(),
                               "text": i18n.t("api.copied", lg, dst=new_id, slot=slot, note=copy_note)})
        if u.path == "/api/stations/delete":
            sid = str(body.get("id") or "")
            d = h.core.d
            if config.station(sid) is None:
                return h._json({"ok": False, "code": "station_unknown",
                                "text": i18n.t("api.station_unknown", i18n.lang(), sid=sid)}, 404)
            busy = _running_cards(d, sid)
            if busy and not body.get("confirm"):
                t = busy[0]
                return h._json({"ok": False, "code": "busy", "task_id": t["id"], "title": t["title"],
                                   "text": i18n.t("api.busy_delete", i18n.lang(), sid=sid, title=t["title"])}, 409)
            # 先中断（进程、卡、事件、首领信箱），再删工位：中断时要问得出首领是谁
            hit = d.interrupt_station(sid, "worker_deleted")
            gone = next((s for s in config.stations() if s.get("id") == sid), {})
            items = [s for s in config.stations() if s.get("id") != sid]
            config.save_stations(items)
            config.set_secret(sid, None)                       # a deleted station takes its key with it
            d.clear_config_bad(sid)
            d.runners.pop(sid, None)
            d.retired.pop(sid, None)                            # 退休的运行器也一并扔掉
            # 复制出来的猫删掉时不删它的目录和分支（怕删掉没合的活），回执和事件里说清楚
            text = ""
            lg = i18n.lang()
            if gone.get("cwd_from"):
                text = i18n.t("api.keep_dir", lg, path=gone.get("cwd") or "", sid=sid)
                d.store.event("station_deleted", i18n.t("ev.station_deleted", lg, sid=sid, note=text))
            else:
                d.store.event("station_deleted", i18n.t("ev.station_deleted", lg, sid=sid, note=""))
            out = {"ok": True, "stations": items, "interrupted": hit}
            if text:
                out["text"] = text
            return h._json(out)
        if u.path == "/api/reset":                              # 重置所有
            if not body.get("confirm"):
                return h._json({"ok": False, "code": "need_confirm",
                                "text": i18n.t("api.need_confirm", i18n.lang())}, 400)
            d = h.core.d
            running = d.store.list_tasks(state="dispatched,running")
            if running and not body.get("force"):
                return h._json({"ok": False, "code": "busy", "running": len(running),
                                   "text": i18n.t("api.busy_reset", i18n.lang(), n=len(running))}, 409)
            from .. import reset as _reset
            return h._json(_reset.reset_all(d))
        if u.path == "/api/onboard/progress":                   # 上岗进度（§5）：合并更新
            if any(k in body for k in ("step", "played", "draft")):
                p = config.save_onboard_progress(body.get("step"), body.get("played"), body.get("draft"))
            else:
                p = config.onboard_progress()
            return h._json(dict(ok=True, **p))
        if u.path == "/api/secrets":                           # write-only: {"station": id, "api_key": "..."}; empty = remove
            sid = str(body.get("station") or "")
            if not sid or config.station(sid) is None:
                return h._json({"ok": False, "code": "station_unknown",
                                "text": i18n.t("api.station_unknown", i18n.lang(), sid=sid)}, 404)
            key = str(body.get("api_key") or "").strip()
            if "\n" in key or "\r" in key:
                return h._json({"ok": False, "code": "bad_key",
                                "text": i18n.t("api.bad_key", i18n.lang())}, 400)
            config.set_secret(sid, key or None)
            h.core.d.release_config_bad(sid)                # 改了 key：配置有问题的标记清掉，排队的卡接着开
            runner = h.core.d.runners.get(sid)
            if not (runner is not None and getattr(runner, "live", None)):
                h.core.d.runners.pop(sid, None)             # next run rebuilds the env with the new key
            # 手上还有在跑的进程就别丢运行器（进程表在它手上，丢了在跑的卡会被误记失败）
            h.core.d.store.event("secret_set" if key else "secret_cleared",
                                 i18n.t("api.secret_set" if key else "api.secret_cleared", i18n.lang(), sid=sid), sid)
            return h._json({"ok": True, "station": sid, "has_key": bool(key)})
        if u.path == "/api/quota/check":                  # 现在查一次：同步查，结果存 kv，不带 key
            st = config.station(str(body.get("station") or ""))
            if st is None:
                return h._json({"ok": False, "code": "station_unknown",
                                "text": i18n.t("api.station_missing", i18n.lang())}, 404)
            return h._json(quota.localize(quota.check_station(st, h.core.d.store)))
        if u.path == "/api/providers/refresh":            # 更新服务商清单：要联网，先确认
            r = providers.refresh(bool(body.get("confirm")))
            if r.get("ok"):
                h.core.d.store.event("providers_refresh", i18n.t("api.providers_updated", i18n.lang(), text=r.get("text", "")))
            elif not r.get("needs_confirm"):
                h.core.d.store.event("providers_refresh", i18n.t("api.providers_failed", i18n.lang(), text=r.get("text", "")))
            return h._json(r)
        if u.path == "/api/connectors/install":
            client = str(body.get("client") or "")
            sid = str(body.get("station") or "")
            core_url = "http://127.0.0.1:%d" % h.server.server_port
            if client not in connectors.load() or not sid:
                return h._json({"ok": False, "code": "bad_args", "text": i18n.t("api.need_client_station", i18n.lang())}, 400)
            try:
                st = connectors.install(client, sid, core_url, project_dir=config.project_dir(), lang=i18n.lang())
            except ValueError as e:                        # GUI client: no file to write -> hand back the snippet
                return h._json({"ok": False, "code": "snippet_only", "text": str(e),
                                   "snippet": connectors.snippet(client, sid, core_url)})
            h.core.d.store.event("connector", i18n.t("api.connector_written", i18n.lang(),
                                                      sid=sid, client=client, path=st.get("path")), sid)
            return h._json(dict(ok=True, **st))
        return h._json({"error": "not found"}, 404)
    except Exception as e:  # noqa: BLE001
        return h._json({"ok": False, "code": "error", "text": str(e)}, 500)
