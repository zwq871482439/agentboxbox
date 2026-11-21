/* 上岗流程 · 打工猫那几步：招募（起名选样子）、接入方式（API key 自动跑 / 会话模式）、测试、保存。
   Pi 那部分的表单在 pi-form.js 里（上岗和帮手页共用一份）。依赖 onboard-common.js（先加载）。 */
(function () {
  "use strict";
  var NS = window.BXOB;
  var S = NS.S;
  var $ = NS.$, esc = NS.esc, num = NS.num, api = NS.api, post = NS.post;
  var win = NS.win, catCard = NS.catCard, wireCat = NS.wireCat;
  var dget = NS.dget, draft = NS.draft;
  /* 共用表单的词条在 i18n-stations.js 的 pf.* 里（和帮手页同一份） */
  function P(k, vars) { return window.BXi18n ? window.BXi18n.t(k, vars) : k; }

  /* ================= 这一份文件的文案（中文 / 英文） ================= */
  NS.addTxt("member", {
    'access.copyPath': ['复制路径', 'Copy the path'],
    'access.copyPrompt': ['复制这段话', 'Copy the text'],
    'access.doneBtn': ['接好了', 'Connected'],
    'access.modePi': ['用 API key 自动跑', 'Run it with an API key'],
    'access.modePiDesc': [
      '盒子自己拉起这个帮手，派活就开工。模型平台、密钥、模型在下面填。',
      'The box starts the helper by itself and work begins as soon as there is some. ' +
        'Fill in the model platform, the key and the model below.'
    ],
    'access.modeSched': ['会话模式', 'Check-in mode'],
    'access.modeSchedDesc': [
      '你的 AI 软件每隔几分钟开一个新对话来领卡，不分是哪个软件，也不用 API key。',
      'Your AI app opens a new chat every few minutes to pick up cards — whichever app it is, ' +
        'and no API key needed.'
    ],
    'access.notFound': ['查不到这个工位', 'station not found'],
    'access.ready': ['已就绪', 'Ready'],
    'access.readyMsg': [
      '先测一下：用 API key 的点「测试连接」，会话模式点「测试」，测通了才算接好',
      'Test first: click “Test connection” for the API key mode, ' +
        'or “Test” for check-in mode. Only then it counts as connected'
    ],
    'access.saveFail': ['保存失败：{why}', 'Could not save: {why}'],
    'access.schedEvery': ['每隔几分钟来领一次活', 'Pick up cards every few minutes'],
    'access.schedHint': [
      '建好定时任务后，等它第一次跑完，再点一次「测试」就能看到「来过了」。',
      'After you set up the timer, wait for its first run, ' +
        'then click “Test” again to see that it has been here.'
    ],
    'access.schedNoPath': ['先点下面的「测试」登记工位，这里就有路径了', 'Click “Test” below to register the station, then the path shows up'],
    'access.schedNoPrompt': ['先点下面的「测试」登记工位，再回来复制', 'Click “Test” below to register the station, then come back to copy it'],
    'access.schedOk': ['来读过了：{state}', 'It has been here: {state}'],
    'access.schedPath': ['任务单文件路径', 'Job list file path'],
    'access.schedPrompt': ['贴进定时任务的那段话', 'Text for the scheduled task'],
    'access.schedTesting': ['正在登记工位并检查…', 'Registering the station and checking…'],
    'access.schedTitle': ['会话模式', 'Check-in mode'],
    'access.schedWait': [
      '还没来过：{state}。照说明在客户端里建好定时任务，等它第一次跑完，这只猫才算接上；再点一次「测试」就能看到「来过了」。',
      'Not here yet: {state}. ' +
        'Set up the timer in your app as described and wait for its first run; ' +
        'then this worker is connected. Click “Test” again to see that it has been here.'
    ],
    'access.seeGuide': ['查看说明', 'Show the guide'],
    'access.test': ['测试', 'Test'],
    'access.title': ['加一个帮手：怎么干活', 'Add a helper: how it works'],
    'access.unknownWhy': ['未知原因', 'unknown reason'],
    'access.whyMember': [
      '编程助手只派活、不自己干：所以至少要加一个帮手。手上没有 API key 也行，另一种接法不用 key。',
      'Your coding assistant only hands work out, so add at least one helper. ' +
        'No API key? The other option needs none.'
    ],
    'recruit.acc': ['换一套配饰', 'Shuffle the extras'],
    'recruit.defaultWorker': ['打工猫猫', 'Worker'],
    'recruit.nameEmpty': ['给帮手起个名字吧', 'Give the helper a name'],
    'recruit.nameHint': ['默认「{name}」，可改。已经有的名字会提醒你换一个。', 'Default “{name}”, you can change it. Names already in use are flagged.'],
    'recruit.nameLabel': ['帮手的名字', 'Helper name'],
    'recruit.nameTaken': ['已经有叫「{name}」的猫了，换一个名字吧', 'A cat called “{name}” already exists, pick another name'],
    'recruit.title': ['加一个帮手', 'Add a helper'],
  });

  var PI_APIS = ["anthropic-messages", "openai-completions", "openai-responses", "google-generative-ai"];
  /* Pi 测试失败按退出码说人话：10 忙 / 11 没额度 / 12 连不上 / 13 key 不对 / 14 被路由拦下 */
  var PI_FAIL = {
    quota: [11, "pf.failQuota", "pf.failQuotaFix"],
    unreachable: [12, "pf.failUnreachable", "pf.failUnreachableFix"],
    auth: [13, "pf.failAuth", "pf.failAuthFix"],
    route: [14, "pf.failRoute", "pf.failRouteFix"],
    unknown: [1, "pf.failUnknown", "pf.failUnknownFix"]
  };
  NS.PI_FAIL = PI_FAIL;
  var piForm = null;         /* 共用的 Pi 配置表（pi-form.js） */

  /* 把唯一条件写死——首领只派活不干活，没有打工猫就派不了卡。能先跳过，但要说清楚跳过的后果 */
  function whyMember() {
    return '<p class="hint" id="ob-why-member">' + NS.tx("member.access.whyMember") + "</p>";
  }
  function skipMember(x, res) {
    S.skipMember = true;
    post("/api/settings", { skipped_member: true }).catch(function () { /* 记不上也不挡：只影响下次打开要不要接着上岗 */ });
    x.close();
    res();
  }
  NS.skipMember = skipMember;
  function stationsDef() { return api("/api/stations_def").then(function (r) { return r.data.stations || []; }); }
  NS.stationsDef = stationsDef;
  function nextMemberName(items) {
    var letters = "ABCDEF".split("");
    var base = NS.defaultMemberBase();
    for (var i = 0; i < letters.length; i++) {
      var id = base + letters[i];
      if (!items.some(function (s) { return s.id === id; })) { return id; }
    }
    return base + (letters.length + 1);
  }

  /* ---------- 招募打工猫猫 ---------- */
  function stepRecruitMember() {
    return stationsDef().then(function (items) {
      var dflt = String(dget("member_name", nextMemberName(items)));
      var used = NS.usedCats(items, null);                     /* 别和已有工位撞底猫 */
      var no = num(dget("member_cat", 0) || NS.randomCat(used));
      var look = { cat: no, acc: dget("member_acc", {}) };
      S.memberLook = look;
      S.memberName = dflt;
      return new Promise(function (res) {
        var spec = { no: no, look: look };
        var w = win({
          title: "招募打工猫猫",
          titleKey: "member.recruit.title",
          body: '<div class="grid2">' +
            catCard(no, '<div class="adv-acc"><button type="button" class="pxb small" id="ob-acc">' +
              esc(NS.tx("member.recruit.acc")) + "</button></div>") +
            '<div class="card"><label class="lb" for="ob-member-name">' + esc(NS.tx("member.recruit.nameLabel")) + "</label>" +
            '<input id="ob-member-name" type="text" maxlength="24" value="' + esc(dflt) + '">' +
            '<p class="hint">' + esc(NS.tx("member.recruit.nameHint", { name: dflt })) + "</p>" +
            '<div class="msg hide" id="ob-member-msg"></div></div></div>' + whyMember(),
          buttons: [{
            text: NS.tx("common.next"), main: true, on: function (x) {
              var v = (x.$("#ob-member-name").value || "").trim();
              if (!v) { x.msg("#ob-member-msg", "fail", NS.tx("member.recruit.nameEmpty")); return; }
              if (items.some(function (s) { return s.id === v; })) {
                x.msg("#ob-member-msg", "fail", NS.tx("member.recruit.nameTaken", { name: esc(v) }));
                return;
              }
              S.memberName = v;
              draft({ member_name: v, member_cat: spec.no, member_acc: spec.look.acc });
              x.close();
              res();
            }
          }, { text: NS.tx("common.later"), small: true, on: function (x) { skipMember(x, res); } }]
        });
        wireCat(w, spec, function (s) { draft({ member_cat: s.no }); });
        w.$("#ob-acc").onclick = function () {         /* 换一套配饰：重新随机 0–3 件 */
          spec.look.acc = NS.randomAcc();
          wireCat(w, spec, null);
          draft({ member_acc: spec.look.acc });
        };
      });
    });
  }

  /* ---------- 打工猫接入方式 ---------- */
  function stepMemberAccess() {
    var mode = String(dget("m_mode", "pi"));
    return new Promise(function (res) {
      var w = win({
        title: "打工猫接入方式",
        titleKey: "member.access.title",
        body: '<div class="pick2">' +
          '<div class="card" id="ob-m-pi"><h3>' + esc(NS.tx("member.access.modePi")) + "</h3>" +
          '<p class="lb">' + esc(NS.tx("member.access.modePiDesc")) + "</p></div>" +
          '<div class="card" id="ob-m-sched"><h3>' + esc(NS.tx("member.access.modeSched")) + "</h3>" +
          '<p class="lb">' + esc(NS.tx("member.access.modeSchedDesc")) + "</p></div></div>" +
          '<div class="sub3" id="ob-pi-box"></div><div class="sub3 hide" id="ob-sched-box"></div>' +
          '<div class="msg hide" id="ob-m-msg"></div>',
        buttons: [{
          text: NS.tx("member.access.doneBtn"), main: true, on: function (x, btn) {
            if (!x._ready) {
              x.msg("#ob-m-msg", "fail", NS.tx("member.access.readyMsg"));
              return;
            }
            btn.disabled = true;
            saveMember(x).then(function (ok) {
              btn.disabled = false;
              if (!ok) { return; }
              x.close();
              res();
            });
          }
        }, { text: NS.tx("common.later"), small: true, on: function (x) { skipMember(x, res); } }]
      });
      mountPiBox(w);
      mountSchedBox(w, mode);
      w.$("#ob-m-pi").onclick = function () { pickMode(w, "pi"); };
      w.$("#ob-m-sched").onclick = function () { pickMode(w, "sched"); };
      pickMode(w, mode);
    });
  }
  function pickMode(w, mode) {
    w.$("#ob-m-pi").classList.toggle("sel", mode === "pi");
    w.$("#ob-m-sched").classList.toggle("sel", mode === "sched");
    w.$("#ob-pi-box").classList.toggle("hide", mode !== "pi");
    w.$("#ob-sched-box").classList.toggle("hide", mode !== "sched");
    draft({ m_mode: mode });
    if (mode === "sched") { showSched(w); }
  }

  /* ---------- Pi 那部分：共用 pi-form.js 的表 ---------- */
  function mountPiBox(w) {
    var q = dget("m_quota", {}) || {};
    var box = w.$("#ob-pi-box");
    box.innerHTML = '<div class="card"><div id="ob-pi-form"></div></div>';
    piForm = window.BXPiForm.mount(box.querySelector("#ob-pi-form"), {
      ids: window.BXPiForm.ids("ob-"),
      value: {
        base_url: String(dget("m_base", "")),
        api: String(dget("m_api", PI_APIS[0])),
        model: String(dget("m_model", "")),
        model_id: String(dget("m_model_id", "")),
        provider_id: String(dget("m_provider", "")),
        context_window: num(dget("m_ctx", 200000), 200000),
        max_tokens: num(dget("m_max", 32000), 32000),
        quota: q
      },
      onChange: savePiDraft,
      onTest: function (cfg) { return testPi(w, cfg); }
    });
    /* 接着做（刷新 / 关掉再开）时这只猫可能已经存过 key 了——问一句核心，
       存过就把 key 框的占位换成「已存好」，测试也不用再填 key */
    NS.piForm = piForm;
    api("/api/stations").then(function (b) {
      var row = null;
      ((b.data || {}).stations || []).forEach(function (s) { if (s.id === S.memberName) { row = s; } });
      setKeyed(!!(row && row.has_key));
    });
  }
  /* 表里改了值就存进草稿：刷新 / 关掉再开，刚才填的还在 */
  function savePiDraft(cfg) {
    var pi = cfg.pi;
    draft({
      m_base: pi.base_url, m_api: pi.api, m_model: pi.model,
      m_ctx: pi.context_window, m_max: pi.max_tokens,
      m_provider: pi.provider_id || "", m_model_id: pi.model_id || "",
      m_quota: cfg.quota
    });
  }
  function memberStation() {
    return { id: S.memberName || NS.defaultMemberBase() + "A", role: "member", client: "pi",
      runner: "once", enabled: true, look: S.memberLook, lang: NS.lang() };
  }
  function readyUp(w) {
    w._ready = true;
    w.msg("#ob-m-msg", "ok", NS.tx("member.access.ready"));
  }
  /* key 存好没好这个状态走 S.memberHasKey；存好了 key 框就只是「想换才填」 */
  function setKeyed(on) {
    S.memberHasKey = !!on;
    if (piForm) { piForm.setKeyed(S.memberHasKey); }
  }
  function keptNote() {
    return S.memberHasKey ? P("pf.keyKept") : "";
  }
  function testPi(w, cfg) {
    var pi = cfg.pi;
    savePiDraft(cfg);
    var miss = [];
    if (!pi.base_url) { miss.push(P("pf.base")); }
    if (!pi.model) { miss.push(P("pf.model")); }
    if (!(pi.context_window > 0)) { miss.push(P("pf.ctx")); }
    if (!(pi.max_tokens > 0)) { miss.push(P("pf.max")); }
    if (!cfg.key && !S.memberHasKey) { miss.push(P("pf.key")); }
    if (miss.length) { piForm.setMessage("fail", P("pf.missFields", { x: esc(miss.join("、")) })); return; }
    piForm.setMessage("wait", P("pf.testing"));
    var t0 = Date.now();
    var st = memberStation();
    st.pi = pi;
    st.quota = cfg.quota;
    post("/api/stations", st).then(function (r) {
      if (!r.ok || !r.data.ok) {
        piForm.setMessage("fail", P("pf.registerFail",
          { why: esc((r.data.errors || [r.data.text || P("pf.unknownWhy")]).join("；")) }));
        return null;
      }
      if (!cfg.key) { return api("/api/pi/check?station=" + encodeURIComponent(S.memberName)); }
      return post("/api/secrets", { station: S.memberName, api_key: cfg.key }).then(function (r2) {
        if (!r2.ok || !r2.data.ok) {
          piForm.setMessage("fail", P("pf.keySaveFail", { why: esc(r2.data.text || P("pf.unknownWhy")) }));
          return null;
        }
        piForm.clearKey();                 /* 填过就不再留在页面里，更不进草稿 */
        setKeyed(true);                    /* key 存好了——之后测试失败也不丢，不逼用户重填 */
        return api("/api/pi/check?station=" + encodeURIComponent(S.memberName));
      });
    }).then(function (r) {
      if (!r) { return; }
      var d = r.data || {};
      var secs = ((Date.now() - t0) / 1000).toFixed(1);
      var raw = d.text && d.text !== "ok" ?
        '<details class="msg-detail"><summary>' + esc(P("pf.detail")) + "</summary><pre>" +
        esc(String(d.text).slice(0, 300)) + "</pre></details>" : "";
      if (r.ok && (d.ok || d.state === "ok")) {
        /* 盒子按模型平台的要求自动改过设置，就把改了什么一起说（d.text 是那句说明） */
        piForm.setMessage("ok", P("pf.connected", { model: esc(pi.model), n: secs }) +
          (d.text && d.text !== "ok" ? "<br>" + esc(d.text) : ""));
        readyUp(w);
      } else if (d.state === "limited") {
        /* 429 / 太忙：请求到了模型平台、密钥也认了——算连上，只提醒一句它这会儿在限流 */
        piForm.setMessage("ok", P("pf.connectedLimited", { model: esc(pi.model) }) + raw);
        readyUp(w);
      } else if (d.state === "unreachable") {
        /* 连不上不算招不了——这只猫先招进来，派给它的卡会排队等接口，连上自动开工 */
        piForm.setMessage("fail", P("pf.unreachable", { host: esc(d.host || pi.base_url || "?") }) + keptNote());
        readyUp(w);
      } else {
        var f = PI_FAIL[d.state] || PI_FAIL.unknown;
        /* 给用户看的只按状态说人话；平台原文收进默认折叠的详情（后端已脱敏、截到 300 字）。
           除了 key 本身不对，别的失败都带上「key 已经存好了」——别让人以为没存上、再填一遍 */
        piForm.setMessage("fail", P(f[1]) + P("pf.howToFix", { x: P(f[2]) }) +
          (d.state === "auth" ? "" : keptNote()) + raw);
      }
    });
  }
  function mountSchedBox(w, mode) {
    var box = w.$("#ob-sched-box");
    box.innerHTML =
      '<div class="card"><h3>' + esc(NS.tx("member.access.schedTitle")) + "</h3>" +
      '<label class="lb" for="ob-every">' + esc(NS.tx("member.access.schedEvery")) + "</label>" +
      '<input id="ob-every" type="number" min="5" value="' + esc(dget("m_every", 30)) + '">' +
      '<div class="msg hide" id="ob-sched-test"></div>' +
      '<div style="margin-top:8px"><button type="button" class="pxb main" id="ob-sched-test-btn">' +
      esc(NS.tx("member.access.test")) + "</button> " +
      '<button type="button" class="pxb small" id="ob-sched-help">' + esc(NS.tx("member.access.seeGuide")) + "</button></div>" +
      '<div class="card hide" id="ob-sched-guide" style="margin-top:10px">' +
      '<div class="lb">' + esc(NS.tx("member.access.schedPath")) + '</div><pre id="ob-sched-path"></pre>' +
      '<button type="button" class="pxb small" id="ob-copy-path">' + esc(NS.tx("member.access.copyPath")) + "</button>" +
      '<div class="lb" style="margin-top:10px">' + esc(NS.tx("member.access.schedPrompt")) + '</div><pre id="ob-sched-prompt"></pre>' +
      '<button type="button" class="pxb small" id="ob-copy-sched">' + esc(NS.tx("member.access.copyPrompt")) + "</button>" +
      '<ol id="ob-sched-steps" class="hint"></ol></div>' +
      '<p class="hint">' + esc(NS.tx("member.access.schedHint")) + "</p></div>";
    box.querySelector("#ob-every").onchange = function () { draft({ m_every: num(this.value, 30) }); };
    box.querySelector("#ob-sched-test-btn").onclick = function () { testSched(w); };
    box.querySelector("#ob-sched-help").onclick = function () { showSched(w); };
    box.querySelector("#ob-copy-path").onclick = function () { NS.copyText(box.querySelector("#ob-sched-path").textContent, this); };
    box.querySelector("#ob-copy-sched").onclick = function () { NS.copyText(box.querySelector("#ob-sched-prompt").textContent, this); };
    if (mode === "sched") { showSched(w); }
  }
  function showSched(w) {
    var box = w.$("#ob-sched-box");
    return api("/api/summon/" + encodeURIComponent(S.memberName) + NS.langParam()).then(function (r) {
      var d = r.data || {};
      box.querySelector("#ob-sched-path").textContent = d.exchange_dir || NS.tx("member.access.schedNoPath");
      box.querySelector("#ob-sched-prompt").textContent = d.prompt || NS.tx("member.access.schedNoPrompt");
      box.querySelector("#ob-sched-steps").innerHTML = (d.steps || []).map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("");
      box.querySelector("#ob-sched-guide").classList.remove("hide");
    });
  }
  function schedStation(every) {
    return { id: S.memberName || NS.defaultMemberBase() + "A", role: "member", client: "", runner: "scheduled", enabled: true,
             look: S.memberLook, lang: NS.lang(), runner_args: { every_min: every } };
  }
  function testSched(w) {
    var every = Math.max(5, num(w.$("#ob-every").value, 30));
    draft({ m_every: every, m_mode: "sched" });
    w.msg("#ob-sched-test", "wait", NS.tx("member.access.schedTesting"));
    post("/api/stations", schedStation(every)).then(function (r) {
      if (!r.ok || !r.data.ok) {
        w.msg("#ob-sched-test", "fail", NS.tx("member.access.saveFail",
          { why: esc((r.data.errors || [r.data.text || NS.tx("member.access.unknownWhy")]).join("；")) }));
        return;
      }
      return api("/api/stations").then(function (b) {
        var row = null;
        (b.data.stations || []).forEach(function (s) { if (s.id === S.memberName) { row = s; } });
        if (row && (row.last_scheduled_at || row.word_code === "on_duty_sched" || row.word_code === "running")) {
          w.msg("#ob-sched-test", "ok", NS.tx("member.access.schedOk", { state: esc(row.word) }));
          readyUp(w);
        } else {
          w.msg("#ob-sched-test", "wait", NS.tx("member.access.schedWait",
            { state: esc(row ? row.word : NS.tx("member.access.notFound")) }));
        }
        showSched(w);
      });
    });
  }
  function saveMember(w) {
    var mode = String(dget("m_mode", "pi"));
    var st = mode === "sched"
      ? schedStation(Math.max(5, num(w.$("#ob-every").value, 30)))
      : memberStation();
    if (mode !== "sched") {
      var cfg = piForm.read();
      savePiDraft(cfg);
      st.pi = cfg.pi;
      st.quota = cfg.quota;
    }
    return post("/api/stations", st).then(function (r) {
      if (!r.ok || !r.data.ok) {
        w.msg("#ob-m-msg", "fail", NS.tx("member.access.saveFail",
          { why: esc((r.data.errors || [r.data.text || NS.tx("member.access.unknownWhy")]).join("；")) }));
        return false;
      }
      S.memberSlot = (r.data.station || {}).slot || S.memberSlot;
      draft({ member_slot: S.memberSlot });
      NS.fillScene();
      return true;
    });
  }

  NS.stepRecruitMember = stepRecruitMember;
  NS.stepMemberAccess = stepMemberAccess;
})();
