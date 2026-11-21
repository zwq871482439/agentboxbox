"""帮手能力的开关、来源许可和近 30 天实测。只读设置和任务库。"""
from __future__ import annotations

import datetime as _dt
import json

from . import config, efficiency, i18n

CAPS = [
    {"id": "ponytail", "setting": "ponytail", "kind": "choice", "choices": ["off", "lite", "full"],
     "applies": "code", "licenses": ["Ponytail"], "idea": ""},
    {"id": "search_tools", "setting": "search_tools", "kind": "bool", "choices": [False, True],
     "applies": "any", "licenses": ["ripgrep", "fd"], "idea": ""},
    {"id": "repo_map", "setting": "repo_map", "kind": "bool", "choices": [False, True],
     "applies": "code", "licenses": [], "idea": "https://aider.chat/docs/repomap.html"},
    {"id": "member_feedback", "setting": "member_feedback", "kind": "bool", "choices": [False, True],
     "applies": "any", "licenses": [], "idea": ""},
]

ALWAYS = [
    {"id": "git_no_editor", "idea": ""},
    {"id": "command_guard", "idea": "https://github.com/All-Hands-AI/OpenHands"},
]


def report(store, lang: str) -> dict:
    settings = config.settings()
    measured = _measure(store)
    return {
        "caps": [_row(cap, settings, measured.get(cap["id"]), lang) for cap in CAPS],
        "always": [_row(cap, settings, None, lang) for cap in ALWAYS],
    }


def _row(cap: dict, settings: dict, measured: dict | None, lang: str) -> dict:
    cid = cap["id"]
    value = True if cid in {c["id"] for c in ALWAYS} else settings.get(cap["setting"], False)
    return {
        "id": cid,
        "setting": cap.get("setting"),
        "kind": cap.get("kind", "bool"),
        "applies": cap.get("applies", "any"),
        "name": i18n.t("cap.%s.name" % cid, lang),
        "description": i18n.t("cap.%s.desc" % cid, lang),
        "cost": i18n.t("cap.%s.cost" % cid, lang),
        "value": value,
        "choices": cap.get("choices", []),
        "licenses": _licenses(cap.get("licenses", [])),
        "idea": cap.get("idea", ""),
        "measured": measured,
    }


def _licenses(names: list[str]) -> list[dict]:
    """只读打包文件的目录节；全文节里同名标题不是目录条目。"""
    found = {}
    try:
        with (config.BUNDLE / "THIRD_PARTY_LICENSES.txt").open(encoding="utf-8") as f:
            in_catalog = False
            for line in f:
                if line.startswith("== 目录"):
                    in_catalog = True
                elif in_catalog and line.startswith("==="):
                    break
                elif in_catalog and line.startswith("- "):
                    parts = line[2:].rstrip().split(" — ", 2)
                    if len(parts) == 3 and " " in parts[0]:
                        name, version = parts[0].rsplit(" ", 1)
                        found[name] = {"name": name, "version": version, "license": parts[1]}
    except OSError:
        pass
    return [found.get(name, {"name": name, "version": "", "license": ""}) for name in names]


def _measure(store) -> dict:
    now = _dt.datetime.now().astimezone().replace(microsecond=0)
    since = now - _dt.timedelta(days=30)
    since_iso = since.isoformat()
    with store.lock:
        tasks = [dict(r) for r in store.db.execute("SELECT * FROM tasks WHERE created_at>=?", (since_iso,)).fetchall()]
    groups = {cap["id"]: {_key(v): [] for v in cap["choices"]} for cap in CAPS}
    events = efficiency._event_times(store, since_iso)
    for task in tasks:
        try:
            card = json.loads(task.get("card_json") or "{}")
        except (TypeError, ValueError):
            continue
        for cap in CAPS:
            if cap["setting"] not in card:
                continue
            value = card[cap["setting"]]
            value = bool(value) if cap["kind"] == "bool" else str(value)
            key = _key(value)
            if key not in groups[cap["id"]]:
                continue
            timing = efficiency._timing(store, task["id"], task, events)
            groups[cap["id"]][key].append((timing.get("work_s"), int(task.get("round") or 1)))
    return {
        cid: {
            key: None if len(rows) < 3 else {
                "cards": len(rows),
                "work_s": efficiency._median([work for work, _ in rows if work is not None]),
                "rounds": efficiency._median([rnd for _, rnd in rows]),
            }
            for key, rows in by_value.items()
        }
        for cid, by_value in groups.items()
    }


def _key(value) -> str:
    return "true" if value is True else "false" if value is False else str(value)
