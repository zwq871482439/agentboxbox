# -*- coding: utf-8 -*-
"""office/office.html 是 office/build/build.py 从骨架 office.src.html + src/ 模块 + art/ 像素数据
+ cats.js + sample.json 拼出来的。直接改 office.html 的改动下次 build 就丢了，
这条测试保证提交的 office.html 和现在 build 出来的一模一样。"""
import importlib
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
B = ROOT / "office" / "build"
sys.path.insert(0, str(B))

build = importlib.import_module("build")     # office/build/build.py


def built() -> str:
    """跟 build.py 一样的拼法（别的测试也 import 这个函数）。"""
    src = (B / "office.src.html").read_text(encoding="utf-8")
    sample = json.dumps(json.loads((ROOT / "office" / "sample.json").read_text(encoding="utf-8")), ensure_ascii=False)
    cats = (B / "cats.js").read_text(encoding="utf-8")
    css = (B / "src" / "style.css").read_text(encoding="utf-8")
    body = (B / "src" / "body.html").read_text(encoding="utf-8")
    parts = [build.art_js()]
    for name in build.SRC_ORDER:
        text = (B / "src" / name).read_text(encoding="utf-8")
        parts.append(text.replace("__CATS_JS__", cats))
    return (src.replace("__CSS__", css)
               .replace("__BODY__", body)
               .replace("__SAMPLE__", sample.replace("</", "<\\/"))
               .replace("__SCRIPTS__", "\n".join(parts)))


class TestOfficeBuilt(unittest.TestCase):
    def test_office_html_is_build_output(self):
        have = (ROOT / "office" / "office.html").read_text(encoding="utf-8")
        self.assertTrue(have == built(), "office/office.html 和 build 出来的不一样："
                        "只改 office/build/src/ 下的源文件，然后跑 python office/build/build.py")


if __name__ == "__main__":
    unittest.main()
