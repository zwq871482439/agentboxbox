/* 上岗流程 · 打工猫那几步：招募（起名选样子）、接入方式（API key 自动跑 / 会话模式）、测试、保存。
   依赖 onboard-common.js（先加载）。 */
(function () {
  "use strict";
  var NS = window.BXOB;
  var S = NS.S;
  var $ = NS.$, esc = NS.esc, num = NS.num, api = NS.api, post = NS.post;
  var win = NS.win, catCard = NS.catCard, wireCat = NS.wireCat;
  var dget = NS.dget, draft = NS.draft;

  /* ================= 这一份文件的文案（中文 / 英文） ================= */
  NS.addTxt("member", {
    'access.advanced': ['高级', 'Advanced'],
    'access.apiAnthropic': ['Anthropic 兼容（Claude 格式）', 'Anthropic compatible (Claude format)'],
    'access.apiGemini': ['Google 兼容（Gemini 格式）', 'Google compatible (Gemini format)'],
    'access.apiKey': ['API key', 'API key'],
    'access.apiOpenai': ['OpenAI 兼容（大多数服务商）', 'OpenAI compatible (most providers)'],
    'access.apiResponses': ['OpenAI 兼容（Responses 新接口）', 'OpenAI compatible (new Responses API)'],
    'access.apiType': ['接口类型', 'API type'],
    'access.baseUrl': ['接口地址', 'API address'],
    'access.connected': ['连上了：{model}，用时 {n} 秒', 'Connected: {model}, took {n} s'],
    'access.connectedLimited': [
      '连上了：{model}，地址和密钥都对。服务商这会儿在限流或额度见底（429）；派卡时还这样，这只猫会先歇着，到点自己接着干。',
      'Connected: {model}, the address and the key are right. The provider is rate limiting right now or the quota is nearly used up (429);'
        + ' if that is still so when a card comes, this cat takes a break and carries on by itself later.'],
    'access.copyPath': ['复制路径', 'Copy the path'],
    'access.copyPrompt': ['复制这段话', 'Copy the text'],
    'access.ctx': ['上下文窗口', 'Context window'],
    'access.detail': ['详情', 'Details'],
    'access.doneBtn': ['接好了', 'Connected'],
    'access.failAuth': ['密钥不对', 'The key was rejected'],
    'access.failAuthFix': ['重新复制一个 API key 填进来，填了就会换掉旧的。', 'Paste a new API key — it replaces the old one.'],
    'access.failQuota': ['这个账号没额度了', 'This account has no credit left'],
    'access.failQuotaFix': ['去服务商的页面看看余额，充点值或者换个账号。', 'Check the balance on the provider page, top up or use another account.'],
    'access.failRoute': ['请求没到服务商', 'The request did not reach the provider'],
    'access.failRouteFix': ['检查接口地址、接口类型和模型名填对没有。', 'Check the API address, the API type and the model name.'],
    'access.failUnknown': ['没测出来', 'Could not test'],
    'access.failUnknownFix': ['把接口地址、模型名再看一遍，再点一次测试连接。', 'Check the API address and model name, then test again.'],
    'access.failUnreachable': ['连不上服务商的地址', 'Cannot reach the provider address'],
    'access.failUnreachableFix': ['检查接口地址有没有写错、这台电脑的网络通不通。', 'Check the API address and whether this computer is online.'],
    'access.howToFix': ['。怎么修：{x}', ' How to fix: {x}'],
    'access.keyHint': [
      'API key 存在这台电脑的 data/secrets.json 里，不进日志、不进接口返回，也不进上岗草稿。',
      'The API key is stored in data/secrets.json on this computer. ' +
        'It never reaches the log, the API replies or the onboarding draft.'
    ],
    'access.keyKept': [
      '<br>API key 已经存好了，不用重填；要换的话在 key 框里重新填一个就行。',
      '<br>The API key is already saved, do not fill it in again; ' +
        'to replace it, type a new one in the key box.'
    ],
    'access.keyPlaceholder': ['存在这台电脑的 data/secrets.json 里', 'Stored in data/secrets.json on this computer'],
    'access.keyPlaceholderSet': ['已存好，要换就重新填', 'Already stored, fill in a new one to replace it'],
    'access.keySaveFail': ['工位登记了，但密钥没存上：{why}', 'The station is registered, but the key was not saved: {why}'],
    'access.maxOut': ['最大输出', 'Max output'],
    'access.missBase': ['接口地址', 'the API address'],
    'access.missCtx': ['上下文窗口要填正整数', 'a positive context window'],
    'access.missFields': ['先补齐：{x}', 'Fill in first: {x}'],
    'access.missMax': ['最大输出要填正整数', 'a positive max output'],
    'access.missModel': ['模型', 'the model'],
    'access.modePi': ['用 API key 自动跑', 'Run it with an API key'],
    'access.modePiDesc': [
      '盒子自己拉起打工猫（用的是 Pi），派活就开工。服务商、密钥、模型在下面填。',
      'The box starts the worker by itself (with Pi) and work begins as soon as there is some. ' +
        'Fill in the provider, the key and the model below.'
    ],
    'access.modeSched': ['会话模式', 'Check-in mode'],
    'access.modeSchedDesc': [
      '你的 AI 软件每隔几分钟开一个新对话来领卡，不分是哪个软件，也不用 API key。',
      'Your AI app opens a new chat every few minutes to pick up cards — whichever app it is, ' +
        'and no API key needed.'
    ],
    'access.model': ['模型', 'Model'],
    'access.notFound': ['查不到这个工位', 'station not found'],
    'access.piTitle': ['Pi 接口配置', 'Pi connection'],
    'access.planCustom': ['自定义', 'Custom'],
    'access.planGlm': ['智谱 GLM 套餐', 'Zhipu GLM plan'],
    'access.planKimi': ['Kimi 套餐', 'Kimi plan'],
    'access.planMiniMax': ['MiniMax 套餐', 'MiniMax plan'],
    'access.provider': ['服务商', 'Provider'],
    'access.quotaAdapter': ['用哪种查询', 'How to check'],
    'access.quotaAfterRun': ['每轮跑完查一次', 'Check after each run'],
    'access.quotaBy': ['按 {x} 查', 'Checked against {x}'],
    'access.quotaEvery': ['间隔分钟', 'Every (minutes)'],
    'access.quotaInterval': ['每 N 分钟查一次', 'Check every N minutes'],
    'access.quotaMode': ['额度查询（套餐还剩多少）', 'Check remaining quota'],
    'access.quotaOff': ['关', 'Off'],
    'access.ready': ['已就绪', 'Ready'],
    'access.readyMsg': [
      '先测一下：Pi 点「测试连接」，会话模式点「测试」，测通了才算接好',
      'Test first: click “Test connection” for Pi, ' +
        'or “Test” for check-in mode — only then it counts as connected'
    ],
    'access.registerFail': ['登记失败：{why}', 'Could not register: {why}'],
    'access.saveFail': ['保存失败：{why}', 'Could not save: {why}'],
    'access.schedEvery': ['每隔几分钟来领一次活', 'Pick up cards every few minutes'],
    'access.schedHint': [
      '建好定时任务后，等它第一次跑完（它会写一个记号文件），再点一次「测试」就能看到「来过了」。',
      'After you set up the timer, wait for its first run (it writes a marker file), ' +
        'then click “Test” again to see that it has been here.'
    ],
    'access.schedNoPath': ['（先点下面的「测试」登记工位，这里就有路径了）', '(click “Test” below to register the station, then the path shows up)'],
    'access.schedNoPrompt': ['（先点下面的「测试」登记工位，再回来复制）', '(click “Test” below to register the station, then come back to copy it)'],
    'access.schedOk': ['来读过了：{state}', 'It has been here: {state}'],
    'access.schedPath': ['任务单文件路径', 'Job list file path'],
    'access.schedPrompt': ['贴进定时任务的那段话', 'Text for the scheduled task'],
    'access.schedTesting': ['正在登记工位并检查…', 'Registering the station and checking…'],
    'access.schedTitle': ['会话模式', 'Check-in mode'],
    'access.schedWait': [
      '还没来过（{state}）。照说明在客户端里建好定时任务，等它第一次跑完（它每次来都会留个记号），这只猫才算接上；再点一次「测试」就能看到「来过了」。',
      'Not here yet ({state}). ' +
        'Set up the timer in your app as described and wait for its first run (it leaves a marker each time); ' +
        'then this worker is connected — click “Test” again to see that it has been here.'
    ],
    'access.seeGuide': ['查看说明', 'Show the guide'],
    'access.test': ['测试', 'Test'],
    'access.testConn': ['测试连接', 'Test connection'],
    'access.testing': ['正在登记工位并测试连接…', 'Registering the station and testing…'],
    'access.title': ['打工猫接入方式', 'How the worker cat connects'],
    'access.unknownWhy': ['未知原因', 'unknown reason'],
    'access.unreachable': [
      '连不上接口地址 {host}。这只猫可以先招进来，派给它的卡会排队，等这台电脑连得上接口就自动开工。',
      'Cannot reach {host}. ' +
        'You can still hire this cat: its cards will queue and start as soon as this ' +
        'computer can reach the address.'
    ],
    'access.whyMember': [
      '首领只派活、不自己干：派出去的卡要打工猫来干，所以至少要招一只才能派卡。手上没有 API key 也行，下一步还有「会话模式」这种接法。',
      'The leader only hands out work, it does not do it itself: a card needs a worker cat, ' +
        'so hire at least one before you can hand out work. ' +
        'No API key yet? That is fine — the next step has a “check-in mode” option too.'
    ],
    'recruit.acc': ['换一套配饰', 'Shuffle the extras'],
    'recruit.defaultWorker': ['打工猫猫', 'Worker'],
    'recruit.nameEmpty': ['给打工猫起个名字吧', 'Give the worker cat a name'],
    'recruit.nameHint': ['默认「{name}」，可改。已经有的名字会提醒你换一个。', 'Default “{name}”, you can change it. Names already in use are flagged.'],
    'recruit.nameLabel': ['打工猫的名字', 'Worker cat name'],
    'recruit.nameTaken': ['已经有叫「{name}」的猫了，换一个名字吧', 'A cat called “{name}” already exists, pick another name'],
    'recruit.title': ['招募打工猫猫', 'Hire a worker cat'],
  });

  var PI_APIS = ["anthropic-messages", "openai-completions", "openai-responses", "google-generative-ai"];
  /* 接口类型说人话，值不变（核心 pi_config 认的就是这几个值） */
  var PI_API_LABEL = {
    "anthropic-messages": "member.access.apiAnthropic",
    "openai-completions": "member.access.apiOpenai",
    "openai-responses": "member.access.apiResponses",
    "google-generative-ai": "member.access.apiGemini"
  };
  var QUOTA_ADAPTERS = ["kimi_code", "glm_coding_plan", "minimax_token_plan", "custom"];
  var QUOTA_ADAPTER_LABEL = {
    kimi_code: "member.access.planKimi", glm_coding_plan: "member.access.planGlm",
    minimax_token_plan: "member.access.planMiniMax", custom: "member.access.planCustom"
  };
  /* 额度查询按主机名认服务商（跟核心 quota 的口径同一套）：认得出就不用让人选 */
  var QUOTA_HOSTS = {
    "api.kimi.com": "kimi_code", "open.bigmodel.cn": "glm_coding_plan",
    "minimaxi.com": "minimax_token_plan", "minimax.cn": "minimax_token_plan"
  };
  /* Pi 测试失败按退出码说人话：10 忙 / 11 没额度 / 12 连不上 / 13 key 不对 / 14 被路由拦下 */
  var PI_FAIL = {
    quota: [11, "access.failQuota", "access.failQuotaFix"],
    unreachable: [12, "access.failUnreachable", "access.failUnreachableFix"],
    auth: [13, "access.failAuth", "access.failAuthFix"],
    route: [14, "access.failRoute", "access.failRouteFix"],
    unknown: [1, "access.failUnknown", "access.failUnknownFix"]
  };
  NS.PI_FAIL = PI_FAIL;

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
      var no = num(dget("member_cat"), 0) || NS.randomCat(used);
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
  /* 额度查询按接口地址的主机名认服务商（跟核心同一套口径） */
  function quotaHost(url) {
    var s = String(url || "").trim().toLowerCase();
    s = s.replace(/^[a-z][a-z0-9+.-]*:\/\//, "");
    s = s.split("/")[0].split("?")[0].split("#")[0];
    if (s.indexOf("@") >= 0) { s = s.split("@").pop(); }
    return s.replace(/:\d+$/, "");
  }
  function quotaAdapterFor(url) {
    /* 按主机名认额度查询方式：主机名完全一样，或者以它打头的一个子域；认不出就返回空（让人自己挑） */
    var host = quotaHost(url);
    if (!host) { return ""; }
    var keys = Object.keys(QUOTA_HOSTS);
    for (var i = 0; i < keys.length; i++) {
      var h = keys[i];
      if (host === h || host.slice(-(h.length + 1)) === "." + h) { return QUOTA_HOSTS[h]; }
    }
    return "";
  }
  function syncQuotaPick(box) {
    /* 额度查询选「关」→ 整行藏起来；开着 → 按服务商自动定：
       认得出只写一行「按 XX 的套餐查」，认不出才给选择框 */
    var mode = box.querySelector("#ob-qmode").value;
    var row = box.querySelector("#ob-qadapter-f");
    var note = box.querySelector("#ob-qadapter-note");
    var sel = box.querySelector("#ob-qadapter");
    var off = mode === "off";
    row.classList.toggle("hide", off);
    note.classList.toggle("hide", off);
    if (off) { return; }
    var known = quotaAdapterFor(box.querySelector("#ob-base").value);
    if (known) {
      sel.value = known;
      row.classList.add("hide");
      note.classList.remove("hide");
      note.textContent = NS.tx("member.access.quotaBy",
        { x: QUOTA_ADAPTER_LABEL[known] ? NS.tx(QUOTA_ADAPTER_LABEL[known]) : known });
    } else {
      row.classList.remove("hide");
      note.classList.add("hide");
    }
  }
  function mountPiBox(w) {
    var q = dget("m_quota", {}) || {};
    var apiCur = String(dget("m_api", PI_APIS[0]));          /* 只能有一个默认：每个 option 都 selected 会选中最后一个 */
    var known0 = quotaAdapterFor(dget("m_base", ""));       /* 草稿里的地址认得出的服务商 */
    var adapterCur = String(q.adapter || known0 || "custom");
    var box = w.$("#ob-pi-box");
    box.innerHTML =
      '<div class="card"><h3>' + esc(NS.tx("member.access.piTitle")) + "</h3>" +
      '<div class="grid2">' +
      '<div><label class="lb">' + esc(NS.tx("member.access.provider")) + '</label><div id="ob-prov"></div></div>' +
      '<div><label class="lb">' + esc(NS.tx("member.access.model")) + '</label><div id="ob-model"></div></div></div>' +
      '<div class="grid2 frow">' +
      '<div><label class="lb" for="ob-base">' + esc(NS.tx("member.access.baseUrl")) + "</label>" +
      '<input id="ob-base" type="text" value="' + esc(dget("m_base", "")) + '"></div>' +
      '<div><label class="lb" for="ob-api">' + esc(NS.tx("member.access.apiType")) + '</label><select id="ob-api">' +
      PI_APIS.map(function (a) {
        return '<option value="' + esc(a) + '"' + (apiCur === a ? " selected" : "") + ">" +
          esc(PI_API_LABEL[a] ? NS.tx(PI_API_LABEL[a]) : a) + "</option>";
      }).join("") + "</select></div></div>" +
      '<div class="frow"><label class="lb" for="ob-key">' + esc(NS.tx("member.access.apiKey")) + "</label>" +
      '<input id="ob-key" type="password" autocomplete="off" placeholder="' +
      esc(NS.tx("member.access.keyPlaceholder")) + '"></div>' +
      '<div class="grid2 frow">' +
      '<div><label class="lb" for="ob-qmode">' + esc(NS.tx("member.access.quotaMode")) + '</label><select id="ob-qmode">' +
      [["off", "member.access.quotaOff"], ["after_run", "member.access.quotaAfterRun"],
       ["interval", "member.access.quotaInterval"]].map(function (p) {
        return '<option value="' + p[0] + '"' + ((q.mode || "off") === p[0] ? " selected" : "") + ">" +
          esc(NS.tx(p[1])) + "</option>";
      }).join("") + "</select></div>" +
      '<div id="ob-qadapter-f" class="hide"><label class="lb" for="ob-qadapter">' +
      esc(NS.tx("member.access.quotaAdapter")) + '</label><select id="ob-qadapter">' +
      QUOTA_ADAPTERS.map(function (a) {
        return '<option value="' + esc(a) + '"' + (adapterCur === a ? " selected" : "") + ">" +
          esc(QUOTA_ADAPTER_LABEL[a] ? NS.tx(QUOTA_ADAPTER_LABEL[a]) : a) + "</option>";
      }).join("") + "</select></div></div>" +
      '<div id="ob-qadapter-note" class="hint hide"></div>' +
      '<div id="ob-qevery-f" class="frow' + (q.mode === "interval" ? "" : " hide") + '">' +
      '<label class="lb" for="ob-qevery">' + esc(NS.tx("member.access.quotaEvery")) + '</label>' +
      '<input id="ob-qevery" type="number" min="1" value="' + esc(q.interval_min || 30) + '"></div>' +
      '<details class="adv"><summary>高级</summary><div class="grid2 frow">' +
      '<div><label class="lb" for="ob-ctx">' + esc(NS.tx("member.access.ctx")) + '</label>' +
      '<input id="ob-ctx" type="number" min="1" value="' + esc(dget("m_ctx", 200000)) + '"></div>' +
      '<div><label class="lb" for="ob-max">' + esc(NS.tx("member.access.maxOut")) + '</label>' +
      '<input id="ob-max" type="number" min="1" value="' + esc(dget("m_max", 32000)) + '"></div>' +
      "</div></details>" +
      '<div class="msg hide" id="ob-pi-test"></div>' +
      '<div class="frow"><button type="button" class="pxb main" id="ob-pi-test-btn">' +
      esc(NS.tx("member.access.testConn")) + "</button></div>" +
      '<p class="hint">' + esc(NS.tx("member.access.keyHint")) + "</p></div>";
    /* 高级那栏的标题跟着语言走（中文默认就是上面那句） */
    var adv = box.querySelector("details.adv > summary");
    if (adv) { adv.textContent = NS.tx("member.access.advanced"); }

    if (window.BXProviders) {
      S.provMount = window.BXProviders.mount({
        provBox: box.querySelector("#ob-prov"),
        modelBox: box.querySelector("#ob-model"),
        provider: String(dget("m_provider", "")),
        model: String(dget("m_model_id", "")),
        onProvider: function (p) {
          draft({ m_provider: p ? p.id : "" });
          if (!p) { return; }
          if (p.api) { box.querySelector("#ob-base").value = p.api; }
          if (p.api_type) { box.querySelector("#ob-api").value = p.api_type; }
          syncQuotaPick(box);
          collectPi(box);
        },
        onModel: function (m) {
          draft({ m_model_id: m ? m.id : "" });
          /* 清单里的模型带着窗口大小：选了就把上下文和最大输出一起填上 */
          if (m) {
            if (m.context) { box.querySelector("#ob-ctx").value = m.context; }
            if (m.output) { box.querySelector("#ob-max").value = m.output; }
          }
          collectPi(box);
        }
      });
    }
    ["#ob-base", "#ob-api", "#ob-ctx", "#ob-max",
     "#ob-qadapter", "#ob-qevery", "#ob-model"].forEach(function (sel) {
      var el = box.querySelector(sel);
      if (el) { el.addEventListener("change", function () { collectPi(box); }); }
    });
    box.querySelector("#ob-base").addEventListener("change", function () { syncQuotaPick(box); });
    box.querySelector("#ob-qmode").onchange = function () {
      box.querySelector("#ob-qevery-f").classList.toggle("hide", this.value !== "interval");
      syncQuotaPick(box);
      collectPi(box);
    };
    box.querySelector("#ob-pi-test-btn").onclick = function () { testPi(w); };
    syncQuotaPick(box);
    /* 接着做（刷新 / 关掉再开）时这只猫可能已经存过 key 了——问一句核心，
       存过就把 key 框的占位换成「已存好」，测试也不用再填 key */
    api("/api/stations").then(function (b) {
      var row = null;
      ((b.data || {}).stations || []).forEach(function (s) { if (s.id === S.memberName) { row = s; } });
      setKeyed(box, !!(row && row.has_key));
    });
  }
  function collectPi(box) {
    function val(sel) { var el = box.querySelector(sel); return el ? String(el.value == null ? "" : el.value).trim() : ""; }
    /* 清单里选的服务商 / 模型要记上：核心按 provider_id 算服务商 key，余量、价格都靠它 */
    var p = S.provMount && S.provMount.provider && S.provMount.provider();
    var mo = S.provMount && S.provMount.model && S.provMount.model();
    var pi = {
      base_url: val("#ob-base"),
      api: box.querySelector("#ob-api").value,
      /* 清单里的模型存它的 id：下拉框里显示的是名字（Kimi K3），存下的要是 id（k3）；手动填写才用框里的字 */
      model: (mo && mo.id) ? String(mo.id) : val("#ob-model input"),
      context_window: num(val("#ob-ctx"), 200000),
      max_tokens: num(val("#ob-max"), 32000),
      reasoning: (mo && typeof mo.reasoning === "boolean") ? mo.reasoning : true
    };
    if (p && p.id) { pi.provider_id = String(p.id); }
    if (mo && mo.id) { pi.model_id = String(mo.id); }
    draft({
      m_base: pi.base_url, m_api: pi.api, m_model: pi.model,
      m_ctx: pi.context_window, m_max: pi.max_tokens
    });
    return pi;
  }

  function collectQuota(box) {
    var mode = box.querySelector("#ob-qmode").value;
    /* 按服务商自动定查询方式；认得出就用它，认不出才用用户挑的 */
    var known = quotaAdapterFor(box.querySelector("#ob-base").value);
    var sel = box.querySelector("#ob-qadapter");
    var q = { mode: mode, adapter: known || (sel ? sel.value : "custom") };
    if (mode === "interval") { q.interval_min = Math.max(1, num(box.querySelector("#ob-qevery").value, 30)); }
    draft({ m_quota: q });          /* 记进草稿：刷新后额度查询的挑法还在 */
    return q;
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
  function setKeyed(box, on) {
    S.memberHasKey = !!on;
    var el = box && box.querySelector("#ob-key");
    if (el) {
      el.placeholder = S.memberHasKey ? NS.tx("member.access.keyPlaceholderSet") : NS.tx("member.access.keyPlaceholder");
    }
  }
  function keptNote() {
    return S.memberHasKey ? NS.tx("member.access.keyKept") : "";
  }
  function testPi(w) {
    var box = w.$("#ob-pi-box");
    var pi = collectPi(box);
    var miss = [];
    if (!pi.base_url) { miss.push(NS.tx("member.access.missBase")); }
    if (!pi.model) { miss.push(NS.tx("member.access.missModel")); }
    if (!(pi.context_window > 0)) { miss.push(NS.tx("member.access.missCtx")); }
    if (!(pi.max_tokens > 0)) { miss.push(NS.tx("member.access.missMax")); }
    if (!box.querySelector("#ob-key").value.trim() && !S.memberHasKey) { miss.push(NS.tx("member.access.apiKey")); }
    if (miss.length) { w.msg("#ob-pi-test", "fail", NS.tx("member.access.missFields", { x: esc(miss.join("、")) })); return; }
    w.msg("#ob-pi-test", "wait", NS.tx("member.access.testing"));
    var t0 = Date.now();
    var st = memberStation();
    st.pi = pi;
    st.quota = collectQuota(box);
    post("/api/stations", st).then(function (r) {
      if (!r.ok || !r.data.ok) {
        w.msg("#ob-pi-test", "fail", NS.tx("member.access.registerFail",
          { why: esc((r.data.errors || [r.data.text || NS.tx("member.access.unknownWhy")]).join("；")) }));
        return null;
      }
      var key = box.querySelector("#ob-key").value.trim();
      if (!key) { return api("/api/pi/check?station=" + encodeURIComponent(S.memberName)); }
      return post("/api/secrets", { station: S.memberName, api_key: key }).then(function (r2) {
        if (!r2.ok || !r2.data.ok) {
          w.msg("#ob-pi-test", "fail", NS.tx("member.access.keySaveFail",
            { why: esc(r2.data.text || NS.tx("member.access.unknownWhy")) }));
          return null;
        }
        box.querySelector("#ob-key").value = "";         /* 填过就不再留在页面里，更不进草稿 */
        setKeyed(box, true);                                 /* key 存好了——之后测试失败也不丢，不逼用户重填 */
        return api("/api/pi/check?station=" + encodeURIComponent(S.memberName));
      });
    }).then(function (r) {
      if (!r) { return; }
      var d = r.data || {};
      var secs = ((Date.now() - t0) / 1000).toFixed(1);
      var raw = d.text && d.text !== "ok" ?
        '<details class="msg-detail"><summary>' + esc(NS.tx("member.access.detail")) + "</summary><pre>" +
        esc(String(d.text).slice(0, 300)) + "</pre></details>" : "";
      if (r.ok && (d.ok || d.state === "ok")) {
        /* 盒子按服务商的要求自动改过设置，就把改了什么一起说（d.text 是那句说明） */
        w.msg("#ob-pi-test", "ok", NS.tx("member.access.connected", { model: esc(pi.model), n: secs }) +
          (d.text && d.text !== "ok" ? "<br>" + esc(d.text) : ""));
        readyUp(w);
      } else if (d.state === "limited") {
        /* 429 / 太忙：请求到了服务商、密钥也认了——算连上，只提醒一句它这会儿在限流 */
        w.msg("#ob-pi-test", "ok", NS.tx("member.access.connectedLimited", { model: esc(pi.model) }) + raw);
        readyUp(w);
      } else if (d.state === "unreachable") {
        /* 连不上不算招不了——这只猫先招进来，派给它的卡会排队等接口，连上自动开工 */
        w.msg("#ob-pi-test", "fail", NS.tx("member.access.unreachable",
          { host: esc(d.host || pi.base_url || "?") }) + keptNote());
        readyUp(w);
      } else {
        var f = PI_FAIL[d.state] || PI_FAIL.unknown;
        /* 给用户看的只按状态说人话；服务商原文收进默认折叠的详情（后端已脱敏、截到 300 字）。
           除了 key 本身不对，别的失败都带上「key 已经存好了」——别让人以为没存上、再填一遍 */
        w.msg("#ob-pi-test", "fail", NS.tx(f[1]) + NS.tx("member.access.howToFix", { x: NS.tx(f[2]) }) +
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
        w.msg("#ob-sched-test", "fail", NS.tx("member.access.registerFail",
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
    var box = w.$("#ob-pi-box");
    if (mode !== "sched") {
      st.pi = collectPi(box);
      st.quota = collectQuota(box);
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
