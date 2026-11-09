"""Path A: Pi with an API key, one process per card (once). Pure Python, no PowerShell (工作计划 2.3).

The core owns its Pi config directory (data/pi, handed to Pi via PI_CODING_AGENT_DIR; see pi_config.py),
so provider names / endpoints / key env var names come from the station's `pi` block that the user
filled in at onboarding, not from ~/.pi/agent/models.json.

Pi runs as `node cli.js --mode json --no-skills --no-prompt-templates --provider boxbox-<id> --model <m> --session-dir <dir> <prompt>`
(never load the user's local ~/.agents skills / prompt templates).
Its stdout is a JSONL event stream (pi_events.py) read on a thread: token usage per assistant message,
tool-call count, last tool, final text, "suspect" detection. stderr is kept (masked) for classification.

Exit contract (same as the old wake-*.ps1): 0 ok, 10 busy, 11 quota, 12 unreachable, 13 auth, 14 route, 1 unknown.
"""
from __future__ import annotations

import datetime as _dt
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading

from .. import classify, config, i18n, pi_catalog, pi_config, pi_events, procjob, runlog, stall, tasks, tmpdir
from .base import Heartbeat, RunHandle, Runner, RunResult

IS_WIN = sys.platform.startswith("win")
MAX_STDERR_LINES = 200
LOG_MARK = "# ---- pi --mode json ----"   # 运行日志里这一轮事件流的起点（补记用量时靠它认哪一轮）
_NODE_NOISE = re.compile(r"^\s*(\(node:\d+\)\s*)?\[?\w*Warning\b", re.I)
# 打工猫的进程不是交互终端。这些口子一开，git / gh 就会等编辑器、分页器或密码，一直不回来。
# 用户自己设了也盖掉：true / cat 马上返回，提交说明沿用 git 已经写好的那份。
QUIET_ENV = {
    "GIT_EDITOR": "true",
    "GIT_SEQUENCE_EDITOR": "true",
    "GIT_MERGE_AUTOEDIT": "no",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_PAGER": "cat",
    "PAGER": "cat",
    "EDITOR": "true",
    "VISUAL": "true",
    "GH_PROMPT_DISABLED": "1",
}


def _now() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def _git_bash_dir() -> str | None:
    """<git root>\\bin so Pi's bash tool lands in Git Bash, not System32\\bash.exe (WSL)."""
    git = shutil.which("git")
    if not git:
        return None
    root = pathlib.Path(git).resolve().parent.parent
    for cand in (root / "bin", root / "usr" / "bin"):
        if (cand / ("bash.exe" if IS_WIN else "bash")).exists():
            return str(cand)
    return None


class _Live:
    """Per-run process state kept by the runner (not persisted)."""

    def __init__(self, proc: subprocess.Popen, log_path: pathlib.Path, pid: int | None = None, lang: str | None = None):
        self.proc = proc
        self.pid = pid if pid is not None else (getattr(proc, "pid", None) if proc is not None else None)
        self.parser = pi_events.PiEventParser(lang)
        self.log_path = log_path
        self.stderr: list[str] = []
        self.last_event_at: str | None = None
        self.first_event_at: str | None = None
        self.progress: dict = {}
        self.lock = threading.Lock()
        self.threads: list[threading.Thread] = []
        self.slim = runlog.Slimmer()          # 记录只记有用的：逐字片段和长命令的重复输出不进文件

    def _pump_stdout(self):
        f = self.proc.stdout
        try:
            for raw in iter(f.readline, b""):
                line = raw.decode("utf-8", "replace")
                with self.lock:
                    ev = self.parser.feed_line(line)
                    if ev is not None:
                        ts = _now()
                        self.last_event_at = ts
                        self.first_event_at = self.first_event_at or ts
                        self.progress = stall.feed(self.progress, ev, ts)
                kept = self.slim.line(line)       # 解析和卡住判断用的是整行；只是写进文件的少了
                if kept is not None:
                    self._log(kept)
        except (OSError, ValueError):
            pass

    def _pump_stderr(self):
        f = self.proc.stderr
        try:
            for raw in iter(f.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                with self.lock:
                    if len(self.stderr) < MAX_STDERR_LINES:
                        self.stderr.append(line)
                self._log("[stderr] " + line + "\n")
        except (OSError, ValueError):
            pass

    def _log(self, text: str):
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(classify.mask(text))
        except OSError:
            pass

    def start_pumps(self):
        for fn in (self._pump_stdout, self._pump_stderr):
            t = threading.Thread(target=fn, daemon=True)
            t.start()
            self.threads.append(t)

    def join(self, timeout: float = 5.0):
        for t in self.threads:
            t.join(timeout)


class PiOnceRunner(Runner):
    mode = "once"

    def __init__(self, station_cfg: dict):
        super().__init__(station_cfg)
        self.pi = station_cfg.get("pi") or {}
        self.live: dict[str, _Live] = {}

    # ---- pre-flight (no tokens) ----
    def preflight(self) -> tuple[str, str]:
        """Return (state, reason). state 'ok' means go."""
        errs = pi_config.validate_pi_block(self.pi, self.lang)
        if errs:
            return "route", i18n.t("runner.pi_incomplete", self.lang, sid=self.station,
                                   errs=i18n.t("runner.list_sep", self.lang).join(errs))
        if not pi_config.key_available(self.cfg):
            return "auth", i18n.t("runner.no_key", self.lang, sid=self.station)
        host = pi_config.host_of(self.pi)
        if host and not classify.tcp_reachable(host):   # 统一在 dispatcher 开工前探（_network_wait），这里只留公网 443 的老预检
            return "unreachable", i18n.t("runner.host_unreachable", self.lang, host=host)
        try:
            pi_config.pi_cli_argv(self.cfg, "x", config.DATA)  # only checks node + cli.js exist
        except FileNotFoundError as e:
            return "route", str(e)
        return "ok", "ok"

    def _ping(self, timeout_s: float) -> tuple[int | None, str]:
        """用同一个 Pi 真发一句最短的话（不带工具、不存会话）。返回（退出码，输出）；超时退出码是 None。
        思考开着发（最省的一档）：请求格式跟派卡时一样，有的模型不许关思考，关着测会冤枉它。"""
        pi_config.write_pi_dir(config.stations())
        rt = pi_config.runtime()
        argv = [rt["node"], rt["cli"], "--print", "--no-tools", "--no-session",
                "--no-skills", "--no-prompt-templates",                     # 这句也不碰用户本机 skills / 提示模板
                "--thinking", "low",
                "--provider", pi_config.provider_name(self.station), "--model", str(self.pi.get("model", "")),
                i18n.t("runner.ping_prompt", self.lang)]
        try:
            r = subprocess.run(argv, env=pi_config.pi_env(self.cfg), capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout_s, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            return None, i18n.t("runner.live_timeout", self.lang, sid=self.station, n=int(timeout_s))
        return r.returncode, ((r.stdout or "") + "\n" + (r.stderr or "")).strip()

    def live_check(self, timeout_s: float = 60.0) -> tuple[str, str]:
        """「测试连接」：preflight 只看配置、有没有 key、端口通不通，填错的 key 也显示「连上了」，
        所以 preflight 过了再真发一句话，按回来的报错分成 忙 / 没额度 / 密钥不对 / 连不上 / 路由不对。
        服务商回话里写明要哪个兼容开关（比如要自适应思考），记进工位设置后再试一次。
        429 / 说太忙：请求已经到了服务商、密钥也认了，算连上（limited），只是这会儿被限流或额度见底。"""
        state, reason = self.preflight()
        if state != "ok":
            return state, reason
        code, out = self._ping(timeout_s)
        healed = None
        if code not in (0, None):
            healed = pi_catalog.apply_heal(self.station, out)
            if healed:
                self.reconfigure(config.station(self.station) or self.cfg)
                code, out = self._ping(timeout_s)
        if code == 0 and out:
            return "ok", (i18n.t("runner.healed", self.lang, what=i18n.t(healed, self.lang)) if healed else "ok")
        if code is None:
            return "unreachable", out
        masked = classify.mask(out)[-300:] or i18n.t("runner.live_unknown", self.lang, code=code)
        st = classify.classify(out)
        if st != "auth" and (st == "busy" or re.search(r"\b429\b", out)):
            return "limited", masked
        return (st if st != "ok" else "unknown"), masked
    def start(self, task_id, run_id, card, prompt, log_path) -> RunHandle:
        state, reason = self.preflight()
        if state != "ok":
            raise RuntimeError(i18n.t("runner.start_err", self.lang, state=state, reason=reason))
        pi_config.write_pi_dir(config.stations())
        cwd = card.get("cwd") or self.cfg.get("cwd") or os.getcwd()
        # 续跑：卡上带着上次的对话记录目录 → 用它 + --continue，接着那段对话往下做
        resume = str(card.get("resume_session") or "").strip()
        sess_dir = pathlib.Path(resume) if resume else (config.DATA / "sessions" / run_id)
        sess_dir.mkdir(parents=True, exist_ok=True)
        argv = pi_config.pi_cli_argv(self.cfg, prompt, sess_dir, continue_session=bool(resume))
        env = pi_config.pi_env(self.cfg)
        tmp_dir = tmpdir.card_tmp(task_id)          # 临时文件放程序目录 tmp\ 里这张卡专用的子目录
        env.update(BOXBOX_TASK_ID=task_id, BOXBOX_RUN_ID=run_id, BOXBOX_STATION=self.station,
                   BOXBOX_CORE="http://127.0.0.1:%s" % config.settings().get("core_port", 8878),
                   BOXBOX_REPORT_PATH=str((tasks.card_dir(task_id) / "report.md")),   # 和 dispatcher._member_prompt 同一个路径
                   BOXBOX_ROUND=str(card.get("round") or 1),                    # 卡上的轮次，拿不到写 1
                   TMP=str(tmp_dir), TEMP=str(tmp_dir), TMPDIR=str(tmp_dir),     # 临时文件别进系统临时目录
                   BOXBOX_TMP_DIR=str(tmp_dir))
        env.update(QUIET_ENV)                                 # 放在后面：盖住用户环境里的编辑器 / 分页器 / 密码提示
        gb = _git_bash_dir()
        if gb:
            env["PATH"] = gb + os.pathsep + env.get("PATH", "")
        log_path = pathlib.Path(log_path)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write("# %s %s run=%s station=%s model=%s cwd=%s\n# prompt:\n%s\n%s\n"
                     % (_now(), task_id, run_id, self.station, self.pi.get("model"), cwd, classify.mask(prompt), LOG_MARK))
        flags = subprocess.CREATE_NO_WINDOW if IS_WIN else 0
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=cwd, env=env, creationflags=flags, **procjob.popen_kwargs())
        procjob.assign(proc)                  # 核心退出 / 崩溃时这个进程跟着结束
        live = _Live(proc, log_path, lang=self.lang)
        live.start_pumps()
        self.live[run_id] = live
        return RunHandle(run_id=run_id, task_id=task_id, station=self.station, pid=proc.pid, started_at=_now(),
                         log_path=str(log_path),
                         extra={"session_dir": str(sess_dir), "continued": bool(resume)})

    # ---- liveness ----
    def delivered(self, handle: RunHandle) -> bool:
        live = self.live.get(handle.run_id)
        if live is None:
            return False
        if live.first_event_at:
            return True                       # the JSON session header arrived: Pi is up
        return live.proc.poll() is None       # still booting; a live pid counts as "came up"

    def lost_process(self, run_id: str) -> bool:
        """这个 run 的进程记录还在不在手上？（运行器被换掉 / 进程表被清空时为真）"""
        return run_id not in self.live

    def reconfigure(self, station_cfg: dict) -> None:
        """工位配置改了、运行器还留着（因为有在跑的进程）：换新配置。"""
        super().reconfigure(station_cfg)
        self.pi = station_cfg.get("pi") or {}

    def adopt(self, run_row: dict) -> RunHandle:
        """按 runs 表里的 pid 重新接管一个还在跑的进程：核心重启过 / 运行器被换掉时用。
        手上没有 Popen（拿不到它的输出管道），只能看这个进程号还在不在。"""
        run_id = run_row["run_id"]
        pid = run_row.get("pid")
        log_path = pathlib.Path(run_row.get("log_path") or "")
        self.live[run_id] = _Live(None, log_path, pid=int(pid or 0), lang=self.lang)
        return RunHandle(run_id=run_id, task_id=run_row["task_id"], station=run_row["station"], pid=pid,
                         session_id=run_row.get("session_id"), started_at=run_row.get("started") or "",
                         log_path=str(log_path), extra={"adopted": True})

    def heartbeat(self, handle: RunHandle) -> Heartbeat:
        live = self.live.get(handle.run_id)
        if live is None:
            return Heartbeat(alive=False, finished=True)
        if live.proc is None:                # 接管的进程：没有 Popen，看进程号还在不在
            alive = procjob.pid_alive(live.pid)
            return Heartbeat(alive=alive, finished=not alive, evidence="pid")
        alive = live.proc.poll() is None
        with live.lock:
            run = live.parser.run
            progress = dict(live.progress) if live.progress else None
            hb = Heartbeat(alive=alive, finished=not alive, last_activity=live.last_event_at,
                           evidence="event" if live.last_event_at else "pid", n_tools=run.tool_calls,
                           progress=progress)
        return hb

    def finish(self, handle: RunHandle) -> RunResult:
        live = self.live.pop(handle.run_id, None)
        if live is None:
            return RunResult(exit=1, status="fail", error=i18n.t("runner.no_record", self.lang))
        if live.proc is None:                # 接管的进程：拿不到退出码，只能说它已经不在了
            return RunResult(exit=1, status="fail", error=i18n.t("runner.gone", self.lang, pid=live.pid))
        try:
            code = live.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            live.proc.kill()
            code = live.proc.wait(timeout=5)
        live.join()
        for f in (live.proc.stdout, live.proc.stderr):
            try:
                if f:
                    f.close()
            except OSError:
                pass
        with live.lock:
            run = live.parser.close()
            summ = live.parser.summary(self.lang)
            stderr_txt = "\n".join(live.stderr)
        tokens = summ.get("tokens")
        err_txt = stderr_txt + "\n" + "\n".join(run.errors)
        # 模型接口连不上了：Pi 自重试用完还是失败（auto_retry_end success=false，退出码还是 0），
        # 或者错误本身就是网络 / 服务端类（超时、502、Connection error…）。这轮没干完，核心要按
        # 「接口连不上」处理：不算交回、不跑质检、不记 failed。报错原文给 dispatcher 写原因用。
        iface_err = run.retry_failed or next((e for e in reversed(run.errors) if classify.network_or_server_error(e)), "")
        if code == 0 and run.settled and not run.errors and not iface_err:
            state = "ok"
        else:
            state = classify.classify(err_txt) if err_txt.strip() else "unknown"
            if state == "unknown" and code == 0 and not iface_err:
                state = "ok"                   # exited clean, just no settled event (older Pi) -> trust exit code
        if iface_err and state == "ok":
            state = "unreachable"               # 12：接口连不上（但只作参考，真相在 iface_error）
        exit_code = classify.EXIT_CODES.get(state, 1)
        error = ""
        if state != "ok":
            # 服务商回的报错优先；stderr 里 Node 自己的警告（证书、实验特性）不是原因，别拿它当原因给人看
            last = (run.errors[-1] if run.errors else "") or next(
                (ln for ln in reversed(live.stderr) if ln.strip() and not _NODE_NOISE.match(ln)), "")
            error = classify.mask(last)[:300] or i18n.t("runner.exit_code", self.lang, code=code)
        status = "fail" if state != "ok" else ("suspect" if summ.get("suspect") else "ok")
        try:
            with open(live.log_path, "a", encoding="utf-8") as fh:
                fh.write("# ---- %s (pi exit %s, boxbox exit %d) tools=%s tokens=%s ----\n"
                         % (state, code, exit_code, summ.get("tools"), tokens))
        except OSError:
            pass
        try:
            # 卡被中断时（handle.extra["keep_session"]）不删对话记录目录 —— 下次要靠它接着做；
            # 接口报错断在半路的也留着：猫歇完回来要接着这段对话往下做
            keep = bool((handle.extra or {}).get("keep_session")) or (bool(iface_err) and run.tool_calls > 0)
            if not keep:
                tmpdir.rmtree_safe(handle.extra.get("session_dir") or "", ignore_errors=True)  # one card = one throwaway session
        except OSError:
            pass
        # 最后几行要带给收尾：live 马上丢掉，日志里那份是打过码的，这里留原文
        stderr_tail = "\n".join([ln for ln in stderr_txt.splitlines() if ln.strip()][-5:])
        return RunResult(exit=exit_code, status=status, tokens=tokens, error=error,
                         suspect_why=summ.get("suspect_why") or "", session_id=run.session_id,
                         n_tools=int(summ.get("tools") or 0), iface_error=(iface_err[:200] if iface_err else ""),
                         stderr=stderr_tail, split=summ.get("split"))

    def stop(self, run_id: str) -> bool:
        """停掉这一次运行的整棵进程树。记录先留着，finish / discard 再收。"""
        live = self.live.get(run_id)
        if live is None:
            return False
        if live.proc is not None:
            procjob.kill_tree(live.proc)
            return live.proc.poll() is not None
        return procjob.kill_pid(live.pid)

    def discard(self, run_id: str) -> None:
        """进程已经停了：丢掉记录、关上管道。不删对话目录（撤卡不走 finish）。"""
        live = self.live.pop(run_id, None)
        if live is None or live.proc is None:
            return
        for f in (live.proc.stdout, live.proc.stderr):
            try:
                if f:
                    f.close()
            except OSError:
                pass

    def stop_all(self) -> list[str]:
        """核心退出：结束这个工位所有在跑的 Pi 进程（连子进程），返回被中断的 run_id。
        之后照常调 finish() 收尾：进程已经没了，finish() 会拿到非 0 退出码和已经记下的 token。"""
        ids = list(self.live)
        for rid in ids:
            procjob.kill_tree(self.live[rid].proc)
        return ids


def make_runner(station_cfg: dict) -> Runner | None:
    """Factory: once/pi (path A) and scheduled (path C) exist."""
    mode = station_cfg.get("runner")
    if mode == "once" and station_cfg.get("client") == "pi":
        return PiOnceRunner(station_cfg)
    if mode == "scheduled":
        from .scheduled import ScheduledRunner
        return ScheduledRunner(station_cfg)
    return None
