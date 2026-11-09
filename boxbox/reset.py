# -*- coding: utf-8 -*-
"""重置所有：把核心恢复成刚装好的样子。

删掉：全部工位、设置（含上岗进度）、secrets.json 里的 API key、数据库里所有表的数据、
data/logs、data/tasks、data/sessions、data/pi。
保留：data/work（用户的产出）、boxbox.db 文件本身（用 DELETE 清表，不然 Windows 上删不动）。

先中断所有在跑的卡（同一套逻辑见 Dispatcher.interrupt_station），每一步单独记结果，
页面照 steps 画进度条。
"""
from __future__ import annotations

from . import config, i18n, tmpdir

CLEAR_DIRS = ("tasks", "sessions", "pi")      # 整个目录清掉重建
TRUNCATE_DIRS = ("logs",)                     # 正在写的日志不删，截断成空文件


def reset_all(d) -> dict:
    """按顺序做，每步一个 {"name", "ok"}；全过 ok=True。"""
    steps: list[dict] = []

    def step(name: str, fn) -> None:
        try:
            fn()
            steps.append({"name": name, "ok": True})
        except Exception as e:  # noqa: BLE001 - 一步失败也要把后面的做完，最后如实报给页面
            steps.append({"name": name, "ok": False, "text": str(e)})

    step(i18n.t("app.reset.stop_cards"), lambda: _stop_work(d))
    step(i18n.t("app.reset.clear_stations"), _clear_stations_settings)
    step(i18n.t("app.reset.clear_keys"), _clear_secrets)
    step(i18n.t("app.reset.clear_tasks"), lambda: d.store.clear_all())
    step(i18n.t("app.reset.clear_files"), _clear_files)
    return {"ok": all(s["ok"] for s in steps), "steps": steps, "kept": ["data/work"]}


def _stop_work(d) -> None:
    d.interrupt_all("reset_all")
    d.runners.clear()


def _clear_stations_settings() -> None:
    config.save_stations([])
    config.save_settings({})           # 含上岗进度（§5）
    config.ensure_dirs()


def _clear_secrets() -> None:
    for name in ("secrets.json", "README-secrets.txt"):
        try:
            (config.DATA / name).unlink(missing_ok=True)
        except OSError:
            pass


def _clear_files() -> None:
    for sub in CLEAR_DIRS:
        root = config.DATA / sub
        if root.is_dir():
            for child in root.iterdir():
                if child.is_dir():
                    tmpdir.rmtree_safe(child, ignore_errors=True)
                else:
                    try:
                        child.unlink()
                    except OSError:
                        pass
    for sub in TRUNCATE_DIRS:
        root = config.DATA / sub
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.is_file():
                try:
                    p.write_text("", encoding="utf-8")   # 正在被写的日志：截断，不删
                except OSError:
                    pass
    config.ensure_dirs()
