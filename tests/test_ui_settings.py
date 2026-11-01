# -*- coding: utf-8 -*-
"""设置页 /settings（工作计划 3.8 的 v0.1 子集）：页面静态检查 + 起真核心打 HTTP 的接口级测试。

静态部分守住：页面认得四个接口、参数名、在跑禁删、无外链；PAGES 里有 /settings。
接口部分：GET /settings 出页面、POST /api/settings 改 wake_min 并能读回、scheduled 工位 K 增删。
    python -m unittest tests.test_ui_settings -v
"""
import json
import pathlib
import re
import sys
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from boxbox import config  # noqa: E402

PAGE = ROOT / "boxbox" / "static" / "settings.html"
# 工位增删改从设置页搬到「工位」页；页面样式/脚本拆到了 stations.css / stations.js / stations-drawer.js
STATIONS_FILES = ["stations.html", "stations.js", "stations-drawer.js", "i18n-stations.js"]
HTTP_PY = ROOT / "boxbox" / "facades" / "http.py"


class TestSettingsPageStatic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = PAGE.read_text(encoding="utf-8")
        cls.st = "".join(
            (ROOT / "boxbox" / "static" / n).read_text(encoding="utf-8") for n in STATIONS_FILES
        )

    def test_endpoints(self):
        for needle in ("/api/settings", "/api/doctor"):
            self.assertIn(needle, self.src, needle)
        for needle in ("/api/stations_def", "/api/stations/delete", "/api/pi/check"):
            self.assertIn(needle, self.st, needle)

    def test_field_names(self):
        for needle in ("wake_min", "ack_timeout_s", "heartbeat_s"):
            self.assertIn(needle, self.src, needle)
        self.assertNotIn("pin_min", self.src)   # #82：pin_min（提醒升级）已删，阈值只剩 wake_min
        self.assertNotIn("not_started_min", self.src)   # 这一项没人用，删了
        for needle in ("every_min", "context_window", "max_tokens", "reasoning"):
            self.assertIn(needle, self.st, needle)
        self.assertNotIn("api_key_env", self.st)   # 密钥变量名不再让用户填：密钥只存 data/secrets.json

    def test_busy_station_cannot_be_deleted(self):
        self.assertIn("在跑", self.st)
        self.assertIn("在跑中，先等它做完", self.st)

    def test_no_third_party(self):
        # 只许本机的 /static/*.js（共用顶栏 topbar.js）；外链脚本一律不行
        self.assertEqual(re.findall(r'<script src="(?!/static/)[^"]*"', self.src), [])
        self.assertNotIn("cdn.", self.src)
        body = self.src.replace("http://127.0.0.1", "")      # 本机回环不算外链
        self.assertNotIn("http://", body)
        self.assertNotIn("https://", body)

    def test_page_registered(self):
        src = HTTP_PY.read_text(encoding="utf-8")
        self.assertIn('"/settings": "settings.html"', src)
        self.assertIn('"/stations": "stations.html"', src)


class TestSettingsOverHttp(unittest.TestCase):
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

    def post(self, path, obj):
        req = urllib.request.Request(self.url + path, data=json.dumps(obj).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            e.close()
            return e.code, body

    def test_settings_page_is_served(self):
        code, body = self.get("/settings")
        self.assertEqual(code, 200)
        self.assertIn("设置", body)
        self.assertIn("工位", body)

    def test_wake_min_round_trip(self):
        code, out = self.post("/api/settings", {"wake_min": 45})
        self.assertEqual(code, 200)
        self.assertEqual(out["wake_min"], 45)
        _, body = self.get("/api/settings")
        self.assertEqual(json.loads(body)["wake_min"], 45)

    def test_station_lifecycle_over_http(self):
        code, out = self.post("/api/stations", {"id": "K", "role": "member", "client": "grok-bot",
                                                "runner": "scheduled", "enabled": True,
                                                "runner_args": {"every_min": 10}})
        self.assertEqual(code, 200, out)
        self.assertTrue(out["ok"], out)
        _, body = self.get("/api/stations_def")
        ids = [s["id"] for s in json.loads(body)["stations"]]
        self.assertIn("K", ids)
        st = [s for s in json.loads(body)["stations"] if s["id"] == "K"][0]
        self.assertEqual(st["runner_args"]["every_min"], 10)
        code, out = self.post("/api/stations/delete", {"id": "K"})
        self.assertEqual(code, 200)
        self.assertTrue(out["ok"])
        _, body = self.get("/api/stations_def")
        self.assertNotIn("K", [s["id"] for s in json.loads(body)["stations"]])

    def test_incomplete_pi_block_is_rejected_with_errors(self):
        code, out = self.post("/api/stations", {"id": "P", "role": "member", "client": "pi",
                                                "runner": "once", "enabled": True, "pi": {}})
        self.assertEqual(code, 400)
        self.assertEqual(out["code"], "station_invalid")
        self.assertTrue(out["errors"], out)


if __name__ == "__main__":
    unittest.main()
