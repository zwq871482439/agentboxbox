/* ===================== 原创 Q 版猫猫（程序绘制的像素画，没有外部素材） =====================
   设计坐标：32×32 网格，脚底在 y=32，身体中线 x=16。首领（lead）用 k=1.25 放大到 40×40 网格。
   每个精灵分两层：back（身体 + 头）和 front（爪子 / 道具，要盖在箱沿上的部分）。
   #79 配饰系统：配饰按槽位挂（head / face / neck / ears / body），每个槽位最多一件，同槽位互斥；
   王冠只给首领（lead=true 时头部槽位换成王冠，原头部配饰摘掉，其它槽位保留）；
   送货时（courier=true）快递帽盖住头部槽位（含王冠），送完恢复；
   #65 上岗动画：noCrown=true 把王冠暂时摘掉（戴王冠动画落下前先不戴），不影响其它槽位；
   花色（三花的斑块、暹罗的重点色、虎斑的条纹）是猫本身的毛色，不再和任何配饰绑在一起。 */
const SLOTS={head:["crown","cap","beanie","flower","bow"],face:["glasses","sunglasses"],neck:["scarf","bell","tie","bandana"],ears:["phones"],body:["hoodie"]};
const ACC_SLOT={};for(const _s in SLOTS)for(const _a of SLOTS[_s])ACC_SLOT[_a]=_s;
const CATS={
 1:{name:"橘猫",fur:"#f7a248",shade:"#df7f2c",light:"#ffe4bf",ear:"#ffb3c1",iris:"#5b3a1e",line:"#7a3f12",stripes:"#d9722a",acc:{}},
 2:{name:"白猫",fur:"#f8f5f1",shade:"#ddd6cf",light:"#ffffff",ear:"#ffb8c8",iris:"#3b82f6",line:"#6b5e57",acc:{ears:"phones"}},
 3:{name:"灰猫",fur:"#a9aebb",shade:"#8a8f9c",light:"#dfe2e8",ear:"#f5b5c4",iris:"#16a34a",line:"#4b4f5a",stripes:"#7c818e",cheek:1,acc:{face:"glasses"}},
 4:{name:"黑猫",fur:"#3b3747",shade:"#2c2937",light:"#4d4860",ear:"#f2a7bb",iris:"#facc15",line:"#0e0c14",rim:"#5f5978",glow:"#6e6890",acc:{body:"hoodie"}},
 5:{name:"三花",fur:"#fbf6ee",shade:"#e6ddd0",light:"#ffffff",ear:"#ffb3c1",iris:"#b45309",line:"#6b5848",patchA:"#f39a45",patchB:"#3d3542",acc:{head:"bow"}},
 6:{name:"暹罗",fur:"#f2e6d2",shade:"#dccbb0",light:"#fbf4e8",ear:"#d9a3a3",iris:"#38bdf8",line:"#5a4032",point:"#6e4b3a",acc:{neck:"scarf"}},
 7:{name:"虎斑（棕）",fur:"#b98559",shade:"#9a6a43",light:"#f3dcc0",ear:"#f2a7a0",iris:"#65a30d",line:"#4a2e1a",stripes:"#7d5233",cheek:1,acc:{}},
 8:{name:"奶牛猫（黑白）",fur:"#33303b",shade:"#26232d",light:"#fbfaf7",ear:"#f2a7bb",iris:"#22c55e",line:"#0e0c14",rim:"#57536a",acc:{}}
};
const POSES={ // 每个姿势的帧数和帧率
 sit:[1,1],type:[2,8],tea:[2,.7],phone:[2,2],game:[2,5],nap:[2,1],walk:[4,7],stretch:[3,2.5],wait:[1,1],you:[2,3],fail:[2,3],yay:[2,6]};
const SPRITE_CACHE=new Map();
function hexRGB(h){const n=parseInt(h.slice(1),16);return[n>>16,(n>>8)&255,n&255]}
function mixHex(a,b,t){const A=hexRGB(a),B=hexRGB(b);return "#"+A.map((v,i)=>Math.round(v+(B[i]-v)*t).toString(16).padStart(2,"0")).join("")}
/* 姿势参数（设计坐标） */
function poseParams(pose,f,lead){
 const P={hdy:0,rot:0,bdy:0,eyes:"open",mouth:"w",paws:[[13,26],[19,26]],feet:[[12.5,30.6],[19.5,30.6]],prop:null,tail:0,lines:null,lit:false,sweat:false,armsFront:true};
 switch(pose){
  case"sit":P.paws=[[13.2,25.5],[18.8,25.5]];break;
  case"type":P.hdy=1;P.eyes="focus";P.mouth="flat";P.paws=f?[[12.2,22.6],[19.8,21.4]]:[[12.2,21.4],[19.8,22.6]];P.lines=f?"r":"l";break;
  case"tea":P.paws=f?[[14,18.6],[18,18.6]]:[[14,21],[18,21]];P.prop=f?"cup-up":"cup";P.eyes=f?"happy":"open";P.mouth=f?"none":"w";break;
  case"phone":P.hdy=.6;P.paws=[[13.6,21.8],[18.4,21.8]];P.prop="phone";P.eyes=f?"happy":"down";P.lit=true;break;
  case"game":P.paws=[[12.4,22],[19.6,22]];P.prop="pad";P.eyes="focus";P.mouth=f?"o":"flat";break;
  case"nap":P.hdy=4.2;P.rot=.14;P.eyes="sleep";P.mouth="tiny";P.paws=[[12.8,24.2],[19.4,24.4]];P.prop="chin";break;
  case"walk":{const s=[0,1,0,-1][f];P.bdy=Math.abs(s)?-.6:0;P.hdy=P.bdy;P.rot=s*.06;P.paws=[[11.6,24.5+s],[20.4,24.5-s]];P.feet=[[12.5,30.6-(s>0?1:0)],[19.5,30.6-(s<0?1:0)]];P.tail=s;P.armsFront=false;break}
  case"stretch":P.eyes=f===1?"squeeze":"happy";P.mouth=f===1?"yawn":"w";P.paws=f===1?[[7.6,2.6],[24.4,2.6]]:[[6.6,7],[25.4,7]];P.hdy=f===1?.6:0;break;
  case"wait":P.rot=.24;P.paws=[[13.2,25.5],[21.6,21.4]];P.mouth="o";break;
  case"you":P.eyes="wide";P.mouth="open";P.paws=[[13.2,25.5],[26,f?4.6:6.4]];P.tail=f?1:-1;break;
  case"fail":P.eyes="worried";P.mouth="wavy";P.sweat=true;P.paws=[[13.2,25.5],[18.8,25.5]];P.hdy=f?.5:0;break;
  case"yay":P.eyes="happy";P.mouth="open";P.paws=f?[[6.2,5.4],[25.8,5.4]]:[[6.6,8],[25.4,8]];break;
 }
 return P;
}
/* 整理一只猫的装扮（spec={cat,acc,lead,courier}；acc 可以是 {槽位:配饰}、一串配饰名或单个名字，缺省用这只猫的默认配饰）：
   不认识的槽位 / 配饰丢掉，同槽位只留一件（先来先得）；
   首领头部强制王冠（原头部配饰摘掉，其它槽位保留），不是首领就没有王冠；送货时快递帽盖住头部槽位（含王冠）。 */
function catLook(cat,spec){
 const C=CATS[cat]||CATS[2],src=spec?spec.acc:undefined,acc={};
 const put=a=>{const s=ACC_SLOT[a];if(s&&!acc[s])acc[s]=a};
 if(src==null)Object.values(C.acc||{}).forEach(put);
 else if(typeof src==="string")put(src);
 else if(Array.isArray(src))src.forEach(put);
 else if(typeof src==="object")for(const s in SLOTS)put(src[s]);
 if(spec&&spec.lead)acc.head="crown";else if(acc.head==="crown")delete acc.head;
 if(spec&&spec.courier)acc.head="cap";
 if(spec&&spec.noCrown&&acc.head==="crown")delete acc.head;
 return acc;
}
function renderCatSprite(spec,pose,f,expr){
 if(typeof spec==="number")spec={cat:spec,lead:spec===1};   // 旧调用只给编号：1 号橘猫按首领画（王冠 + 胸前红徽章 + 大一号）
 spec=spec||{};
 const C=CATS[spec.cat]||CATS[2],lead=!!spec.lead,k=lead?1.25:1,N=lead?40:32;
 const acc=catLook(spec.cat,spec),HAS=a=>acc[ACC_SLOT[a]]===a;
 const key=JSON.stringify([spec.cat,acc,lead,!!spec.courier,pose,f,expr||""]);if(SPRITE_CACHE.has(key))return SPRITE_CACHE.get(key);
 const P=poseParams(pose,f,lead);if(expr==="joy"){P.eyes="happy";P.mouth="open"}if(expr==="focus"){P.eyes="focus"}
 const back=new Array(N*N).fill(null),front=new Array(N*N).fill(null);
 const HC={x:16,y:12.6+P.hdy},NECK={x:16,y:20+P.hdy},rot=P.rot,cs=Math.cos(rot),sn=Math.sin(rot);
 const toLocal=(X,Y)=>{const dx=X-NECK.x,dy=Y-NECK.y;return{u:dx*cs+dy*sn+NECK.x-HC.x,v:-dx*sn+dy*cs+NECK.y-HC.y}};
 const toDesign=(u,v)=>{const x=u+HC.x-NECK.x,y=v+HC.y-NECK.y;return{X:x*cs-y*sn+NECK.x,Y:x*sn+y*cs+NECK.y}};
 const cellOf=(X,Y)=>[Math.floor((X-16)*k+N/2),Math.floor((Y-32)*k+N)];
 function paint(L,fn){for(let y=0;y<N;y++)for(let x=0;x<N;x++){const X=(x+.5-N/2)/k+16,Y=(y+.5-N)/k+32;const c=fn(X,Y);if(c)L[y*N+x]=c}}
 function paintHead(L,fn){paint(L,(X,Y)=>{const q=toLocal(X,Y);return fn(q.u,q.v,X,Y)})}
 function stamp(L,rows,u0,v0,pal,mirror){rows.forEach((r,j)=>{[...r].forEach((ch,i)=>{if(ch==="."||ch===" ")return;const uu=mirror?u0-i-.5:u0+i+.5;const d=toDesign(uu,v0+j+.5);const [cx,cy]=cellOf(d.X,d.Y);
   const reps=k>1?[[0,0],[1,0],[0,1],[1,1]].filter(([a,b])=>((d.X-16)*k+N/2+a*.5)<Math.floor((d.X-16)*k+N/2)+1.2&&true):[[0,0]];
   for(const [a,b] of k>1?[[0,0]]:[[0,0]])if(cx+a>=0&&cx+a<N&&cy+b>=0&&cy+b<N)L[(cy+b)*N+cx+a]=pal[ch]})})}
 const ell=(X,Y,cx,cy,rx,ry)=>((X-cx)/rx)**2+((Y-cy)/ry)**2<=1;
 const capsule=(X,Y,ax,ay,bx,by,r)=>{const vx=bx-ax,vy=by-ay,t=Math.max(0,Math.min(1,((X-ax)*vx+(Y-ay)*vy)/(vx*vx+vy*vy||1)));return (X-ax-vx*t)**2+(Y-ay-vy*t)**2<=r*r};
 const fur=C.fur,sh=C.shade,lt=C.light;
 const bodyCol=HAS("hoodie")?"#7c5cd6":fur, bodySh=HAS("hoodie")?"#6345b8":sh;
 // 尾巴
 paint(back,(X,Y)=>{const w=P.tail*1.2;for(let i=0;i<=10;i++){const s=i/10,tx=21+s*6+w*s*s,ty=29-s*8-Math.sin(s*3)*1.5;if((X-tx)**2+(Y-ty)**2<=1.7)return C.point?C.point:(i>7&&C.patchB?C.patchB:(i>6&&C.stripes?C.stripes:sh))}return null});
 // 脚
 paint(back,(X,Y)=>{for(const [fx,fy] of P.feet)if(ell(X,Y,fx,fy,2.6,1.6))return C.point?C.point:lt;return null});
 // 身体
 const BY=24.6+P.bdy;
 paint(back,(X,Y)=>{if(!ell(X,Y,16,BY,6.8,6.2))return null;if(!HAS("hoodie")&&ell(X,Y,16,BY+1.4,3.8,4))return lt;if(!ell(X,Y-0.9,16,BY,6.8,6.2))return bodySh;
   if(C.patchA&&ell(X,Y,19.5,BY+1,2.6,2.4))return C.patchA;return bodyCol});
 if(HAS("hoodie")){paint(back,(X,Y)=>{if(Math.abs(X-14.6)<.5&&Y>BY-4.5&&Y<BY-.5)return "#f1ecff";if(Math.abs(X-17.4)<.5&&Y>BY-4.5&&Y<BY-1.5)return "#f1ecff";if(X>13&&X<19&&Y>BY+1.6&&Y<BY+3.4)return bodySh;return null})}
 if(lead){paint(back,(X,Y)=>{const y0=BY-5.2;if(Y<y0||Y>BY+3.5)return null;const d=Math.abs(X-16);   // 胸前红徽章：只给首领
   if(Y>BY+2.2)return null;if(Y<y0+1.5&&d<1.1)return "#b91c1c";if(Y>=y0+1.5&&d<.7+(Y-y0-1.5)*.32&&d<1.6)return Y>BY+1.4?"#991b1b":"#dc2626";
   if(Y<y0+1.6&&d<3&&d>=1.1&&Y-y0<(3-d)*.8)return "#ffffff";return null})}
 // 脖子槽位
 if(HAS("scarf")){paint(back,(X,Y)=>{const y0=BY-5.6;if(Y>y0&&Y<y0+2.6&&ell(X,Y,16,BY,7.2,6.6))return Math.floor(X)%3===0?"#fde68a":"#e11d48";if(X>18.4&&X<20.8&&Y>=y0+2.6&&Y<y0+7)return Math.floor(Y)%3===0?"#fde68a":"#e11d48";return null})}
 if(HAS("bell"))paint(back,(X,Y)=>{const y=BY-4.6;if(Math.abs(Y-y)<.8&&Math.abs(X-16)<5.4)return "#dc2626";if(ell(X,Y,16,y+1.6,1.3,1.2))return Y<y+1.3?"#fde047":"#ca8a04";return null});
 if(HAS("tie"))paint(back,(X,Y)=>{const y=BY-4.8;if(Math.abs(Y-y)<.6&&Math.abs(X-16)<4.6)return "#e5e7eb";if(Y>y&&Y<y+5.2&&Math.abs(X-16)<.8+(Y-y)*.18)return Y<y+1.2?"#1e3a8a":"#2563eb";return null});
 if(HAS("bandana"))paint(back,(X,Y)=>{const y=BY-5;if(Y>y-.6&&Y<y+3.6-Math.abs(X-16)*.7&&Math.abs(X-16)<5.6)return ((Math.floor(X)+Math.floor(Y))%3===0)?"#fff7ed":"#ef4444";return null});
 // 手臂（非前景姿势：画在头后面，举手不挡脸）
 const FRONT_POSES={type:1,tea:1,phone:1,game:1,nap:1};
 const sx=[11.4,20.6], sy=19.6+P.bdy, pawCol=C.point?mixHex(C.point,C.fur,.35):lt, armCol=HAS("hoodie")?"#7c5cd6":fur;
 const drawArms=Lr=>paint(Lr,(X,Y)=>{for(let i=0;i<2;i++){const [px,py]=P.paws[i];if(ell(X,Y,px,py,1.9,1.7))return pawCol;if(capsule(X,Y,sx[i],sy,px,py,1.6))return armCol}return null});
 if(!FRONT_POSES[pose])drawArms(back);
 // 头（含耳朵）
 const HR={x:10.2,y:8.6};
 const earL=(u,v,s)=>{const a=[-9.4,-2.6],b=[-7.2,-11.2],c=[-2.2,-7.6];const sgn=(p,q,r)=>(p[0]-r[0])*(q[1]-r[1])-(q[0]-r[0])*(p[1]-r[1]);const pt=[u,v];const d1=sgn(pt,a,b),d2=sgn(pt,b,c),d3=sgn(pt,c,a);
   const ins=!((d1<0||d2<0||d3<0)&&(d1>0||d2>0||d3>0));if(!s)return ins;const a2=[-8,-4.4],b2=[-7,-9.2],c2=[-3.8,-7];const e1=sgn(pt,a2,b2),e2=sgn(pt,b2,c2),e3=sgn(pt,c2,a2);return !((e1<0||e2<0||e3<0)&&(e1>0||e2>0||e3>0))};
 if(HAS("hoodie"))paint(back,(X,Y)=>ell(X,Y,16,20.2+P.bdy,8.4,2.6)?"#6a4cc4":null);
 paintHead(back,(u,v)=>{
   const inHead=ell(u,v,0,0,HR.x,HR.y), eL=earL(u,v),eR=earL(-u,v);
   if(!inHead&&!eL&&!eR)return null;
   if(!inHead){const inner=eL?earL(u,v,1):earL(-u,v,1);if(C.point)return inner?mixHex(C.point,C.ear,.3):C.point;
     if(C.patchA&&eL)return inner?C.ear:C.patchA; if(C.patchB&&eR)return inner?C.ear:C.patchB; return inner?C.ear:fur}
   let col=fur;
   if(C.patchA){if(ell(u,v,-6,-4.5,5.5,4.8))col=C.patchA;if(ell(u,v,6.5,-5,4.6,4))col=C.patchB}
   if(C.stripes&&v<-5.2&&(Math.abs(u)<.6||Math.abs(Math.abs(u)-2.4)<.5)&&v>-8.6+Math.abs(u)*.3)col=C.stripes;
   if(C.stripes&&C.cheek&&Math.abs(u)>8.2&&Math.abs(Math.abs(v)-1.2)<.55)col=C.stripes;
   if(C.point&&ell(u,v,0,3.4,3.4,2.6))col=mixHex(C.point,fur,.5);
   else if(!C.point&&ell(u,v,0,3.6,3.6,2.5))col=HAS("hoodie")?C.light:lt;
   if(!ell(u,v-1,0,0,HR.x,HR.y))col=C.patchB&&u>2?mixHex(C.patchB,"#000",.2):sh;
   if(C.rim&&!ell(u,v+.9,0,0,HR.x,HR.y)&&v<-2)col=C.rim;
   if(P.lit&&v>-1)col=mixHex(col,"#bfe3ff",.28);
   return col});
 // 五官（贴图）
 const E={"#":"#241a2a","o":"#ffffff","i":C.iris,"p":"#ff8fab","b":"#ffb3c6","m":"#241a2a","t":"#ff6b8b"};
 const EYES={open:[".##.","#o##","##o#","#ii#",".##."],wide:[".##.","#oo#","#o##","#ii#",".##."],down:["....",".##.","#o##","#ii#",".##."],
   focus:["....","####","#o##",".##.","...."],happy:["....",".##.","#..#","....","...."],sleep:["....","....","#..#",".##.","...."],
   squeeze:["#...",".##.","#...","....","...."],worried:["...#",".##.","#o##","#ii#",".##."]};
 const er=EYES[P.eyes]||EYES.open, ex=4.6, ey=-1.6;
 stamp(back,er,-ex-2,ey,E,false); stamp(back,er,ex+2,ey,E,true);
 if(P.eyes==="focus"){stamp(back,["##"],-ex-1.2,ey-1.2,E);stamp(back,["##"],ex+1.2,ey-1.2,E,true)}
 stamp(back,["bb"],-7.6,2.2,E);stamp(back,["bb"],7.6,2.2,E,true);
 stamp(back,["pp"],-1,1.4,E);
 const M={w:["#.##.#",".#..#."],flat:[".##."],o:[".#.","#t#",".#."],open:[".##.","#tt#",".##."],yawn:[".##.","#tt#","#tt#",".##."],none:[],tiny:["##"],wavy:["#.#.",".#.#"]}[P.mouth]||[];
 if(M.length)stamp(back,M,-M[0].length/2,2.6,E);
 if(P.eyes==="sleep"&&pose==="nap")stamp(back,["##"],-1,3,E);
 // 配饰（头部 / 面部 / 耳部槽位，贴在头上）
 if(HAS("crown"))paintHead(back,(u,v)=>{if(v<-12.4||v>-8.4||Math.abs(u)>4.2)return null;const base=v>-10;const sp=[-3.4,0,3.4].some(c=>Math.abs(u-c)<1.4-(-10-v)*.55&&v>-12.4);
   if(!base&&!sp)return null;if(base&&Math.abs(u)<1&&v>-9.6&&v<-8.6)return "#ef4444";return v>-9?"#ca8a04":"#facc15"});
 if(HAS("cap"))paintHead(back,(u,v)=>{const top=-HR.y-1.6;if(v<top-2.6||v>top+2.2)return null;
   if(v>top+.8&&v<=top+2.2&&u>-HR.x+1&&u<HR.x+3.8)return "#c2410c";
   if(v<=top+.8&&Math.abs(u)<HR.x-1.2){if(Math.abs(v-(top-.2))<.55)return "#facc15";if(Math.abs(u)<1.2&&v<top-.6&&v>top-2)return "#ffffff";return "#f97316"}return null});
 if(HAS("beanie"))paintHead(back,(u,v)=>{const top=-HR.y-1.2;if(v<top-2.4||v>top+2)return null;if(Math.hypot(u,v-(top-2.4))<1.3)return "#fde68a";
   if(Math.abs(u)<HR.x-.6+(v-top)*.6)return v>top+1?"#0f766e":((Math.floor(u)&1)?"#14b8a6":"#0d9488");return null});
 if(HAS("flower"))paintHead(back,(u,v)=>{const cx=-6.2,cy=-8.6,d=Math.hypot(u-cx,v-cy);if(d<.9)return "#facc15";if(d<2.3&&[0,1,2,3,4].some(i=>{const a=i*1.2566;return Math.hypot(u-cx-Math.cos(a)*1.5,v-cy-Math.sin(a)*1.5)<1}))return "#f472b6";return null});
 if(HAS("bow"))paintHead(back,(u,v)=>{const cx=6.4,cy=-8.8,dx=u-cx,dy=v-cy;if(Math.abs(dx)<1&&Math.abs(dy)<1)return "#be185d";if(Math.abs(dx)<3.6&&Math.abs(dy)<Math.abs(dx)*.75+.4)return Math.abs(dy)<.5&&Math.abs(dx)>1.4?"#f9a8d4":"#ec4899";return null});
 if(HAS("phones")){const acc2="#5aa9ff";paintHead(back,(u,v)=>{const r=((u/(HR.x+1.4))**2+((v+.6)/(HR.y+1.6))**2);if(v<-2&&r<=1.08&&r>=.86)return "#374151";
   if(ell(u,v,-HR.x-.2,.6,1.9,3)||ell(u,v,HR.x+.2,.6,1.9,3))return Math.abs(u)>HR.x+.9?mixHex(acc2,"#000",.25):acc2;return null})}
 if(HAS("glasses"))paintHead(back,(u,v)=>{const d1=Math.hypot(u+ex,v-.4),d2=Math.hypot(u-ex,v-.4);if((d1>2.7&&d1<3.5)||(d2>2.7&&d2<3.5))return "#b8860b";if(Math.abs(u)<1.6&&Math.abs(v+.2)<.45)return "#b8860b";return null});
 if(HAS("sunglasses"))paintHead(back,(u,v)=>{if(Math.abs(v-.3)<1.4&&(Math.abs(u+3.4)<2.4||Math.abs(u-3.4)<2.4))return (v<-.4&&(u<-4||(u>2.4&&u<3.4)))?"#64748b":"#111827";if(Math.abs(v+.5)<.45&&Math.abs(u)<1.2)return "#111827";return null});
 if(P.sweat)paint(back,(X,Y)=>{const d=toDesign(9.4,-3.4);const sx=d.X,sy=d.Y;if(ell(X,Y,sx,sy+1,1.3,1.5)||(Math.abs(X-sx)<.5&&Y>sy-1.4&&Y<sy))return Y<sy+.6&&X<sx?"#e0f2fe":"#7dd3fc";return null});
 // 前景层：手臂、爪子、道具
 if(P.prop==="chin"){paint(front,(X,Y)=>{for(const [px,py] of P.paws)if(ell(X,Y,px,py,2.2,1.6))return pawCol;return null})}
 else if(FRONT_POSES[pose])drawArms(front);
 if(P.prop==="cup"||P.prop==="cup-up"){const y0=P.prop==="cup"?18.4:15.8;paint(front,(X,Y)=>{if(X>13.6&&X<18.4&&Y>y0&&Y<y0+3.8){if(Y<y0+1)return "#a16207";return X<14.6?"#dbeafe":"#93c5fd"}if(X>=18.4&&X<19.6&&Y>y0+.8&&Y<y0+2.8&&!(X>18.6&&Y>y0+1.4&&Y<y0+2.2))return "#93c5fd";return null});
   for(const [px,py] of P.paws)paint(front,(X,Y)=>ell(X,Y,px,py+.4,1.6,1.4)?pawCol:null)}
 if(P.prop==="phone"){paint(front,(X,Y)=>{if(X>13.8&&X<18.2&&Y>17.4&&Y<22.6){if(X>14.6&&X<17.4&&Y>18.2&&Y<21.8)return Y<19.4?"#bae6fd":"#7dd3fc";return "#1f2937"}return null});for(const [px,py] of P.paws)paint(front,(X,Y)=>ell(X,Y,px,py,1.5,1.4)?pawCol:null)}
 if(P.prop==="pad"){paint(front,(X,Y)=>{if(ell(X,Y,16,21.6,5.4,2.1)){if(ell(X,Y,13.6,21.4,.7,.7))return "#374151";if(ell(X,Y,18.2,21,.6,.6))return "#f87171";if(ell(X,Y,19.4,21.9,.6,.6))return "#60a5fa";return Y<20.6?"#e5e7eb":"#c4c8d0"}return null});
   for(const [px,py] of P.paws)paint(front,(X,Y)=>ell(X,Y,px,py+.2,1.6,1.5)?pawCol:null)}
 if(P.lines){paint(front,(X,Y)=>{const xs=P.lines==="l"?[8.6,7.4]:[23.4,24.6];for(let j=0;j<2;j++)if(Math.abs(X-xs[j])<.5&&Y>18.2+j&&Y<20.2+j)return "#fef3c7";return null})}
 // 描边
 function outline(Lr,col){const out=Lr.slice();for(let y=0;y<N;y++)for(let x=0;x<N;x++){if(Lr[y*N+x])continue;const nb=[[1,0],[-1,0],[0,1],[0,-1]].some(([a,b])=>{const xx=x+a,yy=y+b;return xx>=0&&yy>=0&&xx<N&&yy<N&&Lr[yy*N+xx]});if(nb)out[y*N+x]=col}return out}
 const ol=C.line;let b2=outline(back,ol), f2=outline(front,ol);if(C.glow){b2=outline(b2,C.glow);}
 const toCanvas=A=>{const cv=document.createElement("canvas");cv.width=N;cv.height=N;const x=cv.getContext("2d"),id=x.createImageData(N,N);
   A.forEach((c,i)=>{if(!c)return;const [r,g,b]=hexRGB(c);id.data[i*4]=r;id.data[i*4+1]=g;id.data[i*4+2]=b;id.data[i*4+3]=255});x.putImageData(id,0,0);return cv};
 const out={back:toCanvas(b2),front:toCanvas(f2),N,k,head:toDesign(0,-HR.y-3),cup:P.prop&&P.prop.startsWith("cup")?{x:16,y:P.prop==="cup"?18:15.4}:null};
 SPRITE_CACHE.set(key,out);return out;
}
