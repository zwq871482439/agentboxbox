/* ===================== 
   首页（上岗窗口）和画布只靠 postMessage 说话：
     home → office：{"type":"bx-anim","id":N,"name":"box_in|box_open|crown|say|remove","slot":"leader|A..F",...}
     office → home：{"type":"bx-anim-ready"}（加载好发一次）/ {"type":"bx-anim-done","id":N,"name":...}（播完）/
                    {"type":"bx-anim-click","id":N}（say 的按钮被点）
   每个动画都支持 instant:true（直接摆成播完的样子，立刻回 done）；系统开「减少动态效果」时全部换成淡入淡出，照样回 done。
   日常（?live=1）画布自己也播：feed 里新出现的打工猫 → box_in + box_open；消失的 → remove；刚打开页面时已有的猫直接坐着。
   箱子 / 像素「咚」按 assets/chibicat/onboard/ 的设计稿逐像素搬进代码（调色板 + 点阵），和现有物件一个画法。 */

function dongArt(){return uiLang()==="en"?DONG_ART_EN:DONG_ART}
const DOOR={x:WW+16,y:268};            /* 快递猫进出场的门口：画面右缘外 */
const FX_SPEED=76, SAY_HOLD=8, DONG_S=.7, SEAT_HOLD=20;   /* 快递猫抬箱速度（世界像素/秒）；不带按钮的气泡挂 8 秒自己收起；「咚」弹 DONG_S 秒；刚开箱的猫先坐 SEAT_HOLD 秒 */
let SLOT_FX={}, SAYFX={}, ANIMS=[], ANIM_Q={}, EXPLICIT_SLOT={}, SEEN_IDS=null, ANIM_FEED_ID=0, COURIER_OUT=[];
function reducedMotion(){try{return window.matchMedia("(prefers-reduced-motion: reduce)").matches}catch(e){return false}}
function animPost(m){try{window.parent.postMessage(m,"*")}catch(e){}}
function animView(a){return{id:a.id,name:a.name,slot:a.slot,phase:a.phase,rm:!!a.rm,x:a.x,y:a.y,couriers:!!a.couriers,hasBox:!!a.hasBox}}
function slotXY(slot){const p=slot==="leader"?BOSS:{x:(SLOT_POS[slot]||SLOT_POS.A)[0],y:(SLOT_POS[slot]||SLOT_POS.A)[1]};return{x:p.x,y:p.y}}
function slotCh(slot){const st=STATIONS.find(s=>s.slot===slot);return st?CH[st.id]:null}
function slotFx(slot){return SLOT_FX[slot]||(SLOT_FX[slot]={})}
function slotBusy(slot){return ANIMS.some(a=>a.slot===slot)||(ANIM_Q[slot]||[]).length>0}
function lookSpec(look,slot){const lk=look&&typeof look==="object"?look:{};
  return{cat:lk.cat>=1&&lk.cat<=8?lk.cat:1+Math.floor(Math.random()*8),acc:lk.acc,lead:slot==="leader"}}
function courierSpec(l){const lk=l&&typeof l==="object"?l:{};return{cat:lk.cat>=1&&lk.cat<=8?lk.cat:1+Math.floor(Math.random()*8),acc:lk.acc}}
function groupMove(a,dt,speed){
  if(!a.path||!a.path.length)return true;
  const tx=a.path[0][0],ty=a.path[0][1],d=Math.hypot(tx-a.x,ty-a.y),sp=speed*dt;
  if(Math.abs(tx-a.x)>.5)a.face=tx>a.x?1:-1;
  if(d<=sp){a.x=tx;a.y=ty;a.path.shift();return!a.path.length}
  a.x+=(tx-a.x)/d*sp;a.y+=(ty-a.y)/d*sp;return false}
function animBlocked(x,y){for(const a of ANIMS){const b=a.block;if(b&&x>b.x&&x<b.x+b.w&&y>b.y&&y<b.y+b.h)return true}return false}
/* 点阵画到世界层（g）：x 中线、y 底，1 格 = k 世界像素 */
function drawArt(art,x,y,k){k=k||1;const r=art.r,w=r[0].length,h=r.length,x0=Math.round(x-w*k/2),y0=Math.round(y-h*k);
  for(let j=0;j<h;j++)for(let i=0;i<w;i++){const c=art.p[r[j][i]];if(c)R(x0+i*k,y0+j*k,k,k,c)}}
/* 点阵画到高清层（hi），用法同 pix() */
function pixArt(art,cx,by,k,al){const rows=art.r,w=rows[0].length,h=rows.length,x0=cx-w*k/2,y0=by-h*k;
  hi.save();if(al!=null&&al<1)hi.globalAlpha=al;
  for(let j=0;j<h;j++)for(let i=0;i<w;i++){const c=art.p[rows[j][i]];if(!c)continue;hi.fillStyle=c;
    hi.fillRect(Math.round(W2(x0+i*k)),Math.round(W2(y0+j*k)),Math.ceil(W2(k))+1,Math.ceil(W2(k))+1)}
  hi.restore()}
/* 王冠单图：同一只猫「戴 / 不戴王冠」两张精灵逐像素 diff 出来（画法即 cats.js 的王冠，含描边） */
const CROWN_SPR={};
function crownSprite(cat){
  if(CROWN_SPR[cat])return CROWN_SPR[cat];
  const a=renderCatSprite({cat,acc:[],lead:true},"sit",0).back,b=renderCatSprite({cat,acc:[],lead:true,noCrown:true},"sit",0).back,N=40;
  const A=a.getContext("2d").getImageData(0,0,N,N).data,B=b.getContext("2d").getImageData(0,0,N,N).data;
  const c2=document.createElement("canvas");c2.width=N;c2.height=N;const x2=c2.getContext("2d"),id=x2.createImageData(N,N);
  for(let i=0;i<A.length;i+=4){const same=A[i]===B[i]&&A[i+1]===B[i+1]&&A[i+2]===B[i+2]&&A[i+3]===B[i+3];
    if(!same){id.data[i]=A[i];id.data[i+1]=A[i+1];id.data[i+2]=A[i+2];id.data[i+3]=A[i+3]}}
  x2.putImageData(id,0,0);return CROWN_SPR[cat]=c2;
}
/* ---- 播完的样子（instant / 收尾共用） ---- */
/* 猫放到工位上：刚到位的先坐满 SEAT_HOLD 秒（stepChar 里看着），不抽摸鱼动作、不溜达；被派活不受限 */
function seatNow(ch){ch.inBox=true;ch.moving=false;ch.path=[];ch.seatT=SEAT_HOLD}
function finalBoxOpen(slot,look,who){
  const fx=slotFx(slot),ch=slotCh(slot),p=slotXY(slot);
  fx.box=null;
  if(ch){ch.spawnHide=false;seatNow(ch);delete fx.cat}
  else fx.cat={spec:lookSpec(look,slot),x:p.x,y:p.y+2,pose:"sit",f:0,crown:false,who:who||null,al:1};
}
function applyCrown(a){if(a.ch)a.ch.fxNoCrown=false;if(SLOT_FX[a.slot]&&SLOT_FX[a.slot].cat)SLOT_FX[a.slot].cat.crown=true}
/* 收尾：say 带 instant（刷新后重发）时不画气泡 —— 一次性的话说过就完了，画面上不留带按钮的气泡等人点 */
function finalSay(m,slot){
  if(m.instant){delete SAYFX[slot];return}
  SAYFX[slot]={id:m.id,text:String(m.text||""),button:m.button?String(m.button):null,t:0,al:1}}
function applyAnimFinal(m){
  const slot=m.slot||"leader",fx=slotFx(slot),ch=slotCh(slot);
  if(m.name==="box_in"){fx.box="closed";fx.boxA=1;if(ch)ch.spawnHide=true}
  else if(m.name==="box_open")finalBoxOpen(slot,m.look,m.who);
  else if(m.name==="crown"){if(ch)ch.fxNoCrown=false;if(fx.cat)fx.cat.crown=true}
  else if(m.name==="say")finalSay(m,slot);
  else if(m.name==="remove"){delete SAYFX[slot];fx.box=null;fx.cat=null;if(ch)ch.spawnHide=true}
}
/* ---- 启动 / 收尾 / 排队 ---- */
function finishAnim(a){
  ANIMS=ANIMS.filter(x=>x!==a);
  animPost({type:"bx-anim-done",id:a.id,name:a.name});
  (a.acks||[]).forEach(id=>animPost({type:"bx-anim-done",id,name:a.name}));
  pumpAnim(a.slot);
}
function pumpAnim(slot){
  if(ANIMS.some(a=>a.slot===slot))return;
  const q=ANIM_Q[slot];if(!q||!q.length)return;
  launchAnim(q.shift());
}
function cancelSlot(slot){   /* 送箱送到一半猫从 feed 里没了：这个工位的动画撤掉，挂着的 id 照常回 done（不卡住对面） */
  const act=ANIMS.filter(a=>a.slot===slot);ANIMS=ANIMS.filter(a=>a.slot!==slot);
  const q=ANIM_Q[slot]||[];ANIM_Q[slot]=[];
  act.concat(q).forEach(a=>{animPost({type:"bx-anim-done",id:a.id,name:a.name});(a.acks||[]).forEach(id=>animPost({type:"bx-anim-done",id,name:a.name}))});
  delete SLOT_FX[slot];delete SAYFX[slot];
}
function launchAnim(m){
  const a={id:m.id,name:m.name,slot:m.slot||"leader",t:0,phase:"",phaseT:0,acks:[],rm:reducedMotion()};
  ANIMS.push(a);
  LAUNCH[m.name](a,m);
}
function handleAnimMsg(m){
  ONBOARD=true;   /* 收到上岗动画消息：空位虚线框转橙色，直到 feed 里第一只打工猫坐下 */
  const slot=m.slot||"leader";
  if(!SKIN.zoned){applyAnimFinal(m);animPost({type:"bx-anim-done",id:m.id,name:m.name});return}   /* 纸箱人皮肤：不播，直接摆结果 */
  EXPLICIT_SLOT[slot]=true;
  if(m.instant){applyAnimFinal(m);animPost({type:"bx-anim-done",id:m.id,name:m.name});return}
  const dup=ANIMS.find(a=>a.slot===slot&&a.name===m.name)||(ANIM_Q[slot]||[]).find(a=>a.name===m.name);
  if(dup){(dup.acks=dup.acks||[]).push(m.id);return}   /* 同名同工位已在播 / 在排：挂上 id，播完一起回 done */
  (ANIM_Q[slot]=ANIM_Q[slot]||[]).push(m);pumpAnim(slot);
}
addEventListener("message",e=>{const m=e.data||{};if(m.type==="bx-anim"&&LAUNCH[m.name])handleAnimMsg(m)});
/* ---- 五个动画 ---- */
const LAUNCH={
 box_in(a,m){
  const p=slotXY(a.slot),fx=slotFx(a.slot),ch=slotCh(a.slot);
  if(ch)ch.spawnHide=true;   /* 猫随箱子来，工位先空着 */
  a.block={x:p.x-48,y:p.y-28,w:96,h:60};
  if(a.rm){fx.box="closed";fx.boxA=0;a.phase="fade"}
  else{a.couriers=(Array.isArray(m.couriers)?m.couriers:[]).map(courierSpec).slice(0,2);
    while(a.couriers.length<2)a.couriers.push(courierSpec());
    a.x=DOOR.x;a.y=DOOR.y;a.face=-1;a.hasBox=true;a.boxArt="closed";a.path=route([DOOR.x,DOOR.y],[p.x,p.y+6]);a.phase="walk"}
 },
 box_open(a,m){
  const fx=slotFx(a.slot),ch=slotCh(a.slot),p=slotXY(a.slot);
  a.look=m.look;a.who=m.who;
  if(ch)ch.spawnHide=true;
  if(a.rm){
    if(!ch)fx.cat={spec:lookSpec(m.look,a.slot),x:p.x,y:p.y+2,pose:"sit",f:0,crown:false,who:m.who||null,al:0};
    a.phase="fade";
  }else{if(!fx.box){fx.box="closed";fx.boxA=1}a.phase="open"}
 },
 crown(a,m){
  const ch=slotCh(a.slot),fx=SLOT_FX[a.slot],p=slotXY(a.slot);
  a.ch=ch&&!ch.spawnHide?ch:null;a.fx=fx&&fx.cat?fx.cat:null;
  a.lead=a.ch?a.ch.st.lead:a.fx?a.fx.spec.lead:a.slot==="leader";
  a.catNo=a.ch?a.ch.cat:a.fx?a.fx.spec.cat:1;
  a.feetY=a.ch?(a.ch.inBox?a.ch.st.y-(a.ch.st.lead?3:1):a.ch.y):a.fx?a.fx.y:p.y;
  a.hx=a.ch?(a.ch.head?a.ch.head.x:a.ch.x):a.fx?a.fx.x:p.x;
  a.cy=a.feetY-46;
  if(a.ch)a.ch.fxNoCrown=true;   /* 落下前先摘掉，落稳（flash）再戴上 */
  a.phase="fade0";
 },
 say(a,m){
  SAYFX[a.slot]={id:m.id,text:String(m.text||""),button:m.button?String(m.button):null,t:0,al:0};
  a.phase="pop";a.popDur=a.rm?.45:.22;
 },
 remove(a,m){
  const fx=slotFx(a.slot),ch=slotCh(a.slot),p=slotXY(a.slot);
  delete SAYFX[a.slot];
  if(ch){ch.spawnHide=true;
    if(!fx.cat)fx.cat={spec:{cat:ch.cat,acc:ch.look&&ch.look.acc,lead:ch.st.lead},x:ch.st.x,y:ch.st.y-(ch.st.lead?3:1),pose:"sit",f:0,crown:true,al:1}}
  if(!fx.cat&&m.look)fx.cat={spec:lookSpec(m.look,a.slot),x:p.x,y:p.y+2,pose:"sit",f:0,crown:false,al:1};
  if(a.rm){a.phase="fade"}
  else{a.couriers=[courierSpec(),courierSpec()];
    a.x=DOOR.x;a.y=DOOR.y;a.face=-1;
    a.block={x:p.x-48,y:p.y-28,w:96,h:60};
    if(fx.cat){fx.boxA=0;a.phase="mkbox"}
    else if(fx.box){a.phase="seal";a.sealed=false}
    else finishAnim(a)}   /* 工位本来就是空的：没什么可抬，直接回 done */
 }
};
const STEP={
 box_in(a,dt){
  const p=slotXY(a.slot),fx=slotFx(a.slot);
  if(a.rm){fx.boxA=Math.min(1,(fx.boxA||0)+dt/.45);if(fx.boxA>=1)finishAnim(a);return}
  if(a.phase==="walk"){if(groupMove(a,dt,FX_SPEED)){a.phase="drop";a.phaseT=0}}
  else if(a.phase==="drop"){a.phaseT+=dt;const k=Math.min(1,a.phaseT/.24);
    a.boxPos={x:a.x+(p.x-a.x)*k,y:a.y-13+(p.y+1-(a.y-13))*k};
    if(k>=1){a.hasBox=false;a.boxPos=null;fx.box="closed";fx.boxA=1;a.phase="dong";a.phaseT=0;PUFFS.push({x:p.x,y:p.y-6,t:0})}}
  else if(a.phase==="dong"){a.phaseT+=dt;if(a.phaseT>=DONG_S){courierLeave(a);finishAnim(a)}}   /* 收尾：箱子落地、「咚」弹完就回 done；快递猫自己走出去那段在 done 之后接着播 */
 },
 box_open(a,dt){
  const p=slotXY(a.slot),fx=slotFx(a.slot);
  if(a.rm){a.phaseT+=dt;
    if(fx.box)fx.boxA=Math.max(0,(fx.boxA==null?1:fx.boxA)-dt/.4);
    if(fx.cat&&fx.cat.al<1)fx.cat.al=Math.min(1,fx.cat.al+dt/.45);
    if(a.phaseT>=.5){fx.box=null;finalBoxOpen(a.slot,a.look,a.who);finishAnim(a)}return}
  if(a.phase==="open"){fx.box="open";a.phaseT+=dt;
    if(a.phaseT>=.28){a.phase="jump";a.phaseT=0;
      a.jcat={spec:lookSpec(a.look,a.slot),x:p.x,y:p.y-11,pose:"yay",f:0};a.jfrom={x:p.x,y:p.y-11};a.jto={x:p.x,y:p.y+2}}}
  else if(a.phase==="jump"){a.phaseT+=dt;const k=Math.min(1,a.phaseT/.6);
    a.jcat.x=a.jfrom.x+(a.jto.x-a.jfrom.x)*k;a.jcat.y=a.jfrom.y+(a.jto.y-a.jfrom.y)*k-Math.sin(Math.PI*k)*16;a.jcat.f=Math.floor(T*6)%2;
    if(k>=1){a.jcat=null;PUFFS.push({x:p.x,y:p.y-4,t:0});finalBoxOpen(a.slot,a.look,a.who);a.phase="fade";a.phaseT=0}}
  else if(a.phase==="fade"){a.phaseT+=dt;fx.boxA=Math.max(0,1-a.phaseT/.3);if(a.phaseT>=.3){fx.box=null;finishAnim(a)}}
 },
 crown(a,dt){
  if(a.rm){a.phaseT+=dt;if(a.phaseT>=.45){applyCrown(a);finishAnim(a)}return}
  if(a.phase==="fade0"){a.phase="fall";a.phaseT=0}
  else if(a.phase==="fall"){a.phaseT+=dt;const k=Math.min(1,a.phaseT/.5);a.cy=a.feetY-46+46*k*k;
    if(k>=1){a.phase="bounce";a.phaseT=0}}
  else if(a.phase==="bounce"){a.phaseT+=dt;const k=Math.min(1,a.phaseT/.16);a.cy=a.feetY-2.6*Math.sin(Math.PI*k);
    if(k>=1){a.phase="flash";a.phaseT=0;applyCrown(a)}}
  else if(a.phase==="flash"){a.phaseT+=dt;if(a.phaseT>=.34)finishAnim(a)}
 },
 say(a,dt){a.phaseT+=dt;if(a.phaseT>=a.popDur)finishAnim(a)},
 remove(a,dt){
  const p=slotXY(a.slot),fx=slotFx(a.slot);
  if(a.rm){a.phaseT+=dt;
    if(fx.cat&&fx.cat.al!=null)fx.cat.al=Math.max(0,fx.cat.al-dt/.5);
    if(fx.box)fx.boxA=Math.max(0,(fx.boxA==null?1:fx.boxA)-dt/.5);
    if(a.phaseT>=.55){fx.cat=null;fx.box=null;finishAnim(a)}return}
  if(a.phase==="mkbox"){fx.box="open";fx.boxA=Math.min(1,(fx.boxA||0)+dt/.22);
    if(fx.boxA>=1){a.phase="hop";a.phaseT=0;a.hopFrom=fx.cat?{x:fx.cat.x,y:fx.cat.y}:null}}
  else if(a.phase==="hop"){a.phaseT+=dt;const k=Math.min(1,a.phaseT/.5),c=fx.cat;
    if(c&&a.hopFrom){c.x=a.hopFrom.x+(p.x-a.hopFrom.x)*k;c.y=a.hopFrom.y+(p.y-11-a.hopFrom.y)*k-Math.sin(Math.PI*k)*10;c.pose="yay"}
    if(k>=1){fx.cat=null;fx.box="closed";PUFFS.push({x:p.x,y:p.y-8,t:0});a.phase="seal";a.phaseT=0;a.sealed=false}}
  else if(a.phase==="seal"){
    if(!a.sealed){a.sealed=true;fx.box="parcel";fx.boxA=1;PUFFS.push({x:p.x,y:p.y-10,t:0,star:true})}
    a.phaseT+=dt;if(a.phaseT>=.42){a.phase="come";a.path=route([a.x,a.y],[p.x,p.y+6])}}
  else if(a.phase==="come"){if(groupMove(a,dt,FX_SPEED+6)){a.phase="lift";a.phaseT=0}}
  else if(a.phase==="lift"){a.phaseT+=dt;const k=Math.min(1,a.phaseT/.24);
    if(fx.box)fx.boxPos={x:p.x,y:p.y+1+(a.y-13-(p.y+1))*k};
    if(k>=1){fx.box=null;fx.boxPos=null;a.hasBox=true;a.boxArt="parcel";a.phase="go";a.path=route([a.x,a.y],[DOOR.x,DOOR.y])}}
  else if(a.phase==="go"){if(groupMove(a,dt,FX_SPEED+10)){a.couriers=null;a.hasBox=false;finishAnim(a)}}
 }
};
/* 送完箱：done 已经回了，快递猫自己走回门口 —— 这一段归 COURIER_OUT 管，不占工位、不排队，接下来的 box_open 不等它 */
function courierLeave(a){
  COURIER_OUT.push({id:a.id,name:a.name,slot:a.slot,x:a.x,y:a.y,face:a.face,couriers:a.couriers,boxArt:a.boxArt,
    hasBox:false,boxPos:null,phase:"out",path:route([a.x,a.y],[DOOR.x,DOOR.y]),speed:FX_SPEED+10,t:0});
  a.couriers=null}
function stepAnims(dt){
  for(const a of ANIMS.slice()){a.t+=dt;STEP[a.name](a,dt)}
  for(const o of COURIER_OUT.slice()){o.t+=dt;if(groupMove(o,dt,o.speed))COURIER_OUT=COURIER_OUT.filter(x=>x!==o)}}
/* ---- 日常（?live=1）：feed 里新出现的打工猫由快递猫送来，消失的封箱抬走；页面刚打开时已有的猫直接坐着 ---- */
function feedAnimSync(prev){
  const ids=Object.keys(CH);
  if(ONBOARD&&ids.some(id=>CH[id].st&&!CH[id].st.lead&&!CH[id].spawnHide))ONBOARD=false;   /* 第一只打工猫坐下了：上岗流程结束，空位框回灰 */
  if(SEEN_IDS===null){SEEN_IDS=new Set(ids);return}
  if(LIVE&&SKIN.zoned)try{feedAnimDiff(prev,ids)}catch(e){}
  SEEN_IDS=new Set(ids);
}
function feedAnim(m){m.id=--ANIM_FEED_ID;(ANIM_Q[m.slot]=ANIM_Q[m.slot]||[]).push(m);pumpAnim(m.slot)}
function feedAnimDiff(prev,ids){
  for(const id of ids){const ch=CH[id],fx=ch.st&&SLOT_FX[ch.st.slot];   /* 上岗动画播完 feed 才跟上：假猫换真猫 */
    if(fx&&fx.cat&&!slotBusy(ch.st.slot)){delete fx.cat;ch.spawnHide=false;seatNow(ch)}}   /* 真猫接上假猫的位置：同样先坐满 20 秒，别一露面就溜达 */
  for(const id of ids){const ch=CH[id];if(!ch.st||ch.st.lead||SEEN_IDS.has(id))continue;
    const slot=ch.st.slot;
    if(ch.data&&ch.data.pending_open)continue;   /* 第 6 条：刚招、还在开箱 → 这只猫的送箱动画归上岗流程管 */
    if(EXPLICIT_SLOT[slot]||slotBusy(slot)||(SLOT_FX[slot]&&(SLOT_FX[slot].box||SLOT_FX[slot].cat)))continue;   /* 上岗流程在管这个工位 */
    ch.spawnHide=true;
    feedAnim({name:"box_in",slot});
    feedAnim({name:"box_open",slot,look:ch.look||{cat:ch.cat},who:ch.data&&(ch.data.cat_name||ch.data.label)})}
  for(const id in prev){const was=prev[id];
    if(CH[id]||!SEEN_IDS.has(id)||!was.st||was.st.lead)continue;
    const slot=was.st.slot;
    if(slotBusy(slot)){cancelSlot(slot);continue}   /* 送箱送到一半猫没了：撤掉，不再补播 */
    if(EXPLICIT_SLOT[slot])continue;
    feedAnim({name:"remove",slot,look:{cat:was.cat,acc:was.look&&was.look.acc}})}
}
/* ---- 画法 ---- */
function drawFxBox(slot){
  const fx=SLOT_FX[slot];if(!fx||!fx.box)return;const p=slotXY(slot);
  const pos=fx.boxPos||{x:p.x,y:p.y+1};
  const art=fx.box==="open"?BOX_OPEN:fx.box==="parcel"?BOX_PARCEL:BOX_CLOSED;
  g.save();if(fx.boxA!=null&&fx.boxA<1)g.globalAlpha=Math.max(0,fx.boxA);
  drawArt(art,pos.x,pos.y,1);g.restore();
}
function drawFxCat(slot){
  const fx=SLOT_FX[slot],c=fx&&fx.cat;if(!c)return;
  const spr=renderCatSprite({cat:c.spec.cat,acc:c.spec.acc,lead:c.spec.lead,noCrown:!c.crown},c.pose||"sit",c.f||0);
  g.save();if(c.al!=null&&c.al<1)g.globalAlpha=Math.max(0,c.al);
  g.globalAlpha*=.28;R(Math.round(c.x-7),Math.round(c.y),14,1.5,"#000");g.globalAlpha=c.al!=null?Math.max(0,c.al):1;
  drawCatSprite(spr,c.x,c.y,1,"back");drawCatSprite(spr,c.x,c.y,1,"front");
  g.restore();
  c.head=catWorld(spr,c.x,c.y,1,spr.head.X,spr.head.Y);
}
function drawJumpCat(a){
  const c=a.jcat;if(!c)return;
  const spr=renderCatSprite({cat:c.spec.cat,acc:c.spec.acc,lead:c.spec.lead,noCrown:true},c.pose,c.f||0);
  g.globalAlpha=.28;R(Math.round(c.x-7),Math.round(a.jto?a.jto.y:c.y),14,1.5,"#000");g.globalAlpha=1;
  drawCatSprite(spr,c.x,c.y,1,"back");drawCatSprite(spr,c.x,c.y,1,"front");
}
function drawCourierGroup(a){
  if(!a.couriers)return;
  const walk=a.phase==="walk"||a.phase==="come"||a.phase==="go"||a.phase==="out",f=walk?Math.floor(T*9)%4:0,pose=walk?"walk":"sit";
  if(a.hasBox||a.boxPos){const bp=a.boxPos||{x:a.x,y:a.y-13};
    drawArt(a.boxArt==="parcel"?BOX_PARCEL:BOX_CLOSED,bp.x,bp.y,1)}
  a.couriers.forEach((c,i)=>{
    const x=a.x+(i?24:-24),face=walk?a.face:(i?-1:1);
    const spr=renderCatSprite({cat:c.cat,acc:c.acc,courier:true},pose,f);
    g.globalAlpha=.28;R(Math.round(x-7),Math.round(a.y),14,1.5,"#000");g.globalAlpha=1;
    drawCatSprite(spr,x,a.y,face,"back");drawCatSprite(spr,x,a.y,face,"front")});
}
function drawCrownSpr(a,cy,al){   /* 落下的王冠：单图锚点和猫精灵一致（脚底对齐），落点就是戴上 */
  const spr=crownSprite(a.catNo),N=a.lead?40:32;
  g.save();if(al!=null&&al<1)g.globalAlpha=al;
  g.drawImage(spr,Math.round(a.hx-N/2),Math.round(cy-N),N,N);g.restore()}
function drawCrownFx(){
  for(const a of ANIMS){if(a.name!=="crown")continue;
    if(a.rm){drawCrownSpr(a,a.feetY,Math.min(1,a.phaseT/.4));continue}
    if(a.phase==="fall"||a.phase==="bounce")drawCrownSpr(a,a.cy,1);
    else if(a.phase==="flash"){const e=a.phaseT;   /* 落稳一闪 */
      g.save();g.globalAlpha=Math.max(0,1-e/.34);
      for(let i=0;i<6;i++){const an=i/6*Math.PI*2+e*2;R(a.hx+Math.cos(an)*(5+e*10)-.5,a.feetY-38+Math.sin(an)*(4+e*7)-.5,1,1,"#fffbe6")}
      g.restore()}}
}
function drawDongFx(){   /* 像素「咚」三帧弹出（小 → 大 + 放射线 → 正常），没有声音 */
  for(const a of ANIMS){if(a.name!=="box_in"||a.phase!=="dong")continue;
    const p=slotXY(a.slot),e=a.phaseT;
    const k=e<.12?.55:e<.3?1.4:1,al=e>DONG_S-.2?Math.max(0,1-(e-(DONG_S-.2))/.2):1;
    if(e>=.12&&e<.3){hi.save();hi.strokeStyle="#ffb43c";hi.lineWidth=Math.max(1,S*.5);
      for(let i=0;i<8;i++){const an=i/8*Math.PI*2+.4;
        hi.beginPath();hi.moveTo(W2(p.x+Math.cos(an)*13),W2(p.y-27+Math.sin(an)*13));hi.lineTo(W2(p.x+Math.cos(an)*17),W2(p.y-27+Math.sin(an)*17));hi.stroke()}
      hi.restore()}
    pixArt(dongArt(),p.x,p.y-15,k,al)}
  WHO_DRAWN={};
  for(const s in SLOT_FX){const f=SLOT_FX[s];if(f.cat&&f.cat.who){
    const rc=slotCh(s);if(rc&&!rc.spawnHide)continue;   /* 真猫已经坐在工位上了：名字由工位那行画（同一行），这里不再叠一行 */
    const p=slotXY(s);WHO_DRAWN[s]=f.cat.who;txt(f.cat.who,p.x,p.y+9,{sz:4.7,b:1,c:PAL.name})}}
}
/* ---- say 的像素对话气泡（高清层，可点按钮） ----
   白底、深色粗描边、硬阴影的大对话框，宽约画布 40%（一行放得下「让我们来招募第一个打工猫猫吧！」）；
   深色加粗大字（字号 = 工位名字的两倍多）；有按钮时是橙底白字的大按钮，在文字下方左对齐；
   气泡放在猫的右上方，一个小三角指向猫，不出画布、不盖住猫本身。 */
const SAY_W=Math.round(WW*.4),SAY_SZ=10,SAY_PAD=6,SAY_LH=13,SAY_BTN_H=14;
const SAY_FONT=`"Microsoft YaHei","PingFang SC","Noto Sans CJK SC","Noto Serif CJK SC",sans-serif`;
function sayAnchor(slot){
  const ch=slotCh(slot);if(ch&&!ch.spawnHide&&ch.head)return{x:ch.head.x,y:ch.head.y};
  const fx=SLOT_FX[slot];if(fx&&fx.cat&&fx.cat.head)return fx.cat.head;
  const p=slotXY(slot);return{x:p.x,y:p.y-30};
}
function drawSayBubble(s,pos){
  hi.save();hi.globalAlpha=s.al;
  hi.font=`700 ${SAY_SZ*S}px ${SAY_FONT}`;
  const maxw=SAY_W-SAY_PAD*2,lines=[];let cur="";
  for(const ch of s.text){if(ch==="\n"||hi.measureText(cur+ch).width>W2(maxw)){lines.push(cur);cur=ch==="\n"?"":ch}else cur+=ch}
  if(cur)lines.push(cur);if(!lines.length)lines.push("");
  hi.font=`700 ${8*S}px ${SAY_FONT}`;
  const btw=s.button?hi.measureText(s.button).width/S+18:0;
  const bw=SAY_W,bh=SAY_PAD+lines.length*SAY_LH+(s.button?5+SAY_BTN_H:0)+SAY_PAD;
  const bx=clamp(pos.x+20,2,WW-bw-2),by=Math.max(2,pos.y-22-bh);   /* 猫的右上方，钳在画布内 */
  hi.fillStyle="rgba(11,11,16,.55)";hi.fillRect(W2(bx+2),W2(by+2),W2(bw),W2(bh));   /* 硬阴影 */
  hi.fillStyle="#2b2233";hi.fillRect(W2(bx-.8),W2(by-.8),W2(bw+1.6),W2(bh+1.6));   /* 3px 深色描边 */
  hi.fillStyle="#fffdf7";hi.fillRect(W2(bx),W2(by),W2(bw),W2(bh));   /* 白底 */
  const tx=clamp(pos.x+8,bx+10,bx+bw-26),ty=by+bh;   /* 底边伸一个小三角指向猫 */
  hi.fillStyle="#2b2233";hi.beginPath();hi.moveTo(W2(tx-1),W2(ty-.5));hi.lineTo(W2(tx+15),W2(ty-.5));hi.lineTo(W2(pos.x+5),W2(ty+12));hi.closePath();hi.fill();
  hi.fillStyle="#fffdf7";hi.beginPath();hi.moveTo(W2(tx+1.5),W2(ty-.5));hi.lineTo(W2(tx+12.5),W2(ty-.5));hi.lineTo(W2(pos.x+7),W2(ty+9));hi.closePath();
    hi.fill();
  hi.fillStyle="#2b2233";hi.textAlign="left";hi.font=`700 ${SAY_SZ*S}px ${SAY_FONT}`;
  lines.forEach((l,i)=>hi.fillText(l,W2(bx+SAY_PAD),W2(by+SAY_PAD+SAY_LH*(i+.78))));
  if(s.button){
    const bx2=bx+SAY_PAD,by2=by+SAY_PAD+lines.length*SAY_LH+4;   /* 文字下方左对齐 */
    s.btnRect={x:bx2,y:by2,w:btw,h:SAY_BTN_H};
    hi.fillStyle="#e07020";hi.fillRect(W2(bx2),W2(by2),W2(btw),W2(SAY_BTN_H));   /* 橙底白字大按钮 */
    hi.strokeStyle="#2b2233";hi.lineWidth=Math.max(1,S*.4);hi.strokeRect(W2(bx2),W2(by2),W2(btw),W2(SAY_BTN_H));
    hi.fillStyle="#ffffff";hi.textAlign="center";hi.font=`700 ${8*S}px ${SAY_FONT}`;
    hi.fillText(s.button,W2(bx2+btw/2),W2(by2+SAY_BTN_H-3.5));
  }
  s.rect={x:bx,y:by,w:bw,h:bh+12};
  hi.restore();
}
function drawSayFx(dt){
  for(const slot in SAYFX){const s=SAYFX[slot];
    s.t+=dt;
    if(s.closing){s.al=Math.max(0,s.al-dt/.3);if(s.al<=0){delete SAYFX[slot];continue}}
    else{s.al=Math.min(1,s.al+dt/.22);if(!s.button&&s.t>SAY_HOLD)s.closing=true}
    const pos=sayAnchor(slot);if(!pos){delete SAYFX[slot];continue}
    drawSayBubble(s,pos);
  }
}
function sayClick(p){   /* 点了按钮：发 bx-anim-click 给首页，气泡收起；点在气泡上不算点猫 */
  for(const slot in SAYFX){const s=SAYFX[slot];
    if(s.btnRect&&!s.closing&&p.x>=s.btnRect.x&&p.x<=s.btnRect.x+s.btnRect.w&&p.y>=s.btnRect.y&&p.y<=s.btnRect.y+s.btnRect.h){
      animPost({type:"bx-anim-click",id:s.id});s.closing=true;return true}
    if(s.rect&&p.x>=s.rect.x&&p.x<=s.rect.x+s.rect.w&&p.y>=s.rect.y&&p.y<=s.rect.y+s.rect.h)return true}
  return false}
