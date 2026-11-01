/* ===================== 小屏幕：内容随状态变 ===================== */
/* 屏幕坐标 (x,y,w,h) 世界单位；p 是半像素网格 */
const SCREENS={
 code(x,y,w,h,t,seed){R(x,y,w,h,"#0e1726");const lh=1.5,n=Math.floor(h/lh),off=(t*3)%1;
   for(let i=0;i<n+1;i++){const li=Math.floor(t*3)+i,yy=y+h-(i+off)*lh;if(yy<y||yy>y+h-1)continue;const hs=hash(seed+":"+li);const ind=(hs%3)*1,
     len=2+(hs>>>3)%(w-4-ind);
     R(x+1+ind,yy,len*.6,1,["#7dd3fc","#c4b5fd","#86efac","#fca5a5"][hs%4]);R(x+1.5+ind+len*.6,yy,len*.35,1,"#64748b")}
   if(Math.floor(t*2)%2)R(x+1,y+h-1.5,1,1,"#e2e8f0")},
 term(x,y,w,h,t,seed){R(x,y,w,h,"#07120b");const n=Math.floor(h/1.5);for(let i=0;i<n;i++){const li=Math.floor(t*1.6)+i-n,hs=hash(seed+"t"+li);
   const yy=y+.5+i*1.5;R(x+.5,yy,1,1,"#22c55e");R(x+2,yy,1+hs%(w-4),1,hs%7===0?"#f87171":"#4ade80")}},
 progress(x,y,w,h,t,seed){R(x,y,w,h,"#111827");const p=(t*.12+hash(seed)%10/10)%1;R(x+1.5,y+h/2-1,w-3,2,"#374151");R(x+1.5,y+h/2-1,(w-3)*p,2,PAL.run);
   for(let i=0;i<3;i++)R(x+1.5+i*2,y+1.5,1,1,Math.floor(t*4)%3===i?"#e5e7eb":"#4b5563");R(x+1.5,y+h-2.5,(w-3)*.6,1,"#6b7280")},
 snake(x,y,w,h,t,seed){R(x,y,w,h,"#0b1f0e");const cols=Math.floor(w*2)-2,rows=Math.floor(h*2)-2,len=7,st=Math.floor(t*7);
   const path=i=>{const L=2*(cols+rows)-4,k=((i%L)+L)%L;if(k<cols)return[k,0];if(k<cols+rows-1)return[cols-1,k-cols+1];
     if(k<2*cols+rows-2)return[cols-1-(k-cols-rows+2),rows-1];return[0,rows-1-(k-2*cols-rows+3)]};
   for(let i=0;i<len;i++){const [a,b]=path(st-i);R(x+.5+a*.5,y+.5+b*.5,.5,.5,i?"#4ade80":"#bbf7d0")}
   const fh=hash(seed+"f"+Math.floor(st/40));R(x+.5+(fh%(cols-4)+2)*.5,y+.5+((fh>>>4)%(rows-4)+2)*.5,.5,.5,"#f87171")},
 blocks(x,y,w,h,t,seed){R(x,y,w,h,"#140f24");const cols=Math.floor(w*2)-2,base=y+h-.5;const cs=["#f472b6","#60a5fa","#facc15","#34d399","#fb923c"];
   for(let c=0;c<cols;c++){const hgt=1+hash(seed+"c"+c)%4;for(let r=0;r<hgt;r++)R(x+.5+c*.5,base-(r+1)*.5,.5,.5,cs[(c+r)%5])}
      const fall=(t*3)%(h*2-6),
   col=hash(seed+"p"+Math.floor(t*3/(h*2-6)))%(cols-2);for(const [a,b] of [[0,0],[1,0],[1,1],[2,1]])R(x+.5+(col+a)*.5,y+.5+(Math.floor(fall)+b)*.5,.5,.5,
     "#c084fc")},
 shooter(x,y,w,h,t,seed){R(x,y,w,h,"#05050f");for(let i=0;i<6;i++){const hs=hash(seed+"s"+i);R(x+(hs%Math.floor(w*2))*.5,y+((hs>>>5)%20+t*6)%h,.5,.5,"#475569")}
   const sx=x+w/2-1+Math.sin(t*2)*(w/2-2);R(sx,y+h-1.5,2,1,"#38bdf8");R(sx+.5,y+h-2,1,.5,"#38bdf8");
   for(let i=0;i<3;i++){const ex=x+1+((hash(seed+"e"+i)%10)/10)*(w-3);R(ex,y+1+((t*2+i)%3),1.5,1,(Math.floor(t*4)+i)%2?"#f87171":"#fb923c")}
   const by=y+h-2.5-((t*14)%(h-3));R(sx+.75,by,.5,1,"#fde047")},
 video(x,y,w,h,t,seed){R(x,y,w,h,"#1e293b");R(x,y,w,h-1.5,"#7dd3fc");R(x,y+h-4,w,2.5,"#4d7c0f");const bx=x+w/2+Math.sin(t*1.3)*(w/3);
   R(bx-1,y+h-6+Math.abs(Math.sin(t*4))*-1.5,2,1.5,"#f97316");R(bx-.5,y+h-7+Math.abs(Math.sin(t*4))*-1.5,.5,.5,"#f97316");R(bx+.5,
     y+h-7+Math.abs(Math.sin(t*4))*-1.5,.5,.5,"#f97316");
   R(x,y+h-1.5,w,1.5,"#0f172a");R(x,y+h-1,w*((t*.05)%1),.5,"#e10600")},
 sleep(x,y,w,h,t,seed){R(x,y,w,h,"#0a0a12");const px=x+((t*3)%(w-2)),py=y+Math.abs(((t*2.2)%(2*(h-2)))-(h-2));R(px,py,2,1,"#334155")},
 off(x,y,w,h){R(x,y,w,h,"#1a1a22");R(x+1,y+1,1,.5,"#2a2a35")},
 wait(x,y,w,h,t){R(x,y,w,h,"#111827");const on=Math.floor(t*1.5)%2;R(x+w/2-1.5,y+h/2-1.5,3,3,on?"#f5b301":"#78350f");R(x+w/2-.5,y+h/2-.75,1,1.5,"#111827")},
 alert(x,y,w,h,t){R(x,y,w,h,Math.floor(t*3)%2?"#450a0a":"#7f1d1d");R(x+w/2-.5,y+1.5,1,h-4.5,"#fecaca");R(x+w/2-.5,y+h-2,1,1,"#fecaca")}
};
const WORK_SCENES=["code","term","progress"], PLAY_SCENES=["snake","blocks","shooter","video"];

/* ===================== 皮肤：猫猫箱（默认） / 纸箱人 ===================== */
/* 一个皮肤 = 一组画函数 + 空闲时可做的动作。行为引擎（下面）只管“去哪里、做什么”，画法全在皮肤里。 */
const CARD={main:"#b98250",dark:"#8b5a2b",in:"#4a2f18",tape:"#dcc08a",lead:"#8a5530",leadDark:"#5f3a1f",grey:"#5d5d68",greyDark:"#44444d"};
function drawFlap(x0,y0,len,dir,lift,col){for(let d=0;d<len;d++){const yy=Math.round(y0-d*lift);R(x0+dir*d-(dir<0?1:0),yy-3,1,3,d===len-1?shade(col,.15):col)}}
function drawBox(x,y,w,h,o){ // x 中心、y 底；o:{lead,off,flap(0..1),label,accent}
  const L=Math.round(x-w/2), c=o.off?{m:CARD.grey,d:CARD.greyDark}:o.lead?{m:CARD.lead,d:CARD.leadDark}:{m:CARD.main,d:CARD.dark};
  if(o.part!=="front"){ // 后壁 + 盖子
    if(o.off){R(L,y-h-2,w,2,c.d);return}
    R(L,y-h-2,w,2,CARD.in);
    const lf=o.flap??1, fl=o.lead?7:5; drawFlap(L,y-h,fl,-1,lf,shade(c.m,-.08)); drawFlap(L+w,y-h,fl,1,lf*.9,shade(c.m,-.14));
    R(L+2,y-h-3,w-4,1,shade(c.d,-.2)); return}
  R(L,y-h,w,h,c.m); R(L,y-1,w,1,c.d); R(L,y-h,w,1,shade(c.m,.18)); R(L+w-2,y-h,2,h,shade(c.m,-.1));
  if(o.off){R(L,y-h-2,w,2,c.d);R(x-2,y-h-2,4,h+1,"#9a9aa4");for(let i=0;i<h;i++){R(L+3+i*1.4,y-h+i,2,1,"#8a8a94");R(L+w-5-i*1.4,y-h+i,2,1,"#8a8a94")}return}
  R(x-2,y-h,4,Math.round(h*.45),CARD.tape);
  if(o.accent){R(L+3,y-h+3,6,5,o.accent);R(L+3,y-h+7,6,1,shade(o.accent,-.35))}
}
function drawDesk(x,y,scene,t,seed,lead){ // 小桌 + 显示器（朝外，内容可见）
  const sw=lead?22:18, sh=lead?14:12, w=sw+6;
  R(x,y-9,w,2,"#3b3b4a");R(x+1,y-7,2,7,"#2c2c38");R(x+w-3,y-7,2,7,"#2c2c38");R(x,y-9,w,1,"#4b4b5c");
  const mx=x+(w-sw)/2-1, my=y-10-sh-2;
  R(mx-1,my-1,sw+2,sh+2,"#23232c");R(mx+sw/2-1.5,y-12,3,2,"#23232c");R(mx+sw/2-3,y-10,6,1,"#2f2f3a");
  SCREENS[scene](mx,my,sw,sh,t,seed);
  if(scene!=="off"){g.globalAlpha=.10+.04*Math.sin(t*6);R(mx-3,my-2,sw+6,sh+10,scene==="alert"?"#ff4d4f":"#9bd4ff");g.globalAlpha=1}
  R(x+3,y-10,8,1,"#6b7280"); // 键盘
  return {kx:x+3,ky:y-10,mx,my,sw,sh};
}
function drawSnackBox(x,y){ /* 加班夜宵的外卖盒：像素小白盒 + 红封条 + 一双筷子，立在桌面上、不挡显示器 */
  R(x,y-4.5,3.2,4.5,"#f8fafc");R(x,y-4.5,3.2,.8,"#ffffff");R(x,y-1.2,3.2,1.2,"#cbd5e1");   /* 盒身 */
  R(x+1.2,y-4.5,.8,4.5,"#e10600");R(x+.4,y-5.2,2.4,.9,"#e10600");                     /* 红封条 + 封口 */
  R(x-.6,y-7,3,.6,"#b98250");R(x-.6,y-6,3,.6,"#b98250")                                /* 一双筷子 */
}

const SKINS={
 chibicat:{
  zoned:true,
  idleActs:[{a:"deskplay",w:3,where:"box"},{a:"sleepbox",w:2,where:"box"},{a:"teabox",w:1.2,where:"box"},{a:"wander",w:2,where:"wander"},
            {a:"phone",w:1.8,where:"rug"},{a:"tea",w:1.5,where:"tea"},{a:"stretch",w:1,where:"here"}],
  boxW:30, boxH:9,
  drawStation(st,ch,t){
    const lead=st.lead,w=lead?40:this.boxW,h=lead?11:this.boxH,off=ch.state==="off";
    const inBox=ch.inBox&&!off, ps=inBox?catPose(ch,t):null, typing=ps&&ps.p==="type";
    const flap=typing?.5+.9*Math.abs(Math.sin(t*7+st.seed)):(off?0:1);
    drawBox(st.x,st.y,w,h,{lead,off,flap});
    let spr=null;
    const fy=st.y-(lead?3:1);
    if(inBox){spr=renderCatSprite({cat:ch.cat,acc:ch.look&&ch.look.acc,lead,courier:!!ch.carry,noCrown:!!ch.fxNoCrown},ps.p,ps.f,ps.e);drawCatSprite(spr,st.x,
      fy,1,"back");ch.head=catWorld(spr,st.x,fy,1,spr.head.X,spr.head.Y)}
    drawBox(st.x,st.y,w,h,{lead,off,part:"front",accent:st.accent});
    if(inBox){
      if(typing){const kw=lead?24:20,kx=st.x-kw/2,ky=st.y-h-2.5;R(kx-.5,ky-.5,kw+1,3.5,"#3f3f46");R(kx,ky,kw,2.5,"#e4e4e7");for(let i=0;i<kw/2-1;i++)R(kx+1+i*2,
        ky+.5,1,.5,"#a1a1aa");R(kx+3,ky+1.5,kw-6,.5,"#a1a1aa")}
      drawCatSprite(spr,st.x,fy,1,"front");
      if(spr.cup){const c=catWorld(spr,st.x,fy,1,spr.cup.x,spr.cup.y);propFx(ch,c,t)}
    }
    const d=drawDesk(st.x+w/2+2,st.y,off?"off":ch.screen,t,st.seed,lead);
    if(SNACKS.has(st.id))drawSnackBox(d.mx+d.sw+1,st.y-9);   /* 加班夜宵的外卖盒：摆在桌上、显示器旁边不挡屏幕 */
    if(off&&this.zoned){const cx=d.mx-3,cy=d.my-2,cw=d.sw+6;R(cx,cy,cw,d.sh+12,"#6b6b78");R(cx,cy,cw,1.5,"#8a8a96");for(let i=2;i<cw;i+=4)R(cx+i,cy+2,1,d.sh+10,
      "#5d5d68");R(cx-1,cy+d.sh+10,cw+2,2,"#55555f")}  /* 下线：工位盖上布 */
    if(ch.cup>0&&ch.inBox&&!off&&ch.act!=="drink"&&!(lead&&ch.act==="boss_idle"&&ch.bossAnim==="tea")){const mx=st.x-w/2-7;R(mx,st.y-6,5,6,"#e5e7eb");R(mx-1,
      st.y-5,1,3,"#e5e7eb");R(mx+1,st.y-5,3,1,"#7c4a24");if((ch.cupT||0)<40)steam(mx+2.5,st.y-7,t)}   /* 有咖啡才有杯子 */
    return d;
  },
  drawOut(ch,t){
        const ps=catPose(ch,t),
    spr=renderCatSprite({cat:ch.cat,acc:ch.look&&ch.look.acc,lead:ch.st.lead,courier:!!ch.carry,noCrown:!!ch.fxNoCrown},ps.p,ps.f,ps.e),
    face=ps.p==="walk"||ch.act==="brew"?ch.face:1;
    g.globalAlpha=.28;R(Math.round(ch.x-7),Math.round(ch.y),14,1.5,"#000");g.globalAlpha=1;
    drawCatSprite(spr,ch.x,ch.y,face,"back");drawCatSprite(spr,ch.x,ch.y,face,"front");
    ch.head=catWorld(spr,ch.x,ch.y,face,spr.head.X,spr.head.Y);
    if(spr.cup){const c=catWorld(spr,ch.x,ch.y,face,spr.cup.x,spr.cup.y);propFx(ch,c,t)}
  },
  hit(ch){const lead=ch.st.lead,k=lead?1.25:1;return ch.inBox?{x:ch.st.x-(lead?22:17),y:ch.st.y-34*k,w:lead?74:58,h:34*k+2}:{x:ch.x-10,y:ch.y-30,w:20,h:31}}
 },
 boxes:{
    idleActs:[{a:"deskplay",w:3,where:"box"},{a:"sleepbox",w:2,where:"box"},{a:"wander",w:2,where:"wander"},{a:"phone",w:1.5,where:"spot"},{a:"tea",w:1.5,
      where:"tea"},{a:"roll",w:1,where:"wander"}],
  
  boxW:22, boxH:8,
  drawStation(st,ch,t){const lead=st.lead,off=ch.state==="off";
    R(st.x-8,st.y-6,16,2,"#2c2c38");R(st.x-1,st.y-4,2,4,"#2c2c38"); // 椅子
    if(off){drawBox(st.x,st.y-4,14,10,{off:true});drawBox(st.x,st.y-4,14,10,{off:true,part:"front"})}
    else if(ch.inBox){const typing=ch.act==="type";boxGuy(st.x,st.y-4,lead,ch,t,typing?"type":ch.act==="sleepbox"?"sleep":"sit");ch.head={x:st.x,
      y:st.y-4-(lead?20:14)}}
    const d=drawDesk(st.x+(lead?14:10),st.y,off?"off":ch.screen,t,st.seed,lead);
    if(SNACKS.has(st.id))drawSnackBox(d.mx+d.sw+1,st.y-9);   /* 加班夜宵的外卖盒 */
    return d},
  drawOut(ch,t){g.globalAlpha=.25;R(Math.round(ch.x-6),Math.round(ch.y),12,1,"#000");g.globalAlpha=1;
    boxGuy(ch.x,ch.y,ch.st.lead,ch,t,ch.moving?(ch.act==="roll"?"roll":"walk"):ch.act);ch.head={x:ch.x,y:ch.y-14}},
  hit(ch){return ch.inBox?{x:ch.st.x-12,y:ch.st.y-(ch.st.lead?34:24),w:46,h:26}:{x:ch.x-9,y:ch.y-16,w:18,h:18}}
 }
};
function boxGuy(x,y,lead,ch,t,pose){ // 纸箱人：方盒身体 + 点点眼 + 小短腿
  const w=lead?18:13,h=lead?15:11,c=lead?{m:CARD.lead,d:CARD.leadDark}:{m:CARD.main,d:CARD.dark};
  g.save();g.translate(Math.round(x),Math.round(y));
  if(pose==="roll"){g.rotate(Math.floor(t*6)%4*Math.PI/2*0+(t*6%(Math.PI*2)));g.translate(0,0)}
  const bob=pose==="walk"?Math.floor(t*8)%2:0, L=-w/2, T=-h-2-bob;
  if(pose==="walk"){R(-4,-2,2,2+(Math.floor(t*8)%2),c.d);R(2,-2,2,2+((Math.floor(t*8)+1)%2),c.d)}else{R(-4,-2,2,2,c.d);R(2,-2,2,2,c.d)}
  R(L,T,w,h,c.m);R(L,T,w,1,shade(c.m,.2));R(L+w-1,T,1,h,c.d);R(-1,T,2,4,CARD.tape);
  const lf=pose==="type"?.3+.4*Math.abs(Math.sin(t*7)):pose==="sleep"?0:.4;
  if(pose!=="sleep"){drawFlap(L,T,3,-1,lf*2,shade(c.m,-.1));drawFlap(L+w,T,3,1,lf*2,shade(c.m,-.15))}
  const ey=T+h/2-1;
  if(pose==="sleep"){R(L+3,ey+1,3,1,"#2b1a0e");R(L+w-6,ey+1,3,1,"#2b1a0e")}
  else{const blink=(Math.floor(t*10)%37)===0;R(L+3,ey,2,blink?1:2,"#2b1a0e");R(L+w-5,ey,2,blink?1:2,"#2b1a0e")}
  R(-1,ey+3,2,1,"#2b1a0e");
  if(lead){R(-1,T+h-5,2,1,"#e10600");R(-1.5,T+h-4,3,3,"#e10600")}
  if(ch.st.accent){R(L+1,T+h-3,3,2,ch.st.accent)}
  const arm=pose==="type"?Math.floor(t*10)%2:0;
  if(pose==="phone"){R(w/2,T+h/2,2,1,c.d);R(w/2+1,T+h/2-3,3,4,"#111827");R(w/2+1.5,T+h/2-2.5,2,2,"#93c5fd")}
  else if(pose==="tea"){R(w/2,T+h/2,2,1,c.d);R(w/2+1,T+h/2-2,3,3,"#f5f5f4")}
  else{R(L-2,T+h/2+arm,2,1,c.d);R(L+w,T+h/2+(1-arm),2,1,c.d)}
  g.restore();
}
let SKIN=SKINS[Q.get("skin")]||SKINS[{cats:"chibicat"}[Q.get("skin")]]||SKINS.chibicat;
