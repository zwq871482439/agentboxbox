/* 看板「效率」：近 7 天按猫、按卡的用时和用量。数字来自 /api/efficiency，这里只画。 */
(function () {
  "use strict";

  function T(k, v) { return window.BXi18n ? window.BXi18n.t(k, v) : k; }
  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function num(n) {
    if (n == null) { return T("bd.eff.dash"); }
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  function dur(sec) {
    if (sec == null) { return T("bd.eff.dash"); }
    var whole = Math.round(Number(sec) || 0);
    if (whole < 60) { return T("bd.eff.sec", { n: whole }); }
    var m = Math.floor(whole / 60);
    var s = whole % 60;
    if (whole < 3600) {
      return s ? T("bd.eff.minSec", { n: m, s: s }) : T("bd.eff.min", { n: m });
    }
    var h = Math.floor(whole / 3600);
    return T("bd.eff.hour", { n: h, m: Math.round((whole % 3600) / 60) });
  }
  function hit(n) {
    return n == null ? T("bd.eff.dash") : String(n) + "%";
  }
  function cost(row) {
    if (row && row.price === "plan") { return T("bd.eff.plan"); }
    if (!row || row.price !== "money" || row.cost_est == null) { return T("bd.cost.none"); }
    return "$" + Number(row.cost_est).toFixed(2);
  }
  function when(iso) {
    if (!iso) { return T("bd.eff.dash"); }
    return String(iso).replace("T", " ").slice(0, 16);
  }

  function summary(d) {
    var bits = [];
    var busy = d.busy || {};
    if (busy.avg == null) { bits.push(T("bd.eff.busyNone")); }
    else { bits.push(T("bd.eff.busy", { avg: busy.avg, cats: busy.cats })); }
    if (d.accept_wait_s == null) { bits.push(T("bd.eff.waitNone")); }
    else { bits.push(T("bd.eff.wait", { t: dur(d.accept_wait_s) })); }
    var s = d.split || {};
    if (s.model_s == null) { bits.push(T("bd.eff.splitNone")); }
    else if (s.model_pct == null) { bits.push(T("bd.eff.split", { m: dur(s.model_s), c: dur(s.cmd_s) })); }
    else { bits.push(T("bd.eff.splitPct", { m: dur(s.model_s), mp: s.model_pct, c: dur(s.cmd_s), cp: s.cmd_pct })); }
    if (s.turns_before_edit != null) {
      var line = T("bd.eff.beforeEdit", { n: s.turns_before_edit });
      if (s.unedited) { line = line + " " + T("bd.eff.beforeEditNote", { n: s.unedited }); }
      bits.push(line);
    }
    if (s.model_s != null || s.test_runs) { bits.push(T("bd.eff.tests", { n: s.test_runs || 0 })); }
    if (s.longest_s != null) {
      bits.push(T("bd.eff.longest", { t: dur(s.longest_s), cmd: s.longest_cmd || T("bd.eff.dash") }));
    }
    return '<div class="eff-sum">' + bits.map(function (b) { return "<span>" + esc(b) + "</span>"; }).join("") + "</div>";
  }

  function head(keys) {
    return "<tr>" + keys.map(function (k) {
      var cls = (k === "cat" || k === "card") ? "" : ' class="num"';
      return "<th" + cls + ">" + esc(T("bd.eff.h." + k)) + "</th>";
    }).join("") + "</tr>";
  }
  function td(html, cls) {
    return "<td" + (cls ? ' class="' + cls + '"' : "") + ">" + html + "</td>";
  }
  function rowHtml(row, cards) {
    var who = cards
      ? td(esc(row.title || row.task_id) + '<span class="eff-id">' + esc(row.task_id) + "</span>")
      : td(esc(row.station));
    var extra = cards ? td(esc(row.station)) : "";
    var tail = cards ? "" : td(esc(row.model_s == null ? T("bd.eff.dash") : dur(row.model_s)), "num") +
      td(esc(row.cmd_s == null ? T("bd.eff.dash") : dur(row.cmd_s)), "num");
    var id = cards ? ' data-id="' + esc(row.task_id) + '"' : "";
    return "<tr" + id + ">" + who + extra +
      td(esc(dur(row.seconds)), "num") +
      td(esc(num(row.turns)), "num") +
      td(esc(num(row.tools)), "num") +
      td(esc(num(row.tok_in)), "num") +
      td(esc(num(row.tok_out)), "num") +
      td(esc(num(row.tok_cr)), "num") +
      td(esc(hit(row.hit)), "num") +
      td(esc(cost(row)), "num") + tail + "</tr>";
  }
  function table(rows, cards) {
    var keys = cards
      ? ["card", "cat", "time", "turns", "tools", "inn", "out", "cr", "hit", "cost"]
      : ["cat", "time", "turns", "tools", "inn", "out", "cr", "hit", "cost", "model", "cmd"];
    var body = rows.length
      ? rows.map(function (r) { return rowHtml(r, cards); }).join("")
      : '<tr><td class="empty" colspan="' + keys.length + '">' + esc(T("bd.eff.empty")) + "</td></tr>";
    return '<div class="scroll"><table class="tbl"><thead>' + head(keys) + "</thead><tbody>" + body + "</tbody></table></div>";
  }

  function render(d) {
    var box = $("effBody");
    if (!box) { return; }
    if (!d) {
      box.innerHTML = '<div class="empty">' + esc(T("bd.eff.loading")) + "</div>";
      return;
    }
    var cats = d.cats || [];
    var cards = d.cards || [];
    var busy = d.busy || {};
    var quiet = !cats.length && !cards.length && d.accept_wait_s == null && busy.avg == null &&
      !(d.split && d.split.model_s != null);
    if (quiet) {
      box.innerHTML = '<div class="empty">' + esc(T("bd.eff.empty")) + "</div>";
      return;
    }
    box.innerHTML = summary(d) +
      '<div class="eff-sec"><h3>' + esc(T("bd.eff.cats")) + "</h3>" + table(cats, false) + "</div>" +
      '<div class="eff-sec"><h3>' + esc(T("bd.eff.pricey")) +
      ' <span class="sub">' + esc(T("bd.eff.priceyHint")) + "</span></h3>" + table(cards, true) +
      '<p class="hint">' + esc(T("bd.eff.hitHint")) + " · " + esc(T("bd.eff.since")) + " " +
      esc(when(d.since)) + "</p></div>";
    Array.prototype.forEach.call(box.querySelectorAll("tr[data-id]"), function (el) {
      el.onclick = function () {
        if (window.BXBoard && window.BXBoard.openTask) { window.BXBoard.openTask(el.getAttribute("data-id")); }
      };
    });
  }

  window.BXEff = { render: render };
})();
