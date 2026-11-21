# -*- coding: utf-8 -*-
"""Windows 原生托盘（ctypes 直调 Shell_NotifyIconW）：图标、左键、右键菜单、气泡通知。

为什么自己写而不用 pystray：pystray 是 LGPL-3.0，是 exe 里唯一的 LGPL 组件，打包脚本因此必须公开；
换掉它之后 exe 里没有 LGPL 依赖了。整块只在 Windows 的托盘线程里用（tray.py 会先判平台），
菜单和文字都由 tray.py 给（menu_builder 每次右键现调，拿到的就是最新的数）。

    icon = TrayIcon(menu_builder=..., on_click=..., tip=..., icons={状态: .ico 路径})
    icon.run(ready)      # 托盘线程上调，阻塞到 stop()；ready 在图标真的进了托盘之后才调
    icon.set_state("red")   # normal / running / red：按 icons 表换图（换不了就不换，图标别消失）
    icon.set_tip("...")     # 悬停提示
    icon.notify(body, title)   # 气泡（NIF_INFO）
    icon.stop()              # 任何线程都能调
"""
from __future__ import annotations

import ctypes
import sys
import threading

IS_WIN = sys.platform.startswith("win")

NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETVERSION = 0, 1, 2, 4
NOTIFYICON_VERSION = 3          # 设了这个版本，气泡的 NIN_* 回调才会送回来（不设只送鼠标消息）
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
NIIF_INFO = 0x01
WM_APP = 0x8000
TRAY_MSG = WM_APP + 1          # Explorer 把托盘图标上的鼠标消息用这个窗口消息送回来
WM_DESTROY, WM_CLOSE, WM_NULL = 0x0002, 0x0010, 0x0000
WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_RBUTTONUP, WM_CONTEXTMENU = 0x0202, 0x0203, 0x0205, 0x007B
NIN_BALLOONSHOW = 0x0402       # 气泡真的弹出来了（排障和验收都靠这个回调）
IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010
SM_CXSMICON = 49
MF_GRAYED, MF_CHECKED, MF_POPUP, MF_SEPARATOR = 0x1, 0x8, 0x10, 0x800
TPM_RETURNCMD, TPM_RIGHTBUTTON = 0x0100, 0x0002


class MenuItem:
    """托盘菜单的一项：label 为 None 是分隔线；action 是点了要跑的函数；submenu 是下一层的列表；
    checked / enabled 在建菜单那一刻取值（每次右键都重建，不用担心过期）。"""

    __slots__ = ("label", "action", "enabled", "checked", "submenu")

    def __init__(self, label, action=None, enabled=True, checked=False, submenu=None):
        self.label = label
        self.action = action
        self.enabled = enabled
        self.checked = checked
        self.submenu = submenu


SEP = MenuItem(None)


def item_flags(item: MenuItem) -> int:
    """一个菜单项 → AppendMenuW 的旗子（纯函数，方便测）。"""
    f = 0
    if not item.enabled:
        f |= MF_GRAYED
    if item.checked:
        f |= MF_CHECKED
    if item.submenu is not None:
        f |= MF_POPUP
    return f


if IS_WIN:
    import ctypes.wintypes as wintypes

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadImageW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT)
    user32.RegisterWindowMessageW.restype = wintypes.UINT
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.TrackPopupMenuEx.restype = wintypes.BOOL
    # 不定 argtypes 的话 ctypes 把 int 当 32 位 C int，lParam 带着指针位时会溢出抛错
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    shell32.Shell_NotifyIconW.argtypes = (wintypes.UINT, ctypes.c_void_p)
    _TASKBAR_RESTART = user32.RegisterWindowMessageW("TaskbarCreated")   # Explorer 重启后补图标
    _CLASS = "agentboxbox-tray"
    _CLASS_ATOM = 0
    _ICON = None    # 整个进程只有一个托盘图标（tray.py 的单实例互斥挡着重复开），窗口过程从这找它
    # LRESULT 用 c_ssize_t：ctypes.wintypes 里没这个名字（新版 Python 去掉了）
    _WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class _GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    # WNDCLASSW 自己定义：新版 Python 的 ctypes.wintypes 把它删了，老版又有，两头部不住就自己写
    class _WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                    ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR)]

    class _NID(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("uTimeout", wintypes.UINT), ("uVersion", wintypes.UINT)]

        _fields_ = [
            ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HANDLE),
            ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256), ("_u", _U), ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD), ("guidItem", _GUID), ("hBalloonIcon", wintypes.HANDLE),
        ]


def _wndproc(hwnd, msg, wp, lp):
    icon = _ICON
    if icon is None:
        return user32.DefWindowProcW(hwnd, msg, wp, lp)
    return icon.on_message(hwnd, msg, wp, lp)


class TrayIcon:
    def __init__(self, menu_builder, on_click, tip, icons):
        self.menu_builder = menu_builder    # () -> list[MenuItem]
        self.on_click = on_click            # 左键点图标：默认动作（打开看板）
        self.tip = tip
        self.icons = icons                  # {状态名: .ico 路径}
        self.state = next(iter(icons))
        self.hwnd = None
        self._nid = None
        self._handles = {}                  # 状态 -> HICON（三个图标各一份，进程活着不撒手）
        self._lock = threading.Lock()       # notify/set_tip/set_state 会从别的线程来
        self._stopped = threading.Event()
        self._wndproc = None                # 得攥住，ctypes 回调被回收了进程就崩

    # ---- 生命周期 ----
    def run(self, ready=None):
        """起隐藏窗口、把图标放进托盘、跑消息循环；阻塞到 stop()。
        图标没放进去（比如这个会话没有托盘）也照样阻塞，等 stop()：跟 pystray 时代的线程约定一致。"""
        if not IS_WIN:
            return
        ok = self._create()
        try:
            if ok:
                if self._stopped.is_set():          # stop() 抢在窗口建好之前来了：补一发 WM_CLOSE
                    user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
                if ready is not None:
                    ready()
                self._pump()
        finally:
            if ok and self.hwnd:
                self._remove()                      # 窗口还在（消息循环异常跳出）时的兜底
        if not ok:
            self._stopped.wait()

    def stop(self):
        self._stopped.set()
        hwnd = self.hwnd
        if hwnd:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

    def _create(self) -> bool:
        global _CLASS_ATOM, _ICON
        if self._stopped.is_set() or not self.icons:
            return False
        with self._lock:
            self._wndproc = _WNDPROC(_wndproc)
            hinst = kernel32.GetModuleHandleW(None)
            if not _CLASS_ATOM:
                wc = _WNDCLASSW()
                wc.style = 0
                wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p)
                wc.hInstance = hinst
                wc.lpszClassName = _CLASS
                _CLASS_ATOM = user32.RegisterClassW(ctypes.byref(wc))
            # 普通隐藏窗口（不是 message-only）：message-only 收不到广播，Explorer 重启的补图标消息就没了
            _ICON = self
            self.hwnd = user32.CreateWindowExW(0, _CLASS, _CLASS, 0, 0, 0, 0, 0, None, None, hinst, None)
            if not self.hwnd:
                return False
            nid = _NID()
            nid.cbSize = ctypes.sizeof(_NID)
            nid.hWnd = self.hwnd
            nid.uID = 1
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = TRAY_MSG
            nid.szTip = (self.tip or "")[:127]
            for state in self.icons:                 # 哪个状态的 .ico 在用哪个
                nid.hIcon = self._hicon(state)
                if nid.hIcon:
                    self.state = state
                    break
            if not nid.hIcon or not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
                user32.DestroyWindow(self.hwnd)
                self.hwnd = None
                return False
            nid._u.uVersion = NOTIFYICON_VERSION
            shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))   # 失败也不要紧：少了气泡回调而已
            self._nid = nid
            return True

    def _pump(self):
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _remove(self):
        with self._lock:
            if self._nid is not None:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
                self._nid = None

    # ---- 对外接口（托盘线程之外的线程也会调） ----
    def set_state(self, state):
        """换图标（红点 / 绿点）。状态没变、文件载不了就不动：托盘上别没了图标。"""
        with self._lock:
            if self._nid is None or state not in self.icons or state == self.state:
                return
            h = self._hicon(state)
            if not h:
                return
            self._nid.uFlags = NIF_ICON
            self._nid.hIcon = h
            if shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid)):
                self.state = state

    def set_tip(self, text):
        with self._lock:
            if self._nid is None:
                return
            t = (text or "")[:127]
            if t == self._nid.szTip:
                return
            self._nid.uFlags = NIF_TIP
            self._nid.szTip = t
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))

    def notify(self, body, title=""):
        """气泡通知；返回有没有发出去（收不收是系统的事）。"""
        with self._lock:
            if self._nid is None:
                return False
            self._nid.uFlags = NIF_INFO
            self._nid.szInfo = (body or "")[:255]
            self._nid.szInfoTitle = (title or "")[:63]
            self._nid.dwInfoFlags = NIIF_INFO
            ok = bool(shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid)))
            if not ok:
                sys.stderr.write("tray balloon failed\n")
            return ok

    # ---- 托盘线程里的事 ----
    def on_message(self, hwnd, msg, wp, lp):
        if msg == TRAY_MSG and wp == 1:
            if lp in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self._safe(self.on_click)
            elif lp in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_menu(hwnd)
            elif lp == NIN_BALLOONSHOW:                     # 气泡也是从回调消息进来的（和鼠标事件同一条路）
                sys.stderr.write("tray balloon shown\n")  # 验收「气泡真的弹了」就靠这行日志
        elif msg == _TASKBAR_RESTART:
            with self._lock:                              # Explorer 重启：托盘清空了，把图标补回去
                if self._nid is not None:
                    self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
                    shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid))
        elif msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        elif msg == WM_DESTROY:
            self._remove()
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    def _show_menu(self, hwnd):
        """右键菜单：每次现建（文字和数字都是最新的），TrackPopupMenu 等用户点完再收。"""
        try:
            items = self.menu_builder() or []
        except Exception as e:  # noqa: BLE001 - 菜单建不出来也别让消息循环死掉
            sys.stderr.write("tray menu build failed: %r\n" % (e,))
            return
        hmenu, acts = self._build(items)
        try:
            user32.SetForegroundWindow(hwnd)              # 不前台的话，菜单在外面点一下不肯收（MSDN 的老坑）
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            cmd = user32.TrackPopupMenuEx(hmenu, TPM_RETURNCMD | TPM_RIGHTBUTTON, pt.x, pt.y, hwnd, None)
            user32.PostMessageW(hwnd, WM_NULL, 0, 0)      # 配合上面的 SetForegroundWindow
        finally:
            user32.DestroyMenu(hmenu)
        it = acts.get(cmd)
        if it is not None and it.enabled and it.action is not None:
            self._safe(it.action)

    def _build(self, items):
        """MenuItem 列表 → (菜单句柄, {命令 id: MenuItem})；分隔线和灰项不进表（点了也没动作）。"""
        hmenu = user32.CreatePopupMenu()
        acts: dict[int, MenuItem] = {}
        nid = [100]                                     # Win32 命令 id 从 100 起，0 是「没点」

        def add(menu, lst):
            for it in lst:
                if it.label is None:
                    user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                    continue
                if it.submenu is not None:
                    sub = user32.CreatePopupMenu()
                    add(sub, it.submenu)
                    user32.AppendMenuW(menu, item_flags(it), sub, it.label)
                    continue
                nid[0] += 1
                acts[nid[0]] = it
                user32.AppendMenuW(menu, item_flags(it), nid[0], it.label)

        add(hmenu, items)
        return hmenu, acts

    def _hicon(self, state):
        if state not in self._handles:
            sz = user32.GetSystemMetrics(SM_CXSMICON) or 16
            self._handles[state] = user32.LoadImageW(None, str(self.icons[state]), IMAGE_ICON, sz, sz, LR_LOADFROMFILE)
        return self._handles[state]

    def _safe(self, action):
        """菜单动作在托盘线程里跑；炸了写日志，别把消息循环带死。"""
        try:
            action()
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("tray action failed: %r\n" % (e,))
