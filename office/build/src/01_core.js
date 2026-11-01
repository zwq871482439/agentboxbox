/* ===================== 常量 / 工具 ===================== */
const WW=480, LOK=2; let WH=270;  /* 大办公室：16:9，四个区（工位区 / 茶水间 / 沙发区 / 会议室） */               // 世界坐标 360×256；低清画布 2×（屏幕内容可以画到半像素）；猫猫 1 像素 = 1 世界像素
const STATE={run:["state.run","#3ddc84"],arch:["state.arch","#f5b301"],you:["state.you","#ff4d4f"],idle:["state.idle","#8d8d9b"],
  off:["state.off","#5c5c6b"],rest:["state.rest","#f5b301"],fail:["state.fail","#ff4d4f"],appr:["state.appr","#5aa9ff"],
  done:["state.done","#8d8d9b"],block:["state.block","#8d8d9b"]};
const stateWord=s=>(STATE[s]||["state.idle","#8d8d9b"])[0];   /* 状态词走词表：画布上写的是当前语言 */

/* ===================== 昼夜（assets/design/office-daynight/spec.md，UI 组 ）=====================
   只换房间的光和配色，布局 / 猫 / 纸箱 / 气泡 / 告警全部不动。四套色表 + 按分钟插值；
   自动档跟本机时间（四个时间点可在设置页改），手动档白天 / 夜晚存本机 localStorage。 */
/* v2 大窗天空 / 光影参数（assets/design/office-v2/spec.md 第 3–5 节）：四个时段各一套，过渡时段和 PAL 同一节奏按分钟插值。
   s0/s1 天空渐变，b0/b1 前后两排楼，win 楼窗灯色，lit 亮灯比例，fr 窗框色，sun 太阳/月亮 [x,y,色]，sg* 光晕，
   patch/pa/L/dx 地上窗形光斑（色 / 透明度 / 长度 / 偏移），vx/vy/sa/sc 影子（方向系数 / 不透明度 / 色）。 */
const SKYS={dawn:SKY_DAWN,day:SKY_DAY,dusk:SKY_DUSK,night:SKY_NIGHT};
function skyLerp(a,b,k){const o={};for(const key in a){const va=a[key],vb=b[key];
  o[key]=typeof va==="number"?va+(vb-va)*k:Array.isArray(va)?va.map((v,i)=>typeof v==="number"?v+(vb[i]-v)*k:hexLerp(v,vb[i],
    k)):(typeof va==="string"&&va[0]==="#"?hexLerp(va,vb,k):(k<.5?va:vb))}return o}
let THEME_TIMES={dawn:"06:30",day:"07:00",dusk:"18:00",night:"18:30"};   /* /api/settings.office_theme_times 可覆盖 */
let PAL=PAL_NIGHT, SKY=SKY_NIGHT, THEME={phase:"night",label:TR("phase.night"),mode:"auto"};
function hexLerp(a,b,k){if(k<=0)return a;if(k>=1)return b;const A=parseInt(a.slice(1),16),B=parseInt(b.slice(1),16);
  const ch=s=>Math.round(((A>>s)&255)+(((B>>s)&255)-((A>>s)&255))*k);return "#"+[ch(16),ch(8),ch(0)].map(v=>v.toString(16).padStart(2,"0")).join("")}
function palLerp(a,b,k){const o={};for(const key in a){const va=a[key],vb=b[key];
  o[key]=typeof va==="number"?va+(vb-va)*k:(typeof va==="string"&&va[0]==="#"?hexLerp(va,vb,k):(k<.5?va:vb))}return o}
function minOf(s){const m=/^(\d{1,2}):(\d{2})$/.exec(String(s||""));return m?(+m[1])*60+(+m[2]):null}
function themeAuto(date){ /* 自动档：按本机时间算当前该是哪套色（黄昏 / 黎明按分钟插值，各分两段经过橙 / 粉色表） */
  const now=date.getHours()*60+date.getMinutes();
  const dawn=minOf(THEME_TIMES.dawn)??390,day=minOf(THEME_TIMES.day)??420,dusk=minOf(THEME_TIMES.dusk)??1080,night=minOf(THEME_TIMES.night)??1110;
  const seg=(a,b)=>b>a?clamp((now-a)/(b-a),0,1):1;
  if(now>=day&&now<dusk)return{phase:"day",pal:PAL_DAY,sky:SKY_DAY};
  if(now>=dusk&&now<night){const k=seg(dusk,night);return{phase:"dusk",pal:k<.5?palLerp(PAL_DAY,PAL_DUSK,k*2):palLerp(PAL_DUSK,PAL_NIGHT,(k-.5)*2),
    sky:k<.5?skyLerp(SKY_DAY,SKY_DUSK,k*2):skyLerp(SKY_DUSK,SKY_NIGHT,(k-.5)*2)}}
  if(now>=dawn&&now<day){const k=seg(dawn,day);return{phase:"dawn",pal:k<.5?palLerp(PAL_NIGHT,PAL_DAWN,k*2):palLerp(PAL_DAWN,PAL_DAY,(k-.5)*2),
    sky:k<.5?skyLerp(SKY_NIGHT,SKY_DAWN,k*2):skyLerp(SKY_DAWN,SKY_DAY,(k-.5)*2)}}
  return{phase:"night",pal:PAL_NIGHT,sky:SKY_NIGHT};
}
const THEME_MODES=["auto","dawn","day","dusk","night"];   /* 五档 = 自动 / 清晨 / 白天 / 傍晚 / 夜晚（存本机 bx-office-theme） */
function themeMode(){try{const m=localStorage.getItem("bx-office-theme");return THEME_MODES.indexOf(m)>=0?m:"auto"}catch(e){return "auto"}}
function setThemeMode(m){try{localStorage.setItem("bx-office-theme",THEME_MODES.indexOf(m)>=0?m:"auto")}catch(e){}applyTheme(true)}
function applyTheme(force){ /* 每分钟一次；页面刚打开直接到当前时段的颜色，不播过渡 */
  const mode=themeMode(),d=new Date(Date.now()),phx=Q.get("phase");   /* ?phase=dawn|day|dusk|night：固定时段（预览 / 截图 / 测试用） */
  const PALS={dawn:PAL_DAWN,day:PAL_DAY,dusk:PAL_DUSK,night:PAL_NIGHT};
  const r=phx&&PALS[phx]?{phase:phx,pal:PALS[phx],sky:SKYS[phx]}:mode==="auto"?themeAuto(d):{phase:mode,pal:PALS[mode],sky:SKYS[mode]};
  /* 固定档 dawn / day / dusk / night 各自一套色；auto 跟电脑时间走 */
  const hm=String(d.getHours()).padStart(2,"0")+":"+String(d.getMinutes()).padStart(2,"0");
  const label=TR("phase."+r.phase)+" "+hm;
  const changed=force||r.phase!==THEME.phase||mode!==THEME.mode||r.pal.wall!==PAL.wall;
  PAL=r.pal;SKY=r.sky;THEME={phase:r.phase,label,mode};STATE.run[1]=PAL.run;
  const rs=document.documentElement.style;rs.setProperty("--bg",PAL.bg);rs.setProperty("--bg2",PAL.bg2);rs.setProperty("--txt",PAL.txt);rs.setProperty("--line",
    PAL.line);
  const lab=$("#theme-label");if(lab)lab.textContent=label;
  document.querySelectorAll("#theme-seg button").forEach(b=>b.classList.toggle("on",b.dataset.m===mode));
  if(changed||force){try{if(parent&&parent!==window)parent.postMessage({type:"bx-office-theme",phase:r.phase,label,mode,bg:PAL.bg},"*")}catch(e){}}
}
addEventListener("storage",e=>{if(e.key==="bx-office-theme")applyTheme(true)});
addEventListener("message",e=>{const m=e.data||{};
  if(m.type==="bx-office-theme-set")setThemeMode(m.mode);
  else if(m.type==="bx-unread")UNREAD={feed:+m.feed||0,usage:+m.usage||0}   /* 首页报过来的未读数（动态 / 用量） */
  else if(m.type==="bx-lang")applyUiLang(m.lang)});   /* the outer page switched language: follow it */
const ACCENTS=["#5aa9ff","#a78bfa","#ff9f43","#2dd4bf","#f472b6","#a3e635","#facc15","#60a5fa"];
/* 语言那几个（Q / LANG_SET / uiLang / applyUiLang）在 01_i18n.js 里：词表要先能查 */
const EMBED=Q.get("embed")==="1";              // ?embed=1：只露舞台，藏顶栏/标题/演示/页脚/列表切换（嵌进 mockup 用）
const LIVE=!!Q.get("live");                     // ?live=1：吃实时接口；日常上岗动画（feed 新增 / 减少打工猫）只在这个模式下自动播
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const catNameOf=d=>(d&&d.cat_name)||(d&&d.label)||"";   /* 猫脚下只画一行名字 = 它的名字（feed 的 cat_name = 工位名，上岗时起的；channel.name 是型号，不能用）；没有才退回标签 */
const rnd=(a,b)=>a+Math.random()*(b-a), pick=a=>a[Math.floor(Math.random()*a.length)], clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function hash(s){let h=7;for(const c of String(s))h=(h*31+c.charCodeAt(0))>>>0;return h}
/* 种子随机：同一只猫在同一个时间片（IDLE_SLOT_S 秒）里选的活动 / 位置固定 → 刷新页面、5 秒轮询都不乱跳 */
const IDLE_SLOT_S=45;
function srand(seed){let a=hash(seed)||1;return()=>{a=(a+0x6D2B79F5)>>>0;let t=a;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);
  return((t^t>>>14)>>>0)/4294967296}}
function slotOf(){return Math.floor(Date.now()/1000/IDLE_SLOT_S)}
/* 测试钩子：把墙上时钟钉住（tests/test_office_coffee.py）。
   空闲时间片 slotOf() 和首领休闲的种子都取墙上时钟，不钉住的话同一个过程重跑一遍结果就可能不一样；
   钉住之后，__office.tick() 推进多少帧就演多少秒，重跑多少遍都一样。thaw() 放回真时钟。 */
let REAL_NOW=null,FROZEN_NOW=0;
function freezeClock(ms){if(REAL_NOW===null){REAL_NOW=Date.now;Date.now=()=>FROZEN_NOW}FROZEN_NOW=ms;return FROZEN_NOW}
function thawClock(){if(REAL_NOW!==null){Date.now=REAL_NOW;REAL_NOW=null}FROZEN_NOW=0}
/* 测试钩子（在页面第一个脚本里就装好，所以连刚打开时给每只猫定的初始时间都一样）：
   ?seed=<整数> 固定随机数，?clock=<毫秒> 钉住墙上时钟。两个都只给测试用（tests/test_office_coffee.py 连跑 20 次）；
   平时打开不带这两个参数，行为不变。 */
(function(){const sd=Q.get("seed"),ck=Q.get("clock");
  if(sd!==null&&sd!==""){let a=(parseInt(sd,10)||1)>>>0;Math.random=()=>{a=(a+0x6D2B79F5)>>>0;let t=a;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);
    return((t^t>>>14)>>>0)/4294967296}}
  if(ck!==null&&ck!=="")freezeClock(parseInt(ck,10)||0)})();

/* 。
   第 1 级一条一行「text → action」，最多 3 行，多了写「还有 N 条」；action_id=summon 的那行带「叫醒首领」。 */
function lvl1Alerts(){return ((DATA&&DATA.alerts)||[]).filter(a=>a&&a.level===1)}
function renderAlertBar(){
  const bar=$("#alertbar");if(!bar)return;const all=lvl1Alerts();
  if(!all.length){bar.hidden=true;bar.innerHTML="";return}
  const rows=all.slice(0,3).map(a=>`<div class="al"><span class="al-t"><b>!</b><span>${esc(a.text||"")}${a.action?" → ":""}
    <span class="act">${esc(a.action||"")}</span></span></span>
    ${a.action_id==="summon"?`<button type="button" data-summon="${esc(a.station||"")}">${TR("alert.summon")}</button>`:""}</div>`).join("")
    +(all.length>3?`<div class="more">${TR("alert.more",{n:all.length-3})}</div>`:"");
  bar.innerHTML=rows;
  bar.hidden=false;
  bar.querySelectorAll("[data-summon]").forEach(b=>b.onclick=()=>summonLeader(b.getAttribute("data-summon")));
}
/* 「叫醒首领」：复用原横幅「看怎么叫它回来」的逻辑——bx-summon 事件（首页接住开上岗抽屉），没人接就跳 /#summon=。
   嵌在首页 iframe 里时事件发给父页面。 */
function summonLeader(sid){
  try{const w=(EMBED&&window.parent&&window.parent!==window)?window.parent:window;
    const ev=new w.CustomEvent("bx-summon",{cancelable:true,detail:sid||""});
    if(w.dispatchEvent(ev))w.location.href="/#summon="+encodeURIComponent(sid||"")}catch(e){location.href="/#summon="+encodeURIComponent(sid||"")}
}
