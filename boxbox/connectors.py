"""客户端连接器：告诉各 agent 客户端怎么连上 boxbox。

0.3 起所有客户端（connectors.json 里 transport=http）的条目都只写
`http://127.0.0.1:<端口>/mcp?station=<工位>`，客户端直接连核心，不起子进程、不占 exe 文件。

盒子不替用户改 AI 软件的配置：写配置文件这条路（install）已经删掉，
上岗改成用户自己复制条目。本模块现在只做两件事（§17.2「登记」）：
查条目（status）、给手动粘贴片段（snippet）。

仅标准库。不打印、不联网；只有 cursor_boxbox_disabled() 读 APPDATA 找 Cursor 的设置库（只读）。
"""

import base64
import json
import tomllib
import urllib.parse
from pathlib import Path

from . import i18n

_DATA_FILE = Path(__file__).with_name("connectors.json")


def load() -> dict:
    """读 connectors.json，返回 {客户端键: 条目}。"""
    return json.loads(_DATA_FILE.read_text(encoding="utf-8"))


def hint_text(client: str, field: str, lang: str | None = None) -> str:
    """界面上给用户看的那句提示（贴到哪个聊天框、菜单叫什么）：按语言给。

    词表里有就用词表里的（带 {app} 占位符的填上客户端名），没有就回落 connectors.json 里那份。
    """
    lg = lang or i18n.lang()
    entry = load().get(client) or {}
    label = entry.get("label") or client
    if field == "chat_box":
        if client == "cursor":
            key = "conn.cursor.chat"
        elif client in ("claude-code", "codex"):
            key = "conn.terminal.chat"
        else:
            key = "conn.app.chat"
    elif field == "menu":
        key = {"cursor": "conn.cursor.menu", "claude-code": "conn.terminal.menu",
               "codex": "conn.codex.menu"}.get(client, "conn.app.menu")
    else:
        return ""
    text = i18n.t(key, lg, app=label)
    if text != key:
        return text
    return str(entry.get(field) or "")


def mcp_url(station: str, core_url: str) -> str:
    return "%s/mcp?station=%s" % (core_url.rstrip("/"), urllib.parse.quote(station, safe=""))


def server_entry(station: str, core_url: str, client: str | None = None) -> dict:
    """这家客户端的 boxbox 条目：只写网址（+ http_entry 里的额外键），客户端直接连核心。"""
    conf = (load().get(client) or {}) if client else {}
    return dict(conf.get("http_entry") or {}, url=mcp_url(station, core_url))


def resolve_path(client: str, project_dir: str | None, home: str | None = None) -> Path | None:
    """把 connectors.json 里的 config_path 模板（`~`、`{project}` 占位）落成实际路径。

    GUI 客户端 config_path 为 null → 返回 None。
    cursor 没给 project_dir 时回落到全局 ~/.cursor/mcp.json。
    """
    entry = load()[client]
    template = entry.get("config_path")
    home = str(home) if home is not None else str(Path.home())
    if template is None:
        return None
    if "{project}" in template:
        if project_dir is not None:
            template = template.replace("{project}", str(project_dir))
        elif entry.get("config_path_global"):
            template = entry["config_path_global"]
        else:
            return None
    if template.startswith("~"):
        template = home + template[1:]
    return Path(template)


def _read_entry(path: Path, fmt: str) -> dict | None:
    """从配置文件里取出 boxbox 条目（没有或文件解析失败都返回 None）。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        if fmt == "toml":
            return tomllib.loads(text).get("mcp_servers", {}).get("boxbox")
        return json.loads(text).get("mcpServers", {}).get("boxbox")
    except (ValueError, tomllib.TOMLDecodeError):
        return None


def _station_of(entry: dict | None) -> str | None:
    if not entry:
        return None
    if entry.get("url"):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(str(entry["url"])).query)
        return (q.get("station") or [None])[0]
    args = entry.get("args") or []
    if "--station" in args:
        i = args.index("--station")
        if i + 1 < len(args):
            return args[i + 1]
    return None


def status(client: str, project_dir: str | None = None, home: str | None = None) -> dict:
    """检查该客户端的配置文件是否存在、是否已有 boxbox 条目。"""
    entry = load()[client]
    path = resolve_path(client, project_dir, home)
    if path is None:
        return {"client": client, "path": None, "exists": False, "installed": False, "station": None}
    box_entry = _read_entry(path, entry["format"]) if path.exists() else None
    return {
        "client": client,
        "path": str(path),
        "exists": path.exists(),
        "installed": box_entry is not None,
        "station": _station_of(box_entry),
        "command": (box_entry or {}).get("command") if isinstance(box_entry, dict) else None,
        "url": (box_entry or {}).get("url") if isinstance(box_entry, dict) else None,
    }


def _toml_section(entry: dict) -> str:
    """生成 [mcp_servers.boxbox] 段文本。json.dumps(ensure_ascii=False) 的输出是合法 TOML 基本字符串。"""
    return "[mcp_servers.boxbox]\n" + f"url = {json.dumps(entry['url'], ensure_ascii=False)}\n"


def snippet(client: str, station: str, core_url: str) -> str:
    """给人工复制粘贴的片段：JSON 客户端给标准 mcpServers 片段，codex 给 TOML 段。"""
    entry = load()[client]
    if entry["format"] == "toml":
        return _toml_section(server_entry(station, core_url, client))
    return json.dumps(
        {"mcpServers": {"boxbox": server_entry(station, core_url, client)}},
        ensure_ascii=False,
        indent=2,
    )


def setup_cmd(client: str, station: str, core_url: str) -> str:
    """这家客户端的一条安装命令（claude-code / codex 有）：connectors.json 里的 {url} 换成连接地址。没有就空串。
    只给命令文本，不替用户执行。"""
    tmpl = (load().get(client) or {}).get("install_cmd")
    return str(tmpl).replace("{url}", mcp_url(station, core_url)) if tmpl else ""


def setup_link(client: str, station: str, core_url: str) -> str:
    """一键安装链接（Cursor 有）：config 是 base64(JSON) 再做 URL 编码。没有就空串。"""
    tmpl = (load().get(client) or {}).get("install_link")
    if not tmpl:
        return ""
    payload = json.dumps({"url": mcp_url(station, core_url)}, ensure_ascii=False).encode("utf-8")
    return str(tmpl).replace("{config}", urllib.parse.quote(base64.b64encode(payload).decode("ascii"), safe=""))


def dispatch_link(client: str, lang: str | None = None) -> str:
    """「派活」命令链接（Cursor 有）：text 是 URL 编码的一句话，让首领把用户接下来给的活派给帮手。没有就空串。"""
    tmpl = (load().get(client) or {}).get("dispatch_link")
    if not tmpl:
        return ""
    text = i18n.t("conn.cursor.dispatch_text", lang or i18n.lang())
    return str(tmpl).replace("{text}", urllib.parse.quote(text, safe=""))


# 上岗不替用户写任何 AI 软件的配置：核心只给首领一段话，让用户问过首领再自己加。
# 那段话在 i18n 的 leader.mcp_hint 里。


def cursor_state_db(appdata: str | None = None) -> Path | None:
    """Cursor 自己记设置的库（只读用）：%APPDATA%/Cursor/User/globalStorage/state.vscdb。
    BOXBOX_CURSOR_STATE 可以指别的路径（测试用，见 tests/conftest.py）。"""
    import os
    if os.environ.get("BOXBOX_CURSOR_STATE"):
        p = Path(os.environ["BOXBOX_CURSOR_STATE"])
        return p if p.exists() else None
    base = appdata if appdata is not None else os.environ.get("APPDATA")
    if not base:
        return None
    p = Path(base) / "Cursor" / "User" / "globalStorage" / "state.vscdb"
    return p if p.exists() else None


def cursor_boxbox_disabled(db: Path | None = None) -> bool | None:
    """Cursor 是不是把 boxbox 关掉了（设置 → Tools & MCP 里的开关）。开关按名字记，
    关过一次以后重新登记也还是关着，Cursor 根本不连，会话里就没有 boxbox 的工具。
    只读、只查这一个键；读不到（没装 Cursor / 库的格式变了）返回 None，不当成问题。"""
    import sqlite3
    db = db if db is not None else cursor_state_db()
    if db is None:
        return None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db.as_posix(), uri=True, timeout=2)
        try:
            row = con.execute("SELECT value FROM ItemTable WHERE key = ?", ("cursor/disabledGlobalMcpServers",)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    if not row:
        return False
    raw = row[0].decode("utf-8", "replace") if isinstance(row[0], bytes) else str(row[0])
    try:
        names = json.loads(raw)
    except ValueError:
        return None
    return isinstance(names, list) and "user-boxbox" in names
