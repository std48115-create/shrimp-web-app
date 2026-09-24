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
    version="3.0.0"
)

# ประเภทกุ้งที่ระบบรองรับ
SHRIMP_TYPES = [
    "กุ้งเล็ก",
    "กุ้งกลาง",
    "กุ้งใหญ่"
]

# =========================================================
# MEMORY
# =========================================================

latest_round = None
round_history = deque(maxlen=100)
live_frame = None
live_ts = 0.0

# =========================================================
# DATA MODEL
# =========================================================

class RoundReport(BaseModel):
    round_id: int = 0
    counts: dict[str, int] = Field(default_factory=dict)
    avg_fps: float = 0.0
    duration: float = 0.0
    frames: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    frame_b64: str | None = None


class LiveReport(BaseModel):
    counts: dict[str, int] = Field(default_factory=dict)
    fps: float = 0.0
    frame_b64: str | None = None

# =========================================================
# CLEAN SHRIMP COUNTS
# =========================================================

def clean_counts(raw_counts):
    result = {}
    for shrimp_type in SHRIMP_TYPES:
        value = raw_counts.get(shrimp_type, 0)
        try:
            value = int(value)
        except Exception:
            value = 0
        if value < 0:
            value = 0
        result[shrimp_type] = value
    return result

# =========================================================
# RECEIVE COMPLETED ROUND
# =========================================================

@app.post("/api/round")
def receive_round(
    data: RoundReport,
    x_api_key: str = Header(default="")
):
    global latest_round, live_frame, live_ts

    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    counts = clean_counts(data.counts)
    total = sum(counts.values())

    result = {
        "round_id": int(data.round_id),
        "counts": counts,
        "total": total,
        "avg_fps": round(max(0, float(data.avg_fps)), 2),
        "duration": round(max(0, float(data.duration)), 2),
        "frames": max(0, int(data.frames)),
        "started_at": data.started_at,
        "finished_at": data.finished_at,
        "received_at": time.time()
    }

    latest_round = result
    round_history.appendleft(result)

    if data.frame_b64:
        try:
            live_frame = base64.b64decode(data.frame_b64, validate=True)
            live_ts = time.time()
        except Exception:
            pass

    return {"ok": True, "round_id": data.round_id, "counts": counts, "total": total}

# =========================================================
# RECEIVE LIVE CAMERA
# =========================================================

@app.post("/api/live")
def receive_live(
    data: LiveReport,
    x_api_key: str = Header(default="")
):
    global live_frame, live_ts

    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if data.frame_b64:
        try:
            live_frame = base64.b64decode(data.frame_b64, validate=True)
            live_ts = time.time()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid image")

    return {"ok": True}

# =========================================================
# DASHBOARD API
# =========================================================

@app.get("/api/dashboard")
def dashboard():
    return {
        "has_round": latest_round is not None,
        "latest": latest_round,
        "history": list(round_history),
        "shrimp_types": SHRIMP_TYPES
    }

# =========================================================
# LIVE STATUS
# =========================================================

@app.get("/api/live/status")
def live_status():
    if live_ts == 0:
        return {"online": False, "age": 0, "has_frame": False}

    age = time.time() - live_ts
    return {
        "online": age < 10,
        "age": age,
        "has_frame": live_frame is not None
    }

# =========================================================
# LIVE FRAME
# =========================================================

@app.get("/api/live/frame")
def get_live_frame():
    if live_frame is None:
        return Response(status_code=204)

    return Response(
        live_frame,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"}
    )

# =========================================================
# PAGE 1 - DASHBOARD
# =========================================================

DASHBOARD_PAGE = r"""
<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Shrimp Sorting Vision Pro</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
    --bg-main: #0f172a;
    --bg-card: rgba(30, 41, 59, 0.7);
    --border-card: rgba(255, 255, 255, 0.08);
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --accent-blue: #38bdf8;
    --accent-green: #22c55e;
    --accent-orange: #f97316;
    --accent-purple: #a855f7;
    --shadow-glow: 0 0 25px rgba(56, 189, 248, 0.15);
}

* {
    box-sizing: border-box;
    font-family: 'Kanit', sans-serif;
    transition: all 0.25s ease;
}

body {
    margin: 0;
    background: radial-gradient(circle at top right, #1e1b4b, #0f172a 60%);
    color: var(--text-primary);
    min-height: 100vh;
}

/* HEADER */
header {
    background: rgba(15, 23, 42, 0.75);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--border-card);
    padding: 16px 40px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 100;
}

.logo {
    display: flex;
    align-items: center;
    gap: 16px;
}

.logo-icon {
    width: 48px;
    height: 48px;
    border-radius: 14px;
    background: linear-gradient(135deg, #0284c7, #0d9488);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 26px;
    box-shadow: 0 0 15px rgba(14, 165, 233, 0.4);
}

.logo h1 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
    letter-spacing: 0.5px;
    background: linear-gradient(to right, #ffffff, #93c5fd);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.logo p {
    margin: 2px 0 0;
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 300;
}

nav {
    display: flex;
    gap: 10px;
}

nav a {
    text-decoration: none;
    color: var(--text-secondary);
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-card);
    padding: 8px 18px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 400;
    display: flex;
    align-items: center;
    gap: 8px;
}

nav a:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
    transform: translateY(-2px);
}

nav a.active {
    color: #fff;
    background: linear-gradient(135deg, #0284c7, #2563eb);
    border-color: transparent;
    box-shadow: 0 4px 12px rgba(2, 132, 199, 0.3);
}

/* MAIN */
main {
    width: min(1280px, 92%);
    margin: 32px auto 60px;
}

/* STATS GRID */
.stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 20px;
}

.stat {
    background: var(--bg-card);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-card);
    border-radius: 20px;
    padding: 22px;
    position: relative;
    overflow: hidden;
}

.stat:hover {
    transform: translateY(-4px);
    border-color: rgba(56, 189, 248, 0.3);
    box-shadow: var(--shadow-glow);
}

.stat-title {
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 400;
}

.stat-number {
    margin-top: 10px;
    font-size: 36px;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1;
}

.stat-unit {
    color: #64748b;
    font-size: 12px;
    margin-top: 8px;
    font-weight: 300;
}

/* CARDS BY SIZE */
.size-section {
    margin-top: 32px;
}

.section-title {
    margin-bottom: 16px;
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 10px;
}

.size-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 20px;
}

.size-card {
    background: var(--bg-card);
    backdrop-filter: blur(12px);
    border-radius: 20px;
    padding: 24px;
    border: 1px solid var(--border-card);
    position: relative;
}

.size-card:hover {
    transform: translateY(-4px);
}

.size-card.small { border-top: 4px solid var(--accent-green); }
.size-card.medium { border-top: 4px solid var(--accent-blue); }
.size-card.large { border-top: 4px solid var(--accent-orange); }

.size-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.size-name {
    font-weight: 500;
    font-size: 16px;
    color: var(--text-secondary);
}

.size-number {
    font-size: 42px;
    font-weight: 700;
    margin-top: 12px;
    line-height: 1;
}

.small .size-number { color: var(--accent-green); }
.medium .size-number { color: var(--accent-blue); }
.large .size-number { color: var(--accent-orange); }

.size-percent {
    color: #64748b;
    font-size: 13px;
    margin-top: 8px;
    font-weight: 300;
}

/* PANELS */
.panel {
    background: var(--bg-card);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-card);
    border-radius: 20px;
    margin-top: 24px;
    padding: 28px;
}

.panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 20px;
}

.panel-header h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
}

.badge {
    background: rgba(34, 197, 94, 0.15);
    color: var(--accent-green);
    border: 1px solid rgba(34, 197, 94, 0.3);
    border-radius: 30px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 6px;
}

.badge::before {
    content: "";
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent-green);
    box-shadow: 0 0 8px var(--accent-green);
}

/* DETAILS GRID */
.detail-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
}

.detail {
    background: rgba(15, 23, 42, 0.5);
    border: 1px solid var(--border-card);
    border-radius: 14px;
    padding: 16px;
}

.detail-label {
    font-size: 12px;
    color: var(--text-secondary);
    font-weight: 300;
}

.detail-value {
    margin-top: 6px;
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
}

/* BAR CHART */
.chart {
    margin-top: 24px;
}

.bar-row {
    margin: 18px 0;
}

.bar-label {
    display: flex;
    justify-content: space-between;
    font-size: 14px;
    margin-bottom: 8px;
    color: var(--text-secondary);
}

.bar-bg {
    width: 100%;
    height: 10px;
    background: rgba(15, 23, 42, 0.6);
    border-radius: 20px;
    overflow: hidden;
    border: 1px solid var(--border-card);
}

.bar {
    height: 100%;
    border-radius: 20px;
    transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

.bar-small { background: linear-gradient(90deg, #16a34a, var(--accent-green)); }
.bar-medium { background: linear-gradient(90deg, #0284c7, var(--accent-blue)); }
.bar-large { background: linear-gradient(90deg, #ea580c, var(--accent-orange)); }

/* TABLE */
.table-wrapper {
    width: 100%;
    overflow-x: auto;
}

table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    min-width: 700px;
}

th {
    background: rgba(15, 23, 42, 0.6);
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 500;
    padding: 14px 18px;
    text-align: left;
    border-bottom: 1px solid var(--border-card);
}

th:first-child { border-radius: 12px 0 0 12px; }
th:last-child { border-radius: 0 12px 12px 0; }

td {
    padding: 16px 18px;
    font-size: 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.03);
    color: var(--text-primary);
}

tr:hover td {
    background: rgba(255, 255, 255, 0.02);
}

.round-number {
    color: var(--accent-blue);
    font-weight: 600;
}

.total-cell {
    color: var(--accent-orange);
    font-weight: 600;
}

.empty {
    text-align: center;
    padding: 50px 10px;
    color: #475569;
    font-weight: 300;
}

footer {
    text-align: center;
    padding: 20px 0 40px;
    color: #475569;
    font-size: 13px;
    font-weight: 300;
}

@media(max-width: 768px) {
    header { padding: 16px 20px; }
    main { width: 94%; }
}
</style>
</head>

<body>

<header>
    <div class="logo">
        <div class="logo-icon">🦐</div>
        <div>
            <h1>ระบบคัดแยกกุ้ง AI Pro</h1>
            <p>Smart Shrimp Sorting & Analytics Dashboard</p>
        </div>
    </div>
    <nav>
        <a href="/" class="active">📊 สรุปผล</a>
        <a href="/live">📷 กล้อง Live</a>
    </nav>
</header>

<main>
    <!-- TOP STATS -->
    <div class="stats">
        <div class="stat">
            <div class="stat-title">รอบคัดแยกล่าสุด</div>
            <div id="round" class="stat-number">-</div>
            <div class="stat-unit">Round ID</div>
        </div>
        <div class="stat">
            <div class="stat-title">จำนวนรวมทั้งหมด</div>
            <div id="total" class="stat-number">-</div>
            <div class="stat-unit">ตัว (Shrimps)</div>
        </div>
        <div class="stat">
            <div class="stat-title">ความเร็วการประมวลผล</div>
            <div id="fps" class="stat-number">-</div>
            <div class="stat-unit">FPS Average</div>
        </div>
        <div class="stat">
            <div class="stat-title">เวลาที่ใช้ไป</div>
            <div id="duration" class="stat-number">-</div>
            <div class="stat-unit">วินาที (Seconds)</div>
        </div>
    </div>

    <!-- SIZE CARDS -->
    <div class="size-section">
        <div class="section-title">🦐 สรุปจำนวนแยกตามขนาด</div>
        <div class="size-cards">
            <div class="size-card small">
                <div class="size-top">
                    <span class="size-name">กุ้งเล็ก (Small)</span>
                    <span>🟢</span>
                </div>
                <div id="smallCount" class="size-number">0</div>
                <div id="smallPercent" class="size-percent">0% ของทั้งหมด</div>
            </div>
            <div class="size-card medium">
                <div class="size-top">
                    <span class="size-name">กุ้งกลาง (Medium)</span>
                    <span>🔵</span>
                </div>
                <div id="mediumCount" class="size-number">0</div>
                <div id="mediumPercent" class="size-percent">0% ของทั้งหมด</div>
            </div>
            <div class="size-card large">
                <div class="size-top">
                    <span class="size-name">กุ้งใหญ่ (Large)</span>
                    <span>🟠</span>
                </div>
                <div id="largeCount" class="size-number">0</div>
                <div id="largePercent" class="size-percent">0% ของทั้งหมด</div>
            </div>
        </div>
    </div>

    <!-- LATEST DETAILS -->
    <div class="panel">
        <div class="panel-header">
            <h2>📋 ข้อมูลประมวลผลรอบล่าสุด</h2>
            <div id="badge" class="badge">รอข้อมูลจากระบบ</div>
        </div>

        <div class="detail-grid">
            <div class="detail">
                <div class="detail-label">รอบการทำงาน</div>
                <div id="detailRound" class="detail-value">-</div>
            </div>
            <div class="detail">
                <div class="detail-label">จำนวนเฟรมภาพ</div>
                <div id="frames" class="detail-value">-</div>
            </div>
            <div class="detail">
                <div class="detail-label">เวลาเริ่มต้น</div>
                <div id="started" class="detail-value">-</div>
            </div>
            <div class="detail">
                <div class="detail-label">เวลาที่สิ้นสุด</div>
                <div id="finished" class="detail-value">-</div>
            </div>
        </div>

        <!-- PROGRESS BARS -->
        <div class="chart">
            <div class="bar-row">
                <div class="bar-label">
                    <span>🟢 กุ้งเล็ก</span>
                    <b id="smallBarText">0 ตัว</b>
                </div>
                <div class="bar-bg">
                    <div id="smallBar" class="bar bar-small" style="width:0%"></div>
                </div>
            </div>

            <div class="bar-row">
                <div class="bar-label">
                    <span>🔵 กุ้งกลาง</span>
                    <b id="mediumBarText">0 ตัว</b>
                </div>
                <div class="bar-bg">
                    <div id="mediumBar" class="bar bar-medium" style="width:0%"></div>
                </div>
            </div>

            <div class="bar-row">
                <div class="bar-label">
                    <span>🟠 กุ้งใหญ่</span>
                    <b id="largeBarText">0 ตัว</b>
                </div>
                <div class="bar-bg">
                    <div id="largeBar" class="bar bar-large" style="width:0%"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- HISTORY TABLE -->
    <div class="panel">
        <div class="panel-header">
            <h2>📚 ประวัติการตรวจคัดแยก</h2>
        </div>

        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>รอบที่</th>
                        <th>กุ้งเล็ก</th>
                        <th>กุ้งกลาง</th>
                        <th>กุ้งใหญ่</th>
                        <th>รวมทั้งหมด</th>
                        <th>FPS</th>
                        <th>ระยะเวลา</th>
                    </tr>
                </thead>
                <tbody id="history">
                    <tr>
                        <td colspan="7" class="empty">กำลังโหลดประวัติการทำงาน...</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</main>

<footer>
    🦐 AI-Powered Shrimp Sorting System &copy; 2026 DEKTECH Vision Workstation
</footer>

<script>
function esc(value) {
    return String(value).replace(/[&<>"']/g, function(c) {
        return {
            "&": "&amp;", "<": "&lt;", ">": "&gt;",
            '"': "&quot;", "'": "&#039;"
        }[c];
    });
}

async function updateDashboard() {
    try {
        const response = await fetch("/api/dashboard", { cache: "no-store" });
        const data = await response.json();
        const latest = data.latest;

        if (!latest) return;

        document.getElementById("round").textContent = latest.round_id;
        document.getElementById("total").textContent = latest.total.toLocaleString();
        document.getElementById("fps").textContent = latest.avg_fps;
        document.getElementById("duration").textContent = latest.duration + "s";
        document.getElementById("detailRound").textContent = "#" + latest.round_id;
        document.getElementById("frames").textContent = latest.frames.toLocaleString();
        document.getElementById("started").textContent = latest.started_at || "-";
        document.getElementById("finished").textContent = latest.finished_at || "-";
        document.getElementById("badge").textContent = "อัปเดตแล้ว";

        const counts = latest.counts || {};
        const small = Number(counts["กุ้งเล็ก"] || 0);
        const medium = Number(counts["กุ้งกลาง"] || 0);
        const large = Number(counts["กุ้งใหญ่"] || 0);
        const total = small + medium + large;

        document.getElementById("smallCount").textContent = small.toLocaleString();
        document.getElementById("mediumCount").textContent = medium.toLocaleString();
        document.getElementById("largeCount").textContent = large.toLocaleString();

        function percent(val) {
            return total <= 0 ? 0 : ((val / total) * 100).toFixed(1);
        }

        document.getElementById("smallPercent").textContent = percent(small) + "% ของทั้งหมด";
        document.getElementById("mediumPercent").textContent = percent(medium) + "% ของทั้งหมด";
        document.getElementById("largePercent").textContent = percent(large) + "% ของทั้งหมด";

        document.getElementById("smallBar").style.width = percent(small) + "%";
        document.getElementById("mediumBar").style.width = percent(medium) + "%";
        document.getElementById("largeBar").style.width = percent(large) + "%";

        document.getElementById("smallBarText").textContent = small.toLocaleString() + " ตัว";
        document.getElementById("mediumBarText").textContent = medium.toLocaleString() + " ตัว";
        document.getElementById("largeBarText").textContent = large.toLocaleString() + " ตัว";

        const tbody = document.getElementById("history");
        if (!data.history || data.history.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="empty">ยังไม่มีข้อมูลการประมวลผล</td></tr>`;
            return;
        }

        tbody.innerHTML = data.history.map(item => {
            const c = item.counts || {};
            const s = Number(c["กุ้งเล็ก"] || 0);
            const m = Number(c["กุ้งกลาง"] || 0);
            const l = Number(c["กุ้งใหญ่"] || 0);
            return `
                <tr>
                    <td><span class="round-number">#${esc(item.round_id)}</span></td>
                    <td>${s.toLocaleString()} ตัว</td>
                    <td>${m.toLocaleString()} ตัว</td>
                    <td>${l.toLocaleString()} ตัว</td>
                    <td><span class="total-cell">${item.total.toLocaleString()} ตัว</span></td>
                    <td>${item.avg_fps}</td>
                    <td>${item.duration}s</td>
                </tr>
            `;
        }).join("");

    } catch (error) {
        console.error("Dashboard error:", error);
    }
}

updateDashboard();
setInterval(updateDashboard, 2000);
</script>
</body>
</html>
"""

# =========================================================
# PAGE 2 - LIVE CAMERA
# =========================================================

LIVE_PAGE = r"""
<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Live Camera - AI Shrimp Vision</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
    --bg-main: #0f172a;
    --bg-card: rgba(30, 41, 59, 0.7);
    --border-card: rgba(255, 255, 255, 0.08);
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --accent-blue: #38bdf8;
    --accent-red: #ef4444;
    --accent-green: #22c55e;
}

* {
    box-sizing: border-box;
    font-family: 'Kanit', sans-serif;
    transition: all 0.25s ease;
}

body {
    margin: 0;
    background: radial-gradient(circle at top right, #1e1b4b, #0f172a 60%);
    color: var(--text-primary);
    min-height: 100vh;
}

header {
    background: rgba(15, 23, 42, 0.75);
    backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--border-card);
    padding: 16px 40px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 100;
}

h1 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
    background: linear-gradient(to right, #ffffff, #93c5fd);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

nav {
    display: flex;
    gap: 10px;
}

nav a {
    text-decoration: none;
    color: var(--text-secondary);
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-card);
    padding: 8px 18px;
    border-radius: 12px;
    font-size: 14px;
}

nav a:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
}

nav a.active {
    color: #fff;
    background: linear-gradient(135deg, #0284c7, #2563eb);
    border-color: transparent;
}

main {
    width: min(1100px, 92%);
    margin: 32px auto;
}

.camera-card {
    background: var(--bg-card);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-card);
    border-radius: 24px;
    padding: 24px;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
}

.video-container {
    width: 100%;
    aspect-ratio: 16/9;
    background: #020617;
    border-radius: 16px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border-card);
    position: relative;
}

#frame {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: none;
}

.placeholder {
    text-align: center;
    color: var(--text-secondary);
}

.placeholder-icon {
    font-size: 48px;
    margin-bottom: 12px;
    opacity: 0.8;
}

.status-bar {
    margin-top: 18px;
    padding: 14px 20px;
    border-radius: 14px;
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.2);
    color: var(--accent-red);
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 500;
}

.status-bar.online {
    background: rgba(34, 197, 94, 0.1);
    border-color: rgba(34, 197, 94, 0.2);
    color: var(--accent-green);
}

.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 10px currentColor;
}
</style>
</head>

<body>

<header>
    <h1>📷 สัญญาณกล้องตรวจจับ Real-time</h1>
    <nav>
        <a href="/">📊 สรุปผล</a>
        <a href="/live" class="active">📷 กล้อง Live</a>
    </nav>
</header>

<main>
    <div class="camera-card">
        <div class="video-container">
            <img id="frame" alt="Live Stream">
            <div id="placeholder" class="placeholder">
                <div class="placeholder-icon">📷</div>
                กำลังเชื่อมต่อสัญญาณภาพจาก AI...
            </div>
        </div>

        <div id="status" class="status-bar">
            <div class="status-dot"></div>
            <span id="status-text">กำลังตรวจสอบสถานะกล้อง...</span>
        </div>
    </div>
</main>

<script>
async function updateCamera() {
    try {
        const response = await fetch("/api/live/status", { cache: "no-store" });
        const data = await response.json();

        const status = document.getElementById("status");
        const statusText = document.getElementById("status-text");
        const frame = document.getElementById("frame");
        const placeholder = document.getElementById("placeholder");

        if (data.online) {
            status.className = "status-bar online";
            statusText.textContent = "ระบบทำงานปกติ (Camera Online)";

            if (data.has_frame) {
                frame.src = "/api/live/frame?t=" + Date.now();
                frame.style.display = "block";
                placeholder.style.display = "none";
            }
        } else {
            status.className = "status-bar";
            statusText.textContent = "ขาดการติดต่อกับกล้อง (Camera Offline)";
            frame.style.display = "none";
            placeholder.style.display = "block";
        }
    } catch (error) {
        console.error("Camera update error:", error);
    }
}

updateCamera();
setInterval(updateCamera, 1000);
</script>
</body>
</html>
"""

# =========================================================
# ROUTES
# =========================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return DASHBOARD_PAGE


@app.get("/live", response_class=HTMLResponse)
def live():
    return LIVE_PAGE

# =========================================================
# RUN SERVER
# =========================================================

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000))
    )
