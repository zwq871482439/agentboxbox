/* 上岗流程 · 首领那几步：欢迎（定位一句话）、第 1 步装进编程助手（页签 + 等它连上 + 已连上）、挑样子小窗。
   依赖 onboard-common.js（先加载）。 */
(function () {
  "use strict";
  var NS = window.BXOB;
  var S = NS.S;
  var esc = NS.esc, num = NS.num, api = NS.api, post = NS.post;
  var win = NS.win, catCard = NS.catCard, wireCat = NS.wireCat;
  var dget = NS.dget, draft = NS.draft;

  /* 页签 / 流程条 / 小链接这一小块样式从 JS 注进 head（窗口的样式表不归这组文件管），只挂在 #bx-onboard 下 */
  var CSS_DONE = false;
  function injectCss() {
    if (CSS_DONE) { return; }
    CSS_DONE = true;
    var s = document.createElement("style");
    s.textContent = [
      "#bx-onboard .ob-one{font-size:16px;font-weight:700;color:#2b1d12;margin:4px 0 6px}",
      "#bx-onboard .ob-flow{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:10px 0 4px}",
      "#bx-onboard .ob-flow .n{border:2px solid #2b1d12;background:#f0e4c6;box-shadow:2px 2px 0 rgba(0,0,0,.25);",
      "padding:2px 8px;font-size:12.5px;color:#2b1d12;font-weight:700}",
      "#bx-onboard .ob-flow .a{color:#4a3728;font-size:12.5px}",
      "#bx-onboard .ob-tabs{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 8px}",
      "#bx-onboard .ob-tab{padding:3px 10px;background:#6b4a2f;color:#fff8e7;border:2px solid #2b1d12;",
      "box-shadow:2px 2px 0 rgba(0,0,0,.35);font-size:12.5px}",
      "#bx-onboard .ob-tab:hover{background:#7d5836}",
      "#bx-onboard .ob-tab.on{background:#3f9b4f;color:#fff}",
      "#bx-onboard .ob-link{background:none;border:0;padding:0;color:#3b2a1a;font:inherit;font-size:12.5px;",
      "text-decoration:underline;text-underline-offset:3px;cursor:pointer}"
    ].join("");
    document.head.appendChild(s);
  }

  /* 装进哪家：页签就是客户端；「其他」不记客户端 */
  /* 名字从共用的客户端名字表（util.js）取，这里只定哪几家有页签 */
  var TABS = ["cursor", "claude-code", "codex", ""].map(function (k) { return { key: k }; });
  function labelOf(key) {
    return key ? window.BXu.clientLabel(key) : NS.tx("lead.install.tabOther");
  }

  /* ---------- 欢迎 ---------- */
  function stepWelcome() {
    return new Promise(function (res) {
      injectCss();
      function paint() {
        var steps = [NS.tx("lead.welcome.step1"), NS.tx("lead.welcome.step2"), NS.tx("lead.welcome.step3")];
        var flow = [["n", "lead.welcome.flow1"], ["a", "lead.welcome.flowA1"], ["n", "lead.welcome.flow2"],
          ["a", "lead.welcome.flowA2"], ["n", "lead.welcome.flow3"]];
        var w = win({
          title: "欢迎来到猫猫盒子",
          titleKey: "lead.welcome.title",
          body: '<p class="ob-one">' + esc(NS.tx("lead.welcome.one")) + "</p>" +
            "<p>" + esc(NS.tx("lead.welcome.intro")) + "</p>" +
            '<div class="ob-flow">' + flow.map(function (p) {
              return '<span class="' + p[0] + '">' + esc(NS.tx(p[1])) + "</span>";
            }).join("") + "</div>" +
            '<p class="lb" style="margin-top:10px">' + esc(NS.tx("lead.welcome.next")) + "</p>" +
            '<ol id="ob-intro-steps">' + steps.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") +
            "</ol>" + NS.langSwitch(),
          buttons: [{ text: NS.tx("lead.welcome.start"), main: true, on: function (x) { x.close(); res(); } }]
        });
        NS.wireLang(w);
        NS.rerender = paint;      /* 换语言：欢迎窗口重画一遍 */
      }
      paint();
    });
  }

  /* ---------- 工位存取 ----------
     进这一步就把编程助手的工位自动建好（默认名字和样子）；之后只在挑完样子 / 换页签时再存。
     盒子不替用户改任何 AI 软件的设置：装进哪家由用户自己点、自己跑。 */
  function leaderStation(client) {
    return { id: S.leaderName, role: "leader", client: client, runner: "manual", enabled: true,
      look: S.leaderLook, lang: NS.lang() };
  }
  /* 存失败了在 msgSel 那个框里说清原因，旁边给「重试」；重试做的事记在 onSaveRetry（点按钮才触发） */
  var onSaveRetry = null;
  document.addEventListener("click", function (e) {
    var b = e.target && e.target.closest ? e.target.closest("#ob-save-retry") : null;
    if (b && onSaveRetry) { onSaveRetry(); }
  });
  function saveLeaderStation(client, msgSel, afterOk) {
    return post("/api/stations", leaderStation(client)).then(function (r) {
      var el = document.querySelector("#bx-onboard " + msgSel);
      if (r.ok && r.data.ok) {
        if (el) { el.className = "msg hide"; }
        if (afterOk) { afterOk(); }
        return true;
      }
      if (!el) { return false; }
      var why = esc((r.data.errors || [r.data.text || NS.tx("lead.install.unknownWhy")])
        .join(NS.tx("lead.common.listSep")));
      el.className = "msg fail";
      el.innerHTML = NS.tx("lead.install.saveFail", { why: why }) +
        ' <button type="button" class="pxb small" id="ob-save-retry">' + esc(NS.tx("lead.install.retry")) + "</button>";
      onSaveRetry = function () { saveLeaderStation(client, msgSel, afterOk); };
      return false;
    });
  }

  /* ---------- 第 1 步：装进你的编程助手 ---------- */
  function stepInstallLeader() {
    return new Promise(function (res) {
      injectCss();
      var client = String(dget("leader_client", ""));
      var tab = TABS.some(function (t) { return t.key === client && client; }) ? client : "cursor";
      draft({ leader_client: tab });   /* 记住停在哪家：收尾窗口给不给 Cursor 派活按钮看它 */
      var t0 = Date.now(), timer = null, hinted = false, checked = false, stopped = false;
      if (dget("leader_cat") != null) {
        S.leaderLook = { cat: num(dget("leader_cat"), 1), acc: dget("leader_acc", {}) };
      }
      S.leaderName = String(dget("leader_name", "")) || S.leaderName || NS.defaultLeaderName();

      function q(s) { return document.querySelector("#bx-onboard " + s); }
      function waitedText(s) {
        return s < 60 ? NS.tx("lead.install.waitedSec", { n: s })
          : NS.tx("lead.install.waitedMin", { n: Math.floor(s / 60) });
      }

      function paint() {
        var tabs = '<div class="ob-tabs" id="ob-tabs">' + TABS.map(function (t) {
          return '<button type="button" class="ob-tab' + (t.key === tab ? " on" : "") +
            '" data-tab="' + t.key + '">' + esc(labelOf(t.key)) + "</button>";
        }).join("") + "</div>";
        var w = win({
          title: "第 1 步：装进你的编程助手",
          titleKey: "lead.install.title",
          body: '<p class="hint" id="ob-prep" style="margin:10px 0 8px">' + esc(NS.tx("lead.install.prep")) + "</p>" +
            '<div class="tri">' +
            '<div class="card"><div class="step">1</div><h3>' + esc(NS.tx("lead.install.step1")) + "</h3>" + tabs +
            '<div id="ob-ins-body"></div><div class="msg hide" id="ob-ins-msg"></div></div>' +
            '<div class="card" id="ob-wait"><div class="step">2</div><h3>' + esc(NS.tx("lead.install.step2")) + "</h3>" +
            '<canvas class="av" width="96" height="96"></canvas>' +
            '<p><span class="dots"><span></span><span></span><span></span></span> <span id="ob-wait-t"></span></p>' +
            '<p class="hint">' + esc(NS.tx("lead.install.waitHint")) + "</p>" +
            '<p class="hint"><button type="button" class="ob-link" id="ob-look">' +
            esc(NS.tx("lead.install.lookLink")) + "</button></p></div>" +
            '<div class="card hide done" id="ob-ok"><div class="step">3</div><h3 id="ob-ok-t"></h3>' +
            "<p>" + esc(NS.tx("lead.install.okBody")) + "</p>" +
            '<button type="button" class="pxb main" id="ob-next">' + esc(NS.tx("lead.install.nextBtn")) +
            "</button></div></div>" +
            '<div id="ob-late-wrap">' +
            '<div class="msg hide" id="ob-wait-late"></div>' +
            '<div class="hide" id="ob-late-btns" style="margin-top:8px">' +
            '<button type="button" class="pxb small" id="ob-help">' + esc(NS.tx("lead.install.checkApp")) +
            "</button></div>" +
            '<div class="card hide" id="ob-help-box" style="margin-top:10px"></div></div>'
        });
        NS.rerender = null;
        NS.drawCat(w.$("#ob-wait canvas"), { cat: S.leaderLook.cat, acc: S.leaderLook.acc, lead: true });
        w.$$("#ob-tabs .ob-tab").forEach(function (b) {
          b.onclick = function () {
            tab = b.getAttribute("data-tab");
            w.$$("#ob-tabs .ob-tab").forEach(function (x) { x.classList.toggle("on", x === b); });
            draft({ leader_client: tab });
            saveLeaderStation(tab, "#ob-ins-msg", loadInstall);
            loadInstall();
          };
        });
        w.$("#ob-look").onclick = function () { pickLeaderLook(tab).then(paint); };
        w.$("#ob-next").onclick = function () { stop(); w.close(); res(); };
        w.$("#ob-help").onclick = showHelp;
        loadInstall();
        apply();
      }

      /* 第 1 栏：按页签给一键装 / 安装命令 / 配置片段。读失败能重试 */
      function loadInstall() {
        var box = q("#ob-ins-body");
        if (!box) { return; }
        var msg = q("#ob-ins-msg");
        if (msg) { msg.className = "msg hide"; }
        box.innerHTML = '<p class="hint">' + esc(NS.tx("lead.install.loading")) + "</p>";
        /* 「其他」给通用 JSON 片段：这几家 snippet 型客户端的片段一个样，取一家的就行 */
        var ask = tab || "kimi-code";
        api("/api/connectors/snippet?client=" + encodeURIComponent(ask) +
          "&station=" + encodeURIComponent(S.leaderName) + NS.langParam2()).then(function (r) {
          if (!box.isConnected) { return; }
          var d = r.data || {};
          if (!r.ok || !d.snippet) {
            box.innerHTML = '<p class="hint">' + esc(NS.tx("lead.install.loadFail",
              { why: d.text || d.code || NS.tx("lead.install.down") })) + "</p>" +
              '<button type="button" class="pxb small" id="ob-ins-retry">' + esc(NS.tx("lead.install.retry")) + "</button>";
            var rb = document.getElementById("ob-ins-retry");
            if (rb) { rb.onclick = loadInstall; }
            return;
          }
          if (tab === "cursor") {
            box.innerHTML = '<p><a class="pxb main" id="ob-install-btn" href="' + esc(d.install_link || "#") + '">' +
              esc(NS.tx("lead.install.cursorBtn")) + "</a></p>" +
              '<p class="hint">' + esc(NS.tx("lead.install.cursorHint")) + "</p>";
          } else if (d.install_cmd) {
            box.innerHTML = '<p class="hint">' + esc(NS.tx("lead.install.cmdHint")) + "</p>" +
              "<pre>" + esc(d.install_cmd) + "</pre>" +
              '<button type="button" class="pxb small" id="ob-copy-cmd">' + esc(NS.tx("lead.install.copyCmd")) + "</button>";
            var cb = document.getElementById("ob-copy-cmd");
            if (cb) { cb.onclick = function () { NS.copyText(d.install_cmd, cb); }; }
          } else {
            box.innerHTML = '<p class="hint">' + esc(NS.tx("lead.install.otherHint")) + "</p>" +
              "<pre>" + esc(d.snippet) + "</pre>" +
              '<button type="button" class="pxb small" id="ob-copy-cmd">' + esc(NS.tx("lead.install.copySnippet")) +
              "</button>";
            var cb2 = document.getElementById("ob-copy-cmd");
            if (cb2) { cb2.onclick = function () { NS.copyText(d.snippet, cb2); }; }
          }
        });
      }

      /* 三栏跟着状态走：没握手等第 2 栏，握过手亮第 3 栏 */
      function apply() {
        var wait = q("#ob-wait"), ok = q("#ob-ok");
        if (!wait || !ok) { return; }
        var connected = !!(S.state && S.state.leader && !S.state.leader_unshaken);
        wait.classList.toggle("hide", connected);
        var late = q("#ob-late-wrap");
        if (late) { late.classList.toggle("hide", connected); }
        ok.classList.toggle("hide", !connected);
        if (connected) {
          q("#ob-ok-t").textContent = tab ? NS.tx("lead.install.okTitle", { app: labelOf(tab) })
            : NS.tx("lead.install.okAny");
          if (S.state.leader_link === "http" && !q("#ob-via-http")) {
            var v = document.createElement("div");
            v.className = "msg wait";
            v.id = "ob-via-http";
            v.innerHTML = NS.tx("lead.install.viaHttp");
            ok.insertBefore(v, q("#ob-next"));
          }
          return;
        }
        var wt = q("#ob-wait-t");
        if (wt) { wt.textContent = NS.tx("lead.install.waited", { n: waitedText(Math.floor((Date.now() - t0) / 1000)) }); }
      }
      function tick() {
        return api("/api/onboard/state").then(function (r) {
          if (!r.ok) { return; }
          S.state = r.data;
          apply();
          if (r.data.leader && !r.data.leader_unshaken) { stop(); return; }   /* 核心真检测到握手才亮「已连上」 */
          if (Date.now() - t0 > NS.LEADER_CHECK_MS && !checked) {   /* 20 秒先查一次 Cursor 的开关 */
            checked = true;
            checkClients(false);
          }
          if (Date.now() - t0 > NS.LEADER_HINT_MS && !hinted) {     /* 45 秒还没来：给排查清单，接着等 */
            hinted = true;
            if (!S._cursorOff) {
              var m = q("#ob-wait-late");
              if (m) {
                m.className = "msg fail";
                m.innerHTML = NS.tx("lead.install.lateTitle") + "<ol><li>" + NS.tx("lead.install.late1") + "</li><li>" +
                  NS.tx("lead.install.late2") + "</li><li>" + NS.tx("lead.install.late3") + "</li><li>" +
                  NS.tx("lead.install.late4") + "</li></ol>";
              }
            }
            var b = q("#ob-late-btns");
            if (b) { b.classList.remove("hide"); }
          }
        });
      }
      function stop() { stopped = true; if (timer) { clearInterval(timer); timer = null; } }
      function checkClients(verbose) {   /* 最常见的卡点是 Cursor 把 boxbox 关了——查到就直说怎么开 */
        return api("/api/connectors/check?station=" + encodeURIComponent(S.leaderName)).then(function (r) {
          var d = r.data || {};
          if (d.cursor_disabled) {
            S._cursorOff = true;
            var m = q("#ob-wait-late");
            if (m) { m.className = "msg fail"; m.innerHTML = NS.tx("lead.install.appSwitchOff"); }
            var b = q("#ob-late-btns");
            if (b) { b.classList.remove("hide"); }
          }
          var el = q("#ob-help-check");
          if (el && verbose) { el.innerHTML = d.cursor_disabled ? "" : NS.tx("lead.install.helpOk"); }
        }).catch(function () { /* 查不到就算了，不挡等待 */ });
      }
      function showHelp() {
        var box = q("#ob-help-box");
        if (!box) { return; }
        box.innerHTML = '<p class="lb">' + esc(NS.tx("lead.install.helpTitle")) + "</p>" +
          '<p class="hint" id="ob-help-check">' + esc(NS.tx("lead.install.helpChecking")) + "</p>";
        box.classList.remove("hide");
        checkClients(true);
      }

      paint();
      saveLeaderStation(tab, "#ob-ins-msg", loadInstall);
      if (!timer && !stopped) {
        tick().then(function () { if (!timer && !stopped) { timer = setInterval(tick, NS.POLL_MS); } });
      }
    });
  }

  /* ---------- 给它挑个样子（可跳过） ---------- */
  function pickLeaderLook(client) {
    return new Promise(function (res) {
      var look = { cat: num(dget("leader_cat"), (S.leaderLook || {}).cat || 1),
        acc: dget("leader_acc", (S.leaderLook || {}).acc || {}) };
      var w = win({
        title: "给它挑个样子",
        titleKey: "lead.look.title",
        body: '<div class="grid2">' + catCard(look.cat,
          '<div class="adv-acc"><button type="button" class="pxb small" id="ob-acc">' +
          esc(NS.tx("lead.look.acc")) + "</button></div>") +
          '<div class="card"><p class="lb">' + esc(NS.tx("lead.look.note")) + "</p>" +
          '<p class="hint">' + esc(NS.tx("lead.look.crownNote")) + "</p>" +
          '<div class="msg hide" id="ob-look-msg"></div></div></div>',
        buttons: [{
          text: NS.tx("lead.look.ok"), main: true, on: function (x) {
            S.leaderLook = look;
            draft({ leader_cat: look.cat, leader_acc: look.acc });
            saveLeaderStation(client, "#ob-look-msg", function () { x.close(); res(); });
          }
        }, { text: NS.tx("lead.look.skip"), small: true, on: function (x) { x.close(); res(); } }]
      });
      var spec = { no: look.cat, look: look };
      wireCat(w, spec, null);
      w.$("#ob-acc").onclick = function () {         /* 换一套配饰：重新随机 0–3 件 */
        look.acc = NS.randomAcc();
        wireCat(w, spec, null);
      };
    });
  }

  NS.stepWelcome = stepWelcome;
  NS.stepInstallLeader = stepInstallLeader;
  NS.pickLeaderLook = pickLeaderLook;
})();

/* ================= 这一份文件的文案（中文 / 英文） ================= */
window.BXOB.addTxt("lead", {
    'common.listSep': ['；', '; '],
    'install.appSwitchOff': [
      'Cursor 里 boxbox 的开关是关着的，所以连不上。到 Cursor 的设置里把 boxbox 打开，这里会自己变绿。',
      'The agentboxbox switch in Cursor is off, so it cannot connect. ' +
        'Turn agentboxbox on in Cursor\'s settings and this turns green on its own.'
    ],
    'install.checkApp': ['查一下 AI 软件那边', 'Check your AI app'],
    'install.cmdHint': ['在终端里运行这一条：', 'Run this one line in the terminal:'],
    'install.copyCmd': ['复制命令', 'Copy the command'],
    'install.copySnippet': ['复制这段配置', 'Copy this config'],
    'install.cursorBtn': ['一键装进 Cursor', 'Install into Cursor'],
    'install.cursorHint': ['Cursor 会问要不要启用 boxbox，点「启用」。',
      'Cursor will ask whether to enable agentboxbox — click Enable.'],
    'install.down': ['猫猫盒子没应答', 'agentboxbox did not answer'],
    'install.helpChecking': ['正在查 Cursor 那边…', 'Checking Cursor…'],
    'install.helpOk': [
      '那边是开着的。还不行的话：在 Cursor 的设置里把 boxbox 关掉再打开一次。',
      'It is on. If it still does not connect, turn agentboxbox off and on again in Cursor\'s settings.'
    ],
    'install.helpTitle': ['查 Cursor 里 boxbox 的开关', 'Check the agentboxbox switch in Cursor'],
    'install.late1': ['装进去了吗：上面的按钮点了，或命令跑了', 'Did the install finish — the button above clicked, or the command run'],
    'install.late2': ['在它的设置里，boxbox 是开着的吗', 'Is agentboxbox switched on in its settings'],
    'install.late3': ['终端里装的：新开一个会话，它才会来连', 'Installed from the terminal: start a new session so it connects'],
    'install.late4': ['猫猫盒子还开着吗', 'Is agentboxbox still open'],
    'install.lateTitle': ['还没连上。对一下这几件事：', 'Not connected yet. Check these:'],
    'install.loadFail': ['没读到：{why}', 'Could not read it: {why}'],
    'install.loading': ['正在读…', 'Reading…'],
    'install.lookLink': ['给它挑个样子', 'Pick a look for it'],
    'install.nextBtn': ['下一步：加一个帮手', 'Next: add a helper'],
    'install.okAny': ['连上了', 'Connected'],
    'install.okBody': [
      '不用先做别的。以后在它的任何一个对话里说「派给帮手」就行。',
      'Nothing else to set up. From now on, say “hand it to the helpers” in any of its chats.'
    ],
    'install.okTitle': ['{app} 连上了', '{app} is connected'],
    'install.otherHint': [
      '把这段配置放进你的编程助手的配置里，名字叫 boxbox。',
      'Put this into your coding assistant\'s config, keeping the entry name as shown.'
    ],
    'install.prep': ['命令和按钮都由你自己点，盒子不改你的软件设置。', 'Every command and button is yours to click — the box never touches your app settings.'],
    'install.retry': ['重试', 'Try again'],
    'install.saveFail': ['工位没登记上：{why}', 'Could not register the station: {why}'],
    'install.step1': ['装进你在用的那个', 'Install into the one you use'],
    'install.step2': ['等它连上', 'Waiting for it to connect'],
    'install.tabOther': ['其他', 'Other'],
    'install.title': ['第 1 步：装进你的编程助手', 'Step 1: Install into your coding assistant'],
    'install.unknownWhy': ['未知原因', 'unknown reason'],
    'install.viaHttp': [
      '它是按地址直接连上的，照样能干活。第一步装好以后，新开对话会自动连上。',
      'It connected straight to the address and works fine. Once step 1 is installed, new chats connect on their own.'
    ],
    'install.waitHint': ['装好它就会自己连上，这里会变绿，不用在对话里说话。',
      'Once installed it connects on its own and this turns green. No need to type anything in its chat.'],
    'install.waited': ['已等 {n}', 'Waited {n}'],
    'install.waitedMin': ['{n} 分钟', '{n} min'],
    'install.waitedSec': ['{n} 秒', '{n} s'],
    'look.acc': ['换一套配饰', 'Shuffle the extras'],
    'look.crownNote': ['王冠不用挑：它上岗的时候就戴上了。', 'No crown to pick — it gets one when it starts work.'],
    'look.note': ['换到喜欢的为止，点「好了」保存。', 'Shuffle until you like it, then click Done.'],
    'look.ok': ['好了', 'Done'],
    'look.skip': ['先不换了', 'Not now'],
    'look.title': ['给它挑个样子', 'Pick a look for it'],
    'recruit.defaultLeader': ['猫猫首领', 'Boss'],
    'welcome.flow1': ['你的编程助手', 'Your coding assistant'],
    'welcome.flow2': ['帮手们', 'The helpers'],
    'welcome.flow3': ['你的会话', 'Your chat'],
    'welcome.flowA1': ['— 派活 →', '— dispatch →'],
    'welcome.flowA2': ['— 做完交回 →', '— results back →'],
    'welcome.intro': [
      '你原来怎么用编程助手还怎么用。它想把活分出去时，派给这里的帮手，几个帮手同时做，做完交回你的会话。',
      'Keep using your coding assistant as you always have. When it wants to hand work out, ' +
        'it sends it to the helpers here — several run at once, and the results come back to your chat.'
    ],
    'welcome.next': ['三步开工：', 'Three steps to start:'],
    'welcome.one': ['给你的 AI 编程助手配几个帮手。', 'A few helpers for your AI coding assistant.'],
    'welcome.start': ['开始', 'Start'],
    'welcome.step1': ['装进你的编程助手', 'Install it into your coding assistant'],
    'welcome.step2': ['加一个帮手，填一个 API Key', 'Add a helper with an API key'],
    'welcome.step3': ['回到你的会话说「把 XX 派给帮手」', 'Back in your chat, say “hand XX to the helpers”'],
    'welcome.title': ['欢迎来到猫猫盒子', 'Welcome to agentboxbox'],
});
