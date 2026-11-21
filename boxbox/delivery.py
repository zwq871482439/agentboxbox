"""从已有事件、运行记录和回报拼出任务时间线与交付单。"""
from __future__ import annotations

import json
import re

from . import i18n, runlog, tasks


def _data(ev: dict) -> dict:
    try:
        value = json.loads(ev.get("json") or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _node(nodes: list, ev: dict, kind: str, who: str, lang: str) -> None:
    nodes.append({"kind": kind, "label": i18n.t("delivery.timeline." + kind, lang),
                  "at": ev.get("ts") or "", "who": who or ""})


def timeline(store, task_id: str, lang: str | None = None) -> list[dict]:
    """按实际发生顺序列出派活、每轮开工 / 退回、做完和确认。"""
    lg = lang or i18n.lang()
    task = store.get_task(task_id) or {}
    events = list(reversed(store.events(10000, task_id=task_id)))
    nodes: list[dict] = []
    started = False
    delivered = False
    pending_start = None
    accepted_by = ""
    for ev in events:
        kind = str(ev.get("kind") or "")
        data = _data(ev)
        who = str(ev.get("station") or task.get("assignee") or "")
        if kind == "assign":
            _node(nodes, ev, "assigned", str(task.get("dispatcher") or task.get("created_by") or who), lg)
        elif kind in ("delivered_receipt", "working", "heartbeat", "report_seen"):
            if delivered and not started:
                pending_start = ev
            elif not started:
                _node(nodes, ev, "started", who, lg)
                started = True
        elif kind == "review" and data.get("verdict") in ("return", "return_max"):
            _node(nodes, ev, "returned", who, lg)
            started = False
            delivered = False
            if pending_start is not None:
                _node(nodes, pending_start, "started", str(pending_start.get("station") or who), lg)
                started = True
                pending_start = None
        elif kind == "review" and data.get("verdict") == "accept":
            accepted_by = who
        elif kind == "delivered" or (kind == "report" and data.get("status") == "done"):
            if pending_start is not None:
                _node(nodes, pending_start, "started", str(pending_start.get("station") or who), lg)
                pending_start = None
                started = True
            if not delivered:
                _node(nodes, ev, "delivered", who, lg)
            delivered = True
            started = False
        elif kind == "done":
            _node(nodes, ev, "confirmed", accepted_by or who, lg)
    return nodes


def _report_section(report: str, headings: tuple[str, ...]) -> str:
    if not report:
        return ""
    match = re.search(r"(?mi)^##\s*(?:%s)\s*[：:]?[ \t]*(.*)$" % "|".join(map(re.escape, headings)), report)
    if not match:
        return ""
    body = report[match.end():]
    next_heading = re.search(r"(?m)^##\s", body)
    if next_heading:
        body = body[:next_heading.start()]
    return "\n".join(part for part in (match.group(1).strip(), body.strip()) if part).strip()


def _changed_files(store, task_id: str) -> list[str]:
    files: list[str] = []
    seen = set()
    for run in store.runs_for_task(task_id):
        for line in runlog.read_text(str(run.get("log_path") or "")).splitlines():
            # 运行记录能有十几 MB，任务页开着详情每 5 秒取一次：不含工具调用的行不解析
            if '"toolCall"' not in line or ('"write"' not in line and '"edit"' not in line):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            message = event.get("message") if isinstance(event, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "toolCall" or block.get("name") not in ("write", "edit"):
                    continue
                args = block.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {}
                path = str(args.get("path") or "").strip() if isinstance(args, dict) else ""
                if path and path not in seen:
                    seen.add(path)
                    files.append(path)
    return files


def sheet(store, task_id: str, lang: str | None = None) -> str:
    """固定四栏；原始记录没写的内容留成「没写」，不从别的字段猜。"""
    lg = lang or i18n.lang()
    missing = i18n.t("delivery.missing", lg)
    files = _changed_files(store, task_id)
    files_text = "\n".join("- " + path for path in files) or missing
    report = tasks.read_report(task_id) or ""
    selfcheck = _report_section(report, ("自检结果", "Self-check"))
    try:
        review = (tasks.card_dir(task_id) / "review.md").read_text(encoding="utf-8").strip()
    except OSError:
        review = ""
    checks = []
    if review:
        review_body = "\n".join(review.splitlines()[1:]) if review.startswith("## ") else review
        checks.append("### " + i18n.t("delivery.gates", lg) + "\n" + review_body)
    if selfcheck:
        checks.append("### " + i18n.t("delivery.selfcheck", lg) + "\n" + selfcheck)
    unfinished = _report_section(report, ("没做完或没把握的", "Not finished or unsure"))
    confirm = _report_section(report, ("需要谁做什么", "Who needs to do what"))
    values = (files_text, "\n\n".join(checks) or missing, unfinished or missing, confirm or missing)
    keys = ("files", "checks", "unfinished", "confirm")
    return "\n\n".join("## %s\n%s" % (i18n.t("delivery." + key, lg), value) for key, value in zip(keys, values, strict=True))
