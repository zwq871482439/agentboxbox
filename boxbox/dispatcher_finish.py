"""收尾：卡跑完了怎么记账。"""
from __future__ import annotations

import json

from . import classify, exchange, fail_why, gates, i18n, pi_catalog, tasks, tmpdir
from .dispatcher_const import (
    IFACE_RETRIES,
    IFACE_WHY,
    NET_RETRY_KEY,
    NOTE_FOLLOW_MAX,
    QUEUE_FRONT,
    RESUME_AT,
    RESUME_SESSION,
    WAIT_BUSY,
    WAIT_NETWORK,
    WAIT_REASON_KEY,
    WAIT_REST,
)
from .dispatcher_util import _every_min, _git_head, _hhmm, _who
from .runners import RunResult
from .store import now_iso


def _json_obj(ev: dict) -> dict:
    try:
        data = json.loads(ev.get("json") or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _note_text(notes: list) -> str:
    return "\n".join(str(n.get("text") or "") for n in notes)


class FinishMixin:
    def on_run_finished(self, run_id: str, res: RunResult) -> None:
        run = self.store.get_run(run_id)
        if run is None or run["ended"]:
            return
        t = self.store.get_task(run["task_id"])
        if t is not None and (res.exit != 0 or res.iface_error) and self._heal_compat(run_id, run, t, res):
            return
        if res.iface_error:
            self._close_run(run_id, res, task_failed=False)   # 接口连不上：不是交付也不是失败，先把运行收尾
            self._after_iface_error(run, t, res)
            self._quota_after_run(run["station"])
            self.start_ready_queued()
            return
        # Pi 猫没有盒子的工具，这一轮里看不到收件箱。正常退出、过质检之前，有新留言就接着同一段对话处理。
        if (res.exit == 0 and t is not None and t["state"] in ("dispatched", "running")
                and self._notes_pi(self.station(run["station"]))):
            if self._try_follow_notes(run, t, res):
                return
            self._park_leftover_notes(run, t)
        failed = res.exit != 0
        self._close_run(run_id, res, task_failed=failed and t is not None and t["state"] in ("dispatched", "running"))
        self._quota_after_run(run["station"])
        self.start_ready_queued()   # 这张卡结束（交付 / 失败）了：同服务商排队的下一张自动开工
        if t is None or failed:
            return
        if t["state"] in ("dispatched", "running"):
            self._reset_rest_tries(run["station"])   # 干成了：歇着的退避次数清零
            self.store.update_task(t["id"], state="delivered", delivered_at=now_iso())
            self.store.event("delivered", i18n.t("ev.delivered", self.lang(), sid=run["station"],
                                                  suspect=i18n.t("ev.delivered.suspect", self.lang()) if res.status == "suspect" else ""),
                             run["station"], t["id"])
            self._after_delivered(t["id"])
    def _notes_pi(self, st: dict | None) -> bool:
        """Pi 一次性开工才由盒子代转留言。会话模式的猫自己会读收件箱。"""
        return bool(st) and st.get("client") == "pi" and st.get("runner") == "once"
    def note_receipt(self, receiver: str, lang: str) -> str:
        """post 的回执：说清楚对方什么时候能看到，不说已经送到。"""
        st = self.station(receiver) or {}
        if not self._notes_pi(st):
            return i18n.t("tool.posted_inbox", lang, sid=receiver)
        for row in self.store.list_tasks(state="dispatched,running"):
            if row["assignee"] == receiver:
                return i18n.t("tool.posted_running", lang, sid=receiver, tid=row["id"])
        return i18n.t("tool.posted_next", lang, sid=receiver)
    def _splice_pending_notes(self, st: dict, prompt: str) -> tuple[str, list]:
        """闲着时的留言拼到说明末尾。先不标已读：进程没拉起来就还留在收件箱。"""
        notes = self.store.unread_messages(st["id"])
        if not notes:
            return prompt, []
        extra = i18n.t("card.notes.pending", self.lang_of(st["id"]), text=_note_text(notes))
        return prompt + "\n\n" + extra, notes
    def _note_follow_count(self, t: dict) -> int:
        rnd = int(t.get("round") or 1)
        n = 0
        for ev in self.store.events_by_kind(t["id"], "note_follow"):
            if int(_json_obj(ev).get("round") or 0) == rnd:
                n += 1
        return n
    def _try_follow_notes(self, run: dict, t: dict, res: RunResult) -> bool:
        """有未读留言就用 --continue 接着跑。同一轮、不加轮数。接不上（到了次数 / 没有留言）返回 False。
        这一轮的运行已经收掉时返回 True，调用方不要再按交回记账。"""
        if self._note_follow_count(t) >= NOTE_FOLLOW_MAX:
            return False
        notes = self.store.unread_messages(run["station"], since=str(run.get("started") or ""))
        if not notes:
            return False
        st = self.station(run["station"])
        runner = self.runner_for(st) if st else None
        if runner is None:
            return False
        card = dict(t.get("card") or {})
        # 只这一次接着上次的对话：不写回卡，打回重派仍是新开一段
        card[RESUME_SESSION] = self._session_dir_of(run)
        prompt = i18n.t("card.notes.follow", self.lang_of(st["id"]), text=_note_text(notes))
        self._close_run(run["run_id"], res, task_failed=False)
        self._quota_after_run(run["station"])
        out = self._launch(st, runner, t["id"], card, attempt=int(t.get("round") or 1), prompt=prompt, take_notes=False)
        fresh = self.store.get_task(t["id"]) or {}
        if fresh.get("state") in ("dispatched", "running") and out.get("code") == "delivered":
            self.store.mark_messages_read([n["id"] for n in notes])
            self.store.event("note_follow", i18n.t("ev.note_follow", self.lang(), n=len(notes)),
                             run["station"], t["id"], data={"round": int(t.get("round") or 1), "n": len(notes)})
            return True
        self.start_ready_queued()
        return True
    def _park_leftover_notes(self, run: dict, t: dict) -> None:
        """这一轮已经接满两次：剩下的留言不再跟，交回时在待办里告诉首领。"""
        if self._note_follow_count(t) < NOTE_FOLLOW_MAX:
            return
        notes = self.store.unread_messages(run["station"], since=str(run.get("started") or ""))
        if not notes:
            return
        texts = [str(n.get("text") or "") for n in notes]
        self.store.mark_messages_read([n["id"] for n in notes])
        self.store.event("notes_left", i18n.t("todo.notes_left", self.lang(), n=len(notes)),
                         run["station"], t["id"], data={"n": len(notes), "texts": texts})
    def _notes_left_reason(self, task_id: str, lg: str) -> str:
        rows = self.store.events_by_kind(task_id, "notes_left")
        if not rows:
            return ""
        data = _json_obj(rows[-1])
        n = int(data.get("n") or 0)
        if n <= 0:
            return ""
        reason = i18n.t("todo.notes_left", lg, n=n)
        texts = [str(x) for x in (data.get("texts") or []) if str(x).strip()]
        if texts:
            reason = reason + "\n" + "\n".join(texts)
        return reason
    def _heal_compat(self, run_id: str, run: dict, t: dict, res: RunResult) -> bool:
        """服务商回话里写明这个模型要哪个兼容开关（比如要自适应思考）：记进工位设置，这张卡马上照新设置重跑。
        同一个开关只改一次——改过了还报一样的错，就照常记失败。"""
        if t["state"] not in ("dispatched", "running"):
            return False
        label = pi_catalog.apply_heal(run["station"], "%s\n%s" % (res.error or "", res.iface_error or ""))
        if not label:
            return False
        lg = self.lang()
        self._close_run(run_id, res, task_failed=False)
        card = dict(t["card"])
        card[WAIT_REASON_KEY] = WAIT_BUSY
        card.pop("returned_reason", None)
        if (res.n_tools or 0) > 0:                   # 干到一半才被拦：接着那段对话做
            card[RESUME_SESSION] = self._session_dir_of(run)
            card[RESUME_AT] = _hhmm(run.get("last_activity") or run.get("started") or "")
            card[IFACE_WHY] = i18n.t(label, lg)
        tasks.write_card(t["id"], card)
        self.store.update_task(t["id"], state="queued", returned_reason=None, card_json=json.dumps(card, ensure_ascii=False))
        self.store.event("compat_fixed", i18n.t("ev.compat_fixed", lg, sid=run["station"], what=i18n.t(label, lg)),
                         run["station"], t["id"])
        self.start_ready_queued()
        return True
    def _after_iface_error(self, run: dict, t: dict | None, res: RunResult) -> None:
        """模型接口连不上了（Pi 自重试失败 / 网络服务端类报错，以退出码 0 结束）：不算交回、不跑质检、不记 failed。
        额度用完 / 被限流 / 服务端出错 / 连不上 → 这只猫出去玩了（歇着），核心自动判、自动解除；
        卡排队等它回来（到点自动开工），接口连不上的那种复用 探测（_network_wait / network_retry_s）。
        这一轮一个工具都没调 → 卡回排队（同一张卡最多自动重来 3 次，超过进 interrupted 等首领处置）；
        调过工具（干到一半断的）→ 卡也回排队：记下这一轮的对话目录，猫歇完回来接着做（--continue 续那段对话）。"""
        if t is None:
            return
        lg = self.lang()
        err = str(res.iface_error or "")
        masked = classify.mask(err) or i18n.t("ack.iface_masked", lg)
        kind = classify.classify(err)
        reason = {"quota": "quota", "busy": "busy"}.get(kind)
        if kind == "unreachable":
            reason = "server" if classify.server_error(err) else "network"
        if reason:
            self.rest_after_error(run["station"], err, reason)      # 这只猫出去玩了
        if (res.n_tools or 0) > 0:
            self._iface_resume(run, t, masked, reason)     # 干到一半断的：卡回排队，猫回来接着做
            return
        if reason in ("quota", "busy", "server"):
            # 额度用完 / 被限流 / 服务端出错：卡排队等它回来（核心到点自己恢复）
            rest = self.rest_of(run["station"]) or {}
            card = dict(t["card"])
            card[WAIT_REASON_KEY] = WAIT_REST
            card.pop(NET_RETRY_KEY, None)
            card.pop("returned_reason", None)
            tasks.write_card(t["id"], card)
            self.store.update_task(t["id"], state="queued", returned_reason=None, card_json=json.dumps(card, ensure_ascii=False))
            self.store.event("queued", i18n.t("ev.queued_rest", lg, why=i18n.t("rest.reason." + reason, lg), masked=masked,
                                              sid=run["station"], when=self.rest_when(rest.get("hint") or "", lg)),
                             run["station"], t["id"])
            return
        why = i18n.t("ack.iface_down", lg, masked=masked)
        tries = int((t.get("card") or {}).get(NET_RETRY_KEY) or 0) + 1
        card = dict(t["card"])
        if tries > IFACE_RETRIES:
            card.pop(NET_RETRY_KEY, None)
            tasks.write_card(t["id"], card)
            self.store.update_task(t["id"], state="interrupted", card_json=json.dumps(card, ensure_ascii=False), returned_reason=why)
            self.store.event("interrupted", i18n.t("ev.interrupted_iface", lg, sid=run["station"], n=IFACE_RETRIES),
                             run["station"], t["id"])
            return
        card[NET_RETRY_KEY] = tries
        card[WAIT_REASON_KEY] = WAIT_NETWORK
        card.pop("returned_reason", None)
        tasks.write_card(t["id"], card)
        self.store.update_task(t["id"], state="queued", returned_reason=None, card_json=json.dumps(card, ensure_ascii=False))
        self.store.event("queued", i18n.t("ev.queued_retry", lg, why=why, tries=tries, total=IFACE_RETRIES),
                         run["station"], t["id"])
    def _iface_resume(self, run: dict, t: dict, masked: str, reason: str | None) -> None:
        """接口报错断在半路（这一轮调过工具）的卡：不记「中断」，卡回排队等猫回来接着做。
        卡上记好这一轮的对话目录（resume_session）和被打断的时间，猫回来时用 --continue 续那段对话；
        同一张卡因为接口报错自动续跑最多 IFACE_RETRIES 次，超过才记「中断」交给首领定。"""
        lg = self.lang()
        card = dict(t.get("card") or {})
        tries = int(card.get(NET_RETRY_KEY) or 0) + 1
        if tries > IFACE_RETRIES:
            card.pop(NET_RETRY_KEY, None)
            tasks.write_card(t["id"], card)
            why = i18n.t("ack.iface_repeat", lg, n=tries)
            self.store.update_task(t["id"], state="interrupted", card_json=json.dumps(card, ensure_ascii=False),
                                   returned_reason=why)
            self.store.event("interrupted", i18n.t("ev.interrupted_iface2", lg, sid=run["station"], n=tries),
                             run["station"], t["id"])
            return
        at = _hhmm(run.get("last_activity") or run.get("started") or "")
        card[NET_RETRY_KEY] = tries
        card[RESUME_SESSION] = self._session_dir_of(run)
        card[RESUME_AT] = at
        card[IFACE_WHY] = masked
        card[WAIT_REASON_KEY] = WAIT_NETWORK if reason in (None, "network") else WAIT_REST
        card.pop("returned_reason", None)
        tasks.write_card(t["id"], card)
        self.store.update_task(t["id"], state="queued", returned_reason=None, card_json=json.dumps(card, ensure_ascii=False))
        self.store.event("queued", i18n.t("ev.queued_resume", lg,
                                           why=i18n.t("rest.reason." + (reason or "network"), lg), masked=masked,
                                           sid=run["station"], at=at or i18n.t("ev.just_now", lg),
                                           tries=tries, total=IFACE_RETRIES),
                         run["station"], t["id"])
    def _close_run(self, run_id: str, res: RunResult, task_failed: bool) -> None:
        run = self.store.get_run(run_id)
        if run is None or run.get("status") == "cancelled":
            return                                 # 撤掉已经收成 cancelled，后到的收尾不能再改成失败
        rng = run.get("commit_range")
        if rng and rng.endswith(".."):
            head = _git_head(run.get("worktree"))
            rng = rng + (head or "")
        self.store.update_run(run_id, ended=now_iso(), exit=res.exit, status=res.status, commits=res.commits, dirty=res.dirty,
                              commit_range=rng,
                              tokens_json=json.dumps(res.tokens) if res.tokens else None, error=res.error or None,
                              split_json=json.dumps(res.split, ensure_ascii=False) if res.split else None)
        if res.tokens and res.tokens.get("source"):
            from . import tokens as _tok
            _tok.record(self.store, run, res.tokens)
        self.handles.pop(run_id, None)
        self.run_owners.pop(run_id, None)
        self.store.station_touch(run["station"], state="idle", task_id=None, since=now_iso())
        if task_failed:
            # 密钥不对 / 模型 id 不存在不会自己好：工位退出可派名单，待办写明是配置问题。
            # 其余：调过工具的写清断在哪；一个工具都没调的照旧（有错误信息用它，没有就写被结束、退出码多少）
            lg = self.lang()
            raw = str(res.error or "").strip()
            if self._config_failure(res):
                quote = self.config_quote(raw)
                why = i18n.t("todo.config_bad", lg, sid=run["station"],
                             why=quote or i18n.t("ack.config_no_why", lg))
                self.mark_config_bad(run["station"], raw)
                text, data = why, {"config": True}
            else:
                task = self.store.get_task(run["task_id"]) or {}
                built = fail_why.for_failure(run, res, task.get("card") or {}, lg, run["station"])
                if built is None:
                    why = raw or i18n.t("ack.proc_killed", lg, exit=res.exit)
                    text = i18n.t("ev.failed", lg, sid=run["station"], exit=res.exit,
                                  err=i18n.t("ev.failed.err", lg, err=res.error) if res.error else "")
                    data = None
                else:
                    why, text, data = built["reason"], built["event"], built["data"]
            self.store.update_task(run["task_id"], state="failed", returned_reason=why)
            self.store.event("failed", text, run["station"], run["task_id"], data=data)
        self._maybe_write_idle(run["station"], run["task_id"])
    def _quota_after_run(self, station_id: str) -> None:
        """工位设了「每轮跑完查一次」→ 起线程查余量，不阻塞收尾。坏了不影响派活。"""
        try:
            from . import quota
            quota.after_run(self.store, station_id)
        except Exception:  # noqa: BLE001 - 查余量绝不能带崩核心
            pass
    def _maybe_write_idle(self, station_id: str, task_id: str | None = None) -> None:
        """文件档（onboard v0.2 §6）：这个工位的卡进入 delivered / failed / cancelled / done / blocked
        且没别的卡在排队 → 交换文件改写「没活：下次 HH:MM 再来」。已经是我活就不再写。"""
        st = self.station(station_id)
        if not exchange.is_file_mode(st):
            return
        t = self.store.get_task(task_id) if task_id else None
        if t and t["state"] in ("queued", "dispatched", "running"):
            return                       # 这张卡还活着，不能盖掉
        if any(x["assignee"] == station_id for x in self.store.list_tasks(state="queued")):
            return                       # 还有别的卡在排队，current.md 留最新那张
        try:
            cur = exchange.current_path(station_id).read_text(encoding="utf-8")
        except OSError:
            cur = ""
        if exchange.read_marker(cur):     # 现在是一张卡 → 改写我活；已经是我活就不重复写
            exchange.write_current(self.store, station_id,
                                    exchange.render_idle(exchange.next_hhmm(_every_min(st)), self.lang_of(station_id)))
    def _after_delivered(self, task_id: str) -> None:
        """delivered → gates (free, §3.1.1) → review per the card. Any failed gate auto-returns without the leader."""
        t = self.store.get_task(task_id)
        card = t.get("card") or {}
        lg = self.lang()
        results = self._run_gates(t)
        review_md = tasks.card_dir(task_id) / "review.md"
        if results:
            try:
                review_md.write_text(gates.render_review_md(results, lg) + "\n", encoding="utf-8")
            except OSError:
                pass
            failed = [r for r in results if not r.ok]
            if failed:
                reason = i18n.t("ack.gates_fail", lg, list="; ".join("%s (%s)" % (r.check, r.reason) for r in failed))
                self.store.event("gates_fail", i18n.t("ev.gates_fail", lg, ok=len(results) - len(failed), total=len(results)),
                                 t["assignee"], task_id)
                self._return_task(t, reason, by=i18n.t("ack.gates_by", lg))
                return
            self.store.event("gates_ok", i18n.t("ev.gates_ok", lg, ok=len(results), total=len(results)), t["assignee"], task_id)
        review = str(card.get("acceptance", {}).get("review", "leader"))
        if review == "none":
            self.store.update_task(task_id, state="accepted")
            self._on_accept(task_id)
        else:
            self.store.update_task(task_id, state="reviewing")
            self.store.event("reviewing", i18n.t("ev.reviewing", self.lang(),
                                                  who=t["dispatcher"] if review == "leader" else review), t["assignee"], task_id,
                             data={"who": "user" if review == "user" else "leader"})   # 首页「只看需要我处理的」按 who=user 筛
        self._maybe_write_idle(t["assignee"], task_id)   # 文件档：交付后交换文件改写我活（质检打回重排的话上面已重写新卡，这里会跳过）
    def _run_gates(self, t: dict) -> list:
        card = t.get("card") or {}
        if not (card.get("acceptance") or {}).get("gates"):
            return []
        base = None
        for r in self.store.runs_for_task(t["id"]):
            rng = r.get("commit_range") or ""
            if ".." in rng:
                base = rng.split("..", 1)[0] or None  # earliest run's base = where this card started
                break
        try:
            return gates.run_gates(card, card.get("cwd") or "", base_commit=base, lang=self.lang())
        except Exception as e:  # noqa: BLE001 - gates must never take the core down
            return [gates.GateResult("gates", False, i18n.t("ack.gates_broken", self.lang(), why=e))]
    def _return_task(self, t: dict, note: str, by: str, force: bool = False) -> dict:
        """Round+1 redispatch with the reason written into the card (§3.1.2 rule 5); stops at max_rounds unless force."""
        task_id = t["id"]
        lg = self.lang()
        if self.station(t["assignee"]) is None:
            # 工位已经没了（删猫 / 重置）：没法原路重派，卡留在原状态，首领给别的工位派一张新的
            return self._ack("station_unknown", i18n.t("ack.gone_station2", lg, sid=t["assignee"]),
                             task_id=task_id, state=t["state"])
        card = dict(t["card"])
        max_rounds = int((card.get("acceptance") or {}).get("max_rounds") or 2)
        if int(t["round"]) >= max_rounds and not force:
            # 到了上限不再自动开工，但这次的说明要写进卡：之后重派读的是卡，不是上一轮留下的旧话
            card["returned_reason"] = note or ""
            tasks.write_card(task_id, card)
            self.store.update_task(task_id, state="returned", returned_reason=note or "",
                                   card_json=json.dumps(card, ensure_ascii=False))
            self.store.event("review", i18n.t("ev.review_max", lg, by=_who(by, lg), n=max_rounds, note=note or ""), by, task_id,
                              data={"verdict": "return_max", "to": t["assignee"], "round": max_rounds, "landed": "pending"})
            return self._ack("ok", i18n.t("ack.returned_max", lg), state="returned")
        card["round"] = int(t["round"]) + 1
        card["returned_reason"] = note or ""
        card.pop(NET_RETRY_KEY, None)   # 首领发起新一轮：接口断的自动重试计数重新数
        tasks.write_card(task_id, card)
        self.store.update_task(task_id, state="dispatched", round=card["round"], returned_reason=note, card_json=json.dumps(card, ensure_ascii=False))
        st = self.station(t["assignee"])
        runner = self.runner_for(st) if st else None
        if runner is None:
            self._note_return(by, task_id, t["assignee"], card["round"], note, "redispatched")
            return self._ack("no_runner", i18n.t("ack.returned_no_runner", lg, sid=t["assignee"]), state="dispatched")
        # 打回重派和接着做同一套开工检查：猫忙或歇着就排队，不另起进程
        out = self._launch_resume(st, runner, task_id, card, attempt=card["round"])
        if out.get("queued"):
            saved = dict((self.store.get_task(task_id) or {}).get("card") or {})
            if saved.get(WAIT_REASON_KEY) in (WAIT_BUSY, WAIT_REST):
                saved[QUEUE_FRONT] = True
                tasks.write_card(task_id, saved)
                self.store.update_task(task_id, card_json=json.dumps(saved, ensure_ascii=False))
                out["text"] = self._returned_queue_text(st["id"], task_id)
        fresh = self.store.get_task(task_id) or {}
        # 开工结果出来再记：猫忙或接口不通时卡是排队，不能假设一定已经开工
        landed = "queued" if fresh.get("state") == "queued" else "redispatched"
        self._note_return(by, task_id, t["assignee"], card["round"], note, landed)
        return out
    def _note_return(self, by: str, task_id: str, assignee: str, rnd: int, note: str, landed: str) -> None:
        """打回事件记下落地（已重派 / 已排队）。写在开工或排队之后，给首领的摘要才能按真实状态说。"""
        lg = self.lang()
        self.store.event("review", i18n.t("ev.review_round", lg, by=_who(by, lg), n=rnd, note=note or ""), by, task_id,
                         data={"verdict": "return", "to": assignee, "round": rnd, "landed": landed})
    def _returned_queue_text(self, station_id: str, task_id: str) -> str:
        """打回没马上开工：回执写排在谁后面，不说已送达。"""
        lg = self.lang()
        ahead = [row["id"] for row in self.store.list_tasks(state="dispatched,running")
                 if row["assignee"] == station_id and row["id"] != task_id]
        if ahead:
            return i18n.t("ack.returned_queued", lg, ahead=i18n.t("card.list_sep", lg).join(ahead))
        return i18n.t("ack.returned_wait", lg, sid=station_id)
    def _on_accept(self, task_id: str) -> None:
        t = self.store.get_task(task_id)
        oa = (t.get("card") or {}).get("on_accept") or {"action": "none"}
        # M1: only 'none'; move/channel arrive in M3
        self.store.update_task(task_id, state="done", done_at=now_iso())
        self.store.event("done", i18n.t("ev.done", self.lang(),
                                        oa=i18n.t("ev.done_oa", self.lang(), a=oa.get("action")) if oa.get("action", "none") != "none" else ""),
                         t["assignee"], task_id)
        tmpdir.remove_card(task_id)          # 验收通过：这张卡的临时目录没用了，马上清
