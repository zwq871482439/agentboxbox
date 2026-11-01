/* ===================== =====================
   原来顶栏的「场景」菜单没了，入口换成会议室里的实体道具：投影机旁的桌角上立一台聚会街机（16×26 像素，
   立绘逐像素搬进代码，见上面 ARCADE_ART / MENU_ART）。悬停换「-悬停」立绘并冒一行小字「聚会时间 / Party time」；
   点它弹出像素窗口菜单（上岗那套米白底、深棕描边、硬阴影）：
   - 放电影 / 来一局：照旧走 sceneStart（画面在「
   - 回去干活：收当前会议室场景、猫各自回工位（没有场景在演时置灰）
   场景演着的时候街机播「进行中」三帧动画；夜晚用 -夜 的立绘（跟整间办公室换夜色同步）。 */
let SCENE_BUBBLES=null;   /* 场景气泡的总开关：没在画面上摆开关了（设置页还有），本地记着用于临时覆盖 */
function sceneBubblesOn(){
  if(SCENE_BUBBLES!=null)return SCENE_BUBBLES;
  const s=DATA&&DATA.scenes;
  return !(s&&s.enabled===false)}
const ARCADE={foot:[448,122],w:16,h:26};   /* 脚点 / 占地：MANIFEST 建议的 (448,122)，立在会议室桌角、投影机旁，不挡幕布 */
let ARC_HOVER=false,INV_HOVER=false;       /* 这一帧鼠标在不在街机 / 邀请气泡上（mousemove 里维护） */
function arcadeRect(){return{x:ARCADE.foot[0]-ARCADE.w/2,y:ARCADE.foot[1]-ARCADE.h,w:ARCADE.w,h:ARCADE.h}}
function arcadeHit(p){const r=arcadeRect();return p.x>=r.x&&p.x<=r.x+r.w&&p.y>=r.y-2&&p.y<=r.y+r.h}
function arcadeArt(){const n=THEME.phase==="night";
  if(SCENE&&SCENE.name)return ARCADE_ART["run"+(Math.floor(T*5)%3)+(n?"N":"")];   /* 场景演着：进行中三帧 */
  if(ARC_HOVER)return ARCADE_ART[n?"hoverN":"hover"];
  return ARCADE_ART[n?"idleN":"idle"]}
function drawArtW(rows,x0,y0,pal){ /* 世界层逐像素画一张立绘（1 格 = 1 世界像素，透明跳过） */
  pal=pal||APAL;
  for(let j=0;j<rows.length;j++)for(let i=0;i<rows[j].length;i++){const c=pal[rows[j][i]];if(c)R(x0+i,y0+j,1,1,c)}}
function drawArcade(t){const r=arcadeRect();drawArtW(arcadeArt(),r.x,r.y)}
function partyItems(){const en=uiLang()==="en";
  return[{k:"movie",ic:"movie",t:en?"Movie":"放电影"},
         {k:"game",ic:"pad",t:en?"Play a round":"来一局"},
         {k:"work",ic:"desk",t:en?"Back to work":"回去干活"}]}
function menuIconCanvas(ic){const c=document.createElement("canvas");c.width=c.height=8;
  const x=c.getContext("2d"),rows=MENU_ART[ic]||[];
  for(let j=0;j<rows.length;j++)for(let i=0;i<rows[j].length;i++){const col=APAL[rows[j][i]];if(col){x.fillStyle=col;x.fillRect(i,j,1,1)}}
  return c}
function partyEndScene(){ /* 「回去干活」：收当前场景，猫各自回工位（和庆祝场景到点收场一个走法） */
  if(!SCENE||!SCENE.name)return;
  const ids=SCENE.name&&SCENE.ids?[...SCENE.ids]:[];
  sceneEnd("work");
  for(const id of ids){const ch=CH[id];if(ch&&!NAPS.has(id))wantHome(ch,ch.st&&ch.st.lead?"boss_idle":"sit")}}
function partyMenuCmd(k){closePartyPop();
  if(k==="movie")sceneStart("movie");
  else if(k==="game")sceneStart("game");
  else if(k==="work")partyEndScene()}
function closePartyPop(){const p=$("#party-pop");if(p)p.hidden=true}
function renderPartyPop(){const p=$("#party-pop");p.innerHTML="";
  for(const it of partyItems()){const b=document.createElement("button");b.type="button";b.dataset.k=it.k;
    b.appendChild(menuIconCanvas(it.ic));const sp=document.createElement("span");sp.textContent=it.t;b.appendChild(sp);
    if(it.k==="work"&&!SCENE)b.disabled=true;                       /* 没场景在演：置灰，点了没用 */
    b.onclick=()=>{if(b.disabled)return;partyMenuCmd(it.k)};
    p.appendChild(b)}}
function placePartyPop(){const p=$("#party-pop");if(!p||p.hidden)return;   /* 菜单右缘对齐街机右缘、开在脚点下方 */
  const r=arcadeRect(),c=cv.getBoundingClientRect(),s=$("#stage").getBoundingClientRect(),k=c.width/WW;
  p.style.left=((c.left-s.left)+(r.x+r.w)*k-p.offsetWidth)+"px";
  p.style.top=((c.top-s.top)+(r.y+r.h)*k+4)+"px"}
function arcadeClick(p){if(!arcadeHit(p))return false;   /* 点街机：开 / 关聚会菜单（开的时候重新按当前语言和场景渲染） */
  const el=$("#party-pop");el.hidden=!el.hidden;
  if(!el.hidden){renderPartyPop();placePartyPop()}
  return true}
$("#party-pop").addEventListener("click",e=>e.stopPropagation());
document.addEventListener("click",e=>{const p=$("#party-pop");if(p&&!p.hidden&&!p.contains(e.target))p.hidden=true});
