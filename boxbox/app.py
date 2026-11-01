"""Core process assembly: store + dispatcher + watchdog + HTTP."""
from __future__ import annotations

import sys
import threading

from . import __version__, config, i18n, pi_catalog, tmpdir
from .dispatcher import Dispatcher
from .facades.http import Core
from .facades.http import serve as http_serve
from .store import Store
from .watchdog import Watchdog

_stop_event = threading.Event()        # serve() 的主线在这儿等；stop() 叫醒它，进程才退得出去


def build():
    config.ensure_dirs()
    store = Store(config.DATA / "boxbox.db")
    d = Dispatcher(store)
    try:                                       # 核心启动时清一次孤儿临时目录（库里已经没有的卡）
        known = [str(t.get("id")) for t in store.list_tasks(limit=100000) if t.get("id")]
        tmpdir.clean_orphans(known)
    except Exception:                          # noqa: BLE001 - 清临时文件坏了不能挡住核心启动
        pass
    try:                                       # 上次没正常退出的卡：启动时就记成「中断」（不是失败），能接着做
        d.mark_crashed_runs()
    except Exception:                          # noqa: BLE001 - 查旧 run 坏了不能挡住核心启动
        pass
    return store, d, Core(d)


def core_alive(port: int, timeout: float = 1.5) -> bool:
    """Is a boxbox core already answering on this port? (another exe / `serve()` instance)"""
    import json
    import socket
    import urllib.request
    try:                                  # cheap TCP probe first: a closed port on Windows loopback can take ~2 s via urllib
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            pass
    except OSError:
        return False
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/health" % port, timeout=timeout) as r:
            return bool(json.loads(r.read().decode("utf-8")).get("ok"))
    except Exception:  # noqa: BLE001
        return False


def start(port: int | None = None):
    """Start the core without blocking (tray shell, tests). Returns (store, dispatcher, httpd, watchdog, port).
    Raises RuntimeError if a core is already serving that port (never run two cores on one data dir).
    端口传 0 = 不指定，让系统挑一个空着的（测试用；不用先占一个再放掉，中间不会被别人抢走）。"""
    want = int(config.settings().get("core_port", 8878)) if port is None else int(port)
    _stop_event.clear()
    if want and core_alive(want):
        raise RuntimeError(i18n.t("app.core_already", i18n.lang(), port=want))
    store, d, core = build()
    wd = Watchdog(d)
    wd.start()
    try:
        httpd = http_serve(core, want, block=False)
    except OSError as e:
        wd.stop_flag.set()
        raise RuntimeError(i18n.t("app.port_busy", i18n.lang(), port=want, why=e)) from e
    port = httpd.server_address[1]              # 传 0 时是系统刚挑的那个端口
    httpd.on_stop = lambda: stop(store, httpd, wd, d)      # POST /api/shutdown 收工，和托盘「退出」同一条路
    store.event("core_start", i18n.t("app.core_started", i18n.lang(), port=port), data={"data": str(config.DATA)})
    sys.stderr.write("boxbox core %s · http://127.0.0.1:%d · data=%s\n" % (__version__, port, config.DATA))
    # 先问好 Pi 自带的模型清单（换了 Pi 版本才真去问，约一秒）：第一次「测试连接」不用等它
    threading.Thread(target=pi_catalog.load, name="boxbox-pi-catalog", daemon=True).start()
    return store, d, httpd, wd, port


def stop(store, httpd, wd, d=None) -> None:
    """按顺序收尾：先停看门狗和 HTTP（不再接新活）→ 结束所有打工进程 → 关数据库。
    之后 data 目录里不该再有任何文件被本进程或它的子进程占着。同一个核心只收一次：
    /api/shutdown 收过之后，serve() 的 finally 还会再调一次，那次直接返回（库已经关了）。"""
    if getattr(wd, "bx_stopped", False):
        return
    wd.bx_stopped = True          # type: ignore[attr-defined] - wd 可能是测试里的替身
    wd.stop_flag.set()
    if wd.is_alive():
        wd.join(timeout=10)               # 等它这一轮 tick 跑完，免得和下面的收尾抢同一个 run / 写已关的库
    try:
        httpd.shutdown()
        httpd.server_close()
    except Exception:  # noqa: BLE001
        pass
    if d is not None:
        try:
            d.shutdown()
        except Exception:  # noqa: BLE001
            pass
    store.event("core_stop", i18n.t("app.core_stopped", i18n.lang()))
    store.close()
    _stop_event.set()          # serve() 的主线别再等了（POST /api/shutdown 走这条路时，进程自己要退出去）


def serve(port: int | None = None) -> int:
    try:
        store, d, httpd, wd, port = start(port)
    except RuntimeError as e:
        sys.stderr.write(str(e) + "\n")
        return 2
    try:
        _wait_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop(store, httpd, wd, d)
    return 0


def _wait_forever():
    _stop_event.wait()
