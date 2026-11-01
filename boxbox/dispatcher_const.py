"""派卡用到的常量：排队原因、歇着退避、中断续跑。"""
from __future__ import annotations

WAIT_LEGACY = "concurrency"   # 老版本按服务商限并发时写下的排队原因：现在没这个限制了，老卡当普通排队卡处理


WAIT_BUSY = "busy"


WAIT_NETWORK = "network"


WAIT_REST = "rest"


REST_REASONS = ("quota", "busy", "network", "server")   # 歇着的机器原因码（给用户看的话在词表里）


REST_BACKOFF = (2, 5, 10, 20)


REST_KV = "resting"


REST_TRY_KV = "rest_tries"


NET_RETRY_KEY = "iface_retries"


IFACE_RETRIES = 3


WAIT_REASON_KEY = "wait_reason"


CONFLICT_STATES = "queued,dispatched,running,returned"


INT_EXIT = "exit"


INT_CRASH = "crash"


RESUME_SESSION = "resume_session"


RESUME_AT = "resume_at"


IFACE_WHY = "iface_why"      # 卡上记着这次是被模型接口打断的（原因一句话，喂给猫的提示词用）


INTERRUPT_KIND = "interrupt_kind"


ASKED_KV = "interrupted_asked"


