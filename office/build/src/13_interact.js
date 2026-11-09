/* ===================== 交互：点击 → 详情抽屉 ===================== */
let OPEN=null,HOVER=null;
function worldPt(e){const r=cv.getBoundingClientRect();return{x:(e.clientX-r.left)/r.width*WW,y:(e.clientY-r.top)/r.height*WH}}
function hitTest(p){let best=null;for(const id in CH){if(CH[id].spawnHide)continue;const b=SKIN.hit(CH[id]);
  if(p.x>=b.x&&p.x<=b.x+b.w&&p.y>=b.y&&p.y<=b.y+b.h)best=id}
  if(!best&&BGT[0]&&Math.abs(p.x-PRINTER.x)<14&&p.y>PRINTER.y-18&&p.y<PRINTER.y+12)best="__bg";
  if(!best&&p.x>=TODO_BOARD.x&&p.x<=TODO_BOARD.x+TODO_BOARD.w&&p.y>=TODO_BOARD.y&&p.y<=TODO_BOARD.y+TODO_BOARD.h)best="__todo";return best}
function todoHtml(){const a=(DATA&&DATA.arch)||{},it=a.items||[];const hm=s=>s?String(s).replace("T"," ").slice(5,16):"—";
  return `<h4>${TR("p.todoTitle",{n:a.count||0})}</h4><div class="sub">${esc(a.summary||"")}</div>`+
  (it.length?it.map(x=>`<div class="todo-it"><div><b>${esc(x.kind)}</b>${TR("p.sep")}${
  x.url?`<a href="${esc(x.url)}" target="_top">${esc(x.title||"")}</a>`:esc(x.title||"")}</div><div class="sub">${
  TR("p.from",{t:esc(hm(x.since))})}${TR("p.sep")}${esc(x.why||"")}${x.source?TR("p.source",{s:esc(x.source)}):""}</div></div>`).join("")
  :`<div class="sub">${a.count?TR("p.notReady"):TR("p.noTodo")}</div>`)
  +`<div class="sub" style="margin-top:8px">${TR("p.howTo")}</div>`}
cv.addEventListener("mousemove",e=>{const p=worldPt(e);
  const inv=inviteGeom();INV_HOVER=!!inv&&p.x>=inv.x0&&p.x<=inv.x0+inv.w&&p.y>=inv.y0&&p.y<=inv.y0+inv.h;   /* 街机 / 邀请气泡的悬停态 */
  ARC_HOVER=arcadeHit(p);
  SW_HOVER=switchHit(p);BTN_HOVER=dockBtnHit(p);       /* 昼夜开关 / 动态用量按钮的悬停态 */
  const h=(ARC_HOVER||INV_HOVER||SW_HOVER||BTN_HOVER)?null:hitTest(p);HOVER=h&&h!=="__bg"&&h!=="__todo"?h:null;
  cv.style.cursor=(ARC_HOVER||INV_HOVER||SW_HOVER||BTN_HOVER||HOVER)?"pointer":"default";
  const c=HOVER&&CH[HOVER];
  cv.title=SW_HOVER?modeName(themeMode()):BTN_HOVER?(uiLang()==="en"?BTN_HOVER.en:BTN_HOVER.zh):ARC_HOVER?(uiLang()==="en"?"Party time":"聚会时间")
  :INV_HOVER?inviteWord(inv.kind):c?`${c.data.label}（${c.data.name||""}）：${statusTip(c)}`:""});
cv.addEventListener("mouseleave",()=>{HOVER=null;ARC_HOVER=false;INV_HOVER=false;SW_HOVER=false;BTN_HOVER=null;SW_PRESS=false;BTN_PRESS=null});
cv.addEventListener("mousedown",e=>{const p=worldPt(e);SW_PRESS=switchHit(p);BTN_PRESS=dockBtnHit(p)});   /* 按下的样子 */
addEventListener("mouseup",()=>{SW_PRESS=false;BTN_PRESS=null});
cv.addEventListener("click",e=>{const p=worldPt(e);if(sayClick(p))return;if(inviteClick(p))return;if(switchClick(p)){e.stopPropagation();
return}if(dockBtnClick(p)){e.stopPropagation();return}if(arcadeClick(p)){e.stopPropagation();return}const h=hitTest(p);if(h)openDrawer(h);
  else closeDrawer()});
$("#dx").onclick=closeDrawer;
function closeDrawer(){OPEN=null;$("#drawer").classList.remove("open")}
function openDrawer(id){
  OPEN=id;let html="";
  if(id==="__todo"){html=todoHtml()}
  else if(id==="__bg"){const b=BGT[0];
    html=`<h4>${TR("p.paren2",{a:esc(b.label),b:esc(b.name)})}</h4><div class="sub">${TR("p.bgNote")}</div>`+
    `<dl><dt>${TR("p.state")}</dt><dd>${chip(b.state)}</dd>
    <dt>${TR("p.current")}</dt><dd>${esc(b.task_d)}</dd><dt>${TR("p.heartbeat")}</dt><dd>${esc(b.heartbeat||"—")}</dd>
    <dt>${TR("p.queue")}</dt><dd>${TR("p.queueN",{n:b.queue??0})}</dd></dl>`}
  else{const ch=CH[id];if(!ch)return closeDrawer();const d=ch.data,left=d.quota_left_pct;
    const al=lvl1Alerts().find(a=>a.station===id);   /* 点一只头上有 ! 的猫，抽屉最上面也显示它那条提示 */
    const alHtml=al?`<div class="drawer-alert"><b>!</b> ${esc(al.text||"")}${al.action?" → "+esc(al.action):""}${
    alertActionBtn(al,true)}</div>`:"";
    const tk=d.tok&&d.tok.today?`${TR("p.tokenIn",{a:fmt(d.tok.today.in),b:fmt(d.tok.today.out),c:fmt(d.tok.today.cr)})}<br>${
    TR("p.hit",{n:d.tok.today.hit})}${TR("p.sep")}${TR("p.calls",{n:d.tok.today.calls})}`:`<span style="color:var(--dim)">${TR("p.noData")}${
    d.tok&&d.tok.na?TR("p.paren",{v:esc(d.tok.na)}):""}</span>`;
    const qb=left==null?`<span style="color:var(--dim)">${TR("p.noData")}</span>`:`${
    TR("p.left",{n:left,u:d.quota_used_pct,slot:esc(d.quota_slot||""),src:esc(d.quota_source||"")})}`+
    `<div class="bar"><i style="width:${left}%;background:${left<10?"var(--red)":left<30?"#f5b301":"#dcc08a"}"></i></div>`;
    html=`<h4>${TR("p.paren2",{a:esc(d.label),b:esc(d.name)})}</h4><div class="sub">${TR("p.paren2",{a:esc(d.model),b:esc(d.channel)})}</div>
    <dl><dt>${TR("p.state")}</dt><dd>${chip(ch.state)} ${esc(d.state_sub||"")}</dd><dt>${TR("p.task")}</dt><dd>${esc(d.task_d||"—")}</dd>${
      d.tool?`<dt>${TR("p.tool")}</dt><dd>${esc(d.tool)}</dd>`:""}
    <dt>${TR("p.queue")}</dt><dd>${TR("p.queueN",{n:d.queue||0})}${
      (d.queue_items||[]).length?"<br>"+d.queue_items.map(esc).join("<br>"):""}</dd><dt>${TR("p.quota")}</dt><dd>${
      qb}</dd><dt>${TR("p.token")}</dt><dd>${tk}</dd><dt>${TR("p.last")}</dt><dd>${esc(d.last||"—")}</dd></dl>`;
    html=alHtml+html}
  $("#dbody").innerHTML=html;$("#drawer").classList.add("open");
  const ds=$("#d-summon");if(ds)ds.onclick=()=>summonLeader((lvl1Alerts().find(a=>a.action_id==="summon")||{}).station||"");
  const da=$("#d-add-leader");if(da)da.onclick=()=>openAddLeader();
}
const fmt=n=>n==null?"–":n>=1e6?(n/1e6).toFixed(2)+"M":n>=1e3?(n/1e3).toFixed(1)+"k":n;
function chip(s){const v=STATE[s]||[s,"#8d8d9b"];return `<span class="chip" style="color:${v[1]}">${TR(v[0])}</span>`}
/* 歇着：悬停给完整那句（出去玩了，预计 01:54 回来（额度用完）） */
function statusTip(ch){const w=statusWord(ch);if(ch&&ch.state==="rest"){const r=(ch.data&&ch.data.rest)||{};return r.word||w}return w}
