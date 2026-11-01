"""v0.1 shell: tray icon + embedded dashboard window (工作计划 4.1 / 4.2, 架构设计 §17.1).

This is the ONLY module that imports the two GUI dependencies (pystray, pywebview; Pillow comes with pystray).
The core runs in-process on 127.0.0.1:<core_port>; everything else keeps working without this file.

    python -m boxbox tray            # start core + tray; window hidden until clicked
    python -m boxbox tray --show     # also show the window at startup

Tray menu: 打开看板 · 在跑 N · 工位 ▸ · 上岗（Onboard）· 设置 · 自检 · 打开日志文件夹 · 开机启动 ☑ · 退出
Icon: pixel box; red dot only when the core is unreachable（提醒不再让图标变红，提醒看办公室提示条）; "running" variant when something is in flight.
Real pixel icons (0.6) can replace _draw_icon() later; keep the three states.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from . import __version__, config, i18n
from .facades.http_const import LEADER_EVENT_KINDS
from .store import Store

IS_WIN = sys.platform.startswith("win")
APP_NAME = "agent-boxbox"        # 内部 id：开机自启的 .cmd 文件名、托盘图标名，别改（改了老用户的自启就失效）
POLL_S = 5


# ---------- icon ----------
def _draw_icon(state: str, size: int = 64):
    """Tray icon: assets/icon/icon-64.png (方案 A) with a state badge: 'normal' | 'red' (核心连不上) | 'running' (在跑).
    Falls back to a code-drawn pixel box if the asset is missing."""
    from PIL import Image, ImageDraw
    src = config.BUNDLE / "assets" / "icon" / ("icon-%d.png" % size)
    try:
        img = Image.open(src).convert("RGBA")
        if img.size != (size, size):
            img = img.resize((size, size))
    except Exception:  # noqa: BLE001 - asset missing: placeholder box
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d0 = ImageDraw.Draw(img)
        u0 = size // 16
        d0.rectangle((2 * u0, 3 * u0, 14 * u0, 14 * u0), fill=(210, 160, 90, 255), outline=(90, 60, 30, 255), width=u0)
    d = ImageDraw.Draw(img)
    u = size // 16
    if state == "red":        # 核心连不上
        d.ellipse((10 * u, 0, 16 * u, 6 * u), fill=(220, 50, 50, 255), outline=(255, 255, 255, 255), width=u // 2 or 1)
    elif state == "running":  # 有卡在跑
        d.ellipse((10 * u, 0, 16 * u, 6 * u), fill=(70, 170, 100, 255), outline=(255, 255, 255, 255), width=u // 2 or 1)
    return img


# ---------- core access ----------
def _get(port: int, path: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ---------- autostart (4.2): a .cmd in the user's Startup folder, no COM / pywin32 needed ----------
def _startup_dir() -> pathlib.Path | None:
    if not IS_WIN:
        return None
    base = os.environ.get("APPDATA")
    return pathlib.Path(base, "Microsoft", "Windows", "Start Menu", "Programs", "Startup") if base else None


def _startup_file() -> pathlib.Path | None:
    d = _startup_dir()
    return d / ("%s.cmd" % APP_NAME) if d else None


def title_text(meta: dict, badge: dict | None = None, lang: str | None = None) -> str:
    """托盘图标的悬停提示：带版本号。不再数「等你」，提醒统一看 /api/meta 的 alerts。"""
    lg = lang or i18n.lang()
    head = "%s %s" % (display_name(lg), __version__)
    if not meta:
        return "%s · %s" % (head, i18n.t("tray.title.down", lg))
    return "%s · %s" % (head, i18n.t("tray.title.running", lg, n=meta.get("running", 0)))


def display_name(lang: str | None = None) -> str:
    """对用户显示的名字：中文界面「猫猫盒子」，英文界面 agentboxbox。"""
    return i18n.t("tray.display_name", lang or i18n.lang())


def autostart_enabled() -> bool:
    f = _startup_file()
    return bool(f and f.exists())


def set_autostart(on: bool) -> None:
    f = _startup_file()
    if not f:
        return
    if not on:
        try:
            f.unlink()
        except OSError:
            pass
        return
    if getattr(sys, "frozen", False):                       # PyInstaller exe
        cmd = '"%s" tray' % sys.executable
    else:
        cmd = '"%s" -m boxbox tray' % sys.executable
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("@echo off\r\ncd /d \"%s\"\r\nstart \"\" /min %s\r\n" % (config.ROOT, cmd), encoding="utf-8")


# ---------- shell ----------
def _promote_tray_icon() -> None:
    """Windows 11 parks every new tray icon in the hidden overflow (the ^ chevron), so people think there is no icon.
    Explorer keeps per-exe settings in HKCU\\Control Panel\\NotifyIconSettings\\<id>; IsPromoted=1 is what the
    Settings page writes when you switch the icon on. Best effort, exe builds only (python.exe would be too broad)."""
    if not IS_WIN or not getattr(sys, "frozen", False):
        return
    try:
        import winreg
        me = os.path.normcase(os.path.abspath(sys.executable))
        running = _running_our_exe_paths()
        stale = []
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\NotifyIconSettings") as root:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(root, name, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                        path, _ = winreg.QueryValueEx(k, "ExecutablePath")
                        if os.path.normcase(os.path.abspath(str(path))) != me:
                            if is_stale_tray_entry(str(path), running):
                                stale.append(name)
                            continue
                        try:
                            cur, _ = winreg.QueryValueEx(k, "IsPromoted")
                        except OSError:
                            cur = None
                        if cur != 1:
                            winreg.SetValueEx(k, "IsPromoted", 0, winreg.REG_DWORD, 1)
                except OSError:
                    continue
            for name in stale:                            # 枚举完再删，边枚举边删会跳号
                try:
                    winreg.DeleteKey(root, name)
                except OSError:
                    pass
    except Exception:  # noqa: BLE001
        pass


_OUR_EXE = re.compile(r"^(agentboxbox[\w.+-]*|boxbox)\.exe$", re.I)


def _running_our_exe_paths() -> set[str]:
    """现在还在跑的猫猫盒子 exe 的完整路径（normcase 后的小写）。只有 Windows 知道这些，
    别的平台上没有「在跑」这回事，就当没有在跑的。"""
    if not IS_WIN:
        return set()
    try:
        import ctypes
        from ctypes import wintypes

        class _Entry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260),
            ]

        kernel32 = ctypes.windll.kernel32
        snap = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)      # TH32CS_SNAPPROCESS
        if snap == -1:
            return set()
        out: set[str] = set()
        try:
            entry = _Entry()
            entry.dwSize = ctypes.sizeof(_Entry)
            more = kernel32.Process32FirstW(snap, ctypes.byref(entry))
            while more:
                if _OUR_EXE.match(str(entry.szExeFile)):
                    handle = kernel32.OpenProcess(0x1000, False, entry.th32ProcessID)   # QUERY_LIMITED_INFORMATION
                    if handle:
                        try:
                            buf = ctypes.create_unicode_buffer(32768)
                            size = wintypes.DWORD(len(buf))
                            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                                out.add(os.path.normcase(os.path.abspath(buf.value)))
                        finally:
                            kernel32.CloseHandle(handle)
                more = kernel32.Process32NextW(snap, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snap)
        return out
    except Exception:  # noqa: BLE001
        return set()


def is_stale_tray_entry(path: str, running: set[str]) -> bool:
    """Explorer 按 exe 路径各记一条托盘图标设置，exe 删了也不清：每升一次版本（文件名带版本号）、每换个目录就多一条，
    「设置 → 任务栏 → 其他系统托盘图标」里会排出一串 agentboxbox。只清我们自己的那些：exe 已经不在，
    或者 exe 还在但没在跑（别处那个旧盒子已经关了，它那条也没用了）。"""
    if not _OUR_EXE.match(os.path.basename(path)):
        return False
    if not os.path.exists(path):
        return True
    return os.path.normcase(os.path.abspath(path)) not in running


# ---------- desktop notifications ----------
# 首领在用户自己的 AI 软件里，那边的会话闲着时后台命令结束也叫不醒它：盒子自己弹系统通知，
# 用户看到了去会话里跟首领说一声。哪些事件该让用户知道，跟给首领拼事件行用同一套判断。
NOTIFY_POLL_S = 5        # 多久读一次新事件
NOTIFY_MERGE_S = 10      # 这么短时间里来的几条合成一条，别连着弹

_NOTIFY_ONE = {
    "returned": "tray.notify.returned",
    "pending": "tray.notify.pending",
    "not_started": "tray.notify.not_started",
    "failed": "tray.notify.failed",
    "stuck": "tray.notify.stuck",
    "issue": "tray.notify.issue",
}
_NOTIFY_MANY = {
    "returned": "tray.notify.many_returned",
    "pending": "tray.notify.many_pending",
    "not_started": "tray.notify.many_not_started",
    "failed": "tray.notify.many_failed",
    "stuck": "tray.notify.many_stuck",
    "issue": "tray.notify.many_issue",
}
_NOTIFY_TAIL = {"returned": "tray.notify.tail_returned"}
_NOTIFY_TAIL_DEFAULT = "tray.notify.tail"


def _ev_data(ev: dict) -> dict:
    """事件里带的结构化数据（json 列）；读不出来就当空的。"""
    try:
        data = json.loads(ev.get("json") or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _notify_kind(store, ev: dict) -> str:
    """一条事件 → 要不要弹通知、弹哪一类。按事件种类和数据判断，不看事件文字（文字跟着语言变）。"""
    kind = str(ev.get("kind") or "")
    data = _ev_data(ev)
    tid = str(ev.get("task_id") or "")
    if kind == "reviewing":
        return "returned"                                    # 交回：等首领验收
    if kind == "review":
        return "" if str(data.get("verdict") or "return") == "accept" else "pending"
    if kind == "failed":
        return "not_started" if (tid and not store.runs_for_task(tid)) else "failed"
    if kind == "report":
        status = str(data.get("status") or "")
        if status == "blocked":
            return "stuck"
        if status == "issue":
            return "issue"
        # 老事件没有结构化标记：按当下语言的标记词认一下
        text = str(ev.get("text") or "")
        lg = i18n.lang()
        if i18n.t("ev.report.how.blocked", lg) in text:
            return "stuck"
        if i18n.t("ev.report.how.issue", lg) in text:
            return "issue"
    return ""


def _notify_item(store, ev: dict) -> tuple[str, str, str, str] | None:
    """一条事件 → (类别, 工位名, 卡号, 标题前 30 字)；不用用户管的返回 None。
    文案只带工位名、卡号、标题，不带回报正文、不带任何 key。"""
    tid = str(ev.get("task_id") or "")
    t = store.get_task(tid) if tid else None
    title = str((t or {}).get("title") or "")
    key = _notify_kind(store, ev)
    if not key:
        return None
    return key, str(ev.get("station") or ""), tid, title[:30]


class TrayNotifier:
    """托盘的后台通知线程：按事件序号追 store 里的新事件，攒一小阵合成一条弹出去。
    只有托盘模式起它（serve 没有托盘，不起也不报错）。"""

    def __init__(self, store, icon):
        self.store = store
        self.icon = icon
        self.after = store.last_event_id()     # 从现在开始，不把启动前的历史弹出来
        self.pending: list[tuple[str, str, str, str]] = []
        self.first_pending = 0.0
        self.stop_flag = threading.Event()
        self.thread: threading.Thread | None = None

    def poll(self) -> tuple[str, str] | None:
        """读一轮新事件，返回该弹的 (标题, 正文)。这一轮有新的就先攒着（可能还有下一条），
        没有了或攒过合并窗口才弹。"""
        added = False
        try:
            for ev in self.store.events_after(self.after, LEADER_EVENT_KINDS, limit=50):
                self.after = max(self.after, int(ev.get("id") or 0))
                it = _notify_item(self.store, ev)
                if it:
                    if not self.pending:
                        self.first_pending = time.time()
                    self.pending.append(it)
                    added = True
        except Exception:  # noqa: BLE001 - 退出时库正被关掉：这轮跳过
            return None
        if not config.settings().get("tray_notify", True):
            self.pending = []                   # 关了就不攒也不补弹，重开时从新的开始
            return None
        hold = added and time.time() - self.first_pending < NOTIFY_MERGE_S
        return None if (hold or not self.pending) else self._merge()

    def _merge(self) -> tuple[str, str]:
        lg = i18n.lang()
        items, self.pending = self.pending, []
        if len(items) == 1:
            key, who, tid, title = items[0]
            head = " ".join(x for x in (tid, title) if x)
            body = i18n.t("tray.notify.body", lg, head=head) if head else ""
            return i18n.t(_NOTIFY_ONE[key], lg, who=who),                 body + i18n.t(_NOTIFY_TAIL.get(key, _NOTIFY_TAIL_DEFAULT), lg)
        keys = {k for k, *_ in items}
        if len(keys) == 1:
            title = i18n.t(_NOTIFY_MANY[next(iter(keys))], lg, n=len(items))
        else:
            title = i18n.t("tray.notify.mixed", lg, n=len(items))
        return title, i18n.t(_NOTIFY_TAIL_DEFAULT, lg)

    def _notify(self, title: str, body: str) -> None:
        if self.icon is None:
            return
        try:
            self.icon.notify(body, title)
        except Exception:  # noqa: BLE001 - 系统不收通知（比如 Linux 没服务）：跳过就好
            pass

    def tick(self) -> None:
        out = self.poll()
        if out:
            self._notify(*out)

    def run(self) -> None:
        while not self.stop_flag.is_set():
            self.tick()
            self.stop_flag.wait(NOTIFY_POLL_S)

    def start(self) -> None:
        self.thread = threading.Thread(target=self.run, name="boxbox-tray-notify", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_flag.set()
        if self.thread is not None:
            self.thread.join(3)
            self.thread = None


class Shell:
    def __init__(self, port: int, show: bool = False, on_quit=None, core_stopped: threading.Event | None = None,
                 store=None):
        self.port = port
        self.on_quit = on_quit                # 托盘「退出」时收核心（自己起的核心才有；接上别人的核心时是 None）
        self.core_stopped = core_stopped      # 核心自己收工了（app._stop_event）→ 窗口和托盘也退
        self.store = store                    # 桌面通知按事件序号追这个库（serve 模式没有，不起通知）
        self.notifier: TrayNotifier | None = None
        self.url = "http://127.0.0.1:%d/" % port
        self.window = None
        self.icon = None
        self.state = "normal"
        self.meta: dict = {}
        self.board: list = []
        self.stop_flag = threading.Event()
        self.show_at_start = show
        self.webview_ok = False
        self._tray_tip_shown = False
        self._quit_lock = threading.Lock()     # 退出确认框同一时间只开一个

    # ---- window ----
    def open_board(self, path: str = "/"):
        if self.window is not None and self.webview_ok:
            try:
                if path != "/":
                    self.window.load_url(self.url.rstrip("/") + path)
                self.window.show()
                try:
                    self.window.restore()                 # hidden while minimised -> Show() alone brings back a minimised window
                except Exception:  # noqa: BLE001
                    pass
                return
            except Exception:  # noqa: BLE001
                pass
        webbrowser.open(self.url.rstrip("/") + path)

    def _to_tray(self, tip: str | None):
        """Hide the window; the core keeps running behind the tray icon. First time: a balloon so nobody thinks it quit."""
        try:
            self.window.hide()
        except Exception:  # noqa: BLE001
            pass
        if tip and not self._tray_tip_shown and self.icon is not None:
            self._tray_tip_shown = True
            try:
                self.icon.notify(tip, display_name())
            except Exception:  # noqa: BLE001
                pass

    def _on_closing(self):
        """Close button (X) = minimise to tray (§17.1); only the tray's 退出 really quits.
        退出时 quit() 先立 stop_flag 再 destroy：destroy 也会走到这里，这时必须放行，不然窗口关不掉、进程一直挂着。"""
        if self.stop_flag.is_set():
            return True
        self._to_tray(i18n.t("tray.to_tray.close", i18n.lang()))
        return False

    def _on_minimized(self):
        """Minimise button (–) = also to the tray; done off the WinForms resize handler so we don't hide mid-event."""
        threading.Timer(0.05, self._to_tray, args=(i18n.t("tray.to_tray.min", i18n.lang()),)).start()

    # ---- tray ----
    def _menu(self):
        import pystray
        lg = i18n.lang()
        m = self.meta or {}
        running = m.get("running", 0)
        rows = [pystray.MenuItem("%s · %s%s" % (b.get("id"), b.get("word", "?"), (": " + b["title"]) if b.get("title") else ""),
                                    None, enabled=False) for b in (self.board or [])]
        stations = rows or [pystray.MenuItem(i18n.t("tray.menu.no_stations", lg), None, enabled=False)]
        return pystray.Menu(
            pystray.MenuItem(i18n.t("tray.menu.board", lg), lambda: self.open_board("/"), default=True),
            pystray.MenuItem(i18n.t("tray.menu.running", lg, n=running), lambda: self.open_board("/"), enabled=False),
            pystray.MenuItem(i18n.t("tray.menu.stations", lg), pystray.Menu(*stations)),
            pystray.MenuItem(i18n.t("tray.menu.onboard", lg), lambda: self.open_board("/onboard")),
            pystray.MenuItem(i18n.t("tray.menu.settings", lg), lambda: self.open_board("/settings")),
            pystray.MenuItem(i18n.t("tray.menu.doctor", lg), lambda: self.open_board("/doctor")),
            pystray.MenuItem(i18n.t("tray.menu.logs", lg), self._open_logs),
            pystray.MenuItem(i18n.t("tray.menu.autostart", lg), self._toggle_autostart, checked=lambda item: autostart_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(i18n.t("tray.menu.version", lg, v=__version__), None, enabled=False),
            pystray.MenuItem(i18n.t("tray.menu.quit", lg), self._menu_quit),
        )

    def _open_logs(self):
        p = config.DATA / "logs"
        p.mkdir(parents=True, exist_ok=True)
        if IS_WIN:
            os.startfile(str(p))  # noqa: S606 - opens Explorer on a local folder we created
        else:
            subprocess.Popen(["xdg-open", str(p)])

    def _toggle_autostart(self):
        set_autostart(not autostart_enabled())

    def _poll(self):
        """Refresh icon state + menu numbers from the core every POLL_S seconds."""
        while not self.stop_flag.is_set():
            meta = _get(self.port, "/api/meta") or {}
            board = (_get(self.port, "/api/stations") or {}).get("stations") or []
            self.meta, self.board = meta, board
            if not meta:
                state = "red"                                     # 红色只留给「核心连不上」
            else:
                state = "running" if meta.get("running") else "normal"
            if self.icon is not None:
                try:
                    if state != self.state:
                        self.icon.icon = _draw_icon(state)
                        self.state = state
                    self.icon.menu = self._menu()
                    self.icon.title = title_text(meta)
                except Exception:  # noqa: BLE001
                    pass
            self.stop_flag.wait(POLL_S)

    def _run_tray(self):
        import pystray
        self.icon = pystray.Icon(APP_NAME, _draw_icon("normal"), display_name(), self._menu())
        threading.Thread(target=self._poll, name="boxbox-tray-poll", daemon=True).start()
        threading.Timer(3.0, _promote_tray_icon).start()  # Explorer writes the NotifyIconSettings entry once the icon is added
        self.icon.run(setup=self._icon_ready)              # blocks this (non-main) thread until icon.stop()

    def _icon_ready(self, icon):
        """托盘图标进了系统托盘再开通知线程：图标还没建好时弹通知会失败，那条就白丢了。"""
        icon.visible = True
        self.start_notifier()

    def start_notifier(self):
        """桌面通知只在托盘模式起：没有 store（serve）或图标还没建好就不起，也不报错。"""
        if self.store is None or self.icon is None:
            return
        self.notifier = TrayNotifier(self.store, self.icon)
        self.notifier.start()

    def _menu_quit(self, *_):
        """托盘菜单「退出」。确认框放到单独线程里弹：pystray 的消息循环不能卡在框里
        （卡住时托盘不响应、框和托盘抢消息，点「否」点不动）。同一时间只弹一个。"""
        if not self._quit_lock.acquire(blocking=False):
            return                                        # 框已经开着：别再叠一个
        def _go():
            try:
                if self._confirm_quit():
                    self.quit(ask=False)
            finally:
                self._quit_lock.release()
        threading.Thread(target=_go, name="boxbox-quit-ask", daemon=True).start()

    def _confirm_quit(self) -> bool:
        """有卡在跑才问。按钮是「确定 / 取消」：右上角 X 和 Esc 都等于取消（是 / 否 那种框 X 是灰的、Esc 没反应）。"""
        running = int((self.meta or {}).get("running") or 0)
        if not (running and IS_WIN):
            return True
        text = i18n.t("tray.quit.confirm", i18n.lang(), n=running)
        flags = 0x1 | 0x30 | 0x100 | 0x10000 | 0x40000   # MB_OKCANCEL | MB_ICONWARNING | MB_DEFBUTTON2 | MB_SETFOREGROUND | MB_TOPMOST
        return _ask(text, flags) == 1                   # IDOK；_ask 出错返回 0 = 不退

    def quit(self, ask: bool = True):
        if ask and not self._confirm_quit():
            return
        if self.notifier is not None:         # 先停通知线程再关库，别让它在关着的库上查
            self.notifier.stop()
            self.notifier = None
        self.stop_flag.set()
        if self.on_quit is not None:                     # 先收核心（结束 Pi 进程、关库），不靠窗口关掉之后的 finally
            try:
                self.on_quit()
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(i18n.t("tray.stderr.quit_err", i18n.lang(), err=e) + "\n")
        try:
            if self.icon is not None:
                self.icon.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self.window is not None and self.webview_ok:
                self.window.destroy()
        except Exception:  # noqa: BLE001
            pass
        # 兜底：窗口 / 托盘线程万一卡住，8 秒后直接结束进程（核心上面已经收好了），exe 文件不能一直被占着
        t = threading.Timer(8.0, os._exit, args=(0,))
        t.daemon = True
        t.start()

    # ---- main ----
    def run(self):
        """pywebview owns the main thread (Windows requirement); pystray runs on a worker thread."""
        tray = threading.Thread(target=self._run_tray, name="boxbox-tray", daemon=True)
        if self.core_stopped is not None:
            # 核心被 POST /api/shutdown 收了（冒烟测试 / 以后的「从页面退出」）：托盘和窗口跟着走同一条退出路
            def _watch():
                self.core_stopped.wait()
                if not self.stop_flag.is_set():
                    self.quit(ask=False)
            threading.Thread(target=_watch, name="boxbox-core-stopped", daemon=True).start()
        try:
            import webview
            self.window = webview.create_window(display_name(), self.url, width=1180, height=760, hidden=not self.show_at_start)
            self.window.events.closing += self._on_closing
            self.window.events.minimized += self._on_minimized
            self.webview_ok = True
            webview.start(tray.start)                     # tray thread starts once the GUI loop is up
        except Exception as e:  # noqa: BLE001 - no WebView2 / no GUI: tray only, board opens in the browser
            if self.stop_flag.is_set():
                return                                    # 正在退出时窗口才初始化完 / 被打断（WebView2 报 E_ABORT）：别再起一个托盘
            sys.stderr.write(i18n.t("tray.stderr.no_webview", i18n.lang(), err=e) + "\n")
            self.webview_ok = False
            if self.show_at_start:
                webbrowser.open(self.url)
            self._run_tray()                              # blocks until 退出


def main(show: bool = False, port: int | None = None) -> int:
    from . import app
    if IS_WIN and getattr(sys, "frozen", False) and not os.environ.get("BOXBOX_KEEP_CONSOLE"):
        # Double-clicked exe: drop the console window, keep the tray. After FreeConsole the old stdout/stderr handles
        # are dead and the first print() would raise OSError and kill the process silently ("没反应") -> send all
        # output to data/logs/tray.log instead.
        try:
            import ctypes
            ctypes.windll.kernel32.FreeConsole()
        except Exception:  # noqa: BLE001
            pass
        try:
            log_dir = config.DATA / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            sys.stdout = sys.stderr = open(log_dir / "tray.log", "a", encoding="utf-8", buffering=1)
            sys.stderr.write("\n== boxbox tray %s ==\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:  # noqa: BLE001
            sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None or sys.stdout is None:
        # 无控制台的 exe 又设了 BOXBOX_KEEP_CONSOLE 却没重定向输出（测试脚本这么起过）：stdout/stderr 是 None，
        # 第一句 write 就抛错，被下面当成「启动失败」弹框挂住进程。给个空的去处。
        devnull = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = sys.stdout or devnull
        sys.stderr = sys.stderr or devnull
    try:
        return _main(show, port, app)
    except Exception as e:  # noqa: BLE001 - never die silently: show the error, log the traceback
        import traceback
        traceback.print_exc()
        if IS_WIN:
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    None, i18n.t("tray.start_failed", i18n.lang(), why=e, path=config.DATA / "logs" / "tray.log"),
                    display_name(), 0x10)
            except Exception:  # noqa: BLE001
                pass
        return 1


def _port_owner_pid(port: int) -> int | None:
    """谁在 127.0.0.1:<port> 上监听（Windows：netstat -ano）。拿不到返回 None。"""
    if not IS_WIN:
        return None
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except Exception:  # noqa: BLE001
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1].endswith(":%d" % port) and parts[3].upper() == "LISTENING":
            try:
                return int(parts[4])
            except ValueError:
                return None
    return None


def end_old_core(port: int, app) -> bool:
    """结束端口上那个别的版本的核心：先请它自己收工（0.3 起有 /api/shutdown），不理就按进程树结束。返回端口是否空出来了。"""
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/api/shutdown" % port, data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:  # noqa: BLE001 - 0.2 没有这个接口，直接走下面
        pass
    for _ in range(20):
        if not app.core_alive(port):
            return True
        time.sleep(0.25)
    pid = _port_owner_pid(port)
    if pid and pid != os.getpid():
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(20):
        if not app.core_alive(port):
            return True
        time.sleep(0.25)
    return False


def _ask(text: str, flags: int) -> int:
    if not IS_WIN:
        return 0
    try:
        import ctypes
        return int(ctypes.windll.user32.MessageBoxW(None, text, display_name(), flags))
    except Exception:  # noqa: BLE001
        return 0


_INSTANCE_MUTEX = None    # 进程活着就一直攥着；进程退出时系统自己放掉


def claim_single_instance(port: int, wait_s: float = 0.0) -> bool:
    """同一个端口只许开一个托盘：抢到返回 True，已经有一个开着返回 False。不是 Windows 一律放行。
    wait_s：旧的那个正在退出时等它放手。"""
    global _INSTANCE_MUTEX
    if not IS_WIN or _INSTANCE_MUTEX:
        return True
    try:
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        deadline = time.time() + wait_s
        while True:
            h = k32.CreateMutexW(None, False, "Local\\agentboxbox-tray-%d" % port)
            if not h:
                return True
            if ctypes.get_last_error() != 183:          # ERROR_ALREADY_EXISTS
                _INSTANCE_MUTEX = h
                return True
            k32.CloseHandle(ctypes.c_void_p(h))
            if time.time() >= deadline:
                return False
            time.sleep(0.5)
    except (AttributeError, OSError):
        return True


def show_running(port: int, wait_s: float = 20.0) -> bool:
    """叫已经开着的那个把窗口弹出来；它还在起核心就等一会儿。叫不到返回 False。"""
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)   # 让它能把窗口提到最前面（ASFW_ANY）
        except (AttributeError, OSError):
            pass
    deadline = time.time() + wait_s
    while True:
        try:
            req = urllib.request.Request("http://127.0.0.1:%d/api/window/show" % port, data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as r:
                return bool(json.loads(r.read().decode("utf-8")).get("ok"))
        except urllib.error.HTTPError:
            return False                                 # 核心在，但它没有窗口（serve 起的）
        except Exception:  # noqa: BLE001 - 那个还在起核心，等一会儿
            if time.time() >= deadline:
                return False
            time.sleep(0.5)


def _show_other(port: int) -> int:
    """已经开着一个：叫它弹窗口；叫不到就在浏览器里打开首页，总之用户点了就有东西出来。"""
    sys.stderr.write(i18n.t("tray.stderr.already_open", i18n.lang(), port=port) + "\n")
    if not show_running(port):
        webbrowser.open("http://127.0.0.1:%d/" % port)
    return 0


def _attach_store():
    """接上端口上已有的核心时也开一份库连接给桌面通知用；开不了就不做通知，别挡住看板。"""
    try:
        return Store(config.DATA / "boxbox.db")
    except Exception:  # noqa: BLE001
        return None


def _main(show: bool, port: int | None, app) -> int:
    want = int(port or config.settings().get("core_port", 8878))
    if app.core_alive(want):
        meta = _get(want, "/api/meta") or {}
        other = str(meta.get("app_version") or "")
        if other == __version__:
            if not claim_single_instance(want):
                return _show_other(want)                  # 双击了两次 exe：叫开着的那个弹窗口，不再起第二个托盘
            # 同一个版本的核心已经在跑、但没有托盘（另开了 serve）：托盘接上它，不起第二个核心
            sys.stderr.write(i18n.t("tray.stderr.attached", i18n.lang(), port=want, other=other) + "\n")
            st = _attach_store()
            try:
                Shell(want, show=show, store=st).run()
            finally:
                if st is not None:
                    st.close()
            return 0
        # 别的版本（比如没退干净的 0.2）：不能悄悄接上去，不然用户看到的是旧版本的页面
        sys.stderr.write(i18n.t("tray.stderr.other_core", i18n.lang(), port=want, other=other or "0.2") + "\n")
        ans = _ask(i18n.t("tray.old_core", i18n.lang(), port=want,
                             other=other or i18n.t("tray.version.older", i18n.lang()), cur=__version__),
                   0x1 | 0x20 | 0x10000 | 0x40000)   # MB_OKCANCEL | MB_ICONQUESTION | 前台 | 置顶
        if ans != 1:                                      # IDOK
            return 0
        if not end_old_core(want, app):
            _ask(i18n.t("tray.old_core.gone", i18n.lang(), port=want), 0x10)
            return 2
        sys.stderr.write(i18n.t("tray.stderr.old_started", i18n.lang(), v=__version__) + "\n")
        claim_single_instance(want, wait_s=10.0)          # 旧版本的托盘跟着它的核心一起退，等它放手
    elif not claim_single_instance(want):
        return _show_other(want)                          # 另一个刚双击的还在起核心：等它起好、叫它弹窗口
    try:
        store, d, httpd, wd, port = app.start(want)
    except RuntimeError as e:
        sys.stderr.write(str(e) + "\n")
        if IS_WIN:
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, str(e), display_name(), 0x10)
            except Exception:  # noqa: BLE001
                pass
        return 2
    try:
        sh = Shell(port, show=show, on_quit=lambda: app.stop(store, httpd, wd, d), core_stopped=app._stop_event, store=store)
        httpd.on_show = sh.open_board                     # 再双击一次 exe 时，POST /api/window/show 走这里
        sh.run()
    finally:
        app.stop(store, httpd, wd, d)                   # 同一个核心只收一次（app.stop 自己会认出来）
    return 0
