import os
import base64
from collections import deque
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, Response
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
    version="3.0"
)


# =========================================================
# MEMORY
# =========================================================

latest_round: Dict[str, Any] = {}

round_history = deque(maxlen=1000)

live_frame = None
live_ts = None

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

    counts: Dict[str, int] = Field(
        default_factory=dict
    )

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

def check_api_key(key):

    if key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )


def clean_counts(counts):

    result = {}

    for shrimp in SHRIMP_TYPES:

        try:
            value = int(
                counts.get(shrimp, 0)
            )
        except Exception:
            value = 0

        result[shrimp] = max(0, value)

    return result


def parse_datetime(value):

    if not value:
        return None

    value = str(value).strip()

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d"
    ]

    for fmt in formats:

        try:
            return datetime.strptime(
                value,
                fmt
            )
        except Exception:
            pass

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except Exception:
        return None


def get_round_date(item):

    for key in [
        "finished_at",
        "started_at",
        "received_at"
    ]:

        dt = parse_datetime(
            item.get(key)
        )

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

    counts = clean_counts(
        report.counts
    )

    total = sum(
        counts.values()
    )

    item = {

        "round_id":
            report.round_id,

        "counts":
            counts,

        "total":
            total,

        "avg_fps":
            report.avg_fps,

        "duration":
            report.duration,

        "frames":
            report.frames,

        "started_at":
            report.started_at,

        "finished_at":
            report.finished_at,

        "received_at":
            datetime.now().isoformat()
    }

    latest_round.clear()

    latest_round.update(
        item
    )

    round_history.appendleft(
        item
    )

    return {
        "success": True,
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

    decoded = decode_frame(
        report.frame
    )

    if decoded:

        live_frame = decoded

    live_ts = datetime.now()

    live_status["online"] = True
    live_status["fps"] = report.fps
    live_status["last_update"] = (
        live_ts.isoformat()
    )

    return {
        "success": True
    }


# =========================================================
# DASHBOARD API
# =========================================================

@app.get("/api/dashboard")
async def dashboard_api():

    counts = clean_counts(
        latest_round.get(
            "counts",
            {}
        )
    )

    total = sum(
        counts.values()
    )

    return {

        "success": True,

        "latest_round":
            latest_round,

        "counts":
            counts,

        "total":
            total,

        "rounds":
            len(round_history)
    }


# =========================================================
# ANALYTICS
# =========================================================

def build_analytics(mode):

    groups = {}

    for item in round_history:

        dt = get_round_date(
            item
        )

        if mode == "daily":

            key = dt.strftime(
                "%Y-%m-%d"
            )

        elif mode == "monthly":

            key = dt.strftime(
                "%Y-%m"
            )

        else:

            key = dt.strftime(
                "%Y"
            )

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
            item.get(
                "counts",
                {}
            )
        )

        for shrimp in SHRIMP_TYPES:

            groups[key][shrimp] += (
                counts[shrimp]
            )

        groups[key]["total"] += sum(
            counts.values()
        )

    data = list(
        groups.values()
    )

    data.sort(
        key=lambda x: x["label"]
    )

    if mode == "daily":
        data = data[-30:]

    elif mode == "monthly":
        data = data[-12:]

    else:
        data = data[-10:]

    return data


@app.get("/api/analytics/daily")
async def daily_api():

    return {
        "success": True,
        "data":
            build_analytics("daily")
    }


@app.get("/api/analytics/monthly")
async def monthly_api():

    return {
        "success": True,
        "data":
            build_analytics("monthly")
    }


@app.get("/api/analytics/yearly")
async def yearly_api():

    return {
        "success": True,
        "data":
            build_analytics("yearly")
    }


# =========================================================
# LIVE
# =========================================================

@app.get("/api/live/status")
async def live_status_api():

    # ถ้าไม่มีข้อมูลเกิน 10 วินาที
    # ถือว่า Offline

    if live_ts:

        seconds = (
            datetime.now() - live_ts
        ).total_seconds()

        if seconds > 10:

            live_status["online"] = False

    return {
        "success": True,
        **live_status
    }


@app.get("/api/live/frame")
async def live_frame_api():

    if not live_frame:

        return Response(
            status_code=404
        )

    return Response(

        content=live_frame,

        media_type="image/jpeg",

        headers={
            "Cache-Control":
                "no-store, no-cache"
        }
    )


# =========================================================
# CSS
# =========================================================

CSS = r"""
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

    color: #17243a;

    background:
        #f4f8fc;
}


/* =====================================================
   SIDEBAR
===================================================== */

.sidebar {

    position: fixed;

    left: 0;
    top: 0;
    bottom: 0;

    width: 258px;

    background: #ffffff;

    border-right:
        1px solid #e4ebf3;

    padding: 22px 18px;

    z-index: 100;

    display: flex;

    flex-direction: column;
}


/* BRAND */

.brand {

    display: flex;

    align-items: center;

    gap: 12px;

    padding:
        4px 7px 27px;
}

.brand-icon {

    width: 47px;
    height: 47px;

    border-radius: 15px;

    display: grid;

    place-items: center;

    font-size: 24px;

    color: white;

    background:
        linear-gradient(
            135deg,
            #4f8df7,
            #6ca5ff
        );

    box-shadow:
        0 8px 20px
        rgba(66,132,240,.25);
}

.brand-title {

    font-size: 17px;

    font-weight: 800;

    color: #17243a;

    line-height: 1.15;
}

.brand-sub {

    margin-top: 4px;

    font-size: 10px;

    color: #8391a6;
}


/* MENU */

.sidebar-menu {

    display: flex;

    flex-direction: column;

    gap: 5px;

    flex: 1;
}

.menu-item {

    display: flex;

    align-items: center;

    gap: 13px;

    padding:
        13px 13px;

    border-radius: 14px;

    color: #33445b;

    font-size: 14px;

    font-weight: 600;

    transition: .2s;

    cursor: pointer;
}

.menu-item:hover {

    background: #f2f7fd;

    color: #2372df;
}

.menu-item.active {

    color: #2675e5;

    background:
        #eaf2ff;

    box-shadow:
        inset 0 -2px 0
        #3d83ed;
}

.menu-icon {

    width: 25px;

    text-align: center;

    font-size: 18px;
}


/* SIDEBAR BOTTOM */

.sidebar-bottom {

    border-top:
        1px solid #e6edf5;

    padding-top: 14px;
}

.mode-button {

    width: 100%;

    border: 0;

    background:
        #f0f5fb;

    border-radius: 14px;

    padding: 12px;

    color: #30415a;

    text-align: left;

    font-size: 13px;

    cursor: pointer;
}

.logout {

    padding:
        13px;

    color:
        #ff5d67;

    font-size: 13px;

    font-weight: 600;
}


/* =====================================================
   MAIN
===================================================== */

.main {

    margin-left: 258px;

    min-height: 100vh;
}


/* =====================================================
   TOPBAR
===================================================== */

.topbar {

    height: 67px;

    background:
        rgba(255,255,255,.94);

    border-bottom:
        1px solid #e3ebf4;

    display: flex;

    align-items: center;

    justify-content: space-between;

    padding:
        0 25px;

    position: sticky;

    top: 0;

    z-index: 50;

    backdrop-filter:
        blur(15px);
}

.top-info {

    display: flex;

    flex-direction: column;
}

.top-label {

    color: #4b88f4;

    font-size: 10px;

    font-weight: 800;

    letter-spacing: 1px;
}

.top-heading {

    font-size: 16px;

    font-weight: 800;

    margin-top: 3px;
}

.top-actions {

    display: flex;

    align-items: center;

    gap: 9px;
}

.top-button {

    width: 40px;
    height: 40px;

    border-radius: 12px;

    border:
        1px solid #e3ebf4;

    background:
        #f4f8fc;

    display: grid;

    place-items: center;

    color: #31435c;

    cursor: pointer;

    font-size: 17px;
}

.avatar {

    width: 39px;
    height: 39px;

    border-radius: 50%;

    display: grid;

    place-items: center;

    background:
        #5e91ee;

    color: white;

    font-weight: 800;
}


/* =====================================================
   CONTENT
===================================================== */

.content {

    width:
        min(
            1100px,
            calc(100% - 60px)
        );

    margin:
        0 auto;

    padding:
        39px 0 70px;

    background-image:
        linear-gradient(
            rgba(62,113,182,.035) 1px,
            transparent 1px
        ),
        linear-gradient(
            90deg,
            rgba(62,113,182,.035) 1px,
            transparent 1px
        );

    background-size:
        25px 25px;
}


/* =====================================================
   WELCOME
===================================================== */

.welcome {

    margin-bottom: 25px;
}

.welcome h1 {

    margin: 0;

    font-size: 28px;

    font-weight: 800;

    letter-spacing: -.6px;
}

.welcome p {

    margin:
        8px 0 0;

    color: #8290a4;

    font-size: 14px;
}


/* =====================================================
   AI RECOMMENDATION
===================================================== */

.ai-card {

    position: relative;

    overflow: hidden;

    min-height: 210px;

    padding:
        25px 30px;

    border-radius: 24px;

    color: white;

    background:
        linear-gradient(
            110deg,
            #3275e4,
            #2762c9
        );

    box-shadow:
        0 18px 40px
        rgba(40,100,210,.23);

    margin-bottom: 25px;
}

.ai-card::after {

    content: "";

    position: absolute;

    width: 210px;
    height: 210px;

    right: -75px;
    top: -105px;

    border-radius: 50%;

    border:
        35px solid
        rgba(255,255,255,.10);
}

.ai-inner {

    position: relative;

    z-index: 2;

    display: flex;

    gap: 17px;
}

.ai-icon {

    width: 45px;
    height: 45px;

    flex-shrink: 0;

    display: grid;

    place-items: center;

    border-radius: 14px;

    background:
        rgba(255,255,255,.18);

    font-size: 22px;
}

.ai-title {

    font-size: 17px;

    font-weight: 800;
}

.ai-text {

    max-width: 800px;

    margin-top: 8px;

    color:
        rgba(255,255,255,.88);

    line-height: 1.7;

    font-size: 13px;
}

.ai-tags {

    display: flex;

    flex-wrap: wrap;

    gap: 7px;

    margin-top: 12px;
}

.ai-tag {

    padding:
        6px 10px;

    border-radius: 999px;

    background:
        rgba(255,255,255,.17);

    font-size: 11px;

    font-weight: 700;
}

.ai-button {

    display: inline-block;

    margin-top: 14px;

    padding:
        10px 17px;

    border-radius: 10px;

    background:
        white;

    color:
        #3976d9;

    font-size: 12px;

    font-weight: 800;
}


/* =====================================================
   KPI AREA
===================================================== */

.stats-layout {

    display: grid;

    grid-template-columns:
        1fr 2fr;

    gap: 17px;

    margin-bottom: 29px;
}


/* BIG GOAL CARD */

.goal-card {

    min-height: 220px;

    border-radius: 22px;

    background:
        white;

    border:
        1px solid #e0e8f1;

    box-shadow:
        0 10px 35px
        rgba(38,77,125,.07);

    display: flex;

    flex-direction: column;

    align-items: center;

    justify-content: center;
}

.goal-circle {

    width: 100px;
    height: 100px;

    border-radius: 50%;

    background:
        conic-gradient(
            #2dbb82 0 28%,
            #e5edf5 28% 100%
        );

    position: relative;

    display: grid;

    place-items: center;
}

.goal-circle::after {

    content: "";

    position: absolute;

    width: 76px;
    height: 76px;

    border-radius: 50%;

    background:
        white;
}

.goal-value {

    position: relative;

    z-index: 2;

    font-size: 20px;

    font-weight: 800;

    color: #1f3150;
}

.goal-label {

    margin-top: 12px;

    font-size: 12px;

    color: #7c8ba0;
}


/* KPI GRID */

.kpi-grid {

    display: grid;

    grid-template-columns:
        1fr 1fr;

    gap: 17px;
}

.kpi-card {

    min-height: 101px;

    padding:
        20px;

    border-radius: 20px;

    background:
        white;

    border:
        1px solid #e0e8f1;

    box-shadow:
        0 10px 30px
        rgba(38,77,125,.06);

    display: flex;

    align-items: center;

    gap: 15px;
}

.kpi-icon {

    width: 45px;
    height: 45px;

    border-radius: 14px;

    display: grid;

    place-items: center;

    font-size: 21px;

    flex-shrink: 0;
}

.kpi-blue {
    background: #eaf2ff;
    color: #377ff0;
}

.kpi-green {
    background: #e5f8ef;
    color: #18a66b;
}

.kpi-orange {
    background: #fff2dc;
    color: #e99b1f;
}

.kpi-red {
    background: #ffebee;
    color: #ed5b69;
}

.kpi-label {

    color:
        #7d8ba0;

    font-size: 11px;
}

.kpi-value {

    margin-top: 4px;

    font-size: 21px;

    font-weight: 800;

    color:
        #1c2c45;
}

.kpi-sub {

    margin-top: 3px;

    color: #4784e6;

    font-size: 10px;
}


/* =====================================================
   QUICK MENU
===================================================== */

.section-title {

    margin:
        0 0 17px;

    font-size: 25px;

    font-weight: 800;
}

.quick-grid {

    display: grid;

    grid-template-columns:
        repeat(4,1fr);

    gap: 16px;
}

.quick-card {

    min-height: 145px;

    padding:
        20px;

    border-radius: 20px;

    background:
        white;

    border:
        1px solid #e0e8f1;

    box-shadow:
        0 10px 30px
        rgba(38,77,125,.06);

    display: flex;

    flex-direction: column;

    align-items: center;

    justify-content: center;

    text-align: center;

    transition:
        .22s;
}

.quick-card:hover {

    transform:
        translateY(-4px);

    border-color:
        #b8d1f7;

    box-shadow:
        0 18px 35px
        rgba(50,108,210,.12);
}

.quick-icon {

    width: 47px;
    height: 47px;

    border-radius: 14px;

    display: grid;

    place-items: center;

    margin-bottom: 13px;

    font-size: 21px;

    background:
        #eaf2ff;

    color:
        #347ce8;
}

.quick-icon.green {

    background:
        #e5f8ef;

    color:
        #18a66b;
}

.quick-icon.orange {

    background:
        #fff2dc;

    color:
        #e99b1f;
}

.quick-title {

    font-size: 14px;

    font-weight: 800;

    color:
        #24344c;
}

.quick-desc {

    margin-top: 5px;

    color:
        #8996a8;

    font-size: 10px;
}


/* =====================================================
   ANALYTICS
===================================================== */

.page-title {

    margin-bottom: 25px;
}

.back {

    display: inline-flex;

    padding:
        8px 12px;

    margin-bottom: 15px;

    border-radius: 10px;

    background:
        white;

    border:
        1px solid #e0e8f1;

    color:
        #4a7fd4;

    font-size: 12px;

    font-weight: 700;
}

.page-title h1 {

    margin: 0;

    font-size: 30px;
}

.page-title p {

    color:
        #8290a4;

    font-size: 13px;
}


/* PANEL */

.panel {

    padding:
        25px;

    background:
        white;

    border:
        1px solid #e0e8f1;

    border-radius:
        22px;

    box-shadow:
        0 10px 35px
        rgba(38,77,125,.06);

    margin-bottom:
        20px;
}

.panel-title {

    font-size: 18px;

    font-weight: 800;
}

.panel-sub {

    margin-top: 5px;

    color:
        #8b98a9;

    font-size: 12px;
}


/* CHART */

.chart-box {

    width: 100%;

    min-height: 400px;

    margin-top: 20px;
}

canvas {

    width: 100% !important;

    height: 400px !important;
}


/* TABLE */

.table-wrap {

    overflow-x:
        auto;
}

table {

    width: 100%;

    border-collapse:
        collapse;

    font-size: 12px;
}

th {

    padding:
        14px;

    text-align:
        left;

    color:
        #7d8ba0;

    background:
        #f5f8fc;
}

td {

    padding:
        15px 14px;

    border-bottom:
        1px solid #edf1f6;
}

tr:hover td {

    background:
        #f9fbfe;
}


/* =====================================================
   LIVE CAMERA
===================================================== */

.live-layout {

    display: grid;

    grid-template-columns:
        1.7fr .6fr;

    gap: 20px;
}

.camera {

    min-height:
        500px;

    border-radius:
        22px;

    overflow:
        hidden;

    background:
        #07111e;

    position:
        relative;

    display:
        grid;

    place-items:
        center;

    box-shadow:
        0 20px 50px
        rgba(20,45,80,.18);
}

.camera img {

    width: 100%;

    height: 100%;

    object-fit:
        contain;
}

.camera-placeholder {

    color:
        #8d9db2;

    text-align:
        center;
}

.live-badge {

    position:
        absolute;

    top: 15px;
    left: 15px;

    z-index: 5;

    padding:
        8px 12px;

    border-radius:
        999px;

    background:
        white;

    color:
        #15a66a;

    font-size:
        11px;

    font-weight:
        800;
}

.live-dot {

    display:
        inline-block;

    width: 8px;
    height: 8px;

    border-radius:
        50%;

    background:
        #21c47b;

    margin-right:
        5px;
}

.live-stats {

    display:
        flex;

    flex-direction:
        column;

    gap:
        14px;
}

.live-stat {

    background:
        white;

    border:
        1px solid #e0e8f1;

    border-radius:
        18px;

    padding:
        20px;

    box-shadow:
        0 10px 30px
        rgba(38,77,125,.06);
}

.live-stat-label {

    color:
        #8290a4;

    font-size:
        11px;
}

.live-stat-value {

    margin-top:
        7px;

    font-size:
        25px;

    font-weight:
        800;
}


/* =====================================================
   FOOTER
===================================================== */

.footer {

    padding:
        25px;

    text-align:
        center;

    color:
        #94a1b2;

    font-size:
        10px;
}


/* =====================================================
   MOBILE
===================================================== */

@media(max-width:1000px) {

    .sidebar {

        width:
            80px;

        padding:
            20px 10px;
    }

    .brand {

        justify-content:
            center;
    }

    .brand-title,
    .brand-sub {

        display:
            none;
    }

    .brand-icon {

        width:
            45px;

        height:
            45px;
    }

    .menu-item {

        justify-content:
            center;
    }

    .menu-item span:not(.menu-icon) {

        display:
            none;
    }

    .sidebar-bottom {

        display:
            none;
    }

    .main {

        margin-left:
            80px;
    }

    .stats-layout {

        grid-template-columns:
            1fr;
    }

    .quick-grid {

        grid-template-columns:
            repeat(2,1fr);
    }

    .live-layout {

        grid-template-columns:
            1fr;
    }
}


@media(max-width:650px) {

    .sidebar {

        width:
            64px;
    }

    .main {

        margin-left:
            64px;
    }

    .content {

        width:
            calc(100% - 24px);

        padding-top:
            25px;
    }

    .topbar {

        padding:
            0 12px;
    }

    .top-heading {

        font-size:
            14px;
    }

    .welcome h1 {

        font-size:
            23px;
    }

    .ai-card {

        padding:
            20px;
    }

    .kpi-grid {

        grid-template-columns:
            1fr;
    }

    .quick-grid {

        grid-template-columns:
            1fr 1fr;
    }

    .camera {

        min-height:
            300px;
    }
}
"""


# =========================================================
# LAYOUT
# =========================================================

def navbar(active="home"):

    items = [

        ("home", "/", "⌂", "หน้าหลัก"),

        ("daily", "/daily", "▥", "รายวัน"),

        ("monthly", "/monthly", "◈", "รายเดือน"),

        ("yearly", "/yearly", "▥", "รายปี"),

        ("live", "/live", "◉", "Live Camera"),
    ]

    menu = ""

    for key, url, icon, name in items:

        active_class = (
            "active"
            if key == active
            else ""
        )

        menu += f"""
        <a
            href="{url}"
            class="menu-item {active_class}"
        >
            <span class="menu-icon">
                {icon}
            </span>

            <span>
                {name}
            </span>
        </a>
        """

    return f"""

    <aside class="sidebar">

        <div class="brand">

            <div class="brand-icon">
                🦐
            </div>

            <div>

                <div class="brand-title">
                    Shrimp AI
                </div>

                <div class="brand-sub">
                    Intelligent Factory
                </div>

            </div>

        </div>


        <div class="sidebar-menu">

            {menu}

        </div>


        <div class="sidebar-bottom">

            <button
                class="mode-button"
                onclick="toggleMode()"
            >
                ☼ &nbsp; โหมดสว่าง
            </button>

            <div class="logout">
                ↪ &nbsp; ระบบออนไลน์
            </div>

        </div>

    </aside>


    <header class="topbar">

        <div class="top-info">

            <div class="top-label">
                SHRIMP AI FACTORY
            </div>

            <div class="top-heading">
                ระบบคัดแยกกุ้งอัจฉริยะ
            </div>

        </div>


        <div class="top-actions">

            <button
                class="top-button"
                onclick="toggleMode()"
            >
                ☼
            </button>

            <button class="top-button">
                ♧
            </button>

            <div class="avatar">
                AI
            </div>

        </div>

    </header>
    """


def page(
    title,
    content,
    active="home",
    script=""
):

    return f"""
<!DOCTYPE html>

<html lang="th">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1.0"
>

<title>
    {title} - Shrimp AI Factory
</title>

<style>
{CSS}
</style>

</head>

<body>

{navbar(active)}

<div class="main">

    <main class="content">

        {content}

    </main>

    <footer class="footer">

        SHRIMP AI FACTORY
        ·
        AI Intelligent Sorting System

    </footer>

</div>


<script>

function toggleMode() {{

    alert(
        "ระบบนี้ใช้โหมด Premium Light เป็นค่าเริ่มต้น"
    );

}}

{script}

</script>

</body>

</html>
"""


# =========================================================
# HOME
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def home():

    content = """

    <section class="welcome">

        <h1>
            สวัสดีตอนเย็น 👋
        </h1>

        <p>
            ยินดีต้อนรับเข้าสู่ระบบ
            Shrimp AI Factory
        </p>

    </section>


    <section class="ai-card">

        <div class="ai-inner">

            <div class="ai-icon">
                ✨
            </div>

            <div>

                <div class="ai-title">
                    คำแนะนำจาก AI
                </div>

                <div class="ai-text">

                    ระบบ AI พร้อมทำงาน
                    และกำลังติดตามผลการคัดแยกกุ้ง
                    จากกล้องแบบเรียลไทม์
                    สามารถตรวจสอบจำนวนกุ้ง
                    และประสิทธิภาพของแต่ละรอบได้

                </div>

                <div class="ai-tags">

                    <span class="ai-tag">
                        🦐 AI Sorting
                    </span>

                    <span class="ai-tag">
                        📷 Camera
                    </span>

                    <span class="ai-tag">
                        📊 Analytics
                    </span>

                </div>

                <a
                    href="/live"
                    class="ai-button"
                >
                    เริ่มดูระบบ
                </a>

            </div>

        </div>

    </section>


    <section class="stats-layout">


        <div class="goal-card">

            <div class="goal-circle">

                <div class="goal-value">
                    0%
                </div>

            </div>

            <div class="goal-label">
                เป้าหมายการคัดแยกวันนี้
            </div>

        </div>


        <div class="kpi-grid">


            <div class="kpi-card">

                <div
                    class="kpi-icon kpi-orange"
                >
                    🦐
                </div>

                <div>

                    <div class="kpi-label">
                        กุ้งทั้งหมด
                    </div>

                    <div
                        id="total"
                        class="kpi-value"
                    >
                        0
                    </div>

                    <div class="kpi-sub">
                        จากระบบ AI
                    </div>

                </div>

            </div>


            <div class="kpi-card">

                <div
                    class="kpi-icon kpi-green"
                >
                    ◎
                </div>

                <div>

                    <div class="kpi-label">
                        รอบการคัดแยก
                    </div>

                    <div
                        id="rounds"
                        class="kpi-value"
                    >
                        0
                    </div>

                    <div class="kpi-sub">
                        Sorting Rounds
                    </div>

                </div>

            </div>


            <div class="kpi-card">

                <div
                    class="kpi-icon kpi-blue"
                >
                    ◷
                </div>

                <div>

                    <div class="kpi-label">
                        AI FPS
                    </div>

                    <div
                        id="fps"
                        class="kpi-value"
                    >
                        0
                    </div>

                    <div class="kpi-sub">
                        Camera Performance
                    </div>

                </div>

            </div>


            <div class="kpi-card">

                <div
                    class="kpi-icon kpi-orange"
                >
                    ⚡
                </div>

                <div>

                    <div class="kpi-label">
                        สถานะระบบ
                    </div>

                    <div
                        id="system"
                        class="kpi-value"
                    >
                        ONLINE
                    </div>

                    <div class="kpi-sub">
                        System Status
                    </div>

                </div>

            </div>


        </div>

    </section>


    <h2 class="section-title">
        เมนูด่วน
    </h2>


    <section class="quick-grid">


        <a
            href="/daily"
            class="quick-card"
        >

            <div class="quick-icon">
                ▥
            </div>

            <div class="quick-title">
                รายวัน
            </div>

            <div class="quick-desc">
                Daily Analytics
            </div>

        </a>


        <a
            href="/monthly"
            class="quick-card"
        >

            <div class="quick-icon green">
                ≋
            </div>

            <div class="quick-title">
                รายเดือน
            </div>

            <div class="quick-desc">
                Monthly Analytics
            </div>

        </a>


        <a
            href="/yearly"
            class="quick-card"
        >

            <div class="quick-icon orange">
                ♡
            </div>

            <div class="quick-title">
                รายปี
            </div>

            <div class="quick-desc">
                Yearly Analytics
            </div>

        </a>


        <a
            href="/live"
            class="quick-card"
        >

            <div class="quick-icon">
                ◉
            </div>

            <div class="quick-title">
                Live Camera
            </div>

            <div class="quick-desc">
                ดูกล้อง AI
            </div>

        </a>


    </section>


    <section
        class="panel"
        style="margin-top:25px"
    >

        <div class="panel-title">
            ผลการคัดแยกรอบล่าสุด
        </div>

        <div class="panel-sub">
            Latest AI Sorting Result
        </div>


        <div
            class="table-wrap"
            style="margin-top:20px"
        >

            <table>

                <thead>

                    <tr>

                        <th>
                            รอบ
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

                    </tr>

                </thead>

                <tbody id="latestTable">

                    <tr>

                        <td colspan="6">
                            กำลังโหลดข้อมูล...
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
            await fetch(
                "/api/dashboard"
            );

        const data =
            await response.json();

        const counts =
            data.counts || {};

        const latest =
            data.latest_round || {};


        document.getElementById(
            "total"
        ).textContent =
            Number(
                data.total || 0
            ).toLocaleString();


        document.getElementById(
            "rounds"
        ).textContent =
            Number(
                data.rounds || 0
            ).toLocaleString();


        document.getElementById(
            "fps"
        ).textContent =
            Number(
                latest.avg_fps || 0
            ).toFixed(1);


        const table =
            document.getElementById(
                "latestTable"
            );


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
                    <b>
                        ${data.total || 0}
                    </b>
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
        "home",
        script
    )


# =========================================================
# ANALYTICS PAGE
# =========================================================

def analytics_page(
    title,
    endpoint,
    active,
    description
):

    content = f"""

    <section class="page-title">

        <a
            href="/"
            class="back"
        >
            ← กลับหน้าหลัก
        </a>

        <h1>
            {title}
        </h1>

        <p>
            {description}
        </p>

    </section>


    <section class="panel">

        <div class="panel-title">
            Shrimp Sorting Analytics
        </div>

        <div class="panel-sub">
            จำนวนกุ้งที่ระบบ AI ตรวจพบ
        </div>


        <div class="chart-box">

            <canvas id="chart"></canvas>

        </div>

    </section>


    <section class="panel">

        <div class="panel-title">
            รายละเอียดข้อมูล
        </div>

        <div class="panel-sub">
            Sorting History
        </div>


        <div
            class="table-wrap"
            style="margin-top:20px"
        >

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
            await fetch(
                "{endpoint}"
            );

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
                    <b>
                        ${{row.total}}
                    </b>
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
        document.getElementById(
            "chart"
        );

    const ctx =
        canvas.getContext("2d");


    const width =
        canvas.clientWidth;

    const height =
        400;

    const dpr =
        window.devicePixelRatio || 1;


    canvas.width =
        width * dpr;

    canvas.height =
        height * dpr;


    ctx.scale(
        dpr,
        dpr
    );


    ctx.clearRect(
        0,
        0,
        width,
        height
    );


    if(!analyticsData.length){{

        ctx.fillStyle =
            "#8492a5";

        ctx.font =
            "14px Arial";

        ctx.textAlign =
            "center";

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
            10
        );


    const niceMax =
        Math.ceil(
            maxValue / 10
        ) * 10;


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
            (
                value /
                niceMax
            ) *
            chartHeight;


        ctx.strokeStyle =
            "#e8eef5";

        ctx.beginPath();

        ctx.moveTo(
            padding.left,
            y
        );

        ctx.lineTo(
            width -
            padding.right,
            y
        );

        ctx.stroke();


        ctx.fillStyle =
            "#8a98a9";

        ctx.font =
            "10px Arial";

        ctx.textAlign =
            "right";

        ctx.fillText(
            Math.round(value),
            padding.left - 10,
            y + 4
        );

    }}


    const groupWidth =
        chartWidth /
        analyticsData.length;


    const types = [

        "กุ้งเล็ก",

        "กุ้งกลาง",

        "กุ้งใหญ่",

        "กุ้งป่วย"

    ];


    const colors = [

        "#38b978",

        "#4388ed",

        "#f4a62a",

        "#ee626e"

    ];


    analyticsData.forEach(
        (row, index) => {{

            const center =
                padding.left +
                groupWidth *
                index +
                groupWidth / 2;


            const barWidth =
                Math.min(
                    16,
                    groupWidth / 7
                );


            types.forEach(
                (type, typeIndex) => {{

                    const value =
                        row[type] || 0;


                    const barHeight =
                        value /
                        niceMax *
                        chartHeight;


                    const x =
                        center -
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
                "#8592a4";

            ctx.font =
                "10px Arial";

            ctx.textAlign =
                "center";


            let label =
                row.label;


            if(label.length > 10){{

                label =
                    label.substring(5);

            }}


            ctx.fillText(
                label,
                center,
                height - 22
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

@app.get(
    "/daily",
    response_class=HTMLResponse
)
async def daily_page():

    return analytics_page(

        "รายวัน",

        "/api/analytics/daily",

        "daily",

        "สรุปผลการคัดแยกกุ้งในแต่ละวัน"
    )


# =========================================================
# MONTHLY
# =========================================================

@app.get(
    "/monthly",
    response_class=HTMLResponse
)
async def monthly_page():

    return analytics_page(

        "รายเดือน",

        "/api/analytics/monthly",

        "monthly",

        "สรุปผลการคัดแยกกุ้งในแต่ละเดือน"
    )


# =========================================================
# YEARLY
# =========================================================

@app.get(
    "/yearly",
    response_class=HTMLResponse
)
async def yearly_page():

    return analytics_page(

        "รายปี",

        "/api/analytics/yearly",

        "yearly",

        "สรุปผลการคัดแยกกุ้งในแต่ละปี"
    )


# =========================================================
# LIVE PAGE
# =========================================================

@app.get(
    "/live",
    response_class=HTMLResponse
)
async def live_page():

    content = """

    <section class="page-title">

        <a
            href="/"
            class="back"
        >
            ← กลับหน้าหลัก
        </a>

        <h1>
            Live Camera
        </h1>

        <p>
            ดูภาพจากกล้อง AI แบบเรียลไทม์
        </p>

    </section>


    <section class="live-layout">


        <div class="camera">

            <div
                id="liveBadge"
                class="live-badge"
            >
                <span class="live-dot"></span>
                CAMERA ONLINE
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

                <div
                    style="
                    font-size:55px;
                    margin-bottom:10px;
                    "
                >
                    📷
                </div>

                <div>
                    กำลังรอภาพจากกล้อง AI...
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
                    style="font-size:15px"
                >
                    -
                </div>

            </div>


        </div>

    </section>

    """


    script = r"""

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


        const placeholder =
            document.getElementById(
                "placeholder"
            );


        if(data.online){

            status.textContent =
                "ONLINE";

            status.style.color =
                "#18a66b";

            badge.innerHTML =
                '<span class="live-dot"></span>' +
                'CAMERA ONLINE';

            placeholder.style.display =
                "none";

        }
        else {

            status.textContent =
                "OFFLINE";

            status.style.color =
                "#ed5b69";

            badge.innerHTML =
                '<span class="live-dot" ' +
                'style="background:#ed5b69"></span>' +
                'CAMERA OFFLINE';

            placeholder.style.display =
                "block";

        }


        document.getElementById(
            "liveFps"
        ).textContent =
            Number(
                data.fps || 0
            ).toFixed(1);


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

    const camera =
        document.getElementById(
            "camera"
        );

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
# HEALTH
# =========================================================

@app.get("/api/health")
async def health():

    return {

        "status":
            "ok",

        "rounds":
            len(round_history),

        "live":
            live_status["online"]
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
