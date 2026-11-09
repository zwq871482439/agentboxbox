"""从旧版导入：把另一份 data 里的猫、设置和卡换进当前盒子。

不合并。当前库里已经有卡就拒绝。旧版 exe 还在那个文件夹里跑也拒绝，
免得导入之后旧版又写出新卡，两边各写各的。
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import urllib.parse

from . import config, i18n, tasks
from .dispatcher_const import INT_CRASH, INTERRUPT_KIND
from .runners import RunResult
from .store import now_iso

# 卡目录里给人看的小文件。运行记录（run-*.log）又大又是旧进程的，不搬。
# sessions / logs / pi / work 整目录不搬：那是旧进程的现场，对不上这个核心。
_CARD_FILES = ("card.json", "prompt.txt", "report.md", "review.md")


def exe_in_folder(folder: pathlib.Path) -> bool:
    """这个文件夹里有没有进程的 exe 正在跑。

    只在 Windows 上查（旧版 exe 是 Windows 的）。查不到进程列表就抛 OSError，
    调用方另说一句，不把记录换掉。其它系统没有这种 exe，返回 False。
    """
    if not sys.platform.startswith("win"):
        return False
    return _win_exe_in(folder)


def import_from(d, raw_path: str, running=None) -> dict:
    """把 raw_path（旧版文件夹，或它的 data 文件夹）换进当前核心。

    running 默认是 exe_in_folder。测试可以换成自己的函数，不必真的列进程。
    检查不过就回一句人话，什么都不改。
    """
    check = exe_in_folder if running is None else running
    found = _locate(raw_path)
    if found is None:
        return _no("import.no_db")
    data, install = found
    if _is_current(data, d.store):
        return _no("import.same")
    try:
        still = bool(check(install))
    except OSError:
        return _no("import.unchecked")
    if still:
        return _no("import.running")
    if _card_count(d.store):
        return _no("import.has_cards")
    port = config.settings().get("core_port")
    try:
        with d.lock:                                  # 和看门狗同一把锁：换库的时候别同时收尾
            if _card_count(d.store):
                return _no("import.has_cards")
            _backup(d.store, data / "boxbox.db")
            _copy_side(data, port)
            _settle(d)
            cats = len(config.stations())
            cards = _card_count(d.store)
            text = i18n.t("import.done", d.lang(), cats=cats, cards=cards)
            d.store.event("import_old", text, data={"cats": cats, "cards": cards, "from": str(data)})
    except (OSError, sqlite3.Error):
        return _no("import.failed")
    return {"ok": True, "text": text, "cats": cats, "cards": cards}


def _no(key: str) -> dict:
    return {"ok": False, "code": key.split(".", 1)[-1], "text": i18n.t(key, i18n.lang())}


def _locate(raw) -> tuple[pathlib.Path, pathlib.Path] | None:
    """(data 目录, 旧版 exe 所在的文件夹)。指到 data 时，exe 在它的上一级。"""
    text = str(raw or "").strip().strip('"')
    if not text:
        return None
    try:
        given = pathlib.Path(text).expanduser()
    except OSError:
        return None
    if given.is_file() and given.name == "boxbox.db":
        given = given.parent
    try:
        given = given.resolve()
    except OSError:
        return None
    if (given / "boxbox.db").is_file():
        return given, given.parent
    if (given / "data" / "boxbox.db").is_file():
        return given / "data", given
    return None


def _is_current(data: pathlib.Path, store) -> bool:
    try:
        if data.resolve() == pathlib.Path(config.DATA).resolve():
            return True
        return (data / "boxbox.db").resolve() == pathlib.Path(store.path).resolve()
    except OSError:
        return os.path.normcase(str(data)) == os.path.normcase(str(config.DATA))


def _card_count(store) -> int:
    row = store._row("SELECT COUNT(*) AS n FROM tasks")
    return int((row or {}).get("n") or 0)


def _backup(store, src_path: pathlib.Path) -> None:
    """用 sqlite backup 把旧库拷进已经开着的当前连接，不换文件。调用方拿着调度器的锁。"""
    # 只读打开：导入只读旧库，别在旧版的 data 里留下任何改动
    src = sqlite3.connect("file:%s?mode=ro" % urllib.parse.quote(pathlib.Path(src_path).resolve().as_posix(), safe="/:"), uri=True)
    try:
        with store.lock:
            src.backup(store.db)
            store._migrate()
    finally:
        src.close()


def _copy_side(data: pathlib.Path, port) -> None:
    """库以外的文件：设置（端口留新版的）、工位、密钥、模板、每张卡的小文件。"""
    _copy_settings(data, port)
    for name in ("stations.json", "secrets.json"):
        src = data / name
        if src.is_file():
            shutil.copyfile(src, config.DATA / name)
    _copy_files(data / "templates", config.DATA / "templates")
    _copy_cards(data / "tasks", config.DATA / "tasks")
    config.ensure_dirs()


def _copy_settings(data: pathlib.Path, port) -> None:
    src = data / "settings.json"
    if not src.is_file():
        return
    try:
        doc = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(doc, dict):
        return
    doc["core_port"] = port                       # 新版已经在听自己的端口，别改回旧的
    config.save_settings(doc)


def _copy_files(src: pathlib.Path, dst: pathlib.Path) -> None:
    if not src.is_dir():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        if child.is_file():
            shutil.copyfile(child, dst / child.name)


def _copy_cards(src: pathlib.Path, dst: pathlib.Path) -> None:
    if not src.is_dir():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for card in src.iterdir():
        if not card.is_dir():
            continue
        out = dst / card.name
        out.mkdir(parents=True, exist_ok=True)
        for name in _CARD_FILES:
            f = card / name
            if f.is_file():
                shutil.copyfile(f, out / name)


def _settle(d) -> None:
    """旧核心已经不在：照启动时的收尾，把还开着的运行、已派和在跑的卡记成中断。

    不看 pid 还在不在。那些进程不是这个核心拉起来的，接着管会把别人的进程当成自己的。
    """
    d.store.kv_set("core_started_at", now_iso())
    d.mark_crashed_runs()
    why = i18n.t("why.crash", d.lang())
    res = RunResult(exit=1, status="fail", error=why)
    for run in list(d.store.open_runs()):
        task = d.store.get_task(run["task_id"]) or {}
        if task.get("state") in ("dispatched", "running"):
            d.interrupt_run(run["run_id"], res, why=why, kind=INT_CRASH)
    for task in d.store.list_tasks(state="dispatched,running"):
        _mark_interrupted(d, task, why)
    d.drop_idle_runners()


def _mark_interrupted(d, task: dict, why: str) -> None:
    """没有运行记录的已派卡：库里没有 run 可收，卡本身记成中断并告诉首领。"""
    card = dict(task.get("card") or {})
    card[INTERRUPT_KIND] = INT_CRASH
    tasks.write_card(task["id"], card)
    d.store.update_task(task["id"], state="interrupted", card_json=json.dumps(card, ensure_ascii=False),
                        returned_reason=why)
    d.store.event("interrupted", i18n.t("ev.interrupted", d.lang(), sid=task.get("assignee") or "",
                                        title=task.get("title") or "", why=why),
                  task.get("assignee"), task["id"], data={"kind": INT_CRASH})


def _win_exe_in(folder: pathlib.Path) -> bool:
    # 跟 procjob 列进程同一套：CIM + 超时。输出用 UTF-8，中文路径才不会乱。
    ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
          "Get-CimInstance Win32_Process | "
          "ForEach-Object { if ($_.ExecutablePath) { $_.ExecutablePath } }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                             capture_output=True, timeout=15,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        raise OSError("process list failed") from e
    if out.returncode != 0 and not out.stdout:
        raise OSError("process list failed")
    root = pathlib.Path(folder).resolve()
    for line in out.stdout.decode("utf-8", "replace").splitlines():
        exe = line.strip().strip('"')
        if exe and _is_inside(pathlib.Path(exe), root):
            return True
    return False


def _is_inside(path: pathlib.Path, folder: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except (OSError, ValueError):
        a = os.path.normcase(os.path.abspath(str(path)))
        b = os.path.normcase(os.path.abspath(str(folder)))
        return a == b or a.startswith(b.rstrip("\\/") + os.sep)
