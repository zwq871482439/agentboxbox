"""临时文件统一放程序目录 tmp\\：每张卡一个子目录，自动清理。

约定：exe 所在目录只有三样——软件本体、data\\（配置和记录，不能随便删）、tmp\\（过程垃圾）。
tmp\\ 下面每张卡一个子目录（卡号），首领用 leader\\。
完成或撤掉的卡马上删自己的目录；失败或中断的留着查，过了 tmp_keep_days 再清。
删的时候碰到目录联接或符号链接只删链接本身，不进到它指的目录。

根目录：默认 <exe 目录>/tmp（源码跑时是仓库根下的 tmp\\），环境变量 BOXBOX_TMP 可以改（测试用）。
这里每次都现取 config.TMP / 环境变量，不在模块导入时缓存，测试改环境变量才有效。

只有名字像卡号（20261029-007）的子目录才算盒子的卡目录：清理和算大小都只认这些 + leader。
exe 放在 C:\\ 根目录时 C:\\tmp 里可能有用户自己的文件夹——不是卡号的目录和文件一律不碰。
"""
from __future__ import annotations

import os
import pathlib
import re
import stat
import time

from . import config

LEADER_DIR = "leader"          # 首领的临时文件目录（不分卡）
DAY = 24 * 60 * 60
# 卡号目录的样子：20261029-007。tmp\\ 下面只有这种名字的目录才算盒子的卡目录。
# exe 放在 C:\\ 根目录时 C:\\tmp 里可能有用户自己的文件夹——不是卡号的一律不碰（不删、不算大小）。
CARD_DIR_RE = re.compile(r"^\d{8}-\d{3}$")


def root() -> pathlib.Path:
    """临时文件根目录：BOXBOX_TMP 优先（测试用），否则 config.TMP（默认 <exe 目录>/tmp）。现取。"""
    env = os.environ.get("BOXBOX_TMP")
    return pathlib.Path(env) if env else pathlib.Path(config.TMP)


def card_tmp(task_id: str) -> pathlib.Path:
    """这张卡专用的临时目录，建好返回（不存在就建）。"""
    p = root() / str(task_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def leader_tmp() -> pathlib.Path:
    """首领的临时目录（HTTP 细节里让首领把请求正文存这儿），建好返回。"""
    p = root() / LEADER_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _is_card_dir(p: pathlib.Path) -> bool:
    """这个子目录是不是卡目录：名字像卡号（20261029-007）才算。别的目录、文件一律不是。"""
    return p.is_dir() and bool(CARD_DIR_RE.match(p.name))


def _leader_dir() -> list[pathlib.Path]:
    """leader 目录（存在才算）。"""
    p = root() / LEADER_DIR
    return [p] if p.is_dir() else []


def size_bytes() -> int:
    """tmp\\ 里盒子的东西多大（字节）：只算卡目录 + leader，用户自己的目录不算。目录不在就是 0。"""
    total = 0
    r = root()
    if not r.is_dir():
        return 0
    for d in card_dirs() + _leader_dir():
        for dirpath, _dirnames, filenames in os.walk(d):
            for fn in filenames:
                try:
                    total += (pathlib.Path(dirpath) / fn).stat().st_size
                except OSError:
                    continue
    return total


def card_dirs() -> list[pathlib.Path]:
    """tmp\\ 下面的卡目录（名字像卡号的子目录；leader 和用户自己的目录都不算）。"""
    r = root()
    if not r.is_dir():
        return []
    return sorted([p for p in r.iterdir() if _is_card_dir(p)])


def _is_junction(path) -> bool:
    """Windows 目录联接。它不算符号链接，当成普通目录删会走进去。"""
    if os.name != "nt":
        return False
    checker = getattr(os.path, "isjunction", None)
    if checker is not None:
        try:
            return bool(checker(path))
        except OSError:
            return False
    try:
        st = os.lstat(path)
    except OSError:
        return False
    tag = getattr(st, "st_reparse_tag", None)
    mount = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)
    if tag is not None:
        return tag == mount
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & reparse) and stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode)


def _link_kind(path: pathlib.Path) -> str:
    """'junction' / 'symlink' / ''。联接优先：Windows 上它常常不是 is_symlink。"""
    try:
        if _is_junction(path):
            return "junction"
        if path.is_symlink():
            return "symlink"
    except OSError:
        return ""
    return ""


def _remove_link(path: pathlib.Path, junction: bool) -> None:
    """只删链接本身。目录联接用 rmdir；符号链接用 unlink。"""
    if junction:
        os.rmdir(path)
        return
    try:
        os.unlink(path)
    except OSError:
        # Windows 上指着目录的符号链接，unlink 会拒绝；rmdir 同样只拆链接
        if os.name == "nt":
            os.rmdir(path)
            return
        raise


def rmtree_safe(path, ignore_errors: bool = False) -> None:
    """删一棵目录。目录联接和符号链接只删链接，不进到它指的地方。"""
    if path is None or str(path) == "":
        if not ignore_errors:
            raise FileNotFoundError(str(path))
        return
    try:
        _rm_entry(pathlib.Path(path), ignore_errors)
    except OSError:
        if not ignore_errors:
            raise


def _rm_entry(path: pathlib.Path, ignore_errors: bool) -> None:
    kind = _link_kind(path)
    if kind:
        _remove_link(path, kind == "junction")
        return
    if not path.exists():
        if not ignore_errors:
            raise FileNotFoundError(path)
        return
    if not path.is_dir():
        path.unlink()
        return
    with os.scandir(path) as it:
        names = [entry.name for entry in it]
    for name in names:
        try:
            _rm_entry(path / name, ignore_errors)
        except OSError:
            if not ignore_errors:
                raise
    os.rmdir(path)


def _gone(path: pathlib.Path) -> bool:
    return not path.exists() and not path.is_symlink() and not _is_junction(path)


def remove_card(task_id: str) -> bool:
    """删掉这一张卡的临时目录。名字不像卡号的不动，免得误删 leader 或别的目录。

    目录本来就没有，返回 False。文件还被占着、删不干净，也返回 False，按天清理会再试。
    """
    if not CARD_DIR_RE.match(str(task_id or "")):
        return False
    d = root() / str(task_id)
    if _gone(d):
        return False
    rmtree_safe(d, ignore_errors=True)
    return _gone(d)


def clean(keep_days: int, running_ids) -> int:
    """删掉「最后修改超过 keep_days 天」的卡目录；跳过 running_ids 里的卡和 leader。返回删了几个。

    keep_days=0 = 立刻清（传进来的在跑的卡还是不动）。
    """
    r = root()
    if not r.is_dir():
        return 0
    keep = {str(x) for x in (running_ids or [])}
    cutoff = time.time() - max(0, int(keep_days)) * DAY
    removed = 0
    for d in card_dirs():
        if d.name in keep:
            continue
        try:
            mtime = d.lstat().st_mtime
        except OSError:
            continue
        if mtime > cutoff:
            continue
        rmtree_safe(d, ignore_errors=True)
        if _gone(d):
            removed += 1
    return removed


def clean_orphans(known_ids) -> int:
    """删掉不在 known_ids 里的卡目录（leader 不动）——核心重启后剩下的空壳。返回删了几个。"""
    r = root()
    if not r.is_dir():
        return 0
    known = {str(x) for x in (known_ids or [])}
    removed = 0
    for d in card_dirs():
        if d.name in known:
            continue
        rmtree_safe(d, ignore_errors=True)
        if _gone(d):
            removed += 1
    return removed


def count_running(running_ids) -> int:
    """还在跑的卡占了几个目录（清临时文件时这些跳过，回报里报个数）。"""
    keep = {str(x) for x in (running_ids or [])}
    return len([d for d in card_dirs() if d.name in keep])
