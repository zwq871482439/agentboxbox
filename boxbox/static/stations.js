/* 工位页：工牌、详情抽屉、编辑浮层。词条在 i18n-stations.js。 */
(function () {
  var NS = window.BXST = window.BXST || {};
  function T(k, v) { return window.BXi18n ? window.BXi18n.t(k, v) : k; }
  var CLIENT_LABEL = {
    cursor: "Cursor", "claude-code": "Claude Code", codex: "Codex", pi: "Pi",
    "kimi-code": "Kimi Code", "minimax-code": "MiniMax Code", "grok-bot": "Grok Bot",
    workbuddy: "WorkBuddy", zcode: "ZCode"
  };
  var QUOTA_ADAPTER_LABEL = {
    kimi_code: "Kimi Code", glm_coding_plan: "GLM Coding Plan",
    minimax_token_plan: "MiniMax Token Plan"
  };
  var ACC_KEY = {
    cap: 1, beanie: 1, flower: 1, bow: 1, crown: 1,
    glasses: 1, sunglasses: 1, scarf: 1, bell: 1, tie: 1,
    bandana: 1, phones: 1, hoodie: 1
  };
  var SKIN_CATS = [2, 3, 4, 5, 6];       /* 和办公室同一套选猫顺序（office_feed）：首领 1 号，打工猫 2 到 6 循环 */
  var SLOT_ORDER = { A: 0, B: 1, C: 2, D: 3, E: 4, F: 5 };
  /* 配饰槽位和办公室画猫代码、核心 looks.py 同一套；王冠只给首领，这里不让选 */
  var CAT_COUNT = 8;
  var LOOK_SLOTS = {
    head: ["cap", "beanie", "flower", "bow"], face: ["glasses", "sunglasses"],
    neck: ["scarf", "bell", "tie", "bandana"], ears: ["phones"], body: ["hoodie"]
  };
  var lookDraft = { cat: 2, acc: {} };   /* 「修改配置」里正在编辑的 look（打开表单时填成工位现在的样子） */

  function $(s) { return document.querySelector(s); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function post(obj) { return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(obj) }; }
  function api(path, opts) { return fetch(path, opts).then(function (r) { return r.json(); }); }
  function num(v) { var n = Number(v); return isFinite(n) ? n : 0; }
  function fmtDT(iso) { return iso ? String(iso).slice(5, 16).replace("T", " ") : ""; }
  function clientLabel(c) {
    if (c === "pi") { return "Pi"; }
    if (c === "other") { return T("st.other"); }
    if (c === "other-direct") { return T("st.otherDirect"); }
    return CLIENT_LABEL[c] || c || "";
  }
  function accLabel(a) { return ACC_KEY[a] ? T("st.acc." + a) : a; }
  function quotaModeLabel(m) {
    if (m === "off") { return T("st.quotaOff"); }
    if (m === "after_run") { return T("st.quotaAfter"); }
    if (m === "interval") { return T("st.quotaInterval"); }
    return m || "";
  }
  function quotaAdapterLabel(a) { return a === "custom" ? T("st.adapterCustom") : (QUOTA_ADAPTER_LABEL[a] || a || ""); }

  /* 服务器返回的英文/代码错误翻成人话 */
  function humanErr(e) {
    var s = String(e || "");
    /* 后端的错词有中英两套，两套都认 */
    var m = /^(?:pi 块缺少|pi block is missing) (\w+)/.exec(s);
    if (m) {
      var field = { base_url: T("st.fieldBaseUrl"), api: T("st.fieldApi"),
                    model: T("st.fieldModel") }[m[1]] || m[1];
      return T("st.humanErrMissing", { field: field });
    }
    if (/^(?:pi 块不是对象|the pi block is not an object)/.test(s)) { return T("st.humanErrNoObj"); }
    if (/pi\.api/.test(s)) { return T("st.humanErrApi"); }
    if (/(?:必须是正整数|must be a whole number above zero)/.test(s)) { return T("st.humanErrInt"); }
    return s;
  }

  var defs = [];            // /api/stations_def
  var board = {};           // id -> /api/stations 行（word / first_seen / last_seen / has_key）
  var editing = null;       // 正在编辑的原始定义（新增时 null）
  var formLeader = false;   // 这次开的是首领的表单：只让改猫的样子
  var curProvider = "", curModel = "";   // 清单里选中的服务商 / 模型 id（手动填写时空）
  var provMount = null;
  var provNames = {};       // provider id -> 名字（工牌接入方式那行用）
  var settings = {};        // /api/settings（首领掉线阈值 wake_min）
  var meta = {};            // /api/meta（alerts：首领没反应只认这里）
  var lastOffline = null;   // 上次画工牌时首领是不是「没反应」，变了才重画

  function memberCount() { return defs.filter(function (s) { return s.role !== "leader"; }).length; }
  function slotsFull() { return memberCount() >= 6; }

  /* 首领掉线不再自己按 wake_min 算（会和看板 / 详情 / 办公室打架）。词一律用 /api/stations 的 word；
     只有核心的提醒里有 leader_quiet 时才说「没反应」。 */
  function leaderOffline(sid) {
    return (meta.alerts || []).some(function (a) { return a && a.kind === "leader_quiet" && (!sid || a.station === sid); });
  }

  /* 样式按 word_code 判（界面上换成哪种语言都一样的意思） */
  function wordClass(code) {
    if (code === "stuck" || code === "config") { return "bad"; }
    if (code === "running" || code === "running_queue" || code === "sched_late" || code === "rest") { return "busy"; }
    if (code === "off" || code === "off_queue") { return "off"; }
    if (code === "not_connected" || code === "wait_sched") { return "bad"; }
    return "ok";
  }

  /* 工牌头像：配了 look 的工位按 look 画（首领戴王冠），没 look 的老工位照旧：
     首领 1 号猫、打工猫按 2 到 6 循环。画法用办公室同一套 renderCatSprite。 */
  function avatarSpec(st, mi) {
    var lead = st.role === "leader";
    var lk = st.look && typeof st.look === "object" ? st.look : null;
    if (lk && lk.cat >= 1 && lk.cat <= 8) {
      return { cat: lk.cat, acc: (lk.acc && typeof lk.acc === "object") ? lk.acc : undefined, lead: lead };
    }
    return { cat: lead ? 1 : SKIN_CATS[mi % SKIN_CATS.length], lead: lead };
  }
  function drawAvatar(cv, st, mi) {
    if (!cv || !window.renderCatSprite) { return; }
    var spr;
    try { spr = window.renderCatSprite(avatarSpec(st || {}, mi), "sit", 0); } catch (e) { return; }
    cv.width = spr.N; cv.height = spr.N;
    var x = cv.getContext("2d");
    x.imageSmoothingEnabled = false;
    x.clearRect(0, 0, cv.width, cv.height);
    x.drawImage(spr.back, 0, 0);
    x.drawImage(spr.front, 0, 0);
  }

  /* ---------- 换猫样子：选猫框（和上岗招募同一个：8 只底猫 ◀ ▶ + 配饰五槽位） ----------
     打开表单时填成这只工位现在的 look；保存时随工位一起 POST /api/stations。
     首领的 lead 传给 renderCatSprite，预览里也能看到王冠；存的时候不写 crown，核心会自动补。 */
  function lookOf(st, mi) {
    var lk = st && st.look && typeof st.look === "object" ? st.look : null;
    if (lk && lk.cat >= 1 && lk.cat <= CAT_COUNT) {
      return { cat: lk.cat, acc: (lk.acc && typeof lk.acc === "object") ? lk.acc : {} };
    }
    var lead = st && st.role === "leader";
    return { cat: lead ? 1 : SKIN_CATS[(mi || 0) % SKIN_CATS.length], acc: {} };   // 老工位没有 look：按头像现在的分法补一个
  }
  function paintLook() {
    var lead = formLeader;
    $("#lk-cnt").textContent = T("st.pickCount", { n: lookDraft.cat, total: CAT_COUNT });
    var cv = $("#lk-cat");
    if (cv && window.renderCatSprite) {
      try {
        var spr = window.renderCatSprite({ cat: lookDraft.cat, acc: lookDraft.acc, lead: lead }, "sit", 0);
        cv.width = spr.N; cv.height = spr.N;
        var x = cv.getContext("2d");
        x.imageSmoothingEnabled = false;
        x.clearRect(0, 0, cv.width, cv.height);
        x.drawImage(spr.back, 0, 0);
        x.drawImage(spr.front, 0, 0);
      } catch (e) { }
    }
  }
  function stepLookCat(d) {
    lookDraft.cat = ((lookDraft.cat - 1 + d + CAT_COUNT) % CAT_COUNT) + 1;
    paintLook();
  }
  function fillLookSelects() {
    Object.keys(LOOK_SLOTS).forEach(function (s) {
      var sel = $("#lk-" + s);
      if (!sel || sel.options.length > 1) { return; }
      LOOK_SLOTS[s].forEach(function (a) {
        var o = document.createElement("option");
        o.value = a;
        o.textContent = accLabel(a);
        sel.appendChild(o);
      });
    });
  }
  function syncLookForm(look) {
    fillLookSelects();
    lookDraft = { cat: look.cat, acc: Object.assign({}, look.acc || {}) };
    Object.keys(LOOK_SLOTS).forEach(function (s) {
      var sel = $("#lk-" + s);
      if (sel) { sel.value = (lookDraft.acc || {})[s] || ""; }
    });
    paintLook();
  }
  function collectLook() {
    var acc = {};
    Object.keys(LOOK_SLOTS).forEach(function (s) {
      var v = $("#lk-" + s) ? $("#lk-" + s).value : "";
      if (v) { acc[s] = v; }
    });
    return { cat: lookDraft.cat, acc: acc };
  }
  /* 招新猫不撞样子：只从没被别的工位用的底猫号里挑，8 只都用过了才允许重复（和上岗那套同一个规则） */
  function pickFreeCat(used) {
    var taken = (used || []).filter(function (n) { return n >= 1 && n <= CAT_COUNT; });
    var free = [];
    for (var c = 1; c <= CAT_COUNT; c++) {
      if (taken.indexOf(c) < 0) { free.push(c); }
    }
    if (!free.length) { return 1 + Math.floor(Math.random() * CAT_COUNT); }
    return free[Math.floor(Math.random() * free.length)];
  }

  /* 打工猫只有两种接活方式：用 API key 自动跑 / 会话模式（AI 软件定时来领卡） */
  function modeOf(st) {
    if (!st) { return "pi"; }
    if (st.runner === "scheduled") { return "sched"; }
    if (st.client === "pi" || st.runner === "once") { return "pi"; }
    if (!st.client && !st.runner) { return "pi"; }   /* 新工位还没填：默认用 API key 自动跑 */
    return "sched";       /* 老工位：在会话里手动领活，按会话模式算 */
  }
  function modeText(st) {
    if (modeOf(st) !== "sched") { return T("st.modePi"); }
    return T("st.modeSchedEvery", { n: (st.runner_args || {}).every_min || 30 });
  }
  function accessLine(st, b) {
    if (st.role === "leader") {
      /* 首领用的是用户自己常用的那家 AI 软件：认得出是哪一家才写得出名字 */
      var c = (b || {}).client || "";
      var named = (c === "cursor" || c === "claude-code" || c === "codex");
      var who = named ? T("st.yourAppNamed", { x: clientLabel(c) }) : T("st.yourApp");
      return who + " · " + ((b || {}).first_seen ? T("st.connected") : T("st.notConnected"));
    }
    if (modeOf(st) === "sched") { return modeText(st); }
    var pi = st.pi || {};
    var prov = provNames[pi.provider_id] || hostOf(pi.base_url) || T("st.notConfigured");
    return T("st.modePi") + " · " + prov + " · " + (pi.model || T("st.notConfigured"));
  }
  function hostOf(base) {
    var m = /^\s*https?:\/\/([^\/\s]+)/i.exec(base || "");
    return m ? m[1] : (base || "").split("/")[0] || "";
  }
  function provName(id) {
    if (!id) { return ""; }
    if (window.BXProviders) {
      /* 清单已经在拉了（providers.js 会缓存），到货后补名字 */
      window.BXProviders.list().then(function (ps) {
        ps.forEach(function (p) { provNames[p.id] = p.name || p.id; });
        if (provNames[id]) { render(); }
      }).catch(function () {});
    }
    return provNames[id] || id;
  }

  /* 工号：首领 001，打工猫按工位 A–F 是 002–007；跟着工位走，名字随便改工号不变 */
  function workNo(st) {
    if (st.role === "leader") { return "001"; }
    var i = "ABCDEF".indexOf(st.slot || "");
    return i >= 0 ? "00" + (i + 2) : "—";
  }

  /* ---------- 工牌列表 ---------- */
  function badgeHTML(st, mi) {
    var lead = st.role === "leader";
    var b = board[st.id] || {};
    var word = b.word || T("st.idle");
    var code = b.word_code || "";
    var offline = lead && leaderOffline(st.id);
    if (offline) { word = T("st.noReact"); code = "no_react"; }
    var slot = st.slot || (lead ? "leader" : "-");
    var top = lead ? T("st.badgeTopLeader") : T("st.badgeTopMember", { slot: slot });
    var up = b.first_seen ? fmtDT(b.first_seen) : T("st.neverOnDuty");
    var shown = st.name && st.name !== st.id ? st.name : st.id;          /* 用户另起了名字就先显示名字，工位名放小字 */
    var html = '<div class="badge ' + (lead ? "leader" : "member") + '" data-id="' + esc(st.id) + '">' +
      '<div class="rope"><i class="clip"></i></div>' +
      '<div class="bcard" data-open="' + esc(st.id) + '" title="" + T("st.badgeTitle") + "">' +
        '<div class="btop"><b>' + esc(top) + '</b><span class="brand">' + esc(T("st.workNo", { n: workNo(st) })) + "</span></div>" +
        '<div class="bbody">' +
          '<canvas class="avatar" width="32" height="32"></canvas>' +
          '<div class="binfo">' +
            '<p class="bname">' + esc(shown) + (shown !== st.id ? ' <span class="bid">' + esc(st.id) + "</span>" : "") + "</p>" +
            '<p class="bline">' + esc(T("st.access", { x: accessLine(st, b) })) + "</p>" +
            '<p class="bline">' + esc(T("st.onDuty", { x: up })) + "</p>" +
            '<p class="bline">' + esc(T("st.state")) + '<b class="word ' + wordClass(code) + '">' + esc(word) + "</b></p>" +
          "</div>" +
        "</div>" +
        '<div class="bbtns">';
    if (lead) {
      html += '<button class="mbtn" data-edit="' + esc(st.id) + '" title="' + esc(T("st.reRecruitTitle")) + '">' +
        esc(T("st.reRecruit")) + "</button>" +
        '<button class="mbtn' + (offline || code === "not_connected" ? " hl" : "") + '" data-summon="' + esc(st.id) +
        '" title="' + esc(T("st.wakeTitle")) + '">' + esc(T("st.wake")) + "</button>";
      if (defs.filter(function (s) { return s.role === "leader"; }).length > 1) {
        html += '<button class="mbtn danger" data-del="' + esc(st.id) + '" title="' + esc(T("st.delLeaderTitle")) + '">' + esc(T("st.del")) + "</button>";
      }
    } else {
      var full = slotsFull();
      var copyTip = full ? ' disabled title="' + esc(T("st.copyFullTitle")) + '"'
        : ' title="' + esc(T("st.copyTitle")) + '"';
      html += '<button class="mbtn" data-copy="' + esc(st.id) + '"' + copyTip + ">" + esc(T("st.copy")) + "</button>" +
        '<button class="mbtn" data-edit="' + esc(st.id) + '" title="' + esc(T("st.editTitle")) + '">' +
        esc(T("st.edit")) + "</button>" +
        '<button class="mbtn danger" data-del="' + esc(st.id) +
        '" title="' + esc(T("st.delTitle")) + '">' + esc(T("st.del")) + "</button>";
    }
    html += '<button class="mbtn" data-detail="' + esc(st.id) + '">' + esc(T("st.detail")) + "</button>";
    html += "</div></div></div>";
    return html;
  }

  function render() {
    var leaders = defs.filter(function (s) { return s.role === "leader"; });
    var members = defs.filter(function (s) { return s.role !== "leader"; }).sort(function (a, b) {
      var oa = SLOT_ORDER[a.slot] == null ? 9 : SLOT_ORDER[a.slot];
      var ob = SLOT_ORDER[b.slot] == null ? 9 : SLOT_ORDER[b.slot];
      return oa - ob || String(a.id).localeCompare(String(b.id));
    });
    lastOffline = leaders.length ? leaderOffline() : null;
    $("#head-count").textContent = T("st.headCount", { l: leaders.length, m: members.length });
    var html = "";
    if (!defs.length) {
      html = '<div class="empty">' + esc(T("st.empty")) + "</div>";
    } else {
      html += leaders.map(function (s) { return badgeHTML(s, 0); }).join("");
      html += members.map(function (s, i) { return badgeHTML(s, i); }).join("");
    }
    $("#badges").innerHTML = html;
    var ordered = leaders.concat(members);      /* 工牌顺序，对着 canvas 画头像 */
    Array.prototype.forEach.call($("#badges").querySelectorAll("canvas.avatar"), function (cv, i) {
      if (ordered[i]) { drawAvatar(cv, ordered[i], i - leaders.length); }
    });
    $("#lonely").hidden = !(leaders.length && !members.length);
    var btn = $("#btn-new");
    if (slotsFull()) {
      btn.disabled = true;
      btn.textContent = T("st.full");
      btn.title = T("st.fullTitle");
    } else {
      btn.disabled = false;
      btn.textContent = T("st.recruit", { n: members.length });
      btn.title = T("st.recruitTitle");
    }
  }

  function load() {
    return Promise.all([
      api("/api/stations_def", { cache: "no-store" }),
      api("/api/stations", { cache: "no-store" }),
      api("/api/settings", { cache: "no-store" }),
      api("/api/meta", { cache: "no-store" })
    ]).then(function (r) {
      defs = (r[0] && r[0].stations) || [];
      board = {};
      ((r[1] && r[1].stations) || []).forEach(function (row) { board[row.id] = row; });
      settings = r[2] || {};
      meta = r[3] || {};
      render();
      var need = {};
      defs.forEach(function (s) {
        var pi = (s.client === "pi" || s.runner === "once") && (s.pi || {});
        if (pi && pi.provider_id) { need[pi.provider_id] = true; }
      });
      var ids = Object.keys(need);
      if (ids.length && !Object.keys(provNames).length && window.BXProviders) {
        provName(ids[0]);   /* 拉一次清单，到货后 render 重画名字 */
      }
    }).catch(function () {
      $("#badges").innerHTML = '<div class="empty">' + esc(T("st.down")) + "</div>";
    });
  }

  function pageMsg(text, kind) {
    var box = $("#table-msg");
    box.hidden = !text;
    box.textContent = text || "";
    box.className = "msg " + (kind || "fail");
  }

  /* 顶栏 5 秒一次的 /api/meta 顺路拿来判断首领掉线，状态变了重画 */
  window.addEventListener("bx-top", function (ev) {
    if (!ev.detail || !ev.detail.meta) { return; }
    meta = ev.detail.meta;
    var now = leaderOffline();
    if (defs.length && now !== lastOffline) { render(); }
  });

  /* ---------- 复制 ---------- */
  function copyText(text) {
    var box = $("#copy-fallback");
    box.value = text;
    box.hidden = false;
    box.select();
    try { document.execCommand("copy"); } catch (e) { }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(function () { });
    }
    setTimeout(function () { box.hidden = true; }, 4000);
  }

  /* ---------- 首领「恢复状态」：复制唤醒话（复用 summon 接口） ---------- */
  function summon(sid) {
    api("/api/summon/" + encodeURIComponent(sid)).then(function (r) {
      if (!r || !r.ok) { pageMsg(T("st.wakeFail", { why: (r && r.text) || T("st.wakeNoAnswer") })); return; }
      copyText(r.prompt || "");
      pageMsg(T("st.wakeOk", { x: String(r.prompt || "").slice(0, 10) }), "ok");
    }).catch(function (e) { pageMsg(T("st.wakeFail", { why: String(e) })); });
  }

  /* ---------- 复制打工猫 ---------- */
  function copyStation(id) {
    api("/api/stations/copy", post({ id: id })).then(function (r) {
      if (!r || !r.ok) { pageMsg(T("st.copyFail", { why: (r && r.text) || T("st.copyUnknown") })); return; }
      pageMsg(T("st.copyOk", { id: r.station.id, slot: r.station.slot }), "ok");
      load();
    }).catch(function (e) { pageMsg(T("st.copyFail", { why: String(e) })); });
  }

  /* ---------- 删除（在跑的先弹页面内确认框） ---------- */
  var dlgYes = null;
  function askDelete(text, yes) {
    $("#del-text").textContent = text;
    $("#delDlg").hidden = false;
    dlgYes = yes;
  }
  function doDelete(id, confirmIt) {
    api("/api/stations/delete", post({ id: id, confirm: !!confirmIt })).then(function (r) {
      if (r && r.code === "busy") {
        askDelete(r.text + T("st.askSure"), function () { doDelete(id, true); });
        return;
      }
      if (!r || !r.ok) { pageMsg(T("st.delFail", { why: (r && r.text) || T("st.delNoBox") })); return; }
      var cut = (r.interrupted || []).length ? T("st.delCut", { n: r.interrupted.length }) : "";
      pageMsg(T("st.delOk", { id: id, cut: cut, extra: r.text ? " " + r.text : "" }), "ok");
      closeForm();
      load();
    }).catch(function (e) { pageMsg(T("st.delFail", { why: String(e) })); });
  }
  $("#del-no").onclick = function () { $("#delDlg").hidden = true; dlgYes = null; };
  $("#del-yes").onclick = function () {
    $("#delDlg").hidden = true;
    var f = dlgYes; dlgYes = null;
    if (f) { f(); }
  };

  /* ---------- 编辑浮层 ---------- */
  function flashErr(text) {
    $("#errs").innerHTML = "<div>" + esc(text) + "</div>";
    $("#formBox").hidden = false;
  }

  function openForm(id) {
    editing = null;
    defs.forEach(function (s) { if (s.id === id) { editing = s; } });
    var st = editing || { id: "", role: "member", enabled: true };
    var pi = st.pi || {};
    var q = st.quota || {};
    var custom = q.custom || {};
    formLeader = st.role === "leader";
    $("#formTitle").textContent = editing ? T("st.formEdit", { id: editing.id }) : T("st.formNew");
    $("#f-id").value = st.id || "";
    $("#f-id").readOnly = !!editing;
    $("#f-mode").value = modeOf(st);
    $("#f-cwd").value = st.cwd || "";
    $("#f-enabled").checked = st.enabled !== false;
    $("#p-base").value = pi.base_url || "";
    $("#p-api").value = pi.api || "anthropic-messages";
    $("#p-key").value = "";
    $("#p-key").placeholder = (board[st.id] || {}).has_key ? T("st.keySetPh") : T("st.keyPh");
    $("#p-model").value = pi.model || "";
    $("#p-ctx").value = pi.context_window || 200000;
    $("#p-max").value = pi.max_tokens || 32000;
    curProvider = pi.provider_id || "";
    curModel = pi.model_id || "";
    if (provMount) { provMount.resetPickers(pi.provider_id, pi.model_id); }
    /* 打开表单时选猫框显示这只工位现在的 look（老工位没 look 的按头像分法补一个；新增时挑没被用的底猫） */
    if (editing) {
      var mi = 0;
      defs.filter(function (s) { return s.role !== "leader"; }).forEach(function (s, i) { if (s.id === editing.id) { mi = i; } });
      syncLookForm(lookOf(editing, mi));
    } else {
      var used = defs.map(function (s) { return num((s.look || {}).cat); }).filter(function (n) { return n >= 1 && n <= CAT_COUNT; });
      syncLookForm({ cat: pickFreeCat(used), acc: {} });
    }
    $("#q-mode").value = q.mode || "off";
    $("#q-every").value = q.interval_min || 30;
    $("#q-adapter").removeAttribute("data-dirty");
    $("#q-adapter").value = q.adapter || suggestQuotaAdapter();
    $("#q-url").value = custom.url || "";
    $("#q-auth").value = custom.auth || "bearer";
    $("#q-pct").value = custom.pct_path || "";
    $("#q-rem").value = custom.remaining_pct_path || "";
    $("#q-reset").value = custom.reset_path || "";
    $("#s-every").value = (st.runner_args || {}).every_min || 30;
    $("#c-in").value = (st.cost || {}).in == null ? "" : st.cost.in;
    $("#c-out").value = (st.cost || {}).out == null ? "" : st.cost.out;
    $("#errs").innerHTML = "";
    msg("", true);
    $("#picheck-msg").hidden = true;
    $("#quota-msg").hidden = true;
    $("#sched-hint").textContent = T("st.schedHint");
    syncBlocks();
    $("#formBox").hidden = false;
  }

  function closeForm() {
    $("#formBox").hidden = true;
    editing = null;
    formLeader = false;
    $("#errs").innerHTML = "";
    msg("", true);
  }

  /* 首领的表单只留「猫的样子」：接活方式、接口、工作目录、启用都不露 */
  function syncRoleBlocks() {
    $("#f-mode-row").hidden = formLeader;
    $("#f-cwd-row").hidden = formLeader;
    $("#f-enabled-row").hidden = formLeader;
    if (formLeader) {
      $("#piBox").hidden = true;
      $("#schedBox").hidden = true;
    }
  }

  function syncBlocks() {
    var mode = $("#f-mode").value;
    $("#piBox").hidden = mode !== "pi";
    $("#schedBox").hidden = mode !== "sched";
    $("#f-mode-hint").textContent = mode === "pi" ? T("st.modePiDesc") : T("st.modeSchedDesc");
    syncRoleBlocks();
    syncQuotaBlocks();
  }

  function syncQuotaBlocks() {
    $("#q-every-f").hidden = $("#q-mode").value !== "interval";
    $("#q-custom").hidden = $("#q-adapter").value !== "custom";
  }

  /* 按接口地址主机名建议余量适配器；用户手动换过（data-dirty）就不动 */
  var HOST_ADAPTER = {
    "api.kimi.com": "kimi_code", "open.bigmodel.cn": "glm_coding_plan",
    "minimaxi.com": "minimax_token_plan", "minimax.cn": "minimax_token_plan"
  };
  function suggestQuotaAdapter() {
    var m = /^\s*https?:\/\/([^\/\s]+)/i.exec($("#p-base").value || "");
    var host = m ? m[1].toLowerCase() : ($("#p-base").value || "").toLowerCase();
    var a = "custom";
    Object.keys(HOST_ADAPTER).forEach(function (h) {
      if (host === h || host.endsWith("." + h)) { a = HOST_ADAPTER[h]; }
    });
    return a;
  }
  function refreshQuotaSuggestion() {
    var sel = $("#q-adapter");
    if (sel.getAttribute("data-dirty")) { return; }
    sel.value = suggestQuotaAdapter();
    syncQuotaBlocks();
  }

  function msg(text, hide, kind) {
    var box = $("#form-msg");
    box.hidden = !!hide;
    box.textContent = text || "";
    box.className = "msg " + (kind || "info");
  }

  function collect() {
    var look = collectLook();              // 换猫样子，随工位一起存（crown 不选，首领的王冠核心自动补）
    if (formLeader && editing) {
      /* 首领只让改样子：原来那条工位原样带回去 */
      var keep = Object.assign({}, editing);
      keep.look = look;
      return keep;
    }
    var st = { id: $("#f-id").value.trim(), role: "member", enabled: $("#f-enabled").checked };
    var cwd = $("#f-cwd").value.trim();
    if (cwd) { st.cwd = cwd; }
    st.look = look;
    if (editing && editing.note != null) {
      st.note = editing.note;           // 没露面的字段原样带走（quota 由查余量设置区编辑）
    }
    if ($("#f-mode").value === "sched") {
      st.client = "";
      st.runner = "scheduled";
      st.runner_args = { every_min: Math.max(5, num($("#s-every").value) || 30) };
      if (editing && editing.quota != null) { st.quota = editing.quota; }   /* 会话模式不查余量：原样带走 */
    } else {
      st.client = "pi";
      st.runner = "once";
      st.pi = collectPi();
      st.quota = collectQuota();
    }
    var ci = $("#c-in").value.trim(), co = $("#c-out").value.trim();
    if (ci !== "" || co !== "") {
      st.cost = {};
      if (ci !== "") { st.cost.in = num(ci); }
      if (co !== "") { st.cost.out = num(co); }
    }
    return st;
  }

  function collectPi() {
    var pi = { base_url: $("#p-base").value.trim(), api: $("#p-api").value,
               model: $("#p-model").value.trim(),
               context_window: num($("#p-ctx").value), max_tokens: num($("#p-max").value),
               reasoning: piReasoning() };
    if (curProvider) { pi.provider_id = curProvider; }   // 清单里选的，算价格用
    if (curModel) { pi.model_id = curModel; }
    return pi;
  }

  /* 推理：清单里选的模型说了算；没选就沿用原来的；都没有就开着 */
  function piReasoning() {
    var m = provMount && provMount.model ? provMount.model() : null;
    if (m && m.reasoning != null) { return !!m.reasoning; }
    if (editing && editing.pi && editing.pi.reasoning != null) { return !!editing.pi.reasoning; }
    return true;
  }

  function collectQuota() {
    var q = { mode: $("#q-mode").value };
    if (q.mode === "interval") { q.interval_min = Math.max(1, num($("#q-every").value) || 30); }
    q.adapter = $("#q-adapter").value;
    if (q.adapter === "custom") {
      q.custom = { url: $("#q-url").value.trim(), auth: $("#q-auth").value,
                   pct_path: $("#q-pct").value.trim(),
                   remaining_pct_path: $("#q-rem").value.trim(),
                   reset_path: $("#q-reset").value.trim() };
    }
    return q;
  }

  $("#btn-new").onclick = function () { openForm(null); };
  $("#btn-lonely").onclick = function () { openForm(null); };
  /* 从首页「登记向导」过来（/#recruit → 这里）：已经上岗过，直接弹出招募表单 */
  if (location.hash === "#recruit") { setTimeout(function () { openForm(null); }, 300); }
  $("#btn-cancel").onclick = closeForm;
  $("#btn-x").onclick = closeForm;
  $("#f-mode").onchange = syncBlocks;
  $("#q-mode").onchange = syncQuotaBlocks;
  $("#q-adapter").onchange = function () { this.setAttribute("data-dirty", "1"); syncQuotaBlocks(); };
  $("#p-base").oninput = refreshQuotaSuggestion;
  $("#btn-cost-reset").onclick = function () { $("#c-in").value = ""; $("#c-out").value = ""; };
  /* ◀ ▶ 换底猫 */
  $("#lk-prev").onclick = function () { stepLookCat(-1); };
  $("#lk-next").onclick = function () { stepLookCat(1); };

  /* 服务商 / 模型从清单选：选中自动填，手动填写就自己填 */
  if (window.BXProviders) {
    provMount = window.BXProviders.mount({
      provBox: document.getElementById("provPick"),
      modelBox: document.getElementById("modelPick"),
      onProvider: function (p) {
        curProvider = p ? p.id : "";
        curModel = "";
        if (p) {
          if (p.api) { $("#p-base").value = p.api; }
          if (p.api_type) { $("#p-api").value = p.api_type; }
          refreshQuotaSuggestion();
        }
      },
      onModel: function (m) {
        curModel = m ? m.id : "";
        if (m) {
          $("#p-model").value = m.id;
          if (m.context) { $("#p-ctx").value = m.context; }
          if (m.output) { $("#p-max").value = m.output; }
        }
      }
    });
  }

  $("#btn-save").onclick = function () {
    var btn = this;
    var st = collect();
    $("#errs").innerHTML = "";
    msg("", true);
    if (!st.id) { flashErr(T("st.errEmptyId")); return; }
    btn.disabled = true;
    api("/api/stations", post(st))
      .then(function (r) {
        if (!r.ok) {
          var box = $("#errs");
          var errs = r.errors && r.errors.length ? r.errors : [r.text || T("st.saveFailDefault")];
          box.innerHTML = errs.map(function (e) { return "<div>· " + esc(humanErr(e)) + "</div>"; }).join("");
          msg(T("st.notSaved"), false, "fail");
          return;
        }
        var say = T("st.saved", { id: st.id });
        if (st.runner === "scheduled") {
          say += " " + T("st.savedSched", { n: st.runner_args.every_min });
        }
        editing = st;
        $("#f-id").readOnly = true;
        var key = $("#p-key").value;
        if (key && (st.client === "pi" || st.runner === "once")) {       // key goes to the write-only endpoint, never into the station
          return api("/api/secrets", post({ station: st.id, api_key: key })).then(function (r2) {
            if (!r2.ok) { pageMsg(T("st.savedKeyFail", { why: r2.text || T("st.savedKeyUnknown") })); }
            else { say = T("st.savedKey", { id: st.id }); $("#p-key").value = ""; }
            pageMsg(say, "ok");
            closeForm();
            return load();
          });
        }
        pageMsg(say, "ok");
        closeForm();
        return load();
      })
      .catch(function (e) { flashErr(String(e)); })
      .then(function () { btn.disabled = false; });
  };

  $("#btn-picheck").onclick = function () {
    var box = $("#picheck-msg");
    box.hidden = false;
    box.className = "msg info";
    var sid = $("#f-id").value.trim();
    if (!sid) { box.className = "msg fail"; box.textContent = T("st.picheckNeedId"); return; }
    var known = defs.some(function (s) { return s.id === sid; });
    if (!known) { box.className = "msg fail"; box.textContent = T("st.picheckNotSaved", { id: sid }); return; }
    box.textContent = T("st.pichecking");
    api("/api/pi/check?station=" + encodeURIComponent(sid))
      .then(function (r) {
        if (r.ok || r.state === "ok") {
          box.className = "msg ok";
          box.textContent = T("st.picheckOk", { x: (r.text && r.text !== "ok" ? r.text : T("st.picheckOkDefault")) });
        } else if (r.state === "unreachable") {
          /* 连不上不算招不了——这只猫先留着，派给它的卡会排队等接口，连上自动开工 */
          box.className = "msg info";
          box.textContent = T("st.picheckUnreachable", { host: r.host || "?" });
        } else if (r.state === "limited") {
          /* 429 / 太忙：请求到了、密钥也认了，只是这会儿被限流或额度见底 */
          box.className = "msg info";
          box.textContent = T("st.picheckLimited", { why: r.text || "" });
        } else {
          box.className = "msg fail";
          box.textContent = T("st.picheckFail", { state: r.state || "?", why: r.text || T("st.picheckUnknown") });
        }
      })
      .catch(function (e) { box.className = "msg fail"; box.textContent = T("st.reqFail", { why: e }); });
  }

  /* 现在查一次余量：同步查，结果显示在旁边；不存 key */
  $("#btn-quota").onclick = function () {
    var box = $("#quota-msg");
    box.hidden = false;
    box.className = "msg info";
    var sid = $("#f-id").value.trim();
    if (!sid) { box.className = "msg fail"; box.textContent = T("st.quotaNeedId"); return; }
    var known = defs.some(function (s) { return s.id === sid; });
    if (!known) { box.className = "msg fail"; box.textContent = T("st.quotaNotSaved", { id: sid }); return; }
    box.textContent = T("st.quotaChecking");
    api("/api/quota/check", post({ station: sid }))
      .then(function (r) {
        if (r && r.ok) {
          box.className = "msg ok";
          var parts = ["h5", "week", "month"].map(function (k) {
            var w = (r.windows || {})[k];
            if (!w) { return null; }
            return (w.label || T("st.quotaWindow." + k)) + T("st.quotaUsed", { n: Math.round(w.pct) });
          }).filter(Boolean);
          box.textContent = parts.length ? parts.join(", ") : T("st.quotaUnknownWindow");
        } else {
          box.className = "msg fail";
          box.textContent = T("st.quotaFail", { kind: (r && r.error_kind) || T("st.quotaUnknown"), why: (r && r.error) || "" });
        }
      })
      .catch(function (e) { box.className = "msg fail"; box.textContent = T("st.reqFail", { why: e }); });
  }

  /* ---------- 工牌上的按钮（事件委托） ---------- */
  $("#badges").addEventListener("click", function (ev) {
    var t = ev.target;
    var id = t.getAttribute && t.getAttribute("data-edit");
    if (id) { openForm(id); return; }
    id = t.getAttribute && t.getAttribute("data-copy");
    if (id) { if (!t.disabled) { copyStation(id); } return; }
    id = t.getAttribute && t.getAttribute("data-del");
    if (id) {
      var b = board[id] || {};
      if (b.task_id && b.title) {                        /* 在跑：第一道确认框就说清会中断哪张卡 */
        askDelete(T("st.askDelBusy", { id: id, title: b.title }), function () { doDelete(id, true); });
      } else {
        askDelete(T("st.askDel", { id: id }), function () { doDelete(id, false); });
      }
      return;
    }
    id = t.getAttribute && t.getAttribute("data-summon");
    if (id) { summon(id); return; }
    id = t.getAttribute && t.getAttribute("data-detail");
    if (id) { NS.openDrawer(id); return; }
    if (t.closest && !t.closest("button")) {          /* 点工牌本体（不是按钮）也进详情 */
      var card = t.closest("[data-open]");
      if (card) { NS.openDrawer(card.getAttribute("data-open")); }
    }
  });

  $("#reload").onclick = function () { pageMsg(""); load(); };

  /* 详情抽屉（stations-drawer.js）要用的都挂上来 */
  NS.esc = esc;
  NS.clientLabel = clientLabel;
  NS.modeOf = modeOf;
  NS.modeText = modeText;
  NS.fmtDT = fmtDT;
  NS.workNo = workNo;
  NS.drawAvatar = drawAvatar;
  NS.api = api;
  NS.getDefs = function () { return defs; };
  NS.quotaModeLabel = quotaModeLabel;
  NS.quotaAdapterLabel = quotaAdapterLabel;
  NS.$ = $;
  NS.openForm = openForm;

  /* 换语言：词表换一遍，工牌和表单重画 */
  addEventListener("bx-lang-changed", function () {
    if (defs.length) { render(); }
    if (!$("#formBox").hidden) { openForm(editing ? editing.id : null); }
  });

  load();
  window.BXStations = { load: load, pickFreeCat: pickFreeCat, summon: summon, pageMsg: pageMsg };
})();
