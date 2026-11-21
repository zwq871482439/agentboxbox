/* 页面共用的小工具：转义、时间、问接口、复制、客户端显示名。
   这些函数以前每个页面各拷一份，改一处要改八处；现在只有这一份，页面用 BXu.xxx 拿。 */
(function () {
  "use strict";
  var U = window.BXu = window.BXu || {};

  /* 往页面上插文字前先转义 */
  U.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  /* 几点几分 */
  U.hm = function (iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d)) return String(iso).slice(11, 16) || "—";
    return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
  };
  /* 什么时候：今天的只写时分，别的补上月-日 */
  U.when = function (iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d)) return String(iso).replace("T", " ").slice(0, 16);
    var t = new Date();
    var same = d.getFullYear() === t.getFullYear() && d.getMonth() === t.getMonth() && d.getDate() === t.getDate();
    var md = ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2);
    return (same ? "" : md + " ") + U.hm(iso);
  };
  /* 完整日期时间：效率面板那种要看出是哪天 */
  U.whenFull = function (iso) {
    if (!iso) return "";
    return String(iso).replace("T", " ").slice(0, 16);
  };
  /* 问接口：回 {ok, data, status}，页面自己看 ok */
  U.api = function (path, opt) {
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        return { ok: r.ok, data: d, status: r.status };
      });
    }).catch(function (e) {
      return { ok: false, error: String(e) };
    });
  };
  /* 接口的原始返回：页面各处习惯直接用返回体里的字段，用这个 */
  U.apiRaw = function (path, opt) {
    return U.api(path, opt).then(function (r) {
      if (r.error) { throw r.error; }
      return r.data;
    });
  };
  /* 复制到剪贴板：按钮上闪一下「复制好了」 */
  U.copy = function (text, btn, doneWord, failWord) {
    var done = function () {
      var old = btn.textContent;
      btn.textContent = doneWord;
      setTimeout(function () { btn.textContent = old; }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(); });
    } else { fallback(); }
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); done(); } catch (e) { btn.textContent = failWord; }
      document.body.removeChild(ta);
    }
  };
  /* 数字有两种：toNum 是取值（转成数字），fmtNum 是给人看的（加千分位） */
  U.toNum = function (v) { var n = Number(v); return isFinite(n) ? n : 0; };
  U.fmtNum = function (n, dash) {
    if (n == null) return dash == null ? "—" : dash;
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  };
  /* 客户端显示名：connectors.json 里那几家都在这儿，页面不再各抄一张表 */
  U.CLIENT_LABEL = {
    cursor: "Cursor", "claude-code": "Claude Code", codex: "Codex", pi: "Pi",
    "kimi-code": "Kimi Code", "minimax-code": "MiniMax Code", "grok-bot": "Grok Bot",
    workbuddy: "WorkBuddy", zcode: "ZCode"
  };
  var WORDS = {
    zh: { other: "其他", otherDirect: "其他（直连）" },
    en: { other: "Other", otherDirect: "Other (direct)" }
  };
  /* 页面把自己的词传进来：没登记客户端、别人接的直连，各页说法不一样 */
  U.clientLabel = function (c, w) {
    w = w || {};
    var d = WORDS[(window.BXi18n && window.BXi18n.lang()) === "en" ? "en" : "zh"];
    if (!c) return w.none || "";
    if (c === "other") return w.other || d.other;
    if (c === "other-direct") return w.otherDirect || d.otherDirect;
    return U.CLIENT_LABEL[c] || String(c);
  };
})();
