# -*- coding: utf-8 -*-
"""浏览器禁用端口（Chromium 的 kRestrictedPorts）。

这些端口浏览器不让访问（ERR_UNSAFE_PORT）。让系统随便挑端口（port=0）时可能挑中 1719、6665 这种——
Playwright 一打开就报错，测试会偶发挂。核心起服务器和拍图 / 冒烟脚本挑端口时都躲开这张表。

单独一个模块：tools/ 下的脚本要 import 它，但不能为了一个常量把整个盒子核心拉起来。
"""
from __future__ import annotations

BROWSER_RESTRICTED_PORTS = frozenset({
    1, 7, 9, 11, 13, 15, 17, 19, 20, 21, 22, 23, 25, 37, 42, 43, 53, 69, 77, 79, 87, 95, 101, 102,
    103, 104, 109, 110, 111, 113, 115, 117, 119, 123, 135, 137, 139, 143, 161, 179, 389, 427, 465,
    512, 513, 514, 515, 526, 530, 531, 532, 540, 548, 554, 556, 563, 587, 601, 636, 989, 990,
    993, 995, 1719, 1720, 1723, 2049, 3659, 4045, 4190, 5060, 5061, 6000, 6566, 6665, 6666, 6667,
    6668, 6669, 6679, 6697, 10080,
})


def is_restricted(port: int) -> bool:
    """这个端口浏览器不让访问吗？"""
    try:
        return int(port) in BROWSER_RESTRICTED_PORTS
    except (TypeError, ValueError):
        return False
