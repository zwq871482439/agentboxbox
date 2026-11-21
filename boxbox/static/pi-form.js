/* 共用的 Pi 配置表：上岗「加一个帮手」和帮手页「修改配置」都用这一份，两边存出来的配置一模一样。

   主表只露四样：模型平台、模型、密钥、测试连接。
   接口地址、接口类型、上下文窗口、最大输出、单价、额度查询收在默认折叠的「高级」里。
   选模型自动带出上下文窗口、最大输出和单价；存的是模型的 id（不是下拉框里显示的名字）。

   用法：
     var f = BXPiForm.mount(box, {
       ids: {prov: "ob-prov", model: "ob-model", ...},   // 元素 id，缺省用 pf- 前缀
       value: {provider_id: "", model_id: "", base_url: "", ...},
       onChange: function (cfg) {},                      // 改了值就叫人一声（上岗那边存草稿用）
       onTest: function (cfg) { return Promise.resolve(); },   // 点「测试连接」做的事
       onQuotaCheck: function (cfg) { return Promise.resolve(); }  // 「现在查一次」（可以不传）
     });
     f.read()   → {pi: {...}, quota: {...}, cost: {...}|null, key: "..."}
     f.fill(v)  → 回填
     f.test()   → 走 onTest
   词条在 i18n-stations.js 的 pf.* 里（中英各一份）。 */
(function () {
  "use strict";
  var NS = window.BXPiForm = window.BXPiForm || {};

  function T(k, v) { return window.BXi18n ? window.BXi18n.t(k, v) : k; }
  var esc = window.BXu.esc;   /* util.js 在本文件前加载（帮手页、首页都是） */
  function num(v, dflt) { var n = parseInt(v, 10); return isNaN(n) ? (dflt || 0) : n; }
  function money(v) { var n = parseFloat(v); return isNaN(n) ? null : n; }

  /* 接口类型 / 额度查询方式：值是核心认的那几个，界面上说人话 */
  var API_OPTS = [
    ["anthropic-messages", "pf.apiAnthropic"],
    ["openai-completions", "pf.apiOpenai"],
    ["openai-responses", "pf.apiResponses"],
    ["google-generative-ai", "pf.apiGemini"]
  ];
  var ADAPTER_OPTS = [
    ["kimi_code", "pf.planKimi"],
    ["glm_coding_plan", "pf.planGlm"],
    ["minimax_token_plan", "pf.planMiniMax"],
    ["custom", "pf.planCustom"]
  ];
  var ADAPTER_WORDS = {
    kimi_code: "pf.planKimi", glm_coding_plan: "pf.planGlm",
    minimax_token_plan: "pf.planMiniMax", custom: "pf.planCustom"
  };
  /* 额度查询按接口地址的主机名认服务商（跟核心 quota 同一套口径）：认得出就不用让人挑 */
  var HOSTS = {
    "api.kimi.com": "kimi_code", "open.bigmodel.cn": "glm_coding_plan",
    "minimaxi.com": "minimax_token_plan", "minimax.cn": "minimax_token_plan"
  };
  var DEFAULT_IDS = {
    prov: "pf-prov", model: "pf-model", base: "pf-base", api: "pf-api",
    ctx: "pf-ctx", max: "pf-max", key: "pf-key", costIn: "pf-cost-in", costOut: "pf-cost-out",
    qmode: "pf-qmode", qadapter: "pf-qadapter", qevery: "pf-qevery",
    qurl: "pf-q-url", qauth: "pf-q-auth", qpct: "pf-q-pct", qrem: "pf-q-rem", qreset: "pf-q-reset",
    testBtn: "pf-test-btn", testMsg: "pf-test-msg", quotaBtn: "pf-quota-btn", quotaMsg: "pf-quota-msg"
  };
  var CSS_DONE = false;
  function injectCss() {
    if (CSS_DONE) { return; }
    CSS_DONE = true;
    var s = document.createElement("style");
    s.textContent = [
      ".pif{color:#2b1d12}",
      ".pif-h3{margin:0 0 8px;font-size:14px;font-weight:700;color:#2b1d12}",
      ".pif-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px 14px}",
      "@media (max-width:640px){.pif-grid{grid-template-columns:1fr}}",
      ".pif-cell label{display:block;margin:0 0 3px;font-size:12.5px;color:#5a4632}",
      ".pif-cell input,.pif-cell select{display:block;width:100%;padding:6px 9px;border:2px solid #2b1d12;",
      "background:#fff;color:#2b1d12;font:inherit;border-radius:0}",
      ".pif-cell input:focus,.pif-cell select:focus{outline:2px solid #3f9b4f;outline-offset:-1px}",
      ".pif-cell input[readonly]{background:#f0e4c6;color:#5a4632}",
      ".pif-row{margin-top:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}",
      ".pif-btn{border:2px solid #2b1d12;background:#6b4a2f;color:#fff8e7;padding:6px 16px;font:inherit;cursor:pointer;",
      "box-shadow:3px 3px 0 rgba(0,0,0,.35)}",
      ".pif-btn:hover:not(:disabled){background:#7d5836}",
      ".pif-btn[disabled]{opacity:.5;cursor:default;box-shadow:none}",
      ".pif-btn.small{padding:4px 10px;font-size:12.5px}",
      ".pif-msg{margin-top:10px;padding:8px 12px;border:2px solid #2b1d12;background:#fdf8ec;font-size:13px}",
      ".pif-msg.ok{background:#e2f3e2;color:#215c2c}",
      ".pif-msg.fail{background:#fbe3df;color:#8c2318}",
      ".pif-msg.wait{background:#fdf3d8;color:#6b4a2f}",
      ".pif-adv{margin-top:12px;border:2px solid #2b1d12;background:#f6ecd6;padding:8px 12px}",
      ".pif-adv>summary{cursor:pointer;font-size:13px;font-weight:700;color:#3b2a1a}",
      ".pif-hint{margin:8px 0 0;font-size:12.5px;color:#5a4632}",
      ".pif-hide{display:none}"
    ].join("");
    document.head.appendChild(s);
  }

  function hostOf(url) {
    var s = String(url || "").trim().toLowerCase();
    s = s.replace(/^[a-z][a-z0-9+.-]*:\/\//, "");
    s = s.split("/")[0].split("?")[0].split("#")[0];
    if (s.indexOf("@") >= 0) { s = s.split("@").pop(); }
    return s.replace(/:\d+$/, "");
  }
  function adapterFor(url) {
    /* 主机名一样，或者以它打头的一个子域，才算这家 */
    var host = hostOf(url);
    if (!host) { return ""; }
    var keys = Object.keys(HOSTS);
    for (var i = 0; i < keys.length; i++) {
      var h = keys[i];
      if (host === h || host.slice(-(h.length + 1)) === "." + h) { return HOSTS[h]; }
    }
    return "";
  }

  /* 按前缀凑一整套元素 id：两个页面各起一份，id 不撞 */
  NS.ids = function (prefix) {
    var p = prefix || "pf-";
    return {
      prov: p + "prov", model: p + "model", base: p + "base", api: p + "api",
      ctx: p + "ctx", max: p + "max", key: p + "key",
      costIn: p + "cost-in", costOut: p + "cost-out",
      qmode: p + "qmode", qadapter: p + "qadapter", qevery: p + "qevery",
      qurl: p + "q-url", qauth: p + "q-auth", qpct: p + "q-pct", qrem: p + "q-rem", qreset: p + "q-reset",
      testBtn: p + "pi-test-btn", testMsg: p + "pi-test",
      quotaBtn: p + "quota-btn", quotaMsg: p + "quota-msg"
    };
  };

  function build(ids) {
    function opts(list) {
      return list.map(function (a) {
        return '<option value="' + a[0] + '">' + esc(T(a[1])) + "</option>";
      }).join("");
    }
    function cell(label, forId, inner) {
      return '<div class="pif-cell"><label for="' + forId + '">' + esc(label) + "</label>" + inner + "</div>";
    }
    var qModes = [["off", "pf.quotaOff"], ["after_run", "pf.quotaAfterRun"], ["interval", "pf.quotaInterval"]];
    return '<h3 class="pif-h3">' + esc(T("pf.title")) + "</h3>" +
      '<div class="pif-grid">' +
      cell(T("pf.provider"), ids.provInput, '<div id="' + ids.prov + '"></div>') +
      cell(T("pf.model"), ids.modelInput, '<div id="' + ids.model + '"></div>') +
      "</div>" +
      '<div class="pif-cell" style="margin-top:10px">' +
      '<label for="' + ids.key + '">' + esc(T("pf.key")) + "</label>" +
      '<input id="' + ids.key + '" type="password" autocomplete="off" placeholder="' + esc(T("pf.keyPh")) + '">' +
      "</div>" +
      '<div class="pif-row"><button type="button" class="pif-btn" id="' + ids.testBtn + '">' +
      esc(T("pf.test")) + "</button></div>" +
      '<div class="pif-msg pif-hide" id="' + ids.testMsg + '"></div>' +
      '<details class="pif-adv"><summary>' + esc(T("pf.advanced")) + "</summary>" +
      '<div class="pif-grid" style="margin-top:10px">' +
      cell(T("pf.base"), ids.base, '<input id="' + ids.base + '" type="text">') +
      cell(T("pf.api"), ids.api, '<select id="' + ids.api + '">' + opts(API_OPTS) + "</select>") +
      cell(T("pf.ctx"), ids.ctx, '<input id="' + ids.ctx + '" type="number" min="1">') +
      cell(T("pf.max"), ids.max, '<input id="' + ids.max + '" type="number" min="1">') +
      cell(T("pf.costIn"), ids.costIn, '<input id="' + ids.costIn + '" type="number" min="0" step="0.01">') +
      cell(T("pf.costOut"), ids.costOut, '<input id="' + ids.costOut + '" type="number" min="0" step="0.01">') +
      "</div>" +
      '<div class="pif-grid" style="margin-top:10px">' +
      cell(T("pf.quotaMode"), ids.qmode, '<select id="' + ids.qmode + '">' + opts(qModes) + "</select>") +
      '<div class="pif-cell" id="' + ids.qadapterF + '">' +
      '<label for="' + ids.qadapter + '">' + esc(T("pf.quotaAdapter")) + "</label>" +
      '<select id="' + ids.qadapter + '">' + opts(ADAPTER_OPTS) + "</select>" +
      '<p class="pif-hint" id="' + ids.qadapterNote + '"></p>' +
      "</div>" +
      cell(T("pf.quotaEvery"), ids.qevery, '<input id="' + ids.qevery + '" type="number" min="1">') +
      "</div>" +
      '<div class="pif-grid pif-hide" id="' + ids.qcustom + '" style="margin-top:10px">' +
      cell(T("pf.quotaUrl"), ids.qurl, '<input id="' + ids.qurl + '" type="text">') +
      cell(T("pf.quotaAuth"), ids.qauth, '<select id="' + ids.qauth + '">' +
        '<option value="bearer">' + esc(T("pf.authBearer")) + "</option>" +
        '<option value="raw">' + esc(T("pf.authRaw")) + "</option>" +
        '<option value="none">' + esc(T("pf.authNone")) + "</option>" + "</select>") +
      cell(T("pf.quotaPct"), ids.qpct, '<input id="' + ids.qpct + '" type="text">') +
      cell(T("pf.quotaRem"), ids.qrem, '<input id="' + ids.qrem + '" type="text">') +
      cell(T("pf.quotaReset"), ids.qreset, '<input id="' + ids.qreset + '" type="text">') +
      "</div>" +
      '<div class="pif-row"><button type="button" class="pif-btn small" id="' + ids.quotaBtn + '">' +
      esc(T("pf.quotaNow")) + "</button></div>" +
      '<div class="pif-msg pif-hide" id="' + ids.quotaMsg + '"></div>' +
      '<p class="pif-hint">' + esc(T("pf.keyHint")) + "</p>" +
      "</details>";
  }

  NS.mount = function (box, opts) {
    opts = opts || {};
    var ids = Object.assign({}, DEFAULT_IDS, opts.ids || {});
    ids.provInput = ids.provInput || (ids.prov + "-input");
    ids.modelInput = ids.modelInput || (ids.model + "-input");
    ids.qcustom = ids.qcustom || (ids.qadapter + "-custom");
    ids.qadapterF = ids.qadapterF || (ids.qadapter + "-f");
    ids.qadapterNote = ids.qadapterNote || (ids.qadapter + "-note");
    injectCss();
    box.innerHTML = build(ids);
    var provBox = box.querySelector("#" + ids.prov);
    var modelBox = box.querySelector("#" + ids.model);
    var value = opts.value || {};
    var fallbackReasoning = (value.reasoning == null) ? true : !!value.reasoning;
    var adapterDirty = false;
    var provMount = null;

    function el(id) { return box.querySelector("#" + id); }
    function val(id) { var e = el(id); return e ? String(e.value == null ? "" : e.value).trim() : ""; }
    function setVal(id, v) { var e = el(id); if (e) { e.value = v == null ? "" : v; } }

    /* 清单里的下拉框是自己长出来的：拿到输入框要等它挂好（下面的 input / onChange 都要用） */
    function modelInput() { return modelBox ? modelBox.querySelector("input") : null; }
    function provInput() { return provBox ? provBox.querySelector("input") : null; }

    function pickedModel() { return provMount && provMount.model ? provMount.model() : null; }
    function pickedProvider() { return provMount && provMount.provider ? provMount.provider() : null; }

    /* 下拉框里显示的是名字，存下来的是 id：框里的字和选中项对不上就按手填的算 */
    function modelText() {
      var m = pickedModel();
      var inp = modelInput();
      var text = inp ? String(inp.value || "").trim() : "";
      if (m && text && text === String(m.name || m.id)) { return String(m.id); }
      return text;
    }
    function onProvider(p) {
      if (p) {
        if (p.api) { setVal(ids.base, p.api); }
        if (p.api_type) { setVal(ids.api, p.api_type); }
      }
      syncQuota();
      changed();
    }
    function onModel(m) {
      if (m) {
        if (m.context) { setVal(ids.ctx, m.context); }
        if (m.output) { setVal(ids.max, m.output); }
        /* 清单里带着单价：选了模型就把每百万用量的价填上 */
        var c = m.cost || {};
        if (c.input != null) { setVal(ids.costIn, c.input); }
        if (c.output != null) { setVal(ids.costOut, c.output); }
      }
      changed();
    }
    /* 额度查询收着的几块：查询方式关了就整行藏起来；认得出服务商就写一行说明，不让人挑 */
    function syncQuota() {
      var every = el(ids.qevery);
      if (every && every.parentElement) {
        every.parentElement.classList.toggle("pif-hide", val(ids.qmode) !== "interval");
      }
      var off = val(ids.qmode) === "off";
      var known = adapterFor(val(ids.base));
      if (known && !adapterDirty) { setVal(ids.qadapter, known); }
      var row = el(ids.qadapterF);
      var note = el(ids.qadapterNote);
      if (row) { row.classList.toggle("pif-hide", off || (!!known && !adapterDirty)); }
      if (note) {
        note.classList.toggle("pif-hide", off || !known);
        if (known) { note.textContent = T("pf.quotaBy", { x: T(ADAPTER_WORDS[known] || "") }); }
      }
      var custom = el(ids.qcustom);
      if (custom) { custom.classList.toggle("pif-hide", val(ids.qadapter) !== "custom"); }
    }
    function changed() {
      syncQuota();
      if (opts.onChange) { opts.onChange(read()); }
    }

    if (window.BXProviders) {
      provMount = window.BXProviders.mount({
        provBox: provBox,
        modelBox: modelBox,
        provider: String(value.provider_id || ""),
        model: String(value.model_id || ""),
        onProvider: onProvider,
        onModel: onModel
      });
    }
    /* 下拉框长出来了：把输入框的 id 补上（表里的 label 指着它） */
    var mi = modelInput(), pi2 = provInput();
    if (mi) { mi.id = ids.modelInput; }
    if (pi2) { pi2.id = ids.provInput; }
    /* 清单是异步到的：到了以后再把选中的填回去 */
    if (provMount && provMount.resetPickers) {
      provMount.resetPickers(String(value.provider_id || ""), String(value.model_id || ""));
    }

    [ids.base, ids.api, ids.ctx, ids.max, ids.costIn, ids.costOut, ids.key, ids.qevery,
     ids.qurl, ids.qauth, ids.qpct, ids.qrem, ids.qreset].forEach(function (id) {
      var e = el(id);
      if (e) { e.addEventListener("change", function () { changed(); }); }
    });
    var baseEl = el(ids.base);
    if (baseEl) { baseEl.addEventListener("change", function () { changed(); }); }
    var qmode = el(ids.qmode);
    if (qmode) { qmode.addEventListener("change", changed); }
    var qadapter = el(ids.qadapter);
    if (qadapter) {
      qadapter.addEventListener("change", function () { adapterDirty = true; changed(); });
    }
    if (mi) { mi.addEventListener("change", changed); }
    if (pi2) { pi2.addEventListener("change", changed); }

    function read() {
      var p = pickedProvider();
      var m = pickedModel();
      var pi = {
        base_url: val(ids.base),
        api: val(ids.api) || "anthropic-messages",
        model: modelText(),
        context_window: num(val(ids.ctx), 200000),
        max_tokens: num(val(ids.max), 32000),
        reasoning: fallbackReasoning
      };
      if (m && m.reasoning != null) { pi.reasoning = !!m.reasoning; }
      if (p && p.id) { pi.provider_id = String(p.id); }
      if (m && m.id) { pi.model_id = String(m.id); }
      var q = { mode: val(ids.qmode) || "off" };
      if (q.mode === "interval") { q.interval_min = Math.max(1, num(val(ids.qevery), 30)); }
      q.adapter = val(ids.qadapter) || "custom";
      if (q.adapter === "custom") {
        q.custom = { url: val(ids.qurl), auth: val(ids.qauth) || "bearer",
                     pct_path: val(ids.qpct), remaining_pct_path: val(ids.qrem), reset_path: val(ids.qreset) };
      }
      var ci = money(val(ids.costIn)), co = money(val(ids.costOut));
      var cost = null;
      if (ci != null || co != null) {
        cost = {};
        if (ci != null) { cost.in = ci; }
        if (co != null) { cost.out = co; }
      }
      return {
        pi: pi,
        quota: q,
        cost: cost,
        key: val(ids.key)
      };
    }

    function fill(v) {
      v = v || {};
      var pi = v.pi || v;
      setVal(ids.base, pi.base_url || "");
      setVal(ids.api, pi.api || "anthropic-messages");
      setVal(ids.ctx, pi.context_window || 200000);
      setVal(ids.max, pi.max_tokens || 32000);
      setVal(ids.costIn, v.cost_in == null ? "" : v.cost_in);
      setVal(ids.costOut, v.cost_out == null ? "" : v.cost_out);
      setVal(ids.key, "");                 /* 密钥不留在表单里：回填只回配置 */
      if (pi.reasoning != null) { fallbackReasoning = !!pi.reasoning; }
      adapterDirty = false;
      if (provMount && provMount.resetPickers) {
        provMount.resetPickers(String(pi.provider_id || ""), String(pi.model_id || ""));
      }
      /* 清单里没有的模型就按手填的记：框里的字留着 */
      if (!pi.model_id && modelInput()) { modelInput().value = String(pi.model || ""); }
      var q = v.quota || {};
      setVal(ids.qmode, q.mode || "off");
      setVal(ids.qevery, q.interval_min || 30);
      setVal(ids.qadapter, q.adapter || adapterFor(pi.base_url || "") || "custom");
      var c = q.custom || {};
      setVal(ids.qurl, c.url || "");
      setVal(ids.qauth, c.auth || "bearer");
      setVal(ids.qpct, c.pct_path || "");
      setVal(ids.qrem, c.remaining_pct_path || "");
      setVal(ids.qreset, c.reset_path || "");
      syncQuota();
    }

    function setMessage(kind, html, msgId) {
      var m = el(msgId || ids.testMsg);
      if (!m) { return; }
      m.className = "pif-msg " + (kind || "info");
      m.innerHTML = html == null ? "" : html;
    }
    function clearMessage(msgId) {
      var m = el(msgId || ids.testMsg);
      if (m) { m.className = "pif-msg pif-hide"; m.innerHTML = ""; }
    }
    function setKeyed(on) {
      var k = el(ids.key);
      if (k) { k.placeholder = on ? T("pf.keyPhSet") : T("pf.keyPh"); }
    }
    function clearKey() {
      var k = el(ids.key);
      if (k) { k.value = ""; }
    }
    function test() {
      if (!opts.onTest) { return Promise.resolve(null); }
      var btn = el(ids.testBtn);
      if (btn) { btn.disabled = true; }
      return Promise.resolve(opts.onTest(read())).then(function (r) {
        if (btn) { btn.disabled = false; }
        return r;
      }, function (e) {
        if (btn) { btn.disabled = false; }
        throw e;
      });
    }

    var testBtn = el(ids.testBtn);
    if (testBtn) { testBtn.onclick = function () { test(); }; }
    var quotaBtn = el(ids.quotaBtn);
    if (quotaBtn) {
      if (!opts.onQuotaCheck) { quotaBtn.parentElement.classList.add("pif-hide"); }
      else {
        quotaBtn.onclick = function () {
          quotaBtn.disabled = true;
          Promise.resolve(opts.onQuotaCheck(read())).then(function () { quotaBtn.disabled = false; },
                                                            function () { quotaBtn.disabled = false; });
        };
      }
    }

    fill(value);
    return {
      read: read,
      fill: fill,
      test: test,
      setMessage: setMessage,
      clearMessage: clearMessage,
      setKeyed: setKeyed,
      clearKey: clearKey,
      ids: ids
    };
  };
})();
