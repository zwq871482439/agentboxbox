# -*- coding: utf-8 -*-
"""同一个首领工位上，是不是有两个对话在交替调用。

只在内存里记最近一小段的调用顺序（会话号 + 时间），不存盘、不进卡、不拿来认人。
没带会话号的调用不参与。换了个新号、旧号不再出现，是重连，不算两个对话。
"""
from __future__ import annotations

import threading
import time

# 只看最近这一段：更早的调用丢掉。这段里没再出现「走了又回来」，就不算两个对话了。
WINDOW_S = 15 * 60

_clock = time.time


def set_clock(fn) -> None:
    """测试把时间钉住，免得真等这一段过去。"""
    global _clock
    _clock = fn


def reset_clock() -> None:
    global _clock
    _clock = time.time


def _now() -> float:
    return float(_clock())


class _Log:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: dict[str, list[tuple[str, float]]] = {}

    def note(self, station: str, session: str, now: float) -> None:
        sid = str(session or "").strip()
        if not station or not sid:
            return
        with self._lock:
            rows = [row for row in self._rows.get(station, ()) if now - row[1] < WINDOW_S]
            rows.append((sid, now))
            self._rows[station] = rows

    def shared(self, station: str, now: float) -> bool:
        with self._lock:
            rows = [row for row in self._rows.get(station, ()) if now - row[1] < WINDOW_S]
            if rows:
                self._rows[station] = rows
            else:
                self._rows.pop(station, None)
            return _alternates(rows)


def _alternates(rows: list[tuple[str, float]]) -> bool:
    """连续同一个号并成一次。某个号走了又回来（中间夹了别的号）才算两个对话在交替。"""
    seq: list[str] = []
    for sid, _ts in rows:
        if not seq or seq[-1] != sid:
            seq.append(sid)
    seen: set[str] = set()
    for sid in seq:
        if sid in seen:
            return True
        seen.add(sid)
    return False


def _log(dispatcher) -> _Log:
    box = dispatcher.__dict__
    log = box.get("_leader_sessions")
    if log is None:
        log = _Log()
        box["_leader_sessions"] = log
    return log


def note(dispatcher, station: str, session: str) -> None:
    if not str(session or "").strip():
        return
    _log(dispatcher).note(station, session, _now())


def shared(dispatcher, station: str) -> bool:
    log = dispatcher.__dict__.get("_leader_sessions")
    if log is None:
        return False
    return log.shared(station, _now())
