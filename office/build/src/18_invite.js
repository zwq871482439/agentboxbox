/* ===================== 
   核心给的数据（/api/office 的 scenes.invites，最多 3 条）冒一个可点的像素邀请气泡（
   挪到会议室投影机旁、挨着聚会街机，凑成一角「要开演了」）。白底深框硬阴影，中间一个图标（礼花筒 / 烟花 / 小 bug），
   右上角小「×」。整个气泡就是一个按钮：点气泡任意处 = ack play 并开演对应场景，点「×」= ack dismiss
   （原来的橙底「放」块删了）；悬停时在气泡下面画一行提示（庆祝一下 / 开收工会 / 开复盘会）。点了本地马上隐藏（记在 INV_DONE），接着冒下一条。 */
const PARTY=["celebrate","wrapup","postmortem"];            /* 这张卡的三个会议室场景 */
const PARTY_DUR={celebrate:20,wrapup:30,postmortem:60};       /* 放多久（秒）：约 20 / 30 / 60 */
const PARTY_WORD={celebrate:TR("party.celebrate"),wrapup:TR("party.wrapup"),postmortem:TR("party.postmortem")};
const PARTY_SEED=parseInt(Q.get("seed")||"0",10)||0;        /* 事故复盘的随机元素用 ?seed 固定后可复现 */
const INV_DONE=new Set();                                     /* 点过「放」/「×」的邀请 id：下一次 feed 刷新也不再冒 */
/* 邀请气泡左边的小图标（8×8，画法跟现有 ICON 一样）：celebrate 礼花筒 / wrapup 烟花；postmortem 用现成的 bug */
Object.assign(ICON,{party:["..y...r.",".u....y.","...r.u..",".kkkkkk.",".kwwcwk.","..kwwk..","..kwcw..","...kk..."],
 firework:["r...y..u",".r..y.u.","..ryyu..","yyykkyyy","..uyyr..",".u..y.r.","u...y..r","....p..."]});
function leaderCh(){for(const id in CH){if(CH[id]&&CH[id].st&&CH[id].st.lead)return CH[id]}return null}
function leaderAlerted(){ /* 首领有第 1 级提醒（的「!」）：要你拍板，或提醒条上有落在它头上的第 1 级 */
  const l=leaderCh();if(!l)return false;
  if(l.state==="you")return true;
  return lvl1Alerts().some(a=>a&&a.station===l.id)}
function curInvite(){ /* 现在该冒的那条邀请：一次只冒一条，点过的不再冒 */
  if(!sceneBubblesOn()||SCENE)return null;                  /* 关掉场景气泡 / 已经有会议室场景在演 */
  if(Object.keys(SAYFX).length)return null;                 /* 正在播上岗动画的 say 对话框 */
  const l=leaderCh();if(!l||l.state==="off"||leaderAlerted())return null;
  const list=DATA&&DATA.scenes&&Array.isArray(DATA.scenes.invites)?DATA.scenes.invites:[];
  return list.find(i=>i&&i.id&&PARTY.includes(i.kind)&&!INV_DONE.has(i.id))||null}
const INV_WORD={celebrate:["庆祝一下","Celebrate"],wrapup:["开收工会","Wrap-up meeting"],postmortem:["开复盘会","Post-mortem"]};
function inviteWord(k){const w=INV_WORD[k];return w?(uiLang()==="en"?w[1]:w[0]):""}
function inviteGeom(){ /* 气泡占位（）：会议室投影机旁、聚会街机上方，跟着轻微上下浮动；整个气泡是「放」按钮，右上角「×」 */
  const inv=curInvite(),l=inv&&leaderCh();
  if(!inv||!l)return null;
  const w=17,hh=12,x0=Math.round(ARCADE.foot[0]-w/2),y0=Math.round(ARCADE.foot[1]-ARCADE.h-hh-4+Math.sin(T*2.4)*1.2);
  return{id:inv.id,kind:inv.kind,x0,y0,w,h:hh,
    play:{x:x0,y:y0,w,h:hh},cross:{x:x0+w-5.5,y:y0+.5,w:5,h:4.5}}}
function drawInvite(t){ /* 高清层画气泡（跟 say 气泡一个调子：方角、深框、硬阴影）；去掉橙底「放」块，中间只留图标 */
  const b=inviteGeom();if(!b)return;
  const x0=b.x0,y0=b.y0,w=b.w,hh=b.h;
  hi.save();
  hi.fillStyle="rgba(11,11,16,.55)";hi.fillRect(W2(x0+1.5),W2(y0+1.5),W2(w),W2(hh));   /* 硬阴影 */
  hi.fillStyle="#2b2233";hi.fillRect(W2(x0-.8),W2(y0-.8),W2(w+1.6),W2(hh+1.6));        /* 深色粗描边 */
  hi.fillStyle="#fffdf7";hi.fillRect(W2(x0),W2(y0),W2(w),W2(hh));                     /* 白底 */
  pix(ICON[b.kind==="celebrate"?"party":b.kind==="wrapup"?"firework":"bug"],x0+w/2,y0+hh/2,1.05);
  const c=b.cross;
  hi.fillStyle="#2b2233";hi.textAlign="center";hi.font=`700 ${5*S}px ${SAY_FONT}`;
  hi.fillText("×",W2(c.x+c.w/2),W2(c.y+c.h-1));                                     /* 右上角小「×」 */
  if(INV_HOVER)txt(inviteWord(b.kind),x0+w/2,y0+hh+7,{sz:4.6,b:1,c:"#1f1a24",bg:"#fffdf7",bd:"#2b1d12"});   /* 悬停提示一行 */
  hi.restore()}
function inviteClick(p){ /* 先看有没有点中邀请气泡（整只气泡都是「放」，只有右上角「×」是关，参考 sayClick 那套）；点在气泡上都不算点猫 */
  const b=inviteGeom();if(!b)return false;
  if(p.x<b.x0-1||p.x>b.x0+b.w+1||p.y<b.y0-1||p.y>b.y0+b.h+1)return false;
  const inR=r=>p.x>=r.x&&p.x<=r.x+r.w&&p.y>=r.y&&p.y<=r.y+r.h;
  const play=!inR(b.cross),close=inR(b.cross);
  if(play||close){
    INV_DONE.add(b.id);                                   /* 点了本地马上隐藏这条，接着冒下一条 */
    const action=play?"play":"dismiss";                    /* live 模式发 ack；演示数据只本地处理 */
    if(LIVE_BASE!=null){try{fetch(LIVE_BASE+"/api/scenes/ack",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:b.id,
      action})}).catch(()=>{})}catch(e){}}
    if(play)sceneStart(b.kind);
  }
  return true}

/* ---- 三个场景本体的开演 ---- */
let CONFETTI=[],FWORKS=[];   /* 庆祝的彩带粒子 / 收工庆祝幕布上的烟花 */
function partyIds(){ /* 谁参加：空闲的打工猫 + 首领也来（要拍板 / 下线的首领不来） */
  const out=[];
  for(const id in CH){const ch=CH[id];if(!ch||!ch.st)continue;
    if(ch.st.lead){if(ch.state!=="off"&&ch.state!=="you")out.push(id);continue}
    if(ch.state==="idle"&&!ch.pending&&!ch.deliver)out.push(id)}
  return out.sort()}
function pmElems(){ /* 事故复盘投影上的随机抽象元素：3–5 个（叉 / 往下的折线 / 问号块 / 齿轮），?seed 固定后可复现 */
  const rr=srand("postmortem:"+PARTY_SEED),kinds=["cross","zig","ask","gear"],slots=[0,1,2,3,4,5];
  for(let i=slots.length-1;i>0;i--){const j=Math.floor(rr()*(i+1)),t=slots[i];slots[i]=slots[j];slots[j]=t}
  const n=3+Math.floor(rr()*3),out=[];
  for(let i=0;i<n;i++)out.push({kind:kinds[Math.floor(rr()*kinds.length)],slot:slots[i]});
  return out}
function partyTick(){ /* 每帧：报名 + 到点收场（猫各自回工位）+ 彩带 / 烟花的粒子 */
  const s=SCENE;
  if(!s||!PARTY.includes(s.name)){CONFETTI.length=0;FWORKS.length=0;return}
  const dt=clamp(T-(s.pt!=null?s.pt:s.t0),0,.06);s.pt=T;
  if(!s.joined){
    s.joined=true;
    const ids=partyIds();
    for(const id of ids){const ch=CH[id];if(!ch)continue;      /* 报名：打断手头的事，睡着的叫醒 */
      ch.goal=null;ch.plan=null;ch.hold=null;ch.mate=null;ch.actT=0;ch.actDur=0;
      if(NAPS.has(id))napWake(ch,"start")}
    s.ids=new Set(ids);s.hadIds=!!ids.length;
    if(s.name==="postmortem")s.pm=pmElems()}
  if(T-s.t0>=PARTY_DUR[s.name]){          /* 放完了：收场景，猫各自回工位 */
    const ids=[...s.ids];sceneEnd("ended");
    for(const id of ids){const ch=CH[id];if(ch&&!NAPS.has(id))wantHome(ch,ch.st.lead?"boss_idle":"sit")}
    return}
  if(s.name==="celebrate")confettiTick(dt);
  else if(s.name==="wrapup")fireworksTick(dt)}
function partySeatFor(ch){ /* 场景里这只猫的座位：首领坐桌头（收工庆祝站幕布前），成员按 id 坐两侧、多了站桌下一排 */
  const s=SCENE;if(!s||!PARTY.includes(s.name)||!s.ids.has(ch.id)||ch.state==="off")return null;
  if(ch.st.lead)return s.name==="wrapup"?[404,116]:MEET_HEAD;
  const ids=[...s.ids].filter(id=>CH[id]&&CH[id].st&&!CH[id].st.lead).sort(),i=Math.max(0,ids.indexOf(ch.id));
  ch.meetStand=i>=MEET_SEATS.length;
  return ch.meetStand?MEET_STAND[(i-MEET_SEATS.length)%MEET_STAND.length]:MEET_SEATS[i]}
function partyStep(ch,dt){ /* 场景成员这一帧：走去座位，到了坐下（庆祝举杯 / 收工鼓掌坐好 / 复盘围坐） */
  const seat=partySeatFor(ch);if(!seat)return;
  const act=SCENE.name==="celebrate"?"tea":SCENE.name==="wrapup"?(ch.st.lead?"wait":"sit"):"sit";
  ch.plan=null;ch.hold=null;
  if(ch.goal!=="scene"||Math.hypot(ch.x-seat[0],ch.y-seat[1])>2.5){
    if(ch.inBox||ch.goal!=="scene"){leaveBox(ch);goTo(ch,seat[0],seat[1],true);ch.goal="scene";ch.after=act}
    moveStep(ch,dt);return}
  ch.moving=false;ch.path=[];ch.act=act;ch.face=ch.x<422?1:-1}
function partyScreenOn(){return !!(SCENE&&PARTY.includes(SCENE.name))}   /* 这张卡的场景：幕布也要放下来 */
/* 事故复盘投影上的抽象元素（5×5 像素小画，颜色查 IPAL）；问号块直接用现成的 ask 图标 */
const PMSLOT=[[399,77],[446,77],[399,84],[446,84],[399,91],[446,91]];   /* 幕布上中间留给大 bug，元素排在两侧六格 */
function pixLo(rows,cx,cy,u){ /* 像素图标画到世界层（幕布内容用）：跟 pix() 一个画法，只是画在 g 上 */
  const n=rows.length,x0=cx-n*u/2,y0=cy-n*u/2;
  for(let j=0;j<n;j++)for(let i=0;i<rows[j].length;i++){const c=IPAL[rows[j][i]];if(c)R(x0+i*u,y0+j*u,u,u,c)}}
function partyScreenDraw(t){ /* 幕布上的画面（画在世界层 drawRoom 里）；不是这张卡的场景返回 false 让老逻辑画 */
  const s=SCENE;if(!s||!PARTY.includes(s.name))return false;
  if(s.name==="celebrate"){ /* 完成庆祝：大对勾 + 几道闪光 */
    R(390,72,64,26,"#ffffff");R(390,72,64,2,"#dcfce7");
    for(let k=0;k<7;k++)R(403+k,83+k,2.6,2.6,"#16a34a");
    for(let k=0;k<17;k++)R(409+k,89-k,2.6,2.6,"#16a34a");
    for(let i=0;i<5;i++){const h=hash("cel"+i),fx=396+h%52,fy=75+(h>>>3)%20;
      if(Math.floor(t*2.5+i*1.3)%3<2){R(fx-.6,fy,2.2,.9,"#ffffff");R(fx,fy-.6,.9,2.2,"#ffffff");R(fx,fy,.9,.9,"#fde047")}}
  }else if(s.name==="wrapup"){ /* 收工庆祝：夜空底 + 像素烟花在幕布范围内炸开 */
    R(390,72,64,26,"#0b1220");
    for(const f of FWORKS){const k=clamp(f.t/f.dur,0,1),e=1-Math.pow(1-k,2);
      g.globalAlpha=Math.max(0,1-k);
      for(const p of f.parts)R(f.x+Math.cos(p.a)*p.r*e,f.y+Math.sin(p.a)*p.r*.8*e,1,1,f.c);
      g.globalAlpha=1}
  }else{ /* 事故复盘：底色变红，中间一个大 bug + 随机抽象元素 */
    R(390,72,64,26,"#7f1d1d");R(390,72,64,1.5,"#b91c1c");R(390,96.5,64,1.5,"#600f0f");
    pixLo(ICON.bug,422,85,2.2);
    if(s.pm)for(const e of s.pm)pixLo(e.kind==="ask"?ICON.ask:PMELEM[e.kind],PMSLOT[e.slot][0],PMSLOT[e.slot][1],e.kind==="ask"?.85:1.15)}
  return true}
const CONF_COLS=["#ff6b6b","#facc15","#5aa9ff","#a78bfa","#34d399","#f472b6"];
function confettiTick(dt){ /* 彩带：会议室上方不断飘下彩色像素，落地消失 */
  while(CONFETTI.length<36)CONFETTI.push({x:rnd(374,470),y:rnd(64,72),v:rnd(9,17),ph:rnd(0,6.28),land:rnd(184,205),c:pick(CONF_COLS)});
  for(const p of CONFETTI){p.y+=p.v*dt;p.x+=Math.sin(p.y*.4+p.ph)*dt*6}
  CONFETTI=CONFETTI.filter(p=>p.y<p.land)}
function fireworksTick(dt){ /* 烟花：幕布里隔一阵炸一朵，几种颜色 */
  const s=SCENE;
  if(T-(s.fw||0)>1.25){s.fw=T;
    const n=10+Math.floor(Math.random()*5),parts=[];
    for(let i=0;i<n;i++)parts.push({a:i/n*Math.PI*2+Math.random()*.35,r:rnd(4,8)});
    FWORKS.push({x:rnd(398,446),y:rnd(77,91),t:0,dur:.95,c:pick(["#ff6b6b","#facc15","#5aa9ff","#a78bfa","#f97316"]),parts})}
  for(const f of FWORKS)f.t+=dt;
  FWORKS=FWORKS.filter(f=>f.t<f.dur)}
function drawPartyFx(t){ /* 世界层、画在猫上面：庆祝的彩带 / 收工鼓掌的两只小手 */
  const s=SCENE;if(!s||!PARTY.includes(s.name))return;
  if(s.name==="celebrate"){for(const p of CONFETTI)R(p.x,p.y,1,1.5,p.c);return}
  if(s.name==="wrapup"){
    for(const id of s.ids){const ch=CH[id];if(!ch||ch.st.lead||ch.moving||ch.inBox)continue;
      const bob=Math.sin(t*11+(hash(id)%7))*1.3;
      R(ch.x-3.1,ch.y-10+bob-.3,2.2,2.2,"#2b2233");R(ch.x+.9,ch.y-10-bob-.3,2.2,2.2,"#2b2233");
      R(ch.x-2.9,ch.y-9.8+bob,1.8,1.8,"#ffe9c4");R(ch.x+1.1,ch.y-9.8-bob,1.8,1.8,"#ffe9c4")}}}
function drawPartyHi(t){ /* 高清层：复盘的猫挠不了头，头上冒小汗滴 + 无语 / 疑问气泡 */
  const s=SCENE;if(!s||s.name!=="postmortem")return;
  for(const id of s.ids){const ch=CH[id];if(!ch||!ch.head||ch.moving||ch.inBox)continue;
    drawSweat(ch,t);
    if(((t*.5+(hash(id)%10))%6)<2.6)drawPixBubble(ch,hash(id)%2?"meh":"huh",1,0)}}
