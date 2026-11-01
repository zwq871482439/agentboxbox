/* ===================== v3：工位状态词 + 像素气泡 ===================== */
/* 工位上常驻的只有一个简单中文状态词；猫在干什么改用头顶气泡（动作切换时 + 每隔一段时间冒出来几秒） */
function actKind(ch){const st=ch.state,lead=ch.st.lead;
  if(SCENE&&PARTY.includes(SCENE.name)&&SCENE.ids.has(ch.id))return null;   /* 场景里不冒活动气泡（复盘另有自己的无语 / 疑问气泡） */
  if(lead&&st!=="off"&&st!=="you"){if(SKIN.zoned&&(ch.goal==="meet"||(inMeeting(ch)&&!ch.inBox)))return"meet";return({nap:"zzz",tea:"coffee",phone:"phone",
    game:"game"})[ch.bossAnim]||null}
  if(st==="off")return null;if(st==="fail")return"fail";if(st==="arch"||st==="you")return lead?null:"ask";
  if(SKIN.zoned&&(ch.goal==="meet"||(inMeeting(ch)&&!ch.inBox)))return"meet";
  if(ch.goal==="deliver"||ch.carry)return"file";
  if(st==="run"||st==="appr"){if(snackOn(ch)&&Math.floor((T+ch.st.seed)/18)%3===0)return"tired";return"key"}   /* 夜里赶工摆了外卖盒：偶尔冒「累」的气泡 */
  if(st==="idle"){if(lead){return ch.bossAnim==="nap"?"zzz":ch.bossAnim==="tea"?"coffee":null}
  if(ch.inBox){return ch.act==="sleepbox"?"zzz":ch.act==="drink"?"coffee":ch.act==="eat"?"snack":ch.act==="deskplay"?"game":null}
    if(ch.act==="eat")return"snack";if(ch.act==="drink")return"coffee";
    const p=ch.plan;
    return p==="coffee"?"coffee":p==="fridge"?"fridge":p==="rugphone"||p==="meetslack"?"phone":p==="cards"?"cards":p==="sofa"?
      (ch.act==="sofaphone"?"phone":ch.act==="sofachat"?"chat":"zzz"):p==="visit"?"chat":null}
  return null}
function statusWord(ch){const st=ch.state,lead=ch.st.lead,k=actKind(ch);
  if(NAPS.has(ch.id))return TR("st.nap");
  if(SCENE&&PARTY.includes(SCENE.name)&&SCENE.ids.has(ch.id))return PARTY_WORD[SCENE.name]||TR("st.meeting");   /* –庆祝 / 复盘中 */
  if(lead&&st!=="off"&&st!=="you"){const n=(DATA&&DATA.arch&&DATA.arch.count)||0;return n?TR("st.todoN",{n}):TR("st.noTodo")}
  if(st==="off")return TR("q.off");if(st==="fail")return TR("state.fail");if(st==="appr")return TR("state.appr");
  if(st==="rest")return TR("state.rest");   /* 歇着：画布上写短词，完整那句（几点回来）给悬停 */
  if(st==="you")return lead?TR("st.yourCall"):TR("st.waiting");
  if(st==="arch")return lead?(DATA&&DATA.arch&&DATA.arch.count?TR("st.hasTodoN",{n:DATA.arch.count}):TR("st.hasTodo")):TR("st.waiting");
  if(k==="meet")return TR("st.meeting");if(k==="file")return TR("st.delivering");
  if(st==="run")return TR("st.working");
  if(st==="idle"){const A={brew:TR("st.brew"),drink:TR("st.drink"),fridgeopen:TR("st.fridgeopen"),eat:TR("st.eat"),
      cards:TR("st.cards"),sofachat:TR("st.sofachat"),sofaphone:TR("st.sofaphone")}[ch.act];
    if(A&&!ch.moving)return A;
    if(ch.moving&&ch.hold)return ch.hold==="cup"?TR("st.carryCup"):TR("st.carrySnack");
    if(ch.moving&&ch.goal==="home")return TR("st.backToDesk");
    if(ch.plan==="wander"&&!ch.inBox)return TR("st.wander");
    if(ch.plan==="meetslack"&&!ch.moving)return TR("st.meetslack");
    return({coffee:ch.plan==="tea"||ch.plan==="tabletea"||ch.act==="teabox"||ch.bossAnim==="tea"?TR("st.tea"):TR("st.pour"),
      fridge:TR("st.fridgeopen"),phone:TR("st.phone"),zzz:ch.plan==="sofa"?TR("st.sofa"):TR("st.sleep"),
      game:TR("st.game"),chat:TR("st.chat")})[k]||TR("st.idle")}
  return TR(stateWord(st))}
/* 像素图标 8×8：. 透明；其余字符查调色板。描边色和 chibicat 的线条色一致（深褐 / 深灰） */
function pix(rows,cx,cy,u){/* 在 hi 画布上按世界坐标画像素格，cx/cy 为中心 */const n=rows.length,x0=cx-n*u/2,y0=cy-n*u/2;
  for(let j=0;j<n;j++)for(let i=0;i<rows[j].length;i++){const c=IPAL[rows[j][i]];if(!c)continue;hi.fillStyle=c;hi.fillRect(Math.floor(W2(x0+i*u)),
    Math.floor(W2(y0+j*u)),Math.ceil(W2(u)),Math.ceil(W2(u)))}}
/* ===================== 融合：常驻头顶符号 + 像素气泡（只做补充） ===================== */
/* 常驻符号表达「真实状态」，一直挂着：? 等待 / × 失败(+唉…) / ! 要决策 / zzz 睡着(趴桌，沙发，TL打盹) / ♪ 串门聊天
   像素气泡只在「活动变了」时冒一次；有常驻符号时绝不冒；没有定时器；每只猫冷却 BUB_COOLDOWN 秒；全场同时最多 BUB_MAX 个、错开 BUB_GAP 秒 */
const BUB_SHOW=3.2, BUB_COOLDOWN=30, BUB_MAX=2, BUB_GAP=0.9, BUB_STALE=8;
let BUBQ=[], BUBLOG=[];
/* v2：「想法」= 白底像素气泡（? 等待 / × 失败 / ! 要决策），状态持续多久就挂多久；
   「身体反应」画在猫旁边、不进气泡：Zzz 睡着、汗滴 紧张、♪ 聊天 */
function thoughtOf(ch){const st=ch.state,lead=ch.st.lead;if(st==="off")return null;
  if(st==="you")return lead?"bang":"!";if(st==="fail")return"×";
  if(!lead&&DATA&&DATA.leader_quiet&&st==="idle")return"?";   /* 首领没反应，围过去的空闲猫冒 ? */
  if(st==="arch"&&!lead&&!ch.moving)return"…";return null}   /* 卡住 / 打回待定 / 等首领验收 → 省略号 */
function persistentSym(ch){const th=thoughtOf(ch);if(th)return th;
  if(ch.state==="rest")return"time";   /* 歇着：头顶一个小钟（几点回来） */
  if(isSleeping(ch,ch.st))return"zzz";
  if(ch.state==="idle"&&!ch.moving&&(ch.act==="chat"||ch.act==="sofachat"))return"♪";
  return null}
/* 紧张（冒汗）：失败、要决策、连续跑太久（run_s ≥ 30 分钟，字段有才算）、排队 > 2 件 */
const TENSE_RUN_S=1800, TENSE_QUEUE=2;
function isTense(ch){const st=ch.state,d=ch.data||{};if(st==="off")return false;
  return st==="fail"||(st==="you"&&!ch.st.lead)||(st==="run"&&(d.run_s||0)>=TENSE_RUN_S)||(d.queue||0)>TENSE_QUEUE}
function drawSweat(ch,t){const h=ch.head;if(!h)return;for(let i=0;i<2;i++){const p=(t*.9+i*.5)%1,x=h.x-10-i*3,y=h.y+6+p*7;hi.globalAlpha=1-p*.7;
  hi.fillStyle="#7dd3fc";hi.fillRect(W2(x),W2(y),W2(1.4),W2(2));hi.fillRect(W2(x+.35),W2(y-.8),W2(.7),W2(.8));hi.fillStyle="#e0f2fe";hi.fillRect(W2(x+.2),
    W2(y+.3),W2(.4),W2(.6));hi.globalAlpha=1}}
function actKey(ch){const k=actKind(ch);if(!k||k==="zzz"||persistentSym(ch))return null;return k}   /* 想法气泡 / 睡着 / 聊天时不冒活动气泡 */
function bubbleTick(){
  for(const id in CH){const ch=CH[id];const k=actKey(ch);
    if(ch.bubOn!=null&&(T-ch.bubOn>=BUB_SHOW||!k||k!==ch.bubKey))ch.bubOn=null;   /* 到点 / 换成常驻符号 / 活动又变 → 收起 */
    if(k!==ch.bubKey){ch.bubKey=k;if(k&&T-(ch.bubLast??-1e9)>=BUB_COOLDOWN&&!BUBQ.some(q=>q.ch===ch))BUBQ.push({ch,k,t:T})}}
  let on=Object.values(CH).filter(c=>c.bubOn!=null);
  const lastStart=Math.max(-1e9,...on.map(c=>c.bubOn));
  BUBQ=BUBQ.filter(q=>CH[q.ch.id]===q.ch&&q.ch.bubKey===q.k&&T-q.t<BUB_STALE);   /* 排到时活动已变 / 太久 → 丢掉 */
  if(BUBQ.length&&on.length<BUB_MAX&&T-lastStart>=BUB_GAP){const q=BUBQ.shift();const ch=q.ch;
    if(T-(ch.bubLast??-1e9)>=BUB_COOLDOWN){ch.bubOn=T;ch.bubLast=T;BUBLOG.push({id:ch.id,k:q.k,t:T});if(BUBLOG.length>400)BUBLOG.shift()}}
}
function bubbleVisible(ch){if(ch.bubOn==null||!ch.bubKey)return 0;const a=T-ch.bubOn;if(a<0||a>=BUB_SHOW)return 0;
  return Math.min(1,a/.18,(BUB_SHOW-a)/.3)}
/* 常驻符号绘制：沿用原型 bubble() 的圆角小牌（?白 / ×红 / !红），♪ 黄色音符，× 旁边定时叹「唉…」；Zzz 见 drawZzz */
function drawPersistent(ch,sym,t){if(!ch.head)return;
  if(sym==="?")drawPixBubble(ch,"ask",1,Math.abs(Math.sin(t*3))*.8);
  else if(sym==="!")drawPixBubble(ch,"bang",1,Math.abs(Math.sin(t*5))*1.2);
  else if(sym==="×"){drawPixBubble(ch,"fail",1,0);if((t%4)<1.5)txt(TR("st.sigh"),ch.head.x-15,ch.head.y+4,{sz:3.8,c:PAL.dim})}
  else if(sym==="…")drawPixBubble(ch,"dots",1,Math.abs(Math.sin(t*2.2))*.6);
  else if(sym==="time")drawPixBubble(ch,"time",1,0);   /* 歇着：头顶小钟 */
  else if(sym==="♪"){const b=Math.abs(Math.sin(t*2.4))*1.6;txt("♪",ch.head.x+10,ch.head.y+2-b,{sz:6.5,b:1,c:"#fde68a"})}
  else if(sym==="zzz")drawZzz(ch,t)}
function drawZzz(ch,t){const h=ch.head||{x:ch.st.x,y:ch.st.y-10};for(let i=0;i<3;i++){const p=((t*.6+i/3)%1);hi.globalAlpha=1-p;txt(i%2?"z":"Z",h.x-12-p*6-i,
  h.y+12-p*9,{sz:3.6+p*3,b:1,c:"#c7d2fe"});hi.globalAlpha=1}}
function drawActBubble(ch){const al=bubbleVisible(ch);if(!al||!ch.head)return;drawPixBubble(ch,ch.bubKey,al,(1-al)*2)}
function drawPixBubble(ch,key,al,lift){if(!ch.head)return;
  /* 气泡放在血条正上方居中：不再挡住血条和「剩余xx%」 */
  const lead=ch.st.lead,bx=ch.head.x,by=ch.head.y-(ch.state==="off"?0:(ch.hp?11:6))-(lead?2:0)-lift,w=10,h=9;
  hi.save();hi.globalAlpha=al;
  hi.fillStyle="#2b2233";hi.fillRect(W2(bx-w/2-.5),W2(by-h-.5),W2(w+1),W2(h+1));
  hi.fillStyle="#fffdf7";hi.fillRect(W2(bx-w/2),W2(by-h),W2(w),W2(h));
  hi.fillStyle="#2b2233";hi.fillRect(W2(bx-1.5),W2(by+.5),W2(3),W2(.75));hi.fillRect(W2(bx-.75),W2(by+1.25),W2(1.5),W2(.75));
  hi.fillStyle="#fffdf7";hi.fillRect(W2(bx-1),W2(by),W2(2),W2(.9));
  pix(ICON[key],bx,by-h/2,1);hi.restore()}
/* ===================== 开会气泡：气泡 + 图标，不写字（office-v2/spec.md 第 6 节） ===================== */
/* 18 个 8×8 像素图标：话题 10 + 情绪 8；气泡就是平时活动气泡的样式（drawPixBubble），里面只画一个图标 */
Object.assign(ICON,MICON);
const MTOPIC=["task","work","doc","plan","money","code","chart","bug","time","merge"],MEMO=["meh","happy","joy","tired","huh","angry","wow","idea"];
/* 按会议类型加权：全部图标底子都是 1；验收 代码4 bug4 疑问3 图表2 合入2；派活 任务4 计划4 时间2 工作2 文档2 灵感2；
   结果好 高兴/开心各加 8、合入加 4；结果差 生气/无语各加 6、累/bug 各加 4（只看会议类型和结果，不读信箱正文） */
const MW={review:{code:4,bug:4,huh:3,chart:2,merge:2},assign:{task:4,plan:4,time:2,work:2,doc:2,idea:2}};
const MW_MOOD={good:{happy:8,joy:8,merge:4},bad:{angry:6,meh:6,tired:4,bug:4}};
const MEET_RULE={slot:1.3,show:2.2,max:2,fadeIn:.18,fadeOut:.3};   /* 每 1.3 秒冒一个，显示 2.2 秒，0.18 淡入，最后 0.3 淡出上浮，全场最多 2 个 */
function meetMood(){return Q.get("mood")||(DATA&&DATA.meet_mood)||null}   /* ?mood=good|bad 或 feed 的 meet_mood 字段 */
function meetPick(n,why,mood){mood=mood===undefined?meetMood():mood;const w={};
  for(const k of MTOPIC.concat(MEMO))w[k]=(MW[why]&&MW[why][k])||1;
  if(mood&&MW_MOOD[mood])for(const k in MW_MOOD[mood])w[k]=(w[k]||1)+MW_MOOD[mood][k];
  const ks=Object.keys(w),sum=ks.reduce((a,k)=>a+w[k],0);let r=hash("mpick"+n)%sum;for(const k of ks){if((r-=w[k])<0)return k}return ks[0]}
let MEET_BUBS=[],MEET_SNAP=null;
function drawMeetBubbles(t){MEET_BUBS=[];
  let ppl=null,tn=t;
  if(meetReady()){ppl=meetArrived().sort((a,b)=>a.x-b.x);MEET_SNAP={ppl,t0:t}}
  else if(MEET_SNAP&&t-MEET_SNAP.t0<MEET_RULE.show){ppl=MEET_SNAP.ppl;tn=MEET_SNAP.t0}   /* 散会后不再冒新的，已有的按淡出走完 */
  if(!ppl||ppl.length<2)return;
  const cx=ZONE.meet.x+ZONE.meet.w/2;
  const L=ppl.filter(c=>c.x<cx),Rr=ppl.filter(c=>c.x>=cx);const side=n=>(n%2?(Rr.length?Rr:L):(L.length?L:Rr));   /* 桌子左半边和右半边轮流冒 */
  const n0=Math.floor(tn/MEET_RULE.slot);
  for(let n=n0-MEET_RULE.max+1;n<=n0;n++){if(n<0)continue;const age=t-n*MEET_RULE.slot;if(age>MEET_RULE.show)continue;
    const grp=side(n),ch=grp[hash("mspk"+n)%grp.length];if(!ch||!ch.head)continue;   /* 同一边有几只猫时随机挑一只 */
    const al=Math.min(1,age/MEET_RULE.fadeIn,(MEET_RULE.show-age)/MEET_RULE.fadeOut);if(al<=0)continue;
    const bang=persistentSym(ch)==="bang";   /* TL 头上有「需要你拍板」时，开会气泡抬到牌子上面，不叠 */
    const lift=(1-al)*2+(bang?16:0),icon=meetPick(n,MEET.why);
    MEET_BUBS.push({id:ch.id,icon,al,lift,n,side:L.includes(ch)?"L":"R"});
    drawPixBubble(ch,icon,al,lift)}}
function isSleeping(ch,st){if(ch.state==="off")return false;
  if(NAPS.has(ch.id))return true;   /* 午睡里：趴工位 / 窝沙发都算睡着（头上 Zzz） */
  if(ch.inBox)return ch.state==="idle"&&ch.act==="sleepbox"||!!(st.lead&&ch.act==="boss_idle"&&ch.bossAnim==="nap");
  return ch.state==="idle"&&!ch.moving&&ch.plan==="sofa"&&ch.act==="sofanap"}  /* ：沙发窝着也算睡着 */
function drawOverlay(t){
  // 霓虹字
  hi.save();hi.shadowColor="#e10600";hi.shadowBlur=S*3;{const en=uiLang()==="en",lab=en?"agentboxbox":"猫猫盒子",sz=en?5.4:6.2,gap=en?1.35:2.1;
hi.font=`700 ${sz*S}px "Microsoft YaHei","PingFang SC","Noto Sans CJK SC","Noto Serif CJK SC",sans-serif`;hi.textAlign="left";hi.textBaseline="alphabetic";
hi.fillStyle="#ff4d4f";let tw=0;for(const ch of lab)tw+=hi.measureText(ch).width+gap*S;tw-=gap*S;let x=W2(424)-tw/2,y=W2(23.6);
    for(const ch of lab){hi.fillText(ch,x,y);x+=hi.measureText(ch).width+gap*S}}hi.restore();
  const todoN=(DATA&&DATA.arch&&DATA.arch.count)||0;
  txt(TR("board.todo",{n:todoN}),TODO_BOARD.x+TODO_BOARD.w/2,TODO_BOARD.y+6.5,{sz:3.8,b:1,c:"#374151"});
  if(todoN>8)txt("+"+(todoN-8),TODO_BOARD.x+TODO_BOARD.w-5,TODO_BOARD.y+TODO_BOARD.h-3.5,{sz:3.6,b:1,c:"#e10600"});   /* 便利贴最多 8 张，超出右下角红「+N」 */
  /* 融合：恢复会议室「开会中，派活/验收」字样（区域名仍不标） */
  if(SKIN.zoned&&meetReady())txt(MEET.why==="assign"?TR("meet.assigning"):TR("meet.reviewing"),
    ZONE.meet.x+ZONE.meet.w-14,ZONE.meet.y+ZONE.meet.h-3,{sz:4,b:1,c:"#fde68a"});
  /* v2：字样挪到会议室右下角；至少 TeamLeader + 1 只相关的猫都到了才算开会 */
  bubbleTick();
  for(const id in CH){const ch=CH[id];if(ch.carry&&!ch.inBox&&ch.head)pix(ICON.file,ch.head.x+4,ch.head.y+11,.6);
    if(ch.hold&&ch.moving&&ch.head)pix(ch.hold==="cup"?ICON.coffee:ICON.snack,ch.head.x+6,ch.head.y+13,.6)}
  for(const st of STATIONS){const ch=CH[st.id];if(ch.spawnHide)continue;const d=ch.data,s=STATE[ch.state]||STATE.idle;
    const lx=st.x+(st.lead?14:12),ly=st.y+9;
    txt(catNameOf(d),lx,ly,{sz:st.lead?5.2:4.7,b:1,c:st.lead?PAL.nameLead:PAL.name});   /* 工位名只画一行：它的名字，没名字退回标签 */
    const sw=statusWord(ch);
    txt(sw,lx,ly+6.2,{sz:4.2,c:s[1]});
    if(ch.hp){const left=d.quota_left_pct,lx0=ch.hp.x+ch.hp.w+1.5,rEdge=lx0+22>WW;   /* v2：靠右墙的猫（会议室右座）标签改画在血条左边，不被墙截掉 */
      txt(ch.state==="off"?TR("q.off"):left==null?TR("q.noData"):TR("q.left",{n:left}),rEdge?ch.hp.x-1.5:lx0,ch.hp.y+2.6,{sz:3.4,al:rEdge?"right":"left",
        c:ch.state==="off"||left==null?"#8d8d9b":left<10?"#ff6b6b":PAL.quota})}
    const sym=persistentSym(ch),sayUp=!!SAYFX[ch.st.slot];   /* ，气泡收起后恢复 */
    if(sym==="bang"){if(!sayUp){youBang(ch,t);if(ch.head)txt(TR("q.yourCall"),ch.head.x-6,ch.head.y-14,{sz:4.6,b:1,c:"#1f2937",bg:"#fde68a",bd:"#d97706"})}}
    else if(sym)drawPersistent(ch,sym,t);   /* 常驻符号在 → 不画活动气泡（一只猫头顶同时只出一样） */
    else drawActBubble(ch);
    if(isTense(ch))drawSweat(ch,t);
  }
  const b=BGT[0];if(b){txt(b.label,PRINTER.x,PRINTER.y+7,{sz:4,c:PAL.dim});
txt(b.state==="run"?TR("q.merging",{n:(b.task_d||"").split(" ")[0]}):(b.state==="off"?(b.state_word||TR("q.offline")):TR("q.idle")),
    PRINTER.x,PRINTER.y+12.5,{sz:3.6,
    c:b.state==="run"?PAL.run:"#6b7280"})}
  if(HOVER){const ch=CH[HOVER];if(ch){const hb=SKIN.hit(ch);hi.strokeStyle="rgba(255,255,255,.35)";hi.lineWidth=Math.max(1,S*.3);hi.setLineDash([S,S]);
    rr(W2(hb.x),W2(hb.y),W2(hb.w),W2(hb.h),S*2);hi.stroke();hi.setLineDash([])}}
  if(ARC_HOVER)txt(uiLang()==="en"?"Party time":"聚会时间",ARCADE.foot[0],ARCADE.foot[1]-ARCADE.h-3.5,{sz:4.6,b:1,c:"#1f1a24",bg:"#fffdf7",bd:"#2b1d12"});
  /* 街机悬停冒一行小字 */
  if(SW_HOVER)txt(modeName(themeMode()),SWITCH.x-3,SWITCH.y+17,{al:"right",sz:4.6,b:1,c:"#1f1a24",bg:"#fffdf7",bd:"#2b1d12"});   /* 开关悬停冒当前档名 */
  if(EMBED)for(const b of DOCK_BTN){   /* 按钮上的字 + 未读数 */
    const en=uiLang()==="en";
    txt(en?b.en:b.zh,b.x+14,b.y+11.5,{al:"left",sz:en?3.3:3.6,b:1,c:"#f8fafc"});
    const n=UNREAD[b.k]||0;if(n>0)txt(String(n),b.x+b.w-4.5,b.y+6.5,{sz:n>9?3:4,b:1,c:"#ffffff"});
  }
}
