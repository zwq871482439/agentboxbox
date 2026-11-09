"""撤掉在跑的卡，和单条命令跑太久时停掉整次运行。"""
from __future__ import annotations

from . import i18n, procjob, tmpdir
from .dispatcher_util import _who
from .runners import RunResult
from .store import now_iso


def _drop_live(runner, run_id: str) -> None:
    """进程已经停了：丢掉运行器手里的记录。没有 discard 的（假运行器）就直接从 live 里拿掉。"""
    if runner is None:
        return
    drop = getattr(runner, "discard", None)
    if callable(drop):
        drop(run_id)
        return
    live = getattr(runner, "live", None)
    if isinstance(live, dict):
        live.pop(run_id, None)


class StallMixin:
    def stop_run(self, run: dict, discard: bool = True) -> str:
        """停掉这一次运行的整棵进程树。返回空串表示停了（或本来就没有）；否则是一句停不掉。

        进程表还在就让运行器停；丢了就按 runs 里的 pid。discard 为假时先留着记录，
        调用方还要 finish() 去收用量、决定对话目录留不留。
        """
        rid = str(run.get("run_id") or "")
        runner = self.run_owners.get(rid)
        if runner is None:
            st = self.station(str(run.get("station") or ""))
            runner = self.runner_for(st) if st else None
        stopped = False
        try:
            if runner is not None and not runner.lost_process(rid):
                stopped = bool(runner.stop(rid))
        except Exception:  # noqa: BLE001 - 停不掉要在回执里说，不能把撤卡带崩
            stopped = False
        if not stopped:
            stopped = procjob.kill_pid(run.get("pid"))
        if stopped and discard:
            _drop_live(runner, rid)
        if not stopped and procjob.pid_alive(run.get("pid")):
            return i18n.t("ack.cancel_alive", self.lang(), pid=run.get("pid"))
        return ""

    def cancel_task(self, t: dict, task_id: str, note: str, by: str) -> dict:
        """撤掉一张卡。在跑 / 已派的要停进程，运行记 cancelled，工位回闲。
        说明记在 cancel_note，不写 returned_reason（那一栏是打回原因）。"""
        with self.lock:
            return self._cancel_locked(t, task_id, note, by)

    def _cancel_locked(self, t: dict, task_id: str, note: str, by: str) -> dict:
        lg = self.lang()
        kill_msg = ""
        if t["state"] in ("dispatched", "running"):
            for run in self.store.runs_for_task(task_id):
                if run.get("ended"):
                    continue
                msg = self.stop_run(run, discard=True)
                if msg:
                    kill_msg = msg
                self.store.update_run(run["run_id"], ended=now_iso(), status="cancelled")
                self.handles.pop(run["run_id"], None)
                self.run_owners.pop(run["run_id"], None)
            self.store.station_touch(t["assignee"], state="idle", task_id=None, since=now_iso())
        self.store.update_task(task_id, state="cancelled", cancel_note=str(note or ""))
        shown = note or i18n.t("ev.cancelled.note", lg)
        self.store.event("cancelled", i18n.t("ev.cancelled", lg, by=_who(by, lg), tid=task_id, note=shown), by, task_id)
        tmpdir.remove_card(task_id)          # 撤掉了：临时目录马上清；失败和中断的留着查
        if not any(x["assignee"] == t["assignee"] for x in self.store.list_tasks(state="queued")):
            self.clear_resting(t["assignee"])
        return self._ack("ok", kill_msg or i18n.t("ack.cancelled", lg), state="cancelled")

    def fail_overtime(self, run: dict, why: str) -> None:
        """单条命令到了硬上限：停整次运行，卡记失败，原因用传进来的那句。对话目录留着，首领还能重派接着做。"""
        rid = str(run.get("run_id") or "")
        self.stop_run(run, discard=False)
        handle = self.handles.get(rid)
        runner = self.run_owners.get(rid)
        if handle is not None:
            handle.extra["keep_session"] = True
        res = RunResult(exit=1, status="fail", error=why)
        if runner is not None and handle is not None:
            try:
                got = runner.finish(handle)
            except Exception:  # noqa: BLE001 - 收尾失败也要把卡记成失败
                got = None
            if got is not None and got.tokens:
                res.tokens = got.tokens
        _drop_live(runner, rid)
        self.on_run_finished(rid, res)
