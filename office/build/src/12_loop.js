/* ===================== 主循环 ===================== */
let last=performance.now(),T=0,RUN=true,MODE="office";
const MANUAL=Q.get("manual")==="1";
function frame(now){
  if(!RUN||MANUAL)return;const dt=Math.min(.05,(now-last)/1000);last=now;tick(dt);requestAnimationFrame(frame)}
function tick(dt){T+=dt;sceneTick();
  for(const id in CH)stepChar(CH[id],dt);
  stepAnims(dt);   /* 上岗动画（快递猫 / 箱子 / 假猫 / 王冠都归它推） */
  g.setTransform(LOK,0,0,LOK,0,0);g.imageSmoothingEnabled=false;g.clearRect(0,0,WW,WH);
  drawRoom(T);
  EMPTY_DRAWN={};   /* 每帧重记：哪些空位画了虚线框 / 字母、用的什么色（测试钩子 emptyDrawn） */
  if(SKIN.zoned){drawShadows(T);drawLightFx(T)}   /* v2 光影只给猫猫箱皮肤；纸箱人（黑白皮肤）不画光影 */
  // 深度排序：工位 + 空位虚线框 + 在外面的角色 + 打印机 + 上岗动画的箱子 / 猫 / 快递猫
  const items=[];for(const st of STATIONS){const ch=CH[st.id];if(SKIN.zoned&&ch.spawnHide)continue;items.push({y:st.y,f:()=>SKIN.drawStation(st,CH[st.id],T)})}
  {const occ=new Set(STATIONS.filter(s=>!(SKIN.zoned&&CH[s.id]&&CH[s.id].spawnHide)).map(s=>s.slot));
    for(const s of SLOT_ORDER)if(!occ.has(s))items.push({y:SLOT_POS[s][1],f:()=>drawEmptySlot(s)})}
  for(const id in CH){const ch=CH[id];if(!ch.inBox&&ch.state!=="off"&&!ch.spawnHide)items.push({y:ch.y,f:()=>SKIN.drawOut(ch,T)})}
  items.push({y:PRINTER.y,f:()=>drawPrinter(T)});
  for(const s in SLOT_FX){const fx=SLOT_FX[s],pp=slotXY(s);
    if(fx.box)items.push({y:pp.y+.5,f:()=>drawFxBox(s)});
    if(fx.cat)items.push({y:fx.cat.y+.2,f:()=>drawFxCat(s)})}
  for(const a of ANIMS){if(a.couriers)items.push({y:a.y,f:()=>drawCourierGroup(a)});
    if(a.jcat)items.push({y:a.jcat.y,f:()=>drawJumpCat(a)})}
  for(const o of COURIER_OUT)items.push({y:o.y,f:()=>drawCourierGroup(o)})   /* done 之后还在走的快递猫 */
  items.sort((a,b)=>a.y-b.y).forEach(i=>i.f());
  drawLight(T);
  if(SKIN.zoned)drawSceneDim();   /* 看电影调暗灯：只盖地面和桌子，画在投影机之前，不压幕布和投影光 */
  if(SKIN.zoned)drawProjector(T);   /* 投影机 + 光锥：罩在猫身上，画在角色之后 */
  drawSceneFx(T);   /* 会议室场景道具：爆米花 / 加油小牌 / 指示棒（–画布 2/3） */
  for(const id in CH)drawHP(CH[id]);
  drawPuffs(dt);drawEnvelopes(dt);
  drawPartyFx(T);   /* –彩带 / 鼓掌的小手（世界层，画在猫上面） */
  drawCrownFx();   /* 落下的王冠 + 落稳一闪 */
  hi.setTransform(1,0,0,1,0,0);hi.imageSmoothingEnabled=false;hi.clearRect(0,0,cv.width,cv.height);hi.drawImage(lo,0,0,cv.width,cv.height);
  drawOverlay(T);
  if(SKIN.zoned)drawMeetBubbles(T);   /* 开会气泡（气泡 + 图标）画在最上层 */
  drawSceneBubbles(T);   /* 场景气泡：看电影的高兴 / 打比赛一局结束的胜负（–） */
  drawPartyHi(T);   /* –复盘的汗滴 + 无语 / 疑问气泡 */
  drawDongFx();drawSayFx(dt);   /* 像素「咚」+ say 的像素对话气泡（最顶层） */
  drawInvite(T);                /* –首领的邀请气泡（最顶层） */
}
document.addEventListener("visibilitychange",()=>{if(document.hidden){RUN=false}else if(!RUN&&MODE==="office"){RUN=true;last=performance.now();
  requestAnimationFrame(frame)}});
