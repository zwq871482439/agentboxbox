# -*- coding: utf-8 -*-
import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from boxbox import classify  # noqa: E402


class Classify(unittest.TestCase):
    def test_auth(self):
        self.assertEqual(classify.classify("401 Unauthorized"), "auth")
        self.assertEqual(classify.classify("invalid api key provided"), "auth")
        self.assertEqual(classify.classify("authentication failed"), "auth")

    def test_busy(self):
        self.assertEqual(classify.classify("429 Too Many Requests"), "busy")
        self.assertEqual(classify.classify("server is busy, try again later"), "busy")
        self.assertEqual(classify.classify("model overloaded"), "busy")

    def test_quota(self):
        self.assertEqual(classify.classify("insufficient balance"), "quota")
        self.assertEqual(classify.classify("usage limit reached"), "quota")
        self.assertEqual(classify.classify("账户余额不足"), "quota")

    def test_429_that_says_quota_is_quota(self):
        """Kimi 周额度用完回 429 rate_limit_error；按「忙」说用户会一直等。普通 429 还是「忙」。"""
        kimi = ('429 {"error":{"type":"rate_limit_error","message":"You\'ve reached your weekly (7-day) usage limit. '
                'Your quota will reset when the current 7-day window ends."},"type":"error"}')
        self.assertEqual(classify.classify(kimi), "quota")
        self.assertEqual(classify.classify("429 rate limit: too many requests, please slow down"), "busy")

    def test_unreachable(self):
        self.assertEqual(classify.classify("ECONNRESET"), "unreachable")
        self.assertEqual(classify.classify("fetch failed"), "unreachable")
        self.assertEqual(classify.classify("getaddrinfo ENOTFOUND api.x.com"), "unreachable")

    def test_unknown(self):
        self.assertEqual(classify.classify("hello"), "unknown")
        self.assertEqual(classify.classify(""), "unknown")

    def test_exit_codes(self):
        self.assertEqual(classify.EXIT_CODES["ok"], 0)
        self.assertEqual(classify.EXIT_CODES["busy"], 10)
        self.assertEqual(classify.EXIT_CODES["quota"], 11)
        self.assertEqual(classify.EXIT_CODES["unreachable"], 12)
        self.assertEqual(classify.EXIT_CODES["auth"], 13)
        self.assertEqual(classify.EXIT_CODES["route"], 14)
        self.assertEqual(classify.EXIT_CODES["unknown"], 1)


class ResetTime(unittest.TestCase):
    def test_iso(self):
        r = classify.reset_time("quota exceeded, resets at 2026-10-22T00:00:00Z")
        self.assertIsNotNone(r)
        # 比时刻，不比字符串：打包机可能不在东八区，写死本地钟点会在别的时区挂掉
        expected = datetime(2026, 10, 22, 0, 0, tzinfo=timezone.utc).astimezone()
        self.assertEqual(datetime.fromisoformat(r), expected)

    def test_retry_after(self):
        now = datetime.now().astimezone()
        r = classify.reset_time("429 retry after 30 s", now)
        self.assertIsNotNone(r)
        got = datetime.fromisoformat(r)
        self.assertAlmostEqual((got - now).total_seconds(), 30, delta=2)
        r2 = classify.reset_time("reset in 2 hours", now)
        got2 = datetime.fromisoformat(r2)
        self.assertAlmostEqual((got2 - now).total_seconds(), 7200, delta=2)

    def test_none(self):
        self.assertIsNone(classify.reset_time("quota exceeded, good luck"))
        self.assertIsNone(classify.reset_time(""))


class Mask(unittest.TestCase):
    def test_kv(self):
        self.assertEqual(classify.mask("api_key=placeholder"), "api_key=***")
        self.assertIn("***", classify.mask('Authorization: Bearer abc.def.ghi'))

    def test_tokens(self):
        self.assertNotIn("abcdefgh", classify.mask("key is sk-abcdefgh123456"))
        self.assertNotIn("payload", classify.mask("jwt eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"))
        self.assertNotIn("0123456789abcdef0123456789abcdef", classify.mask("hash 0123456789abcdef0123456789abcdef.ABCDEFGHIJ"))

    def test_empty(self):
        self.assertEqual(classify.mask(""), "")


class Tcp(unittest.TestCase):
    def test_empty_host_skips(self):
        self.assertTrue(classify.tcp_reachable("", 443, tries=1, timeout_s=0.1))

    def test_closed_port(self):
        self.assertFalse(classify.tcp_reachable("127.0.0.1", 9, tries=1, timeout_s=0.5))

    def test_bad_dns(self):
        import socket
        try:                                                   # 有的网络 / 沙箱把不存在的域名也解析到一个地址（#92 假阳性）
            socket.getaddrinfo("no-such-host.invalid", 443)
            self.skipTest("这台机器的 DNS 会把 .invalid 也解析出地址，测不了")
        except OSError:
            pass
        self.assertFalse(classify.tcp_reachable("no-such-host.invalid", 443, tries=1, timeout_s=0.5))


if __name__ == "__main__":
    unittest.main()
