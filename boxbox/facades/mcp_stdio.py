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
from .http_const import WAIT_MAX_S

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
                                                      "note": {"type": "string"},
                                                      "station": {"type": "string",
                                                                  "description": i18n.t("mcp.resolve.station", lg)}},
                     "required": ["task_id", "action"]}),
        "report": (i18n.t("mcp.report", lg),
                   {"type": "object", "properties": {"task_id": {"type": "string"},
                                                    "status": {"type": "string", "enum": ["heartbeat", "done", "blocked", "issue"]},
                                                    "summary": {"type": "string"}}, "required": ["task_id", "status"]}),
        "post": (i18n.t("mcp.post", lg),
                 {"type": "object", "properties": {"to": {"type": "string"}, "text": {"type": "string"}},
                  "required": ["to", "text"]}),
        "read_inbox": (i18n.t("mcp.read_inbox", lg), empty),
        "wait_for_update": (i18n.t("mcp.wait_for_update", lg),
                            {"type": "object", "properties": {
                                "timeout_s": {"type": "integer", "minimum": 1, "maximum": WAIT_MAX_S}}}),
    }


LEADER_TOOLS = ("get_briefing", "get_board", "get_todo", "get_task", "assign", "review", "resolve", "post", "read_inbox",
                "wait_for_update")
MEMBER_TOOLS = ("get_briefing", "get_board", "get_task", "report")


def _enabled_members(stations) -> list[dict]:
    out = []
    for st in stations or []:
        if not isinstance(st, dict) or st.get("role") != "member" or not st.get("enabled", True):
            continue
        if str(st.get("id") or ""):
            out.append(st)
    return out


def _model_of(st: dict) -> str:
    pi = st.get("pi")
    if isinstance(pi, dict) and pi.get("model"):
        return str(pi["model"])
    return ""


def _station_choices(schema: dict, lg: str, stations) -> dict:
    """启用中的打工猫做成 enum，描述里带各自的模型。一只都没有就不加 enum，空枚举会把正常派卡挡在外面。"""
    members = _enabled_members(stations)
    if not members:
        return schema
    ids, bits = [], []
    for st in members:
        sid = str(st["id"])
        ids.append(sid)
        model = _model_of(st)
        bits.append(i18n.t("mcp.assign.station.one", lg, sid=sid, model=model) if model else sid)
    prop = dict((schema.get("properties") or {}).get("station") or {})
    prop["enum"] = ids
    prop["description"] = i18n.t("mcp.assign.station", lg) + i18n.t(
        "mcp.assign.station.models", lg, cats=i18n.t("list.sep", lg).join(bits))
    props = dict(schema.get("properties") or {})
    props["station"] = prop
    return dict(schema, properties=props)


def _load_stations(load_stations):
    if load_stations is None:
        from .. import config
        return config.stations()
    try:
        got = load_stations()
    except Exception:  # noqa: BLE001 - 问不到工位就先不给枚举，工具列表还在
        return []
    return got if isinstance(got, list) else []


def _schemas_for_list(schemas: dict, lg: str, names, load_stations) -> dict:
    if "assign" not in names:
        return schemas
    schemas = dict(schemas)
    desc, schema = schemas["assign"]
    schemas["assign"] = (desc, _station_choices(schema, lg, _load_stations(load_stations)))
    return schemas


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


def _tool_result(mid, res: dict) -> dict:
    text = json.dumps(res, ensure_ascii=False, indent=1)
    return {"jsonrpc": "2.0", "id": mid, "result": {
        "content": [{"type": "text", "text": text}], "isError": not res.get("ok", True)}}


def _args_error(name: str, args, schema: dict, lg: str) -> str | None:
    """schema 没声明的字段直接拒，不往下传。只看工具这一层：卡和质检项里的字段写在说明里，
    properties 没逐个列（比如质检的 path）。打回没写说明也拒：空说明重派出去，猫只能猜。"""
    if not isinstance(args, dict):
        return i18n.t("mcp.bad_args_type", lg, tool=name)
    known = list((schema.get("properties") or {}).keys())
    extra = [str(k) for k in args if k not in known]
    if extra:
        fields = i18n.t("list.sep", lg).join(known) if known else i18n.t("mcp.no_fields", lg)
        unknown = i18n.t("list.sep", lg).join(extra)
        text = i18n.t("mcp.unknown_fields", lg, tool=name, unknown=unknown, fields=fields)
        if name == "review" and "comment" in extra:
            text += i18n.t("mcp.note_named", lg)
        return text
    if name == "review" and args.get("verdict") == "return" and not str(args.get("note") or "").strip():
        return i18n.t("mcp.return_needs_note", lg)
    return None


def handle(msg: dict, station: str, role: str, call, lang: str | None = None, load_stations=None) -> dict | None:
    """一条 JSON-RPC 消息 → 回复（通知返回 None）。stdio 和 HTTP（核心的 /mcp）共用这一份，行为一模一样。
    call(tool, args) -> dict：stdio 版转发到核心的 /rpc，HTTP 版直接调核心。
    lang 给当下语言（工位资料里的，没写就跟界面语言）。"""
    mid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}
    names = tool_names(role)
    lg = lang or i18n.lang()
    schemas = tool_schemas(lg)
    if method == "notifications/cancelled":
        # 取消从另一条连接进来。stdio 的读循环被这次调用堵住，取消通知要等这次回来才读得到，接不住；
        # Cursor 走 HTTP，取消和这次调用不在同一条连接上，这里喊停正在等的那一趟。
        from .http_leader import note_cancelled
        rid = params.get("requestId") if isinstance(params, dict) else None
        note_cancelled(station, rid)
        return None
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
        # 每次现查：工位改了，下一次列工具就跟着变。校验仍用上面那份不带 enum 的 schema，
        # 免得可选值只是给客户端下拉用，却把写对了的派卡拒掉。
        listed = _schemas_for_list(schemas, lg, names, load_stations)
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": n, "description": listed[n][0], "inputSchema": listed[n][1]} for n in names]}}
    if method == "tools/call":
        from .http_leader import arm_cancel, drop_held
        name = params.get("name")
        if name not in names:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "unknown tool %s" % name}}
        if not station:
            return {"jsonrpc": "2.0", "id": mid, "result": {"isError": True, "content": [
                {"type": "text", "text": i18n.t("mcp.no_station", lg)}]}}
        args = params.get("arguments") or {}
        why = _args_error(name, args, schemas[name][1], lg)
        if why:
            return _tool_result(mid, {"ok": False, "code": "bad_args", "text": why})
        arm_cancel(station, mid)
        try:
            return _tool_result(mid, call(name, args))
        except Exception as e:  # noqa: BLE001
            drop_held()          # 回话里没有这些事件，不能当成已经告诉过首领
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

    def load_stations():
        # stdio 进程自己的数据目录不一定是核心的，工位以核心这份为准，每次列工具问一次
        try:
            return _get(a.core, "/api/stations_def").get("stations") or []
        except Exception:  # noqa: BLE001 - 核心没开着：先给不带枚举的工具列表
            return []

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
        out = handle(msg, a.station, role, call, lang or None, load_stations)
        if out is not None:
            stdout.write((json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8"))
            stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
