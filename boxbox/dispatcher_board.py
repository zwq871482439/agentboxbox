"""看板和待办：给人看的进度。"""
from __future__ import annotations

import datetime as _dt

from . import config, i18n, mcp_client, pi_config, tasks, tmpdir
from .dispatcher_const import REST_REASONS, WAIT_BUSY, WAIT_LEGACY, WAIT_NETWORK, WAIT_REASON_KEY, WAIT_REST
from .dispatcher_util import _every_min, _mins_since
from .store import now_iso


class BoardMixin:
    def queue_text(self, t: dict) -> str:
        """这张卡为什么在排队：写清楚等谁（看板 / 首领待办 / 卡详情 / 办公室同一句）。"""
        lg = self.lang()
        sid = str(t.get("assignee") or "")
        st = self.station(sid) or {}
        if not st.get("enabled", True):
            return i18n.t("board.queue.off", lg, sid=sid)
        rest = self.rest_of(sid)
        if rest:
            when = self.rest_hint(rest.get("hint") or "", lg)
            return i18n.t("board.queue.rest", lg, sid=sid, when=when)
        reason = (t.get("card") or {}).get(WAIT_REASON_KEY)
        if reason in (WAIT_BUSY, WAIT_LEGACY):
            return i18n.t("board.queue.busy", lg, sid=sid)   # 老版本留下的排队原因也按这个说
        if reason == WAIT_NETWORK:
            return i18n.t("board.queue.network", lg, sid=sid)
        if reason == WAIT_REST:
            return i18n.t("board.queue.back", lg, sid=sid)
        return i18n.t("board.queue.plain", lg)
    def board(self) -> list[dict]:
        states = self.store.station_states()
        lifetimes = self.store.station_lifetimes()   # Pi 工位没有外部会话握手：上岗 / 最近活动从 runs 表算
        clients = self.store.kv_get("station_client") or {}   # 真正连上来的那一家（握手时按 clientInfo 记下的）
        open_by_station = {}
        for t in self.store.list_tasks(state=",".join(tasks.OPEN_STATES)):
            open_by_station.setdefault(t["assignee"], []).append(t)
        # 歇着的工位（额度用完 / 被限流 / 接口连不上 / 服务端出错）：核心自动判、自动解除
        rest_all = self.resting()
        # 进程还在跑的猫：不许显示失败 / 离线
        alive = self._alive_stations()
        rows = []
        for st in config.stations():
            ss = states.get(st["id"], {})
            life = lifetimes.get(st["id"]) or {}
            mine = open_by_station.get(st["id"], [])
            cur = next((t for t in mine if t["state"] in ("dispatched", "running")), None)   # 排队的不算「在跑」
            queued_n = sum(1 for t in mine if t["state"] == "queued")          # 后面还排着几张
            queue_texts = [self.queue_text(t) for t in mine if t["state"] == "queued"]   # 排队写清楚等谁
            scheduled = st.get("runner") == "scheduled"
            last_sched = ss.get("last_scheduled_at")
            late = bool(scheduled and last_sched and _mins_since(last_sched) > 2 * _every_min(st))
            rest = rest_all.get(st["id"]) or None
            running = bool(cur) or st["id"] in alive        # 进程还在跑 = 在跑
            lg = self.lang()
            if scheduled:
                if not st.get("enabled", True):
                    word, code = i18n.t("board.word.off", lg), "off"
                elif not last_sched:
                    word, code = i18n.t("board.word.wait_sched", lg), "wait_sched"
                elif late:
                    word, code = i18n.t("board.word.sched_late", lg), "sched_late"
                elif cur and cur["state"] == "running":
                    word, code = i18n.t("board.word.running", lg), "running"
                else:
                    # 定时任务至少来过一回；可能有卡在排队
                    word, code = i18n.t("board.word.on_duty_sched", lg), "on_duty_sched"
            else:
                if not st.get("enabled", True):
                    # 已停用：只有用户手动关掉才是这个，不自动恢复；名下有排队的卡写清楚
                    word = i18n.t("board.word.off_queue", lg, n=queued_n) if queued_n \
                        else i18n.t("board.word.off", lg)
                    code = "off_queue" if queued_n else "off"
                elif rest:
                    # 歇着：出去玩了，预计 01:54 回来（额度用完）
                    word, code = self.rest_word(rest, lg), "rest"
                elif running:
                    word, code = i18n.t("board.word.running", lg), "running"
                elif st.get("role") == "leader":
                    word, code = i18n.t("board.word.on_duty", lg), "on_duty"
                else:
                    word, code = i18n.t("board.word.idle", lg), "idle"
                if code == "on_duty" and not ss.get("first_seen"):
                    # 首领从没来报到过，别说它「在岗」；工牌 / 详情 / 办公室都用这个词
                    word, code = i18n.t("board.word.not_connected", lg), "not_connected"
                if running and queued_n and st.get("enabled", True):
                    word = i18n.t("board.word.running_queue", lg, n=queued_n)    # 跑，后面还排着几张
                    code = "running_queue"
            minutes = None
            if cur:
                try:
                    minutes = int((_dt.datetime.now().astimezone() - _dt.datetime.fromisoformat(cur["created_at"])).total_seconds() // 60)
                except ValueError:
                    minutes = None
            # 首领那行的客户端 = 真正连上来的那一家（握手时报的 clientInfo），没连上过就是空
            if st.get("role") == "leader":
                client = clients.get(st["id"]) or ""
            else:
                client = st.get("client")
            rows.append({"id": st["id"], "role": st.get("role"), "client": client,
                         "client_label": mcp_client.label(client, lg),
                         "runner": st.get("runner"),
                         "slot": st.get("slot"), "enabled": st.get("enabled", True), "word": word,
                         "word_code": code,
                         "task_id": cur["id"] if cur else None,
                         "title": cur["title"] if cur else None, "minutes": minutes,
                         "open": len(mine),
                         # 排队只数还没开始跑的：正在跑 / 已交在验收的那张（task_id 这一条）不算排队
                         "queue": queued_n,
                         # 排队写清楚等谁（看板 / 首领待办 / 卡详情 / 办公室同一句）
                         "queue_text": queue_texts[0] if queue_texts else "",
                         "queue_texts": queue_texts,
                         # 歇着：出去玩了，预计 01:54 回来（额度用完）；办公室画布拿去画小钟
                         "rest": ({"reason": rest.get("reason"),
                                   "reason_text": i18n.t("rest.reason." + str(rest.get("reason") or ""), lg)
                                   if str(rest.get("reason") or "") in REST_REASONS else rest.get("reason_text"),
                                   "back_at": rest.get("back_at"), "hint": rest.get("hint") or "",
                                   "word": self.rest_word(rest, lg)} if rest else None),
                         "last_seen": ss.get("last_seen") or (life.get("last") if st.get("client") == "pi" else None),
                         # 第一次握手 = 上岗时间（工位页工牌用）；Pi 工位永远没握手 → runs 表最早一条 started 顶上
                         "first_seen": ss.get("first_seen") or (life.get("first") if st.get("client") == "pi" else None),
                         "last_scheduled_at": last_sched or None, "scheduled_late": late,
                         # Pi stations: whether the child process would see a key (stored secret or env var). Never the key.
                         "has_key": (pi_config.key_available(st) if st.get("client") == "pi" else None)})
        return rows
    def _unstarted(self, t: dict) -> bool:
        """这张 failed 的卡是「没开工」还是「真跑挂了」：runs 表里一条记录都没有 = 开工前就被拦下
        （仅内网连不上 / 启动器报错 / 启动器没回执都不插 runs），算没开工；有运行记录的是真跑过，算失败。"""
        return not self.store.runs_for_task(t["id"])
    def todo(self) -> dict:
        """首领的待办，按谁在等排序。每条带 who：
        leader = 首领和工位之间的事（验收、卡住、打回待定、失败、没开工），用户不用管；
        user = 只有用户能定的事（卡的 acceptance.review=user）。
        「没开工」（state=failed 但 runs 表里一条记录都没有，即开工前就被拦下）和「失败」分开列，
        每条都能用 resolve 重派或撤掉；count 是全部，user_count / leader_count 分开数，徽标、顶栏「等你」只看 user_count。"""
        items = []
        lg = self.lang()

        def _who(t: dict) -> str:
            rv = str(((t.get("card") or {}).get("acceptance") or {}).get("review", "leader"))
            return "user" if rv == "user" else "leader"

        # 每个工位最新一张卡的 created_at：失败 / 中断是不是「最新还没处理的那张」看它，
        # 更早的失败只留在待办里，不影响猫的样子（latest=False）
        latest_at: dict[str, str] = {}
        for t in self.store.list_tasks(limit=500):
            sid, ca = t["assignee"], (t.get("created_at") or "")
            if ca > latest_at.get(sid, ""):
                latest_at[sid] = ca

        for t in self.store.list_tasks(state="reviewing"):
            items.append({"kind": i18n.t("todo.kind.reviewing", lg), "kind_code": "reviewing", "who": _who(t),
                          "task_id": t["id"], "title": t["title"],
                          "station": t["assignee"], "since": t["delivered_at"] or t["updated_at"]})
        for t in self.store.list_tasks(state="blocked"):
            items.append({"kind": i18n.t("todo.kind.blocked", lg), "kind_code": "blocked", "who": "leader",
                          "task_id": t["id"], "title": t["title"],
                          "station": t["assignee"], "reason": t["returned_reason"], "since": t["updated_at"]})
        for t in self.store.list_tasks(state="returned"):
            items.append({"kind": i18n.t("todo.kind.returned", lg), "kind_code": "returned", "who": "leader",
                          "task_id": t["id"], "title": t["title"],
                          "station": t["assignee"], "reason": t["returned_reason"], "since": t["updated_at"]})
        for t in self.store.list_tasks(state="failed", limit=20):
            code = "unstarted" if self._unstarted(t) else "failed"   # 开工前被拦下的不是失败
            items.append({"kind": i18n.t("todo.kind." + code, lg), "kind_code": code, "who": "leader",
                          "task_id": t["id"], "title": t["title"], "station": t["assignee"],
                          "reason": t["returned_reason"], "since": t["updated_at"],
                          "latest": (t.get("created_at") or "") >= latest_at.get(t["assignee"], "")})
        for t in self.store.list_tasks(state="interrupted", limit=20):
            items.append({"kind": i18n.t("todo.kind.interrupted", lg), "kind_code": "interrupted", "who": "leader",
                          "task_id": t["id"], "title": t["title"], "station": t["assignee"],
                          "reason": t["returned_reason"], "since": t["updated_at"],
                          "latest": (t.get("created_at") or "") >= latest_at.get(t["assignee"], "")})
        # 排队的卡也要看得见：写清楚在等谁（跟看板 / 卡详情 / 办公室同一句）
        queued = [{"kind": i18n.t("todo.kind.queued", lg), "kind_code": "queued", "who": "leader",
                   "task_id": t["id"], "title": t["title"],
                   "station": t["assignee"], "reason": self.queue_text(t), "since": t["created_at"]}
                  for t in self.store.list_tasks(state="queued", limit=100)]
        idle_words = (i18n.t("board.word.idle", lg), i18n.t("board.word.on_duty_sched", lg))
        idle = [b["id"] for b in self.board() if b["role"] == "member" and b["enabled"] and b["word"] in idle_words]
        order = {"blocked": 0, "reviewing": 1, "returned": 2, "interrupted": 3, "unstarted": 4, "failed": 5}
        items.sort(key=lambda x: (0 if x["who"] == "user" else 1, order.get(x["kind_code"], 9), x.get("since") or ""))
        user_n = sum(1 for x in items if x["who"] == "user")
        return {"items": items, "idle_stations": idle, "queued": queued,
                "count": len(items), "user_count": user_n, "leader_count": len(items) - user_n}
    def nudge(self) -> dict | None:
        td = self.todo()
        if not td["count"]:
            return None
        return {"kind": "boxbox.nudge",
                "text": i18n.t("leader.nudge", self.lang(), n=td["count"], m=len(td["idle_stations"]))}
    def briefing(self, station_id: str) -> dict:
        seen = self.touch_leader(station_id)      # 首领的时间戳一路带到下面的 station_touch，两处对得上
        st = self.station(station_id) or {"id": station_id, "role": "member"}
        role = st.get("role", "member")
        lg = self.lang_of(station_id)
        if role == "leader":
            tools = "get_briefing, get_board, get_todo, get_task, assign, review, resolve, post, wait_for_update"
        else:
            tools = "get_briefing, get_board, get_task, report"
        board_txt = "\n".join("%s · %s · %s" % (b["id"], b["word"], b["title"] or "-") for b in self.board())
        tpl = tasks.localized("leader" if role == "leader" else "member", lg)
        text = tasks.render(tpl, station=station_id, role=role, task_id="", card="",
                            cwd=st.get("cwd") or "", report_path="", returned_reason="", round="", tools=tools, board=board_txt,
                            tmp_dir=str(tmpdir.root()))   # 没卡的时候给 tmp 根目录（具体卡目录随卡一起给）
        self.store.station_touch(station_id, last_seen=seen or now_iso())
        return {"station": station_id, "role": role, "tools": tools.split(", "), "text": text, "board": self.board(),
                "todo": self.todo() if role == "leader" else None}
