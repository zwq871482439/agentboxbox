# -*- coding: utf-8 -*-
"""MCP over HTTP（核心的 /mcp）：客户端配置里只写 url，不起子进程，不占 exe。

  - initialize / tools/list / tools/call 和 stdio 那条路回的一样（共用 mcp_stdio.handle）
  - 通知回 202 没正文；批量请求回数组；GET /mcp 回 405
  - Cursor / Claude Code 的条目写 url，Codex 和只能手贴的客户端照旧 stdio；status 能从 url 里读出工位

    python -m pytest tests/test_mcp_http.py
"""
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from boxbox import config, connectors  # noqa: E402
from boxbox.dispatcher import Dispatcher  # noqa: E402
from boxbox.facades.http import Core, serve  # noqa: E402
from boxbox.store import Store  # noqa: E402

LEADER = {"id": "猫猫首领", "role": "leader", "client": "cursor", "runner": "manual", "enabled": True}


class TestMcpHttp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = config.DATA
        config.DATA = pathlib.Path(self.tmp.name)
        config.ensure_dirs()
        config.save_stations([dict(LEADER)])
        self.d = Dispatcher(Store(config.DATA / "boxbox.db"))
        self.httpd = serve(Core(self.d), 0, block=False)
        self.core = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        self.url = connectors.mcp_url("猫猫首领", self.core)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        # 关库走 store.close()（里面拿锁）：直接 db.close() 会在别的请求线程还在查库时把连接关了 → Windows 上 access violation
        self.d.store.close()
        config.DATA = self._old
        self.tmp.cleanup()

    def rpc(self, payload, url=None):
        req = urllib.request.Request(url or self.url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if body else None)

    def test_initialize_list_call(self):
        code, out = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}})
        self.assertEqual(code, 200)
        self.assertEqual(out["result"]["serverInfo"]["name"], "boxbox")
        self.assertIn("猫猫首领", out["result"]["instructions"])
        code, out = self.rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual((code, out), (202, None))
        _, out = self.rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in out["result"]["tools"]]
        self.assertIn("assign", names)                      # 首领的工具
        self.assertIn("review", names)
        _, out = self.rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_briefing", "arguments": {}}})
        self.assertFalse(out["result"]["isError"], out)
        self.assertEqual(json.loads(out["result"]["content"][0]["text"])["role"], "leader")
        st = self.d.store.station_states().get("猫猫首领") or {}
        self.assertTrue(st.get("first_seen"), "走 HTTP 报到也要记 first_seen（上岗靠它判断连上了）")

    def test_first_briefing_shows_leader_connected(self):
        """第一次拿简报：简报里附的看板就要把首领自己写成连上了，不是「没连上」"""
        _, out = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_briefing", "arguments": {}}})
        brief = json.loads(out["result"]["content"][0]["text"])
        me = next(b for b in brief["board"] if b["id"] == "猫猫首领")
        self.assertNotEqual(me["word_code"], "not_connected", me)
        self.assertNotIn("没连上", brief["text"])

    def test_batch_and_errors(self):
        _, out = self.rpc([{"jsonrpc": "2.0", "id": 1, "method": "ping"},
                           {"jsonrpc": "2.0", "method": "notifications/initialized"},
                           {"jsonrpc": "2.0", "id": 2, "method": "nope"}])
        self.assertEqual([o["id"] for o in out], [1, 2])
        self.assertEqual(out[1]["error"]["code"], -32601)
        _, out = self.rpc({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "get_briefing"}},
                          url=self.core + "/mcp")
        self.assertTrue(out["result"]["isError"])
        self.assertIn("station", out["result"]["content"][0]["text"])

    def test_get_is_405(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(self.url, timeout=10)
        self.assertEqual(cm.exception.code, 405)


class TestEntries(unittest.TestCase):
    CORE = "http://127.0.0.1:8878"

    def test_cursor_and_claude_write_url(self):
        e = connectors.server_entry("猫猫首领", self.CORE, "cursor")
        self.assertEqual(set(e), {"url"})
        self.assertTrue(e["url"].startswith(self.CORE + "/mcp?station="))
        self.assertEqual(connectors.server_entry("猫猫首领", self.CORE, "claude-code")["type"], "http")
        for client in ("codex", "kimi-code", "minimax-code", "grok-bot", "workbuddy"):   # 全部走 url
            self.assertEqual(set(connectors.server_entry("猫猫首领", self.CORE, client)), {"url"}, client)
        self.assertIn("command", connectors.server_entry("猫猫首领", self.CORE))       # 不说是哪家 = 老写法（只剩 `boxbox mcp` 手动用）

    def test_install_and_status_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = connectors.install("cursor", "猫猫首领", self.CORE, project_dir=tmp, home=tmp)
            self.assertTrue(st["installed"])
            self.assertEqual(st["station"], "猫猫首领")
            self.assertIsNone(st["command"])
            data = json.loads(pathlib.Path(st["path"]).read_text(encoding="utf-8"))
            self.assertEqual(list(data["mcpServers"]["boxbox"]), ["url"])
            snip = json.loads(connectors.snippet("cursor", "猫猫首领", self.CORE))
            self.assertIn("url", snip["mcpServers"]["boxbox"])



class TestLeaderLink(TestMcpHttp):
    """#98：MCP 客户端先 initialize；那段话里的 HTTP 兜底直接 tools/call。核心要分得出，上岗窗口才能告诉用户 MCP 没连上。"""
    def state(self):
        with urllib.request.urlopen(self.core + "/api/onboard/state", timeout=10) as r:
            return json.loads(r.read())

    def test_http_fallback_then_mcp(self):
        self.assertIsNone(self.state()["leader_link"])
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_briefing", "arguments": {}}}
        _, out = self.rpc(call)                                           # 没 initialize 直接调：兜底那条路
        self.assertFalse(out["result"]["isError"], out)
        st = self.state()
        self.assertFalse(st["leader_unshaken"])                           # 照样算报到
        self.assertEqual(st["leader_link"], "http")
        self.rpc({"jsonrpc": "2.0", "id": 2, "method": "initialize",
                  "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}})
        self.rpc(dict(call, id=3))
        self.assertEqual(self.state()["leader_link"], "mcp")              # 客户端里 MCP 连上以后改过来

if __name__ == "__main__":
    unittest.main()
