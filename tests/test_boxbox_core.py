# -*- coding: utf-8 -*-
"""boxbox v2 core: state machine, card validation, dispatcher flows, HTTP/RPC facade. Stdlib only.

Runs against a temporary data dir and a fake runner; no Pi, no network beyond 127.0.0.1.
    python -m unittest tests.test_boxbox_core -v
"""
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from boxbox import config, tasks  # noqa: E402
from boxbox.dispatcher import Dispatcher  # noqa: E402
from boxbox.facades.http import Core, serve  # noqa: E402
from boxbox.runners.base import Heartbeat, RunHandle, Runner, RunResult  # noqa: E402
from boxbox.store import Store  # noqa: E402

GOOD_CARD = {
    "title": "写一个 hello 文件",
    "goal": "在 cwd 下写 hello.txt，内容为 hello",
    "inputs": ["README.md"],
    "expected_output": {"kind": "doc", "path": "hello.txt"},
    "acceptance": {"review": "leader", "max_rounds": 2},
}


class FakeRunner(Runner):
    """Deterministic runner: 'delivered' immediately unless the card title says 'unreachable'."""
    mode = "once"
    started = []

    def __init__(self, cfg):
        super().__init__(cfg)
        self.alive = {}

    def start(self, task_id, run_id, card, prompt, log_path):
        FakeRunner.started.append((task_id, run_id, card.get("title")))
        pathlib.Path(log_path).write_text(prompt, encoding="utf-8")
        self.alive[run_id] = "unreachable" not in (card.get("title") or "")
        return RunHandle(run_id=run_id, task_id=task_id, station=self.station, pid=4242, log_path=str(log_path))

    def delivered(self, handle):
        return self.alive.get(handle.run_id, False)

    def heartbeat(self, handle):
        a = self.alive.get(handle.run_id, False)
        return Heartbeat(alive=a, finished=not a, last_activity=None)

    def finish(self, handle):
        return RunResult(exit=0 if self.alive.pop(handle.run_id, False) else 12, status="ok",
                         tokens={"in": 100, "out": 20, "cr": 0, "cw": 0, "turns": 1, "source": "pi_session"}, commits=1)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = config.DATA
        config.DATA = pathlib.Path(self.tmp.name)
        config.ensure_dirs()
        config.save_stations([
            {"id": "架构师", "role": "leader", "client": "cursor", "runner": "manual", "enabled": True},
            {"id": "A", "role": "member", "client": "fake", "runner": "once", "enabled": True, "cwd": self.tmp.name,
             "cost": {"in": 1.0, "out": 2.0}},
            {"id": "B", "role": "member", "client": "fake", "runner": "once", "enabled": False},
        ])
        config.save_settings({"ack_timeout_s": 2, "heartbeat_s": 1})
        self.store = Store(config.DATA / "boxbox.db")
        self.d = Dispatcher(self.store)
        FakeRunner.started = []
        self.d.runners = {"A": FakeRunner(config.station("A")), "B": FakeRunner(config.station("B"))}

    def tearDown(self):
        config.DATA = self._old
        # 关库走 store.close()（里面拿锁）：直接 db.close() 会在别的请求线程还在查库时把连接关了 → Windows 上 access violation
        self.store.close()
        self.tmp.cleanup()


class TestTasks(unittest.TestCase):
    def test_validate_card(self):
        self.assertEqual(tasks.validate_card(GOOD_CARD), [])
        bad = dict(GOOD_CARD, goal="", inputs=[], expected_output={"kind": "doc"}, acceptance={})
        errs = tasks.validate_card(bad)
        self.assertEqual(len(errs), 4)
        self.assertTrue(any("goal" in e for e in errs))
        self.assertTrue(any("path" in e for e in errs))
        self.assertTrue(tasks.validate_card(dict(GOOD_CARD, acceptance={"review": "nobody"})))
        self.assertTrue(tasks.validate_card(dict(GOOD_CARD, acceptance={"review": "member:C"})))
        self.assertEqual(tasks.validate_card(dict(GOOD_CARD, expected_output={"kind": "run"})), [])

    def test_state_machine_edges(self):
        for s, evs in tasks.TRANSITIONS.items():
            for ev, nxt in evs.items():
                self.assertIn(nxt, tasks.TRANSITIONS, "%s --%s--> %s not a state" % (s, ev, nxt))
        self.assertEqual(tasks.next_state("dispatched", "heartbeat"), "running")
        self.assertEqual(tasks.next_state("running", "done"), "delivered")
        self.assertEqual(tasks.next_state("delivered", "gates_fail"), "returned")
        self.assertEqual(tasks.next_state("reviewing", "accept"), "accepted")
        self.assertIsNone(tasks.next_state("done", "heartbeat"))
        self.assertIsNone(tasks.next_state("reviewing", "heartbeat"))


class TestStore(Base):
    def test_task_id_is_date_plus_seq(self):
        a = self.store.next_task_id()
        self.assertRegex(a, r"^\d{8}-001$")
        self.store.insert_task({"id": a, "title": "x", "state": "queued", "created_at": "t", "updated_at": "t"})
        self.assertTrue(self.store.next_task_id().endswith("-002"))

    def test_report_key_once(self):
        self.assertTrue(self.store.report_key_once("k"))
        self.assertFalse(self.store.report_key_once("k"))


class TestDispatcher(Base):
    def test_assign_happy_path_then_review_accept(self):
        r = self.d.assign("A", GOOD_CARD, "架构师")
        self.assertEqual(r["code"], "delivered", r)
        tid = r["task_id"]
        self.assertRegex(tid, r"^\d{8}-\d{3}$")
        self.assertTrue((config.DATA / "tasks" / tid / "card.json").exists())
        self.assertTrue((config.DATA / "tasks" / tid / "prompt.txt").exists())
        t = self.store.get_task(tid)
        self.assertEqual(t["state"], "dispatched")
        self.assertEqual(t["dispatcher"], "架构师")
        # member heartbeats -> running; done -> delivered -> reviewing (review=leader)
        self.assertEqual(self.d.report(tid, "heartbeat", "开工", "A")["state"], "running")
        self.assertEqual(self.d.report(tid, "done", "写好了", "A")["state"], "reviewing")
        self.assertEqual(self.d.report(tid, "done", "再报一次", "A")["code"], "duplicate_report")
        # only the dispatcher may review
        self.assertEqual(self.d.review(tid, "accept", "", "A")["code"], "forbidden")
        self.assertEqual(self.d.review(tid, "accept", "好", "架构师")["state"], "done")
        self.assertEqual(self.store.get_task(tid)["state"], "done")
        kinds = [e["kind"] for e in self.store.events(50, task_id=tid)]
        self.assertIn("assign", kinds)
        self.assertIn("done", kinds)

    def test_card_incomplete_rejected(self):
        r = self.d.assign("A", {"goal": "做点什么"}, "架构师")
        self.assertEqual(r["code"], "card_incomplete")
        self.assertEqual(self.store.list_tasks(), [])
        self.assertEqual(FakeRunner.started, [])

    def test_missing_cwd_rejected_before_start(self):
        """卡上写了的工作目录不存在：直接拒收说清楚是哪个目录，不建卡也不开工。"""
        missing = str(pathlib.Path(self.tmp.name) / "no-such-dir")
        r = self.d.assign("A", dict(GOOD_CARD, cwd=missing), "架构师")
        self.assertEqual(r["code"], "bad_cwd")
        self.assertIn(missing, r["text"])
        self.assertEqual(self.store.list_tasks(), [])
        self.assertEqual(FakeRunner.started, [])

    def test_existing_cwd_still_delivered(self):
        """工作目录存在：照旧送达。"""
        r = self.d.assign("A", dict(GOOD_CARD, cwd=self.tmp.name), "架构师")
        self.assertEqual(r["code"], "delivered", r)
        self.assertEqual(len(FakeRunner.started), 1)
        self.assertEqual(self.store.get_task(r["task_id"])["state"], "dispatched")

    def test_duplicate_assign(self):
        a = self.d.assign("A", GOOD_CARD, "架构师")
        b = self.d.assign("A", GOOD_CARD, "架构师")
        self.assertEqual(b["code"], "already_running")
        self.assertEqual(b["task_id"], a["task_id"])
        self.assertEqual(len(FakeRunner.started), 1)

    def test_disabled_station_and_unknown_and_leader(self):
        self.assertEqual(self.d.assign("B", GOOD_CARD, "架构师")["code"], "station_disabled")
        self.assertEqual(self.d.assign("Z", GOOD_CARD, "架构师")["code"], "station_unknown")
        self.assertEqual(self.d.assign("架构师", GOOD_CARD, "架构师")["code"], "not_member")

    def test_unreachable_marks_failed_no_retry(self):
        r = self.d.assign("A", dict(GOOD_CARD, title="unreachable 工位"), "架构师")
        self.assertEqual(r["code"], "unreachable")
        t = self.store.get_task(r["task_id"])
        self.assertEqual(t["state"], "failed")
        self.assertEqual(len(FakeRunner.started), 1)
        run = self.store.runs_for_task(t["id"])[0]
        self.assertIsNotNone(run["ended"])
        self.assertIn(run["exit"], (12, 1))

    def test_run_finished_exit0_delivers_and_records_tokens(self):
        r = self.d.assign("A", GOOD_CARD, "架构师")
        tid, rid = r["task_id"], r["run_id"]
        self.d.on_run_finished(rid, RunResult(exit=0, status="ok",
                                              tokens={"in": 1000, "out": 200, "cr": 0, "cw": 0, "turns": 3, "source": "pi_session"},
                                              commits=1))
        self.assertEqual(self.store.get_task(tid)["state"], "reviewing")
        tok = self.store.tokens_for_task(tid)
        self.assertEqual(tok["tok_in"], 1000)
        self.assertAlmostEqual(tok["cost"], 1000 * 1.0 / 1e6 + 200 * 2.0 / 1e6, places=9)
        # a second finish for the same run is ignored
        self.d.on_run_finished(rid, RunResult(exit=1, status="fail"))
        self.assertEqual(self.store.get_task(tid)["state"], "reviewing")

    def test_run_finished_nonzero_fails(self):
        r = self.d.assign("A", GOOD_CARD, "架构师")
        self.d.on_run_finished(r["run_id"], RunResult(exit=11, status="fail", error="quota"))
        self.assertEqual(self.store.get_task(r["task_id"])["state"], "failed")
        self.assertEqual(self.d.todo()["items"][0]["kind"], "失败")

    def test_return_redispatches_with_reason_then_caps_at_max_rounds(self):
        r = self.d.assign("A", GOOD_CARD, "架构师")
        tid = r["task_id"]
        self.d.report(tid, "done", "v1", "A")
        r2 = self.d.review(tid, "return", "缺标题", "架构师")
        self.assertEqual(r2["code"], "delivered", r2)
        t = self.store.get_task(tid)
        self.assertEqual((t["state"], t["round"], t["returned_reason"]), ("dispatched", 2, "缺标题"))
        self.assertEqual(len(FakeRunner.started), 2)
        prompt2 = (config.DATA / "tasks" / tid / "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("缺标题", prompt2)
        self.d.report(tid, "done", "v2", "A")
        r3 = self.d.review(tid, "return", "还是不行", "架构师")
        self.assertEqual(r3["state"], "returned")
        self.assertEqual(len(FakeRunner.started), 2)
        self.assertEqual(self.d.todo()["items"][0]["kind"], "打回待定")

    def test_review_none_goes_straight_to_done(self):
        r = self.d.assign("A", dict(GOOD_CARD, acceptance={"review": "none"}), "架构师")
        self.d.report(r["task_id"], "done", "ok", "A")
        self.assertEqual(self.store.get_task(r["task_id"])["state"], "done")

    def test_gates_fail_auto_returns_without_leader(self):
        acc = {"review": "leader", "max_rounds": 2, "gates": [{"check": "exists", "path": "hello.txt"}]}
        r = self.d.assign("A", dict(GOOD_CARD, acceptance=acc), "架构师")
        tid = r["task_id"]
        self.d.report(tid, "done", "声称写好了", "A")        # hello.txt never written -> gate fails
        t = self.store.get_task(tid)
        self.assertEqual(t["state"], "dispatched")             # auto-returned and redispatched: round 2
        self.assertEqual(t["round"], 2)
        self.assertIn("质检不过", t["returned_reason"])
        self.assertEqual(len(FakeRunner.started), 2)
        review_md = (tasks.card_dir(tid) / "review.md").read_text(encoding="utf-8")
        self.assertIn("质检 0/1 过", review_md)
        kinds = [e["kind"] for e in self.store.events(20, task_id=tid)]
        self.assertIn("gates_fail", kinds)
        self.assertNotIn("reviewing", kinds)
        # round 2: member actually produces the file -> gates pass -> waits for the leader
        pathlib.Path(self.tmp.name, "hello.txt").write_text("hello", encoding="utf-8")
        self.d.report(tid, "done", "这次真写了", "A")
        t = self.store.get_task(tid)
        self.assertEqual(t["state"], "reviewing")
        self.assertIn("质检 1/1 过", (tasks.card_dir(tid) / "review.md").read_text(encoding="utf-8"))

    def test_gates_pass_then_review_none_is_done(self):
        pathlib.Path(self.tmp.name, "out.md").write_text("# 第1章\n正文\n# 第2章\n", encoding="utf-8")
        acc = {"review": "none", "gates": [{"check": "headings", "path": "out.md", "must": ["第1章", "第2章"]},
                                            {"check": "size", "path": "out.md", "min_chars": 5}]}
        r = self.d.assign("A", dict(GOOD_CARD, acceptance=acc), "架构师")
        self.d.report(r["task_id"], "done", "ok", "A")
        self.assertEqual(self.store.get_task(r["task_id"])["state"], "done")

    def test_blocked_shows_in_todo_first(self):
        r = self.d.assign("A", GOOD_CARD, "架构师")
        self.d.report(r["task_id"], "blocked", "缺 API key", "A")
        td = self.d.todo()
        self.assertEqual(td["items"][0]["kind"], "卡住")
        self.assertIn("A", td["idle_stations"])  # blocked card is not running -> station idle
        self.assertIsNotNone(self.d.nudge())

    def test_board_and_briefing(self):
        self.d.assign("A", GOOD_CARD, "架构师")
        rows = {b["id"]: b for b in self.d.board()}
        self.assertEqual(rows["A"]["word"], "在跑")
        self.assertEqual(rows["B"]["word"], "已停用")
        self.assertEqual(rows["架构师"]["word"], "没连上")        # #88：首领还没来报到过（报到在 HTTP 那层记 first_seen）
        br = self.d.briefing("架构师")
        self.assertEqual(br["role"], "leader")
        self.assertIn("assign", br["tools"])
        self.assertIsNotNone(self.d.leader_last_seen)


class TestHttp(Base):
    def setUp(self):
        super().setUp()
        self.httpd = serve(Core(self.d), 0, block=False)
        self.url = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def _post(self, path, payload, origin=None):
        req = urllib.request.Request(self.url + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def _get(self, path):
        with urllib.request.urlopen(self.url + path, timeout=10) as r:
            return json.loads(r.read().decode())

    def test_rpc_roles_and_flow(self):
        code, r = self._post("/rpc/assign", {"station": "A", "args": {"station": "A", "card": GOOD_CARD}})
        self.assertEqual(r["code"], "forbidden")  # members cannot assign
        code, r = self._post("/rpc/assign", {"station": "架构师", "args": {"station": "A", "card": GOOD_CARD}})
        self.assertEqual(r["code"], "delivered")
        tid = r["task_id"]
        code, r = self._post("/rpc/get_task", {"station": "B", "args": {"task_id": tid}})
        self.assertEqual(r["code"], "forbidden")  # other member cannot read A's card
        code, r = self._post("/rpc/report", {"station": "A", "args": {"task_id": tid, "status": "done", "summary": "ok"}})
        self.assertEqual(r["state"], "reviewing")
        code, r = self._post("/rpc/get_todo", {"station": "架构师", "args": {}})
        self.assertEqual(r["count"], 1)
        self.assertIn("_boxbox", r)
        self.assertEqual(self._get("/api/meta")["open"], 1)
        self.assertEqual(self._get("/api/tasks?state=reviewing")["tasks"][0]["id"], tid)
        self.assertEqual(self._get("/api/tasks/%s" % tid)["task"]["state"], "reviewing")
        self.assertEqual(self._get("/api/stations")["stations"][1]["id"], "A")

    def test_bad_origin_rejected(self):
        code, r = self._post("/rpc/get_board", {"station": "A", "args": {}}, origin="http://evil.example")
        self.assertEqual(code, 403)
        code, r = self._post("/rpc/get_board", {"station": "A", "args": {}}, origin=self.url)
        self.assertEqual(code, 200)


if __name__ == "__main__":
    unittest.main()
