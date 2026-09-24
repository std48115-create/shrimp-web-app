from fastapi import FastAPI, Request, Header
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any
from collections import deque
from datetime import datetime
import base64
import os
import io
import uvicorn


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="Shrimp AI Factory Dashboard",
    version="2.0.0"
)


# =========================================================
# CONFIG
# =========================================================

API_KEY = os.getenv("API_KEY", "change-me")

PORT = int(
    os.getenv("PORT", "10000")
)


# =========================================================
# SHRIMP TYPES
# =========================================================

SHRIMP_TYPES = [
    "กุ้งเล็ก",
    "กุ้งกลาง",
    "กุ้งใหญ่",
    "กุ้งป่วย"
]


# =========================================================
# MEMORY DATA
# =========================================================

latest_round: Optional[dict] = None

round_history = deque(
    maxlen=1000
)

live_frame: Optional[bytes] = None

live_ts: Optional[float] = None

live_info = {
    "fps": 0,
    "updated_at": None
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

    started_at: Optional[str] = None

    finished_at: Optional[str] = None


class LiveReport(BaseModel):

    fps: float = 0

    timestamp: Optional[str] = None

    frame: Optional[str] = None


# =========================================================
# HELPERS
# =========================================================

def clean_counts(
    counts: Optional[Dict[str, Any]]
) -> Dict[str, int]:

    result = {}

    counts = counts or {}

    for shrimp_type in SHRIMP_TYPES:

        try:

            value = int(
                counts.get(
                    shrimp_type,
                    0
                )
            )

        except Exception:

            value = 0

        if value < 0:
            value = 0

        result[shrimp_type] = value

    return result


def total_counts(
    counts: Dict[str, int]
) -> int:

    return sum(
        int(
            counts.get(
                shrimp_type,
                0
            )
        )
        for shrimp_type in SHRIMP_TYPES
    )


def get_report_dict(
    report: RoundReport
) -> dict:

    counts = clean_counts(
        report.counts
    )

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


def check_api_key(
    key: Optional[str]
) -> bool:

    return (
        key is not None
        and key == API_KEY
    )


def decode_frame(
    frame_data: str
) -> bytes:

    if "," in frame_data:

        frame_data = frame_data.split(
            ",",
            1
        )[1]

    return base64.b64decode(
        frame_data
    )


def parse_datetime(
    value: Any
) -> Optional[datetime]:

    if not value:
        return None

    if isinstance(
        value,
        datetime
    ):
        return value

    text = str(value).strip()

    if not text:
        return None

    # ISO format
    try:

        return datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00"
            )
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

            return datetime.strptime(
                text,
                fmt
            )

        except Exception:
            continue

    return None


def get_round_datetime(
    item: dict
) -> Optional[datetime]:

    # ใช้เวลาที่จบรอบก่อน
    for key in [
        "finished_at",
        "started_at",
        "received_at"
    ]:

        result = parse_datetime(
            item.get(key)
        )

        if result:
            return result

    return None


# =========================================================
# ANALYTICS
# =========================================================

def build_analytics(
    mode: str
) -> list:

    buckets = {}

    for item in round_history:

        dt = get_round_datetime(
            item
        )

        if dt is None:
            continue


        if mode == "daily":

            key = dt.strftime(
                "%Y-%m-%d"
            )

            label = dt.strftime(
                "%d/%m/%Y"
            )


        elif mode == "monthly":

            key = dt.strftime(
                "%Y-%m"
            )

            label = dt.strftime(
                "%m/%Y"
            )


        elif mode == "yearly":

            key = dt.strftime(
                "%Y"
            )

            label = dt.strftime(
                "%Y"
            )


        else:

            continue


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


        for shrimp_type in SHRIMP_TYPES:

            buckets[key]["counts"][
                shrimp_type
            ] += counts[
                shrimp_type
            ]


        buckets[key]["total"] += total_counts(
            counts
        )

        buckets[key]["rounds"] += 1


    result = list(
        buckets.values()
    )

    result.sort(
        key=lambda x: x["key"]
    )

    return result


# =========================================================
# API - ROUND
# =========================================================

@app.post("/api/round")
async def receive_round(
    report: RoundReport,
    x_api_key: Optional[str] = Header(
        default=None
    )
):

    if not check_api_key(
        x_api_key
    ):

        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "Invalid API key"
            }
        )


    global latest_round


    data = get_report_dict(
        report
    )


    latest_round = data


    round_history.append(
        data
    )


    return {
        "ok": True,
        "message": "Round received",
        "round": data
    }


# =========================================================
# API - LIVE CAMERA
# =========================================================

@app.post("/api/live")
async def receive_live(
    report: LiveReport,
    x_api_key: Optional[str] = Header(
        default=None
    )
):

    if not check_api_key(
        x_api_key
    ):

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
                    "error": (
                        "Invalid frame: "
                        + str(e)
                    )
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


# =========================================================
# API - DASHBOARD
# =========================================================

@app.get("/api/dashboard")
async def dashboard_api():

    counts = clean_counts(
        latest_round.get(
            "counts",
            {}
        )
        if latest_round
        else {}
    )


    return {
        "ok": True,
        "latest_round": latest_round,
        "history_count": len(
            round_history
        ),
        "counts": counts,
        "total": total_counts(
            counts
        )
    }


# =========================================================
# API - DAILY
# =========================================================

@app.get("/api/analytics/daily")
async def analytics_daily():

    return {
        "ok": True,
        "mode": "daily",
        "data": build_analytics(
            "daily"
        )
    }


# =========================================================
# API - MONTHLY
# =========================================================

@app.get("/api/analytics/monthly")
async def analytics_monthly():

    return {
        "ok": True,
        "mode": "monthly",
        "data": build_analytics(
            "monthly"
        )
    }


# =========================================================
# API - YEARLY
# =========================================================

@app.get("/api/analytics/yearly")
async def analytics_yearly():

    return {
        "ok": True,
        "mode": "yearly",
        "data": build_analytics(
            "yearly"
        )
    }


# =========================================================
# API - LIVE STATUS
# =========================================================

@app.get("/api/live/status")
async def live_status():

    now = datetime.now().timestamp()

    online = False

    if live_ts:

        online = (
            now - live_ts
        ) < 10


    return {
        "ok": True,
        "online": online,
        "fps": live_info.get(
            "fps",
            0
        ),
        "updated_at": live_info.get(
            "updated_at"
        )
    }


# =========================================================
# API - LIVE FRAME
# =========================================================

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
                "no-store, no-cache, must-revalidate"
        }
    )


# =========================================================
# API - HEALTH
# =========================================================

@app.get("/api/health")
async def health():

    return {
        "ok": True,
        "service":
            "shrimp-web-app",
        "rounds":
            len(round_history),
        "live":
            live_frame is not None
    }


# =========================================================
# GLOBAL CSS
# =========================================================

CSS = """
<style>

* {
    box-sizing: border-box;
}

html {
    scroll-behavior: smooth;
}

body {
    margin: 0;
    background: #f5f7f9;
    color: #17212b;
    font-family:
        Inter,
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
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
    height: 72px;
    background: rgba(255,255,255,.94);
    border-bottom: 1px solid #e8edf1;
    display: flex;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 100;
    backdrop-filter: blur(16px);
}

.nav-inner {
    width: min(1400px, calc(100% - 40px));
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
    font-weight: 800;
    letter-spacing: -.3px;
}

.logo-icon {
    width: 40px;
    height: 40px;
    border-radius: 12px;
    background: #152532;
    color: white;
    display: grid;
    place-items: center;
    font-size: 20px;
}

.logo-text small {
    display: block;
    font-size: 10px;
    color: #8b96a1;
    letter-spacing: 1.5px;
    margin-bottom: 2px;
}

.logo-text strong {
    font-size: 15px;
}

.nav-links {
    display: flex;
    align-items: center;
    gap: 6px;
}

.nav-links a {
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 13px;
    color: #687582;
    transition: .2s;
}

.nav-links a:hover {
    background: #f0f3f5;
    color: #17212b;
}

.nav-links a.active {
    background: #172b39;
    color: white;
}


/* =====================================================
   CONTAINER
   ===================================================== */

.container {
    width: min(1400px, calc(100% - 40px));
    margin: 0 auto;
}

.page {
    padding: 42px 0 70px;
}


/* =====================================================
   HERO
   ===================================================== */

.hero {
    padding: 42px;
    border-radius: 28px;
    background:
        linear-gradient(
            135deg,
            #ffffff 0%,
            #f1f5f7 100%
        );
    border: 1px solid #e4eaee;
    box-shadow:
        0 20px 60px rgba(31,48,61,.07);
    margin-bottom: 28px;
}

.eyebrow {
    color: #8a96a1;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 2px;
    margin-bottom: 12px;
}

.hero h1,
.page-title h1 {
    margin: 0;
    font-size: clamp(30px, 4vw, 48px);
    line-height: 1.1;
    letter-spacing: -1.5px;
}

.hero p,
.page-title p {
    color: #7a8792;
    margin: 14px 0 0;
    font-size: 15px;
}

.page-title {
    margin-bottom: 28px;
}


/* =====================================================
   KPI
   ===================================================== */

.kpi-grid {
    display: grid;
    grid-template-columns:
        repeat(4, minmax(0, 1fr));
    gap: 16px;
    margin-bottom: 28px;
}

.kpi {
    background: white;
    border: 1px solid #e5ebef;
    border-radius: 20px;
    padding: 24px;
    box-shadow:
        0 12px 35px rgba(31,48,61,.05);
}

.kpi-label {
    color: #8a96a1;
    font-size: 12px;
    font-weight: 700;
}

.kpi-value {
    margin-top: 10px;
    font-size: 32px;
    font-weight: 800;
    letter-spacing: -1px;
}


/* =====================================================
   SHRIMP CARDS
   ===================================================== */

.shrimp-grid {
    display: grid;
    grid-template-columns:
        repeat(4, minmax(0, 1fr));
    gap: 16px;
    margin-bottom: 28px;
}

.shrimp-card {
    background: white;
    border: 1px solid #e5ebef;
    border-radius: 20px;
    padding: 22px;
    box-shadow:
        0 12px 35px rgba(31,48,61,.05);
}

.shrimp-card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.shrimp-name {
    font-size: 14px;
    font-weight: 800;
}

.shrimp-icon {
    width: 40px;
    height: 40px;
    border-radius: 12px;
    display: grid;
    place-items: center;
    background: #f1f4f6;
}

.shrimp-number {
    font-size: 32px;
    font-weight: 800;
    margin-top: 20px;
}

.shrimp-sub {
    color: #909aa4;
    font-size: 12px;
    margin-top: 5px;
}


/* =====================================================
   PANELS
   ===================================================== */

.panel {
    background: white;
    border: 1px solid #e5ebef;
    border-radius: 22px;
    box-shadow:
        0 12px 35px rgba(31,48,61,.05);
}

.section {
    margin-top: 28px;
}

.section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
}

.section-head h2 {
    margin: 0;
    font-size: 18px;
}


/* =====================================================
   ANALYTICS CHART
   ===================================================== */

.chart-panel {
    padding: 28px;
}

.chart-box {
    width: 100%;
    height: 420px;
    position: relative;
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
    gap: 22px;
    margin-top: 12px;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 7px;
    color: #71808c;
    font-size: 12px;
}

.dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
}

.dot.a {
    background: #8b9aaa;
}

.dot.b {
    background: #4e6477;
}

.dot.c {
    background: #1f3445;
}

.dot.d {
    background: #d27b72;
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
    min-width: 720px;
}

th {
    background: #f8fafb;
    color: #7f8a95;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .5px;
    padding: 15px 18px;
    text-align: left;
}

td {
    padding: 16px 18px;
    border-top: 1px solid #edf0f3;
    font-size: 13px;
}

tbody tr:hover {
    background: #fafcfd;
}


/* =====================================================
   DASHBOARD
   ===================================================== */

.dashboard-actions {
    display: grid;
    grid-template-columns:
        repeat(4, minmax(0, 1fr));
    gap: 14px;
    margin-top: 28px;
}

.action-card {
    background: white;
    border: 1px solid #e5ebef;
    border-radius: 18px;
    padding: 20px;
    transition: .2s;
}

.action-card:hover {
    transform: translateY(-2px);
    box-shadow:
        0 15px 35px rgba(31,48,61,.08);
}

.action-icon {
    font-size: 24px;
    margin-bottom: 14px;
}

.action-card strong {
    display: block;
    font-size: 14px;
}

.action-card span {
    display: block;
    color: #89949e;
    font-size: 12px;
    margin-top: 5px;
}


/* =====================================================
   LIVE
   ===================================================== */

.live-page {
    padding: 30px 0 60px;
}

.live-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
}

.live-header h1 {
    margin: 0;
    font-size: 32px;
}

.status {
    display: flex;
    align-items: center;
    gap: 8px;
    background: white;
    border: 1px solid #e5ebef;
    border-radius: 999px;
    padding: 9px 14px;
    font-size: 12px;
    color: #71808c;
}

.status-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: #c5cbd0;
}

.status.online .status-dot {
    background: #5c9b7a;
}

.camera-panel {
    background: #101920;
    border-radius: 26px;
    overflow: hidden;
    min-height: 600px;
    display: grid;
    place-items: center;
    box-shadow:
        0 25px 70px rgba(10,20,28,.18);
}

.camera-panel img {
    width: 100%;
    height: 100%;
    min-height: 600px;
    object-fit: contain;
    display: block;
}

.camera-empty {
    color: #77838d;
    text-align: center;
    padding: 40px;
}

.live-stats {
    display: grid;
    grid-template-columns:
        repeat(3, minmax(0, 1fr));
    gap: 16px;
    margin-top: 20px;
}

.live-stat {
    background: white;
    border: 1px solid #e5ebef;
    border-radius: 18px;
    padding: 20px;
}

.live-stat span {
    display: block;
    color: #89949e;
    font-size: 12px;
}

.live-stat strong {
    display: block;
    margin-top: 8px;
    font-size: 25px;
}


/* =====================================================
   RESPONSIVE
   ===================================================== */

@media (max-width: 1000px) {

    .kpi-grid,
    .shrimp-grid {
        grid-template-columns:
            repeat(2, minmax(0, 1fr));
    }

    .dashboard-actions {
        grid-template-columns:
            repeat(2, minmax(0, 1fr));
    }

}

@media (max-width: 720px) {

    .container,
    .nav-inner {
        width: min(
            100% - 24px,
            1400px
        );
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
        overflow-x: auto;
    }

    .nav-links a {
        white-space: nowrap;
    }

    .hero {
        padding: 26px;
    }

    .kpi-grid,
    .shrimp-grid,
    .dashboard-actions,
    .live-stats {
        grid-template-columns: 1fr;
    }

    .chart-panel {
        padding: 18px;
    }

    .chart-box {
        height: 330px;
    }

    .live-header {
        align-items: flex-start;
        gap: 15px;
        flex-direction: column;
    }

    .camera-panel,
    .camera-panel img {
        min-height: 350px;
    }

}

</style>
"""


# =========================================================
# NAVBAR
# =========================================================

def navbar(
    active: str
) -> str:

    links = [
        (
            "/",
            "Dashboard",
            "dashboard"
        ),
        (
            "/daily",
            "รายวัน",
            "daily"
        ),
        (
            "/monthly",
            "รายเดือน",
            "monthly"
        ),
        (
            "/yearly",
            "รายปี",
            "yearly"
        ),
        (
            "/live",
            "กล้อง",
            "live"
        )
    ]


    html = """
    <nav class="navbar">

        <div class="nav-inner">

            <a
                href="/"
                class="logo"
            >

                <div class="logo-icon">
                    🦐
                </div>

                <div class="logo-text">

                    <small>
                        AI FACTORY
                    </small>

                    <strong>
                        Shrimp Vision
                    </strong>

                </div>

            </a>


            <div class="nav-links">
    """


    for href, text, key in links:

        active_class = (
            "active"
            if active == key
            else ""
        )

        html += (
            '<a href="'
            + href
            + '" class="'
            + active_class
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
# HTML WRAPPER
# =========================================================

def html_page(
    title: str,
    body: str,
    active: str = "",
    script: str = ""
) -> str:

    return (
        "<!DOCTYPE html>"
        "<html lang='th'>"
        "<head>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' "
        "content='width=device-width, "
        "initial-scale=1.0'>"
        "<title>"
        + title
        + " | Shrimp Vision"
        + "</title>"
        + CSS
        + "</head>"
        "<body>"
        + navbar(active)
        + body
        + script
        + "</body>"
        "</html>"
    )


# =========================================================
# DASHBOARD PAGE
# =========================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
async def home():

    body = """
    <main class="container">

        <div class="page">

            <section class="hero">

                <div class="eyebrow">
                    AI SHRIMP SORTING SYSTEM
                </div>

                <h1>
                    Shrimp Vision
                </h1>

                <p>
                    ระบบวิเคราะห์และคัดแยกกุ้ง
                    ด้วย AI สำหรับโรงงาน
                </p>

            </section>


            <section class="kpi-grid">

                <div class="kpi">

                    <div class="kpi-label">
                        กุ้งในรอบล่าสุด
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
                        ระยะเวลารอบ
                    </div>

                    <div
                        class="kpi-value"
                        id="duration"
                    >
                        0s
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


            <section class="shrimp-grid">

                <div class="shrimp-card">

                    <div class="shrimp-card-top">

                        <div class="shrimp-name">
                            กุ้งเล็ก
                        </div>

                        <div class="shrimp-icon">
                            🦐
                        </div>

                    </div>

                    <div
                        class="shrimp-number"
                        id="small"
                    >
                        0
                    </div>

                    <div class="shrimp-sub">
                        รอบล่าสุด
                    </div>

                </div>


                <div class="shrimp-card">

                    <div class="shrimp-card-top">

                        <div class="shrimp-name">
                            กุ้งกลาง
                        </div>

                        <div class="shrimp-icon">
                            🦐
                        </div>

                    </div>

                    <div
                        class="shrimp-number"
                        id="medium"
                    >
                        0
                    </div>

                    <div class="shrimp-sub">
                        รอบล่าสุด
                    </div>

                </div>


                <div class="shrimp-card">

                    <div class="shrimp-card-top">

                        <div class="shrimp-name">
                            กุ้งใหญ่
                        </div>

                        <div class="shrimp-icon">
                            🦐
                        </div>

                    </div>

                    <div
                        class="shrimp-number"
                        id="large"
                    >
                        0
                    </div>

                    <div class="shrimp-sub">
                        รอบล่าสุด
                    </div>

                </div>


                <div class="shrimp-card">

                    <div class="shrimp-card-top">

                        <div class="shrimp-name">
                            กุ้งป่วย
                        </div>

                        <div class="shrimp-icon">
                            ⚠️
                        </div>

                    </div>

                    <div
                        class="shrimp-number"
                        id="sick"
                    >
                        0
                    </div>

                    <div class="shrimp-sub">
                        รอบล่าสุด
                    </div>

                </div>

            </section>


            <div class="dashboard-actions">

                <a
                    class="action-card"
                    href="/daily"
                >

                    <div class="action-icon">
                        📅
                    </div>

                    <strong>
                        รายวัน
                    </strong>

                    <span>
                        ดูสถิติและกราฟรายวัน
                    </span>

                </a>


                <a
                    class="action-card"
                    href="/monthly"
                >

                    <div class="action-icon">
                        🗓️
                    </div>

                    <strong>
                        รายเดือน
                    </strong>

                    <span>
                        ดูสถิติและกราฟรายเดือน
                    </span>

                </a>


                <a
                    class="action-card"
                    href="/yearly"
                >

                    <div class="action-icon">
                        📈
                    </div>

                    <strong>
                        รายปี
                    </strong>

                    <span>
                        ดูสถิติและกราฟรายปี
                    </span>

                </a>


                <a
                    class="action-card"
                    href="/live"
                >

                    <div class="action-icon">
                        📷
                    </div>

                    <strong>
                        กล้อง Real-time
                    </strong>

                    <span>
                        ดูภาพจาก AI แบบสด
                    </span>

                </a>

            </div>


            <section class="section">

                <div class="section-head">

                    <h2>
                        ข้อมูลรอบล่าสุด
                    </h2>

                </div>


                <div class="panel">

                    <div class="table-wrap">

                        <table>

                            <thead>

                                <tr>
                                    <th>รอบ</th>
                                    <th>เริ่ม</th>
                                    <th>สิ้นสุด</th>
                                    <th>FPS</th>
                                    <th>Frames</th>
                                    <th>รวม</th>
                                </tr>

                            </thead>

                            <tbody id="latestTable">

                                <tr>
                                    <td
                                        colspan="6"
                                        style="
                                        text-align:center;
                                        padding:40px;
                                        color:#89949e;
                                        "
                                    >
                                        ยังไม่มีข้อมูล
                                    </td>
                                </tr>

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

    async function loadDashboard() {

        try {

            const response =
                await fetch(
                    "/api/dashboard",
                    {
                        cache: "no-store"
                    }
                );


            const data =
                await response.json();


            const counts =
                data.counts || {};


            const latest =
                data.latest_round;


            document.getElementById(
                "total"
            ).textContent =
                data.total || 0;


            document.getElementById(
                "rounds"
            ).textContent =
                data.history_count || 0;


            document.getElementById(
                "small"
            ).textContent =
                counts["กุ้งเล็ก"] || 0;


            document.getElementById(
                "medium"
            ).textContent =
                counts["กุ้งกลาง"] || 0;


            document.getElementById(
                "large"
            ).textContent =
                counts["กุ้งใหญ่"] || 0;


            document.getElementById(
                "sick"
            ).textContent =
                counts["กุ้งป่วย"] || 0;


            if (latest) {

                document.getElementById(
                    "fps"
                ).textContent =
                    Number(
                        latest.avg_fps || 0
                    ).toFixed(1);


                document.getElementById(
                    "duration"
                ).textContent =
                    Number(
                        latest.duration || 0
                    ).toFixed(1)
                    + "s";


                const table =
                    document.getElementById(
                        "latestTable"
                    );


                table.innerHTML = `

                    <tr>

                        <td>
                            #${latest.round_id || "-"}
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
                            <strong>
                                ${latest.total || 0}
                            </strong>
                        </td>

                    </tr>

                `;

            }

        } catch (error) {

            console.error(
                "Dashboard error:",
                error
            );

        }

    }


    loadDashboard();


    setInterval(
        loadDashboard,
        5000
    );

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
    title: str,
    subtitle: str,
    endpoint: str,
    active: str,
    chart_title: str
) -> HTMLResponse:

    body = (
        """
        <main class="container">

            <div class="page">

                <div class="page-title">

                    <div class="eyebrow">
                        SHRIMP ANALYTICS
                    </div>

                    <h1>
                        """
        + title
        + """
                    </h1>

                    <p>
                        """
        + subtitle
        + """
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
                                """
        + chart_title
        + """
                            </h2>

                            <div
                                style="
                                color:#8a96a1;
                                font-size:13px;
                                margin-top:6px;
                                "
                            >
                                แสดงจำนวนกุ้ง
                                แยกตามประเภท
                            </div>

                        </div>

                    </div>


                    <div class="chart-box">

                        <canvas
                            id="barChart"
                        ></canvas>

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


                                <tbody
                                    id="tableBody"
                                ></tbody>

                            </table>

                        </div>

                    </div>

                </section>

            </div>

        </main>
        """
    )


    # =====================================================
    # IMPORTANT
    # JavaScript เป็น string ธรรมดา
    # ไม่ใช้ f-string
    # =====================================================

    script = """
    <script>

    const ENDPOINT = "__ENDPOINT__";

    let chartData = [];


    async function loadAnalytics() {

        try {

            const response =
                await fetch(
                    ENDPOINT,
                    {
                        cache: "no-store"
                    }
                );


            const result =
                await response.json();


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

        } catch (error) {

            console.error(
                "Analytics error:",
                error
            );

        }

    }


    function updateSummary(data) {

        let total = 0;

        let small = 0;

        let medium = 0;

        let other = 0;


        data.forEach(
            function(item) {

                const counts =
                    item.counts || {};


                small += Number(
                    counts["กุ้งเล็ก"] || 0
                );


                medium += Number(
                    counts["กุ้งกลาง"] || 0
                );


                other += Number(
                    counts["กุ้งใหญ่"] || 0
                );


                other += Number(
                    counts["กุ้งป่วย"] || 0
                );


                total += Number(
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

        const body =
            document.getElementById(
                "tableBody"
            );


        body.innerHTML = "";


        if (!data.length) {

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


        const rows =
            data.slice().reverse();


        rows.forEach(
            function(item) {

                const counts =
                    item.counts || {};


                const row =
                    document.createElement(
                        "tr"
                    );


                row.innerHTML = `

                    <td>
                        <strong>
                            ${item.label || "-"}
                        </strong>
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
                        <strong>
                            ${item.total || 0}
                        </strong>
                    </td>

                    <td>
                        ${item.rounds || 0}
                    </td>

                `;


                body.appendChild(
                    row
                );

            }
        );

    }


    function drawChart(data) {

        const canvas =
            document.getElementById(
                "barChart"
            );


        if (!canvas) {
            return;
        }


        const ctx =
            canvas.getContext(
                "2d"
            );


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


        const padding = {

            left: 60,

            right: 25,

            top: 30,

            bottom: 65

        };


        const chartWidth =
            width
            - padding.left
            - padding.right;


        const chartHeight =
            height
            - padding.top
            - padding.bottom;


        let maxValue = 0;


        data.forEach(
            function(item) {

                const counts =
                    item.counts || {};


                maxValue = Math.max(

                    maxValue,

                    Number(
                        counts["กุ้งเล็ก"] || 0
                    ),

                    Number(
                        counts["กุ้งกลาง"] || 0
                    ),

                    Number(
                        counts["กุ้งใหญ่"] || 0
                    ),

                    Number(
                        counts["กุ้งป่วย"] || 0
                    )

                );

            }
        );


        maxValue =
            Math.ceil(
                maxValue * 1.2
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
        ) {

            const value =
                maxValue *
                (
                    i /
                    gridCount
                );


            const y =
                padding.top
                + chartHeight
                - (
                    value /
                    maxValue
                )
                * chartHeight;


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

        }


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
            chartWidth /
            data.length;


        const barGap = 4;


        const barWidth =
            Math.max(

                5,

                (
                    groupWidth *
                    0.68 /
                    keys.length
                )
                - barGap

            );


        data.forEach(
            function(item, index) {

                const centerX =

                    padding.left
                    + index *
                    groupWidth
                    + groupWidth / 2;


                keys.forEach(
                    function(
                        key,
                        keyIndex
                    ) {

                        const counts =
                            item.counts || {};


                        const value =
                            Number(
                                counts[key] || 0
                            );


                        const barHeight =

                            (
                                value /
                                maxValue
                            )
                            * chartHeight;


                        const x =

                            centerX
                            - (
                                keys.length *
                                (
                                    barWidth +
                                    barGap
                                )
                            ) / 2
                            + keyIndex *
                            (
                                barWidth +
                                barGap
                            );


                        const y =

                            padding.top
                            + chartHeight
                            - barHeight;


                        ctx.fillStyle =
                            colors[keyIndex];


                        ctx.beginPath();


                        // รองรับ browser ที่ไม่มี roundRect
                        if (
                            typeof ctx.roundRect
                            === "function"
                        ) {

                            ctx.roundRect(
                                x,
                                y,
                                barWidth,
                                barHeight,
                                4
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


                        if (
                            data.length <= 15
                            && value > 0
                        ) {

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

                        }

                    }
                );


                ctx.fillStyle =
                    "#7f8a95";


                ctx.font =
                    "11px Arial";


                ctx.textAlign =
                    "center";


                let label =
                    item.label || "";


                if (
                    data.length > 20
                    && index % 2 !== 0
                ) {

                    label = "";

                }


                ctx.fillText(

                    label,

                    centerX,

                    height - 25

                );

            }
        );

    }


    window.addEventListener(
        "resize",
        function() {

            drawChart(
                chartData
            );

        }
    );


    loadAnalytics();


    setInterval(
        loadAnalytics,
        5000
    );

    </script>
    """


    script = script.replace(
        "__ENDPOINT__",
        endpoint
    )


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

@app.get(
    "/daily",
    response_class=HTMLResponse
)
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

@app.get(
    "/monthly",
    response_class=HTMLResponse
)
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

@app.get(
    "/yearly",
    response_class=HTMLResponse
)
async def yearly_page():

    return analytics_page(

        "สรุปรายปี",

        "วิเคราะห์จำนวนกุ้งที่ตรวจพบในแต่ละปี",

        "/api/analytics/yearly",

        "yearly",

        "แผนภูมิแท่งรายปี"

    )


# =========================================================
# LIVE PAGE
# =========================================================

@app.get(
    "/live",
    response_class=HTMLResponse
)
async def live_page():

    body = """
    <main class="container">

        <div class="live-page">

            <div class="live-header">

                <div>

                    <div class="eyebrow">
                        REAL-TIME CAMERA
                    </div>

                    <h1>
                        กล้อง AI
                    </h1>

                </div>


                <div
                    class="status"
                    id="status"
                >

                    <span
                        class="status-dot"
                    ></span>

                    <span
                        id="statusText"
                    >
                        กำลังเชื่อมต่อ
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

                    <div
                        style="
                        font-size:45px;
                        margin-bottom:15px;
                        "
                    >
                        📷
                    </div>

                    <div>
                        กำลังรอภาพจากกล้อง AI
                    </div>

                </div>

            </section>


            <section class="live-stats">

                <div class="live-stat">

                    <span>
                        FPS
                    </span>

                    <strong id="fps">
                        0
                    </strong>

                </div>


                <div class="live-stat">

                    <span>
                        สถานะ
                    </span>

                    <strong id="online">
                        Offline
                    </strong>

                </div>


                <div class="live-stat">

                    <span>
                        อัปเดตล่าสุด
                    </span>

                    <strong
                        id="updated"
                        style="font-size:15px;"
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

            const response =
                await fetch(
                    "/api/live/status",
                    {
                        cache: "no-store"
                    }
                );


            const data =
                await response.json();


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
                    "Online";


                online.textContent =
                    "Online";


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
                    "Offline";


                online.textContent =
                    "Offline";


                camera.style.display =
                    "none";


                empty.style.display =
                    "block";

            }

        } catch (error) {

            console.error(
                "Live error:",
                error
            );

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
        html_page(
            "กล้อง Real-time",
            body,
            "live",
            script
        )
    )


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    uvicorn.run(

        app,

        host="0.0.0.0",

        port=PORT

    )
