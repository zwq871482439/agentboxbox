"""Watchdog thread: heartbeats for open runs, finish detection, 'dispatched but not started' marks,
leader silence -> badge. Never kills anything (§六)."""
from __future__ import annotations

import datetime as _dt
import threading
import time

from . import config, exchange, i18n, procjob, tasks, tmpdir
from .dispatcher import INT_CRASH
from .store import now_iso


class Watchdog(threading.Thread):
    def __init__(self, dispatcher):
        super().__init__(name="boxbox-watchdog", daemon=True)
        self.d = dispatcher
        self.stop_flag = threading.Event()
        self._last_tmp_clean = 0.0            # 上次清临时文件的时间（每小时一次）

    def run(self):
        while not self.stop_flag.is_set():
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001 - the watchdog must never die
                try:
                    self.d.store.event("watchdog_error", str(e)[:200])
                except Exception:
                    pass
            self.stop_flag.wait(float(config.settings().get("heartbeat_s", 15)))

    def tick(self):
        store = self.d.store
        for run in store.open_runs():
            handle = self.d.handles.get(run["run_id"])
            st = config.station(run["station"])
            # 优先用起这个 run 的那个运行器（配置改了以后老运行器可能已经挪到 retired）
            runner = self.d.run_owners.get(run["run_id"]) or (self.d.runner_for(st) if st else None)
            if handle is None and runner is not None and runner.mode == "scheduled":
                # path C: there is no process to lose — rebuild the handle from the runs row and keep watching
                handle = runner.adopt(run)
                self.d.handles[run["run_id"]] = handle
            if runner is not None and runner.lost_process(run["run_id"]):
                # 运行器被换掉 / 进程表丢了 → 先看 runs 表里的 pid 还在不在：
                # 还在就重新接管（Pi 进程还在干活，核心继续管它），不在才按结束处理
                if procjob.pid_alive(run.get("pid")):
                    handle = runner.adopt(run)
                    self.d.handles[run["run_id"]] = handle
                    store.event("adopted", i18n.t("ev.adopted", self.d.lang(), sid=run["station"]),
                                run["station"], run["task_id"])
                else:
                    handle = None
            if handle is None or runner is None:
                # 进程真不在了 = 上次没正常退出（核心崩了 / 被任务管理器结束）：卡记「中断」，
                # 不是「失败」——下次打开可以接着做（对话记录留着）。
                from .runners import RunResult
                self.d.interrupt_run(run["run_id"],
                                     RunResult(exit=1, status="fail", error=i18n.t("why.crash", self.d.lang())),
                                     why=i18n.t("why.crash", self.d.lang()), kind=INT_CRASH)
                continue
            if runner.mode == "scheduled":
                # 定时任务工位：看文件等价于看回报
                t = store.get_task(run["task_id"])
                rnd = int((t or {}).get("round") or run.get("attempt") or 1)
                d = tasks.card_dir(run["task_id"])
                rep = d / "report.md"
                if rep.is_file() and not handle.extra.get("picked_at"):
                    # report.md 出现 = 交回了回报（文件档拿不到领走时间，就用这个时间当开工时间）
                    now = now_iso()
                    handle.extra["picked_at"] = now
                    store.update_run(run["run_id"], first_activity=run["first_activity"] or now, last_activity=now, status="running")
                    if t and t["state"] == "queued":
                        store.update_task(t["id"], state="running")
                    store.station_touch(run["station"], state="running", task_id=run["task_id"], since=now)
                    self._scheduled_came(run["station"], now)
                    try:
                        nbytes = rep.stat().st_size
                    except OSError:
                        nbytes = 0
                    store.exchange_add(run["station"], run["task_id"], rnd, "report_seen", nbytes)
                    store.event("report_seen", i18n.t("ev.report_seen", sid=run["station"]), run["station"], run["task_id"])
                if (d / "DONE").is_file():
                    # DONE 出现 = 等价于 report(done)，摘要取 report.md 里「## 做了什么」下第一段
                    self._scheduled_came(run["station"], now_iso())
                    summary = exchange.report_summary(tasks.read_report(run["task_id"]) or "")
                    store.exchange_add(run["station"], run["task_id"], rnd, "done_seen", 0)
                    store.event("done_seen", i18n.t("ev.done_seen", sid=run["station"]), run["station"], run["task_id"])
                    self.d.report(run["task_id"], "done", summary, run["station"])
                    continue
            hb = runner.heartbeat(handle)
            if hb.last_activity:
                fields = {"last_activity": hb.last_activity}
                if not run["first_activity"]:
                    fields["first_activity"] = hb.last_activity
                    t = store.get_task(run["task_id"])
                    if t and t["state"] == "dispatched":
                        store.update_task(t["id"], state="running")
                        store.station_touch(run["station"], state="running", task_id=t["id"], since=now_iso())
                        store.event("running", i18n.t("ev.working", self.d.lang(), sid=run["station"]), run["station"], t["id"], data={"evidence": hb.evidence})
                store.update_run(run["run_id"], **fields)
            if hb.finished:
                file_mode = runner.mode == "scheduled" and not handle.extra.get("reported")
                t_row = store.get_task(run["task_id"]) if file_mode else None
                self.d.on_run_finished(run["run_id"], runner.finish(handle))
                if file_mode:
                    # 超时：领走后 work_timeout_min 没 DONE（§6 action=timeout）
                    store.exchange_add(run["station"], run["task_id"], int((t_row or {}).get("round") or 1), "timeout", 0)
                    store.event("timeout", i18n.t("ev.timeout_file", sid=run["station"]), run["station"], run["task_id"])
        self._quota_interval()
        self._badge()
        self._tmp_clean()
        self._scheduled_seen()
        try:
            self.d.start_ready_queued()   # 自愈：排队里还有能开工的（比如核心重启过）就补开
        except Exception as e:  # noqa: BLE001
            try:
                store.event("watchdog_error", i18n.t("ev.wd.start_err", err=e))
            except Exception:  # noqa: BLE001
                pass
        try:   # 等接口的排队卡：到 network_retry_s 的点就再探一次，通了自动开工（内部自己限频）
            self.d.retry_network_queued()
        except Exception as e:  # noqa: BLE001
            try:
                store.event("watchdog_error", i18n.t("ev.wd.retry_err", err=e))
            except Exception:  # noqa: BLE001
                pass
        try:   # 歇着的猫到点回来：变回「闲」并接排队的卡（额度用完 / 被限流 / 服务端出错）
            self.d.restore_resting()
        except Exception as e:  # noqa: BLE001
            try:
                store.event("watchdog_error", i18n.t("ev.wd.back_err", err=e))
            except Exception:  # noqa: BLE001
                pass
        try:   # 回来了但没卡可接的：也说一声（首领听得到）
            self.d.announce_back()
        except Exception:  # noqa: BLE001
            pass

    def _scheduled_came(self, station_id: str, now: str) -> None:
        """定时任务来过了（交回了回报就是证据）：记下这次来的时间，第一次来时留个事件。"""
        store = self.d.store
        first = not (store.station_states().get(station_id) or {}).get("last_scheduled_at")
        store.station_touch(station_id, last_scheduled_at=now, runner="scheduled")
        if first:
            store.event("scheduled_on", i18n.t("ev.scheduled_on", sid=station_id), station_id)

    def _scheduled_seen(self) -> None:
        """定时任务每次被叫起来都写 seen.txt：文件比上次记的时间新 = 它来过（没活也算）。"""
        states = self.d.store.station_states()
        for st in config.stations():
            if st.get("runner") != "scheduled":
                continue
            sid = st.get("id")
            if not sid:
                continue
            try:
                mtime = exchange.seen_path(sid).stat().st_mtime
            except OSError:
                continue                      # 还没写过（或读不到）就跳过，不报错
            last = (states.get(sid) or {}).get("last_scheduled_at")
            if last:
                try:
                    if int(mtime) <= int(_dt.datetime.fromisoformat(last).timestamp()):
                        continue              # 还没更新过（按秒比，避免同一秒里反复记）
                except ValueError:
                    pass
            at = _dt.datetime.fromtimestamp(mtime).astimezone().replace(microsecond=0).isoformat()
            self._scheduled_came(sid, at)

    def _tmp_clean(self):
        """每小时清一次临时文件——已结束、且最后修改超过 tmp_keep_days 天的卡目录。
        在跑的卡（dispatched / running / queued / interrupted）目录保留：中断的卡还能接着做。"""
        now = time.time()
        if now - self._last_tmp_clean < 3600:
            return
        self._last_tmp_clean = now
        try:
            keep = int(config.settings().get("tmp_keep_days", 1))
            rows = self.d.store.list_tasks(state="dispatched,running,queued,interrupted", limit=1000)
            running = [str(t.get("id")) for t in rows if t.get("id")]
            removed = tmpdir.clean(keep, running)
            if removed:
                self.d.store.event("tmp_cleaned", i18n.t("ev.tmp_cleaned", n=removed))
        except Exception as e:  # noqa: BLE001 - 清临时文件坏了不能带崩看门狗
            try:
                self.d.store.event("watchdog_error", i18n.t("ev.wd.clean_err", err=e))
            except Exception:
                pass

    def _quota_interval(self):
        """设了「每 N 分钟查余量」的工位到点就查（后台线程，不阻塞看门狗）。"""
        from . import quota
        for st in quota.due_stations(self.d.store):
            try:
                quota.spawn(st, self.d.store)
            except Exception:  # noqa: BLE001 - 查余量坏了不能带崩看门狗
                continue

    def _badge(self):
        """Tray badge flag (kv, 留给旧代码；级别以 /api/meta 的 alerts 为准，这里不再往动态写 badge 事件)。
        Red only for things a human must do:
        - cards whose acceptance.review=user (td.user_count);
        - the 首领 has leader-side work piling up but has been silent too long (summon_leader);
        - a scheduled station whose client-side timer stopped firing.
        Leader-side work (待验收 / 卡住 / 打回待定 / 失败) is between the 首领 and its members: counted in leader_todo, never red."""
        s = config.settings()
        td = self.d.todo()
        silent_min = None
        if self.d.leader_last_seen:
            try:
                silent_min = int((_dt.datetime.now().astimezone() - _dt.datetime.fromisoformat(self.d.leader_last_seen)).total_seconds() // 60)
            except ValueError:
                silent_min = None
        leader_quiet = td["leader_count"] > 0 and (silent_min is None or silent_min >= int(s.get("wake_min", 30)))
        late = [b["id"] for b in self.d.board() if b.get("scheduled_late")]
        you = int(td["user_count"]) + len(late)
        badge = {"red": bool(you or leader_quiet), "todo": you, "leader_todo": td["leader_count"],
                 "scheduled_late": late, "leader_silent_min": silent_min,
                 "summon_leader": leader_quiet, "at": now_iso()}
        self.d.store.kv_set("badge", badge)
