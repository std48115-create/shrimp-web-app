from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from collections import deque
from datetime import datetime
from typing import Optional
import base64
import os
import uvicorn


# =========================================================
# APP
# =========================================================

app = FastAPI(title="Shrimp Vision AI")


# =========================================================
# CONFIG
# =========================================================

API_KEY = os.getenv("API_KEY", "change-me")
PORT = int(os.getenv("PORT", "10000"))

SHRIMP_TYPES = [
    "กุ้งเล็ก",
    "กุ้งกลาง",
    "กุ้งใหญ่",
    "กุ้งป่วย",
]


# =========================================================
# MEMORY STORAGE
# =========================================================

latest_round = None

round_history = deque(maxlen=1000)

live_frame = None
live_ts = None
live_info = {
    "fps": 0,
    "status": "offline",
    "last_update": None,
}


# =========================================================
# MODELS
# =========================================================

class RoundReport(BaseModel):
    round_id: int

    counts: dict[str, int] = Field(default_factory=dict)

    avg_fps: float = 0
    duration: float = 0
    frames: int = 0

    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class LiveReport(BaseModel):
    frame: str

    fps: float = 0

    status: str = "online"

    timestamp: Optional[str] = None


# =========================================================
# HELPERS
# =========================================================

def check_api_key(key: Optional[str]):
    if key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )


def clean_counts(counts):
    result = {}

    for shrimp_type in SHRIMP_TYPES:
        try:
            result[shrimp_type] = max(
                0,
                int(counts.get(shrimp_type, 0))
            )
        except Exception:
            result[shrimp_type] = 0

    return result


def parse_datetime(value):
    if not value:
        return datetime.now()

    if isinstance(value, datetime):
        return value

    value = str(value).strip()

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    except Exception:
        return datetime.now()


def get_round_datetime(item):
    return parse_datetime(
        item.get("finished_at")
        or item.get("started_at")
        or item.get("received_at")
    )


def total_count(counts):
    return sum(counts.get(x, 0) for x in SHRIMP_TYPES)


def make_round_record(report: RoundReport):
    counts = clean_counts(report.counts)

    now = datetime.now()

    return {
        "round_id": report.round_id,
        "counts": counts,
        "total": total_count(counts),
        "avg_fps": report.avg_fps,
        "duration": report.duration,
        "frames": report.frames,
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "received_at": now.isoformat(),
    }


def decode_frame(frame_data):
    if not frame_data:
        return None

    if "," in frame_data:
        frame_data = frame_data.split(",", 1)[1]

    try:
        return base64.b64decode(frame_data)
    except Exception:
        return None


# =========================================================
# API - ROUND
# =========================================================

@app.post("/api/round")
async def receive_round(
    report: RoundReport,
    x_api_key: Optional[str] = Header(None)
):
    global latest_round

    check_api_key(x_api_key)

    record = make_round_record(report)

    latest_round = record

    round_history.append(record)

    return {
        "success": True,
        "message": "Round received",
        "round_id": report.round_id,
    }


# =========================================================
# API - LIVE CAMERA
# =========================================================

@app.post("/api/live")
async def receive_live(
    report: LiveReport,
    x_api_key: Optional[str] = Header(None)
):
    global live_frame
    global live_ts
    global live_info

    check_api_key(x_api_key)

    decoded = decode_frame(report.frame)

    if decoded:
        live_frame = decoded

    now = datetime.now()

    live_ts = now

    live_info = {
        "fps": report.fps,
        "status": report.status,
        "last_update": now.isoformat(),
    }

    return {
        "success": True
    }


# =========================================================
# API - DASHBOARD
# =========================================================

@app.get("/api/dashboard")
async def dashboard_data():
    return {
        "latest_round": latest_round,
        "history": list(round_history)[-20:],
        "total_rounds": len(round_history),
    }


# =========================================================
# API - LIVE STATUS
# =========================================================

@app.get("/api/live/status")
async def live_status():

    status = live_info.copy()

    if live_ts:
        elapsed = (
            datetime.now() - live_ts
        ).total_seconds()

        if elapsed > 5:
            status["status"] = "offline"

    return status


# =========================================================
# API - LIVE FRAME
# =========================================================

@app.get("/api/live/frame")
async def live_frame_api():

    if not live_frame:
        raise HTTPException(
            status_code=404,
            detail="No camera frame"
        )

    return Response(
        content=live_frame,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store"
        }
    )


# =========================================================
# ANALYTICS
# =========================================================

def aggregate_daily():

    buckets = {}

    for item in round_history:

        dt = get_round_datetime(item)

        key = dt.strftime("%Y-%m-%d")

        if key not in buckets:
            buckets[key] = {
                "period": key,
                "label": dt.strftime("%d/%m"),
                "counts": {
                    x: 0 for x in SHRIMP_TYPES
                },
                "total": 0,
                "rounds": 0,
            }

        counts = clean_counts(item.get("counts", {}))

        for shrimp_type in SHRIMP_TYPES:
            buckets[key]["counts"][shrimp_type] += counts[shrimp_type]

        buckets[key]["total"] += total_count(counts)
        buckets[key]["rounds"] += 1

    return sorted(
        buckets.values(),
        key=lambda x: x["period"]
    )


def aggregate_monthly():

    buckets = {}

    for item in round_history:

        dt = get_round_datetime(item)

        key = dt.strftime("%Y-%m")

        if key not in buckets:
            buckets[key] = {
                "period": key,
                "label": dt.strftime("%m/%Y"),
                "counts": {
                    x: 0 for x in SHRIMP_TYPES
                },
                "total": 0,
                "rounds": 0,
            }

        counts = clean_counts(item.get("counts", {}))

        for shrimp_type in SHRIMP_TYPES:
            buckets[key]["counts"][shrimp_type] += counts[shrimp_type]

        buckets[key]["total"] += total_count(counts)
        buckets[key]["rounds"] += 1

    return sorted(
        buckets.values(),
        key=lambda x: x["period"]
    )


def aggregate_yearly():

    buckets = {}

    for item in round_history:

        dt = get_round_datetime(item)

        key = dt.strftime("%Y")

        if key not in buckets:
            buckets[key] = {
                "period": key,
                "label": key,
                "counts": {
                    x: 0 for x in SHRIMP_TYPES
                },
                "total": 0,
                "rounds": 0,
            }

        counts = clean_counts(item.get("counts", {}))

        for shrimp_type in SHRIMP_TYPES:
            buckets[key]["counts"][shrimp_type] += counts[shrimp_type]

        buckets[key]["total"] += total_count(counts)
        buckets[key]["rounds"] += 1

    return sorted(
        buckets.values(),
        key=lambda x: x["period"]
    )


# =========================================================
# ANALYTICS API
# =========================================================

@app.get("/api/analytics/daily")
async def analytics_daily():

    data = aggregate_daily()

    return {
        "type": "daily",
        "data": data[-30:],
    }


@app.get("/api/analytics/monthly")
async def analytics_monthly():

    data = aggregate_monthly()

    return {
        "type": "monthly",
        "data": data[-12:],
    }


@app.get("/api/analytics/yearly")
async def analytics_yearly():

    data = aggregate_yearly()

    return {
        "type": "yearly",
        "data": data[-10:],
    }


# =========================================================
# COMMON CSS
# =========================================================

COMMON_CSS = """
* {
    box-sizing: border-box;
}

html {
    scroll-behavior: smooth;
}

body {
    margin: 0;
    font-family:
        Inter,
        "Noto Sans Thai",
        Arial,
        sans-serif;

    background:
        linear-gradient(
            135deg,
            #f7f9fc 0%,
            #eef3f8 100%
        );

    color: #16202a;
}

a {
    color: inherit;
    text-decoration: none;
}

.navbar {
    height: 76px;

    background: rgba(255,255,255,.90);

    backdrop-filter: blur(18px);

    border-bottom: 1px solid #e5eaf0;

    display: flex;
    align-items: center;

    padding: 0 5%;

    position: sticky;
    top: 0;
    z-index: 100;
}

.logo {
    font-size: 21px;
    font-weight: 800;

    display: flex;
    align-items: center;

    gap: 10px;

    white-space: nowrap;
}

.logo-icon {
    width: 38px;
    height: 38px;

    border-radius: 12px;

    background:
        linear-gradient(
            135deg,
            #111827,
            #34495e
        );

    color: white;

    display: flex;
    align-items: center;
    justify-content: center;

    font-size: 19px;
}

.nav {
    margin-left: auto;

    display: flex;
    align-items: center;

    gap: 7px;

    overflow-x: auto;
}

.nav a {
    padding: 10px 15px;

    border-radius: 12px;

    color: #65717e;

    font-size: 14px;

    font-weight: 600;

    white-space: nowrap;

    transition: .2s;
}

.nav a:hover,
.nav a.active {
    background: #edf2f6;
    color: #111827;
}

.container {
    width: min(1400px, 90%);

    margin: 0 auto;
}

.page {
    padding: 42px 0 70px;
}

.page-title {
    margin-bottom: 28px;
}

.page-title .eyebrow {
    color: #7b8794;

    font-size: 12px;

    font-weight: 800;

    text-transform: uppercase;

    letter-spacing: 1.8px;

    margin-bottom: 8px;
}

.page-title h1 {
    margin: 0;

    font-size: clamp(30px, 4vw, 48px);

    letter-spacing: -1.5px;
}

.page-title p {
    margin-top: 10px;

    color: #73808d;

    font-size: 15px;
}

.hero {
    padding: 55px 0 35px;
}

.hero-grid {
    display: grid;

    grid-template-columns:
        1.35fr
        .65fr;

    gap: 25px;

    align-items: stretch;
}

.hero-main {
    background:
        linear-gradient(
            135deg,
            #ffffff,
            #f1f5f8
        );

    border: 1px solid #e1e7ed;

    border-radius: 28px;

    padding: 45px;

    box-shadow:
        0 20px 50px rgba(31,41,55,.07);
}

.hero-main h1 {
    margin: 0;

    font-size: clamp(34px, 5vw, 64px);

    line-height: 1.02;

    letter-spacing: -2.5px;
}

.hero-main h1 span {
    color: #687785;
}

.hero-main p {
    color: #687785;

    max-width: 680px;

    line-height: 1.8;

    margin-top: 20px;
}

.hero-side {
    background: #111827;

    color: white;

    border-radius: 28px;

    padding: 35px;

    display: flex;

    flex-direction: column;

    justify-content: space-between;

    box-shadow:
        0 20px 50px rgba(17,24,39,.18);
}

.hero-side .number {
    font-size: 58px;

    font-weight: 800;

    letter-spacing: -3px;
}

.hero-side .label {
    color: #aeb8c3;

    font-size: 14px;
}

.btn {
    display: inline-flex;

    align-items: center;

    justify-content: center;

    gap: 8px;

    padding: 12px 18px;

    border-radius: 12px;

    font-weight: 700;

    font-size: 14px;

    transition: .2s;
}

.btn-dark {
    background: #111827;
    color: white;
}

.btn-light {
    background: white;

    border: 1px solid #dfe5eb;
}

.btn:hover {
    transform: translateY(-2px);
}

.kpi-grid {
    display: grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap: 16px;

    margin: 28px 0;
}

.kpi {
    background: rgba(255,255,255,.85);

    border: 1px solid #e3e8ed;

    border-radius: 20px;

    padding: 23px;

    box-shadow:
        0 10px 30px rgba(31,41,55,.045);
}

.kpi-label {
    color: #7d8995;

    font-size: 13px;

    font-weight: 600;
}

.kpi-value {
    margin-top: 8px;

    font-size: 31px;

    font-weight: 800;

    letter-spacing: -1px;
}

.shrimp-grid {
    display: grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap: 16px;

    margin-top: 18px;
}

.shrimp-card {
    background: white;

    border: 1px solid #e3e8ed;

    border-radius: 20px;

    padding: 22px;

    box-shadow:
        0 10px 30px rgba(31,41,55,.04);
}

.shrimp-card .icon {
    font-size: 28px;

    margin-bottom: 13px;
}

.shrimp-card .name {
    color: #75818d;

    font-size: 13px;
}

.shrimp-card .value {
    font-size: 30px;

    font-weight: 800;

    margin-top: 5px;
}

.section {
    margin-top: 32px;
}

.section-head {
    display: flex;

    justify-content: space-between;

    align-items: center;

    margin-bottom: 15px;
}

.section-head h2 {
    margin: 0;

    font-size: 20px;
}

.panel {
    background: white;

    border: 1px solid #e2e7ec;

    border-radius: 24px;

    padding: 25px;

    box-shadow:
        0 10px 35px rgba(31,41,55,.045);
}

.table-wrap {
    overflow-x: auto;
}

table {
    width: 100%;

    border-collapse: collapse;

    font-size: 14px;
}

th {
    text-align: left;

    color: #7d8995;

    font-size: 12px;

    font-weight: 700;

    padding: 13px;

    border-bottom: 1px solid #edf0f3;
}

td {
    padding: 15px 13px;

    border-bottom: 1px solid #f0f2f5;
}

.badge {
    display: inline-flex;

    padding: 6px 10px;

    border-radius: 999px;

    background: #f0f3f6;

    color: #4e5c69;

    font-size: 12px;

    font-weight: 700;
}

.chart-panel {
    min-height: 500px;

    position: relative;
}

.chart-box {
    width: 100%;

    height: 430px;

    position: relative;
}

canvas {
    width: 100% !important;

    height: 100% !important;
}

.chart-legend {
    display: flex;

    gap: 18px;

    flex-wrap: wrap;

    margin-top: 18px;

    color: #697582;

    font-size: 13px;
}

.legend-item {
    display: flex;

    align-items: center;

    gap: 7px;
}

.dot {
    width: 10px;
    height: 10px;

    border-radius: 50%;

    background: #111827;
}

.dot.a { background: #8b9aaa; }
.dot.b { background: #4e6477; }
.dot.c { background: #1f3445; }
.dot.d { background: #d27b72; }

.empty {
    min-height: 350px;

    display: flex;

    align-items: center;

    justify-content: center;

    text-align: center;

    color: #8a96a1;
}

.camera-panel {
    background: #101820;

    border-radius: 28px;

    overflow: hidden;

    box-shadow:
        0 25px 70px rgba(16,24,32,.18);
}

.camera-screen {
    width: 100%;

    aspect-ratio: 16 / 9;

    background:
        radial-gradient(
            circle at center,
            #27333d,
            #0b1117
        );

    display: flex;

    align-items: center;

    justify-content: center;

    position: relative;
}

.camera-screen img {
    width: 100%;
    height: 100%;

    object-fit: contain;
}

.camera-empty {
    color: #87939d;

    text-align: center;
}

.camera-status {
    padding: 17px 22px;

    display: flex;

    justify-content: space-between;

    align-items: center;

    color: white;
}

.status {
    display: inline-flex;

    align-items: center;

    gap: 8px;

    font-size: 13px;
}

.status-dot {
    width: 9px;
    height: 9px;

    border-radius: 50%;

    background: #ef4444;
}

.status.online .status-dot {
    background: #4ade80;
}

.live-stats {
    display: grid;

    grid-template-columns:
        repeat(3, 1fr);

    gap: 15px;

    margin-top: 20px;
}

.live-stat {
    background: white;

    border: 1px solid #e3e8ed;

    border-radius: 18px;

    padding: 20px;
}

.live-stat span {
    color: #7c8894;

    font-size: 12px;
}

.live-stat strong {
    display: block;

    margin-top: 5px;

    font-size: 25px;
}

.footer {
    padding: 35px 0;

    text-align: center;

    color: #8b96a1;

    font-size: 12px;
}

@media(max-width: 1000px) {
    .hero-grid {
        grid-template-columns: 1fr;
    }

    .kpi-grid,
    .shrimp-grid {
        grid-template-columns:
            repeat(2, 1fr);
    }
}

@media(max-width: 650px) {
    .navbar {
        height: auto;

        padding: 12px 5%;

        flex-direction: column;

        align-items: stretch;

        gap: 10px;
    }

    .nav {
        margin-left: 0;
    }

    .hero-main {
        padding: 30px;
    }

    .kpi-grid,
    .shrimp-grid,
    .live-stats {
        grid-template-columns: 1fr;
    }

    .page {
        padding-top: 28px;
    }

    .chart-box {
        height: 320px;
    }
}
"""


# =========================================================
# NAVBAR
# =========================================================

def navbar(active="dashboard"):

    return f"""
    <nav class="navbar">

        <a href="/" class="logo">
            <div class="logo-icon">🦐</div>
            Shrimp Vision AI
        </a>

        <div class="nav">

            <a href="/"
               class="{ 'active' if active == 'dashboard' else '' }">
                🏠 Dashboard
            </a>

            <a href="/daily"
               class="{ 'active' if active == 'daily' else '' }">
                📅 รายวัน
            </a>

            <a href="/monthly"
               class="{ 'active' if active == 'monthly' else '' }">
                📆 รายเดือน
            </a>

            <a href="/yearly"
               class="{ 'active' if active == 'yearly' else '' }">
                📊 รายปี
            </a>

            <a href="/live"
               class="{ 'active' if active == 'live' else '' }">
                📷 กล้อง Live
            </a>

        </div>

    </nav>
    """


# =========================================================
# HTML WRAPPER
# =========================================================

def html_page(title, body, active="dashboard", script=""):

    return f"""
    <!DOCTYPE html>

    <html lang="th">

    <head>

        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0"
        >

        <title>{title} | Shrimp Vision AI</title>

        <style>
            {COMMON_CSS}
        </style>

    </head>

    <body>

        {navbar(active)}

        {body}

        <footer class="footer">
            Shrimp Vision AI • Intelligent Shrimp Sorting System
        </footer>

        {script}

    </body>

    </html>
    """


# =========================================================
# DASHBOARD PAGE
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard_page():

    body = """

    <main class="container">

        <section class="hero">

            <div class="hero-grid">

                <div class="hero-main">

                    <div
                        style="
                        color:#7d8995;
                        font-size:12px;
                        font-weight:800;
                        letter-spacing:2px;
                        margin-bottom:15px;
                        "
                    >
                        INTELLIGENT SHRIMP SORTING
                    </div>

                    <h1>
                        Shrimp
                        <span>Vision AI</span>
                    </h1>

                    <p>
                        ระบบวิเคราะห์และคัดแยกกุ้งด้วย AI
                        พร้อมสรุปข้อมูลการตรวจสอบ
                        และติดตามประสิทธิภาพของกระบวนการผลิต
                    </p>

                    <div
                        style="
                        margin-top:25px;
                        display:flex;
                        gap:10px;
                        flex-wrap:wrap;
                        "
                    >

                        <a href="/daily"
                           class="btn btn-dark">
                            ดูสถิติ
                        </a>

                        <a href="/live"
                           class="btn btn-light">
                            เปิดกล้อง Live
                        </a>

                    </div>

                </div>

                <div class="hero-side">

                    <div>

                        <div class="label">
                            TOTAL SHRIMP
                        </div>

                        <div
                            class="number"
                            id="heroTotal"
                        >
                            0
                        </div>

                    </div>

                    <div class="label">
                        จากรอบการตรวจล่าสุด
                    </div>

                </div>

            </div>

        </section>


        <section class="kpi-grid">

            <div class="kpi">

                <div class="kpi-label">
                    รอบล่าสุด
                </div>

                <div
                    class="kpi-value"
                    id="roundId"
                >
                    -
                </div>

            </div>


            <div class="kpi">

                <div class="kpi-label">
                    กุ้งทั้งหมด
                </div>

                <div
                    class="kpi-value"
                    id="total"
                >
                    0
                </div>

            </div>


            <div class="kpi">

                <div class="kpi-label">
                    FPS เฉลี่ย
                </div>

                <div
                    class="kpi-value"
                    id="fps"
                >
                    0
                </div>

            </div>


            <div class="kpi">

                <div class="kpi-label">
                    จำนวนรอบทั้งหมด
                </div>

                <div
                    class="kpi-value"
                    id="rounds"
                >
                    0
                </div>

            </div>

        </section>


        <section>

            <div class="section-head">

                <h2>
                    ผลการคัดแยกล่าสุด
                </h2>

            </div>

            <div class="shrimp-grid">

                <div class="shrimp-card">

                    <div class="icon">🦐</div>

                    <div class="name">
                        กุ้งเล็ก
                    </div>

                    <div
                        class="value"
                        id="small"
                    >
                        0
                    </div>

                </div>


                <div class="shrimp-card">

                    <div class="icon">🦐</div>

                    <div class="name">
                        กุ้งกลาง
                    </div>

                    <div
                        class="value"
                        id="medium"
                    >
                        0
                    </div>

                </div>


                <div class="shrimp-card">

                    <div class="icon">🦐</div>

                    <div class="name">
                        กุ้งใหญ่
                    </div>

                    <div
                        class="value"
                        id="large"
                    >
                        0
                    </div>

                </div>


                <div class="shrimp-card">

                    <div class="icon">⚠️</div>

                    <div class="name">
                        กุ้งป่วย
                    </div>

                    <div
                        class="value"
                        id="sick"
                    >
                        0
                    </div>

                </div>

            </div>

        </section>


        <section class="section">

            <div class="panel">

                <div class="section-head">

                    <h2>
                        วิเคราะห์ข้อมูล
                    </h2>

                </div>

                <div
                    style="
                    display:grid;
                    grid-template-columns:
                    repeat(auto-fit,minmax(220px,1fr));
                    gap:14px;
                    "
                >

                    <a href="/daily" class="kpi">
                        <div class="kpi-label">
                            DAILY
                        </div>
                        <div class="kpi-value">
                            📅 รายวัน
                        </div>
                        <div
                            style="
                            color:#8a96a1;
                            margin-top:7px;
                            font-size:13px;
                            "
                        >
                            ดูข้อมูลแยกตามวัน
                        </div>
                    </a>


                    <a href="/monthly" class="kpi">
                        <div class="kpi-label">
                            MONTHLY
                        </div>
                        <div class="kpi-value">
                            📆 รายเดือน
                        </div>
                        <div
                            style="
                            color:#8a96a1;
                            margin-top:7px;
                            font-size:13px;
                            "
                        >
                            ดูข้อมูลแยกตามเดือน
                        </div>
                    </a>


                    <a href="/yearly" class="kpi">
                        <div class="kpi-label">
                            YEARLY
                        </div>
                        <div class="kpi-value">
                            📊 รายปี
                        </div>
                        <div
                            style="
                            color:#8a96a1;
                            margin-top:7px;
                            font-size:13px;
                            "
                        >
                            ดูข้อมูลแยกตามปี
                        </div>
                    </a>

                </div>

            </div>

        </section>


        <section class="section">

            <div class="section-head">

                <h2>
                    รอบล่าสุด
                </h2>

            </div>

            <div class="panel">

                <div class="table-wrap">

                    <table>

                        <thead>

                            <tr>
                                <th>รอบ</th>
                                <th>กุ้งเล็ก</th>
                                <th>กุ้งกลาง</th>
                                <th>กุ้งใหญ่</th>
                                <th>กุ้งป่วย</th>
                                <th>รวม</th>
                            </tr>

                        </thead>

                        <tbody id="history">
                        </tbody>

                    </table>

                </div>

            </div>

        </section>

    </main>
    """

    script = """

    <script>

    async function loadDashboard() {

        try {

            const response =
                await fetch("/api/dashboard");

            const data =
                await response.json();

            const latest =
                data.latest_round;

            document.getElementById("rounds")
                .textContent =
                data.total_rounds || 0;

            if (!latest) {
                return;
            }

            const c = latest.counts || {};

            document.getElementById("roundId")
                .textContent =
                latest.round_id ?? "-";

            document.getElementById("total")
                .textContent =
                latest.total ?? 0;

            document.getElementById("heroTotal")
                .textContent =
                latest.total ?? 0;

            document.getElementById("fps")
                .textContent =
                Number(latest.avg_fps || 0)
                    .toFixed(1);

            document.getElementById("small")
                .textContent =
                c["กุ้งเล็ก"] || 0;

            document.getElementById("medium")
                .textContent =
                c["กุ้งกลาง"] || 0;

            document.getElementById("large")
                .textContent =
                c["กุ้งใหญ่"] || 0;

            document.getElementById("sick")
                .textContent =
                c["กุ้งป่วย"] || 0;


            const history =
                document.getElementById("history");

            history.innerHTML = "";

            const rows =
                (data.history || [])
                    .slice()
                    .reverse();

            rows.forEach(item => {

                const c =
                    item.counts || {};

                history.innerHTML += `
                    <tr>

                        <td>
                            <span class="badge">
                                #${item.round_id}
                            </span>
                        </td>

                        <td>${c["กุ้งเล็ก"] || 0}</td>

                        <td>${c["กุ้งกลาง"] || 0}</td>

                        <td>${c["กุ้งใหญ่"] || 0}</td>

                        <td>${c["กุ้งป่วย"] || 0}</td>

                        <td>
                            <strong>
                                ${item.total || 0}
                            </strong>
                        </td>

                    </tr>
                `;

            });

        } catch (error) {

            console.error(error);

        }

    }

    loadDashboard();

    setInterval(loadDashboard, 3000);

    </script>

    """

    return HTMLResponse(
        html_page(
            "Dashboard",
            body,
            "dashboard",
            script
        )
    )


# =========================================================
# ANALYTICS PAGE
# =========================================================

def analytics_page(
    title,
    subtitle,
    endpoint,
    active,
    chart_title
):

    body = f"""

    <main class="container">

        <div class="page">

            <div class="page-title">

                <div class="eyebrow">
                    SHRIMP ANALYTICS
                </div>

                <h1>
                    {title}
                </h1>

                <p>
                    {subtitle}
                </p>

            </div>


            <section class="kpi-grid">

                <div class="kpi">

                    <div class="kpi-label">
                        กุ้งทั้งหมด
                    </div>

                    <div
                        class="kpi-value"
                        id="total"
                    >
                        0
                    </div>

                </div>


                <div class="kpi">

                    <div class="kpi-label">
                        กุ้งเล็ก
                    </div>

                    <div
                        class="kpi-value"
                        id="small"
                    >
                        0
                    </div>

                </div>


                <div class="kpi">

                    <div class="kpi-label">
                        กุ้งกลาง
                    </div>

                    <div
                        class="kpi-value"
                        id="medium"
                    >
                        0
                    </div>

                </div>


                <div class="kpi">

                    <div class="kpi-label">
                        กุ้งใหญ่ + ป่วย
                    </div>

                    <div
                        class="kpi-value"
                        id="other"
                    >
                        0
                    </div>

                </div>

            </section>


            <section class="panel chart-panel">

                <div class="section-head">

                    <div>

                        <h2>
                            {chart_title}
                        </h2>

                        <div
                            style="
                            color:#8a96a1;
                            font-size:13px;
                            margin-top:6px;
                            "
                        >
                            แสดงจำนวนกุ้งแยกตามประเภท
                        </div>

                    </div>

                </div>


                <div class="chart-box">

                    <canvas id="barChart">
                    </canvas>

                </div>


                <div class="chart-legend">

                    <div class="legend-item">
                        <span class="dot a"></span>
                        กุ้งเล็ก
                    </div>

                    <div class="legend-item">
                        <span class="dot b"></span>
                        กุ้งกลาง
                    </div>

                    <div class="legend-item">
                        <span class="dot c"></span>
                        กุ้งใหญ่
                    </div>

                    <div class="legend-item">
                        <span class="dot d"></span>
                        กุ้งป่วย
                    </div>

                </div>

            </section>


            <section class="section">

                <div class="section-head">

                    <h2>
                        ตารางสรุป
                    </h2>

                </div>


                <div class="panel">

                    <div class="table-wrap">

                        <table>

                            <thead>

                                <tr>

                                    <th>
                                        ช่วงเวลา
                                    </th>

                                    <th>
                                        กุ้งเล็ก
                                    </th>

                                    <th>
                                        กุ้งกลาง
                                    </th>

                                    <th>
                                        กุ้งใหญ่
                                    </th>

                                    <th>
                                        กุ้งป่วย
                                    </th>

                                    <th>
                                        รวม
                                    </th>

                                    <th>
                                        รอบ
                                    </th>

                                </tr>

                            </thead>

                            <tbody id="tableBody">
                            </tbody>

                        </table>

                    </div>

                </div>

            </section>

        </div>

    </main>
    """


    script = f"""

    <script>

    const ENDPOINT = "{endpoint}";

    let chartData = [];


    async function loadAnalytics() {

        try {

            const response =
                await fetch(ENDPOINT);

            const result =
                await response.json();

            chartData =
                result.data || [];

            updateSummary(chartData);

            renderTable(chartData);

            drawChart(chartData);

        } catch (error) {

            console.error(error);

        }

    }


    function updateSummary(data) {

        let total = 0;
        let small = 0;
        let medium = 0;
        let other = 0;

        data.forEach(item => {

            const c =
                item.counts || {{}};

            small +=
                Number(c["กุ้งเล็ก"] || 0);

            medium +=
                Number(c["กุ้งกลาง"] || 0);

            other +=
                Number(c["กุ้งใหญ่"] || 0);

            other +=
                Number(c["กุ้งป่วย"] || 0);

            total +=
                Number(item.total || 0);

        });

        document.getElementById("total")
            .textContent = total;

        document.getElementById("small")
            .textContent = small;

        document.getElementById("medium")
            .textContent = medium;

        document.getElementById("other")
            .textContent = other;

    }


    function renderTable(data) {

        const body =
            document.getElementById("tableBody");

        body.innerHTML = "";

        const rows =
            data.slice().reverse();

        if (rows.length === 0) {

            body.innerHTML = `
                <tr>
                    <td
                        colspan="7"
                        style="
                        text-align:center;
                        padding:50px;
                        color:#8a96a1;
                        "
                    >
                        ยังไม่มีข้อมูล
                    </td>
                </tr>
            `;

            return;
        }


        rows.forEach(item => {

            const c =
                item.counts || {{}};

            body.innerHTML += `

                <tr>

                    <td>
                        <strong>
                            ${{item.label}}
                        </strong>
                    </td>

                    <td>
                        ${{c["กุ้งเล็ก"] || 0}}
                    </td>

                    <td>
                        ${{c["กุ้งกลาง"] || 0}}
                    </td>

                    <td>
                        ${{c["กุ้งใหญ่"] || 0}}
                    </td>

                    <td>
                        ${{c["กุ้งป่วย"] || 0}}
                    </td>

                    <td>
                        <strong>
                            ${{item.total || 0}}
                        </strong>
                    </td>

                    <td>
                        ${{item.rounds || 0}}
                    </td>

                </tr>

            `;

        });

    }


    function drawChart(data) {

        const canvas =
            document.getElementById("barChart");

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

        ctx.scale(dpr, dpr);

        const width =
            rect.width;

        const height =
            rect.height;


        ctx.clearRect(
            0,
            0,
            width,
            height
        );


        if (!data.length) {

            ctx.fillStyle =
                "#8a96a1";

            ctx.font =
                "15px Arial";

            ctx.textAlign =
                "center";

            ctx.fillText(
                "ยังไม่มีข้อมูลสำหรับแสดงกราฟ",
                width / 2,
                height / 2
            );

            return;

        }


        const padding = {{
            left: 58,
            right: 25,
            top: 25,
            bottom: 65
        }};


        const chartWidth =
            width -
            padding.left -
            padding.right;

        const chartHeight =
            height -
            padding.top -
            padding.bottom;


        let maxValue = 0;

        data.forEach(item => {{

            const c =
                item.counts || {{}};

            maxValue =
                Math.max(
                    maxValue,
                    Number(c["กุ้งเล็ก"] || 0),
                    Number(c["กุ้งกลาง"] || 0),
                    Number(c["กุ้งใหญ่"] || 0),
                    Number(c["กุ้งป่วย"] || 0)
                );

        }});


        maxValue =
            Math.ceil(
                maxValue * 1.15
            );

        if (maxValue < 10) {
            maxValue = 10;
        }


        // GRID

        const gridCount = 5;

        ctx.font =
            "11px Arial";

        ctx.textAlign =
            "right";

        for (
            let i = 0;
            i <= gridCount;
            i++
        ) {{

            const value =
                maxValue *
                (i / gridCount);

            const y =
                padding.top +
                chartHeight -
                (
                    value /
                    maxValue
                ) *
                chartHeight;


            ctx.strokeStyle =
                "#edf0f3";

            ctx.lineWidth = 1;

            ctx.beginPath();

            ctx.moveTo(
                padding.left,
                y
            );

            ctx.lineTo(
                width - padding.right,
                y
            );

            ctx.stroke();


            ctx.fillStyle =
                "#8b96a1";

            ctx.fillText(
                Math.round(value),
                padding.left - 10,
                y + 4
            );

        }}


        const colors = [
            "#8b9aaa",
            "#4e6477",
            "#1f3445",
            "#d27b72"
        ];


        const keys = [
            "กุ้งเล็ก",
            "กุ้งกลาง",
            "กุ้งใหญ่",
            "กุ้งป่วย"
        ];


        const groupWidth =
            chartWidth / data.length;

        const barGap = 4;

        const barWidth =
            Math.max(
                5,
                (
                    groupWidth * .68
                    / keys.length
                ) - barGap
            );


        data.forEach(
            (item, index) => {{

                const centerX =
                    padding.left +
                    index * groupWidth +
                    groupWidth / 2;


                keys.forEach(
                    (key, keyIndex) => {{

                        const value =
                            Number(
                                (
                                    item.counts || {{}}
                                )[key] || 0
                            );


                        const barHeight =
                            (
                                value /
                                maxValue
                            ) *
                            chartHeight;


                        const x =
                            centerX -
                            (
                                keys.length *
                                (
                                    barWidth +
                                    barGap
                                )
                            ) / 2 +
                            keyIndex *
                            (
                                barWidth +
                                barGap
                            );


                        const y =
                            padding.top +
                            chartHeight -
                            barHeight;


                        ctx.fillStyle =
                            colors[keyIndex];

                        ctx.beginPath();

                        ctx.roundRect(
                            x,
                            y,
                            barWidth,
                            barHeight,
                            4
                        );

                        ctx.fill();


                        if (
                            data.length <= 15 &&
                            value > 0
                        ) {{

                            ctx.fillStyle =
                                "#56626e";

                            ctx.font =
                                "10px Arial";

                            ctx.textAlign =
                                "center";

                            ctx.fillText(
                                value,
                                x +
                                barWidth / 2,
                                y - 5
                            );

                        }}

                    }}
                );


                // X LABEL

                ctx.fillStyle =
                    "#7f8a95";

                ctx.font =
                    "11px Arial";

                ctx.textAlign =
                    "center";


                let label =
                    item.label;


                if (
                    data.length > 20 &&
                    index % 2 !== 0
                ) {{
                    label = "";
                }}


                ctx.fillText(
                    label,
                    centerX,
                    height - 25
                );

            }}
        );

    }


    window.addEventListener(
        "resize",
        () => drawChart(chartData)
    );


    loadAnalytics();

    setInterval(
        loadAnalytics,
        5000
    );

    </script>

    """


    return HTMLResponse(
        html_page(
            title,
            body,
            active,
            script
        )
    )


# =========================================================
# DAILY PAGE
# =========================================================

@app.get("/daily", response_class=HTMLResponse)
async def daily_page():

    return analytics_page(
        "สรุปรายวัน",
        "วิเคราะห์จำนวนกุ้งที่ตรวจพบในแต่ละวัน",
        "/api/analytics/daily",
        "daily",
        "แผนภูมิแท่งรายวัน"
    )


# =========================================================
# MONTHLY PAGE
# =========================================================

@app.get("/monthly", response_class=HTMLResponse)
async def monthly_page():

    return analytics_page(
        "สรุปรายเดือน",
        "วิเคราะห์จำนวนกุ้งที่ตรวจพบในแต่ละเดือน",
        "/api/analytics/monthly",
        "monthly",
        "แผนภูมิแท่งรายเดือน"
    )


# =========================================================
# YEARLY PAGE
# =========================================================

@app.get("/yearly", response_class=HTMLResponse)
async def yearly_page():

    return analytics_page(
        "สรุปรายปี",
        "วิเคราะห์จำนวนกุ้งที่ตรวจพบในแต่ละปี",
        "/api/analytics/yearly",
        "yearly",
        "แผนภูมิแท่งรายปี"
    )


# =========================================================
# LIVE CAMERA PAGE
# =========================================================

@app.get("/live", response_class=HTMLResponse)
async def live_page():

    body = """

    <main class="container">

        <div class="page">

            <div class="page-title">

                <div class="eyebrow">
                    REAL-TIME MONITORING
                </div>

                <h1>
                    กล้อง Live
                </h1>

                <p>
                    ตรวจสอบภาพจากกล้องและสถานะ AI
                    แบบ Real-time
                </p>

            </div>


            <section class="camera-panel">

                <div
                    class="camera-screen"
                    id="cameraScreen"
                >

                    <img
                        id="camera"
                        src="/api/live/frame"
                        alt="Live Camera"
                    >

                    <div
                        class="camera-empty"
                        id="empty"
                        style="display:none"
                    >
                        <div
                            style="
                            font-size:40px;
                            margin-bottom:10px;
                            "
                        >
                            📷
                        </div>

                        ไม่พบสัญญาณจากกล้อง

                    </div>

                </div>


                <div class="camera-status">

                    <div
                        class="status"
                        id="status"
                    >

                        <span
                            class="status-dot"
                        ></span>

                        <span id="statusText">
                            กำลังตรวจสอบ...
                        </span>

                    </div>


                    <div>
                        FPS:
                        <strong id="fps">
                            0
                        </strong>
                    </div>

                </div>

            </section>


            <section class="live-stats">

                <div class="live-stat">

                    <span>
                        สถานะระบบ
                    </span>

                    <strong id="systemStatus">
                        -
                    </strong>

                </div>


                <div class="live-stat">

                    <span>
                        FPS
                    </span>

                    <strong id="fps2">
                        0
                    </strong>

                </div>


                <div class="live-stat">

                    <span>
                        อัปเดตล่าสุด
                    </span>

                    <strong
                        id="lastUpdate"
                        style="font-size:15px"
                    >
                        -
                    </strong>

                </div>

            </section>

        </div>

    </main>
    """


    script = """

    <script>

    const camera =
        document.getElementById("camera");

    const empty =
        document.getElementById("empty");


    async function updateStatus() {

        try {

            const response =
                await fetch(
                    "/api/live/status",
                    {
                        cache: "no-store"
                    }
                );

            const data =
                await response.json();


            const online =
                data.status === "online";


            const status =
                document.getElementById("status");


            status.className =
                online
                ? "status online"
                : "status";


            document.getElementById(
                "statusText"
            ).textContent =
                online
                ? "AI Camera Online"
                : "Camera Offline";


            document.getElementById(
                "systemStatus"
            ).textContent =
                online
                ? "Online"
                : "Offline";


            document.getElementById(
                "fps"
            ).textContent =
                Number(
                    data.fps || 0
                ).toFixed(1);


            document.getElementById(
                "fps2"
            ).textContent =
                Number(
                    data.fps || 0
                ).toFixed(1);


            document.getElementById(
                "lastUpdate"
            ).textContent =
                data.last_update
                ? new Date(
                    data.last_update
                ).toLocaleString("th-TH")
                : "-";


            if (!online) {

                empty.style.display =
                    "block";

                camera.style.display =
                    "none";

            } else {

                empty.style.display =
                    "none";

                camera.style.display =
                    "block";

            }

        } catch (error) {

            console.error(error);

        }

    }


    function refreshCamera() {

        const current =
            camera.src.split("?")[0];

        camera.src =
            current +
            "?t=" +
            Date.now();

    }


    setInterval(
        updateStatus,
        1500
    );

    setInterval(
        refreshCamera,
        300
    );


    updateStatus();

    </script>

    """


    return HTMLResponse(
        html_page(
            "Live Camera",
            body,
            "live",
            script
        )
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/api/health")
async def health():

    return {
        "status": "ok",
        "rounds": len(round_history),
        "camera": live_info["status"],
    }


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT
    )
