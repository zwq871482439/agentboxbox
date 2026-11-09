"""Dispatcher: 派卡、排队、收尾、歇着、看板的总入口。

assign() -> 校验、去重、生成卡号、拼提示词、起运行器、等回执。
report() -> 打工猫的心跳 / 汇报（同一个 task_id + round + status 只记一次）。
review() -> 首领验收：收下还是打回。
on_run_finished() -> 运行器进程结束时由看门狗调用。

各块细节拆在 dispatcher_assign.py（派卡 / 排队）、dispatcher_finish.py（收尾）、
dispatcher_interrupt.py（中断 / 接着做）、dispatcher_rest.py（歇着）、dispatcher_board.py（看板 / 待办）、
dispatcher_stall.py（撤卡停进程、命令跑太久）。
"""
from __future__ import annotations

import json
import threading

from . import config, i18n, procjob, tasks, tmpdir
from . import feedback as _feedback
from .dispatcher_assign import AssignMixin
from .dispatcher_board import BoardMixin
from .dispatcher_const import (
    ASKED_KV,
    CONFIG_KV,
    CONFLICT_STATES,
    IFACE_RETRIES,
    INT_CRASH,
    INT_EXIT,
    INTERRUPT_KIND,
    NET_RETRY_KEY,
    QUEUE_FRONT,
    REST_BACKOFF,
    REST_KV,
    REST_REASONS,
    REST_TRY_KV,
    RESUME_AT,
    RESUME_SESSION,
    WAIT_BUSY,
    WAIT_CONFIG,
    WAIT_LEGACY,
    WAIT_NETWORK,
    WAIT_REASON_KEY,
    WAIT_REST,
)
from .dispatcher_finish import FinishMixin
from .dispatcher_interrupt import InterruptMixin
from .dispatcher_rest import RestMixin
from .dispatcher_stall import StallMixin
from .dispatcher_util import _prepare_resume, _runner_mode, _who
from .runners import RunHandle, RunResult, make_runner
from .store import Store, now_iso

__all__ = [
    "Dispatcher", "ASKED_KV", "CONFIG_KV", "CONFLICT_STATES", "IFACE_RETRIES", "INT_CRASH", "INT_EXIT",
    "INTERRUPT_KIND", "NET_RETRY_KEY", "RESUME_AT", "RESUME_SESSION", "REST_BACKOFF", "REST_KV", "REST_REASONS",
    "REST_TRY_KV", "WAIT_BUSY", "WAIT_CONFIG", "WAIT_LEGACY", "WAIT_NETWORK", "WAIT_REASON_KEY", "WAIT_REST",
            ]


class Dispatcher(AssignMixin, BoardMixin, FinishMixin, InterruptMixin, RestMixin, StallMixin):
    def __init__(self, store: Store):
        self.store = store
        self.runners = {}
        self.handles: dict[str, RunHandle] = {}
        self.retired: dict[str, object] = {}      # 配置改了但还有在跑进程的运行器：挪这儿，老进程它管着
        self.run_owners: dict[str, object] = {}   # run_id → 起它的运行器（运行器被换掉后还找得到进程）
        self.lock = threading.RLock()
        self.leader_last_seen: str | None = store.kv_get("leader_last_seen")
        self._net_retry_at: dict[str, float] = {}   # 每个工位下次可以重探接口的时刻（时间戳，秒）
        self._just_back: set[str] = set()           # 刚回来的猫：接上排队的卡时发「回来了，接着干 X」
        # 全员空闲的起点：从来没卡时用它（写入库，重启后从库里算）
        store.kv_set("core_started_at", now_iso())
    def lang(self) -> str:
        """界面语言：设置里的 ui_lang（前端切语言时写进来），没设过按系统语言定。"""
        return i18n.lang()
    def lang_of(self, station_id: str) -> str:
        """某个工位说的语言：上岗时用它那套话招的（英文上岗话 → 这个工位 lang=en），没记就用界面语言。
        首领那边的回话、提醒、简报按这个来。"""
        st = config.station(str(station_id or "")) or {}
        v = str(st.get("lang") or "").strip().lower()
        return v if v in i18n.LANGS else self.lang()
    def station(self, sid: str) -> dict | None:
        return config.station(sid)
    def runner_for(self, st: dict):
        if st.get("role") == "leader":
            return None                    # Leader 不跑一次性进程：它住在用户自己的 AI 软件里，自己来领活
        r = self.runners.get(st["id"])
        if r is None:
            r = make_runner(st)
            if r is not None:
                self.runners[st["id"]] = r
        return r
    def all_runners(self) -> list:
        """所有运行器：现在的 + 挪去退休的（还有在跑进程的老运行器也得算上）。"""
        return list(self.runners.values()) + list(self.retired.values())
    def drop_idle_runners(self) -> int:
        """工位配置改了以后调用：只丢掉「没有在跑进程」的运行器。
        有在跑进程的运行器要留着——它记着进程表，丢了核心就管不住那个 Pi 进程了：
        下一次心跳查不到进程记录，就会把还在干活的卡误记成「没跑成（退出码 1）」。
        留着的同时把配置换成新的：在跑的那张卡不受影响，下一张卡用新配置。"""
        dropped = 0
        for sid, r in list(self.retired.items()):     # 退休的运行器：手上的进程都结束了就扔掉
            if not getattr(r, "live", None):
                self.retired.pop(sid, None)
        for sid, r in list(self.runners.items()):
            if getattr(r, "live", None):
                st = self.station(sid)
                if st is not None and _runner_mode(st) == getattr(r, "mode", ""):
                    r.reconfigure(st)                  # 只是配置变了：在跑的卡不动，下一张用新配置
                else:
                    self.runners.pop(sid, None)        # 工位类型变了：老运行器只管手上这个进程
                    self.retired[sid] = r
                continue
            self.runners.pop(sid, None)
            dropped += 1
        return dropped
    def shutdown(self) -> int:
        """核心退出：结束所有打工进程，把它们的卡记成「中断」，返回中断了几张。
        不是「做砸了」，是「被打断」——原因写「退出时中断」，对话记录留着，下次打开能接着做。
        token 照常记（finish 会把进程已经吐出来的用量交回来）。"""
        n = 0
        for r in self.all_runners():
            try:
                ids = r.stop_all()
            except Exception:  # noqa: BLE001 - 一个工位收不了尾不能挡住其它工位
                continue
            for rid in ids:
                h = self.handles.get(rid)
                if h is None:
                    continue
                if h.extra:                      # 留着这一轮的对话记录，下次能接着做
                    h.extra["keep_session"] = True
                try:
                    res = r.finish(h)
                except Exception as e:  # noqa: BLE001
                    res = RunResult(exit=1, status="fail", error=str(e))
                res.exit = res.exit or 1
                res.status = "fail"
                res.error = i18n.t("why.exit", self.lang())
                self.interrupt_run(rid, res, why=i18n.t("why.exit", self.lang()), kind=INT_EXIT)
                n += 1
        if n:
            self.store.event("core_interrupt", i18n.t("ev.core_interrupt", self.lang(), n=n))
        return n
    def touch_leader(self, who: str | None) -> str | None:
        """首领动了一下：这个工位的最近活动记在 stations_state。
        全局 leader_last_seen 只跟主首领走，这样只有一个首领时和原来一样；
        别的首领只更新自己那一行，免得一个在干活把另一个的沉默冲掉。
        返回记下的时间（不是首领返回 None）。"""
        if not (who and config.is_leader(who)):
            return None
        now = now_iso()
        if who == config.leader_id():
            self.leader_last_seen = now
            self.store.kv_set("leader_last_seen", now)
        self.store.station_touch(who, last_seen=now)
        return now
    def report(self, task_id: str, status: str, summary: str, by: str) -> dict:
        lg = self.lang()
        if not tasks.TASK_ID_RE.match(task_id or ""):
            return self._ack("bad_task_id", i18n.t("ack.bad_task_id", lg))
        t = self.store.get_task(task_id)
        if t is None:
            return self._ack("bad_task_id", i18n.t("ack.no_task", lg, tid=task_id))
        if by and t["assignee"] != by and not config.is_leader(by):
            return self._ack("forbidden", i18n.t("ack.forbidden_station", lg, by=by))
        if status not in ("heartbeat", "done", "blocked", "issue"):
            return self._ack("bad_state", i18n.t("ack.bad_status", lg))
        if status != "heartbeat" and not self.store.report_key_once("%s+%s+%s" % (task_id, t["round"], status)):
            return self._ack("duplicate_report", i18n.t("ack.duplicate_report", lg, status=status), state=t["state"])
        nxt = tasks.next_state(t["state"], status)
        if nxt is None:
            return self._ack("bad_state", i18n.t("ack.bad_state", lg, state=t["state"], status=status), state=t["state"])
        now = now_iso()
        for r in self.store.runs_for_task(task_id):
            if r["ended"] is not None:
                continue
            self.store.update_run(r["run_id"], last_activity=now, first_activity=r["first_activity"] or now)
            got = self._scheduled_handle(r)          # path C: a report is also the receipt
            if got is None:
                continue
            runner, handle = got
            if status == "heartbeat":
                handle.extra["last_report_at"] = now
            else:
                handle.extra["reported"] = status
                self._close_run(r["run_id"], runner.finish(handle), task_failed=False)  # close before the task moves on
        if status == "done":
            self.store.update_task(task_id, state="delivered", delivered_at=now)
            self.store.event("report", i18n.t("ev.report_done", lg, sid=t["assignee"], summary=summary or ""), t["assignee"], task_id,
                              data={"status": "done"})
            self._after_delivered(task_id)
            self.start_ready_queued()   # 一张卡交付了：同服务商排队的下一张自动开工
        elif status in ("blocked", "issue"):
            self.store.update_task(task_id, state="blocked", returned_reason=summary)
            self.store.event("report", i18n.t("ev.report_issue", lg, sid=t["assignee"],
                                              how=i18n.t("ev.report.how." + status, lg), summary=summary or ""),
                             t["assignee"], task_id, data={"status": status})
            self._maybe_write_idle(t["assignee"], task_id)   # 文件档：卡住也没活了，别让它重读旧卡
        else:
            if t["state"] == "dispatched":
                self.store.update_task(task_id, state="running")
            self.store.event("heartbeat", summary or i18n.t("ev.heartbeat", lg), t["assignee"], task_id)
        return self._ack("ok", i18n.t("ack.received", lg), state=self.store.get_task(task_id)["state"])
    def review(self, task_id: str, verdict: str, note: str, by: str, feedback: str = "") -> dict:
        out = self._review(task_id, verdict, note, by)
        if feedback.strip() and out.get("code") not in ("bad_task_id", "forbidden", "bad_state"):
            t = self.store.get_task(task_id)
            if t is not None:                 # 开关开着才真的记；关着回执里说一声
                r = _feedback.add(t["assignee"], feedback, task_id, store=self.store,
                                  lang=self.lang_of(t["assignee"]))
                out["feedback"] = "recorded" if r["recorded"] else r["why"]
                if not r["recorded"]:
                    # 只回一个 off 首领看不懂：说清楚是开关关着、谁能开
                    out["feedback_text"] = i18n.t("ack.feedback." + str(r["why"] or "empty"), self.lang())
        return out
    def _review(self, task_id: str, verdict: str, note: str, by: str) -> dict:
        self.touch_leader(by)
        lg = self.lang()
        if not tasks.TASK_ID_RE.match(task_id or ""):
            return self._ack("bad_task_id", i18n.t("ack.bad_task_id", lg))
        t = self.store.get_task(task_id)
        if t is None:
            return self._ack("bad_task_id", i18n.t("ack.no_task", lg, tid=task_id))
        if by not in (t["dispatcher"], "user"):
            return self._ack("forbidden", i18n.t("ack.forbidden_review", lg, who=t["dispatcher"], by=by))
        if verdict not in ("accept", "return"):
            return self._ack("bad_state", i18n.t("ack.bad_verdict", lg))
        # returned = 质检打回已达 max_rounds，「交 leader 定」——所以 leader 必须能在这个状态上拍板
        # interrupted = 工位被删掉时卡停在半路，首领在这里拍板就是要求再来一轮
        if t["state"] not in ("reviewing", "delivered", "blocked", "returned", "interrupted"):
            return self._ack("bad_state", i18n.t("ack.cannot_review", lg, state=t["state"]), state=t["state"])
        if verdict == "accept":
            self.store.update_task(task_id, state="accepted")
            self.store.event("review", i18n.t("ev.review_accept", lg, by=_who(by, lg), note=note or ""), by, task_id,
                              data={"verdict": "accept", "to": t["assignee"]})
            self._on_accept(task_id)
            return self._ack("ok", i18n.t("ack.approved", lg), state="done")
        # leader 对一张已经 returned / interrupted 的卡再打回 = 明确要再来一轮，max_rounds 不再拦
        return self._return_task(t, note, by, force=(t["state"] in ("returned", "interrupted")))
    def resolve(self, task_id: str, action: str, note: str, by: str, station: str = "") -> dict:
        """首领拍板一张 failed / interrupted / blocked / returned 的卡：redispatch 再走一次开工检查和
        送达回执。带了 station 就改派给那只猫，卡号不变。打回待定再派算新的一轮（round+1，带上最新的打回说明）；
        其余不翻轮次。cancel 进 cancelled、不再出现在待办。在跑或已派出的卡会停掉这次运行的整棵进程。
        只有这张卡的 dispatcher 能调，别人回 forbidden。"""
        self.touch_leader(by)
        lg = self.lang()
        if not tasks.TASK_ID_RE.match(task_id or ""):
            return self._ack("bad_task_id", i18n.t("ack.bad_task_id", lg))
        t = self.store.get_task(task_id)
        if t is None:
            return self._ack("bad_task_id", i18n.t("ack.no_task", lg, tid=task_id))
        if by not in (t["dispatcher"], "user"):          # 用户是老板：首领不在时也能在看板上自己拍板
            return self._ack("forbidden", i18n.t("ack.forbidden_resolve", lg, who=t["dispatcher"]))
        if action not in ("redispatch", "cancel"):
            return self._ack("bad_state", i18n.t("ack.bad_action", lg))
        nxt = tasks.next_state(t["state"], action if action == "cancel" else "redispatch")
        if nxt is None:
            return self._ack("bad_state", i18n.t("ack.cannot_resolve", lg, state=t["state"]), state=t["state"])
        if action == "cancel":
            # 在跑的卡要停进程；说明记在 cancel_note，不进 returned_reason
            return self.cancel_task(t, task_id, note, by)
        target = str(station or "").strip() or t["assignee"]
        moved_from = t["assignee"] if target != t["assignee"] else ""
        st = self.station(target)
        if st is None:
            return self._ack("station_unknown", i18n.t("ack.gone_station", lg, sid=target),
                             task_id=task_id, state=t["state"])
        if moved_from and st.get("role") != "member":
            return self._ack("not_member", i18n.t("ack.not_member", lg, sid=target))
        if moved_from and not st.get("enabled", True):
            return self._ack("station_disabled", i18n.t("ack.station_disabled", lg, sid=target), exit=14)
        runner = self.runner_for(st)
        if runner is None:
            return self._ack("no_runner", i18n.t("ack.no_runner2", lg, sid=target), state=t["state"])
        card = dict(t["card"] or {})
        card["assignee"] = target
        card.pop(NET_RETRY_KEY, None)   # 首领重派：接口断的自动重试计数重新数
        card.pop(WAIT_REASON_KEY, None)  # 重派是重新开工：旧的排队标记不算数
        attempt = int(t["round"] or 1)
        returned = t["state"] == "returned"
        if returned:
            # 停在打回待定后再派是新的一轮：轮次 +1，说明用这次写的，没写就用卡上最新那条
            attempt += 1
            card["round"] = attempt
            latest = str(note or "").strip() or str(card.get("returned_reason") or t.get("returned_reason") or "")
            card["returned_reason"] = latest
        elif note:
            card["returned_reason"] = note
        # 首领重派一张中断的卡 = 接着做：上次的对话记录还在就接着做（--continue），不在就从头开始
        if t["state"] == "interrupted":
            card, _can = _prepare_resume(card)
            card["returned_reason"] = note or ""      # 上次中断的原因不用再喂给猫（提示词里已经说了）
            if card.get("resume_note"):
                self.store.event("resume", i18n.t("ev.resume_no_session", lg, title=t["title"],
                                                  why=i18n.t("why.no_session", lg)), by, task_id)
        tasks.write_card(task_id, card)
        upd = {"state": "dispatched", "assignee": target, "returned_reason": note or None,
               "card_json": json.dumps(card, ensure_ascii=False)}
        if returned:
            upd["round"] = attempt
            upd["returned_reason"] = card.get("returned_reason") or None
        self.store.update_task(task_id, **upd)
        shown = (card.get("returned_reason") if returned else note) or i18n.t("ev.resolve.note", lg)
        if moved_from:
            text = i18n.t("ev.resolve_move", lg, by=_who(by, lg), tid=task_id,
                          old=moved_from, sid=target, note=shown)
            self.store.event("resolve", text, by, task_id, data={"from": moved_from, "to": target})
        else:
            self.store.event("resolve", i18n.t("ev.resolve", lg, by=_who(by, lg), tid=task_id, note=shown), by, task_id)
        if t["state"] == "failed" and not card.get(RESUME_SESSION):
            # 失败的卡留着是为了查；首领拍板从头重派，旧的临时目录没用了。
            # 中断的卡重派是接着那段对话做，对话里提到的脚本和中间文件还在临时目录里，不能删
            tmpdir.remove_card(task_id)
        # 这只猫在歇着（额度用完 / 被限流 / 接口连不上）：这张卡排队等它回来
        if not self._rest_ok_to_start(st):
            if returned:
                card[QUEUE_FRONT] = True
            card[WAIT_REASON_KEY] = self._rest_wait_key(target)
            tasks.write_card(task_id, card)
            self.store.update_task(task_id, state="queued", card_json=json.dumps(card, ensure_ascii=False))
            text = self.queue_text(dict(t, assignee=target, card=card))
            self.store.event("queued", text, target, task_id)
            return self._ack("queued", text, task_id=task_id, state="queued", queued=True)
        # 一只猫同一时间只跑一张卡：它手上已经有在跑的卡 → 这张排队等它干完
        if getattr(runner, "mode", "") != "scheduled" and self._busy_wait(target, exclude=task_id):
            if returned:
                card[QUEUE_FRONT] = True
            text = i18n.t("board.queue.busy", lg, sid=target)
            card[WAIT_REASON_KEY] = WAIT_BUSY
            tasks.write_card(task_id, card)
            self.store.update_task(task_id, state="queued", card_json=json.dumps(card, ensure_ascii=False))
            self.store.event("queued", text, target, task_id)
            return self._ack("queued", text, task_id=task_id, state="queued", queued=True)
        return self._launch(st, runner, task_id, card, attempt=attempt)
    def _alive_stations(self) -> set[str]:
        """进程还在跑的工位：这些猫不许显示失败 / 离线。"""
        out: set[str] = set()
        try:
            for r in self.store.open_runs():
                if procjob.pid_alive(r.get("pid")):
                    out.add(str(r.get("station")))
        except Exception:  # noqa: BLE001 - 查不到就当没有，不带崩看板
            return out
        return out
    def leader_client(self) -> str:
        """首领真正连上来的那家 AI 软件（cursor / claude-code / codex / other…）；没连上过就是空。"""
        lid = config.leader_id()
        if not lid:
            return ""
        return str((self.store.kv_get("station_client") or {}).get(lid) or "")
    @staticmethod
    def _ack(code: str, text: str, **extra) -> dict:
        out = {"ok": code in ("ok", "delivered", "queued"), "code": code, "text": text}
        out.update(extra)
        return out
