# -*- coding: utf-8 -*-
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from boxbox import pi_config  # noqa: E402

GOOD_PI = {"base_url": "https://api.example.com/coding", "api": "anthropic-messages",
           "model": "M1", "context_window": 500000,
           "max_tokens": 32000, "reasoning": True}


def st(sid, pi=None, **kw):
    d = {"id": sid, "role": "member", "client": "pi", "runner": "once", "enabled": True,
         "cwd": "C:/work/" + sid, "pi": dict(pi if pi is not None else GOOD_PI)}
    d.update(kw)
    return d


class ProviderName(unittest.TestCase):
    def test_ascii(self):
        self.assertEqual(pi_config.provider_name("A"), "boxbox-a")
        self.assertEqual(pi_config.provider_name("B_2"), "boxbox-b-2")

    def test_non_ascii(self):
        name = pi_config.provider_name("审查")
        self.assertTrue(name.startswith("boxbox-"))
        self.assertTrue(name.isascii(), "中文 id 生成的 provider 名不能含非 ASCII")
        self.assertEqual(name, "boxbox-" + "审查".encode("utf-8").hex()[:8])


class Validate(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(pi_config.validate_pi_block(GOOD_PI), [])

    def test_missing_fields(self):
        errs = pi_config.validate_pi_block({"api": "anthropic-messages"})
        joined = "；".join(errs)
        for k in ("base_url", "model"):
            self.assertIn(k, joined)
        self.assertNotIn("api_key_env", joined)   # 密钥存 data/secrets.json，pi 块里不再有变量名

    def test_bad_api(self):
        errs = pi_config.validate_pi_block({**GOOD_PI, "api": "curl"})
        self.assertTrue(any("api" in e for e in errs))

    def test_bad_numbers(self):
        errs = pi_config.validate_pi_block({**GOOD_PI, "context_window": -1, "max_tokens": 0})
        self.assertTrue(any("context_window" in e for e in errs))
        self.assertTrue(any("max_tokens" in e for e in errs))

    def test_host_of(self):
        self.assertEqual(pi_config.host_of(GOOD_PI), "api.example.com")


class BuildModelsJson(unittest.TestCase):
    def test_one_good_one_bad(self):
        good = st("A")
        bad = st("B", pi={k: v for k, v in GOOD_PI.items() if k != "model"})
        off = st("C", enabled=False)
        other = st("D", client="cursor")
        doc = pi_config.build_models_json([good, bad, off, other])
        self.assertEqual(list(doc["providers"].keys()), ["boxbox-a"])
        self.assertIn("B", doc["_skipped"])
        p = doc["providers"]["boxbox-a"]
        self.assertEqual(p["apiKey"], "$BOXBOX_KEY_A")
        self.assertEqual(p["models"][0]["contextWindow"], 500000)
        self.assertTrue(p["models"][0]["reasoning"])


class WritePiDir(unittest.TestCase):
    def test_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = pi_config.write_pi_dir([st("A")], pathlib.Path(tmp) / "pi")
            with open(d / "models.json", encoding="utf-8") as f:
                doc = json.load(f)
            self.assertNotIn("_skipped", doc)
            key = doc["providers"]["boxbox-a"]["apiKey"]
            self.assertEqual(key, "$BOXBOX_KEY_A")  # 原样引用，不落明文
            blob = json.dumps(doc, ensure_ascii=False)
            self.assertNotIn("real-secret", blob)
            self.assertTrue((d / "settings.json").exists())


class PiEnv(unittest.TestCase):
    def test_env_vars_and_no_mutation(self):
        before = dict(os.environ)
        env = pi_config.pi_env(st("A"))
        self.assertIn("PI_CODING_AGENT_DIR", env)
        self.assertEqual(env["PI_TELEMETRY"], "0")
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(dict(os.environ), before, "pi_env 不能改 os.environ")

    def test_base_env_copy(self):
        base = {"PATH": "x"}
        env = pi_config.pi_env(st("A"), base)
        self.assertEqual(base, {"PATH": "x"})
        self.assertIn("PI_CODING_AGENT_DIR", env)


class PiCliArgv(unittest.TestCase):
    def test_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            cli = tmp / "npm" / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "bundle" / "cli.js"
            cli.parent.mkdir(parents=True)
            cli.write_text("// fake", encoding="utf-8")
            node = tmp / "node.exe"
            node.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"APPDATA": str(tmp)}), \
                 mock.patch.object(pi_config.shutil, "which", lambda name: str(node) if name == "node" else None):
                argv = pi_config.pi_cli_argv(st("A"), "你好", tmp / "sess")
            self.assertEqual(argv[0], str(node))
            self.assertIn("--mode", argv)
            self.assertEqual(argv[argv.index("--mode") + 1], "json")
            self.assertIn("boxbox-a", argv)
            self.assertIn("--no-skills", argv)                                # #120：不加载用户本机 skills
            self.assertIn("--no-prompt-templates", argv)                      # #120：也不加载提示模板
            self.assertNotIn("--no-context-files", argv)                      # 项目里的 AGENTS.md 有用
            self.assertEqual(argv[-1], "你好")

    def test_missing_pi(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"APPDATA": tmp}), \
                 mock.patch.object(pi_config.shutil, "which", lambda name: None):
                with self.assertRaises(FileNotFoundError):
                    pi_config.pi_cli_argv(st("A"), "x", pathlib.Path(tmp))


if __name__ == "__main__":
    unittest.main()
