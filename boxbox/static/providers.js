/* 服务商 / 模型选择：从 /api/providers 拉 models.dev 清单，给页面两个可输入搜索的下拉。
   单独成一个文件，因为上岗像素窗口和工位编辑浮层都要用。
   用法：
     BXProviders.mount({
       provBox: el, modelBox: el,       // 两个容器（服务商、模型）
       provider: "kimi-code-plan-cn",   // 编辑时预选的服务商 id（可省）
       model: "kimi-for-coding",        // 编辑时预选的模型 id（可省）
       onProvider: function (p) {},     // 选中清单里一家时给对象；手动填写 / 没匹配上给 null
       onModel: function (m) {}         // 选中清单里一个模型时给对象；手动填写 / 没匹配上给 null
     });
   样式用各页已有的 CSS 变量（--panel / --line / --ink / --dim / --accent），没有就用默认值。 */
(function () {
  "use strict";
  var CSS_DONE = false;
  var listPromise = null;

  /* 词条在各页自己的词表里（设置页 / 上岗页），这里只负责把字归到输入框 */
  function T(k, v) { return window.BXi18n ? window.BXi18n.t(k, v) : k; }

  function injectCss() {
    if (CSS_DONE) { return; }
    CSS_DONE = true;
    var s = document.createElement("style");
    s.textContent = [
      ".bxp{position:relative}",
      ".bxp input{display:block;width:100%;margin-top:3px;padding:6px 9px;border:1px solid var(--line,#2b3037);",
      "background:var(--panel,#1b1e24);color:var(--ink,#e5e8ea);font:inherit;border-radius:0}",
      ".bxp input:focus{outline:2px solid var(--accent,#7aa8d8);outline-offset:-1px}",
      ".bxp .dd{position:absolute;left:0;right:0;top:100%;z-index:60;max-height:230px;overflow-y:auto;",
      "background:var(--panel,#1b1e24);border:1px solid var(--line,#2b3037);box-shadow:4px 4px 0 rgba(0,0,0,.55);margin-top:2px}",
      ".bxp .dd[hidden]{display:none}",
      ".bxp .it{display:flex;justify-content:space-between;gap:8px;padding:5px 9px;cursor:pointer;font-size:13px}",
      ".bxp .it:hover,.bxp .it.sel{background:var(--code,#22262d)}",
      ".bxp .it .id{color:var(--dim,#98a1ac);font-family:ui-monospace,Consolas,monospace}",
      ".bxp .it.manual{color:var(--dim,#98a1ac)}"
    ].join("");
    document.head.appendChild(s);
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function list() {
    if (!listPromise) {
      listPromise = fetch("/api/providers", { cache: "no-store" })
        .then(function (r) { return r.json(); })
        .then(function (d) { return (d && d.providers) || []; })
        .catch(function () { return []; });
    }
    return listPromise;
  }

  /* 一个可输入搜索的下拉。items() 每次现取（服务商选完模型列表会换）。 */
  function combo(box, opts) {
    var input = document.createElement("input");
    input.type = "text";
    input.placeholder = opts.placeholder || "";
    input.setAttribute("autocomplete", "off");
    var dd = document.createElement("div");
    dd.className = "dd";
    dd.hidden = true;
    box.className = "bxp";
    box.appendChild(input);
    box.appendChild(dd);
    var picked = null;        // 当前选中的清单项（手动填写 / 没匹配上 = null）
    var query = "";

    function items() { return opts.items() || []; }
    function label(it) { return opts.label(it); }
    function itemId(it) { return opts.itemId(it); }
    function matches(it) {
      if (!query) { return true; }
      var q = query.toLowerCase();
      return String(label(it)).toLowerCase().indexOf(q) >= 0 || String(itemId(it)).toLowerCase().indexOf(q) >= 0;
    }
    function open() {
      var all = items().filter(matches).slice(0, 60);
      var html = '<div class="it manual" data-i="-1">' + esc(T("prov.manual")) + "</div>";
      html += all.map(function (it, i) {
        return '<div class="it" data-i="' + i + '"><span>' + esc(label(it)) + '</span><span class="id">' + esc(itemId(it)) + "</span></div>";
      }).join("");
      dd.innerHTML = html;
      dd.hidden = false;
    }
    function close() { dd.hidden = true; }
    function pick(it) {
      picked = it || null;
      input.value = it ? label(it) : "";
      close();
      if (opts.onPick) { opts.onPick(picked); }
    }
    input.addEventListener("focus", function () { query = input.value.trim(); open(); });
    input.addEventListener("input", function () { query = input.value.trim(); open(); });
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        var first = items().filter(matches)[0];
        if (input.value.trim() && first) { pick(first); } else { pick(null); }
      } else if (ev.key === "Escape") { close(); }
    });
    /* mousedown 比 blur 先到：点下拉项不会先被 blur 收掉 */
    dd.addEventListener("mousedown", function (ev) {
      var row = ev.target.closest ? ev.target.closest(".it") : null;
      if (!row) { return; }
      ev.preventDefault();
      var i = parseInt(row.getAttribute("data-i"), 10);
      if (i < 0) { pick(null); return; }
      var all = items().filter(matches);
      pick(all[i] || null);
    });
    input.addEventListener("blur", function () {
      setTimeout(function () {
        close();
        var text = input.value.trim();
        if (!text) { if (picked) { picked = null; if (opts.onPick) { opts.onPick(null); } } return; }
        var exact = null;
        items().forEach(function (it) { if (!exact && (label(it) === text || itemId(it) === text)) { exact = it; } });
        if (exact !== picked) { picked = exact; if (opts.onPick) { opts.onPick(exact); } }
      }, 120);
    });
    return {
      /* 程序设值（编辑表单回填）：不触发 onPick */
      set: function (it) {
        picked = it || null;
        input.value = it ? label(it) : "";
      },
      current: function () { return picked; },
      reset: function () { picked = null; input.value = ""; },
      /* 清单慢一点到（/api/providers 两百多家要一会儿）：下拉正开着就把刚到的补上 */
      reopen: function () { if (!dd.hidden) { query = input.value.trim(); open(); } }
    };
  }

  function findById(rows, id) {
    var hit = null;
    (rows || []).forEach(function (x) { if (x.id === id) { hit = x; } });
    return hit;
  }

  function mount(o) {
    injectCss();
    var state = { providers: [], provider: null, model: null };
    var pending = { provider: o.provider || "", model: o.model || "" };   // 清单还没到时先记着要预选谁

    var modelC = combo(o.modelBox, {
      placeholder: T("prov.modelPh"),
      items: function () { return state.provider ? (state.provider.models || []) : []; },
      label: function (m) { return m.name || m.id; },
      itemId: function (m) { return m.id; },
      onPick: function (m) {
        state.model = m;
        if (o.onModel) { o.onModel(m); }
      }
    });
    var provC = combo(o.provBox, {
      placeholder: T("prov.providerPh"),
      items: function () { return state.providers; },
      label: function (p) { return p.name || p.id; },
      itemId: function (p) { return p.id; },
      onPick: function (p) {
        state.provider = p;
        state.model = null;
        modelC.reset();
        if (o.onProvider) { o.onProvider(p); }
      }
    });

    function applyPending() {
      if (!pending.provider) { return; }
      var p = findById(state.providers, pending.provider) || null;
      provC.set(p);
      state.provider = p;
      if (pending.model && p) {
        var m = findById(p.models || [], pending.model) || null;
        modelC.set(m);
        state.model = m;
      }
      pending = { provider: "", model: "" };
    }
    list().then(function (provs) {
      state.providers = provs;
      applyPending();
      provC.reopen();          /* 清单晚到时，下拉开着就补上（不然只看得见「手动填写」） */
      modelC.reopen();
    });
    return {
      provider: function () { return state.provider; },
      model: function () { return state.model; },
      /* 编辑表单回填：重置两个选择器并预选；不触发 onProvider / onModel */
      resetPickers: function (pid, mid) {
        provC.reset();
        modelC.reset();
        state.provider = null;
        state.model = null;
        pending = { provider: pid || "", model: mid || "" };
        applyPending();
      }
    };
  }

  window.BXProviders = { list: list, mount: mount };
})();
