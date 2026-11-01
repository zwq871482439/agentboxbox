# -*- coding: utf-8 -*-
"""#86：页面里的 div / dialog / section 等要成对闭合，不能把后面的区块吞进一个 hidden 弹层里。
设置页曾经因为 #fixDlg 少了两个 </div>，「重置所有」整块被包进隐藏的弹层，页面上看不到。

    python -m unittest tests.test_static_html_balance -v
"""
import pathlib
import unittest
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGES = sorted((ROOT / "boxbox" / "static").glob("*.html"))
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
CHECK = {"div", "section", "dialog", "form", "main", "aside", "header", "footer", "nav", "ul", "ol", "table", "details"}


class _Balance(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack: list[tuple[str, int, str]] = []
        self.errors: list[str] = []
        self.parents: dict[str, list[str]] = {}     # id -> 祖先的 id 列表

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        a = dict(attrs)
        if a.get("id"):
            self.parents[a["id"]] = [i for _, _, i in self.stack if i]
        if tag in CHECK:
            self.stack.append((tag, self.getpos()[0], a.get("id") or ""))

    def handle_endtag(self, tag):
        if tag not in CHECK:
            return
        if not self.stack or self.stack[-1][0] != tag:
            self.errors.append("第 %d 行多了 </%s>（当时开着的是 %s）" % (self.getpos()[0], tag, self.stack[-1:] or "无"))
            return
        self.stack.pop()


class TestStaticHtmlBalance(unittest.TestCase):
    def test_pages_balanced(self):
        self.assertTrue(PAGES)
        for p in PAGES:
            with self.subTest(page=p.name):
                b = _Balance()
                b.feed(p.read_text(encoding="utf-8"))
                b.close()
                self.assertEqual(b.errors, [], p.name)
                self.assertEqual(b.stack, [], "%s 有没闭合的标签：%s" % (p.name, b.stack))

    def test_settings_reset_not_inside_dialog(self):
        b = _Balance()
        b.feed((ROOT / "boxbox" / "static" / "settings.html").read_text(encoding="utf-8"))
        for dlg in ("fixDlg", "provDlg"):
            self.assertNotIn(dlg, b.parents.get("resetBox", []), "「重置所有」被包进了 #%s" % dlg)


if __name__ == "__main__":
    unittest.main()
