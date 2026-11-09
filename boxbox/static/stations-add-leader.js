/* 工位页「再加一个首领」：填名字，登记成首领，再复制和「叫醒首领」同一段话。 */
(function () {
  function T(k, v) { return window.BXi18n ? window.BXi18n.t(k, v) : k; }
  function $(s) { return document.querySelector(s); }
  var btn = $("#btn-add-leader");
  if (!btn) { return; }
  btn.addEventListener("click", function () {
    var BX = window.BXStations || {};
    fetch("/api/stations_def", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (doc) {
      var taken = {};
      ((doc && doc.stations) || []).forEach(function (s) { if (s && s.id) { taken[s.id] = true; } });
      var name = window.prompt(T("st.addLeaderAsk"), "");
      if (name == null) { return; }
      name = String(name).trim().slice(0, 24);
      if (!name) { return; }
      if (taken[name]) {
        if (BX.pageMsg) { BX.pageMsg(T("st.addLeaderExists")); }
        return;
      }
      var lg = (window.BXi18n && window.BXi18n.lang) ? window.BXi18n.lang() : "zh";
      var body = { id: name, role: "leader", client: "", runner: "manual", enabled: true, lang: lg, add_leader: true };
      fetch("/api/stations", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, data: d }; });
      }).then(function (r) {
        if (!r.ok || (r.data && r.data.ok === false)) {
          var why = (r.data && (r.data.text || (r.data.errors || []).join(" "))) || "";
          if (BX.pageMsg) { BX.pageMsg(T("st.addLeaderFail", { why: why })); }
          return;
        }
        var again = BX.load ? BX.load() : null;
        return Promise.resolve(again).then(function () { if (BX.summon) { BX.summon(name); } });
      });
    }).catch(function (e) {
      if (BX.pageMsg) { BX.pageMsg(T("st.addLeaderFail", { why: String(e) })); }
    });
  });
})();
