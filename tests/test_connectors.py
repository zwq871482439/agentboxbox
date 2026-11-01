import json
import tempfile
import tomllib
import unittest
from pathlib import Path

import boxbox.connectors as c

STATION = "架构师"
CORE = "http://127.0.0.1:8877"


class TestCursor(unittest.TestCase):
    def test_project_install_preserves_other_entries(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as proj:
            cfg = Path(proj) / ".cursor" / "mcp.json"
            cfg.parent.mkdir(parents=True)
            cfg.write_text(json.dumps({
                "mcpServers": {"other": {"command": "x", "args": []}},
                "unrelatedKey": 1,
            }), encoding="utf-8")

            st = c.install("cursor", STATION, CORE, project_dir=proj, home=home)
            self.assertTrue(st["exists"])
            self.assertTrue(st["installed"])
            self.assertEqual(st["station"], STATION)

            data = json.loads(cfg.read_text(encoding="utf-8"))
            self.assertEqual(data["unrelatedKey"], 1)
            self.assertIn("other", data["mcpServers"])
            entry = data["mcpServers"]["boxbox"]
            self.assertEqual(entry, {"url": c.mcp_url(STATION, CORE)})      # 0.3：Cursor 写 url，不起子进程
            self.assertEqual(c.stdio_entry(STATION, CORE)["args"],
                             ["-m", "boxbox", "mcp", "--station", STATION, "--core", CORE])
            # 备份文件已生成
            self.assertTrue(Path(str(cfg) + ".bak-boxbox").exists())

    def test_cursor_falls_back_to_global(self):
        with tempfile.TemporaryDirectory() as home:
            st = c.install("cursor", STATION, CORE, project_dir=None, home=home)
            self.assertTrue(st["installed"])
            self.assertEqual(Path(st["path"]), Path(home) / ".cursor" / "mcp.json")


class TestClaudeCode(unittest.TestCase):
    def test_global_install_idempotent(self):
        with tempfile.TemporaryDirectory() as home:
            cfg = Path(home) / ".claude.json"
            cfg.write_text(json.dumps({"otherTopKey": {"a": 1}}), encoding="utf-8")

            st1 = c.install("claude-code", STATION, CORE, home=home)
            first = cfg.read_text(encoding="utf-8")
            st2 = c.install("claude-code", STATION, CORE, home=home)
            second = cfg.read_text(encoding="utf-8")

            self.assertTrue(st1["installed"] and st2["installed"])
            self.assertEqual(first, second)  # 装两次内容一样
            data = json.loads(second)
            self.assertEqual(data["otherTopKey"], {"a": 1})
            self.assertIn("boxbox", data["mcpServers"])


class TestCodex(unittest.TestCase):
    def test_append_when_section_missing(self):
        with tempfile.TemporaryDirectory() as home:
            cfg = Path(home) / ".codex" / "config.toml"
            cfg.parent.mkdir(parents=True)
            cfg.write_text('model = "gpt-5"\n', encoding="utf-8")

            st = c.install("codex", STATION, CORE, home=home)
            self.assertTrue(st["installed"])
            self.assertEqual(st["station"], STATION)

            data = tomllib.loads(cfg.read_text(encoding="utf-8"))
            self.assertEqual(data["model"], "gpt-5")
            entry = data["mcp_servers"]["boxbox"]
            self.assertEqual(entry, {"url": c.mcp_url(STATION, CORE)})       # 0.3：Codex 也只写 url，不起子进程占着 exe

    def test_replace_when_section_exists(self):
        with tempfile.TemporaryDirectory() as home:
            cfg = Path(home) / ".codex" / "config.toml"
            cfg.parent.mkdir(parents=True)
            cfg.write_text(
                'model = "gpt-5"\n\n'
                "[mcp_servers.boxbox]\n"
                'command = "/old/python"\n'
                'args = ["-m", "boxbox", "mcp", "--station", "旧工位", "--core", "http://x"]\n\n'
                "[profiles.dev]\n"
                'model = "gpt-5-mini"\n',
                encoding="utf-8",
            )

            st = c.install("codex", STATION, CORE, home=home)
            self.assertTrue(st["installed"])
            self.assertEqual(st["station"], STATION)

            text = cfg.read_text(encoding="utf-8")
            self.assertEqual(text.count("[mcp_servers.boxbox]"), 1)  # 整段替换，不留旧段
            self.assertNotIn("旧工位", text)
            data = tomllib.loads(text)  # 结果必须是合法 TOML
            self.assertEqual(data["profiles"]["dev"]["model"], "gpt-5-mini")  # 后面的段保留
            self.assertEqual(data["mcp_servers"]["boxbox"], {"url": c.mcp_url(STATION, CORE)})   # 旧的 command 写法整段换成 url

            # 幂等：再装一次内容不变
            again = c.install("codex", STATION, CORE, home=home)
            self.assertTrue(again["installed"])
            self.assertEqual(cfg.read_text(encoding="utf-8"), text)


class TestSnippetClients(unittest.TestCase):
    def test_gui_snippet_and_no_path(self):
        for client in ("kimi-code", "minimax-code", "grok-bot", "workbuddy"):
            with self.subTest(client=client):
                snip = c.snippet(client, STATION, CORE)
                self.assertIn('"boxbox"', snip)
                parsed = json.loads(snip)  # 合法 JSON 片段
                self.assertEqual(parsed["mcpServers"]["boxbox"], {"url": c.mcp_url(STATION, CORE)})

                st = c.status(client, home="whatever")
                self.assertIsNone(st["path"])
                self.assertFalse(st["installed"])

    def test_gui_install_raises(self):
        with self.assertRaises(ValueError):
            c.install("kimi-code", STATION, CORE)

    def test_codex_snippet_is_toml(self):
        snip = c.snippet("codex", STATION, CORE)
        data = tomllib.loads(snip)
        self.assertEqual(data["mcp_servers"]["boxbox"], {"url": c.mcp_url(STATION, CORE)})

    def test_every_client_writes_url(self):
        """所有客户端都只写 url（不起 exe 子进程）"""
        for client, conf in c.load().items():
            with self.subTest(client=client):
                self.assertEqual(conf.get("transport"), "http")
                self.assertNotIn("command", c.server_entry(STATION, CORE, client))


if __name__ == "__main__":
    unittest.main()
