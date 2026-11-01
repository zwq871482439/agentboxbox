/* ===================== 启动 ===================== */
(async()=>{
 if(EMBED){
  // 嵌进外层看板时：藏 .top / .ph / .demo / .foot / .seg，body 改成 flex 居中方便父页用 .stage 做缩放
  const s=document.createElement("style");
  s.id="bx-embed";
  s.textContent=
   "html{background:var(--bg) !important;}"+
   ".top,.ph,.demo,.foot,.seg{display:none !important;}"+
   ".wrap{padding:0 !important;max-width:none !important;}"+
   "body{display:flex !important;align-items:center !important;justify-content:center !important;"+
    "overflow:hidden !important;background:transparent !important;margin:0 !important;padding:0 !important;}";
  document.head.appendChild(s);
 }
 applyTheme(true);setInterval(applyTheme,60*1000);   /* 昼夜：每分钟检查一次（页面一打开直接到当前时段，不播过渡） */
 fit();const live=Q.get("live");BASE=live?await loadLive(live==="1"?"":live):await loadSample();if(live)LIVE_BASE=live==="1"?"":live;syncData(clone(BASE));
  if(live)loadThemeTimes(live==="1"?"":live);
  try{const m=localStorage.getItem("bx-office-mode");if(m==="list")document.querySelector('.seg button[data-v=list]').click()}catch(e){}
  if(live)setInterval(async()=>{try{syncData(await loadLive(live==="1"?"":live))}catch(e){}},5000);
  last=performance.now();requestAnimationFrame(frame);
  animPost({type:"bx-anim-ready"});   /* 画布加载好、能接动画了，告诉首页（嵌在 iframe 里时） */
  window.__office={force(id,a){const ch=CH[id];const A=SKIN.idleActs.find(x=>x.a===a);const keep=SKIN.idleActs;SKIN.idleActs=[A];pickIdle(ch);
SKIN.idleActs=keep;ch.actDur=99},run(id){const d=clone(DATA);const c=d.channels.find(x=>x.id===id);
  c.state="run";c.state_word=TR("demo.running");c.task_d=TR("demo.test");
syncData(d)},tick,get CH(){return CH},syncData,get DATA(){return DATA},dispatchDemo:()=>$("#b-disp").click(),plan(id,a){const ch=CH[id];ch.goal=null;
ch.deliver=false;ch.carry=false;ch.moving=false;pickIdleZoned(ch,a);ch.actDur=999},sym(id){return persistentSym(CH[id])},actlog(){return ACTLOG.slice()},
tense(id){return isTense(CH[id])},bub(){return{on:Object.values(CH).filter(c=>bubbleVisible(c)>0).map(c=>c.id),log:BUBLOG.slice(),q:BUBQ.length,T}},
sleeping(id){const c=CH[id];return isSleeping(c,c.st)},meet(){return meetReady()?MEET.why:null},applyEvents,get EV_SEEN(){return EV_SEEN},
    envelopes(){return ENVS.map(e=>({id:e.ch.id,mail:!!e.mail}))},
    get THEME(){return THEME}, get PAL(){return PAL}, get SKY(){return SKY}, setThemeMode, themeAuto,
  setTimes(t){THEME_TIMES=Object.assign({},THEME_TIMES,t);applyTheme(true)}, lamps(){return STATIONS.filter(lampOn).map(s=>s.id)}, seed:(f)=>{Math.random=f},
  freeze:freezeClock, thaw:thawClock, clockNow:()=>Date.now(),
    SLOT_POS, slots(){return STATIONS.map(s=>({id:s.id,slot:s.slot,x:s.x,y:s.y}))},
  emptySlots(){const occ=new Set(STATIONS.map(s=>s.slot));return SLOT_ORDER.filter(s=>!occ.has(s))}, slotReset(){SLOT_MEM={}},
    meetRule:MEET_RULE, meetPick, meetBubs(){return MEET_BUBS.slice()}, meetLayout(){return{seats:MEET_SEATS,head:MEET_HEAD,stand:MEET_STAND}},
  proj(){return{k:PROJ.k,on:meetReady()}}, stand(id){return!!CH[id].meetStand}, startMeeting,
  animMsg(m){handleAnimMsg(m)},anims(){return ANIMS.map(animView).concat(COURIER_OUT.map(a=>Object.assign(animView(a),{out:true})))},
    slotFx(){const o={};for(const s in SLOT_FX){const f=SLOT_FX[s];if(!f.box&&!f.cat)continue;o[s]={box:f.box||null,cat:!!f.cat,crown:!!(f.cat&&f.cat.crown),
      catAl:f.cat?f.cat.al:null,boxA:f.boxA==null?null:f.boxA}}return o},
  
    sayFx(){const o={};for(const s in SAYFX){const f=SAYFX[s];o[s]={text:f.text,button:f.button,al:f.al,btn:f.btnRect||null,rect:f.rect||null,
      closing:!!f.closing}}return o},
  
  hit(id){const ch=CH[id];return ch?SKIN.hit(ch):null},   /* 角色占地矩形（say 气泡不能盖住猫） */
  catName(id){const ch=CH[id];return ch?catNameOf(ch.data):null},   /* 猫脚下那行名字（它的名字，没名字退回标签） */
  whoDrawn(){return Object.assign({},WHO_DRAWN)},   /* 这一帧开箱假猫画出去的名字行（真猫坐下后应为空，不叠字） */
  bangUp(id){const ch=CH[id];return!!(ch&&!ch.spawnHide&&persistentSym(ch)==="bang"&&!SAYFX[ch.st.slot])},   /* 首领的「!」现在画没画（say 期间先不画） */
  emptyDrawn(){return JSON.parse(JSON.stringify(EMPTY_DRAWN))},onboard(){return ONBOARD},
  chFlags(id){const c=CH[id];return c?{hide:!!c.spawnHide,noCrown:!!c.fxNoCrown,inBox:!!c.inBox,slot:c.st&&c.st.slot}:null},
    px(x,y,w,h){const d=hi.getImageData(Math.round(x*S),Math.round(y*S),Math.max(1,Math.round(w*S)),Math.max(1,Math.round(h*S))).data;const m={};for(let i=0;
      i<d.length;i+=4){if(d[i+3]<200)continue;const c=d[i]+","+d[i+1]+","+d[i+2];m[c]=(m[c]||0)+1}return m},
  
  scene(name){return sceneStart(name,{force:true})},   /* –测试钩子：直接开演（nap / snack / movie / game / standup 都支持；standup 没给名单就拿现在的打工猫假装一批） */
  sceneNow(){return SCENE?SCENE.name:null},              /* 当前会议室场景名，没有就是 null */
  sceneInfo(){if(!SCENE)return null;const o={name:SCENE.name,ids:[...SCENE.ids].sort()};   /* 当前场景的断言用信息 */
    if(SCENE.round!=null)o.round=SCENE.round;if(SCENE.winner!=null)o.winner=SCENE.winner;
    if(SCENE.name==="movie")o.dim=true;if(SCENE.players)o.players=SCENE.players.slice();
    return o},
  sceneBubs(){return SCENE_BUBS.slice()},                /* 这一帧画出去的场景气泡（看电影的高兴 / 打比赛的胜负） */
  napping(){return[...NAPS.keys()]},                    /* 在午睡的猫 id */
  snacks(){return[...SNACKS]},                           /* 桌上有外卖盒的猫 id */
  sceneStart,sceneEnd,sceneLast:n=>SCENE_LAST[n]||0,   /* 给第 2、3 张卡接着用 */
    invite(){const b=inviteGeom();return b?{id:b.id,kind:b.kind,rect:{x:b.x0,y:b.y0,w:b.w,h:b.h},playRect:b.play,xRect:b.cross,hover:INV_HOVER,
      word:inviteWord(b.kind)}:null},
  
  /* –当前冒着的邀请气泡（含点得到的矩形；整只气泡都是 playRect），没有就是 null */
    arcade(){const r=arcadeRect(),el=document.getElementById("party-pop");return{rect:{x:r.x,y:r.y,w:r.w,h:r.h},hover:ARC_HOVER,menu:!!(el&&!el.hidden),
      scene:SCENE?SCENE.name:null}},
  
  /* 聚会街机（点它弹聚会菜单）；menu：菜单现在开没开 */
    themeSwitch(){const el=document.getElementById("theme-pop");return{rect:{x:SWITCH.x,y:SWITCH.y,w:SWITCH.w,h:SWITCH.h},mode:themeMode(),hover:SW_HOVER,
      menu:!!(el&&!el.hidden),names:MODE_ORDER.map(m=>modeName(m))}},
  
  /* 昼夜开关（点它弹五档菜单） */
    dock(){return{embed:EMBED,drawn:EMBED,buttons:DOCK_BTN.map(b=>({k:b.k,panel:b.panel,rect:{x:b.x,y:b.y,w:b.w,h:b.h},unread:UNREAD[b.k]||0,
      label:uiLang()==="en"?b.en:b.zh}))}},
  
  /* 动态 / 用量按钮（只在嵌进首页时画） */
  partyInfo(){return SCENE&&PARTY.includes(SCENE.name)?{name:SCENE.name,t0:SCENE.t0,ids:[...SCENE.ids],confetti:SCENE.name==="celebrate"?CONFETTI.length:0,
confY:SCENE.name==="celebrate"?CONFETTI.slice(0,6).map(p=>Math.round(p.y)):[],fireworks:SCENE.name==="wrapup"?FWORKS.length:0,
    pm:SCENE.pm||null}:null}};   /* 当前庆祝 / 复盘场景的内情（测试用） */
})();
