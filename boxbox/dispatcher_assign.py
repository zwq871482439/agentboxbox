"""派卡：派活、开工、排队等谁。"""
from __future__ import annotations

import datetime as _dt
import json
import os
import time

from . import config, exchange, gates, i18n, pi_config, scenes, tasks, tmpdir
from . import feedback as _feedback
from .dispatcher_const import CONFLICT_STATES, IFACE_WHY, RESUME_AT, RESUME_SESSION, WAIT_BUSY, WAIT_LEGACY, WAIT_NETWORK, WAIT_REASON_KEY, WAIT_REST
from .dispatcher_util import _default_workdir, _git_head, _prepare_resume, _st_lang
from .runners import RunResult
from .store import now_iso


class AssignMixin:
    def assign(self, station_id: str, card: dict, by: str) -> dict:
        self.touch_leader(by)
        lg = self.lang()
        self.start_ready_queued()   # 先把排队里能开工的开起来（比如核心重启后 nobody 触发）
        st = self.station(station_id)
        if st is None:
            return self._ack("station_unknown", i18n.t("ack.station_unknown", lg, sid=station_id))
        if st.get("role") != "member":
            return self._ack("not_member", i18n.t("ack.not_member", lg, sid=station_id))
        if not st.get("enabled", True):
            return self._ack("station_disabled", i18n.t("ack.station_disabled", lg, sid=station_id), exit=14)
        errs = tasks.validate_card(card, lg) + gates.validate_gates(card, lang=lg)
        if errs:
            return self._ack("card_incomplete", i18n.t("ack.card_incomplete", lg, errs="; ".join(errs)), errors=errs)
        # 卡上自己写了工作目录、而这个目录不在：直接拒收说清楚，别等开工失败后报成「工位不通」
        card_cwd = str((card or {}).get("cwd") or "").strip()
        if card_cwd and not os.path.isdir(card_cwd):
            return self._ack("bad_cwd", i18n.t("ack.bad_cwd", lg, cwd=card_cwd))
        with self.lock:
            dup = self._find_open(station_id, tasks.normalize_title(card))
            if dup:
                return self._ack("already_running", i18n.t("ack.already_running", lg, sid=station_id, title=dup["title"],
                                                             state=dup["state"], at=dup["created_at"][11:16]),
                                 task_id=dup["id"], state=dup["state"])
            runner = self.runner_for(st)
            if runner is None:
                return self._ack("no_runner", i18n.t("ack.no_runner", lg, sid=station_id,
                                                     client=st.get("client"), runner=st.get("runner")))
            task_id = self.store.next_task_id()
            card = dict(card)
            card.update(id=task_id, assignee=station_id, created_by=by, dispatcher=card.get("dispatcher") or by,
                        created_at=now_iso(), round=int(card.get("round") or 1), state="dispatched")
            if not card.get("cwd"):
                # 卡上没写就用工位登记的；工位也没登记就给一个默认目录 data/work/<工位>（工作目录不该逼用户填）
                card["cwd"] = st.get("cwd") or str(_default_workdir(station_id))
            card.setdefault("title", tasks.normalize_title(card))
            # 定时任务工位（文件档）：先算交换文件里这张卡的长度，超了就不派（不写任何东西，也没建卡）
            prompt = self._member_prompt(st, task_id, card)
            if runner.mode == "scheduled":
                text = exchange.render_card(task_id, int(card["round"]), card.get("cwd") or "",
                                            tasks.card_dir(task_id) / "report.md", prompt,
                                            self.lang_of(station_id))
                if len(text) > exchange.PROMPT_MAX_CHARS:
                    return self._ack("card_incomplete", i18n.t("ack.card_too_long", lg, n=len(text),
                                                               max=exchange.PROMPT_MAX_CHARS))
            path = tasks.write_card(task_id, card)
            self.store.insert_task({
                "id": task_id, "title": card["title"], "kind": card["expected_output"]["kind"], "assignee": station_id,
                "state": "dispatched", "round": card["round"], "parent": card.get("parent"), "created_by": by,
                "dispatcher": card["dispatcher"], "created_at": card["created_at"], "updated_at": card["created_at"],
                "acceptance_json": json.dumps(card.get("acceptance"), ensure_ascii=False),
                "card_json": json.dumps(card, ensure_ascii=False), "card_path": str(path)})
            self.store.event("assign", i18n.t("ev.assign", lg, by=by, sid=station_id, title=card["title"]), station_id, task_id)
            scenes.note_assign(self.store, task_id, station_id, card.get("goal"))   # 同一个 goal 10 分钟内 ≥ 2 张 → 站会
            # 改同一批文件的提醒（不拦）：和还开着的卡比工作目录 / files 重叠
            warnings = self._conflict_warnings(task_id, card)
            # 这只猫在歇着（额度用完 / 被限流 / 接口连不上 / 服务端出错）：卡排队等它回来
            if not self._rest_ok_to_start(st):
                text = self.queue_text({"assignee": station_id, "card": {}})
                card[WAIT_REASON_KEY] = self._rest_wait_key(station_id)
                tasks.write_card(task_id, card)
                self.store.update_task(task_id, state="queued", card_json=json.dumps(card, ensure_ascii=False))
                self.store.event("queued", text, station_id, task_id)
                if warnings:
                    self.store.event("assign_warning", i18n.t("card.list_sep", lg).join(warnings), station_id, task_id)
                return self._ack("queued", text, task_id=task_id, queued=True, **({"warnings": warnings} if warnings else {}))
            # 一只猫同一时间只跑一张卡：它手上已经有在跑的卡 → 这张卡照建，排队等它干完
            if getattr(runner, "mode", "") != "scheduled" and self._busy_wait(station_id, exclude=task_id):
                text = i18n.t("board.queue.busy", lg, sid=station_id)
                card[WAIT_REASON_KEY] = WAIT_BUSY
                tasks.write_card(task_id, card)
                self.store.update_task(task_id, state="queued", card_json=json.dumps(card, ensure_ascii=False))
                self.store.event("queued", text, station_id, task_id)
                if warnings:
                    self.store.event("assign_warning", i18n.t("card.list_sep", lg).join(warnings), station_id, task_id)
                return self._ack("queued", text, task_id=task_id, queued=True, **({"warnings": warnings} if warnings else {}))
        if warnings:
            self.store.event("assign_warning", i18n.t("card.list_sep", lg).join(warnings), station_id, task_id)
        out = self._launch(st, runner, task_id, card, attempt=1, prompt=prompt)
        if warnings:
            out["warnings"] = warnings
        return out
    @staticmethod
    def _member_prompt(st: dict, task_id: str, card: dict) -> str:
        """给打工猫的说明：卡的内容 + 反馈 + （被打断过就）接着做。语言跟这个工位走。"""
        report_path = tasks.card_dir(task_id) / "report.md"
        text = tasks.render(tasks.localized("member", _st_lang(st)), station=st["id"], role="member", task_id=task_id,
                            card=json.dumps(card, ensure_ascii=False, indent=1), cwd=card.get("cwd") or "",
                            report_path=str(report_path), returned_reason=card.get("returned_reason") or "",
                            round=card.get("round", 1), tools="report", board="",
                            tmp_dir=str(tmpdir.card_tmp(task_id))) + _feedback.block(st["id"], _st_lang(st))   # /
        if card.get(RESUME_SESSION):
            lg = _st_lang(st)
            at = card.get(RESUME_AT) or i18n.t("card.resume.at", lg)
            if card.get(IFACE_WHY):
                # 上次是被模型接口打断的：告诉猫为什么断的、让它先看一眼自己写了一半的东西
                text += "\n\n" + i18n.t("card.resume.interface", lg, at=at, why=card.get(IFACE_WHY))
            else:
                # 接着做：告诉猫上次被打断了，工作目录里的东西可能是它写了一半的
                text += "\n\n" + i18n.t("card.resume.interrupted", lg, at=at)
        return text
    def _network_wait(self, st: dict, task_id: str) -> dict | None:
        """Pi 工位开工前先探一次接口地址（连不上就不开工，排队等接口）：
    连不上不记失败，卡排队等接口，排队标记 WAIT_NETWORK，watchdog 会隔 network_retry_s 秒再探、通了自动开工。
    assign / 打回重派 / resolve redispatch / 排队自动开工都走 _launch，所以都在这里拦。
    连不上时返回 queued 回执（那句就是给用户看的原因），通着返回 None。"""
        pi = st.get("pi") or {}
        if not pi.get("base_url"):
            return None                       # 没写接口地址：不探，按原流程走
        probe = pi_config.api_probe(pi)
        if probe.ok:
            return None
        card = dict((self.store.get_task(task_id) or {}).get("card") or {})
        lg = self.lang()
        text = i18n.t("ev.queued_network", lg, sid=st["id"], stage=pi_config.host_port(pi)[0],
                      why=i18n.t("probe.why." + (probe.stage or "connect"), lg), ms=probe.ms)
        card[WAIT_REASON_KEY] = WAIT_NETWORK
        tasks.write_card(task_id, card)
        self.store.update_task(task_id, state="queued", returned_reason=None, card_json=json.dumps(card, ensure_ascii=False))
        self.store.event("queued", text, st["id"], task_id,
                         data={"probe_ms": probe.ms, "probe_stage": probe.stage, "probe_addr": probe.addr})
        # 接口连不上 = 这只猫出去玩了（歇着）；等接口探通或者到点自己回来
        interval = float(config.settings().get("network_retry_s", 120))
        back_at = (_dt.datetime.now().astimezone() + _dt.timedelta(seconds=interval)).isoformat(timespec="seconds")
        self.mark_resting(st["id"], "network", back_at=back_at, hint="", why=i18n.t("rest.reason.network", lg))
        return self._ack("queued", text, task_id=task_id, queued=True)
    def _launch(self, st: dict, runner, task_id: str, card: dict, attempt: int, prompt: str | None = None) -> dict:
        if st.get("client") == "pi":
            wait = self._network_wait(st, task_id)     # 接口连不上：不启动，排队等接口
            if wait is not None:
                return wait
        run_id = "%s-r%d" % (task_id, attempt)
        if self.store.get_run(run_id) is not None:   # 接口断了重跑同一轮：run_id 唯一，后面加 .2 .3 …
            n = 2
            while self.store.get_run("%s.%d" % (run_id, n)) is not None:
                n += 1
            run_id = "%s.%d" % (run_id, n)
        d = tasks.card_dir(task_id)
        report_path = d / "report.md"
        prompt = prompt if prompt is not None else self._member_prompt(st, task_id, card)
        (d / "prompt.txt").write_text(prompt, encoding="utf-8")
        log_path = d / ("run-%d.log" % attempt)
        base = _git_head(card.get("cwd"))
        lg = self.lang()
        try:
            handle = runner.start(task_id, run_id, card, prompt, log_path)
        except Exception as e:  # noqa: BLE001 - surface launcher failure as unreachable
            text = i18n.t("ack.unreachable", lg, sid=st["id"], why=e)
            self.store.update_task(task_id, state="failed", returned_reason=text)   # 拦下的原因写进卡
            self.store.event("unreachable", i18n.t("ev.unreachable", lg, sid=st["id"], why=e), st["id"], task_id)
            return self._ack("unreachable", text, task_id=task_id)
        self.handles[run_id] = handle
        self.run_owners[run_id] = runner      # 记住是哪个运行器起的，配置改了也找得到进程
        scheduled = runner.mode == "scheduled"
        self.store.insert_run({"run_id": run_id, "task_id": task_id, "station": st["id"], "runner": runner.mode, "attempt": attempt,
                               "worktree": card.get("cwd"), "commit_range": (base + "..") if base else None,
                               "pid": handle.pid, "session_id": handle.session_id,
                               "session_dir": (handle.extra or {}).get("session_dir"),   # 中断后靠它接着做
                               "started": now_iso(), "status": "queued" if scheduled else "running", "log_path": str(log_path)})
        self.store.station_touch(st["id"], runner=runner.mode, state="queued" if scheduled else "dispatched",
                                 task_id=task_id, since=now_iso())
        if scheduled:
            # 定时任务工位不起进程：卡排着队，任务单写进交换文件，定时任务来读这个文件领活
            self.store.update_task(task_id, state="queued")
            rnd = int(card.get("round") or 1)
            exchange.write_current(self.store, st["id"],
                                   exchange.render_card(task_id, rnd, card.get("cwd") or "", report_path, prompt,
                                                        self.lang_of(st["id"])),
                                   task_id=task_id, round=rnd)
            self.store.event("wrote_card", i18n.t("ev.wrote_card", lg, sid=st["id"]), st["id"], task_id)
            self.store.event("queued", i18n.t("ev.queued_sched", lg, sid=st["id"]), st["id"], task_id)
            return self._ack("queued", i18n.t("ack.queued_sched", lg, sid=st["id"], tid=task_id),
                             task_id=task_id, run_id=run_id, queued=True)
        lim = float(config.settings().get("ack_timeout_s", 30))
        t0 = time.time()
        while time.time() - t0 < lim:
            if runner.delivered(handle):
                self.store.event("delivered_receipt", i18n.t("ev.started", lg, sid=st["id"], sec=round(time.time() - t0, 1)),
                                 st["id"], task_id)
                return self._ack("delivered", i18n.t("ack.delivered", lg, sid=st["id"], tid=task_id),
                                 task_id=task_id, run_id=run_id, delivered=True)
            hb = runner.heartbeat(handle)
            if hb.finished:
                break
            time.sleep(0.5)
        # never came up within the window: finish the run, mark failed, no retry
        res = runner.finish(handle) if runner.heartbeat(handle).finished else RunResult(exit=12, status="fail", error="no receipt in %ds" % lim)
        self._close_run(run_id, res, task_failed=True)
        text = i18n.t("ack.unreachable_timeout", lg, sid=st["id"], lim=lim)
        self.store.update_task(task_id, returned_reason=text)   # 给用户看的原因写进卡（_close_run 写的是进程那头的说法）
        return self._ack("unreachable", text, task_id=task_id, exit=res.exit)
    def _find_open(self, station_id: str, title: str) -> dict | None:
        for t in self.store.list_tasks(state="queued,dispatched,running"):
            if t["assignee"] == station_id and tasks.normalize_title({"title": t["title"]}) == title:
                return t
        return None
    @staticmethod
    def _norm_cwd(cwd) -> str:
        return os.path.normcase(os.path.normpath(os.path.abspath(str(cwd or "").strip())))
    @staticmethod
    def _norm_file(f) -> str:
        """卡上 files 的一条：/ 和 \\ 都认，去掉开头的 ./ 和 /，结尾的 /，大小写不分（Windows）。"""
        s = str(f or "").strip().replace("\\", "/").lower()
        while s.startswith("./"):
            s = s[2:]
        return s.strip("/")
    @staticmethod
    def _files_overlap(a: str, b: str) -> bool:
        """同一个文件，或一个是另一个的上级目录。"""
        return a == b or a.startswith(b + "/") or b.startswith(a + "/")
    def _conflict_warnings(self, new_task_id: str, card: dict) -> list[str]:
        """新卡和所有还开着的卡比：① cwd 相同（不同猫用同一个目录）；② files 重叠（同文件 / 上下级目录）。
        有重叠不拦，只回一串人话提醒。没写 files 的卡只比 ①。"""
        lg = self.lang()
        new_cwd = self._norm_cwd(card.get("cwd"))
        new_files = [self._norm_file(x) for x in (card.get("files") or []) if isinstance(x, str) and x.strip()]
        warns: list[str] = []
        for t in self.store.list_tasks(state=CONFLICT_STATES):
            if t["id"] == new_task_id:
                continue
            oc = t.get("card") or {}
            doing = "%s (%s %s)" % (t["id"], t["assignee"], i18n.t("ev.doing." + t["state"], lg))
            if new_cwd and self._norm_cwd(oc.get("cwd")) == new_cwd:
                w = i18n.t("ev.warn_same_cwd", lg, doing=doing, cwd=card.get("cwd") or "")
                if w not in warns:
                    warns.append(w)
            old_files = [self._norm_file(x) for x in (oc.get("files") or []) if isinstance(x, str) and x.strip()]
            if not new_files or not old_files:
                continue
            for nf in new_files:
                for of in old_files:
                    if self._files_overlap(nf, of):
                        w = i18n.t("ev.warn_same_files", lg, doing=doing, files=nf or of)
                        if w not in warns:
                            warns.append(w)
        return warns
    def _busy_wait(self, station_id: str, exclude: str | None = None) -> bool:
        """这只猫手上是不是已经有一张在跑的卡（dispatched / running）？（一只猫同一时间只跑一张卡）
        是 → 这张新卡要排队（wait_reason=busy），等它手上那张结束再开工。"""
        for t in self.store.list_tasks(state="dispatched,running"):
            if t["id"] == exclude:
                continue
            if t["assignee"] == station_id:
                return True
        return False
    def start_ready_queued(self) -> int:
        """排队卡自动开工：等这只猫腾出手的（wait_reason=busy）、等猫歇完回来的（wait_reason=rest），
        还有老版本留下的排队原因——都当普通排队卡处理，猫闲着就开工。按先来后到。返回开了几张。"""
        started = []
        with self.lock:
            waiting = sorted((t for t in self.store.list_tasks(state="queued")
                              if (t.get("card") or {}).get(WAIT_REASON_KEY) in (WAIT_BUSY, WAIT_REST, WAIT_LEGACY)),
                             key=lambda t: t["id"])
            if not waiting:
                return 0
            busy: set[str] = set()
            for t in self.store.list_tasks(state="dispatched,running"):
                busy.add(t["assignee"])          # 这只猫手上已经有一张在跑
            for t in waiting:
                st = self.station(t["assignee"])
                if st is None or not st.get("enabled", True):
                    continue
                runner = self.runner_for(st)
                if runner is None or runner.mode == "scheduled":
                    continue
                if t["assignee"] in busy:        # 这只猫还在忙：跳过，等它干完手上那张
                    continue
                if self.rest_of(t["assignee"]):   # 这只猫还在歇着：等它回来再说
                    continue
                card = dict(t["card"])
                card.pop(WAIT_REASON_KEY, None)
                card, _can = _prepare_resume(card)   # 对话记录没了就别接着聊，从头开始
                tasks.write_card(t["id"], card)
                self.store.update_task(t["id"], state="dispatched", round=int(t["round"] or 1),
                                       card_json=json.dumps(card, ensure_ascii=False))
                busy.add(t["assignee"])
                wait = (t.get("card") or {}).get(WAIT_REASON_KEY)
                started.append((st, runner, t, card,
                                "busy" if wait == WAIT_BUSY else ("rest" if wait == WAIT_REST else "idle")))
        lg = self.lang()
        for st, runner, t, card, kind in started:
            if kind == "busy":
                why = i18n.t("ev.start_why.busy", lg, sid=st["id"])
            elif kind == "rest":
                why = i18n.t("ev.start_why.back", lg, sid=st["id"])   # 歇着的猫到点回来，接着干排队的卡
            else:
                why = i18n.t("ev.start_why.free", lg, sid=st["id"])
            self.store.event("start", i18n.t("ev.start", lg, sid=st["id"], title=card.get("title") or t["id"], why=why),
                             st["id"], t["id"])
            try:
                self._launch(st, runner, t["id"], card, attempt=int(t["round"] or 1))
            except Exception as e:  # noqa: BLE001 - 自动开工坏了不能带崩触发它的那一路
                why = i18n.t("ack.start_failed", lg, sid=st["id"], why=e)
                self.store.update_task(t["id"], state="failed", returned_reason=why)   # 原因写进卡
                self.store.event("failed", why, st["id"], t["id"])
            if st["id"] in self._just_back:   # 猫回来了，接着干这张
                self._back_event(st["id"], t["id"])
        return len(started)
    def retry_network_queued(self, force: bool = False) -> int:
        """等接口的排队卡：隔 network_retry_s 秒重探一次工位接口，通了就按卡号顺序开工。
        同一工位一轮只探一次；接口通了就开工。返回这一轮开工的张数。"""
        now = time.time()
        interval = float(config.settings().get("network_retry_s", 120))
        with self.lock:
            waiting = sorted((t for t in self.store.list_tasks(state="queued")
                              if (t.get("card") or {}).get(WAIT_REASON_KEY) == WAIT_NETWORK), key=lambda t: t["id"])
            if not waiting:
                self._net_retry_at = {}
                return 0
            stations: dict[str, list[dict]] = {}
            for t in waiting:
                stations.setdefault(t["assignee"], []).append(t)
            due = []
            for sid in sorted(stations):
                if not force and now < self._net_retry_at.get(sid, 0):
                    continue
                st = self.station(sid)
                if st is None or not st.get("enabled", True):
                    continue
                if pi_config.api_probe(st.get("pi") or {}).ok:
                    due.extend(stations[sid])
                    self.clear_resting(sid)        # 接口通了：猫回来了
                else:
                    self._net_retry_at[sid] = now + interval   # 还不通：下一轮再探（同步存，重启不丢）
                    # 还是连不上：猫继续歇着（状态词不变）
                    self.mark_resting(sid, "network", back_at=(now + interval).isoformat(timespec="seconds"),
                                      hint="", why=i18n.t("rest.reason.network", self.lang()))
            if not due:
                return 0
            started = []
            for t in due:
                st = self.station(t["assignee"])
                if st is None or not st.get("enabled", True):
                    continue
                runner = self.runner_for(st)
                if runner is None or runner.mode == "scheduled":
                    continue
                card = dict(t["card"])
                card.pop(WAIT_REASON_KEY, None)
                card, _can = _prepare_resume(card)   # 对话记录没了就别接着聊，从头开始
                tasks.write_card(t["id"], card)
                self.store.update_task(t["id"], state="dispatched", round=int(t["round"] or 1),
                                       card_json=json.dumps(card, ensure_ascii=False))
                started.append((st, runner, t, card))
            ok_sids = {st["id"] for st, _r, _t, _c in started}
            for sid in ok_sids:
                self._net_retry_at.pop(sid, None)      # 排的卡都开了：这个工位不用再计时
        lg = self.lang()
        for st, runner, t, card in started:
            self.store.event("start", i18n.t("ev.start_why.net", lg, sid=st["id"]), st["id"], t["id"])
            try:
                self._launch(st, runner, t["id"], card, attempt=int(t["round"] or 1))
            except Exception as e:  # noqa: BLE001 - 重探开工坏了不能带崩看门狗
                why = i18n.t("ack.start_failed", lg, sid=st["id"], why=e)
                self.store.update_task(t["id"], state="failed", returned_reason=why)
                self.store.event("failed", why, st["id"], t["id"])
            if st["id"] in self._just_back:   # 猫回来了，接着干这张
                self._back_event(st["id"], t["id"])
        return len(started)
    def _scheduled_handle(self, run: dict):
        """(runner, handle) for an open scheduled run; adopts from the runs row after a core restart."""
        if run.get("runner") != "scheduled" or run["ended"] is not None:
            return None
        st = self.station(run["station"])
        runner = self.runner_for(st) if st else None
        if runner is None or runner.mode != "scheduled":
            return None
        handle = self.handles.get(run["run_id"])
        if handle is None:
            handle = runner.adopt(run)
            self.handles[run["run_id"]] = handle
        return runner, handle
