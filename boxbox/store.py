"""SQLite store: the single source of truth for tasks / runs / tokens / events.

One connection, one lock; every public method is atomic. Files under data/tasks/<id>/
are mirrors for humans and for clients without MCP; the DB wins on conflict.
"""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks(
  id TEXT PRIMARY KEY, title TEXT, kind TEXT, assignee TEXT, state TEXT, round INTEGER DEFAULT 1,
  parent TEXT, returned_reason TEXT, cancel_note TEXT, created_by TEXT, dispatcher TEXT,
  created_at TEXT, updated_at TEXT, delivered_at TEXT, done_at TEXT,
  acceptance_json TEXT, card_json TEXT, card_path TEXT);
CREATE INDEX IF NOT EXISTS tasks_state ON tasks(state);
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY, task_id TEXT, station TEXT, runner TEXT, attempt INTEGER DEFAULT 1,
  worktree TEXT, lock_owner TEXT, commit_range TEXT, pid INTEGER,   session_id TEXT,
  session_dir TEXT,
  last_tool TEXT, last_tool_at TEXT, last_tool_cmd TEXT, last_tool_out TEXT,
  last_output_at TEXT, last_model_at TEXT, last_tool_end_at TEXT, tool_open TEXT,
  stall_kind TEXT, stall_since TEXT,
  started TEXT, first_activity TEXT, last_activity TEXT, ended TEXT,
  exit INTEGER, status TEXT, tokens_json TEXT, commits INTEGER, dirty INTEGER, log_path TEXT, error TEXT,
  split_json TEXT);
CREATE INDEX IF NOT EXISTS runs_station_ended ON runs(station, ended);
CREATE TABLE IF NOT EXISTS token_ledger(
  run_id TEXT, seq INTEGER, station TEXT, task_id TEXT,
  tok_in INTEGER, tok_out INTEGER, tok_cr INTEGER, tok_cw INTEGER, turns INTEGER,
  source TEXT, cost REAL, at TEXT, PRIMARY KEY(run_id, seq));
CREATE TABLE IF NOT EXISTS channels(
  name TEXT PRIMARY KEY, kind TEXT, device TEXT, script_path TEXT, enabled INTEGER,
  authorized_by TEXT, last_run TEXT, last_exit INTEGER);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, station TEXT, task_id TEXT, text TEXT, json TEXT);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, sender TEXT, receiver TEXT, text TEXT, read_at TEXT);
CREATE TABLE IF NOT EXISTS stations_state(
  station TEXT PRIMARY KEY, runner TEXT, state TEXT, task_id TEXT, since TEXT,
  last_seen TEXT, host_pid INTEGER, host_alive INTEGER, last_scheduled_at TEXT, json TEXT,
  first_seen TEXT);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, json TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS report_keys(k TEXT PRIMARY KEY, at TEXT);
CREATE TABLE IF NOT EXISTS exchange_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, station TEXT, task_id TEXT, round INTEGER, action TEXT, bytes INTEGER, ts TEXT);
"""


def now_iso() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def today_key() -> str:
    return _dt.datetime.now().strftime("%Y%m%d")


def _with_card_state(card_json, state):
    """卡快照里的 state 跟着任务表走。没快照或解析不了就原样返回。"""
    if not card_json or state is None:
        return card_json
    try:
        card = json.loads(card_json) if isinstance(card_json, str) else dict(card_json)
    except (TypeError, ValueError):
        return card_json
    if not isinstance(card, dict):
        return card_json
    if card.get("state") == state and isinstance(card_json, str):
        return card_json
    card = dict(card)
    card["state"] = state
    return json.dumps(card, ensure_ascii=False)


class Store:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self._migrate()

    def _migrate(self) -> None:
        """补上后来才加的列。调用方拿着 self.lock。
        导入会把整库换掉，换完还要再走一遍：旧库是按当时的表建的。"""
        self.db.executescript(SCHEMA)
        # 老库补列（onboard v0.2 §9）：stations_state.first_seen —— 该工位第一次来调 get_briefing 的时间
        # 老库补列：runs.session_dir —— 这一轮 Pi 的对话记录目录（中断后要靠它接着做）
        # 老库补列：新装的库 CREATE 里已经有，升级上来的才缺
        self._add_cols("runs", ("session_dir", "last_tool", "last_tool_at", "last_tool_cmd", "last_tool_out",
                                "last_output_at", "last_model_at", "last_tool_end_at", "tool_open",
                                "stall_kind", "stall_since", "split_json"))
        self._add_cols("tasks", ("cancel_note",))
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(stations_state)")}
        if "first_seen" not in cols:
            self.db.execute("ALTER TABLE stations_state ADD COLUMN first_seen TEXT")
            # 老库里早就来过的工位（有 last_seen）当然握过手：回填，不然升级后首页会把老用户踢回上岗页第 4 步
            self.db.execute("UPDATE stations_state SET first_seen=last_seen WHERE first_seen IS NULL AND last_seen IS NOT NULL")
        self.db.commit()

    def _add_cols(self, table: str, cols: tuple) -> None:
        have = {r[1] for r in self.db.execute("PRAGMA table_info(%s)" % table)}
        for col in cols:
            if col not in have:
                self.db.execute("ALTER TABLE %s ADD COLUMN %s TEXT" % (table, col))

    def close(self) -> None:
        """核心退出时关掉数据库（不然 boxbox.db 一直被占着）。关了以后再写会抛 ProgrammingError。"""
        with self.lock:
            try:
                self.db.close()
            except sqlite3.Error:
                pass

    # ---- helpers ----
    def _rows(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def _row(self, sql, args=()):
        rows = self._rows(sql, args)
        return rows[0] if rows else None

    def _exec(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    # ---- tasks ----
    def next_task_id(self) -> str:
        """YYYYMMDD-NNN, per day, generated under the lock (not a PR number)."""
        day = today_key()
        with self.lock:
            r = self.db.execute("SELECT id FROM tasks WHERE id LIKE ? ORDER BY id DESC LIMIT 1", (day + "-%",)).fetchone()
            n = int(r[0].split("-")[1]) + 1 if r else 1
            return "%s-%03d" % (day, n)

    def insert_task(self, t: dict) -> None:
        cols = ("id", "title", "kind", "assignee", "state", "round", "parent", "returned_reason", "created_by",
                "dispatcher", "created_at", "updated_at", "delivered_at", "done_at", "acceptance_json", "card_json", "card_path")
        self._exec("INSERT INTO tasks(%s) VALUES(%s)" % (",".join(cols), ",".join("?" * len(cols))),
                   tuple(t.get(c) for c in cols))

    def update_task(self, task_id: str, **fields) -> None:
        fields["updated_at"] = now_iso()
        with self.lock:
            if "state" in fields:
                # 和这次写入放在同一把锁里：心跳改状态时，别用过期快照盖掉别人刚写进卡里的字段
                raw = fields.get("card_json")
                if raw is None:
                    row = self.db.execute("SELECT card_json FROM tasks WHERE id=?", (task_id,)).fetchone()
                    raw = row["card_json"] if row else None
                synced = _with_card_state(raw, fields["state"])
                if synced is not None:
                    fields["card_json"] = synced
            sets = ",".join("%s=?" % k for k in fields)
            self.db.execute("UPDATE tasks SET %s WHERE id=?" % sets, tuple(fields.values()) + (task_id,))
            self.db.commit()

    def get_task(self, task_id: str) -> dict | None:
        t = self._row("SELECT * FROM tasks WHERE id=?", (task_id,))
        if t and t.get("card_json"):
            t["card"] = json.loads(t["card_json"])
        return t

    def tasks_of_station(self, assignee: str, limit: int = 200) -> list[dict]:
        """这个工位的卡（最新的在前），不带 card 大块，给工位详情用。"""
        return self._rows("SELECT id,title,kind,assignee,state,round,created_at,updated_at,done_at,returned_reason "
                          "FROM tasks WHERE assignee=? ORDER BY id DESC LIMIT ?", (assignee, limit))

    def list_tasks(self, state: str | None = None, limit: int = 200) -> list[dict]:
        if state:
            states = tuple(state.split(","))
            rows = self._rows("SELECT * FROM tasks WHERE state IN (%s) ORDER BY id DESC LIMIT ?" % ",".join("?" * len(states)), states + (limit,))
        else:
            rows = self._rows("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,))
        for t in rows:
            if t.get("card_json"):
                t["card"] = json.loads(t["card_json"])
        return rows

    # ---- runs ----
    def insert_run(self, r: dict) -> None:
        cols = ("run_id", "task_id", "station", "runner", "attempt", "worktree", "lock_owner", "commit_range", "pid",
                "session_id", "session_dir", "started", "first_activity", "last_activity", "ended", "exit", "status", "tokens_json",
                "commits", "dirty", "log_path", "error")
        self._exec("INSERT INTO runs(%s) VALUES(%s)" % (",".join(cols), ",".join("?" * len(cols))),
                   tuple(r.get(c) for c in cols))

    def update_run(self, run_id: str, **fields) -> None:
        sets = ",".join("%s=?" % k for k in fields)
        self._exec("UPDATE runs SET %s WHERE run_id=?" % sets, tuple(fields.values()) + (run_id,))

    def get_run(self, run_id: str) -> dict | None:
        return self._row("SELECT * FROM runs WHERE run_id=?", (run_id,))

    def open_runs(self) -> list[dict]:
        return self._rows("SELECT * FROM runs WHERE ended IS NULL ORDER BY started")

    def runs_for_task(self, task_id: str) -> list[dict]:
        return self._rows("SELECT * FROM runs WHERE task_id=? ORDER BY started", (task_id,))

    def recent_runs(self, limit: int = 50) -> list[dict]:
        return self._rows("SELECT * FROM runs ORDER BY started DESC LIMIT ?", (limit,))

    def runs_overlapping(self, since_iso: str) -> list[dict]:
        """窗口里结束的运行，加上还没结束的。效率面板和「有活时几只猫在干」共用这一份，页面不再重扫日志。"""
        return self._rows(
            "SELECT * FROM runs WHERE (ended IS NOT NULL AND ended>=?) "
            "OR (ended IS NULL AND started IS NOT NULL) ORDER BY started",
            (since_iso,))

    def tasks_done_since(self, since_iso: str) -> list[dict]:
        """验收完落在窗口里、而且交回时间还在的卡。等了多久用这两个时间相减。"""
        return self._rows(
            "SELECT id, title, assignee, state, delivered_at, done_at FROM tasks "
            "WHERE done_at>=? AND delivered_at IS NOT NULL AND delivered_at!=''",
            (since_iso,))

    def tasks_brief(self, ids: list[str]) -> list[dict]:
        out: list[dict] = []
        for i in range(0, len(ids), 400):
            chunk = [str(x) for x in ids[i:i + 400] if x]
            if not chunk:
                continue
            q = ",".join("?" * len(chunk))
            out.extend(self._rows("SELECT id, title, assignee FROM tasks WHERE id IN (%s)" % q, tuple(chunk)))
        return out

    def ledger_for_runs(self, run_ids: list[str]) -> list[dict]:
        out: list[dict] = []
        for i in range(0, len(run_ids), 400):
            chunk = [str(x) for x in run_ids[i:i + 400] if x]
            if not chunk:
                continue
            q = ",".join("?" * len(chunk))
            out.extend(self._rows("SELECT * FROM token_ledger WHERE run_id IN (%s)" % q, tuple(chunk)))
        return out

    def runs_ended_by_task(self) -> dict[str, str]:
        """{task_id: 最后一次运行的 ended}（全员空闲的起点：最后一张卡结束的时间；也用它判断「有没有真跑过」）。"""
        return {r["task_id"]: r["m"] for r in self._rows(
            "SELECT task_id, MAX(ended) m FROM runs WHERE ended IS NOT NULL GROUP BY task_id")}

    def station_lifetimes(self) -> dict[str, dict]:
        """{station: {first: 最早一条 started, last: 最近一条 last_activity（没有就用 started)}}（Pi 工位的上岗 / 最近活动）。
        Pi 工位（盒子自己拉起进程）没有外部会话来握手，stations_state.first_seen / last_seen 永远是空，用 runs 表顶上。"""
        return {r["station"]: {"first": r["first"], "last": r["last"]} for r in self._rows(
            "SELECT station, MIN(started) first, MAX(COALESCE(NULLIF(last_activity,''), started)) last "
            "FROM runs WHERE started IS NOT NULL GROUP BY station")}

    # ---- tokens ----
    def ledger_add(self, run_id: str, station: str, task_id: str, tok: dict, source: str, cost: float | None = None) -> None:
        with self.lock:
            r = self.db.execute("SELECT COALESCE(MAX(seq),0) FROM token_ledger WHERE run_id=?", (run_id,)).fetchone()
            seq = int(r[0]) + 1
            self.db.execute("INSERT INTO token_ledger(run_id,seq,station,task_id,tok_in,tok_out,tok_cr,tok_cw,turns,source,cost,at) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                            (run_id, seq, station, task_id, tok.get("in"), tok.get("out"), tok.get("cr"), tok.get("cw"),
                             tok.get("turns"), source, cost, now_iso()))
            self.db.commit()

    def ledger_has_run(self, run_id: str) -> bool:
        """这个 run 在用量账本里记过没有（补记前先看一眼，别记两遍）。"""
        r = self._row("SELECT COUNT(*) n FROM token_ledger WHERE run_id=?", (run_id,))
        return bool(int((r or {}).get("n") or 0))

    def tokens_summary(self, since_iso: str) -> list[dict]:
        return self._rows("SELECT station, COUNT(DISTINCT run_id) runs, SUM(tok_in) tok_in, SUM(tok_out) tok_out, "
                          "SUM(tok_cr) tok_cr, SUM(tok_cw) tok_cw, SUM(cost) cost "
                          "FROM token_ledger WHERE at>=? GROUP BY station ORDER BY station", (since_iso,))

    def tokens_for_task(self, task_id: str) -> dict:
        r = self._row("SELECT SUM(tok_in) tok_in, SUM(tok_out) tok_out, SUM(tok_cr) tok_cr, SUM(tok_cw) tok_cw, "
                      "SUM(cost) cost FROM token_ledger WHERE task_id=?", (task_id,))
        return r or {}

    # ---- events / messages / kv / station state ----
    def event(self, kind: str, text: str, station: str | None = None, task_id: str | None = None, data: dict | None = None) -> None:
        self._exec("INSERT INTO events(ts,kind,station,task_id,text,json) VALUES(?,?,?,?,?,?)",
                   (now_iso(), kind, station, task_id, text, json.dumps(data, ensure_ascii=False) if data else None))

    def event_update(self, eid: int, text: str, data: dict | None = None) -> None:
        """改一条已有事件（站会：第 3、4 张卡并进同一条，不出新的）。id 不动，画布不会重放。"""
        self._exec("UPDATE events SET text=?, json=? WHERE id=?",
                   (text, json.dumps(data, ensure_ascii=False) if data else None, eid))

    def events(self, limit: int = 100, task_id: str | None = None, station: str | None = None) -> list[dict]:
        if task_id:
            return self._rows("SELECT * FROM events WHERE task_id=? ORDER BY id DESC LIMIT ?", (task_id, limit))
        if station:
            return self._rows("SELECT * FROM events WHERE station=? ORDER BY id DESC LIMIT ?", (station, limit))
        return self._rows("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))

    def events_after(self, after_id: int, kinds=None, limit: int = 50) -> list[dict]:
        """id 大于 after_id 的事件，按 id 升序（首领等交回，只看「上次之后」的那些）。
        kinds 给了就只取这些种类（空列表 = 全都要）。"""
        after = int(after_id or 0)
        kinds = [str(k) for k in (kinds or []) if k]
        if kinds:
            q = ",".join("?" * len(kinds))
            return self._rows("SELECT * FROM events WHERE id>? AND kind IN (%s) ORDER BY id ASC LIMIT ?" % q,
                              [after] + kinds + [int(limit)])
        return self._rows("SELECT * FROM events WHERE id>? ORDER BY id ASC LIMIT ?", (after, int(limit)))

    def last_event_id(self) -> int:
        """最后一条事件的 id（没有事件就是 0）。首领第一次来时从这里开始，别把历史全倒出来。"""
        r = self._row("SELECT MAX(id) AS m FROM events")
        return int((r or {}).get("m") or 0)

    def post_message(self, sender: str, receiver: str, text: str) -> None:
        self._exec("INSERT INTO messages(at,sender,receiver,text) VALUES(?,?,?,?)", (now_iso(), sender, receiver, text))

    def read_inbox(self, receiver: str, mark: bool = True) -> list[dict]:
        rows = self._rows("SELECT * FROM messages WHERE receiver=? AND read_at IS NULL ORDER BY id", (receiver,))
        if mark and rows:
            self._exec("UPDATE messages SET read_at=? WHERE receiver=? AND read_at IS NULL", (now_iso(), receiver))
        return rows

    def unread_messages(self, receiver: str, since: str | None = None) -> list[dict]:
        """还没读的留言。since 给了就只要这个时间之后的（这一轮开工之后才算这一轮的）。"""
        if since:
            return self._rows("SELECT * FROM messages WHERE receiver=? AND read_at IS NULL AND at>=? ORDER BY id",
                              (receiver, since))
        return self._rows("SELECT * FROM messages WHERE receiver=? AND read_at IS NULL ORDER BY id", (receiver,))

    def mark_messages_read(self, ids) -> None:
        ids = [int(i) for i in (ids or [])]
        if not ids:
            return
        q = ",".join("?" * len(ids))
        self._exec("UPDATE messages SET read_at=? WHERE id IN (%s) AND read_at IS NULL" % q, [now_iso(), *ids])

    def events_by_kind(self, task_id: str, kind: str) -> list[dict]:
        return self._rows("SELECT * FROM events WHERE task_id=? AND kind=? ORDER BY id", (task_id, kind))

    def kv_get(self, k: str, default=None):
        r = self._row("SELECT json FROM kv WHERE k=?", (k,))
        return json.loads(r["json"]) if r else default

    def kv_set(self, k: str, v) -> None:
        self._exec("INSERT INTO kv(k,json,ts) VALUES(?,?,?) ON CONFLICT(k) DO UPDATE SET json=excluded.json, ts=excluded.ts",
                   (k, json.dumps(v, ensure_ascii=False), now_iso()))

    def station_touch(self, station: str, **fields) -> None:
        cur = self._row("SELECT * FROM stations_state WHERE station=?", (station,)) or {"station": station}
        cur.update(fields)
        cols = ("station", "runner", "state", "task_id", "since", "last_seen", "host_pid", "host_alive", "last_scheduled_at", "json", "first_seen")
        self._exec("INSERT OR REPLACE INTO stations_state(%s) VALUES(%s)" % (",".join(cols), ",".join("?" * len(cols))),
                   tuple(cur.get(c) for c in cols))

    def station_states(self) -> dict[str, dict]:
        return {r["station"]: r for r in self._rows("SELECT * FROM stations_state")}

    def report_key_once(self, key: str) -> bool:
        """Idempotency for report(): True the first time a key is seen, False afterwards."""
        with self.lock:
            try:
                self.db.execute("INSERT INTO report_keys(k,at) VALUES(?,?)", (key, now_iso()))
                self.db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    # ---- exchange log (onboard v0.2 §6: 路径 C 文件档的调用记录) ----
    def exchange_add(self, station: str, task_id: str | None, round: int | None, action: str, nbytes: int) -> None:
        """action ∈ {wrote_card, wrote_idle, report_seen, done_seen, timeout}."""
        self._exec("INSERT INTO exchange_log(station,task_id,round,action,bytes,ts) VALUES(?,?,?,?,?,?)",
                   (station, task_id, round, action, int(nbytes or 0), now_iso()))

    def exchange_log(self, station: str, limit: int = 20) -> list[dict]:
        return self._rows("SELECT * FROM exchange_log WHERE station=? ORDER BY id DESC LIMIT ?", (station, limit))

    # ---- 重置所有----
    def clear_all(self) -> None:
        """清空所有表的数据。用 DELETE，不删正在用的 db 文件（删了库 Windows 上会一直被占着）。"""
        with self.lock:
            names = [r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                                   "AND name NOT LIKE 'sqlite_%'").fetchall()]
            for name in names:
                self.db.execute("DELETE FROM %s" % name)
            try:
                self.db.execute("DELETE FROM sqlite_sequence")     # 任务号 / 事件号从头数
            except sqlite3.OperationalError:
                pass
            self.db.commit()
