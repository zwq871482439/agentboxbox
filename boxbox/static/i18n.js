/* 中英双语：语言怎么定、词条怎么查、页面上的字怎么换。
   语言：?lang=zh|en 临时覆盖 → localStorage 里的 bx-lang（跟办公室画布共用这一个键）→ 都没有就按系统语言定并记住。
   词条：词典按页面分文件注册（i18n-home.js 等），zh / en 两份放在一起；
   上岗那几个文件各有自己的一份文案表（onboard-common.js 里的 NS.addTxt）。
   英文缺了就回落中文并 warn 一次 —— 漏翻的句子会露出来，不会变成一串 key。
   换语言：setLang() 写 bx-lang、告诉办公室画布（postMessage bx-lang）、把页面上带 data-i18n 的元素换掉，
   再抛一个 bx-lang-changed 事件，各页自己重画（顶栏、上岗窗口那些是 JS 生成的，得自己重画）。 */
(function () {
  "use strict";
  var DICT = { zh: {}, en: {} };
  var warned = {};
  var CUR = null;       /* 当前语言定下来就不再看 localStorage（切换时自己改） */

  function isObj(v) { return v && typeof v === "object" && !Array.isArray(v); }

  /* 注册词典：zh / en 两包，深合并（同一段前缀可以分几个文件注册） */
  function merge(dst, src) {
    Object.keys(src || {}).forEach(function (k) {
      if (isObj(src[k]) && isObj(dst[k])) { merge(dst[k], src[k]); } else { dst[k] = src[k]; }
    });
  }
  function register(pack) {
    if (!pack) { return; }
    merge(DICT.zh, pack.zh || {});
    merge(DICT.en, pack.en || {});
  }

  /* 查词条：键是点号路径（home.panel.feed），一层层往下找 */
  function lookup(dict, key) {
    var parts = String(key).split(".");
    var v = dict;
    for (var i = 0; i < parts.length; i++) {
      if (!isObj(v)) { return undefined; }
      v = v[parts[i]];
    }
    return v;
  }

  function queryLang() {
    var q = new URLSearchParams(location.search).get("lang");
    return q === "zh" || q === "en" ? q : "";
  }

  /* 当前语言：URL 上的临时覆盖优先，其次记住的，最后按系统语言定（第一次定下来就写进 bx-lang） */
  function cookieLang() {
    try {
      var m = ("; " + (document.cookie || "")).match(/;\s*bx-lang=(zh|en)\b/);
      return m ? m[1] : "";
    } catch (e) { return ""; }
  }
  function lang() {
    if (CUR) { return CUR; }
    var q = queryLang();
    if (q) { CUR = q; return CUR; }
    var c = cookieLang();              // 核心那边定的语言（设置里的 ui_lang）：跟页面一起发过来的
    if (c) { CUR = c; return CUR; }
    try {
      var m = localStorage.getItem("bx-lang");
      if (m === "zh" || m === "en") { CUR = m; return CUR; }
    } catch (e) { }
    var l = /^zh/i.test(navigator.language || navigator.userLanguage || "") ? "zh" : "en";
    try { localStorage.setItem("bx-lang", l); } catch (e) { }
    CUR = l;
    return l;
  }

  /* 用户明确选了语言：URL 上的 ?lang= 就不再生效（不然选了也切不动） */
  function dropQueryLang() {
    try {
      if (!queryLang()) { return; }
      var u = new URL(location.href);
      u.searchParams.delete("lang");
      history.replaceState(null, "", u.pathname + u.search + u.hash);
    } catch (e) { }
  }

  function setLang(l) {
    l = l === "en" ? "en" : "zh";
    CUR = l;
    try { localStorage.setItem("bx-lang", l); } catch (e) { }
    try { document.cookie = "bx-lang=" + l + "; path=/; SameSite=Lax"; } catch (e) { }
    dropQueryLang();
    /* 后端也要知道：核心生成的文字（看板 / 提醒 / 托盘 / 首领的话）跟着这个语言走 */
    try {
      fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ui_lang: l }) }).catch(function () { });
    } catch (e) { }
    document.documentElement.lang = l === "en" ? "en" : "zh-CN";
    var f = document.getElementById("office-frame");
    if (f && f.contentWindow) {
      try { f.contentWindow.postMessage({ type: "bx-lang", lang: l }, "*"); } catch (e) { }
    }
    apply(document);
    try { window.dispatchEvent(new CustomEvent("bx-lang-changed", { detail: l })); } catch (e) { }
    return l;
  }

  /* 取词条：当前语言没有就回落中文；vars 里的 {名} 会被替换掉 */
  function t(key, vars) {
    var l = lang();
    var v = lookup(DICT[l], key);
    if (typeof v !== "string") {
      v = lookup(DICT.zh, key);
      if (typeof v !== "string") {
        if (!warned[key]) { warned[key] = true; console.warn("i18n: 没有词条 " + key); }
        return key;
      }
      if (!warned[key]) { warned[key] = true; console.warn("i18n: 英文缺 " + key + "，先显示中文"); }
    }
    if (vars) {
      Object.keys(vars).forEach(function (k) { v = v.split("{" + k + "}").join(vars[k]); });
    }
    return v;
  }

  /* 把页面上带 data-i18n 的元素换成当前语言：正文、title、placeholder */
  function apply(root) {
    var r = root || document;
    var l = lang();
    document.documentElement.lang = l === "en" ? "en" : "zh-CN";
    r.querySelectorAll("[data-i18n]").forEach(function (el) { el.textContent = t(el.getAttribute("data-i18n")); });
    r.querySelectorAll("[data-i18n-title]").forEach(function (el) { el.setAttribute("title", t(el.getAttribute("data-i18n-title"))); });
    r.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
      el.setAttribute("placeholder", t(el.getAttribute("data-i18n-placeholder")));
    });
    if (isObj(DICT[l].doc) && typeof DICT[l].doc.title === "string") { document.title = t("doc.title"); }
  }

  /* 词典里所有的词条（点号路径）：自检用 —— 中文有的英文也得有 */
  function keys(l) {
    var out = [];
    (function walk(o, pre) {
      Object.keys(o).forEach(function (k) {
        var v = o[k];
        if (isObj(v)) { walk(v, pre ? pre + "." + k : k); } else { out.push(pre ? pre + "." + k : k); }
      });
    })(DICT[l || lang()], "");
    return out;
  }

  /* 页面上的接口请求都带上当前语言：核心生成的文字跟着页面的语言走 */
  function withLang(u) {
    var s = String(u || "");
    if (s.indexOf("/api/") !== 0) { return s; }
    var l = lang();
    return s + (s.indexOf("?") >= 0 ? "&" : "?") + "lang=" + encodeURIComponent(l);
  }

  var rawFetch = window.fetch ? window.fetch.bind(window) : null;
  if (rawFetch) {
    window.fetch = function (input, init) {
      try {
        if (typeof input === "string") { input = withLang(input); }
      } catch (e) { }
      return rawFetch(input, init);
    };
  }

  window.BXi18n = { lang: lang, setLang: setLang, t: t, apply: apply, register: register, keys: keys };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { apply(document); });
  } else {
    apply(document);
  }
})();
