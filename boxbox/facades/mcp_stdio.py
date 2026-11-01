"""MCP facade, two transports sharing handle():

- HTTP（0.3 起首选）：核心自己在 http://127.0.0.1:<端口>/mcp?station=<工位> 上回 JSON-RPC，客户端配置里只写 url，
  不再起子进程，也就不会一直占着 exe 文件（升级、删除都不受影响）。
- stdio（后备）：newline-delimited JSON-RPC on stdin/stdout, forwarded to the core over HTTP. 给不支持 url 的客户端、
  核心里的 Pi 用。 python -m boxbox mcp --station 架构师 --core http://127.0.0.1:8878
"""
from __future__ import annotations

import json
import sys
import urllib.request

from .. import i18n

PROTOCOL_FALLBACK = "2025-06-18"

def tool_schemas(lg: str | None = None) -> dict:
    """工具说明（给模型看的）：按当下语言给。"""
    lg = lg or i18n.lang()
    empty = {"type": "object", "properties": {}}
    return {
        "get_briefing": (i18n.t("mcp.get_briefing", lg), empty),
        "get_board": (i18n.t("mcp.get_board", lg), empty),
        "get_todo": (i18n.t("mcp.get_todo", lg), empty),
        "get_task": (i18n.t("mcp.get_task", lg),
                     {"type": "object", "properties": {"task_id": {"type": "string", "pattern": r"^\d{8}-\d{3}$"}},
                      "required": ["task_id"]}),
        "assign": (i18n.t("mcp.assign", lg),
                   {"type": "object", "properties": {
                       "station": {"type": "string", "description": i18n.t("mcp.assign.station", lg)},
                       "card": {"type": "object", "required": ["title", "goal", "inputs", "expected_output", "acceptance"],
                                "properties": {
                                    "title": {"type": "string", "description": i18n.t("mcp.assign.title", lg)},
                                    "goal": {"type": "string", "description": i18n.t("mcp.assign.goal", lg)},
                                    "cwd": {"type": "string", "description": i18n.t("mcp.assign.cwd", lg)},
                                    "inputs": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                                               "description": i18n.t("mcp.assign.inputs", lg)},
                                    "expected_output": {"type": "object", "required": ["kind"], "properties": {
                                        "kind": {"type": "string", "enum": ["code", "doc", "data", "run", "review"]},
                                        "path": {"type": "string", "description": i18n.t("mcp.assign.expected_output", lg)}}},
                                    "acceptance": {"type": "object", "required": ["review"], "properties": {
                                        "review": {"type": "string", "enum": ["leader", "user", "none"],
                                                   "description": i18n.t("mcp.assign.review", lg)},
                                        "max_rounds": {"type": "integer", "description": i18n.t("mcp.assign.max_rounds", lg)},
                                        "gates": {"type": "array", "description": i18n.t("mcp.assign.gates", lg),
                                                  "items": {"type": "object", "required": ["check"], "properties": {
                                                      "check": {"type": "string",
                                                                "enum": ["exists", "size", "headings", "json", "commits", "command"]}}}}}},
                                    "files": {"type": "array", "items": {"type": "string"},
                                              "description": i18n.t("mcp.assign.files", lg)}}}},
                   "required": ["station", "card"]}),
        "review": (i18n.t("mcp.review", lg),
                   {"type": "object", "properties": {"task_id": {"type": "string"},
                                                     "verdict": {"type": "string", "enum": ["accept", "return"]},
                                                     "note": {"type": "string"},
                                                     "feedback": {"type": "string", "maxLength": 120}},
                    "required": ["task_id", "verdict"]}),
        "resolve": (i18n.t("mcp.resolve", lg),
                    {"type": "object", "properties": {"task_id": {"type": "string"},
                                                      "action": {"type": "string", "enum": ["redispatch", "cancel"]},
                                                      "note": {"type": "string"}}, "required": ["task_id", "action"]}),
        "report": (i18n.t("mcp.report", lg),
                   {"type": "object", "properties": {"task_id": {"type": "string"},
                                                    "status": {"type": "string", "enum": ["heartbeat", "done", "blocked", "issue"]},
                                                    "summary": {"type": "string"}}, "required": ["task_id", "status"]}),
        "post": (i18n.t("mcp.post", lg),
                 {"type": "object", "properties": {"to": {"type": "string"}, "text": {"type": "string"}},
                  "required": ["to", "text"]}),
        "read_inbox": (i18n.t("mcp.read_inbox", lg), empty),
        "wait_for_update": (i18n.t("mcp.wait_for_update", lg),
                            {"type": "object", "properties": {"timeout_s": {"type": "integer", "minimum": 1, "maximum": 120}}}),
    }


LEADER_TOOLS = ("get_briefing", "get_board", "get_todo", "get_task", "assign", "review", "resolve", "post", "read_inbox",
                "wait_for_update")
MEMBER_TOOLS = ("get_briefing", "get_board", "get_task", "report")


def _post(core: str, path: str, payload: dict, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(core.rstrip("/") + path, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(core: str, path: str) -> dict:
    with urllib.request.urlopen(core.rstrip("/") + path, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def tool_names(role: str) -> tuple:
    return LEADER_TOOLS if role == "leader" else MEMBER_TOOLS


def handle(msg: dict, station: str, role: str, call, lang: str | None = None) -> dict | None:
    """一条 JSON-RPC 消息 → 回复（通知返回 None）。stdio 和 HTTP（核心的 /mcp）共用这一份，行为一模一样。
    call(tool, args) -> dict：stdio 版转发到核心的 /rpc，HTTP 版直接调核心。
    lang 给当下语言（工位资料里的，没写就跟界面语言）。"""
    mid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}
    names = tool_names(role)
    lg = lang or i18n.lang()
    schemas = tool_schemas(lg)
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_FALLBACK,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "boxbox", "version": __import__("boxbox").__version__},
            "instructions": i18n.t("mcp.instructions", lg, sid=station or i18n.t("mcp.no_station", lg), role=role)}}
    if mid is None or (method or "").startswith("notifications/"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": n, "description": schemas[n][0], "inputSchema": schemas[n][1]} for n in names]}}
    if method == "tools/call":
        name = params.get("name")
        if name not in names:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "unknown tool %s" % name}}
        if not station:
            return {"jsonrpc": "2.0", "id": mid, "result": {"isError": True, "content": [
                {"type": "text", "text": i18n.t("mcp.no_station", lg)}]}}
        try:
            res = call(name, params.get("arguments") or {})
            text = json.dumps(res, ensure_ascii=False, indent=1)
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": not res.get("ok", True)}}
        except Exception as e:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": mid,
                    "result": {"content": [{"type": "text", "text": i18n.t("mcp.core_unreachable", lg, err=e)}],
                               "isError": True}}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found: %s" % method}}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="boxbox mcp")
    ap.add_argument("--station", required=True)
    ap.add_argument("--core", default="http://127.0.0.1:8878")
    ap.add_argument("--log", default=None, help="append method names / sizes here (no bodies)")
    a = ap.parse_args(argv)
    role = "member"
    lang = ""
    try:
        for s in _get(a.core, "/api/stations_def").get("stations", []):
            if s.get("id") == a.station:
                role = s.get("role", "member")
                lang = str(s.get("lang") or "")
    except Exception:  # noqa: BLE001 - core may be down; still answer initialize so the client shows a clear error later
        pass
    logf = open(a.log, "a", encoding="utf-8") if a.log else None
    stdout = sys.stdout.buffer
    client_info = {}                   # 客户端报的名字，转发给核心，核心照样归类

    def call(name, args):
        payload = {"station": a.station, "args": args}
        if client_info:
            payload["client_info"] = client_info
        return _post(a.core, "/rpc/%s" % name, payload)

    for raw in sys.stdin.buffer:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
        if logf:
            logf.write("%s %dB\n" % (msg.get("method"), len(raw)))
            logf.flush()
        if msg.get("method") == "initialize":            # 记下客户端报的名字
            info = (msg.get("params") or {}).get("clientInfo") or {}
            if info.get("name"):
                client_info = {"name": str(info.get("name"))}
        out = handle(msg, a.station, role, call, lang or None)
        if out is not None:
            stdout.write((json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8"))
            stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
