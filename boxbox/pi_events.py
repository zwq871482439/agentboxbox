"""逐行解析 `pi --mode json` 的 JSONL 事件流（工作计划 2.3 中段）。

纯解析，不启动进程、不打印、不写文件、不读环境变量。

三条 suspect 规则与 scripts/_wake-core.ps1（Get-StalePathHit 的 PowerShell 兜底正则、
why 判定）保持一致：
  1. 最终回复说任务没到/被截断
  2. 整个运行没有任何 toolCall
  3. 工具结果或工具参数里碰到 WSL/旧快照路径（/home/runner、\\wsl$\\发行版\\非 mnt）
`/mnt/c` 这类 Windows 盘挂载、以及裸的 `fatal: not a git repository` 不算。
第 3 条在已交付时抑制（tool_calls>=5；与 _wake-core 的 commits>0|tools>=5 对齐，
本解析器看不到 commits）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import i18n, run_timing

# /home/runner —— bash 掉进 WSL 时读到的 home，不是真用户的家目录
RE_HOME_RUNNER = re.compile(r"/home/runner\b", re.I)

# \\wsl$\Ubuntu\home\... 或 \\wsl.localhost\Ubuntu-24.04\mnt\c\...；mnt\ 开头不算
# 与 _wake-core.ps1 兜底正则一致（要求真的 UNC 双反斜杠前缀）
RE_WSL_UNC = re.compile(r"\\\\wsl(?:\$|\.localhost)\\[^\\]+\\(?!mnt)", re.I)

# 最终回复说任务单没到/被截断
RE_TASK_MISSING = re.compile("任务单缺失|没贴|被截断|截断了|等你补|无法执行")

_MAX_TOOL = 120  # last_tool 截断长度，与 _wake-core.ps1 一致
_MAX_FINAL = 4000


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    turns: int = 0

    def as_dict(self) -> dict:
        """键名与 runs.tokens_json / token_ledger 一致（in/out/cr/cw/turns/source）。"""
        return {"in": self.input, "out": self.output, "cr": self.cache_read,
                "cw": self.cache_write, "turns": self.turns, "source": "pi_json"}


@dataclass
class PiRun:
    session_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    tool_calls: int = 0
    last_tool: str = ""
    final_text: str = ""
    stop_reason: str | None = None
    settled: bool = False
    aborted: bool = False
    errors: list[str] = field(default_factory=list)
    retried_errors: list[str] = field(default_factory=list)   # 出错后 Pi 自动重试成功了的，不算这次运行失败
    retry_failed: str = ""     # auto_retry_end success=false：Pi 自重试用完还是失败，finalError 原文
    stale_hit: str = ""
    last_event_type: str = ""
    events: int = 0
    bad_lines: int = 0


def _text_of(content) -> str:
    """content 可能是 str、TextContent 列表、或别的；尽量取出全部文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict) and isinstance(b.get("text"), str):
                out.append(b["text"])
        return "".join(out)
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return ""


def _arg_summary(args) -> str:
    if isinstance(args, dict):
        for k in ("command", "path"):
            v = args.get(k)
            if isinstance(v, str) and v.strip():
                return v
        try:
            return json.dumps(args, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            return str(args)
    if isinstance(args, str):
        return args
    return "{}"


def stale_hit_in_text(text: str) -> str:
    """WSL/旧快照路径命中串；没命中返回 ""。/mnt/c 与裸 git 报错都不算。"""
    if not text:
        return ""
    if RE_HOME_RUNNER.search(text):
        return "/home/runner"
    m = RE_WSL_UNC.search(text)
    return m.group(0)[:80] if m else ""


class PiEventParser:
    """半行/粘包都由内部 _buf 消化；feed 随便切几字符都行。"""

    def __init__(self, lang: str | None = None):
        self.run = PiRun()
        self.timing = run_timing.Accum()
        self._buf = ""
        self.lang = lang or i18n.lang()

    # ---------- 输入 ----------

    def feed(self, chunk: str) -> list[dict]:
        """喂任意长度文本，返回本次完整解析出的事件对象（非 JSON 行不算在内）。"""
        if chunk is None:
            return []
        if isinstance(chunk, (bytes, bytearray)):
            chunk = chunk.decode("utf-8", "replace")
        buf = self._buf + chunk
        parts = buf.split("\n")
        self._buf = parts.pop()  # 最后一段是半行，留着
        out = []
        for ln in parts:
            obj = self.feed_line(ln)
            if obj is not None:
                out.append(obj)
        return out

    def feed_line(self, line: str) -> dict | None:
        """处理一整行（不含换行符）。空行跳过；非 JSON 行计 bad_lines 不抛异常。"""
        if not isinstance(line, str):
            line = "" if line is None else str(line)
        line = line[1:] if line.startswith("\r") else line  # 行首 \r 去掉
        if not line.strip():
            return None
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            self.run.bad_lines += 1
            return None
        if not isinstance(obj, dict):
            self.run.bad_lines += 1
            return None
        self._apply(obj)
        return obj

    def close(self) -> PiRun:
        """进程/流结束后调用：残留半行也试着解析一遍。"""
        rest, self._buf = self._buf, ""
        if rest.strip():
            self.feed_line(rest)
        return self.run

    # ---------- 状态 ----------

    @property
    def suspect_why(self) -> list[str]:
        return self._suspect_why(self.lang)

    def _suspect_why(self, lg: str) -> list[str]:
        why: list[str] = []
        if RE_TASK_MISSING.search(self.run.final_text or ""):
            why.append(i18n.t("runner.suspect.task_missing", lg))
        if self.run.tool_calls == 0:
            why.append(i18n.t("runner.suspect.no_tools", lg))
        # Delivery gate: path hit alone is not suspect once the run clearly worked.
        if self.run.stale_hit and self.run.tool_calls < 5:
            why.append(i18n.t("runner.suspect.stale_path", lg, path=self.run.stale_hit))
        return why

    def summary(self, lang: str | None = None) -> dict:
        r = self.run
        lg = lang or self.lang
        why = self._suspect_why(lg)
        return {"tokens": r.usage.as_dict() if r.usage.turns else None,
                "tools": r.tool_calls,
                "last_tool": r.last_tool,
                "suspect": bool(why),
                "suspect_why": i18n.t("runner.list_sep", lg).join(why),
                "settled": r.settled,
                "aborted": r.aborted,
                "stop_reason": r.stop_reason,
                "errors": list(r.errors),
                "retried_errors": list(r.retried_errors),
                "retry_failed": r.retry_failed,
                "final_text": (r.final_text or "")[:_MAX_FINAL],
                "split": self.timing.snapshot()}

    # ---------- 事件处理 ----------

    def _apply(self, ev: dict) -> None:
        r = self.run
        r.events += 1
        etype = ev.get("type")
        if isinstance(etype, str) and etype:
            r.last_event_type = etype

        if etype == "session":
            sid = ev.get("id")
            if isinstance(sid, str) or sid is None:
                r.session_id = sid if isinstance(sid, str) and sid else r.session_id
        elif etype == "message_end":
            self._message_end(ev.get("message"))
        elif etype == "agent_settled":
            r.settled = True
            if ev.get("aborted") is True:
                r.aborted = True
        elif etype == "auto_retry_end":
            # Pi 自重试到头还是失败（success=false，finalError 是模型接口那头的报错）——
            # 这轮没干完，不能当「交回」跑质检；成功就只是把 errors 挪去 retried_errors 的另一种说法。
            if ev.get("success") is False:
                fe = ev.get("finalError")
                r.retry_failed = fe if isinstance(fe, str) and fe.strip() else i18n.t("runner.retry_failed", self.lang)
            else:
                if r.errors:
                    r.retried_errors.extend(r.errors)
                    r.errors.clear()

    def _message_end(self, message) -> None:
        if not isinstance(message, dict):
            return
        role = message.get("role")
        if role == "assistant":
            self._assistant(message)
        elif role == "toolResult":
            self._tool_result(message)

    def _assistant(self, msg: dict) -> None:
        r = self.run
        usage = msg.get("usage")
        if isinstance(usage, dict):
            r.usage.input += _int(usage.get("input"))
            r.usage.output += _int(usage.get("output"))
            r.usage.cache_read += _int(usage.get("cacheRead"))
            r.usage.cache_write += _int(usage.get("cacheWrite"))
        r.usage.turns += 1  # 每条 assistant 消息一次；message_update 的中间值不计入

        r.final_text = _text_of(msg.get("content"))
        stop = msg.get("stopReason")
        if isinstance(stop, str) and stop:
            r.stop_reason = stop
        if stop == "error":
            err = msg.get("errorMessage")
            r.errors.append(err if isinstance(err, str) and err else "assistant stopReason=error")
        elif r.errors:
            # 服务商偶发超时 → Pi auto_retry → 后面的回复正常。之前的错已经被重试消化，不能再让整张卡判失败。
            r.retried_errors.extend(r.errors)
            r.errors.clear()

        for block in msg.get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "toolCall":
                continue
            r.tool_calls += 1
            name = block.get("name")
            name = name if isinstance(name, str) else "?"
            args_text = _arg_summary(block.get("arguments"))
            summary = re.sub(r"\s+", " ", f"{name}: {args_text}").strip()
            r.last_tool = summary[:_MAX_TOOL]
            self._note_stale(args_text)
        self.timing.assistant(msg)

    def _tool_result(self, msg: dict) -> None:
        self.timing.tool_result(msg)
        self._note_stale(_text_of(msg.get("content")))

    def _note_stale(self, text: str) -> None:
        if self.run.stale_hit:
            return  # 首个命中即止，与 scan_session_lines 一致
        hit = stale_hit_in_text(text)
        if hit:
            self.run.stale_hit = hit


def _int(v) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v.strip())
        except ValueError:
            return 0
    return 0


