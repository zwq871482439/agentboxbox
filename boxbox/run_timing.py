"""从 Pi 事件流里分出模型时间和命令时间。

助手消息上的 durationMs 是模型时间，工具结果上的是这条命令的时间。
同一条助手消息发出的几条命令是并行的，时间取最长的那条，不能加总。
消息上的 timestamp 是创建时间，相减会得到 0，所以不用。
"""
from __future__ import annotations

import re

from . import classify

# 改文件只认这两个工具名：第一次出现之前的助手消息条数，就是「改文件前的轮数」
FILE_TOOLS = {"edit", "write"}
SHELL_TOOLS = {"bash", "shell"}

# 命令开头（或接在 ; & | ` ( 后面）才算跑了一次测试，免得文件名里带 pytest 也被数进去。
# 前面可以有环境变量（ISP_FAKE_EMBED=1）和包一层的命令（timeout 600、uv run、npx）：说明书要求长命令带 timeout，
# 不认这些的话猫照规矩跑的测试一次都数不到
_ENV = r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*"
_WRAP = (r"(?:(?:sudo|nice|time|npx|bunx|timeout(?:\s+-{1,2}\S+)*\s+\d+(?:\.\d+)?[smhd]?"
         r"|uv\s+run|poetry\s+run|pipenv\s+run|pnpm\s+exec)\s+)*")
_PM_FLAGS = r"(?:\s+-{1,2}[A-Za-z][\w-]*(?:[ =][^\s-]\S*)?)*"      # pnpm -C apps/web test、npm --prefix web test
_TEST = re.compile(
    r"(?:^|[;&|`(]\s*)" + _ENV + _WRAP +
    r"(?:pytest|py\.test|py(?:thon)?(?:\d+(?:\.\d+)?)?(?:\s+-X\s+\S+)*\s+-m\s+(?:pytest|unittest)"
    r"|(?:npm|pnpm|yarn)" + _PM_FLAGS + r"\s+(?:run\s+)?test(?::[\w-]+)?|vitest|jest|node\s+--test"
    r"|cargo\s+test|go\s+test|mvn\s+(?:test|surefire:test)|gradle\s+test"
    r"|dotnet\s+test|rspec|phpunit|ctest)\b",
    re.I,
)


def _ms(v) -> int | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        n = int(v)
        return n if n >= 0 else None
    if isinstance(v, str):
        try:
            n = int(float(v.strip()))
        except ValueError:
            return None
        return n if n >= 0 else None
    return None


def _one(text: str) -> str:
    return " ".join(str(text).split())


def _cmd(name: str, args) -> str:
    text = ""
    if isinstance(args, dict):
        for k in ("command", "cmd"):
            v = args.get(k)
            if isinstance(v, str) and v.strip():
                text = v
                break
        if not text and isinstance(args.get("path"), str):
            text = args["path"]
    elif isinstance(args, str):
        text = args
    text = classify.mask(_one(text))      # 命令里可能带着 key：存进库、上面板之前先打码
    if text:
        return text[:120]
    return (name or "")[:40]


class Accum:
    """一边读事件一边累加。snapshot 可以反复调，不会把还没结束的那批命令算丢。"""

    def __init__(self):
        self.model_ms = 0
        self.cmd_ms = 0
        self._batch: list[int] = []
        self._saw = False
        self.turns = 0
        self.turns_before_edit: int | None = None
        self.edited = False
        self.tools = 0
        self.test_runs = 0
        self.longest_ms: int | None = None
        self.longest_cmd = ""
        self._calls: dict[str, tuple[str, str]] = {}

    def assistant(self, msg: dict) -> None:
        self._flush()
        self.turns += 1
        dur = _ms(msg.get("durationMs"))
        if dur is not None:
            self._saw = True
            self.model_ms += dur
        for block in msg.get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "toolCall":
                continue
            self.tools += 1
            name = str(block.get("name") or "")
            cmd = _cmd(name, block.get("arguments"))
            cid = block.get("id")
            if isinstance(cid, str) and cid:
                self._calls[cid] = (name, cmd)
            if name.lower() in FILE_TOOLS and not self.edited:
                self.edited = True
                self.turns_before_edit = self.turns - 1
            if name.lower() in SHELL_TOOLS and _TEST.search(cmd):
                self.test_runs += 1

    def tool_result(self, msg: dict) -> None:
        dur = _ms(msg.get("durationMs"))
        if dur is None:
            return
        self._saw = True
        self._batch.append(dur)
        name = str(msg.get("toolName") or "")
        cid = msg.get("toolCallId")
        saved = self._calls.get(cid) if isinstance(cid, str) else None
        if saved:
            name = name or saved[0]
            cmd = saved[1]
        else:
            cmd = name
        if name.lower() in SHELL_TOOLS and (self.longest_ms is None or dur > self.longest_ms):
            self.longest_ms = dur
            self.longest_cmd = cmd[:120]

    def snapshot(self) -> dict | None:
        if self.turns == 0 and not self._saw and self.tools == 0:
            return None
        extra = max(self._batch) if self._batch else 0
        before = self.turns if self.turns_before_edit is None else self.turns_before_edit
        return {
            "model_ms": self.model_ms if self._saw else None,
            "cmd_ms": (self.cmd_ms + extra) if self._saw else None,
            "measured": self._saw,
            "turns_before_edit": before,
            "edited": self.edited,
            "tools": self.tools,
            "test_runs": self.test_runs,
            "longest_ms": self.longest_ms,
            "longest_cmd": self.longest_cmd,
        }

    def _flush(self) -> None:
        if not self._batch:
            return
        self.cmd_ms += max(self._batch)
        self._batch = []
