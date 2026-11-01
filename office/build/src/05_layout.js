/* ===================== 场景 / 布局 ===================== */
const BOSS={x:228,y:118}, PRINTER={x:436,y:252}, CUSHION={x:40,y:228}, TEA={x:30,y:112};
const ZONE={tea:{x:4,y:64,w:104,h:94},sofa:{x:4,y:162,w:104,h:104},desk:{x:112,y:64,w:254,h:202},meet:{x:370,y:64,w:106,h:140}};
const SPOTS={coffee:[[26,132],[40,134]],fridge:[[84,134],[72,136]],sofa:[[28,214],[46,214],[64,214],[82,214]],
  rug:[[22,226],[86,228]],table:[[32,244],[76,244]],brew:[[54,126]],fridgeopen:[[62,126]]};  /* 融合：原型的「地毯刷手机」「茶几喝茶」搬进沙发区 */
/* v2 大落地窗（office-v2/spec.md 第 1、3 节）：5 扇窗 + 城市天际线，换掉原墙面；左边小窗和右边绿植去掉 */
const WIN={x:146,y:2,w:198,h:59};
const TODO_BOARD={x:296,y:64,w:42,h:30};   /* 立式白板：首领工位右边，「待办 N」+ 便利贴，点它弹明细 */
/* v2 固定 7 个工位（）：首领上方居中 + 打工猫 A–F 两排各 3 个，位置写死，不随工位数量重排 */
const SLOT_ORDER=["A","B","C","D","E","F"];
const SLOT_POS={A:[146,186],B:[226,186],C:[306,186],D:[146,246],E:[226,246],F:[306,246]};
/* v2 会议室（office-v2/spec.md 第 7 节）：两侧各 2 座给成员，桌头 1 座固定给 TeamLeader；人多站 MEET_STAND。
   ；
   左右座位间距拉开，7 只猫全开会时任两只的头矩形（±10，y-31..-11）/ 身体矩形（±7，y-14..+1；首领 1.25 倍）两两都不相交；
   后两个站位是门口两侧的溢出位（最多 6 只打工猫，平时用不到） */
const MEET_SEATS=[[382,148],[462,148],[382,180],[462,180]],MEET_HEAD=[422,200],MEET_STAND=[[398,201],[446,201],[374,201],[470,201]];
const PROJ={k:0,t0:0,was:false};   /* 投影幕布：k 0=卷起 1=全放下 */
const GATHER_SPOTS=[[194,164],[281,164],[162,138],[314,138],[122,138],[354,138]];
/* ，相邻至少隔一只猫的宽度，不压首领的箱子 / 名字标签 / 头顶，? 各自在头顶互不压 */
let ACTLOG=[];
let STATIONS=[], CH={}, ENVS=[], PUFFS=[], BGT=[];
const MAX_WS=6;
let SLOT_MEM={};   /* 没给 slot 的老数据：记住谁坐哪，工位数量变化时其它猫不挪 */
function slotFor(chans){ /* 频道 → 槽位：feed 给了 slot（"A"…"F"）就坐自己的；没给的按顺序补空位，坐过的记住 */
  const out={},used=new Set();
  for(const c of chans){if(c.role==="lead")continue;const s=String(c.slot||"").toUpperCase();
    if(SLOT_ORDER.includes(s)&&!used.has(s)){out[c.id]=s;used.add(s)}}
  for(const id in SLOT_MEM)if(chans.some(c=>c.id===id&&c.role!=="lead")&&!out[id]&&!used.has(SLOT_MEM[id])){out[id]=SLOT_MEM[id];used.add(SLOT_MEM[id])}
  for(const c of chans){if(c.role==="lead"||out[c.id])continue;const s=SLOT_ORDER.find(x=>!used.has(x));if(!s)continue;out[c.id]=s;used.add(s)}
  SLOT_MEM=out;return out}
function syncData(d){
  DATA=d;const chans=(d.channels||[]).filter((c,i,a)=>c.role==="lead"||a.filter(x=>x.role!=="lead").indexOf(c)<MAX_WS);const prev=CH;CH={};
  const slots=slotFor(chans);
  STATIONS=[];let wi=0;
  const evDriven=Array.isArray(d.events);   /* 核心给了事件流：开会 / 丢信全按事件来，状态差异不再自己猜 */
  chans.forEach((c,i)=>{
    const lead=c.role==="lead", p=lead?BOSS:{x:SLOT_POS[slots[c.id]][0],y:SLOT_POS[slots[c.id]][1]};
    const st={id:c.id,lead,slot:lead?"leader":slots[c.id],x:p.x,y:p.y,seed:hash(c.id)%997,accent:lead?null:(c.accent||ACCENTS[wi%ACCENTS.length])};
    if(!lead)wi++;
    STATIONS.push(st);
    let ch=prev[c.id],isNew=!ch;
    const lk=c.look&&typeof c.look==="object"?c.look:null;   /* 工位配了固定装扮（猫 + 配饰）就按它画；没有 look 的老工位照老规矩轮流分猫 */
    const catNo=lk&&lk.cat>=1&&lk.cat<=8?lk.cat:(lead?1:((c.skin&&c.skin.cat&&c.skin.cat>1)?c.skin.cat:[2,4,5,3,6][(wi-1)%5]));
    if(!ch){ch={id:c.id,x:p.x,y:p.y+3,face:1,inBox:true,act:"sit",t:rnd(0,5),actT:0,actDur:0,cat:catNo,state:c.state,bossAnim:"sit",
      workScene:WORK_SCENES[st.seed%3],playScene:PLAY_SCENES[(hash(c.id+"p"))%4],path:[]};ch.shown=c.state}
    if(isNew&&c.pending_open)ch.spawnHide=true;   /* 第 6 条：刚招、还在开箱 → 先不画它，等开箱动画演完再出来 */
    else if(!evDriven&&ch.shown!==c.state&&c.state==="run"&&ch.shown!=="run"&&!lead){dispatch(ch,st,c.state)}
    else if(!lead&&ch.shown==="run"&&c.state==="idle"&&!ch.pending){ch.deliver=true;ch.goal=null;ch.shown=c.state}
    /* 刚做完 → 抱文件去交活（和 TeamLeader 进会议室验收）；shown 要跟上，否则每次轮询都重新交一遍 */
    else if(!ch.pending)ch.shown=c.state;
    if(!lead&&c.state==="run"&&ch.state!=="run")sceneDrop(c.id,"assign");   /* 被派活：立刻退出场景回工位 */
    ch.cat=catNo;ch.look=lk;ch.data=c;ch.st=st;ch.state=ch.pending?ch.shown:c.state;CH[c.id]=ch;
  });
  BGT=d.background||[];
  STATIONS.sort((a,b)=>a.y-b.y);
  if(evDriven)applyEvents(d.events);
  feedAnimSync(prev);   /* live 模式下 feed 里新增 / 消失的打工猫播上岗 / 抬走动画（页面刚打开那次不播） */
  renderStrip();renderList();renderAlertBar();if(OPEN)openDrawer(OPEN);
}
/* 开会和丢信是两件事，按核心的事件流来——
   assign（第一次把卡交给这只猫）= 开会：TeamLeader 和它进会议室 9 秒，没有信封；
   redispatch（同一张卡打回再派）/ post（工位之间留言）= 丢信：信封飞过去落地冒星星，不开会；
   delivered / done 交活动作由状态差异（run→idle 抱文件进会议室）照旧触发，这里不重复。
   页面刚打开时只记下最新事件号，不回放旧事件。 */
let EV_SEEN=null;
function applyEvents(evs){
  let maxId=EV_SEEN;
  for(const e of evs){if(e&&typeof e.id==="number"&&(maxId==null||e.id>maxId))maxId=e.id}
  if(EV_SEEN==null){EV_SEEN=maxId;return}
  const fresh=evs.filter(e=>e&&typeof e.id==="number"&&e.id>EV_SEEN).sort((a,b)=>a.id-b.id);
  EV_SEEN=maxId;
  for(const e of fresh){
    if(e.kind==="standup"){standupStart(e);continue}   /* 派活站会：被派的一批猫 + 首领去会议室站着开会（只看新来的事件，上面已按 id 去重） */
    const ch=CH[e.station];if(!ch||ch.st.lead)continue;
    if(e.kind==="assign")meet(ch,"assign");
    else if(e.kind==="redispatch"||e.kind==="post")envelope(ch,ch.st,CH[e.from]);
  }
}
function meet(ch,why){ /* 开会：不丢信封，TeamLeader 小跑进会议室，猫也去；开完各自回座 */
  startMeeting(ch.id,why);ch.pending=null;ch.shown=ch.state=ch.data.state;
}
function envelope(ch,st,fromCh){ /* 丢信：从发信方（缺省 TeamLeader 的电脑）弧线飞到这只猫，落地冒星星 + 欢呼；不开会、不改状态 */
  const from=fromCh&&!fromCh.st.lead?{x:fromCh.x,y:fromCh.y-20}:{x:BOSS.x+34,y:BOSS.y-30};
  const to=ch.inBox?{x:st.x,y:st.y-24}:{x:ch.x,y:ch.y-24};
  const dist=Math.hypot(to.x-from.x,to.y-from.y);
  ENVS.push({ch,from,to,t:0,dur:.8+dist/170,arc:Math.min(26,dist*.3)+6,mail:true});
  const boss=Object.values(CH).find(c=>c.st&&c.st.lead);
  if(!fromCh||fromCh.st.lead){if(boss)boss.toss=.5}else fromCh.toss=.5;
}
function dispatch(ch,st,ns){ // 老路（样例 / 演示，没有事件流）：信封飞过去，落地后再切状态，同时开会
  const from={x:BOSS.x+34,y:BOSS.y-30};const to=ch.inBox?{x:st.x,y:st.y-24}:{x:ch.x,y:ch.y-24};
  ch.pending=ns;const dist=Math.hypot(to.x-from.x,to.y-from.y);
  ENVS.push({ch,from,to,t:0,dur:.8+dist/170,arc:Math.min(26,dist*.3)+6});
  startMeeting(ch.id,"assign");
  const boss=Object.values(CH).find(c=>c.st&&c.st.lead)||Object.values(CH)[0];
  if(boss&&boss.st&&boss.st.lead){boss.toss=.5}
}
