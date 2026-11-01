"""安全执行（§12.1）：参数数组启动、占位符整体替换、白名单校验，绝不走 shell。"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import time

from . import config, i18n

MAX_OUT_CHARS = 4000

# 一个元素就是一个占位符：{name}
_PLACEHOLDER_RE = re.compile(r"^\{([A-Za-z_]\w*)\}$")
# path 的默认字符白名单：相对路径常见字符（不含空格、分号等）
_PATH_CHARS_RE = re.compile(r"^[\w./\\-]+$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class RejectedArgv(ValueError):
    """argv 或占位符值不合规，拒绝执行。str(e) 是拒绝的原因（按当下语言）。"""


def safe_path(path: str, cwd: str) -> pathlib.Path:
    """校验相对路径并返回解析后的绝对路径；不合法抛 RejectedArgv。"""
    p = str(path)
    if not p.strip():
        raise RejectedArgv(i18n.t("safe.path_empty"))
    if p.startswith("-"):
        raise RejectedArgv(i18n.t("safe.path_dash"))
    if _DRIVE_RE.match(p) or p.startswith(("/", "\\")) or os.path.isabs(p):
        raise RejectedArgv(i18n.t("safe.path_relative"))
    if ".." in re.split(r"[/\\]+", p):
        raise RejectedArgv(i18n.t("safe.path_dotdot"))
    if not _PATH_CHARS_RE.match(p):
        raise RejectedArgv(i18n.t("safe.path_chars"))
    base = pathlib.Path(cwd).resolve()
    full = (base / p).resolve()
    try:
        full.relative_to(base)
    except ValueError:
        raise RejectedArgv(i18n.t("safe.path_escape")) from None
    return full


def resolve_argv(argv: list, values: dict, cwd: str, allowed_args: dict | None = None) -> list:
    """只做占位符替换 + 校验，不执行。values 可含 task_id / path / cwd 及 allowed_args 里的名字。"""
    values = values or {}
    allowed_args = allowed_args or {}
    out = []
    for elem in argv:
        elem = str(elem)
        m = _PLACEHOLDER_RE.match(elem)
        if not m:
            if "{" in elem or "}" in elem:
                raise RejectedArgv(i18n.t("safe.placeholder_whole"))
            out.append(elem)
            continue
        name = m.group(1)
        if name == "task_id":
            v = str(values.get("task_id") or "")
            if not re.match(config.TASK_ID_RE, v):
                raise RejectedArgv(i18n.t("safe.task_id"))
            out.append(v)
        elif name == "cwd":
            out.append(str(values.get("cwd") or cwd))
        elif name == "path":
            if values.get("path") is None:
                raise RejectedArgv(i18n.t("safe.need_path"))
            out.append(str(safe_path(str(values["path"]), cwd)))
        else:
            if name not in allowed_args:
                raise RejectedArgv(i18n.t("safe.not_allowed", name=name))
            v = str(values.get(name) or "")
            if not re.match(str(allowed_args[name]), v):
                raise RejectedArgv(i18n.t("safe.arg_mismatch", name=name))
            out.append(v)
    return out


def run_argv(argv: list, cwd: str, timeout_s: int = 120) -> dict:
    """执行参数数组（shell=False），UTF-8 环境，输出各截 4000 字符，超时算失败。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    args = [str(a) for a in argv]
    t0 = time.monotonic()
    try:
        p = subprocess.run(args, cwd=str(cwd), shell=False,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout_s, env=env)
        return {"exit": p.returncode,
                "stdout": p.stdout.decode("utf-8", "replace")[:MAX_OUT_CHARS],
                "stderr": p.stderr.decode("utf-8", "replace")[:MAX_OUT_CHARS],
                "timed_out": False,
                "duration_s": round(time.monotonic() - t0, 3)}
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = (e.stderr or b"").decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return {"exit": None, "stdout": out[:MAX_OUT_CHARS], "stderr": err[:MAX_OUT_CHARS],
                "timed_out": True, "duration_s": round(time.monotonic() - t0, 3)}
    except OSError as e:
        return {"exit": None, "stdout": "", "stderr": str(e),
                "timed_out": False, "duration_s": round(time.monotonic() - t0, 3)}
