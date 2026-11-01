/* ===================== 数据：样例 / 实时接口 ===================== */
let DATA=null;
async function loadSample(){
  try{const r=await fetch(Q.get("src")||"sample.json",{cache:"no-store"});if(!r.ok)throw 0;
    $("#src-note").textContent=TR("d.sample");return localizeSample(await r.json())}
  catch(e){$("#src-note").textContent=TR("d.builtin");return localizeSample(JSON.parse($("#sample-inline").textContent))}
}
/* 样例里写死的中文（还有旧称呼）换成当前语言 */
function localizeSample(v){
  if(typeof v==="string"){
    const m=v.match(/^Team Member (.+)$/);if(m)return TR("demo.memberLabel",{id:m[1]});
    const k=SAMPLE_TXT[v];return k?TR(k):v}
  if(Array.isArray(v))return v.map(localizeSample);
  if(v&&typeof v==="object"){const o={};for(const k in v)o[k]=localizeSample(v[k]);return o}
  return v}
/* 实时：直接吃 dashboard.py 现有接口（?live=1，同源）。服务端有 /api/office 时优先用它。 */
async function loadLive(base){
  const J=async p=>{const r=await fetch(base+p,{cache:"no-store"});if(!r.ok)throw new Error(p+" "+r.status);return r.json()};
  try{const o=await J("/api/office");$("#src-note").textContent=TR("d.office");return o}catch(e){}
  const [st,mt,ca,qa,ar,mg]=await Promise.all(["/api/stations","/api/metrics","/api/cards","/api/quota","/api/arch","/api/merge"].map(p=>J(p).catch(()=>null)));
  $("#src-note").textContent=TR("d.live");
  return adaptLive({stations:st,metrics:mt,cards:ca,quota:qa,arch:ar,merge:mg});
}
/* 把 dashboard.py 的原始返回拼成办公室用的结构（字段对照见 README） */
function adaptLive(R){
  const rows=(R.metrics&&R.metrics.stations&&R.metrics.stations.length?R.metrics.stations:(R.stations&&R.stations.rows)||[]);
  const C=(R.metrics&&R.metrics.c)||{}, TOK=(R.metrics&&R.metrics.tok)||{}, cards=((R.cards&&R.cards.cards)||[]);
  const BG=new Set(["background"]), SKIP=/^D$/;
  const chans=[];let i=0;
  for(const r of rows){
    const id=r.station||r.id; if(BG.has(id)||SKIP.test(id)||SKIP.test(r.model||""))continue;
    const m=C[id]||{}, c=cards.find(x=>x.key===id||x.station===id)||{};
    let state=r.enabled===false?"off":(m.state||r.state||"idle");
    if(c.enabled===false||((c.color==="grey"||c.color==="red")&&(c.word_code==="off"||c.word_code==="not_connected"
      ||/已停|已禁用|已关闭|离线|断开|不通|可能挂了|没开/.test(c.word||""))))state="off";
    /* 与 dashboard.station_status() 同一规则 */
    const lead=id==="架构师"||id==="主模型"||id==="TeamLeader"||id==="Leader";
    let used=c.quota&&c.quota.pct!=null?c.quota.pct:null, slot=c.quota&&c.quota.slot, src=c.quota&&c.quota.source;
    if(c.quota_mode==="off"){used=null;slot=null;
src=null}else if(lead&&R.quota&&R.quota.per&&R.quota.per.cursor&&R.quota.per.cursor.max_pct!=null){used=R.quota.per.cursor.max_pct;slot=TR("d.month");
      src=R.quota.per.cursor.source}
    chans.push({id,slot:r.slot||"",role:lead?"lead":"worker",label:lead?TR("d.leader"):id,name:lead?String(r.model||"").replace(/（.*）/,
      ""):String(r.model||"").replace(/\u00b7/g," "),model:r.model,channel:r.channel,
            state, state_word:stateWord(state), state_sub:m.sub??r.state_sub, quota_mode:c.quota_mode||(lead?"off":undefined), quota_used_pct:used,
      quota_left_pct:used==null?null:Math.max(0,Math.round(100-used)),
      quota_slot:slot,quota_source:src,quota_reset:c.quota&&c.quota.reset,task_d:m.task_d||m.task||r.latest,tool:m.tool,queue:m.queue||0,
      last:r.last,tok:TOK[id]||null,accent:ACCENTS[i++%ACCENTS.length]});
  }
  const a=(R.metrics&&R.metrics.a)||{}, b=(R.metrics&&R.metrics.b)||{};
  const mg=R.merge||{}, bg=[];
  if(mg.heartbeat)bg.push({id:"background",label:TR("d.bgTask"),name:TR("d.mergeScript"),state:mg.current&&mg.heartbeat.ok?"run":(mg.heartbeat.ok?"idle":"off"),
    state_word:mg.heartbeat.ok?"":TR("d.offline"),
          task_d:mg.current&&mg.heartbeat.ok?("#"+mg.current.pr+" "+(mg.current.phase||"")):TR("d.idle"),
     heartbeat:mg.heartbeat.age_s!=null?TR("d.ago",{n:mg.heartbeat.age_s}):"", queue:(mg.daemon_queue||[]).length});
  return {schema:"boxbox.office/1",fetched:(R.metrics||{}).fetched,
    strip:{calls_today:R.calls_today??null,ok_pct:a.ok_pct,running:(b.run||[]).length,total:(b.run||[]).length+(b.wait||[]).length+(b.idle||[]).length},
    arch:{count:(R.arch&&R.arch.count)||0,summary:R.arch&&R.arch.summary},channels:chans,background:bg};
}
