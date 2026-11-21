/* 帮手页：工牌、详情抽屉、编辑浮层。词条在 i18n-stations.js。 */
(function () {
  var NS = window.BXST = window.BXST || {};
  function T(k, v) { return window.BXi18n ? window.BXi18n.t(k, v) : k; }
  /* 共用工具在 util.js 里 */
  var U = window.BXu;
  var QUOTA_ADAPTER_LABEL = {
    kimi_code: "Kimi Code", glm_coding_plan: "GLM Coding Plan",
    minimax_token_plan: "MiniMax Token Plan"
  };
  var ACC_KEY = {
    cap: 1, beanie: 1, flower: 1, bow: 1, crown: 1,
    glasses: 1, sunglasses: 1, scarf: 1, bell: 1, tie: 1,
    bandana: 1, phones: 1, hoodie: 1
  };
  var SKIN_CATS = [2, 3, 4, 5, 6];       /* 和办公室同一套选猫顺序（office_feed）：编程助手 1 号，帮手 2 到 6 循环 */
  var SLOT_ORDER = { A: 0, B: 1, C: 2, D: 3, E: 4, F: 5 };
  /* 配饰槽位和办公室画猫代码、核心 looks.py 同一套；王冠只给编程助手，这里不让选 */
  var CAT_COUNT = 8;
  var LOOK_SLOTS = {
    head: ["cap", "beanie", "flower", "bow"], face: ["glasses", "sunglasses"],
    neck: ["scarf", "bell", "tie", "bandana"], ears: ["phones"], body: ["hoodie"]
  };
  var lookDraft = { cat: 2, acc: {} };   /* 「换个样子」小窗里正在挑的样子 */
  var lookState = { cat: 2, acc: {} };   /* 这只帮手现在的样子（表单保存时一起带走） */
  var lookLead = false;                 /* 预览里要不要戴王冠（编程助手） */

  function $(s) { return document.querySelector(s); }
  var esc = U.esc, api = U.apiRaw, toNum = U.toNum;
  function post(obj) { return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(obj) }; }
  function fmtDT(iso) { return iso ? String(iso).slice(5, 16).replace("T", " ") : ""; }
  /* 客户端显示名：名字表在 util.js，这里只传本页的词 */
  function clientLabel(c) {
    return U.clientLabel(c, { other: T("st.other"), otherDirect: T("st.otherDirect") });
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
  var formLeader = false;   // 这次开的是编程助手的表单：只让改名字那些
  var piForm = null;         // 共用的 Pi 配置表（pi-form.js）
  var lookStation = null;    // 正在改样子的工位（换个样子的小窗）
  var settings = {};        // /api/settings（编程助手掉线阈值 wake_min）
  var meta = {};            // /api/meta（alerts：编程助手没反应只认这里）
  var lastOffline = null;   // 上次画工牌时编程助手是不是「没反应」，变了才重画

  function memberCount() { return defs.filter(function (s) { return s.role !== "leader"; }).length; }
  function slotsFull() { return memberCount() >= 6; }

  /* 编程助手掉线不再自己按 wake_min 算（会和看板 / 详情 / 办公室打架）。词一律用 /api/stations 的 word；
     只有核心的提醒里有 leader_quiet 时才说「没反应」。 */
  function leaderOffline(sid) {
    return (meta.alerts || []).some(function (a) { return a && a.kind === "leader_quiet" && (!sid || a.station === sid); });
  }

  /* 工牌头像：配了 look 的帮手按 look 画（编程助手戴王冠），没 look 的老帮手照旧：
     编程助手 1 号猫、帮手按 2 到 6 循环。画法用办公室同一套 renderCatSprite。 */
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
     打开表单时填成这只帮手现在的 look；保存时随帮手一起 POST /api/stations。
     编程助手的 lead 传给 renderCatSprite，预览里也能看到王冠；存的时候不写 crown，核心会自动补。 */
  function lookOf(st, mi) {
    var lk = st && st.look && typeof st.look === "object" ? st.look : null;
    if (lk && lk.cat >= 1 && lk.cat <= CAT_COUNT) {
      return { cat: lk.cat, acc: (lk.acc && typeof lk.acc === "object") ? lk.acc : {} };
    }
    var lead = st && st.role === "leader";
    return { cat: lead ? 1 : SKIN_CATS[(mi || 0) % SKIN_CATS.length], acc: {} };   // 老帮手没有 look：按头像现在的分法补一个
  }
  function paintLook() {
    var lead = lookLead;
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
  /* 小窗里挑好的样子：先记住，已经存过的帮手顺手就存了 */
  function applyLook(next) {
    lookState = { cat: next.cat, acc: Object.assign({}, next.acc || {}) };
    if (!lookStation) { return; }
    var st = lookStation;
    var payload = Object.assign({}, st);
    payload.look = lookState;
    api("/api/stations", post(payload)).then(function (r) {
      if (!r || !r.ok) {
        pageMsg(T("st.lookFail", { why: (r && r.text) || T("st.saveFailDefault") }), "fail");
        return;
      }
      $("#lookDlg").hidden = true;
      lookStation = null;
      pageMsg(T("st.lookOk", { id: st.id }), "ok");
      load();
    }).catch(function (e) { pageMsg(T("st.lookFail", { why: String(e) }), "fail"); });
  }
  /* 招新猫不撞样子：只从没被别的帮手用的底猫号里挑，8 只都用过了才允许重复（和上岗那套同一个规则） */
  function pickFreeCat(used) {
    var taken = (used || []).filter(function (n) { return n >= 1 && n <= CAT_COUNT; });
    var free = [];
    for (var c = 1; c <= CAT_COUNT; c++) {
      if (taken.indexOf(c) < 0) { free.push(c); }
    }
    if (!free.length) { return 1 + Math.floor(Math.random() * CAT_COUNT); }
    return free[Math.floor(Math.random() * free.length)];
  }

  /* 帮手只有两种干活方式：用 API key 自动跑 / 定时来领活（AI 软件定时来领卡） */
  function modeOf(st) {
    if (!st) { return "pi"; }
    if (st.runner === "scheduled") { return "sched"; }
    if (st.client === "pi" || st.runner === "once") { return "pi"; }
    if (!st.client && !st.runner) { return "pi"; }   /* 新帮手还没填：默认用 API key 自动跑 */
    return "sched";       /* 老帮手：在会话里手动领活，按定时来领活算 */
  }
  function modeText(st) {
    if (modeOf(st) !== "sched") { return T("st.modePi"); }
    return T("st.modeSchedEvery", { n: (st.runner_args || {}).every_min || 30 });
  }
  /* 工号：编程助手 001，帮手按帮手 A–F 是 002–007；跟着帮手走，名字随便改工号不变 */
  function workNo(st) {
    if (st.role === "leader") { return "001"; }
    var i = "ABCDEF".indexOf(st.slot || "");
    return i >= 0 ? "00" + (i + 2) : "—";
  }

  /* ---------- 工牌列表 ---------- */
  /* 工牌上只留一个「⋯」：名字下面一句话状态（status_line），别的都在「⋯」菜单里 */
  function badgeHTML(st, mi) {
    var lead = st.role === "leader";
    var b = board[st.id] || {};
    var word = b.word || T("st.idle");
    var code = b.word_code || "";
    var offline = lead && leaderOffline(st.id);
    if (offline) { word = T("st.noReact"); }
    var slot = st.slot || (lead ? "leader" : "-");
    var top = lead ? T("st.badgeTopLeader") : T("st.badgeTopMember", { slot: slot });
    /* 显示名优先；老版本起过的 name 也认（升级上来的不丢名字）；都没有就 id */
    var shown = (b.label || "").trim() || (st.name && st.name !== st.id ? st.name : "") || st.id;
    var line = (b.status_line || "").trim() || word;
    return '<div class="badge ' + (lead ? "leader" : "member") + '" data-id="' + esc(st.id) + '">' +
      '<div class="rope"><i class="clip"></i></div>' +
      '<div class="bcard" data-open="' + esc(st.id) + '" title="' + esc(lead ? T("st.badgeTitleLeader") : T("st.badgeTitleMember")) + '">' +
        '<div class="btop"><b>' + esc(top) + '</b><span class="brand">' + esc(T("st.workNo", { n: workNo(st) })) + "</span></div>" +
        '<div class="bbody">' +
          '<canvas class="avatar" width="32" height="32"></canvas>' +
          '<div class="binfo">' +
            '<p class="bname">' + esc(shown) + "</p>" +
            '<p class="bline st">' + esc(line) + "</p>" +
          "</div>" +
        "</div>" +
        '<button class="mbtn dots' + (lead && (offline || code === "not_connected") ? " hl" : "") +
        '" type="button" data-menu="' + esc(st.id) + '" aria-haspopup="true"' +
        ' aria-expanded="false" title="' + esc(T("st.more")) + '">⋯</button>' +
      "</div></div>";
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
      btn.textContent = T("st.addHelper");
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

  /* 顶栏 5 秒一次的 /api/meta 顺路拿来判断编程助手掉线，状态变了重画 */
  window.addEventListener("bx-top", function (ev) {
    if (!ev.detail || !ev.detail.meta) { return; }
    meta = ev.detail.meta;
    var now = leaderOffline();
    if (defs.length && now !== lastOffline) { render(); }
  });

  /* ---------- 编程助手「恢复状态」：复制唤醒话（复用 summon 接口） ---------- */
  /* 「怎么派活」：去首页的「叫醒编程助手」抽屉——上面是「装进 Cursor / Claude Code / Codex」
     （装一次以后新对话不用再贴话），下面才是复制唤醒话。上岗走完以后只有那里能装 */
  function summon(sid) {
    location.href = "/#summon=" + encodeURIComponent(sid);
  }

  /* ---------- 复制帮手 ---------- */
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
  /* 菜单里点「删除」：在跑的那只先说清会中断哪张卡 */
  function askDel(id) {
    var b = board[id] || {};
    if (b.task_id && b.title) {
      askDelete(T("st.askDelBusy", { id: id, title: b.title }), function () { doDelete(id, true); });
    } else {
      askDelete(T("st.askDel", { id: id }), function () { doDelete(id, false); });
    }
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
    formLeader = st.role === "leader";
    $("#formTitle").textContent = editing ? T("st.formEdit", { id: editing.id }) : T("st.formNew");
    $("#f-id").value = st.id || "";
    $("#f-id").readOnly = !!editing;
    $("#f-mode").value = modeOf(st);
    $("#f-cwd").value = st.cwd || "";
    $("#f-enabled").checked = st.enabled !== false;
    /* Pi 那部分：共用 pi-form.js 的表，上岗那边也是它 */
    var pi = st.pi || {};
    piForm.fill({
      base_url: pi.base_url || "", api: pi.api || "anthropic-messages",
      model: pi.model || "", model_id: pi.model_id || "", provider_id: pi.provider_id || "",
      context_window: pi.context_window || 200000, max_tokens: pi.max_tokens || 32000,
      reasoning: pi.reasoning,
      cost_in: (st.cost || {}).in == null ? "" : st.cost.in,
      cost_out: (st.cost || {}).out == null ? "" : st.cost.out,
      quota: st.quota || {}
    });
    piForm.setKeyed(!!(board[st.id] || {}).has_key);
    /* 猫的样子在单独的小窗里改：新增时先挑一个没用过的底猫号 */
    if (editing) {
      lookState = lookOf(editing, memberIndex(editing.id));
    } else {
      var used = defs.map(function (s) { return toNum((s.look || {}).cat); }).filter(function (n) { return n >= 1 && n <= CAT_COUNT; });
      lookState = { cat: pickFreeCat(used), acc: {} };
    }
    lookLead = formLeader;
    $("#s-every").value = (st.runner_args || {}).every_min || 30;
    $("#errs").innerHTML = "";
    msg("", true);
    piForm.clearMessage();
    piForm.clearMessage(piForm.ids.quotaMsg);
    $("#sched-hint").textContent = T("st.schedHint");
    syncBlocks();
    $("#formBox").hidden = false;
  }
  /* 这只帮手在成员里的序号（头像和样子按它排） */
  function memberIndex(id) {
    var mi = 0;
    defs.filter(function (s) { return s.role !== "leader"; }).forEach(function (s, i) { if (s.id === id) { mi = i; } });
    return mi;
  }

  function closeForm() {
    $("#formBox").hidden = true;
    editing = null;
    formLeader = false;
    $("#errs").innerHTML = "";
    msg("", true);
  }

  /* 编程助手的表单只留「猫的样子」：干活方式、接口、工作目录、启用都不露 */
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
  }

  function msg(text, hide, kind) {
    var box = $("#form-msg");
    box.hidden = !!hide;
    box.textContent = text || "";
    box.className = "msg " + (kind || "info");
  }

  function collect() {
    if (formLeader && editing) {
      /* 编程助手只让改名字：原来那条工位原样带回去（样子以「换个样子」小窗里挑的为准） */
      var lead = Object.assign({}, editing);
      lead.look = { cat: lookState.cat, acc: Object.assign({}, lookState.acc || {}) };
      return lead;
    }
    var st = { id: $("#f-id").value.trim(), role: "member", enabled: $("#f-enabled").checked };
    var cwd = $("#f-cwd").value.trim();
    if (cwd) { st.cwd = cwd; }
    /* 猫的样子在「换个样子」的小窗里改，这里原样带走 */
    st.look = { cat: lookState.cat, acc: Object.assign({}, lookState.acc || {}) };
    if (editing && editing.note != null) {
      st.note = editing.note;           // 没露面的字段原样带走
    }
    if ($("#f-mode").value === "sched") {
      st.client = "";
      st.runner = "scheduled";
      st.runner_args = { every_min: Math.max(5, toNum($("#s-every").value) || 30) };
      if (editing && editing.quota != null) { st.quota = editing.quota; }   /* 定时来领活不查额度：原样带走 */
    } else {
      st.client = "pi";
      st.runner = "once";
      var cfg = piForm.read();
      st.pi = cfg.pi;
      st.quota = cfg.quota;
      if (cfg.cost) { st.cost = cfg.cost; }
    }
    return st;
  }

  $("#btn-new").onclick = function () { openForm(null); };
  $("#btn-lonely").onclick = function () { openForm(null); };
  /* 从首页「登记向导」过来（/#recruit → 这里）：已经上岗过，直接弹出招募表单 */
  if (location.hash === "#recruit") { setTimeout(function () { openForm(null); }, 300); }
  $("#btn-cancel").onclick = closeForm;
  $("#btn-x").onclick = closeForm;
  $("#f-mode").onchange = syncBlocks;
  /* ◀ ▶ 换底猫 */
  $("#lk-prev").onclick = function () { stepLookCat(-1); };
  $("#lk-next").onclick = function () { stepLookCat(1); };
  $("#lk-cancel").onclick = function () { $("#lookDlg").hidden = true; lookStation = null; };
  $("#lk-save").onclick = saveLook;
  $("#f-look-btn").onclick = function () { openLook(editing ? editing.id : null); };

  /* Pi 那部分：共用 pi-form.js 的表（上岗「加一个帮手」也是它） */
  mountPiForm();

  /* 换个样子：单独的小窗，改完单独存（crown 不选，编程助手的王冠核心自动补）
     id 为空 = 还没存过的帮手：先挑好，跟表单一起存 */
  function openLook(id) {
    var st = id ? defs.filter(function (s) { return s.id === id; })[0] : null;
    lookStation = st || null;
    lookLead = st ? st.role === "leader" : formLeader;
    syncLookForm(st ? lookOf(st, memberIndex(st.id)) : lookState);
    $("#lookDlg").hidden = false;
  }
  function saveLook() {
    var next = collectLook();
    lookState = { cat: next.cat, acc: Object.assign({}, next.acc || {}) };
    if (!lookStation) {           /* 还没存过的帮手：跟着表单一起存 */
      $("#lookDlg").hidden = true;
      return;
    }
    applyLook(lookState);
  }
  function mountPiForm() {
    piForm = window.BXPiForm.mount($("#piForm"), {
      ids: {
        prov: "provPick", provInput: "p-prov", model: "modelPick", modelInput: "p-model",
        base: "p-base", api: "p-api", ctx: "p-ctx", max: "p-max", key: "p-key",
        costIn: "p-cost-in", costOut: "p-cost-out",
        qmode: "p-qmode", qadapter: "p-qadapter", qevery: "p-qevery",
        qurl: "p-q-url", qauth: "p-q-auth", qpct: "p-q-pct", qrem: "p-q-rem", qreset: "p-q-reset",
        testBtn: "btn-picheck", testMsg: "picheck-msg",
        quotaBtn: "btn-quota", quotaMsg: "quota-msg"
      },
      onTest: testPi,
      onQuotaCheck: checkQuota
    });
  }
  /* 测试连接：测的是已存好的那个工位（密钥在保存时存进 data/secrets.json） */
  function testPi(cfg) {
    var sid = $("#f-id").value.trim();
    if (!sid) { piForm.setMessage("fail", T("st.picheckNeedId")); return; }
    var known = defs.some(function (s) { return s.id === sid; });
    if (!known) { piForm.setMessage("fail", T("st.picheckNotSaved", { id: sid })); return; }
    piForm.setMessage("wait", T("st.pichecking"));
    var t0 = Date.now();
    return api("/api/pi/check?station=" + encodeURIComponent(sid))
      .then(function (r) {
        var secs = ((Date.now() - t0) / 1000).toFixed(1);
        if (r.ok || r.state === "ok") {
          piForm.setMessage("ok", T("pf.connected", { model: esc(cfg.pi.model), n: secs }) +
            (r.text && r.text !== "ok" ? "<br>" + esc(r.text) : ""));
        } else if (r.state === "unreachable") {
          piForm.setMessage("fail", T("pf.unreachable", { host: esc(r.host || "?") }));
        } else if (r.state === "limited") {
          piForm.setMessage("ok", T("pf.connectedLimited", { model: esc(cfg.pi.model) }));
        } else {
          piForm.setMessage("fail", T("st.picheckFail",
            { state: esc(r.state || "?"), why: esc(r.text || T("st.picheckUnknown")) }));
        }
      })
      .catch(function (e) { piForm.setMessage("fail", T("st.reqFail", { why: e })); });
  }
  /* 现在查一次额度：查的是已存好的那个工位 */
  function checkQuota() {
    var sid = $("#f-id").value.trim();
    var qid = piForm.ids.quotaMsg;
    if (!sid) { piForm.setMessage("fail", T("st.quotaNeedId"), qid); return; }
    var known = defs.some(function (s) { return s.id === sid; });
    if (!known) { piForm.setMessage("fail", T("st.quotaNotSaved", { id: sid }), qid); return; }
    piForm.setMessage("wait", T("st.quotaChecking"), qid);
    return api("/api/quota/check", post({ station: sid }))
      .then(function (r) {
        if (r && r.ok) {
          var parts = ["h5", "week", "month"].map(function (k) {
            var w = (r.windows || {})[k];
            if (!w) { return null; }
            return (w.label || T("st.quotaWindow." + k)) + T("st.quotaUsed", { n: Math.round(w.pct) });
          }).filter(Boolean);
          piForm.setMessage("ok", parts.length ? parts.join(", ") : T("st.quotaUnknownWindow"), qid);
        } else {
          piForm.setMessage("fail",
            T("st.quotaFail", { kind: (r && r.error_kind) || T("st.quotaUnknown"), why: (r && r.error) || "" }), qid);
        }
      })
      .catch(function (e) { piForm.setMessage("fail", T("st.reqFail", { why: e }), qid); });
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
        var key = piForm.read().key;
        if (key && (st.client === "pi" || st.runner === "once")) {       // key goes to the write-only endpoint, never into the station
          return api("/api/secrets", post({ station: st.id, api_key: key })).then(function (r2) {
            if (!r2.ok) { pageMsg(T("st.savedKeyFail", { why: r2.text || T("st.savedKeyUnknown") })); return load(); }
            say = T("st.savedKey", { id: st.id });
            piForm.clearKey();
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

  $("#reload").onclick = function () { pageMsg(""); load(); };

  /* 详情抽屉（stations-drawer.js）和共用小功能（stations-shared.js）要用的都挂上来 */
  NS.esc = esc;
  NS.clientLabel = clientLabel;
  NS.modeOf = modeOf;
  NS.modeText = modeText;
  NS.fmtDT = fmtDT;
  NS.workNo = workNo;
  NS.drawAvatar = drawAvatar;
  NS.api = api;
  NS.post = post;
  NS.load = load;
  NS.pageMsg = pageMsg;
  NS.summon = summon;
  NS.copyStation = copyStation;
  NS.askDel = askDel;
  NS.getDefs = function () { return defs; };
  NS.labelOf = function (id) { return ((board[id] || {}).label || "").trim(); };
  NS.quotaModeLabel = quotaModeLabel;
  NS.quotaAdapterLabel = quotaAdapterLabel;
  NS.$ = $;
  NS.openForm = openForm;
  NS.openLook = openLook;

  /* 换语言：词表换一遍，工牌和表单重画 */
  addEventListener("bx-lang-changed", function () {
    if (defs.length) { render(); }
    if (!$("#formBox").hidden) { openForm(editing ? editing.id : null); }
  });

  load();
  window.BXStations = { load: load, pickFreeCat: pickFreeCat, summon: summon, pageMsg: pageMsg, piForm: piForm };
})();
