"""Configuration: data/settings.json, data/stations.json.

Everything the core writes lives under DATA (default <repo>/data, override BOXBOX_DATA).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import threading
import time

FROZEN = bool(getattr(sys, "frozen", False))                                   # PyInstaller single-file exe (4.5)
BUNDLE = pathlib.Path(getattr(sys, "_MEIPASS", "")) if FROZEN else pathlib.Path(__file__).resolve().parent.parent
ROOT = pathlib.Path(sys.executable).resolve().parent if FROZEN else BUNDLE     # data/ lives next to the exe
DATA = pathlib.Path(os.environ.get("BOXBOX_DATA") or ROOT / "data")
# 临时文件统一放程序目录 tmp\：每张卡一个子目录。没有卡在跑时随时能删（data\ 不能随便删）。
TMP = pathlib.Path(os.environ.get("BOXBOX_TMP") or ROOT / "tmp")
TASK_ID_RE = r"^\d{8}-\d{3}$"

# 固定 7 个工位：首领占 leader，打工猫按 A→F 占位置。工位满了就是 6 只打工猫。
LEADER_SLOT = "leader"
SLOTS = ("A", "B", "C", "D", "E", "F")


def project_dir() -> str | None:
    """Where client-side MCP entries are written (Cursor's .cursor/mcp.json). Dev: the repo; exe: the user's choice via
    BOXBOX_PROJECT, else None -> connectors fall back to each client's global config."""
    return os.environ.get("BOXBOX_PROJECT") or (None if FROZEN else str(ROOT))

SETTINGS_DEFAULTS = {
    "core_port": 8878,            # v2 core dev port
    "ack_timeout_s": 30,          # delivery receipt window (launcher-level, no model call)
    "heartbeat_s": 15,            # watchdog poll interval
    "network_retry_s": 120,       # 等接口的排队卡隔多少秒再探一次工位接口，通了自动开工
    "wake_min": 30,               # 首领有待办却多少分钟没来调 get_todo → 提醒你叫它（唯一的提醒阈值）
    "skipped_member": False,     # onboard v0.2 §3 步骤 6：用户逃了「先只要首领」
    # 办公室昼夜四个时间点（assets/design/office-daynight/spec.md §3）：清晨 / 白天 / 傍晚 / 夜晚各从几点开始
    "office_theme_times": {"dawn": "06:30", "day": "07:00", "dusk": "18:00", "night": "18:30"},
    "scene_bubbles": True,      # 办公室场景：首领冒不冒庆祝 / 复盘的邀请气泡（场景本身照演）
    "onboard": {},              # 上岗进度（§5）：{"step": 步骤名, "played": [播过的动画], "draft": 填到一半的表单}
    "member_feedback": False,   # 首领验收时给的一句约束记进打工猫的说明（默认关）
    "member_feedback_max_chars": 800,   # 那段说明最多多少字，超了挤掉最旧的
    "tmp_keep_days": 1,        # 临时文件（tmp\ 里每张卡一个子目录）留几天就清掉；在跑的卡不动
    "tray_notify": True,       # 托盘模式下卡交回 / 出问题时弹系统通知（首领闲着，靠这个叫用户去说话）
    "ui_lang": "",             # 界面语言：zh / en；空 = 没选过，核心第一次启动按系统语言定下来
}


# 设置里只认这些键：老版本留下的键读的时候忽略、存的时候丢掉，不认的键不会把核心带崩
SETTINGS_KEYS = frozenset(SETTINGS_DEFAULTS) | {"trigger"}

_WRITE_LOCK = threading.RLock()          # data/*.json 的读和写共用一把锁


def _read_json(path: pathlib.Path, default):
    # Windows 上文件正被另一个线程开着时 os.replace 会报「拒绝访问」；读和写都走这把锁就不会撞上
    with _WRITE_LOCK:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default


def _replace(tmp: pathlib.Path, path: pathlib.Path) -> None:
    for i in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:              # 还有别的进程开着这个文件：等一下再试
            if i == 19:
                raise
            time.sleep(0.02)


def _write_json(path: pathlib.Path, obj) -> None:
    with _WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        # tmp 文件名带线程 id：两个请求同时写同一个文件时（上岗流程会连着存进度）不会互相抢同一个 .tmp
        tmp = path.with_name("%s.%d.tmp" % (path.name, threading.get_ident()))
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        _replace(tmp, path)


def settings() -> dict:
    s = dict(SETTINGS_DEFAULTS)
    raw = _read_json(DATA / "settings.json", {}) or {}
    if isinstance(raw, dict):
        s.update({k: v for k, v in raw.items() if k in SETTINGS_KEYS})
    return s


def save_settings(s: dict) -> None:
    out = {k: v for k, v in (s or {}).items() if k in SETTINGS_KEYS}
    _write_json(DATA / "settings.json", out)
    from . import i18n  # 局部导入：i18n 也引 config，模块层会循环
    i18n.refresh()              # 语言可能改了：缓存里那份旧的丢掉


def _default_stations() -> dict:
    """First start: no stations at all -> the home page sends the user to Onboard (docs/onboard-v0.2.md §0 B1).
    A seeded leader used to live here; it became a ghost member as soon as the user registered a real leader."""
    return {"version": 2, "stations": []}


def stations() -> list[dict]:
    p = DATA / "stations.json"
    doc = _read_json(p, None)
    if doc is None:
        doc = _default_stations()
        _write_json(p, doc)
    items = list(doc.get("stations", []))
    if fill_slots(items):              # 老数据没 slot 的按现有顺序补上，存一次（已有的猫不挪）
        save_stations(items)
    return items


def save_stations(items: list[dict]) -> None:
    items = list(items)
    fill_slots(items)
    _write_json(DATA / "stations.json", {"version": 2, "stations": items})


def next_slot(items: list[dict], ignore_id: str | None = None) -> str | None:
    """下一个空位（A→F 里第一个没人用的）；全占满了返回 None。"""
    used = {str(s.get("slot")) for s in items if s.get("id") != ignore_id and s.get("role") != "leader"}
    return next((x for x in SLOTS if x not in used), None)


def fill_slots(items: list[dict]) -> bool:
    """给工位补 slot：首领 leader，打工猫占空位。已经有位置的猫不动。返回有没有改过。"""
    used: set[str] = set()
    changed = False
    for s in items:
        if s.get("role") == "leader":
            if s.get("slot") != LEADER_SLOT:
                s["slot"] = LEADER_SLOT
                changed = True
            continue
        slot = str(s.get("slot") or "")
        if slot in SLOTS and slot not in used:
            used.add(slot)
            continue
        free = next((x for x in SLOTS if x not in used), None)
        if free is None:
            continue                     # 超过 6 只的老数据：不硬塞，留着原样
        if slot != free:
            s["slot"] = free
            changed = True
        used.add(free)
    return changed


def onboard_progress() -> dict:
    """上岗进度（§5）：播到哪一步、哪些动画播过、填了一半的表单。不含 API key。"""
    p = settings().get("onboard")
    p = p if isinstance(p, dict) else {}
    played = [str(x) for x in (p.get("played") or [])] if isinstance(p.get("played"), list) else []
    draft = p.get("draft") if isinstance(p.get("draft"), dict) else {}
    return {"step": str(p.get("step") or ""), "played": played, "draft": dict(draft)}


def pending_open_station() -> str:
    """刚招、还在开箱的工位 id（第 6 条）。

    上岗流程招打工猫时，工位是「测试连接」那一刻就登记好的，可办公室的送箱动画（快递猫送箱 → 开箱）
    还没演完。这时办公室先别画这只猫，等开箱演完再让它出来。没有这样的工位就返回空串。"""
    p = onboard_progress()
    step = str(p.get("step") or "")
    if step not in ("member", "member_access", "box_in2"):
        return ""
    if "box_open2" in [str(x) for x in (p.get("played") or [])]:
        return ""                       # 开箱演完了：猫可以出来了
    return str((p.get("draft") or {}).get("member_name") or "")


def save_onboard_progress(step=None, played=None, draft=None) -> dict:
    """合并更新：step 换掉，played 并集（去重、保序），draft 按字段合并。"""
    with _WRITE_LOCK:                      # 上岗流程会连着存好几步，合并不能被别的写覆盖掉
        p = onboard_progress()
        if isinstance(step, str) and step:
            p["step"] = step
        if isinstance(played, list):
            p["played"] = list(dict.fromkeys(p["played"] + [str(x) for x in played]))
        if isinstance(draft, dict):
            p["draft"] = {**p["draft"], **draft}
        s = settings()
        s["onboard"] = p
        save_settings(s)
    return p


# ---- secrets (Onboard v0.2 §7): API keys live in data/secrets.json, local only, never echoed by any /api ----


def secrets() -> dict:
    """{"stations": {"<id>": {"api_key": "..."}}}; missing file -> empty."""
    doc = _read_json(DATA / "secrets.json", None) or {}
    if not isinstance(doc.get("stations"), dict):
        doc["stations"] = {}
    return doc


def get_secret(station_id: str) -> str | None:
    v = (secrets()["stations"].get(str(station_id)) or {}).get("api_key")
    return str(v) if v else None


def set_secret(station_id: str, api_key: str | None) -> None:
    """Empty / None removes the entry. Writes the one-line README next to the file on first use."""
    with _WRITE_LOCK:
        doc = secrets()
        if api_key:
            doc["stations"][str(station_id)] = {"api_key": str(api_key)}
        else:
            doc["stations"].pop(str(station_id), None)
        _write_json(DATA / "secrets.json", doc)
        note = DATA / "README-secrets.txt"
        if not note.exists():
            try:
                from . import i18n  # 局部导入：i18n 也引 config，模块层会循环
                note.write_text(i18n.t("app.secrets_note", i18n.lang()), encoding="utf-8")
            except OSError:
                pass


def all_secret_values() -> list[str]:
    """Every stored key, for log masking."""
    return [str(v.get("api_key")) for v in secrets()["stations"].values() if v.get("api_key")]


def station(sid: str) -> dict | None:
    for s in stations():
        if s.get("id") == sid:
            return s
    return None


def leader_id() -> str | None:
    for s in stations():
        if s.get("role") == "leader":
            return s["id"]
    return None


def ensure_dirs() -> None:
    for d in ("tasks", "templates", "sessions", "channels", "logs"):
        (DATA / d).mkdir(parents=True, exist_ok=True)
    try:                                   # 临时文件目录（程序目录 tmp\，和 data\ 并列）
        pathlib.Path(os.environ.get("BOXBOX_TMP") or TMP).mkdir(parents=True, exist_ok=True)
    except OSError:                        # 目录建不了（比如没权限）不该挡住核心启动
        pass
