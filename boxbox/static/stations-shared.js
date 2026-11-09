/* 首领工牌上补一句「两个对话在用同一个首领」。
   工牌是 stations.js 画的，画完再补，免得那个文件再长就超行数。
   按钮点的就是页上已经有的「再加一个首领」。 */
(function () {
  function T(k) { return window.BXi18n ? window.BXi18n.t(k) : k; }
  var meta = { alerts: [] };

  function sharedFor(id) {
    var list = meta.alerts || [];
    for (var i = 0; i < list.length; i++) {
      var a = list[i];
      if (a && a.kind === "leader_shared" && a.station === id) { return a; }
    }
    return null;
  }

  function paint() {
    var root = document.querySelector("#badges");
    if (!root) { return; }
    Array.prototype.forEach.call(root.querySelectorAll(".badge.leader"), function (badge) {
      var old = badge.querySelector(".shared-note");
      if (old) { old.remove(); }
      var hit = sharedFor(badge.getAttribute("data-id"));
      if (!hit) { return; }
      var note = document.createElement("p");
      note.className = "note shared-note";
      note.textContent = hit.text || "";
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "mbtn";
      btn.textContent = T("st.addLeader");
      btn.title = T("st.addLeaderTitle");
      btn.addEventListener("click", function (ev) {
        ev.stopPropagation();
        var add = document.querySelector("#btn-add-leader");
        if (add) { add.click(); }
      });
      note.appendChild(document.createTextNode(" "));
      note.appendChild(btn);
      var btns = badge.querySelector(".bbtns");
      if (btns) { btns.parentNode.insertBefore(note, btns); }
    });
  }

  function refresh() {
    fetch("/api/meta", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (m) {
      meta = m || {};
      paint();
    }).catch(function () {});
  }

  var root = document.querySelector("#badges");
  if (root && window.MutationObserver) {
    new MutationObserver(function () { paint(); }).observe(root, { childList: true });
  }
  addEventListener("bx-top", function (ev) {
    if (ev.detail && ev.detail.meta) {
      meta = ev.detail.meta;
      paint();
    }
  });
  addEventListener("bx-lang-changed", function () { refresh(); });
  refresh();
})();
