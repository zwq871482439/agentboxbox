# -*- coding: utf-8 -*-
"""Watchdog tests: first heartbeat -> running, dead child -> failed, core restart -> 'interrupted',
leader silence -> red badge, and the loop must survive a tick() exception. Stdlib only.

    python -m unittest tests.test_watchdog -v
"""
import datetime
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from boxbox import config  # noqa: E402
from boxbox.runners.base import Heartbeat  # noqa: E402
from boxbox.store import now_iso  # noqa: E402
from boxbox.watchdog import Watchdog  # noqa: E402

try:  # `python -m unittest tests.test_watchdog` vs `discover -s tests`
    from tests.test_boxbox_core import GOOD_CARD, Base  # noqa: E402
except ImportError:  # pragma: no cover
    from test_boxbox_core import GOOD_CARD, Base  # noqa: E402


def _ago(minutes):
    return (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=minutes)).isoformat()


class TestWatchdog(Base):
    def test_first_heartbeat_flips_dispatched_to_running(self):
        r = self.d.assign("A", GOOD_CARD, "架构师")
        self.assertEqual(r["code"], "delivered", r)
        tid, rid = r["task_id"], r["run_id"]
        self.assertEqual(self.store.get_task(tid)["state"], "dispatched")
        # FakeRunner.heartbeat gives last_activity=None; patch it to report activity (FakeRunner itself untouched)
        hb = Heartbeat(alive=True, finished=False, last_activity=now_iso(), evidence="pid 4242")
        with patch.object(self.d.runners["A"], "heartbeat", return_value=hb):
            Watchdog(self.d).tick()
        self.assertEqual(self.store.get_task(tid)["state"], "running")
        run = self.store.get_run(rid)
        self.assertIsNotNone(run["first_activity"])
        self.assertIsNotNone(run["last_activity"])
        self.assertIsNone(run["ended"])
        kinds = [e["kind"] for e in self.store.events(50, task_id=tid)]
        self.assertIn("running", kinds)

    def test_dead_process_marks_task_failed(self):
        r = self.d.assign("A", GOOD_CARD, "架构师")
        tid, rid = r["task_id"], r["run_id"]
        self.d.runners["A"].alive[rid] = False  # child process died -> heartbeat finished, finish() exit=12
        Watchdog(self.d).tick()
        self.assertEqual(self.store.get_task(tid)["state"], "failed")
        run = self.store.get_run(rid)
        self.assertIsNotNone(run["ended"])
        self.assertEqual(run["exit"], 12)
        kinds = [e["kind"] for e in self.store.events(50, task_id=tid)]
        self.assertIn("failed", kinds)

    def test_core_restart_closes_run_as_process_lost(self):
        """#97 核心重启、进程也不在了 = 上次没正常退出：卡记「中断」（不是 failed），下次能接着做"""
        r = self.d.assign("A", GOOD_CARD, "架构师")
        tid, rid = r["task_id"], r["run_id"]
        self.d.handles.clear()  # core restarted: handles gone, old process invisible
        Watchdog(self.d).tick()
        t = self.store.get_task(tid)
        self.assertEqual(t["state"], "interrupted")
        self.assertIn("上次没正常退出", t["returned_reason"] or "")
        run = self.store.get_run(rid)
        self.assertIsNotNone(run["ended"])
        self.assertIn("上次没正常退出", run["error"] or "")
        kinds = [e["kind"] for e in self.store.events(50, task_id=tid)]
        self.assertNotIn("failed", kinds)
        self.assertIn("interrupted", kinds)

    def test_badge_red_and_leader_silence(self):
        config.save_settings({"ack_timeout_s": 2, "heartbeat_s": 1, "wake_min": 30})
        wd = Watchdog(self.d)
        wd.tick()
        self.assertFalse(self.store.kv_get("badge")["red"])          # nothing waiting -> no red dot
        r = self.d.assign("A", GOOD_CARD, "架构师")
        self.d.report(r["task_id"], "blocked", "缺 API key", "A")      # -> TeamLeader 的待办非空；用户没事 -> 不红
        wd.tick()
        badge = self.store.kv_get("badge")
        self.assertFalse(badge["red"])
        self.assertEqual(badge["todo"], 0)
        self.assertEqual(badge["leader_todo"], 1)
        self.d.leader_last_seen = _ago(60)                             # silent 60min >= wake_min 30
        wd.tick()
        badge = self.store.kv_get("badge")
        self.assertTrue(badge["summon_leader"])
        self.d.leader_last_seen = _ago(1)                              # leader active -> no summon; nothing for the user -> no red
        wd.tick()
        badge = self.store.kv_get("badge")
        self.assertFalse(badge["red"])
        self.assertFalse(badge["summon_leader"])
        self.d.leader_last_seen = None                                 # never showed up, todo pending -> summon
        wd.tick()
        self.assertTrue(self.store.kv_get("badge")["summon_leader"])
        # #82：badge 只留在 kv 里给旧代码用，不再往动态写「要你处理的事」事件；级别以 /api/meta 的 alerts 为准
        self.assertNotIn("badge", [e["kind"] for e in self.store.events(50)])
        self.assertNotIn("pin", self.store.kv_get("badge"))            # pin_min 已删

    def test_tick_exception_is_swallowed_by_run_loop(self):
        r = self.d.assign("A", GOOD_CARD, "架构师")
        self.assertEqual(r["code"], "delivered", r)
        wd = Watchdog(self.d)

        def boom(handle):
            wd.stop_flag.set()            # one iteration only, then run() may exit
            raise RuntimeError("boom")

        with patch.object(self.d.runners["A"], "heartbeat", side_effect=boom):
            wd.run()                      # must not raise: the watchdog never dies
        kinds = [e["kind"] for e in self.store.events(50)]
        self.assertIn("watchdog_error", kinds)


if __name__ == "__main__":
    unittest.main()
