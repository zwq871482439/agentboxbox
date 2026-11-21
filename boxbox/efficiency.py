"""效率面板要的数：近几天按卡、按猫汇总。只读库，不改运行、不重扫日志。

模型时间和命令时间在收工时已经记进 runs.split_json。老运行没有这列，对应的格子是空。
命中率 = 读缓存 / (入 + 读缓存)，和办公室抽屉同一把尺子。
有公开单价的按单价估一个钱（tokens.cost_est）；单价全是 0 的套餐只报用量。

每张卡还分三段：等开工（派活 → 第一次开工）、干活（开工 → 交回）、等验收（交回 → 确认）。
可以按首领（dispatcher）和批次（goal）筛，筛了就列全部匹配的卡，不截前 10。
"""
from __future__ import annotations

import datetime as _dt
import json

from . import config, tokens

_PROBE = {"tok_in": 1_000_000, "tok_out": 1_000_000, "tok_cr": 1_000_000, "tok_cw": 1_000_000}


def report(store, days=7, dispatcher=None, goal=None) -> dict:
    days = _days(days)
    now = _dt.datetime.now().astimezone().replace(microsecond=0)
    since = now - _dt.timedelta(days=days)
    since_iso = since.isoformat()
    runs = store.runs_overlapping(since_iso)
    ledgers: dict[str, list] = {}
    for row in store.ledger_for_runs([r["run_id"] for r in runs if r.get("run_id")]):
        ledgers.setdefault(row["run_id"], []).append(row)
    titles = {t["id"]: t for t in store.tasks_brief([r.get("task_id") for r in runs])}
    stations = {s["id"]: s for s in config.stations()}
    finished = [r for r in runs if _in_window(r, since)]
    cats: dict[str, dict] = {}
    cards: dict[str, dict] = {}
    split_rows = []
    for run in finished:
        tok = _tokens(run, ledgers.get(run["run_id"]) or [])
        split = _split(run.get("split_json"))
        wall = _wall(run, now)
        sid = str(run.get("station") or "")
        tid = str(run.get("task_id") or "")
        _add(cats, sid, tok, wall, split)
        if tid:
            _add(cards, tid, tok, wall, split)
            cards[tid]["station"] = cards[tid].get("station") or sid
            title = (titles.get(tid) or {}).get("title") or ""
            if title and not cards[tid].get("title"):
                cards[tid]["title"] = title
        if split:
            split_rows.append((split, wall))
    cat_rows = [_finish_group(sid, g, stations.get(sid)) for sid, g in cats.items()]
    cat_rows.sort(key=lambda r: (-r["turns"], -r["usage"], r["station"]))
    card_rows = []
    for tid, g in cards.items():
        row = _finish_group(tid, g, stations.get(g.get("station") or ""))
        row["task_id"] = tid
        row["title"] = g.get("title") or ""
        row["station"] = g.get("station") or ""
        card_rows.append(row)
    card_rows.sort(key=lambda r: (-r["turns"], -r["usage"], r["task_id"]))
    events = _event_times(store, since_iso)
    scope = []
    for row in card_rows:
        tid = row["task_id"]
        t = _task_of(store, tid)
        if dispatcher and str(t.get("dispatcher") or "") != str(dispatcher):
            continue
        card = t.get("card") or {}
        if goal and str(card.get("goal") or "").strip() != str(goal).strip():
            continue
        row.update(_timing(store, tid, t, events))
        row["dispatcher"] = str(t.get("dispatcher") or "")
        row["goal"] = str(card.get("goal") or "")
        scope.append((row, t))
    listed = [r for r, _ in scope]
    if not (dispatcher or goal):
        listed = listed[:10]           # 没筛的时候还是只列花得最多的 10 张
    timing = _timing_summary(scope)
    timing["listed"] = len(listed)
    return {
        "days": days,
        "since": since_iso,
        "busy": _busy(runs, since, now),
        "accept_wait_s": _wait(store.tasks_done_since(since_iso), since),
        "split": _split_sum(split_rows),
        "cats": cat_rows,
        "cards": listed,
        "timing": timing,
        "dispatcher": str(dispatcher or ""),
        "goal": str(goal or ""),
    }


def _task_of(store, task_id: str) -> dict:
    try:
        return store.get_task(task_id) or {}
    except (TypeError, ValueError):
        return {}


def _event_times(store, since_iso: str) -> dict:
    """每张卡「交回等确认」和「确认完成」的最晚时间。事件正文很大，只取时间和种类。"""
    sql = ("SELECT task_id, kind, MAX(ts) ts FROM events WHERE task_id IS NOT NULL AND ts>=? "
           "AND kind IN ('reviewing','done') GROUP BY task_id, kind")
    with store.lock:
        rows = [dict(r) for r in store.db.execute(sql, (since_iso,)).fetchall()]
    return {(r["task_id"], r["kind"]): r["ts"] for r in rows}


def _timing(store, task_id: str, t: dict, events: dict) -> dict:
    """一张卡的三段时间：等开工、干活、等验收。缺一环就是空，不猜。"""
    starts = sorted(s for s in (_parse(r.get("started")) for r in store.runs_for_task(task_id)) if s)
    first_start = starts[0] if starts else None
    review_raw = events.get((task_id, "reviewing"))
    review_at = _parse(review_raw) or _parse(t.get("delivered_at"))
    done_at = _parse(events.get((task_id, "done"))) or _parse(t.get("done_at"))
    work_start = None
    if review_at is not None:
        earlier = [s for s in starts if s <= review_at]
        work_start = earlier[-1] if earlier else None
    elif first_start is not None:
        work_start = first_start
    return {
        "wait_start_s": _dur(_parse(t.get("created_at")), first_start),
        "work_s": _dur(work_start, review_at),
        # 没交回等确认过就没有「等验收」这回事
        "wait_review_s": _dur(review_at, done_at) if review_raw else None,
        "done": bool(events.get((task_id, "done")) or t.get("done_at")),
        "round": int(t.get("round") or 1),
    }


def _timing_summary(scope: list) -> dict:
    def med(key):
        return _median([r.get(key) for r, _ in scope if r.get(key) is not None])
    finished = [r for r, _ in scope if r.get("done")]
    passed = sum(1 for r in finished if int(r.get("round") or 1) <= 1)
    return {
        "wait_start_s": med("wait_start_s"),
        "work_s": med("work_s"),
        "wait_review_s": med("wait_review_s"),
        "pass_rate": int(round(100.0 * passed / len(finished))) if finished else None,
        "cards": len(scope),
        "finished": len(finished),
    }


def _dur(start, end):
    if start is None or end is None or end < start:
        return None
    return int(round((end - start).total_seconds()))


def _days(days) -> int:
    try:
        n = int(days)
    except (TypeError, ValueError):
        return 7
    if n < 1:
        return 1
    if n > 90:
        return 90
    return n


def _in_window(run: dict, since: _dt.datetime) -> bool:
    end = _parse(run.get("ended"))
    return end is not None and end >= since


def _tokens(run: dict, rows: list) -> tuple[int, int, int, int, int]:
    if rows:
        inn = sum(int(r.get("tok_in") or 0) for r in rows)
        out = sum(int(r.get("tok_out") or 0) for r in rows)
        cr = sum(int(r.get("tok_cr") or 0) for r in rows)
        cw = sum(int(r.get("tok_cw") or 0) for r in rows)
        turns = sum(int(r.get("turns") or 0) for r in rows)
        if turns <= 0:
            turns = _json_turns(run)
        return inn, out, cr, cw, turns
    blob = _loads(run.get("tokens_json")) or {}
    return (int(blob.get("in") or 0), int(blob.get("out") or 0), int(blob.get("cr") or 0),
            int(blob.get("cw") or 0), int(blob.get("turns") or 0))


def _json_turns(run: dict) -> int:
    blob = _loads(run.get("tokens_json")) or {}
    try:
        return int(blob.get("turns") or 0)
    except (TypeError, ValueError):
        return 0


def _split(raw) -> dict | None:
    if not raw:
        return None
    blob = _loads(raw)
    return blob if isinstance(blob, dict) else None


def _loads(raw):
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _wall(run: dict, now: _dt.datetime) -> int:
    start = _parse(run.get("started"))
    end = _parse(run.get("ended")) or now
    if start is None or end < start:
        return 0
    return int(round((end - start).total_seconds()))


def _add(groups: dict, key: str, tok: tuple, wall: int, split: dict | None) -> None:
    g = groups.get(key)
    if g is None:
        g = {"runs": 0, "seconds": 0, "turns": 0, "tools": None, "in": 0, "out": 0, "cr": 0, "cw": 0,
             "model_ms": None, "cmd_ms": None, "wall_measured": 0, "before": [], "title": "", "station": ""}
        groups[key] = g
    g["runs"] += 1
    g["seconds"] += wall
    g["in"] += tok[0]
    g["out"] += tok[1]
    g["cr"] += tok[2]
    g["cw"] += tok[3]
    g["turns"] += tok[4]
    if split and isinstance(split.get("tools"), int):
        g["tools"] = (g["tools"] or 0) + split["tools"]
    if split and split.get("measured") and split.get("model_ms") is not None:
        g["model_ms"] = (g["model_ms"] or 0) + int(split.get("model_ms") or 0)
        g["cmd_ms"] = (g["cmd_ms"] or 0) + int(split.get("cmd_ms") or 0)
        g["wall_measured"] += wall
    if split and isinstance(split.get("turns_before_edit"), int):
        g["before"].append(split["turns_before_edit"])


def _finish_group(key: str, g: dict, station: dict | None) -> dict:
    kind, est = _price(station, g)
    return {
        "station": key,
        "runs": g["runs"],
        "seconds": g["seconds"],
        "turns": g["turns"],
        "tools": g["tools"],
        "tok_in": g["in"],
        "tok_out": g["out"],
        "tok_cr": g["cr"],
        "tok_cw": g["cw"],
        "usage": g["in"] + g["out"] + g["cr"] + g["cw"],
        "hit": _hit(g["in"], g["cr"]),
        "cost_est": est,
        "price": kind,
        "model_s": _sec(g["model_ms"]),
        "cmd_s": _sec(g["cmd_ms"]),
        "turns_before_edit": _median(g["before"]),
    }


def _price(station: dict | None, g: dict) -> tuple[str, float | None]:
    kind = _price_kind(station)
    if kind != "money":
        return kind, None
    est = tokens.cost_est(station or {}, {"tok_in": g["in"], "tok_out": g["out"], "tok_cr": g["cr"], "tok_cw": g["cw"]})
    return kind, est


def _price_kind(station: dict | None) -> str:
    """套餐单价全是 0，估出来也是 0，不能当成「没有价格」，也不能写成花了 0 块。"""
    est = tokens.cost_est(station or {}, _PROBE)
    if est is None:
        return "none"
    if est == 0:
        return "plan"
    return "money"


def _hit(inn: int, cr: int):
    den = inn + cr
    if den <= 0:
        return None
    return _num(round(cr * 1000.0 / den) / 10.0)


def _sec(ms) -> int | float | None:
    if ms is None:
        return None
    return _num(round(int(ms) / 1000.0, 3))


def _num(v):
    f = float(v)
    if f.is_integer():
        return int(f)
    return round(f, 3)


def _median(nums: list) -> int | float | None:
    if not nums:
        return None
    xs = sorted(nums)
    n = len(xs)
    mid = n // 2
    if n % 2:
        return xs[mid]
    return _num((xs[mid - 1] + xs[mid]) / 2.0)


def _split_sum(rows: list) -> dict:
    model_ms = cmd_ms = wall = tests = unedited = 0
    befores = []
    saw = False
    longest = None
    for split, run_wall in rows:
        if isinstance(split.get("turns_before_edit"), int):
            befores.append(split["turns_before_edit"])
        if split.get("edited") is False and "edited" in split:
            unedited += 1
        tests += int(split.get("test_runs") or 0)
        ms = split.get("longest_ms")
        if isinstance(ms, (int, float)) and (longest is None or ms > longest[0]):
            longest = (ms, str(split.get("longest_cmd") or ""))
        if split.get("measured") and split.get("model_ms") is not None:
            saw = True
            model_ms += int(split.get("model_ms") or 0)
            cmd_ms += int(split.get("cmd_ms") or 0)
            wall += int(run_wall or 0)
    model_s = _sec(model_ms) if saw else None
    cmd_s = _sec(cmd_ms) if saw else None
    return {
        "model_s": model_s,
        "cmd_s": cmd_s,
        "model_pct": _pct(model_s, wall) if saw else None,
        "cmd_pct": _pct(cmd_s, wall) if saw else None,
        "wall_s": wall if saw else None,
        "turns_before_edit": _median(befores),
        "unedited": unedited,
        "test_runs": tests,
        "longest_s": _sec(longest[0]) if longest else None,
        "longest_cmd": longest[1] if longest else "",
    }


def _pct(part, whole) -> int | None:
    if part is None or not whole:
        return None
    return int(round(100.0 * float(part) / float(whole)))


def _busy(runs: list, since: _dt.datetime, now: _dt.datetime) -> dict:
    """有活的那段时间里，平均同时几只猫在干。同一只猫叠着两张卡只算一只。"""
    points = []
    seen = set()
    for run in runs:
        start = _parse(run.get("started"))
        if start is None:
            continue
        end = _parse(run.get("ended")) or now
        if end <= since or start >= now or end <= start:
            continue
        a = max(start, since)
        b = min(end, now)
        if b <= a:
            continue
        sid = str(run.get("station") or "")
        seen.add(sid)
        points.append((a, 1, sid))
        points.append((b, -1, sid))
    cats = _member_n() or len(seen)
    if not points:
        return {"avg": None, "cats": cats}
    # 同一时刻先结束再开始，交接的那一瞬间不算两只都在
    points.sort(key=lambda p: (p[0], p[1]))
    active: dict[str, int] = {}
    integral = 0.0
    busy = 0.0
    prev = None
    prev_n = 0
    for t, delta, sid in points:
        if prev is not None and t > prev and prev_n > 0:
            dt = (t - prev).total_seconds()
            integral += prev_n * dt
            busy += dt
        active[sid] = active.get(sid, 0) + delta
        if active[sid] <= 0:
            active.pop(sid, None)
        prev = t
        prev_n = len(active)
    avg = None if busy <= 0 else _num(round(integral / busy, 1))
    return {"avg": avg, "cats": cats}


def _member_n() -> int:
    n = 0
    for st in config.stations():
        if st.get("role") == "member" and st.get("enabled", True) is not False:
            n += 1
    return n


def _wait(tasks: list, since: _dt.datetime):
    waits = []
    for t in tasks:
        done = _parse(t.get("done_at"))
        delivered = _parse(t.get("delivered_at"))
        if done is None or delivered is None or done < since or done < delivered:
            continue
        waits.append((done - delivered).total_seconds())
    return _median(waits)


def _parse(iso) -> _dt.datetime | None:
    if not iso:
        return None
    try:
        then = _dt.datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=_dt.datetime.now().astimezone().tzinfo)
    return then
