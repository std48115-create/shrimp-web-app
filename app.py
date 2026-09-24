import os
import base64
from datetime import datetime
from collections import deque
from typing import Dict, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field


# =========================================================
# CONFIG
# =========================================================

API_KEY = os.environ.get("API_KEY", "change-me")

SHRIMP_TYPES = [
    "กุ้งเล็ก",
    "กุ้งกลาง",
    "กุ้งใหญ่",
    "กุ้งป่วย",
]

app = FastAPI(title="Shrimp Vision AI")


# =========================================================
# MEMORY
# =========================================================

latest_round = None
round_history = deque(maxlen=100)

live_frame: Optional[bytes] = None
live_ts: Optional[datetime] = None


# =========================================================
# MODELS
# =========================================================

class RoundReport(BaseModel):
    round_id: int = 0

    counts: Dict[str, int] = Field(default_factory=dict)

    avg_fps: float = 0
    duration: float = 0
    frames: int = 0

    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    frame_b64: Optional[str] = None


class LiveReport(BaseModel):
    counts: Dict[str, int] = Field(default_factory=dict)

    fps: float = 0

    frame_b64: Optional[str] = None


# =========================================================
# HELPERS
# =========================================================

def clean_counts(counts: Dict[str, int]):
    result = {}

    for shrimp_type in SHRIMP_TYPES:
        try:
            value = int(counts.get(shrimp_type, 0))
        except Exception:
            value = 0

        result[shrimp_type] = max(0, value)

    return result


def decode_frame(frame_b64: Optional[str]):
    if not frame_b64:
        return None

    try:
        if "," in frame_b64:
            frame_b64 = frame_b64.split(",", 1)[1]

        return base64.b64decode(frame_b64)
    except Exception:
        return None


def check_api_key(x_api_key: Optional[str]):
    if API_KEY and API_KEY != "change-me":
        if x_api_key != API_KEY:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )


def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


# =========================================================
# API
# =========================================================

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "Shrimp Vision AI"
    }


@app.post("/api/round")
def receive_round(
    data: RoundReport,
    x_api_key: Optional[str] = Header(default=None)
):
    global latest_round

    check_api_key(x_api_key)

    counts = clean_counts(data.counts)

    total = sum(counts.values())

    normal_total = (
        counts["กุ้งเล็ก"]
        + counts["กุ้งกลาง"]
        + counts["กุ้งใหญ่"]
    )

    sick_total = counts["กุ้งป่วย"]

    result = {
        "round_id": data.round_id,
        "counts": counts,

        "total": total,
        "normal_total": normal_total,
        "sick_total": sick_total,

        "avg_fps": data.avg_fps,
        "duration": data.duration,
        "frames": data.frames,

        "started_at": data.started_at,
        "finished_at": data.finished_at,

        "received_at": datetime.now().isoformat(),
    }

    latest_round = result

    round_history.appendleft(result)

    frame = decode_frame(data.frame_b64)

    global live_frame, live_ts

    if frame:
        live_frame = frame
        live_ts = datetime.now()

    return {
        "ok": True,
        "message": "Round received",
        "round": result
    }


@app.post("/api/live")
def receive_live(
    data: LiveReport,
    x_api_key: Optional[str] = Header(default=None)
):
    global live_frame, live_ts

    check_api_key(x_api_key)

    frame = decode_frame(data.frame_b64)

    if frame:
        live_frame = frame
        live_ts = datetime.now()

    return {
        "ok": True
    }


@app.get("/api/dashboard")
def dashboard_api():
    response = {
        "latest": latest_round,
        "history": list(round_history),
        "shrimp_types": SHRIMP_TYPES
    }

    return response


@app.get("/api/live/status")
def live_status():
    return {
        "online": live_frame is not None,
        "last_update": live_ts.isoformat() if live_ts else None
    }


@app.get("/api/live/frame")
def get_live_frame():

    if not live_frame:
        raise HTTPException(
            status_code=404,
            detail="No live frame"
        )

    response = Response(
        content=live_frame,
        media_type="image/jpeg"
    )

    return no_cache(response)


# =========================================================
# PREMIUM UI
# =========================================================

HTML = r"""
<!DOCTYPE html>
<html lang="th">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Shrimp Vision AI</title>

<style>

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+Thai:wght@400;500;600;700;800&display=swap');

:root{

    --bg:#f3f8fc;
    --card:#ffffff;
    --text:#10233d;
    --muted:#718096;

    --blue:#1687ff;
    --cyan:#00c6ff;
    --purple:#7957ff;

    --green:#12b981;
    --orange:#ff9d42;
    --red:#ff5364;

    --border:rgba(25,80,130,.09);

    --shadow:
        0 20px 60px rgba(26,72,110,.10);

}

*{
    box-sizing:border-box;
}

html{
    scroll-behavior:smooth;
}

body{

    margin:0;

    background:
        radial-gradient(
            circle at 10% 0%,
            rgba(0,198,255,.12),
            transparent 28%
        ),
        radial-gradient(
            circle at 90% 10%,
            rgba(121,87,255,.10),
            transparent 28%
        ),
        var(--bg);

    color:var(--text);

    font-family:
        "Noto Sans Thai",
        Inter,
        sans-serif;

    min-height:100vh;
}

a{
    text-decoration:none;
    color:inherit;
}

button{
    font-family:inherit;
}


/* ======================================================
   NAVBAR
====================================================== */

.navbar{

    position:sticky;
    top:0;
    z-index:100;

    height:76px;

    display:flex;
    align-items:center;
    justify-content:space-between;

    padding:0 42px;

    background:rgba(255,255,255,.82);

    backdrop-filter:blur(24px);

    border-bottom:1px solid var(--border);
}

.brand{

    display:flex;
    align-items:center;
    gap:13px;
}

.logo{

    width:45px;
    height:45px;

    display:grid;
    place-items:center;

    border-radius:15px;

    background:
        linear-gradient(
            135deg,
            #00c6ff,
            #1687ff,
            #7957ff
        );

    color:white;

    font-size:22px;

    box-shadow:
        0 10px 25px rgba(22,135,255,.25);
}

.brand-text h1{

    margin:0;

    font-size:18px;
    font-weight:800;

    letter-spacing:-.4px;
}

.brand-text span{

    color:var(--muted);

    font-size:11px;

    font-weight:600;
}

.nav-right{

    display:flex;
    align-items:center;
    gap:12px;
}

.status{

    display:flex;
    align-items:center;
    gap:8px;

    padding:9px 14px;

    background:#ecfbf5;

    color:#0b9b6c;

    border-radius:999px;

    font-size:12px;
    font-weight:700;
}

.status-dot{

    width:8px;
    height:8px;

    border-radius:50%;

    background:#16c58c;

    box-shadow:
        0 0 0 5px rgba(22,197,140,.12);
}

.nav-btn{

    padding:10px 17px;

    border-radius:12px;

    background:#f1f6fb;

    color:#29435f;

    font-size:13px;

    font-weight:700;

    transition:.2s;
}

.nav-btn:hover{

    background:#e5f2ff;
    color:var(--blue);

}


/* ======================================================
   PAGE
====================================================== */

.container{

    width:min(1440px, calc(100% - 48px));

    margin:auto;

    padding:38px 0 70px;
}


/* ======================================================
   HERO
====================================================== */

.hero{

    position:relative;

    overflow:hidden;

    padding:40px;

    min-height:240px;

    border-radius:30px;

    background:

        radial-gradient(
            circle at 85% 25%,
            rgba(255,255,255,.35),
            transparent 24%
        ),

        linear-gradient(
            120deg,
            #0b74e5 0%,
            #1687ff 40%,
            #00bde9 100%
        );

    color:white;

    box-shadow:
        0 25px 70px rgba(13,117,225,.25);
}

.hero:before{

    content:"";

    position:absolute;

    width:340px;
    height:340px;

    right:-90px;
    top:-170px;

    border-radius:50%;

    border:55px solid rgba(255,255,255,.08);
}

.hero:after{

    content:"";

    position:absolute;

    width:180px;
    height:180px;

    right:230px;
    bottom:-110px;

    border-radius:50%;

    background:rgba(255,255,255,.08);
}

.hero-content{

    position:relative;
    z-index:2;

    max-width:720px;
}

.hero-kicker{

    display:inline-flex;

    padding:7px 12px;

    border-radius:999px;

    background:rgba(255,255,255,.16);

    backdrop-filter:blur(10px);

    font-size:11px;

    font-weight:700;

    margin-bottom:16px;
}

.hero h2{

    margin:0 0 10px;

    font-size:clamp(30px,4vw,48px);

    line-height:1.1;

    letter-spacing:-1.7px;
}

.hero p{

    margin:0;

    max-width:600px;

    color:rgba(255,255,255,.85);

    font-size:14px;

    line-height:1.8;
}

.hero-actions{

    display:flex;

    gap:10px;

    margin-top:25px;
}

.hero-button{

    padding:12px 19px;

    border:0;

    border-radius:13px;

    background:white;

    color:#0876e8;

    font-weight:800;

    cursor:pointer;

    box-shadow:
        0 8px 25px rgba(0,0,0,.12);
}

.hero-button.secondary{

    background:rgba(255,255,255,.14);

    color:white;

    border:1px solid rgba(255,255,255,.18);

}


/* ======================================================
   KPI
====================================================== */

.section-title{

    display:flex;

    justify-content:space-between;
    align-items:end;

    margin:34px 0 15px;
}

.section-title h3{

    margin:0;

    font-size:19px;
}

.section-title span{

    color:var(--muted);

    font-size:12px;
}

.kpi-grid{

    display:grid;

    grid-template-columns:
        repeat(4,1fr);

    gap:16px;
}

.kpi{

    position:relative;

    overflow:hidden;

    padding:23px;

    background:rgba(255,255,255,.9);

    border:1px solid var(--border);

    border-radius:22px;

    box-shadow:var(--shadow);

    transition:.25s;
}

.kpi:hover{

    transform:translateY(-4px);

    box-shadow:
        0 28px 70px rgba(26,72,110,.15);
}

.kpi-top{

    display:flex;

    justify-content:space-between;
    align-items:center;
}

.kpi-icon{

    width:43px;
    height:43px;

    display:grid;
    place-items:center;

    border-radius:14px;

    font-size:20px;
}

.kpi:nth-child(1) .kpi-icon{
    background:#e8f3ff;
}

.kpi:nth-child(2) .kpi-icon{
    background:#e9fbf4;
}

.kpi:nth-child(3) .kpi-icon{
    background:#fff5e8;
}

.kpi:nth-child(4) .kpi-icon{
    background:#fff0f2;
}

.kpi-label{

    margin-top:18px;

    color:var(--muted);

    font-size:12px;

    font-weight:600;
}

.kpi-value{

    margin-top:3px;

    font-size:31px;

    font-weight:800;

    letter-spacing:-1px;
}

.kpi-small{

    margin-top:4px;

    color:var(--muted);

    font-size:10px;
}


/* ======================================================
   SHRIMP CARDS
====================================================== */

.shrimp-grid{

    display:grid;

    grid-template-columns:
        repeat(4,1fr);

    gap:16px;
}

.shrimp{

    position:relative;

    overflow:hidden;

    padding:22px;

    min-height:165px;

    background:white;

    border-radius:23px;

    border:1px solid var(--border);

    box-shadow:var(--shadow);

    transition:.25s;
}

.shrimp:hover{

    transform:translateY(-5px);

}

.shrimp:after{

    content:"";

    position:absolute;

    width:110px;
    height:110px;

    border-radius:50%;

    right:-45px;
    bottom:-50px;

    background:var(--accent);

    opacity:.08;
}

.shrimp-icon{

    width:48px;
    height:48px;

    display:grid;
    place-items:center;

    border-radius:16px;

    background:var(--soft);

    font-size:24px;

    margin-bottom:16px;
}

.shrimp-name{

    color:var(--muted);

    font-size:12px;

    font-weight:700;
}

.shrimp-count{

    margin-top:2px;

    font-size:30px;

    font-weight:800;
}

.shrimp-unit{

    font-size:11px;
    color:var(--muted);
}

.shrimp-bar{

    height:5px;

    margin-top:13px;

    background:#edf3f7;

    border-radius:99px;

    overflow:hidden;
}

.shrimp-bar span{

    display:block;

    height:100%;

    width:0%;

    background:var(--accent);

    border-radius:99px;

    transition:width .7s ease;
}


/* ======================================================
   CONTENT GRID
====================================================== */

.content-grid{

    display:grid;

    grid-template-columns:
        1.5fr 1fr;

    gap:18px;

    margin-top:18px;
}

.panel{

    background:rgba(255,255,255,.94);

    border:1px solid var(--border);

    border-radius:25px;

    padding:25px;

    box-shadow:var(--shadow);
}

.panel-head{

    display:flex;

    justify-content:space-between;
    align-items:center;

    margin-bottom:20px;
}

.panel-head h3{

    margin:0;

    font-size:16px;
}

.panel-head span{

    color:var(--muted);

    font-size:11px;
}


/* ======================================================
   CHART
====================================================== */

.chart-wrap{

    height:280px;

    display:flex;

    align-items:center;
    justify-content:center;

    position:relative;
}

canvas{

    max-width:100%;
}


/* ======================================================
   ROUND SUMMARY
====================================================== */

.round-id{

    padding:7px 11px;

    border-radius:10px;

    background:#edf7ff;

    color:#0876e8;

    font-size:11px;

    font-weight:800;
}

.summary-number{

    font-size:52px;

    font-weight:800;

    letter-spacing:-3px;

    line-height:1;

    margin:12px 0 5px;
}

.summary-label{

    color:var(--muted);

    font-size:12px;
}

.progress{

    height:9px;

    margin:25px 0 10px;

    background:#edf2f6;

    border-radius:99px;

    overflow:hidden;
}

.progress span{

    display:block;

    height:100%;

    width:0%;

    background:
        linear-gradient(
            90deg,
            #00c6ff,
            #1687ff,
            #7957ff
        );

    border-radius:99px;

    transition:width .8s ease;
}

.summary-grid{

    display:grid;

    grid-template-columns:1fr 1fr;

    gap:10px;

    margin-top:20px;
}

.mini{

    padding:13px;

    border-radius:14px;

    background:#f7fafc;
}

.mini label{

    display:block;

    color:var(--muted);

    font-size:10px;
}

.mini strong{

    display:block;

    margin-top:4px;

    font-size:16px;
}


/* ======================================================
   HISTORY
====================================================== */

.history-panel{

    margin-top:18px;
}

.table-wrap{

    overflow-x:auto;
}

table{

    width:100%;

    border-collapse:collapse;

    font-size:12px;
}

th{

    text-align:left;

    color:#8492a3;

    font-size:10px;

    font-weight:700;

    padding:13px;

    border-bottom:1px solid #edf2f6;

}

td{

    padding:15px 13px;

    border-bottom:1px solid #f0f4f7;

    white-space:nowrap;
}

tr:last-child td{
    border-bottom:0;
}

.round-pill{

    display:inline-flex;

    padding:6px 9px;

    background:#edf7ff;

    color:#1687ff;

    border-radius:8px;

    font-weight:800;
}

.sick-pill{

    display:inline-flex;

    padding:5px 8px;

    background:#fff0f2;

    color:#e7485b;

    border-radius:7px;

    font-weight:700;
}

.empty{

    padding:55px 20px;

    text-align:center;

    color:var(--muted);
}

.empty-icon{

    font-size:40px;

    margin-bottom:10px;
}


/* ======================================================
   LIVE PAGE
====================================================== */

.live-layout{

    display:grid;

    grid-template-columns:
        1.65fr .7fr;

    gap:18px;
}

.camera{

    position:relative;

    overflow:hidden;

    min-height:600px;

    border-radius:28px;

    background:#091827;

    box-shadow:
        0 25px 70px rgba(7,28,49,.22);
}

.camera img{

    width:100%;
    height:100%;

    min-height:600px;

    object-fit:cover;

    display:block;
}

.camera-overlay{

    position:absolute;

    left:18px;
    right:18px;
    top:18px;

    display:flex;

    justify-content:space-between;

    align-items:center;
}

.camera-status{

    display:flex;
    align-items:center;
    gap:8px;

    padding:9px 13px;

    border-radius:12px;

    color:white;

    background:rgba(5,22,39,.65);

    backdrop-filter:blur(12px);

    font-size:11px;

    font-weight:700;
}

.live-dot{

    width:8px;
    height:8px;

    border-radius:50%;

    background:#16d391;

    animation:pulse 1.5s infinite;
}

@keyframes pulse{

    0%,100%{
        box-shadow:0 0 0 0 rgba(22,211,145,.4);
    }

    50%{
        box-shadow:0 0 0 9px rgba(22,211,145,0);
    }
}

.no-camera{

    position:absolute;

    inset:0;

    display:grid;

    place-items:center;

    color:#8ba2b8;

    text-align:center;
}

.no-camera div{

    padding:30px;
}

.no-camera-icon{

    font-size:55px;

    margin-bottom:10px;
}

.live-side{

    display:flex;

    flex-direction:column;

    gap:16px;
}


/* ======================================================
   FOOTER
====================================================== */

.footer{

    text-align:center;

    color:#8a99aa;

    font-size:10px;

    padding-top:35px;
}


/* ======================================================
   RESPONSIVE
====================================================== */

@media(max-width:1100px){

    .kpi-grid,
    .shrimp-grid{

        grid-template-columns:
            repeat(2,1fr);
    }

    .content-grid,
    .live-layout{

        grid-template-columns:1fr;
    }

}

@media(max-width:700px){

    .navbar{

        padding:0 17px;
    }

    .nav-right .status{
        display:none;
    }

    .container{

        width:min(
            100% - 24px,
            1440px
        );

        padding-top:18px;
    }

    .hero{

        padding:28px;

        border-radius:23px;
    }

    .hero h2{

        font-size:31px;
    }

    .hero-actions{

        flex-direction:column;
    }

    .hero-button{

        width:100%;
    }

    .kpi-grid,
    .shrimp-grid{

        grid-template-columns:1fr;
    }

    .panel{

        padding:18px;
    }

    .camera,
    .camera img{

        min-height:420px;
    }

}

</style>

</head>


<body>


<!-- =====================================================
     NAVBAR
====================================================== -->

<nav class="navbar">

    <a class="brand" href="/">

        <div class="logo">
            🦐
        </div>

        <div class="brand-text">

            <h1>Shrimp Vision AI</h1>

            <span>
                Intelligent Shrimp Sorting System
            </span>

        </div>

    </a>


    <div class="nav-right">

        <div class="status">

            <span class="status-dot"></span>

            AI SYSTEM ONLINE

        </div>

        <a class="nav-btn" href="/">
            Dashboard
        </a>

        <a class="nav-btn" href="/live">
            Live Camera
        </a>

    </div>

</nav>



<main class="container">


<!-- =====================================================
     HERO
====================================================== -->

<section class="hero">

    <div class="hero-content">

        <div class="hero-kicker">
            ✦ AI-POWERED QUALITY CONTROL
        </div>

        <h2>
            ระบบคัดแยกกุ้ง<br>
            อัจฉริยะสำหรับโรงงาน
        </h2>

        <p>
            วิเคราะห์และสรุปผลการคัดแยกกุ้งด้วย AI
            แบบเป็นรอบ พร้อมติดตามจำนวนกุ้ง
            คุณภาพ และกุ้งป่วยจากศูนย์กลางเดียว
        </p>

        <div class="hero-actions">

            <a
                class="hero-button"
                href="/live"
            >
                ▶ เปิดกล้อง Real-time
            </a>

            <button
                class="hero-button secondary"
                onclick="loadData()"
            >
                ↻ รีเฟรชข้อมูล
            </button>

        </div>

    </div>

</section>



<!-- =====================================================
     KPI
====================================================== -->

<div class="section-title">

    <h3>
        ภาพรวมการทำงาน
    </h3>

    <span id="lastUpdate">
        กำลังโหลด...
    </span>

</div>


<section class="kpi-grid">


    <div class="kpi">

        <div class="kpi-top">

            <div class="kpi-icon">
                🧠
            </div>

        </div>

        <div class="kpi-label">
            รอบล่าสุด
        </div>

        <div
            class="kpi-value"
            id="kpiRound"
        >
            —
        </div>

        <div class="kpi-small">
            AI Processing Round
        </div>

    </div>



    <div class="kpi">

        <div class="kpi-top">

            <div class="kpi-icon">
                🦐
            </div>

        </div>

        <div class="kpi-label">
            กุ้งทั้งหมด
        </div>

        <div
            class="kpi-value"
            id="kpiTotal"
        >
            0
        </div>

        <div class="kpi-small">
            Total Detected
        </div>

    </div>



    <div class="kpi">

        <div class="kpi-top">

            <div class="kpi-icon">
                ✓
            </div>

        </div>

        <div class="kpi-label">
            กุ้งปกติ
        </div>

        <div
            class="kpi-value"
            id="kpiNormal"
        >
            0
        </div>

        <div class="kpi-small">
            Normal Shrimp
        </div>

    </div>



    <div class="kpi">

        <div class="kpi-top">

            <div class="kpi-icon">
                ⚠
            </div>

        </div>

        <div class="kpi-label">
            กุ้งป่วย
        </div>

        <div
            class="kpi-value"
            id="kpiSick"
        >
            0
        </div>

        <div class="kpi-small">
            Quality Alert
        </div>

    </div>

</section>



<!-- =====================================================
     SHRIMP TYPES
====================================================== -->

<div class="section-title">

    <h3>
        ผลการจำแนกประเภท
    </h3>

    <span>
        AI Classification
    </span>

</div>


<section class="shrimp-grid">


    <div
        class="shrimp"
        style="--accent:#1687ff;--soft:#eaf4ff"
    >

        <div class="shrimp-icon">
            🦐
        </div>

        <div class="shrimp-name">
            กุ้งเล็ก
        </div>

        <div
            class="shrimp-count"
            id="smallCount"
        >
            0
        </div>

        <span class="shrimp-unit">
            ตัว
        </span>

        <div class="shrimp-bar">
            <span id="smallBar"></span>
        </div>

    </div>



    <div
        class="shrimp"
        style="--accent:#7957ff;--soft:#f0edff"
    >

        <div class="shrimp-icon">
            🦐
        </div>

        <div class="shrimp-name">
            กุ้งกลาง
        </div>

        <div
            class="shrimp-count"
            id="mediumCount"
        >
            0
        </div>

        <span class="shrimp-unit">
            ตัว
        </span>

        <div class="shrimp-bar">
            <span id="mediumBar"></span>
        </div>

    </div>



    <div
        class="shrimp"
        style="--accent:#ff9d42;--soft:#fff5e8"
    >

        <div class="shrimp-icon">
            🦐
        </div>

        <div class="shrimp-name">
            กุ้งใหญ่
        </div>

        <div
            class="shrimp-count"
            id="largeCount"
        >
            0
        </div>

        <span class="shrimp-unit">
            ตัว
        </span>

        <div class="shrimp-bar">
            <span id="largeBar"></span>
        </div>

    </div>



    <div
        class="shrimp"
        style="--accent:#ff5364;--soft:#fff0f2"
    >

        <div class="shrimp-icon">
            ⚠️
        </div>

        <div class="shrimp-name">
            กุ้งป่วย
        </div>

        <div
            class="shrimp-count"
            id="sickCount"
        >
            0
        </div>

        <span class="shrimp-unit">
            ตัว
        </span>

        <div class="shrimp-bar">
            <span id="sickBar"></span>
        </div>

    </div>


</section>



<!-- =====================================================
     CHART + SUMMARY
====================================================== -->

<section class="content-grid">


    <div class="panel">

        <div class="panel-head">

            <h3>
                สัดส่วนการคัดแยก
            </h3>

            <span>
                Latest Round
            </span>

        </div>

        <div class="chart-wrap">

            <canvas
                id="donut"
                width="500"
                height="280"
            ></canvas>

        </div>

    </div>



    <div class="panel">

        <div class="panel-head">

            <h3>
                สรุปรอบล่าสุด
            </h3>

            <span
                class="round-id"
                id="roundBadge"
            >
                —
            </span>

        </div>


        <div
            class="summary-number"
            id="summaryTotal"
        >
            0
        </div>

        <div class="summary-label">
            กุ้งที่ตรวจพบทั้งหมด
        </div>


        <div class="progress">

            <span id="qualityProgress"></span>

        </div>


        <div class="summary-grid">


            <div class="mini">

                <label>
                    FPS เฉลี่ย
                </label>

                <strong id="fps">
                    —
                </strong>

            </div>


            <div class="mini">

                <label>
                    ระยะเวลารอบ
                </label>

                <strong id="duration">
                    —
                </strong>

            </div>


            <div class="mini">

                <label>
                    จำนวน Frame
                </label>

                <strong id="frames">
                    —
                </strong>

            </div>


            <div class="mini">

                <label>
                    อัตรากุ้งปกติ
                </label>

                <strong id="quality">
                    —
                </strong>

            </div>


        </div>

    </div>


</section>



<!-- =====================================================
     HISTORY
====================================================== -->

<section class="panel history-panel">

    <div class="panel-head">

        <h3>
            ประวัติการทำงาน
        </h3>

        <span>
            Latest 100 Rounds
        </span>

    </div>


    <div class="table-wrap">

        <table>

            <thead>

                <tr>

                    <th>
                        รอบ
                    </th>

                    <th>
                        ทั้งหมด
                    </th>

                    <th>
                        เล็ก
                    </th>

                    <th>
                        กลาง
                    </th>

                    <th>
                        ใหญ่
                    </th>

                    <th>
                        ป่วย
                    </th>

                    <th>
                        FPS
                    </th>

                    <th>
                        เวลา
                    </th>

                </tr>

            </thead>

            <tbody id="history">

            </tbody>

        </table>

    </div>

</section>


<div class="footer">

    SHRIMP VISION AI · Intelligent Quality Control System

</div>


</main>



<script>


// ======================================================
// UTIL
// ======================================================

function number(n){

    return Number(n || 0).toLocaleString("th-TH");

}


function escapeHtml(text){

    const div = document.createElement("div");

    div.textContent = text ?? "";

    return div.innerHTML;

}


// ======================================================
// DONUT CHART
// ======================================================

function drawDonut(counts){

    const canvas = document.getElementById("donut");

    const ctx = canvas.getContext("2d");

    const dpr = window.devicePixelRatio || 1;

    const width = canvas.clientWidth || 500;

    const height = 280;

    canvas.width = width * dpr;

    canvas.height = height * dpr;

    ctx.scale(dpr,dpr);

    ctx.clearRect(0,0,width,height);


    const values = [

        Number(counts["กุ้งเล็ก"] || 0),

        Number(counts["กุ้งกลาง"] || 0),

        Number(counts["กุ้งใหญ่"] || 0),

        Number(counts["กุ้งป่วย"] || 0)

    ];


    const labels = [

        "กุ้งเล็ก",
        "กุ้งกลาง",
        "กุ้งใหญ่",
        "กุ้งป่วย"

    ];


    const colors = [

        "#1687ff",
        "#7957ff",
        "#ff9d42",
        "#ff5364"

    ];


    const total = values.reduce(
        (a,b)=>a+b,
        0
    );


    if(total === 0){

        ctx.beginPath();

        ctx.arc(
            width/2 - 70,
            height/2,
            72,
            0,
            Math.PI*2
        );

        ctx.strokeStyle="#e9f0f5";

        ctx.lineWidth=25;

        ctx.stroke();

        ctx.fillStyle="#718096";

        ctx.font="600 13px Noto Sans Thai";

        ctx.textAlign="center";

        ctx.fillText(
            "ยังไม่มีข้อมูล",
            width/2 - 70,
            height/2 + 5
        );

        return;
    }


    let angle = -Math.PI/2;

    const cx = width/2 - 70;

    const cy = height/2;

    const radius = 72;


    values.forEach((value,index)=>{

        const slice =
            (value / total) * Math.PI * 2;

        ctx.beginPath();

        ctx.arc(
            cx,
            cy,
            radius,
            angle,
            angle + slice
        );

        ctx.strokeStyle =
            colors[index];

        ctx.lineWidth=25;

        ctx.lineCap="round";

        ctx.stroke();

        angle += slice;

    });


    ctx.fillStyle="#10233d";

    ctx.font="800 25px Inter";

    ctx.textAlign="center";

    ctx.fillText(
        total.toLocaleString(),
        cx,
        cy + 7
    );


    ctx.fillStyle="#718096";

    ctx.font="11px Noto Sans Thai";

    ctx.fillText(
        "ตัว",
        cx,
        cy + 27
    );


    labels.forEach((label,index)=>{

        const y =
            62 + index * 50;

        ctx.beginPath();

        ctx.arc(
            width - 135,
            y - 4,
            5,
            0,
            Math.PI*2
        );

        ctx.fillStyle=colors[index];

        ctx.fill();


        ctx.textAlign="left";

        ctx.fillStyle="#718096";

        ctx.font="600 11px Noto Sans Thai";

        ctx.fillText(
            label,
            width - 122,
            y
        );


        ctx.fillStyle="#10233d";

        ctx.font="800 13px Inter";

        ctx.fillText(
            values[index].toLocaleString(),
            width - 122,
            y + 19
        );

    });

}


// ======================================================
// UPDATE UI
// ======================================================

function updateDashboard(data){

    const latest = data.latest;

    if(!latest){

        document.getElementById("lastUpdate")
            .textContent =
            "ยังไม่มีรอบการประมวลผล";

        return;

    }


    const counts =
        latest.counts || {};


    const total =
        Number(latest.total || 0);

    const normal =
        Number(latest.normal_total || 0);

    const sick =
        Number(latest.sick_total || 0);


    document.getElementById("kpiRound")
        .textContent =
        latest.round_id ?? "—";


    document.getElementById("kpiTotal")
        .textContent =
        number(total);


    document.getElementById("kpiNormal")
        .textContent =
        number(normal);


    document.getElementById("kpiSick")
        .textContent =
        number(sick);


    document.getElementById("summaryTotal")
        .textContent =
        number(total);


    document.getElementById("roundBadge")
        .textContent =
        "ROUND " + (latest.round_id ?? "—");


    document.getElementById("fps")
        .textContent =
        Number(latest.avg_fps || 0)
        .toFixed(1);


    document.getElementById("duration")
        .textContent =
        Number(latest.duration || 0)
        .toFixed(1) + " s";


    document.getElementById("frames")
        .textContent =
        number(latest.frames);


    const quality =
        total > 0
            ? (normal / total) * 100
            : 0;


    document.getElementById("quality")
        .textContent =
        quality.toFixed(1) + "%";


    document.getElementById("qualityProgress")
        .style.width =
        quality + "%";


    const mapping = {

        "กุ้งเล็ก":"small",
        "กุ้งกลาง":"medium",
        "กุ้งใหญ่":"large",
        "กุ้งป่วย":"sick"

    };


    SHRIMP_TYPES.forEach(type=>{

        const key = mapping[type];

        const value =
            Number(counts[type] || 0);


        document.getElementById(
            key + "Count"
        ).textContent =
            number(value);


        const percent =
            total > 0
                ? (value / total) * 100
                : 0;


        document.getElementById(
            key + "Bar"
        ).style.width =
            percent + "%";

    });


    drawDonut(counts);


    document.getElementById("lastUpdate")
        .textContent =
        latest.finished_at
            ? "จบรอบล่าสุด " + latest.finished_at
            : "อัปเดตล่าสุด";

}


// ======================================================
// HISTORY
// ======================================================

function renderHistory(history){

    const tbody =
        document.getElementById("history");


    if(!history || history.length === 0){

        tbody.innerHTML = `

            <tr>

                <td colspan="8">

                    <div class="empty">

                        <div class="empty-icon">
                            🦐
                        </div>

                        <div>
                            ยังไม่มีข้อมูลการประมวลผล
                        </div>

                    </div>

                </td>

            </tr>

        `;

        return;
    }


    tbody.innerHTML =
        history.map(row=>{

            const c =
                row.counts || {};


            return `

                <tr>

                    <td>
                        <span class="round-pill">
                            #${escapeHtml(row.round_id)}
                        </span>
                    </td>

                    <td>
                        <strong>
                            ${number(row.total)}
                        </strong>
                    </td>

                    <td>
                        ${number(c["กุ้งเล็ก"])}
                    </td>

                    <td>
                        ${number(c["กุ้งกลาง"])}
                    </td>

                    <td>
                        ${number(c["กุ้งใหญ่"])}
                    </td>

                    <td>
                        <span class="sick-pill">
                            ${number(c["กุ้งป่วย"])}
                        </span>
                    </td>

                    <td>
                        ${Number(row.avg_fps || 0).toFixed(1)}
                    </td>

                    <td>
                        ${escapeHtml(
                            row.finished_at || "-"
                        )}
                    </td>

                </tr>

            `;

        }).join("");

}


// ======================================================
// LOAD DATA
// ======================================================

async function loadData(){

    try{

        const response =
            await fetch(
                "/api/dashboard",
                {
                    cache:"no-store"
                }
            );


        const data =
            await response.json();


        updateDashboard(data);

        renderHistory(data.history);


    }catch(error){

        console.error(error);

        document.getElementById(
            "lastUpdate"
        ).textContent =
            "เชื่อมต่อระบบไม่ได้";

    }

}


// ======================================================
// INITIAL
// ======================================================

loadData();


// Update every 3 seconds

setInterval(
    loadData,
    3000
);


window.addEventListener(
    "resize",
    ()=>{
        if(window.lastCounts){
            drawDonut(window.lastCounts);
        }
    }
);

</script>


</body>

</html>
"""


# =========================================================
# LIVE HTML
# =========================================================

LIVE_HTML = HTML.replace(

    '<main class="container">',

    r'''
<main class="container">

<section class="hero" style="margin-bottom:20px">

    <div class="hero-content">

        <div class="hero-kicker">
            ✦ REAL-TIME AI VISION
        </div>

        <h2>
            กล้องตรวจสอบ<br>
            Real-time
        </h2>

        <p>
            ดูภาพจากกล้อง AI พร้อมสถานะระบบ
            และผลการตรวจจับล่าสุดแบบเรียลไทม์
        </p>

    </div>

</section>


<section class="live-layout">


    <div class="camera">

        <img
            id="liveImage"
            src="/api/live/frame"
            onerror="this.style.display='none'"
        >


        <div
            class="no-camera"
            id="noCamera"
        >

            <div>

                <div class="no-camera-icon">
                    📷
                </div>

                <strong>
                    กำลังรอสัญญาณจาก AI
                </strong>

                <p>
                    เมื่อกล้องเริ่มส่งข้อมูล
                    ภาพจะแสดงที่นี่อัตโนมัติ
                </p>

            </div>

        </div>


        <div class="camera-overlay">

            <div class="camera-status">

                <span class="live-dot"></span>

                LIVE AI CAMERA

            </div>


            <div
                class="camera-status"
                id="cameraTime"
            >
                —
            </div>

        </div>

    </div>



    <div class="live-side">


        <div class="panel">

            <div class="panel-head">

                <h3>
                    Camera Status
                </h3>

            </div>


            <div class="summary-number"
                 id="liveFps">

                —

            </div>

            <div class="summary-label">
                FPS ของรอบล่าสุด
            </div>

        </div>



        <div class="panel">

            <div class="panel-head">

                <h3>
                    รอบล่าสุด
                </h3>

                <span
                    class="round-id"
                    id="liveRound"
                >
                    —
                </span>

            </div>


            <div class="summary-number"
                 id="liveTotal">

                0

            </div>

            <div class="summary-label">
                กุ้งทั้งหมด
            </div>


            <div class="summary-grid">


                <div class="mini">

                    <label>
                        กุ้งเล็ก
                    </label>

                    <strong id="liveSmall">
                        0
                    </strong>

                </div>


                <div class="mini">

                    <label>
                        กุ้งกลาง
                    </label>

                    <strong id="liveMedium">
                        0
                    </strong>

                </div>


                <div class="mini">

                    <label>
                        กุ้งใหญ่
                    </label>

                    <strong id="liveLarge">
                        0
                    </strong>

                </div>


                <div class="mini">

                    <label>
                        กุ้งป่วย
                    </label>

                    <strong id="liveSick">
                        0
                    </strong>

                </div>


            </div>

        </div>


        <a
            href="/"
            class="hero-button"
            style="
                text-align:center;
                display:block;
            "
        >
            ← กลับ Dashboard
        </a>


    </div>


</section>


<div class="footer">

    SHRIMP VISION AI · REAL-TIME MONITORING

</div>
'''
)


# =========================================================
# LIVE SCRIPT
# =========================================================

LIVE_SCRIPT = r"""

<script>

let lastFrame = 0;


function number(n){

    return Number(n || 0).toLocaleString("th-TH");

}


async function updateLive(){

    try{

        const status =
            await fetch(
                "/api/live/status",
                {cache:"no-store"}
            );

        const s =
            await status.json();


        const img =
            document.getElementById(
                "liveImage"
            );

        const empty =
            document.getElementById(
                "noCamera"
            );


        if(s.online){

            img.style.display="block";

            empty.style.display="none";

            img.src =
                "/api/live/frame?t="
                + Date.now();

            document.getElementById(
                "cameraTime"
            ).textContent =
                new Date().toLocaleTimeString(
                    "th-TH"
                );

        }else{

            img.style.display="none";

            empty.style.display="grid";

        }


        const data =
            await fetch(
                "/api/dashboard",
                {cache:"no-store"}
            );


        const dashboard =
            await data.json();


        const latest =
            dashboard.latest;


        if(latest){

            const c =
                latest.counts || {};


            document.getElementById(
                "liveFps"
            ).textContent =
                Number(
                    latest.avg_fps || 0
                ).toFixed(1);


            document.getElementById(
                "liveRound"
            ).textContent =
                "ROUND " +
                (latest.round_id ?? "—");


            document.getElementById(
                "liveTotal"
            ).textContent =
                number(latest.total);


            document.getElementById(
                "liveSmall"
            ).textContent =
                number(c["กุ้งเล็ก"]);


            document.getElementById(
                "liveMedium"
            ).textContent =
                number(c["กุ้งกลาง"]);


            document.getElementById(
                "liveLarge"
            ).textContent =
                number(c["กุ้งใหญ่"]);


            document.getElementById(
                "liveSick"
            ).textContent =
                number(c["กุ้งป่วย"]);

        }


    }catch(error){

        console.error(error);

    }

}


updateLive();

setInterval(
    updateLive,
    1500
);

</script>

"""


LIVE_HTML = LIVE_HTML.replace(
    "</body>",
    LIVE_SCRIPT + "</body>"
)


# =========================================================
# ROUTES
# =========================================================

@app.get("/", response_class=HTMLResponse)
def home():

    return HTMLResponse(
        content=HTML,
        headers={
            "Cache-Control":"no-store"
        }
    )


@app.get("/live", response_class=HTMLResponse)
def live():

    return HTMLResponse(
        content=LIVE_HTML,
        headers={
            "Cache-Control":"no-store"
        }
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.environ.get(
            "PORT",
            8000
        )
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )
