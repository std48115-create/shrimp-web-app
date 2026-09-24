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
    title="Shrimp Sorting AI Dashboard",
    version="4.0.0"
)


# =========================================================
# ประเภทกุ้งทั้งหมดในระบบ
# =========================================================

SHRIMP_TYPES = [
    "กุ้งเล็ก",
    "กุ้งกลาง",
    "กุ้งใหญ่",
    "กุ้งป่วย"
]


# =========================================================
# DATA STORAGE
# =========================================================

# ผลการทำงานรอบล่าสุด
latest_round = None

# เก็บประวัติสูงสุด 100 รอบ
round_history = deque(maxlen=100)

# ภาพกล้องล่าสุด
live_frame = None
live_ts = 0.0


# =========================================================
# DATA MODEL
# =========================================================

class RoundReport(BaseModel):

    # หมายเลขรอบ
    round_id: int = 0

    # จำนวนกุ้งแต่ละประเภท
    counts: dict[str, int] = Field(
        default_factory=dict
    )

    # FPS เฉลี่ยของ AI
    avg_fps: float = 0.0

    # เวลาที่ใช้ในการทำงานรอบนั้น
    duration: float = 0.0

    # จำนวนเฟรมที่ตรวจ
    frames: int = 0

    # เวลาเริ่ม
    started_at: str | None = None

    # เวลาจบ
    finished_at: str | None = None

    # ภาพผลลัพธ์ล่าสุด
    frame_b64: str | None = None


class LiveReport(BaseModel):

    # จำนวนที่ AI เห็น ณ ตอนนั้น
    counts: dict[str, int] = Field(
        default_factory=dict
    )

    # FPS
    fps: float = 0.0

    # ภาพจากกล้อง
    frame_b64: str | None = None


# =========================================================
# CLEAN COUNTS
# =========================================================

def clean_counts(raw_counts):

    result = {}

    # บังคับให้มี 4 ประเภทเสมอ
    for shrimp_type in SHRIMP_TYPES:

        value = raw_counts.get(
            shrimp_type,
            0
        )

        try:
            value = int(value)
        except Exception:
            value = 0

        if value < 0:
            value = 0

        result[shrimp_type] = value

    return result


# =========================================================
# RECEIVE RESULT WHEN ROUND FINISHES
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
    # จัดข้อมูลจำนวนกุ้ง
    # -------------------------

    counts = clean_counts(
        data.counts
    )

    # -------------------------
    # รวมกุ้งทั้งหมด
    # -------------------------

    total = sum(
        counts.values()
    )

    # -------------------------
    # จำนวนกุ้งปกติ
    # -------------------------

    normal_total = (
        counts["กุ้งเล็ก"]
        + counts["กุ้งกลาง"]
        + counts["กุ้งใหญ่"]
    )

    # -------------------------
    # สร้างผลรอบ
    # -------------------------

    result = {

        "round_id":
            int(data.round_id),

        "counts":
            counts,

        "total":
            total,

        "normal_total":
            normal_total,

        "sick_total":
            counts["กุ้งป่วย"],

        "avg_fps":
            round(
                max(
                    0,
                    float(data.avg_fps)
                ),
                2
            ),

        "duration":
            round(
                max(
                    0,
                    float(data.duration)
                ),
                2
            ),

        "frames":
            max(
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
    # บันทึกผลรอบล่าสุด
    # -------------------------

    latest_round = result

    # -------------------------
    # เพิ่มลงประวัติ
    # -------------------------

    round_history.appendleft(
        result
    )

    # -------------------------
    # ถ้ามีภาพ
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

        "counts":
            counts,

        "total":
            total,

        "sick":
            counts["กุ้งป่วย"]
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

    # รับภาพจาก AI
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
# DASHBOARD API
# =========================================================

@app.get("/api/dashboard")
def dashboard():

    return {

        "has_round":
            latest_round is not None,

        "latest":
            latest_round,

        "history":
            list(round_history),

        "shrimp_types":
            SHRIMP_TYPES
    }


# =========================================================
# LIVE STATUS
# =========================================================

@app.get("/api/live/status")
def live_status():

    if live_ts == 0:

        return {

            "online": False,

            "age": 0,

            "has_frame": False

        }

    age = (
        time.time()
        - live_ts
    )

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
                "no-store, no-cache, must-revalidate"
        }

    )


# =========================================================
# PAGE 1
# DASHBOARD
# =========================================================

DASHBOARD_PAGE = r"""
<!DOCTYPE html>

<html lang="th">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>ระบบคัดแยกกุ้ง AI</title>

<style>

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    background: #f5f9fc;

    color: #183247;

    font-family:
        "Noto Sans Thai",
        "Segoe UI",
        Arial,
        sans-serif;
}


/* =====================================================
   HEADER
===================================================== */

header {

    background: #ffffff;

    border-bottom:
        1px solid #dbeaf2;

    padding: 18px 30px;

    display: flex;

    align-items: center;

    justify-content: space-between;

    gap: 20px;

    flex-wrap: wrap;

    box-shadow:
        0 3px 15px
        rgba(40,90,120,.08);
}

.logo {

    display: flex;

    align-items: center;

    gap: 13px;
}

.logo-icon {

    width: 52px;

    height: 52px;

    border-radius: 15px;

    background: #e6f7ff;

    border: 1px solid #ccecf8;

    display: flex;

    align-items: center;

    justify-content: center;

    font-size: 28px;
}

.logo h1 {

    margin: 0;

    font-size: 22px;

    color: #16435d;
}

.logo p {

    margin: 4px 0 0;

    color: #78909c;

    font-size: 12px;
}


/* =====================================================
   NAV
===================================================== */

nav {

    display: flex;

    gap: 8px;
}

nav a {

    text-decoration: none;

    color: #506b7a;

    background: #ffffff;

    border: 1px solid #d5e5ed;

    padding: 9px 15px;

    border-radius: 9px;

    font-size: 13px;

    transition: .2s;
}

nav a:hover {

    background: #effaff;

    border-color: #9dd8ef;
}

nav a.active {

    color: #ffffff;

    background: #0ea5e9;

    border-color: #0ea5e9;
}


/* =====================================================
   MAIN
===================================================== */

main {

    width: min(1200px, 94%);

    margin: 25px auto 40px;
}


/* =====================================================
   STAT CARDS
===================================================== */

.stats {

    display: grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap: 15px;
}

.stat {

    background: #ffffff;

    border: 1px solid #dceaf1;

    border-radius: 16px;

    padding: 20px;

    box-shadow:
        0 5px 18px
        rgba(50,100,130,.07);
}

.stat-title {

    color: #78909e;

    font-size: 13px;
}

.stat-number {

    margin-top: 8px;

    font-size: 32px;

    font-weight: 800;

    color: #f97316;
}

.stat-unit {

    color: #9aabb5;

    font-size: 12px;
}


/* =====================================================
   SECTION
===================================================== */

.section-title {

    margin: 22px 0 12px;

    font-size: 18px;

    font-weight: 700;

    color: #234b62;
}


/* =====================================================
   SHRIMP CARDS
===================================================== */

.shrimp-cards {

    display: grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap: 15px;
}

.shrimp-card {

    background: #ffffff;

    border-radius: 16px;

    padding: 20px;

    border: 1px solid #dceaf1;

    box-shadow:
        0 5px 18px
        rgba(50,100,130,.07);

    position: relative;

    overflow: hidden;
}

.shrimp-card::before {

    content: "";

    position: absolute;

    left: 0;

    top: 0;

    width: 5px;

    height: 100%;
}

.small::before {

    background: #22c55e;
}

.medium::before {

    background: #0ea5e9;
}

.large::before {

    background: #f97316;
}

.sick::before {

    background: #ef4444;
}

.shrimp-top {

    display: flex;

    justify-content: space-between;

    align-items: center;
}

.shrimp-name {

    font-weight: 700;

    color: #31576b;
}

.shrimp-icon {

    font-size: 26px;
}

.shrimp-number {

    margin-top: 10px;

    font-size: 34px;

    font-weight: 800;
}

.small .shrimp-number {

    color: #16a34a;
}

.medium .shrimp-number {

    color: #0284c7;
}

.large .shrimp-number {

    color: #ea580c;
}

.sick .shrimp-number {

    color: #dc2626;
}

.percent {

    margin-top: 4px;

    color: #8196a2;

    font-size: 12px;
}


/* =====================================================
   PANEL
===================================================== */

.panel {

    background: #ffffff;

    border: 1px solid #dceaf1;

    border-radius: 16px;

    margin-top: 18px;

    padding: 20px;

    box-shadow:
        0 5px 18px
        rgba(50,100,130,.07);
}

.panel-header {

    display: flex;

    align-items: center;

    justify-content: space-between;

    gap: 10px;

    margin-bottom: 15px;
}

.panel-header h2 {

    margin: 0;

    font-size: 18px;

    color: #234b62;
}

.badge {

    padding: 6px 12px;

    border-radius: 20px;

    background: #eaf8ef;

    color: #15803d;

    font-size: 12px;

    font-weight: 600;
}


/* =====================================================
   DETAIL
===================================================== */

.details {

    display: grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap: 10px;
}

.detail {

    padding: 13px;

    border-radius: 10px;

    background: #f7fafc;

    border: 1px solid #e4eef3;
}

.detail-label {

    color: #8398a4;

    font-size: 11px;
}

.detail-value {

    margin-top: 5px;

    color: #31576b;

    font-weight: 700;

    font-size: 15px;
}


/* =====================================================
   BAR CHART
===================================================== */

.chart-row {

    margin-top: 16px;
}

.chart-label {

    display: flex;

    justify-content: space-between;

    margin-bottom: 6px;

    font-size: 13px;

    color: #506b7a;
}

.bar-bg {

    width: 100%;

    height: 13px;

    background: #edf3f6;

    border-radius: 20px;

    overflow: hidden;
}

.bar {

    height: 100%;

    border-radius: 20px;

    transition:
        width .5s ease;
}

.bar-small {

    background: #22c55e;
}

.bar-medium {

    background: #0ea5e9;
}

.bar-large {

    background: #f97316;
}

.bar-sick {

    background: #ef4444;
}


/* =====================================================
   HISTORY TABLE
===================================================== */

.table-wrap {

    width: 100%;

    overflow-x: auto;
}

table {

    width: 100%;

    min-width: 850px;

    border-collapse: collapse;
}

th {

    padding: 13px;

    text-align: left;

    background: #f3f8fb;

    color: #67818f;

    font-size: 12px;

    border-bottom:
        1px solid #dceaf1;
}

td {

    padding: 13px;

    color: #506b7a;

    font-size: 13px;

    border-bottom:
        1px solid #edf2f5;
}

tr:hover td {

    background: #f9fcfe;
}

.round {

    color: #0284c7;

    font-weight: 700;
}

.total {

    color: #ea580c;

    font-weight: 800;
}

.sick-value {

    color: #dc2626;

    font-weight: 700;
}

.empty {

    text-align: center;

    color: #94a8b3;

    padding: 45px;
}


/* =====================================================
   FOOTER
===================================================== */

footer {

    text-align: center;

    color: #8ba0ab;

    font-size: 12px;

    padding: 5px 0 35px;
}


/* =====================================================
   RESPONSIVE
===================================================== */

@media(max-width:1000px) {

    .stats {

        grid-template-columns:
            repeat(2, 1fr);
    }

    .shrimp-cards {

        grid-template-columns:
            repeat(2, 1fr);
    }

    .details {

        grid-template-columns:
            repeat(2, 1fr);
    }
}

@media(max-width:600px) {

    header {

        padding: 15px;
    }

    .stats {

        grid-template-columns: 1fr;
    }

    .shrimp-cards {

        grid-template-columns: 1fr;
    }

    .details {

        grid-template-columns: 1fr;
    }

    .logo h1 {

        font-size: 18px;
    }

    main {

        width: 94%;
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

<h1>
ระบบคัดแยกกุ้ง AI
</h1>

<p>
Shrimp Size Sorting & Health Detection
</p>

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
📷 กล้อง Real-time
</a>

</nav>

</header>


<main>


<!-- =====================================================
     TOP STATISTICS
===================================================== -->

<div class="stats">


<div class="stat">

<div class="stat-title">
รอบล่าสุด
</div>

<div
id="round"
class="stat-number"
>
-
</div>

<div class="stat-unit">
รอบการคัด
</div>

</div>


<div class="stat">

<div class="stat-title">
กุ้งทั้งหมด
</div>

<div
id="total"
class="stat-number"
>
-
</div>

<div class="stat-unit">
ตัว
</div>

</div>


<div class="stat">

<div class="stat-title">
FPS เฉลี่ย
</div>

<div
id="fps"
class="stat-number"
>
-
</div>

<div class="stat-unit">
Frames / Second
</div>

</div>


<div class="stat">

<div class="stat-title">
เวลาทำงาน
</div>

<div
id="duration"
class="stat-number"
>
-
</div>

<div class="stat-unit">
วินาที
</div>

</div>


</div>


<!-- =====================================================
     SHRIMP TYPES
===================================================== -->

<div class="section-title">
🦐 ผลการคัดแยกกุ้ง
</div>


<div class="shrimp-cards">


<!-- SMALL -->

<div class="shrimp-card small">

<div class="shrimp-top">

<div class="shrimp-name">
กุ้งเล็ก
</div>

<div class="shrimp-icon">
🦐
</div>

</div>

<div
id="smallCount"
class="shrimp-number"
>
0
</div>

<div
id="smallPercent"
class="percent"
>
0% ของทั้งหมด
</div>

</div>


<!-- MEDIUM -->

<div class="shrimp-card medium">

<div class="shrimp-top">

<div class="shrimp-name">
กุ้งกลาง
</div>

<div class="shrimp-icon">
🦐
</div>

</div>

<div
id="mediumCount"
class="shrimp-number"
>
0
</div>

<div
id="mediumPercent"
class="percent"
>
0% ของทั้งหมด
</div>

</div>


<!-- LARGE -->

<div class="shrimp-card large">

<div class="shrimp-top">

<div class="shrimp-name">
กุ้งใหญ่
</div>

<div class="shrimp-icon">
🦐
</div>

</div>

<div
id="largeCount"
class="shrimp-number"
>
0
</div>

<div
id="largePercent"
class="percent"
>
0% ของทั้งหมด
</div>

</div>


<!-- SICK -->

<div class="shrimp-card sick">

<div class="shrimp-top">

<div class="shrimp-name">
กุ้งป่วย
</div>

<div class="shrimp-icon">
🩺
</div>

</div>

<div
id="sickCount"
class="shrimp-number"
>
0
</div>

<div
id="sickPercent"
class="percent"
>
0% ของทั้งหมด
</div>

</div>


</div>


<!-- =====================================================
     LATEST ROUND
===================================================== -->

<div class="panel">

<div class="panel-header">

<h2>
📋 สรุปผลรอบล่าสุด
</h2>

<div
id="badge"
class="badge"
>
รอข้อมูลจาก AI
</div>

</div>


<div class="details">


<div class="detail">

<div class="detail-label">
หมายเลขรอบ
</div>

<div
id="detailRound"
class="detail-value"
>
-
</div>

</div>


<div class="detail">

<div class="detail-label">
จำนวนเฟรม
</div>

<div
id="frames"
class="detail-value"
>
-
</div>

</div>


<div class="detail">

<div class="detail-label">
เวลาเริ่ม
</div>

<div
id="started"
class="detail-value"
>
-
</div>

</div>


<div class="detail">

<div class="detail-label">
เวลาจบ
</div>

<div
id="finished"
class="detail-value"
>
-
</div>

</div>


</div>


<!-- =====================================================
     BAR CHART
===================================================== -->

<div class="chart-row">

<div class="chart-label">

<span>
🟢 กุ้งเล็ก
</span>

<b id="smallBarText">
0 ตัว
</b>

</div>

<div class="bar-bg">

<div
id="smallBar"
class="bar bar-small"
style="width:0%"
>
</div>

</div>

</div>


<div class="chart-row">

<div class="chart-label">

<span>
🔵 กุ้งกลาง
</span>

<b id="mediumBarText">
0 ตัว
</b>

</div>

<div class="bar-bg">

<div
id="mediumBar"
class="bar bar-medium"
style="width:0%"
>
</div>

</div>

</div>


<div class="chart-row">

<div class="chart-label">

<span>
🟠 กุ้งใหญ่
</span>

<b id="largeBarText">
0 ตัว
</b>

</div>

<div class="bar-bg">

<div
id="largeBar"
class="bar bar-large"
style="width:0%"
>
</div>

</div>

</div>


<div class="chart-row">

<div class="chart-label">

<span>
🔴 กุ้งป่วย
</span>

<b id="sickBarText">
0 ตัว
</b>

</div>

<div class="bar-bg">

<div
id="sickBar"
class="bar bar-sick"
style="width:0%"
>
</div>

</div>

</div>


</div>


<!-- =====================================================
     HISTORY
===================================================== -->

<div class="panel">

<div class="panel-header">

<h2>
📚 ประวัติการคัดกุ้ง
</h2>

</div>


<div class="table-wrap">

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

<th>
FPS
</th>

<th>
เวลา
</th>

</tr>

</thead>


<tbody id="history">

<tr>

<td
colspan="8"
class="empty"
>
ยังไม่มีข้อมูลจาก AI
</td>

</tr>

</tbody>

</table>

</div>

</div>


</main>


<footer>

🦐 Shrimp AI Sorting System

</footer>


<script>


// =========================================================
// HTML ESCAPE
// =========================================================

function esc(value) {

    return String(value)
        .replace(
            /[&<>"']/g,
            function(c) {

                return {
                    "&": "&amp;",
                    "<": "&lt;",
                    ">": "&gt;",
                    '"': "&quot;",
                    "'": "&#039;"
                }[c];

            }
        );

}


// =========================================================
// PERCENT
// =========================================================

function getPercent(
    value,
    total
) {

    if (total <= 0) {

        return 0;

    }

    return (
        value / total * 100
    ).toFixed(1);

}


// =========================================================
// UPDATE DASHBOARD
// =========================================================

async function updateDashboard() {

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

        const latest =
            data.latest;


        // ไม่มีรอบ
        if (!latest) {

            return;

        }


        // =================================================
        // BASIC
        // =================================================

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
                latest.duration;


        document
            .getElementById("detailRound")
            .textContent =
                "#" + latest.round_id;


        document
            .getElementById("frames")
            .textContent =
                latest.frames;


        document
            .getElementById("started")
            .textContent =
                latest.started_at || "-";


        document
            .getElementById("finished")
            .textContent =
                latest.finished_at || "-";


        document
            .getElementById("badge")
            .textContent =
                "✓ AI ส่งผลแล้ว";


        // =================================================
        // COUNTS
        // =================================================

        const counts =
            latest.counts || {};


        const small =
            Number(
                counts["กุ้งเล็ก"] || 0
            );


        const medium =
            Number(
                counts["กุ้งกลาง"] || 0
            );


        const large =
            Number(
                counts["กุ้งใหญ่"] || 0
            );


        const sick =
            Number(
                counts["กุ้งป่วย"] || 0
            );


        const total =
            small +
            medium +
            large +
            sick;


        // =================================================
        // CARDS
        // =================================================

        document
            .getElementById("smallCount")
            .textContent =
                small;


        document
            .getElementById("mediumCount")
            .textContent =
                medium;


        document
            .getElementById("largeCount")
            .textContent =
                large;


        document
            .getElementById("sickCount")
            .textContent =
                sick;


        // =================================================
        // PERCENT
        // =================================================

        document
            .getElementById("smallPercent")
            .textContent =
                getPercent(
                    small,
                    total
                )
                + "% ของทั้งหมด";


        document
            .getElementById("mediumPercent")
            .textContent =
                getPercent(
                    medium,
                    total
                )
                + "% ของทั้งหมด";


        document
            .getElementById("largePercent")
            .textContent =
                getPercent(
                    large,
                    total
                )
                + "% ของทั้งหมด";


        document
            .getElementById("sickPercent")
            .textContent =
                getPercent(
                    sick,
                    total
                )
                + "% ของทั้งหมด";


        // =================================================
        // BARS
        // =================================================

        document
            .getElementById("smallBar")
            .style.width =
                getPercent(
                    small,
                    total
                ) + "%";


        document
            .getElementById("mediumBar")
            .style.width =
                getPercent(
                    medium,
                    total
                ) + "%";


        document
            .getElementById("largeBar")
            .style.width =
                getPercent(
                    large,
                    total
                ) + "%";


        document
            .getElementById("sickBar")
            .style.width =
                getPercent(
                    sick,
                    total
                ) + "%";


        document
            .getElementById("smallBarText")
            .textContent =
                small + " ตัว";


        document
            .getElementById("mediumBarText")
            .textContent =
                medium + " ตัว";


        document
            .getElementById("largeBarText")
            .textContent =
                large + " ตัว";


        document
            .getElementById("sickBarText")
            .textContent =
                sick + " ตัว";


        // =================================================
        // HISTORY
        // =================================================

        const tbody =
            document.getElementById(
                "history"
            );


        if (
            !data.history ||
            data.history.length === 0
        ) {

            tbody.innerHTML = `

                <tr>

                    <td
                        colspan="8"
                        class="empty"
                    >
                        ยังไม่มีข้อมูลจาก AI
                    </td>

                </tr>

            `;

            return;

        }


        tbody.innerHTML =
            data.history
                .map(
                    function(item) {

                        const c =
                            item.counts || {};


                        const s =
                            Number(
                                c["กุ้งเล็ก"] || 0
                            );


                        const m =
                            Number(
                                c["กุ้งกลาง"] || 0
                            );


                        const l =
                            Number(
                                c["กุ้งใหญ่"] || 0
                            );


                        const si =
                            Number(
                                c["กุ้งป่วย"] || 0
                            );


                        return `

                        <tr>

                            <td>

                                <span
                                    class="round"
                                >
                                    #${esc(
                                        item.round_id
                                    )}
                                </span>

                            </td>

                            <td>
                                ${s} ตัว
                            </td>

                            <td>
                                ${m} ตัว
                            </td>

                            <td>
                                ${l} ตัว
                            </td>

                            <td>

                                <span
                                    class="sick-value"
                                >
                                    ${si} ตัว
                                </span>

                            </td>

                            <td>

                                <span
                                    class="total"
                                >
                                    ${item.total} ตัว
                                </span>

                            </td>

                            <td>
                                ${item.avg_fps}
                            </td>

                            <td>
                                ${item.duration}s
                            </td>

                        </tr>

                        `;

                    }
                )
                .join("");


    } catch (error) {

        console.log(
            "Dashboard error:",
            error
        );

    }

}


// =========================================================
// START
// =========================================================

updateDashboard();


setInterval(
    updateDashboard,
    2000
);

</script>


</body>

</html>
"""


# =========================================================
# PAGE 2
# LIVE CAMERA
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

<title>กล้อง Real-time - ระบบคัดแยกกุ้ง</title>

<style>

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    background: #f5f9fc;

    color: #183247;

    font-family:
        "Noto Sans Thai",
        "Segoe UI",
        Arial,
        sans-serif;
}


/* HEADER */

header {

    background: #ffffff;

    border-bottom:
        1px solid #dbeaf2;

    padding: 18px 30px;

    display: flex;

    justify-content: space-between;

    align-items: center;

    gap: 15px;

    flex-wrap: wrap;

    box-shadow:
        0 3px 15px
        rgba(40,90,120,.08);
}

h1 {

    margin: 0;

    color: #16435d;

    font-size: 22px;
}

nav {

    display: flex;

    gap: 8px;
}

nav a {

    text-decoration: none;

    color: #506b7a;

    padding: 9px 15px;

    border-radius: 9px;

    border: 1px solid #d5e5ed;

    background: #ffffff;
}

nav a.active {

    background: #0ea5e9;

    border-color: #0ea5e9;

    color: #ffffff;
}


/* MAIN */

main {

    width: min(1100px,94%);

    margin: 25px auto;
}


/* CAMERA */

.camera {

    background: #ffffff;

    border: 1px solid #dceaf1;

    border-radius: 16px;

    padding: 18px;

    box-shadow:
        0 5px 18px
        rgba(50,100,130,.08);
}

.video {

    width: 100%;

    aspect-ratio: 16 / 9;

    background: #eef5f8;

    border-radius: 12px;

    overflow: hidden;

    display: flex;

    align-items: center;

    justify-content: center;

    border: 1px solid #dbe9ef;
}

#frame {

    width: 100%;

    height: 100%;

    object-fit: contain;

    display: none;
}

.placeholder {

    color: #7d96a4;

    text-align: center;

    font-size: 14px;
}

.placeholder-icon {

    font-size: 55px;

    margin-bottom: 10px;
}


/* STATUS */

.status {

    margin-top: 13px;

    padding: 12px 15px;

    border-radius: 10px;

    background: #fff1f1;

    border: 1px solid #ffd6d6;

    color: #dc2626;

    font-size: 13px;
}

.status.online {

    background: #edfff4;

    border-color: #c8efd8;

    color: #15803d;
}

</style>

</head>


<body>


<header>

<h1>
🦐 กล้องคัดแยกกุ้ง Real-time
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

<div class="placeholder-icon">
📷
</div>

กำลังรอสัญญาณจาก AI...

</div>

</div>


<div
    id="status"
    class="status"
>
● กำลังรอสัญญาณจากกล้อง
</div>

</div>

</main>


<script>


async function updateCamera() {

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


        const frame =
            document.getElementById(
                "frame"
            );


        const placeholder =
            document.getElementById(
                "placeholder"
            );


        if (data.online) {

            status.className =
                "status online";

            status.textContent =
                "● กล้องออนไลน์";


            if (data.has_frame) {

                frame.src =
                    "/api/live/frame?t="
                    + Date.now();

                frame.style.display =
                    "block";

                placeholder.style.display =
                    "none";

            }

        } else {

            status.className =
                "status";

            status.textContent =
                "● รอสัญญาณจากกล้อง";

        }


    } catch (error) {

        console.log(error);

    }

}


updateCamera();


setInterval(
    updateCamera,
    1000
);

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
