"""工位相关的辅助：召唤、复制、详情、余量。"""
from __future__ import annotations

import pathlib
import re
import subprocess

from .. import config, connectors, i18n, pi_config, providers, quota, tasks
from ..store import now_iso, today_key
from .http_const import COPY_TAIL_RE, DISPATCH_EVENT_KINDS, STATION_ROLES, STATION_RUNNERS
from .http_core import normalize_role
from .http_leader import hire_prompt


def _summon(station: dict, core_url: str, lang: str = "zh") -> dict:
    """「叫醒首领」(§11.1): what a human pastes where, per runner kind.
    lang="en" 给英文版的那几句话（上岗话和贴到哪儿、怎么贴）。"""
    sid = station["id"]
    runner = station.get("runner") or "manual"
    client = station.get("client") or ""
    hint = (connectors.load().get(client) or {}) if client else {}
    out = {"station": sid, "runner": runner, "client": client,
           "chat_box_name": connectors.hint_text(client, "chat_box", lang) if client else "",
           "mcp_menu_hint": connectors.hint_text(client, "menu", lang) if client else "",
           "mcp": None, "prompt": "", "where": "", "steps": []}
    try:
        out["mcp"] = connectors.status(client, project_dir=config.project_dir()) if client in connectors.load() else None
    except Exception:  # noqa: BLE001
        out["mcp"] = None
    if runner == "once":
        out["where"] = i18n.t("api.summon.once.where", lang)
        out["steps"] = [i18n.t("api.summon.once.step1", lang), i18n.t("api.summon.once.step2", lang)]
        return out
    if runner == "scheduled":
        every_min = int((station.get("runner_args") or {}).get("every_min", 30) or 30)
        # 会话模式不挑是哪一家 AI 软件：客户端没登记就说「你常用的 AI 软件」
        app_label = hint.get("label") or client or i18n.t("api.summon.manual.app", lang)
        out["every_min"] = every_min
        # 文件档：只贴一段话，不用配 MCP，靠读写交换文件
        out["exchange"] = "file"
        out["exchange_dir"] = str(config.DATA / "exchange" / sid)
        out["prompt"] = tasks.render(tasks.localized("scheduled-file-member", lang), station=sid, role="member", task_id="", card="",
                                     cwd=station.get("cwd") or "", report_path="", returned_reason="", round="",
                                     tools="", board="", exchange=str(config.DATA / "exchange" / sid))
        out["where"] = i18n.t("api.summon.sched.where", lang, app=app_label, n=every_min)
        out["steps"] = [
            i18n.t("api.summon.sched.exchange.1", lang),
            i18n.t("api.summon.sched.step2", lang, n=every_min, where=i18n.t("api.summon.sched.entry_hint", lang)),
            i18n.t("api.summon.sched.exchange.3", lang, dir=out["exchange_dir"]),
            i18n.t("api.summon.sched.exchange.4", lang, n=every_min * 2),
        ]
        return out
    # manual (leader or a hand-driven member): the hire prompt; the full briefing comes back from get_briefing
    role = station.get("role", "member")
    out["mcp_url"] = connectors.mcp_url(sid, core_url)
    out["prompt"] = hire_prompt(sid, role, core_url, lang)
    out["where"] = i18n.t("api.summon.manual.where", lang,
                          app=hint.get("label", client) or i18n.t("api.summon.manual.app", lang),
                          box=out["chat_box_name"] or i18n.t("api.summon.manual.box", lang))
    out["steps"] = [i18n.t("api.summon.manual.step1", lang),
                    i18n.t("api.summon.manual.step2", lang),
                    i18n.t("api.summon.manual.step3", lang)]
    return out
def _station_errors(st: dict) -> list[str]:
    lg = i18n.lang()
    errs = []
    if not str(st.get("id") or "").strip():
        errs.append(i18n.t("api.err_name_empty", lg))
    role = normalize_role(st.get("role"))
    if role not in STATION_ROLES:
        errs.append(i18n.t("api.err_role", lg))
    runner = st.get("runner")
    if runner not in STATION_RUNNERS:
        errs.append(i18n.t("api.err_runner", lg))
    elif role == "leader":
        if runner != "manual":                    # 首领是你在 AI 软件里开对话，不能让盒子替他干活
            errs.append(i18n.t("api.err_runner_leader", lg))
    else:
        # 打工猫只有两种接活方式：用 API key 自动跑（client 必须是 pi）或会话模式
        if runner == "once" and st.get("client") != "pi":
            errs.append(i18n.t("api.err_runner_member", lg))
        elif runner not in ("once", "scheduled"):
            errs.append(i18n.t("api.err_runner_member", lg))
    if st.get("client") == "pi":                      # only Pi stations carry a pi block (once != pi, e.g. test runners)
        errs += pi_config.validate_pi_block(st.get("pi") or {}, lg)
        errs += _quota_errors(st.get("quota"))       # 查余量设置也只对 Pi 工位有意义
    return errs
def _quota_errors(q) -> list[str]:
    """工位的 quota 块：off / after_run / interval 三档；adapter 认识；custom 要有地址。"""
    if not isinstance(q, dict):
        return []                                      # 老工位没这块，当 off 算
    lg = i18n.lang()
    errs = []
    if q.get("mode", "off") not in ("off", "after_run", "interval"):
        errs.append(i18n.t("api.err_quota_mode", lg))
    if q.get("adapter") and q.get("adapter") not in quota.ADAPTERS:
        errs.append(i18n.t("api.err_quota_adapter", lg, list=" / ".join(quota.ADAPTERS)))
    if q.get("mode") == "interval":
        try:
            if q.get("interval_min") is not None and int(q.get("interval_min")) < 1:
                raise ValueError
        except (TypeError, ValueError):
            errs.append(i18n.t("api.err_quota_interval", lg))
    if q.get("adapter") == "custom" and q.get("mode") != "off":
        c = q.get("custom") or {}
        if not str(c.get("url") or "").strip():
            errs.append(i18n.t("api.err_quota_url", lg))
        if not str(c.get("pct_path") or "").strip() and not str(c.get("remaining_pct_path") or "").strip():
            errs.append(i18n.t("api.err_quota_path", lg))
    return errs
def _copy_name(name: str, items: list[dict]) -> str:
    """复制出来的名字（工牌「复制」）：末尾是 A–F 的就换下一个没人用的字母；
    末尾是数字的接着往上数（minimax2 → minimax3）；其它名字加 2、3。"""
    taken = {str(s.get("id")) for s in items}
    m = COPY_TAIL_RE.match(name or "")
    if m:
        head = m.group(1)
        for c in config.SLOTS:
            if head + c not in taken:
                return head + c
    base = name or i18n.t("api.new_station", i18n.lang())
    m = re.match(r"^(.*?)(\d+)$", base)
    n = int(m.group(2)) + 1 if m else 2
    head = m.group(1) if m else base
    while "%s%d" % (head, n) in taken:
        n += 1
    return "%s%d" % (head, n)
def _running_cards(d, sid: str) -> list[dict]:
    return [t for t in d.store.list_tasks(state="dispatched,running") if t["assignee"] == sid]
def _git(cwd: str, args: list[str]) -> tuple[int, str]:
    """git 用参数列表调，不走 shell。返回 (退出码, 输出)。"""
    p = subprocess.run(["git", "-C", str(cwd)] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120, shell=False)
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
def _is_git_repo(cwd: str) -> bool:
    try:
        rc, out = _git(cwd, ["rev-parse", "--show-toplevel"])
    except (OSError, subprocess.SubprocessError):
        return False
    return rc == 0 and bool(out.splitlines())
def _make_worktree(src_cwd: str, new_id: str) -> tuple[str | None, str]:
    """在原目录旁边建一个 git worktree：<原 cwd>-<新工位 id>（被占就 -2、-3），分支 bx/<新工位 id>，从原目录当前 HEAD 开。
    成功返回 (路径, "")；失败返回 (None, 一句为什么)。"""
    base = "%s-%s" % (str(src_cwd).rstrip("\\/"), new_id)
    for suffix in ("", "-2", "-3", "-4", "-5"):
        cand = base + suffix
        if pathlib.Path(cand).exists():
            continue
        rc, out = _git(src_cwd, ["worktree", "add", "-b", "bx/" + new_id, cand, "HEAD"])
        if rc == 0:
            return cand, ""
        # 分支已经在了（比如删过一只同名的猫，分支留着）→ 不新建，直接用它
        rc2, out2 = _git(src_cwd, ["worktree", "add", cand, "bx/" + new_id])
        if rc2 == 0:
            return cand, ""
        fallback = i18n.t("api.git_exit", i18n.lang(), code=rc)
        return None, (out2 or out or fallback).splitlines()[-1][:160]
    return None, i18n.t("api.git_paths_taken", i18n.lang(), base=base)
def _station_detail(d, sid: str) -> tuple[dict, int]:
    """工位详情（「查看详情」抽屉）：完整配置（不含 key）、连接状态、今天的活、调度记录、余量。"""
    st = config.station(sid)
    if st is None:
        return {"ok": False, "code": "station_unknown",
                "text": i18n.t("api.station_missing", i18n.lang())}, 404
    store = d.store
    today = today_key()
    todays = [t for t in store.tasks_of_station(sid, limit=100) if str(t.get("id") or "").startswith(today)]
    # 成功率口径跟顶栏一致：只算真跑完的（没开工的失败不算失败，中断 / 撤掉的本来就不在 done / failed 里）
    counted = [t for t in todays if t.get("state") == "done"
               or (t.get("state") == "failed" and store.runs_for_task(t["id"]))]
    done = sum(1 for t in counted if t.get("state") == "done")
    failed = len(counted) - done
    evs = [e for e in store.events(80, station=sid) if e.get("kind") in DISPATCH_EVENT_KINDS][:10]
    pi = st.get("pi") or {}
    provider = ""
    if pi.get("provider_id"):
        for p in providers.list_doc().get("providers") or []:      # 清单里有名字就用名字
            if p.get("id") == pi.get("provider_id"):
                provider = str(p.get("name") or p.get("id"))
                break
        provider = provider or str(pi["provider_id"])
    quota_peers = []            # 同一服务商（同 key）的其它工位：额度是共用的一份
    my_provider = providers.station_provider(st) if st.get("client") == "pi" else None
    if my_provider:
        my_key = config.get_secret(sid) or ""
        for s2 in config.stations():
            if s2.get("id") == sid or s2.get("client") != "pi":
                continue
            if providers.station_provider(s2) == my_provider and (config.get_secret(str(s2.get("id") or "")) or "") == my_key:
                quota_peers.append(str(s2.get("id")))
    detail = {
        "ok": True,
        "station": st,                                                  # stations.json 里本来就没有 key（key 在 secrets.json）
        "provider": provider or pi_config.host_of(pi),
        "board": next((r for r in d.board() if r["id"] == sid), {}),
        "picheck": store.kv_get("picheck:" + sid),                    # 最近一次「测试连接」的结果和时间
        "today": {"assigned": len(todays), "done": done, "failed": failed,
                  "rate": round(done / (done + failed), 3) if (done + failed) else None},
        "events": [{"id": e.get("id"), "ts": e.get("ts"), "kind": e.get("kind"),
                    "text": e.get("text"), "task_id": e.get("task_id")} for e in evs],
        "quota": quota.localize(store.kv_get("quota:" + sid)),
        "quota_peers": quota_peers,
        "now": now_iso(),
    }
    return detail, 200
