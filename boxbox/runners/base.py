"""Runner interface (§2.2). The core waits; the model never does.

mode: once (A: Pi with API key; B: zcode -p / claude -p / codex exec / agent -p)
      hold (B: a protocol process the core keeps alive)
      scheduled (C: the client's own timer triggers a session that reads the exchange file)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import i18n

EXIT_WORDS = {0: "ok", 10: "busy", 11: "quota", 12: "unreachable", 13: "auth", 14: "route", 1: "other"}


@dataclass
class RunHandle:
    run_id: str
    task_id: str
    station: str
    pid: int | None = None
    session_id: str | None = None
    started_at: str = ""
    log_path: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Heartbeat:
    alive: bool
    last_activity: str | None = None
    evidence: str = ""          # pid | log | event | tool
    n_tools: int | None = None
    finished: bool = False       # process gone; call finish()


@dataclass
class RunResult:
    exit: int
    status: str                  # ok | fail | suspect
    tokens: dict | None = None   # {in,out,cr,cw,turns,source}
    commits: int | None = None
    dirty: int | None = None
    report_path: str | None = None
    session_id: str | None = None
    error: str = ""
    suspect_why: str = ""
    n_tools: int | None = None    # 这一轮事件流里调过几次工具（Pi），用来分「回排队」还是「进中断」
    iface_error: str = ""         # 模型接口连不上了（自重试失败 / 网络类报错）：报错原文，空 = 不是这件事


class Runner:
    mode = "once"

    def __init__(self, station_cfg: dict):
        self.cfg = station_cfg
        self.station = station_cfg["id"]
        lg = station_cfg.get("lang")
        self.lang = lg if lg in ("zh", "en") else i18n.lang()

    def start(self, task_id: str, run_id: str, card: dict, prompt: str, log_path) -> RunHandle:
        raise NotImplementedError

    def delivered(self, handle: RunHandle) -> bool:
        """Launcher-level receipt: the process came up. No model call involved."""
        raise NotImplementedError

    def heartbeat(self, handle: RunHandle) -> Heartbeat:
        raise NotImplementedError

    def finish(self, handle: RunHandle) -> RunResult:
        raise NotImplementedError

    def lost_process(self, run_id: str) -> bool:
        """这个运行器是不是把某个 run 的进程记录弄丢了？（运行器被换掉 / 进程表被清空时为真）
        底下返回 False：不知道就当没丢（老运行器、假运行器不受影响）。"""
        return False

    def reconfigure(self, station_cfg: dict) -> None:
        """工位配置改了、运行器还留着（因为有在跑的进程）：把配置换成新的。
        在跑的那张卡不受影响（进程已经起来了），下一张卡用新配置。"""
        self.cfg = station_cfg

    def adopt(self, run_row: dict) -> RunHandle:
        """按 runs 表里的一行重新接管一个 run（核心重启过 / 运行器被换掉以后）。"""
        raise NotImplementedError

    def stop_all(self) -> list[str]:
        """核心退出时结束本运行器起的所有进程，返回被中断的 run_id。没有自己进程的运行器什么都不做。"""
        return []
