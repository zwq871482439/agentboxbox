"""错误分类 / 配额重置时间解析 / 敏感信息打码 / TCP 预检。

从 scripts/_wake-core.ps1 的 Classify / ResetTime / Mask 移植，规则保持一致（照搬正则，大小写不敏感）。
退出码契约：ok=0 busy=10 quota=11 unreachable=12 auth=13 route=14 unknown=1。
"""
from __future__ import annotations

import re
import socket
from datetime import datetime, timedelta

EXIT_CODES = {"ok": 0, "busy": 10, "quota": 11, "unreachable": 12, "auth": 13, "route": 14, "unknown": 1}

_RE_AUTH = re.compile(r"\b401\b|unauthori[sz]ed|invalid.{0,10}(api.?key|token)|authentication.?(error|failed)", re.I)
_RE_BUSY = re.compile(r"\b429\b|\b529\b|rate.?limit|too many requests|concurren|overloaded|server is busy|try again later", re.I)
_RE_QUOTA = re.compile(r"\b403\b|quota|usage limit|insufficient|balance|exceeded your|billing|欠费|余额", re.I)
# 写明是额度/套餐用完的话，哪怕状态码是 429 也是「没额度」不是「忙」：Kimi 周额度用完回的就是
# 429 rate_limit_error + "reached your weekly (7-day) usage limit"，按「忙」说用户会一直等（10 个新用户模拟时撞上）
_RE_QUOTA_WORDS = re.compile(r"quota|usage limit|insufficient (balance|quota|credit)|balance|billing|欠费|余额|额度|用量已", re.I)
# Connection error 是 Node fetch 报网络断的另一种写法；502/503/504 是网关/服务端出错（自重试失败时 Pi 以退出码 0 结束，
# 核心要按「模型接口连不上」处理而不是当成交回），跟 ENOTFOUND 那批同属 unreachable 一档
_RE_UNREACH = re.compile(r"ENOTFOUND|EAI_AGAIN|getaddrinfo|ECONNREFUSED|ECONNRESET|ETIMEDOUT|timed? ?out|fetch failed|"
                         r"socket hang up|network|connect(ion)? error|connection error|\b50[234]\b", re.I)

_RE_RESET_ISO = re.compile(r"reset[^0-9]{0,40}(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:?\d{2})?)", re.I)
_RE_RESET_AFTER = re.compile(r"(?:retry|reset|try again)\w*\s+(?:after|in)\s+(\d+)\s*(s|sec|seconds|m|min|minutes|h|hours)", re.I)
# 中文钟点：「将在 01:54 重置」「01:54 后恢复」→ 记下回来的钟点
_RE_RESET_CLOCK = re.compile(r"(\d{1,2})\s*[:：]\s*(\d{2})\s*(?:后|之后)?\s*(?:重置|恢复|再来|重试|解除)", re.I)
# 英文钟点："resets at 01:54" / "available again at 01:54"
_RE_RESET_CLOCK_EN = re.compile(r"(?:resets?|available|back|retry)\w*\s+(?:again\s+)?(?:at|in)\s+(\d{1,2})\s*[:：]\s*(\d{2})", re.I)
# HTTP 头：Retry-After: 120（秒）/ x-ratelimit-reset: 1730000000（秒数或时间戳）
_RE_RETRY_AFTER = re.compile(r"retry-after\s*[:=]\s*(\d+)", re.I)
_RE_RATELIMIT_RESET = re.compile(r"x-ratelimit-reset\s*[:=]\s*(\d+)", re.I)

_RE_MASK_KV = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)([\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+")
_RE_MASK_TOKEN = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+\S+|figu_\S+|[0-9a-f]{32}\.[A-Za-z0-9]{10,}|eyJ[A-Za-z0-9_\-]{20,}\S*)")


def classify(text: str) -> str:
    """auth > 写明额度用完 > busy > quota > unreachable > unknown；空串 -> unknown。"""
    if not text:
        return "unknown"
    if _RE_AUTH.search(text):
        return "auth"
    if _RE_QUOTA_WORDS.search(text):
        return "quota"
    if _RE_BUSY.search(text):
        return "busy"
    if _RE_QUOTA.search(text):
        return "quota"
    if _RE_UNREACH.search(text):
        return "unreachable"
    return "unknown"


def network_or_server_error(text: str) -> bool:
    """这个报错是不是「模型接口连不上 / 服务端出错」（网络类 + 服务端 5xx）。
    判定跟 classify 的 unreachable 一档是同一套正则（连接被拒、超时、DNS、ECONNRESET、
    fetch failed、Connection error、HTTP 502/503/504）。"""
    return bool(text) and _RE_UNREACH.search(text) is not None


def server_error(text: str) -> bool:
    """服务端自己出错（502 / 503 / 504）：跟「连不上」分开说（歇着的原因不一样）。"""
    return bool(text) and re.search(r"\b50[234]\b", text) is not None


def clock_hint(text: str) -> str | None:
    """错误里写的钟点（「将在 01:54 重置」「01:54 后恢复」「resets at 01:54」）-> 「01:54」；没有 -> None。
    工位歇着的时候要把「几点回来」写给用户看，所以钟点原文要留着。"""
    if not text:
        return None
    for rx in (_RE_RESET_CLOCK, _RE_RESET_CLOCK_EN):
        m = rx.search(text)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
            if hh < 24 and mm < 60:
                return "%02d:%02d" % (hh, mm)
    return None


def retry_after_seconds(text: str) -> int | None:
    """Retry-After / x-ratelimit-reset 里的秒数；没有 -> None。
    Retry-After: 120 → 120；x-ratelimit-reset: 1730000000 这种时间戳不算秒数（返回 None）。"""
    if not text:
        return None
    m = _RE_RETRY_AFTER.search(text)
    if m:
        return int(m.group(1))
    m = _RE_RATELIMIT_RESET.search(text)
    if m:
        n = int(m.group(1))
        return n if n < 10 ** 9 else None      # 十位数 = Unix 时间戳，不是「再等几秒」
    return None


def retry_delay_seconds(text: str) -> int | None:
    """「再等多久」：retry after 30 s / try again in 30 seconds / Retry-After: 120（秒）；没有 -> None。"""
    if not text:
        return None
    m = _RE_RESET_AFTER.search(text)
    if m:
        n = int(m.group(1))
        u = m.group(2).lower()
        return n * 3600 if u.startswith("h") else n * 60 if u.startswith("m") else n
    return retry_after_seconds(text)


def reset_time(text: str, now: datetime | None = None) -> str | None:
    """各种写法 -> 本地时区 ISO 字符串；没有 -> None。

    1) "reset at 2026-10-21T08:00:00Z" 这类 ISO 时间；2) "retry after 30 s|min|h"；
    3) "try again in 30 seconds"；4) 钟点「将在 01:54 重置」→ 今天（过了就明天）的那个钟点；
    5) HTTP 头 Retry-After: 120（秒）、x-ratelimit-reset（秒数）。
    """
    if not text:
        return None
    m = _RE_RESET_ISO.search(text)
    if m:
        raw = m.group(1)
        try:
            iso = raw.replace("Z", "+00:00").replace("z", "+00:00")
            # [+-]DD:DD 或 [+-]DDDD 两种偏移写法都归一成 fromisoformat 能吃的
            iso = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", iso)
            dt = datetime.fromisoformat(iso.replace(" ", "T", 1) if " " in iso[:16] else iso)
            if dt.tzinfo is None:
                dt = dt.astimezone()  # 无偏移按本地时间理解
            return dt.astimezone().isoformat(timespec="seconds")
        except ValueError:
            pass
    m = _RE_RESET_AFTER.search(text)
    if m:
        n = int(m.group(1))
        u = m.group(2).lower()
        sec = n * 3600 if u.startswith("h") else n * 60 if u.startswith("m") else n
        base = now or datetime.now().astimezone()
        return (base + timedelta(seconds=sec)).astimezone().isoformat(timespec="seconds")
    # 钟点：「将在 01:54 重置」→ 今天（已经过了就明天）的那个钟点
    hint = clock_hint(text)
    if hint:
        base = (now or datetime.now().astimezone()).astimezone()
        hh, mm = int(hint[:2]), int(hint[3:])
        dt = base.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if dt <= base:
            dt += timedelta(days=1)
        return dt.isoformat(timespec="seconds")
    # HTTP 头：Retry-After: 120（秒）
    secs = retry_after_seconds(text)
    if secs is not None:
        base = now or datetime.now().astimezone()
        return (base + timedelta(seconds=secs)).astimezone().isoformat(timespec="seconds")
    # x-ratelimit-reset 给的是 Unix 时间戳：那就是重置的时刻
    m = _RE_RATELIMIT_RESET.search(text)
    if m:
        n = int(m.group(1))
        if n >= 10 ** 9:
            try:
                return datetime.fromtimestamp(n).astimezone().isoformat(timespec="seconds")
            except (OSError, OverflowError, ValueError):
                pass
    return None


def mask(text: str) -> str:
    """api key / token / Bearer / sk-… / eyJ… / 32 位 hex.xxx -> ***；data/secrets.json 里存的值也一律 ***。"""
    if not text:
        return text
    try:
        from . import config
        for v in config.all_secret_values():
            if len(v) >= 6:
                text = text.replace(v, "***")
    except Exception:  # noqa: BLE001 - masking must never raise
        pass
    text = _RE_MASK_KV.sub(r"\1\2***", text)
    return _RE_MASK_TOKEN.sub("***", text)


def tcp_reachable(host: str, port: int = 443, tries: int = 2, timeout_s: float = 3.0) -> bool:
    """socket.create_connection 试 tries 次；DNS 失败或都连不上 -> False；host 为空 -> True（跳过预检）。"""
    if not host:
        return True
    for _ in range(max(1, tries)):
        try:
            with socket.create_connection((host, port), timeout=timeout_s):
                return True
        except OSError:
            continue
    return False
