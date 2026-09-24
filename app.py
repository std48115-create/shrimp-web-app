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

:root {
    --bg: #07111c;
    --bg2: #0c1a29;
    --card: rgba(255,255,255,.075);
    --border: rgba(255,255,255,.12);
    --text: #f5f9fc;
    --muted: #8fa2b5;
    --cyan: #31d7ff;
    --blue: #557cff;
    --green: #35df9b;
    --orange: #ffad4d;
    --red: #ff626f;
}

* {
    box-sizing: border-box;
}

html {
    scroll-behavior: smooth;
}

body {
    margin: 0;
    color: var(--text);
    font-family:
        Inter,
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    background:
        radial-gradient(
            circle at 10% 10%,
            rgba(49,215,255,.12),
            transparent 30%
        ),
        radial-gradient(
            circle at 90% 15%,
            rgba(85,124,255,.13),
            transparent 30%
        ),
        radial-gradient(
            circle at 50% 100%,
            rgba(53,223,155,.08),
            transparent 35%
        ),
        linear-gradient(
            135deg,
            #050c14,
            #091725 45%,
            #06101b
        );

    min-height: 100vh;
}

body:before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;

    background:
        linear-gradient(
            120deg,
            transparent 0%,
            rgba(255,255,255,.025) 50%,
            transparent 100%
        );

    z-index: -1;
}

a {
    color: inherit;
    text-decoration: none;
}

button,
input {
    font: inherit;
}


/* =====================================================
   NAVBAR
   ===================================================== */

.navbar {
    position: sticky;
    top: 0;
    z-index: 100;

    height: 76px;

    background:
        rgba(5,13,22,.78);

    backdrop-filter: blur(22px);

    border-bottom:
        1px solid rgba(255,255,255,.09);
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

.logo {
    display: flex;
    align-items: center;
    gap: 12px;
}

.logo-icon {
    width: 45px;
    height: 45px;

    border-radius: 14px;

    display: grid;
    place-items: center;

    font-size: 24px;

    background:
        linear-gradient(
            135deg,
            #1d4157,
            #0c2435
        );

    border:
        1px solid rgba(49,215,255,.3);

    box-shadow:
        0 0 25px rgba(49,215,255,.14);
}

.logo-small {
    font-size: 9px;
    color: var(--cyan);
    letter-spacing: 2px;
    font-weight: 800;
}

.logo-title {
    font-size: 15px;
    font-weight: 850;
}

.nav-links {
    display: flex;
    gap: 5px;
    overflow-x: auto;
}

.nav-links a {
    padding: 10px 14px;
    border-radius: 11px;

    color: #91a3b5;

    font-size: 13px;
    white-space: nowrap;

    transition: .2s;
}

.nav-links a:hover {
    color: white;
    background: rgba(255,255,255,.07);
}

.nav-links a.active {
    color: white;

    background:
        linear-gradient(
            135deg,
            rgba(49,215,255,.18),
            rgba(85,124,255,.16)
        );

    border:
        1px solid rgba(49,215,255,.18);

    box-shadow:
        0 0 20px rgba(49,215,255,.08);
}


/* =====================================================
   CONTAINER
   ===================================================== */

.container {
    width:
        min(
            1450px,
            calc(100% - 40px)
        );

    margin: auto;
}

.page {
    padding: 38px 0 80px;
}


/* =====================================================
   GLOW
   ===================================================== */

.glow {
    position: fixed;
    width: 420px;
    height: 420px;

    border-radius: 50%;

    background:
        rgba(49,215,255,.055);

    filter: blur(90px);

    pointer-events: none;
    z-index: -1;
}

.glow.one {
    top: 120px;
    left: -180px;
}

.glow.two {
    right: -200px;
    top: 420px;

    background:
        rgba(85,124,255,.07);
}


/* =====================================================
   HERO
   ===================================================== */

.hero {
    position: relative;
    overflow: hidden;

    padding: 42px;

    border-radius: 30px;

    background:
        linear-gradient(
            135deg,
            rgba(255,255,255,.10),
            rgba(255,255,255,.035)
        );

    border:
        1px solid rgba(255,255,255,.13);

    box-shadow:
        0 30px 100px rgba(0,0,0,.24);

    backdrop-filter: blur(25px);

    margin-bottom: 24px;
}

.hero:after {
    content: "AI";
    position: absolute;

    right: 35px;
    bottom: -35px;

    font-size: 180px;
    font-weight: 900;

    color: rgba(49,215,255,.035);
}

.eyebrow {
    color: var(--cyan);

    font-size: 10px;
    font-weight: 900;

    letter-spacing: 2.5px;

    margin-bottom: 12px;
}

.hero h1 {
    margin: 0;

    font-size:
        clamp(
            32px,
            5vw,
            58px
        );

    line-height: 1;

    letter-spacing: -2px;
}

.hero h1 span {
    background:
        linear-gradient(
            90deg,
            #ffffff,
            #31d7ff,
            #7890ff
        );

    -webkit-background-clip: text;
    color: transparent;
}

.hero p {
    color: var(--muted);

    margin:
        15px 0 0;

    font-size: 14px;
}

.factory-status {
    margin-top: 25px;

    display: inline-flex;
    align-items: center;
    gap: 9px;

    padding: 9px 13px;

    border-radius: 999px;

    background:
        rgba(53,223,155,.08);

    border:
        1px solid rgba(53,223,155,.16);

    color: #8fe9c5;

    font-size: 12px;
}

.pulse {
    width: 8px;
    height: 8px;

    border-radius: 50%;

    background: var(--green);

    box-shadow:
        0 0 0 0 rgba(53,223,155,.5);

    animation:
        pulse 1.8s infinite;
}

@keyframes pulse {

    70% {
        box-shadow:
            0 0 0 9px rgba(53,223,155,0);
    }

    100% {
        box-shadow:
            0 0 0 0 rgba(53,223,155,0);
    }

}


/* =====================================================
   BACK BUTTON
   ===================================================== */

.back-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;

    padding: 10px 15px;

    margin-bottom: 20px;

    border-radius: 12px;

    color: #b5c3cf;

    background:
        rgba(255,255,255,.055);

    border:
        1px solid rgba(255,255,255,.10);

    font-size: 13px;

    transition: .2s;
}

.back-btn:hover {
    color: white;

    transform: translateX(-3px);

    background:
        rgba(49,215,255,.10);

    border-color:
        rgba(49,215,255,.25);
}


/* =====================================================
   KPI
   ===================================================== */

.kpi-grid {
    display: grid;

    grid-template-columns:
        repeat(
            4,
            minmax(0,1fr)
        );

    gap: 15px;

    margin-bottom: 18px;
}

.kpi {
    position: relative;
    overflow: hidden;

    padding: 23px;

    border-radius: 20px;

    background:
        linear-gradient(
            145deg,
            rgba(255,255,255,.09),
            rgba(255,255,255,.035)
        );

    border:
        1px solid rgba(255,255,255,.11);

    box-shadow:
        0 18px 50px rgba(0,0,0,.16);

    backdrop-filter: blur(20px);

    transition:
        transform .25s,
        border .25s;
}

.kpi:hover {
    transform: translateY(-4px);

    border-color:
        rgba(49,215,255,.25);
}

.kpi-label {
    color: #8194a7;

    font-size: 11px;
    font-weight: 700;
}

.kpi-value {
    margin-top: 8px;

    font-size: 34px;
    font-weight: 900;

    letter-spacing: -1px;
}

.kpi-unit {
    color: #71879a;
    font-size: 12px;
}


/* =====================================================
   SHRIMP CARDS
   ===================================================== */

.shrimp-grid {
    display: grid;

    grid-template-columns:
        repeat(
            4,
            minmax(0,1fr)
        );

    gap: 15px;

    margin-bottom: 20px;
}

.shrimp-card {
    position: relative;
    overflow: hidden;

    min-height: 160px;

    padding: 21px;

    border-radius: 21px;

    background:
        rgba(255,255,255,.065);

    border:
        1px solid rgba(255,255,255,.10);

    backdrop-filter: blur(20px);

    transition:
        transform .25s,
        box-shadow .25s;
}

.shrimp-card:hover {
    transform: translateY(-5px);
}

.shrimp-card:after {
    content: "";

    position: absolute;

    width: 130px;
    height: 130px;

    right: -60px;
    bottom: -60px;

    border-radius: 50%;

    filter: blur(35px);
}

.card-green:after {
    background: rgba(53,223,155,.16);
}

.card-blue:after {
    background: rgba(49,215,255,.16);
}

.card-orange:after {
    background: rgba(255,173,77,.16);
}

.card-red:after {
    background: rgba(255,98,111,.16);
}

.shrimp-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.shrimp-name {
    font-weight: 800;
    font-size: 14px;
}

.shrimp-icon {
    width: 42px;
    height: 42px;

    border-radius: 13px;

    display: grid;
    place-items: center;

    font-size: 21px;

    background:
        rgba(255,255,255,.07);

    border:
        1px solid rgba(255,255,255,.10);
}

.shrimp-number {
    margin-top: 17px;

    font-size: 34px;
    font-weight: 900;
}

.shrimp-sub {
    color: #75899a;

    font-size: 11px;

    margin-top: 2px;
}


/* =====================================================
   GLASS PANEL
   ===================================================== */

.panel {
    border-radius: 23px;

    background:
        linear-gradient(
            145deg,
            rgba(255,255,255,.075),
            rgba(255,255,255,.035)
        );

    border:
        1px solid rgba(255,255,255,.10);

    box-shadow:
        0 20px 70px rgba(0,0,0,.15);

    backdrop-filter: blur(20px);
}

.section {
    margin-top: 22px;
}

.section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;

    margin-bottom: 13px;
}

.section-head h2 {
    margin: 0;

    font-size: 17px;
}


/* =====================================================
   CHART
   ===================================================== */

.chart-panel {
    padding: 25px;
}

.chart-box {
    height: 390px;
}

.chart-box canvas {
    width: 100%;
    height: 100%;
    display: block;
}

.chart-legend {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;

    gap: 20px;

    margin-top: 10px;
}

.legend {
    display: flex;
    align-items: center;
    gap: 7px;

    color: #8193a3;

    font-size: 11px;
}

.legend-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
}

.legend-green {
    background: #35df9b;
}

.legend-blue {
    background: #31d7ff;
}

.legend-orange {
    background: #ffad4d;
}

.legend-red {
    background: #ff626f;
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

    min-width: 750px;
}

th {
    padding: 15px 18px;

    text-align: left;

    color: #718598;

    font-size: 10px;

    letter-spacing: 1px;

    background:
        rgba(255,255,255,.025);
}

td {
    padding: 16px 18px;

    border-top:
        1px solid rgba(255,255,255,.055);

    color: #b9c6d1;

    font-size: 12px;
}

tbody tr {
    transition: .2s;
}

tbody tr:hover {
    background:
        rgba(49,215,255,.035);
}

.number {
    font-weight: 850;
    color: white;
}


/* =====================================================
   ANALYTICS TITLE
   ===================================================== */

.page-title {
    margin-bottom: 22px;
}

.page-title h1 {
    margin: 0;

    font-size:
        clamp(
            30px,
            4vw,
            48px
        );

    letter-spacing: -1.5px;
}

.page-title p {
    color: var(--muted);

    margin-top: 9px;

    font-size: 13px;
}


/* =====================================================
   ACTION CARDS
   ===================================================== */

.actions {
    display: grid;

    grid-template-columns:
        repeat(
            4,
            minmax(0,1fr)
        );

    gap: 14px;

    margin-top: 20px;
}

.action {
    padding: 20px;

    border-radius: 18px;

    background:
        rgba(255,255,255,.055);

    border:
        1px solid rgba(255,255,255,.09);

    transition: .2s;
}

.action:hover {
    transform: translateY(-4px);

    border-color:
        rgba(49,215,255,.25);

    background:
        rgba(49,215,255,.07);
}

.action-icon {
    font-size: 25px;
    margin-bottom: 13px;
}

.action strong {
    display: block;
    font-size: 14px;
}

.action span {
    display: block;

    margin-top: 5px;

    color: #788c9e;

    font-size: 11px;
}


/* =====================================================
   LIVE CAMERA
   ===================================================== */

.live-header {
    display: flex;
    align-items: center;
    justify-content: space-between;

    margin-bottom: 18px;
}

.live-header h1 {
    margin: 0;

    font-size:
        clamp(
            30px,
            4vw,
            45px
        );
}

.status {
    display: flex;
    align-items: center;
    gap: 8px;

    padding: 10px 14px;

    border-radius: 999px;

    background:
        rgba(255,255,255,.06);

    border:
        1px solid rgba(255,255,255,.10);

    color: #8498aa;

    font-size: 11px;
}

.status-dot {
    width: 8px;
    height: 8px;

    border-radius: 50%;

    background: #65727d;
}

.status.online {
    color: #83e7bd;
}

.status.online .status-dot {
    background: var(--green);

    box-shadow:
        0 0 14px var(--green);

    animation: pulse 1.8s infinite;
}

.camera-panel {
    position: relative;

    min-height: 620px;

    display: grid;
    place-items: center;

    overflow: hidden;

    border-radius: 25px;

    background:
        #02070c;

    border:
        1px solid rgba(255,255,255,.11);

    box-shadow:
        0 30px 100px rgba(0,0,0,.35);
}

.camera-panel:before {
    content: "LIVE AI CAMERA";

    position: absolute;

    left: 20px;
    top: 18px;

    z-index: 2;

    padding: 7px 10px;

    border-radius: 8px;

    background:
        rgba(0,0,0,.45);

    border:
        1px solid rgba(255,255,255,.08);

    color: #91a7b9;

    font-size: 9px;

    letter-spacing: 1.5px;
}

.camera-panel img {
    width: 100%;
    height: 620px;

    object-fit: contain;

    display: none;
}

.camera-empty {
    text-align: center;
    color: #687b8c;
}

.camera-empty-icon {
    font-size: 50px;
    margin-bottom: 12px;
}

.live-stats {
    display: grid;

    grid-template-columns:
        repeat(
            3,
            minmax(0,1fr)
        );

    gap: 14px;

    margin-top: 15px;
}

.live-stat {
    padding: 19px;

    border-radius: 17px;

    background:
        rgba(255,255,255,.055);

    border:
        1px solid rgba(255,255,255,.09);
}

.live-stat span {
    display: block;

    color: #72879a;

    font-size: 10px;
}

.live-stat strong {
    display: block;

    margin-top: 7px;

    font-size: 24px;
}


/* =====================================================
   ANIMATION UPDATE
   ===================================================== */

.updated {
    animation:
        updateFlash .5s ease;
}

@keyframes updateFlash {

    0% {
        transform: scale(1);
        filter: brightness(1);
    }

    45% {
        transform: scale(1.06);
        filter: brightness(1.45);
    }

    100% {
        transform: scale(1);
        filter: brightness(1);
    }

}


/* =====================================================
   RESPONSIVE
   ===================================================== */

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
        height: auto;
        padding: 10px 0;
    }

    .nav-inner {
        flex-direction: column;
        align-items: stretch;
    }

    .nav-links {
        width: 100%;
    }

    .hero {
        padding: 28px 22px;
    }

    .kpi-grid,
    .shrimp-grid,
    .actions,
    .live-stats {
        grid-template-columns: 1fr;
    }

    .chart-panel {
        padding: 17px;
    }

    .chart-box {
        height: 320px;
    }

    .live-header {
        flex-direction: column;
        align-items: flex-start;
        gap: 14px;
    }

    .camera-panel {
        min-height: 350px;
    }

    .camera-panel img {
        height: 350px;
    }

}

</style>
"""


# =========================================================
# NAVBAR
# =========================================================

def navbar(active):

    links = [
        ("/", "Dashboard", "dashboard"),
        ("/daily", "📅 รายวัน", "daily"),
        ("/monthly", "🗓️ รายเดือน", "monthly"),
        ("/yearly", "📈 รายปี", "yearly"),
        ("/live", "📷 กล้อง AI", "live")
    ]

    html = """
    <nav class="navbar">

        <div class="nav-inner">

            <a href="/" class="logo">

                <div class="logo-icon">
                    🦐
                </div>

                <div>
                    <div class="logo-small">
                        AI FACTORY CONTROL
                    </div>

                    <div class="logo-title">
                        Shrimp Vision
                    </div>
                </div>

            </a>

            <div class="nav-links">
    """

    for href, text, key in links:

        cls = "active" if key == active else ""

        html += (
            '<a href="'
            + href
            + '" class="'
            + cls
            + '">'
            + text
            + "</a>"
        )

    html += """
            </div>

        </div>

    </nav>
    """

    return html


# =========================================================
# PAGE WRAPPER
# =========================================================

def page_html(title, body, active, script=""):

    return (
        "<!DOCTYPE html>"
        "<html lang='th'>"
        "<head>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' "
        "content='width=device-width,initial-scale=1.0'>"
        "<title>"
        + title
        + " | Shrimp Vision"
        + "</title>"
        + CSS
        + "</head>"
        "<body>"

        "<div class='glow one'></div>"
        "<div class='glow two'></div>"

        + navbar(active)

        + body

        + script

        + "</body>"
        "</html>"
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard():

    body = """
    <main class="container">

        <div class="page">

            <section class="hero">

                <div class="eyebrow">
                    AI SHRIMP SORTING FACTORY
                </div>

                <h1>
                    <span>Shrimp Vision</span>
                    Control Center
                </h1>

                <p>
                    ระบบควบคุมและวิเคราะห์
                    การคัดแยกกุ้งด้วย AI
                    แบบ Real-time
                </p>

                <div class="factory-status">

                    <span class="pulse"></span>

                    AI SYSTEM ONLINE

                </div>

            </section>


            <section class="kpi-grid">

                <div class="kpi">

                    <div class="kpi-label">
                        กุ้งทั้งหมดในรอบล่าสุด
                    </div>

                    <div
                        class="kpi-value"
                        id="total"
                    >
                        0
                    </div>

                    <div class="kpi-unit">
                        SHRIMP / ROUND
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

                    <div class="kpi-unit">
                        AI PROCESSING
                    </div>

                </div>


                <div class="kpi">

                    <div class="kpi-label">
                        ระยะเวลารอบล่าสุด
                    </div>

                    <div
                        class="kpi-value"
                        id="duration"
                    >
                        0s
                    </div>

                    <div class="kpi-unit">
                        PROCESSING TIME
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

                    <div class="kpi-unit">
                        TOTAL ROUNDS
                    </div>

                </div>

            </section>


            <section class="shrimp-grid">

                <div class="shrimp-card card-green">

                    <div class="shrimp-top">

                        <div class="shrimp-name">
                            🦐 กุ้งเล็ก
                        </div>

                        <div class="shrimp-icon">
                            🟢
                        </div>

                    </div>

                    <div
                        class="shrimp-number"
                        id="small"
                    >
                        0
                    </div>

                    <div class="shrimp-sub">
                        SMALL SHRIMP
                    </div>

                </div>


                <div class="shrimp-card card-blue">

                    <div class="shrimp-top">

                        <div class="shrimp-name">
                            🦐 กุ้งกลาง
                        </div>

                        <div class="shrimp-icon">
                            🔵
                        </div>

                    </div>

                    <div
                        class="shrimp-number"
                        id="medium"
                    >
                        0
                    </div>

                    <div class="shrimp-sub">
                        MEDIUM SHRIMP
                    </div>

                </div>


                <div class="shrimp-card card-orange">

                    <div class="shrimp-top">

                        <div class="shrimp-name">
                            🦐 กุ้งใหญ่
                        </div>

                        <div class="shrimp-icon">
                            🟠
                        </div>

                    </div>

                    <div
                        class="shrimp-number"
                        id="large"
                    >
                        0
                    </div>

                    <div class="shrimp-sub">
                        LARGE SHRIMP
                    </div>

                </div>


                <div class="shrimp-card card-red">

                    <div class="shrimp-top">

                        <div class="shrimp-name">
                            ⚠️ กุ้งป่วย
                        </div>

                        <div class="shrimp-icon">
                            🔴
                        </div>

                    </div>

                    <div
                        class="shrimp-number"
                        id="sick"
                    >
                        0
                    </div>

                    <div class="shrimp-sub">
                        SICK SHRIMP
                    </div>

                </div>

            </section>


            <section class="panel chart-panel">

                <div class="section-head">

                    <div>

                        <h2>
                            📊 ผลการคัดแยก
                        </h2>

                        <div
                            style="
                            color:#72879a;
                            font-size:11px;
                            margin-top:5px;
                            "
                        >
                            ผลการตรวจจับจากรอบล่าสุด
                        </div>

                    </div>

                </div>

                <div class="chart-box">

                    <canvas id="dashboardChart"></canvas>

                </div>

                <div class="chart-legend">

                    <div class="legend">
                        <span class="legend-dot legend-green"></span>
                        กุ้งเล็ก
                    </div>

                    <div class="legend">
                        <span class="legend-dot legend-blue"></span>
                        กุ้งกลาง
                    </div>

                    <div class="legend">
                        <span class="legend-dot legend-orange"></span>
                        กุ้งใหญ่
                    </div>

                    <div class="legend">
                        <span class="legend-dot legend-red"></span>
                        กุ้งป่วย
                    </div>

                </div>

            </section>


            <section class="actions">

                <a class="action" href="/daily">

                    <div class="action-icon">
                        📅
                    </div>

                    <strong>
                        สรุปรายวัน
                    </strong>

                    <span>
                        วิเคราะห์ผลการคัดแยกรายวัน
                    </span>

                </a>


                <a class="action" href="/monthly">

                    <div class="action-icon">
                        🗓️
                    </div>

                    <strong>
                        สรุปรายเดือน
                    </strong>

                    <span>
                        วิเคราะห์ผลการคัดแยกรายเดือน
                    </span>

                </a>


                <a class="action" href="/yearly">

                    <div class="action-icon">
                        📈
                    </div>

                    <strong>
                        สรุปรายปี
                    </strong>

                    <span>
                        วิเคราะห์ผลการคัดแยกรายปี
                    </span>

                </a>


                <a class="action" href="/live">

                    <div class="action-icon">
                        📷
                    </div>

                    <strong>
                        Live Camera
                    </strong>

                    <span>
                        ดูกล้อง AI แบบ Real-time
                    </span>

                </a>

            </section>


            <section class="section">

                <div class="section-head">

                    <h2>
                        🧾 ประวัติการคัดแยก
                    </h2>

                </div>


                <div class="panel">

                    <div class="table-wrap">

                        <table>

                            <thead>

                                <tr>
                                    <th>รอบ</th>
                                    <th>เริ่มต้น</th>
                                    <th>สิ้นสุด</th>
                                    <th>FPS</th>
                                    <th>Frames</th>
                                    <th>จำนวน</th>
                                </tr>

                            </thead>

                            <tbody id="history">
                            </tbody>

                        </table>

                    </div>

                </div>

            </section>

        </div>

    </main>
    """


    script = """
    <script>

    let lastValues = [];


    async function loadDashboard() {

        try {

            const res =
                await fetch(
                    "/api/dashboard",
                    {cache:"no-store"}
                );

            const data =
                await res.json();

            const c =
                data.counts || {};

            const latest =
                data.latest_round;


            updateValue(
                "total",
                data.total || 0
            );

            updateValue(
                "rounds",
                data.history_count || 0
            );

            updateValue(
                "small",
                c["กุ้งเล็ก"] || 0
            );

            updateValue(
                "medium",
                c["กุ้งกลาง"] || 0
            );

            updateValue(
                "large",
                c["กุ้งใหญ่"] || 0
            );

            updateValue(
                "sick",
                c["กุ้งป่วย"] || 0
            );


            if (latest) {

                updateValue(
                    "fps",
                    Number(
                        latest.avg_fps || 0
                    ).toFixed(1)
                );

                updateValue(
                    "duration",
                    Number(
                        latest.duration || 0
                    ).toFixed(1)
                    + "s"
                );


                drawDashboardChart(c);


                const history =
                    document.getElementById(
                        "history"
                    );


                history.innerHTML = `

                    <tr>

                        <td>
                            <span class="number">
                                #${latest.round_id || "-"}
                            </span>
                        </td>

                        <td>
                            ${latest.started_at || "-"}
                        </td>

                        <td>
                            ${latest.finished_at || "-"}
                        </td>

                        <td>
                            ${Number(
                                latest.avg_fps || 0
                            ).toFixed(1)}
                        </td>

                        <td>
                            ${latest.frames || 0}
                        </td>

                        <td>
                            <span class="number">
                                ${latest.total || 0}
                            </span>
                        </td>

                    </tr>

                `;

            }

        } catch (e) {

            console.error(e);

        }

    }


    function updateValue(id, value) {

        const el =
            document.getElementById(id);

        if (!el) return;


        if (
            el.textContent != String(value)
        ) {

            el.classList.remove(
                "updated"
            );

            void el.offsetWidth;

            el.classList.add(
                "updated"
            );

        }

        el.textContent = value;

    }


    function drawDashboardChart(counts) {

        const canvas =
            document.getElementById(
                "dashboardChart"
            );

        if (!canvas) return;


        const rect =
            canvas.getBoundingClientRect();

        const dpr =
            window.devicePixelRatio || 1;

        canvas.width =
            rect.width * dpr;

        canvas.height =
            rect.height * dpr;

        const ctx =
            canvas.getContext("2d");

        ctx.setTransform(
            dpr,
            0,
            0,
            dpr,
            0,
            0
        );


        const width = rect.width;
        const height = rect.height;


        ctx.clearRect(
            0,
            0,
            width,
            height
        );


        const names = [
            "กุ้งเล็ก",
            "กุ้งกลาง",
            "กุ้งใหญ่",
            "กุ้งป่วย"
        ];

        const colors = [
            "#35df9b",
            "#31d7ff",
            "#ffad4d",
            "#ff626f"
        ];


        const values = names.map(
            n => Number(
                counts[n] || 0
            )
        );


        const max =
            Math.max(
                10,
                ...values
            ) * 1.2;


        const baseY =
            height - 50;

        const chartHeight =
            height - 90;


        const groupWidth =
            width / values.length;

        const barWidth =
            Math.min(
                90,
                groupWidth * .5
            );


        values.forEach(
            function(value, i) {

                const barHeight =
                    value / max *
                    chartHeight;

                const x =
                    groupWidth * i
                    + groupWidth / 2
                    - barWidth / 2;

                const y =
                    baseY - barHeight;


                const gradient =
                    ctx.createLinearGradient(
                        0,
                        y,
                        0,
                        baseY
                    );

                gradient.addColorStop(
                    0,
                    colors[i]
                );

                gradient.addColorStop(
                    1,
                    "rgba(255,255,255,.04)"
                );


                ctx.fillStyle =
                    gradient;


                ctx.beginPath();


                if (
                    ctx.roundRect
                ) {

                    ctx.roundRect(
                        x,
                        y,
                        barWidth,
                        barHeight,
                        10
                    );

                } else {

                    ctx.rect(
                        x,
                        y,
                        barWidth,
                        barHeight
                    );

                }


                ctx.fill();


                ctx.fillStyle =
                    "#ffffff";

                ctx.font =
                    "bold 14px Arial";

                ctx.textAlign =
                    "center";

                ctx.fillText(
                    value,
                    x + barWidth / 2,
                    y - 10
                );


                ctx.fillStyle =
                    "#8094a6";

                ctx.font =
                    "12px Arial";

                ctx.fillText(
                    names[i],
                    x + barWidth / 2,
                    height - 20
                );

            }
        );

    }


    loadDashboard();


    setInterval(
        loadDashboard,
        5000
    );


    window.addEventListener(
        "resize",
        loadDashboard
    );

    </script>
    """


    return HTMLResponse(
        page_html(
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
    active
):

    body = """
    <main class="container">

        <div class="page">

            <a
                href="/"
                class="back-btn"
            >
                ← กลับ Dashboard
            </a>


            <div class="page-title">

                <div class="eyebrow">
                    SHRIMP ANALYTICS
                </div>

                <h1>
                    TITLE_HERE
                </h1>

                <p>
                    SUBTITLE_HERE
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
                        กุ้งใหญ่ + กุ้งป่วย
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
                            📊 แผนภูมิแท่ง
                        </h2>

                        <div
                            style="
                            color:#72879a;
                            font-size:11px;
                            margin-top:5px;
                            "
                        >
                            จำนวนกุ้งแยกตามช่วงเวลา
                        </div>

                    </div>

                </div>


                <div class="chart-box">

                    <canvas id="chart"></canvas>

                </div>


                <div class="chart-legend">

                    <div class="legend">
                        <span class="legend-dot legend-green"></span>
                        กุ้งเล็ก
                    </div>

                    <div class="legend">
                        <span class="legend-dot legend-blue"></span>
                        กุ้งกลาง
                    </div>

                    <div class="legend">
                        <span class="legend-dot legend-orange"></span>
                        กุ้งใหญ่
                    </div>

                    <div class="legend">
                        <span class="legend-dot legend-red"></span>
                        กุ้งป่วย
                    </div>

                </div>

            </section>


            <section class="section">

                <div class="section-head">

                    <h2>
                        🧾 ตารางข้อมูล
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

                            <tbody id="table">
                            </tbody>

                        </table>

                    </div>

                </div>

            </section>

        </div>

    </main>
    """


    body = body.replace(
        "TITLE_HERE",
        title
    )

    body = body.replace(
        "SUBTITLE_HERE",
        subtitle
    )


    script = """
    <script>

    const endpoint =
        "ENDPOINT_HERE";

    let chartData = [];


    async function loadData() {

        try {

            const res =
                await fetch(
                    endpoint,
                    {cache:"no-store"}
                );

            const result =
                await res.json();

            chartData =
                result.data || [];


            updateSummary(
                chartData
            );

            renderTable(
                chartData
            );

            drawChart(
                chartData
            );

        } catch (e) {

            console.error(e);

        }

    }


    function updateSummary(data) {

        let total = 0;
        let small = 0;
        let medium = 0;
        let other = 0;


        data.forEach(
            function(item) {

                const c =
                    item.counts || {};

                small +=
                    Number(
                        c["กุ้งเล็ก"] || 0
                    );

                medium +=
                    Number(
                        c["กุ้งกลาง"] || 0
                    );

                other +=
                    Number(
                        c["กุ้งใหญ่"] || 0
                    );

                other +=
                    Number(
                        c["กุ้งป่วย"] || 0
                    );

                total +=
                    Number(
                        item.total || 0
                    );

            }
        );


        document.getElementById(
            "total"
        ).textContent = total;


        document.getElementById(
            "small"
        ).textContent = small;


        document.getElementById(
            "medium"
        ).textContent = medium;


        document.getElementById(
            "other"
        ).textContent = other;

    }


    function renderTable(data) {

        const table =
            document.getElementById(
                "table"
            );


        table.innerHTML = "";


        if (!data.length) {

            table.innerHTML = `

                <tr>

                    <td
                        colspan="7"
                        style="
                        text-align:center;
                        padding:45px;
                        color:#72879a;
                        "
                    >
                        ยังไม่มีข้อมูล
                    </td>

                </tr>

            `;

            return;

        }


        data
            .slice()
            .reverse()
            .forEach(
                function(item) {

                    const c =
                        item.counts || {};


                    const row =
                        document.createElement(
                            "tr"
                        );


                    row.innerHTML = `

                        <td>
                            <span class="number">
                                ${item.label || "-"}
                            </span>
                        </td>

                        <td>
                            ${c["กุ้งเล็ก"] || 0}
                        </td>

                        <td>
                            ${c["กุ้งกลาง"] || 0}
                        </td>

                        <td>
                            ${c["กุ้งใหญ่"] || 0}
                        </td>

                        <td>
                            ${c["กุ้งป่วย"] || 0}
                        </td>

                        <td>
                            <span class="number">
                                ${item.total || 0}
                            </span>
                        </td>

                        <td>
                            ${item.rounds || 0}
                        </td>

                    `;


                    table.appendChild(
                        row
                    );

                }
            );

    }


    function drawChart(data) {

        const canvas =
            document.getElementById(
                "chart"
            );

        if (!canvas) return;


        const rect =
            canvas.getBoundingClientRect();

        const dpr =
            window.devicePixelRatio || 1;


        canvas.width =
            rect.width * dpr;

        canvas.height =
            rect.height * dpr;


        const ctx =
            canvas.getContext("2d");


        ctx.setTransform(
            dpr,
            0,
            0,
            dpr,
            0,
            0
        );


        const width = rect.width;
        const height = rect.height;


        ctx.clearRect(
            0,
            0,
            width,
            height
        );


        if (!data.length) {

            ctx.fillStyle =
                "#72879a";

            ctx.font =
                "14px Arial";

            ctx.textAlign =
                "center";

            ctx.fillText(
                "ยังไม่มีข้อมูลสำหรับกราฟ",
                width / 2,
                height / 2
            );

            return;

        }


        const keys = [
            "กุ้งเล็ก",
            "กุ้งกลาง",
            "กุ้งใหญ่",
            "กุ้งป่วย"
        ];


        const colors = [
            "#35df9b",
            "#31d7ff",
            "#ffad4d",
            "#ff626f"
        ];


        let max = 10;


        data.forEach(
            function(item) {

                const c =
                    item.counts || {};

                keys.forEach(
                    function(key) {

                        max = Math.max(
                            max,
                            Number(
                                c[key] || 0
                            )
                        );

                    }
                );

            }
        );


        max =
            Math.ceil(
                max * 1.2
            );


        const left = 55;
        const right = 20;
        const top = 25;
        const bottom = 55;


        const chartWidth =
            width - left - right;

        const chartHeight =
            height - top - bottom;


        const groupWidth =
            chartWidth / data.length;


        const barWidth =
            Math.max(
                5,
                Math.min(
                    30,
                    groupWidth *
                    .68 /
                    keys.length
                )
            );


        data.forEach(
            function(item, index) {

                const center =
                    left
                    + index *
                    groupWidth
                    + groupWidth / 2;


                keys.forEach(
                    function(key, j) {

                        const value =
                            Number(
                                (
                                    item.counts
                                    || {}
                                )[key] || 0
                            );


                        const barHeight =
                            value / max
                            * chartHeight;


                        const x =
                            center
                            -
                            (
                                keys.length
                                *
                                barWidth
                            )
                            / 2
                            +
                            j * barWidth;


                        const y =
                            top
                            + chartHeight
                            - barHeight;


                        ctx.fillStyle =
                            colors[j];


                        ctx.beginPath();


                        if (
                            ctx.roundRect
                        ) {

                            ctx.roundRect(
                                x + 2,
                                y,
                                barWidth - 4,
                                barHeight,
                                5
                            );

                        } else {

                            ctx.rect(
                                x + 2,
                                y,
                                barWidth - 4,
                                barHeight
                            );

                        }


                        ctx.fill();


                        if (
                            data.length <= 15
                            && value > 0
                        ) {

                            ctx.fillStyle =
                                "#a9b8c5";

                            ctx.font =
                                "10px Arial";

                            ctx.textAlign =
                                "center";

                            ctx.fillText(
                                value,
                                x + barWidth / 2,
                                y - 5
                            );

                        }

                    }
                );


                if (
                    data.length <= 25
                    ||
                    index % 2 === 0
                ) {

                    ctx.fillStyle =
                        "#778b9d";

                    ctx.font =
                        "10px Arial";

                    ctx.textAlign =
                        "center";

                    ctx.fillText(
                        item.label || "",
                        center,
                        height - 20
                    );

                }

            }
        );

    }


    loadData();


    setInterval(
        loadData,
        5000
    );


    window.addEventListener(
        "resize",
        function() {

            drawChart(
                chartData
            );

        }
    );

    </script>
    """


    script = script.replace(
        "ENDPOINT_HERE",
        endpoint
    )


    return HTMLResponse(
        page_html(
            title,
            body,
            active,
            script
        )
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
        "สรุปรายวัน",
        "ดูผลการคัดแยกกุ้งในแต่ละวัน",
        "/api/analytics/daily",
        "daily"
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
        "สรุปรายเดือน",
        "ดูผลการคัดแยกกุ้งในแต่ละเดือน",
        "/api/analytics/monthly",
        "monthly"
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
        "สรุปรายปี",
        "ดูผลการคัดแยกกุ้งในแต่ละปี",
        "/api/analytics/yearly",
        "yearly"
    )


# =========================================================
# LIVE CAMERA
# =========================================================

@app.get(
    "/live",
    response_class=HTMLResponse
)
async def live_page():

    body = """
    <main class="container">

        <div class="page">

            <a
                href="/"
                class="back-btn"
            >
                ← กลับ Dashboard
            </a>


            <div class="live-header">

                <div>

                    <div class="eyebrow">
                        REAL-TIME AI CAMERA
                    </div>

                    <h1>
                        📷 Live Camera
                    </h1>

                </div>


                <div
                    class="status"
                    id="status"
                >

                    <span
                        class="status-dot"
                    ></span>

                    <span id="statusText">
                        Connecting...
                    </span>

                </div>

            </div>


            <section class="camera-panel">

                <img
                    id="camera"
                    alt="AI Camera"
                >


                <div
                    class="camera-empty"
                    id="empty"
                >

                    <div class="camera-empty-icon">
                        📷
                    </div>

                    <div>
                        กำลังรอภาพจากกล้อง AI
                    </div>

                    <div
                        style="
                        margin-top:7px;
                        font-size:11px;
                        color:#4e6171;
                        "
                    >
                        CAMERA STREAM WAITING
                    </div>

                </div>

            </section>


            <section class="live-stats">

                <div class="live-stat">

                    <span>
                        AI FPS
                    </span>

                    <strong id="fps">
                        0
                    </strong>

                </div>


                <div class="live-stat">

                    <span>
                        CAMERA STATUS
                    </span>

                    <strong id="online">
                        Offline
                    </strong>

                </div>


                <div class="live-stat">

                    <span>
                        LAST UPDATE
                    </span>

                    <strong
                        id="updated"
                        style="font-size:14px;"
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
        document.getElementById(
            "camera"
        );

    const empty =
        document.getElementById(
            "empty"
        );


    async function updateLive() {

        try {

            const res =
                await fetch(
                    "/api/live/status",
                    {cache:"no-store"}
                );


            const data =
                await res.json();


            const status =
                document.getElementById(
                    "status"
                );

            const statusText =
                document.getElementById(
                    "statusText"
                );

            const online =
                document.getElementById(
                    "online"
                );

            const fps =
                document.getElementById(
                    "fps"
                );

            const updated =
                document.getElementById(
                    "updated"
                );


            fps.textContent =
                Number(
                    data.fps || 0
                ).toFixed(1);


            updated.textContent =
                data.updated_at || "-";


            if (data.online) {

                status.classList.add(
                    "online"
                );

                statusText.textContent =
                    "Camera Online";

                online.textContent =
                    "ONLINE";


                camera.src =
                    "/api/live/frame?t="
                    + Date.now();

                camera.style.display =
                    "block";

                empty.style.display =
                    "none";

            } else {

                status.classList.remove(
                    "online"
                );

                statusText.textContent =
                    "Camera Offline";

                online.textContent =
                    "OFFLINE";


                camera.style.display =
                    "none";

                empty.style.display =
                    "block";

            }

        } catch (e) {

            console.error(e);

        }

    }


    updateLive();


    setInterval(
        updateLive,
        1000
    );

    </script>
    """


    return HTMLResponse(
        page_html(
            "Live Camera",
            body,
            "live",
            script
        )
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
