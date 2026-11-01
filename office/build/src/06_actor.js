/* ===================== 行为引擎 ===================== */
function blocked(x,y){return STATIONS.some(s=>x>s.x-19&&x<s.x+(s.lead?50:42)&&y>s.y-13&&y<s.y+5)||animBlocked(x,y)}
/* animBlocked：送货 / 抬走期间，别的猫不走进正在送货的路线 */
function segOK(a,b){const n=Math.max(1,Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/2));for(let i=1;i<n;i++){const t=i/n;if(blocked(a[0]+(b[0]-a[0])*t,
  a[1]+(b[1]-a[1])*t))return false}return true}
function route(from,to){ // 绕开工位走：直线不通就走工位前 / 后的过道
  if(segOK(from,to))return[to];
  const ys=[...new Set(STATIONS.flatMap(s=>[s.y+9,s.y-17]))].sort((a,b)=>(Math.abs(a-from[1])+Math.abs(a-to[1]))-(Math.abs(b-from[1])+Math.abs(b-to[1])));
  for(const y of ys){const p1=[from[0],y],p2=[to[0],y];if(segOK(from,p1)&&segOK(p1,p2)&&segOK(p2,to))return[p1,p2,to]}
  return[to]}
function goTo(ch,x,y,hurry){ch.path=route([ch.x,ch.y],[x,y]);ch.moving=true;ch.hurry=!!hurry;ch.inBox=false}
function leaveBox(ch){if(ch.inBox){ch.inBox=false;ch.x=ch.st.x;ch.y=ch.st.y+7;PUFFS.push({x:ch.st.x,y:ch.st.y-12,t:0})}}
function homeIn(ch){ch.inBox=true;ch.moving=false;ch.x=ch.st.x;ch.y=ch.st.y+7;PUFFS.push({x:ch.st.x,y:ch.st.y-12,t:0})}
function wantHome(ch,act,hurry){if(ch.inBox){ch.act=act;return}
  const hx=ch.st.x,hy=ch.st.y+7;
  if(Math.hypot(ch.x-hx,ch.y-hy)<2){homeIn(ch);ch.act=act}else if(!ch.moving||ch.goal!=="home"){goTo(ch,hx,hy,hurry);ch.goal="home";ch.after=act}}
/* 开会（近似）：派活 / 验收后 MEET_S 秒，TeamLeader 和相关的猫进会议室 */
const MEET_S=9;let MEET=null;
function startMeeting(id,why){MEET={ids:new Set([id,...(MEET&&MEET.until>T?MEET.ids:[])]),until:T+MEET_S,why};sceneEnd(why)}   /* 开会：会议室要让出来，正在演的会议室场景结束 */
function inMeeting(ch){return MEET&&MEET.until>T&&(MEET.ids.has(ch.id)||ch.st.lead)}
function meetArrived(){return Object.values(CH).filter(c=>inMeeting(c)&&c.goal==="meet"&&!c.moving&&!c.inBox)}
function meetReady(){if(!(MEET&&MEET.until>T))return false;const a=meetArrived();return a.length>=2&&a.some(c=>c.st.lead)&&a.some(c=>!c.st.lead)}
function meetSeat(ch){ /* 桌头 1 座固定给 TeamLeader；成员按 id 排序先坐两侧 4 座，多了站 MEET_STAND（用完循环），站着的做 stand 不做 sit */
  if(ch.st&&ch.st.lead)return MEET_HEAD;
  const ids=[...Object.values(CH)].filter(c=>inMeeting(c)&&!(c.st&&c.st.lead)).map(c=>c.id).sort();const i=Math.max(0,ids.indexOf(ch.id));
  ch.meetStand=i>=MEET_SEATS.length;return ch.meetStand?MEET_STAND[(i-MEET_SEATS.length)%MEET_STAND.length]:MEET_SEATS[i]}
function pickIdle(ch){
  if(SKIN.zoned)return pickIdleZoned(ch);
  const acts=SKIN.idleActs;let tot=acts.reduce((s,a)=>s+a.w,0),r=Math.random()*tot,A=acts[0];for(const a of acts){if((r-=a.w)<=0){A=a;break}}
  ch.actT=0;ch.actDur=A.a==="stretch"?3.4:rnd(5,9);ch.goal=null;
  if(A.where==="box"){ch.plan=A.a;wantHome(ch,A.a)}
  else{leaveBox(ch);ch.plan=A.a;
    if(A.where==="wander"){ch.act=A.a;let cur=[ch.x,ch.y];const pts=[];for(let i=0;i<3;i++){const q=randFloor();pts.push(...route(cur,q));cur=q}ch.path=pts;
      ch.moving=true;ch.hurry=false;ch.goal="wander"}
    else if(A.where==="spot"){const p=randFloor();goTo(ch,p[0],p[1]);ch.goal="spot";ch.after=A.a}
    else if(A.where==="tea"){goTo(ch,TEA.x-6+rnd(-1,1),TEA.y+15);ch.goal="spot";ch.after="tea"}
    else if(A.where==="rug"){goTo(ch,rnd(22,36),rnd(123,127));ch.goal="spot";ch.after=A.a}
    else{ch.act=A.a;ch.moving=false}}
}
function pickIdleZoned(ch,force){ /* 空闲：按种子在 茶水间（咖啡 / 冰箱）、沙发区、工位上摸鱼、伸懒腰、串门 里挑一件，同一时间片结果固定 */
  if(ch.plan&&ch.actDur>0)ACTLOG.push({id:ch.id,plan:ch.plan,held:ch.actT,dur:ch.actDur});if(ACTLOG.length>500)ACTLOG.shift();
  const slot=slotOf(), r=srand(ch.id+":"+slot+":"+(ch.pickN=(ch.pickN||0)+1));ch.slot=slot;ch.actT=0;ch.goal=null;
  const idle=Object.values(CH).filter(c=>!c.st.lead&&c.state==="idle").map(c=>c.id).sort();
  /* 融合：加回原型的 溜达 wander、地毯刷手机 rugphone；工位喝茶 / 茶几喝茶 v2 并入咖啡机连锁 */
  /* v2：喝茶/咖啡都从咖啡机起步（不再有凭空的工位喝茶）；零食从冰箱起步；没开会时会议室可以摸鱼，2 只以上空闲可以打牌 */
  const meetFree=!(MEET&&MEET.until>T)&&!SCENE;   /* 会议室演着场景（看电影 / 打比赛 / 站会）时也不去会议室摸鱼 / 打牌 */
  const acts=[["coffee",3],["fridge",2],["sofa",3],["deskplay",2],["sleepbox",1.5],["stretch",1],["wander",1.5],["rugphone",1.2]];
  if(meetFree)acts.push(["meetslack",1]);
  if(idle.length>=2)acts.push(["visit",2.5]);
  if(idle.length>=2&&meetFree)acts.push(["cards",2]);
  let tot=acts.reduce((a,x)=>a+x[1],0),v=r()*tot,A=acts[0][0];for(const [a,w] of acts){if((v-=w)<=0){A=a;break}}
  if(force)A=force;
  /* 电脑上玩是长活动 12–18 秒；其他空闲小动作 5–8 秒。时长从「到地方」开始算（moveStep 到达时 actT 归零），路上不算 */
  ch.actDur=A==="deskplay"?12+r()*6:5+r()*3;
  if(A==="teabox"||A==="tabletea"||A==="tea")A="coffee";
  if(A==="coffee"&&ch.cup>0){ch.cup--;ch.actDur=3+r()*2;ch.plan="sip";wantHome(ch,"drink");return}   /* 杯里还有：坐回工位喝一口 */
  ch.plan=A;
  if(A==="deskplay")ch.playScene=["shooter","snake","blocks"][Math.floor(r()*3)];   /* 和原型一样：工位电脑上玩射击 / 贪吃蛇 / 方块 */
  if(A==="deskplay"||A==="sleepbox"){wantHome(ch,A);return}
  if(A==="stretch"){wantHome(ch,"sit");ch.after2="stretch";return}
  leaveBox(ch);
  if(A==="visit"){const mates=idle.filter(x=>x!==ch.id),m=CH[mates[Math.floor(r()*mates.length)]];if(m){goTo(ch,m.st.x+(m.st.x<ch.st.x?30:-24),m.st.y+9);
    ch.goal="spot";ch.after="chat";ch.mate=m.id;return}}
  if(A==="wander"){startWander(ch);return}
  if(A==="coffee"){const [x,y]=SPOTS.brew[0];goTo(ch,x+(hash(ch.id)%2)*6,y);ch.goal="spot";ch.after="brew";ch.faceTo=26;return}
  if(A==="fridge"){const [x,y]=SPOTS.fridgeopen[0];goTo(ch,x,y);ch.goal="spot";ch.after="fridgeopen";return}
  if(A==="cards"||A==="meetslack"){const seat=MEET_SEATS[(idle.indexOf(ch.id)+(A==="meetslack"?4:0))%MEET_SEATS.length];goTo(ch,seat[0],seat[1]);ch.goal="spot";
    ch.after=A==="cards"?"cards":"phone";return}
    const L=A==="coffee"?SPOTS.coffee:A==="fridge"?SPOTS.fridge:A==="rugphone"?SPOTS.rug:A==="tabletea"?SPOTS.table:SPOTS.sofa,
   i=(hash(ch.id)+Math.floor(r()*L.length))%L.length;
  goTo(ch,L[i][0],L[i][1]);ch.goal="spot";ch.after=A==="coffee"||A==="tabletea"?"tea":A==="fridge"?"fridge":A==="rugphone"?"phone":"sofanap";
}
/* v2 茶水间连锁：咖啡 = 走到咖啡机 → 煮 4 秒 → 端杯回工位 → 坐着喝；零食 = 走到冰箱 → 开门拿 2.5 秒 → 拿着回工位或去沙发 → 吃
   沙发：一只猫=躺下（睡 Zzz 或刷手机）；两只以上=聊天（♪）。开会优先：会议室打牌 / 摸鱼的猫散场 */
const BREW_S=4, FRIDGE_S=2.5;
function chainStep(ch){
  if(ch.act==="brew"&&ch.actT>BREW_S){ch.hold="cup";ch.cupNext=3+Math.floor(srand(ch.id+":cup:"+ch.t)()*6);wantHome(ch,"drink")}   /* 一杯 3–8 口 */
  else if(ch.act==="fridgeopen"&&ch.actT>FRIDGE_S){ch.hold="snack";if(srand(ch.id+"eat"+ch.slot)()<.5)wantHome(ch,"eat");else{const L=SPOTS.sofa,
    i=hash(ch.id)%L.length;goTo(ch,L[i][0],L[i][1]);ch.goal="spot";ch.after="eat"}}
  else if((ch.act==="drink"||ch.act==="eat")&&!ch.moving){if(ch.act==="drink"&&ch.hold==="cup"){ch.cup=Math.max(0,(ch.cupNext||5)-1);ch.cupT=0}ch.hold=null}
  if(ch.plan==="sofa"&&!ch.inBox&&(ch.act==="sofanap"||ch.act==="sofaphone"||ch.act==="sofachat")){
    const mates=Object.values(CH).filter(c=>c!==ch&&c.state==="idle"&&c.plan==="sofa"&&!c.moving&&!c.inBox).length;
    ch.act=mates?"sofachat":(ch.sofaPref||(srand(ch.id+"sofa"+ch.slot)()<.6?"sofanap":"sofaphone"))}
  if((ch.plan==="cards"||ch.plan==="meetslack")&&((MEET&&MEET.until>T)||SCENE)&&!inMeeting(ch)){ch.plan=null;ch.actDur=0}   /* 开会 / 演场景优先 */
  if(ch.plan==="cards"&&!ch.moving&&ch.act==="cards"&&Object.values(CH).filter(c=>c.plan==="cards"&&c.state==="idle").length<2)ch.act="phone"}
function cardsOn(){return Object.values(CH).filter(c=>c.act==="cards"&&!c.moving).length>=2}
function startWander(ch){ch.act="wander";let cur=[ch.x,ch.y];const pts=[];for(let i=0;i<3;i++){const q=randFloor();pts.push(...route(cur,q));cur=q}ch.path=pts;
  ch.moving=true;ch.hurry=false;ch.goal="wander"}
function randFloor(){for(let i=0;i<60;i++){const x=rnd(ZONE.desk.x+8,ZONE.desk.x+ZONE.desk.w-8),y=rnd(140,262);if(!blocked(x,
  y)&&!STATIONS.some(s=>Math.abs(s.x+12-x)<34&&y>s.y-6&&y<s.y+20))return[x,y]}return[40,140]}
function moveStep(ch,dt){
  if(ch.moving&&ch.path.length){const [tx,ty]=ch.path[0],sp=(ch.hurry?64:ch.act==="roll"?30:20)*dt,dx=tx-ch.x,dy=ty-ch.y,d=Math.hypot(dx,dy);
    if(Math.abs(dx)>.5)ch.face=dx>0?1:-1;
    if(d<=sp){ch.x=tx;ch.y=ty;ch.path.shift();if(!ch.path.length){ch.moving=false;if(!(ch.plan==="wander"&&ch.goal==="wander"))ch.actT=0;
        if(ch.goal==="home"){homeIn(ch);ch.act=ch.after;if(ch.after==="type"){ch.meowT=0}}
        else if(ch.goal==="wait"){ch.act="wait";ch.face=ch.x<BOSS.x?1:-1}
        else if(ch.goal==="gather"){ch.act="wait";ch.face=ch.x<BOSS.x?1:-1}   /* 围到首领旁边：面向它站着冒 ? */
        else if(ch.goal==="spot"){ch.act=ch.after;if(ch.faceTo!=null){ch.face=ch.faceTo>ch.x?1:-1;
          ch.faceTo=null}if(ch.after==="chat"&&CH[ch.mate])ch.face=CH[ch.mate].st.x>ch.x?1:-1}
        else if(ch.goal==="rest"){ch.act="sofanap";ch.plan="sofa"}   /* 歇着：到了沙发就窝着 */
        else if(ch.goal==="deliver"){ch.carry=false;ch.deliver=false;PUFFS.push({x:ch.x,y:ch.y-20,t:0,star:true});startMeeting(ch.id,"review");ch.goal=null;
          ch.act="sit"}
        else if(ch.goal==="meet"){ch.act=ch.meetStand?"stand":"sit";ch.face=ch.x<422?1:-1}
        else if(ch.goal==="wander"){ch.act="idle";if(SKIN.zoned&&ch.plan==="wander"&&ch.state==="idle"){ch.wanderRest=rnd(1,2.5)}else ch.actDur=rnd(1,2.5)}}}
    else{ch.x+=dx/d*sp;ch.y+=dy/d*sp}}
}
function stepChar(ch,dt){
  ch.t+=dt;ch.actT+=dt;if(ch.cup>0)ch.cupT=(ch.cupT||0)+dt;if(ch.toss)ch.toss=Math.max(0,ch.toss-dt);
  const c=ch.data, st=ch.state, lead=ch.st.lead;
  // 屏幕内容
  ch.screen=st==="off"?"off":st==="run"?ch.workScene:st==="you"?"alert":st==="fail"?"alert":(lead&&ch.act==="boss_idle"&&ch.bossAnim==="game")
  ?(ch.playScene||"shooter"):st==="arch"?"wait":
  /* arch 态玩电脑也要显示游戏画面 */
    (ch.inBox&&ch.act==="deskplay")?ch.playScene:(ch.inBox&&ch.act==="sleepbox")
    ?"sleep":lead?(ch.bossAnim==="nap"?"sleep":ch.bossAnim==="game"?(ch.playScene||"shooter"):"video"):ch.inBox?"video":"sleep";
  if(!ch.inBox&&st!=="run"&&st!=="off")ch.screen=st==="arch"?"wait":"sleep";
  if(ch.spawnHide)return;   /* 等快递箱的猫不占工位，不活动、不摸鱼 */
  if(ch.wakeT>0){ /* 刚从午睡醒来：先伸个懒腰，伸完该干嘛干嘛（被派活的回工位干活） */
    ch.wakeT-=dt;ch.plan=null;ch.hold=null;ch.path=[];ch.moving=false;ch.act="stretch";
    if(ch.wakeT<=0){ch.wakeT=0;ch.act="idle";ch.actT=0;ch.actDur=0;ch.goal=null}
    return}
  if(napStep(ch,dt))return;   /* 午睡中的猫：这一帧全交给午睡（去沙发 / 趴工位 / 睡着不动） */
  if(partySeatFor(ch)){partyStep(ch,dt);return}   /* –庆祝 / 复盘：这只猫这帧归场景管 */
  if(meetSceneStep(ch,dt))return;   /* 会议室场景（看电影 / 打比赛 / 站会）里的猫：这一帧全交给场景 */
  if(lead&&SKIN.zoned&&ch.coffeeTrip&&!inMeeting(ch)){ // TeamLeader 自己去打咖啡
    if(!ch.moving)chainStep(ch);
    moveStep(ch,dt);
    if(ch.inBox&&!ch.moving&&ch.act==="drink"){chainStep(ch);ch.coffeeTrip=0;ch.act="boss_idle";ch.bossAnim="tea";ch.actT=0;ch.actDur=rnd(5,8)}
    return
  }
  if(lead&&inMeeting(ch)&&ch.coffeeTrip){ch.coffeeTrip=0;ch.hold=null}
  if(lead&&SKIN.zoned&&(inMeeting(ch)||!ch.inBox)){ // 开会：TeamLeader 也去会议室，开完回座位
    if(inMeeting(ch)){const [mx,my]=meetSeat(ch);if(ch.goal!=="meet"){leaveBox(ch);goTo(ch,mx,my,true);ch.goal="meet";ch.after="sit"}}
    /* 派活/验收：TeamLeader 小跑进会议室 */
    else if(ch.goal!=="home"){goTo(ch,ch.st.x,ch.st.y+7);ch.goal="home";ch.after="boss_idle"}
    moveStep(ch,dt);return
  }else if(lead){ // TeamLeader 平时坐在自己的大箱子里
    ch.inBox=true;ch.moving=false;
    if(st==="you")ch.act="you"; /* TeamLeader 不推断忙闲，只按老板节奏轮着休闲 */
    else{ch.act="boss_idle";if(ch.actT>ch.actDur){if(ch.actDur)ACTLOG.push({id:ch.id,plan:"boss_"+ch.bossAnim,held:ch.actT,dur:ch.actDur});ch.actT=0;
ch.bossAnim=["game","tea","phone","nap","game"][Math.floor(srand("boss:"+Date.now()+":"+ch.t)()*5)];ch.actDur=ch.bossAnim==="game"?rnd(12,18):rnd(5,8);
if(ch.bossAnim==="tea"){if(ch.cup>0)ch.cup--;else if(SKIN.zoned){const [bx,by]=SPOTS.brew[0];leaveBox(ch);goTo(ch,bx+6,by);ch.goal="spot";ch.after="brew";
      ch.faceTo=26;ch.coffeeTrip=1;return}}if(ch.bossAnim==="game")ch.playScene=["shooter","snake","blocks"][hash(ch.id+Math.floor(ch.t))%3]}}
    return}
  if(st==="off"){ch.inBox=true;ch.moving=false;ch.act="off";return}
  if(st==="rest"){ /* 歇着（额度用完 / 被限流 / 接口连不上 / 服务端出错）：去沙发那边歇着，头顶一个小钟 */
    if(ch.goal!=="rest"){leaveBox(ch);const L=SPOTS.sofa,i=hash(ch.id)%L.length;goTo(ch,L[i][0],L[i][1]);ch.goal="rest";ch.after="sofanap"}
    if(!ch.moving&&ch.act!=="sofanap")ch.act="sofanap";
    moveStep(ch,dt);return}
  if(ch.meowT>0){ch.meowT-=dt;ch.act="meow";if(!ch.inBox)ch.moving=false;if(ch.meowT>0)return}
  if(ch.seatT>0&&SKIN.zoned&&!lead&&st==="idle"&&!inMeeting(ch)&&!ch.deliver){ /* 收尾：刚开箱的猫先在工位坐满 20 秒，期间不抽摸鱼动作、不溜达（被派活 / 开会不受限） */
    ch.seatT=Math.max(0,ch.seatT-dt);ch.act="sit";ch.actT=0;ch.actDur=0;ch.plan=null;ch.hold=null;ch.goal=null;ch.path=[];ch.moving=false;return}
  if(SKIN.zoned&&inMeeting(ch)&&!lead){const [mx,my]=meetSeat(ch);if(ch.goal!=="meet"){leaveBox(ch);goTo(ch,mx,my,true);ch.goal="meet";
    ch.after=ch.meetStand?"stand":"sit"}}
  else if(SKIN.zoned&&ch.goal==="meet"){ch.goal=null;ch.deliver=false;wantHome(ch,st==="run"?"type":"sit")}
  else if(SKIN.zoned&&ch.deliver&&st==="idle"){ /* 交活：抱着文件进会议室，TeamLeader 一起验收 */
    if(ch.goal!=="deliver"){leaveBox(ch);ch.carry=true;const [mx,my]=MEET_SEATS[1];goTo(ch,mx,my,true);ch.goal="deliver";ch.after="sit"}}
  else if(st==="run"||st==="fail"||st==="appr"||st==="you"){wantHome(ch,st==="run"?"type":"sit",st==="run")}
  else if(st==="arch"){ /* 等待 / 卡住：坐在自己工位上冒省略号（不再跑去 TeamLeader 旁边站着） */
    if(SKIN.zoned)wantHome(ch,"sit");else{const slot=[[132,132],[234,132]][Object.values(CH).filter(x=>x.state==="arch"&&!x.st.lead).indexOf(ch)%2];
    if(ch.goal!=="wait"){leaveBox(ch);goTo(ch,slot[0],slot[1]);ch.goal="wait";ch.after="wait"}}}
  else if(st==="idle"&&SKIN.zoned&&DATA&&DATA.leader_quiet){ /* 首领没反应 → 空闲的猫围到它工位旁边冒 ?；首领有动静（leader_quiet 消失）自动散 */
    ch.plan=null;ch.hold=null;
    const mates=Object.values(CH).filter(c=>!c.st.lead&&c.state==="idle").map(c=>c.id).sort();
    const spot=GATHER_SPOTS[Math.max(0,mates.indexOf(ch.id))%GATHER_SPOTS.length];
    if(ch.goal!=="gather"){leaveBox(ch);goTo(ch,spot[0],spot[1]);ch.goal="gather";ch.after="wait"}}
  else{ // 空闲：随机摸鱼
    if(ch.goal==="wait"||ch.goal==="gather"||ch.goal==="home"&&ch.after==="type"){ch.goal=null;ch.actDur=0}
    if(SKIN.zoned){
      if((!ch.moving||ch.plan==="wander")&&(!ch.actDur||ch.actT>ch.actDur)&&!(ch.act==="brew"||ch.act==="fridgeopen"||ch.hold&&ch.moving))pickIdle(ch);
      else if(!ch.moving&&ch.plan==="wander"&&ch.wanderRest!=null&&(ch.wanderRest-=dt)<=0){ch.wanderRest=null;startWander(ch)}}
    else if(!ch.moving&&ch.actT>ch.actDur)pickIdle(ch)}
  if(st==="idle"&&SKIN.zoned&&!ch.moving)chainStep(ch);
  if(ch.after2==="stretch"&&ch.inBox){ch.after2=null;leaveBox(ch);ch.act="stretch";ch.actT=0}
  if(ch.act==="stretch"&&ch.actT>3.3&&!ch.moving){ch.act="idle"}
  moveStep(ch,dt);
}
