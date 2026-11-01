/* 工位页脚本 · 查看详情抽屉（只读）。依赖 stations.js（先加载，公共工具都在 window.BXST 里）。 */
(function () {
  var NS = window.BXST;
  var $ = NS.$, esc = NS.esc, api = NS.api, fmtDT = NS.fmtDT;
  var clientLabel = NS.clientLabel;
  var workNo = NS.workNo;
  var quotaModeLabel = NS.quotaModeLabel, quotaAdapterLabel = NS.quotaAdapterLabel;
  function T(k, v) { return window.BXi18n ? window.BXi18n.t(k, v) : k; }
  function kvRow(k, v) { return "<tr><th>" + esc(k) + "</th><td>" + (v == null || v === "" ? "—" : v) + "</td></tr>"; }

  function drawerHTML(d) {
    var st = d.station || {};
    var pi = st.pi || {};
    var q = st.quota || {};
    var b = d.board || {};
    var isPi = st.client === "pi" || st.runner === "once";
    var rows = "";
    rows += kvRow(T("st.kv.role"), esc(st.role === "leader" ? T("st.badgeTopLeader") : T("st.roleMemberShort")));
    rows += kvRow(T("st.kv.station"), esc(st.id) + T("st.kv.slot", { slot: esc(st.slot || "-") }));
    if (st.role === "leader") {
      /* 首领用的是用户自己常用的那家 AI 软件：连上了才点名是哪一家 */
      var shownClient = b.client || "";
      rows += kvRow(T("st.kv.app"), esc(shownClient ? clientLabel(shownClient) : T("st.yourApp")));
    } else {
      rows += kvRow(T("st.kv.mode"), esc(NS.modeText(st)));
    }
    /* 复制出来的猫：目录是从原目录复制的 git worktree，分支 bx/<工位名> */
    var cwdV = st.cwd ? esc(st.cwd) : T("st.cwdNone");
    if (st.cwd && st.cwd_from) {
      cwdV += T("st.cwdWorktree", { from: esc(st.cwd_from), id: esc(st.id) });
    }
    rows += kvRow(T("st.kv.cwd"), cwdV);
    rows += kvRow(T("st.kv.enabled"), st.enabled === false ? T("st.disabled") : T("st.enabledNow"));
    var cfg = '<div class="dsec"><h3>' + esc(T("st.kv.config")) + '</h3><table class="kv">' + rows + "</table></div>";
    if (isPi) {
      var prows = "";
      prows += kvRow(T("st.kv.provider"), esc(d.provider || "—"));
      prows += kvRow(T("st.kv.model"), esc(pi.model || "—"));
      prows += kvRow(T("st.kv.base"), esc(pi.base_url || "—"));
      prows += kvRow(T("st.kv.api"), esc(pi.api || "—"));
      var keyv = (b.has_key ? T("st.keyStored") : T("st.keyNone"));
      prows += kvRow(T("st.kv.key"), keyv);
      prows += kvRow(T("st.kv.ctx"), pi.context_window ? esc(pi.context_window) + " token" : "—");
      prows += kvRow(T("st.kv.max"), pi.max_tokens ? esc(pi.max_tokens) + " token" : "—");
      var ql = quotaModeLabel(q.mode || "off");
      if (q.mode === "interval" && q.interval_min) { ql += T("st.quotaEvery", { n: q.interval_min }); }
      if (q.adapter && q.mode !== "off") { ql += " · " + quotaAdapterLabel(q.adapter); }
      prows += kvRow(T("st.kv.quota"), esc(ql));
      cfg += '<div class="dsec"><h3>' + esc(T("st.kv.pi")) + '</h3><table class="kv">' + prows + "</table></div>";
    }
    var conn = T("st.connNever");
    if (d.picheck) {
      var word = d.picheck.state === "ok" ? T("st.connOk")
        : d.picheck.state === "limited" ? T("st.connLimited") : T("st.connFail", { state: d.picheck.state });
      conn = word + ": " + esc(d.picheck.text || "") +
        "<br>" + T("st.connChecked", { t: esc(fmtDT(d.picheck.checked_at)) });
    }
    cfg += '<div class="dsec"><h3>' + esc(T("st.kv.conn")) + '</h3><table class="kv">' +
      kvRow(T("st.kv.apiConn"), conn) + "</table></div>";
    var t = d.today || {};
    var rate = t.rate == null ? "—" : Math.round(t.rate * 100) + "%";
    cfg += '<div class="dsec"><h3>' + esc(T("st.kv.today")) + '</h3><table class="kv">' +
      kvRow(T("st.kv.assigned"), esc(t.assigned || 0) + T("st.times")) +
      kvRow(T("st.kv.doneFailed"), esc((t.done || 0) + " / " + (t.failed || 0))) +
      kvRow(T("st.kv.rate"), esc(rate)) + "</table></div>";
    var evs = (d.events || []).map(function (e) {
      return '<li><span class="ts">' + esc(fmtDT(e.ts)) + "</span>" + esc(e.text || e.kind) + "</li>";
    }).join("");
    cfg += '<div class="dsec"><h3>' + esc(T("st.kv.events")) + '</h3>' +
      (evs ? '<ul class="evs">' + evs + "</ul>" : '<p class="hint">' + esc(T("st.noEvents")) + "</p>") + "</div>";
    var qb = T("st.quotaNever");
    if (d.quota && d.quota.ok) {
      var parts = ["h5", "week", "month"].map(function (k) {
        var w = (d.quota.windows || {})[k];
        if (!w) { return ""; }
        var pct = Math.min(100, Math.max(0, Math.round(w.pct)));
        var lab = esc(T("st.quotaWindow." + k));
        if (w.label) { lab += esc(T("st.quotaLabelExtra", { label: w.label })); }
        return '<div class="qrow"><span class="ql">' + lab + '</span>' +
          '<span class="qbar' + (pct >= 90 ? " red" : "") + '"><i style="width:' + pct + '%"></i></span>' +
          '<span class="qp">' + esc(T("st.quotaUsed", { n: pct })) +
          (w.reset ? " · " + esc(T("st.quotaReset", { t: fmtDT(w.reset) })) : "") + "</span></div>";
      }).join("");
      qb = parts || T("st.quotaUnknownWindow");
    } else if (d.quota && d.quota.ok === false) {
      qb = T("st.quotaFail", { kind: d.quota.error_kind || T("st.quotaUnknown"), why: d.quota.error || "" });
    }
    if (d.quota_peers && d.quota_peers.length) {           /* 同服务商的几只猫共用一份额度 */
      qb += '<p class="hint">' + esc(T("st.quotaPeers", { names: d.quota_peers.join(", ") })) + "</p>";
    }
    cfg += '<div class="dsec"><h3>' + esc(T("st.kv.quotaLeft")) + "</h3>" + qb + "</div>";
    return cfg;
  }

  function openDrawer(id) {
    $("#drawer").hidden = false;
    $("#drawerBack").hidden = false;
    $("#d-name").textContent = id;
    $("#d-sub").textContent = T("st.drawerLoading");
    $("#d-body").innerHTML = '<div class="dsec"><p class="hint">' + esc(T("st.loading")) + "</p></div>";
    var defs = NS.getDefs();
    var lead = defs.some(function (s) { return s.role === "leader" && s.id === id; });
    var idx = 0;
    defs.filter(function (s) { return s.role !== "leader"; }).forEach(function (s, i) { if (s.id === id) { idx = i; } });
    NS.drawAvatar($("#d-cat"), defs.filter(function (s) { return s.id === id; })[0] || { role: lead ? "leader" : "member", id: id }, idx);
    api("/api/stations/detail?id=" + encodeURIComponent(id)).then(function (d) {
      if (!d || !d.ok) { $("#d-sub").textContent = (d && d.text) || T("st.noDetail"); return; }
      var b = d.board || {};
      var st = d.station || {};
      var who = st.role === "leader" ? T("st.badgeTopLeader") : T("st.badgeTopMember", { slot: st.slot || "-" });
      $("#d-sub").textContent = T("st.workNo", { n: workNo(st) }) + " · " + who +
        " · " + T("st.state") + (b.word || "-") + " · " + T("st.onDuty", { x: b.first_seen ? fmtDT(b.first_seen) : T("st.neverOnDuty") });
      $("#d-body").innerHTML = drawerHTML(d);
    }).catch(function (e) {
      $("#d-sub").textContent = T("st.noDetail") + ": " + String(e);
    });
  }
  function closeDrawer() { $("#drawer").hidden = true; $("#drawerBack").hidden = true; }
  $("#d-close").onclick = closeDrawer;
  $("#drawerBack").onclick = closeDrawer;
  $("#d-edit").onclick = function () { closeDrawer(); NS.openForm($("#d-name").textContent); };

  NS.openDrawer = openDrawer;
})();
