"""Token ledger: only measured usage is recorded (§8.3/8.4). No estimates, no 'saved' math.

每个工位带 cost_est（实测 token × models.dev 公开单价）和 quota（套餐余量查询结果），
都是在 /api/tokens 出口现算，不进账本。"""
from __future__ import annotations

from . import config, i18n

PRECISE_SOURCES = {"pi_json", "pi_session", "zcode_usage", "claude_json", "codex_json"}


def cost_for(station_id: str, tok: dict) -> float | None:
    st = config.station(station_id) or {}
    c = st.get("cost") or {}
    if not c:
        return None
    try:
        def per_m(k: str) -> float:
            return float(c.get(k) or 0) / 1_000_000.0
        return round((tok.get("in") or 0) * per_m("in") + (tok.get("out") or 0) * per_m("out")
                     + (tok.get("cr") or 0) * per_m("cache_read") + (tok.get("cw") or 0) * per_m("cache_write"), 6)
    except (TypeError, ValueError):
        return None


def cost_est(station: dict, row: dict) -> float | None:
    """估算花费（美元）：实测 token × models.dev 单价（每百万 token 美元）。
    优先 pi 块里的 provider_id/model_id；没有就按 base_url 主机名 + model 在清单里找；找不到 → None。"""
    from . import pi_config, providers
    pi = (station or {}).get("pi") or {}
    if not pi:
        return None
    cost = None
    if pi.get("provider_id") and pi.get("model_id"):
        cost = providers.price(pi["provider_id"], pi["model_id"])
    if cost is None:
        host = pi_config.host_of(pi)
        found = providers.match(host, pi.get("model")) if host and pi.get("model") else None
        if found:
            cost = providers.price(found[0], found[1])
    if cost is None:
        return None
    try:
        def per(k: str) -> float:
            return float(cost.get(k) or 0) / 1e6
        return round((row.get("tok_in") or 0) * per("input") + (row.get("tok_out") or 0) * per("output")
                     + (row.get("tok_cr") or 0) * per("cache_read") + (row.get("tok_cw") or 0) * per("cache_write"), 6)
    except (TypeError, ValueError):
        return None


def record(store, run: dict, tok: dict) -> bool:
    if tok.get("source") not in PRECISE_SOURCES:
        return False
    store.ledger_add(run["run_id"], run["station"], run["task_id"], tok, tok["source"], cost_for(run["station"], tok))
    return True


def summary(store, days: int = 7, lang: str | None = None) -> dict:
    import datetime
    since = (datetime.datetime.now().astimezone() - datetime.timedelta(days=days)).replace(microsecond=0).isoformat()
    rows = store.tokens_summary(since)
    counted = {r["station"] for r in rows}
    stations = {s["id"]: s for s in config.stations()}
    for r in rows:
        st = stations.get(r["station"])
        r["cost_est"] = cost_est(st or {}, r)
        r["quota"] = store.kv_get("quota:" + r["station"])
    # 还没跑过活但查过余量的 Pi 工位也列出来（用量区看得到余量）
    for sid, st in sorted(stations.items()):
        if sid in counted or st.get("client") != "pi":
            continue
        q = store.kv_get("quota:" + sid)
        if not q:
            continue
        rows.append({"station": sid, "runs": 0, "tok_in": 0, "tok_out": 0, "tok_cr": 0, "tok_cw": 0,
                     "cost": None, "cost_est": None, "quota": q})
    # 额度按服务商算一份：同一服务商（同一把 key）的几个工位，余量只显示一份，其余标明跟谁共用
    by_group: dict[tuple, list[dict]] = {}
    for r in rows:
        g = _quota_group(stations.get(r["station"]) or {})
        if g:
            by_group.setdefault(g, []).append(r)
    for grp in by_group.values():
        if len(grp) < 2:
            continue
        grp.sort(key=lambda r: str(r["station"]))
        owner = next((r for r in grp if r.get("quota")), None)
        if owner is None:
            continue
        for r in grp:
            if r is owner:
                continue
            r["quota"] = None
            r["quota_peer"] = owner["station"]
    not_counted = [s["id"] for s in config.stations()
                   if s.get("role") == "member" and s["id"] not in counted and s.get("client") not in ("pi", "zcode", "claude-code", "codex")]
    note = i18n.t("tokens.note", lang)
    return {"since": since, "stations": rows, "not_counted": not_counted, "note": note}


def _quota_group(st: dict) -> tuple | None:
    """能共用一份额度的工位归成一组：(服务商, key)；不是 Pi 工位或设不出服务商 → None（不归组）。"""
    if not st or st.get("client") != "pi":
        return None
    from . import providers
    p = providers.station_provider(st)
    if not p:
        return None
    return (p, config.get_secret(str(st.get("id") or "")) or "")
