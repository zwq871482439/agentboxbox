/* ===================== =====================
   场景分两类：会议室场景（放电影 / 来一局 / 站会 / 庆祝…，画面第 2、3 张卡做）全场同一时间最多一个；
   不进会议室的场景（分头午睡 / 加班夜宵）按猫各自生效，可以和别的场景同时存在。
   有猫被派活（state 变成 run）就让它立刻退出场景回工位；派活会 / 验收会开始时会议室场景结束。
   每种场景记最近一次开始的时间（后面「1 小时内不重复」用）。 */
const SCENE_MEET=["movie","game","standup","celebrate","wrapup","postmortem"];   /* 会议室场景名单（画布 2/3 已加站会；第 3 张卡的庆祝 / 复盘再往里加） */
let SCENE=null;                        /* 当前会议室场景 {name,t0,ids:Set,hadIds,...}；没有就是 null */
let SCENE_LAST={};                     /* 每种场景最近一次开始的时间（Date.now 毫秒） */
const NAPS=new Map();                  /* 分头午睡：猫 id → {t0,where:"sofa"|"desk",spot} */
const SNACKS=new Set();                /* 加班夜宵：桌上有外卖盒的猫 id */
let NAP_FORCE=0;                       /* 测试钩子直接开演的午睡：睡到这个模拟时刻为止 */
let SNACK_PHASE=null;                  /* 上一帧的天色（夜里摆盒，第一次离开夜晚才收盒） */
function nowDate(){return new Date(Date.now())}   /* 场景用的钟：测试把 Date.now 钉住时它也跟着钉住 */
function napTime(d){ /* 午睡时段：本地时间 12:00–14:00（这个时段里不触发放电影 / 来一局） */
  d=d||nowDate();const m=d.getHours()*60+d.getMinutes();return m>=720&&m<840}
function sceneIsMeet(name){return SCENE_MEET.includes(name)}
function sceneStart(name,opts){ /* 开一个场景：会议室场景全场只能同时一个（先散掉现有场景；）；午睡 / 夜宵按猫各自生效 */
  opts=opts||{};SCENE_LAST[name]=Date.now();
  if(sceneIsMeet(name)){
    if(napTime()&&(name==="movie"||name==="game"))return SCENE;   /* 午睡时段不放电影 / 不来一局 */
    sceneEnd("switch");
    let ids=opts.ids;
    if(!ids){ /* 没点名：看电影 / 来一局把现在没活的猫（首领也算）都叫上；站会把被派的猫和首领叫上 */
      if(name==="standup"){const ws=Object.keys(CH).filter(id=>!(CH[id].st&&CH[id].st.lead)).sort();
        opts=Object.assign({},opts,{stations:ws});   /* 测试钩子直接开站会：拿现在的打工猫假装一批 */
        ids=ws.concat(Object.keys(CH).filter(id=>CH[id].st&&CH[id].st.lead))}
      else ids=name==="movie"?sceneMovieCats():sceneIdleCats()}   /* 看电影：没在干活的都去（含失败 / 等你处理）；来一局还是只有空闲的 */
    SCENE={name,t0:T,ids:new Set(ids),hadIds:!!ids.length};
    if(opts.stations)SCENE.stations=opts.stations.filter(id=>CH[id]&&!(CH[id].st&&CH[id].st.lead));   /* 站会散场顺序 */
    if(name==="standup")SCENE.dur=30+Math.floor(srand("standup:"+Math.round(T))()*31);   /* 站会开 30–60 秒 */
    if(name==="game")SCENE.players=[...SCENE.ids].filter(id=>!(CH[id].st&&CH[id].st.lead)).sort().slice(0,2);   /* 两只选手坐桌头两侧 */
    return SCENE}
  if(name==="nap")napStart(!!opts.force);
  else if(name==="snack")snackStart(!!opts.force);
  return null}
function sceneEnd(reason){ /* 会议室场景结束：参与的猫清掉目标回去各干各的（画面第 2 张卡接） */
  if(!SCENE)return;
  const ids=[...SCENE.ids];SCENE=null;
  for(const id of ids){const ch=CH[id];if(ch&&!NAPS.has(id)){ch.goal=null;ch.plan=null;ch.hold=null;ch.actDur=0;ch.actT=0}}
}
function sceneDrop(id,why){ /* 一只猫退出场景（被派活回工位）：会议室名单里去掉，午睡的醒来 */
  if(SCENE&&SCENE.ids){SCENE.ids.delete(id);if(SCENE.hadIds&&!SCENE.ids.size)sceneEnd(why||"left")}
  const ch=CH[id];if(ch&&NAPS.has(id))napWake(ch,why||"assign")}
function sceneTick(){napTick();snackTick();meetSceneTick();partyTick()}

/* ---- 分头午睡（本地 12:00–14:00 没活的猫去睡。沙发最多 2 只（蜷着，现有沙发睡姿），多的趴自己工位；
   被派活就醒（伸个懒腰后回工位干活），到 14:00 全部醒来伸懒腰。首领也算没活的猫。 ---- */
function napIdle(ch){ /* 没活的猫（按猫单独判）：打工猫要空闲；首领没在干活 / 没等拍板就行 */
  const st=ch.state;
  if(SCENE&&PARTY.includes(SCENE.name)&&SCENE.ids.has(ch.id))return false;   /* –庆祝 / 复盘里的猫不睡 */
  if(st==="off"||st==="run"||st==="fail"||st==="you")return false;
  if(ch.pending||ch.deliver||inMeeting(ch))return false;
  if(ch.seatT>0)return false;   /* 收尾：刚开箱的猫先坐满 20 秒，场景（来一局 / 午睡）不拉它，免得一落地就被叫走 */
  return ch.st.lead||st==="idle"}
function napStart(force){ /* 开演：测试钩子可以直接开（不看钟）；自然触发只看钟 */
  if(force)NAP_FORCE=T+7200;
  napJoin()}
function napJoin(){ /* 把还没睡的没活猫排进午睡：沙发 2 个位按 id 排先到先得（稳定），多的趴工位 */
  const ids=Object.keys(CH).filter(id=>napIdle(CH[id])&&!NAPS.has(id)).sort();
  if(!NAPS.size&&ids.length)SCENE_LAST.nap=Date.now();
  let sofa=[...NAPS.values()].filter(n=>n.where==="sofa").length;
  for(const id of ids){
    let where="desk",spot=null;
    if(sofa<2){where="sofa";spot=SPOTS.sofa[sofa];sofa++}
    NAPS.set(id,{t0:T,where,spot})}}
function napWake(ch,why){ /* 醒来：伸个懒腰（现有 stretch 动作），伸完该干嘛干嘛 */
  if(!ch)return;NAPS.delete(ch.id);
  ch.plan=null;ch.hold=null;ch.path=[];ch.moving=false;
  if(ch.st.lead)ch.bossAnim="sit";
  ch.wakeT=3.2;ch.act="stretch";ch.actT=0}
function napTick(){ /* 每帧：进了时段把没活的猫排去睡；出了时段全醒；睡着以后有活的（被派活）单只醒 */
  if(napTime())NAP_FORCE=0;
  if(napTime()||T<NAP_FORCE)napJoin();
  else for(const id of[...NAPS.keys()]){const ch=CH[id];if(ch)napWake(ch,"time")}
  for(const id of[...NAPS.keys()]){const ch=CH[id];if(!ch||!napIdle(ch))napWake(ch,"work")}}
function napStep(ch,dt){ /* 午睡中的猫这一帧：去沙发 / 趴工位，睡着了就不动；要开会的先醒来 */
  const n=NAPS.get(ch.id);if(!n)return false;
  if(inMeeting(ch)){napWake(ch,"meet");return false}
  if(n.where==="desk"){ /* 趴自己工位：回箱子里睡（身体压低 + 头上 Zzz） */
    if(!ch.inBox){wantHome(ch,"sleepbox");moveStep(ch,dt);return true}
    ch.plan=null;ch.act="sleepbox";if(ch.st.lead)ch.bossAnim="nap";return true}
  if(ch.inBox)leaveBox(ch);
  if(ch.moving){moveStep(ch,dt);return true}
  if(Math.hypot(ch.x-n.spot[0],ch.y-n.spot[1])>2.5){goTo(ch,n.spot[0],n.spot[1]);moveStep(ch,dt);return true}
  ch.plan=null;ch.act="sofanap";if(ch.st.lead)ch.bossAnim="nap";return true}

/* ---- 加班夜宵（夜晚（跟昼夜切换的「夜」一致）在干活的猫，工位桌上摆一个外卖盒（一晚每只一次，记在本机）；
   盒子留到天亮（第一次离开夜晚）才收走；干活中偶尔冒「累」的气泡（actKind 里的 tired 图标）。 ---- */
function snackNightId(){ /* 一晚一个 id：中午 12 点以后算当天，凌晨算昨天那一晚 */
  const d=nowDate();if(d.getHours()<12)d.setDate(d.getDate()-1);
  return d.getFullYear()+"-"+(d.getMonth()+1)+"-"+d.getDate()}
function snackRec(){ /* 本机记的「这一晚已经摆过盒的猫」：刷新页面同一晚不重复出现 */
  try{const v=localStorage.getItem("bx-snack")||"",i=v.indexOf("|");
    return i<0?["",[]]:[v.slice(0,i),v.slice(i+1).split(",").filter(Boolean)]}catch(e){return["",[]]}}
function snackRecSave(nid,ids){try{localStorage.setItem("bx-snack",nid+"|"+ids.join(","))}catch(e){}}
function snackStart(force){ /* 开演：夜里在干活的猫桌上摆盒（force 是测试钩子，不看天色也不记本机） */
  if(force){ /* 认 feed 里的状态：刚被派活的猫可能还在午睡醒来的懒腰里，画布上的 state 晚一两秒才变 */
    const run=new Set((DATA&&DATA.channels||[]).filter(c=>c.state==="run").map(c=>c.id));
    for(const id in CH)if(CH[id].state==="run"||run.has(id))SNACKS.add(id);return}
  snackTick()}
function snackTick(){ /* 每帧：夜里给在干活的猫摆盒（每只一晚一次，第一次摆就记进本机，刷新不重复）；一离开夜晚收盒 */
  for(const id of[...SNACKS])if(!CH[id])SNACKS.delete(id);
  if(THEME.phase==="night"){
    const nid=snackNightId(),[rn,rids]=snackRec(),done=new Set(rn===nid?rids:[]);
    let added=false;
    for(const id in CH){const c=CH[id];
      if(c.state==="run"&&!SNACKS.has(id)&&!done.has(id)){SNACKS.add(id);done.add(id);added=true}}
    if(added){snackRecSave(nid,[...done]);SCENE_LAST.snack=Date.now()}}   /* 盒子留到白天才收，但记录当晚就写 */
  else if(SNACK_PHASE==="night")SNACKS.clear();   /* 盒子留到白天：第一次离开夜晚才收 */
  SNACK_PHASE=THEME.phase}
function snackOn(ch){return SNACKS.has(ch.id)&&THEME.phase==="night"&&ch.state==="run"}
