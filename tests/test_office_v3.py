# -*- coding: utf-8 -*-
"""v3：区域不标字；工位状态词不带中点；像素气泡图标齐全；血条按「剩余」。"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    o = open(os.path.join(ROOT, "office", "office.html"), encoding="utf-8").read()
    assert "txt(z.name" not in o and '"开会中 · "' not in o  # 会议室只写「派活中」/「验收中」
    assert 'sw+=" · "' not in o and "txt(`${d.label} · ${d.name}`" not in o
    for k in ("fridge", "coffee", "zzz", "key", "file", "meet", "ask", "fail"):
        m = re.search(r"\n %s:\[(.*?)\]" % k, o)
        assert m, k
    for w in ("工作中", "空闲", "倒咖啡中", "开会中", "等待中", "已下线"):
        assert '"%s"' % w in o, w
    assert 'BUB_EVERY' not in o and '"剩余"+left+"%"' in o
    print("OK test_office_v3")


if __name__ == "__main__":
    main()
