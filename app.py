import os
import base64
from collections import deque
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field
import uvicorn


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

app = FastAPI(
    title="Shrimp AI Factory",
    version="2.0.0"
)


# =========================================================
# MEMORY
# =========================================================

latest_round: Dict[str, Any] = {}
round_history = deque(maxlen=1000)

live_frame: bytes | None = None
live_ts: datetime | None = None

live_status = {
    "online": False,
    "fps": 0,
    "last_update": None
}


# =========================================================
# MODELS
# =========================================================

class RoundReport(BaseModel):
    round_id: int = 0

    counts: Dict[str, int] = Field(default_factory=dict)

    avg_fps: float = 0
    duration: float = 0
    frames: int = 0

    started_at: str | None = None
    finished_at: str | None = None


class LiveReport(BaseModel):
    frame: str | None = None
    fps: float = 0


# =========================================================
# HELPERS
# =========================================================

def check_api_key(key: str | None):

    if not key or key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )


def clean_counts(counts: Dict[str, Any]):

    result = {}

    for shrimp_type in SHRIMP_TYPES:

        try:
            value = int(counts.get(shrimp_type, 0))
        except Exception:
            value = 0

        result[shrimp_type] = max(0, value)

    return result


def parse_datetime(value):

    if not value:
        return None

    if isinstance(value, datetime):
        return value

    value = str(value).strip()

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
    ]

    for fmt in formats:

        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def get_round_datetime(item):

    for key in [
        "finished_at",
        "started_at",
        "received_at"
    ]:

        dt = parse_datetime(item.get(key))

        if dt:
            return dt

    return datetime.now()


def decode_frame(data):

    if not data:
        return None

    try:

        if "," in data:
            data = data.split(",", 1)[1]

        return base64.b64decode(data)

    except Exception:
        return None


# =========================================================
# ROUND API
# =========================================================

@app.post("/api/round")
async def receive_round(
    report: RoundReport,
    x_api_key: str | None = Header(default=None)
):

    check_api_key(x_api_key)

    counts = clean_counts(report.counts)

    total = sum(counts.values())

    item = {
        "round_id": report.round_id,

        "counts": counts,

        "total": total,

        "avg_fps": report.avg_fps,
        "duration": report.duration,
        "frames": report.frames,

        "started_at": report.started_at,
        "finished_at": report.finished_at,

        "received_at": datetime.now().isoformat()
    }

    latest_round.clear()
    latest_round.update(item)

    round_history.appendleft(item)

    return {
        "success": True,
        "message": "Round received",
        "data": item
    }


# =========================================================
# LIVE API
# =========================================================

@app.post("/api/live")
async def receive_live(
    report: LiveReport,
    x_api_key: str | None = Header(default=None)
):

    global live_frame
    global live_ts

    check_api_key(x_api_key)

    decoded = decode_frame(report.frame)

    if decoded:
        live_frame = decoded

    live_ts = datetime.now()

    live_status["online"] = True
    live_status["fps"] = report.fps
    live_status["last_update"] = live_ts.isoformat()

    return {
        "success": True
    }


# =========================================================
# DASHBOARD API
# =========================================================

@app.get("/api/dashboard")
async def dashboard_api():

    counts = clean_counts(
        latest_round.get("counts", {})
    )

    total = sum(counts.values())

    return {
        "success": True,

        "latest_round": latest_round,

        "counts": counts,

        "total": total,

        "rounds": len(round_history)
    }


# =========================================================
# ANALYTICS
# =========================================================

def build_analytics(mode: str):

    groups = {}

    for item in round_history:

        dt = get_round_datetime(item)

        if mode == "daily":
            key = dt.strftime("%Y-%m-%d")

        elif mode == "monthly":
            key = dt.strftime("%Y-%m")

        elif mode == "yearly":
            key = dt.strftime("%Y")

        else:
            continue

        if key not in groups:

            groups[key] = {
                "label": key,
                "rounds": 0,
                "กุ้งเล็ก": 0,
                "กุ้งกลาง": 0,
                "กุ้งใหญ่": 0,
                "กุ้งป่วย": 0,
                "total": 0
            }

        groups[key]["rounds"] += 1

        counts = clean_counts(
            item.get("counts", {})
        )

        for shrimp_type in SHRIMP_TYPES:

            groups[key][shrimp_type] += counts[
                shrimp_type
            ]

        groups[key]["total"] += sum(counts.values())

    data = list(groups.values())

    data.sort(
        key=lambda x: x["label"]
    )

    if mode == "daily":
        data = data[-30:]

    elif mode == "monthly":
        data = data[-12:]

    elif mode == "yearly":
        data = data[-10:]

    return data


@app.get("/api/analytics/daily")
async def analytics_daily():

    return {
        "success": True,
        "period": "daily",
        "data": build_analytics("daily")
    }


@app.get("/api/analytics/monthly")
async def analytics_monthly():

    return {
        "success": True,
        "period": "monthly",
        "data": build_analytics("monthly")
    }


@app.get("/api/analytics/yearly")
async def analytics_yearly():

    return {
        "success": True,
        "period": "yearly",
        "data": build_analytics("yearly")
    }


# =========================================================
# LIVE STATUS
# =========================================================

@app.get("/api/live/status")
async def get_live_status():

    return {
        "success": True,
        **live_status
    }


@app.get("/api/live/frame")
async def get_live_frame():

    if not live_frame:

        return Response(
            status_code=404
        )

    return Response(
        content=live_frame,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store"
        }
    )


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
async def health():

    return {
        "status": "ok",
        "rounds": len(round_history),
        "live": live_status["online"]
    }


# =========================================================
# CSS
# =========================================================

CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

* {
    box-sizing: border-box;
}

:root {
    --blue: #1677ff;
    --blue2: #4ba3ff;
    --cyan: #19c8ff;

    --text: #10233f;
    --muted: #71829a;

    --bg: #f4f9ff;
    --white: #ffffff;

    --border: #e3edf8;

    --shadow:
        0 20px 60px rgba(31, 104, 190, 0.10);

    --shadow2:
        0 10px 30px rgba(31, 104, 190, 0.08);
}

body {
    margin: 0;
    font-family: Inter, Arial, sans-serif;
    color: var(--text);

    background:
        radial-gradient(
            circle at 10% 0%,
            rgba(75,163,255,.18),
            transparent 30%
        ),
        radial-gradient(
            circle at 90% 10%,
            rgba(25,200,255,.13),
            transparent 28%
        ),
        linear-gradient(
            180deg,
            #ffffff 0%,
            #f5faff 100%
        );

    min-height: 100vh;
}

a {
    text-decoration: none;
    color: inherit;
}

.container {
    width: min(1400px, calc(100% - 40px));
    margin: auto;
}


/* NAVBAR */

.navbar {
    height: 82px;

    display: flex;
    align-items: center;
    justify-content: space-between;

    padding: 0 35px;

    background: rgba(255,255,255,.86);

    backdrop-filter: blur(20px);

    border-bottom: 1px solid var(--border);

    position: sticky;
    top: 0;

    z-index: 100;
}

.logo {
    display: flex;
    align-items: center;
    gap: 12px;

    font-size: 20px;
    font-weight: 800;
}

.logo-icon {
    width: 45px;
    height: 45px;

    display: grid;
    place-items: center;

    border-radius: 14px;

    background:
        linear-gradient(
            135deg,
            #1677ff,
            #42c9ff
        );

    color: white;

    box-shadow:
        0 10px 25px rgba(22,119,255,.25);

    font-size: 23px;
}

.nav-links {
    display: flex;
    gap: 8px;
}

.nav-links a {
    padding: 11px 15px;

    color: #60738c;

    border-radius: 10px;

    font-size: 14px;
    font-weight: 600;
}

.nav-links a:hover,
.nav-links a.active {
    color: var(--blue);

    background: #edf6ff;
}


/* HERO */

.hero {
    padding: 60px 0 35px;
}

.badge {
    display: inline-flex;

    padding: 8px 13px;

    border-radius: 999px;

    background: #edf7ff;

    border: 1px solid #d8edff;

    color: var(--blue);

    font-size: 12px;
    font-weight: 700;

    margin-bottom: 18px;
}

.hero h1 {
    margin: 0;

    font-size: clamp(34px, 5vw, 62px);

    line-height: 1.05;

    letter-spacing: -2px;
}

.gradient-text {
    background:
        linear-gradient(
            90deg,
            #1677ff,
            #20bfff
        );

    -webkit-background-clip: text;
    background-clip: text;

    color: transparent;
}

.hero p {
    color: var(--muted);

    max-width: 700px;

    line-height: 1.7;

    margin-top: 20px;
}


/* BACK BUTTON */

.back-btn {
    display: inline-flex;

    align-items: center;
    gap: 8px;

    padding: 10px 15px;

    background: white;

    border: 1px solid var(--border);

    border-radius: 12px;

    color: #59708c;

    font-weight: 700;

    box-shadow: var(--shadow2);

    margin-top: 25px;
}

.back-btn:hover {
    color: var(--blue);
    transform: translateX(-2px);
}


/* KPI */

.kpi-grid {
    display: grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap: 18px;

    margin: 25px 0;
}

.kpi {
    position: relative;

    overflow: hidden;

    padding: 24px;

    background:
        linear-gradient(
            145deg,
            rgba(255,255,255,.98),
            rgba(247,251,255,.95)
        );

    border: 1px solid var(--border);

    border-radius: 22px;

    box-shadow: var(--shadow);

    transition: .25s;
}

.kpi:hover {
    transform: translateY(-4px);

    box-shadow:
        0 25px 60px
        rgba(22,119,255,.14);
}

.kpi-icon {
    width: 42px;
    height: 42px;

    display: grid;
    place-items: center;

    border-radius: 12px;

    background: #edf6ff;

    margin-bottom: 17px;

    font-size: 20px;
}

.kpi-label {
    color: var(--muted);

    font-size: 13px;

    font-weight: 600;
}

.kpi-value {
    margin-top: 7px;

    font-size: 32px;

    font-weight: 800;

    letter-spacing: -1px;
}


/* SHRIMP */

.shrimp-grid {
    display: grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap: 18px;

    margin: 25px 0;
}

.shrimp-card {
    padding: 22px;

    border-radius: 22px;

    background: white;

    border: 1px solid var(--border);

    box-shadow: var(--shadow2);

    position: relative;

    overflow: hidden;
}

.shrimp-card::after {
    content: "";

    position: absolute;

    width: 100px;
    height: 100px;

    right: -30px;
    bottom: -30px;

    border-radius: 50%;

    background: rgba(22,119,255,.06);
}

.shrimp-top {
    display: flex;

    justify-content: space-between;

    align-items: center;
}

.shrimp-name {
    font-size: 14px;

    font-weight: 700;
}

.shrimp-icon {
    font-size: 25px;
}

.shrimp-number {
    font-size: 32px;

    font-weight: 800;

    margin-top: 14px;
}

.shrimp-sub {
    font-size: 12px;

    color: var(--muted);

    margin-top: 5px;
}


/* PANELS */

.panel {
    background: rgba(255,255,255,.9);

    border: 1px solid var(--border);

    border-radius: 24px;

    box-shadow: var(--shadow);

    padding: 28px;

    margin: 22px 0;
}

.panel-head {
    display: flex;

    justify-content: space-between;

    align-items: center;

    gap: 15px;

    margin-bottom: 22px;
}

.panel-title {
    font-size: 19px;

    font-weight: 800;
}

.panel-sub {
    color: var(--muted);

    font-size: 13px;

    margin-top: 5px;
}


/* CHART */

.chart-box {
    width: 100%;

    min-height: 400px;

    position: relative;
}

canvas {
    width: 100% !important;
    height: 400px !important;
}


/* TABLE */

.table-wrap {
    overflow-x: auto;
}

table {
    width: 100%;

    border-collapse: collapse;

    font-size: 13px;
}

th {
    text-align: left;

    color: #71839b;

    background: #f6faff;

    padding: 15px;
}

td {
    padding: 16px 15px;

    border-bottom: 1px solid #edf2f7;
}

tbody tr:hover {
    background: #f9fcff;
}

.total-pill {
    display: inline-flex;

    padding: 6px 10px;

    border-radius: 999px;

    background: #edf7ff;

    color: var(--blue);

    font-weight: 700;
}


/* ANALYTICS */

.page-title {
    padding: 45px 0 15px;
}

.page-title h1 {
    font-size: 38px;

    margin: 0;

    letter-spacing: -1px;
}

.page-title p {
    color: var(--muted);

    margin-top: 10px;
}


/* ACTION */

.action-grid {
    display: grid;

    grid-template-columns:
        repeat(3, 1fr);

    gap: 18px;

    margin: 30px 0;
}

.action-card {
    padding: 25px;

    background: white;

    border: 1px solid var(--border);

    border-radius: 20px;

    box-shadow: var(--shadow2);

    transition: .25s;
}

.action-card:hover {
    transform: translateY(-4px);

    border-color: #bdddff;
}

.action-icon {
    font-size: 28px;

    margin-bottom: 15px;
}

.action-title {
    font-size: 17px;

    font-weight: 800;
}

.action-text {
    color: var(--muted);

    font-size: 13px;

    line-height: 1.6;

    margin: 8px 0 18px;
}

.action-btn {
    display: inline-flex;

    padding: 9px 13px;

    border-radius: 10px;

    background: #edf6ff;

    color: var(--blue);

    font-size: 13px;

    font-weight: 700;
}


/* LIVE */

.live-layout {
    display: grid;

    grid-template-columns:
        minmax(0, 1.7fr)
        minmax(280px, .6fr);

    gap: 22px;
}

.camera {
    background: #07111f;

    border-radius: 24px;

    overflow: hidden;

    position: relative;

    min-height: 500px;

    display: grid;

    place-items: center;

    box-shadow:
        0 25px 70px
        rgba(6,30,60,.18);
}

.camera img {
    width: 100%;
    height: 100%;

    object-fit: contain;

    display: block;
}

.camera-placeholder {
    color: #91a5bd;

    text-align: center;
}

.live-badge {
    position: absolute;

    top: 18px;
    left: 18px;

    padding: 8px 12px;

    background: rgba(255,255,255,.95);

    border-radius: 999px;

    font-size: 12px;

    font-weight: 800;

    color: #159447;

    box-shadow: 0 8px 25px rgba(0,0,0,.15);
}

.live-dot {
    display: inline-block;

    width: 8px;
    height: 8px;

    border-radius: 50%;

    background: #19c56a;

    margin-right: 6px;
}

.live-offline {
    color: #e34a4a;
}

.live-stats {
    display: grid;

    gap: 14px;
}

.live-stat {
    padding: 20px;

    background: white;

    border: 1px solid var(--border);

    border-radius: 18px;

    box-shadow: var(--shadow2);
}

.live-stat-label {
    color: var(--muted);

    font-size: 12px;
}

.live-stat-value {
    font-size: 27px;

    font-weight: 800;

    margin-top: 8px;
}


/* FOOTER */

.footer {
    padding: 50px 0;

    color: #8a9bb0;

    text-align: center;

    font-size: 12px;
}


/* UPDATE */

.update {
    animation: update .45s ease;
}

@keyframes update {

    0% {
        transform: scale(.97);
        opacity: .5;
    }

    100% {
        transform: scale(1);
        opacity: 1;
    }
}


/* RESPONSIVE */

@media(max-width: 1000px) {

    .kpi-grid,
    .shrimp-grid {
        grid-template-columns:
            repeat(2, 1fr);
    }

    .live-layout {
        grid-template-columns: 1fr;
    }

    .action-grid {
        grid-template-columns: 1fr;
    }

    .nav-links {
        display: none;
    }
}

@media(max-width: 600px) {

    .container {
        width: min(
            100% - 24px,
            1400px
        );
    }

    .navbar {
        padding: 0 15px;
    }

    .hero {
        padding-top: 35px;
    }

    .hero h1 {
        font-size: 38px;
    }

    .kpi-grid,
    .shrimp-grid {
        grid-template-columns: 1fr;
    }

    .panel {
        padding: 18px;
    }

    .camera {
        min-height: 300px;
    }

    .page-title h1 {
        font-size: 30px;
    }
}
"""


# =========================================================
# HTML HELPERS
# =========================================================

def navbar(active="dashboard"):

    links = [
        ("dashboard", "/", "Dashboard"),
        ("daily", "/daily", "รายวัน"),
        ("monthly", "/monthly", "รายเดือน"),
        ("yearly", "/yearly", "รายปี"),
        ("live", "/live", "Live Camera"),
    ]

    html = ""

    for key, url, name in links:

        cls = "active" if active == key else ""

        html += f"""
        <a class="{cls}" href="{url}">
            {name}
        </a>
        """

    return f"""
    <nav class="navbar">

        <a href="/" class="logo">

            <div class="logo-icon">
                🦐
            </div>

            <div>
                Shrimp AI
                <span style="color:#1677ff">
                    Factory
                </span>
            </div>

        </a>

        <div class="nav-links">
            {html}
        </div>

    </nav>
    """


def page(title, content, active="dashboard", script=""):

    return f"""
    <!DOCTYPE html>

    <html lang="th">

    <head>

        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width,initial-scale=1"
        >

        <title>
            {title} | Shrimp AI Factory
        </title>

        <style>
            {CSS}
        </style>

    </head>

    <body>

        {navbar(active)}

        <main class="container">

            {content}

        </main>

        <footer class="footer">

            SHRIMP AI FACTORY
            ·
            Intelligent Sorting Control System

        </footer>

        <script>
            {script}
        </script>

    </body>

    </html>
    """


# =========================================================
# DASHBOARD PAGE
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard():

    content = """

    <section class="hero">

        <div class="badge">
            ● AI SORTING CONTROL SYSTEM
        </div>

        <h1>
            Shrimp
            <span class="gradient-text">
                Intelligence
            </span>
        </h1>

        <p>
            ระบบควบคุมและวิเคราะห์การคัดแยกกุ้งด้วย AI
            สำหรับโรงงานอัจฉริยะ พร้อมติดตามผลการทำงาน
            แบบเรียลไทม์
        </p>

    </section>


    <section class="kpi-grid">

        <div class="kpi">
            <div class="kpi-icon">🦐</div>
            <div class="kpi-label">
                กุ้งทั้งหมด
            </div>
            <div id="total" class="kpi-value">
                0
            </div>
        </div>


        <div class="kpi">
            <div class="kpi-icon">⚙️</div>
            <div class="kpi-label">
                รอบการทำงาน
            </div>
            <div id="rounds" class="kpi-value">
                0
            </div>
        </div>


        <div class="kpi">
            <div class="kpi-icon">📡</div>
            <div class="kpi-label">
                AI FPS
            </div>
            <div id="fps" class="kpi-value">
                0
            </div>
        </div>


        <div class="kpi">
            <div class="kpi-icon">🟢</div>
            <div class="kpi-label">
                ระบบ
            </div>
            <div
                id="system"
                class="kpi-value"
                style="font-size:22px"
            >
                ONLINE
            </div>
        </div>

    </section>


    <section class="shrimp-grid">

        <div class="shrimp-card">
            <div class="shrimp-top">
                <div class="shrimp-name">
                    กุ้งเล็ก
                </div>
                <div class="shrimp-icon">
                    🟢
                </div>
            </div>

            <div id="small" class="shrimp-number">
                0
            </div>

            <div class="shrimp-sub">
                Small Shrimp
            </div>
        </div>


        <div class="shrimp-card">
            <div class="shrimp-top">
                <div class="shrimp-name">
                    กุ้งกลาง
                </div>
                <div class="shrimp-icon">
                    🔵
                </div>
            </div>

            <div id="medium" class="shrimp-number">
                0
            </div>

            <div class="shrimp-sub">
                Medium Shrimp
            </div>
        </div>


        <div class="shrimp-card">
            <div class="shrimp-top">
                <div class="shrimp-name">
                    กุ้งใหญ่
                </div>
                <div class="shrimp-icon">
                    🟠
                </div>
            </div>

            <div id="large" class="shrimp-number">
                0
            </div>

            <div class="shrimp-sub">
                Large Shrimp
            </div>
        </div>


        <div class="shrimp-card">
            <div class="shrimp-top">
                <div class="shrimp-name">
                    กุ้งป่วย
                </div>
                <div class="shrimp-icon">
                    🔴
                </div>
            </div>

            <div id="sick" class="shrimp-number">
                0
            </div>

            <div class="shrimp-sub">
                Sick Shrimp
            </div>
        </div>

    </section>


    <section class="action-grid">

        <a href="/daily" class="action-card">

            <div class="action-icon">
                📊
            </div>

            <div class="action-title">
                Daily Analytics
            </div>

            <div class="action-text">
                ดูจำนวนกุ้งที่คัดแยกในแต่ละวัน
                พร้อมกราฟเปรียบเทียบ
            </div>

            <span class="action-btn">
                เปิดรายงาน →
            </span>

        </a>


        <a href="/monthly" class="action-card">

            <div class="action-icon">
                📈
            </div>

            <div class="action-title">
                Monthly Analytics
            </div>

            <div class="action-text">
                วิเคราะห์ผลการคัดแยกแบบรายเดือน
                สำหรับติดตามประสิทธิภาพโรงงาน
            </div>

            <span class="action-btn">
                เปิดรายงาน →
            </span>

        </a>


        <a href="/yearly" class="action-card">

            <div class="action-icon">
                🏭
            </div>

            <div class="action-title">
                Yearly Analytics
            </div>

            <div class="action-text">
                สรุปภาพรวมการทำงานของระบบ
                แบบรายปี
            </div>

            <span class="action-btn">
                เปิดรายงาน →
            </span>

        </a>


        <a href="/live" class="action-card">

            <div class="action-icon">
                📷
            </div>

            <div class="action-title">
                Live Camera
            </div>

            <div class="action-text">
                ดูภาพจากกล้อง AI และสถานะระบบ
                แบบเรียลไทม์
            </div>

            <span class="action-btn">
                เปิดกล้อง →
            </span>

        </a>

    </section>


    <section class="panel">

        <div class="panel-head">

            <div>
                <div class="panel-title">
                    Latest Sorting Round
                </div>

                <div class="panel-sub">
                    ผลการคัดแยกรอบล่าสุด
                </div>
            </div>

        </div>

        <div class="table-wrap">

            <table>

                <thead>

                    <tr>
                        <th>Round</th>
                        <th>กุ้งเล็ก</th>
                        <th>กุ้งกลาง</th>
                        <th>กุ้งใหญ่</th>
                        <th>กุ้งป่วย</th>
                        <th>รวม</th>
                    </tr>

                </thead>

                <tbody id="latestTable">

                    <tr>
                        <td colspan="6">
                            กำลังโหลด...
                        </td>
                    </tr>

                </tbody>

            </table>

        </div>

    </section>
    """

    script = r"""

    async function loadDashboard() {

        try {

            const response =
                await fetch("/api/dashboard");

            const data =
                await response.json();

            const counts =
                data.counts || {};

            document.getElementById("total")
                .textContent =
                Number(data.total || 0).toLocaleString();

            document.getElementById("rounds")
                .textContent =
                Number(data.rounds || 0).toLocaleString();

            document.getElementById("small")
                .textContent =
                Number(counts["กุ้งเล็ก"] || 0).toLocaleString();

            document.getElementById("medium")
                .textContent =
                Number(counts["กุ้งกลาง"] || 0).toLocaleString();

            document.getElementById("large")
                .textContent =
                Number(counts["กุ้งใหญ่"] || 0).toLocaleString();

            document.getElementById("sick")
                .textContent =
                Number(counts["กุ้งป่วย"] || 0).toLocaleString();


            const latest =
                data.latest_round || {};

            document.getElementById("fps")
                .textContent =
                Number(latest.avg_fps || 0)
                .toFixed(1);


            const table =
                document.getElementById("latestTable");

            table.innerHTML = `

                <tr>

                    <td>
                        #${latest.round_id ?? "-"}
                    </td>

                    <td>
                        ${counts["กุ้งเล็ก"] || 0}
                    </td>

                    <td>
                        ${counts["กุ้งกลาง"] || 0}
                    </td>

                    <td>
                        ${counts["กุ้งใหญ่"] || 0}
                    </td>

                    <td>
                        ${counts["กุ้งป่วย"] || 0}
                    </td>

                    <td>
                        <span class="total-pill">
                            ${data.total || 0}
                        </span>
                    </td>

                </tr>

            `;

        }

        catch(error) {

            console.error(error);

        }

    }


    loadDashboard();

    setInterval(
        loadDashboard,
        3000
    );

    """

    return page(
        "Dashboard",
        content,
        "dashboard",
        script
    )


# =========================================================
# ANALYTICS PAGE
# =========================================================

def analytics_page(
    title,
    endpoint,
    active,
    subtitle
):

    content = f"""

    <section class="page-title">

        <a
            href="/"
            class="back-btn"
        >
            ← กลับ Dashboard
        </a>

        <h1>
            {title}
        </h1>

        <p>
            {subtitle}
        </p>

    </section>


    <section class="panel">

        <div class="panel-head">

            <div>

                <div class="panel-title">
                    Shrimp Sorting Analytics
                </div>

                <div class="panel-sub">
                    จำนวนกุ้งแต่ละประเภท
                </div>

            </div>

        </div>


        <div class="chart-box">

            <canvas id="chart"></canvas>

        </div>

    </section>


    <section class="panel">

        <div class="panel-head">

            <div>

                <div class="panel-title">
                    รายละเอียดข้อมูล
                </div>

                <div class="panel-sub">
                    สรุปผลการทำงานของ AI
                </div>

            </div>

        </div>


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

                <tbody id="analyticsTable">

                    <tr>
                        <td colspan="7">
                            กำลังโหลด...
                        </td>
                    </tr>

                </tbody>

            </table>

        </div>

    </section>
    """


    script = f"""

    let analyticsData = [];


    async function loadAnalytics() {{

        try {{

            const response =
                await fetch("{endpoint}");

            const result =
                await response.json();

            analyticsData =
                result.data || [];


            renderTable();

            drawChart();

        }}

        catch(error) {{

            console.error(error);

        }}

    }}


    function renderTable(){{

        const table =
            document.getElementById(
                "analyticsTable"
            );

        if(!analyticsData.length){{

            table.innerHTML = `
                <tr>
                    <td colspan="7">
                        ยังไม่มีข้อมูล
                    </td>
                </tr>
            `;

            return;

        }}


        table.innerHTML =
            analyticsData
            .slice()
            .reverse()
            .map(row => `

                <tr>

                    <td>
                        <b>
                            ${{row.label}}
                        </b>
                    </td>

                    <td>
                        ${{row["กุ้งเล็ก"]}}
                    </td>

                    <td>
                        ${{row["กุ้งกลาง"]}}
                    </td>

                    <td>
                        ${{row["กุ้งใหญ่"]}}
                    </td>

                    <td>
                        ${{row["กุ้งป่วย"]}}
                    </td>

                    <td>

                        <span class="total-pill">
                            ${{row.total}}
                        </span>

                    </td>

                    <td>
                        ${{row.rounds}}
                    </td>

                </tr>

            `)
            .join("");

    }}


    function drawChart(){{

        const canvas =
            document.getElementById("chart");

        const ctx =
            canvas.getContext("2d");

        const dpr =
            window.devicePixelRatio || 1;

        const width =
            canvas.clientWidth;

        const height =
            400;

        canvas.width =
            width * dpr;

        canvas.height =
            height * dpr;

        ctx.scale(dpr, dpr);

        ctx.clearRect(
            0,
            0,
            width,
            height
        );


        if(!analyticsData.length){{

            ctx.fillStyle = "#71829a";

            ctx.font = "15px Inter";

            ctx.textAlign = "center";

            ctx.fillText(
                "ยังไม่มีข้อมูล",
                width / 2,
                height / 2
            );

            return;

        }}


        const padding = {{
            top: 30,
            right: 20,
            bottom: 55,
            left: 55
        }};


        const chartWidth =
            width -
            padding.left -
            padding.right;

        const chartHeight =
            height -
            padding.top -
            padding.bottom;


        const maxValue =
            Math.max(
                ...analyticsData.map(
                    x => x.total
                ),
                1
            );


        const niceMax =
            Math.ceil(
                maxValue / 10
            ) * 10;


        // GRID

        ctx.font = "11px Inter";

        ctx.textAlign = "right";

        for(
            let i = 0;
            i <= 5;
            i++
        ){{

            const value =
                niceMax * i / 5;

            const y =
                padding.top +
                chartHeight -
                (value / niceMax) *
                chartHeight;


            ctx.strokeStyle =
                "#eaf1f8";

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
                "#8191a5";

            ctx.fillText(
                Math.round(value),
                padding.left - 10,
                y + 4
            );

        }}


        const groupWidth =
            chartWidth /
            analyticsData.length;


        const barWidth =
            Math.max(
                4,
                Math.min(
                    18,
                    groupWidth / 6
                )
            );


        const colors = [
            "#35b86b",
            "#258cff",
            "#ff9f43",
            "#ef5350"
        ];


        const types = [
            "กุ้งเล็ก",
            "กุ้งกลาง",
            "กุ้งใหญ่",
            "กุ้งป่วย"
        ];


        analyticsData.forEach(
            (row, index) => {{

                const xCenter =
                    padding.left +
                    groupWidth *
                    index +
                    groupWidth / 2;


                types.forEach(
                    (type, typeIndex) => {{

                        const value =
                            row[type] || 0;


                        const barHeight =
                            value /
                            niceMax *
                            chartHeight;


                        const x =
                            xCenter -
                            (
                                types.length *
                                barWidth
                            ) / 2 +
                            typeIndex *
                            barWidth;


                        const y =
                            padding.top +
                            chartHeight -
                            barHeight;


                        ctx.fillStyle =
                            colors[typeIndex];


                        ctx.beginPath();

                        ctx.roundRect(
                            x,
                            y,
                            barWidth - 2,
                            barHeight,
                            4
                        );

                        ctx.fill();

                    }}
                );


                ctx.fillStyle =
                    "#71829a";

                ctx.font =
                    "10px Inter";

                ctx.textAlign =
                    "center";


                let label =
                    row.label;


                if(label.length > 10){{
                    label =
                        label.slice(5);
                }}


                ctx.fillText(
                    label,
                    xCenter,
                    height - 25
                );

            }}
        );


        // LEGEND

        types.forEach(
            (type, index) => {{

                const x =
                    padding.left +
                    index * 95;


                ctx.fillStyle =
                    colors[index];


                ctx.fillRect(
                    x,
                    8,
                    10,
                    10
                );


                ctx.fillStyle =
                    "#61748b";

                ctx.textAlign =
                    "left";

                ctx.font =
                    "11px Inter";

                ctx.fillText(
                    type,
                    x + 15,
                    17
                );

            }}
        );

    }}


    window.addEventListener(
        "resize",
        drawChart
    );


    loadAnalytics();

    setInterval(
        loadAnalytics,
        5000
    );

    """

    return page(
        title,
        content,
        active,
        script
    )


# =========================================================
# DAILY
# =========================================================

@app.get("/daily", response_class=HTMLResponse)
async def daily():

    return analytics_page(
        "Daily Analytics",
        "/api/analytics/daily",
        "daily",
        "วิเคราะห์ผลการคัดแยกกุ้งแบบรายวัน"
    )


# =========================================================
# MONTHLY
# =========================================================

@app.get("/monthly", response_class=HTMLResponse)
async def monthly():

    return analytics_page(
        "Monthly Analytics",
        "/api/analytics/monthly",
        "monthly",
        "วิเคราะห์ผลการคัดแยกกุ้งแบบรายเดือน"
    )


# =========================================================
# YEARLY
# =========================================================

@app.get("/yearly", response_class=HTMLResponse)
async def yearly():

    return analytics_page(
        "Yearly Analytics",
        "/api/analytics/yearly",
        "yearly",
        "วิเคราะห์ผลการคัดแยกกุ้งแบบรายปี"
    )


# =========================================================
# LIVE PAGE
# =========================================================

@app.get("/live", response_class=HTMLResponse)
async def live_page():

    content = """

    <section class="page-title">

        <a
            href="/"
            class="back-btn"
        >
            ← กลับ Dashboard
        </a>

        <h1>
            Live
            <span class="gradient-text">
                Camera
            </span>
        </h1>

        <p>
            ระบบตรวจสอบภาพจากกล้อง AI
            แบบเรียลไทม์
        </p>

    </section>


    <section class="live-layout">


        <div class="camera">

            <div
                id="liveBadge"
                class="live-badge"
            >
                <span class="live-dot"></span>
                AI CAMERA ONLINE
            </div>


            <img
                id="camera"
                src="/api/live/frame"
                alt="AI Camera"
            >


            <div
                id="placeholder"
                class="camera-placeholder"
            >

                <div style="font-size:50px">
                    📷
                </div>

                <div>
                    Waiting for AI Camera...
                </div>

            </div>

        </div>


        <div class="live-stats">


            <div class="live-stat">

                <div class="live-stat-label">
                    CAMERA STATUS
                </div>

                <div
                    id="status"
                    class="live-stat-value"
                >
                    OFFLINE
                </div>

            </div>


            <div class="live-stat">

                <div class="live-stat-label">
                    AI FPS
                </div>

                <div
                    id="liveFps"
                    class="live-stat-value"
                >
                    0
                </div>

            </div>


            <div class="live-stat">

                <div class="live-stat-label">
                    LAST UPDATE
                </div>

                <div
                    id="lastUpdate"
                    class="live-stat-value"
                    style="font-size:16px"
                >
                    -
                </div>

            </div>


        </div>

    </section>
    """


    script = r"""

    const camera =
        document.getElementById(
            "camera"
        );

    const placeholder =
        document.getElementById(
            "placeholder"
        );


    async function updateStatus(){

        try {

            const response =
                await fetch(
                    "/api/live/status"
                );

            const data =
                await response.json();


            const status =
                document.getElementById(
                    "status"
                );

            const badge =
                document.getElementById(
                    "liveBadge"
                );


            if(data.online){

                status.textContent =
                    "ONLINE";

                status.style.color =
                    "#16a05d";

                badge.innerHTML =
                    '<span class="live-dot"></span>' +
                    'AI CAMERA ONLINE';

                placeholder.style.display =
                    "none";

            }
            else {

                status.textContent =
                    "OFFLINE";

                status.style.color =
                    "#e34a4a";

                badge.innerHTML =
                    '<span class="live-dot" ' +
                    'style="background:#e34a4a"></span>' +
                    'AI CAMERA OFFLINE';

                placeholder.style.display =
                    "block";

            }


            document.getElementById(
                "liveFps"
            ).textContent =
                Number(data.fps || 0)
                .toFixed(1);


            if(data.last_update){

                const date =
                    new Date(
                        data.last_update
                    );

                document.getElementById(
                    "lastUpdate"
                ).textContent =
                    date.toLocaleTimeString(
                        "th-TH"
                    );

            }

        }

        catch(error){

            console.error(error);

        }

    }


    function refreshCamera(){

        camera.src =
            "/api/live/frame?t=" +
            Date.now();

    }


    updateStatus();

    refreshCamera();


    setInterval(
        updateStatus,
        1000
    );

    setInterval(
        refreshCamera,
        500
    );

    """

    return page(
        "Live Camera",
        content,
        "live",
        script
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT
    )
