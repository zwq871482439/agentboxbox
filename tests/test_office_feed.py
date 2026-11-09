# -*- coding: utf-8 -*-
"""办公室视图数据适配（工作计划 1.12）：核心 v2 的四份数据 → boxbox.office/1。

守住：leader 是 arch 且 skin.cat==1（#82：首领永不落 you，它没反应由别的猫围过去冒 ?，feed 给 leader_quiet 布尔值）；
在跑的工位是 run；失败落 fail；卡住 / 打回待定 / 等首领验收落 arch（…）；第 1 级提醒（等你验收 / 定时任务没来）落 you（!）；
状态级别只读 meta.alerts（boxbox.alerts 算好的唯一一份），feed 不重算；
停用工位是 off；token 映射对、缺了全 0；channels 的键不小于 office/sample.json 的样例；
空 board / 缺字段不炸。
    python -m unittest tests.test_office_feed -v
"""
import json
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from boxbox import office_feed  # noqa: E402

NOW = "2026-10-21T16:00:00+08:00"

META = {"version": 2, "now": NOW, "running": 1, "open": 2, "done_today": 3,
        "leader": "架构师", "leader_last_seen": NOW, "data": "calls"}


def alert(level, kind, station, **kw):
    """一条 /api/meta 的 alerts（boxbox.alerts.compute 的产出形状）。"""
    a = {"level": level, "kind": kind, "station": station, "task_id": "T1", "title": "任务",
         "text": "提示", "action": "去做点什么" if level == 1 else ""}
    a.update(kw)
    return a


WORD_CODES = {"闲": "idle", "在跑": "running", "在岗": "on_duty", "已停用": "off",
              "待定时任务": "wait_sched", "在岗（定时）": "on_duty_sched", "定时任务没触发": "sched_late"}
KIND_CODES = {"卡住": "blocked", "待验收": "reviewing", "打回待定": "returned",
              "中断": "interrupted", "没开工": "unstarted", "失败": "failed"}


def board_row(sid, role="member", word="闲", enabled=True, **kw):
    row = {"id": sid, "role": role, "client": "pi", "runner": "once", "enabled": enabled,
           "word": word, "word_code": kw.pop("word_code", WORD_CODES.get(word, "")),
           "task_id": None, "title": None, "minutes": None, "open": 0, "last_seen": NOW}
    row.update(kw)
    return row


def todo_of(items):
    return {"items": items, "idle_stations": [], "count": len(items)}


def item(kind, station, **kw):
    d = {"kind": kind, "kind_code": kw.pop("kind_code", KIND_CODES.get(kind, "")),
         "task_id": "T1", "title": "任务", "station": station, "since": NOW}
    d.update(kw)
    return d


def sample():
    with open(os.path.join(ROOT, "office", "sample.json"), encoding="utf-8") as f:
        return json.load(f)


class TestStates(unittest.TestCase):
    def build(self, board, todo=None, tokens=None, meta=None, defs=None, alerts=None):
        meta = dict(meta or META)
        if alerts is not None:
            meta["alerts"] = alerts
        return office_feed.build(meta, board, todo or todo_of([]), tokens or {"stations": []}, defs, lang="zh")

    def ch(self, data, sid):
        return next(c for c in data["channels"] if c["id"] == sid)

    def test_leader_is_arch(self):
        d = self.build([board_row("架构师", role="leader", word="在岗", client="cursor", runner="manual")])
        lead = d["channels"][0]
        self.assertEqual(lead["state"], "arch")
        self.assertEqual(lead["role"], "lead")
        self.assertEqual(lead["label"], "首领 · 架构师")          # #93：界面上叫首领
        self.assertEqual(lead["skin"]["cat"], 1)
        self.assertEqual(lead["accent"], "#ffb347")
        self.assertEqual(lead["channel"], "你在 AI 软件里开对话")
        self.assertEqual(lead["route"], "manual")

    def test_cat_name_is_station_name(self):
        """猫脚下画的名字 = 工位名（上岗时起的）；name 字段是型号 / 客户端，不能拿来当猫名"""
        d = self.build([board_row("猫猫首领", role="leader", word="在岗", client="cursor", runner="manual")])
        lead = d["channels"][0]
        self.assertEqual(lead["cat_name"], "猫猫首领")
        self.assertNotEqual(lead["name"], "猫猫首领")

    def test_leader_never_you_and_quiet_flag(self):
        # #82：首领头上不冒叹号——它没反应时状态仍是 arch，feed 给 leader_quiet=True 让别的猫围过去
        d = self.build([board_row("架构师", role="leader", word="在岗")],
                       todo=todo_of([item("卡住", "A")]),
                       alerts=[alert(1, "leader_quiet", "架构师", action_id="summon")])
        self.assertEqual(d["channels"][0]["state"], "arch")
        self.assertTrue(d["leader_quiet"])
        self.assertEqual(d["alerts"][0]["kind"], "leader_quiet")
        d2 = self.build([board_row("架构师", role="leader", word="在岗")], todo=todo_of([item("卡住", "A")]))
        self.assertEqual(d2["channels"][0]["state"], "arch")      # 没有 leader_quiet 提醒：首领就是在岗
        self.assertFalse(d2["leader_quiet"])

    def test_running_member_is_run(self):
        d = self.build([board_row("A", word="在跑", title="写单测")])
        c = d["channels"][0]
        self.assertEqual(c["state"], "run")
        self.assertEqual(c["state_word"], "在跑")
        self.assertEqual(c["task_d"], "写单测")
        self.assertEqual(c["label"], "A")                      # #93：打工猫直接用名字

    def test_todo_failed_is_fail(self):
        d = self.build([board_row("A")], todo_of([item("失败", "A")]), alerts=[alert(2, "failed", "A")])
        self.assertEqual(self.ch(d, "A")["state"], "fail")
        self.assertEqual(self.ch(d, "A")["state_word"], "失败")

    def test_todo_drawer_gets_items(self):
        """办公室的待办抽屉拿得到明细：有待办就不再停在「明细还没算出来」"""
        d = self.build([board_row("A")], todo_of([item("卡住", "A", reason="缺 README", title="写说明")]))
        self.assertEqual(d["arch"]["items"], [{"kind": "卡住", "title": "写说明", "since": NOW,
                                               "why": "缺 README", "source": "A", "url": "/board"}])
        self.assertEqual(self.build([board_row("A")])["arch"]["items"], [])

    def test_todo_waiting_review_is_arch(self):
        # 等首领验收：第 2 级，落 arch（头上 …），不是要用户决策
        d = self.build([board_row("A")], todo_of([item("待验收", "A")]), alerts=[alert(2, "reviewing", "A")])
        self.assertEqual(self.ch(d, "A")["state"], "arch")
        self.assertEqual(self.ch(d, "A")["state_word"], "待验收")

    def test_todo_waiting_user_review_is_you(self):
        # 验收人是用户：第 1 级 → you（头上 !）
        d = self.build([board_row("A")], todo_of([item("待验收", "A", who="user")]), alerts=[alert(1, "review_user", "A")])
        self.assertEqual(self.ch(d, "A")["state"], "you")
        self.assertEqual(self.ch(d, "A")["state_word"], "待验收")

    def test_todo_blocked_is_arch(self):
        for kind, code in (("卡住", "blocked"), ("打回待定", "returned")):
            d = self.build([board_row("A")], todo_of([item(kind, "A")]), alerts=[alert(2, code, "A")])
            self.assertEqual(self.ch(d, "A")["state"], "arch", kind)
            self.assertEqual(self.ch(d, "A")["state_word"], kind)

    def test_fail_beats_you(self):
        d = self.build([board_row("A")], todo_of([item("待验收", "A"), item("失败", "A")]),
                       alerts=[alert(2, "failed", "A"), alert(1, "review_user", "A")])
        self.assertEqual(self.ch(d, "A")["state"], "you")          # 第 1 级优先：先让用户去验收

    def test_running_beats_todo(self):
        d = self.build([board_row("A", word="在跑")], todo_of([item("卡住", "A")]), alerts=[alert(2, "blocked", "A")])
        self.assertEqual(self.ch(d, "A")["state"], "run")

    def test_disabled_is_off(self):
        d = self.build([board_row("A", word="已停用", enabled=False)])
        self.assertEqual(self.ch(d, "A")["state"], "off")
        self.assertEqual(self.ch(d, "A")["state_word"], "已停用")

    def test_idle_by_default(self):
        d = self.build([board_row("A")])
        self.assertEqual(self.ch(d, "A")["state"], "idle")
        self.assertEqual(self.ch(d, "A")["state_word"], "闲")


class TestSkinAndAccent(unittest.TestCase):
    def test_cats_cycle_and_leader_first(self):
        board = [board_row("架构师", role="leader")] + [board_row(s) for s in ("A", "B", "C", "D", "E", "F")]
        d = office_feed.build(META, board, todo_of([]), {"stations": []}, lang="zh")
        cats = [c["skin"]["cat"] for c in d["channels"]]
        self.assertEqual(cats, [1, 2, 3, 4, 5, 6, 2])
        self.assertEqual(d["channels"][2]["accent"], "#b48cff")


class TestTokensAndStrip(unittest.TestCase):
    def test_tokens_mapped(self):
        tokens = {"stations": [{"station": "A", "runs": 4, "tok_in": 32547, "tok_out": 8689,
                                "tok_cr": 592128, "tok_cw": 10, "cost": 0.5},
                               {"station": "B", "runs": 2, "tok_in": 1, "tok_out": 2, "tok_cr": 3, "tok_cw": 4}]}
        d = office_feed.build(META, [board_row("A"), board_row("B"), board_row("C")], todo_of([]), tokens, lang="zh")
        a, b, c = (ch for ch in d["channels"])
        self.assertEqual(a["tok"]["today"], {"in": 32547, "out": 8689, "cr": 592128, "calls": 4, "hit": 95})   # 命中率 = 缓存读 / (输入 + 缓存读)
        self.assertEqual(b["tok"]["today"]["calls"], 2)
        self.assertEqual(c["tok"]["today"], {"in": 0, "out": 0, "cr": 0, "calls": 0, "hit": 0})
        self.assertEqual(d["strip"]["calls_today"], 6)

    def test_tokens_missing_all_zero(self):
        d = office_feed.build(META, [board_row("A")], todo_of([]), {}, lang="zh")
        self.assertEqual(d["channels"][0]["tok"]["today"]["in"], 0)
        self.assertEqual(d["strip"]["calls_today"], 0)


class TestShapeMatchesSample(unittest.TestCase):
    def test_channel_keys_cover_sample(self):
        s = sample()
        need = set(s["channels"][0].keys())
        d = office_feed.build(META, [board_row("架构师", role="leader"), board_row("A")], todo_of([]), {"stations": []}, lang="zh")
        for ch in d["channels"]:
            self.assertTrue(need.issubset(set(ch.keys())), need - set(ch.keys()))

    def test_top_level_keys_cover_sample(self):
        s = sample()
        d = office_feed.build(META, [board_row("A")], todo_of([]), {"stations": []}, lang="zh")
        self.assertTrue(set(s.keys()).issubset(set(d.keys())))
        self.assertEqual(d["schema"], "boxbox.office/1")
        self.assertEqual(d["fetched"], NOW)
        self.assertEqual(d["background"], [])

    def test_page_can_read_it(self):
        """页面直接 .xxx 取的字段都不能是 None。"""
        d = office_feed.build(META, [board_row("架构师", role="leader"), board_row("A", word="在跑")],
                              todo_of([item("卡住", "A")]), {"stations": []}, lang="zh")
        for ch in d["channels"]:
            for k in ("id", "role", "label", "name", "model", "channel", "route", "accent", "state",
                      "state_word", "state_sub", "quota_source", "quota_reset", "task_d", "tool", "last"):
                self.assertIsNotNone(ch[k], k)
            self.assertIsNone(ch["quota_left_pct"])   # v2 不记额度：页面看到 null 写「无数据」
            self.assertIsInstance(ch["queue"], int)
            self.assertIsInstance(ch["queue_items"], list)
            self.assertIsInstance(ch["skin"]["cat"], int)
            self.assertIsInstance(ch["tok"]["today"]["calls"], int)


class TestHeader(unittest.TestCase):
    def test_strip_and_arch(self):
        todo = todo_of([item("卡住", "A"), item("待验收", "B"), item("待验收", "B"), item("失败", "A")])
        d = office_feed.build(dict(META, running=2), [board_row("架构师", role="leader"), board_row("A"), board_row("B")],
                              todo, {"stations": [{"station": "A", "runs": 3}]}, lang="zh")
        self.assertEqual(d["strip"], {"calls_today": 3, "ok_pct": None, "running": 2, "total": 3})   # #91：没有收尾的卡不报 100%
        d2 = office_feed.build(dict(META, success_7d={"done": 3, "failed": 1, "rate": 0.75}), [], todo, {"stations": []}, lang="zh")
        self.assertEqual(d2["strip"]["ok_pct"], 75.0)                                       # 和顶栏同一个口径
        self.assertEqual(d["arch"]["count"], 4)
        self.assertEqual(d["arch"]["summary"], "首领待办 4：卡住 1、待验收 2、失败 1")

    def test_arch_summary_zero_count(self):
        d = office_feed.build(META, [], todo_of([]), {"stations": []}, lang="zh")
        self.assertEqual(d["arch"], {"count": 0, "user_count": 0, "summary": "首领待办 0：没有待办", "items": []})
        self.assertEqual(d["channels"], [])

    def test_minutes_ago(self):
        f = office_feed.minutes_ago
        self.assertEqual(f("2026-10-21T15:57:00+08:00", NOW, "zh"), "3 分钟前")
        self.assertEqual(f("2026-10-21T16:00:00+08:00", NOW, "zh"), "0 分钟前")
        self.assertEqual(f(None, NOW, "zh"), "从未")
        self.assertEqual(f("昨晚", NOW, "zh"), "未知")
        self.assertEqual(f("2026-10-21T16:30:00+08:00", NOW, "zh"), "0 分钟前")
        self.assertEqual(f("2026-10-21T15:57:00+08:00", NOW, "en"), "3 min ago")


class TestModelAndRunner(unittest.TestCase):
    def test_pi_model_wins(self):
        board = [board_row("A", client="pi")]
        defs = [{"id": "A", "client": "pi", "pi": {"model": "Kimi K3"}}]
        d = office_feed.build(META, board, todo_of([]), {"stations": []}, defs, lang="zh")
        self.assertEqual(d["channels"][0]["name"], "Kimi K3")
        self.assertEqual(d["channels"][0]["model"], "Kimi K3")
        self.assertEqual(d["channels"][0]["state_sub"], "pi")

    def test_fallback_to_client(self):
        d = office_feed.build(META, [board_row("A", client="cursor")], todo_of([]), {"stations": []}, [{"id": "A"}], lang="zh")
        self.assertEqual(d["channels"][0]["name"], "cursor")

    def test_runner_labels(self):
        for mode, label in (("manual", "你在 AI 软件里开对话"), ("once", "用 API key 自动跑"),
                           ("scheduled", "会话模式：AI 软件定时来领")):
            d = office_feed.build(META, [board_row("A", runner=mode)], todo_of([]), {"stations": []}, lang="zh")
            self.assertEqual(d["channels"][0]["channel"], label)


class TestMissingFields(unittest.TestCase):
    def test_empty_board(self):
        d = office_feed.build({}, [], {}, {}, lang="zh")
        self.assertEqual(d["channels"], [])
        self.assertEqual(d["strip"]["total"], 0)
        self.assertEqual(d["fetched"], "")
        self.assertEqual(d["schema"], "boxbox.office/1")

    def test_sparse_rows(self):
        d = office_feed.build({"alerts": [{"level": 2, "kind": "blocked", "station": "A"}]},
                              [{"id": "A"}], {"items": [{"kind": "卡住", "kind_code": "blocked", "station": "A"}]},
                              {}, lang="zh")
        c = d["channels"][0]
        self.assertEqual(c["state"], "arch")
        self.assertEqual(c["state_word"], "卡住")
        self.assertEqual(c["label"], "A")                      # #93：打工猫直接用名字
        self.assertEqual(c["channel"], "")
        self.assertEqual(c["last"], "从未")
        self.assertEqual(c["task_d"], "")
        self.assertIsNone(c["quota_left_pct"])

    def test_none_inputs(self):
        d = office_feed.build(None, None, None, None, None, lang="zh")
        self.assertEqual(d["channels"], [])
        self.assertEqual(d["background"], [])


class TestQuota(unittest.TestCase):
    """猫头顶的余量血条：数据从查余量的结果来（同一份额度一份）。"""

    def build(self, quotas=None, defs=None, lang="zh"):
        defs = defs if defs is not None else [{"id": "A", "quota": {"mode": "interval"}}]
        return office_feed.build(META, [board_row("A")], todo_of([]), {"stations": []}, defs,
                                 lang=lang, quotas=quotas or {})

    def ch(self, data, sid="A"):
        return next(c for c in data["channels"] if c["id"] == sid)

    def test_takes_most_used_window(self):
        res = {"ok": True, "windows": {"h5": {"pct": 20.0, "reset": "2026-11-02T10:00:00+08:00"},
                                       "week": {"pct": 75.4, "reset": "2026-11-05T10:00:00+08:00"}}}
        c = self.ch(self.build({"A": res}))
        self.assertEqual(c["quota_mode"], "interval")
        self.assertEqual(c["quota_used_pct"], 75)
        self.assertEqual(c["quota_left_pct"], 25)
        self.assertEqual(c["quota_slot"], "周")
        self.assertEqual(c["quota_source"], "套餐余量")
        self.assertEqual(c["quota_reset"], "2026-11-05T10:00:00+08:00")

    def test_expired_window_dropped(self):
        """重置时间已经过的窗口旧数不算数，丢掉它。"""
        res = {"ok": True, "windows": {"h5": {"pct": 90.0, "reset": "2026-10-20T10:00:00+08:00"},
                                       "week": {"pct": 40.0, "reset": "2026-11-05T10:00:00+08:00"}}}
        c = self.ch(self.build({"A": res}))
        self.assertEqual(c["quota_used_pct"], 40)
        self.assertEqual(c["quota_slot"], "周")

    def test_all_windows_expired_is_off(self):
        res = {"ok": True, "windows": {"h5": {"pct": 90.0, "reset": "2026-10-20T10:00:00+08:00"}}}
        c = self.ch(self.build({"A": res}))
        self.assertEqual(c["quota_mode"], "off")
        self.assertIsNone(c["quota_left_pct"])
        self.assertEqual(c["quota_slot"], "")

    def test_station_without_quota_mode_is_off(self):
        res = {"ok": True, "windows": {"h5": {"pct": 30.0, "reset": None}}}
        c = self.ch(self.build({"A": res}, defs=[{"id": "A", "quota": {"mode": "off"}}]))
        self.assertEqual(c["quota_mode"], "off")
        self.assertIsNone(c["quota_used_pct"])

    def test_missing_result_is_off(self):
        c = self.ch(self.build({}))
        self.assertEqual(c["quota_mode"], "off")
        self.assertIsNone(c["quota_left_pct"])
        self.assertEqual(c["quota_source"], "不计")

    def test_failed_result_is_off(self):
        c = self.ch(self.build({"A": {"ok": False, "error_kind": "bad_key"}}))
        self.assertEqual(c["quota_mode"], "off")
        self.assertIsNone(c["quota_used_pct"])

    def test_english_window_words(self):
        res = {"ok": True, "windows": {"h5": {"pct": 10.0, "reset": None},
                                       "month": {"pct": 60.0, "reset": None}}}
        c = self.ch(self.build({"A": res}, lang="en"))
        self.assertEqual(c["quota_slot"], "month")
        self.assertEqual(c["quota_source"], "plan quota")

    def test_unknown_window_name_written_as_is(self):
        res = {"ok": True, "windows": {"weird": {"pct": 30.0, "reset": None}}}
        c = self.ch(self.build({"A": res}))
        self.assertEqual(c["quota_slot"], "weird")


class TestScheduledWords(unittest.TestCase):
    """路径 C（定时任务）工位的四个状态词：待定时任务 / 在岗（定时）/ 在跑 / 定时任务没触发。"""

    def build(self, board, todo=None, alerts=None):
        meta = dict(META)
        if alerts is not None:
            meta["alerts"] = alerts
        return office_feed.build(meta, board, todo or todo_of([]), {"stations": []}, lang="zh")

    def ch(self, data, sid):
        return next(c for c in data["channels"] if c["id"] == sid)

    def row(self, sid="K", word="待定时任务", **kw):
        d = {"client": "kimi-code", "runner": "scheduled", "last_scheduled_at": NOW, "scheduled_late": False}
        d.update(kw)
        return board_row(sid, word=word, **d)

    def test_waiting_first_trigger_is_idle(self):
        c = self.ch(self.build([self.row(last_scheduled_at=None)]), "K")
        self.assertEqual(c["state"], "idle")
        self.assertEqual(c["state_word"], "待定时任务")

    def test_on_duty_scheduled_is_idle(self):
        c = self.ch(self.build([self.row(word="在岗（定时）")]), "K")
        self.assertEqual(c["state"], "idle")
        self.assertEqual(c["state_word"], "在岗（定时）")

    def test_running_still_runs(self):
        c = self.ch(self.build([self.row(word="在跑", title="写单测")]), "K")
        self.assertEqual(c["state"], "run")
        self.assertEqual(c["state_word"], "在跑")

    def test_late_word_is_you(self):
        c = self.ch(self.build([self.row(word="定时任务没触发", scheduled_late=True)],
                               alerts=[alert(1, "scheduled_late", "K")]), "K")
        self.assertEqual(c["state"], "you")
        self.assertEqual(c["state_word"], "定时任务没触发")

    def test_late_flag_alone_is_you(self):
        c = self.ch(self.build([self.row(word="在岗（定时）", scheduled_late=True)],
                               alerts=[alert(1, "scheduled_late", "K")]), "K")
        self.assertEqual(c["state"], "you")

    def test_late_flag_without_alert_is_not_you(self):
        # #82：级别只读 alerts；核心没算出第 1 级，board 行的标记自己不升级
        c = self.ch(self.build([self.row(word="在岗（定时）", scheduled_late=True)]), "K")
        self.assertEqual(c["state"], "idle")

    def test_scheduled_fields_pass_through(self):
        d = self.build([self.row(word="定时任务没触发", scheduled_late=True)])
        c = self.ch(d, "K")
        self.assertTrue(c["scheduled_late"])
        self.assertEqual(c["last_scheduled_at"], NOW)
        plain = self.ch(self.build([board_row("A")]), "A")
        self.assertFalse(plain["scheduled_late"])
        self.assertIsNone(plain["last_scheduled_at"])

    def test_fail_beats_scheduled_idle(self):
        d = self.build([self.row(word="待定时任务", last_scheduled_at=None)], todo_of([item("失败", "K")]),
                       alerts=[alert(2, "failed", "K")])
        c = self.ch(d, "K")
        self.assertEqual(c["state"], "fail")
        self.assertEqual(c["state_word"], "失败")

    def test_blocked_beats_scheduled_idle(self):
        d = self.build([self.row(word="在岗（定时）")], todo_of([item("卡住", "K")]), alerts=[alert(2, "blocked", "K")])
        c = self.ch(d, "K")
        self.assertEqual(c["state"], "arch")
        self.assertEqual(c["state_word"], "卡住")

    def test_running_beats_late_flag(self):
        d = self.build([self.row(word="在跑", scheduled_late=True)], alerts=[alert(1, "scheduled_late", "K")])
        self.assertEqual(self.ch(d, "K")["state"], "run")

    def test_disabled_scheduled_is_off(self):
        d = self.build([self.row(word="已停用", enabled=False)])
        self.assertEqual(self.ch(d, "K")["state"], "off")


if __name__ == "__main__":
    unittest.main()
