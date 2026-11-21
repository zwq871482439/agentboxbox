(function () {
  "use strict";

  function T(k, v) { return window.BXi18n ? window.BXi18n.t(k, v) : k; }

  var $ = function (s, r) { return (r || document).querySelector(s); };
  /* 共用工具在 util.js 里：esc / hm / when / api / copy / clientLabel 都只有那一份 */
  var U = window.BXu;
  var esc = U.esc, hm = U.hm, when = U.when, fmtNum = U.fmtNum, api = U.api;

  /* 状态词表在 i18n-board.js 里（bd.state.*），这里只留样式 */
  var STATE_CLS = {
    running: "s-run", reviewing: "s-rev", failed: "s-fail", blocked: "s-block",
    returned: "s-ret", interrupted: "s-ret", done: "s-done", accepted: "s-acc"
  };
  function stateWord(s) {
    var w = T("bd.state." + String(s == null ? "" : s));
    return w === "bd.state." + String(s == null ? "" : s) ? String(s == null ? "" : s) : w;
  }
  function taskStateWord(t) {
    /* 排队原因优先用核心给的那一句；核心没给（老数据）才按 wait_reason 自己猜。 */
    var s = typeof t === "string" ? t : (t && t.state);
    if (s === "queued" && t && typeof t === "object" && t.wait_text) { return t.wait_text; }
    if (s === "queued" && t && typeof t === "object" && t.wait_reason === "busy") { return T("bd.queue.busy"); }
    if (s === "queued" && t && typeof t === "object" && t.wait_reason === "network") { return T("bd.queue.network"); }
    return stateWord(s);
  }
  /* 客户端、运行器、类别、退出码：界面只显示人话，代码名不出现在页面上 */
  /* 客户端显示名：名字表在 util.js，这里只传本页的词 */
  function clientLabel(c) {
    return U.clientLabel(c, { none: T("bd.client.none"), other: T("bd.client.other"), otherDirect: T("bd.client.otherDirect") });
  }
  function runnerLabel(r) { if (!r) return "-"; return T("bd.runner." + r); }
  function kindLabel(k) { if (!k) return "-"; return T("bd.kind." + k); }
  function runStatusLabel(s) { if (!s) return "-"; return T("bd.run." + s); }
  function evKindLabel(k) {
    var key = "bd.ev." + String(k == null ? "" : k);
    var w = T(key);
    return w === key ? String(k == null ? "" : k) : w;
  }
  function reviewLabel(r) {
    if (!r || r === "leader") { return T("bd.review.leader"); }
    if (r === "user") { return T("bd.review.user"); }
    var m = /^member:(.+)$/.exec(r);
    if (m) return m[1];
    return String(r);
  }
  function schedAgo(iso) {
    if (!iso) { return T("bd.sched.never"); }
    var t = new Date().getTime() - new Date(iso).getTime();
    if (isNaN(t)) { return T("bd.sched.never"); }
    return T("bd.sched.ago", { n: Math.max(0, Math.round(t / 60000)) });
  }
  function stateBadge(t) {
    var s = typeof t === "string" ? t : (t && t.state);
    var c = STATE_CLS[s] ? " " + STATE_CLS[s] : "";
    return '<span class="badge' + c + '">' + esc(taskStateWord(t)) + "</span>";
  }
  function roleWord(r) {
    if (r === "leader") { return T("bd.role.leader"); }
    return T("bd.role.member");
  }
  function exitWord(v) {
    if (v == null || v === "") { return "—"; }
    var key = "bd.exit." + Number(v);
    var w = T(key);
    return w === key ? T("bd.exitOther", { v: v }) : w;
  }

  var S = { meta: null, stations: [], todo: null, tasks: [], tokens: null, eff: null, doctor: null, down: true, stamp: "—",
            stationDefs: null, defsReq: null };
  var openKeys = {};       /* 记住折叠区展开状态 */
  var detail = null;       /* {kind:'task'|'station', id, data} */
  var busy = false;

  /* ---------- 工位 ---------- */
  function renderStations() {
    var box = $("#stations");
    var list = S.stations || [];
    $("#stN").textContent = list.length ? T("bd.st.count", { n: list.length }) : "";
    if (!list.length) { box.innerHTML = '<div class="empty">' + esc(T("bd.st.empty")) + "</div>"; return; }
    box.innerHTML = list.map(function (s) {
      /* 待定时任务 / 在岗（定时）和「闲」一样是灰词；定时任务没触发是红的 */
      var code = s.word_code || "";
      var wc = (code === "stuck" || code === "config") ? " word-stuck"
        : (code === "running" || code === "running_queue") ? " word-run"
        : (code === "rest" ? " word-rest"   /* 歇着：额度用完，等重置 */
        : (code === "sched_late" ? " word-late" : (s.enabled ? "" : " word-off")));
      var task = '<div class="title" title="' + esc(s.title) + '">' + esc(s.title || "") + "</div>";   /* 固定高度：不填也在，三条一样高 */
      var mins = s.minutes != null ? T("bd.st.minutes", { n: s.minutes }) : "";
      /* 首领那行的客户端 = 真正连上来的那一家；还没连上就别点名某一家 */
      var cl = (s.role === "leader" && !s.client) ? T("bd.st.yourApp") : clientLabel(s.client);
      var line = (s.role === "leader" ? esc(cl) + " · " : "") + esc(runnerLabel(s.runner)) + " · " +
        esc(T("bd.st.todo", { n: fmtNum(s.open) })) + mins;
      if (s.runner === "scheduled") line += " · " + esc(schedAgo(s.last_scheduled_at));
      return '<div class="st' + wc + (s.enabled ? "" : " off") + '" data-id="' + esc(s.id) + '">' +
        '<div class="r1"><span class="id">' + esc(s.id) + "</span>" +
        '<span class="role">' + esc(roleWord(s.role)) + "</span>" +
        '<span class="word">' + esc(s.status_line || s.word || "-") + "</span></div>" +
        '<div class="r2">' + line + "</div>" + task + "</div>";
    }).join("");
    Array.prototype.forEach.call(box.querySelectorAll(".st"), function (el) {
      el.onclick = function () { openStation(el.dataset.id); };
    });
    $("#stHint").textContent = T("bd.st.hint");
  }

  /* ---------- 等你 ---------- */
  function renderTodo() {
    var td = S.todo || { items: [] };
    var items = td.items || [];
    var box = $("#todo");
    var n = items.length ? T("bd.todo.count", { n: items.length }) : "";
    if (items.length) {
      n += (td.user_count || 0) ? T("bd.todo.waitYou", { n: td.user_count }) : T("bd.todo.allLeader");
    }
    $("#tdN").textContent = n;
    if (!items.length) {
      box.innerHTML = '<li class="empty">' + esc(T("bd.todo.empty")) + "</li>";
      return;
    }
    var kinds = { blocked: "k0", reviewing: "k1", returned: "k2", interrupted: "k0", failed: "k0", unstarted: "k2" };
    box.innerHTML = items.map(function (it) {
      var acts = decideBtns(it.task_id, it.kind_code === "unstarted" ? "failed" : it.kind_code);   /* 没开工的卡状态是 failed */
      return "<li>" +
        '<div class="t1"><span class="kind ' + (kinds[it.kind_code] || "") + '">' + esc(it.kind) + "</span>" +
        '<span class="tid" data-tid="' + esc(it.task_id) + '">' + esc(it.task_id) + "</span>" +
        '<span style="color:var(--dim);font-size:12px">' + esc(it.station || "-") + " · " + esc(hm(it.since)) + "</span></div>" +
        '<div class="r2"><span class="ttl">' + esc(it.title || T("bd.todo.noTitle")) + "</span>" +
        (acts ? '<span class="acts">' + acts + "</span>" : "") + "</div>" +   /* 按钮和标题同一行，标题让位，每条待办不变高 */
        (it.reason ? '<div class="why">' + esc(it.reason) + "</div>" : "") +
        '<div class="okmsg" data-msg="' + esc(it.task_id) + '"></div></li>';
    }).join("");
    Array.prototype.forEach.call(box.querySelectorAll("[data-tid]"), function (el) {
      el.onclick = function () { openTask(el.dataset.tid); };
    });
    wireDecide(box);
    items.forEach(function (it) { showMsg(it.task_id); });
  }

  /* 拍板按钮：按卡的状态给。待办本来等首领处理，首领不在时用户也能自己定（核心记成「你」拍的板） */
  var DECIDE = {
    reviewing: ["accept", "return"], delivered: ["accept", "return"], queued: ["cancel"],
    blocked: ["redispatch", "cancel"], failed: ["redispatch", "cancel"], interrupted: ["redispatch", "cancel"],
    returned: ["redispatch", "cancel"]
  };
  function decideBtns(taskId, state) {
    return (DECIDE[state] || []).map(function (a, i) {
      return '<button class="btn' + (i ? "" : " p") + '" type="button" data-act="' + a + '" data-act-tid="' + esc(taskId) + '">' +
        esc(T("bd.act." + a)) + "</button>";
    }).join("");
  }
  /* 拍板结果记在这里：原来只写进页面上那一个格子，下一次刷新就被冲掉了 */
  var msgs = {};
  function showMsg(taskId) {
    var text = msgs[taskId] || "";
    Array.prototype.forEach.call(document.querySelectorAll('[data-msg="' + taskId + '"]'), function (el) {
      el.textContent = text;
    });
  }
  function decide(taskId, act, note) {
    if (busy) return;
    if (act === "cancel" && !window.confirm(T("bd.act.cancelConfirm"))) return;
    if (act === "return" && note == null) {
      note = window.prompt(T("bd.todo.rejectNote"), "");
      if (note === null) return;
    }
    busy = true;
    api("/api/tasks/" + encodeURIComponent(taskId) + "/decide", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: act, note: note || "" })
    }).then(function (r) {
      var text = (r.data && (r.data.text || r.data.error)) || (r.ok ? T("bd.todo.submitted") : T("bd.todo.failed"));
      msgs[taskId] = text;
      showMsg(taskId);
      poll();
    }).then(function () { busy = false; }, function () { busy = false; });
  }
  function wireDecide(root) {
    Array.prototype.forEach.call(root.querySelectorAll("[data-act]"), function (el) {
      el.onclick = function () {
        var note = $("#rvNote", root);
        decide(el.getAttribute("data-act-tid"), el.getAttribute("data-act"), note ? note.value : null);
      };
    });
  }

  /* 任务卡列表：一页 15 条，按最后更新时间筛（全部 / 今天 / 近 7 天 / 近 30 天 / 自定义起止），导出 CSV。
     筛选是纯函数 tkPick（测试直接喂数据）：f = {mode:'all'|'today'|'7'|'30'|'custom', from, to}，按 updated_at 的日期比。 */
  var TK_PER = 15, tkPage = 0;
  function tkDay(offset) {
    var d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - offset);
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function tkPick(list, f) {
    var all = list || [];
    f = f || {};
    if (f.mode === "custom") {                       /* 自定义：起、止都含当天；一端没填就不卡这一头 */
      var a = f.from || "", b = f.to || "";
      if (!a && !b) return all;
      return all.filter(function (t) {
        var d = String(t.updated_at || "").slice(0, 10);
        return !!d && (!a || d >= a) && (!b || d <= b);
      });
    }
    if (!f.mode || f.mode === "all") return all;
    var since = tkDay(parseInt(f.mode, 10) - 1);
    return all.filter(function (t) { return String(t.updated_at || "").slice(0, 10) >= since; });
  }
  function tkFilter() {                              /* 当前页面上选的筛选条件 */
    var v = $("#tkDays").value;
    return v === "custom" ? { mode: "custom", from: $("#tkFrom").value, to: $("#tkTo").value } : { mode: v === "0" ? "all" : v };
  }
  function tkFiltered() { return tkPick(S.tasks || [], tkFilter()); }
  function tkSyncRange() { $("#tkRange").hidden = $("#tkDays").value !== "custom"; }
  function renderTasks() {
    var full = tkFiltered(), pages = Math.max(1, Math.ceil(full.length / TK_PER));
    if (tkPage >= pages) tkPage = pages - 1;
    var list = full.slice(tkPage * TK_PER, tkPage * TK_PER + TK_PER);
    var box = $("#tasks");
    $("#tkN").textContent = full.length ? T("bd.tk.count", { n: full.length }) : "";
    $("#tkPager").hidden = pages <= 1;
    $("#tkPage").textContent = T("bd.tk.page", { n: tkPage + 1, m: pages });
    $("#tkPrev").disabled = tkPage <= 0; $("#tkNext").disabled = tkPage >= pages - 1;
    if (!list.length) { box.innerHTML = '<tr><td colspan="8" class="empty">' + emptyTasksText() + '</td></tr>'; return; }
    box.innerHTML = list.map(function (t) {
      return '<tr data-id="' + esc(t.id) + '">' +
        "<td>" + esc(t.id) + "</td>" +
        '<td title="' + esc(t.title) + '">' + esc(t.title || "-") + "</td>" +
        "<td>" + esc(kindLabel(t.kind)) + "</td>" +
        "<td>" + esc(t.assignee || "-") + "</td>" +
        "<td>" + stateBadge(t) + "</td>" +
        '<td class="num">' + esc(t.round == null ? "-" : t.round) + "</td>" +
        "<td>" + esc(t.dispatcher || "-") + "</td>" +
        "<td>" + esc(hm(t.updated_at)) + "</td></tr>";
    }).join("");
    Array.prototype.forEach.call(box.querySelectorAll("tr[data-id]"), function (el) {
      el.onclick = function () { openTask(el.dataset.id); };
    });
  }

  function emptyTasksText() {
    var st = (S.stations || []);
    var hasMember = st.some(function (s) { return s && s.role === "member"; });
    /* 空态主句跟上岗收尾那句对齐：告诉用户去哪、说什么 */
    if (hasMember) { return T("bd.tk.emptyMember"); }
    return T("bd.tk.emptyNoMember");
  }

  /* ---------- 用量 ---------- */
  function costEst(v) { return v == null ? T("bd.cost.none") : "$" + v.toFixed(2); }
  function quotaCell(q) {
    if (!q) { return ""; }
    if (!q.ok) { return '<span class="qerr">' + esc(q.error_kind || T("bd.quota.fail")) + "</span>"; }
    return ["h5", "week", "month"].map(function (k) {
      var w = (q.windows || {})[k];
      if (!w || w.pct == null) { return ""; }
      var t = (w.label || T("bd.quota.window." + k)) + T("bd.quota.used", { n: Math.round(w.pct) }) +
        (w.reset ? T("bd.quota.reset", { t: when(w.reset) }) : "");
      var red = w.pct >= 90 ? " red" : "";
      var wid = Math.min(100, Math.round(w.pct));
      return '<span class="qbar' + red + '" title="' + esc(t) + '"><i style="width:' + wid + '%"></i></span>';
    }).join("");
  }
  function renderTokens() {
    var d = S.tokens;
    var box = $("#tokBody");
    if (!d) { box.innerHTML = '<div class="empty">' + esc(T("bd.tok.loading")) + "</div>"; return; }
    var rows = (d.stations || []).map(function (r) {
      return "<tr><td>" + esc(r.station) + '</td><td class="num">' + fmtNum(r.runs) + "</td>" +
        '<td class="num">' + fmtNum(r.tok_in) + '</td><td class="num">' + fmtNum(r.tok_out) + "</td>" +
        '<td class="num">' + fmtNum(r.tok_cr) + '</td><td class="num">' + fmtNum(r.tok_cw) + "</td>" +
        '<td class="num">' + (r.cost == null ? T("bd.tok.noPrice") : r.cost) + "</td>" +
        '<td class="num">' + esc(costEst(r.cost_est)) + "</td><td>" + quotaCell(r.quota) + "</td></tr>";
    });
    (d.not_counted || []).forEach(function (sid) {
      rows.push("<tr><td>" + esc(sid) + "</td><td colspan='8' style='color:var(--dim)'>" + esc(T("bd.tok.notCounted")) + "</td></tr>");
    });
    box.innerHTML = '<div class="scroll"><table class="tbl"><thead><tr><th>' + esc(T("bd.tok.h.station")) +
      '</th><th class="num">' + esc(T("bd.tok.h.run")) + "</th>" +
      '<th class="num">' + esc(T("bd.tok.h.in")) + '</th><th class="num">' + esc(T("bd.tok.h.out")) + '</th>' +
      '<th class="num">' + esc(T("bd.tok.h.cr")) + "</th>" +
      '<th class="num">' + esc(T("bd.tok.h.cw")) + '</th><th class="num">' + esc(T("bd.tok.h.amount")) + '</th><th class="num">' + esc(T("bd.tok.h.estimate")) +
      '<span class="th-note">' + esc(T("bd.tok.estimateNote")) + "</span></th>" +
      "<th>" + esc(T("bd.tok.h.quota")) + "</th></tr></thead><tbody>" +
      (rows.length ? rows.join("")
        : '<tr><td colspan="9" class="empty">' + esc(T("bd.tok.empty")) + "</td></tr>") + "</tbody></table></div>" +
      (rows.length ? '<p class="hint">' + esc(d.note || T("bd.tok.note")) + " " + esc(T("bd.tok.since")) + " " + esc(when(d.since)) + "</p>" : "");
  }
  function renderEff() {
    if (window.BXEff) { window.BXEff.render(S.eff); }
  }

  /* 「花了多少」：标题行一句话总数（次数 + 有单价才给钱），两张表收在下面 */
  function renderCostSummary() {
    var d = S.tokens;
    var runs = 0, cost = null;
    ((d && d.stations) || []).forEach(function (r) {
      runs += Number(r.runs) || 0;
      if (r.cost_est != null) { cost = (cost || 0) + Number(r.cost_est); }
    });
    var bits = [T("bd.cost.runs", { n: fmtNum(runs) })];
    if (cost != null) { bits.push(T("bd.cost.approx", { c: cost.toFixed(2) })); }
    var el = $("#costSum");
    if (el) { el.textContent = T("bd.cost.title") + " · " + bits.join(" · "); }
  }


  /* ---------- 抽屉 ---------- */
  function openTask(id) {
    detail = { kind: "task", id: id, data: null };
    $("#scrim").hidden = false; $("#drawer").hidden = false;
    $("#drawer").innerHTML = '<div class="dbody">' + esc(T("bd.drawer.loading")) + "</div>";
    loadTask(id);
  }
  function openStation(id) {
    if (!id) return;
    detail = { kind: "station", id: id, data: null };
    $("#scrim").hidden = false; $("#drawer").hidden = false;
    $("#drawer").innerHTML = '<div class="dbody">' + esc(T("bd.drawer.loading")) + "</div>";
    api("/api/summon/" + encodeURIComponent(id)).then(function (r) {
      if (detail && detail.kind === "station" && detail.id === id) {
        detail.data = r.ok ? r.data : { error: T("bd.drawer.noStation") };
        drawDrawer();
      }
    });
  }
  function loadTask(id) {
    api("/api/tasks/" + encodeURIComponent(id)).then(function (r) {
      if (!detail || detail.kind !== "task" || detail.id !== id) return;
      if (!r.ok) { detail.data = null; drawDrawer(T("bd.drawer.noStation") + ": " + ((r.data && r.data.error) || r.status)); return; }
      detail.data = r.data.task;
      drawDrawer();
    });
  }
  function closeDrawer() {
    detail = null;
    $("#drawer").hidden = true; $("#drawer").innerHTML = "";
    $("#scrim").hidden = true;
  }
  function head(title, sub) {
    return '<div class="dhead"><div><div class="ttl">' + esc(title) + "</div>" +
      '<div class="sub">' + sub + "</div></div>" +
      '<button class="btn x" type="button" id="dclose">' + esc(T("bd.drawer.close")) + "</button></div>";
  }
  function fold(key, title, inner) {
    return '<details data-k="' + esc(key) + '"' + (openKeys[key] ? " open" : "") + "><summary>" + esc(title) +
      "</summary><div style='padding:10px 2px'>" + inner + "</div></details>";
  }
  function parseTok(s) {
    if (!s) return null;
    try { var j = JSON.parse(s); return (j && typeof j === "object") ? j : null; } catch (e) { return null; }
  }
  function tokCell(s) {
    var j = parseTok(s);
    if (!j) { return T("bd.task.notCounted"); }
    return T("bd.tok.h.in") + " " + fmtNum(j.in) + " " + T("bd.tok.h.out") + " " + fmtNum(j.out) + " " +
      T("bd.tok.h.cr") + " " + fmtNum(j.cr) + " " + T("bd.tok.h.cw") + " " + fmtNum(j.cw) + " " + fmtNum(j.turns) + " turns";
  }
  function gatesHtml(md) {
    var lines = String(md || "").split("\n").filter(function (l) { return l.trim(); });
    if (!lines.length) { return '<div class="empty">' + esc(T("bd.drawer.noGates")) + "</div>"; }
    return '<ul class="gates">' + lines.map(function (l) {
      var t = l.trim(), m;
      if ((m = /^- \[x\]\s*(.*)$/i.exec(t))) return '<li class="ok"><span class="mark">✓</span>' + esc(m[1]) + "</li>";
      if ((m = /^- \[ \]\s*(.*)$/i.exec(t))) return '<li class="no"><span class="mark">✗</span>' + esc(m[1]) + "</li>";
      if (/^#{1,6}\s/.test(t)) return '<li class="h">' + esc(t.replace(/^#+\s*/, "")) + "</li>";
      return '<li class="tail">' + esc(t) + "</li>";
    }).join("") + "</ul>";
  }
  function drawDrawer(errText) {
    var box = $("#drawer");
    if (!detail) return;
    var body = "";
    if (detail.kind === "station") body = stationHtml(detail.data);
    else if (detail.data) body = taskHtml(detail.data);
    else body = '<div class="empty">' + esc(errText || T("bd.drawer.reading")) + "</div>";
    var remember = box.querySelectorAll("details[data-k]");
    Array.prototype.forEach.call(remember, function (d) { openKeys[d.dataset.k] = d.open; });
    box.innerHTML = head(detail.id, detail.kind === "task" ? T("bd.drawer.task") : T("bd.drawer.station")) + body;
    wire(box);
    if (detail.kind === "task") showMsg(detail.id);
  }
  function stationHtml(d) {
    if (!d || d.error) {
      return '<div class="dsec"><div class="empty">' + esc(T("bd.station.noStationFull")) + "</div></div>";
    }
    var st = (S.stations || []).filter(function (x) { return x.id === d.station || x.id === detail.id; })[0] || {};
    var sid = d.station || detail.id;
    var kv = [
      [T("bd.station.kv.station"), esc(d.station || detail.id)],
      [T("bd.station.kv.role"), esc(roleWord(st.role))]
    ];
    /* 首领写它在哪个 AI 软件；打工猫只写接活方式（用 API key 自动跑 / 会话模式） */
    if (st.role === "leader") {
      kv.push([T("bd.station.kv.app"), esc(st.client ? clientLabel(st.client) : T("bd.st.yourApp"))]);
    }
    kv.push([T("bd.station.kv.how"), esc(runnerLabel(d.runner))]);
    kv.push(
      [T("bd.station.kv.state"), esc(st.word || "-") + (st.minutes != null ? T("bd.st.minutes", { n: st.minutes }) : "")],
      [T("bd.station.kv.todo"), fmtNum(st.open)],
      [T("bd.station.kv.lastSeen"), esc(when(st.last_seen))],
      [T("bd.station.kv.where"), esc(d.where || "—")]
    );
    var sched = d.runner === "scheduled";
    if (sched) {
      kv.push([T("bd.station.kv.everyMin"), esc(everyMinText(d.every_min)), "everyMin"]);
      kv.push([T("bd.station.kv.lastRun"), st.last_scheduled_at ? esc(when(st.last_scheduled_at)) : T("bd.sched.never")]);
    }
    var promptBox = d.prompt
      ? "<pre>" + esc(d.prompt) + '</pre><div class="btnrow"><button class="btn" id="cpPrompt">' +
        esc(T("bd.station.copyPrompt")) + "</button></div>"
      : '<div class="empty">' + esc(T("bd.station.noPrompt")) + "</div>";
    var mcpBox = sched
      ? '<div class="dsec"><h3>' + esc(T("bd.station.connTitle")) + '</h3><div id="mcpBox">' +
        (d.snippet ? snippetHtml(d.snippet, d.mcp_menu_hint) : '<div class="empty">' + esc(T("bd.drawer.loading")) + "</div>") + "</div></div>"
      : "";
    var steps = (d.steps && d.steps.length)
      ? "<ol style='margin:0;padding-left:20px;font-size:13px'>" + d.steps.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ol>"
      : '<div class="empty">' + esc(T("bd.station.noSteps")) + "</div>";
    var taskLink = st.task_id
      ? '<div class="btnrow"><button class="btn" id="stTask" data-tid="' + esc(st.task_id) + '">' +
        esc(T("bd.station.openTask", { id: st.task_id })) + "</button></div>"
      : "";
    var html = '<div class="dsec"><h3>' + esc(T("bd.station.baseTitle")) + '</h3><div class="kv">' +
      kv.map(function (p) {
        return '<div class="k">' + p[0] + '</div><div class="v"' + (p[2] ? ' id="' + p[2] + '"' : "") + ">" + p[1] + "</div>";
      }).join("") +
      "</div>" + taskLink + "</div>" + mcpBox +
      '<div class="dsec"><h3>' + esc(T("bd.station.wakeTitle")) + "</h3>" + promptBox + "</div>" +
      '<div class="dsec"><h3>' + esc(T("bd.station.stepsTitle")) + "</h3>" + steps + "</div>";
    if (sched) {
      if (!d.snippet) loadSnippet(sid, d);
      if (!d.every_min) loadEveryMin(sid, d);
    }
    return html;
  }
  function everyMinText(v) { return v == null || v === "" ? "—" : T("bd.station.everyMinText", { n: fmtNum(v) }); }
  /* /api/summon 还没给 every_min 时，回工位定义里查 runner_args.every_min（只查一次） */
  function loadEveryMin(sid, d) {
    var cur = (S.stationDefs || []).filter(function (x) { return x.id === sid; })[0];
    if (cur) { fillEveryMin(sid, d, cur); return; }
    if (!S.defsReq) S.defsReq = api("/api/stations_def");
    S.defsReq.then(function (r) {
      if (r.ok && r.data && r.data.stations) S.stationDefs = r.data.stations;
      var def = (S.stationDefs || []).filter(function (x) { return x.id === sid; })[0];
      fillEveryMin(sid, d, def);
    });
  }
  function fillEveryMin(sid, d, def) {
    var v = def ? (def.runner_args || {}).every_min : null;
    if (v == null) return;
    d.every_min = v;
    var cell = $("#everyMin");
    if (cell && detail && detail.kind === "station" && detail.data === d) cell.textContent = everyMinText(v);
  }
  function snippetHtml(text, hint) {
    return "<pre>" + esc(text) + '</pre><div class="btnrow"><button class="btn" id="cpMcp">' +
      esc(T("bd.station.copyConn")) + "</button></div>" +
      (hint ? '<p class="hint">' + esc(hint) + "</p>" : "");
  }
  function loadSnippet(sid, d) {
    api("/api/connectors/snippet?client=" + encodeURIComponent(d.client || "") + "&station=" + encodeURIComponent(sid))
      .then(function (r) {
        var box = $("#mcpBox");
        if (!box || !detail || detail.kind !== "station" || detail.data !== d) return;
        var sn = (r.data && r.data.snippet) || "";
        if (!r.ok || !sn) { box.innerHTML = '<div class="empty">' + esc(T("bd.station.noSnippet")) + "</div>"; return; }
        d.snippet = sn;
        d.mcp_menu_hint = (r.data && r.data.mcp_menu_hint) || d.mcp_menu_hint || "";
        box.innerHTML = snippetHtml(sn, d.mcp_menu_hint);
        wire($("#drawer"));
      });
  }
  /* 抽屉顶上三行：结果 / 下一步 / 用时 */
  var DONE_STATES = { delivered: 1, reviewing: 1, accepted: 1, done: 1 };
  function gatesCount(md) {
    var ok = 0, n = 0;
    String(md || "").split("\n").forEach(function (l) {
      var m = /^\s*-\s*\[([ xX])\]/.exec(l);
      if (m) { n++; if (m[1] !== " ") { ok++; } }
    });
    return { ok: ok, n: n };
  }
  function spanSec(a, b) {
    if (!a) { return 0; }
    var t1 = new Date(a).getTime();
    if (isNaN(t1)) { return 0; }
    var t2 = b ? new Date(b).getTime() : Date.now();
    if (isNaN(t2)) { t2 = Date.now(); }
    return Math.max(0, Math.round((t2 - t1) / 1000));
  }
  function durText(sec) {
    var s = Math.max(0, Math.round(Number(sec) || 0));
    if (s < 60) { return T("bd.eff.sec", { n: s }); }
    var m = Math.floor(s / 60);
    if (m < 60) { return T("bd.eff.min", { n: m }); }
    return T("bd.eff.hour", { n: Math.floor(m / 60), m: m % 60 });
  }
  function resultText(t) {
    var s = t.state;
    if (DONE_STATES[s]) {
      var g = gatesCount(t.review_md);
      return T("bd.task.resultDone") + (g.n ? "，" + T("bd.task.gatesSum", { ok: g.ok, n: g.n }) : "");
    }
    if (s === "running" || s === "dispatched") { return T("bd.task.resultWorking"); }
    if (s === "queued") { return T("bd.task.resultQueued"); }
    return T("bd.task.resultFailed");
  }
  function nextText(t) {
    var s = t.state;
    var acc = (t.card || {}).acceptance || {};
    if (s === "reviewing" || s === "delivered") {
      return acc.review === "user" ? T("bd.task.nextUser") : T("bd.task.nextLeader");
    }
    if (s === "running" || s === "dispatched") { return T("bd.task.nextWorking"); }
    if (s === "queued") { return T("bd.task.nextQueued"); }
    if (s === "failed" || s === "returned" || s === "blocked" || s === "interrupted") { return T("bd.task.nextFailed"); }
    return T("bd.task.nextNone");
  }
  function timeText(t) {
    var work = 0;
    (t.runs || []).forEach(function (r) { work += spanSec(r.started, r.ended); });
    var total = durText(spanSec(t.created_at, t.done_at || t.delivered_at || null));
    return work > 0 ? T("bd.task.timeText", { t: total, w: durText(work) }) : T("bd.task.timeNone", { t: total });
  }
  function threeRows(t) {
    return '<div class="rows">' +
      "<div><b>" + esc(T("bd.task.result")) + "</b>　" + esc(resultText(t)) + "</div>" +
      "<div><b>" + esc(T("bd.task.next")) + "</b>　" + esc(nextText(t)) + "</div>" +
      "<div><b>" + esc(T("bd.task.time")) + "</b>　" + esc(timeText(t)) + "</div></div>";
  }
  /* 时间线：一项一行 —— 时分 + 名称 + 谁 */
  function timelineHtml(nodes) {
    var list = nodes || [];
    if (!list.length) { return '<div class="empty">' + esc(T("bd.task.noTimeline")) + "</div>"; }
    return '<ul class="tl">' + list.map(function (n) {
      return "<li><span class='t'>" + esc(hm(n.at)) + "</span><span class='n'>" + esc(n.label || "") +
        "</span><span class='w'>" + esc(n.who || "") + "</span></li>";
    }).join("") + "</ul>";
  }
  /* 交付单：markdown 里的一点点排版（- 开头是条目，### 是小标题） */
  function mdBody(text) {
    var out = [], ul = false;
    String(text || "").split("\n").forEach(function (l) {
      var s = l.trim();
      if (!s) { if (ul) { out.push("</ul>"); ul = false; } return; }
      if (/^###\s+/.test(s)) {
        if (ul) { out.push("</ul>"); ul = false; }
        out.push('<div class="dl-h">' + esc(s.replace(/^###\s+/, "")) + "</div>");
        return;
      }
      if (/^-\s+/.test(s)) {
        if (!ul) { out.push("<ul>"); ul = true; }
        out.push("<li>" + esc(s.replace(/^-\s+/, "")) + "</li>");
        return;
      }
      if (ul) { out.push("</ul>"); ul = false; }
      out.push("<p>" + esc(s) + "</p>");
    });
    if (ul) { out.push("</ul>"); }
    return out.join("");
  }
  /* 交付单：## 拆成四小块 */
  function deliveryHtml(md) {
    var text = String(md || "").trim();
    if (!text) { return '<div class="empty">' + esc(T("bd.task.noDelivery")) + "</div>"; }
    var chunks = text.split(/^##[ \t]+/m);
    chunks.shift();
    return '<div class="dl">' + chunks.map(function (c) {
      var i = c.indexOf("\n");
      var h = (i < 0 ? c : c.slice(0, i)).trim();
      var b = (i < 0 ? "" : c.slice(i + 1)).trim();
      return '<div class="dl-b"><div class="dl-t">' + esc(h) + "</div>" + mdBody(b) + "</div>";
    }).join("") + "</div>";
  }
  function taskHtml(t) {
    var card = t.card || {};
    var acc = card.acceptance || {};
    var toks = t.tokens || {};
    var tokSum = (toks.tok_in == null && toks.tok_out == null)
      ? T("bd.task.notCounted")
      : T("bd.tok.h.in") + " " + fmtNum(toks.tok_in) + " " + T("bd.tok.h.out") + " " + fmtNum(toks.tok_out) + " " +
        T("bd.tok.h.cr") + " " + fmtNum(toks.tok_cr) + " " + T("bd.tok.h.cw") + " " + fmtNum(toks.tok_cw) + " " +
        (toks.cost == null ? T("bd.tok.noPrice") : toks.cost);
    var kv = [
      [T("bd.task.kv.id"), esc(t.id)],
      [T("bd.task.kv.title"), esc(t.title || "-")],
      [T("bd.task.kv.kind"), esc(kindLabel(t.kind))],
      [T("bd.task.kv.station"), esc(t.assignee || "-")],
      [T("bd.task.kv.state"), stateBadge(t)],
      [T("bd.task.kv.round"), esc(t.round == null ? "-" : t.round)],
      [T("bd.task.kv.from"), esc(t.dispatcher || "-")],
      [T("bd.task.kv.reviewer"), esc(reviewLabel(acc.review)) + (acc.review === "user" && t.state === "reviewing" ? T("bd.task.waitYou") : "")],
      [T("bd.task.kv.gates"), esc((acc.gates || []).length)],
      [T("bd.task.kv.created"), esc(when(t.created_at))],
      [T("bd.task.kv.updated"), esc(when(t.updated_at))],
      [T("bd.task.kv.delivered"), esc(when(t.delivered_at))],
      [T("bd.task.kv.done"), esc(when(t.done_at))],
      [T("bd.task.kv.usage"), esc(tokSum)]
    ];
    if (t.returned_reason) kv.push([T("bd.task.kv.reason"), esc(t.returned_reason)]);

    var runs = (t.runs || []).map(function (r) {
      return "<tr><td>" + esc(r.attempt == null ? "-" : r.attempt) + "</td>" +
        "<td>" + esc(hm(r.started)) + " → " + esc(r.ended ? hm(r.ended) : T("bd.task.running")) + "</td>" +
        "<td>" + esc(exitWord(r.exit)) + "</td>" +
        "<td>" + esc(runStatusLabel(r.status)) + "</td>" +
        "<td>" + esc(tokCell(r.tokens_json)) + "</td></tr>";
    }).join("");

    var evs = (t.events || []).slice(0, 50).map(function (e) {
      return "<li><span class='t'>" + esc(when(e.ts)) + "</span><span class='k'>" + esc(evKindLabel(e.kind)) + "</span><span>" +
        esc(e.text || "") + "</span></li>";
    }).join("");

    var acts = decideBtns(t.id, t.state), reviewBox = "";
    if (acts) {
      reviewBox = '<div class="btnrow"><input class="note" id="rvNote" type="text" placeholder="' + esc(T("bd.task.note")) + '">' + acts + "</div>" +
        '<div class="okmsg" data-msg="' + esc(t.id) + '"></div>' +
        '<p class="hint">' + esc(T(acc.review === "user" && t.state === "reviewing" ? "bd.task.decideYou" : "bd.task.decideLeader")) + "</p>";
    }

    /* 高级：基本信息、任务原文、运行、自动检查、回报、事件都收在这里（默认收起） */
    var advKey = t.id + "-adv";
    var adv = '<details class="dsec adv" data-k="' + esc(advKey) + '"' + (openKeys[advKey] ? " open" : "") + ">" +
      "<summary>" + esc(T("bd.task.advanced")) + "</summary>" +
      '<div class="dsec"><h3>' + esc(T("bd.task.baseTitle")) + '</h3><div class="kv">' +
      kv.map(function (p) { return '<div class="k">' + p[0] + '</div><div class="v">' + p[1] + "</div>"; }).join("") +
      "</div></div>" +
      fold(t.id + "-card", T("bd.task.cardJson"), "<pre>" + esc(JSON.stringify(card, null, 2)) + "</pre>") +
      '<div class="dsec"><h3>' + esc(T("bd.task.runs", { n: (t.runs || []).length })) + "</h3><div class='scroll'><table class='tbl'>" +
      "<thead><tr><th>" + esc(T("bd.task.runHead")) + "</th><th>" + esc(T("bd.task.runFrom")) + "</th><th>" +
      esc(T("bd.task.runResult")) + "</th><th>" + esc(T("bd.task.runStatus")) + "</th><th>" +
      esc(T("bd.task.runUsage")) + "</th></tr></thead><tbody>" +
      (runs || '<tr><td colspan="5" class="empty">' + esc(T("bd.task.neverRan")) + "</td></tr>") + "</tbody></table></div></div>" +
      '<div class="dsec"><h3>' + esc(T("bd.task.gates")) + "</h3>" + gatesHtml(t.review_md) + "</div>" +
      '<div class="dsec"><h3>' + esc(T("bd.task.report")) + "</h3>" +
      (t.report ? "<pre>" + esc(t.report) + "</pre>" : '<div class="empty">' + esc(T("bd.task.noReport")) + "</div>") + "</div>" +
      '<div class="dsec"><h3>' + esc(T("bd.task.events", { n: Math.min((t.events || []).length, 50) })) + "</h3>" +
      ('<ul class="ev">' + (evs || '<li class="empty">' + esc(T("bd.task.noEvents")) + "</li>") + "</ul>") + "</div>" +
      "</details>";

    return '<div class="dsec">' + threeRows(t) + reviewBox + "</div>" +
      '<div class="dsec"><h3>' + esc(T("bd.task.timeline")) + "</h3>" + timelineHtml(t.timeline) + "</div>" +
      '<div class="dsec"><h3>' + esc(T("bd.task.delivery")) + "</h3>" + deliveryHtml(t.delivery) + "</div>" +
      adv;
  }
  function wire(root) {
    var close = $("#dclose", root);
    if (close) close.onclick = closeDrawer;
    var cp = $("#cpPrompt", root);
    if (cp) cp.onclick = function () { U.copy(detail.data.prompt, this, T("bd.copy.done"), T("bd.copy.fail")); };
    var cm = $("#cpMcp", root);
    if (cm) cm.onclick = function () { U.copy(detail.data.snippet, this, T("bd.copy.done"), T("bd.copy.fail")); };
    var st = $("#stTask", root);
    if (st) st.onclick = function () { openTask(st.getAttribute("data-tid") || detail.data.station || detail.id); };
    wireDecide(root);
  }

  /* ---------- 轮询 ---------- */
  function poll() {
    if (document.hidden) return Promise.resolve();
    return Promise.all([
      api("/api/meta"), api("/api/stations"), api("/api/todo"), api("/api/tasks?limit=1000")
    ]).then(function (rs) {
      var names = ["meta", "stations", "todo", "tasks"];
      var okAny = false;
      rs.forEach(function (r, i) {
        if (!r.ok) return;
        okAny = true;
        if (names[i] === "meta") S.meta = r.data;
        else if (names[i] === "stations") S.stations = r.data.stations || [];
        else if (names[i] === "todo") S.todo = r.data;
        else S.tasks = r.data.tasks || [];
      });
      S.down = !okAny;
      S.stamp = hm(new Date().toISOString());
      renderStations(); renderTodo(); renderTasks();
      if (detail && detail.kind === "task" && detail.id && detail.data) {
        if (!$("#drawer").contains(document.activeElement)) loadTask(detail.id);
      }
    });
  }
  function pollHeavy() {
    if (document.hidden) return Promise.resolve();
    var jobs = [];
    /* 用量一直要拿：标题行那句总数靠它。效率只在展开时读 */
    jobs.push(api("/api/tokens?days=7").then(function (r) {
      if (r.ok) { S.tokens = r.data; renderCostSummary(); if ($("#costBox").open) { renderTokens(); } }
    }));
    if ($("#costBox").open) {
      jobs.push(api("/api/efficiency?days=7").then(function (r) { if (r.ok) { S.eff = r.data; renderEff(); } }));
    }
    return Promise.all(jobs);
  }
  $("#costBox").addEventListener("toggle", function () {
    if (!$("#costBox").open) { return; }
    renderTokens(); renderEff(); pollHeavy();
  });
  addEventListener("bx-summon", function (e) { e.preventDefault(); openStation(e.detail); });
  $("#tkDays").onchange = function () { tkPage = 0; tkSyncRange(); renderTasks(); };
  $("#tkFrom").onchange = function () { tkPage = 0; renderTasks(); };
  $("#tkTo").onchange = function () { tkPage = 0; renderTasks(); };
  $("#tkPrev").onclick = function () { tkPage--; renderTasks(); };
  $("#tkNext").onclick = function () { tkPage++; renderTasks(); };
  $("#tkCsv").onclick = function () {
    var cols = ["id", "title", "kind", "assignee", "state", "round", "dispatcher", "created_at", "updated_at"];
    var head = T("bd.csv.head").split(",");
    var q = function (v) { v = v == null ? "" : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    var rows = [head.join(",")].concat(tkFiltered().map(function (t) {
      return cols.map(function (c) {
        return q(c === "state" ? taskStateWord(t) : c === "kind" ? kindLabel(t.kind) : t[c]);
      }).join(",");
    }));
    var blob = new Blob(["\ufeff" + rows.join("\r\n")], { type: "text/csv;charset=utf-8" });
    var a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = T("bd.csv.name", { d: new Date().toISOString().slice(0, 10) });
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  };
  $("#scrim").onclick = closeDrawer;
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeDrawer(); });
  window.BXBoard = { pickTasks: tkPick, filter: tkFilter, openTask: openTask };   /* 给测试直接喂数据调筛选逻辑 */

  /* 换语言：整页重画一遍 */
  addEventListener("bx-lang-changed", function () {
    renderStations(); renderTodo(); renderTasks(); renderCostSummary();
    if ($("#costBox").open) { renderTokens(); renderEff(); }
    if (detail) { drawDrawer(); }
  });

  pollHeavy();
  poll().then(function () {
    $("#foot").textContent = T("bd.foot.refresh") +
      (S.meta && S.meta.version ? T("bd.foot.version", { v: S.meta.version }) : "");
  });
  setInterval(poll, 5000);
  setInterval(pollHeavy, 30000);
})();
