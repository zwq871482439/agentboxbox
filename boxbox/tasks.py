"""Task cards: validation (self-contained rule, §3.1.2), the state machine (§3.2), prompt rendering (§11)."""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import string

from . import config, i18n

TASK_ID_RE = re.compile(config.TASK_ID_RE)
KINDS = ("code", "doc", "data", "run", "review")
REVIEW_MODES = ("leader", "user", "none")

# state -> {event: next_state}
TRANSITIONS = {
    "queued":     {"start": "dispatched", "cancel": "cancelled", "redispatch": "dispatched"},   # redispatch: 等接口的排队卡首领也能重派
    "dispatched": {"heartbeat": "running", "done": "delivered", "exit_ok": "delivered", "blocked": "blocked",
                   "issue": "blocked", "fail": "failed", "cancel": "cancelled", "interrupt": "interrupted"},
    "running":    {"heartbeat": "running", "done": "delivered", "exit_ok": "delivered", "blocked": "blocked",
                   "issue": "blocked", "fail": "failed", "cancel": "cancelled", "interrupt": "interrupted"},
    "delivered":  {"gates_ok": "reviewing", "gates_fail": "returned", "cancel": "cancelled"},
    "reviewing":  {"accept": "accepted", "return": "returned", "cancel": "cancelled"},
    "accepted":   {"on_accept_done": "done"},
    "returned":   {"redispatch": "dispatched", "escalate": "reviewing", "cancel": "cancelled"},
    "blocked":    {"redispatch": "dispatched", "cancel": "cancelled"},
    "failed":     {"redispatch": "dispatched", "cancel": "cancelled"},
    # 中断：干活的工位被删掉 / 重置所有时卡停在半路。跟 failed 一样，首领可以重新派。
    "interrupted": {"redispatch": "dispatched", "cancel": "cancelled"},
    "done":       {},
    "cancelled":  {},
}
OPEN_STATES = ("queued", "dispatched", "running", "delivered", "reviewing", "accepted", "returned", "blocked")


def next_state(state: str, event: str) -> str | None:
    return TRANSITIONS.get(state, {}).get(event)


def validate_card(card: dict, lang: str | None = None) -> list[str]:
    """Minimal self-contained check: four fields non-empty, well-typed. Returns a list of problems."""
    lg = lang or i18n.lang()
    errs = []
    if not isinstance(card, dict):
        return [i18n.t("card.not_object", lg)]
    if not str(card.get("goal") or "").strip():
        errs.append(i18n.t("card.goal_empty", lg))
    inputs = card.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        errs.append(i18n.t("card.inputs_empty", lg))
    eo = card.get("expected_output")
    if not isinstance(eo, dict) or not eo.get("kind") or eo.get("kind") not in KINDS:
        errs.append(i18n.t("card.eo_kind", lg, list="/".join(KINDS)))
    elif eo.get("kind") != "run" and not eo.get("path"):
        errs.append(i18n.t("card.eo_path", lg))
    acc = card.get("acceptance")
    if not isinstance(acc, dict) or "review" not in acc:
        errs.append(i18n.t("card.acc_review_missing", lg))
    else:
        rv = str(acc.get("review"))
        if rv not in REVIEW_MODES:
            errs.append(i18n.t("card.acc_review_bad", lg, v=rv))
        if acc.get("gates") is not None and not isinstance(acc.get("gates"), list):
            errs.append(i18n.t("card.acc_gates", lg))
    if card.get("on_accept") is not None:
        oa = card["on_accept"]
        if not isinstance(oa, dict) or oa.get("action") not in ("none", "move", "channel"):
            errs.append(i18n.t("card.on_accept", lg))
    if card.get("files") is not None:       # 可选：这张卡打算改的文件或目录，几只猫并行时靠它提醒冲突
        f = card["files"]
        if not isinstance(f, list) or not all(isinstance(x, str) and x.strip() for x in f):
            errs.append(i18n.t("card.files", lg))
    return errs


def normalize_title(card: dict) -> str:
    t = str(card.get("title") or card.get("goal") or "").strip()
    return re.sub(r"\s+", " ", t)[:80]


def card_dir(task_id: str) -> pathlib.Path:
    return config.DATA / "tasks" / task_id


def write_card(task_id: str, card: dict) -> pathlib.Path:
    d = card_dir(task_id)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "card.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=1)
    return p


def read_report(task_id: str) -> str | None:
    p = card_dir(task_id) / "report.md"
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


# ---- templates ----
PKG_TEMPLATES = pathlib.Path(__file__).parent / "templates"

TEMPLATE_HEADER_RE = re.compile(r"<!--[\s\S]*?boxbox template\s+v(\d+)[\s\S]*?-->", re.IGNORECASE)


def _template_version(path: pathlib.Path) -> int:
    """模板文件头的版本号（<!-- boxbox template v2 · x.md -->）；没有头或号写不出来 → 0。"""
    try:
        m = TEMPLATE_HEADER_RE.search(path.read_text(encoding="utf-8")[:400])
    except OSError:
        return 0
    return int(m.group(1)) if m else 0


def template_path(name: str) -> pathlib.Path:
    """data/templates/<name>.md wins (user-editable); seeded from the package copy on first use.
    升级：用户那份的头部版本号 < 包里那份时，先把用户那份改名备份成 <name>.md.v<旧号>.bak
    （自己改过也一样备份，不丢），再拴新版的过去；版本号相同或用户那份更高就不动。"""
    user = config.DATA / "templates" / ("%s.md" % name)
    pkg = PKG_TEMPLATES / ("%s.md" % name)
    if user.exists() and pkg.exists() and _template_version(user) < _template_version(pkg):
        bak = user.with_name("%s.md.v%d.bak" % (name, _template_version(user)))
        try:
            os.replace(user, bak)
        except OSError:
            return user                 # 备份不成（占用等）就不升级，继续用旧模板
    if not user.exists() and pkg.exists():
        user.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pkg, user)
    return user if user.exists() else pkg


def localized(name: str, lang: str | None) -> str:
    """English stations get <name>.en when that template ships; anything else falls back to the Chinese one."""
    if lang == "en" and (PKG_TEMPLATES / ("%s.en.md" % name)).exists():
        return name + ".en"
    return name


def render(name: str, **vars) -> str:
    p = template_path(name)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        text = "$card"  # last resort: the card itself is the prompt
    safe = {k: ("" if v is None else str(v)) for k, v in vars.items()}
    return string.Template(text).safe_substitute(safe)
