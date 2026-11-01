# -*- coding: utf-8 -*-
"""路径 C 文件档（onboard v0.2 §5.2/§6，卡 20261022-002）：定时任务工位不靠 MCP，
只读 data/exchange/<工位>/current.md 领活；核心派卡时把卡写进这个文件（只覆盖、永远一张卡），
member 做完写 data/tasks/<id>/report.md 并建 DONE 空文件；看门狗看到这两个文件等价于 report(done)；
每次写文件 / 看到文件都记进 exchange_log。Stdlib only, temp data dir, no client.

    python -m unittest tests.test_exchange_file -v
"""
import json
import pathlib
import sys
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from boxbox import config, exchange  # noqa: E402
from boxbox.facades.http import Core, serve  # noqa: E402
from boxbox.watchdog import Watchdog  # noqa: E402

try:  # `python -m unittest tests.test_exchange_file` vs `discover -s tests`
    from tests.test_boxbox_core import GOOD_CARD  # noqa: E402
    from tests.test_scheduled import ScheduledBase  # noqa: E402
except ImportError:  # pragma: no cover
    from test_boxbox_core import GOOD_CARD  # noqa: E402
    from test_scheduled import ScheduledBase  # noqa: E402


REPORT = "## 做了什么：写好了 hello 文件\n## 产出在哪：hello.txt\n## 自检结果：cat 对过\n## 需要谁做什么：无\n"


class FileBase(ScheduledBase):
    """ScheduledBase（工位 K：runner_args 里没写 exchange）再加工位 F：every_min=15，exchange='file'。"""

    def setUp(self):
        super().setUp()
        config.save_stations(config.stations() + [
            {"id": "F", "role": "member", "client": "kimi-code", "runner": "scheduled", "enabled": True,
             "cwd": self.tmp.name, "runner_args": {"every_min": 15, "exchange": "file"}}])

    def current(self):
        return (config.DATA / "exchange" / "F" / "current.md").read_text(encoding="utf-8")

    def log(self, sid="F"):
        return self.store.exchange_log(sid)

    def actions(self, sid="F"):
        return [r["action"] for r in self.log(sid)]


class TestAssignWritesCard(FileBase):
    def test_a_assign_writes_current_md_and_logs(self):
        r = self.d.assign("F", GOOD_CARD, "架构师")
        self.assertEqual(r["code"], "queued", r)
        tid = r["task_id"]
        self.assertEqual(self.store.get_task(tid)["state"], "queued")
        text = self.current()
        self.assertIn(tid, text)                              # 卡头有任务 ID
        self.assertIn("在 cwd 下写 hello.txt", text)          # goal 原文（prompt.txt 里带着卡）
        self.assertIn("回报写到：", text)
        self.assertIn("DONE 写到：", text)
        self.assertEqual(exchange.read_marker(text), (tid, 1))
        self.assertIn("wrote_card", self.actions())
        row = self.log()[0]
        self.assertEqual((row["station"], row["task_id"], row["action"]), ("F", tid, "wrote_card"))
        self.assertGreater(row["bytes"], 0)
        kinds = [e["kind"] for e in self.store.events(50, task_id=tid)]
        self.assertIn("wrote_card", kinds)
        self.assertIn("queued", kinds)

    def test_b_report_md_seen_by_watchdog(self):
        tid = self.d.assign("F", GOOD_CARD, "架构师")["task_id"]
        Watchdog(self.d).tick()                               # 没有文件：照旧排队
        self.assertEqual(self.store.get_task(tid)["state"], "queued")
        (config.DATA / "tasks" / tid / "report.md").write_text(REPORT, encoding="utf-8")
        Watchdog(self.d).tick()
        self.assertEqual(self.store.get_task(tid)["state"], "running")
        run = self.store.runs_for_task(tid)[0]
        self.assertEqual(run["status"], "running")
        self.assertIsNotNone(run["first_activity"])
        self.assertIn("report_seen", self.actions())
        seen = [r for r in self.log() if r["action"] == "report_seen"][0]
        self.assertEqual(seen["bytes"], (config.DATA / "tasks" / tid / "report.md").stat().st_size)
        self.assertIn("report_seen", [e["kind"] for e in self.store.events(50)])

    def test_c_done_file_delivers_then_current_goes_idle(self):
        tid = self.d.assign("F", GOOD_CARD, "架构师")["task_id"]
        d = config.DATA / "tasks" / tid
        (d / "report.md").write_text(REPORT, encoding="utf-8")
        Watchdog(self.d).tick()                               # 交回回报 → running
        (d / "DONE").write_text("", encoding="utf-8")
        Watchdog(self.d).tick()                               # DONE → 等价 report(done)
        t = self.store.get_task(tid)
        self.assertIn(t["state"], ("delivered", "reviewing", "accepted", "done"))
        self.assertEqual(t["state"], "reviewing")             # GOOD_CARD 无质检、review=leader
        self.assertIn("done_seen", self.actions())
        self.assertIn("done_seen", [e["kind"] for e in self.store.events(50)])
        # 摘要取「## 做了什么」那行
        ev = [e for e in self.store.events(50, task_id=tid) if e["kind"] == "report"][0]
        self.assertIn("写好了 hello 文件", ev["text"])
        # 工位没卡排队了 → current.md 改写「没活」
        cur = self.current()
        self.assertIn("没活", cur)
        self.assertIn("再来。", cur)
        self.assertRegex(cur, r"没活：下次 \d{2}:\d{2} 再来。")
        self.assertIn("wrote_idle", self.actions())

    def test_d_second_card_archives_previous_version(self):
        tid1 = self.d.assign("F", GOOD_CARD, "架构师")["task_id"]
        snapshot = self.current()
        tid2 = self.d.assign("F", dict(GOOD_CARD, title="写第二个文件"), "架构师")["task_id"]
        self.assertEqual(self.store.get_task(tid2)["state"], "queued")
        self.assertIn(tid2, self.current())                   # current.md 永远只有最新一张卡
        arc = config.DATA / "tasks" / tid1 / "exchange" / "round-1.md"
        self.assertTrue(arc.exists())                         # 上一版归档进第一张卡目录
        self.assertEqual(arc.read_text(encoding="utf-8"), snapshot)

    def test_e_oversized_card_rejected_without_touching_exchange(self):
        self.d.assign("F", GOOD_CARD, "架构师")
        before = self.current()
        n_before = len(self.store.list_tasks())
        long_card = dict(GOOD_CARD, title="超长卡", goal="写 hello。" + "细节：" + "字" * 20000)
        r = self.d.assign("F", long_card, "架构师")
        self.assertEqual(r["code"], "card_incomplete", r)
        self.assertIn("卡太长", r["text"])
        self.assertIn("12000", r["text"])
        self.assertEqual(self.current(), before)              # 交换文件没被碰
        self.assertEqual(len(self.store.list_tasks()), n_before)  # 也没建卡
        self.assertNotIn("wrote_idle", self.actions())

    def test_f_http_exchange_log_endpoint(self):
        self.d.assign("F", GOOD_CARD, "架构师")
        httpd = serve(Core(self.d), 0, block=False)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        url = "http://127.0.0.1:%d" % httpd.server_address[1]
        with urllib.request.urlopen(url + "/api/exchange/F/log", timeout=10) as r:
            out = json.loads(r.read().decode("utf-8"))
        self.assertEqual(out["station"], "F")
        self.assertTrue(out["items"])
        self.assertEqual(out["items"][0]["action"], "wrote_card")
        try:
            urllib.request.urlopen(url + "/api/exchange/ZZ/log", timeout=10)
            self.fail("不存在的工位应该 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)
            e.close()

    def test_g_old_station_without_exchange_arg_is_file_mode(self):
        r = self.d.assign("K", GOOD_CARD, "架构师")
        self.assertEqual(r["code"], "queued", r)
        cur = config.DATA / "exchange" / "K" / "current.md"
        self.assertTrue(cur.exists())                 # 老工位没写 exchange 也走文件交换
        self.assertIn(r["task_id"], cur.read_text(encoding="utf-8"))
        self.assertIn("wrote_card", [x["action"] for x in self.log("K")])


class TestSummonFileMode(FileBase):
    def test_summon_uses_file_template_without_mcp(self):
        from boxbox.facades import http
        out = http._summon(config.station("F"), "http://127.0.0.1:1")
        self.assertEqual(out["exchange"], "file")
        self.assertIn("current.md", out["prompt"])
        self.assertIn(str(config.DATA / "exchange" / "F"), out["prompt"])
        self.assertIn(self.tmp.name, out["prompt"])           # $cwd 渲染进模板
        self.assertTrue(any("不用配 MCP" in s for s in out["steps"]))
        self.assertIn("15", out["where"])


if __name__ == "__main__":
    unittest.main()
