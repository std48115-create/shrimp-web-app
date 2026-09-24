from fastapi import FastAPI, Header
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any
from collections import deque
from datetime import datetime
import base64
import os
import uvicorn


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="Shrimp AI Factory",
    version="3.0.0"
)

API_KEY = os.getenv("API_KEY", "change-me")
PORT = int(os.getenv("PORT", "10000"))

SHRIMP_TYPES = [
    "กุ้งเล็ก",
    "กุ้งกลาง",
    "กุ้งใหญ่",
    "กุ้งป่วย"
]


# =========================================================
# MEMORY
# =========================================================

latest_round = None

round_history = deque(maxlen=1000)

live_frame = None
live_ts = None

live_info = {
    "fps": 0,
    "updated_at": None
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
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class LiveReport(BaseModel):
    fps: float = 0
    timestamp: Optional[str] = None
    frame: Optional[str] = None


# =========================================================
# HELPERS
# =========================================================

def clean_counts(counts=None):
    counts = counts or {}

    result = {}

    for shrimp in SHRIMP_TYPES:
        try:
            value = int(counts.get(shrimp, 0))
        except Exception:
            value = 0

        result[shrimp] = max(0, value)

    return result


def total_counts(counts):
    return sum(
        counts.get(shrimp, 0)
        for shrimp in SHRIMP_TYPES
    )


def check_api_key(key):
    return key is not None and key == API_KEY


def decode_frame(data):
    if "," in data:
        data = data.split(",", 1)[1]

    return base64.b64decode(data)


def parse_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    text = str(value).strip()

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except Exception:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            pass

    return None


def round_datetime(item):
    for key in [
        "finished_at",
        "started_at",
        "received_at"
    ]:
        dt = parse_datetime(item.get(key))
        if dt:
            return dt

    return None


def make_round(report):
    counts = clean_counts(report.counts)

    return {
        "round_id": report.round_id,
        "counts": counts,
        "total": total_counts(counts),
        "avg_fps": report.avg_fps,
        "duration": report.duration,
        "frames": report.frames,
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "received_at": datetime.now().isoformat()
    }


# =========================================================
# ANALYTICS
# =========================================================

def analytics(mode):

    buckets = {}

    for item in round_history:

        dt = round_datetime(item)

        if not dt:
            continue

        if mode == "daily":

            key = dt.strftime("%Y-%m-%d")
            label = dt.strftime("%d/%m/%Y")

        elif mode == "monthly":

            key = dt.strftime("%Y-%m")
            label = dt.strftime("%m/%Y")

        else:

            key = dt.strftime("%Y")
            label = dt.strftime("%Y")

        if key not in buckets:

            buckets[key] = {
                "key": key,
                "label": label,
                "counts": {
                    "กุ้งเล็ก": 0,
                    "กุ้งกลาง": 0,
                    "กุ้งใหญ่": 0,
                    "กุ้งป่วย": 0
                },
                "total": 0,
                "rounds": 0
            }

        counts = clean_counts(
            item.get("counts")
        )

        for shrimp in SHRIMP_TYPES:

            buckets[key]["counts"][shrimp] += (
                counts[shrimp]
            )

        buckets[key]["total"] += total_counts(counts)
        buckets[key]["rounds"] += 1

    result = list(buckets.values())

    result.sort(key=lambda x: x["key"])

    return result


# =========================================================
# API
# =========================================================

@app.post("/api/round")
async def receive_round(
    report: RoundReport,
    x_api_key: Optional[str] = Header(default=None)
):

    if not check_api_key(x_api_key):

        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "Invalid API key"
            }
        )

    global latest_round

    data = make_round(report)

    latest_round = data

    round_history.append(data)

    return {
        "ok": True,
        "round": data
    }


@app.post("/api/live")
async def receive_live(
    report: LiveReport,
    x_api_key: Optional[str] = Header(default=None)
):

    if not check_api_key(x_api_key):

        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "Invalid API key"
            }
        )

    global live_frame
    global live_ts

    if report.frame:

        try:
            live_frame = decode_frame(
                report.frame
            )

            live_ts = datetime.now().timestamp()

        except Exception as e:

            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error": str(e)
                }
            )

    live_info["fps"] = report.fps

    live_info["updated_at"] = (
        report.timestamp
        or datetime.now().isoformat()
    )

    return {
        "ok": True
    }


@app.get("/api/dashboard")
async def dashboard_api():

    counts = clean_counts(
        latest_round.get("counts", {})
        if latest_round
        else {}
    )

    return {
        "ok": True,
        "latest_round": latest_round,
        "history_count": len(round_history),
        "counts": counts,
        "total": total_counts(counts)
    }


@app.get("/api/analytics/daily")
async def daily_api():

    return {
        "ok": True,
        "data": analytics("daily")
    }


@app.get("/api/analytics/monthly")
async def monthly_api():

    return {
        "ok": True,
        "data": analytics("monthly")
    }


@app.get("/api/analytics/yearly")
async def yearly_api():

    return {
        "ok": True,
        "data": analytics("yearly")
    }


@app.get("/api/live/status")
async def live_status():

    now = datetime.now().timestamp()

    online = False

    if live_ts:
        online = now - live_ts < 10

    return {
        "ok": True,
        "online": online,
        "fps": live_info.get("fps", 0),
        "updated_at": live_info.get("updated_at")
    }


@app.get("/api/live/frame")
async def get_live_frame():

    if not live_frame:
        return Response(status_code=404)

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
        "ok": True,
        "service": "shrimp-ai-factory",
        "rounds": len(round_history),
        "camera": live_frame is not None
    }


# =========================================================
# PREMIUM CSS
# =========================================================

CSS = """
<style>

/* =========================================================
   LUXURY LIGHT AI FACTORY
   WHITE / ICE BLUE / PREMIUM BLUE
   ========================================================= */

:root {
    --bg: #f4f8fc;
    --bg-soft: #eef6fc;

    --white: #ffffff;
    --white-glass: rgba(255,255,255,.78);

    --text: #142536;
    --text-dark: #0b1c2d;
    --muted: #72869a;
    --muted-light: #9aabba;

    --blue: #1687d9;
    --blue-dark: #0966ad;
    --blue-light: #52b9f5;

    --cyan: #38c6ee;
    --green: #28b887;
    --orange: #f3a43b;
    --red: #e85d68;

    --border: rgba(21,110,166,.11);

    --shadow:
        0 15px 45px rgba(35,94,132,.09);

    --shadow-hover:
        0 25px 65px rgba(35,94,132,.15);
}


/* =========================================================
   RESET
   ========================================================= */

* {
    box-sizing: border-box;
}

html {
    scroll-behavior: smooth;
}

body {

    margin: 0;

    min-height: 100vh;

    color: var(--text);

    font-family:
        Inter,
        "Segoe UI",
        "Noto Sans Thai",
        system-ui,
        sans-serif;

    background:

        radial-gradient(
            circle at 5% 0%,
            rgba(82,185,245,.20),
            transparent 28%
        ),

        radial-gradient(
            circle at 95% 5%,
            rgba(120,195,255,.16),
            transparent 30%
        ),

        radial-gradient(
            circle at 50% 100%,
            rgba(56,198,238,.08),
            transparent 35%
        ),

        linear-gradient(
            135deg,
            #f8fbfe 0%,
            #f1f7fc 45%,
            #f7fbff 100%
        );

}


/* =========================================================
   BACKGROUND GLOW
   ========================================================= */

body::before {

    content: "";

    position: fixed;

    inset: 0;

    pointer-events: none;

    background:

        linear-gradient(
            120deg,
            transparent 0%,
            rgba(255,255,255,.8) 45%,
            transparent 100%
        );

    z-index: -1;
}


/* =========================================================
   LINKS
   ========================================================= */

a {
    color: inherit;
    text-decoration: none;
}


/* =========================================================
   NAVBAR
   ========================================================= */

.navbar {

    position: sticky;

    top: 0;

    z-index: 100;

    height: 76px;

    background:
        rgba(255,255,255,.82);

    backdrop-filter:
        blur(25px);

    -webkit-backdrop-filter:
        blur(25px);

    border-bottom:
        1px solid rgba(22,135,217,.10);

    box-shadow:
        0 5px 30px rgba(35,94,132,.05);
}


.nav-inner {

    width:
        min(
            1450px,
            calc(100% - 40px)
        );

    height: 100%;

    margin: auto;

    display: flex;

    align-items: center;

    justify-content: space-between;

    gap: 20px;
}


/* =========================================================
   LOGO
   ========================================================= */

.logo {

    display: flex;

    align-items: center;

    gap: 12px;
}


.logo-icon {

    width: 46px;
    height: 46px;

    display: grid;

    place-items: center;

    border-radius: 14px;

    font-size: 24px;

    background:

        linear-gradient(
            135deg,
            #e8f7ff,
            #ffffff
        );

    border:
        1px solid rgba(22,135,217,.13);

    box-shadow:

        0 8px 25px
        rgba(22,135,217,.12),

        inset 0 1px 0
        rgba(255,255,255,.9);
}


.logo-small {

    font-size: 9px;

    letter-spacing: 2px;

    font-weight: 900;

    color:
        var(--blue);
}


.logo-title {

    margin-top: 2px;

    font-size: 15px;

    font-weight: 900;

    color:
        var(--text-dark);
}


/* =========================================================
   NAV LINKS
   ========================================================= */

.nav-links {

    display: flex;

    gap: 5px;

    overflow-x: auto;
}


.nav-links a {

    padding:
        10px 14px;

    border-radius: 11px;

    color:
        #70869a;

    font-size: 13px;

    white-space: nowrap;

    transition:
        all .2s ease;
}


.nav-links a:hover {

    color:
        var(--blue);

    background:
        rgba(22,135,217,.06);
}


.nav-links a.active {

    color:
        var(--blue-dark);

    background:

        linear-gradient(
            135deg,
            rgba(82,185,245,.16),
            rgba(255,255,255,.9)
        );

    border:
        1px solid rgba(22,135,217,.12);

    box-shadow:
        0 5px 18px
        rgba(22,135,217,.08);
}


/* =========================================================
   CONTAINER
   ========================================================= */

.container {

    width:
        min(
            1450px,
            calc(100% - 40px)
        );

    margin:
        auto;
}


.page {

    padding:
        38px 0 80px;
}


/* =========================================================
   HERO
   ========================================================= */

.hero {

    position: relative;

    overflow: hidden;

    padding:
        48px;

    border-radius:
        30px;

    background:

        linear-gradient(
            135deg,
            rgba(255,255,255,.96),
            rgba(239,248,255,.91)
        );

    border:
        1px solid
        rgba(22,135,217,.10);

    box-shadow:
        0 25px 70px
        rgba(39,102,140,.10);

    margin-bottom:
        24px;
}


.hero::before {

    content: "";

    position: absolute;

    width: 320px;
    height: 320px;

    right: -100px;
    top: -140px;

    border-radius: 50%;

    background:
        rgba(82,185,245,.16);

    filter:
        blur(10px);
}


.hero::after {

    content: "AI";

    position: absolute;

    right: 35px;
    bottom: -48px;

    font-size: 180px;

    font-weight: 900;

    color:
        rgba(22,135,217,.035);
}


.eyebrow {

    color:
        var(--blue);

    font-size: 10px;

    font-weight: 900;

    letter-spacing:
        2.8px;

    margin-bottom:
        13px;
}


.hero h1 {

    margin: 0;

    font-size:
        clamp(
            34px,
            5vw,
            60px
        );

    line-height:
        1.03;

    letter-spacing:
        -2.5px;

    color:
        var(--text-dark);
}


.hero h1 span {

    background:

        linear-gradient(
            90deg,
            #0b4773,
            #1687d9,
            #52b9f5
        );

    -webkit-background-clip:
        text;

    color:
        transparent;
}


.hero p {

    color:
        var(--muted);

    margin:
        16px 0 0;

    font-size:
        14px;

    max-width:
        650px;

    line-height:
        1.7;
}


.factory-status {

    margin-top:
        25px;

    display:
        inline-flex;

    align-items:
        center;

    gap:
        9px;

    padding:
        9px 14px;

    border-radius:
        999px;

    background:
        rgba(40,184,135,.07);

    border:
        1px solid
        rgba(40,184,135,.14);

    color:
        #15956b;

    font-size:
        11px;

    font-weight:
        700;
}


.pulse {

    width:
        8px;

    height:
        8px;

    border-radius:
        50%;

    background:
        var(--green);

    box-shadow:
        0 0 0 0
        rgba(40,184,135,.35);

    animation:
        pulse 1.8s infinite;
}


@keyframes pulse {

    70% {
        box-shadow:
            0 0 0 9px
            rgba(40,184,135,0);
    }

    100% {
        box-shadow:
            0 0 0 0
            rgba(40,184,135,0);
    }

}


/* =========================================================
   BACK BUTTON
   ========================================================= */

.back-btn {

    display:
        inline-flex;

    align-items:
        center;

    gap:
        8px;

    padding:
        10px 16px;

    margin-bottom:
        20px;

    border-radius:
        12px;

    color:
        #5d7589;

    background:
        rgba(255,255,255,.82);

    border:
        1px solid
        rgba(22,135,217,.10);

    box-shadow:
        0 6px 20px
        rgba(35,94,132,.06);

    font-size:
        13px;

    font-weight:
        650;

    transition:
        all .2s ease;
}


.back-btn:hover {

    color:
        var(--blue);

    transform:
        translateX(-3px);

    border-color:
        rgba(22,135,217,.22);

    box-shadow:
        0 10px 25px
        rgba(22,135,217,.10);
}


/* =========================================================
   KPI
   ========================================================= */

.kpi-grid {

    display:
        grid;

    grid-template-columns:
        repeat(
            4,
            minmax(0,1fr)
        );

    gap:
        15px;

    margin-bottom:
        18px;
}


.kpi {

    position:
        relative;

    overflow:
        hidden;

    padding:
        23px;

    border-radius:
        20px;

    background:
        rgba(255,255,255,.88);

    border:
        1px solid
        rgba(22,135,217,.09);

    box-shadow:
        var(--shadow);

    transition:
        all .25s ease;
}


.kpi:hover {

    transform:
        translateY(-4px);

    box-shadow:
        var(--shadow-hover);

    border-color:
        rgba(22,135,217,.18);
}


.kpi::after {

    content: "";

    position:
        absolute;

    width:
        100px;

    height:
        100px;

    right:
        -50px;

    top:
        -50px;

    border-radius:
        50%;

    background:
        rgba(82,185,245,.10);
}


.kpi-label {

    color:
        #7c91a3;

    font-size:
        11px;

    font-weight:
        700;
}


.kpi-value {

    margin-top:
        8px;

    font-size:
        34px;

    font-weight:
        900;

    letter-spacing:
        -1px;

    color:
        var(--text-dark);
}


.kpi-unit {

    color:
        #9aabba;

    font-size:
        10px;

    margin-top:
        2px;
}


/* =========================================================
   SHRIMP CARDS
   ========================================================= */

.shrimp-grid {

    display:
        grid;

    grid-template-columns:
        repeat(
            4,
            minmax(0,1fr)
        );

    gap:
        15px;

    margin-bottom:
        20px;
}


.shrimp-card {

    position:
        relative;

    overflow:
        hidden;

    min-height:
        160px;

    padding:
        21px;

    border-radius:
        21px;

    background:
        rgba(255,255,255,.91);

    border:
        1px solid
        rgba(22,135,217,.09);

    box-shadow:
        var(--shadow);

    transition:
        all .25s ease;
}


.shrimp-card:hover {

    transform:
        translateY(-5px);

    box-shadow:
        var(--shadow-hover);
}


.shrimp-card::after {

    content: "";

    position:
        absolute;

    width:
        130px;

    height:
        130px;

    right:
        -60px;

    bottom:
        -60px;

    border-radius:
        50%;

    filter:
        blur(25px);
}


.card-green::after {
    background:
        rgba(40,184,135,.12);
}


.card-blue::after {
    background:
        rgba(56,198,238,.13);
}


.card-orange::after {
    background:
        rgba(243,164,59,.12);
}


.card-red::after {
    background:
        rgba(232,93,104,.11);
}


.shrimp-top {

    display:
        flex;

    align-items:
        center;

    justify-content:
        space-between;
}


.shrimp-name {

    font-weight:
        800;

    font-size:
        14px;

    color:
        var(--text-dark);
}


.shrimp-icon {

    width:
        42px;

    height:
        42px;

    border-radius:
        13px;

    display:
        grid;

    place-items:
        center;

    font-size:
        20px;

    background:
        #f5faff;

    border:
        1px solid
        rgba(22,135,217,.08);
}


.shrimp-number {

    margin-top:
        17px;

    font-size:
        34px;

    font-weight:
        900;

    color:
        var(--text-dark);
}


.shrimp-sub {

    color:
        #91a3b2;

    font-size:
        10px;

    margin-top:
        2px;

    letter-spacing:
        .5px;
}


/* =========================================================
   GLASS PANEL
   ========================================================= */

.panel {

    border-radius:
        23px;

    background:
        rgba(255,255,255,.88);

    border:
        1px solid
        rgba(22,135,217,.09);

    box-shadow:
        var(--shadow);

    backdrop-filter:
        blur(20px);
}


.section {

    margin-top:
        22px;
}


.section-head {

    display:
        flex;

    align-items:
        center;

    justify-content:
        space-between;

    margin-bottom:
        13px;
}


.section-head h2 {

    margin:
        0;

    font-size:
        17px;

    color:
        var(--text-dark);
}


/* =========================================================
   CHART
   ========================================================= */

.chart-panel {

    padding:
        25px;
}


.chart-box {

    height:
        390px;
}


.chart-box canvas {

    width:
        100%;

    height:
        100%;

    display:
        block;
}


.chart-legend {

    display:
        flex;

    flex-wrap:
        wrap;

    justify-content:
        center;

    gap:
        20px;

    margin-top:
        10px;
}


.legend {

    display:
        flex;

    align-items:
        center;

    gap:
        7px;

    color:
        #8094a5;

    font-size:
        11px;
}


.legend-dot {

    width:
        9px;

    height:
        9px;

    border-radius:
        50%;
}


.legend-green {
    background:
        #28b887;
}


.legend-blue {
    background:
        #38bde8;
}


.legend-orange {
    background:
        #f3a43b;
}


.legend-red {
    background:
        #e85d68;
}


/* =========================================================
   TABLE
   ========================================================= */

.table-wrap {

    overflow-x:
        auto;
}


table {

    width:
        100%;

    border-collapse:
        collapse;

    min-width:
        750px;
}


th {

    padding:
        15px 18px;

    text-align:
        left;

    color:
        #8397a8;

    font-size:
        10px;

    letter-spacing:
        1px;

    background:
        rgba(238,247,253,.7);
}


td {

    padding:
        16px 18px;

    border-top:
        1px solid
        rgba(22,135,217,.06);

    color:
        #60798d;

    font-size:
        12px;
}


tbody tr {

    transition:
        all .2s ease;
}


tbody tr:hover {

    background:
        rgba(82,185,245,.045);
}


.number {

    font-weight:
        850;

    color:
        var(--text-dark);
}


/* =========================================================
   PAGE TITLE
   ========================================================= */

.page-title {

    margin-bottom:
        22px;
}


.page-title h1 {

    margin:
        0;

    font-size:
        clamp(
            30px,
            4vw,
            48px
        );

    letter-spacing:
        -1.5px;

    color:
        var(--text-dark);
}


.page-title p {

    color:
        var(--muted);

    margin-top:
        9px;

    font-size:
        13px;
}


/* =========================================================
   ACTION CARDS
   ========================================================= */

.actions {

    display:
        grid;

    grid-template-columns:
        repeat(
            4,
            minmax(0,1fr)
        );

    gap:
        14px;

    margin-top:
        20px;
}


.action {

    padding:
        20px;

    border-radius:
        18px;

    background:
        rgba(255,255,255,.88);

    border:
        1px solid
        rgba(22,135,217,.09);

    box-shadow:
        0 10px 35px
        rgba(35,94,132,.06);

    transition:
        all .2s ease;
}


.action:hover {

    transform:
        translateY(-4px);

    border-color:
        rgba(22,135,217,.20);

    box-shadow:
        0 20px 45px
        rgba(35,94,132,.11);
}


.action-icon {

    font-size:
        25px;

    margin-bottom:
        13px;
}


.action strong {

    display:
        block;

    font-size:
        14px;

    color:
        var(--text-dark);
}


.action span {

    display:
        block;

    margin-top:
        5px;

    color:
        #899dac;

    font-size:
        11px;
}


/* =========================================================
   LIVE CAMERA
   ========================================================= */

.live-header {

    display:
        flex;

    align-items:
        center;

    justify-content:
        space-between;

    margin-bottom:
        18px;
}


.live-header h1 {

    margin:
        0;

    font-size:
        clamp(
            30px,
            4vw,
            45px
        );

    color:
        var(--text-dark);
}


.status {

    display:
        flex;

    align-items:
        center;

    gap:
        8px;

    padding:
        10px 14px;

    border-radius:
        999px;

    background:
        rgba(255,255,255,.88);

    border:
        1px solid
        rgba(22,135,217,.10);

    box-shadow:
        0 8px 25px
        rgba(35,94,132,.06);

    color:
        #879aaa;

    font-size:
        11px;
}


.status-dot {

    width:
        8px;

    height:
        8px;

    border-radius:
        50%;

    background:
        #9eacb7;
}


.status.online {

    color:
        #15956b;
}


.status.online .status-dot {

    background:
        var(--green);

    box-shadow:
        0 0 12px
        rgba(40,184,135,.5);

    animation:
        pulse 1.8s infinite;
}


/* =========================================================
   CAMERA
   ========================================================= */

.camera-panel {

    position:
        relative;

    min-height:
        620px;

    display:
        grid;

    place-items:
        center;

    overflow:
        hidden;

    border-radius:
        25px;

    background:
        linear-gradient(
            135deg,
            #edf7fc,
            #ffffff
        );

    border:
        1px solid
        rgba(22,135,217,.10);

    box-shadow:
        0 25px 70px
        rgba(35,94,132,.10);
}


.camera-panel::before {

    content:
        "LIVE AI CAMERA";

    position:
        absolute;

    left:
        20px;

    top:
        18px;

    z-index:
        2;

    padding:
        7px 10px;

    border-radius:
        8px;

    background:
        rgba(255,255,255,.88);

    border:
        1px solid
        rgba(22,135,217,.09);

    color:
        var(--blue);

    font-size:
        9px;

    letter-spacing:
        1.5px;

    box-shadow:
        0 5px 20px
        rgba(35,94,132,.07);
}


.camera-panel img {

    width:
        100%;

    height:
        620px;

    object-fit:
        contain;

    display:
        none;
}


.camera-empty {

    text-align:
        center;

    color:
        #8397a8;
}


.camera-empty-icon {

    font-size:
        50px;

    margin-bottom:
        12px;
}


/* =========================================================
   LIVE STATS
   ========================================================= */

.live-stats {

    display:
        grid;

    grid-template-columns:
        repeat(
            3,
            minmax(0,1fr)
        );

    gap:
        14px;

    margin-top:
        15px;
}


.live-stat {

    padding:
        19px;

    border-radius:
        17px;

    background:
        rgba(255,255,255,.88);

    border:
        1px solid
        rgba(22,135,217,.09);

    box-shadow:
        0 10px 35px
        rgba(35,94,132,.06);
}


.live-stat span {

    display:
        block;

    color:
        #8397a8;

    font-size:
        10px;
}


.live-stat strong {

    display:
        block;

    margin-top:
        7px;

    font-size:
        24px;

    color:
        var(--text-dark);
}


/* =========================================================
   UPDATE ANIMATION
   ========================================================= */

.updated {

    animation:
        updateFlash .5s ease;
}


@keyframes updateFlash {

    0% {
        transform:
            scale(1);

        filter:
            brightness(1);
    }

    45% {
        transform:
            scale(1.06);

        filter:
            brightness(1.15);
    }

    100% {
        transform:
            scale(1);

        filter:
            brightness(1);
    }

}


/* =========================================================
   RESPONSIVE
   ========================================================= */

@media(max-width: 1050px) {

    .kpi-grid,
    .shrimp-grid {

        grid-template-columns:
            repeat(2,1fr);
    }


    .actions {

        grid-template-columns:
            repeat(2,1fr);
    }

}


@media(max-width: 720px) {

    .container,
    .nav-inner {

        width:
            calc(100% - 24px);
    }


    .navbar {

        height:
            auto;

        padding:
            10px 0;
    }


    .nav-inner {

        flex-direction:
            column;

        align-items:
            stretch;
    }


    .nav-links {

        width:
            100%;
    }


    .hero {

        padding:
            28px 22px;
    }


    .kpi-grid,
    .shrimp-grid,
    .actions,
    .live-stats {

        grid-template-columns:
            1fr;
    }


    .chart-panel {

        padding:
            17px;
    }


    .chart-box {

        height:
            320px;
    }


    .live-header {

        flex-direction:
            column;

        align-items:
            flex-start;

        gap:
            14px;
    }


    .camera-panel {

        min-height:
            350px;
    }


    .camera-panel img {

        height:
            350px;
    }

}

</style>
