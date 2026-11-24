# -*- coding: utf-8 -*-
"""生成单文件 HTML 标注工具 v3：旋转矩形(OBB) 框 + 路段 + 自动吸附 + 分段统计"""
import base64
import json
import os

import cv2
import numpy as np

# ======================= CLI =======================
import argparse

_ap = argparse.ArgumentParser(description="把手绘扫描图打包成单文件标注网页")
_ap.add_argument("--images", nargs="+", required=True, help="扫描图路径（可多张）")
_ap.add_argument("--labels", nargs="*", default=None, help="各图显示名（可省）")
_ap.add_argument("--keys", nargs="*", default=None, help="各图内部 key（可省，默认 i1,i2…）")
_ap.add_argument("--boxes", default=None, help="预置框 JSON（可选）")
_ap.add_argument("--ink", nargs="*", default=None, help="预先生成的掩膜 PNG（可选，用于沿笔迹吸附）")
_ap.add_argument("--out", default="tool.html", help="输出 HTML 路径")
_ap.add_argument("--work", default=None, help="掩膜查找目录（默认取图所在目录）")
ARGS = _ap.parse_args()

OUT = os.path.abspath(ARGS.out)
OUTDIR = os.path.dirname(OUT) or "."
PROJ = os.path.dirname(os.path.abspath(ARGS.images[0])) or "."
WORK = os.path.abspath(ARGS.work) if ARGS.work else PROJ
BOXES_JSON = os.path.abspath(ARGS.boxes) if ARGS.boxes else ""

_labels = ARGS.labels or [os.path.splitext(os.path.basename(p))[0] for p in ARGS.images]
_keys = ARGS.keys or [f"i{i+1}" for i in range(len(ARGS.images))]
IMAGES = [(k, os.path.abspath(p), lb) for k, p, lb in zip(_keys, ARGS.images, _labels)]
MASKS = {k: os.path.abspath(m) for k, m in zip(_keys, ARGS.ink or [])}
# ===================================================
ROOT = PROJ
W = WORK

boxes = json.load(open(BOXES_JSON, encoding="utf-8")) if BOXES_JSON and os.path.exists(BOXES_JSON) else {}


def data_url(path):
    ext = os.path.splitext(path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def to_obb(quad):
    import math
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
    cx = (x0 + x1 + x2 + x3) / 4.0
    cy = (y0 + y1 + y2 + y3) / 4.0
    e1 = math.hypot(x1 - x0, y1 - y0)
    e2 = math.hypot(x2 - x1, y2 - y1)
    if e1 >= e2:
        w, h, ang = e1, e2, math.degrees(math.atan2(y1 - y0, x1 - x0))
    else:
        w, h, ang = e2, e1, math.degrees(math.atan2(y2 - y1, x2 - x1))
    return [round(cx, 1), round(cy, 1), round(w, 1), round(h, 1), round(ang % 180, 1)]


imgs = []
for key, fn, label in IMAGES:
    path = os.path.join(PROJ, fn)
    im = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = im.shape[:2]
    obs = []
    for b in sorted(boxes.get(key, []), key=lambda d: (round(d["cy"] / 55), d["cx"])):
        obs.append(to_obb([[float(p[0]), float(p[1])] for p in b["box"]]))
    entry = {"key": key, "label": label, "src": data_url(path), "w": w, "h": h, "boxes": obs}
    mask_path = MASKS.get(key) or os.path.join(WORK, f"{key}_mask.png")
    entry["mask"] = data_url(mask_path) if os.path.exists(mask_path) else entry["src"]
    imgs.append(entry)

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>公园行为标注 · 旋转框 / 路段</title>
<style>
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;font:13px/1.55 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;color:#222;background:#f4f5f7}
  #app{display:flex;height:100%}
  #stage{flex:1;position:relative;overflow:hidden;background:#fff}
  canvas{display:block}
  #panel{width:356px;background:#fff;border-left:1px solid #e3e5e8;display:flex;flex-direction:column;overflow:hidden}
  .sec{padding:9px 12px;border-bottom:1px solid #eef0f2;flex:none}
  .sec h3{margin:0 0 7px;font-size:12px;color:#666;font-weight:600}
  button{font:inherit;padding:4px 9px;border:1px solid #d5d8dd;background:#fff;border-radius:6px;cursor:pointer}
  button:hover{background:#f7f8fa}
  button.on{background:#1a6dff;border-color:#1a6dff;color:#fff}
  button.danger{color:#c02a2a;border-color:#e6bcbc}
  .row{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
  .scroll{overflow:auto}
  .item{display:flex;justify-content:space-between;gap:6px;padding:3px 12px;cursor:pointer;border-bottom:1px solid #f6f7f9;font-variant-numeric:tabular-nums}
  .item:hover{background:#f5f8ff}
  .item.sel{background:#e8f0ff}
  .item .m{color:#888;font-size:12px}
  input[type=text],select{width:100%;padding:4px 6px;border:1px solid #d5d8dd;border-radius:5px;font:inherit;background:#fff}
  table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
  th,td{padding:2px 4px;text-align:right;border-bottom:1px solid #f2f3f5;font-size:12px}
  th:first-child,td:first-child{text-align:left}
  th{color:#888;font-weight:600}
  #readCard{display:none;position:absolute;left:50%;transform:translateX(-50%);bottom:18px;width:440px;
    background:#fff;border:1px solid #e3e5e8;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.14);padding:12px 14px;z-index:5}
  .rcTop{display:flex;justify-content:space-between;font-size:12px;color:#666}
  .rcRow3{display:flex;gap:8px;margin-top:8px;align-items:flex-end}
  .rcF{flex:1;display:flex;flex-direction:column;gap:2px}
  .rcF i{font-style:normal;font-size:11px;color:#8a8a8a;text-align:center}
  .rcF input{width:100%;font-size:26px;padding:5px 6px;text-align:center;border:2px solid #d5d8dd;
    border-radius:8px;font-family:Consolas,monospace}
  .rcF input:focus{outline:none;border-color:#1a6dff}
  .rcF input.bad{border-color:#d33;background:#fff5f5}
  #rcFmt{font-size:13px;color:#1a6dff;height:18px;text-align:center;margin-top:4px;font-variant-numeric:tabular-nums}
  #rcFmt.bad{color:#c02a2a}
  #rcSuggest{display:none;font-size:12px;color:#1a6dff;margin-top:6px}
  .rcRow{display:flex;gap:6px;margin-top:8px}
  .rcKeys{font-size:11px;color:#999;margin-top:6px;line-height:1.5}
  #zoom{position:absolute;right:12px;bottom:12px;background:rgba(255,255,255,.92);border:1px solid #e3e5e8;border-radius:6px;padding:3px 8px;font-size:12px;color:#555}
  #tabs{display:flex;gap:6px}
  kbd{background:#eef0f2;border-radius:3px;padding:0 4px;font:inherit;font-size:11px}
  .tip{font-size:11.5px;color:#8a8a8a;line-height:1.65}
  .badge{display:inline-block;padding:0 5px;border-radius:4px;background:#eef3ff;color:#1a6dff;font-size:11px}
</style>
</head>
<body>
<div id="app">
  <div id="stage"><canvas id="cv"></canvas><div id="zoom">100%</div>
    <div id="readCard">
      <div class="rcTop"><span id="rcTitle">—</span><span id="rcProgress"></span></div>
      <div class="rcRow3">
        <label class="rcF"><i>人数</i><input id="rcN" inputmode="numeric" maxlength="2" autocomplete="off"></label>
        <label class="rcF"><i>性别</i><input id="rcG" inputmode="numeric" maxlength="1" autocomplete="off"></label>
        <label class="rcF"><i>活动</i><input id="rcA" inputmode="numeric" maxlength="2" autocomplete="off"></label>
      </div>
      <div id="rcFmt"></div>
      <div id="rcSuggest"></div>
      <div class="rcRow">
        <button id="rcPrev">← 上一个</button>
        <button id="rcSkip">跳过</button>
        <button id="rcNext">下一个 →</button>
        <button id="rcExit" style="margin-left:auto">退出</button>
      </div>
      <div class="rcKeys">A1步行/散步 A2跑步 A3骑行/轮滑 A4坐憩/休息 A5社交 A6亲子 A7锻炼 A8遛狗<br>A9野餐/饮食 A10手机/阅读 A11拍照/观景 A12文化 A13其他</div>
    </div>
  </div>
  <div id="panel">
    <div class="sec"><h3>图像</h3><div id="tabs"></div></div>

    <div class="sec">
      <h3>模式</h3>
      <div class="row">
        <button id="mSel" class="on">选择</button>
        <button id="mNew">新建框</button>
        <button id="mSeg">画路段</button>
        <button id="mDet">检测</button>
      </div>
      <div class="row" style="margin-top:6px">
        <button id="fit">适应窗口</button>
        <button id="toggleNum" class="on">编号</button>
        <button id="toggleSnap" class="on">沿路吸附</button>
        <button id="detAll" style="font-size:11px">整图检测</button>
        <button id="readBtn" style="border-color:#ffd8a8;color:#e8590c">读数</button>
        <button id="undo">撤销</button>
      </div>
    </div>

    <div class="sec" style="max-height:170px;display:flex;flex-direction:column;padding-bottom:4px">
      <h3 style="display:flex;justify-content:space-between;align-items:center">
        <span>路段 <span id="segCount" class="badge">0</span></span>
        <span class="row" style="gap:4px">
          <button id="autoAssign" style="padding:2px 7px;font-size:11px">自动吸附</button>
          <button id="mergeSeg" style="padding:2px 7px;font-size:11px">合并</button>
          <button id="delSeg" class="danger" style="padding:2px 7px;font-size:11px">删除</button>
        </span>
      </h3>
      <div id="segList" class="scroll" style="flex:1"></div>
    </div>

    <div class="sec">
      <h3>选中框</h3>
      <div id="selInfo" style="font-size:12px;color:#666;margin-bottom:5px">未选中</div>
      <div class="row" style="gap:6px;margin-bottom:5px">
        <select id="segSel" style="flex:1"><option value="">— 未归属路段 —</option></select>
      </div>
      <input id="note" type="text" placeholder="读数，如 10-2-6（1-2位人数-性别-活动）">
      <div class="row" style="margin-top:6px">
        <button id="del" class="danger">删除框</button>
        <button id="dup">复制</button>
        <button id="bindSeg" style="border-color:#bcd7ff;color:#1a6dff">挂到选中路段</button>
        <button id="rotL" title="逆时针 5°">⟲ 5°</button>
        <button id="rotR" title="顺时针 5°">⟳ 5°</button>
      </div>
    </div>

    <div class="sec scroll" style="flex:1">
      <h3>分段统计</h3>
      <table id="stats"><thead><tr><th>路段</th><th>框</th><th>人数</th><th>男</th><th>女</th><th>停留</th></tr></thead><tbody></tbody></table>
      <div class="tip" id="sum" style="margin-top:6px"></div>
    </div>

    <div class="sec" style="border-bottom:none">
      <h3>导出</h3>
      <div class="row">
        <button id="expJson">JSON</button>
        <button id="expCsv">CSV</button>
        <button id="impSug">导入建议值</button>
        <button id="reset" class="danger">重置</button>
        <input id="sugFile" type="file" accept=".json" style="display:none">
      </div>
      <div class="tip" style="margin-top:5px">
        读数：直接敲数字（1026 → 10-2-6），不用打横杠。<br>
        检测：拖一个范围 → 自动找出范围内的笔迹块（绿色框），可删可改。<br>
        画路段：点起点 → 点终点，自动沿手绘笔迹走线。<br>
        框＝旋转矩形：拖四角＝缩放，拖顶部圆点＝旋转。<br>
        滚轮缩放 · 右键拖动平移 · <kbd>V</kbd>选择 <kbd>N</kbd>框 <kbd>S</kbd>路段 <kbd>Del</kbd>删 · <kbd>F</kbd>适应
      </div>
    </div>
  </div>
</div>
<script>
const IMGS = __IMAGES__;
const DWELL = {1:1,2:1,3:1,4:3,5:3,6:3,7:3,8:2,9:3,10:3,11:2,12:3,13:2};
const VER = 'v3_';

let imgIdx = 0, state = {}, sel = -1, selSeg = -1, mode = 'sel', showNum = true, snapOn = true;
let view = {s:1, x:0, y:0}, drag = null, history = [], draft = null;
let mergeMode = false, mergePick = [];

const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
const stage = document.getElementById('stage'), zoomEl = document.getElementById('zoom');
const DPR = window.devicePixelRatio || 1;

function mk(id, cx, cy, w, h, ang){
  return {id, cx, cy, w, h, ang:((ang%180)+180)%180, status:'kept', note:'', seg:null, manual:false};
}
function pts(b){
  const a=b.ang*Math.PI/180, c=Math.cos(a), s=Math.sin(a), hw=b.w/2, hh=b.h/2;
  return [[-hw,-hh],[hw,-hh],[hw,hh],[-hw,hh]].map(([x,y])=>[b.cx+c*x-s*y, b.cy+s*x+c*y]);
}
function toLocal(b, p){
  const a=b.ang*Math.PI/180, c=Math.cos(a), s=Math.sin(a);
  const dx=p.x-b.cx, dy=p.y-b.cy;
  return {x:c*dx+s*dy, y:-s*dx+c*dy};
}
function inBox(b,p){ const l=toLocal(b,p); return Math.abs(l.x)<=b.w/2 && Math.abs(l.y)<=b.h/2; }
function handlePt(b){
  const a=b.ang*Math.PI/180, c=Math.cos(a), s=Math.sin(a), off=b.h/2+24/view.s;
  return [b.cx+s*off, b.cy-c*off];
}

function initState(i){
  const key=IMGS[i].key;
  const saved=localStorage.getItem(VER+key);
  if(saved){ try{ state[key]=JSON.parse(saved); return; }catch(e){} }
  const old = localStorage.getItem('v2_'+key) || localStorage.getItem('boxlab_'+key);
  if(old){
    try{
      const o=JSON.parse(old);
      state[key]={ boxes:(o.boxes||[]).map(b=>{
                     if(b.cx!==undefined) return b;
                     const q=b.q||[]; if(q.length<4) return mk(b.id,0,0,10,10,0);
                     const cx=(q[0][0]+q[1][0]+q[2][0]+q[3][0])/4, cy=(q[0][1]+q[1][1]+q[2][1]+q[3][1])/4;
                     const e1=Math.hypot(q[1][0]-q[0][0],q[1][1]-q[0][1]);
                     const e2=Math.hypot(q[2][0]-q[1][0],q[2][1]-q[1][1]);
                     const ang=Math.atan2(q[1][1]-q[0][1],q[1][0]-q[0][0])*180/Math.PI;
                     const w=Math.max(e1,e2), h=Math.min(e1,e2);
                     const o2=mk(b.id,cx,cy,w,h,e1>=e2?ang:ang+90);
                     o2.note=b.note||''; o2.status=b.status||'kept'; o2.seg=b.seg||null;
                     return o2;
                   }),
                   segs:o.segs||[], nextId:o.nextId||1000, nextSeg:o.nextSeg||1, del:o.del||[] };
      return;
    }catch(e){}
  }
  state[key]={ boxes: IMGS[i].boxes.map((o,k)=>mk(k+1,o[0],o[1],o[2],o[3],o[4])),
               segs: [], nextId: 1000, nextSeg: 1, del: [] };
}
function cur(){ return state[IMGS[imgIdx].key]; }
function save(){ localStorage.setItem(VER+IMGS[imgIdx].key, JSON.stringify(cur())); }

function resize(){
  cv.width=stage.clientWidth*DPR; cv.height=stage.clientHeight*DPR;
  cv.style.width=stage.clientWidth+'px'; cv.style.height=stage.clientHeight+'px';
  draw();
}
function fit(){
  const im=IMGS[imgIdx];
  const s=Math.min(stage.clientWidth/im.w, stage.clientHeight/im.h)*0.97;
  view.s=s; view.x=(stage.clientWidth-im.w*s)/2; view.y=(stage.clientHeight-im.h*s)/2;
  draw();
}
function toImg(ev){
  const r=cv.getBoundingClientRect();
  return {x:(ev.clientX-r.left-view.x)/view.s, y:(ev.clientY-r.top-view.y)/view.s};
}
function hit(p){
  const bs=cur().boxes;
  for(let i=bs.length-1;i>=0;i--) if(inBox(bs[i],p)) return i;
  return -1;
}
function hitSeg(p){
  const sg=cur().segs;
  let bi=-1, bd=14/view.s;
  sg.forEach((s,i)=>{ const d=distPoly(p, s.pts); if(d<bd){ bd=d; bi=i; } });
  return bi;
}
function distSeg(p,a,b){
  const dx=b[0]-a[0], dy=b[1]-a[1], L=dx*dx+dy*dy;
  let t=L?((p.x-a[0])*dx+(p.y-a[1])*dy)/L:0;
  t=Math.max(0,Math.min(1,t));
  return Math.hypot(p.x-(a[0]+t*dx), p.y-(a[1]+t*dy));
}
function distPoly(p,ps){
  let d=1e9;
  for(let i=0;i<ps.length-1;i++) d=Math.min(d,distSeg(p,ps[i],ps[i+1]));
  return d;
}
function segMid(ps){
  let L=0;
  for(let i=0;i<ps.length-1;i++) L+=Math.hypot(ps[i+1][0]-ps[i][0], ps[i+1][1]-ps[i][1]);
  let acc=0;
  for(let i=0;i<ps.length-1;i++){
    const l=Math.hypot(ps[i+1][0]-ps[i][0], ps[i+1][1]-ps[i][1]);
    if(acc+l>=L/2){ const t=(L/2-acc)/(l||1); return [ps[i][0]+(ps[i+1][0]-ps[i][0])*t, ps[i][1]+(ps[i+1][1]-ps[i][1])*t]; }
    acc+=l;
  }
  return ps[0];
}


/* ---------- 沿墨迹寻路 ---------- */
function grid(){
  const im=IMGS[imgIdx];
  if(im._grid) return im._grid;
  const w2=Math.ceil(im.w/2), h2=Math.ceil(im.h/2);
  const c=document.createElement('canvas'); c.width=w2; c.height=h2;
  const g=c.getContext('2d');
  g.fillStyle='#fff'; g.fillRect(0,0,w2,h2);
  if(im._maskImg) g.drawImage(im._maskImg,0,0,w2,h2);
  const d=g.getImageData(0,0,w2,h2).data;
  const ink=new Uint8Array(w2*h2);
  for(let i=0;i<w2*h2;i++) ink[i]= d[i*4]<128 ? 1 : 0;
  im._grid={w:w2,h:h2,ink};
  return im._grid;
}
class Heap{
  constructor(){ this.k=[]; this.v=[]; }
  get size(){ return this.v.length; }
  push(key,val){
    this.k.push(key); this.v.push(val);
    let i=this.v.length-1;
    while(i>0){ const p=(i-1)>>1; if(this.v[p]<=this.v[i]) break;
      [this.v[p],this.v[i]]=[this.v[i],this.v[p]]; [this.k[p],this.k[i]]=[this.k[i],this.k[p]]; i=p; }
  }
  pop(){
    const top=this.k[0]; const vk=this.v[0];
    const lk=this.k.pop(), lv=this.v.pop();
    if(this.v.length){ this.k[0]=lk; this.v[0]=lv;
      let i=0;
      for(;;){ const l=2*i+1, r=l+1; let m=i;
        if(l<this.v.length && this.v[l]<this.v[m]) m=l;
        if(r<this.v.length && this.v[r]<this.v[m]) m=r;
        if(m===i) break;
        [this.v[m],this.v[i]]=[this.v[i],this.v[m]]; [this.k[m],this.k[i]]=[this.k[i],this.k[m]]; i=m; }
    }
    return top;
  }
}
function snapInk(G,p,rad){
  const cx=Math.round(p.x/2), cy=Math.round(p.y/2);
  let best=null,bd=1e9;
  for(let dy=-rad;dy<=rad;dy++) for(let dx=-rad;dx<=rad;dx++){
    const x=cx+dx,y=cy+dy;
    if(x<0||y<0||x>=G.w||y>=G.h) continue;
    if(!G.ink[y*G.w+x]) continue;
    const d=dx*dx+dy*dy;
    if(d<bd){ bd=d; best={x,y}; }
  }
  return best;
}
function astar(G,s,e){
  const {w,h,ink}=G, N=w*h;
  const gs=new Float32Array(N); gs.fill(1e9);
  const from=new Int32Array(N); from.fill(-1);
  const done=new Uint8Array(N);
  const heap=new Heap();
  const H=(x,y)=>Math.hypot(x-e.x,y-e.y);
  const si=s.y*w+s.x, ei=e.y*w+e.x;
  gs[si]=0; heap.push(si, H(s.x,s.y));
  let guard=0;
  while(heap.size){
    const cur=heap.pop();
    if(done[cur]) continue;
    done[cur]=1;
    if(cur===ei) break;
    if(++guard>260000) return null;
    const cx=cur%w, cy=(cur-cx)/w;
    for(let dy=-1;dy<=1;dy++) for(let dx=-1;dx<=1;dx++){
      if(!dx&&!dy) continue;
      const nx=cx+dx, ny=cy+dy;
      if(nx<0||ny<0||nx>=w||ny>=h) continue;
      const ni=ny*w+nx;
      if(done[ni]) continue;
      const step=(dx&&dy)?1.41421:1;
      const cost=ink[ni]?1:16;
      const ng=gs[cur]+step*cost;
      if(ng<gs[ni]){ gs[ni]=ng; from[ni]=cur; heap.push(ni, ng+H(nx,ny)); }
    }
  }
  if(gs[ei]>=1e9) return null;
  const path=[]; let c=ei;
  while(c!==-1){ const x=c%w, y=(c-x)/w; path.push([x*2+1,y*2+1]); c=from[c]; }
  return path.reverse();
}
function rdp(ps,eps){
  if(ps.length<3) return ps;
  let dmax=0,idx=0;
  const a=ps[0], b=ps[ps.length-1];
  for(let i=1;i<ps.length-1;i++){
    const d=distSeg({x:ps[i][0],y:ps[i][1]}, a, b);
    if(d>dmax){ dmax=d; idx=i; }
  }
  if(dmax>eps){
    const l=rdp(ps.slice(0,idx+1),eps), r=rdp(ps.slice(idx),eps);
    return l.slice(0,-1).concat(r);
  }
  return [a,b];
}
function traceSeg(a,b){
  const im=IMGS[imgIdx];
  if(!im._maskImg){
    const mi=new Image(); mi.onload=()=>{ im._maskImg=mi; }; mi.src=im.mask;
  }
  if(!im._maskImg) return [[a.x,a.y],[b.x,b.y]];
  const G=grid();
  const s=snapInk(G,a,16)||{x:Math.round(a.x/2),y:Math.round(a.y/2)};
  const e=snapInk(G,b,16)||{x:Math.round(b.x/2),y:Math.round(b.y/2)};
  const p=astar(G,s,e);
  if(!p||p.length<2) return [[a.x,a.y],[b.x,b.y]];
  const simp=rdp(p, 3.0);
  return simp;
}


/* ---------- 本地检测：笔画块聚类成"文字行" ---------- */
function maskFull(){
  const im=IMGS[imgIdx];
  if(im._mf) return im._mf;
  if(!im._maskImg) return null;
  const c=document.createElement('canvas'); c.width=im.w; c.height=im.h;
  const g=c.getContext('2d');
  g.drawImage(im._maskImg,0,0,im.w,im.h);
  const d=g.getImageData(0,0,im.w,im.h).data;
  const m=new Uint8Array(im.w*im.h);
  for(let i=0;i<m.length;i++) m[i]= d[i*4]<128?1:0;
  im._mf={w:im.w,h:im.h,m};
  return im._mf;
}
function detectBoxes(mf, rect){
  const {w,h,m}=mf;
  const x0=Math.max(0,Math.floor(rect.x0)), y0=Math.max(0,Math.floor(rect.y0));
  const x1=Math.min(w-1,Math.ceil(rect.x1)), y1=Math.min(h-1,Math.ceil(rect.y1));
  const RW=x1-x0+1, RH=y1-y0+1;
  if(RW<8||RH<8) return [];
  const seen=new Uint8Array(RW*RH);
  const glyphs=[];
  const stack=new Int32Array(RW*RH);
  for(let y=0;y<RH;y++) for(let x=0;x<RW;x++){
    const gi=y*RW+x;
    if(seen[gi]||!m[(y+y0)*w+(x+x0)]) continue;
    let sp=0; stack[sp++]=gi; seen[gi]=1;
    let minx=x,maxx=x,miny=y,maxy=y,n=0,sx=0,sy=0;
    while(sp){
      const cur=stack[--sp]; const cy=(cur/RW)|0, cx=cur-cy*RW;
      n++; sx+=cx; sy+=cy;
      if(cx<minx)minx=cx; if(cx>maxx)maxx=cx; if(cy<miny)miny=cy; if(cy>maxy)maxy=cy;
      for(let dy=-1;dy<=1;dy++) for(let dx=-1;dx<=1;dx++){
        if(!dx&&!dy) continue;
        const nx=cx+dx, ny=cy+dy;
        if(nx<0||ny<0||nx>=RW||ny>=RH) continue;
        const ni=ny*RW+nx;
        if(seen[ni]||!m[(ny+y0)*w+(nx+x0)]) continue;
        seen[ni]=1; stack[sp++]=ni;
      }
    }
    const bw=maxx-minx+1, bh=maxy-miny+1;
    if(n<8||n>3000) continue;
    if(bw>64||bh>64) continue;
    if(n/(bw*bh) < 0.12) continue;
    glyphs.push({cx:x0+sx/n, cy:y0+sy/n, x0:x0+minx, x1:x0+maxx, y0:y0+miny, y1:y0+maxy, n});
  }
  // 按距离聚类
  const par=glyphs.map((_,i)=>i);
  const find=i=>{ while(par[i]!==i){ par[i]=par[par[i]]; i=par[i]; } return i; };
  const uni=(a,b)=>{ a=find(a); b=find(b); if(a!==b) par[b]=a; };
  for(let i=0;i<glyphs.length;i++) for(let j=i+1;j<glyphs.length;j++){
    const d=Math.hypot(glyphs[i].cx-glyphs[j].cx, glyphs[i].cy-glyphs[j].cy);
    if(d<26 && Math.abs(glyphs[i].cy-glyphs[j].cy)<15) uni(i,j);
  }
  const groups={};
  glyphs.forEach((g,i)=>{ const r=find(i); (groups[r]=groups[r]||[]).push(g); });

  const out=[];
  Object.values(groups).forEach(gs=>{
    if(gs.length<3) return;
    let mnx=1e9,mny=1e9,mxx=-1e9,mxy=-1e9,sx=0,sy=0,cnt=0;
    gs.forEach(g=>{ mnx=Math.min(mnx,g.x0); mny=Math.min(mny,g.y0); mxx=Math.max(mxx,g.x1); mxy=Math.max(mxy,g.y1);
                    sx+=g.cx*g.n; sy+=g.cy*g.n; cnt+=g.n; });
    const mx=sx/cnt, my=sy/cnt;
    let sxx=0,syy=0,sxy=0;
    gs.forEach(g=>{ const dx=g.cx-mx, dy=g.cy-my, wgt=g.n; sxx+=wgt*dx*dx; syy+=wgt*dy*dy; sxy+=wgt*dx*dy; });
    const ang=0.5*Math.atan2(2*sxy, sxx-syy);
    const ux=Math.cos(ang), uy=Math.sin(ang), vx=-uy, vy=ux;
    let minu=1e9,maxu=-1e9,minv=1e9,maxv=-1e9;
    gs.forEach(g=>{
      [[g.x0,g.y0],[g.x1,g.y0],[g.x1,g.y1],[g.x0,g.y1]].forEach(([x,y])=>{
        const pu=(x-mx)*ux+(y-my)*uy, pv=(x-mx)*vx+(y-my)*vy;
        minu=Math.min(minu,pu); maxu=Math.max(maxu,pu);
        minv=Math.min(minv,pv); maxv=Math.max(maxv,pv);
      });
    });
    const W=maxu-minu, H=maxv-minv;
    if(W<32||W>300||H<10||H>80) return;
    if(W/H<1.15) return;
    const cx=mx+ux*(minu+maxu)/2+vx*(minv+maxv)/2;
    const cy=my+uy*(minu+maxu)/2+vy*(minv+maxv)/2;
    out.push({cx, cy, w:W, h:H, ang:((ang*180/Math.PI)%180+180)%180});
  });
  return out;
}
function runDetect(rect){
  const mf=maskFull();
  if(!mf){ alert('底图掩膜还没加载完，稍等再试'); return; }
  const found=detectBoxes(mf, rect);
  if(!found.length){ alert('这个范围里没找到像代码的笔迹块'); return; }
  pushHist();
  found.forEach(o=>{
    const b=mk(cur().nextId++, o.cx, o.cy, o.w, o.h, o.ang);
    b.status='new';
    cur().boxes.push(b);
  });
  snapBox(); save(); draw(); renderLists();
  alert(`检出 ${found.length} 个候选框，已用绿框加入，可逐个删改`);
}

function draw(){
  const im=IMGS[imgIdx];
  if(!im._img){ const t=new Image(); t.onload=()=>{im._img=t; draw();}; t.src=im.src; return; }
  ctx.setTransform(DPR,0,0,DPR,0,0);
  ctx.clearRect(0,0,cv.width,cv.height);
  ctx.fillStyle='#fff'; ctx.fillRect(0,0,cv.width,cv.height);
  ctx.save();
  ctx.setTransform(DPR*view.s,0,0,DPR*view.s,DPR*view.x,DPR*view.y);
  ctx.drawImage(im._img,0,0);

  cur().segs.forEach((s,i)=>{
    ctx.beginPath();
    s.pts.forEach((p,k)=> k?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));
    ctx.lineCap='round'; ctx.lineJoin='round';
    ctx.strokeStyle=(i===selSeg)?'rgba(255,122,0,.8)':'rgba(20,160,120,.5)';
    ctx.lineWidth=18/view.s; ctx.stroke();
    ctx.strokeStyle=(i===selSeg)?'rgba(255,195,130,.9)':'rgba(190,245,225,.7)';
    ctx.lineWidth=7/view.s; ctx.stroke();
    const m=segMid(s.pts), fs=15/view.s;
    ctx.font=`700 ${fs}px "Microsoft YaHei",sans-serif`;
    ctx.lineWidth=4/view.s; ctx.strokeStyle='#fff';
    ctx.strokeText(s.id,m[0],m[1]-6/view.s);
    ctx.fillStyle=(i===selSeg)?'#e05a00':'#0b7a5a';
    ctx.fillText(s.id,m[0],m[1]-6/view.s);
  });

  const hiSeg = (selSeg>=0 && cur().segs[selSeg]) ? cur().segs[selSeg].id : null;
  cur().boxes.forEach((b,i)=>{
    const q=pts(b), isSel=(i===sel);
    const inHi = hiSeg && b.seg===hiSeg;
    ctx.beginPath();
    q.forEach((p,k)=> k?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));
    ctx.closePath();
    if(inHi){ ctx.fillStyle='rgba(255,170,0,.16)'; ctx.fill(); }
    ctx.lineWidth=(isSel?3:(inHi?2.8:1.7))/view.s;
    ctx.strokeStyle=isSel?'#ff7a00':(inHi?'#e8890c':(b.seg?'rgba(15,110,200,.95)':'rgba(150,150,150,.85)'));
    ctx.stroke();
    if(showNum){
      const x=Math.min(...q.map(p=>p[0])), y=Math.min(...q.map(p=>p[1])), fs=13/view.s;
      ctx.font=`700 ${fs}px "Microsoft YaHei",sans-serif`;
      ctx.lineWidth=3.2/view.s; ctx.strokeStyle='#fff';
      ctx.strokeText(b.id,x,y-4/view.s);
      ctx.fillStyle=b.seg?'#0b6fd0':'#c33';
      ctx.fillText(b.id,x,y-4/view.s);
    }
    if(isSel){
      q.forEach(p=>{
        ctx.beginPath(); ctx.arc(p[0],p[1],4.6/view.s,0,6.2832);
        ctx.fillStyle='#ff7a00'; ctx.fill();
        ctx.lineWidth=1.4/view.s; ctx.strokeStyle='#fff'; ctx.stroke();
      });
      const h=handlePt(b);
      const top=[(q[2][0]+q[3][0])/2,(q[2][1]+q[3][1])/2];
      ctx.beginPath(); ctx.moveTo(top[0],top[1]); ctx.lineTo(h[0],h[1]);
      ctx.strokeStyle='#ff7a00'; ctx.lineWidth=1.6/view.s; ctx.stroke();
      ctx.beginPath(); ctx.arc(h[0],h[1],5.4/view.s,0,6.2832);
      ctx.fillStyle='#fff'; ctx.fill(); ctx.strokeStyle='#ff7a00'; ctx.lineWidth=2/view.s; ctx.stroke();
    }
  });

  if(draft){
    ctx.beginPath();
    draft.forEach((p,k)=> k?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));
    ctx.strokeStyle='#e05a00'; ctx.lineWidth=3/view.s; ctx.setLineDash([8/view.s,5/view.s]);
    ctx.stroke(); ctx.setLineDash([]);
    draft.forEach(p=>{ ctx.beginPath(); ctx.arc(p[0],p[1],4/view.s,0,6.2832); ctx.fillStyle='#e05a00'; ctx.fill(); });
  }
  ctx.restore();
  zoomEl.textContent=Math.round(view.s*100)+'%';
  if(!drag) updateStats();
}

cv.addEventListener('wheel', e=>{
  e.preventDefault();
  const p=toImg(e), k=e.deltaY<0?1.15:1/1.15;
  const ns=Math.max(0.04,Math.min(8,view.s*k));
  view.x+=p.x*(view.s-ns); view.y+=p.y*(view.s-ns); view.s=ns; draw();
},{passive:false});
cv.addEventListener('contextmenu', e=>e.preventDefault());

cv.addEventListener('mousedown', e=>{
  const p=toImg(e);
  if(e.button===2||e.button===1){ drag={type:'pan',last:{x:e.clientX,y:e.clientY}}; return; }
  if(mode==='det'){ drag={type:'det', a:p, b:p}; return; }
  if(mode==='seg'){
    if(!draft){ draft=[[p.x,p.y]]; draw(); return; }
    const a={x:draft[0][0], y:draft[0][1]};
    if(snapOn) document.body.style.cursor='progress';
    const path = snapOn ? traceSeg(a,p) : [[a.x,a.y],[p.x,p.y]];
    document.body.style.cursor='';
    pushHist();
    cur().segs.push({id:'S'+String(cur().nextSeg++).padStart(2,'0'), pts:path});
    draft=null; save(); draw(); renderLists();
    return;
  }
  if(mode==='new'){ drag={type:'new',a:p,b:p}; return; }

  const bs=cur().boxes;
  if(sel>=0){
    const b=bs[sel], q=pts(b), h=handlePt(b);
    if(Math.hypot(h[0]-p.x,h[1]-p.y) < 10/view.s){ pushHist(); drag={type:'rotate',idx:sel}; return; }
    for(let k=0;k<4;k++) if(Math.hypot(q[k][0]-p.x,q[k][1]-p.y) < 9/view.s){ pushHist(); drag={type:'resize',k,idx:sel}; return; }
  }
  const i=hit(p);
  if(i>=0){ sel=i; pushHist(); drag={type:'move',idx:i,last:p}; syncPanel(); }
  else {
    const si=hitSeg(p);
    if(si>=0){ pickSeg(si); return; }
    sel=-1; selSeg=-1; drag={type:'pan',last:{x:e.clientX,y:e.clientY}}; syncPanel();
  }
  draw();
});

cv.addEventListener('mousemove', e=>{
  if(!drag) return;
  const p=toImg(e), bs=cur().boxes;
  if(drag.type==='pan'){ view.x+=e.clientX-drag.last.x; view.y+=e.clientY-drag.last.y; drag.last={x:e.clientX,y:e.clientY}; draw(); return; }
  if(drag.type==='new'||drag.type==='det'){ drag.b=p; draw(); dashedRect(drag.a,drag.b); return; }
  if(drag.type==='move'){
    const b=bs[drag.idx];
    b.cx+=p.x-drag.last.x; b.cy+=p.y-drag.last.y;
    b.status=b.status==='new'?'new':'mod';
    drag.last=p; draw(); return;
  }
  if(drag.type==='rotate'){
    const b=bs[drag.idx];
    const deg=Math.atan2(p.y-b.cy,p.x-b.cx)*180/Math.PI+90;
    b.ang=((deg%180)+180)%180;
    b.status=b.status==='new'?'new':'mod';
    draw(); return;
  }
  if(drag.type==='resize'){
    const b=bs[drag.idx], sign=[[-1,-1],[1,-1],[1,1],[-1,1]][drag.k];
    const a=b.ang*Math.PI/180, c=Math.cos(a), s=Math.sin(a);
    const fx=b.cx+c*(-sign[0]*b.w/2)-s*(-sign[1]*b.h/2);
    const fy=b.cy+s*(-sign[0]*b.w/2)+c*(-sign[1]*b.h/2);
    const dx=p.x-fx, dy=p.y-fy;
    const lx=c*dx+s*dy, ly=-s*dx+c*dy;
    const nw=Math.max(10,Math.abs(lx)), nh=Math.max(6,Math.abs(ly));
    b.w=nw; b.h=nh;
    b.cx=fx+c*(sign[0]*nw/2)-s*(sign[1]*nh/2);
    b.cy=fy+s*(sign[0]*nw/2)+c*(sign[1]*nh/2);
    b.status=b.status==='new'?'new':'mod';
    draw(); return;
  }
});
function dashedRect(a,b){
  ctx.save(); ctx.setTransform(DPR*view.s,0,0,DPR*view.s,DPR*view.x,DPR*view.y);
  ctx.beginPath(); ctx.rect(Math.min(a.x,b.x),Math.min(a.y,b.y),Math.abs(b.x-a.x),Math.abs(b.y-a.y));
  ctx.setLineDash([6/view.s,4/view.s]); ctx.lineWidth=2/view.s; ctx.strokeStyle='#13a05a'; ctx.stroke(); ctx.restore();
}

window.addEventListener('mouseup', ()=>{
  if(!drag) return;
  if(drag.type==='new'){
    const a=drag.a,b=drag.b, w=Math.abs(b.x-a.x), h=Math.abs(b.y-a.y);
    if(w>5&&h>4){
      pushHist();
      cur().boxes.push(mk(cur().nextId++, Math.min(a.x,b.x)+w/2, Math.min(a.y,b.y)+h/2, w, h, 0));
    }
  } else if(drag.type==='det'){
    const a=drag.a,b=drag.b, w=Math.abs(b.x-a.x), h=Math.abs(b.y-a.y);
    if(w>12&&h>10){
      drag=null; draw();
      runDetect({x0:Math.min(a.x,b.x), y0:Math.min(a.y,b.y), x1:Math.max(a.x,b.x), y1:Math.max(a.y,b.y)});
      return;
    }
  } else if(drag.type!=='pan'){ snapBox(drag.idx); save(); }
  drag=null; draw(); renderLists();
});

function snapBox(onlyIdx, force){
  const bs=cur().boxes, sg=cur().segs;
  if(!sg.length) return;
  const single=(onlyIdx!==undefined && onlyIdx!==null);
  const list=single?[onlyIdx]:bs.map((_,i)=>i);
  list.forEach(i=>{
    const b=bs[i]; if(!b) return;
    if(single && b.manual && !force) return;   // 手动指定的框不被拖动覆盖
    let best=null, bd=1e9;
    sg.forEach(s=>{ const d=distPoly({x:b.cx,y:b.cy}, s.pts); if(d<bd){bd=d;best=s;} });
    b.seg=(best&&bd<140)?best.id:null;
    if(force) b.manual=false;
  });
}

function pushHist(){ history.push(JSON.stringify(cur())); if(history.length>80) history.shift(); }
document.getElementById('undo').onclick=()=>{
  if(!history.length) return;
  state[IMGS[imgIdx].key]=JSON.parse(history.pop());
  sel=-1; selSeg=-1; save(); renderLists(); syncPanel(); draw();
};
document.getElementById('del').onclick=()=>{
  if(sel<0) return;
  pushHist();
  const b=cur().boxes[sel];
  if(b.status!=='new'){ cur().del=cur().del||[]; cur().del.push(b.id); }
  cur().boxes.splice(sel,1); sel=-1; save(); renderLists(); syncPanel(); draw();
};
document.getElementById('dup').onclick=()=>{
  if(sel<0) return;
  pushHist();
  const b=cur().boxes[sel], n=mk(cur().nextId++, b.cx+14, b.cy+14, b.w, b.h, b.ang);
  n.note=b.note; n.seg=b.seg; n.status='new';
  cur().boxes.push(n); save(); renderLists(); draw();
};
function rotateSel(d){
  if(sel<0) return;
  pushHist();
  const b=cur().boxes[sel];
  b.ang=((b.ang+d)%180+180)%180;
  b.status=b.status==='new'?'new':'mod';
  save(); draw(); syncPanel();
}
document.getElementById('rotL').onclick=()=>rotateSel(-5);
document.getElementById('rotR').onclick=()=>rotateSel(5);
document.getElementById('note').oninput=e=>{
  if(sel<0) return;
  cur().boxes[sel].note=e.target.value; save(); updateStats(); renderLists();
};
document.getElementById('segSel').onchange=e=>{
  if(sel<0) return;
  pushHist();
  cur().boxes[sel].seg=e.target.value||null;
  cur().boxes[sel].manual=!!e.target.value;
  save(); draw(); syncPanel(); renderLists();
};
document.getElementById('autoAssign').onclick=()=>{
  if(!cur().segs.length){ alert('先画至少一条路段'); return; }
  pushHist(); snapBox(null,true); save(); draw(); renderLists();
};
function joinPts(A,B){
  const rev=a=>a.slice().reverse();
  let best=null;
  [[A,B],[A,rev(B)],[rev(A),B],[rev(A),rev(B)]].forEach(([a,b])=>{
    const d=Math.hypot(a[a.length-1][0]-b[0][0], a[a.length-1][1]-b[0][1]);
    if(!best||d<best.d) best={d, pts:a.concat(b)};
  });
  const out=[];
  best.pts.forEach(p=>{
    const q=out[out.length-1];
    if(!q || Math.hypot(p[0]-q[0], p[1]-q[1])>1.0) out.push(p);
  });
  return out;
}
function doMerge(i,j){
  const sg=cur().segs;
  const a=sg[i], b=sg[j];
  if(!a||!b||i===j) return;
  pushHist();
  const keepId=a.id, dropId=b.id;
  a.pts=joinPts(a.pts,b.pts);
  cur().boxes.forEach(x=>{ if(x.seg===dropId){ x.seg=keepId; x.manual=true; } });
  const idx=sg.indexOf(b);
  sg.splice(idx,1);
  selSeg=Math.max(0, sg.indexOf(a));
  save(); draw(); renderLists();
}
function setMergeBtn(){
  const el=document.getElementById('mergeSeg');
  el.classList.toggle('on', mergeMode);
  el.textContent = mergeMode ? '点两条…' : '合并';
}
function pickSeg(i){
  if(mergeMode){
    if(mergePick.includes(i)) return;
    mergePick.push(i);
    selSeg=i; sel=-1; syncPanel(); draw(); renderLists();
    if(mergePick.length===2){
      const [a,b]=mergePick; mergePick=[]; mergeMode=false; setMergeBtn(); doMerge(a,b);
    }
    return;
  }
  selSeg=i; sel=-1; syncPanel(); draw(); renderLists();
}
document.getElementById('mergeSeg').onclick=()=>{
  if(cur().segs.length<2){ alert('至少要有两条路段'); return; }
  mergeMode=!mergeMode; mergePick=[]; setMergeBtn();
  if(mergeMode) alert('合并模式：依次点两条要合并的路段（列表或图上都行），第二条点完即合并');
};
document.getElementById('bindSeg').onclick=()=>{
  if(sel<0){ alert('先选中一个框'); return; }
  if(selSeg<0){ alert('先在路段列表或图上选一条路段'); return; }
  pushHist();
  const b=cur().boxes[sel];
  b.seg=cur().segs[selSeg].id; b.manual=true;
  save(); draw(); syncPanel(); renderLists();
};
document.getElementById('delSeg').onclick=()=>{
  if(selSeg<0) return;
  pushHist();
  const id=cur().segs[selSeg].id;
  cur().segs.splice(selSeg,1);
  cur().boxes.forEach(b=>{ if(b.seg===id) b.seg=null; });
  selSeg=-1; save(); draw(); renderLists();
};
document.getElementById('mSel').onclick=()=>{ mode='sel'; setMode(); };
document.getElementById('mNew').onclick=()=>{ mode='new'; setMode(); };
document.getElementById('mSeg').onclick=()=>{ mode='seg'; draft=null; setMode(); };
document.getElementById('mDet').onclick=()=>{ mode='det'; draft=null; setMode(); };
document.getElementById('detAll').onclick=()=>{
  const im=IMGS[imgIdx];
  if(!confirm('对整张图跑一遍检测？会追加候选框（可能较多），可再逐个删。')) return;
  runDetect({x0:0,y0:0,x1:im.w,y1:im.h});
};
function setMode(){
  ['mSel','mNew','mSeg','mDet'].forEach(id=>document.getElementById(id).classList.remove('on'));
  document.getElementById(mode==='sel'?'mSel':mode==='new'?'mNew':mode==='seg'?'mSeg':'mDet').classList.add('on');
  cv.style.cursor=mode==='sel'?'default':'crosshair';
  if(mode==='seg') draft=null;
}
document.getElementById('toggleNum').onclick=e=>{ showNum=!showNum; e.target.classList.toggle('on',showNum); draw(); };
document.getElementById('toggleSnap').onclick=e=>{ snapOn=!snapOn; e.target.classList.toggle('on',snapOn);
  e.target.textContent = snapOn?'沿路吸附':'直连'; };
document.getElementById('fit').onclick=()=>fit();
document.addEventListener('keydown', e=>{
  const typing=document.activeElement && document.activeElement.tagName==='INPUT';
  if(e.key==='Escape'){ if(draft){draft=null;draw();} else {sel=-1;selSeg=-1;syncPanel();draw();} }
  if(typing) return;
  if(e.key==='Enter'&&draft){ commitSeg(); }
  if(e.key==='Delete'||e.key==='Backspace'){ if(sel>=0){ e.preventDefault(); document.getElementById('del').click(); } }
  if(e.key==='['){ rotateSel(-5); }
  if(e.key===']'){ rotateSel(5); }
  if(e.key==='v'||e.key==='V'){ mode='sel'; setMode(); }
  if(e.key==='n'||e.key==='N'){ mode='new'; setMode(); }
  if(e.key==='s'||e.key==='S'){ mode='seg'; setMode(); }
  if(e.key==='d'||e.key==='D'){ mode='det'; setMode(); }
  if((e.key==='r'||e.key==='R') && !typing){ if(readMode) exitRead(); else enterRead(); }
  if(e.key==='f'||e.key==='F'){ fit(); }
});
function commitSeg(){
  if(!draft||draft.length<2){ draft=null; return; }
  pushHist();
  cur().segs.push({id:'S'+String(cur().nextSeg++).padStart(2,'0'), pts:draft.map(p=>[p[0],p[1]])});
  draft=null; save(); draw(); renderLists();
}

function parseCode(t){
  if(!t) return null;
  const m=String(t).trim().match(/^(\d{1,2})\s*-\s*(\d)\s*-\s*(\d{1,2})/);
  if(!m) return null;
  const n=+m[1], g=+m[2], act=+m[3];
  if(!DWELL[act]) return null;
  return {n,g,act,dwell:DWELL[act]};
}
function updateStats(){
  const bs=cur().boxes, sg=cur().segs;
  const tb=document.querySelector('#stats tbody');
  let rows=[], tn=0,tm=0,tf=0,unread=0;
  const groups=sg.map(s=>({id:s.id,list:bs.filter(b=>b.seg===s.id)}));
  const orphan=bs.filter(b=>!b.seg||!sg.some(s=>s.id===b.seg));
  groups.push({id:'—',list:orphan});
  groups.forEach(g=>{
    let n=0,m=0,f=0,mx=0,ot=0,dw={1:0,2:0,3:0};
    g.list.forEach(b=>{
      const p=parseCode(b.note);
      if(p){ n+=p.n; if(p.g===1) m+=p.n; else if(p.g===2) f+=p.n; else if(p.g===3) mx+=p.n; else ot+=p.n; dw[p.dwell]+=p.n; }
      else unread++;
    });
    tn+=n; tm+=m; tf+=f;
    let dm=0,best=-1;
    [1,2,3].forEach(k=>{ if(dw[k]>best){best=dw[k];dm=k;} });
    rows.push(`<tr><td>${g.id}</td><td>${g.list.length}</td><td>${n||''}</td><td>${m||''}</td><td>${f||''}</td><td>${best>0?dm:''}</td></tr>`);
  });
  if(tb) tb.innerHTML=rows.join('');
  const el=document.getElementById('sum');
  if(el) el.innerHTML=`合计 <b>${tn}</b> 人（男 ${tm} / 女 ${tf}）· 框 ${bs.length} 个 · 未读数 ${unread}`;
  const sc=document.getElementById('segCount'); if(sc) sc.textContent=sg.length;
}
function renderLists(){
  const sl=document.getElementById('segList');
  if(sl){
    const bs=cur().boxes;
    sl.innerHTML=cur().segs.map((s,i)=>{
      const c=bs.filter(b=>b.seg===s.id).length;
      return `<div class="item ${i===selSeg?'sel':''}" data-i="${i}"><span>${s.id}</span><span class="m">${c} 框 · ${s.pts.length} 点</span></div>`;
    }).join('')||'<div class="tip" style="padding:6px 12px">还没有路段。切到「画路段」，沿路点几下，回车结束。</div>';
    [...sl.children].forEach(el=>{ if(el.dataset.i!==undefined) el.onclick=()=>{ pickSeg(+el.dataset.i); }; });
  }
  const ss=document.getElementById('segSel');
  if(ss){
    const v=sel>=0?cur().boxes[sel].seg:null;
    ss.innerHTML='<option value="">— 未归属路段 —</option>'+
      cur().segs.map(s=>`<option value="${s.id}" ${v===s.id?'selected':''}>${s.id}</option>`).join('');
  }
  updateStats();
}
function syncPanel(){
  const el=document.getElementById('selInfo');
  if(sel<0){
    if(selSeg>=0 && cur().segs[selSeg]){
      const sg=cur().segs[selSeg];
      const n=cur().boxes.filter(b=>b.seg===sg.id).length;
      el.innerHTML=`已选路段 <b>${sg.id}</b> · ${sg.pts.length} 点 · 高亮 <b>${n}</b> 个框`;
    } else el.textContent='未选中';
    document.getElementById('note').value='';
  }
  else{
    const b=cur().boxes[sel];
    el.innerHTML=`框 <b>${b.id}</b> · ${b.w.toFixed(0)}×${b.h.toFixed(0)}px · ${b.ang.toFixed(0)}°`
      +(b.seg?` · 路段 <b style="color:#e8890c">${b.seg}</b>`:' · 未归属')
      +(b.manual?` <span style="color:#1a6dff">手动</span>`:'');
    document.getElementById('note').value=b.note||'';
  }
  renderLists();
}


/* ---------- 读数模式 ---------- */
let readMode=false, readIdx=-1;
function fmtCode(raw){
  const s=String(raw||"").trim();
  if(!s) return "";
  if(s.includes("-")) return s;
  const d=s.replace(/\D/g,"");
  if(!d) return "";
  const cands=[];
  for(const a of [1,2]){
    if(d.length < a+2) continue;
    const g=+d.slice(a,a+1), c=d.slice(a+1);
    if(c.length<1||c.length>2) continue;
    const n=+d.slice(0,a), act=+c;
    if(n<1||n>60||g<1||g>3||act<1||act>13) continue;
    cands.push({a, s:`${n}-${g}-${act}`});
  }
  return cands.length ? cands[0].s : "";
}

function enterRead(){
  const bs=cur().boxes;
  if(!bs.length){ alert('这张图还没有框'); return; }
  readMode=true;
  document.getElementById('readCard').style.display='block';
  let i = sel>=0 ? sel : bs.findIndex(b=>!b.note);
  readIdx = i<0 ? 0 : i;
  focusBox();
}
function exitRead(){
  readMode=false;
  document.getElementById('readCard').style.display='none';
  fit();
}
function focusBox(){
  const bs=cur().boxes; if(!bs.length) return;
  readIdx=(readIdx%bs.length+bs.length)%bs.length;
  const b=bs[readIdx];
  const need=Math.min(stage.clientWidth*0.55/Math.max(b.w,20), stage.clientHeight*0.5/Math.max(b.h,10));
  view.s=Math.max(0.4, Math.min(14, need));
  view.x=stage.clientWidth/2-b.cx*view.s;
  view.y=stage.clientHeight/2-24-b.cy*view.s;
  sel=readIdx; syncPanel(); draw();
  const m0=/^(\d{1,2})-(\d)-(\d{1,2})$/.exec(b.note||'');
  document.getElementById('rcN').value=m0?m0[1]:'';
  document.getElementById('rcG').value=m0?m0[2]:'';
  document.getElementById('rcA').value=m0?m0[3]:'';
  const fm=document.getElementById('rcFmt'); if(fm){ fm.textContent=''; fm.className=''; }
  document.getElementById('rcTitle').textContent=`框 ${b.id}`+(b.seg?` · 路段 ${b.seg}`:' · 未归属');
  const done=bs.filter(x=>x.note).length;
  document.getElementById('rcProgress').textContent=`${readIdx+1} / ${bs.length} · 已填 ${done}`;
  const sp=document.getElementById('rcSuggest');
  if(b.suggest && !b.note){
    sp.style.display='block';
    sp.innerHTML=`模型建议 <b>${b.suggest}</b> <button id="rcUse" style="padding:1px 8px;font-size:12px">采用</button>`;
    document.getElementById('rcUse').onclick=()=>{
      const mm=/^(\d{1,2})-(\d)-(\d{1,2})$/.exec(b.suggest||'');
      if(mm){
        document.getElementById('rcN').value=mm[1];
        document.getElementById('rcG').value=mm[2];
        document.getElementById('rcA').value=mm[3];
        rcCheck(); document.getElementById('rcN').focus();
      }
    };
  } else sp.style.display='none';
  const inp=document.getElementById('rcN'); if(inp){ inp.focus(); inp.select(); }
}
function stepBox(d){
  const bs=cur().boxes; if(!bs.length) return;
  readIdx=(readIdx+d+bs.length)%bs.length;
  focusBox();
}
function commitRead(){
  const bs=cur().boxes, b=bs[readIdx]; if(!b) return false;
  const v=rcCheck();
  const {n,g,a}=rcVals();
  if(!n&&!g&&!a){ b.note=''; save(); renderLists(); return true; }
  if(!v) return false;
  b.note=v; save(); renderLists(); return true;
}
document.getElementById('readBtn').onclick=()=>{ readMode?exitRead():enterRead(); };
document.getElementById('rcExit').onclick=exitRead;
document.getElementById('rcPrev').onclick=()=>{ commitRead(); stepBox(-1); };
document.getElementById('rcNext').onclick=()=>{ commitRead(); stepBox(1); };
document.getElementById('rcSkip').onclick=()=>stepBox(1);
let rcTimer=null;
function rcVals(){
  return {
    n: document.getElementById('rcN').value.trim(),
    g: document.getElementById('rcG').value.trim(),
    a: document.getElementById('rcA').value.trim()
  };
}
function rcCheck(){
  const {n,g,a}=rcVals();
  const el=document.getElementById('rcFmt');
  const gi=document.getElementById('rcG'), ni=document.getElementById('rcN'), ai=document.getElementById('rcA');
  [ni,gi,ai].forEach(x=>x.classList.remove('bad'));
  if(!n&&!g&&!a){ el.textContent=''; el.className=''; return null; }
  if(!n||!g||!a){ el.textContent='三项都要填'; el.className='bad'; return null; }
  const N=+n, G=+g, A=+a;
  if(!(N>=1&&N<=60)){ ni.classList.add('bad'); el.textContent='人数需 1–60'; el.className='bad'; return null; }
  if(!(G>=1&&G<=3)){ gi.classList.add('bad'); el.textContent='性别码非法：只允许 1=男 2=女 3=均衡'; el.className='bad'; return null; }
  if(!(A>=1&&A<=13)){ ai.classList.add('bad'); el.textContent='活动需 1–13'; el.className='bad'; return null; }
  el.textContent='→ '+N+'-'+G+'-'+A; el.className='';
  return `${N}-${G}-${A}`;
}
function rcArrow(step){
  const order=['rcN','rcG','rcA'];
  const i=order.indexOf(document.activeElement && document.activeElement.id);
  const j=(i+step+order.length)%order.length;
  document.getElementById(order[j]).focus();
}
function rcSchedule(){
  clearTimeout(rcTimer);
  if(!rcCheck()) return;
  rcTimer=setTimeout(()=>{ if(readMode && commitRead()) stepBox(1); }, 1400);
}
['rcN','rcG','rcA'].forEach(id=>{
  const el=document.getElementById(id);
  el.addEventListener('input', ()=>{
    el.value=el.value.replace(/\D/g,'');
    clearTimeout(rcTimer);
    // 性别填完直接跳到活动
    if(id==='rcG' && el.value.length===1 && /^[123]$/.test(el.value)){
      document.getElementById('rcA').focus();
    }
    const code=rcCheck();
    if(!code) return;
    if(id==='rcA' && el.value.length>=2){ if(commitRead()) stepBox(1); return; }
    rcTimer=setTimeout(()=>{ if(readMode && commitRead()) stepBox(1); }, 1400);
  });
  el.addEventListener('keydown', e=>{
    if(e.key==='Enter'){ e.preventDefault(); clearTimeout(rcTimer); if(rcCheck() && commitRead()) stepBox(1); }
    if(e.key==='Backspace' && el.value==='' ){ e.preventDefault(); rcArrow(-1); }
    if(e.key===' '){ e.preventDefault(); rcArrow(1); }
    if(e.key==='Escape'){ exitRead(); }
  });
});


function buildTabs(){
  const t=document.getElementById('tabs');
  t.innerHTML=IMGS.map((m,i)=>`<button data-i="${i}" class="${i===imgIdx?'on':''}">${m.label}</button>`).join('');
  [...t.children].forEach(el=>el.onclick=()=>{
    imgIdx=+el.dataset.i; sel=-1; selSeg=-1; history=[]; draft=null;
    initState(imgIdx); buildTabs(); syncPanel(); fit();
  });
}
function download(name,text,type){
  const blob=new Blob([text],{type:type||'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=name; a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),3000);
}
document.getElementById('expJson').onclick=()=>{
  const out={};
  for(const m of IMGS){
    const st=state[m.key]||{boxes:[],segs:[],del:[]};
    out[m.key]={ boxes: st.boxes.map(b=>({id:b.id,cx:b.cx,cy:b.cy,w:b.w,h:b.h,ang:b.ang,
                    pts:pts(b),status:b.status,note:b.note,seg:b.seg})),
                 segs: st.segs, deleted: st.del||[] };
  }
  download('标注结果.json',JSON.stringify(out,null,1));
};
document.getElementById('expCsv').onclick=()=>{
  const head='image,box_id,seg,note,n,g,act,dwell,cx,cy,w,h,ang,x1,y1,x2,y2,x3,y3,x4,y4';
  let rows=[head], segRows=['image,seg_id,points,box_count,people'];
  for(const m of IMGS){
    const st=state[m.key]; if(!st) continue;
    for(const b of st.boxes){
      const p=parseCode(b.note), q=pts(b);
      rows.push([m.key,b.id,b.seg||'',`"${(b.note||'').replace(/"/g,'')}"`,
                 p?p.n:'',p?p.g:'',p?p.act:'',p?p.dwell:'',
                 b.cx.toFixed(1),b.cy.toFixed(1),b.w.toFixed(1),b.h.toFixed(1),b.ang.toFixed(1),
                 ...q.flat().map(v=>v.toFixed(1))].join(','));
    }
    for(const s of (st.segs||[])){
      const list=st.boxes.filter(b=>b.seg===s.id);
      const people=list.reduce((a,b)=>{const p=parseCode(b.note);return a+(p?p.n:0);},0);
      segRows.push([m.key,s.id,`"${s.pts.map(p=>p.map(v=>v.toFixed(0)).join(' ')).join(';')}"`,list.length,people].join(','));
    }
  }
  download('标注结果.csv','\ufeff'+rows.join('\n')+'\n\n'+segRows.join('\n'),'text/csv');
};
document.getElementById('impSug').onclick=()=>document.getElementById('sugFile').click();
document.getElementById('sugFile').onchange=e=>{
  const f=e.target.files[0]; if(!f) return;
  const rd=new FileReader();
  rd.onload=()=>{
    try{
      const all=JSON.parse(rd.result);
      let n=0;
      for(const key in all){
        const st=state[key]; if(!st||!st.boxes) continue;
        const map=all[key];
        st.boxes.forEach(b=>{
          const v=map[String(b.id)] || map[b.id];
          if(v){ b.suggest=v; n++; }
        });
      }
      save(); draw(); renderLists();
      alert(`已导入 ${n} 条模型建议，读数时会在卡片上显示`);
    }catch(err){ alert('解析失败：'+err.message); }
  };
  rd.readAsText(f);
  e.target.value='';
};
document.getElementById('reset').onclick=()=>{
  if(!confirm('清空当前图的全部修改（框、路段、读数）？')) return;
  localStorage.removeItem(VER+IMGS[imgIdx].key);
  initState(imgIdx); sel=-1; selSeg=-1; draft=null; history=[]; syncPanel(); draw();
};

IMGS.forEach((m,i)=>{ initState(i); const mi=new Image(); mi.onload=()=>{ m._maskImg=mi; }; mi.src=m.mask; });
buildTabs(); syncPanel(); resize(); fit();
window.addEventListener('resize', resize);
</script>
</body>
</html>
"""

os.makedirs(OUTDIR, exist_ok=True)
html = HTML.replace("__IMAGES__", json.dumps(imgs, ensure_ascii=False))
open(OUT, "w", encoding="utf-8").write(html)
print("saved", OUT, round(len(html) / 1024), "KB")
