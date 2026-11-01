/* ===================== 演示按钮 ===================== */
function clone(o){return JSON.parse(JSON.stringify(o))}
let BASE=null,LIVE_BASE=null;   /* LIVE_BASE：live 模式的接口前缀（"" 就是同源），邀请气泡 ack 时用；没在 live 就是 null */
function workers(){return DATA.channels.filter(c=>c.role!=="lead")}
$("#b-disp").onclick=()=>{const d=clone(DATA);const ws=d.channels.filter(c=>c.role!=="lead"&&c.state!=="run"&&c.state!=="off");
  if(!ws.length)return;const c=ws.find(x=>x.state==="arch")||pick(ws);c.state="run";c.state_word=TR("demo.running");
  c.task_d=pick([TR("demo.bug"),TR("demo.test"),TR("demo.minutes"),TR("demo.analysis"),TR("demo.ppt")]);
  c.state_sub=TR("demo.justGot");c.last=TR("demo.zeroAgo");
  d.strip.running=Math.min(d.strip.total,(d.strip.running||0)+1);d.strip.calls_today=(d.strip.calls_today||0)+1;syncData(d)};
$("#b-done").onclick=()=>{const d=clone(DATA);const ws=d.channels.filter(c=>c.role!=="lead"&&c.state==="run");if(!ws.length)return;const c=pick(ws);
  c.state="idle";c.state_word=TR("demo.idle");c.state_sub=TR("demo.justReview");d.strip.running=Math.max(0,(d.strip.running||1)-1);syncData(d)};
$("#b-you").onclick=()=>{const d=clone(DATA);const l=d.channels.find(c=>c.role==="lead");if(l){l.state=l.state==="you"?"run":"you";
  l.state_word=TR(stateWord(l.state))}syncData(d)};
$("#b-off").onclick=()=>{const d=clone(DATA);const ws=d.channels.filter(c=>c.role!=="lead");const c=ws[ws.length-1];if(c){c.state=c.state==="off"?"idle":"off";
  c.state_word=TR(stateWord(c.state))}syncData(d)};
$("#s-n").onchange=e=>{const n=+e.target.value,d=clone(BASE);const ws=d.channels.filter(c=>c.role!=="lead"),names=[["D","Qwen 3.5",TR("demo.model")],["E",
  "DeepSeek V4","DeepSeek"],["F","Doubao",TR("demo.doubao")],["G","Hunyuan",TR("demo.hunyuan")],["H","Step",TR("demo.step")]];
  const st=["idle","run","idle","arch","run"];for(let i=ws.length;i<n;i++){const [id,nm,md]=names[i-3]||["X"+i,"Model "+i,"Model"];ws.push({id,
label:TR("demo.memberLabel",{id:id}),name:nm,model:md,channel:TR("demo.piScript"),route:"pi-wake",state:st[i%5],
    quota_used_pct:20+i*9,quota_left_pct:80-i*9,task_d:"—",queue:0,
    tok:null,skin:{cat:[3,4,1,5,2][i%5]}})}
  d.channels=[d.channels.find(c=>c.role==="lead"),...ws.slice(0,n)];CH={};syncData(d)};
const ss=$("#s-skin");ss.innerHTML=Object.entries(SKINS).map(([k,v])=>`<option value="${k}" ${SKINS[k]===SKIN?"selected":""}>${v.name}</option>`).join("");
ss.onchange=()=>{SKIN=SKINS[ss.value];for(const id in CH){const ch=CH[id];ch.goal=null;ch.actDur=0;if(!ch.st.lead){ch.inBox=true;ch.moving=false;ch.x=ch.st.x;
  ch.y=ch.st.y+3}}};
/* 接真核心（?live=）时「模拟派活」这排调试按钮不露，要看加 ?demo=1 */
if(Q.get("demo")==="0"||(Q.get("live")&&Q.get("demo")!=="1"))$("#demo").hidden=true;
