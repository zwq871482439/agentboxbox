"""pi --mode json 事件流解析器单测（工作计划 2.3 中段）。

样例行都是自己构造的常量，形状照 pi-coding-agent docs/json.md + message-types.md。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from boxbox.pi_events import PiEventParser, stale_hit_in_text  # noqa: E402


def _line(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


SESSION = {"type": "session", "version": 3, "id": "sess-1",
           "timestamp": "2026-10-21T00:00:00.000Z", "cwd": r"C:\work\proj"}

# 第 1 条 assistant：带一个 bash toolCall，stopReason=toolUse
ASSISTANT_TOOL = {
    "type": "message_end",
    "message": {
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": "先看 git 状态"},
            {"type": "text", "text": "查一下仓库状态。"},
            {"type": "toolCall", "id": "c1", "name": "bash", "arguments": {"command": "git  status --short"}},
        ],
        "api": "anthropic-messages", "provider": "anthropic", "model": "claude-x",
        "usage": {"input": 1200, "output": 45, "cacheRead": 300, "cacheWrite": 0, "totalTokens": 1545},
        "stopReason": "toolUse", "timestamp": 1733234401000,
    },
}

TOOL_RESULT = {
    "type": "message_end",
    "message": {
        "role": "toolResult", "toolCallId": "c1", "toolName": "bash",
        "content": [{"type": "text", "text": " M boxbox/pi_events.py\n"}],
        "isError": False, "timestamp": 1733234401500,
    },
}

# 第 2 条 assistant：纯文本收尾，stopReason=stop
ASSISTANT_FINAL = {
    "type": "message_end",
    "message": {
        "role": "assistant",
        "content": [{"type": "text", "text": "解析器已写好，"},
                    {"type": "text", "text": "单测全过。"}],
        "usage": {"input": 1500, "output": 60, "cacheRead": 1200, "cacheWrite": 10, "totalTokens": 2770},
        "stopReason": "stop", "timestamp": 1733234402000,
    },
}

TURN_END = {"type": "turn_end", "message": ASSISTANT_FINAL["message"], "toolResults": []}
AGENT_END = {"type": "agent_end", "messages": [ASSISTANT_TOOL["message"]], "willRetry": False}
AGENT_SETTLED = {"type": "agent_settled", "aborted": False}

GOOD_STREAM = "".join(_line(e) + "\n" for e in
                      [SESSION, ASSISTANT_TOOL, TOOL_RESULT, ASSISTANT_FINAL, TURN_END, AGENT_END, AGENT_SETTLED])


def _parse(stream: str) -> PiEventParser:
    p = PiEventParser()
    p.feed(stream)
    p.close()
    return p


class TestGoodStream(unittest.TestCase):
    def setUp(self):
        self.p = _parse(GOOD_STREAM)
        self.r = self.p.run

    def test_usage_accumulated_once_per_assistant(self):
        u = self.r.usage
        self.assertEqual((u.input, u.output, u.cache_read, u.cache_write, u.turns), (2700, 105, 1500, 10, 2))
        self.assertEqual(u.as_dict(), {"in": 2700, "out": 105, "cr": 1500, "cw": 10, "turns": 2, "source": "pi_json"})

    def test_tools_and_last_tool(self):
        self.assertEqual(self.r.tool_calls, 1)
        self.assertEqual(self.r.last_tool, "bash: git status --short")  # 空白折叠成一个空格

    def test_final_text_and_stop(self):
        self.assertEqual(self.r.final_text, "解析器已写好，单测全过。")
        self.assertEqual(self.r.stop_reason, "stop")
        self.assertTrue(self.r.settled)
        self.assertFalse(self.r.aborted)
        self.assertEqual(self.r.errors, [])

    def test_not_suspect(self):
        self.assertEqual(self.p.suspect_why, [])
        s = self.p.summary()
        self.assertFalse(s["suspect"])
        self.assertEqual(s["suspect_why"], "")
        self.assertEqual(s["tools"], 1)
        self.assertEqual(s["tokens"]["turns"], 2)
        self.assertEqual(self.r.session_id, "sess-1")
        self.assertEqual(self.r.events, 7)
        self.assertEqual(self.r.last_event_type, "agent_settled")
        self.assertEqual(self.r.bad_lines, 0)


class TestMessageUpdateUsageIgnored(unittest.TestCase):
    def test_update_usage_not_counted(self):
        update = {"type": "message_update",
                  "usage": {"input": 999999, "output": 888888, "cacheRead": 777777, "cacheWrite": 0},
                  "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "你好"}}
        p = _parse(_line(update) + "\n" + GOOD_STREAM)
        self.assertEqual(p.run.usage.input, 2700)
        self.assertEqual(p.run.usage.turns, 2)

    def test_update_does_not_become_final_text(self):
        update = {"type": "message_update", "usage": {"input": 5, "output": 5},
                  "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "半句"}}
        p = _parse(_line(update) + "\n")
        self.assertEqual(p.run.final_text, "")
        self.assertIsNone(p.summary()["tokens"])


class TestChunking(unittest.TestCase):
    def _run_chunked(self, stream: str, n: int) -> PiEventParser:
        p = PiEventParser()
        for i in range(0, len(stream), n):
            p.feed(stream[i:i + n])
        p.close()
        return p

    def test_seven_char_chunks_match_whole_feed(self):
        chunked = self._run_chunked(GOOD_STREAM, 7)
        whole = _parse(GOOD_STREAM)
        self.assertEqual(chunked.summary(), whole.summary())
        self.assertEqual(chunked.run, whole.run)

    def test_one_char_chunks_and_trailing_halfline(self):
        p = PiEventParser()
        for ch in GOOD_STREAM:
            p.feed(ch)
        # 最后再喂一个不带换行的半行，close() 要试着解析
        p.feed(_line({"type": "agent_end", "messages": [], "willRetry": True}))
        p.close()
        self.assertEqual(p.run.bad_lines, 0)
        self.assertEqual(p.run.usage.turns, 2)
        self.assertEqual(p.run.tool_calls, 1)

    def test_piggyback_two_lines_in_one_chunk(self):
        p = PiEventParser()
        out = p.feed(_line(SESSION) + "\n" + _line(ASSISTANT_TOOL) + "\n")
        self.assertEqual([o["type"] for o in out], ["session", "message_end"])
        self.assertEqual(p.run.usage.turns, 1)


class TestNoise(unittest.TestCase):
    def test_cr_blank_and_garbage_lines(self):
        stream = ("\r\n" + _line(SESSION) + "\r\n"
                  + "\n" + "[pi] diagnostics: retrying\n" + "   \n"
                  + _line(ASSISTANT_TOOL) + "\n" + _line(ASSISTANT_FINAL) + "\n")
        p = _parse(stream)
        self.assertEqual(p.run.bad_lines, 1)
        self.assertEqual(p.run.usage.turns, 2)
        self.assertEqual(p.run.tool_calls, 1)
        self.assertEqual(p.run.final_text, "解析器已写好，单测全过。")
        self.assertEqual(p.run.session_id, "sess-1")
        self.assertEqual(p.run.events, 3)

    def test_garbage_never_raises(self):
        p = PiEventParser()
        p.feed("{not json\n[[[\n{\"a\":\n")
        p.feed(None)
        p.feed(b"\xff\xfe not utf8\n")
        p.close()
        self.assertGreaterEqual(p.run.bad_lines, 3)

    def test_missing_fields_are_ignored(self):
        stream = "\n".join(_line(e) for e in [
            {"type": "message_end"},
            {"type": "message_end", "message": "not a dict"},
            {"type": "message_end", "message": {"role": "assistant"}},
            {"type": "message_end", "message": {"role": "assistant", "content": "纯字符串", "usage": {"input": "7"}}},
            {"type": "assistant_message", "message": {}},
        ]) + "\n"
        p = _parse(stream)
        self.assertEqual(p.run.bad_lines, 0)
        self.assertEqual(p.run.usage.input, 7)  # 数字字符串也收
        self.assertEqual(p.run.final_text, "纯字符串")
        self.assertEqual(p.run.tool_calls, 0)


class TestSuspect(unittest.TestCase):
    def test_no_tool_calls(self):
        only_text = dict(ASSISTANT_FINAL)
        only_text = json.loads(json.dumps(ASSISTANT_FINAL))
        only_text["message"]["content"] = [{"type": "text", "text": "已经完成。"}]
        p = _parse(_line(SESSION) + "\n" + _line(only_text) + "\n")
        self.assertIn("没有任何工具调用", p.suspect_why)
        self.assertTrue(p.summary()["suspect"])

    def test_task_missing_reply(self):
        m = json.loads(json.dumps(ASSISTANT_FINAL))
        m["message"]["content"] = [{"type": "text", "text": "我这边任务单缺失，请把任务重发。"}]
        p = _parse(_line(SESSION) + "\n" + _line(m) + "\n")
        self.assertIn("回复说任务没到/被截断", p.suspect_why)

    def test_home_runner_in_tool_result(self):
        tr = json.loads(json.dumps(TOOL_RESULT))
        tr["message"]["content"] = [{"type": "text", "text": "cat: /home/runner/work/repo/x: No such file"}]
        p = _parse(_line(SESSION) + "\n" + _line(ASSISTANT_TOOL) + "\n" + _line(tr) + "\n" + _line(ASSISTANT_FINAL) + "\n")
        self.assertEqual(p.run.stale_hit, "/home/runner")
        self.assertIn("碰到 WSL/旧快照路径（/home/runner）", p.suspect_why)
        self.assertEqual(p.summary()["suspect_why"], "碰到 WSL/旧快照路径（/home/runner）")

    def test_wsl_unc_linux_fs_in_tool_args(self):
        a = json.loads(json.dumps(ASSISTANT_TOOL))
        a["message"]["content"][2]["arguments"] = {"command": r"ls \\wsl$\Ubuntu\home\runner\work"}
        p = _parse(_line(SESSION) + "\n" + _line(a) + "\n" + _line(ASSISTANT_FINAL) + "\n")
        self.assertTrue(p.run.stale_hit.startswith("\\\\wsl$\\Ubuntu"), p.run.stale_hit)
        self.assertIn("WSL/旧快照路径", p.summary()["suspect_why"])

    def test_mnt_c_and_bare_fatal_git_are_clean(self):
        tr = json.loads(json.dumps(TOOL_RESULT))
        tr["message"]["content"] = [{"type": "text",
                                     "text": "fatal: not a git repository (or any parent up to mount point)\n/mnt/c/work/proj\n"}]
        p = _parse(_line(SESSION) + "\n" + _line(ASSISTANT_TOOL) + "\n" + _line(tr) + "\n" + _line(ASSISTANT_FINAL) + "\n")
        self.assertEqual(p.run.stale_hit, "")
        self.assertEqual(p.suspect_why, [])

    def test_wsl_localhost_mnt_is_clean(self):
        tr = json.loads(json.dumps(TOOL_RESULT))
        tr["message"]["content"] = [{"type": "text", "text": r"read \\wsl.localhost\Ubuntu-24.04\mnt\c\work\a.txt"}]
        p = _parse(_line(ASSISTANT_TOOL) + "\n" + _line(tr) + "\n")
        self.assertEqual(p.run.stale_hit, "")


    def test_path_hit_suppressed_when_delivered(self):
        # Five toolCalls + a /home/runner mention in a late toolResult → path why suppressed.
        chunks = [_line(SESSION)]
        for i in range(5):
            a = json.loads(json.dumps(ASSISTANT_TOOL))
            a["message"]["content"][2]["arguments"] = {"command": f"echo step-{i}"}
            chunks.append(_line(a))
        tr = json.loads(json.dumps(TOOL_RESULT))
        tr["message"]["content"] = [{"type": "text", "text": "note: docs mention /home/runner as forbidden"}]
        chunks.append(_line(tr))
        chunks.append(_line(ASSISTANT_FINAL))
        p = _parse("\n".join(chunks) + "\n")
        self.assertEqual(p.run.stale_hit, "/home/runner")
        self.assertGreaterEqual(p.run.tool_calls, 5)
        self.assertNotIn("WSL", p.summary()["suspect_why"])
        self.assertFalse(p.summary()["suspect"])

    def test_stale_hit_in_text_helper(self):
        self.assertEqual(stale_hit_in_text("/home/runner/x"), "/home/runner")
        self.assertEqual(stale_hit_in_text(""), "")
        self.assertEqual(stale_hit_in_text("nothing here"), "")
        self.assertEqual(stale_hit_in_text("/mnt/c/Users/me"), "")
        self.assertEqual(stale_hit_in_text("fatal: not a git repository"), "")


class TestErrorsAndAbort(unittest.TestCase):
    def test_stop_reason_error_recorded(self):
        m = json.loads(json.dumps(ASSISTANT_TOOL))
        m["message"]["stopReason"] = "error"
        m["message"]["errorMessage"] = "529 overloaded"
        m["message"]["content"] = [{"type": "text", "text": "抱歉"}]
        p = _parse(_line(SESSION) + "\n" + _line(m) + "\n")
        self.assertEqual(p.run.errors, ["529 overloaded"])
        self.assertEqual(p.run.stop_reason, "error")
        self.assertEqual(p.summary()["errors"], ["529 overloaded"])

    def test_error_then_retry_success_is_not_error(self):
        """#98：Kimi 偶发 Request timed out，Pi 自动重试后把活干完了，不能还记成错（之前整张卡被判失败）。"""
        bad = json.loads(json.dumps(ASSISTANT_TOOL))
        bad["message"]["stopReason"] = "error"
        bad["message"]["errorMessage"] = "Request timed out."
        bad["message"]["content"] = []
        good = json.loads(json.dumps(ASSISTANT_TOOL))
        good["message"]["stopReason"] = "stop"
        p = _parse(_line(SESSION) + "\n" + _line(bad) + "\n" + _line({"type": "auto_retry_start", "attempt": 1}) + "\n"
                   + _line(good) + "\n" + _line({"type": "agent_settled", "aborted": False}) + "\n")
        self.assertEqual(p.run.errors, [])
        self.assertEqual(p.run.retried_errors, ["Request timed out."])
        self.assertEqual(p.summary()["errors"], [])

    def test_error_after_success_still_error(self):
        good = json.loads(json.dumps(ASSISTANT_TOOL))
        bad = json.loads(json.dumps(ASSISTANT_TOOL))
        bad["message"]["stopReason"] = "error"
        bad["message"]["errorMessage"] = "529 overloaded"
        p = _parse(_line(good) + "\n" + _line(bad) + "\n")
        self.assertEqual(p.run.errors, ["529 overloaded"])

    def test_stop_reason_error_without_message(self):
        m = json.loads(json.dumps(ASSISTANT_TOOL))
        m["message"]["stopReason"] = "error"
        m["message"]["content"] = []
        p = _parse(_line(m) + "\n")
        self.assertEqual(p.run.errors, ["assistant stopReason=error"])

    def test_aborted_settled(self):
        p = _parse(GOOD_STREAM + _line({"type": "agent_settled", "aborted": True}) + "\n")
        self.assertTrue(p.run.settled)
        self.assertTrue(p.run.aborted)
        self.assertTrue(p.summary()["aborted"])

    def test_not_settled_without_agent_settled(self):
        p = _parse(GOOD_STREAM.replace(_line(AGENT_SETTLED) + "\n", ""))
        self.assertFalse(p.run.settled)
        self.assertFalse(p.summary()["settled"])


class TestSummaryTokensNone(unittest.TestCase):
    def test_no_assistant_message_means_no_tokens(self):
        p = _parse(_line(SESSION) + "\n" + _line({"type": "turn_start"}) + "\n")
        self.assertIsNone(p.summary()["tokens"])
        self.assertEqual(p.run.usage.turns, 0)
        self.assertEqual(p.run.usage.as_dict()["turns"], 0)

    def test_summary_truncates_final_text(self):
        m = json.loads(json.dumps(ASSISTANT_FINAL))
        m["message"]["content"] = [{"type": "text", "text": "长" * 5000}]
        p = _parse(_line(m) + "\n")
        self.assertEqual(len(p.summary()["final_text"]), 4000)
        self.assertEqual(len(p.run.final_text), 5000)

    def test_last_tool_truncated_to_120(self):
        a = json.loads(json.dumps(ASSISTANT_TOOL))
        a["message"]["content"] = [{"type": "toolCall", "id": "x", "name": "bash", "arguments": {"command": "echo " + "y" * 500}}]
        p = _parse(_line(a) + "\n")
        self.assertEqual(len(p.run.last_tool), 120)
        self.assertTrue(p.run.last_tool.startswith("bash: echo yyy"))


if __name__ == "__main__":
    unittest.main()
