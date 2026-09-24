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
    title="Shrimp AI Dashboard",
    version="2.0"
)


# =========================================================
# DATA
# =========================================================

# ผลรอบล่าสุด
latest_round = None

# เก็บประวัติสูงสุด 100 รอบ
round_history = deque(maxlen=100)

# ภาพล่าสุดจากกล้อง
live_frame = None
live_ts = 0


# =========================================================
# MODEL
# =========================================================

class RoundReport(BaseModel):

    # เลขรอบ เช่น 1, 2, 3
    round_id: int = 0

    # จำนวนกุ้งแต่ละชนิด
    counts: dict[str, int] = Field(default_factory=dict)

    # FPS เฉลี่ย
    avg_fps: float = 0.0

    # เวลาที่ใช้ในการตรวจ
    duration: float = 0.0

    # จำนวนเฟรมที่ตรวจ
    frames: int = 0

    # เวลาที่เริ่มรอบ
    started_at: str | None = None

    # เวลาที่จบรอบ
    finished_at: str | None = None

    # ภาพจาก AI
    frame_b64: str | None = None


class LiveReport(BaseModel):

    counts: dict[str, int] = Field(default_factory=dict)

    fps: float = 0.0

    frame_b64: str | None = None


# =========================================================
# RECEIVE COMPLETED ROUND
# =========================================================

@app.post("/api/round")
def receive_round(
    data: RoundReport,
    x_api_key: str = Header(default="")
):

    global latest_round
    global live_frame
    global live_ts

    # -------------------------
    # ตรวจ API KEY
    # -------------------------

    if x_api_key != API_KEY:

        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    # -------------------------
    # ทำความสะอาดข้อมูล
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
    # รวมทั้งหมด
    # -------------------------

    total = sum(clean_counts.values())

    # -------------------------
    # สร้างข้อมูลรอบ
    # -------------------------

    result = {

        "round_id": data.round_id,

        "counts": clean_counts,

        "total": total,

        "avg_fps": round(
            max(0, float(data.avg_fps)),
            2
        ),

        "duration": round(
            max(0, float(data.duration)),
            2
        ),

        "frames": max(
            0,
            int(data.frames)
        ),

        "started_at":
            data.started_at,

        "finished_at":
            data.finished_at,

        "received_at":
            time.time()
    }

    # -------------------------
    # บันทึก
    # -------------------------

    latest_round = result

    round_history.appendleft(result)

    # -------------------------
    # ถ้ามีภาพให้เก็บไว้ด้วย
    # -------------------------

    if data.frame_b64:

        try:

            live_frame = base64.b64decode(
                data.frame_b64,
                validate=True
            )

            live_ts = time.time()

        except Exception:

            pass

    return {

        "ok": True,

        "round_id":
            data.round_id,

        "total":
            total

    }


# =========================================================
# RECEIVE LIVE CAMERA
# =========================================================

@app.post("/api/live")
def receive_live(
    data: LiveReport,
    x_api_key: str = Header(default="")
):

    global live_frame
    global live_ts

    if x_api_key != API_KEY:

        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    if data.frame_b64:

        try:

            live_frame = base64.b64decode(
                data.frame_b64,
                validate=True
            )

            live_ts = time.time()

        except Exception:

            raise HTTPException(
                status_code=400,
                detail="Invalid image"
            )

    return {
        "ok": True
    }


# =========================================================
# DASHBOARD DATA
# =========================================================

@app.get("/api/dashboard")
def dashboard():

    return {

        "has_round":
            latest_round is not None,

        "latest":
            latest_round,

        "history":
            list(round_history)

    }


# =========================================================
# LIVE STATUS
# =========================================================

@app.get("/api/live/status")
def live_status():

    if live_ts == 0:

        return {
            "online": False,
            "age": 0
        }

    age = time.time() - live_ts

    return {

        "online":
            age < 10,

        "age":
            age,

        "has_frame":
            live_frame is not None

    }


# =========================================================
# LIVE FRAME
# =========================================================

@app.get("/api/live/frame")
def get_live_frame():

    if live_frame is None:

        return Response(
            status_code=204
        )

    return Response(

        live_frame,

        media_type="image/jpeg",

        headers={
            "Cache-Control":
                "no-store"
        }

    )


# =========================================================
# PAGE 1
# =========================================================

DASHBOARD_PAGE = r"""
<!DOCTYPE html>

<html lang="th">

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1"
>

<title>สรุปผลการตรวจจับกุ้ง</title>

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
        Arial,
        sans-serif;
}


/* HEADER */

header{

    padding:20px 30px;

    background:
        linear-gradient(
            135deg,
            #064e3b,
            #075985,
            #172554
        );

    display:flex;

    align-items:center;

    justify-content:space-between;

    gap:15px;

    flex-wrap:wrap;
}

h1{

    margin:0;

    font-size:24px;
}

.subtitle{

    color:#a9c5d6;

    margin-top:4px;

    font-size:13px;
}


/* NAV */

nav{

    display:flex;

    gap:8px;
}

nav a{

    color:#dbeafe;

    text-decoration:none;

    padding:9px 15px;

    border-radius:9px;

    background:
        rgba(255,255,255,.10);
}

nav a.active{

    background:#f97316;

    color:white;
}


/* MAIN */

main{

    width:min(1200px,94%);

    margin:25px auto;
}


/* CARDS */

.cards{

    display:grid;

    grid-template-columns:
        repeat(4,1fr);

    gap:15px;
}

.card{

    background:#0e2030;

    border:1px solid #1b3549;

    border-radius:15px;

    padding:20px;
}

.card-title{

    color:#8eacbe;

    font-size:13px;
}

.number{

    margin-top:10px;

    font-size:32px;

    font-weight:800;

    color:#fb923c;
}


/* LATEST */

.latest{

    margin-top:18px;
}

.latest-header{

    display:flex;

    justify-content:space-between;

    align-items:center;

    margin-bottom:15px;
}

.latest-header h2{

    margin:0;

    font-size:18px;
}

.badge{

    background:#123b32;

    color:#86efac;

    padding:6px 12px;

    border-radius:20px;

    font-size:12px;
}


/* SPECIES */

.species{

    display:grid;

    grid-template-columns:
        repeat(auto-fit,minmax(160px,1fr));

    gap:10px;

    margin-top:15px;
}

.species-item{

    background:#091a28;

    border:1px solid #173247;

    border-radius:10px;

    padding:14px;

}

.species-name{

    color:#9bb7c7;

    font-size:13px;
}

.species-value{

    font-size:24px;

    font-weight:bold;

    color:#fb923c;

    margin-top:5px;
}


/* TABLE */

.history{

    margin-top:18px;
}

.table-wrap{

    overflow:auto;
}

table{

    width:100%;

    border-collapse:collapse;

    min-width:650px;
}

th,td{

    padding:13px;

    text-align:left;

    border-bottom:
        1px solid #193449;
}

th{

    color:#8faabb;

    font-size:12px;
}

td{

    font-size:13px;
}

.empty{

    text-align:center;

    color:#668398;

    padding:50px 10px;
}


/* RESPONSIVE */

@media(max-width:900px){

    .cards{

        grid-template-columns:
            repeat(2,1fr);
    }
}

@media(max-width:550px){

    .cards{

        grid-template-columns:1fr;
    }

    header{

        padding:18px;
    }

    h1{

        font-size:20px;
    }

}

</style>

</head>


<body>


<header>

<div>

<h1>🦐 ระบบสรุปผลการตรวจจับกุ้ง AI</h1>

<div class="subtitle">
ผลการทำงานของ AI แยกตามรอบ
</div>

</div>


<nav>

<a
href="/"
class="active"
>
📊 สรุปผล
</a>

<a href="/live">
📷 กล้อง Live
</a>

</nav>

</header>


<main>


<!-- STATS -->

<div class="cards">


<div class="card">

<div class="card-title">
รอบล่าสุด
</div>

<div
id="round"
class="number"
>
-
</div>

</div>


<div class="card">

<div class="card-title">
กุ้งในรอบล่าสุด
</div>

<div
id="total"
class="number"
>
-
</div>

</div>


<div class="card">

<div class="card-title">
FPS เฉลี่ย
</div>

<div
id="fps"
class="number"
>
-
</div>

</div>


<div class="card">

<div class="card-title">
เวลาทำงาน
</div>

<div
id="duration"
class="number"
>
-
</div>

</div>


</div>


<!-- LATEST ROUND -->

<div class="card latest">

<div class="latest-header">

<h2>
📋 ผลสรุปรอบล่าสุด
</h2>

<span
class="badge"
id="finished"
>
ยังไม่มีข้อมูล
</span>

</div>


<div
id="species"
class="species"
>

<div class="empty">
รอ AI ส่งผลการทำงานรอบแรก
</div>

</div>


</div>


<!-- HISTORY -->

<div class="card history">

<div class="latest-header">

<h2>
📚 ประวัติการทำงาน
</h2>

</div>


<div class="table-wrap">

<table>

<thead>

<tr>

<th>รอบ</th>

<th>จำนวนกุ้ง</th>

<th>FPS</th>

<th>เวลา</th>

<th>จำนวนเฟรม</th>

<th>เวลาจบ</th>

</tr>

</thead>

<tbody
id="history"
>

<tr>

<td
colspan="6"
class="empty"
>
ยังไม่มีประวัติ
</td>

</tr>

</tbody>

</table>

</div>

</div>


</main>


<script>


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


function formatTime(value){

    if(!value)
        return "-";

    return value;

}


async function load(){

    try{

        const res =
            await fetch(
                "/api/dashboard",
                {
                    cache:"no-store"
                }
            );

        const data =
            await res.json();


        const latest =
            data.latest;


        if(!latest){

            return;

        }


        document
            .getElementById("round")
            .textContent =
                latest.round_id;


        document
            .getElementById("total")
            .textContent =
                latest.total;


        document
            .getElementById("fps")
            .textContent =
                latest.avg_fps;


        document
            .getElementById("duration")
            .textContent =
                latest.duration + "s";


        document
            .getElementById("finished")
            .textContent =
                latest.finished_at || "เสร็จแล้ว";


        /* SPECIES */

        const species =
            document.getElementById(
                "species"
            );


        const entries =
            Object.entries(
                latest.counts || {}
            );


        if(!entries.length){

            species.innerHTML = `
                <div class="empty">
                    รอบนี้ไม่พบกุ้ง
                </div>
            `;

        }else{

            species.innerHTML =
                entries.map(
                    ([name,value]) => `

                    <div class="species-item">

                        <div class="species-name">
                            🦐 ${esc(name)}
                        </div>

                        <div class="species-value">
                            ${value} ตัว
                        </div>

                    </div>

                    `
                ).join("");

        }


        /* HISTORY */

        const tbody =
            document.getElementById(
                "history"
            );


        if(!data.history.length){

            tbody.innerHTML = `
                <tr>
                    <td
                    colspan="6"
                    class="empty"
                    >
                    ยังไม่มีประวัติ
                    </td>
                </tr>
            `;

            return;

        }


        tbody.innerHTML =
            data.history.map(
                item => `

                <tr>

                    <td>
                        #${item.round_id}
                    </td>

                    <td>
                        <b>
                            ${item.total}
                        </b> ตัว
                    </td>

                    <td>
                        ${item.avg_fps}
                    </td>

                    <td>
                        ${item.duration}s
                    </td>

                    <td>
                        ${item.frames}
                    </td>

                    <td>
                        ${formatTime(
                            item.finished_at
                        )}
                    </td>

                </tr>

                `
            ).join("");


    }catch(error){

        console.log(error);

    }

}


load();


/*
อัปเดตเฉพาะข้อมูล
ไม่เกี่ยวกับกล้อง
*/

setInterval(
    load,
    2000
);

</script>

</body>

</html>
"""


# =========================================================
# PAGE 2 LIVE CAMERA
# =========================================================

LIVE_PAGE = r"""
<!DOCTYPE html>

<html lang="th">

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1"
>

<title>กล้อง Live</title>

<style>

*{
    box-sizing:border-box;
}

body{

    margin:0;

    background:#050d14;

    color:white;

    font-family:
        "Noto Sans Thai",
        Arial,
        sans-serif;
}

header{

    padding:20px;

    background:
        linear-gradient(
            135deg,
            #064e3b,
            #075985
        );

    display:flex;

    justify-content:space-between;

    align-items:center;

    flex-wrap:wrap;

    gap:10px;
}

h1{

    margin:0;

    font-size:22px;
}

nav{

    display:flex;

    gap:8px;
}

nav a{

    color:white;

    text-decoration:none;

    padding:8px 14px;

    border-radius:8px;

    background:
        rgba(255,255,255,.1);
}

nav a.active{

    background:#f97316;
}

main{

    width:min(1100px,94%);

    margin:25px auto;
}

.camera{

    background:#0c1b27;

    border:1px solid #1c3548;

    border-radius:15px;

    padding:15px;
}

.video{

    background:#02070b;

    aspect-ratio:16/9;

    border-radius:12px;

    overflow:hidden;

    display:flex;

    align-items:center;

    justify-content:center;
}

video,img{

    width:100%;

    height:100%;

    object-fit:contain;
}

#frame{

    display:none;
}

.placeholder{

    color:#648094;

    text-align:center;
}

.status{

    margin-top:12px;

    padding:12px;

    border-radius:10px;

    background:#301919;

    color:#fca5a5;
}

.status.online{

    background:#0c3527;

    color:#86efac;
}

</style>

</head>


<body>


<header>

<h1>
📷 กล้อง AI แบบ Real-time
</h1>


<nav>

<a href="/">
📊 สรุปผล
</a>

<a
href="/live"
class="active"
>
📷 กล้อง Live
</a>

</nav>

</header>


<main>

<div class="camera">

<div class="video">

<img
id="frame"
alt="Live camera"
>

<div
id="placeholder"
class="placeholder"
>

📷

<br>

กำลังรอสัญญาณจากกล้อง...

</div>

</div>


<div
id="status"
class="status"
>

● กำลังเชื่อมต่อกล้อง

</div>

</div>

</main>


<script>

let last = 0;


async function update(){

    try{

        const res =
            await fetch(
                "/api/live/status",
                {
                    cache:"no-store"
                }
            );

        const data =
            await res.json();


        const status =
            document.getElementById(
                "status"
            );


        if(data.online){

            status.className =
                "status online";

            status.textContent =
                "● กล้องออนไลน์";

        }else{

            status.className =
                "status";

            status.textContent =
                "● รอสัญญาณจากกล้อง";

        }


        if(
            data.has_frame &&
            data.online
        ){

            const img =
                document.getElementById(
                    "frame"
                );

            img.src =
                "/api/live/frame?t="
                + Date.now();

            img.style.display =
                "block";

            document
                .getElementById(
                    "placeholder"
                )
                .style.display =
                "none";

        }

    }catch(error){

        console.log(error);

    }

}


setInterval(
    update,
    1000
);

update();

</script>

</body>

</html>
"""


# =========================================================
# ROUTES
# =========================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
def home():

    return DASHBOARD_PAGE


@app.get(
    "/live",
    response_class=HTMLResponse
)
def live():

    return LIVE_PAGE


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
