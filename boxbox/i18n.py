# -*- coding: utf-8 -*-
"""给用户看的文字：中英两张表，键一样，值按语言分。

核心生成的文字（看板 / 工牌的状态词、排队那句、全站提醒、自检项、托盘菜单和通知、
首领那边的规则和简报）都从这里取：t(key, lang, **vars)，{名} 会被替换掉。
页面（前端）有自己的一份词典（boxbox/static/i18n-*.js），两边各写各的，键一一对应。

当前语言：设置里的 ui_lang（前端切语言时 POST /api/settings 写进来），
没设过就按系统语言定（核心第一次启动时定下来写进设置）。
表按模块分文件放在 boxbox/i18n_data/ 下，每个不超过 800 行。
"""
from __future__ import annotations

import contextlib
import locale
import threading

from . import config

LANGS = ("zh", "en")

_MODULES = ()


def _modules():
    """各模块的词表模块：按模块分文件，加新的就在这个列表里加一行。"""
    global _MODULES
    if not _MODULES:
        from .i18n_data import alerts, app, board, cards, cli, connectors, doctor, events, http, leader, mcp, office, quota, stall, tray
        _MODULES = (board, alerts, app, cards, cli, connectors, doctor, events, http, leader, mcp, office, quota, stall, tray)
    return _MODULES


_TABLES: dict[str, dict[str, str]] = {}


def _tables() -> dict[str, dict[str, str]]:
    """两张表装好了：zh / en。词表模块只给纯字典，不引别的模块（免得循环 import）。"""
    if not _TABLES:
        for mod in _modules():
            _TABLES.setdefault("zh", {}).update(mod.ZH)
            _TABLES.setdefault("en", {}).update(mod.EN)
    return _TABLES


def _windows_ui_langid() -> int | None:
    """Windows 的界面语言号（简中 2052、繁中 1028）；不是 Windows 或取不到给 None。"""
    try:
        import ctypes
        return int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
    except (AttributeError, OSError, ValueError):
        return None


def _is_chinese_locale(name: str) -> bool:
    # Windows 上 getlocale() 给的是「Chinese (Simplified)_China」这种全名，不是 zh_CN
    n = (name or "").strip().lower()
    return n.startswith("zh") or n.startswith("chinese")


def detect_lang() -> str:
    """系统语言：中文系统给 zh，其余给 en。Windows 先看界面语言，再看区域设置。"""
    langid = _windows_ui_langid()
    if langid:
        return "zh" if (langid & 0x3FF) == 0x04 else "en"   # 0x04 = LANG_CHINESE，简繁都算
    loc = ""
    try:
        loc = locale.getlocale()[0] or ""
    except (ValueError, TypeError):  # noqa: BLE001 - locale 在有些系统上会抛
        loc = ""
    if not loc:
        try:
            loc = locale.getdefaultlocale()[0] or ""
        except (ValueError, TypeError):  # noqa: BLE001
            loc = ""
    return "zh" if _is_chinese_locale(loc) else "en"


def current_lang() -> str:
    """设置里的 ui_lang；没设过就按系统语言定。"""
    v = str(config.settings().get("ui_lang") or "").strip().lower()
    return v if v in LANGS else detect_lang()


_cache: dict[str, str] = {}
_local = threading.local()


def _cached_lang() -> str:
    """带缓存的当前语言：设置改了要调 refresh()（不然一整个进程都用旧语言）。
    缓存跟着数据目录走：换了目录（测试里会换）就重新读一次。"""
    v = _cache.get("lang")
    key = str(config.DATA)
    if v is None or _cache.get("key") != key:
        v = current_lang()
        _cache["lang"] = v
        _cache["key"] = key
    return v


def lang() -> str:
    """当前语言（设置里的 ui_lang，没设过按系统语言定）。"""
    ov = getattr(_local, "lang", "")
    if ov:
        return ov
    return _cached_lang()


@contextlib.contextmanager
def override(lang: str | None):
    """这一次请求里用哪种语言（页面上问的就是它）：只影响这个线程里的取词。"""
    prev = getattr(_local, "lang", "")
    _local.lang = lang if lang in LANGS else ""
    try:
        yield
    finally:
        _local.lang = prev


def refresh() -> None:
    """设置里的语言改了之后清缓存。"""
    _cache.clear()
    _cache["key"] = str(config.DATA)


def t(key: str, lang: str | None = None, /, **vars) -> str:
    """取一条词条。英文缺了就回落中文；两边都缺就返回键名（露出来比静默出错好）。
    key 和 lang 只按位置传，这样 {key} / {lang} 这类占位名也能用。"""
    lg = lang if lang in LANGS else _cached_lang()
    v = _tables().get(lg, {}).get(key)
    if not isinstance(v, str):
        v = _tables()["zh"].get(key)
        if not isinstance(v, str):
            return key
    for name, val in vars.items():
        v = v.replace("{" + name + "}", str(val))
    return v
