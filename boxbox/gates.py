"""机械质检（§3.1.1）：六种内置检查器 + 登记命令。全过才进评审，任一不过直接打回。"""
from __future__ import annotations

import glob
import json
import os
import pathlib
import subprocess
from dataclasses import dataclass

from . import config, i18n, safe_exec

GIT_TIMEOUT_S = 30


@dataclass
class GateResult:
    check: str
    ok: bool
    reason: str
    detail: str = ""


def load_checks(path: pathlib.Path | None = None) -> dict:
    """读 data/checks.json；文件不存在或解析失败返回 {}。"""
    p = path or (config.DATA / "checks.json")
    doc = config._read_json(pathlib.Path(p), None)
    return doc if isinstance(doc, dict) else {}


def _check_exists(gate, cwd, task_id, base_commit, checks, lang=None):
    pattern = str(gate.get("path") or "")
    detail = "path=%s" % pattern
    if not pattern:
        return GateResult("exists", False, i18n.t("gate.exists.need_path", lang), detail)
    files = [m for m in glob.glob(os.path.join(cwd, pattern)) if os.path.isfile(m)]
    if not files:
        return GateResult("exists", False, i18n.t("gate.exists.no_match", lang), detail)
    if any(os.path.getsize(f) > 0 for f in files):
        return GateResult("exists", True, "", detail)
    return GateResult("exists", False, i18n.t("gate.exists.empty", lang), detail)


def _check_headings(gate, cwd, task_id, base_commit, checks, lang=None):
    path = str(gate.get("path") or "")
    must = [str(m) for m in (gate.get("must") or [])]
    detail = "path=%s" % path
    fp = os.path.join(cwd, path)
    if not os.path.isfile(fp):
        return GateResult("headings", False, i18n.t("gate.file.missing", lang), detail)
    with open(fp, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    missing = []
    for m in must:
        hit = False
        for line in lines:
            s = line.strip()
            if s.startswith("#") and m in s.lstrip("#").strip():
                hit = True
                break
            if s.startswith(m):
                hit = True
                break
        if not hit:
            missing.append(m)
    if missing:
        return GateResult("headings", False, i18n.t("gate.headings.missing", lang, v=i18n.t("gate.list_sep", lang).join(missing)), detail)
    return GateResult("headings", True, "", detail)


def _check_command(gate, cwd, task_id, base_commit, checks, lang=None):
    name = str(gate.get("name") or "")
    detail = "name=%s" % name
    spec = (checks or {}).get(name)
    if not isinstance(spec, dict):
        return GateResult("command", False, i18n.t("gate.command.unregistered", lang, name=name), detail)
    argv = spec.get("argv")
    if not isinstance(argv, list) or not argv:
        return GateResult("command", False, i18n.t("gate.command.no_argv", lang, name=name), detail)
    values = dict(gate.get("args") or {})
    values["task_id"] = task_id
    run_cwd = str(spec.get("cwd") or cwd)
    try:
        real_argv = safe_exec.resolve_argv(argv, values, run_cwd, spec.get("allowed_args"))
    except safe_exec.RejectedArgv as e:
        return GateResult("command", False, i18n.t("gate.command.rejected", lang, err=e), detail)
    r = safe_exec.run_argv(real_argv, run_cwd, int(spec.get("timeout_s") or 120))
    if r["timed_out"]:
        return GateResult("command", False, i18n.t("gate.command.timeout", lang), detail)
    if r["exit"] == 0:
        return GateResult("command", True, "", detail)
    if r["exit"] is None:
        return GateResult("command", False, i18n.t("gate.command.start_failed", lang), detail)
    return GateResult("command", False, i18n.t("gate.command.exit", lang, code=r["exit"]), detail)


def _git(cwd, *args):
    p = subprocess.run(["git", *args], cwd=str(cwd), shell=False,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=GIT_TIMEOUT_S)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def _check_commits(gate, cwd, task_id, base_commit, checks, lang=None):
    min_count = int(gate.get("min") or 1)
    detail = "min=%s" % min_count
    try:
        rc, _ = _git(cwd, "rev-parse", "HEAD")
    except (OSError, subprocess.SubprocessError):
        return GateResult("commits", False, i18n.t("gate.commits.no_git", lang), detail)
    if rc != 0:
        return GateResult("commits", False, i18n.t("gate.commits.not_repo", lang), detail)
    rc, out = _git(cwd, "status", "--porcelain")
    if rc != 0:
        return GateResult("commits", False, i18n.t("gate.commits.status_failed", lang), detail)
    if out.strip():
        return GateResult("commits", False, i18n.t("gate.commits.dirty", lang), detail)
    if base_commit:
        rc, out = _git(cwd, "rev-list", "--count", "%s..HEAD" % base_commit)
        if rc != 0:
            return GateResult("commits", False, i18n.t("gate.commits.count_failed", lang), detail)
        try:
            n = int(out.strip() or "0")
        except ValueError:
            return GateResult("commits", False, i18n.t("gate.commits.count_failed", lang), detail)
        if n < min_count:
            return GateResult("commits", False, i18n.t("gate.commits.too_few", lang, n=n, m=min_count), detail)
    return GateResult("commits", True, "", detail)


def _check_json(gate, cwd, task_id, base_commit, checks, lang=None):
    path = str(gate.get("path") or "")
    keys = [str(k) for k in (gate.get("keys") or [])]
    detail = "path=%s" % path
    fp = os.path.join(cwd, path)
    if not os.path.isfile(fp):
        return GateResult("json", False, i18n.t("gate.file.missing", lang), detail)
    try:
        with open(fp, encoding="utf-8") as f:
            doc = json.loads(f.read())
    except ValueError:
        return GateResult("json", False, i18n.t("gate.json.parse_failed", lang), detail)
    if not isinstance(doc, dict):
        return GateResult("json", False, i18n.t("gate.json.not_object", lang), detail)
    missing = [k for k in keys if k not in doc]
    if missing:
        return GateResult("json", False, i18n.t("gate.json.missing_keys", lang, keys=i18n.t("gate.list_sep", lang).join(missing)), detail)
    return GateResult("json", True, "", detail)


def _check_size(gate, cwd, task_id, base_commit, checks, lang=None):
    path = str(gate.get("path") or "")
    min_chars = int(gate.get("min_chars") or 0)
    detail = "path=%s min_chars=%d" % (path, min_chars)
    fp = os.path.join(cwd, path)
    if not os.path.isfile(fp):
        return GateResult("size", False, i18n.t("gate.file.missing", lang), detail)
    with open(fp, encoding="utf-8") as f:
        n = len(f.read())
    if n < min_chars:
        return GateResult("size", False, i18n.t("gate.size.too_few", lang, n=n, m=min_chars), detail)
    return GateResult("size", True, "", detail)


_CHECKERS = {
    "exists": _check_exists,
    "headings": _check_headings,
    "command": _check_command,
    "commits": _check_commits,
    "json": _check_json,
    "size": _check_size,
}


def run_gate(gate: dict, cwd: str, task_id: str, base_commit: str | None = None,
             checks: dict | None = None, lang: str | None = None) -> GateResult:
    """跑一条质检；任何异常都变成 ok=False，绝不把核心打崩。"""
    check = str((gate or {}).get("check") or "")
    lg = lang or i18n.lang()
    fn = _CHECKERS.get(check)
    if fn is None:
        return GateResult(check or "?", False, i18n.t("gate.unknown_checker", lg, check=check))
    try:
        return fn(gate, str(cwd), str(task_id), base_commit,
                  checks if checks is not None else load_checks(), lg)
    except Exception as e:
        return GateResult(check, False, i18n.t("gate.exception", lg, err=e))


def validate_gates(card: dict, checks: dict | None = None, lang: str | None = None) -> list[str]:
    """派活前静态检查质检写法，省得一张写错的卡白跑两轮才被「未登记命令」打回。
    只查形状：check 认识、必填参数在、command 的 name 已登记在 data/checks.json。"""
    gates = ((card.get("acceptance") or {}).get("gates")) if isinstance(card, dict) else None
    if not isinstance(gates, list):
        return []
    if checks is None:
        checks = load_checks()
    lg = lang or i18n.lang()
    errs: list[str] = []
    for i, g in enumerate(gates, 1):
        if not isinstance(g, dict):
            errs.append(i18n.t("gates.not_object", lg, i=i))
            continue
        check = str(g.get("check") or "")
        if check not in _CHECKERS:
            errs.append(i18n.t("gates.unknown_check", lg, i=i, v=check or i18n.t("gates.empty", lg),
                               list="/".join(_CHECKERS)))
            continue
        if check in ("exists", "headings", "json", "size") and not g.get("path"):
            errs.append(i18n.t("gates.need_path", lg, i=i, check=check))
        if check == "command":
            name = str(g.get("name") or "")
            if not name:
                errs.append(i18n.t("gates.need_name", lg, i=i))
            elif not isinstance((checks or {}).get(name), dict):
                known = " / ".join(sorted(k for k in (checks or {}) if isinstance(checks.get(k), dict))) \
                    or i18n.t("gates.none", lg)
                errs.append(i18n.t("gates.unknown_name", lg, i=i, v=name, list=known))
    return errs


def run_gates(card: dict, cwd: str, base_commit: str | None = None,
              checks: dict | None = None, lang: str | None = None) -> list:
    """按卡顺序跑全部质检（不短路）。"""
    gates = ((card.get("acceptance") or {}).get("gates")) or []
    if checks is None:
        checks = load_checks()
    return [run_gate(g, cwd, str(card.get("id") or ""), base_commit, checks, lang) for g in gates]


def render_review_md(results: list, lang: str | None = None) -> str:
    """质检结果渲染成 Markdown，写进 review.md 给评审者看。"""
    lg = lang or i18n.lang()
    lines = [i18n.t("gate.review.title", lg)]
    for r in results:
        line = "- [%s] %s" % ("x" if r.ok else " ", r.check)
        if r.detail:
            line += " " + r.detail
        if not r.ok and r.reason:
            line += " " + i18n.t("gate.review.reason", lg, reason=r.reason)
        lines.append(line)
    passed = sum(1 for r in results if r.ok)
    lines.append(i18n.t("gate.review.summary", lg, n=passed, m=len(results)))
    return "\n".join(lines)
