/* 帮手页的共用小功能：「⋯」菜单（页头一个、每张工牌一个）、改名小窗，
   还有编程助手工牌上那句「两个对话在用同一个编程助手」。
   工牌是 stations.js 画的，画完再补，免得那个文件再长就超行数。 */
(function () {
  function T(k, v) { return window.BXi18n ? window.BXi18n.t(k, v) : k; }
  var NS = window.BXST || {};
  var $ = NS.$ || function (s) { return document.querySelector(s); };
  var esc = NS.esc || function (s) { return String(s == null ? "" : s); };
  var api = NS.api, post = NS.post, load = NS.load;
  var meta = { alerts: [] };

  /* ---------- 「⋯」菜单 ---------- */
  var badgeMenu = document.createElement("div");
  badgeMenu.className = "menu-pop";
  badgeMenu.id = "badge-menu";
  badgeMenu.hidden = true;
  document.body.appendChild(badgeMenu);

  function closeMenus() {
    badgeMenu.hidden = true;
    var head = $("#head-menu");
    if (head) { head.hidden = true; }
    var more = $("#btn-more");
    if (more) { more.setAttribute("aria-expanded", "false"); }
    Array.prototype.forEach.call(document.querySelectorAll("[data-menu]"), function (b) {
      b.setAttribute("aria-expanded", "false");
    });
  }
  function placePop(pop, btn) {
    pop.hidden = false;
    var r = btn.getBoundingClientRect();
    var w = pop.offsetWidth;
    pop.style.left = Math.max(6, Math.min(window.innerWidth - w - 6, r.right - w)) + "px";
    pop.style.top = (r.bottom + 6) + "px";
  }
  /* 工牌上的「⋯」里有什么：帮手续作 / 编程助手先「怎么派活」 */
  function menuItems(id) {
    var st = (NS.getDefs() || []).filter(function (s) { return s.id === id; })[0] || {};
    var lead = st.role === "leader";
    var items = [];
    if (lead) { items.push({ act: "summon", label: T("st.howTo"), title: T("st.wakeTitle") }); }
    items.push({ act: "rename", label: T("st.rename"), title: T("st.renameTitle") });
    if (!lead) {
      items.push({ act: "look", label: T("st.changeLook"), title: T("st.changeLookTitle") });
      var full = (NS.getDefs() || []).filter(function (s) { return s.role !== "leader"; }).length >= 6;
      items.push({ act: "copy", label: T("st.copyOne"), title: full ? T("st.copyFullTitle") : T("st.copyTitle"),
                   dis: full });
    }
    items.push({ act: "detail", label: T("st.seeDetail"), title: "" });
    items.push({ act: "del", label: T("st.del"), title: lead ? T("st.delLeaderTitle") : T("st.delTitle") });
    return items;
  }
  function openBadgeMenu(id, btn) {
    badgeMenu.innerHTML = menuItems(id).map(function (it) {
      return '<button class="mbtn' + (it.act === "del" ? " danger" : "") + '" type="button" data-act="' + it.act +
        '" title="' + esc(it.title) + '"' + (it.dis ? " disabled" : "") + ">" + esc(it.label) + "</button>";
    }).join("");
    badgeMenu.setAttribute("data-id", id);
    placePop(badgeMenu, btn);
    btn.setAttribute("aria-expanded", "true");
  }
  badgeMenu.addEventListener("click", function (ev) {
    var t = ev.target.closest ? ev.target.closest("[data-act]") : null;
    if (!t) { return; }
    var id = badgeMenu.getAttribute("data-id");
    var act = t.getAttribute("data-act");
    closeMenus();
    if (act === "rename") { openRename(id); return; }
    if (act === "look") { NS.openLook(id); return; }
    if (act === "copy") { NS.copyStation(id); return; }
    if (act === "detail") { NS.openDrawer(id); return; }
    if (act === "summon") { NS.summon(id); return; }
    if (act === "del") { NS.askDel(id); }
  });

  /* ---------- 工牌：点「⋯」开菜单，点工牌本体是另一件事 ---------- */
  var badges = document.querySelector("#badges");
  if (badges) {
    badges.addEventListener("click", function (ev) {
      var t = ev.target;
      var mid = t.getAttribute && t.getAttribute("data-menu");
      if (mid) {
        ev.stopPropagation();
        if (!badgeMenu.hidden && badgeMenu.getAttribute("data-id") === mid) { closeMenus(); }
        else { closeMenus(); openBadgeMenu(mid, t); }
        return;
      }
      if (t.closest && t.closest("button")) { return; }
      var card = t.closest && t.closest("[data-open]");
      if (!card) { return; }
      var id = card.getAttribute("data-open");
      var st = (NS.getDefs() || []).filter(function (s) { return s.id === id; })[0] || {};
      if (st.role === "leader") { NS.summon(id); return; }   /* 编程助手：点工牌 = 怎么派活 */
      NS.openForm(id);                                       /* 帮手：点工牌 = 打开修改配置 */
    });
  }

  /* ---------- 页头的「⋯」 ---------- */
  var more = $("#btn-more");
  if (more) {
    more.addEventListener("click", function (ev) {
      ev.stopPropagation();
      var pop = $("#head-menu");
      if (!pop.hidden) { closeMenus(); return; }
      closeMenus();
      placePop(pop, this);
      this.setAttribute("aria-expanded", "true");
    });
    $("#head-menu").addEventListener("click", function () { setTimeout(closeMenus, 0); });
  }
  document.addEventListener("click", function (ev) {
    if (ev.target.closest && (ev.target.closest(".menu-pop") || ev.target.closest("[data-menu]") ||
                              ev.target.closest("#btn-more"))) { return; }
    closeMenus();
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") { closeMenus(); }
  });

  /* ---------- 改名：小窗里一个输入框 ---------- */
  var renameId = null;
  function openRename(id) {
    renameId = id;
    var box = $("#rename-msg");
    box.hidden = true;
    box.textContent = "";
    $("#rename-input").value = NS.labelOf ? NS.labelOf(id) : "";
    $("#renameDlg").hidden = false;
    $("#rename-input").focus();
  }
  $("#rename-cancel").onclick = function () { $("#renameDlg").hidden = true; };
  $("#rename-ok").onclick = function () {
    var id = renameId;
    if (!id) { return; }
    var label = $("#rename-input").value.trim();
    var btn = this;
    btn.disabled = true;
    api("/api/stations/label", post({ id: id, label: label })).then(function (r) {
      if (!r || !r.ok) {
        var box = $("#rename-msg");
        box.hidden = false;
        box.textContent = (r && r.text) || T("st.renameFail", { why: "" });
        return;
      }
      $("#renameDlg").hidden = true;
      NS.pageMsg(T("st.renameOk", { id: id, label: label || id }), "ok");
      load();
    }).catch(function (e) {
      var box = $("#rename-msg");
      box.hidden = false;
      box.textContent = T("st.renameFail", { why: String(e) });
    }).then(function () { btn.disabled = false; });
  };

  /* ---------- 编程助手工牌上补一句「两个对话在用同一个编程助手」 ---------- */
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
      var card = badge.querySelector(".bcard");
      var body = badge.querySelector(".bbody");
      if (card) { card.insertBefore(note, body); }
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
