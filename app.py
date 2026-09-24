from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from collections import deque
from datetime import datetime
import base64
import os
import uvicorn


# =========================================================
# APP
# =========================================================

app = FastAPI(title="AI Shrimp Sorting System")

API_KEY = os.getenv("API_KEY", "change-me")

SHRIMP_TYPES = [
    "กุ้งเล็ก",
    "กุ้งกลาง",
    "กุ้งใหญ่",
    "กุ้งป่วย"
]

latest_round = None
round_history = deque(maxlen=500)

live_frame = None
live_ts = None


# =========================================================
# MODELS
# =========================================================

class RoundReport(BaseModel):
    round_id: int
    counts: dict[str, int] = Field(default_factory=dict)
    avg_fps: float = 0
    duration: float = 0
    frames: int = 0
    started_at: str | None = None
    finished_at: str | None = None


class LiveReport(BaseModel):
    frame: str | None = None
    fps: float = 0
    counts: dict[str, int] = Field(default_factory=dict)


# =========================================================
# HELPERS
# =========================================================

def clean_counts(counts):
    result = {}

    for shrimp_type in SHRIMP_TYPES:
        try:
            result[shrimp_type] = int(counts.get(shrimp_type, 0))
        except Exception:
            result[shrimp_type] = 0

    return result


def parse_datetime(value):
    if not value:
        return None

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            pass

    try:
        return datetime.fromisoformat(value.replace("Z", ""))
    except Exception:
        return None


def get_report_datetime(report):
    value = (
        report.get("finished_at")
        or report.get("started_at")
        or report.get("received_at")
    )

    dt = parse_datetime(value)

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


def check_api_key(x_api_key):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )


def total_counts(counts):
    return sum(
        int(counts.get(x, 0))
        for x in SHRIMP_TYPES
    )


# =========================================================
# API - ROUND
# =========================================================

@app.post("/api/round")
async def receive_round(
    report: RoundReport,
    x_api_key: str | None = Header(default=None)
):
    check_api_key(x_api_key)

    global latest_round

    counts = clean_counts(report.counts)

    item = {
        "round_id": report.round_id,
        "counts": counts,
        "avg_fps": report.avg_fps,
        "duration": report.duration,
        "frames": report.frames,
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "received_at": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    }

    latest_round = item

    round_history.appendleft(item)

    return {
        "success": True,
        "message": "Round received",
        "round": item
    }


# =========================================================
# API - LIVE
# =========================================================

@app.post("/api/live")
async def receive_live(
    report: LiveReport,
    x_api_key: str | None = Header(default=None)
):
    check_api_key(x_api_key)

    global live_frame
    global live_ts

    frame = decode_frame(report.frame)

    if frame:
        live_frame = frame
        live_ts = datetime.now()

    return {
        "success": True
    }


# =========================================================
# API - DASHBOARD
# =========================================================

@app.get("/api/dashboard")
async def dashboard_api():

    if not latest_round:
        return {
            "latest_round": None,
            "totals": {
                x: 0 for x in SHRIMP_TYPES
            },
            "total": 0,
            "rounds": 0
        }

    counts = clean_counts(
        latest_round["counts"]
    )

    return {
        "latest_round": latest_round,
        "totals": counts,
        "total": total_counts(counts),
        "rounds": len(round_history)
    }


# =========================================================
# ANALYTICS
# =========================================================

def build_analytics(mode):

    groups = {}

    for item in round_history:

        dt = get_report_datetime(item)

        if mode == "daily":
            key = dt.strftime("%Y-%m-%d")

        elif mode == "monthly":
            key = dt.strftime("%Y-%m")

        else:
            key = dt.strftime("%Y")

        if key not in groups:
            groups[key] = {
                "period": key,
                "กุ้งเล็ก": 0,
                "กุ้งกลาง": 0,
                "กุ้งใหญ่": 0,
                "กุ้งป่วย": 0,
                "total": 0,
                "rounds": 0
            }

        counts = clean_counts(
            item.get("counts", {})
        )

        for shrimp_type in SHRIMP_TYPES:
            groups[key][shrimp_type] += counts[
                shrimp_type
            ]

        groups[key]["total"] += total_counts(
            counts
        )

        groups[key]["rounds"] += 1

    data = list(groups.values())

    data.sort(
        key=lambda x: x["period"]
    )

    if mode == "daily":
        data = data[-30:]

    elif mode == "monthly":
        data = data[-12:]

    else:
        data = data[-10:]

    return data


@app.get("/api/analytics/daily")
async def analytics_daily():
    return {
        "mode": "daily",
        "data": build_analytics("daily")
    }


@app.get("/api/analytics/monthly")
async def analytics_monthly():
    return {
        "mode": "monthly",
        "data": build_analytics("monthly")
    }


@app.get("/api/analytics/yearly")
async def analytics_yearly():
    return {
        "mode": "yearly",
        "data": build_analytics("yearly")
    }


# =========================================================
# LIVE STATUS
# =========================================================

@app.get("/api/live/status")
async def live_status():

    online = False

    if live_ts:
        diff = (
            datetime.now() - live_ts
        ).total_seconds()

        online = diff <= 10

    fps = 0

    if latest_round:
        fps = latest_round.get(
            "avg_fps", 0
        )

    return {
        "online": online,
        "fps": fps,
        "last_update": (
            live_ts.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if live_ts
            else None
        )
    }


@app.get("/api/live/frame")
async def get_live_frame():

    if not live_frame:
        raise HTTPException(
            status_code=404,
            detail="No frame"
        )

    return Response(
        content=live_frame,
        media_type="image/jpeg",
        headers={
            "Cache-Control":
                "no-store, no-cache, must-revalidate"
        }
    )


@app.get("/api/health")
async def health():
    return {
        "status": "ok"
    }


# =========================================================
# CSS
# =========================================================

CSS = r"""
* {
    box-sizing: border-box;
}

html,
body {
    margin: 0;
    padding: 0;
    font-family:
        "Noto Sans Thai",
        "Segoe UI",
        Arial,
        sans-serif;

    color: #152238;
    background: #f4f8fc;
}

body {
    min-height: 100vh;
}

a {
    text-decoration: none !important;
    color: inherit;
}

button {
    font-family: inherit;
}


/* =====================================================
   SIDEBAR
===================================================== */

.sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;

    width: 250px;

    background: #ffffff;

    border-right:
        1px solid #dce6f0;

    padding: 24px 16px;

    z-index: 100;

    display: flex;
    flex-direction: column;
}

.logo {
    display: flex;
    align-items: center;

    gap: 13px;

    padding: 4px 10px 30px;
}

.logo-box {
    width: 48px;
    height: 48px;

    display: grid;
    place-items: center;

    background:
        linear-gradient(
            135deg,
            #0875e1,
            #54a9ff
        );

    color: white;

    border-radius: 11px;

    font-size: 24px;

    box-shadow:
        0 9px 22px
        rgba(25,116,220,.20);
}

.logo-title {
    font-size: 18px;
    font-weight: 900;
}

.logo-sub {
    color: #8492a5;
    font-size: 11px;
    margin-top: 2px;
    font-weight: 600;
}

.nav {
    display: flex;
    flex-direction: column;

    gap: 4px;

    flex: 1;
}

.nav a {
    display: flex;
    align-items: center;

    gap: 13px;

    padding: 13px 12px;

    border-radius: 9px;

    color: #536379;

    font-size: 15px;

    font-weight: 700;

    transition: .18s;
}

.nav a:hover {
    background: #f0f6fd;
    color: #1671db;
}

.nav a.active {
    background: #e6f1ff;
    color: #086fe0;

    border-left:
        4px solid #1478e6;

    padding-left: 8px;
}

.nav-icon {
    width: 25px;
    text-align: center;
    font-size: 19px;
}

.sidebar-footer {
    border-top:
        1px solid #e1e8ef;

    padding-top: 14px;
}

.footer-status {
    padding: 12px;

    background: #f3f7fb;

    border-radius: 8px;

    color: #526277;

    font-size: 13px;

    font-weight: 800;
}


/* =====================================================
   MAIN
===================================================== */

.main {
    margin-left: 250px;

    min-height: 100vh;
}


/* =====================================================
   TOPBAR
===================================================== */

.topbar {
    height: 72px;

    background: white;

    border-bottom:
        1px solid #dce6f0;

    display: flex;

    align-items: center;

    justify-content: space-between;

    padding: 0 32px;

    position: sticky;

    top: 0;

    z-index: 50;
}

.top-label {
    color: #1872dc;

    font-size: 11px;

    font-weight: 900;

    letter-spacing: 1.4px;
}

.top-title {
    margin-top: 2px;

    font-size: 19px;

    font-weight: 900;
}

.top-actions {
    display: flex;
    gap: 9px;
}

.top-btn {
    width: 42px;
    height: 42px;

    border:
        1px solid #dbe5ef;

    background: #f6f9fc;

    color: #42536a;

    border-radius: 9px;

    cursor: pointer;

    font-size: 18px;
}

.user-box {
    width: 42px;
    height: 42px;

    display: grid;
    place-items: center;

    background: #1475df;

    color: white;

    border-radius: 9px;

    font-weight: 900;
}


/* =====================================================
   CONTENT
===================================================== */

.content {
    width:
        min(
            1180px,
            calc(100% - 64px)
        );

    margin: auto;

    padding:
        40px 0 70px;
}


/* =====================================================
   HEADER
===================================================== */

.page-head {
    margin-bottom: 27px;
}

.page-head h1 {
    margin: 0;

    font-size: 34px;

    line-height: 1.2;

    font-weight: 900;

    letter-spacing: -.6px;
}

.page-head p {
    margin:
        8px 0 0;

    color: #748398;

    font-size: 16px;

    font-weight: 500;
}


/* =====================================================
   STATUS
===================================================== */

.status-bar {
    display: flex;

    align-items: center;

    justify-content: space-between;

    background:
        linear-gradient(
            100deg,
            #0969d8,
            #2d88eb
        );

    color: white;

    padding:
        20px 23px;

    border-radius: 12px;

    margin-bottom: 23px;

    box-shadow:
        0 14px 32px
        rgba(27,112,216,.18);
}

.status-main {
    display: flex;

    align-items: center;

    gap: 15px;
}

.status-icon {
    width: 46px;
    height: 46px;

    display: grid;
    place-items: center;

    background:
        rgba(255,255,255,.15);

    border-radius: 9px;

    font-size: 22px;
}

.status-title {
    font-size: 19px;
    font-weight: 900;
}

.status-text {
    margin-top: 3px;

    font-size: 12px;

    color:
        rgba(255,255,255,.78);
}

.status-pill {
    background:
        rgba(255,255,255,.16);

    padding:
        9px 14px;

    border-radius: 7px;

    font-size: 12px;

    font-weight: 900;
}


/* =====================================================
   KPI
===================================================== */

.kpi-grid {
    display: grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap: 16px;

    margin-bottom: 28px;
}

.kpi {
    background: white;

    border:
        1px solid #dce6ef;

    border-radius: 12px;

    padding: 23px;

    min-height: 145px;

    box-shadow:
        0 6px 23px
        rgba(36,70,105,.06);

    position: relative;
}

.kpi::before {
    content: "";

    position: absolute;

    left: 0;
    top: 0;
    bottom: 0;

    width: 4px;

    background: #1777df;
}

.kpi.green::before {
    background: #20aa76;
}

.kpi.orange::before {
    background: #efa52b;
}

.kpi.red::before {
    background: #df5e69;
}

.kpi-label {
    color: #7c8b9e;

    font-size: 13px;

    font-weight: 700;
}

.kpi-value {
    margin-top: 9px;

    font-size: 32px;

    font-weight: 900;

    color: #15243a;
}

.kpi-unit {
    margin-top: 4px;

    color: #8491a2;

    font-size: 12px;
}


/* =====================================================
   SECTION
===================================================== */

.section-title {
    margin:
        0 0 16px;

    font-size: 24px;

    font-weight: 900;

    color: #17263b;
}


/* =====================================================
   SHRIMP
===================================================== */

.shrimp-grid {
    display: grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap: 16px;

    margin-bottom: 28px;
}

.shrimp-card {
    background: white;

    border:
        1px solid #dce6ef;

    border-radius: 12px;

    padding: 22px;

    min-height: 140px;

    box-shadow:
        0 6px 23px
        rgba(36,70,105,.06);
}

.shrimp-header {
    display: flex;

    align-items: center;

    justify-content: space-between;
}

.shrimp-name {
    font-size: 17px;

    font-weight: 900;

    color: #2b3b51;
}

.shrimp-square {
    width: 12px;
    height: 12px;

    border-radius: 3px;

    background: #237ce4;
}

.shrimp-square.medium {
    background: #20aa76;
}

.shrimp-square.large {
    background: #efa52b;
}

.shrimp-square.sick {
    background: #df5e69;
}

.shrimp-number {
    margin-top: 16px;

    font-size: 33px;

    font-weight: 900;

    color: #15243a;
}

.shrimp-unit {
    color: #8391a3;

    font-size: 12px;

    margin-top: 3px;
}


/* =====================================================
   PANEL
===================================================== */

.panel {
    background: white;

    border:
        1px solid #dce6ef;

    border-radius: 12px;

    padding: 24px;

    margin-bottom: 22px;

    box-shadow:
        0 6px 23px
        rgba(36,70,105,.06);
}

.panel-head {
    display: flex;

    justify-content: space-between;

    align-items: center;

    margin-bottom: 20px;
}

.panel-title {
    font-size: 20px;

    font-weight: 900;
}

.panel-sub {
    color: #8491a2;

    font-size: 13px;

    margin-top: 4px;
}


/* =====================================================
   TABLE
===================================================== */

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

    padding: 15px;

    background: #f3f7fb;

    color: #66768b;

    font-size: 13px;

    font-weight: 900;
}

td {
    padding: 16px 15px;

    border-bottom:
        1px solid #edf1f5;

    color: #34455b;

    font-weight: 600;
}

tr:hover td {
    background: #f8fbff;
}


/* =====================================================
   QUICK MENU
===================================================== */

.quick-grid {
    display: grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap: 16px;
}

.quick-card {
    background: white;

    border:
        1px solid #dce6ef;

    border-radius: 12px;

    padding: 22px;

    min-height: 125px;

    transition: .18s;
}

.quick-card:hover {
    transform: translateY(-3px);

    border-color: #91bff0;

    box-shadow:
        0 12px 28px
        rgba(36,108,200,.10);
}

.quick-no {
    color: #1d78dd;

    font-size: 12px;

    font-weight: 900;
}

.quick-title {
    margin-top: 14px;

    font-size: 17px;

    font-weight: 900;
}

.quick-desc {
    margin-top: 5px;

    color: #8491a2;

    font-size: 12px;
}


/* =====================================================
   ANALYTICS
===================================================== */

.back {
    display: inline-block;

    padding:
        9px 14px;

    margin-bottom: 18px;

    border:
        1px solid #dce6ef;

    border-radius: 8px;

    background: white;

    color: #2176db;

    font-size: 13px;

    font-weight: 800;
}

.chart-panel {
    background: white;

    border:
        1px solid #dce6ef;

    border-radius: 12px;

    padding: 25px;

    box-shadow:
        0 6px 23px
        rgba(36,70,105,.06);
}

.chart-area {
    height: 430px;

    margin-top: 15px;
}

canvas {
    width: 100% !important;

    height: 100% !important;
}


/* =====================================================
   LIVE
===================================================== */

.live-grid {
    display: grid;

    grid-template-columns:
        minmax(0, 1fr)
        290px;

    gap: 18px;
}

.camera-panel {
    background: #071522;

    min-height: 560px;

    border-radius: 12px;

    overflow: hidden;

    position: relative;

    display: grid;

    place-items: center;
}

.camera-panel img {
    width: 100%;

    height: 100%;

    object-fit: contain;
}

.camera-empty {
    color: #7d8da0;

    font-size: 15px;

    text-align: center;
}

.live-label {
    position: absolute;

    left: 17px;
    top: 17px;

    background: #ffffff;

    color: #16a56f;

    padding:
        8px 12px;

    border-radius: 7px;

    font-size: 12px;

    font-weight: 900;
}

.live-info {
    background: white;

    border:
        1px solid #dce6ef;

    border-radius: 12px;

    padding: 22px;

    box-shadow:
        0 6px 23px
        rgba(36,70,105,.06);
}

.live-info h2 {
    margin: 0 0 20px;

    font-size: 20px;

    font-weight: 900;
}

.live-stat {
    padding:
        17px 0;

    border-bottom:
        1px solid #edf1f5;
}

.live-stat:last-child {
    border-bottom: 0;
}

.live-stat-label {
    color: #8391a3;

    font-size: 12px;

    font-weight: 700;
}

.live-stat-value {
    margin-top: 5px;

    font-size: 25px;

    font-weight: 900;

    color: #17263b;
}


/* =====================================================
   EMPTY
===================================================== */

.empty {
    padding: 45px 20px;

    text-align: center;

    color: #8491a3;

    font-size: 15px;
}


/* =====================================================
   RESPONSIVE
===================================================== */

@media (max-width: 1050px) {

    .sidebar {
        width: 215px;
    }

    .main {
        margin-left: 215px;
    }

    .kpi-grid,
    .shrimp-grid {
        grid-template-columns:
            repeat(2, 1fr);
    }

    .quick-grid {
        grid-template-columns:
            repeat(2, 1fr);
    }

    .live-grid {
        grid-template-columns: 1fr;
    }
}


@media (max-width: 760px) {

    .sidebar {
        position: relative;

        width: 100%;

        height: auto;

        border-right: 0;

        border-bottom:
            1px solid #dce6ef;
    }

    .nav {
        display: grid;

        grid-template-columns:
            repeat(2, 1fr);
    }

    .sidebar-footer {
        display: none;
    }

    .main {
        margin-left: 0;
    }

    .topbar {
        padding:
            0 17px;
    }

    .content {
        width:
            calc(100% - 30px);

        padding-top: 28px;
    }

    .page-head h1 {
        font-size: 28px;
    }

    .kpi-grid,
    .shrimp-grid,
    .quick-grid {
        grid-template-columns: 1fr;
    }

    .status-bar {
        align-items: flex-start;

        flex-direction: column;
    }

    .status-pill {
        width: 100%;

        text-align: center;
    }

    .chart-area {
        height: 350px;
    }
}
"""


# =========================================================
# BASE HTML
# =========================================================

def layout(content, active="dashboard"):

    def nav_class(name):
        return "active" if active == name else ""

    return f"""
<!DOCTYPE html>

<html lang="th">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>AI Shrimp Sorting System</title>

<style>
{CSS}
</style>

</head>

<body>

<aside class="sidebar">

    <div class="logo">

        <div class="logo-box">
            🦐
        </div>

        <div>
            <div class="logo-title">
                AI Shrimp
            </div>

            <div class="logo-sub">
                Sorting Control System
            </div>
        </div>

    </div>


    <nav class="nav">

        <a href="/" class="{nav_class("dashboard")}">
            <span class="nav-icon">⌂</span>
            <span>หน้าหลัก</span>
        </a>

        <a href="/daily" class="{nav_class("daily")}">
            <span class="nav-icon">▥</span>
            <span>สถิติรายวัน</span>
        </a>

        <a href="/monthly" class="{nav_class("monthly")}">
            <span class="nav-icon">▤</span>
            <span>สถิติรายเดือน</span>
        </a>

        <a href="/yearly" class="{nav_class("yearly")}">
            <span class="nav-icon">▦</span>
            <span>สถิติรายปี</span>
        </a>

        <a href="/live" class="{nav_class("live")}">
            <span class="nav-icon">▣</span>
            <span>กล้อง Real-time</span>
        </a>

    </nav>


    <div class="sidebar-footer">

        <div class="footer-status">
            ● ระบบ AI พร้อมทำงาน
        </div>

    </div>

</aside>


<main class="main">

    <header class="topbar">

        <div>
            <div class="top-label">
                AI SHRIMP SORTING
            </div>

            <div class="top-title">
                ระบบควบคุมการคัดแยกกุ้ง
            </div>
        </div>


        <div class="top-actions">

            <button class="top-btn">
                ☼
            </button>

            <button class="top-btn">
                ◉
            </button>

            <div class="user-box">
                AI
            </div>

        </div>

    </header>


    <section class="content">

        {content}

    </section>

</main>

</body>

</html>
"""


# =========================================================
# DASHBOARD PAGE
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def home():

    content = """

<div class="page-head">

    <h1>
        ระบบคัดแยกกุ้งอัจฉริยะ
    </h1>

    <p>
        Dashboard สำหรับติดตามผลการคัดแยกด้วย AI แบบรวมศูนย์
    </p>

</div>


<div class="status-bar">

    <div class="status-main">

        <div class="status-icon">
            🦐
        </div>

        <div>

            <div class="status-title">
                AI Sorting System
            </div>

            <div class="status-text">
                ระบบพร้อมรับข้อมูลจากเครื่อง AI และกล้อง
            </div>

        </div>

    </div>

    <div class="status-pill">
        ● SYSTEM READY
    </div>

</div>


<div class="kpi-grid">

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

        <div class="kpi-unit">
            ตัว
        </div>

    </div>


    <div class="kpi green">

        <div class="kpi-label">
            กุ้งที่คัดแยกแล้ว
        </div>

        <div
            class="kpi-value"
            id="sorted"
        >
            0
        </div>

        <div class="kpi-unit">
            จากรอบล่าสุด
        </div>

    </div>


    <div class="kpi orange">

        <div class="kpi-label">
            จำนวนรอบ
        </div>

        <div
            class="kpi-value"
            id="rounds"
        >
            0
        </div>

        <div class="kpi-unit">
            รอบทั้งหมด
        </div>

    </div>


    <div class="kpi red">

        <div class="kpi-label">
            กุ้งป่วย
        </div>

        <div
            class="kpi-value"
            id="sick"
        >
            0
        </div>

        <div class="kpi-unit">
            ตัว
        </div>

    </div>

</div>


<div class="section-title">
    ผลการคัดแยกกุ้ง
</div>


<div class="shrimp-grid">

    <div class="shrimp-card">

        <div class="shrimp-header">

            <div class="shrimp-name">
                กุ้งเล็ก
            </div>

            <div class="shrimp-square"></div>

        </div>

        <div
            class="shrimp-number"
            id="small"
        >
            0
        </div>

        <div class="shrimp-unit">
            ตัว
        </div>

    </div>


    <div class="shrimp-card">

        <div class="shrimp-header">

            <div class="shrimp-name">
                กุ้งกลาง
            </div>

            <div class="shrimp-square medium"></div>

        </div>

        <div
            class="shrimp-number"
            id="medium"
        >
            0
        </div>

        <div class="shrimp-unit">
            ตัว
        </div>

    </div>


    <div class="shrimp-card">

        <div class="shrimp-header">

            <div class="shrimp-name">
                กุ้งใหญ่
            </div>

            <div class="shrimp-square large"></div>

        </div>

        <div
            class="shrimp-number"
            id="large"
        >
            0
        </div>

        <div class="shrimp-unit">
            ตัว
        </div>

    </div>


    <div class="shrimp-card">

        <div class="shrimp-header">

            <div class="shrimp-name">
                กุ้งป่วย
            </div>

            <div class="shrimp-square sick"></div>

        </div>

        <div
            class="shrimp-number"
            id="sickCard"
        >
            0
        </div>

        <div class="shrimp-unit">
            ตัว
        </div>

    </div>

</div>


<div class="panel">

    <div class="panel-head">

        <div>

            <div class="panel-title">
                รอบการคัดแยกล่าสุด
            </div>

            <div class="panel-sub">
                ข้อมูลที่ได้รับล่าสุดจากเครื่อง AI
            </div>

        </div>

    </div>


    <div class="table-wrap">

        <table>

            <thead>

                <tr>
                    <th>รอบ</th>
                    <th>กุ้งทั้งหมด</th>
                    <th>FPS เฉลี่ย</th>
                    <th>จำนวนเฟรม</th>
                    <th>เวลา</th>
                </tr>

            </thead>

            <tbody id="latestTable">

                <tr>
                    <td colspan="5">
                        <div class="empty">
                            ยังไม่มีข้อมูล
                        </div>
                    </td>
                </tr>

            </tbody>

        </table>

    </div>

</div>


<div class="section-title">
    เมนูระบบ
</div>


<div class="quick-grid">

    <a class="quick-card" href="/daily">

        <div class="quick-no">
            01
        </div>

        <div class="quick-title">
            รายงานรายวัน
        </div>

        <div class="quick-desc">
            ดูผลการคัดแยกในแต่ละวัน
        </div>

    </a>


    <a class="quick-card" href="/monthly">

        <div class="quick-no">
            02
        </div>

        <div class="quick-title">
            รายงานรายเดือน
        </div>

        <div class="quick-desc">
            วิเคราะห์ข้อมูลรายเดือน
        </div>

    </a>


    <a class="quick-card" href="/yearly">

        <div class="quick-no">
            03
        </div>

        <div class="quick-title">
            รายงานรายปี
        </div>

        <div class="quick-desc">
            สรุปผลการทำงานรายปี
        </div>

    </a>


    <a class="quick-card" href="/live">

        <div class="quick-no">
            04
        </div>

        <div class="quick-title">
            กล้อง Real-time
        </div>

        <div class="quick-desc">
            ดูภาพจากเครื่อง AI แบบสด
        </div>

    </a>

</div>


<script>

async function loadDashboard() {

    try {

        const res =
            await fetch("/api/dashboard");

        const data =
            await res.json();

        const counts =
            data.totals || {};

        const total =
            data.total || 0;

        document.getElementById("total")
            .textContent = total;

        document.getElementById("sorted")
            .textContent = total;

        document.getElementById("rounds")
            .textContent =
                data.rounds || 0;

        document.getElementById("sick")
            .textContent =
                counts["กุ้งป่วย"] || 0;

        document.getElementById("small")
            .textContent =
                counts["กุ้งเล็ก"] || 0;

        document.getElementById("medium")
            .textContent =
                counts["กุ้งกลาง"] || 0;

        document.getElementById("large")
            .textContent =
                counts["กุ้งใหญ่"] || 0;

        document.getElementById("sickCard")
            .textContent =
                counts["กุ้งป่วย"] || 0;


        const round =
            data.latest_round;

        const table =
            document.getElementById(
                "latestTable"
            );


        if (!round) {

            table.innerHTML = `
                <tr>
                    <td colspan="5">
                        <div class="empty">
                            ยังไม่มีข้อมูลจากเครื่อง AI
                        </div>
                    </td>
                </tr>
            `;

            return;
        }


        table.innerHTML = `

            <tr>

                <td>
                    #${round.round_id}
                </td>

                <td>
                    ${total}
                </td>

                <td>
                    ${Number(
                        round.avg_fps || 0
                    ).toFixed(1)}
                </td>

                <td>
                    ${round.frames || 0}
                </td>

                <td>
                    ${round.finished_at || "-"}
                </td>

            </tr>

        `;

    } catch (error) {

        console.error(error);

    }

}


loadDashboard();

setInterval(
    loadDashboard,
    3000
);

</script>

"""

    return layout(
        content,
        "dashboard"
    )


# =========================================================
# ANALYTICS PAGE
# =========================================================

def analytics_page(mode):

    titles = {
        "daily": "สถิติการคัดแยกรายวัน",
        "monthly": "สถิติการคัดแยกรายเดือน",
        "yearly": "สถิติการคัดแยกรายปี"
    }

    descriptions = {
        "daily":
            "แสดงจำนวนกุ้งแต่ละประเภทที่คัดแยกได้ในแต่ละวัน",

        "monthly":
            "แสดงจำนวนกุ้งแต่ละประเภทที่คัดแยกได้ในแต่ละเดือน",

        "yearly":
            "แสดงจำนวนกุ้งแต่ละประเภทที่คัดแยกได้ในแต่ละปี"
    }

    endpoint = f"/api/analytics/{mode}"

    content = f"""

<a
    class="back"
    href="/"
>
    ← กลับหน้าหลัก
</a>


<div class="page-head">

    <h1>
        {titles[mode]}
    </h1>

    <p>
        {descriptions[mode]}
    </p>

</div>


<div class="chart-panel">

    <div class="panel-head">

        <div>

            <div class="panel-title">
                จำนวนกุ้งที่คัดแยก
            </div>

            <div class="panel-sub">
                แยกตามประเภทกุ้ง
            </div>

        </div>

    </div>


    <div class="chart-area">

        <canvas id="chart"></canvas>

    </div>

</div>


<script>

const endpoint =
    "{endpoint}";

const canvas =
    document.getElementById("chart");

const ctx =
    canvas.getContext("2d");


async function loadChart() {

    const res =
        await fetch(endpoint);

    const result =
        await res.json();

    const data =
        result.data || [];


    const width =
        canvas.clientWidth;

    const height =
        canvas.clientHeight;

    const dpr =
        window.devicePixelRatio || 1;


    canvas.width =
        width * dpr;

    canvas.height =
        height * dpr;

    ctx.setTransform(
        dpr,
        0,
        0,
        dpr,
        0,
        0
    );


    ctx.clearRect(
        0,
        0,
        width,
        height
    );


    if (!data.length) {

        ctx.fillStyle =
            "#8391a3";

        ctx.font =
            "16px Arial";

        ctx.textAlign =
            "center";

        ctx.fillText(
            "ยังไม่มีข้อมูล",
            width / 2,
            height / 2
        );

        return;
    }


    const left =
        65;

    const right =
        25;

    const top =
        30;

    const bottom =
        65;


    const chartWidth =
        width - left - right;

    const chartHeight =
        height - top - bottom;


    let maxValue = 0;

    data.forEach(item => {

        SHRIMP_TYPES.forEach(type => {

            maxValue =
                Math.max(
                    maxValue,
                    Number(
                        item[type] || 0
                    )
                );

        });

    });


    if (maxValue <= 0)
        maxValue = 10;


    const steps = 5;


    /* GRID */

    ctx.strokeStyle =
        "#e8eef5";

    ctx.lineWidth = 1;

    ctx.font =
        "12px Arial";

    ctx.fillStyle =
        "#7b899b";

    ctx.textAlign =
        "right";


    for (
        let i = 0;
        i <= steps;
        i++
    ) {

        const value =
            maxValue *
            i /
            steps;

        const y =
            top +
            chartHeight -
            (
                value /
                maxValue
            ) *
            chartHeight;


        ctx.beginPath();

        ctx.moveTo(
            left,
            y
        );

        ctx.lineTo(
            width - right,
            y
        );

        ctx.stroke();


        ctx.fillText(
            Math.round(value),
            left - 10,
            y + 4
        );

    }


    /* BAR */

    const colors = [
        "#247ce4",
        "#20aa76",
        "#efa52b",
        "#df5e69"
    ];


    const groupWidth =
        chartWidth /
        data.length;

    const barWidth =
        Math.min(
            25,
            groupWidth / 6
        );


    data.forEach(
        (item, index) => {

            const xCenter =
                left +
                groupWidth *
                index +
                groupWidth / 2;


            SHRIMP_TYPES.forEach(
                (type, typeIndex) => {

                    const value =
                        Number(
                            item[type] || 0
                        );


                    const barHeight =
                        (
                            value /
                            maxValue
                        ) *
                        chartHeight;


                    const x =
                        xCenter -
                        (
                            SHRIMP_TYPES.length *
                            barWidth
                        ) / 2 +
                        typeIndex *
                        barWidth;


                    const y =
                        top +
                        chartHeight -
                        barHeight;


                    ctx.fillStyle =
                        colors[typeIndex];


                    ctx.fillRect(
                        x,
                        y,
                        barWidth - 3,
                        barHeight
                    );

                }
            );


            ctx.fillStyle =
                "#69788c";

            ctx.font =
                "11px Arial";

            ctx.textAlign =
                "center";


            ctx.fillText(
                item.period,
                xCenter,
                height - 28
            );

        }
    );


    /* LEGEND */

    const legendY =
        12;

    let legendX =
        left;


    SHRIMP_TYPES.forEach(
        (type, index) => {

            ctx.fillStyle =
                colors[index];

            ctx.fillRect(
                legendX,
                legendY,
                12,
                12
            );

            ctx.fillStyle =
                "#526176";

            ctx.font =
                "12px Arial";

            ctx.textAlign =
                "left";

            ctx.fillText(
                type,
                legendX + 17,
                legendY + 10
            );

            legendX +=
                95 +
                type.length * 2;

        }
    );

}


loadChart();

window.addEventListener(
    "resize",
    loadChart
);

</script>

"""

    return layout(
        content,
        mode
    )


@app.get("/daily", response_class=HTMLResponse)
async def daily():
    return analytics_page("daily")


@app.get("/monthly", response_class=HTMLResponse)
async def monthly():
    return analytics_page("monthly")


@app.get("/yearly", response_class=HTMLResponse)
async def yearly():
    return analytics_page("yearly")


# =========================================================
# LIVE PAGE
# =========================================================

@app.get("/live", response_class=HTMLResponse)
async def live():

    content = """

<a
    class="back"
    href="/"
>
    ← กลับหน้าหลัก
</a>


<div class="page-head">

    <h1>
        กล้อง Real-time
    </h1>

    <p>
        ภาพจากเครื่อง AI สำหรับติดตามกระบวนการคัดแยกแบบสด
    </p>

</div>


<div class="live-grid">


    <div class="camera-panel">

        <div
            class="live-label"
            id="liveStatus"
        >
            ● OFFLINE
        </div>

        <img
            id="camera"
            alt="AI Camera"
        >

        <div
            class="camera-empty"
            id="cameraEmpty"
        >
            กำลังรอภาพจากเครื่อง AI
        </div>

    </div>


    <div class="live-info">

        <h2>
            สถานะระบบ
        </h2>


        <div class="live-stat">

            <div class="live-stat-label">
                สถานะกล้อง
            </div>

            <div
                class="live-stat-value"
                id="status"
            >
                OFFLINE
            </div>

        </div>


        <div class="live-stat">

            <div class="live-stat-label">
                FPS
            </div>

            <div
                class="live-stat-value"
                id="fps"
            >
                0
            </div>

        </div>


        <div class="live-stat">

            <div class="live-stat-label">
                อัปเดตล่าสุด
            </div>

            <div
                class="live-stat-value"
                id="lastUpdate"
                style="font-size:16px;"
            >
                -
            </div>

        </div>

    </div>

</div>


<script>

const camera =
    document.getElementById(
        "camera"
    );

const empty =
    document.getElementById(
        "cameraEmpty"
    );


async function updateCamera() {

    try {

        const response =
            await fetch(
                "/api/live/frame?t=" +
                Date.now()
            );


        if (!response.ok) {

            camera.style.display =
                "none";

            empty.style.display =
                "block";

            return;
        }


        const blob =
            await response.blob();


        camera.src =
            URL.createObjectURL(blob);

        camera.style.display =
            "block";

        empty.style.display =
            "none";

    } catch (error) {

        camera.style.display =
            "none";

        empty.style.display =
            "block";

    }

}


async function updateStatus() {

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
                "liveStatus"
            );


        if (data.online) {

            status.textContent =
                "ONLINE";

            status.style.color =
                "#20aa76";

            badge.textContent =
                "● ONLINE";

            badge.style.color =
                "#20aa76";

        } else {

            status.textContent =
                "OFFLINE";

            status.style.color =
                "#df5e69";

            badge.textContent =
                "● OFFLINE";

            badge.style.color =
                "#df5e69";
        }


        document.getElementById(
            "fps"
        ).textContent =
            Number(
                data.fps || 0
            ).toFixed(1);


        document.getElementById(
            "lastUpdate"
        ).textContent =
            data.last_update || "-";


    } catch (error) {

        console.error(error);

    }

}


updateCamera();

updateStatus();


setInterval(
    updateCamera,
    500
);

setInterval(
    updateStatus,
    2000
);

</script>

"""

    return layout(
        content,
        "live"
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )
