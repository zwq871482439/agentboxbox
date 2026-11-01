/* 各页共用的顶栏（各页宽度、内容保持一致）。
   用法：页面里放 <header id="bx-top"></header>，再 <script src="/static/topbar.js"></script>。
   - 导航只有 看板 / 工位 / 设置（自检收在设置页里）；当前页高亮。
   - 右侧两个核心指标：工作中（在跑的卡）/ 成功率（近 7 天收尾的卡里完成的占比），
     再加一个核心小圆点：绿 = 核心在跑，红 = 连不上。点圆点 = 连接状态（首页开面板，其它页去设置页的自检）。
   - 顶栏不数决策数、没有横幅；提醒统一读 /api/meta 的 alerts，在办公室顶部提示条里看。
   - 子页面左上角一个悬浮「← 办公室」。
   - 页面想拿到同一份数据（省一次轮询）：监听 window 上的 "bx-top" 事件，detail = {alive, meta}。
   语言：顶栏自己的文案在本文件里两张表（zh / en），跟 i18n.js 共用 bx-lang 这一个键；
   页面还没引 i18n.js 时（看板 / 工位 / 自检页）就用本地的判断，行为一样。 */
(function () {
  var HOME = location.pathname === "/";
  var TOP_ZH = {
    brand: "猫猫盒子",
    navBoard: "看板",
    navStations: "工位",
    navSettings: "设置",
    working: "工作中",
    success: "成功率",
    selfcheck: "自检",
    backOffice: "← 办公室",
    workingTitle: "正在干活的任务卡",
    successTitle: "近 7 天真跑完的任务卡里，完成的占多少（完成 ÷ 完成 + 真跑挂的；没开工 / 中断 / 撤掉的不算）",
    selfcheckTitle: "自检：看看盒子哪里不对",
    down: "猫猫盒子没在跑：双击猫猫盒子的 exe（agentboxbox_版本号.exe） 或运行 python -m boxbox serve",
    doneTitle: "近 7 天收尾的任务卡：完成 {d} 张，失败 {f} 张",
    brandTitle: "agentboxbox",
    alive: "猫猫盒子在跑 · 版本 {v}（更新于 {t}）。点开看自检",
  };
  var TOP_EN = {
    brand: "agentboxbox",
    navBoard: "Board",
    navStations: "Stations",
    navSettings: "Settings",
    working: "Working",
    success: "Success",
    selfcheck: "Check",
    backOffice: "← Office",
    workingTitle: "Cards being worked on",
    successTitle: "Share of finished cards in the last 7 days (done ÷ done + really failed; not started, interrupted and cancelled do not count)",
    selfcheckTitle: "Check whether the box is fine",
    down: "agentboxbox is not running: double-click the exe (agentboxbox_version.exe) or run python -m boxbox serve",
    doneTitle: "Cards finished in the last 7 days: {d} done, {f} failed",
    brandTitle: "agentboxbox",
    alive: "agentboxbox is running · version {v} (updated {t}). Click to see the health check",
  };
  function curLang() {
    if (window.BXi18n) { return window.BXi18n.lang(); }
    try {
      var m = localStorage.getItem("bx-lang");
      if (m === "zh" || m === "en") { return m; }
    } catch (e) { }
    return /^zh/i.test(navigator.language || "") ? "zh" : "en";
  }
  function T() { return curLang() === "en" ? TOP_EN : TOP_ZH; }
  var css = [
    "#bx-top{flex:none;border-top:3px solid #e5484d;display:flex;align-items:center;gap:8px 22px;flex-wrap:wrap;"
    + "padding:9px 16px 8px;border-bottom:1px solid #2a2a37;background:#15151e;"
    + "font-family:'Microsoft YaHei','PingFang SC',system-ui,sans-serif;font-size:13.5px;color:#e5e7eb;position:relative;z-index:20}",
    "#bx-top.down{border-top-color:#ff4d4f}",
    "#bx-top .bx-brand{font-weight:700;font-size:24px;color:#fff;text-decoration:none;line-height:1;letter-spacing:.5px}",
    "#bx-top .bx-nav{display:flex;gap:18px}",
    "#bx-top .bx-nav a{color:#9ca3af;text-decoration:none}",
    "#bx-top .bx-nav a:hover{color:#fff;text-decoration:underline;text-underline-offset:4px}",
    "#bx-top .bx-nav a.cur{color:#fff;font-weight:600}",
    "#bx-top .bx-end{margin-left:auto;display:flex;gap:18px;align-items:center;font-size:12.5px;color:#9ca3af}",
    "#bx-top .bx-k b{color:#e5e7eb;font-weight:600;margin-left:5px;font-family:Consolas,'Cascadia Mono',monospace}",
    "#bx-top .bx-core{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:6px;padding:2px 6px;border-radius:10px}",
    "#bx-top .bx-core:hover{background:#23232f}",
    "#bx-top .bx-dot{width:9px;height:9px;border-radius:50%;background:#3ddc84;box-shadow:0 0 0 2px rgba(61,220,132,.18)}",
    "#bx-top.down .bx-dot{background:#ff4d4f;box-shadow:0 0 0 2px rgba(255,77,79,.2)}",
    "#bx-back{display:inline-block;margin:10px 0 0 12px;background:rgba(21,21,30,.85);color:#e5e7eb;"
    + "border:1px solid #2f2f3d;border-radius:16px;padding:5px 12px;font:13px 'Microsoft YaHei',system-ui,sans-serif;text-decoration:none}",
    "#bx-back:hover{border-color:#e5484d;color:#fff}",
    "[hidden]{display:none!important}"
  ].join("\n");
  var st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  var path = location.pathname;
  var cur = path === "/board" ? "board"
    : (path === "/stations" || path === "/onboard") ? "stations"
    : (path === "/settings" || path === "/doctor") ? "settings" : "";
  var top = document.getElementById("bx-top");
  if (!top) { top = document.createElement("header"); top.id = "bx-top"; document.body.insertBefore(top, document.body.firstChild); }

  /* 品牌名：中文界面「猫猫盒子」，英文界面 agentboxbox */
  function brandHtml(l) {
    var t = l === "en" ? TOP_EN : TOP_ZH;
    return '<a class="bx-brand" href="/" title="' + t.brandTitle + '">' + t.brand + '</a>';
  }
  function renderTop() {
    var l = curLang(), t = T();
    top.innerHTML =
      brandHtml(l) +
      '<nav class="bx-nav">' +
      '<a href="/board"' + (cur === "board" ? ' class="cur"' : "") + '>' + t.navBoard + '</a>' +
      '<a href="/stations"' + (cur === "stations" ? ' class="cur"' : "") + '>' + t.navStations + '</a>' +
      '<a href="/settings"' + (cur === "settings" ? ' class="cur"' : "") + '>' + t.navSettings + '</a></nav>' +
      '<div class="bx-end">' +
      '<span class="bx-k" id="bx-k-run" title="' + t.workingTitle + '">' + t.working + "<b>–</b></span>" +
      '<span class="bx-k" id="bx-k-ok" title="' + t.successTitle + '">' + t.success + "<b>–</b></span>" +
      '<button type="button" class="bx-core" id="bx-core" title="' + t.selfcheckTitle + '">' +
      '<span class="bx-dot"></span>' + t.selfcheck + '</button>' +
      "</div>";
    if (!HOME && !document.getElementById("bx-back")) {
      var back = document.createElement("a"); back.id = "bx-back"; back.href = "/";
      back.textContent = t.backOffice;
      /* 页面留了 #backhome 就放进页头行；没留就在顶栏下面单占一行。浮在内容上会压住页面标题 */
      var slot = document.getElementById("backhome");
      if (slot) { slot.appendChild(back); back.classList.add("inhead"); }
      else { top.parentNode.insertBefore(back, top.nextSibling); }
    } else if (!HOME) {
      document.getElementById("bx-back").textContent = t.backOffice;
    }
    var core = document.getElementById("bx-core");
    if (core) {
      core.onclick = function () {
        var ev = new CustomEvent("bx-core-click", { cancelable: true });
        if (window.dispatchEvent(ev)) { location.href = "/doctor"; }   /* 首页会 preventDefault 并打开连接状态面板 */
      };
    }
  }
  renderTop();

  function get(u) { return fetch(u, { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); }
  function setK(id, v) { var el = document.getElementById(id); if (el) { el.querySelector("b").textContent = v; } }

  function aliveTitle(l, meta, stamp) {
    var t = l === "en" ? TOP_EN : TOP_ZH;
    return t.alive.replace("{v}", meta.app_version || "?").replace("{t}", stamp);
  }
  function render(meta) {
    var alive = !!meta;
    var l = curLang(), t = T();
    top.classList.toggle("down", !alive);
    var stamp = new Date().toTimeString().slice(0, 5);
    var up = alive ? aliveTitle(l, meta, stamp)
      : t.down;
    var core = document.getElementById("bx-core");
    if (core) { core.title = up; }
    var ver = document.getElementById("bx-app-version");
    if (ver && alive) { ver.textContent = meta.app_version || "?"; }
    if (!alive) { setK("bx-k-run", "–"); setK("bx-k-ok", "–"); return; }
    var s = meta.success_7d || {};
    setK("bx-k-run", String(meta.running || 0));
    setK("bx-k-ok", s.rate == null ? "—" : Math.round(s.rate * 100) + "%");
    var k = document.getElementById("bx-k-ok");
    if (k) { k.title = t.doneTitle.replace("{d}", s.done || 0).replace("{f}", s.failed || 0); }
  }

  function tick() {
    get("/api/meta").then(function (meta) {
      render(meta);
      window.dispatchEvent(new CustomEvent("bx-top", { detail: { alive: !!meta, meta: meta } }));
    });
  }
  window.BXTop = { refresh: tick };
  /* 语言换了：顶栏重画一遍（指标数字留着，只换文案） */
  addEventListener("bx-lang-changed", function () { renderTop(); tick(); });
  addEventListener("storage", function (e) { if (e.key === "bx-lang") { renderTop(); tick(); } });
  tick(); setInterval(tick, 5000);
})();
