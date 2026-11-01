/* 上岗流程 · 首领那几步：欢迎、招首领（起名选样子）、登记、等首领来报到。
   依赖 onboard-common.js（先加载）。 */
(function () {
  "use strict";
  var NS = window.BXOB;
  var S = NS.S;
  var $ = NS.$, esc = NS.esc, num = NS.num, api = NS.api, post = NS.post;
  var win = NS.win, catCard = NS.catCard, wireCat = NS.wireCat;
  var dget = NS.dget, draft = NS.draft;

  /* 欢迎窗口先说「这是啥」再说「接下来干啥」，隐喻只留一句 */

  /* ---------- 欢迎 ---------- */
  function stepWelcome() {
    return new Promise(function (res) {
      function paint() {
        var steps = [NS.tx("lead.welcome.step1"), NS.tx("lead.welcome.step2"), NS.tx("lead.welcome.step3")];
        var w = win({
          title: "欢迎来到猫猫盒子：三步开工",
          titleKey: "lead.welcome.title",
          body: "<p>" + esc(NS.tx("lead.welcome.intro")) + "</p><p class=\"lb\">" + esc(NS.tx("lead.welcome.next")) +
            "</p><ol id=\"ob-intro-steps\">" + steps.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") +
            "</ol>" + NS.langSwitch(),
          buttons: [{ text: NS.tx("lead.welcome.start"), main: true, on: function (x) { x.close(); res(); } }]
        });
        NS.wireLang(w);
        NS.rerender = paint;      /* 换语言：欢迎窗口重画一遍 */
      }
      paint();
    });
  }

  /* ---------- 招募猫猫首领 ---------- */
  function stepRecruitLeader() {
    var no = num(dget("leader_cat"), 1);
    var look = { cat: no, acc: dget("leader_acc", {}) };
    S.leaderLook = look;
    S.leaderName = String(dget("leader_name", NS.defaultLeaderName()));
    return new Promise(function (res) {
      var spec = { no: no, look: look };
      var w = win({
        title: "招募猫猫首领",
        titleKey: "lead.recruit.title",
        body: '<div class="grid2">' + catCard(no) +
          '<div class="card"><label class="lb" for="ob-lead-name">' + esc(NS.tx("lead.recruit.nameLabel")) + "</label>" +
          '<input id="ob-lead-name" type="text" maxlength="24" value="' + esc(S.leaderName) + '">' +
          '<p class="hint">' + esc(NS.tx("lead.recruit.nameHint", { name: NS.defaultLeaderName() })) + "</p>" +
          '<div class="msg hide" id="ob-lead-msg"></div></div></div>',
        buttons: [{
          text: NS.tx("common.next"), main: true, on: function (x) {
            var v = (x.$("#ob-lead-name").value || "").trim();
            if (!v) { x.msg("#ob-lead-msg", "fail", NS.tx("lead.recruit.nameEmpty")); return; }
            S.leaderName = v;
            draft({ leader_name: v, leader_cat: spec.no });
            x.close();
            res();
          }
        }]
      });
      wireCat(w, spec, function (s) { draft({ leader_cat: s.no }); });
      NS.rerender = null;
    });
  }

  /* ---------- 首领接入方式 ----------
     猫猫盒子不改用户电脑上任何 AI 软件的设置。这一步只登记首领；
     下一步那段话里带着盒子的地址：首领先按地址直接连上干活，再问用户要不要把盒子
     加进它所在软件的工具列表，用户同意了由那个软件里的 AI 自己加。 */
  function stepLeaderAccess() {
    return new Promise(function (res) {
      var w = win({
        title: "首领接入方式",
        titleKey: "lead.access.title",
        body: "<p>" + esc(NS.tx("lead.access.body1")) + "</p>" +
          '<p class="hint" id="ob-no-touch">' + esc(NS.tx("lead.access.body2")) + "</p>" +
          '<div class="msg wait" id="ob-mcp-msg">' + esc(NS.tx("lead.access.saving")) + "</div>",
        buttons: [{
          text: NS.tx("common.next"), main: true, on: function (x, btn) {
            if (!x._done) { leaderAccessRun(x, btn); return; }   /* 上次没登记成：再试一次 */
            x.close();
            res();
          }
        }]
      });
      leaderAccessRun(w, null);
      NS.rerender = null;
    });
  }
  function leaderAccessRun(w, btn) {
    btn = btn || w.$(".pxw-foot .pxb");   /* 第一次自动登记时也灰着：没登记完就点「下一步」会再登记一遍、窗口不往下走 */
    if (btn) { btn.disabled = true; }
    w.msg("#ob-mcp-msg", "wait", NS.tx("lead.access.saving"));
    return saveLeader(w).then(function (ok) {
      w._done = !!ok;
      if (btn) { btn.disabled = false; }
    }, function (e) {                 /* 核心没应答时按钮别一直灰着，说清楚、能再点 */
      if (btn) { btn.disabled = false; }
      w.msg("#ob-mcp-msg", "fail", NS.tx("lead.access.noSave",
        { why: esc(String((e && e.message) || e || NS.tx("lead.access.unknown"))) }));
    });
  }
  function saveLeader(w) {
    /* 不猜用户用哪家软件：只沿用工位上已经记着的，新首领留空 */
    var name = S.leaderName || dget("leader_name", "") || NS.defaultLeaderName();
    var st = { id: name, role: "leader", client: String(dget("leader_client", "") || ""),
      runner: "manual", enabled: true, look: S.leaderLook, lang: NS.lang() };
    return post("/api/stations", st).then(function (r) {
      if (!r.ok || !r.data.ok) {
        var why = esc((r.data.errors || [r.data.text || NS.tx("lead.access.unknownWhy")])
          .join(NS.tx("lead.common.listSep")));
        w.msg("#ob-mcp-msg", "fail", NS.tx("lead.access.fail", { why: why }));
        return false;
      }
      w.msg("#ob-mcp-msg", "ok", NS.tx("lead.access.ok", { name: esc(name) }));
      return true;
    });
  }

  /* ---------- 连接三栏 ----------
     ① 复制前先说清楚贴到哪（第 0 步）；复制后马上展开「你现在做这三步」；
     ② 45 秒没等到首领就给排查清单；20 秒先查一次客户端那边的开关（Cursor 把 boxbox 关了是最常见的卡点）；
     ③ 首领绕路（HTTP）来的，直接在窗里说「AI 软件还没挂上盒子」，不靠模型转告。主文案不出现内部接口词。 */
  function stepLeaderConnect() {
    return new Promise(function (res) {
      var prompt = "";
      var w = win({
        title: "接首领",
        titleKey: "lead.connect.title",
        body: '<p class="hint" id="ob-prep" style="margin:10px 0 8px">' + esc(NS.tx("lead.connect.prep")) + "</p>" +
          '<div class="tri">' +
          '<div class="card"><div class="step">1</div><h3>' + esc(NS.tx("lead.connect.step1")) + "</h3>" +
          '<p class="hint">' + esc(NS.tx("lead.connect.step1Hint")) + "</p>" +
          '<p class="lb" id="ob-prompt-peek">' + esc(NS.tx("lead.connect.generating")) + "</p>" +
          '<details id="ob-prompt-box"><summary>' + esc(NS.tx("lead.connect.showAll")) +
          '</summary><pre id="ob-prompt">' + esc(NS.tx("lead.connect.generating")) + "</pre></details>" +
          '<button type="button" class="pxb small hide" id="ob-prompt-retry">' + esc(NS.tx("lead.connect.retry")) + "</button>" +
          '<button type="button" class="pxb main" id="ob-copy-prompt">' + esc(NS.tx("lead.connect.copyThis")) + "</button>" +
          '<ol class="hide" id="ob-todo3"><li>' + esc(NS.tx("lead.connect.todo1")) + "</li><li>" +
          esc(NS.tx("lead.connect.todo2")) + "</li><li>" + esc(NS.tx("lead.connect.todo3")) + "</li></ol></div>" +

          '<div class="card" id="ob-wait"><div class="step">2</div><h3>' + esc(NS.tx("lead.connect.step2")) + "</h3>" +
          '<canvas class="av" width="96" height="96"></canvas>' +
          '<p><span class="dots"><span></span><span></span><span></span></span> <span id="ob-wait-t">' +
          esc(NS.tx("lead.connect.waited", { n: waitedText(0) })) + "</span></p>" +
          '<p class="hint">' + esc(NS.tx("lead.connect.waitHint")) + "</p></div>" +

          '<div class="card hide done" id="ob-ok"><div class="step">3</div><h3>' +
          esc(NS.tx("lead.connect.step3", { name: S.leaderName })) + "</h3>" +
          "<p>" + esc(NS.tx("lead.connect.arrived")) + "</p>" +
          '<button type="button" class="pxb main" id="ob-next">' + esc(NS.tx("lead.connect.nextBtn")) + "</button></div></div>" +
          /* 排查清单放三栏下面一整行：塞在中间那栏里太窄，一展开窗口就比 exe 窗口高 */
          '<div id="ob-late-wrap">' +
          '<div class="msg hide" id="ob-wait-late"></div>' +
          '<div class="hide" id="ob-late-btns" style="margin-top:8px">' +
          '<button type="button" class="pxb small" id="ob-again">' + esc(NS.tx("lead.connect.recopy")) + "</button> " +
          '<button type="button" class="pxb small" id="ob-help">' + esc(NS.tx("lead.connect.checkApp")) + "</button></div>" +
          '<div class="card hide" id="ob-help-box" style="margin-top:10px"></div></div>'
      });
      NS.rerender = null;
      NS.drawCat(w.$("#ob-wait canvas"), { cat: S.leaderLook.cat, lead: true });
      var copyBtn = w.$("#ob-copy-prompt"), retryBtn = w.$("#ob-prompt-retry");
      copyBtn.onclick = function () { NS.copyText(prompt, this); w.$("#ob-todo3").classList.remove("hide"); };
      w.$("#ob-again").onclick = function () { NS.copyText(prompt, this); };
      w.$("#ob-next").onclick = function () { stop(); w.close(); res(); };
      w.$("#ob-help").onclick = function () { showHelp(w); };

      function loadPrompt() {          /* ① 栏那段话：先说「正在生成…」，读到就填进去，读不到说清原因并能重试 */
        w.$("#ob-prompt").textContent = NS.tx("lead.connect.generating");
        w.$("#ob-prompt-peek").textContent = NS.tx("lead.connect.generating");
        retryBtn.classList.add("hide");
        copyBtn.disabled = true;
        return api("/api/summon/" + encodeURIComponent(S.leaderName) + NS.langParam()).then(function (r) {
          var d = r.data || {};
          if (!r.ok || !d.prompt) {
            var why = NS.tx("lead.connect.promptFail", { why: d.text || d.code || NS.tx("lead.connect.down") });
            w.$("#ob-prompt").textContent = why;
            w.$("#ob-prompt-peek").textContent = why;
            retryBtn.classList.remove("hide");
            return;
          }
          prompt = d.prompt;
          w.$("#ob-prompt").textContent = prompt;
          /* 主路径只露第一句（里面没有工具名、地址），全文收在「看全文」里 */
          w.$("#ob-prompt-peek").textContent = NS.tx("lead.connect.peekCount",
            { first: firstSentence(prompt), n: prompt.length });
          w._help = d;
          copyBtn.disabled = false;
        });
      }
      retryBtn.onclick = loadPrompt;
      loadPrompt();

      var t0 = Date.now(), timer = null;
      function waitedText(s) {
        return s < 60 ? NS.tx("lead.connect.waitedSec", { n: s }) : NS.tx("lead.connect.waitedMin", { n: Math.floor(s / 60) });
      }
      function waited() { return waitedText(Math.floor((Date.now() - t0) / 1000)); }
      function tick() {
        return api("/api/onboard/state").then(function (r) {
          if (!r.ok) { return; }
          S.state = r.data;
          if (!r.data.leader_unshaken) {          /* 核心真的检测到首领来握过手，才显示「已连接」 */
            w.$("#ob-wait").classList.add("hide");
            w.$("#ob-late-wrap").classList.add("hide");   /* 连上了，排查清单收起来 */
            w.$("#ob-ok").classList.remove("hide");
            if (r.data.leader_link === "http") {  /* 首领是绕路来的——AI 软件里还没挂上盒子，直接告诉用户，不指望模型转告 */
              var via = document.createElement("div");
              via.className = "msg wait";
              via.id = "ob-via-http";
              via.innerHTML = NS.tx("lead.connect.viaHttp");
              w.$("#ob-ok").insertBefore(via, w.$("#ob-next"));
            }
            stop();
            return;
          }
          var t = w.$("#ob-wait-t");
          if (t) { t.textContent = NS.tx("lead.connect.waited", { n: waited() }); }
          if (Date.now() - t0 > NS.LEADER_CHECK_MS && !w._checked) {   /* 先查一次 Cursor 是不是把 boxbox 关了 */
            w._checked = true;
            checkClients(w, false);
          }
          if (Date.now() - t0 > NS.LEADER_HINT_MS && !w._hinted) {     /* 45 秒还没来：给排查清单，继续等 */
            w._hinted = true;
            if (!w._cursorOff) {
              w.msg("#ob-wait-late", "fail", NS.tx("lead.connect.lateTitle") +
                "<ol><li>" + NS.tx("lead.connect.late1") + "</li><li>" + NS.tx("lead.connect.late2") + "</li><li>" +
                NS.tx("lead.connect.late3") + "</li><li>" + NS.tx("lead.connect.late4") + "</li></ol>");
            }
            w.$("#ob-late-btns").classList.remove("hide");
          }
        });
      }
      function stop() { if (timer) { clearInterval(timer); timer = null; } }
      function showHelp(x) {
        var d = x._help || {};
        x.$("#ob-help-box").innerHTML =
          "<p class=\"lb\">" + esc(NS.tx("lead.connect.helpWhere",
            { where: d.where || NS.tx("lead.connect.helpWhereDefault") })) + "</p>" +
          ((d.steps || []).length ? "<ol>" + d.steps.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ol>" : "") +
          '<p class="hint" id="ob-help-check">' + esc(NS.tx("lead.connect.helpChecking")) + "</p>";
        x.$("#ob-help-box").classList.remove("hide");
        checkClients(x, true);
      }
      function checkClients(x, verbose) {   /* 最常见的卡点是 Cursor 把 boxbox 关了——查到就直说怎么开 */
        return api("/api/connectors/check?station=" + encodeURIComponent(S.leaderName)).then(function (r) {
          var d = r.data || {};
          var el = x.$("#ob-help-check");
          if (d.cursor_disabled) {
            x._cursorOff = true;
            x.msg("#ob-wait-late", "fail", NS.tx("lead.connect.appSwitchOff"));
            x.$("#ob-late-btns").classList.remove("hide");
          }
          if (el && verbose) {   /* 不猜你用哪家：猫猫盒子不写别的软件的设置，查完只说下一步怎么办 */
            el.innerHTML = d.cursor_disabled ? "" : NS.tx("lead.connect.helpOk");
          }
        }).catch(function () { /* 查不到就算了，不挡等待 */ });
      }
      tick().then(function () { timer = setInterval(tick, NS.POLL_MS); });
    });
  }

  /* 主路径只露第一句：中文按「。」断，英文按句号断 */
  function firstSentence(p) {
    return NS.lang() === "en" ? p.split(". ")[0] : p.split("。")[0];
  }

  NS.stepWelcome = stepWelcome;
  NS.stepRecruitLeader = stepRecruitLeader;
  NS.stepLeaderAccess = stepLeaderAccess;
  NS.stepLeaderConnect = stepLeaderConnect;
})();

/* ================= 这一份文件的文案（中文 / 英文） ================= */
window.BXOB.addTxt("lead", {
    'access.body1': [
      '首领住在你常用的 AI 软件（Cursor、Claude Code、Codex 等都行）的对话里。下一步你复制一段话贴进去，里面的 AI 就成了首领，会直接连上猫猫盒子开始干活。',
      'The leader lives in a chat in your AI app (Cursor, Claude Code, Codex — any of them). ' +
        'Next you paste a text there; ' +
        'the AI in that chat becomes the leader and connects to agentboxbox to work.'
    ],
    'access.body2': [
      '猫猫盒子不会改你电脑上任何软件的设置。想让首领下次更顺手，它会先问你要不要把盒子加进它的工具列表，你同意了它自己加。',
      'agentboxbox does not change the settings of any app on your computer. ' +
        'To make the next round smoother, ' +
        'the leader will first ask whether agentboxbox may join its tool list; ' +
        'if you say yes, it adds it itself.'
    ],
    'access.fail': ['登记失败：{why}。点「下一步」重试。', 'Could not register: {why}. Click Next to try again.'],
    'access.noSave': ['没保存上：{why}。点「下一步」重试。', 'Could not save: {why}. Click Next to try again.'],
    'access.ok': ['首领「{name}」登记好了。点「下一步」拿那段话。', 'Leader “{name}” is registered. Click Next to get the text.'],
    'access.saving': ['正在登记首领…', 'Registering the leader…'],
    'access.title': ['首领接入方式', 'How the leader connects'],
    'access.unknown': ['猫猫盒子没应答', 'no answer from the box'],
    'access.unknownWhy': ['未知原因', 'unknown reason'],
    'connect.appSwitchOff': [
      '你常用的 AI 软件里 boxbox 的开关可能是关着的，所以对话里用不上盒子的工具。到那边的设置里找到工具列表那一栏，把 boxbox 打开，再新开一个对话贴那段话。' +
        '（不打开也行：首领会按地址直接连上。）',
      'The boxbox switch in your AI app may be off, so the chat cannot use the box tools. ' +
        'Open that app\'s settings, find the tool list and turn boxbox on, ' +
        'then start a new chat and paste the text. ' +
        '(It also works with the switch off: the leader connects by address.)'
    ],
    'connect.arrived': ['首领来报到了。', 'The leader checked in.'],
    'connect.checkApp': ['查一下 AI 软件那边', 'Check your AI app'],
    'connect.copyThis': ['复制这段话', 'Copy this text'],
    'connect.down': ['猫猫盒子没应答', 'agentboxbox did not answer'],
    'connect.generating': ['正在生成…', 'Working…'],
    'connect.helpChecking': ['正在查 AI 软件那边…', 'Checking your AI app…'],
    'connect.helpOk': [
      '那段话整段贴进去、发送了，AI 就会按地址连过来。还不行的话：确认猫猫盒子开着，新开一个对话再贴一次。',
      'Paste the whole text and send it — the AI connects by address. ' +
        'If that does not work: check that agentboxbox is running, ' +
        'start a new chat and paste it again.'
    ],
    'connect.helpWhere': ['贴到哪里：{where}', 'Where to paste: {where}'],
    'connect.helpWhereDefault': ['你常用的 AI 软件里的新对话', 'a new chat in your AI app'],
    'connect.late1': ['是在 AI 软件里<b>新开</b>的对话吗？', 'Did you start a <b>new</b> chat in your AI app?'],
    'connect.late2': ['整段贴进去、<b>发送</b>了吗？', 'Did you paste the whole text and hit <b>send</b>?'],
    'connect.late3': [
      'AI 回话说找不到盒子的工具？没关系，那段话里带着地址，它会按地址直接连过来，多等一会儿。',
      'Did the AI say it cannot find the box tools? Never mind: the text carries the address, ' +
        'so it connects straight to it — just wait a bit longer.'
    ],
    'connect.late4': ['猫猫盒子还开着吗？（任务栏右下角有猫的图标）', 'Is agentboxbox still open? (look for the cat icon in the system tray)'],
    'connect.lateTitle': ['还没等到首领。对一下这几件事：', 'The leader has not shown up. Check these:'],
    'connect.nextBtn': ['下一步', 'Next'],
    'connect.peekCount': ['「{first}……」共 {n} 字', '“{first}…” — {n} characters'],
    'connect.prep': ['先打开你常用的 AI 软件，新开一个对话。', 'Open your AI app and start a new chat.'],
    'connect.promptFail': ['没读到这段话：{why}', 'Could not read that text: {why}'],
    'connect.recopy': ['重新复制', 'Copy again'],
    'connect.retry': ['重试', 'Try again'],
    'connect.showAll': ['看全文', 'Show all'],
    'connect.step1': ['复制这段话', 'Copy this text'],
    'connect.step1Hint': ['这段是写给 AI 看的，不用读，整段复制过去就行。', 'This text is for the AI. You do not need to read it, just copy all of it.'],
    'connect.step2': ['等首领来报到…', 'Waiting for the leader…'],
    'connect.step3': ['「{name}」已连接！', '“{name}” is connected!'],
    'connect.title': ['接首领', 'Connect the leader'],
    'connect.todo1': ['在 AI 软件里新开一个对话', 'Start a new chat in your AI app'],
    'connect.todo2': ['粘贴、发送', 'Paste and send'],
    'connect.todo3': ['回来看这里：首领连上了，第 3 栏会变成「已连接」', 'Come back here: when the leader connects, the third box says “Connected”'],
    'connect.viaHttp': [
      '首领是按地址直接连上的，照样能干活。它会在对话里问你要不要把猫猫盒子加进它的工具列表：同意的话它自己加，下次新开对话就更顺；不同意也没关系，每次照样按地址连。',
      'The leader connected straight to the address and can work just fine. ' +
        'It will ask in the chat whether agentboxbox may join its tool list: if you say yes it ' +
        'adds it and the next chat is smoother; if not, it still connects by address every time.'
    ],
    'connect.waitHint': ['它真的连上盒子了，这里才会变。', 'This only changes once the leader really connects.'],
    'connect.waited': ['已等 {n}', 'Waited {n}'],
    'connect.waitedSec': ['{n} 秒', '{n} s'],
    'connect.waitedMin': ['{n} 分钟', '{n} min'],
    'common.listSep': ['；', '; '],
    'recruit.defaultLeader': ['猫猫首领', 'Boss'],
    'recruit.nameEmpty': ['给首领起个名字吧', 'Give the leader a name'],
    'recruit.nameHint': [
      '默认「{name}」，可改；工号 001。王冠等上岗的时候才戴上。',
      'Default: “{name}” (you can change it). Badge No. 001. The crown goes on once it starts work.'
    ],
    'recruit.nameLabel': ['首领的名字', 'Leader name'],
    'recruit.title': ['招募猫猫首领', 'Hire a leader'],
    'welcome.intro': [
      '猫猫盒子是装在这台电脑上的一间猫猫办公室：首领派活、打工猫干活，你在旁边看着。',
      'agentboxbox is a cat office on this computer: the leader hands out cards, ' +
        'the worker cats do them, you watch.'
    ],
    'welcome.next': ['接下来三步，十来分钟：', 'Three steps, about ten minutes:'],
    'welcome.start': ['开始', 'Start'],
    'welcome.step1': ['招一位首领（起个名字、挑个样子）', 'Hire a leader (give it a name and a look)'],
    'welcome.step2': [
      '复制一段话，贴进你常用的 AI 软件（Cursor、Claude Code、Codex 等）的新对话',
      'Copy a text and paste it into a new chat in your AI app (Cursor, Claude Code, Codex, …)'
    ],
    'welcome.step3': ['招一只打工猫，然后就能跟首领说「帮我派一张卡：……」', 'Hire a worker cat, then tell the leader: “Make me a card: …”'],
    'welcome.title': ['欢迎来到猫猫盒子：三步开工', 'Welcome to agentboxbox: three steps to start'],
});
