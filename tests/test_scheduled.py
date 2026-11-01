# -*- coding: utf-8 -*-
"""定时任务工位（会话模式）：派活只排队不起进程；卡写进交换文件，定时任务读它、干完交回回报；
交回后长时间没 DONE 算失败；核心重启不误杀；看板给定时工位单独的状态词。Stdlib only, temp data dir, no client.

    python -m unittest tests.test_scheduled -v
"""
import datetime
import os
import pathlib
import sys
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from boxbox import config, exchange  # noqa: E402
from boxbox.facades.http import Core, serve  # noqa: E402
from boxbox.runners import make_runner  # noqa: E402
from boxbox.watchdog import Watchdog  # noqa: E402

try:  # `python -m unittest tests.test_scheduled` vs `discover -s tests`
    from tests.test_boxbox_core import GOOD_CARD, Base, FakeRunner  # noqa: E402
except ImportError:  # pragma: no cover
    from test_boxbox_core import GOOD_CARD, Base, FakeRunner  # noqa: E402


REPORT = "## 做了什么：写好了 hello 文件\n## 产出在哪：hello.txt\n## 自检结果：cat 对过\n## 需要谁做什么：无\n"


def _ago(minutes):
    return (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=minutes)).isoformat()


def _dt_parse(iso):
    return datetime.datetime.fromisoformat(iso) if iso else None


class ScheduledBase(Base):
    """Base + 工位 K：定时任务工位，every_min=15（老工位：runner_args 里没写 exchange）。"""

    def setUp(self):
        super().setUp()
        config.save_stations(config.stations() + [
            {"id": "K", "role": "member", "client": "grok-bot", "runner": "scheduled", "enabled": True,
             "cwd": self.tmp.name, "runner_args": {"every_min": 15}}])

    def row(self, sid="K"):
        return {b["id"]: b for b in self.d.board()}[sid]

    def current(self, sid="K"):
        return (config.DATA / "exchange" / sid / "current.md").read_text(encoding="utf-8")

    def hand_in(self, tid, done=True):
        """模拟定时任务交回：写 report.md（= 开工了），需要时再建 DONE。"""
        d = config.DATA / "tasks" / tid
        (d / "report.md").write_text(REPORT, encoding="utf-8")
        if done:
            (d / "DONE").write_text("", encoding="utf-8")


class TestAssignQueues(ScheduledBase):
    def test_assign_queues_without_starting_a_process(self):
        r = self.d.assign("K", GOOD_CARD, "架构师")
        self.assertEqual(r["code"], "queued", r)
        self.assertTrue(r["ok"])
        self.assertTrue(r["queued"])
        tid = r["task_id"]
        self.assertEqual(self.store.get_task(tid)["state"], "queued")
        run = self.store.runs_for_task(tid)[0]
        self.assertEqual(run["runner"], "scheduled")
        self.assertIsNone(run["ended"])
        self.assertIsNone(run["pid"])
        self.assertEqual(FakeRunner.started, [])          # 什么进程都没起
        self.assertIn("queued", [e["kind"] for e in self.store.events(50, task_id=tid)])

    def test_card_goes_into_the_exchange_file(self):
        tid = self.d.assign("K", GOOD_CARD, "架构师")["task_id"]
        text = self.current()
        self.assertIn(tid, text)                          # 卡就在交换文件里，定时任务读它
        self.assertIn("wrote_card", [r["action"] for r in self.store.exchange_log("K")])

    def test_same_card_not_queued_twice(self):
        a = self.d.assign("K", GOOD_CARD, "架构师")
        b = self.d.assign("K", GOOD_CARD, "架构师")
        self.assertEqual(b["code"], "already_running", b)
        self.assertEqual(b["task_id"], a["task_id"])
        self.assertEqual(len(self.store.list_tasks(state="queued")), 1)

    def test_make_runner_gives_scheduled_for_any_client(self):
        self.assertEqual(make_runner({"id": "K", "runner": "scheduled", "client": "grok-bot"}).mode, "scheduled")
        self.assertEqual(make_runner({"id": "K", "runner": "scheduled", "client": "kimi-code"}).mode, "scheduled")
        self.assertIsNone(make_runner({"id": "X", "runner": "hold", "client": "zcode"}))


class TestExchangeFile(ScheduledBase):
    def test_report_file_marks_the_card_running(self):
        tid = self.d.assign("K", GOOD_CARD, "架构师")["task_id"]
        Watchdog(self.d).tick()                            # 还没交回：照旧排队
        self.assertEqual(self.store.get_task(tid)["state"], "queued")
        (config.DATA / "tasks" / tid / "report.md").write_text(REPORT, encoding="utf-8")
        Watchdog(self.d).tick()
        self.assertEqual(self.store.get_task(tid)["state"], "running")
        run = self.store.runs_for_task(tid)[0]
        self.assertEqual(run["status"], "running")
        self.assertIsNotNone(run["first_activity"])
        self.assertIn("report_seen", [r["action"] for r in self.store.exchange_log("K")])

    def test_done_file_delivers_the_card(self):
        tid = self.d.assign("K", GOOD_CARD, "架构师")["task_id"]
        self.hand_in(tid)
        Watchdog(self.d).tick()
        t = self.store.get_task(tid)
        self.assertEqual(t["state"], "reviewing")          # 无质检、review=leader
        self.assertIn("done_seen", [r["action"] for r in self.store.exchange_log("K")])
        self.assertIn("没活", self.current())              # 没卡排队了 → 交换文件改写「没活」

    def test_gates_fail_requeues_round_two(self):
        acc = {"review": "leader", "max_rounds": 2, "gates": [{"check": "exists", "path": "hello.txt"}]}
        tid = self.d.assign("K", dict(GOOD_CARD, acceptance=acc), "架构师")["task_id"]
        self.hand_in(tid)
        Watchdog(self.d).tick()                            # 质检不过 → 自动打回第 2 轮
        t = self.store.get_task(tid)
        self.assertEqual((t["state"], t["round"]), ("queued", 2))
        runs = self.store.runs_for_task(tid)
        self.assertIsNotNone(runs[0]["ended"])              # 第 1 轮的 run 已关
        self.assertIsNone(runs[-1]["ended"])                # 第 2 轮在排队
        self.assertIn(tid, self.current())                  # 交换文件里是第 2 轮那张卡


class TestWatchdogAndRestart(ScheduledBase):
    def test_no_done_after_timeout_fails_the_card(self):
        tid = self.d.assign("K", GOOD_CARD, "架构师")["task_id"]
        (config.DATA / "tasks" / tid / "report.md").write_text(REPORT, encoding="utf-8")
        Watchdog(self.d).tick()                            # 交回回报 → 在跑
        run_id = self.store.runs_for_task(tid)[0]["run_id"]
        self.d.handles[run_id].extra["picked_at"] = _ago(60)     # 60 分钟前交的回报，超时 2×15
        Watchdog(self.d).tick()
        self.assertEqual(self.store.get_task(tid)["state"], "failed")
        run = self.store.get_run(run_id)
        self.assertIsNotNone(run["ended"])
        self.assertEqual(run["exit"], 12)
        self.assertIn("没有回报", run["error"] or "")
        self.assertEqual(self.d.todo()["items"][0]["kind"], "失败")

    def test_core_restart_keeps_queued_and_running_cards(self):
        tid = self.d.assign("K", GOOD_CARD, "架构师")["task_id"]
        (config.DATA / "tasks" / tid / "report.md").write_text(REPORT, encoding="utf-8")
        Watchdog(self.d).tick()                            # 在跑
        run_id = self.store.runs_for_task(tid)[0]["run_id"]
        queued_id = self.d.assign("K", dict(GOOD_CARD, title="写第二个文件"), "架构师")["task_id"]
        self.d.handles.clear()                             # 核心重启：句柄全没了
        Watchdog(self.d).tick()
        self.assertEqual(self.store.get_task(tid)["state"], "running")
        self.assertIsNone(self.store.get_run(run_id)["ended"])
        self.assertIn(run_id, self.d.handles)               # 从 runs 行重新认领
        self.assertEqual(self.store.get_task(queued_id)["state"], "queued")
        self.assertIsNone(self.store.runs_for_task(queued_id)[0]["ended"])

    def test_queued_card_never_goes_stale_on_its_own(self):
        tid = self.d.assign("K", GOOD_CARD, "架构师")["task_id"]
        self.d.handles.clear()
        Watchdog(self.d).tick()
        self.assertEqual(self.store.get_task(tid)["state"], "queued")
        self.assertIsNone(self.store.runs_for_task(tid)[0]["ended"])


class TestBoardWords(ScheduledBase):
    def test_word_for_each_scheduled_stage(self):
        self.assertEqual(self.row()["word"], "待定时任务")        # 定时任务还没来过
        self.assertFalse(self.row()["scheduled_late"])
        self.assertIsNone(self.row()["last_scheduled_at"])
        tid = self.d.assign("K", GOOD_CARD, "架构师")["task_id"]
        self.assertEqual(self.row()["word"], "待定时任务")        # 有卡排队，人还没来
        (config.DATA / "tasks" / tid / "report.md").write_text(REPORT, encoding="utf-8")
        Watchdog(self.d).tick()
        self.assertEqual(self.row()["word"], "在跑")              # 定时任务领走了，正在干
        self.assertTrue(self.row()["last_scheduled_at"])
        (config.DATA / "tasks" / tid / "DONE").write_text("", encoding="utf-8")
        Watchdog(self.d).tick()
        self.assertEqual(self.row()["word"], "在岗（定时）")      # 干完了，在岗
        self.store.station_touch("K", last_scheduled_at=_ago(60), state="idle")
        self.assertEqual(self.row()["word"], "定时任务没触发")     # 超过 2×15 分钟没来
        self.assertTrue(self.row()["scheduled_late"])
        # 非定时工位不受影响
        self.assertEqual(self.row("A")["word"], "闲")
        self.assertFalse(self.row("A")["scheduled_late"])


class TestSeenMarker(ScheduledBase):
    """定时任务每次被叫起来都写 seen.txt：盒子看到文件更新就知道它来过（没活也算）。"""

    def write_seen(self, sid="K", when=None):
        """写 seen.txt（时间写进文件内容，修改时间才是盒子看的）；when 用来固定修改时间。"""
        p = exchange.seen_path(sid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text((when or datetime.datetime.now().astimezone()).isoformat() + "\n", encoding="utf-8")
        if when is not None:
            ts = when.timestamp()
            os.utime(p, (ts, ts))
        return p

    def last_at(self, sid="K"):
        return (self.store.station_states().get(sid) or {}).get("last_scheduled_at")

    def test_seen_file_marks_the_station_as_came(self):
        t1 = datetime.datetime.now().astimezone().replace(microsecond=0) - datetime.timedelta(minutes=3)
        self.write_seen(when=t1)
        Watchdog(self.d).tick()
        self.assertTrue(self.last_at(), "写完 seen.txt 走一轮看门狗就该记上它来过")
        self.assertEqual(_dt_parse(self.last_at()), t1)
        kinds = [e["kind"] for e in self.store.events(50)]
        self.assertIn("scheduled_on", kinds)

    def test_seen_file_again_updates_time_without_new_event(self):
        t1 = datetime.datetime.now().astimezone().replace(microsecond=0) - datetime.timedelta(minutes=5)
        self.write_seen(when=t1)
        Watchdog(self.d).tick()
        t2 = t1 + datetime.timedelta(minutes=2)
        self.write_seen(when=t2)
        Watchdog(self.d).tick()
        self.assertEqual(_dt_parse(self.last_at()), t2)
        self.assertEqual(len([e for e in self.store.events(50) if e["kind"] == "scheduled_on"]), 1)

    def test_no_seen_file_is_fine(self):
        Watchdog(self.d).tick()                              # 没写过 seen.txt：不报错，只是没来过
        self.assertIsNone(self.last_at())
        self.assertNotIn("watchdog_error", [e["kind"] for e in self.store.events(50)])


class TestFacades(ScheduledBase):
    def test_briefing_has_no_pickup_tool(self):
        br = self.d.briefing("K")
        self.assertNotIn("wait_for_work", br["tools"])
        self.assertNotIn("get_todo", br["tools"])

    def test_pickup_endpoint_is_gone(self):
        httpd = serve(Core(self.d), 0, block=False)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        url = "http://127.0.0.1:%d" % httpd.server_address[1]
        self.d.assign("K", GOOD_CARD, "架构师")
        try:
            urllib.request.urlopen(url + "/api/work/next?station=K", timeout=10)
            self.fail("靠接口领活那条路应该没了")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)
            e.close()


if __name__ == "__main__":
    unittest.main()
