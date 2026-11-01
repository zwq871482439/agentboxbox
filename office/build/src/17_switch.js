/* ===================== =====================
   首页顶栏下面那一行（#dock：动态 / 用量 + 自动 / 白天 / 夜晚）没了，入口都挪进画布里：
   - 霓虹牌正下方挂一个昼夜开关（48×28，素材逐像素搬进代码）：点它弹五档菜单（自动 / 清晨 / 白天 / 傍晚 / 夜晚），
     旋钮指向当前档；悬停冒一行当前档名。档位存本机（bx-office-theme），照旧 postMessage 给首页改背景色。
   - 挂钟右边挂「动态」「用量」两个按钮（38×16）：点它让首页开同名面板；只在嵌进首页时（?embed=1）画，
     单独打开 /office 不画。未读数由首页 postMessage 过来（bx-unread），红点 + 数字画在按钮右上角。 */
const SWITCH={x:392,y:30,w:48,h:28};                 /* 霓虹牌正下方（MANIFEST：392,30） */
const MODE_ORDER=["auto","dawn","day","dusk","night"];
const MODE_NAME={auto:{zh:"自动",en:"Auto"},dawn:{zh:"清晨",en:"Dawn"},day:{zh:"白天",en:"Day"},dusk:{zh:"傍晚",en:"Dusk"},night:{zh:"夜晚",en:"Night"}};
const DOCK_BTN=[{k:"feed",panel:"tl",x:96,y:10,w:38,h:16,zh:"动态",en:"Activity"},
                {k:"usage",panel:"tok",x:96,y:28,w:38,h:16,zh:"用量",en:"Usage"}];
let SW_HOVER=false,SW_PRESS=false,BTN_HOVER=null,BTN_PRESS=null;    /* 这一帧鼠标在开关 / 哪个按钮上 */
let UNREAD={feed:0,usage:0};                         /* 首页报过来的未读数（bx-unread） */
function modeName(m){const n=MODE_NAME[m]||MODE_NAME.auto;return uiLang()==="en"?n.en:n.zh}
function switchRect(){return{x:SWITCH.x,y:SWITCH.y,w:SWITCH.w,h:SWITCH.h}}
function switchHit(p){const r=switchRect();return p.x>=r.x&&p.x<=r.x+r.w&&p.y>=r.y&&p.y<=r.y+r.h}
function dockBtnHit(p){if(!EMBED)return null;return DOCK_BTN.find(b=>p.x>=b.x&&p.x<=b.x+b.w&&p.y>=b.y&&p.y<=b.y+b.h)||null}
function switchArt(){const m=themeMode();return SW_PRESS?SWITCH_ART.press:SW_HOVER?SWITCH_ART.hover:(SWITCH_ART[m]||SWITCH_ART.auto)}
function btnArt(b){const A=BTN_ART[b.k],night=THEME.phase==="night";
  return BTN_PRESS===b?A.press:BTN_HOVER===b?A.hover:night?A.night:A.idle}
function drawThemeSwitch(){drawArtW(switchArt(),SWITCH.x,SWITCH.y,NPAL)}
function drawDockBtns(){if(!EMBED)return;for(const b of DOCK_BTN){drawArtW(btnArt(b),b.x,b.y,NPAL);
  const n=UNREAD[b.k]||0;if(n>0)drawArtW(DOT_ART,b.x+b.w-8,b.y+1,NPAL)}}   /* 未读红点底叠在按钮右上角 */
function modeIconCanvas(m){const c=document.createElement("canvas");c.width=c.height=7;
  const x=c.getContext("2d"),rows=MODE_ART[m]||[];
  for(let j=0;j<rows.length;j++)for(let i=0;i<rows[j].length;i++){const col=NPAL[rows[j][i]];if(col){x.fillStyle=col;x.fillRect(i,j,1,1)}}
  return c}
function closeThemePop(){const p=$("#theme-pop");if(p)p.hidden=true}
function renderThemePop(){const p=$("#theme-pop");if(!p)return;p.innerHTML="";
  for(const m of MODE_ORDER){const b=document.createElement("button");b.type="button";b.dataset.m=m;
    b.appendChild(modeIconCanvas(m));const sp=document.createElement("span");sp.textContent=modeName(m);b.appendChild(sp);
    if(m===themeMode())b.classList.add("on");       /* 当前档反白 */
    b.onclick=()=>{closeThemePop();setThemeMode(m)};
    p.appendChild(b)}}
function placeThemePop(){const p=$("#theme-pop");if(!p||p.hidden)return;   /* 菜单开在开关左边（开关贴着右边墙） */
  const r=switchRect(),c=cv.getBoundingClientRect(),s=$("#stage").getBoundingClientRect(),k=c.width/WW;
  p.style.left=Math.max(4,(c.left-s.left)+r.x*k-p.offsetWidth)+"px";
  p.style.top=((c.top-s.top)+r.y*k)+"px"}
function switchClick(p){if(!switchHit(p))return false;   /* 点开关：开 / 关五档菜单 */
  const el=$("#theme-pop");if(!el)return false;
  el.hidden=!el.hidden;
  if(!el.hidden){renderThemePop();placeThemePop()}
  return true}
function dockBtnClick(p){const b=dockBtnHit(p);if(!b)return false;   /* 点按钮：让首页开同名面板 */
  try{if(parent&&parent!==window){const r=cv.getBoundingClientRect();   /* 按钮在 iframe 里的位置（首页拿它摆浮窗） */
    parent.postMessage({type:"bx-open-panel",panel:b.panel,
      rect:{x:r.left+b.x*r.width/WW,y:r.top+b.y*r.height/WH,w:b.w*r.width/WW,h:b.h*r.height/WH}},"*")}}catch(e){}
  return true}
addEventListener("keydown",e=>{if(e.key!=="Escape")return;   /* 焦点在画布里时按 Esc，首页的面板也要关 */
  try{if(parent&&parent!==window)parent.postMessage({type:"bx-close-panel"},"*")}catch(e){}})
$("#theme-pop").addEventListener("click",e=>e.stopPropagation());
document.addEventListener("click",e=>{const p=$("#theme-pop");if(p&&!p.hidden&&!p.contains(e.target))p.hidden=true});
