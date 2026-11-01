# -*- coding: utf-8 -*-
"""许可和隐私（开源前补齐）：仓库根目录的四份文件在、设置页能看、exe 里带着、隐私声明和代码说的一致。"""
import json
import os
import pathlib
import tempfile
import unittest
import urllib.request

from boxbox import app, config, pi_config

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEGAL_FILES = ("LICENSE", "PRIVACY.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_LICENSES.txt")


class TestLegalFiles(unittest.TestCase):
    def test_files_exist(self):
        for f in LEGAL_FILES:
            self.assertTrue((ROOT / f).is_file(), f)
        self.assertTrue((ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License"))

    def test_exe_bundles_legal_files(self):
        ps = (ROOT / "packaging" / "build_exe.ps1").read_text(encoding="utf-8")
        for f in ("LICENSE", "PRIVACY.md", "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_LICENSES.txt"):
            self.assertIn("\\%s;." % f, ps, f)
        self.assertIn("licenses.py --check", ps)
        self.assertIn("licenses.py --verify-toc", ps)

    def test_lgpl_component_has_full_texts(self):
        t = (ROOT / "THIRD_PARTY_LICENSES.txt").read_text(encoding="utf-8")
        i = t.index("\npystray ")
        part = t[i:i + 60000]
        self.assertIn("GNU LESSER GENERAL PUBLIC LICENSE", part)
        self.assertIn("GNU GENERAL PUBLIC LICENSE", part)
        self.assertIn("pystray 和 LGPL-3.0", (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8"))

    def test_privacy_matches_pi_env(self):
        """隐私声明里说关掉了 Pi 的统计和联网，代码里真的这么设"""
        text = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
        env = pi_config.pi_env({"id": "x", "pi": {}}, base_env={})
        for k in ("PI_TELEMETRY=0", "PI_SKIP_VERSION_CHECK=1", "PI_OFFLINE=1"):
            name, val = k.split("=")
            self.assertIn(k, text)
            self.assertEqual(env.get(name), val, k)

    def test_settings_page_shows_privacy(self):
        s = (ROOT / "boxbox" / "static" / "settings.html").read_text(encoding="utf-8")
        self.assertIn("数据和隐私", s)
        self.assertIn('fetch("/legal/privacy?lang="', s)
        self.assertNotIn("_blank", s)             # 这三份在窗口里开，不跳系统浏览器
        for path in ("/legal/license", "/legal/notices", "/legal/third-party"):
            self.assertIn('"%s"' % path, s, path)   # 按钮点开时 fetch 的地址还在页面里


class TestLegalRoutes(unittest.TestCase):
    def test_routes_serve_plain_text(self):
        old_data, old_proj = config.DATA, os.environ.get("BOXBOX_PROJECT")
        with tempfile.TemporaryDirectory() as tmp:
            config.DATA = pathlib.Path(tmp) / "data"
            try:
                store, d, httpd, wd, port = app.start(0)
                try:
                    for path, needle in (("/legal/privacy", "数据使用与隐私声明"), ("/legal/license", "MIT License"),
                                         ("/legal/notices", "第三方声明"), ("/legal/third-party", "pystray")):
                        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=10) as r:
                            self.assertTrue(r.headers["Content-Type"].startswith("text/plain"), path)
                            self.assertIn(needle, r.read().decode("utf-8"), path)
                finally:
                    app.stop(store, httpd, wd, d)
            finally:
                config.DATA = old_data
                if old_proj is not None:
                    os.environ["BOXBOX_PROJECT"] = old_proj


if __name__ == "__main__":
    unittest.main()
    json.dumps({})
