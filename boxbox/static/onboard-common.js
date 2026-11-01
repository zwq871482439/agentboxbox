/* 上岗流程的公共底座：共享状态 S、进度存取、动画协议、像素窗口、选猫框。
   拆成几个文件是为了每个文件不超 800 行：本文件先加载，首领 / 打工猫 / 流程编排三个文件再用它。

   页面（home.html）引 pixelwin.css 和本组文件之后，在首页脚本里调一次 window.BXOnboard.boot(state)：
   state 是 /api/onboard/state 的返回；step 不是 0 就进入上岗模式，办公室照常显示，窗口叠在上面。

   动画在办公室画布（iframe 里）上播，两边只通过 postMessage 说话：
     home → office  {"type":"bx-anim","id":<递增>,"name":<动画名>, ...参数}
     office → home  {"type":"bx-anim-ready"} / {"type":"bx-anim-done","id":同一个 id} / {"type":"bx-anim-click","id":同一个 id}
   画布上线后（发过 bx-anim-ready）就一直等它真回 bx-anim-done：快递猫送一趟箱要走十几秒，3 秒不够；
   画布压根没上线时才退回 3 秒兜底，每次兜底都在 window.__onboardTimeouts 里记一笔（联调测试断言它是 0）。

   每一步把 step 写进 /api/onboard/progress，动画播完把名字加进 played，表单输入实时存 draft（不含 API key）。
   刷新或关掉再开，从记下的那一步接着做；played 里的动画不重播（带 instant:true 直接把画面摆成播完的样子）。 */
(function () {
  "use strict";
  var NS = window.BXOB = window.BXOB || {};

  /* ================= 小工具 ================= */
  NS.$ = function (s, r) { return (r || document).querySelector(s); };
  NS.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  NS.num = function (v, dflt) { var n = parseInt(v, 10); return isNaN(n) ? (dflt || 0) : n; };
  /* 文案表：中文照旧（老文案一个字没动），英文另写一份；每个文件登记自己那一份，键不重名。
     取词：NS.tx("lead.welcome.title")；要带数就 NS.tx("lead.connect.waited", {n: "12 秒"}) */
  NS.TXT = {};
  /* 登记文案：NS.addTxt("lead", {…})，键会带上这个前缀（lead.welcome.title），各文件不重名 */
  NS.addTxt = function (area, o) {
    var pre = typeof area === "string" ? area : "";
    var pack = (typeof area === "string" ? o : area) || {};
    Object.keys(pack).forEach(function (k) { NS.TXT[pre ? pre + "." + k : k] = pack[k]; });
  };
  NS.tx = function (key, vars) {
    var m = NS.TXT[key];
    if (!m) { return key; }
    var s = NS.lang() === "en" ? (m[1] || m[0]) : m[0];
    if (vars) {
      Object.keys(vars).forEach(function (k) { s = s.split("{" + k + "}").join(vars[k]); });
    }
    return s;
  };
  NS.lang = function () { return window.BXi18n ? window.BXi18n.lang() : "zh"; };
  /* 问后端要文案时带上语言，后端照这个语言回 */
  NS.langParam = function () { return "?lang=" + NS.lang(); };
  /* 换语言：记住选择、告诉办公室画布、当前窗口重画（每一步自己登记怎么重画） */
  NS.setLang = function (l) { if (window.BXi18n) { window.BXi18n.setLang(l); } };
  NS.rerender = null;      /* 当前窗口怎么重画 */
  addEventListener("bx-lang-changed", function () { if (NS.rerender) { NS.rerender(); } });
  NS.api = function (path, opts) {
    return fetch(path, Object.assign({ cache: "no-store" }, opts || {})).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, data: d }; });
    }).catch(function (e) { return { ok: false, data: { text: String(e) } }; });
  };
  NS.post = function (path, body) {
    return NS.api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  };
  NS.copyText = function (text, btn) {
    function flash(ok) {
      if (!btn) { return; }
      var o = btn.textContent;
      btn.textContent = ok ? NS.tx("common.copied") : NS.tx("common.copyFail");
      setTimeout(function () { btn.textContent = o; }, 1500);
    }
    function execCopy() {
      var ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      return ok;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { flash(true); }, function () { flash(execCopy()); });
    } else { flash(execCopy()); }
  };
  /* 用办公室同一套画猫代码画一只猫（cats.js 的 renderCatSprite，前后两层叠一张） */
  NS.drawCat = function (cv, spec) {
    if (!cv || typeof renderCatSprite !== "function") { return; }
    var sp = renderCatSprite(spec || { cat: 2 }, "sit", 0, "");
    var s = sp.N * 3;
    cv.width = s; cv.height = s;
    var tmp = document.createElement("canvas");
    tmp.width = s; tmp.height = s;
    var tx = tmp.getContext("2d");
    tx.imageSmoothingEnabled = false;
    tx.drawImage(sp.back, 0, 0, s, s);
    tx.drawImage(sp.front, 0, 0, s, s);
    var x = cv.getContext("2d");
    x.imageSmoothingEnabled = false;
    x.drawImage(tmp, 0, 0);
  };
  NS.CAT_COUNT = 8;          /* 底猫 8 只，跟 looks.py / cats.js 对齐 */
  /* 猫的默认名字跟着界面语言走（英文界面给个英文名，改了也一样能用）；没定下来之前留空，用的时候再取默认 */
  NS.defaultLeaderName = function () { return NS.tx("lead.recruit.defaultLeader"); };
  NS.defaultMemberBase = function () { return NS.tx("member.recruit.defaultWorker"); };

  /* ================= 进度（/api/onboard/progress） ================= */
  var S = NS.S = {
    state: null, prog: { step: "", played: [], draft: {} }, clients: [],
    leaderLook: { cat: 1, acc: {} }, leaderName: "", client: "",
    memberLook: { cat: 2, acc: {} }, memberName: "", memberSlot: "A", provMount: null,
    memberHasKey: false      /* 这只打工猫的 key 存进 data/secrets.json 了吗（GET /api/stations 的 has_key） */
  };
  var SECRET_KEYS = ["api_key", "key", "m_key", "p_key", "ob-key"];   /* 这些不进草稿 */
  function save() { return NS.post("/api/onboard/progress", { step: S.prog.step, played: S.prog.played, draft: S.prog.draft }); }
  NS.setStep = function (k) { S.prog.step = k; save(); };
  NS.markPlayed = function (key) {
    if (S.prog.played.indexOf(key) < 0) { S.prog.played.push(key); save(); }
  };
  NS.draft = function (patch) {
    var clean = {};
    Object.keys(patch || {}).forEach(function (k) { if (SECRET_KEYS.indexOf(k) < 0) { clean[k] = patch[k]; } });
    Object.assign(S.prog.draft, clean);
    save();
  };
  NS.dget = function (k, dflt) { return S.prog.draft[k] === undefined ? dflt : S.prog.draft[k]; };

  /* ================= 上岗动画协议 ================= */
  var animSeq = 0, animReady = false, readyGaveUp = false, waiting = {}, readyWaiters = [];
  window.__onboardTimeouts = 0;         /* 走过兜底的动画次数（联调：接上真画布后全程应该是 0） */
  window.__onboardTimeoutLog = [];      /* 兜底时记一笔：哪个动画等了多久 */
  function postToOffice(msg) {
    var f = document.getElementById("office-frame");
    if (!f || !f.contentWindow) { return false; }
    f.contentWindow.postMessage(msg, "*");
    return true;
  }
  NS.postToOffice = postToOffice;
  addEventListener("message", function (e) {
    var d = e.data || {};
    if (d.type === "bx-anim-ready") {
      animReady = true;
      while (readyWaiters.length) { readyWaiters.shift()(); }
      return;
    }
    /* done = 动画播完；click = 气泡上的按钮被点。两件事分开等：画布回 done 不等于用户点了 */
    if (d.type === "bx-anim-done") { fireBack(d.id, "done"); return; }
    if (d.type === "bx-anim-click") { fireBack(d.id, "click"); }
  });
  /* 画布就绪（最多等 ms；等过一次还没来，后面的不等了，别让流程慢成好几倍） */
  function ready(ms) {
    if (animReady || readyGaveUp) { return Promise.resolve(animReady); }
    return new Promise(function (res) {
      var done = function () { clearTimeout(t); res(animReady); };
      var t = setTimeout(function () { readyGaveUp = true; done(); }, ms || NS.ANIM_READY_TIMEOUT);
      readyWaiters.push(done);
    });
  }
  NS.ready = ready;
  NS.isAnimReady = function () { return animReady; };
  /* 等画布回话。kind = "done"（动画播完）/ "click"（气泡上的按钮被点）；ms = 0 表示一直等。
     来了 resolve(true)，到点还没来 resolve(false)（走兜底）。同一个 id 上两种等的人分开记。 */
  function waitBack(id, kind, ms) {
    return new Promise(function (res) {
      var fired = false, box = waiting[id] = waiting[id] || {};
      function enter() {
        if (fired) { return; }
        fired = true;
        if (box[kind]) {
          box[kind] = box[kind].filter(function (f) { return f !== enter; });
          if (!box[kind].length) { delete box[kind]; }
        }
        if (!(box.done || []).length && !(box.click || []).length) { delete waiting[id]; }
        res(true);
      }
      (box[kind] = box[kind] || []).push(enter);
      if (ms) { setTimeout(function () { if (!fired) { fired = true; res(false); } }, ms); }
    });
  }
  NS.waitBack = waitBack;
  /* 画布回话了：这一种等的全放行；这个 id 上两种都没人等了就从表里去掉（别一直挂着） */
  function fireBack(id, kind) {
    var box = waiting[id], list = box && box[kind];
    if (!list || !list.length) { return; }
    delete box[kind];
    list.forEach(function (fn) { fn(); });
    if (!(box.done || []).length && !(box.click || []).length) { delete waiting[id]; }
  }
  function noteTimeout(name, ms) {                   /* 走兜底：记一笔，联调测试断言这个数是 0 */
    window.__onboardTimeouts += 1;
    window.__onboardTimeoutLog.push({ name: name, waited: ms });
    if (window.console) { window.console.warn("画布 %d 秒没回 done，按播完算：%s", ms, name); }
  }
  /* 播一个动画。播过的（played 里有）不重播：带 instant 直接把画面摆成播完的样子 */
  function play(a) {
    if (S.prog.played.indexOf(a.key) >= 0) { instant(a); return Promise.resolve(); }
    var msg = Object.assign({ type: "bx-anim", id: ++animSeq }, a.msg);
    if (a.button) { msg.button = a.button; }        /* 首领气泡里的按钮文字（画布点一下会回 bx-anim-click） */
    return ready().then(function () {
      /* 气泡要先挂上“等用户点”再发出去：画布画完气泡就能被点，点了也不能漏 */
      var clicked = a.button ? waitBack(msg.id, "click", 0) : null;
      postToOffice(msg);
      /* 画布在线就等它真播完（快递猫送一趟箱十几秒）；不在线才 3 秒兜底 */
      var limit = animReady ? NS.ANIM_WAIT : NS.ANIM_TIMEOUT;
      return waitBack(msg.id, "done", limit).then(function (got) {
        if (!got) { noteTimeout(a.key, limit); }
        NS.markPlayed(a.key);
        /* 带按钮的气泡：画布在线就只等画布上那个按钮被点；不在线就在窗口里给同一个按钮，不把人卡死 */
        if (!animReady) { return a.button ? lineWindow(a) : null; }
        return clicked;
      });
    });
  }
  NS.play = play;
  function instant(a) {
    var msg = Object.assign({ type: "bx-anim", id: ++animSeq, instant: true }, a.msg);
    if (a.button) { msg.button = a.button; }
    postToOffice(msg);
  }
  NS.instant = instant;
  /* 画布还没上线时的兜底小窗口：同一句话、同一个按钮 */
  function lineWindow(a) {
    return new Promise(function (res) {
      var w = win({
        title: a.msg.slot === "leader" ? (S.leaderName || NS.defaultLeaderName()) : (S.memberName || NS.defaultMemberBase() + "A"),
        body: '<p class="lb">' + NS.esc(a.msg.text) + "</p>",
        buttons: [{ text: a.button, main: true, on: function (x) { x.close(); res(); } }]
      });
    });
  }

  /* ================= 像素窗口 ================= */
  function host() {
    var el = document.getElementById("bx-onboard");
    if (!el) {
      el = document.createElement("div");
      el.id = "bx-onboard";
      el.innerHTML = '<div class="pxw-mask"></div>';
      document.body.appendChild(el);
    }
    return el;
  }
  function closeWin() {
    var el = document.getElementById("bx-onboard");
    if (!el) { return; }
    el.classList.remove("on");
    Array.prototype.slice.call(el.querySelectorAll(".pxw")).forEach(function (x) { x.remove(); });
  }
  NS.closeWin = closeWin;
  /* o = {title, titleKey, body, foot, buttons:[{text, main, small, on(w, btn)}]}
     给了 titleKey 就按当前语言取标题；title 是中文默认，词典里没这个词时用它 */
  function win(o) {
    closeWin();
    var el = host();
    var box = document.createElement("div");
    box.className = "pxw";
    box.setAttribute("role", "dialog");
    var title = o.titleKey ? NS.tx(o.titleKey) : (o.title || "");
    box.innerHTML =
      '<div class="pxw-title">' + NS.esc(title) + "</div>" +
      '<div class="pxw-body">' + (o.body || "") + "</div>" +
      '<div class="pxw-foot"><span class="sp">' + (o.foot || "") + "</span>" +
      (o.buttons || []).map(function (b, i) {
        return '<button type="button" class="pxb' + (b.main ? " main" : "") + (b.small ? " small" : "") +
          '" data-b="' + i + '">' + NS.esc(b.text) + "</button>";
      }).join("") + "</div>";
    el.appendChild(box);
    el.classList.add("on");
    var w = {
      el: box,
      $: function (s) { return box.querySelector(s); },
      $$: function (s) { return Array.prototype.slice.call(box.querySelectorAll(s)); },
      close: closeWin,
      msg: function (sel, kind, html) {
        var m = box.querySelector(sel);
        if (!m) { return; }
        m.className = "msg " + kind;
        m.innerHTML = html;
      }
    };
    (o.buttons || []).forEach(function (b, i) {
      var btn = box.querySelector('[data-b="' + i + '"]');
      if (btn) { btn.onclick = function () { if (b.on) { b.on(w, btn); } }; }
    });
    return w;
  }
  NS.win = win;
  /* 左边选猫的一整块：一个大头像框（猫画大一点）+ 框两侧的深色 ◀ ▶ + 框里猫下面一行计数 */
  NS.catCard = function (no, extra) {
    var prev = NS.esc(NS.tx("common.prevCat")), next = NS.esc(NS.tx("common.nextCat"));
    return '<div class="pick">' +
      '<button type="button" class="arrow" data-d="-1" aria-label="' + prev + '" title="' + prev + '">◀</button>' +
      '<div class="avbox"><div class="lb head">' + NS.esc(NS.tx("common.pickLook")) + "</div>" +
      '<canvas class="av" width="190" height="190"></canvas>' +
      '<div class="cnt">' + NS.esc(NS.tx("common.pickCount", { n: no, total: NS.CAT_COUNT })) + "</div>" +
      (extra || "") + "</div>" +
      '<button type="button" class="arrow" data-d="1" aria-label="' + next + '" title="' + next + '">▶</button></div>';
  };
  NS.wireCat = function (w, spec, onPick) {
    function paint() {
      NS.drawCat(w.$("canvas"), spec.look);
      w.$(".cnt").textContent = NS.tx("common.pickCount", { n: spec.no, total: NS.CAT_COUNT });
    }
    w.$$(".arrow").forEach(function (b) {
      b.onclick = function () {
        var d = NS.num(b.getAttribute("data-d"), 1);
        spec.no = ((spec.no - 1 + d) % NS.CAT_COUNT + NS.CAT_COUNT) % NS.CAT_COUNT + 1;
        spec.look.cat = spec.no;
        paint();
        if (onPick) { onPick(spec); }
      };
    });
    paint();
  };
  /* 语言小开关：中文 / English。点了换语言，当前窗口立刻重画一遍 */
  NS.langSwitch = function () {
    var l = NS.lang();
    function b(label, v) {
      var on = l === v;
      return '<button type="button" class="ob-lang-btn' + (on ? " on" : "") + '" data-lang="' + v + '"' +
        ' style="border:1px solid #4a4a5a;background:#1b1b26;color:#c9c9d6;font:12px/1.6 inherit;' +
        'padding:2px 10px;cursor:pointer;' + (on ? "background:#2f2f3d;color:#fff;border-color:#7a7a90;" : "") + '">' +
        NS.esc(label) + "</button>";
    }
    return '<div class="ob-lang" style="margin-top:14px;display:flex;gap:8px;justify-content:flex-end">' +
      b(NS.tx("common.langZh"), "zh") + b(NS.tx("common.langEn"), "en") + "</div>";
  };
  NS.wireLang = function (w, root) {
    var box = root || (w && w.el) || document;
    box.querySelectorAll("[data-lang]").forEach(function (btn) {
      btn.onclick = function () { NS.setLang(btn.getAttribute("data-lang")); };
    });
  };
  /* 每一步都有 key（写进 /api/onboard/progress 的 step，也是 played 里动画的名字） */
  NS.sceneAnim = function (key, msg, button) { return { key: key, anim: { key: key, msg: msg, button: button } }; };
})();

/* ================= 这一份文件的文案（中文 / 英文） ================= */
window.BXOB.addTxt("common", {
    'copied': ['已复制', 'Copied'],
    'copyFail': ['复制失败，请手动选中', 'Copy failed, please select the text yourself'],
    'langEn': ['English', 'English'],
    'langZh': ['中文', 'Chinese'],
    'later': ['稍后再招', 'Maybe later'],
    'next': ['下一步', 'Next'],
    'nextCat': ['下一只', 'Next cat'],
    'pickCount': ['8 只里选 · {n}/{total}', 'Pick from 8 · {n}/{total}'],
    'pickLook': ['选样子', 'Pick a look'],
    'prevCat': ['上一只', 'Previous cat'],
});
