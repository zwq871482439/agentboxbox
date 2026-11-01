/* ===================== 
   不写字，全用像素道具和气泡图标：看电影 = 灯调暗 + 幕布放抽象色块 + 桌上一桶爆米花 + 偶尔冒高兴；
   打比赛 = 投影左右两半各一个小游戏（颜色不同），两只选手坐离幕布最近那排座位对战，围观的站桌子两侧外面 / 桌下站位举「加油」小牌，一局结束赢的冒高兴、输的冒无语；
   站会 = 被派的猫和首领全站着（首领在幕布左下方、被派的猫在桌子左右两侧外面），首领一根指示棒指投影上的三列看板（。
   有猫被派活立刻起身回工位（框架 sceneDrop 会做）：看电影 / 围观的走了剩下的继续，选手走了当场散场，没人了收幕布。 */
function sceneIdleCats(){ /* 现在没活的猫（首领也算）：来一局把他们都叫进会议室 */
  return Object.keys(CH).filter(id=>napIdle(CH[id])&&!NAPS.has(id)).sort()}
function sceneMovieCats(){ /* 看电影的观众：首领 + 没在干活（不是「进行中」）的猫；失败 / 等你处理的本就在等人，也去看；下线的来不了 */
  return Object.keys(CH).filter(id=>{const c=CH[id];if(!c||c.state==="off"||c.state==="run")return false;
    if(c.pending||c.deliver||inMeeting(c))return false;if(c.seatT>0)return false;   /* 刚开箱坐满 20 秒的猫不拉（收尾，同 napIdle） */
    return!NAPS.has(id)}).sort()}
function meetSceneTick(){ /* 每帧：没场景时看自动触发；演着时看到点收 / 有人走 */
  if(!SCENE){meetSceneAuto();return}
  const el=T-SCENE.t0;
  if(SCENE.name==="movie"||SCENE.name==="game"){
    for(const id of[...SCENE.ids]){const c=CH[id];   /* 被派活 / 下线：退出场景（看电影时失败 / 等你处理的留下——它们本就在等人，不是在干活；打比赛照旧请走） */
      if(!c||c.state==="off"||c.state==="run"||(SCENE.name==="game"&&(c.state==="fail"||c.state==="you")))sceneDrop(id,"work")}
    if(!SCENE)return}
  if(SCENE.name==="movie"){if(el>=600)sceneEnd("ended");return}   /* 一场约 10 分钟 */
  if(SCENE.name==="game"){
    const pl=SCENE.players||[];
    if(pl.length&&pl.some(id=>!SCENE.ids.has(id))){sceneEnd("assign");return}   /* 选手被派活：当场结束 */
    if(SCENE.doneAt!=null){if(T-SCENE.doneAt>=4)sceneEnd("ended");return}
    const r=SCENE.round||1;
    if(el>=120*r){   /* 一局约 2 分钟；打完一局胜负随机：赢的冒高兴、输的冒无语；最多 3 局 */
      SCENE.winner=pl.length?pl[Math.floor(srand("gwin:"+Math.round(SCENE.t0)+":"+r)()*pl.length)]:null;
      SCENE.roundEnd=T;
      if(r>=3)SCENE.doneAt=T;else SCENE.round=r+1}
    return}
  if(SCENE.name==="standup"){
    const dur=SCENE.dur||40;
    if(el>=dur){   /* 开完了：按 stations 的顺序一只只回工位，间隔约 2 秒；走完了散场 */
      const all=SCENE.stations||[],n=Math.floor((el-dur)/2);
      for(let i=0;i<n&&i<all.length;i++){const id=all[i];if(!SCENE.ids.has(id))continue;SCENE.ids.delete(id);
        const ch=CH[id];if(ch){ch.goal=null;ch.plan=null;ch.hold=null;ch.actDur=0;ch.actT=0;wantHome(ch,ch.state==="run"?"type":"sit")}}
      if(![...SCENE.ids].some(id=>CH[id]&&!(CH[id].st&&CH[id].st.lead)))sceneEnd("ended")}
    return}
}
let GAME_SLOT=-1;   /* 来一局：每个空闲时间片只掷一次骰子 */
function meetSceneAuto(){ /* 自动触发：核心给了 scenes 才看（老 feed 没这个键就不触发）；手动点菜单 / 测试钩子不看这些条件 */
  if(!DATA||!DATA.scenes||!sceneBubblesOn())return;
  if(MEET&&MEET.until>T)return;   /* 正在开派活会 / 验收会 */
  if(napTime())return;            /* 午睡时段不放 */
  const idleW=Object.values(CH).filter(c=>!(c.st&&c.st.lead)&&c.state==="idle"&&!NAPS.has(c.id));
  const is0=DATA.scenes.idle_since,t0=is0?Date.parse(is0):NaN;   /* 放电影：白天（不是夜晚）、全员空闲满 20 分钟、1 小时内没放过 */
  if(THEME.phase!=="night"&&!isNaN(t0)&&Date.now()-t0>=20*60*1000&&Date.now()-(SCENE_LAST.movie||0)>=3600*1000&&idleW.length){sceneStart("movie");return}
  const slot=slotOf();   /* 来一局：至少 2 只打工猫同时空闲，每个空闲时间片 20% 概率，1 小时内不重复 */
  if(slot!==GAME_SLOT){GAME_SLOT=slot;
    if(idleW.length>=2&&Date.now()-(SCENE_LAST.game||0)>=3600*1000&&srand("game:"+slot)()<0.2)sceneStart("game")}
}
function standupStart(e){ /* 派活站会：被派的猫和首领站着围在会议桌前；正放着电影 / 打着比赛就先收场（sceneStart 会 sceneEnd） */
  const stations=(e.stations||[]).filter(id=>CH[id]&&!(CH[id].st&&CH[id].st.lead));
  if(!stations.length&&e.station&&CH[e.station]&&!(CH[e.station].st&&CH[e.station].st.lead))stations.push(e.station);
  const lead=Object.keys(CH).find(id=>CH[id].st&&CH[id].st.lead);
  const ids=stations.slice();if(lead)ids.push(lead);
  if(ids.length)sceneStart("standup",{ids,stations})}
function sceneSpot(ch){ /* 这只猫在会议室场景里的位置；站着还是坐着顺手记在 ch.sceneStand */
  const ids=[...SCENE.ids].sort(),lead=ch.st&&ch.st.lead;
  const workers=ids.filter(id=>CH[id]&&!(CH[id].st&&CH[id].st.lead));
  if(SCENE.name==="standup"){ch.sceneStand=true;   /* 站会全站着（不坐）：首领在幕布左下方（会议桌左上角外侧），被派的猫分站桌子左右两侧外面（先左后右交替，多了用桌下站位），两两身体矩形不相交、不压幕布 */
    if(lead)return[380,140];
    const spots=[[378,164],[466,140],[378,195],[466,164],[466,188],[398,201],[446,201]];
    return spots[Math.max(0,workers.indexOf(ch.id))%spots.length]}
  if(SCENE.name==="game"){
    const pi=(SCENE.players||[]).indexOf(ch.id);
    if(pi>=0){ch.sceneStand=false;return[[382,148],[462,148]][pi]}   /* 选手坐离幕布最近那排（桌子上端左右两个座位），面朝幕布对战 */
    ch.sceneStand=true;   /* 围观的：普通猫先站桌子左右两侧外面、再桌下站位；首领个子高，直接站桌下站位（举牌不挡选手） */
    const ws=ids.filter(id=>!(SCENE.players||[]).includes(id));
    if(lead)return MEET_STAND[ws.filter(id=>CH[id].st&&CH[id].st.lead).indexOf(ch.id)%MEET_STAND.length];
    const w=ws.filter(id=>!(CH[id].st&&CH[id].st.lead));
    const spots=[[376,180],[468,180],[446,201],[470,201]];
    return spots[Math.max(0,w.indexOf(ch.id))%spots.length]}
  /* 看电影：首领坐桌头，成员先坐两侧 4 座，坐不下站桌下站位（和开会一个规矩） */
  if(lead){ch.sceneStand=false;return MEET_HEAD}
  const wi=Math.max(0,workers.indexOf(ch.id));
  ch.sceneStand=wi>=MEET_SEATS.length;
  return ch.sceneStand?MEET_STAND[(wi-MEET_SEATS.length)%MEET_STAND.length]:MEET_SEATS[wi]}
function meetSceneStep(ch,dt){ /* 场景里的猫这一帧全交给场景：走到自己的位子坐下 / 站定就不动。返回 true = 这一帧已处理 */
  if(!SCENE||!SCENE.ids.has(ch.id))return false;
  if(inMeeting(ch))return false;   /* 真要开会了让出会议室（startMeeting 已经把场景收了，这里只是兜底） */
  const spot=sceneSpot(ch);
  if(ch.inBox)leaveBox(ch);
  if(Math.hypot(ch.x-spot[0],ch.y-spot[1])>2.5){if(!ch.moving||ch.goal!=="scene"){goTo(ch,spot[0],spot[1],true);ch.goal="scene"}moveStep(ch,dt);return true}
  if(ch.moving){moveStep(ch,dt);return true}
  ch.plan=null;ch.hold=null;ch.act=ch.sceneStand?"stand":"sit";ch.face=ch.x<422?1:-1;
  if(ch.st&&ch.st.lead)ch.bossAnim="sit";
  return true}
/* ---- 场景画面道具：全用像素图形，不写字 ---- */
const MOVIE_COLS=["#ef4444","#f59e0b","#22c55e","#3b82f6","#a855f7"];
function movieScreen(t){ /* 放电影：投影把幕布打亮——亮底上一幅会动的像素画（太阳慢慢挪 / 远山慢慢飘 / 前景色块），不能暗成一片 */
  R(390,72,64,26,"#cdd9f6");R(390,72,64,12,"#b4c6f1");
  R(448-((t*2.2)%46),74,5,5,"#fff3b0");R(449-((t*2.2)%46),75,3,3,"#ffe27a");   /* 太阳慢慢挪 */
  for(let i=0;i<3;i++){const w=16+i*8,x=390+((t*(2.5+i)+i*23)%76)-8,h=4+i*2;
    R(x,96-h,w,h,"#93a4cc");R(x,96-h,w,1,"#7e90bd")}   /* 远山慢慢飘 */
  for(let i=0;i<3;i++){const w=7+i*2,x=391+((t*(2+i*1.3)+i*19)%54),y=77+((i*4+Math.floor(t*.6)*2)%9);
    R(x,y,w,3,MOVIE_COLS[(i+Math.floor(t*.5))%MOVIE_COLS.length])}   /* 前景飘过的色块 */
  R(390,96,64,2,"#8fa3d8")}
function gameScreen(t){ /* 打比赛：左半像素小人跳（蓝底），右半方块下落（紫底），两半颜色不一样 */
  R(390,72,32,26,"#172554");R(422,72,32,26,"#3b0764");
  const jx=399+Math.sin(t*.9)*8,jy=90-Math.abs(Math.sin(t*3))*10;
  R(392,94,26,1,"#38bdf8");R(jx,jy,3,4,"#facc15");R(jx+.5,jy-1.5,2,1.5,"#facc15");   /* 地面 + 跳的小人 */
  R(424,94,26,1,"#a855f7");
  for(let i=0;i<3;i++){const fy=73+((t*9+i*11)%20);R(427+i*8+(i%2)*2,fy,4,4,["#f472b6","#4ade80","#fb923c"][i])}   /* 下落的方块 */
}
const SIGN_COLS=["#facc15","#f472b6"];
function drawSceneDim(){ /* 看电影灯调暗：暗色层只盖会议室地面和桌子，不盖幕布和投影光（画在投影机之前） */
  if(SCENE&&SCENE.name==="movie"){const Z=ZONE.meet;g.save();g.globalAlpha=.45;R(Z.x,104,Z.w,Z.y+Z.h-104,"#0b0b14");g.restore()}}
function drawSceneFx(t){ /* 世界层道具：看电影桌上爆米花；打比赛围观猫举牌；站会首领拿指示棒 */
  if(!SCENE)return;
  if(SCENE.name==="movie"){
    R(406,142,9,2,"#fde047");R(407,141,7,1,"#fde047");   /* 桌上一桶爆米花：黄色顶 */
    R(406,144,9,7,"#f8fafc");for(let i=0;i<9;i+=3)R(406+i,144,1.5,7,"#ef4444");   /* 红白条纹小桶 */
    R(406,144,9,1,"#dc2626");R(405,151,11,1,"#d6d3d1")}
  else if(SCENE.name==="game"){   /* 围观猫举「加油」小牌：6×4 纯色牌（黄 / 粉）举在头顶上方，小棍连着头，举起放下看得出来 */
    const watchers=[...SCENE.ids].map(id=>CH[id]).filter(c=>c&&c.head&&!(SCENE.players||[]).includes(c.id));
    watchers.forEach((c,i)=>{const up=Math.sin(t*3+i*1.7)>0?2:0,sx=c.head.x-3,sy=c.head.y-8-up;
      R(sx,sy,6,4,SIGN_COLS[i%SIGN_COLS.length]);R(c.head.x-.5,sy+4,1,c.head.y-sy-4,"#92400e")})}
  else if(SCENE.name==="standup"){   /* 首领手里一根指示棒（深棕色 2 像素粗）斜着伸到幕布上的看板 */
    const lead=Object.values(CH).find(c=>c.st&&c.st.lead&&SCENE.ids.has(c.id));
    if(lead&&!lead.moving){const x0=lead.x+5,y0=lead.y-7,x1=400,y1=90,n=Math.ceil(Math.hypot(x1-x0,y1-y0));
      for(let i=0;i<=n;i++)R(x0+(x1-x0)*i/n-1,y0+(y1-y0)*i/n-1,2,2,"#6b4423")}}
}
let SCENE_BUBS=[];   /* 这一帧画出去的场景气泡（测试钩子 sceneBubs 读） */
function drawSceneBubbles(t){ /* 气泡层：看电影偶尔冒高兴；打比赛一局结束赢的冒高兴、输的冒无语 */
  SCENE_BUBS=[];if(!SCENE)return;
  if(SCENE.name==="movie"){
    const slot=Math.floor(t/8),age=t-slot*8;if(age>=2.4)return;
    const cats=[...SCENE.ids].map(id=>CH[id]).filter(c=>c&&c.head&&!c.moving&&!c.inBox);
    if(!cats.length)return;const ch=cats[hash("movb"+slot)%cats.length];
    const al=Math.min(1,age/.18,(2.4-age)/.3);if(al<=0)return;
    SCENE_BUBS.push({id:ch.id,icon:"happy"});drawPixBubble(ch,"happy",al,(1-al)*2)}
  else if(SCENE.name==="game"&&SCENE.winner!=null&&SCENE.roundEnd!=null&&T-SCENE.roundEnd<3){
    const age=T-SCENE.roundEnd,al=Math.min(1,age/.18,(3-age)/.3);if(al<=0)return;
    const w=CH[SCENE.winner],lid=(SCENE.players||[]).find(id=>id!==SCENE.winner),l=CH[lid];
    if(w&&w.head){SCENE_BUBS.push({id:w.id,icon:"happy"});drawPixBubble(w,"happy",al,0)}
    if(l&&l.head){SCENE_BUBS.push({id:l.id,icon:"meh"});drawPixBubble(l,"meh",al,0)}}
}
