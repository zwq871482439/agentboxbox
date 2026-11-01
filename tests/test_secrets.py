# -*- coding: utf-8 -*-
"""API key 存 data/secrets.json（Onboard v0.2 §7）：

- 存取：set_secret / get_secret / 清除；文件旁边有一句 README；
- Pi 子进程：models.json 里只有 $BOXBOX_KEY_<slug> 引用，值由 pi_env() 从 secrets 注入；
  用户填了变量名就用变量名；secrets 优先于环境变量；
- 对外：/api/stations 只回 has_key，/api/secrets 只写不读，GET 任何接口都不回密钥；
- 日志：classify.mask() 把 secrets 里的值打成 ***；
- doctor：Pi 工位多一项 key:<id>。
    python -m unittest tests.test_secrets -v
"""
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from boxbox import classify, config, doctor, pi_config  # noqa: E402

PI = {"base_url": "https://api.example.com/v1", "api": "anthropic-messages", "model": "m1"}
KEY = "sk-test-not-a-real-key"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = config.DATA
        config.DATA = pathlib.Path(self.tmp.name)
        config.ensure_dirs()
        config.save_stations([{"id": "A", "role": "member", "client": "pi", "runner": "once", "enabled": True, "pi": dict(PI)}])

    def tearDown(self):
        config.DATA = self._old
        self.tmp.cleanup()


class TestStore(Base):
    def test_set_get_clear(self):
        self.assertIsNone(config.get_secret("A"))
        config.set_secret("A", KEY)
        self.assertEqual(config.get_secret("A"), KEY)
        self.assertTrue((config.DATA / "secrets.json").is_file())
        self.assertTrue((config.DATA / "README-secrets.txt").is_file())
        config.set_secret("A", None)
        self.assertIsNone(config.get_secret("A"))
        self.assertEqual(config.all_secret_values(), [])

    def test_file_shape(self):
        config.set_secret("A", KEY)
        doc = json.loads((config.DATA / "secrets.json").read_text(encoding="utf-8"))
        self.assertEqual(doc, {"stations": {"A": {"api_key": KEY}}})


class TestPiEnv(Base):
    def test_models_json_never_holds_the_key(self):
        config.set_secret("A", KEY)
        doc = pi_config.build_models_json(config.stations())
        self.assertEqual(doc["providers"]["boxbox-a"]["apiKey"], "$BOXBOX_KEY_A")
        self.assertNotIn(KEY, json.dumps(doc))

    def test_env_name_is_internal(self):
        self.assertEqual(pi_config.key_env_name("A"), "BOXBOX_KEY_A")
        self.assertTrue(pi_config.key_env_name("审查").startswith("BOXBOX_KEY_"))

    def test_env_injection_prefers_stored_secret(self):
        st = config.station("A")
        self.assertFalse(pi_config.key_available(st))
        env = pi_config.pi_env(st, base_env={})
        self.assertNotIn("BOXBOX_KEY_A", env)
        config.set_secret("A", KEY)
        self.assertTrue(pi_config.key_available(st))
        env = pi_config.pi_env(st, base_env={"BOXBOX_KEY_A": "from-env"})
        self.assertEqual(env["BOXBOX_KEY_A"], KEY)          # secrets.json wins over the process env

    def test_env_var_alone_is_not_a_key(self):
        st = config.station("A")
        self.assertFalse(pi_config.key_available(st))
        env = pi_config.pi_env(st, base_env={"BOXBOX_KEY_A": "from-env"})
        self.assertNotIn("BOXBOX_KEY_A", env)                 # 环境变量里同名的也不算密钥
        self.assertFalse(pi_config.key_available(st))

    def test_validate_no_longer_requires_env_name(self):
        self.assertEqual(pi_config.validate_pi_block(dict(PI)), [])


class TestMaskAndDoctor(Base):
    def test_mask_hides_stored_values(self):
        config.set_secret("A", KEY)
        self.assertNotIn(KEY, classify.mask("Authorization: Bearer %s and raw %s" % (KEY, KEY)))

    def test_doctor_key_check(self):
        checks = {c.id: c for c in doctor.run(core_url=None, data_dir=config.DATA, stations=config.stations())}
        self.assertIn("key:A", checks)
        self.assertIs(checks["key:A"].ok, False)
        config.set_secret("A", KEY)
        checks = {c.id: c for c in doctor.run(core_url=None, data_dir=config.DATA, stations=config.stations())}
        self.assertIs(checks["key:A"].ok, True)
        self.assertNotIn(KEY, checks["key:A"].detail)


class TestHttp(Base):
    def setUp(self):
        super().setUp()
        from boxbox.dispatcher import Dispatcher
        from boxbox.facades.http import Core, serve
        from boxbox.store import Store
        self.d = Dispatcher(Store(config.DATA / "boxbox.db"))
        self.httpd = serve(Core(self.d), 0, block=False)
        self.url = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.d.store.db.close()
        super().tearDown()

    def call(self, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_write_only_and_has_key(self):
        code, out = self.call("/api/stations")
        self.assertIs(out["stations"][0]["has_key"], False)
        code, out = self.call("/api/secrets", {"station": "A", "api_key": KEY})
        self.assertEqual(code, 200, out)
        self.assertTrue(out["has_key"])
        for path in ("/api/stations", "/api/stations_def", "/api/meta", "/api/doctor", "/api/timeline?limit=10"):
            code, body = self.call(path)
            self.assertNotIn(KEY, json.dumps(body, ensure_ascii=False), path)
        self.assertIs(self.call("/api/stations")[1]["stations"][0]["has_key"], True)
        code, out = self.call("/api/secrets", {"station": "A", "api_key": ""})
        self.assertTrue(out["ok"])
        self.assertIs(self.call("/api/stations")[1]["stations"][0]["has_key"], False)

    def test_unknown_station_and_delete_clears(self):
        code, out = self.call("/api/secrets", {"station": "ZZ", "api_key": KEY})
        self.assertEqual(code, 404)
        self.call("/api/secrets", {"station": "A", "api_key": KEY})
        self.call("/api/stations/delete", {"id": "A"})
        self.assertIsNone(config.get_secret("A"))


if __name__ == "__main__":
    unittest.main()
