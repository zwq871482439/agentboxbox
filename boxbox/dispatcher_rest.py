"""歇着：额度用完 / 接口连不上时先歇一会儿。"""
from __future__ import annotations

import datetime as _dt
import re

from . import classify, config, i18n, pi_config, quota
from .dispatcher_const import (
    CONFIG_KV,
    REST_BACKOFF,
    REST_KV,
    REST_REASONS,
    REST_TRY_KV,
    WAIT_NETWORK,
    WAIT_REASON_KEY,
    WAIT_REST,
)
from .runners import pi as pi_runner
from .store import now_iso

# 配置问题里唯一会自己好的一种：Windows 上找不到 Git Bash，装好 git 就能开工（看门狗每拍查一次）
CONFIG_NO_GIT_BASH = "no_git_bash"
# 歇着的「几点回来」：今天的只写「时:分」，别的日子带上「月-日」，周额度常常要等好几天
_CLOCK_HINT = re.compile(r"^(?:\d{2}-\d{2} )?\d{1,2}:\d{2}$")


def _hint_at(back_at: str, now: _dt.datetime) -> str:
    try:
        at = _dt.datetime.fromisoformat(back_at).astimezone(now.tzinfo)
    except ValueError:
        return ""
    return at.strftime("%H:%M") if at.date() == now.date() else at.strftime("%m-%d %H:%M")


class RestMixin:
    def resting(self) -> dict:
        """歇着的工位：{工位: {reason, reason_text, since, back_at, hint, try}}。核心自动判、自动解除。"""
        return self.store.kv_get(REST_KV) or {}
    def rest_of(self, sid: str) -> dict | None:
        return (self.resting() or {}).get(sid)
    @staticmethod
    def rest_when(hint: str, lang: str | None = None) -> str:
        """歇着时那句「什么时候回来」：预计 01:54 回来 / 预计 2 分钟后回来 / 过一会儿再试。"""
        hint = str(hint or "")
        lg = lang or i18n.lang()
        if not hint:
            return i18n.t("rest.when.later", lg)
        if _CLOCK_HINT.match(hint):
            return i18n.t("rest.when.hhmms", lg, t=hint)
        m = re.match(r"^(\d+)\s*(?:分钟后|分钟|min|minutes?)$", hint)
        if m:                      # 老数据里存的是「2 分钟后」这种带单位的
            return i18n.t("rest.when.minutes", lg, t=m.group(1))
        return i18n.t("rest.when.minutes", lg, t=hint)
    @staticmethod
    def rest_hint(hint: str, lang: str | None = None) -> str:
        """歇着的「什么时候回来」短句：预计 01:54 / 预计 2 分钟后 / 过一会儿再试。"""
        hint = str(hint or "")
        lg = lang or i18n.lang()
        if not hint:
            return i18n.t("rest.when.later", lg)
        if _CLOCK_HINT.match(hint):
            return i18n.t("rest.hint.hhmms", lg, t=hint)
        m = re.match(r"^(\d+)\s*(?:\u5206\u949f\u540e|\u5206\u949f|min|minutes?)$", hint)
        if m:                      # \u8001\u6570\u636e\u91cc\u5b58\u7684\u662f\u300c2 \u5206\u949f\u540e\u300d\u8fd9\u79cd\u5e26\u5355\u4f4d\u7684
            return i18n.t("rest.hint.minutes", lg, t=m.group(1))
        return i18n.t("rest.hint.minutes", lg, t=hint)
    @staticmethod
    def rest_word(entry: dict, lang: str | None = None) -> str:
        """歇着的状态词：歇着：额度用完，预计 01:54 回来 / 歇着：接口连不上，过一会儿再试。"""
        lg = lang or i18n.lang()
        reason = str(entry.get("reason") or "")
        why = i18n.t("rest.reason." + reason, lg) if reason in REST_REASONS else \
            str(entry.get("reason_text") or reason or "")
        return i18n.t("rest.word", lg, when=RestMixin.rest_when(entry.get("hint") or "", lg), why=why)
    def mark_resting(self, sid: str, reason: str, back_at: str | None = None, hint: str = "",
                     why: str = "", tries: int | None = None) -> dict:
        """这只猫歇着（额度用完 / 被限流 / 接口连不上 / 服务端出错）：核心自动判、自动解除。
        同样原因已经在歇着了就只更新时间，不重复喊一遍。"""
        with self.lock:
            data = dict(self.resting())
            old = data.get(sid) or {}
            entry = {"reason": reason, "reason_text": reason,
                     "since": old.get("since") or now_iso(), "back_at": back_at, "hint": hint or "",
                     "why": why or "", "try": int(tries if tries is not None else (old.get("try") or 0))}
            data[sid] = entry
            self.store.kv_set(REST_KV, data)
        if old.get("reason") != reason:
            self.store.event("rest_out", i18n.t("ev.rest_out", self.lang(), sid=sid, word=self.rest_word(entry, self.lang())),
                             sid, data={"reason": reason, "hint": entry.get("hint") or "", "back_at": entry.get("back_at") or ""})
        return entry
    def rest_tries(self, sid: str) -> int:
        """这只猫连着歇了几次（退避用）。猫回来干活干成了才清零。"""
        return int((self.store.kv_get(REST_TRY_KV) or {}).get(sid) or 0)
    def _bump_rest_tries(self, sid: str) -> int:
        with self.lock:
            data = dict(self.store.kv_get(REST_TRY_KV) or {})
            n = int(data.get(sid) or 0) + 1
            data[sid] = n
            self.store.kv_set(REST_TRY_KV, data)
        return n
    def _reset_rest_tries(self, sid: str) -> None:
        with self.lock:
            data = dict(self.store.kv_get(REST_TRY_KV) or {})
            if sid not in data:
                return
            data.pop(sid, None)
            self.store.kv_set(REST_TRY_KV, data)
    def rest_after_error(self, sid: str, err: str, reason: str) -> dict:
        """跑挂了（额度用完 / 被限流 / 服务端出错）：算出什么时候回来，写进歇着状态。
        错误里带时间就用它：「将在 01:54 重置」→ 01:54；Retry-After: 120 → 2 分钟后；
        没有就按退避 2、5、10、20 分钟（之后每 20 分钟）。"""
        now = _dt.datetime.now().astimezone()
        if reason == "network":
            # 接口连不上：不知道什么时候好，等 探测（network_retry_s）
            interval = float(config.settings().get("network_retry_s", 120))
            back_at = (now + _dt.timedelta(seconds=interval)).astimezone().isoformat(timespec="seconds")
            return self.mark_resting(sid, "network", back_at=back_at, hint="", why=err, tries=0)
        old = (self.resting() or {}).get(sid) or {}
        hint = classify.clock_hint(err) or ""
        back_at = classify.reset_time(err, now)
        if hint and old.get("reason") == reason and old.get("hint") == hint:
            # 同一个钟点又来了：那条时间早过了（上次就是它害的）→ 改走退避，别再睡一天
            hint = ""
            back_at = None
        if not hint:
            secs = classify.retry_delay_seconds(err)
            if secs is not None:
                back_at = (now + _dt.timedelta(seconds=secs)).astimezone().isoformat(timespec="seconds")
                hint = str(max(1, int(round(secs / 60))))   # 只存数字：显示时再按语言写成「几分钟」
        if back_at and _dt.datetime.fromisoformat(back_at) <= now:
            back_at, hint = None, ""          # 写的时刻已经过了（老消息 / 时钟对不上）：按退避，别每拍都重试
        if back_at and not hint:
            hint = _hint_at(back_at, now)
        if not back_at:
            # 拿不到恢复时间：按退避来（2、5、10、20 分钟，之后每 20 分钟）
            n = self._bump_rest_tries(sid)
            mins = REST_BACKOFF[min(n, len(REST_BACKOFF)) - 1]
            back_at = (now + _dt.timedelta(minutes=mins)).astimezone().isoformat(timespec="seconds")
            entry = self.mark_resting(sid, reason, back_at=back_at, hint=str(mins), why=err, tries=n)
        else:
            self._bump_rest_tries(sid)
            entry = self.mark_resting(sid, reason, back_at=back_at, hint=hint, why=err, tries=self.rest_tries(sid))
        if reason == "quota":
            self._rest_peers(sid, entry)
        return entry
    def _rest_peers(self, sid: str, entry: dict) -> None:
        """额度是按账户算的：同一把 key 的别的帮手一起歇到同一时刻，别轮着去撞同一堵墙。
        手上正在跑的不动（它自己撞上会自己歇）。"""
        running = {r.get("station") for r in self.store.open_runs()}
        for peer in quota.peers(config.station(sid) or {}):
            cur = self.rest_of(peer) or {}
            if peer in running or cur.get("reason") == "quota":
                continue
            self.mark_resting(peer, "quota", back_at=entry.get("back_at"), hint=entry.get("hint") or "",
                              why=entry.get("why") or "")
    def rest_spent_quota(self) -> int:
        """查额度看到账户用满了（某个窗口 ≥100%、重置还没到）：这个账户的帮手歇到重置，
        不再接活也不再一轮轮去试。看门狗每拍查一次（只读 kv 里已有的查询结果，不联网）。"""
        now = _dt.datetime.now().astimezone()
        running = {r.get("station") for r in self.store.open_runs()}
        n = 0
        for st in config.stations():
            sid = str(st.get("id") or "")
            if st.get("client") != "pi" or not st.get("enabled", True) or sid in running:
                continue
            if (self.rest_of(sid) or {}).get("reason") == "quota":
                continue
            until = quota.spent_until(quota.read(self.store, st), now)
            if until:
                self.mark_resting(sid, "quota", back_at=until, hint=_hint_at(until, now), why="quota check: 100%")
                n += 1
        return n
    def clear_resting(self, sid: str) -> bool:
        """猫回来了：清掉歇着状态（事件在接上卡的时候发）。"""
        with self.lock:
            data = dict(self.resting())
            if sid not in data:
                return False
            data.pop(sid, None)
            self.store.kv_set(REST_KV, data)
        self._just_back.add(sid)
        return True
    def _back_event(self, sid: str, task_id: str | None = None) -> None:
        """首领听见的「回来了」：打工猫猫A 回来了，接着干 20261029-003。"""
        self._just_back.discard(sid)
        lg = self.lang()
        text = i18n.t("ev.rest_back", lg, sid=sid, tid=task_id) if task_id else i18n.t("ev.rest_back_alone", lg, sid=sid)
        self.store.event("rest_back", text, sid, task_id, data={"task_id": task_id or ""})
    def restore_resting(self) -> int:
        """到点的歇着的猫回来：清状态 → 变回「闲」→ 按先来后到接排队的卡。返回回来的猫数。"""
        now = _dt.datetime.now().astimezone()
        back = []
        network_waiting = {t["assignee"] for t in self.store.list_tasks(state="queued")
                           if (t.get("card") or {}).get(WAIT_REASON_KEY) == WAIT_NETWORK}
        for sid, entry in (self.resting() or {}).items():
            if entry.get("reason") == "network" and sid in network_waiting:
                continue                      # 还有等接口的卡：等探通，不按点自愈
            ba = entry.get("back_at")
            if not ba:
                continue                      # 没定回来时刻的：等下一次再说
            try:
                when = _dt.datetime.fromisoformat(str(ba))
            except ValueError:
                continue
            if when.tzinfo is None:
                when = when.astimezone()
            if now >= when:
                back.append(sid)
        for sid in back:
            self.clear_resting(sid)
        if not back:
            return 0
        self.start_ready_queued()             # 回来的猫接着干排队的卡
        return len(back)
    def announce_back(self) -> int:
        """回来了但没有卡可接的：也说一声（首领听得到）。"""
        n = 0
        for sid in list(self._just_back):
            self._back_event(sid)
            n += 1
        return n
    def _rest_ok_to_start(self, st: dict) -> bool:
        """歇着的猫能不能现在开工：接口连不上（network）那种探一下，通了就回来；
        额度用完 / 被限流 / 服务端出错那些不行，等它自己到点。"""
        rest = self.rest_of(st["id"]) if st else None
        if not rest:
            return True
        if rest.get("reason") != "network":
            return False
        if pi_config.api_probe((st.get("pi") or {})).ok:
            self.clear_resting(st["id"])
            return True
        return False
    def _rest_wait_key(self, sid: str) -> str:
        """歇着的卡排队标记：接口连不上那种等 探测（network），别的等它回来（rest）。"""
        rest = self.rest_of(sid) or {}
        return WAIT_NETWORK if rest.get("reason") == "network" else WAIT_REST
    def config_bads(self) -> dict:
        """配置有问题的工位：{工位: {why, since}}。模型 id 或密钥错了不会自己好，保存配置才清。"""
        return self.store.kv_get(CONFIG_KV) or {}
    def config_of(self, sid: str) -> dict | None:
        return (self.config_bads() or {}).get(sid)
    @staticmethod
    def config_quote(err: str) -> str:
        """给用户看的服务商原话：去掉密钥，压成一行，只留前 200 字。"""
        text = classify.mask(str(err or "")).replace("\r", " ").replace("\n", " ").strip()
        return text[:200]
    def mark_config_bad(self, sid: str, err: str, reason: str = "") -> dict:
        """记一笔「配置有问题」。不写回来时刻：到点也不会自己变回闲（reason=CONFIG_NO_GIT_BASH 的例外，
        那种装好 git 就能开工，看门狗每拍查一次）。"""
        why = self.config_quote(err)
        with self.lock:
            data = dict(self.config_bads())
            old = data.get(sid) or {}
            entry = {"why": why, "since": old.get("since") or now_iso(), "reason": reason}
            data[sid] = entry
            self.store.kv_set(CONFIG_KV, data)
        return entry
    def clear_config_bad(self, sid: str) -> bool:
        with self.lock:
            data = dict(self.config_bads())
            if sid not in data:
                return False
            data.pop(sid, None)
            self.store.kv_set(CONFIG_KV, data)
        return True
    def release_config_bad(self, sid: str) -> bool:
        """配置保存过了：清掉标记。下一张卡用刚保存的那份，排队的卡接着开工。"""
        if not self.clear_config_bad(sid):
            return False
        st = self.station(sid)
        runner = self.runners.get(sid)
        if runner is not None and st is not None and hasattr(runner, "reconfigure"):
            runner.reconfigure(st)
        self.store.event("config_ok", i18n.t("ev.config_ok", self.lang(), sid=sid), sid)
        self.start_ready_queued()
        return True
    def release_no_git_bash(self) -> int:
        """被标「找不到 Git Bash」的猫：现在找得到了就自动恢复（别的配置错不会自己好，不走这里）。
        release_config_bad 里会接着把排队的卡开起来。"""
        stuck = [sid for sid, e in (self.config_bads() or {}).items() if e.get("reason") == CONFIG_NO_GIT_BASH]
        if not stuck or not pi_runner._git_bash_dir():
            return 0
        for sid in stuck:
            self.release_config_bad(sid)
        return len(stuck)
    def _config_failure(self, res) -> bool:
        """这次失败是不是配置错了：只认退出码 13（Pi 收尾时已把 auth 类报错转成 13）。
        不看报错文字：超时的报错里带着命令本身，pytest -k test_invalid_token 会被冤枉成密钥错了。"""
        return int(getattr(res, "exit", 0) or 0) == classify.EXIT_CODES["auth"]
