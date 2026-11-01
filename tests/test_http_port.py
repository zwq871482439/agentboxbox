# -*- coding: utf-8 -*-
"""serve(port=0) 挑端口时要躲开浏览器禁用端口（Chromium kRestrictedPorts）。

端口 0 让系统随便挑一个，可能挑中 1719、6665 这种——浏览器不让访问（ERR_UNSAFE_PORT），
Playwright 一打开就报错，测试偶发挂。这里让第一次绑到 6665，看 serve() 会不会自己躲开。

    python -m pytest -q -p no:cacheprovider tests/test_http_port.py
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from boxbox import config  # noqa: E402
from boxbox.dispatcher import Dispatcher  # noqa: E402
from boxbox.facades import http as http_facade  # noqa: E402
from boxbox.facades.http import Core, serve  # noqa: E402
from boxbox.ports import BROWSER_RESTRICTED_PORTS  # noqa: E402
from boxbox.store import Store  # noqa: E402


def test_restricted_ports_table_has_chromium_list():
    for p in (1, 7, 9, 11, 13, 15, 17, 19, 20, 21, 22, 23, 25, 37, 42, 43, 53, 69, 77, 79, 87, 95,
              101, 102, 103, 104, 109, 110, 111, 113, 115, 117, 119, 123, 135, 137, 139, 143, 161, 179,
              389, 427, 465, 512, 513, 514, 515, 526, 530, 531, 532, 540, 548, 554, 556, 563, 587,
              601, 636, 989, 990, 993, 995, 1719, 1720, 1723, 2049, 3659, 4045, 4190, 5060, 5061,
              6000, 6566, 6665, 6666, 6667, 6668, 6669, 6679, 6697, 10080):
        assert p in BROWSER_RESTRICTED_PORTS, "禁用端口表少了 %d" % p


def test_serve_skips_restricted_port(tmp_path, monkeypatch):
    """第一次绑到 6665（浏览器禁用）→ serve() 关掉重绑，返回的端口不在禁用表里。"""
    monkeypatch.setenv("BOXBOX_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(config, "DATA", tmp_path / "data")
    config.ensure_dirs()
    store = Store(config.DATA / "boxbox.db")
    d = Dispatcher(store)

    real_server = http_facade._Server
    calls = {"n": 0}

    class FakeServer(real_server):
        """第一次假报 6665（其余照常真绑）。"""

        def __init__(self, addr, handler):
            super().__init__(addr, handler)
            calls["n"] += 1
            if calls["n"] == 1:
                self.server_address = ("127.0.0.1", 6665)

    monkeypatch.setattr(http_facade, "_Server", FakeServer)
    httpd = serve(Core(d), 0, block=False)
    try:
        port = int(httpd.server_address[1])
        assert calls["n"] >= 2, "撞上禁用端口就该重绑"
        assert port != 6665, "serve() 把浏览器禁用端口交出来了"
        assert port not in BROWSER_RESTRICTED_PORTS, port
    finally:
        httpd.shutdown()
        httpd.server_close()
        store.close()
