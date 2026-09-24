"""
เว็บแดชบอร์ดตรวจจับกุ้งแบบเรียลไทม์ (FastAPI)
เว็บนี้ "รับข้อมูล" จากกล้อง/AI ที่รันอยู่อีกเครื่อง (camera_client.py) แล้วแสดงผลสด
เว็บไม่ต้องรัน AI เอง จึงเบา ไม่กิน RAM และไม่ต้องมี best.pt บน Render

ตั้งค่าบน Render:
  Start Command : python app.py   (เหมือนเดิม)
  Environment   : API_KEY = รหัสลับที่คุณตั้งเอง (ต้องตรงกับใน camera_client.py)
                  PYTHON_VERSION = 3.11.9
"""

import base64
import os
import time
from collections import deque

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

API_KEY = os.environ.get("API_KEY", "change-me")

app = FastAPI(title="Shrimp Realtime Dashboard")
state = {"counts": {}, "fps": 0.0, "frame": None, "ts": 0.0}
history = deque(maxlen=120)  # ยอดรวมย้อนหลัง 120 ครั้งล่าสุด


class Report(BaseModel):
    counts: dict[str, int] = {}
    fps: float = 0.0
    frame_b64: str | None = None


@app.post("/api/report")
def report(data: Report, x_api_key: str = Header(default="")):
    """กล้อง/AI ส่งผลตรวจจับเข้ามาที่นี่"""
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="bad api key")
    frame = None
    if data.frame_b64:
        try:
            frame = base64.b64decode(data.frame_b64)
        except Exception:
            raise HTTPException(status_code=400, detail="bad frame")
    state.update(counts=data.counts, fps=data.fps, frame=frame, ts=time.time())
    history.append(sum(data.counts.values()))
    return {"ok": True}


@app.get("/api/latest")
def latest():
    has = state["ts"] > 0
    age = time.time() - state["ts"] if has else 0
    return {
        "has_data": has,
        "online": has and age < 10,
        "age": age,
        "ts": state["ts"],
        "counts": state["counts"],
        "total": sum(state["counts"].values()),
        "fps": state["fps"],
        "has_frame": state["frame"] is not None,
        "history": list(history),
    }


@app.get("/api/frame")
def frame():
    if state["frame"] is None:
        return Response(status_code=204)
    return Response(state["frame"], media_type="image/jpeg", headers={"Cache-Control": "no-store"})


PAGE = """<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ระบบตรวจจับกุ้งแบบเรียลไทม์</title>
<style>
:root{--bg:#0b1a24;--card:#12283a;--line:#1f3d55;--tx:#e6f1f7;--mut:#8fb0c4;--acc:#f97316}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font-family:'Noto Sans Thai',system-ui,sans-serif}
header{padding:22px 20px;background:linear-gradient(135deg,#0f766e,#1e3a8a);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
h1{margin:0;font-size:1.5rem}
.pill{padding:5px 14px;border-radius:999px;font-size:.9rem;background:#3b1d1d;color:#fca5a5}
.pill.on{background:#0f3d2a;color:#86efac}
main{max-width:1100px;margin:20px auto;padding:0 16px;display:grid;gap:16px;grid-template-columns:2fr 1fr}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
.wide{grid-column:1/-1}
.video{aspect-ratio:4/3;background:#08131b;border-radius:10px;display:flex;align-items:center;justify-content:center;color:var(--mut);overflow:hidden}
.video img{width:100%;height:100%;object-fit:contain;display:none}
.big{font-size:3.6rem;font-weight:700;color:var(--acc);line-height:1}
.mut{color:var(--mut);font-size:.85rem}
.row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--line)}
canvas{width:100%;height:180px;display:block}
@media(max-width:760px){main{grid-template-columns:1fr}}
</style></head><body>
<header><h1>🦐 ระบบตรวจจับกุ้งแบบเรียลไทม์</h1><span id="pill" class="pill">● กำลังเชื่อมต่อ...</span></header>
<main>
  <div class="card"><div class="mut" style="margin-bottom:8px">ภาพสดจากกล้อง</div>
    <div class="video"><img id="frame" alt="live"><span id="ph">รอสัญญาณจากกล้อง...</span></div></div>
  <div class="card">
    <div class="mut">จำนวนกุ้งในภาพตอนนี้</div><div class="big" id="total">-</div><div class="mut">ตัว</div>
    <div class="row" style="margin-top:14px"><span class="mut">ความเร็ว AI</span><b><span id="fps">-</span> FPS</b></div>
    <div class="row"><span class="mut">อัปเดตล่าสุด</span><b id="age">-</b></div>
    <div class="mut" style="margin:14px 0 4px">แยกตามชนิด</div><div id="classes"></div>
  </div>
  <div class="card wide"><div class="mut" style="margin-bottom:8px">จำนวนกุ้งย้อนหลัง</div><canvas id="chart"></canvas></div>
</main>
<script>
const $=id=>document.getElementById(id);let lastTs=0;
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function draw(h){const c=$('chart'),x=c.getContext('2d');c.width=c.clientWidth;c.height=180;
  x.clearRect(0,0,c.width,c.height);if(!h.length)return;
  const m=Math.max(5,...h),w=c.width,ht=c.height-24;
  x.strokeStyle='#f97316';x.lineWidth=2;x.beginPath();
  h.forEach((v,i)=>{const px=h.length>1?i/(h.length-1)*w:0,py=ht-v/m*ht+12;i?x.lineTo(px,py):x.moveTo(px,py)});
  x.stroke();x.fillStyle='#8fb0c4';x.font='12px sans-serif';x.fillText('สูงสุด '+m,6,12)}
async function tick(){
  try{
    const d=await(await fetch('/api/latest',{cache:'no-store'})).json();
    $('pill').textContent=d.online?'● ออนไลน์':'● กล้องออฟไลน์';$('pill').className='pill'+(d.online?' on':'');
    $('total').textContent=d.has_data?d.total:'-';
    $('fps').textContent=d.has_data?d.fps.toFixed(1):'-';
    $('age').textContent=d.has_data?Math.round(d.age)+' วินาทีที่แล้ว':'-';
    $('classes').innerHTML=Object.entries(d.counts).sort((a,b)=>b[1]-a[1])
      .map(([k,v])=>'<div class="row"><span>'+esc(k)+'</span><b>'+v+'</b></div>').join('')||'<div class="mut">ยังไม่พบกุ้ง</div>';
    if(d.has_frame&&d.ts!==lastTs){lastTs=d.ts;$('frame').src='/api/frame?t='+d.ts;$('frame').style.display='block';$('ph').style.display='none'}
    draw(d.history);
  }catch(e){$('pill').textContent='● ติดต่อเซิร์ฟเวอร์ไม่ได้';$('pill').className='pill'}
  setTimeout(tick,1000);
}
tick();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
