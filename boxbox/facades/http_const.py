"""HTTP 层用到的常量：设置项、角色别名、首领规则。"""
from __future__ import annotations

import re

TOOLS = ("get_briefing", "get_board", "get_todo", "get_task", "assign", "review", "resolve", "report", "post", "read_inbox", "wait_for_update")


STATION_ROLES = ("leader", "member")


STATION_RUNNERS = ("manual", "once", "scheduled")


ROLE_ALIASES = {"leader": "leader", "teamleader": "leader", "team leader": "leader", "首领": "leader",
                "member": "member", "teammember": "member", "team member": "member", "打工猫": "member", "打工仔": "member"}


SETTINGS_INTS = {"core_port": (1, 65535), "ack_timeout_s": (1, None), "heartbeat_s": (1, None),
                 "wake_min": (0, None), "member_feedback_max_chars": (120, 4000),
                 "stall_cmd_s": (1, None), "stall_model_s": (1, None), "stall_notool_s": (1, None),
                 "cmd_hard_s": (1, None),
                 "log_tool_tail_chars": (0, 200000), "log_gzip_days": (0, 3650), "log_keep_days": (0, 3650)}


SETTINGS_BOOLS = ("skipped_member", "scene_bubbles", "member_feedback", "tray_notify", "log_full")


_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


COPY_DECOR = ("cost", "note")      # 配饰：单价和备注不跟着复制


COPY_SKIP = ("id", "slot", "cwd", "cwd_from")   # 目录不直接抄，复制时另给新猫建（git worktree 或默认目录）


LEADER_EVENT_KINDS = ("reviewing", "failed", "interrupted", "review", "report", "post", "rest_out", "rest_back", "interrupted_handoff")


LEADER_EVENT_MAX = 5          # 一次最多给首领 5 条


# Cursor 的请求大约 115 秒就自己超时。等满了客户端先报错，code=none 送不回去。
WAIT_MAX_S = 100
WAIT_DEFAULT_S = 45


RUNNING_STATES = "dispatched,running,queued,interrupted"


COPY_TAIL_RE = re.compile(r"^(.*?)([A-F])$")


DISPATCH_EVENT_KINDS = ("assign", "queued", "wrote_card", "scheduled_on", "delivered_receipt",
                        "delivered", "failed", "interrupted", "unreachable", "review", "done",
                        "assign_warning", "start", "feedback")
