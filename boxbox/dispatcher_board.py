"""看板和待办：给人看的进度。"""
from __future__ import annotations

import datetime as _dt

from . import config, i18n, mcp_client, pi_config, stall, tasks, tmpdir
from .dispatcher_const import REST_REASONS, WAIT_BUSY, WAIT_LEGACY, WAIT_NETWORK, WAIT_REASON_KEY, WAIT_REST
from .dispatcher_util import _every_min, _mins_since
from .store import now_iso

_NUDGE_CARDS = 5


def _clip_title(title) -> str:
    """标题里的换行会把这一行拆开，看起来像另一张卡。"""
    return " ".join(str(title or "").split())[:30]


def _pending_lines(items: list[dict], lg: str) -> str:
    shown = items[:_NUDGE_CARDS]
    lines = [i18n.t("leader.nudge.pending", lg, n=len(items))]
    for it in shown:
        lines.append(i18n.t("leader.nudge.card", lg, tid=it.get("task_id") or "",
                            kind=it.get("kind") or "", title=_clip_title(it.get("title"))))
    extra = len(items) - len(shown)
    if extra:
        lines.append(i18n.t("leader.nudge.more", lg, n=extra))
    return "\n".join(lines)


def _model_id(st: dict) -> str:
    pi = st.get("pi")
    if isinstance(pi, dict) and pi.get("model"):
        return str(pi["model"])
    return ""


def _how_word(st: dict, lg: str) -> str:
    """接活方式跟工位页同一句：打工猫是用 API key 自动跑，或会话模式。"""
    if st.get("role") == "leader":
        return i18n.t("board.how.manual", lg)
    client, runner = st.get("client"), st.get("runner")
    if client == "pi" or runner == "once" or not (client or runner):
        return i18n.t("board.how.once", lg)
    return i18n.t("board.how.scheduled", lg)


def _clock(reset) -> str:
    """重置时间只留几点几分，和看板别处的钟点一个样子。"""
    if not reset:
        return ""
    s = str(reset).strip()
    if len(s) <= 5 and ":" in s and s.replace(":", "").isdigit():
        return s
    try:
        t = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if t.tzinfo is not None:
        t = t.astimezone()
    return t.strftime("%H:%M")


def _reset_passed(reset, now: _dt.datetime) -> bool:
    if not reset:
        return False
    try:
        then = _dt.datetime.fromisoformat(str(reset).replace("Z", "+00:00"))
    except ValueError:
        return False
    if then.tzinfo is None and now.tzinfo is not None:
        then = then.replace(tzinfo=now.tzinfo)
    return then <= now


def _window_word(name: str, label, lg: str) -> str:
    if name in ("h5", "week", "month"):
        return i18n.t("board.window." + name, lg)
    lab = str(label or "")
    if lab in ("h5", "week", "month", "tools", "plan"):
        return i18n.t("quota.window." + lab, lg)
    return lab or name


def _pick_window(windows: dict, now: _dt.datetime):
    """有 5 小时窗就只报它（爆发额度）；没有再报用得最紧的一个，不把整份窗口铺进回话。"""
    rows = []
    for name, w in windows.items():
        if not isinstance(w, dict):
            continue
        try:
            pct = float(w.get("pct"))
        except (TypeError, ValueError):
            continue
        reset = w.get("reset")
        if _reset_passed(reset, now):
            continue
        rows.append((str(name), pct, reset, w.get("label")))
    if not rows:
        return None
    for row in rows:
        if row[0] == "h5":
            return row
    rows.sort(key=lambda r: (-r[1], r[0]))
    return rows[0]


def _quota_line(store, st: dict, lg: str) -> str:
    """余量摘要。同一把 key 的猫读到同一份；key 不进这句话。"""
    if st.get("role") == "leader" or str((st.get("quota") or {}).get("mode") or "off") == "off":
        return ""   # 和办公室血条一个口径：没开查余量就不报，免得关掉以后还挂着旧数
    try:
        from . import quota
        res = quota.read(store, st)
    except Exception:  # noqa: BLE001 - 余量读坏了不能让看板整页没有
        return ""
    if not isinstance(res, dict) or not res.get("ok"):
        return ""
    windows = res.get("windows")
    if not isinstance(windows, dict):
        return ""
    picked = _pick_window(windows, _dt.datetime.now().astimezone())
    if picked is None:
        return ""
    name, pct, reset, label = picked
    window = _window_word(name, label, lg)
    n = int(round(pct))
    clock = _clock(reset)
    if clock:
        return i18n.t("board.quota.line", lg, window=window, n=n, t=clock)
    return i18n.t("board.quota.norest", lg, window=window, n=n)


def _board_line(b: dict) -> str:
    """简报里的一行，用的就是看板这一条上的字段。"""
    parts = [str(b.get("id") or ""), str(b.get("word") or "")]
    word = parts[1]
    for key in ("how", "model", "quota"):
        val = str(b.get(key) or "").strip()
        if val:
            parts.append(val)
    back = str(b.get("back") or "").strip()
    if back and back not in word:
        parts.append(back)
    parts.append(str(b.get("title") or "-"))
    return " · ".join(p for p in parts if p)


class BoardMixin:
    def queue_text(self, t: dict) -> str:
        """这张卡为什么在排队：写清楚等谁（看板 / 首领待办 / 卡详情 / 办公室同一句）。"""
        lg = self.lang()
        sid = str(t.get("assignee") or "")
        st = self.station(sid) or {}
        if not st.get("enabled", True):
            return i18n.t("board.queue.off", lg, sid=sid)
        if self.config_of(sid):
            return i18n.t("board.queue.config", lg, sid=sid)
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
    def wait_text(self, t: dict) -> str:
        """给卡详情的等待句。没在排队就留空：wait_reason 空着不能回落成「排队中」，
        不然在跑、待验收、已经做完的卡会被读成还在等。"""
        if str(t.get("state") or "") != "queued":
            return ""
        return self.queue_text(t)
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
        open_runs: dict[str, dict] = {}
        for r in self.store.open_runs():
            open_runs.setdefault(str(r.get("station") or ""), r)
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
                    word, code = self._work_word(lg, str(cur.get("dispatcher") or ""), 0)
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
                    word, code = self._work_word(lg, str((cur or {}).get("dispatcher") or ""), 0)
                elif st.get("role") == "leader":
                    word, code = i18n.t("board.word.on_duty", lg), "on_duty"
                else:
                    word, code = i18n.t("board.word.idle", lg), "idle"
                if code == "on_duty" and not ss.get("first_seen"):
                    # 首领从没来报到过，别说它「在岗」；工牌 / 详情 / 办公室都用这个词
                    word, code = i18n.t("board.word.not_connected", lg), "not_connected"
                if running and queued_n and st.get("enabled", True):
                    word, code = self._work_word(lg, str((cur or {}).get("dispatcher") or ""), queued_n)
                if code in ("running", "running_queue"):
                    hit = stall.board_word(open_runs.get(st["id"]), lg)
                    if hit:
                        word, code = hit
            if (st.get("role") != "leader" and self.config_of(st["id"])
                    and code not in ("running", "running_queue", "off", "off_queue", "stuck")):
                # 配置错了不会自己好：比「闲」和「歇着」都优先，免得还能被派活
                word, code = i18n.t("board.word.config", lg), "config"
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
                         "title": cur["title"] if cur else None,
                         "working_for": (cur.get("dispatcher") if cur else None) or None,
                         "minutes": minutes,
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
                         "has_key": (pi_config.key_available(st) if st.get("client") == "pi" else None),
                         # 模型、接活方式、歇着到几点、余量：首领挑猫用。余量是摘要，不含 key。
                         "model": _model_id(st), "how": _how_word(st, lg),
                         "back": (self.rest_when(rest.get("hint") or "", lg) if rest else ""),
                         "quota": _quota_line(self.store, st, lg)})
        return rows
    def _unstarted(self, t: dict) -> bool:
        """这张 failed 的卡是「没开工」还是「真跑挂了」：runs 表里一条记录都没有 = 开工前就被拦下
        （仅内网连不上 / 启动器报错 / 启动器没回执都不插 runs），算没开工；有运行记录的是真跑过，算失败。"""
        return not self.store.runs_for_task(t["id"])
    def _work_word(self, lg: str, who: str, queued_n: int) -> tuple[str, str]:
        """在跑的状态词。多个首领时写清这只猫在给谁干；只有一个首领时仍是「在跑」。"""
        many = len(config.leader_ids()) > 1 and bool(who)
        if queued_n and many:
            return i18n.t("board.word.running_queue_for", lg, n=queued_n, who=who), "running_queue"
        if queued_n:
            return i18n.t("board.word.running_queue", lg, n=queued_n), "running_queue"
        if many:
            return i18n.t("board.word.running_for", lg, who=who), "running"
        return i18n.t("board.word.running", lg), "running"
    def todo(self, for_leader: str | None = None) -> dict:
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

        def _keep(t: dict) -> bool:
            # 待办只给派这张卡的首领；没传 for_leader（看板 / 提醒）就全给
            if not for_leader:
                return True
            return (t.get("dispatcher") or "") == for_leader

        for t in self.store.list_tasks(state="reviewing"):
            if not _keep(t):
                continue
            item = {"kind": i18n.t("todo.kind.reviewing", lg), "kind_code": "reviewing", "who": _who(t),
                    "task_id": t["id"], "title": t["title"], "dispatcher": t.get("dispatcher") or "",
                    "station": t["assignee"], "since": t["delivered_at"] or t["updated_at"]}
            left = self._notes_left_reason(t["id"], lg)
            if left:
                item["reason"] = left   # 这一轮留言接了两次还没看完：交回时告诉首领
            items.append(item)
        for t in self.store.list_tasks(state="blocked"):
            if not _keep(t):
                continue
            items.append({"kind": i18n.t("todo.kind.blocked", lg), "kind_code": "blocked", "who": "leader",
                          "task_id": t["id"], "title": t["title"], "dispatcher": t.get("dispatcher") or "",
                          "station": t["assignee"], "reason": t["returned_reason"], "since": t["updated_at"]})
        for t in self.store.list_tasks(state="returned"):
            if not _keep(t):
                continue
            items.append({"kind": i18n.t("todo.kind.returned", lg), "kind_code": "returned", "who": "leader",
                          "task_id": t["id"], "title": t["title"], "dispatcher": t.get("dispatcher") or "",
                          "station": t["assignee"], "reason": t["returned_reason"], "since": t["updated_at"]})
        for t in self.store.list_tasks(state="failed", limit=20):
            if not _keep(t):
                continue
            code = "unstarted" if self._unstarted(t) else "failed"   # 开工前被拦下的不是失败
            items.append({"kind": i18n.t("todo.kind." + code, lg), "kind_code": code, "who": "leader",
                          "task_id": t["id"], "title": t["title"], "dispatcher": t.get("dispatcher") or "",
                          "station": t["assignee"], "reason": t["returned_reason"], "since": t["updated_at"],
                          "latest": (t.get("created_at") or "") >= latest_at.get(t["assignee"], "")})
        for t in self.store.list_tasks(state="interrupted", limit=20):
            if not _keep(t):
                continue
            items.append({"kind": i18n.t("todo.kind.interrupted", lg), "kind_code": "interrupted", "who": "leader",
                          "task_id": t["id"], "title": t["title"], "dispatcher": t.get("dispatcher") or "",
                          "station": t["assignee"], "reason": t["returned_reason"], "since": t["updated_at"],
                          "latest": (t.get("created_at") or "") >= latest_at.get(t["assignee"], "")})
        for run in self.store.open_runs():
            if not run.get("stall_kind"):
                continue
            t = self.store.get_task(run["task_id"])
            if t is None or t["state"] not in ("dispatched", "running") or not _keep(t):
                continue
            items.append({"kind": i18n.t("todo.kind.maybe_stuck", lg), "kind_code": "maybe_stuck", "who": "leader",
                          "task_id": t["id"], "title": t["title"], "dispatcher": t.get("dispatcher") or "",
                          "station": t["assignee"], "reason": stall.explain(run, lg), "since": run.get("stall_since")})
        # 排队的卡大家都能看见（猫是共用的），标明是哪个首领派的
        queued = [{"kind": i18n.t("todo.kind.queued", lg), "kind_code": "queued", "who": "leader",
                   "task_id": t["id"], "title": t["title"], "dispatcher": t.get("dispatcher") or "",
                   "station": t["assignee"], "reason": self.queue_text(t), "since": t["created_at"]}
                  for t in self.store.list_tasks(state="queued", limit=100)]
        idle = [b["id"] for b in self.board()
                if b["role"] == "member" and b["enabled"] and b["word_code"] in ("idle", "on_duty_sched")]
        order = {"maybe_stuck": 0, "blocked": 0, "reviewing": 1, "returned": 2, "interrupted": 3,
                 "unstarted": 4, "failed": 5}
        items.sort(key=lambda x: (0 if x["who"] == "user" else 1, order.get(x["kind_code"], 9), x.get("since") or ""))
        user_n = sum(1 for x in items if x["who"] == "user")
        return {"items": items, "idle_stations": idle, "queued": queued,
                "count": len(items), "user_count": user_n, "leader_count": len(items) - user_n}
    def nudge(self, for_leader: str | None = None) -> dict | None:
        td = self.todo(for_leader)
        if not td["count"]:
            return None
        lg = self.lang()
        text = i18n.t("leader.nudge", lg, n=td["count"], m=len(td["idle_stations"]))
        # 事件读过就不再重复；漏看一次交回，后面的回话里就再也没有这张卡。点了名的首领每次都重列还在等的
        if for_leader:
            text += "\n" + _pending_lines(td["items"], lg)
        return {"kind": "boxbox.nudge", "text": text}
    def briefing(self, station_id: str) -> dict:
        seen = self.touch_leader(station_id)      # 首领的时间戳一路带到下面的 station_touch，两处对得上
        st = self.station(station_id) or {"id": station_id, "role": "member"}
        role = st.get("role", "member")
        lg = self.lang_of(station_id)
        if role == "leader":
            tools = "get_briefing, get_board, get_todo, get_task, assign, review, resolve, post, wait_for_update"
        else:
            tools = "get_briefing, get_board, get_task, report"
        self.store.station_touch(station_id, last_seen=seen or now_iso())
        rows = self.board()
        # 当前看板这段和 get_board 同一份：简报正文里的一行就是这一条上的字段
        board_txt = "\n".join(_board_line(b) for b in rows)
        tpl = tasks.localized("leader" if role == "leader" else "member", lg)
        text = tasks.render(tpl, station=station_id, role=role, task_id="", card="",
                            cwd=st.get("cwd") or "", report_path="", returned_reason="", round="", tools=tools, board=board_txt,
                            tmp_dir=str(tmpdir.root()))   # 没卡的时候给 tmp 根目录（具体卡目录随卡一起给）
        return {"station": station_id, "role": role, "tools": tools.split(", "), "text": text, "board": rows,
                "todo": self.todo(station_id) if role == "leader" else None}
