"""Runner for scheduled stations: the AI app's own timer starts a brand-new session every `every_min`
minutes; that session reads the exchange file (data/exchange/<station>/current.md), does the card and
writes the report back.

Nothing is launched here. `start()` only records the run row's skeleton: assigning a card is a queue
entry, and the card only reaches the model when the timed session reads the exchange file. Pick-up with
no report back within `work_timeout_min` means the session is gone -> finish() exits 12, card failed.
"""
from __future__ import annotations

import datetime as _dt
import pathlib

from .. import i18n
from .base import Heartbeat, RunHandle, Runner, RunResult


def _mins_since(iso) -> float:
    """Minutes elapsed since an ISO stamp; 0 when absent or unparseable (never negative-blows up the run)."""
    if not iso:
        return 0.0
    try:
        return (_dt.datetime.now().astimezone() - _dt.datetime.fromisoformat(str(iso))).total_seconds() / 60
    except (TypeError, ValueError):
        return 0.0


class ScheduledRunner(Runner):
    mode = "scheduled"

    def every_min(self) -> int:
        try:
            return int((self.cfg.get("runner_args") or {}).get("every_min") or 30)
        except (TypeError, ValueError):
            return 30

    def timeout_min(self) -> int:
        try:
            return int((self.cfg.get("runner_args") or {}).get("work_timeout_min") or 2 * self.every_min())
        except (TypeError, ValueError):
            return 2 * self.every_min()

    # ---- no process: start() just opens the run row ----
    def start(self, task_id: str, run_id: str, card: dict, prompt: str, log_path) -> RunHandle:
        try:
            pathlib.Path(log_path).write_text(prompt, encoding="utf-8")
        except OSError:
            pass
        return RunHandle(run_id=run_id, task_id=task_id, station=self.station, pid=None,
                         log_path=str(log_path),
                         extra={"picked_at": None, "last_report_at": None, "reported": None})

    def delivered(self, handle: RunHandle) -> bool:
        return False  # no process to come up; the dispatcher does not wait for a receipt either

    # ---- heartbeat ----
    def heartbeat(self, handle: RunHandle) -> Heartbeat:
        picked = handle.extra.get("picked_at")
        if not picked:
            return Heartbeat(alive=True, finished=False, last_activity=None)  # queued, waiting for the next trigger
        last = handle.extra.get("last_report_at") or picked
        lost = _mins_since(last) > self.timeout_min() and not handle.extra.get("reported")
        return Heartbeat(alive=not lost, finished=lost, last_activity=last, evidence="tool")

    def finish(self, handle: RunHandle) -> RunResult:
        if handle.extra.get("reported"):
            return RunResult(exit=0, status="ok")
        return RunResult(exit=12, status="fail",
                         error=i18n.t("runner.sched_timeout", self.lang, n=self.timeout_min()))

    def adopt(self, run_row: dict) -> RunHandle:
        """Rebuild a handle from a runs row (core restarted: no process, but the card may still be running)."""
        return RunHandle(run_id=run_row["run_id"], task_id=run_row["task_id"], station=run_row["station"],
                         pid=run_row.get("pid"), session_id=run_row.get("session_id"),
                         started_at=run_row.get("started") or "", log_path=run_row.get("log_path") or "",
                         extra={"picked_at": run_row.get("first_activity"),
                                "last_report_at": run_row.get("last_activity"), "reported": None})
