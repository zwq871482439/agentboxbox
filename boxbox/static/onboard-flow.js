/* 上岗流程 · 编排：常量、随机配饰 / 选号、步骤表 FLOW、收尾、入口 boot。
   依赖 onboard-common.js（状态和窗口）、onboard-leader.js、onboard-member.js（先加载）。 */
(function () {
  "use strict";
  var NS = window.BXOB;
  var S = NS.S;
  var num = NS.num, dget = NS.dget;

  /* ================= 这一份文件的文案（中文 / 英文） ================= */
  NS.addTxt("flow", {
    'askFirst': ['来加第一个帮手吧！', 'Let\'s add the first helper!'],
    'askLater': ['加一个帮手才能派活，去「帮手」页', 'Add a helper before work can be handed out — add one on the Helpers page'],
    'askMore': ['想加更多，去「帮手」页', 'To add more, go to the Helpers page'],
    'done.backToChat': [
      '回到你的编程助手，说一句「把 XX 派给帮手」。',
      'Back in your coding assistant, say “hand XX to the helpers”.'
    ],
    'done.dispatchBtn': ['在 Cursor 里派活', 'Dispatch in Cursor'],
    'done.goStations': ['加一个，回来就能说「把 XX 派给帮手」。', 'Add one, then come back and say “hand XX to the helpers”.'],
    'done.hint': [
      '派出去的活、帮手干的活，都会在办公室和「任务」页里看到。',
      'Dispatched work and helper runs show up in the office and on the Tasks page.'
    ],
    'done.lookOffice': ['先看看办公室', 'Look at the office'],
    'done.noMember': ['还没有帮手，编程助手现在派不了活。它只派活、不自己干。', 'No helper yet, so your coding assistant cannot hand out work. It only hands work out.'],
    'done.okBtn': ['好的', 'OK'],
    'done.stationsLink': ['「帮手」页', 'Helpers page'],
    'done.titleLeaderOnly': ['编程助手到岗了', 'Your coding assistant is on duty'],
    'done.titleReady': ['可以派活了', 'Ready for work'],
    'startRecruit': ['加一个帮手', 'Add a helper'],
  });

  /* ================= 常量 ================= */
  var ANIM_TIMEOUT = 3000;              /* 画布压根没上线时的兜底：3 秒不回 bx-anim-done 就当播完 */
  var ANIM_READY_TIMEOUT = 10000;       /* 等 bx-anim-ready（画布加载好）的上限；机器忙时 exe 第一帧 feed 可能要好几秒 */
  var ANIM_WAIT = 30000;                /* 画布在线时等它真回 done 的上限：快递猫送一趟箱要走十几秒 */
  var RESUME_WAIT = 8000;               /* 刷新后重摆画面：先等画布加载好，不然重发的消息没人收 */
  var LEADER_HINT_MS = window.__bxLeaderHintMs || 45 * 1000;   /* 等首领报到 45 秒还没来就给排查清单；测试可以调短 */
  var LEADER_CHECK_MS = 20 * 1000;      /* 20 秒先查一次客户端那边的开关（Cursor 把 boxbox 关了是最常见的卡点） */
  var POLL_MS = 2000;
  NS.ANIM_TIMEOUT = ANIM_TIMEOUT;
  NS.ANIM_READY_TIMEOUT = ANIM_READY_TIMEOUT;
  NS.ANIM_WAIT = ANIM_WAIT;
  NS.RESUME_WAIT = RESUME_WAIT;
  NS.LEADER_HINT_MS = LEADER_HINT_MS;
  NS.LEADER_CHECK_MS = LEADER_CHECK_MS;
  NS.POLL_MS = POLL_MS;

  /* 配饰槽位：跟核心 looks.py 和办公室画猫代码同一套；首领的王冠由核心存 look 时补上 */
  var SLOTS = {
    head: ["crown", "cap", "beanie", "flower", "bow"], face: ["glasses", "sunglasses"],
    neck: ["scarf", "bell", "tie", "bandana"], ears: ["phones"], body: ["hoodie"]
  };
  var SLOT_KEYS = ["head", "face", "neck", "ears", "body"];

  /* ================= 随机配饰 / 选号 ================= */
  /* 招募用的随机配饰：0–3 件、槽位不重复、永远不出王冠（跟核心 looks.py 的 random_look 同一套规则） */
  function randomAcc() {
    var keys = SLOT_KEYS.slice();
    for (var i = keys.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = keys[i]; keys[i] = keys[j]; keys[j] = t;
    }
    var acc = {};
    keys.slice(0, Math.floor(Math.random() * 4)).forEach(function (s) {
      var opts = SLOTS[s].filter(function (a) { return a !== "crown"; });
      acc[s] = opts[Math.floor(Math.random() * opts.length)];
    });
    return acc;
  }
  function randomCat(used) { return pickFreeCat(used, Math.random); }
  /* 随机选号只从「还没被别的工位用的底猫号」里挑，8 只都用过了才允许重复。
     抽成纯函数（随机源 rng 可以注入）方便单测：rng 是 () -> [0,1) 的浮点，和 Math.random 同口径。 */
  function pickFreeCat(used, rng) {
    var taken = (used || []).filter(function (n) { return n >= 1 && n <= NS.CAT_COUNT; });
    var free = [];
    for (var c = 1; c <= NS.CAT_COUNT; c++) {
      if (taken.indexOf(c) < 0) { free.push(c); }
    }
    if (!free.length) { return 1 + Math.floor(rng() * NS.CAT_COUNT); }
    return free[Math.floor(rng() * free.length)];
  }
  /* 现有工位都在用哪些底猫号（excludeId：正在编辑的这只自己不算，换样子时可以保持原号） */
  function usedCats(items, excludeId) {
    return (items || []).filter(function (s) { return !excludeId || s.id !== excludeId; })
      .map(function (s) { return num((s.look || {}).cat, 0); });
  }
  function courierLook() { return { cat: randomCat(), acc: {} }; }     /* 快递猫：画布那边戴上快递帽 */
  NS.randomAcc = randomAcc;
  NS.randomCat = randomCat;
  NS.pickFreeCat = pickFreeCat;
  NS.usedCats = usedCats;

  /* ================= 流程步骤 ================= */
  var FLOW = [
    NS.sceneAnim("box_in", { name: "box_in", slot: "leader", couriers: [courierLook(), courierLook()] }),
    { key: "welcome", run: NS.stepWelcome },
    { key: "leader_install", run: NS.stepInstallLeader },
    NS.sceneAnim("box_open", { name: "box_open", slot: "leader", look: null }),
    NS.sceneAnim("crown", { name: "crown", slot: "leader" }),
    NS.sceneAnim("say_start", { name: "say", slot: "leader", text: NS.tx("flow.askFirst") }, NS.tx("flow.startRecruit")),
    { key: "member", run: NS.stepRecruitMember },
    { key: "member_access", run: NS.stepMemberAccess },
    NS.sceneAnim("box_in2", { name: "box_in", slot: null, couriers: [courierLook(), courierLook()] }),
    NS.sceneAnim("box_open2", { name: "box_open", slot: null, look: null }),
    NS.sceneAnim("say_more", { name: "say", slot: "leader", text: NS.tx("flow.askMore") }),
    { key: "done", run: stepDone }
  ];
  var SKIP_WITHOUT_MEMBER = ["member", "member_access", "box_in2", "box_open2"];   /* 「稍后再招」以后不走的几步 */

  /* 每条动画消息里有些参数要现算（首领的样子、打工猫的工位），先补齐 */
  function fillScene() {
    FLOW.forEach(function (s) {
      var m = s.anim && s.anim.msg;
      if (!m) { return; }
      if (m.slot === null) { m.slot = S.memberSlot; }
      if (m.name === "say") { m.text = NS.tx(s.key === "say_more" ? "flow.askMore" : "flow.askFirst"); }
      if (s.key === "say_start") { s.anim.button = NS.tx("flow.startRecruit"); }
      if (m.name === "box_open") {
        m.look = m.slot === "leader" ? S.leaderLook : S.memberLook;
        m.who = m.slot === "leader" ? (S.leaderName || NS.defaultLeaderName()) : (S.memberName || NS.defaultMemberBase() + "A");
        /* 猫名走 who：信封里的 name 永远是动画名 */
      }
    });
  }
  NS.fillScene = fillScene;
  /* 老进度里拆成三步的那段（招首领 / 接入方式 / 接首领）现在并成一步 */
  var LEGACY_LEADER = { leader: 1, leader_access: 1, leader_connect: 1 };
  function stepKey() { return LEGACY_LEADER[S.prog.step] ? "leader_install" : S.prog.step; }
  function startIndex() {
    var step = stepKey();
    for (var i = 0; i < FLOW.length; i++) {
      if (FLOW[i].key === step) { return i; }
    }
    return 0;
  }
  function run() {
    fillScene();
    var from = startIndex();
    /* 刷新后 iframe 里的画布是重新加载的：先等它加载好（bx-anim-ready 在它读完数据之后才发），
       再把播过的动画用 instant 摆回去 —— 早发了没人收，箱子、王冠、坐着的猫就都摆不上了 */
    return NS.ready(from > 0 ? RESUME_WAIT : ANIM_READY_TIMEOUT).then(function () {
      /* 已经播过的动画用 instant 摆回播完的样子，不重播 */
      FLOW.slice(0, from).forEach(function (s) {
        if (s.anim && S.prog.played.indexOf(s.anim.key) >= 0) { NS.instant(s.anim); }
      });
      return FLOW.slice(from).reduce(function (chain, s) {
        return chain.then(function () {
          if (S.skipMember && SKIP_WITHOUT_MEMBER.indexOf(s.key) >= 0) { return null; }   /* 点了「稍后再招」 */
          if (s.key) { NS.setStep(s.key); }
          if (s.key === "say_more" && S.skipMember) { s.anim.msg.text = NS.tx("flow.askLater"); }
          return s.anim ? NS.play(s.anim) : (s.run ? s.run() : null);
        });
      }, Promise.resolve());
    });
  }

  /* 上岗结束：不再给要复制的派卡示范，只说一句回编程助手里怎么说；Cursor 再给一键派活按钮 */
  function stepDone() {
    NS.closeWin();
    return new Promise(function (res) {
      setTimeout(function () {                   /* 首领说完那句停 3 秒，再弹收尾窗口 */
        NS.setStep("done");
        var isCursor = String(dget("leader_client", "")) === "cursor";
        var body = S.skipMember
          ? "<p>" + NS.esc(NS.tx("flow.done.noMember")) + "</p>" +
            '<p>去<a href="/stations">' + NS.esc(NS.tx("flow.done.stationsLink")) + "</a>" +
            NS.esc(NS.tx("flow.done.goStations")) + "</p>"
          : "<p>" + NS.esc(NS.tx("flow.done.backToChat")) + "</p>" +
            '<p class="hint">' + NS.esc(NS.tx("flow.done.hint")) + "</p>" +
            (isCursor ? '<p style="margin-top:10px"><a class="pxb main" id="ob-dispatch" href="#">' +
              NS.esc(NS.tx("flow.done.dispatchBtn")) + "</a></p>" : "");
        var w = NS.win({
          title: S.skipMember ? NS.tx("flow.done.titleLeaderOnly") : NS.tx("flow.done.titleReady"),
          titleKey: S.skipMember ? "flow.done.titleLeaderOnly" : "flow.done.titleReady",
          body: body,
          buttons: [{
            text: NS.tx(S.skipMember ? "flow.done.lookOffice" : "flow.done.okBtn"), main: true,
            on: function (x) { x.close(); res(); }
          }]
        });
        if (isCursor) {
          NS.api("/api/connectors/snippet?client=cursor&station=" + encodeURIComponent(S.leaderName || "") +
            NS.langParam2()).then(function (r) {
            var a = w.$("#ob-dispatch");
            if (!a) { return; }
            if (r.ok && r.data.dispatch_link) { a.href = r.data.dispatch_link; }
            else { a.remove(); }
          });
        }
      }, 3000);
    });
  }

  /* ================= 入口 ================= */
  /* 已经有首领（工位页 / 接口登记的，或者上岗进度丢了）时，不能从「欢迎」重来一遍。
     按核心推导的 step 定一个最早能开始的步骤：4 = 首领还没来握手 → 装进编程助手那一步；6 = 还没帮手 → 加一个帮手。
     跳过去的那几段动画记成播过，run() 会用 instant 把箱子 / 王冠摆回去。 */
  function keyIndex(k) {
    for (var i = 0; i < FLOW.length; i++) { if (FLOW[i].key === k) { return i; } }
    return -1;
  }
  function floorStep(state, lead) {
    var floor = null;
    if (state.step === 4 && lead) { floor = "leader_install"; }
    else if (state.step === 6 && lead) { floor = "member"; }
    if (!floor) { return; }
    var fi = keyIndex(floor);
    /* 只在进度是空的、或者还停在「装编程助手」之前时才往后挪；进度已经走到那以后就照进度接着做
       （首领刚握完手、进度停在装那一步时，要先给「已连上」和开箱 / 王冠，不能跳过） */
    if (keyIndex(stepKey()) >= keyIndex("leader_install")) { return; }
    FLOW.slice(0, fi).forEach(function (s) {
      if (s.anim && S.prog.played.indexOf(s.anim.key) < 0) { S.prog.played.push(s.anim.key); }
    });
    S.prog.step = floor;
    if (lead && lead.client) { NS.draft({ leader_client: lead.client }); }
  }
  function boot(state) {
    if (!state || !state.step) { return Promise.resolve(false); }
    S.state = state;
    return NS.api("/api/onboard/progress").then(function (r) {
      if (r.ok && r.data) {
        S.prog = { step: r.data.step || "", played: r.data.played || [], draft: r.data.draft || {} };
      }
      return NS.stationsDef().then(function (items) {
        var lead = items.filter(function (s) { return s.role === "leader"; })[0];
        if (lead) {
          S.leaderName = lead.id;
          if (lead.look) { S.leaderLook = lead.look; }
          NS.draft({ leader_name: lead.id, leader_cat: (lead.look || {}).cat || 1, leader_client: lead.client });
        } else if (S.prog.draft.leader_name) {
          /* 刷新后接着做：首领还没存进工位，名字只在草稿里（招首领那一步填的） */
          S.leaderName = String(S.prog.draft.leader_name);
          S.leaderLook = { cat: num(S.prog.draft.leader_cat, 1), acc: S.prog.draft.leader_acc || {} };
        }
        var mem = items.filter(function (s) { return s.role === "member"; })[0];
        if (mem) {
          S.memberName = mem.id;
          S.memberSlot = mem.slot || "A";
          if (mem.look) { S.memberLook = mem.look; }
        } else if (S.prog.draft.member_name) {
          /* 刷新后接着做：这只猫还没存进工位，名字只在草稿里（招猫那一步填的） */
          S.memberName = String(S.prog.draft.member_name);
          S.memberLook = { cat: num(S.prog.draft.member_cat, 2), acc: S.prog.draft.member_acc || {} };
        }
        floorStep(state, lead);
        return run();
      });
    }).catch(function (e) {
      /* 上岗流程自己出错不该把首页带崩：窗口收起来，办公室照常 */
      NS.closeWin();
      if (window.console) { window.console.warn("上岗流程出错", e); }
      return false;
    });
  }

  window.BXOnboard = {
    boot: boot, play: NS.play, closeWin: NS.closeWin, run: run,
    S: S, FLOW: FLOW, PI_FAIL: NS.PI_FAIL, ANIM_TIMEOUT: ANIM_TIMEOUT, LEADER_HINT_MS: LEADER_HINT_MS,
    randomAcc: randomAcc,                      /* 配饰那套规则（0–3 件、不出王冠）给页面自测用 */
    randomCat: randomCat, pickFreeCat: pickFreeCat, usedCats: usedCats   /* 选号逻辑也给页面自测用 */
  };
})();
