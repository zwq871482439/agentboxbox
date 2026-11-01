/* ===================== 画布 ===================== */
const cv=$("#cv"), hi=cv.getContext("2d");
const lo=document.createElement("canvas"); lo.width=WW*LOK; lo.height=WH*LOK;
let S=4; // 高清画布每个世界像素的大小（整数）
const g=lo.getContext("2d");
  /* 嵌入时按 iframe 可视区等比缩放，整间办公室都放得下，不裁切 */
function fit(){if(EMBED){const k=Math.max(.1,Math.min((innerWidth-2)/WW,(innerHeight-2)/WH));
  cv.style.width=Math.floor(WW*k)+"px";cv.style.height=Math.floor(WH*k)+"px"}
  const w=cv.clientWidth||960;S=Math.max(2,Math.ceil(w*(devicePixelRatio||1)/WW));
  cv.width=WW*S;cv.height=WH*S;placePartyPop();placeThemePop()}
addEventListener("resize",fit);
function R(x,y,w,h,c){g.fillStyle=c;g.fillRect(x,y,w,h)}           // 世界坐标画矩形（g 已缩放 LOK）
function shade(hex,k){const n=parseInt(hex.slice(1),16);let r=n>>16,gg=(n>>8)&255,b=n&255;const f=v=>clamp(Math.round(k<0?v*(1+k):v+(255-v)*k),0,255);
  return "#"+[f(r),f(gg),f(b)].map(v=>v.toString(16).padStart(2,"0")).join("")}

__CATS_JS__
/* 把一只猫画到世界里：x 为中线，y 为脚底 */
function drawCatSprite(spr,x,y,face,layer){g.save();g.translate(Math.round(x),Math.round(y));g.scale(face,1);g.drawImage(spr[layer],-spr.N/2,-spr.N,spr.N,
  spr.N);g.restore()}
function catWorld(spr,x,y,face,X,Y){return{x:x+face*(X-16)*spr.k,y:y+(Y-32)*spr.k}}
/* v2：吃零食 = 手里换成小饭团 + 掉渣；其余捧杯冒热气 */
function propFx(ch,c,t){if(ch.act!=="eat")return steam(c.x,c.y,t);
    const x=Math.round(c.x-2.5), y=Math.round(c.y-1.5),
  bite=(t%1.2)<.5;R(x,y,5,4,"#f8fafc");R(x+1,y-1,3,1,"#f8fafc");R(x+1,y+2,3,2,"#1f2937");if(bite)R(x+3,y-1,2,1.5,"#2b2233");
  for(let i=0;i<2;i++){const p=(t*1.3+i/2)%1;g.globalAlpha=1-p;R(x+1+i*2,y+4+p*6,.6,.6,"#fde68a");g.globalAlpha=1}}
function steam(x,y,t){for(let i=0;i<3;i++){const p=(t*.8+i/3)%1;g.globalAlpha=.55*(1-p);R(x-1+i+Math.sin(t*3+i*2)*1,y-2-p*8,1,1.5,"#ffffff");g.globalAlpha=1}}
/* 角色当前该用哪个姿势 / 帧 / 表情 */
function catPose(ch,t){
  const a=ch.act, fps=n=>Math.floor(t*n);
  const joy=(t%4.2)<.7;
  if(ch.moving)return{p:"walk",f:fps(ch.hurry?12:7)%4};
  if(a==="stand")return{p:"stand",f:0};   /* 站着（开会站位 / 场景围观 / 站会）：站直，不坐 */
  if(a==="meow")return{p:"yay",f:fps(6)%2};
  if(ch.state==="you")return{p:"you",f:fps(3)%2};
  if(ch.state==="fail")return{p:"fail",f:fps(3)%2};
  switch(a){
    case"type":return{p:"type",f:fps(8)%2};
    case"deskplay":{const sc=ch.playScene;if(sc==="video")return{p:"tea",f:(t%5)<1.2?1:0};if(sc==="blocks")return{p:"type",f:fps(5)%2,e:joy?"joy":null};
      return{p:"game",f:fps(5)%2,e:joy?"joy":null}}
    case"sleepbox":return{p:"nap",f:0};
    case"teabox":case"tea":return{p:"tea",f:(t%4)<1.3?1:0};
    case"phone":return{p:"phone",f:(t%3.4)<.6?1:0};
    case"stretch":return{p:"stretch",f:ch.actT<.6?0:ch.actT<2.6?1:ch.actT<3.2?2:0};
    case"wait":return{p:"wait",f:0};
    case"fridge":return{p:"phone",f:(t%2.6)<.5?1:0};
    case"sofanap":return{p:"nap",f:0};
    case"sofaphone":return{p:"phone",f:(t%3.4)<.6?1:0};
    case"sofachat":case"cards":return{p:(t%3)<.8?"yay":"sit",f:fps(4)%2};
    case"brew":return{p:"wait",f:0};
    case"fridgeopen":return{p:"yay",f:0};
    case"drink":return{p:"tea",f:(t%4)<1.3?1:0};
    case"eat":return{p:"tea",f:(t%1.2)<.5?1:0};
    case"chat":return{p:(t%3)<.8?"yay":"sit",f:fps(4)%2};
    case"boss_idle":return ch.bossAnim==="nap"?{p:"nap",f:0}:ch.bossAnim==="game"?{p:"game",f:(t%2.6)<.5?1:0}:ch.bossAnim==="tea"?{p:"tea",
      f:(t%4)<1.3?1:0}:ch.bossAnim==="phone"?{p:"phone",f:(t%3.4)<.6?1:0}:{p:"sit",f:0};
  }
  return{p:"sit",f:0};
}
