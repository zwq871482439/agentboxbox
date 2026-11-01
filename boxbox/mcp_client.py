"""首领用的 AI 软件按真正连上来的那一家记，不猜。

MCP 客户端握手（initialize）时会报 clientInfo.name：Cursor 报 "cursor"，Claude Code 报 "claude-code"，
Codex 报 "codex_cli_rs"，写法和大小写都不固定。这里把它归成固定几类，看板上只显示这几个：

  cursor / claude-code / codex / other        —— 认得出来的
  other                                      —— 报了名字但认不出（不猜）
  other-direct                               —— 没发 initialize 直接 tools/call（那段话里的 HTTP 兜底）
"""
from __future__ import annotations

from . import i18n

LABEL = {"cursor": "Cursor", "claude-code": "Claude Code", "codex": "Codex"}
#: 认不出的那几种：给用户看的话在词表里（中文 / 英文）
I18N_LABEL = {"other": "client.other", "other-direct": "client.other_direct"}


def classify(name: str | None) -> str:
    """clientInfo.name → cursor / claude-code / codex / other。认不准就 other，不猜。"""
    s = str(name or "").strip().lower()
    if "cursor" in s:
        return "cursor"
    if "claude" in s:
        return "claude-code"
    if "codex" in s:
        return "codex"
    return "other"


def label(code: str | None, lang: str | None = None) -> str:
    """看板上显示的名字（没连上过 = 空）。"""
    c = str(code or "")
    if c in I18N_LABEL:
        return i18n.t(I18N_LABEL[c], lang)
    return LABEL.get(c, "")
