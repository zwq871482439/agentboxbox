"""仓库地图：给帮手的一页「文件 + 顶层函数 / 类」，派代码卡时附在说明末尾。

只用标准库（ast + 正则），抽不准的文件只列文件名；总长有硬预算，超了先降级成文件名、再停。
符号按文件修改时间缓存在 data/repomap/ 下，没改过的文件不重新解析；缓存读写出错一律当没缓存，
不能让派活失败。
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import re
import subprocess

from . import config

MAX_CHARS = 4000          # 一页地图的硬预算（约 1024 token）
GIT_TIMEOUT_S = 10        # git ls-files 超过这个秒数就放弃，改走 os.walk
# 只抽这些后缀；别的类型一个字都不占预算。.svelte 不抽符号，只留文件名
PY_SUFFIX = ".py"
JS_SUFFIXES = (".js", ".mjs", ".ts", ".tsx")
SVELTE_SUFFIX = ".svelte"
CANDIDATES = (PY_SUFFIX, *JS_SUFFIXES, SVELTE_SUFFIX)
SKIP_DIRS = {".git", "node_modules", "build", "dist", "__pycache__"}
# 太大的文件（压缩过的前端产物等）解析又慢又没收获，只列文件名
BIG_FILE_BYTES = 512 * 1024

# JS / TS 只认「写在行首」的定义，缩进里的不算顶层
_JS_PATTERNS = (
    re.compile(r"^(?:export\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)", re.M),
    re.compile(r"^(?:export\s+)?class\s+([A-Za-z_$][\w$]*)", re.M),
    re.compile(r"^export\s+(?:async\s+)?const\s+([A-Za-z_$][\w$]*)", re.M),
)


def _git_files(cwd: str) -> list[str] | None:
    """git 仓库就用 git ls-files（只列被跟踪的文件）；不是仓库、git 不在、超时都返回 None。"""
    try:
        p = subprocess.run(["git", "-C", cwd, "ls-files"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT_S, shell=False,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    return [ln for ln in (line.strip() for line in p.stdout.splitlines()) if ln]


def _walk_files(root: pathlib.Path) -> list[str]:
    """不是仓库时的兜底：全目录走一遍，跳过 .git / node_modules / build / dist / __pycache__。"""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            out.append(pathlib.Path(dirpath, fn).relative_to(root).as_posix())
    return sorted(out)


def _py_symbols(src: str) -> list[str]:
    """顶层 def 直接报名字；顶层 class 报「类.方法」（没方法的类只报类名）。"""
    out: list[str] = []
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(node.name)
        elif isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if methods:
                out.extend("%s.%s" % (node.name, m) for m in methods)
            else:
                out.append(node.name)
    return out


def _js_symbols(src: str) -> list[str]:
    names: list[str] = []
    for pat in _JS_PATTERNS:
        names.extend(m.group(1) for m in pat.finditer(src))
    seen: list[str] = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return seen


def _extract(path: pathlib.Path) -> list[str] | None:
    """抽一个文件的顶层符号。抽不出来（语法不对、读不了、太大）返回 None，只列文件名。"""
    if path.suffix not in CANDIDATES or path.suffix == SVELTE_SUFFIX:
        return None
    try:
        if path.stat().st_size > BIG_FILE_BYTES:
            return None
        src = path.read_text(encoding="utf-8", errors="replace")
        return _py_symbols(src) if path.suffix == PY_SUFFIX else _js_symbols(src)
    except (OSError, SyntaxError, ValueError):
        return None


def _cache_path(cwd: str) -> pathlib.Path:
    key = hashlib.sha1(str(pathlib.Path(cwd).resolve()).encode("utf-8", "replace")).hexdigest()
    return pathlib.Path(config.DATA) / "repomap" / (key + ".json")


def _load_cache(cwd: str) -> dict:
    try:
        doc = json.loads(_cache_path(cwd).read_text(encoding="utf-8"))
        return doc.get("files", {}) if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cache(cwd: str, files: dict) -> None:
    try:
        p = _cache_path(cwd)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"files": files}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def build(cwd: str) -> str:
    """拼一页仓库地图（带缓存）。目录不存在、一个能列的文件都没有都返回空串。"""
    root = pathlib.Path(cwd)
    if not root.is_dir():
        return ""
    rels = _git_files(cwd)
    if rels is None:
        rels = _walk_files(root)
    cache = _load_cache(cwd)
    entries: list[tuple[str, list[str] | None]] = []
    fresh: dict[str, dict] = {}
    for rel in rels:
        if not rel.endswith(CANDIDATES):
            continue
        p = root / rel
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        hit = cache.get(rel) if isinstance(cache.get(rel), dict) else None
        if hit is not None and hit.get("mtime") == mtime and isinstance(hit.get("symbols"), (list, type(None))):
            syms = hit.get("symbols")
        elif p.suffix == SVELTE_SUFFIX:
            syms = None              # .svelte 不抽符号，只列文件名，也就没有重算一说
        else:
            syms = _extract(p)
        syms = [s for s in (syms or []) if s] or None
        fresh[rel] = {"mtime": mtime, "symbols": syms}
        entries.append((rel, syms))
    _save_cache(cwd, fresh)
    return _render(entries)


def _render(entries: list[tuple[str, list[str] | None]]) -> str:
    """按预算排版：有符号的整行走前，放不下的降成文件名，文件名也放不下就停，末行报没列的个数。"""
    ordered = sorted(entries, key=lambda e: not e[1])   # 有符号的在前，组内保持文件表顺序
    lines: list[str] = []
    used = 0
    listed = 0

    def put(line: str) -> bool:
        nonlocal used
        cost = len(line) + (1 if lines else 0)
        if used + cost > MAX_CHARS:
            return False
        lines.append(line)
        used += cost
        return True

    for rel, syms in ordered:
        line = "%s: %s" % (rel, ", ".join(syms)) if syms else rel
        if put(line) or (bool(syms) and put(rel)):
            listed += 1
        else:
            break
    rest = len(ordered) - listed
    if rest <= 0:
        return "\n".join(lines)
    tail = "还有 %d 个文件没列" % rest
    while lines and used + len(tail) + 1 > MAX_CHARS:   # 报数那行自己也不能把总长顶过预算
        lines.pop()
        rest += 1
        tail = "还有 %d 个文件没列" % rest
        used = sum(len(x) for x in lines) + max(0, len(lines) - 1)
    lines.append(tail)
    return "\n".join(lines)
