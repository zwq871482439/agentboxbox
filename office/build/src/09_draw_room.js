/* ===================== 画面 ===================== */
function drawRoom(t){
  // 墙
  R(0,0,WW,62,PAL.wall);for(let x=0;x<WW;x+=24)R(x,0,1,62,PAL.wallSeam);R(0,60,WW,3,PAL.skirt);R(0,63,WW,1,PAL.skirtLine);
  // 地板：工位区木地板；茶水间方砖；沙发区地毯；会议室深色地毯
  R(0,64,WW,WH-64,PAL.floor);for(let y=64;y<WH;y+=8){R(0,y,WW,.5,PAL.floorSeam);const o=(y/8%2)*18;for(let x=o;x<WW;x+=36)R(x,y,.5,8,PAL.floorSeam)}
  const Z=ZONE;
  R(Z.tea.x,Z.tea.y,Z.tea.w,Z.tea.h,PAL.tea);for(let x=Z.tea.x;x<Z.tea.x+Z.tea.w;x+=10)R(x,Z.tea.y,.5,Z.tea.h,PAL.teaSeam);for(let y=Z.tea.y;y<Z.tea.y+Z.tea.h;
    y+=10)R(Z.tea.x,y,Z.tea.w,.5,PAL.teaSeam);
  R(Z.meet.x,Z.meet.y,Z.meet.w,Z.meet.h,PAL.meet);
  // 隔断（半高矮墙 + 玻璃）
  R(Z.tea.x+Z.tea.w+2,64,2,WH-64,PAL.part);R(Z.tea.x,Z.sofa.y-3,Z.tea.w,2,PAL.part);
  R(Z.meet.x-3,64,2,Z.meet.h+2,PAL.meetWall);R(Z.meet.x-3,Z.meet.y+Z.meet.h,Z.meet.w+3,2,PAL.meetWall);
  g.globalAlpha=.07;R(Z.meet.x,64,Z.meet.w,Z.meet.h,"#93c5fd");g.globalAlpha=1;
  // v2：5 扇大落地窗 + 城市天际线（office-v2/spec.md 第 3 节）；天空 / 楼 / 楼窗 / 太阳月亮 / 光斑全按 SKY 画（时段已插值）
  {const PH=THEME.phase,W0=WIN,P=SKY;
   R(W0.x-3,W0.y-1,W0.w+6,W0.h+3,P.fr);
   for(let k=0;k<12;k++)R(W0.x,W0.y+k*W0.h/12,W0.w,W0.h/12+.5,hexLerp(P.s0,P.s1,k/11));
   const [sx,sy,sc]=P.sun;{const gr=g.createRadialGradient(sx,sy,1,sx,sy,P.sgr);gr.addColorStop(0,P.sgc);gr.addColorStop(1,P.sgc+"00");g.save();
     g.globalAlpha=P.sga;g.fillStyle=gr;g.fillRect(W0.x,W0.y,W0.w,W0.h);g.restore()}
   g.globalAlpha=.35;R(sx-5,sy-5,10,10,sc);g.globalAlpha=1;R(sx-3,sy-3,6,6,sc);
   if(PH==="night"){for(let k=0;k<26;k++){const h=hash("ns"+k);R(W0.x+h%W0.w,W0.y+1+(h>>>7)%22,.5,.5,"#cbd5e1")}R(sx-1,sy-3,3,3,P.s0)}   /* 星星 + 月亮咬口 */
   for(const [layer,col,hmin,hmax] of [[0,P.b0,12,30],[1,P.b1,18,46]]){let x=W0.x-4,k=0;
     while(x<W0.x+W0.w){const h=hash("bd"+layer+":"+k),bw=8+h%12,bh=hmin+(h>>>5)%(hmax-hmin);const top=W0.y+W0.h-bh;
       const x0=Math.max(x,W0.x),x1=Math.min(x+bw,W0.x+W0.w);if(x1>x0){R(x0,top,x1-x0,bh,col);
       if(layer===1&&(h>>>9)%4===0)R(Math.max(x0,x+bw/2-.5),top-4,1,4,col);   /* 部分楼顶有天线 */
       for(let wy=top+2;wy<W0.y+W0.h-2;wy+=3)for(let wx=x+1.5;wx<x+bw-1.5;wx+=2.5){if(wx<W0.x||wx>W0.x+W0.w-1)continue;
         const q=hash("w"+layer+k+":"+wx+":"+wy)%100;
         if(q<P.lit*100){if(!(PH==="night"&&q%7===0&&Math.floor(t*.8+q)%3===0))R(wx,wy,1,1.2,P.win)}   /* 夜里少量楼窗闪烁 */
         else if(PH!=="night"&&q<40)R(wx,wy,1,1.2,hexLerp(col,P.win,.35))}}
       x+=bw+1+(h>>>13)%3;k++}}
   if(PH==="day"){g.globalAlpha=.18;R(W0.x,W0.y+W0.h-22,W0.w,22,"#e6f3fb");g.globalAlpha=1}   /* 白天楼下薄雾 */
   for(let k=1;k<5;k++)R(W0.x+k*W0.w/5-.75,W0.y,1.5,W0.h,P.fr);R(W0.x,W0.y+W0.h*.38,W0.w,1,P.fr);   /* 5 扇窗的窗棂 + 横档 */
   // 地上的窗形光斑 + 窗棂暗条：长度 / 偏移跟太阳走（SKY.L / SKY.dx 按分钟插值）
      const y0=64,
   y1=Math.min(WH,y0+P.L);g.save();g.globalAlpha=P.pa;g.fillStyle=P.patch;g.beginPath();g.moveTo(W0.x,y0);g.lineTo(W0.x+W0.w,y0);g.lineTo(W0.x+W0.w+P.dx,y1);
     g.lineTo(W0.x+P.dx,y1);g.closePath();g.fill();
   g.globalAlpha=P.pa*.9;g.fillStyle="#000";for(let k=1;k<5;k++){const xa=W0.x+k*W0.w/5;g.beginPath();g.moveTo(xa-1,y0);g.lineTo(xa+1,y0);
     g.lineTo(xa+1+P.dx*1.02,y1);g.lineTo(xa-1+P.dx*.98,y1);g.closePath();g.fill()}
   g.restore();}
  // 挂钟（跟电脑本地时间走，每分钟跳一格）：和绿植一起居中放在大窗左侧那段空墙上
  const now=new Date(Date.now()),hh=now.getHours()%12+now.getMinutes()/60,mm=now.getMinutes();R(78,12,13,13,"#e5e7eb");R(79,13,11,11,"#f8fafc");
  const hand=(a,l,c)=>{for(let i=0;i<l;i+=.5)R(84.5+Math.sin(a)*i-.25,18.5-Math.cos(a)*i-.25,.5,.5,c)};hand(hh/12*Math.PI*2,3,"#111827");hand(mm/60*Math.PI*2,
    4.4,"#e10600");
  // 立式白板（TeamLeader 待办，首领工位右边，带支架；影子在 drawShadows 里画）
  const B=TODO_BOARD;R(B.x+5,B.y+B.h,1.5,15,"#57534e");R(B.x+B.w-6.5,B.y+B.h,1.5,15,"#57534e");R(B.x+B.w/2-.75,B.y+B.h,1.5,12,"#44403c");R(B.x+3,B.y+B.h+14,
    B.w-6,1,"#44403c");
  R(B.x,B.y,B.w,B.h,"#3a3b48");R(B.x+1.5,B.y+1.5,B.w-3,B.h-3,"#e8eaee");R(B.x+3,B.y+B.h-2,B.w-6,1,"#94a3b8");
  const n=(DATA&&DATA.arch&&DATA.arch.count)||0, cols=["#fde047","#f9a8d4","#86efac","#93c5fd"];
  for(let i=0;i<Math.min(n,8);i++){const x=B.x+4+(i%4)*9,y=B.y+10+Math.floor(i/4)*9;R(x,y,7,7,cols[i%4]);R(x,y,7,.8,shade(cols[i%4],-.15));R(x+1.2,y+2.5,4.5,.5,
    "#57534e");R(x+1.2,y+4.3,3,.5,"#57534e")}   /* 一条待办一张便利贴，两排最多 8 张 */
  // 霓虹牌
  g.globalAlpha=.18+.04*Math.sin(t*2);R(380,11,88,17,"#e10600");g.globalAlpha=1;R(382,13,84,13,"#1a0b0d");
  drawThemeSwitch();   // 昼夜开关（霓虹牌正下方）
  drawDockBtns();      // 动态 / 用量（挂钟右边，只在嵌进首页时画）
  // 绿植（v2：右边那盆去掉，左边这盆挪到挂钟旁边）
  for(const px of [56]){R(px,48,9,12,"#7c4a24");R(px-1,47,11,2,"#92582c");for(let i=0;i<7;i++){const a=-1.3+i*.45;R(px+4.5+Math.cos(a)*7-1,
    44-Math.abs(Math.sin(a))*8+Math.sin(t+i)*.5,3,2,i%2?"#16a34a":"#22c55e")}}
  // ② 茶水间：吧台 + 咖啡机 + 小冰箱
  R(8,112,96,4,"#6b4423");R(8,116,96,10,"#4a2f18");R(8,112,96,1,"#8a5a30");
  R(18,96,16,16,"#3f3f46");R(19,97,14,6,"#27272a");R(23,104,6,3,"#18181b");R(30,99,2,2,Math.floor(t*2)%2?PAL.run:"#14532d");   /* 空闲：出水口下没有杯子、不冒汽 */
  R(42,106,6,6,"#e7e5e4");R(43,106,4,1,"#d6d3d1");R(50,107,5,5,"#fda4af");  // 备用空杯
  R(70,76,24,36,"#cbd5e1");R(70,76,24,1,"#e2e8f0");R(70,92,24,1,"#94a3b8");R(90,80,1.5,9,"#64748b");R(90,95,1.5,12,"#64748b");
  R(73,79,6,3,"#fca5a5");R(80,80,4,2,"#86efac");  // 冰箱贴
  // ③ 沙发区：地毯 + 沙发 + 茶几 + 猫爬架
  R(10,196,92,58,PAL.rugEdge);R(12,198,88,54,PAL.rug);for(let i=0;i<88;i+=6)R(12+i,198,3,54,PAL.rugStripe);
  R(16,200,78,6,"#7a3b3b");R(16,206,78,10,"#a35656");R(14,202,4,14,"#7a3b3b");R(92,202,4,14,"#7a3b3b");R(18,207,36,1,"#8f4848");R(56,207,36,1,"#8f4848");
  R(36,232,36,3,"#6b4423");R(38,235,2,8,"#4a2f18");R(68,235,2,8,"#4a2f18");R(48,228,5,4,"#e7e5e4");
  R(84,170,14,3,"#d6b38a");R(89,173,4,24,"#a8a29e");R(82,184,18,3,"#d6b38a");R(86,194,12,4,"#d6b38a");
  R(97,246,4,6,"#c81e1e");R(96,247,6,4,"#c81e1e");R(97,247,2,1,"#f87171");  // 毛线球
  // ④ 会议室：投影幕布（吊顶卷轴，开会才放下）+ 大会议桌 + 5 把椅子
  {const on=meetReady()||!!SCENE||partyScreenOn(),P=THEME.phase;PROJ.k+=((on?1:0)-PROJ.k)*.08;const k=PROJ.k,dn=Math.round(30*k);   /* 开会 / 演会议室场景：幕布放下 */
   R(384,66,76,4,"#3a3b48");R(385,67,74,1,"#565868");R(383,66,2,4,"#2a2b36");R(459,66,2,4,"#2a2b36");   // 卷轴盒
   if(dn>0){R(388,70,68,dn,on||k>.5?"#f4f6fb":"#e8eaee");R(388,70,1,dn,"#cbd2dc");R(455,70,1,dn,"#cbd2dc");R(387,70+dn,70,2,"#3a3b48");R(420,72+dn,4,1.5,
     "#3a3b48")}
   else{R(420,70,4,2,"#3a3b48")} // 拉绳
   if(k>.95){const lit=.6+.4*Math.min(1,(T-PROJ.t0)/0.6);g.save();g.globalAlpha=lit;   /* 画面 0.6 秒淡入，只有抽象图形不写字 */
     if(!partyScreenDraw(t)){   /* –庆祝 / 复盘的画面先画；不是就走看电影 / 打比赛 / 开会 */
     if(SCENE&&(SCENE.name==="movie"||SCENE.name==="game")){ // 放电影 / 打比赛各有各的画面（/ ）
       if(SCENE.name==="movie")movieScreen(t);else gameScreen(t)}
     else{   /* 开会 / 站会：站会用 派活会同款三列看板（MEET 不在时 why 落到「派活」） */
       R(390,72,64,26,P==="night"?"#eaf2ff":"#ffffff");R(390,72,64,5,"#2563eb");R(392,73.5,24,1.5,"#dbeafe"); // 标题条
       const why=(MEET&&MEET.why)||"assign";
     if(why==="review"){ // 验收：通过率柱状图 + 勾
       [[10,"#22c55e"],[14,"#22c55e"],[8,"#f59e0b"],[16,"#22c55e"],[5,"#ef4444"]].forEach(([h,c],i)=>R(395+i*7,96-h,5,h,c));R(394,96,36,1,"#64748b");
       R(436,82,14,10,"#dcfce7");R(439,87,2,2,"#16a34a");R(441,89,2,2,"#16a34a");R(443,87,2,2,"#16a34a");R(445,85,2,2,"#16a34a")}
     else{ // 派活 / 站会：三列任务看板
       ["#fde68a","#bfdbfe","#bbf7d0"].forEach((c,i)=>{R(394+i*20,80,17,2,"#94a3b8");for(let j=0;j<(3-i);j++)R(394+i*20,84+j*5,17,4,c)})}}
     }
     g.restore()}}
  R(392,122,60,60,"#6b4423");R(392,122,60,2,"#8a5a30");R(394,126,56,52,"#7a4e28");R(392,180,60,2,"#4a2f18"); // 大会议桌
  R(394,184,2,6,"#4a2f18");R(448,184,2,6,"#4a2f18");
  for(const [cx,cy] of MEET_SEATS)R(cx-3,cy-4,6,4,"#2c2c38");R(MEET_HEAD[0]-3,MEET_HEAD[1]-4,6,4,"#2c2c38");   // 椅子
  for(const [x,y] of [[404,134],[436,134],[404,164],[436,164]]){R(x-4,y,8,6,"#f8fafc");R(x-3,y+1,6,1,"#94a3b8")}  // 桌上的本子
  R(420,148,4,3,"#1f2937"); // 桌中间的投影遥控
  drawArcade(t); // 聚会街机：投影机旁的桌角上，点它弹聚会菜单（画在桌上、猫的后面）
  const brewer=Object.values(CH).find(c=>c.act==="brew"&&!c.moving);
  if(brewer){const k=clamp(brewer.actT/BREW_S,0,1),fill=Math.round(k*3);R(24,107,4,4,"#f8fafc");if(fill)R(24,111-fill,4,fill,"#7c4a24");R(25,103,2,1+(t*4%4),
    "#7c4a24");g.globalAlpha=.25+.2*Math.sin(t*10);R(19,97,14,6,"#fde68a");g.globalAlpha=1;R(30,99,2,2,Math.floor(t*6)%2?"#facc15":PAL.run);steam(26,104,t*1.8)}
  if(Object.values(CH).some(c=>c.act==="fridgeopen"&&!c.moving)){R(70,76,24,36,"#f1f5f9");R(71,77,22,34,"#fefce8");R(71,88,22,1,"#cbd5e1");R(71,99,22,1,
"#cbd5e1");R(73,82,5,5,"#fca5a5");R(80,83,5,4,"#86efac");R(86,81,5,6,"#93c5fd");R(73,93,7,4,"#fde68a");R(82,92,8,5,"#f8fafc");R(73,103,6,5,"#fdba74");R(94,
    76,7,36,"#cbd5e1");R(95,77,5,34,"#e2e8f0");R(96,92,1.5,8,"#64748b")}
  if(cardsOn()){for(let i=0;i<5;i++)R(410+i*5,160+(i%2),3.5,5,i%2?"#f8fafc":"#fee2e2");R(418,158,3,4,"#ef4444")}
  if(SCENE&&SCENE.name==="wrapup"){g.globalAlpha=.24;R(Z.meet.x,64,Z.meet.w,Z.meet.h,"#0b1020");g.globalAlpha=1}   /* 收工庆祝：会议室灯微暗（比看电影浅） */
  if(meetReady()){g.globalAlpha=.10+.05*Math.sin(t*4);R(Z.meet.x,64,Z.meet.w,Z.meet.h,"#fde68a");g.globalAlpha=1}
}
/* ===== v2：影子 + 光效（office-v2/spec.md 第 4、5 节；纸箱人皮肤不画光影） ===== */
function castShadow(x0,x1,y,h){const P=THEME.phase,v=SKY;g.save();g.globalAlpha=v.sa;g.fillStyle=v.sc;   /* 影子长度 = 物体高度 × 时段系数，方向跟太阳走 */
  if(P==="day"){g.beginPath();g.ellipse((x0+x1)/2+v.vx*h,y+1,(x1-x0)/2+1,2.2+v.vy*h*.3,0,0,Math.PI*2);g.fill()}   /* 白天：物体脚下一小圈 */
  else{const dx=v.vx*h,dy=v.vy*h;g.beginPath();g.moveTo(x0,y);g.lineTo(x1,y);g.lineTo(x1+dx,y+dy);g.lineTo(x0+dx,y+dy);g.closePath();g.fill()}
  /* 黎明往右拉 / 黄昏往左拉 */
  g.restore()}
function seatedAt(st){const ch=CH[st.id];return ch&&ch.inBox&&ch.state!=="off"&&!ch.spawnHide}
function drawShadows(t){const P=THEME.phase;
  if(P==="night"){ // 夜里只有台灯下一圈软影，只给有猫坐着的工位；走动的猫脚下一点
    for(const st of STATIONS){if(!seatedAt(st))continue;const w=st.lead?40:26;g.save();g.globalAlpha=.22;g.fillStyle="#000";g.beginPath();g.ellipse(st.x,st.y+3,
      w/2+3,4,0,0,Math.PI*2);g.fill();g.restore()}
    for(const id in CH){const ch=CH[id];if(!ch.inBox&&ch.state!=="off")castShadow(ch.x-5,ch.x+5,ch.y,8)}return}
  for(const st of STATIONS){const w=st.lead?40:26;castShadow(st.x-w/2,st.x+w/2+28,st.y,st.lead?24:20)}   /* 工位（纸箱 + 桌子） */
  for(const id in CH){const ch=CH[id];if(!ch.inBox&&ch.state!=="off")castShadow(ch.x-5,ch.x+5,ch.y,20)}   /* 在外面走动的猫 */
  const B=TODO_BOARD;castShadow(B.x+2,B.x+B.w-2,B.y+B.h+15,30);   /* 立式白板 */
  castShadow(16,96,216,14);castShadow(8,104,126,12);castShadow(36,72,248,6);castShadow(424,448,252,14);   /* 沙发 / 吧台 / 茶几 / 打印机 */
}
function drawLightFx(t){const P=THEME.phase;
  if(P==="day"||P==="dawn"){ // 白天 / 黎明：三道淡光束 + 光束里慢慢飘的尘埃
    const day=P==="day";g.save();g.globalAlpha=day?.07:.06;g.fillStyle=day?"#fff7d0":"#ffd6dd";const dx=SKY.dx;
    for(let k=0;k<3;k++){const x=180+k*55;g.beginPath();g.moveTo(x,60);g.lineTo(x+14,60);g.lineTo(x+14+dx*.9,64+(day?60:150));g.lineTo(x+dx*.9,64+(day?60:150));
      g.closePath();g.fill()}
    g.globalAlpha=.55;for(let k=0;k<28;k++){const h=hash("dust"+k),u=((h%1000)/1000+t*.03)%1,yy=64+((h>>>10)%(day?50:140)),
      xx=150+(h>>>3)%190+dx*(yy-64)/(day?60:150)+Math.sin(t*.7+k)*2;
      R(xx,yy-u*6,.5,.5,day?"#fffbe6":"#ffe4ea")}g.restore()}
  if(P==="dusk"){const gr=g.createRadialGradient(330,60,4,330,60,220);gr.addColorStop(0,"#ff9a52");gr.addColorStop(1,"#ff9a5200");g.save();g.globalAlpha=.16;
    g.fillStyle=gr;g.fillRect(0,0,WW,WH);g.restore()}   /* 黄昏：从窗右上角铺开的一层暖橙光 */
}
function drawProjector(t){const on=meetReady()||!!SCENE||partyScreenOn(),P=THEME.phase;if(on&&!PROJ.was)PROJ.t0=T;PROJ.was=on;   /* 开会 / 演会议室场景：投影开机 */
  R(421,103,2,5,"#3a3b48");R(417,102,10,1,"#3a3b48");R(414,108,16,7,"#4b5563");R(414,108,16,1,"#6b7280");R(415,114,14,1,"#374151");   // 吊杆 + 机身
  R(419,106,6,2,"#1f2937");R(426,110,2,2,on?(Math.floor(t*2)%2?"#22c55e":"#16a34a"):"#ef4444");   // 镜头 + 指示灯：待机红，开会绿灯闪
  if(PROJ.k>.95){const fl=.9+.1*Math.sin(t*13);g.save();
    const gr=g.createLinearGradient(0,108,0,72);const c=P==="night"?"#bfdbfe":"#fffbe6";gr.addColorStop(0,c+"cc");gr.addColorStop(1,c+"22");
    g.globalAlpha=(P==="night"?.32:.24)*fl;g.fillStyle=gr;g.beginPath();g.moveTo(420,108);g.lineTo(424,108);g.lineTo(454,98);g.lineTo(390,98);g.closePath();
      g.fill();
      // 光锥
    if(P==="night"){g.globalAlpha=.10;g.fillStyle="#93c5fd";g.fillRect(372,64,104,50)}   // 夜里幕布反光照亮会议室上半
    g.globalAlpha=.6;for(let k=0;k<8;k++){const h=hash("pd"+k),u=((h%1000)/1000+t*.05)%1,xx=392+(h>>>3)%60,yy=100+((h>>>8)%8)-u*2;R(xx,yy-(h>>>12)%20*u,.5,.5,
      "#ffffff")}
      // 光锥里的浮尘
    g.restore()}}
/* ；
   上岗流程进行中（收到过 bx-anim、feed 里还没出现第一只坐下的打工猫）虚线框用橙色，平时灰色 */
let ONBOARD=false,EMPTY_DRAWN={},WHO_DRAWN={};
function emptySlotCol(){return ONBOARD?"#e07020":PAL.name}
function drawEmptySlot(s){const [x,y]=SLOT_POS[s];g.save();g.globalAlpha=.30;   /* 空位：淡虚线框 */
  const col=emptySlotCol(),x0=x-15,y0=y-11,w=30,h=12;
  for(let i=0;i<w;i+=5){R(x0+i,y0,3,.8,col);R(x0+i,y0+h,3,.8,col)}
  for(let j=0;j<h;j+=5){R(x0,y0+j,.8,3,col);R(x0+w,y0+j,.8,3,col)}
  const gl=SLOT_LETTER[s];
  if(gl)for(let j=0;j<5;j++)for(let i=0;i<3;i++)if(gl[j][i]==="1")R(x0+2.5+i,y0+2.5+j,.9,.9,col);
  EMPTY_DRAWN[s]={col,letter:!!gl};
  g.restore()}
function lampOn(st){const ch=CH[st.id];return !!(ch&&ch.state!=="off"&&ch.inBox&&!ch.spawnHide)}   /* 台灯只亮有猫坐着的工位（设计稿第二版）：串门 / 茶水间 / 开会去了就灭，回来再亮 */
function drawLight(t){ /* 台灯光晕：只在夜晚（PAL.lampA），只亮有猫坐着的工位，渐亮 / 渐灭 */
  if(PAL.lampA>0){g.save();for(const st of STATIONS){st.lampK=(st.lampK||0)+((lampOn(st)?1:0)-(st.lampK||0))*.12;if(st.lampK<.02)continue;
    const cx=st.x+(st.lead?16:12),cy=st.y-6;   /* 渐亮 / 渐灭，不硬切 */
    const grd=g.createRadialGradient(cx,cy,3,cx,cy,st.lead?38:30);grd.addColorStop(0,
      "rgba(255,208,120,"+(PAL.lampA*st.lampK*(1+.08*Math.sin(t*3+st.seed))).toFixed(3)+")");grd.addColorStop(1,"rgba(255,208,120,0)");
    g.fillStyle=grd;g.fillRect(cx-40,cy-40,80,80)}g.restore()}
}
function drawPrinter(t){
  const b=BGT[0];if(!b)return;const run=b.state==="run",x=PRINTER.x,y=PRINTER.y;
  R(x-12,y-14,24,14,"#4b5563");R(x-12,y-14,24,1,"#6b7280");R(x-10,y-11,20,3,"#1f2937");R(x-12,y-1,24,1,"#374151");
  R(x-9,y-6,3,2,run?(Math.floor(t*4)%2?PAL.run:"#14532d"):"#374151");R(x-5,y-6,3,2,"#1f2937");
  if(run){const p=(t*.6)%1;R(x-6,y-11-p*5,12,p*5,"#f8fafc");for(let i=0;i<p*4;i++)R(x-4,y-15-i*1.2+1,7,.5,"#94a3b8")}
}
function drawHP(ch){
  const d=ch.data,lead=ch.st.lead;if(!ch.head||ch.spawnHide)return;let x=Math.round(ch.head.x-(lead?14:11)),y=Math.round(ch.head.y-4);
  if(ch.state==="off"){x=ch.st.x-11;y=ch.st.y-(lead?24:20)}
  const w=lead?28:22,left=d.quota_left_pct;if(d.quota_mode==="off"){ch.hp=null;return}ch.hp={x,y,w};
  R(x-1,y-1,w+2,4,"#0b0b10");
  if(ch.state==="off"){g.globalAlpha=.35;if(left!=null)R(x,y,Math.round(w*left/100),2,"#6b7280");g.globalAlpha=1;return} /* ：停用工位血条变灰，旁边写「已停用」 */
  if(left==null){for(let i=0;i<w;i+=3)R(x+i,y,2,2,"#4b4b57");return}
  const fw=Math.max(left>0?1:0,Math.round(w*left/100)),col=left<10?"#e10600":left<30?"#f5b301":CARD.tape;
  R(x,y,fw,2,col);for(let i=1;i<fw;i+=3)R(x+i,y,1,2,shade(col,-.12));R(x,y,fw,.5,shade(col,.35));
  if(left<10&&Math.floor(T*2.5)%2){g.globalAlpha=.35;R(x-1,y-1,w+2,4,"#e10600");g.globalAlpha=1}
}
function drawEnvelopes(dt){
  for(const e of ENVS){e.t+=dt;const p=clamp(e.t/e.dur,0,1),ease=p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2;
    const x=e.from.x+(e.to.x-e.from.x)*ease,y=e.from.y+(e.to.y-e.from.y)*ease-Math.sin(p*Math.PI)*e.arc;
    for(let i=1;i<5;i++){const q=Math.max(0,p-i*.04),eq=q<.5?2*q*q:1-Math.pow(-2*q+2,2)/2;g.globalAlpha=.5-i*.1;R(e.from.x+(e.to.x-e.from.x)*eq-.5,
      e.from.y+(e.to.y-e.from.y)*eq-Math.sin(q*Math.PI)*e.arc-.5,1,1,"#fde68a")}
    g.globalAlpha=1;const wob=Math.round(Math.sin(e.t*14));
    const ey=y+wob*.5;R(x-5.5,ey-4.5,11,8,"#0b0b10");R(x-5,ey-4,10,7,"#f8fafc");for(let i=0;i<5;i++){R(x-5+i,ey-4+i*.7,1,1,"#cbd5e1");R(x+4-i,ey-4+i*.7,1,1,
      "#cbd5e1")}R(x-1,ey-.5,2,2,"#e10600");
    if(p>=1&&!e.done){e.done=true;const ch=e.ch;if(!e.mail){ch.state=ch.shown=ch.pending;ch.pending=null;ch.goal=null}ch.meowT=1.1;PUFFS.push({x:e.to.x,
      y:e.to.y,t:0,star:true})}}  /* 丢信（mail）只冒星星 + 欢呼，不改状态 */
  ENVS=ENVS.filter(e=>!e.done);
}
function drawPuffs(dt){for(const p of PUFFS){p.t+=dt;const r=p.t*14;g.globalAlpha=Math.max(0,.7-p.t*1.6);
  for(let i=0;i<6;i++){const a=i/6*Math.PI*2;R(p.x+Math.cos(a)*r-.5,p.y+Math.sin(a)*r*.6-.5,p.star?1:1.5,p.star?1:1.5,
    p.star?"#fde68a":"#e7e5e4")}g.globalAlpha=1}
  PUFFS=PUFFS.filter(p=>p.t<.5)}

/* 高清层：文字 / 气泡 */
function W2(x){return x*S}
function txt(s,x,y,o={}){hi.font=`${o.b?"700 ":""}${(o.sz||4.2)*S}px "Microsoft YaHei","PingFang SC","Noto Sans CJK SC","Noto Serif CJK SC",sans-serif`;
  hi.textAlign=o.al||"center";hi.textBaseline="alphabetic";
  if(o.bg){const w=hi.measureText(s).width,pad=S*1.4,x0=o.al==="left"?W2(x)-pad:W2(x)-w/2-pad;hi.fillStyle=o.bg;rr(x0,W2(y)-(o.sz||4.2)*S-pad*.4,w+pad*2,
    (o.sz||4.2)*S+pad*1.4,S*1.6);hi.fill();if(o.bd){hi.strokeStyle=o.bd;hi.lineWidth=Math.max(1,S*.35);hi.stroke()}}
  hi.fillStyle=o.c||PAL.txt;hi.fillText(s,W2(x),W2(y))}
function rr(x,y,w,h,r){hi.beginPath();hi.moveTo(x+r,y);hi.arcTo(x+w,y,x+w,y+h,r);hi.arcTo(x+w,y+h,x,y+h,r);hi.arcTo(x,y+h,x,y,r);hi.arcTo(x,y,x+w,y,r);
  hi.closePath()}
function bubble(ch,s,col,t){const h=ch.head||{x:ch.x,y:ch.y-24};const bx=h.x+(ch.st.lead?19:15),by=h.y+3-Math.abs(Math.sin(t*3))*1.2;
  hi.fillStyle=col;rr(W2(bx-4),W2(by-6.5),W2(8),W2(8),S*2.2);hi.fill();hi.beginPath();hi.moveTo(W2(bx-3),W2(by+1));hi.lineTo(W2(bx-5),W2(by+3.5));
    hi.lineTo(W2(bx),W2(by+1));hi.fill();
  txt(s,bx,by-0.2,{sz:6,b:1,c:col==="#f8fafc"?"#111827":"#fff"})}
/** TeamLeader「需要用户决策」：夸张大红 !（约 2.5×）+ 弹跳/呼吸；普通 bubble 留给 ? / × */
function youBang(ch,t){
  const h=ch.head||{x:ch.x,y:ch.y-24};
  const bounce=Math.abs(Math.sin(t*5))*3.2;          // 更明显上下弹
  const pulse=1+0.12*Math.sin(t*7);                  // 轻微呼吸放大
  const side=ch.st&&ch.st.lead?22:16;
  const bx=h.x+side, by=h.y-2-bounce;
  const half=10*pulse;                               // 原 bubble 半宽 4 → ~10（≈2.5×）
  hi.save();
  hi.shadowColor="#e10600";hi.shadowBlur=S*5*pulse;
  hi.fillStyle="#e10600";
  rr(W2(bx-half),W2(by-half*1.55),W2(half*2),W2(half*2),S*3.2*pulse);hi.fill();
  hi.beginPath();
  hi.moveTo(W2(bx-half*0.55),W2(by+half*0.85));
  hi.lineTo(W2(bx-half*1.05),W2(by+half*1.55));
  hi.lineTo(W2(bx+half*0.15),W2(by+half*0.85));
  hi.fill();
  hi.restore();
  txt("!",bx,by+half*0.15,{sz:14*pulse,b:1,c:"#fff"});
}
