# -*- coding: utf-8 -*-
"""每次运行的记录（data/tasks/<卡号>/run-N.log）：记什么、留多久。

Pi 的事件流原样记下来会很大：
- 模型思考 / 回话 / 工具参数是逐字流出来的，每几个字一行（message_update 的 *_delta），一次运行几十万行；
- 命令还在跑时，每次更新都把这条命令到目前为止的全部输出重发一遍（tool_execution_update），
  输出多的长命令能把一份记录撑到几个 GB。

- 好几种事件是重复的：message_start 和 message_end 是同一条消息；tool_execution_end 和 role=toolResult 的
  message_end 是同一份命令结果；turn_end / agent_end 把这一轮 / 整段对话的消息又打包了一遍。

精简（默认）：逐字的片段和重复的打包不记，每条消息只留 message_end 那一份（里面是完整内容）；
命令还在跑的输出每 30 秒记一次、只留最后一段（content 和 details 里的长字都截）。
盒子回头读记录只用 session / message_end / agent_settled / auto_retry_end 和 [stderr] 行，这些都照记。
设置里打开「完整运行记录」就原样记，排查问题用。

结束的卡（完成 / 撤掉 / 失败）：过 log_gzip_days 天压成 .gz，过 log_keep_days 天删掉（0 = 一直留）。
卡片、回报这些小文件不动。在跑、排队、等验收、中断的卡都不动。
"""
from __future__ import annotations

import gzip
import json
import os
import pathlib
import shutil
import threading
import time

from . import config

TOOL_EVERY_S = 30.0          # 命令还在跑：同一条命令最多这么久记一次进度
FINISHED = ("done", "cancelled", "failed")
# 精简时不记：内容在 message_end 里已经有一份完整的
DUPLICATES = ("message_start", "turn_end", "agent_end", "tool_execution_end")
_CHUNK = 4 * 1024 * 1024


def _setting(key: str, default):
    try:
        return config.settings().get(key, default)
    except Exception:  # noqa: BLE001 - 读不到设置就按默认
        return default


class Slimmer:
    """一行进、一行出（或 None = 这行不记）。每次运行一个，记着每条命令上次记进度的时间。"""

    def __init__(self, full: bool | None = None, tail_chars: int | None = None, every_s: float = TOOL_EVERY_S,
                 clock=time.monotonic):
        self.full = bool(_setting("log_full", False)) if full is None else bool(full)
        self.tail = int(_setting("log_tool_tail_chars", 2000)) if tail_chars is None else int(tail_chars)
        self.every_s = every_s
        self.clock = clock
        self._last: dict[str, float] = {}

    def line(self, line: str) -> str | None:
        if self.full:
            return line
        s = line.lstrip()
        if not s.startswith("{"):
            return line                       # [stderr] 行、开头那段说明：照记
        try:
            ev = json.loads(s)
        except ValueError:
            return line
        if not isinstance(ev, dict):
            return line
        et = ev.get("type")
        if et in DUPLICATES:
            return None
        if et == "message_update":
            return None                       # 逐字片段和 *_end 都是 message_end 里那份的拆开版
        if et == "tool_execution_update":
            return self._tool_update(ev)
        return line

    def _tool_update(self, ev: dict) -> str | None:
        if self.tail <= 0:
            return None
        key = str(ev.get("toolCallId") or "")
        now = self.clock()
        last = self._last.get(key)
        if last is not None and now - last < self.every_s:
            return None
        self._last[key] = now
        if "partialResult" in ev:
            ev["partialResult"] = _clip(ev["partialResult"], self.tail)
        return json.dumps(ev, ensure_ascii=False) + "\n"


def _clip(obj, tail: int):
    """长字只留最后 tail 个字（命令输出看最后一段最有用）；字典和列表往里走。"""
    if isinstance(obj, str):
        return obj if len(obj) <= tail else "…" + obj[-tail:]
    if isinstance(obj, dict):
        return {k: _clip(v, tail) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clip(v, tail) for v in obj]
    return obj


def read_text(path: str) -> str:
    """读一份运行记录；已经压成 .gz 的也能读。读不到给空串。"""
    if not path:
        return ""
    p = pathlib.Path(path)
    try:
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
        gz = p.with_name(p.name + ".gz")
        if gz.exists():
            with gzip.open(gz, "rt", encoding="utf-8", errors="replace") as fh:
                return fh.read()
    except OSError:
        return ""
    return ""


# ---------- 留多久 ----------

def _logs_of(card_dir: pathlib.Path):
    try:
        for p in card_dir.iterdir():
            if p.is_file() and p.name.startswith("run-") and (p.name.endswith(".log") or p.name.endswith(".log.gz")):
                yield p
    except OSError:
        return


def gzip_file(src: pathlib.Path) -> bool:
    """压成 src.gz：解压回来长度对得上才删原文件。成功返回 True。"""
    dst = src.with_name(src.name + ".gz")
    part = src.with_name(src.name + ".gz.part")
    try:
        size = src.stat().st_size
        with open(src, "rb") as fi, gzip.open(part, "wb", compresslevel=6) as fo:
            shutil.copyfileobj(fi, fo, _CHUNK)
        got = 0
        with gzip.open(part, "rb") as fz:
            while True:
                chunk = fz.read(_CHUNK)
                if not chunk:
                    break
                got += len(chunk)
        if got != size:
            part.unlink(missing_ok=True)
            return False
        st = src.stat()
        os.replace(part, dst)
        os.utime(dst, (st.st_atime, st.st_mtime))      # 留多久按原记录的时间算，压缩不算「新写的」
        src.unlink()
        return True
    except OSError:
        try:
            part.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def sweep(store, gzip_days: int | None = None, keep_days: int | None = None, now: float | None = None,
          force_gzip: bool = False) -> dict:
    """整理结束的卡的运行记录。force_gzip：不看天数，结束的卡全压（设置页的按钮）。"""
    gzip_days = int(_setting("log_gzip_days", 3)) if gzip_days is None else int(gzip_days)
    keep_days = int(_setting("log_keep_days", 30)) if keep_days is None else int(keep_days)
    now = time.time() if now is None else now
    out = {"gzipped": 0, "deleted": 0, "freed": 0}
    root = config.DATA / "tasks"
    for t in store.list_tasks(state=",".join(FINISHED), limit=100000):
        card_dir = root / str(t["id"])
        for p in list(_logs_of(card_dir)):
            try:
                st = p.stat()
            except OSError:
                continue
            age_days = (now - st.st_mtime) / 86400.0
            if keep_days > 0 and age_days >= keep_days:
                try:
                    p.unlink()
                    out["deleted"] += 1
                    out["freed"] += st.st_size
                except OSError:
                    pass
                continue
            if p.name.endswith(".log") and (force_gzip or age_days >= gzip_days):
                if gzip_file(p):
                    out["gzipped"] += 1
                    try:
                        out["freed"] += st.st_size - p.with_name(p.name + ".gz").stat().st_size
                    except OSError:
                        pass
    return out


def usage() -> dict:
    """data\\ 占多少，其中运行记录多少（没压的 / 压过的）。"""
    total = logs = gz = 0
    root = config.DATA
    try:
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                try:
                    size = os.path.getsize(os.path.join(dirpath, name))
                except OSError:
                    continue
                total += size
                if name.startswith("run-") and name.endswith(".log"):
                    logs += size
                elif name.startswith("run-") and name.endswith(".log.gz"):
                    gz += size
    except OSError:
        pass
    return {"bytes": total, "log_bytes": logs, "gz_bytes": gz, "cleaning": _cleaning.is_set()}


_cleaning = threading.Event()


def sweep_in_background(store, force_gzip: bool = False, on_done=None) -> bool:
    """在后台整理（压几个 GB 要一会儿，别挡住看门狗和页面）。已经在整理就不再起，返回 False。"""
    if _cleaning.is_set():
        return False
    _cleaning.set()

    def run():
        try:
            res = sweep(store, force_gzip=force_gzip)
            if on_done is not None:
                on_done(res)
        except Exception:  # noqa: BLE001 - 整理坏了不能带崩核心
            pass
        finally:
            _cleaning.clear()

    threading.Thread(target=run, name="boxbox-runlog", daemon=True).start()
    return True
