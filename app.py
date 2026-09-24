```python
import base64
import os
import time
from collections import deque

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field


# =========================================================
# CONFIG
# =========================================================

API_KEY = os.environ.get("API_KEY", "change-me")

app = FastAPI(
    title="Shrimp Realtime Dashboard",
    version="1.0.0"
)


# =========================================================
# REALTIME STATE
# =========================================================

state = {
    "counts": {},
    "fps": 0.0,
    "frame": None,
    "ts": 0.0,
}

# เก็บจำนวนกุ้งย้อนหลัง
history = deque(maxlen=120)


# =========================================================
# DATA MODEL
# =========================================================

class Report(BaseModel):
    counts: dict[str, int] = Field(default_factory=dict)
    fps: float = 0.0
    frame_b64: str | None = None


# =========================================================
# RECEIVE DATA FROM CAMERA / AI
# =========================================================

@app.post("/api/report")
def report(
    data: Report,
    x_api_key: str = Header(default="")
):
    """
    camera_client.py ส่งข้อมูลมายัง endpoint นี้
    """

    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    frame = None

    # -------------------------
    # Decode image
    # -------------------------

    if data.frame_b64:

        try:
            frame = base64.b64decode(
                data.frame_b64,
                validate=True
            )

        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid base64 image"
            )

    # -------------------------
    # Clean counts
    # -------------------------

    clean_counts = {}

    for name, value in data.counts.items():

        try:
            value = int(value)
        except Exception:
            value = 0

        if value < 0:
            value = 0

        clean_counts[str(name)] = value

    # -------------------------
    # Update state
    # -------------------------

    state["counts"] = clean_counts
    state["fps"] = max(0.0, float(data.fps))
    state["frame"] = frame
    state["ts"] = time.time()

    total = sum(clean_counts.values())

    history.append(total)

    return {
        "ok": True,
        "total": total
    }


# =========================================================
# LATEST DATA
# =========================================================

@app.get("/api/latest")
def latest():

    has_data = state["ts"] > 0

    age = (
        time.time() - state["ts"]
        if has_data
        else 0
    )

    online = (
        has_data
        and age < 10
    )

    return {
        "has_data": has_data,
        "online": online,
        "age": age,
        "ts": state["ts"],
        "counts": state["counts"],
        "total": sum(state["counts"].values()),
        "fps": state["fps"],
        "has_frame": state["frame"] is not None,
        "history": list(history),
    }


# =========================================================
# CAMERA FRAME
# =========================================================

@app.get("/api/frame")
def frame():

    if state["frame"] is None:
        return Response(status_code=204)

    return Response(
        state["frame"],
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate"
        }
    )


# =========================================================
# DASHBOARD
# =========================================================

PAGE = r"""
<!DOCTYPE html>

<html lang="th">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>ระบบตรวจจับกุ้ง AI</title>

<style>

*{
    box-sizing:border-box;
}

body{
    margin:0;
    background:#07111c;
    color:#e8f2f8;
    font-family:
        "Noto Sans Thai",
        "Segoe UI",
        Arial,
        sans-serif;
}


/* =====================================================
   HEADER
===================================================== */

header{

    min-height:80px;

    padding:18px 30px;

    background:
        linear-gradient(
            135deg,
            #064e3b,
            #075985,
            #172554
        );

    display:flex;

    justify-content:space-between;

    align-items:center;

    gap:15px;

    flex-wrap:wrap;

    box-shadow:
        0 5px 30px rgba(0,0,0,.35);
}

.logo{

    display:flex;

    align-items:center;

    gap:12px;
}

.logo-icon{

    width:48px;

    height:48px;

    border-radius:14px;

    background:
        rgba(255,255,255,.12);

    display:flex;

    align-items:center;

    justify-content:center;

    font-size:27px;
}

.logo h1{

    margin:0;

    font-size:22px;

    font-weight:700;
}

.logo p{

    margin:3px 0 0;

    color:#b7d7e8;

    font-size:12px;
}


/* =====================================================
   STATUS
===================================================== */

.status{

    display:flex;

    align-items:center;

    gap:8px;

    padding:9px 16px;

    border-radius:30px;

    background:#3b2020;

    color:#fca5a5;

    font-size:14px;

    font-weight:600;
}

.status.online{

    background:#0b3d2b;

    color:#86efac;
}

.dot{

    width:9px;

    height:9px;

    border-radius:50%;

    background:#ef4444;
}

.status.online .dot{

    background:#22c55e;

    box-shadow:
        0 0 12px #22c55e;
}


/* =====================================================
   MAIN
===================================================== */

.container{

    width:min(1250px, 94%);

    margin:25px auto;

}


/* =====================================================
   TOP CARDS
===================================================== */

.stats{

    display:grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap:15px;

    margin-bottom:18px;
}

.stat{

    background:#0e2030;

    border:1px solid #1b3549;

    border-radius:16px;

    padding:20px;

    box-shadow:
        0 8px 25px rgba(0,0,0,.2);

    transition:.2s;
}

.stat:hover{

    transform:translateY(-2px);

    border-color:#2c526b;
}

.stat-top{

    display:flex;

    justify-content:space-between;

    align-items:center;
}

.stat-title{

    color:#91b1c4;

    font-size:13px;
}

.stat-icon{

    width:38px;

    height:38px;

    border-radius:11px;

    display:flex;

    align-items:center;

    justify-content:center;

    background:#12334a;

    font-size:20px;
}

.stat-value{

    margin-top:12px;

    font-size:30px;

    font-weight:800;
}

.stat-unit{

    color:#7897aa;

    font-size:12px;
}


/* =====================================================
   GRID
===================================================== */

.grid{

    display:grid;

    grid-template-columns:
        1.7fr 1fr;

    gap:18px;
}

.card{

    background:#0e2030;

    border:1px solid #1b3549;

    border-radius:16px;

    padding:18px;

    box-shadow:
        0 8px 25px rgba(0,0,0,.2);
}

.card-title{

    display:flex;

    justify-content:space-between;

    align-items:center;

    margin-bottom:14px;
}

.card-title h2{

    margin:0;

    font-size:16px;
}

.card-sub{

    color:#7897aa;

    font-size:12px;
}


/* =====================================================
   VIDEO
===================================================== */

.video{

    width:100%;

    aspect-ratio:16/10;

    background:#030b12;

    border-radius:12px;

    overflow:hidden;

    position:relative;

    display:flex;

    align-items:center;

    justify-content:center;

    border:1px solid #183346;
}

.video img{

    width:100%;

    height:100%;

    object-fit:contain;

    display:none;
}

.placeholder{

    color:#638095;

    text-align:center;

    font-size:14px;
}

.placeholder-icon{

    font-size:45px;

    margin-bottom:8px;
}


/* =====================================================
   CAMERA INFO
===================================================== */

.camera-info{

    display:grid;

    grid-template-columns:
        repeat(3,1fr);

    gap:10px;

    margin-top:12px;
}

.info{

    background:#0a1926;

    border-radius:10px;

    padding:10px;

    text-align:center;
}

.info small{

    display:block;

    color:#6f8da0;

    font-size:11px;
}

.info b{

    display:block;

    margin-top:4px;

    font-size:15px;
}


/* =====================================================
   SPECIES
===================================================== */

.species{

    display:flex;

    flex-direction:column;

    gap:8px;
}

.species-row{

    display:flex;

    align-items:center;

    justify-content:space-between;

    padding:13px 14px;

    border-radius:10px;

    background:#0a1926;

    border:1px solid #173247;
}

.species-name{

    display:flex;

    align-items:center;

    gap:9px;

    font-size:14px;
}

.species-dot{

    width:8px;

    height:8px;

    border-radius:50%;

    background:#22c55e;
}

.species-count{

    font-weight:700;

    color:#fb923c;
}


/* =====================================================
   CHART
===================================================== */

.chart-card{

    margin-top:18px;
}

.chart-wrap{

    width:100%;

    height:250px;

    position:relative;
}

canvas{

    width:100%;

    height:100%;

}


/* =====================================================
   FOOTER
===================================================== */

footer{

    text-align:center;

    color:#557185;

    font-size:12px;

    padding:25px 0 35px;
}


/* =====================================================
   RESPONSIVE
===================================================== */

@media(max-width:900px){

    .stats{

        grid-template-columns:
            repeat(2,1fr);
    }

    .grid{

        grid-template-columns:1fr;
    }
}

@media(max-width:550px){

    header{

        padding:15px;
    }

    .logo h1{

        font-size:18px;
    }

    .container{

        width:94%;

        margin-top:15px;
    }

    .stats{

        grid-template-columns:1fr;
    }

    .camera-info{

        grid-template-columns:1fr;
    }

}

</style>

</head>


<body>


<!-- =====================================================
     HEADER
===================================================== -->

<header>

<div class="logo">

<div class="logo-icon">
🦐
</div>

<div>

<h1>ระบบตรวจจับกุ้ง AI</h1>

<p>
Shrimp Realtime Detection Dashboard
</p>

</div>

</div>


<div
    id="status"
    class="status"
>

<span class="dot"></span>

<span id="statusText">
กำลังเชื่อมต่อ...
</span>

</div>

</header>


<div class="container">


<!-- =====================================================
     STATISTICS
===================================================== -->

<div class="stats">


<div class="stat">

<div class="stat-top">

<span class="stat-title">
กุ้งทั้งหมด
</span>

<div class="stat-icon">
🦐
</div>

</div>

<div
    id="total"
    class="stat-value"
>
-
</div>

<div class="stat-unit">
ตัวในภาพปัจจุบัน
</div>

</div>


<div class="stat">

<div class="stat-top">

<span class="stat-title">
ความเร็ว AI
</span>

<div class="stat-icon">
⚡
</div>

</div>

<div
    id="fps"
    class="stat-value"
>
-
</div>

<div class="stat-unit">
Frames / Second
</div>

</div>


<div class="stat">

<div class="stat-top">

<span class="stat-title">
ชนิดกุ้ง
</span>

<div class="stat-icon">
🔬
</div>

</div>

<div
    id="classCount"
    class="stat-value"
>
0
</div>

<div class="stat-unit">
ประเภทที่ตรวจพบ
</div>

</div>


<div class="stat">

<div class="stat-top">

<span class="stat-title">
อัปเดตล่าสุด
</span>

<div class="stat-icon">
🕐
</div>

</div>

<div
    id="age"
    class="stat-value"
    style="font-size:22px"
>
-
</div>

<div class="stat-unit">
วินาทีที่แล้ว
</div>

</div>


</div>


<!-- =====================================================
     MAIN GRID
===================================================== -->

<div class="grid">


<!-- CAMERA -->

<div class="card">

<div class="card-title">

<div>

<h2>📷 ภาพจากกล้อง</h2>

<div class="card-sub">
ภาพล่าสุดจากระบบ AI
</div>

</div>

</div>


<div class="video">

<img
    id="frame"
    alt="Camera frame"
>

<div
    id="placeholder"
    class="placeholder"
>

<div class="placeholder-icon">
📷
</div>

<div>
รอสัญญาณจากกล้อง...
</div>

</div>

</div>


<div class="camera-info">

<div class="info">

<small>สถานะ</small>

<b id="cameraStatus">
-
</b>

</div>


<div class="info">

<small>จำนวน</small>

<b id="cameraTotal">
-
</b>

</div>


<div class="info">

<small>อัปเดต</small>

<b id="cameraAge">
-
</b>

</div>

</div>

</div>


<!-- SPECIES -->

<div class="card">

<div class="card-title">

<div>

<h2>🦐 ชนิดกุ้ง</h2>

<div class="card-sub">
จำนวนที่ตรวจพบ
</div>

</div>

</div>


<div
    id="species"
    class="species"
>

<div class="placeholder">
ยังไม่มีข้อมูล
</div>

</div>

</div>


</div>


<!-- =====================================================
     CHART
===================================================== -->

<div class="card chart-card">

<div class="card-title">

<div>

<h2>📈 จำนวนกุ้งย้อนหลัง</h2>

<div class="card-sub">
ข้อมูลล่าสุด 120 ครั้ง
</div>

</div>

<div
    id="chartMax"
    class="card-sub"
>
สูงสุด -
</div>

</div>


<div class="chart-wrap">

<canvas id="chart"></canvas>

</div>

</div>


</div>


<footer>

🦐 Shrimp AI Detection System

</footer>


<script>


// =========================================================
// ELEMENTS
// =========================================================

const $ = id =>
    document.getElementById(id);

let lastTs = 0;


// =========================================================
// ESCAPE HTML
// =========================================================

function esc(value){

    return String(value)
        .replace(
            /[&<>"']/g,
            c => ({
                "&":"&amp;",
                "<":"&lt;",
                ">":"&gt;",
                '"':"&quot;",
                "'":"&#039;"
            }[c])
        );
}


// =========================================================
// DRAW CHART
// =========================================================

function drawChart(history){

    const canvas =
        $("chart");

    const ctx =
        canvas.getContext("2d");

    const rect =
        canvas.getBoundingClientRect();

    const dpr =
        window.devicePixelRatio || 1;

    canvas.width =
        rect.width * dpr;

    canvas.height =
        rect.height * dpr;

    ctx.setTransform(
        dpr,
        0,
        0,
        dpr,
        0,
        0
    );

    const w = rect.width;
    const h = rect.height;

    ctx.clearRect(
        0,
        0,
        w,
        h
    );


    if(!history.length){

        ctx.fillStyle =
            "#638095";

        ctx.font =
            "13px sans-serif";

        ctx.fillText(
            "ยังไม่มีข้อมูลสำหรับแสดงกราฟ",
            15,
            30
        );

        return;
    }


    const max =
        Math.max(
            5,
            ...history
        );


    $("chartMax").textContent =
        "สูงสุด " + max;


    // -------------------------
    // GRID
    // -------------------------

    ctx.strokeStyle =
        "#173247";

    ctx.lineWidth = 1;

    for(let i=0;i<5;i++){

        const y =
            15 +
            i *
            ((h-35)/4);

        ctx.beginPath();

        ctx.moveTo(
            0,
            y
        );

        ctx.lineTo(
            w,
            y
        );

        ctx.stroke();

    }


    // -------------------------
    // LINE
    // -------------------------

    ctx.strokeStyle =
        "#fb923c";

    ctx.lineWidth = 3;

    ctx.lineJoin =
        "round";

    ctx.lineCap =
        "round";

    ctx.beginPath();


    history.forEach(
        (value,index)=>{

            const x =
                history.length === 1
                ? w / 2
                : index /
                  (history.length - 1)
                  * w;

            const y =
                h - 25 -
                (value / max)
                * (h - 50);

            if(index === 0){

                ctx.moveTo(
                    x,
                    y
                );

            }else{

                ctx.lineTo(
                    x,
                    y
                );

            }

        }
    );

    ctx.stroke();


    // -------------------------
    // LAST POINT
    // -------------------------

    const last =
        history[history.length - 1];

    const lastX =
        history.length === 1
        ? w / 2
        : w;

    const lastY =
        h - 25 -
        (last / max)
        * (h - 50);


    ctx.fillStyle =
        "#fb923c";

    ctx.beginPath();

    ctx.arc(
        lastX,
        lastY,
        5,
        0,
        Math.PI * 2
    );

    ctx.fill();

}


// =========================================================
// UPDATE DASHBOARD
// =========================================================

async function updateDashboard(){

    try{

        const response =
            await fetch(
                "/api/latest",
                {
                    cache:"no-store"
                }
            );


        if(!response.ok){

            throw new Error(
                "Server error"
            );

        }


        const data =
            await response.json();


        // -------------------------
        // STATUS
        // -------------------------

        const status =
            $("status");

        const statusText =
            $("statusText");


        if(data.online){

            status.className =
                "status online";

            statusText.textContent =
                "● กล้องออนไลน์";

        }else{

            status.className =
                "status";

            statusText.textContent =
                data.has_data
                ? "● กล้องออฟไลน์"
                : "● รอสัญญาณ";

        }


        // -------------------------
        // TOTAL
        // -------------------------

        const total =
            data.has_data
            ? data.total
            : "-";


        $("total").textContent =
            total;

        $("cameraTotal").textContent =
            total;


        // -------------------------
        // FPS
        // -------------------------

        $("fps").textContent =
            data.has_data
            ? Number(data.fps).toFixed(1)
            : "-";


        // -------------------------
        // AGE
        // -------------------------

        const age =
            data.has_data
            ? Math.max(
                0,
                Math.round(data.age)
              )
            : "-";


        $("age").textContent =
            age;

        $("cameraAge").textContent =
            data.has_data
            ? age + " วินาที"
            : "-";


        $("cameraStatus").textContent =
            data.online
            ? "ออนไลน์"
            : "ออฟไลน์";


        // -------------------------
        // CLASSES
        // -------------------------

        const entries =
            Object.entries(
                data.counts || {}
            ).sort(
                (a,b)=>b[1]-a[1]
            );


        $("classCount").textContent =
            entries.length;


        const species =
            $("species");


        if(!entries.length){

            species.innerHTML = `

                <div class="placeholder">
                    ยังไม่พบกุ้ง
                </div>

            `;

        }else{

            species.innerHTML =
                entries
                .map(
                    ([name,count])=>`

                    <div class="species-row">

                        <div class="species-name">

                            <span class="species-dot">
                            </span>

                            <span>
                                ${esc(name)}
                            </span>

                        </div>

                        <div class="species-count">
                            ${count} ตัว
                        </div>

                    </div>

                    `
                )
                .join("");

        }


        // -------------------------
        // FRAME
        // -------------------------

        if(
            data.has_frame &&
            data.ts !== lastTs
        ){

            lastTs =
                data.ts;


            const image =
                $("frame");


            image.src =
                "/api/frame?t="
                + data.ts;


            image.style.display =
                "block";


            $("placeholder")
                .style.display =
                "none";

        }


        // -------------------------
        // CHART
        // -------------------------

        drawChart(
            data.history || []
        );


    }catch(error){

        $("status").className =
            "status";

        $("statusText").textContent =
            "● ติดต่อเซิร์ฟเวอร์ไม่ได้";

    }

}


// =========================================================
// START
// =========================================================

updateDashboard();


setInterval(
    updateDashboard,
    1000
);


// =========================================================
// RESIZE
// =========================================================

window.addEventListener(
    "resize",
    ()=>{
        updateDashboard();
    }
);

</script>


</body>

</html>
"""


# =========================================================
# HOME
# =========================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
def index():

    return PAGE


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                8000
            )
        )
    )
```
