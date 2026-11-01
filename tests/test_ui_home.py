# -*- coding: utf-8 -*-
"""首页 /（v1 猫猫办公室外壳接 v2 接口）：页面静态检查 + 起真核心打 HTTP 的接口级测试。

静态部分守住：页面认得 v2 的接口、办公室/列表切换记在浏览器里、用离线 tabler、
顶栏给原看板留了 /board 入口、三个页签是人话标题；不再引用 v1 的老接口、无外链；
PAGES 里 / 是 home.html、/board 是 index.html。
接口部分：GET / 出首页（含嵌入办公室），GET /board 还是原看板。
    python -m unittest tests.test_ui_home -v
"""
import pathlib
import re
import sys
import unittest
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from boxbox import config  # noqa: E402

PAGE = ROOT / "boxbox" / "static" / "home.html"
HTTP_PY = ROOT / "boxbox" / "facades" / "http.py"


class TestHomePageStatic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = PAGE.read_text(encoding="utf-8")

    def test_office_only_no_list_mode(self):
        """首页只有办公室，「列表」和看板重复，去掉了。"""
        self.assertIn("/office?embed=1", self.src)
        self.assertNotIn("bx-office-mode", self.src)
        self.assertNotIn('id="mode-seg"', self.src)

    def test_endpoints(self):
        for needle in ("/api/timeline", "/api/tokens", "/api/doctor", "/api/summon/",
                       "/api/stations", "/api/meta", "/api/todo", "/api/health"):
            self.assertIn(needle, self.src, needle)

    def test_offline_tabler(self):
        self.assertIn("/vendor/tabler/tabler.min.css", self.src)

    def test_top_nav_is_shared(self):
        """顶栏统一走 topbar.js：看板 / 工位 / 设置，自检收在设置里；连接状态 = 顶栏核心圆点。"""
        self.assertIn('<header id="bx-top"></header>', self.src)
        self.assertIn('src="/static/topbar.js"', self.src)
        self.assertIn('"bx-core-click"', self.src)
        top = (ROOT / "boxbox" / "static" / "topbar.js").read_text(encoding="utf-8")
        for needle in ('href="/board"', 'href="/stations"', 'href="/settings"', "工作中", "成功率"):
            self.assertIn(needle, top, needle)
        self.assertNotIn('href="/doctor"', top)
        # #82：顶栏不再数「待决策」，整条横幅删掉；提醒统一看办公室提示条（/api/meta 的 alerts）
        self.assertNotIn("待决策", top)
        self.assertNotIn("bx-banner", top)

    def test_tab_titles_are_human_words(self):
        for t in ("动态", "用量", "连接状态"):
            self.assertIn(t, self.src, t)

    def test_no_v1_endpoints(self):
        for needle in ("/api/jiaoliu", "/api/quota", "/api/boxcalls"):
            self.assertNotIn(needle, self.src, needle)

    def test_no_third_party(self):
        # 只许本机的 /static/*.js（共用顶栏 topbar.js）；外链脚本一律不行
        self.assertEqual(re.findall(r'<script src="(?!/static/)[^"]*"', self.src), [])
        self.assertNotIn("cdn.", self.src)


class TestHomeRouting(unittest.TestCase):
    def test_pages_dict(self):
        src = HTTP_PY.read_text(encoding="utf-8")
        self.assertIn('"/": "home.html"', src)
        self.assertIn('"/board": "index.html"', src)


class TestHomeOverHttp(unittest.TestCase):
    def setUp(self):
        import tempfile

        from boxbox.dispatcher import Dispatcher
        from boxbox.facades.http import Core, serve
        from boxbox.store import Store
        self.tmp = tempfile.TemporaryDirectory()
        self._old = config.DATA
        config.DATA = pathlib.Path(self.tmp.name)
        config.ensure_dirs()
        config.save_stations([{"id": "架构师", "role": "leader", "client": "cursor", "runner": "manual", "enabled": True}])
        self.d = Dispatcher(Store(config.DATA / "boxbox.db"))
        self.httpd = serve(Core(self.d), 0, block=False)
        self.url = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.d.store.db.close()
        config.DATA = self._old
        self.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.url + path, timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def test_home_is_the_office_shell(self):
        code, body = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("office?embed=1", body)
        self.assertIn("/static/topbar.js", body)

    def test_board_is_still_the_old_page(self):
        code, body = self.get("/board")
        self.assertEqual(code, 200)
        self.assertIn("任务卡", body)


if __name__ == "__main__":
    unittest.main()
