"""中断：卡被打断怎么记、怎么接着做。"""
from __future__ import annotations

import json
import re

from . import config, i18n, pi_events, procjob, runlog, tasks
from .dispatcher_const import (
    ASKED_KV,
    INT_CRASH,
    INTERRUPT_KIND,
    RESUME_AT,
    RESUME_SESSION,
    WAIT_BUSY,
    WAIT_REASON_KEY,
)
from .dispatcher_util import _hhmm, _prepare_resume
from .runners import RunResult
from .runners.pi import LOG_MARK


class InterruptMixin:
    INTERRUPT_WORD = {"worker_deleted": "why.worker_deleted", "reset_all": "why.station_gone"}
    def interrupt_run(self, run_id: str, res: RunResult, why: str, kind: str) -> dict | None:
        """这一轮被打断了（不是做砸了）：run 收尾、卡记 interrupted、原因写清怎么来的。
        对话记录目录记在卡上（下次能接着做）；token 照常记在这一轮上。"""
        run = self.store.get_run(run_id)
        if run is None or run.get("status") == "cancelled":
            return None
        self._close_run(run_id, res, task_failed=False)      # 先把这一轮收好（token / 用量）
        self._quota_after_run(run["station"])
        t = self.store.get_task(run["task_id"])              # 撤掉可能刚发生，用库里的最新状态
        if t is None or t["state"] not in ("dispatched", "running"):
            return None
        card = dict(t.get("card") or {})
        card[INTERRUPT_KIND] = kind
        sess = self._session_dir_of(run)
        if sess:
            card[RESUME_SESSION] = sess
            card[RESUME_AT] = _hhmm(run.get("last_activity") or run.get("started") or "")
        tasks.write_card(t["id"], card)
        self.store.update_task(t["id"], state="interrupted", card_json=json.dumps(card, ensure_ascii=False),
                               returned_reason=why)
        self._unmark_asked([t["id"]])   # 又中断了一次 → 下次打开要再问一遍
        self.store.event("interrupted", i18n.t("ev.interrupted", self.lang(), sid=run["station"], title=t["title"], why=why),
                         run["station"], t["id"], data={"kind": kind, "session": card.get(RESUME_SESSION, "")})
        self.start_ready_queued()      # 中断也算结束：同服务商排队的下一张自动开工
        return {"task_id": t["id"], "title": t["title"], "station": run["station"], "reason": why}
    def _session_dir_of(self, run: dict) -> str:
        """这一轮的对话记录目录：runs 表里记的优先（续跑时会指到上一次的目录），否则按 run_id 推。"""
        d = str(run.get("session_dir") or "").strip()
        if d:
            return d
        return str(config.DATA / "sessions" / str(run.get("run_id") or ""))
    def mark_crashed_runs(self) -> list[dict]:
        """核心启动时查一遍：上次还有没收尾的 run、进程也不在了 = 上次没正常退出（崩溃 / 被任务管理器结束）。
        卡记「中断」（不是失败），下次打开能接着做。进程还在的不动：看门狗会按 pid 重新接管。"""
        out = []
        for run in self.store.open_runs():
            if not run.get("pid"):
                continue        # 定时任务（路径 C）本来就没进程，等客户端来领：不是崩溃
            try:
                if procjob.pid_alive(run.get("pid")):
                    continue
            except Exception:  # noqa: BLE001 - 查不到进程就当它不在了
                pass
            r = self.interrupt_run(run["run_id"],
                                   RunResult(exit=1, status="fail", error=i18n.t("why.crash", self.lang())),
                                   why=i18n.t("why.crash", self.lang()), kind=INT_CRASH)
            self._recover_run_usage(run)
            if r:
                out.append(r)
        return out
    def _recover_run_usage(self, run: dict) -> bool:
        """强杀 / 崩溃那一轮的用量：进程没了，finish() 没跑出来，账本里没有这一轮的数。
        从运行日志里这一轮的 pi --mode json 事件流把用量捞出来补记进账本；捞不到就算了，不报错。"""
        if self.store.ledger_has_run(run["run_id"]):
            return False                     # 记过了，别记两遍
        text = runlog.read_text(str(run.get("log_path") or ""))   # 已经压成 .gz 的也读得到
        if not text:
            return False
        stream = self._run_stream(text, str(run["run_id"]))
        if not stream:
            return False
        p = pi_events.PiEventParser()
        p.feed(stream)
        p.close()
        summ = p.summary()
        tok = summ.get("tokens")
        if not tok or not tok.get("turns"):
            return False
        fields = {"tokens_json": json.dumps(tok, ensure_ascii=False)}
        # 崩溃没走到 finish，模型/命令用时也从同一份日志补上，免得打开页面再扫一遍
        if summ.get("split"):
            fields["split_json"] = json.dumps(summ["split"], ensure_ascii=False)
        self.store.update_run(run["run_id"], **fields)
        from . import tokens as _tok
        _tok.record(self.store, run, tok)
        return True
    @staticmethod
    def _run_stream(text: str, run_id: str) -> str:
        """运行日志里这一轮的 pi --mode json 事件流（认不出这一轮就返回空串）。
        同一张卡重跑写的是同一个日志文件：按每轮的头认，别把别轮的数算到自己头上。"""
        hits = list(re.finditer("run=%s(?=[ \r\n])" % re.escape(run_id), text))
        if not hits:
            return ""
        j = text.find(LOG_MARK, hits[-1].start())
        if j < 0:
            return ""
        rest = text[j + len(LOG_MARK):]
        k = rest.find("\n# ")                # 下一段（下一轮的头 / 这一轮的收尾行）之前就是这一轮的事件流
        return rest[:k] if k >= 0 else rest
    def interrupted_cards(self, include_asked: bool = False) -> list[dict]:
        """待问的中断卡：还没问过用户的这一批（问过的记在 kv 里，同一批不再弹）。"""
        asked = set(self.store.kv_get(ASKED_KV) or [])
        out = []
        for t in self.store.list_tasks(state="interrupted", limit=100):
            card = t.get("card") or {}
            if not include_asked and t["id"] in asked:
                continue
            out.append({"task_id": t["id"], "title": t["title"], "station": t["assignee"],
                        "reason": t.get("returned_reason") or "", "since": t.get("updated_at") or "",
                        "kind": card.get(INTERRUPT_KIND) or "",
                        "can_resume": bool(card.get(RESUME_SESSION))})
        return out
    def _mark_asked(self, ids) -> None:
        """记下这批问过了：同一批不再弹窗（新的中断还是问）。"""
        seen = list(self.store.kv_get(ASKED_KV) or [])
        for i in ids or []:
            if i and i not in seen:
                seen.append(i)
        self.store.kv_set(ASKED_KV, seen[-200:])
    def _unmark_asked(self, ids) -> None:
        """这张卡又被打断了 → 取消「问过了」的标记（下次打开还要问）。"""
        ids = [str(i) for i in (ids or []) if i]
        if not ids:
            return
        seen = [i for i in (self.store.kv_get(ASKED_KV) or []) if i not in ids]
        self.store.kv_set(ASKED_KV, seen[-200:])
    def dismiss_interrupted(self, ids, to_leader: bool = False) -> dict:
        """「先不管」：卡留在中断，这批记成问过了。to_leader=True =「交给首领决定」：
        同样不再弹，另外给首领留一条话（首领的 get_todo 里本来就能看到这些卡）。"""
        ids = [str(i) for i in (ids or []) if i]
        self._mark_asked(ids)
        if to_leader and ids:
            # 交给派这张卡的那个首领；几张卡不是同一个首领派的，就各发一条
            groups: dict[str, list[str]] = {}
            for i in ids:
                t = self.store.get_task(i) or {}
                lid = str(t.get("dispatcher") or "") or config.leader_id() or ""
                if lid:
                    groups.setdefault(lid, []).append(i)
            for lid, mine in groups.items():
                self.store.event("interrupted_handoff", i18n.t("ev.interrupted_handoff", self.lang(), n=len(mine)),
                                 lid, data={"task_ids": mine, "n": len(mine)})
        return {"ok": True, "dismissed": len(ids), "to_leader": bool(to_leader)}
    def resume_interrupted(self, ids) -> dict:
        """「接着做」：把这几张中断的卡重新派出去，能续上次的对话就续（--continue），续不了就从头开始。"""
        out = []
        for tid in ids or []:
            t = self.store.get_task(str(tid))
            if t is None or t["state"] != "interrupted":
                continue
            out.append(self._resume_task(t))
        self._mark_asked([str(i) for i in (ids or []) if i])
        return {"ok": True, "count": len(out), "resumed": out}
    def _resume_task(self, t: dict) -> dict:
        """接着做一张中断的卡：原卡原工位再走一次开工检查和送达回执（对话能续就续）。"""
        task_id = t["id"]
        st = self.station(t["assignee"])
        lg = self.lang()
        if st is None:
            return {"task_id": task_id, "ok": False, "text": i18n.t("ack.station_gone", lg, sid=t["assignee"])}
        runner = self.runner_for(st)
        if runner is None:
            return {"task_id": task_id, "ok": False, "text": i18n.t("ack.no_runner_resume", lg, sid=t["assignee"])}
        card = dict(t.get("card") or {})
        card, can = _prepare_resume(card)
        card.pop("returned_reason", None)
        if not can and card.get("resume_note"):
            self.store.event("resume", i18n.t("ev.resume_no_session", self.lang(), title=t["title"],
                                              why=i18n.t("why.no_session", self.lang())), t["assignee"], task_id)
        tasks.write_card(task_id, card)
        self.store.update_task(task_id, state="dispatched", card_json=json.dumps(card, ensure_ascii=False),
                               returned_reason=card.get("resume_note") or None)
        self.store.event("resume", i18n.t("ev.resume_continue", lg, sid=t["assignee"], title=t["title"]), t["assignee"], task_id,
                         data={"continued": bool(can)})
        out = self._launch_resume(st, runner, task_id, card, attempt=int(t["round"] or 1))
        out.setdefault("task_id", task_id)
        out["continued"] = bool(can)
        return out
    def _launch_resume(self, st: dict, runner, task_id: str, card: dict, attempt: int) -> dict:
        """续跑 / 重派共用的开工检查：歇着 / 猫忙 都照旧排队（跟 resolve 一样）。"""
        sid = st["id"]
        if not self._rest_ok_to_start(st):
            card[WAIT_REASON_KEY] = self._rest_wait_key(sid)
            tasks.write_card(task_id, card)
            self.store.update_task(task_id, state="queued", card_json=json.dumps(card, ensure_ascii=False))
            text = self.queue_text(dict(self.store.get_task(task_id) or {}, card=card))
            self.store.event("queued", text, sid, task_id)
            return {"ok": True, "code": "queued", "text": text, "task_id": task_id, "queued": True}
        if getattr(runner, "mode", "") != "scheduled" and self._busy_wait(sid, exclude=task_id):
            text = i18n.t("board.queue.busy", self.lang(), sid=sid)
            card[WAIT_REASON_KEY] = WAIT_BUSY
            tasks.write_card(task_id, card)
            self.store.update_task(task_id, state="queued", card_json=json.dumps(card, ensure_ascii=False))
            self.store.event("queued", text, sid, task_id)
            return {"ok": True, "code": "queued", "text": text, "task_id": task_id, "queued": True}
        return self._launch(st, runner, task_id, card, attempt=attempt)
    def interrupt_station(self, station_id: str, cause: str = "worker_deleted") -> list[dict]:
        """结束这个工位所有在跑的进程（只这一只猫的），把它的 dispatched / running 卡记成 interrupted。
        返回 [{task_id, title}]。离线的工位没有进程可结束，卡照样记。"""
        runner = self.runners.get(station_id) or self.retired.get(station_id)
        if runner is not None:
            try:
                ids = runner.stop_all()
            except Exception:  # noqa: BLE001 - 一个工位收不了尾不能挡住其它工位
                ids = []
            for rid in ids:
                h = self.handles.get(rid)
                try:
                    res = runner.finish(h) if h is not None else RunResult(exit=1, status="fail", error=i18n.t("why.no_run_record", self.lang()))
                except Exception as e:  # noqa: BLE001
                    res = RunResult(exit=1, status="fail", error=str(e))
                res.exit = res.exit or 1
                res.status = "fail"
                # task_failed=False：卡不进 failed，下面统一记成中断
                self._close_run(rid, res, task_failed=False)
        return self._mark_interrupted([t for t in self.store.list_tasks(state="dispatched,running")
                                       if t["assignee"] == station_id], station_id, cause)
    def interrupt_all(self, cause: str = "reset_all") -> list[dict]:
        """所有在跑的卡（重置所有）：按工位一只只来，先结束进程再记中断。"""
        sids = list(dict.fromkeys(t["assignee"] for t in self.store.list_tasks(state="dispatched,running")))
        out: list[dict] = []
        for sid in sids:
            out += self.interrupt_station(sid, cause)
        return out
    def _mark_interrupted(self, rows: list[dict], station_id: str, cause: str) -> list[dict]:
        lg = self.lang()
        word = i18n.t(self.INTERRUPT_WORD.get(cause, "why.station_gone"), lg)
        out = []
        for t in rows:
            why = i18n.t("ack.interrupted_why", lg, sid=station_id, word=word)
            self.store.update_task(t["id"], state="interrupted", returned_reason=why)
            self.store.event("interrupted", i18n.t("ev.interrupted_need", lg, sid=station_id, word=word, title=t["title"]),
                             station_id, t["id"], data={"reason": cause, "station": station_id})
            lid = str(t.get("dispatcher") or "") or config.leader_id()
            if lid and lid != station_id:
                self.store.post_message(station_id, lid, i18n.t("ack.interrupted_msg", lg, sid=station_id, word=word,
                                                                title=t["title"], tid=t["id"]))
            out.append({"task_id": t["id"], "title": t["title"]})
        if out:
            self.start_ready_queued()   # 中断也算结束：同服务商排队的下一张自动开工
        return out
