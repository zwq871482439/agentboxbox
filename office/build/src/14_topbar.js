/* ===================== 顶栏 / 列表视图 / 切换 ===================== */
function renderStrip(){const s=(DATA&&DATA.strip)||{};$("#m-calls").textContent=s.calls_today??"–";$("#m-ok").textContent=s.ok_pct!=null?s.ok_pct+"%":"–";
  $("#m-run").innerHTML=`${s.running??"–"}<small>/ ${s.total??"–"}</small>`;const you=(DATA.channels||[]).filter(c=>c.state==="you").length;
    $("#mt-you").hidden=!you;$("#m-you").textContent=you}
function renderList(){$("#list").innerHTML=`<table>${(DATA.channels||[]).map(c=>`<tr><td class="n">${
  TR("p.paren",{v:esc(c.label)+" "+esc(c.name)})}</td><td>${chip(c.state)}
</td><td class="t">${esc(c.task_d||"—")}</td><td class="t">${
  c.quota_left_pct==null?TR("t.noData"):TR("t.left",{n:c.quota_left_pct})}</td></tr>`).join("")}</table>`}
document.querySelectorAll(".seg button[data-v]").forEach(b=>b.onclick=()=>{document.querySelectorAll(".seg button[data-v]").forEach(x=>x.classList.toggle("on",
  x===b));MODE=b.dataset.v;
  $("#cv").hidden=MODE!=="office";$("#list").hidden=MODE!=="list";try{localStorage.setItem("bx-office-mode",MODE)}catch(e){}
  if(MODE==="office"&&!RUN){RUN=true;last=performance.now();requestAnimationFrame(frame)}else if(MODE!=="office")RUN=false});
document.querySelectorAll("#theme-seg button").forEach(b=>b.onclick=()=>setThemeMode(b.dataset.m));
async function loadThemeTimes(base){ /* 四个时间点在设置页改；核心没在跑就用默认 */
  try{const r=await fetch((base||"")+"/api/settings",{cache:"no-store"});if(!r.ok)return;const s=await r.json();const t=s.office_theme_times;
    if(t&&typeof t==="object"){THEME_TIMES=Object.assign({},THEME_TIMES,t);applyTheme(true)}}catch(e){}
}
