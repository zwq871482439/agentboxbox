# -*- coding: utf-8 -*-
"""intranet_reachable 多试几次别误判：同一地址偶发一次连不上就判失败，实测会误伤。

用 mock 打桩 socket.getaddrinfo / socket.create_connection 和 time.sleep（不真等、不真连、不真解析）：
前两次 OSError 第三次成功 -> True；三次都 OSError -> False；第一次解析失败第二次成功 -> True。
"""
import os
import socket
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from boxbox import pi_config  # noqa: E402

PI = {"base_url": "https://llm-api.incact.cn:443/coding", "api": "anthropic-messages", "model": "M1"}
IP = "203.0.113.9"       # 文档保留的测试网段地址：解析结果只写进日志，不真连


def dns_info():
    """假 DNS 解析：返回一个解析函数（给 getaddrinfo 打桩用）。"""

    def resolve(*_a, **_kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (IP, 443))]

    return resolve


class IntranetReachable(unittest.TestCase):
    def _run(self, side_effects, expect_calls=3, expect_sleeps=None, dns=None):
        """打桩解析 / 连接 / sleep 跑一次 intranet_reachable，返回 (结果, 连接 mock)。"""
        with mock.patch.object(pi_config.socket, "getaddrinfo", side_effect=dns or dns_info()), \
                mock.patch.object(pi_config.socket, "create_connection", side_effect=side_effects) as conn, \
                mock.patch.object(pi_config.time, "sleep") as sleep:
            ok = pi_config.intranet_reachable(dict(PI))
        self.assertEqual(conn.call_count, expect_calls)
        if expect_sleeps is not None:
            self.assertEqual(sleep.call_count, expect_sleeps)
        return ok, conn

    def test_fail_twice_then_ok(self):
        """前两次 OSError、第三次连上 -> True，试满 3 次，中间歇了 2 次 0.5 秒"""
        ok, conn = self._run([OSError("timed out"), OSError("timed out"), mock.DEFAULT], expect_sleeps=2)
        self.assertIs(ok, True)
        self.assertEqual([c.args[0] for c in conn.call_args_list], [(IP, 443)] * 3)

    def test_all_fail(self):
        """三次都 OSError -> False"""
        ok, conn = self._run(OSError("refused"), expect_sleeps=2)
        self.assertIs(ok, False)
        self.assertEqual(conn.call_count, 3)

    def test_dns_fail_then_ok(self):
        """第一次解析失败（压根没去连）、第二次连上 -> True"""
        calls = []

        def resolve(*_a, **_kw):
            calls.append(1)
            if len(calls) == 1:
                raise socket.gaierror(-2, "Name or service not known")
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (IP, 443))]

        ok, conn = self._run([mock.DEFAULT], expect_calls=1, expect_sleeps=1, dns=resolve)
        self.assertIs(ok, True)

    def test_first_try_ok(self):
        """一次就连上 -> True，只试 1 次，不歇"""
        ok, conn = self._run([mock.DEFAULT], expect_calls=1, expect_sleeps=0)
        self.assertIs(ok, True)

    def test_timeout_per_try(self):
        """timeout_s 传成每次的超时"""
        with mock.patch.object(pi_config.socket, "getaddrinfo", dns_info()), \
                mock.patch.object(pi_config.socket, "create_connection", side_effect=OSError) as conn, \
                mock.patch.object(pi_config.time, "sleep"):
            pi_config.intranet_reachable(dict(PI), timeout_s=5)
        self.assertEqual([c.kwargs.get("timeout") for c in conn.call_args_list], [5, 5, 5])

    def test_no_host(self):
        """写不出主机 -> True，不碰网络"""
        with mock.patch.object(pi_config.socket, "getaddrinfo") as dns, \
                mock.patch.object(pi_config.socket, "create_connection") as conn:
            self.assertIs(pi_config.intranet_reachable({"base_url": ""}), True)
        dns.assert_not_called()
        conn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
