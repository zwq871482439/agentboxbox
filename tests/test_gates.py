"""质检与安全执行单测（任务卡 20261021-003）。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from boxbox import gates, safe_exec
from boxbox.gates import GateResult
from boxbox.safe_exec import RejectedArgv


class TestExists(unittest.TestCase):
    def test_glob_hit(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "out"))
            with open(os.path.join(d, "out", "a.md"), "w", encoding="utf-8") as f:
                f.write("内容")
            r = gates.run_gate({"check": "exists", "path": "out/*.md"}, d, "20261021-003")
            self.assertTrue(r.ok, r.reason)

    def test_empty_file_fails(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "empty.txt"), "w", encoding="utf-8").close()
            r = gates.run_gate({"check": "exists", "path": "empty.txt"}, d, "20261021-003")
            self.assertFalse(r.ok)
            self.assertIn("空", r.reason)

    def test_no_match_fails(self):
        with tempfile.TemporaryDirectory() as d:
            r = gates.run_gate({"check": "exists", "path": "nothing-*.txt"}, d, "20261021-003")
            self.assertFalse(r.ok)


class TestHeadings(unittest.TestCase):
    def _write(self, d):
        with open(os.path.join(d, "doc.md"), "w", encoding="utf-8") as f:
            f.write("# 第1章 概述\n\n正文\n\n## 第2章 细节\n")

    def test_markdown_heading_hit(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d)
            r = gates.run_gate({"check": "headings", "path": "doc.md",
                                "must": ["第1章", "第2章"]}, d, "20261021-003")
            self.assertTrue(r.ok, r.reason)

    def test_missing_listed_in_reason(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d)
            r = gates.run_gate({"check": "headings", "path": "doc.md",
                                "must": ["第1章", "第9章"]}, d, "20261021-003")
            self.assertFalse(r.ok)
            self.assertIn("第9章", r.reason)
            self.assertNotIn("第1章、", r.reason)


class TestJsonAndSize(unittest.TestCase):
    def test_json_ok(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "data.json"), "w", encoding="utf-8") as f:
                json.dump({"a": 1, "b": 2}, f)
            r = gates.run_gate({"check": "json", "path": "data.json", "keys": ["a", "b"]},
                               d, "20261021-003")
            self.assertTrue(r.ok, r.reason)

    def test_json_missing_key(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "data.json"), "w", encoding="utf-8") as f:
                json.dump({"a": 1}, f)
            r = gates.run_gate({"check": "json", "path": "data.json", "keys": ["a", "c"]},
                               d, "20261021-003")
            self.assertFalse(r.ok)
            self.assertIn("c", r.reason)

    def test_size_ok(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "t.txt"), "w", encoding="utf-8") as f:
                f.write("字" * 100)
            r = gates.run_gate({"check": "size", "path": "t.txt", "min_chars": 50},
                               d, "20261021-003")
            self.assertTrue(r.ok, r.reason)

    def test_size_too_small(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "t.txt"), "w", encoding="utf-8") as f:
                f.write("字" * 10)
            r = gates.run_gate({"check": "size", "path": "t.txt", "min_chars": 200},
                               d, "20261021-003")
            self.assertFalse(r.ok)


class TestCommits(unittest.TestCase):
    def setUp(self):
        if not shutil.which("git"):
            self.skipTest("git 不可用")

    def _repo(self, d):
        def git(*args):
            subprocess.run(["git", *args], cwd=d, shell=False, check=True,
                           capture_output=True)
        git("init")
        git("config", "user.name", "test")
        git("config", "user.email", "test@example.com")
        for name in ("a.txt", "b.txt"):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(name)
            git("add", name)
            git("commit", "-m", "add " + name)

    def test_clean_repo_passes(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            r = gates.run_gate({"check": "commits", "min": 1}, d, "20261021-003")
            self.assertTrue(r.ok, r.reason)

    def test_dirty_tree_fails(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            with open(os.path.join(d, "dirty.txt"), "w", encoding="utf-8") as f:
                f.write("未提交")
            r = gates.run_gate({"check": "commits", "min": 1}, d, "20261021-003")
            self.assertFalse(r.ok)
            self.assertIn("不干净", r.reason)


class TestCommand(unittest.TestCase):
    CHECKS = {
        "pass0": {"argv": [sys.executable, "-c", "import sys; sys.exit(0)"],
                  "cwd": None, "timeout_s": 30},
        "fail3": {"argv": [sys.executable, "-c", "import sys; sys.exit(3)"],
                  "cwd": None, "timeout_s": 30},
    }

    def test_exit0_passes(self):
        with tempfile.TemporaryDirectory() as d:
            r = gates.run_gate({"check": "command", "name": "pass0"}, d, "20261021-003",
                               checks=self.CHECKS)
            self.assertTrue(r.ok, r.reason)

    def test_exit3_fails(self):
        with tempfile.TemporaryDirectory() as d:
            r = gates.run_gate({"check": "command", "name": "fail3"}, d, "20261021-003",
                               checks=self.CHECKS)
            self.assertFalse(r.ok)
            self.assertIn("3", r.reason)

    def test_unregistered_name_fails(self):
        with tempfile.TemporaryDirectory() as d:
            r = gates.run_gate({"check": "command", "name": "nope"}, d, "20261021-003",
                               checks=self.CHECKS)
            self.assertFalse(r.ok)
            self.assertIn("未登记", r.reason)


class TestSafeExecInjection(unittest.TestCase):
    def _resolve(self, argv, values):
        with tempfile.TemporaryDirectory() as d:
            return safe_exec.resolve_argv(argv, values, d)

    def test_all_injections_rejected(self):
        cases = [
            (["x", "{path}"], {"path": "../x"}),
            (["x", "{path}"], {"path": "C:\\x"}),
            (["x", "{path}"], {"path": "/etc/passwd"}),
            (["x", "{path}"], {"path": "-rf"}),
            (["x", "{path}"], {"path": "a; rm -rf /"}),
            (["x", "--file={path}"], {"path": "ok.txt"}),
            (["x", "{task_id}"], {"task_id": "20261021-3"}),
            (["x", "{pr}"], {"pr": "1"}),
        ]
        for argv, values in cases:
            with self.subTest(argv=argv, values=values):
                with self.assertRaises(RejectedArgv):
                    self._resolve(argv, values)

    def test_legit_path_resolves_inside_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            out = safe_exec.resolve_argv(["tool", "{path}"], {"path": "sub/f.txt"}, d)
            self.assertTrue(out[1].startswith(os.path.realpath(d)) or
                            out[1].lower().startswith(os.path.realpath(d).lower()))

    def test_allowed_args_whitelist(self):
        with tempfile.TemporaryDirectory() as d:
            out = safe_exec.resolve_argv(["tool", "{mode}"], {"mode": "fast"}, d,
                                         {"mode": "^(fast|slow)$"})
            self.assertEqual(out, ["tool", "fast"])
            with self.assertRaises(RejectedArgv):
                safe_exec.resolve_argv(["tool", "{mode}"], {"mode": "fast; rm"}, d,
                                       {"mode": "^(fast|slow)$"})


class TestRunArgv(unittest.TestCase):
    def test_timeout(self):
        r = safe_exec.run_argv([sys.executable, "-c", "import time; time.sleep(5)"],
                               os.getcwd(), timeout_s=1)
        self.assertTrue(r["timed_out"])
        self.assertIsNone(r["exit"])

    def test_output_captured_utf8(self):
        r = safe_exec.run_argv([sys.executable, "-c", "print('中文'); import sys; sys.exit(0)"],
                               os.getcwd(), timeout_s=30)
        self.assertEqual(r["exit"], 0)
        self.assertIn("中文", r["stdout"])


class TestRenderReviewMd(unittest.TestCase):
    def test_summary_line(self):
        results = [
            GateResult("exists", True, "", "path=a.md"),
            GateResult("headings", False, "缺标题：第9章", "path=a.md"),
            GateResult("size", True, "", "path=a.md min_chars=50"),
        ]
        md = gates.render_review_md(results)
        self.assertIn("## 质检", md)
        self.assertIn("- [x] exists", md)
        self.assertIn("- [ ] headings", md)
        self.assertIn("缺标题：第9章", md)
        self.assertIn("质检 2/3 过", md)

    def test_unknown_check(self):
        with tempfile.TemporaryDirectory() as d:
            r = gates.run_gate({"check": "magic"}, d, "20261021-003")
            self.assertFalse(r.ok)
            self.assertIn("未知检查器", r.reason)

    def test_run_gates_no_short_circuit(self):
        with tempfile.TemporaryDirectory() as d:
            card = {"id": "20261021-003",
                    "acceptance": {"gates": [{"check": "exists", "path": "nope"},
                                             {"check": "magic"},
                                             {"check": "exists", "path": "also-nope"}]}}
            results = gates.run_gates(card, d, checks={})
            self.assertEqual(len(results), 3)
            self.assertFalse(any(r.ok for r in results))


if __name__ == "__main__":
    unittest.main()
