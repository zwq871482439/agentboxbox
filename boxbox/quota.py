"""套餐余量查询：Kimi Code / 智谱 GLM Coding Plan / MiniMax Token Plan 三家适配器 + 自定义查询地址。

统一返回（成功）{"ok": true, "windows": {"h5"|"week"|"month": {"pct": 已用百分比, "reset": 重置时间}}, "fetched": 时间}；
失败 {"ok": false, "error_kind": "key 不对" | "接口变了" | "网络问题" | "没有 key", "error": 简短原因}。
HTTP 401/403 → key 不对；超时 / 连不上 → 网络问题；字段缺失 → 接口变了。

key 从工位取（只从 data/secrets.json 来），只用来发请求：
绝不写进日志、事件、返回值，也不进 kv 的键。同一份额度（适配器 + key + 自定义查询配置）
只存一份；30 秒内的重复查询合并成一次请求。

仅标准库。真联网的只有 _http_get（测试注入 http_get 参数换掉它）。"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config, i18n
from .store import now_iso

ADAPTERS = ("kimi_code", "glm_coding_plan", "minimax_token_plan", "custom")
#: 按 base_url 主机名自动建议的适配器（其它默认 custom）
HOST_ADAPTERS = {"api.kimi.com": "kimi_code", "open.bigmodel.cn": "glm_coding_plan",
                 "minimaxi.com": "minimax_token_plan", "minimax.cn": "minimax_token_plan"}

KIMI_URL = "https://api.kimi.com/coding/v1/usages"
GLM_URL = "https://open.bigmodel.cn/api/monitor/usage/quota/limit"
MINIMAX_URL = "https://www.minimax.cn/v1/token_plan/remains"

_DEDUP_TTL = 30.0          # 秒：同一份额度这么久以内只查一次
_dedup_locks: dict[str, threading.Lock] = {}
_dedup_cache: dict[str, tuple[float, dict]] = {}

WINDOW_LABELS = ("h5", "week", "month", "tools", "plan")   # 窗口名字的机器值（其余原样，不当成词条翻）
# 自定义查询里真正影响请求的字段（顺序固定，好让同一份配置算出同一个账户）
_CUSTOM_FIELDS = ("url", "auth", "pct_path", "remaining_pct_path", "reset_path")
_busy: set[str] = set()    # 正在后台查的额度账户（同一份额度同时只查一条）
_busy_lock = threading.Lock()

_AUTH_WORDS = re.compile(r"(?i)auth|api[ _-]?key|鉴权|密钥|无效|token|unauthorized|forbidden")


class _Bad(Exception):
    """解析失败：code 是统一的错误编号，kind 是大分类（给界面当标题用）。"""

    def __init__(self, code: str, kind: str = "changed", **vars):
        super().__init__(code)
        self.code, self.kind, self.vars = code, kind, vars


def _fail(code: str, kind: str = "changed", **vars) -> dict:
    """报错：存编号和参数，不存成品文字——成品文字等给人看的时候再按语言翻。"""
    return {"ok": False, "error_kind": kind, "error_code": code, "error_vars": vars}


def localize(res: dict, lang: str | None = None) -> dict:
    """把余量结果里的编号翻成当下的语言（缓存里存的是编号，所以换语言不用重查）。"""
    if not isinstance(res, dict):
        return res
    out = dict(res)
    code = str(out.get("error_code") or "")
    if code:
        kind = str(out.get("error_kind") or "unknown")
        out["error_kind"] = i18n.t("quota.kind." + kind, lang)
        vars_ = dict(out.get("error_vars") or {})
        if code == "auth_said" and not vars_.get("msg"):
            vars_["msg"] = i18n.t("quota.msg.auth_default", lang)
        out["error"] = i18n.t("quota.msg." + code, lang, **vars_)
    wins = out.get("windows")
    if isinstance(wins, dict):
        out["windows"] = {k: (dict(v) if isinstance(v, dict) else v) for k, v in wins.items()}
        for w in out["windows"].values():
            if isinstance(w, dict) and str(w.get("label") or "") in WINDOW_LABELS:
                w["label"] = i18n.t("quota.window." + str(w["label"]), lang)
    return out


# ---- 数值 / 时间（各家都爱把数字当字符串回，还带毫秒时间戳） ----
def _f(v, what: str) -> float:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        raise _Bad("num_not_number", what=what) from None


def _pct(used, limit) -> float:
    u, lm = _f(used, "used"), _f(limit, "limit")
    if lm <= 0:
        raise _Bad("limit_not_positive")
    return round(u / lm * 100, 1)


def _ratio_pct(ratio) -> float:
    """0 到 1 的比值 → 百分比；拿到手的已经是百分数就直接用。"""
    r = _f(ratio, "used_ratio")
    return round(r * 100 if r <= 1.0 else r, 1)


def _reset(v):
    """重置时间：毫秒 / 秒时间戳转成本地 ISO，别的时间文字原样带回；空 → None。"""
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        s = str(v).strip()
        if not s:
            return None
        if not s.isdigit():
            # ISO 文字（Kimi 回的是 UTC 的 ...Z，小数秒有 6 位）→ 统一成本地时区，和另两家一个格式
            try:
                t = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
                if t.tzinfo is not None:
                    return t.astimezone().replace(microsecond=0).isoformat()
            except ValueError:
                pass
            return s
        n = float(s)
    try:
        if n > 1e12:      # 毫秒
            return _dt.datetime.fromtimestamp(n / 1000).astimezone().replace(microsecond=0).isoformat()
        if n > 1e9:       # 秒
            return _dt.datetime.fromtimestamp(n).astimezone().replace(microsecond=0).isoformat()
    except (OSError, OverflowError, ValueError):
        return str(v)
    return str(v)


def _walk(data, path):
    """按 a.b.c 走进返回的 JSON（数组用下标：a.0.b）；取不到 → None。"""
    if not path:
        return None
    cur = data
    for part in str(path).split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur[part]
        else:
            return None
    return cur


# ---- 适配器：解析（fetch 里先换成字典再进来） ----
def _is_h5(duration, time_unit) -> bool:
    """Kimi 的 limits[] 里哪条是 5 小时窗口：duration 300（分钟）或 timeUnit 说明换算后等于 300 分钟。"""
    try:
        d = float(str(duration).strip())
    except (TypeError, ValueError):
        return False
    unit = str(time_unit or "").lower()
    factor = 60.0 if unit in ("h", "hr", "hour", "hours") else 1.0
    return round(d * factor) == 300


def _kimi(data: dict) -> dict:
    """Kimi Code。新格式 usage（周）+ limits[]（5 小时）；老格式 usages.limit_5h / limit_7d 也认。"""
    win: dict = {}
    u = data.get("usage") if isinstance(data.get("usage"), dict) else None
    if u is not None:
        win["week"] = {"pct": _pct(u.get("used"), u.get("limit")), "reset": _reset(u.get("resetTime"))}
    if isinstance(data.get("limits"), list):
        for lim in data["limits"]:
            if not isinstance(lim, dict) or "h5" in win:
                continue
            w = lim.get("window") if isinstance(lim.get("window"), dict) else {}
            if _is_h5(w.get("duration"), w.get("timeUnit")):
                d = lim.get("detail") if isinstance(lim.get("detail"), dict) else {}
                if d.get("limit") is not None and d.get("used") is not None:
                    win["h5"] = {"pct": _pct(d.get("used"), d.get("limit")), "reset": _reset(d.get("resetTime"))}
    old = data.get("usages") if isinstance(data.get("usages"), dict) else {}
    for src, dst in (("limit_5h", "h5"), ("limit_7d", "week")):
        blk = old.get(src) if isinstance(old.get(src), dict) else {}
        if blk.get("used_ratio") is not None and dst not in win:
            win[dst] = {"pct": _ratio_pct(blk.get("used_ratio")), "reset": _reset(blk.get("reset_time"))}
    if not win:
        raise _Bad("no_usage_block")
    return {"ok": True, "windows": win}


def _glm(data: dict) -> dict:
    """智谱 GLM Coding Plan：data.limits[] 里 (unit=3,number=5) 5 小时、(6,1) 周、(5,1) 月（工具次数）。"""
    d = data.get("data") if isinstance(data.get("data"), dict) else {}
    limits = d.get("limits")
    if not isinstance(limits, list) or not limits:
        raise _Bad("no_data_limits")
    key = {(3, 5): "h5", (6, 1): "week", (5, 1): "month"}
    win: dict = {}
    for lim in limits:
        if not isinstance(lim, dict) or lim.get("percentage") is None:
            continue
        try:
            k = (int(_f(lim.get("unit"), "unit")), int(_f(lim.get("number"), "number")))
        except _Bad:
            continue
        w = key.get(k)
        if w and w not in win:
            entry = {"pct": round(_f(lim.get("percentage"), "percentage"), 1), "reset": _reset(lim.get("nextResetTime"))}
            if w == "month":
                entry["label"] = "tools"    # 月窗口是联网工具次数，不是 token
            win[w] = entry
    if not win:
        raise _Bad("no_window_in_limits")
    out = {"ok": True, "windows": win}
    if d.get("level"):
        out["level"] = str(d["level"])
    return out


def _minimax(data: dict) -> dict:
    """MiniMax Token Plan：出错也回 200，看 base_resp.status_code；model_remains[] 里 general 那条（没有取第一条）。"""
    br = data.get("base_resp") if isinstance(data.get("base_resp"), dict) else {}
    try:
        code = int(br.get("status_code") or 0)
    except (TypeError, ValueError):
        code = -1
    if code != 0:
        msg = str(br.get("status_msg") or "")
        if _AUTH_WORDS.search(msg):
            raise _Bad("auth_said", kind="bad_key", msg=msg)
        raise _Bad("provider_error", status=br.get("status_code"), msg=msg[:80])
    rows = data.get("model_remains")
    if not isinstance(rows, list) or not rows:
        raise _Bad("no_model_remains")
    row = next((r for r in rows if isinstance(r, dict) and r.get("model_name") == "general"), None)
    if row is None:
        row = next((r for r in rows if isinstance(r, dict)), None)
    if row is None:
        raise _Bad("model_remains_empty")
    win: dict = {}
    for src, dst, tkey in (("current_interval_remaining_percent", "h5", "end_time"),
                           ("current_weekly_remaining_percent", "week", "weekly_end_time")):
        if row.get(src) is not None:
            win[dst] = {"pct": round(100 - _f(row.get(src), src), 1), "reset": _reset(row.get(tkey))}
    if not win:
        raise _Bad("no_remaining_pct")
    return {"ok": True, "windows": win}


def _custom(data: dict, cfg: dict) -> dict:
    """自定义：pct_path 取已用百分比；没填就取 remaining_pct_path 按 100 减；reset_path 可选。"""
    used = None
    p = _walk(data, cfg.get("pct_path"))
    if p is not None:
        used = round(_f(p, "used_percent"), 1)
    else:
        r = _walk(data, cfg.get("remaining_pct_path"))
        if r is not None:
            used = round(100 - _f(r, "remaining_percent"), 1)
    if used is None:
        raise _Bad("pct_path_missing", a=cfg.get("pct_path"), b=cfg.get("remaining_pct_path"))
    used = min(max(used, 0.0), 100.0)   # 百分比超出 0–100 就截住，条好画
    win = {"h5": {"pct": used, "reset": _reset(_walk(data, cfg.get("reset_path"))), "label": "plan"}}
    return {"ok": True, "windows": win}


# ---- HTTP（只有这里真联网；测试把 http_get 换成假函数） ----
def _http_get(url: str, headers: dict, timeout_s: float = 30.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=dict(headers), method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as r:   # noqa: S310 - 各家固定地址
        return int(r.status), r.read().decode("utf-8", "replace")


def _fetch_json(get, url: str, headers: dict, timeout_s: float) -> dict:
    try:
        status, text = get(url, headers, timeout_s)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise _Bad("http_unauthorized", kind="bad_key", status=e.code) from None
        raise _Bad("http_status", status=e.code) from None
    try:
        data = json.loads(text)
    except ValueError:
        raise _Bad("not_json") from None
    if not isinstance(data, dict):
        raise _Bad("not_object")
    return data


def _why_code(e: Exception) -> str:
    """网络报错的编号：超时、连不上，还是别的（别的就把原文带回去）。"""
    s = str(e).replace("\n", " ")[:120]
    if "timed out" in s or "timeout" in s.lower():
        return "net_timeout"
    if "refused" in s or "unreachable" in s or "getaddrinfo" in s:
        return "net_refused"
    return "net_other"


def _why_msg(e: Exception) -> str:
    """网络报错的原文：只留一句短的，给用户看。"""
    s = str(e).replace("\n", " ")[:120]
    return s or e.__class__.__name__


def fetch(adapter: str, key: str | None, custom: dict | None = None,
          timeout_s: float = 30.0, http_get=None) -> dict:
    """查一家。http_get 可注入（测试用假返回，不联网）。"""
    get = http_get or _http_get
    if adapter not in ADAPTERS:
        return _fail("unknown_adapter", adapter=adapter)
    cfg = custom if isinstance(custom, dict) else {}
    if adapter == "custom":
        url = str(cfg.get("url") or "").strip()
        if not url:
            return _fail("custom_no_url")
        auth = str(cfg.get("auth") or "none")
        headers: dict = {}
        if auth == "bearer" or auth == "raw":
            if not key:
                return _fail("no_key", kind="no_key")
            headers["Authorization"] = ("Bearer " + key) if auth == "bearer" else key
        def parse(data):
            return _custom(data, cfg)
    else:
        if not key:
            return _fail("no_key", kind="no_key")
        if adapter == "kimi_code":
            url, headers, parse = KIMI_URL, {"Authorization": "Bearer " + key}, _kimi
        elif adapter == "glm_coding_plan":
            url, headers, parse = GLM_URL, {"Authorization": key}, _glm        # 智谱不加 Bearer
        else:
            url, headers, parse = MINIMAX_URL, {"Authorization": "Bearer " + key}, _minimax
    try:
        return parse(_fetch_json(get, url, headers, timeout_s))
    except _Bad as b:
        return _fail(b.code, kind=b.kind, **b.vars)
    except (OSError, UnicodeError) as e:      # 超时 / 连不上都算网络问题（key 在请求头里，不会进异常文本）
        return _fail(_why_code(e), kind="network", msg=_why_msg(e))


# ---- 工位这头：选适配器、取 key、去重、后台查 ----
def suggest_adapter(base_url: str) -> str:
    """按接口地址主机名建议适配器；认不出的默认 custom。"""
    try:
        host = (urllib.parse.urlparse(str(base_url or "")).hostname or "").lower()
    except ValueError:
        host = ""
    for h, a in HOST_ADAPTERS.items():
        if host == h or host.endswith("." + h):
            return a
    return "custom"


def station_adapter(st: dict) -> str:
    """工位 quota.adapter 优先；没填就按 base_url 建议。"""
    a = str(((st.get("quota") or {}).get("adapter")) or "")
    if a in ADAPTERS:
        return a
    return suggest_adapter(((st.get("pi") or {}).get("base_url")) or "")


def station_key(st: dict) -> str | None:
    """这个工位的 API key（只从 data/secrets.json 来）。只用来发请求，不进任何返回值。"""
    sid = str((st or {}).get("id") or "")
    return config.get_secret(sid) or None


def _custom_sig(custom) -> str:
    """自定义查询配置的稳定串。没填和空串算同一份，免得同一把 key 被拆成两个账户。"""
    cfg = custom if isinstance(custom, dict) else {}
    return "\x1f".join(str(cfg.get(k) or "").strip() for k in _CUSTOM_FIELDS)


def _account_id(adapter: str, key: str | None, custom) -> str:
    """额度账户。key 只进哈希，哈希进 kv 的键，key 原文不进键也不进值。"""
    raw = "%s\0%s\0%s" % (adapter, key or "", _custom_sig(custom))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def account_id(st: dict) -> str:
    """这个工位所属的额度账户。"""
    q = (st or {}).get("quota") or {}
    return _account_id(station_adapter(st or {}), station_key(st or {}), q.get("custom"))


def acct_key(st: dict) -> str:
    """余量在 kv 里的键：quota:acct:<哈希>。"""
    return "quota:acct:" + account_id(st)


def _newest_legacy(store, aid: str) -> dict | None:
    """老版本按工位存的结果。账户记录还没有时，取共用工位里最新的一份顺过来，升级后第一次打开就有数。"""
    best = None
    best_ts = ""
    for s2 in config.stations():
        if account_id(s2) != aid:
            continue
        old = store.kv_get("quota:" + str(s2.get("id") or ""))
        if not isinstance(old, dict):
            continue
        ts = str(old.get("fetched") or "")
        if best is None or ts > best_ts:
            best, best_ts = dict(old), ts
    return best


def read(store, st: dict | None):
    """工位 → 额度账户 → 结果。没有账户记录时，把共用工位里最新的老记录顺过来。"""
    if store is None or not isinstance(st, dict) or not st.get("id"):
        return None
    key = acct_key(st)
    got = store.kv_get(key)
    if isinstance(got, dict):
        return got
    legacy = _newest_legacy(store, account_id(st))
    if legacy is None:
        return None
    again = store.kv_get(key)
    if isinstance(again, dict):
        return again
    try:
        store.kv_set(key, legacy)
    except Exception:  # noqa: BLE001 - 顺不过去也先把数给用户看
        return legacy
    return legacy


def peers(st: dict) -> list[str]:
    """和这只猫共用一份额度的其它工位。没有 key 的不算共用（说「共用一把 key」会是假的）。"""
    if not st or st.get("client") != "pi" or not station_key(st):
        return []
    aid = account_id(st)
    sid = str(st.get("id") or "")
    names = []
    for s2 in config.stations():
        if s2.get("client") != "pi":
            continue
        other = str(s2.get("id") or "")
        if not other or other == sid or not station_key(s2):
            continue
        if account_id(s2) == aid:
            names.append(other)
    names.sort()
    return names


def _dedup_fetch(adapter: str, key: str | None, custom: dict | None, timeout_s: float, http_get=None) -> dict:
    """同一份额度 30 秒内只查一次。key 只进哈希，不进结果。"""
    k = _account_id(adapter, key, custom)
    lk = _dedup_locks.setdefault(k, threading.Lock())
    with lk:
        hit = _dedup_cache.get(k)
        if hit is not None and time.monotonic() - hit[0] < _DEDUP_TTL:
            return dict(hit[1])
        r = fetch(adapter, key, custom, timeout_s, http_get)
        _dedup_cache[k] = (time.monotonic(), r)
        return dict(r)


def check_station(st: dict, store=None, timeout_s: float = 30.0, http_get=None) -> dict:
    """查这个工位所属额度账户的余量，结果存 kv（失败也存，顺便当节流时间戳）。"""
    adapter = station_adapter(st)
    custom = (st.get("quota") or {}).get("custom")
    out = dict(_dedup_fetch(adapter, station_key(st), custom, timeout_s, http_get))
    out["adapter"] = adapter
    out["fetched"] = now_iso()
    if store is not None:
        try:
            store.kv_set(acct_key(st), out)
        except Exception:  # noqa: BLE001 - 存不进去别影响把结果给用户
            pass
    return out


def _mins_since(iso) -> float:
    if not iso:
        return 1e9
    try:
        return (_dt.datetime.now().astimezone() - _dt.datetime.fromisoformat(str(iso))).total_seconds() / 60
    except (TypeError, ValueError):
        return 1e9


def after_run(store, station_id: str) -> threading.Thread | None:
    """工位设了「每轮跑完查一次」：起线程去查，不阻塞收尾。返回起的线程（不用查 → None）。"""
    st = config.station(str(station_id or ""))
    if not st or st.get("client") != "pi" or (st.get("quota") or {}).get("mode") != "after_run":
        return None
    return spawn(st, store)


def due_stations(store) -> list[dict]:
    """看门狗用：到点该查的额度账户。间隔取共用工位里最短的，每个账户只回一个工位。"""
    groups: dict[str, list[tuple[int, dict]]] = {}
    with _busy_lock:
        busy = set(_busy)
    for st in config.stations():
        q = st.get("quota") or {}
        if q.get("mode") != "interval" or not st.get("enabled", True) or st.get("client") != "pi":
            continue
        try:
            interval_min = max(1, int(q.get("interval_min") or 30))
        except (TypeError, ValueError):
            interval_min = 30
        groups.setdefault(account_id(st), []).append((interval_min, st))
    out = []
    for aid, items in groups.items():
        if aid in busy:
            continue
        items.sort(key=lambda it: (it[0], str(it[1].get("id") or "")))
        shortest, rep = items[0]
        last = (read(store, rep) or {}).get("fetched")
        if last and _mins_since(last) < shortest:
            continue
        out.append(rep)
    return out


def spawn(st: dict, store) -> threading.Thread | None:
    """起后台线程查这个额度账户；同一个账户同时只起一条。"""
    aid = account_id(st)
    with _busy_lock:
        if aid in _busy:
            return None
        _busy.add(aid)
    t = threading.Thread(target=_bg_check, args=(st, store, aid), name="boxbox-quota", daemon=True)
    t.start()
    return t


def _bg_check(st: dict, store, aid: str) -> None:
    try:
        check_station(st, store)
    except Exception as e:  # noqa: BLE001 - 查余量坏了不能带崩核心
        try:
            if store is not None:
                store.kv_set("quota:acct:" + aid, {"ok": False, "error_kind": "changed",
                                                   "error_code": "check_failed", "error_vars": {"msg": str(e)[:120]},
                                                   "fetched": now_iso()})
        except Exception:  # noqa: BLE001
            pass
    finally:
        with _busy_lock:
            _busy.discard(aid)
