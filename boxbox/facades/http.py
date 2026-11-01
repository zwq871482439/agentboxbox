"""HTTP facade: /api/* for the dashboard (GET, read-only) and /rpc/<tool> for the MCP/CLI facades (POST).

Binds 127.0.0.1 only. POST accepts requests with no Origin (local processes) or an Origin equal to this server.
页面和静态文件在这里发，/api/* 的接口在 http_api.py，首领那边的事件和上岗话在 http_leader.py。
"""
from __future__ import annotations

import json
import mimetypes
import pathlib
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import config, i18n, mcp_client
from ..ports import is_restricted
from . import http_api
from .http_const import (
    _HHMM,
    COPY_DECOR,
    COPY_SKIP,
    COPY_TAIL_RE,
    DISPATCH_EVENT_KINDS,
    LEADER_EVENT_KINDS,
    LEADER_EVENT_MAX,
    ROLE_ALIASES,
    RUNNING_STATES,
    SETTINGS_BOOLS,
    SETTINGS_INTS,
    STATION_ROLES,
    STATION_RUNNERS,
    TOOLS,
)
from .http_core import Core, _as_int, _meta, _onboard_state, _task_view, http_tips, normalize_role, running_task_ids, settings_patch
from .http_leader import _event_line, _hhmm, _leader_events, _leader_new, _leader_seen_key, _wait_for_update, hire_prompt
from .http_stations import _copy_name, _git, _is_git_repo, _make_worktree, _quota_errors, _running_cards, _station_detail, _station_errors, _summon

__all__ = ["Core", "serve", "hire_prompt", "_summon",
           # 拆文件之前这些名字都在本模块里，外面可能按老名字取：原样再导出，位置变了、名字没变
           "TOOLS", "STATION_ROLES", "STATION_RUNNERS", "ROLE_ALIASES", "SETTINGS_INTS", "SETTINGS_BOOLS",
           "COPY_DECOR", "COPY_SKIP", "COPY_TAIL_RE", "LEADER_EVENT_KINDS", "LEADER_EVENT_MAX",
           "RUNNING_STATES", "DISPATCH_EVENT_KINDS", "_HHMM", "normalize_role", "_as_int",
           "settings_patch", "http_tips", "_task_view", "_onboard_state", "_meta", "running_task_ids",
           "_hhmm", "_event_line", "_leader_events", "_leader_seen_key", "_leader_new", "_wait_for_update",
           "_station_errors", "_quota_errors", "_copy_name", "_running_cards", "_git", "_is_git_repo",
           "_make_worktree", "_station_detail"]

PKG_STATIC = pathlib.Path(__file__).resolve().parent.parent / "static"     # boxbox/static: pages served by the core

VENDOR_STATIC = config.BUNDLE / "static"                                      # repo static/: tabler css (offline)

ICON_DIR = config.BUNDLE / "assets" / "icon"                                # app icons (favicon, apple-touch, exe)

LEGAL = {"/legal/privacy": "PRIVACY.md", "/legal/license": "LICENSE",
         "/legal/notices": "THIRD_PARTY_NOTICES.md", "/legal/third-party": "THIRD_PARTY_LICENSES.txt"}

PAGES = {"/": "home.html", "/board": "index.html", "/onboard": "onboard.html", "/stations": "stations.html", "/doctor": "doctor.html",
         "/office": "office.html", "/settings": "settings.html"}

PORT_REBIND_TRIES = 20          # 撞上禁用端口最多重绑几次


def _req_lang(q: dict) -> str:
    """页面上问的语言（?lang=en）：这一次回话就按它来，不用等设置里的语言改过来。"""
    return str((q.get("lang") or [""])[0]).strip().lower()


class Handler(BaseHTTPRequestHandler):
    core: Core = None  # 由 serve() 按核心生成子类时填上（每个核心一份，见 serve()）
    server_version = "boxbox/2"

    def log_message(self, fmt, *args):  # quiet; the core has its own event log
        pass
    def _json(self, obj, code=200, lang=True):
        if lang and isinstance(obj, dict):
            obj = dict(obj, lang=i18n.lang())      # 回话里带上当前语言，客户端知道盒子现在说什么语言
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
    def _mcp(self, body, station: str):
        """MCP Streamable HTTP（只用到「POST 一条或一批 JSON-RPC、直接回 JSON」那一半，不开 SSE 流）。
        工位从 URL 的 ?station= 来；角色 / 运行器现查 stations.json，所以改了角色不用重写客户端条目。"""
        from . import mcp_stdio
        st = config.station(station) if station else None
        role = (st or {}).get("role", "member")

        def call(name, args):
            return self.core.call(name, station, args, transport=self._link(station))

        msgs = body if isinstance(body, list) else [body]
        self._note_link(station, msgs)
        lg = self.core.d.lang_of(station)
        outs = [r for r in (mcp_stdio.handle(m, station, role, call, lg) for m in msgs if isinstance(m, dict)) if r is not None]
        if not outs:                                       # 全是通知 / 回复：202、没有正文
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        return self._json(outs if isinstance(body, list) else outs[0], lang=False)
    def _link(self, station: str) -> str:
        """/这个工位是怎么连上来的："mcp" = 客户端发过 initialize（连接设置生效）；"http" = 那段话里的 HTTP 兜底。"""
        inited = self.core.d.__dict__.setdefault("mcp_inited", set())
        return "mcp" if station in inited else "http"
    def _note_link(self, station: str, msgs: list) -> None:
        """记下这个工位是怎么连上来的。MCP 客户端一定先发 initialize；那段话里的 HTTP 兜底直接 tools/call()。
        首领走的是兜底，说明它的客户端里 boxbox 的 MCP 没连上——上岗窗口要直接告诉用户怎么开，不能指望模型转告。
        顺便记下「真正连上来的是哪一家 AI 软件」（initialize 里报的 clientInfo.name），不猜配置。"""
        methods = {m.get("method") for m in msgs if isinstance(m, dict)}
        if not station or not methods & {"initialize", "tools/call"}:
            return
        d = self.core.d
        inited = d.__dict__.setdefault("mcp_inited", set())
        was_inited = station in inited
        if "initialize" in methods:
            inited.add(station)
        link = "mcp" if station in inited else "http"
        kv = d.store.kv_get("station_link") or {}
        if kv.get(station) != link:
            kv[station] = link
            d.store.kv_set("station_link", kv)
        self._note_client(station, msgs, was_inited)
    def _note_client(self, station: str, msgs: list, was_inited: bool) -> None:
        """把「真正连上来的那一家」记进运行状态（kv，不碰 stations.json，也不动配置）。
        initialize 里报的 clientInfo.name → cursor / claude-code / codex / other；
        没发 initialize 直接 tools/call（那段话里的 HTTP 兜底）→ other-direct。"""
        code = ""
        for m in msgs:
            if not isinstance(m, dict) or m.get("method") != "initialize":
                continue
            info = (m.get("params") or {}).get("clientInfo") or {}
            code = mcp_client.classify(info.get("name"))
        if not code:
            if was_inited or not any(m.get("method") == "tools/call" for m in msgs if isinstance(m, dict)):
                return
            code = "other-direct"          # 没 initialize 直接 tools/call
        kv = self.core.d.store.kv_get("station_client") or {}
        old = kv.get(station)
        if old == code:
            return
        if code == "other-direct" and old and old != "other-direct":
            return                 # 正经握手过：别把「真连上来的那一家」降级成直连
        kv[station] = code
        self.core.d.store.kv_set("station_client", kv)
    def _file(self, path: pathlib.Path):
        try:
            data = path.read_bytes()
        except OSError:
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if ctype.startswith("text/html"):
            self.send_header("Set-Cookie", "bx-lang=%s; Path=/; SameSite=Lax" % i18n.lang())
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _safe_under(root: pathlib.Path, rel: str) -> pathlib.Path | None:
        p = (root / rel.lstrip("/")).resolve()
        try:
            p.relative_to(root.resolve())
        except ValueError:
            return None
        return p if p.is_file() else None

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        d = self.core.d
        if u.path == "/mcp":                                     # 不开服务端推送流（Streamable HTTP 允许回 405）
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        try:
            if u.path == "/office":                          # the chibicat office view (office/office.html) fed by /api/office
                if "live" not in q:
                    q2 = {k: v[0] for k, v in q.items()}      # 跳转时把别的参数带上（?lang=en 之类，不然重定向就没了）
                    q2["live"] = "1"
                    self.send_response(302)
                    self.send_header("Location", "/office?" + urllib.parse.urlencode(q2))
                    self.end_headers()
                    return None
                p = config.BUNDLE / "office" / "office.html"
                return self._file(p) if p.is_file() else self._json({"error": i18n.t("api.office_missing", i18n.lang())}, 404)
            if u.path in PAGES:
                p = PKG_STATIC / PAGES[u.path]
                if p.is_file():
                    return self._file(p)
                return self._json({"error": i18n.t("api.page_missing", i18n.lang(), path=u.path, file=PAGES[u.path]), "api": "/api/meta"}, 404)
            if u.path in LEGAL:                                # 许可和隐私声明（设置页「许可和隐私」）：纯文本原样给
                p = config.BUNDLE / LEGAL[u.path]
                want = (q.get("lang") or [""])[0] or i18n.lang()   # 页面上问的语言优先：声明跟着界面走
                if want == "en":                              # 英文界面给英文版声明（没有英文版的照旧给中文那份）
                    alt = p.with_name(p.stem + ".en" + p.suffix)
                    if alt.is_file():
                        p = alt
                if not p.is_file():
                    return self._json({"error": i18n.t("api.legal_missing", i18n.lang(), path=LEGAL[u.path])}, 404)
                data = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return None
            if u.path in ("/favicon.ico", "/apple-touch-icon.png"):
                p = self._safe_under(ICON_DIR, u.path.lstrip("/"))
                return self._file(p) if p else self._json({"error": "not found"}, 404)
            if u.path.startswith("/assets/icon/"):
                p = self._safe_under(ICON_DIR, u.path[len("/assets/icon/"):])
                return self._file(p) if p else self._json({"error": "not found"}, 404)
            if u.path == "/static/cats.js":                   # 办公室的画猫脚本给工位页复用（不复制一份）
                p = config.BUNDLE / "office" / "build" / "cats.js"
                return self._file(p) if p.is_file() else self._json({"error": i18n.t("api.cats_missing", i18n.lang())}, 404)
            if u.path.startswith("/static/"):
                p = self._safe_under(PKG_STATIC, u.path[len("/static/"):])
                return self._file(p) if p else self._json({"error": "not found"}, 404)
            if u.path.startswith("/vendor/"):
                p = self._safe_under(VENDOR_STATIC, u.path[len("/vendor/"):])
                return self._file(p) if p else self._json({"error": "not found"}, 404)
            if u.path == "/api/meta":
                return self._json(_meta(d))
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)
        with i18n.override(_req_lang(q)):
            return http_api.handle_get(self, u, q)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin.rstrip("/") not in ("http://127.0.0.1:%d" % self.server.server_port, "http://localhost:%d" % self.server.server_port):
            return self._json({"ok": False, "code": "forbidden", "text": "bad origin"}, 403)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
        except ValueError:
            return self._json({"ok": False, "code": "bad_json"}, 400)
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        with i18n.override(_req_lang(q)):
            return http_api.handle_post(self, u, body)

class _Server(ThreadingHTTPServer):
    allow_reuse_address = False   # Windows: SO_REUSEADDR lets a second core bind the same port silently -> refuse instead
    request_queue_size = 64       # 默认 5 太窄：页面一开就并发发十几个请求（设置页 / 办公室轮询），
def _open(handler, port: int) -> ThreadingHTTPServer:
    """开服务器。port=0（让系统随便挑一个）时躲开浏览器禁用端口：挑中 1719、6665 这种就关掉重绑。

    Chromium 的 kRestrictedPorts 里的端口浏览器不让访问，Playwright 打不开（ERR_UNSAFE_PORT），
    测试就会偶发挂。最多试 PORT_REBIND_TRIES 次。
    """
    if port:
        return _Server(("127.0.0.1", port), handler)
    for _ in range(PORT_REBIND_TRIES):
        httpd = _Server(("127.0.0.1", 0), handler)
        if not is_restricted(int(httpd.server_address[1])):
            return httpd
        httpd.server_close()          # 挑中禁用端口：关掉重挑
    return _Server(("127.0.0.1", 0), handler)   # 试了 20 次还是挑中禁用端口：再开一个（总得有个端口）
def serve(core: Core, port: int, block: bool = True) -> ThreadingHTTPServer:
    # 核心绑在「这个服务器自己的 Handler 子类」上，不写在 Handler 这个类上：
    # 写成类属性的话，同一个进程里起第二个核心就会把 Handler.core 抢走，
    # 先前那个端口上的请求改由后一个核心的库回答（看板读到别人的卡、库已经关了就 500）。
    handler = type("BoundHandler", (Handler,), {"core": core})
    httpd = _open(handler, port)
    httpd.daemon_threads = True
    if block:
        httpd.serve_forever()
    else:
        threading.Thread(target=httpd.serve_forever, name="boxbox-http", daemon=True).start()
    return httpd
