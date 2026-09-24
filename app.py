"""
เว็บแอปตรวจจับกุ้งด้วย AI (YOLO + Gradio)
สำหรับ deploy บน Render  ->  Start Command: python app.py
"""

import inspect
import os

import cv2
import gradio as gr
from ultralytics import YOLO

# ============================================================
# ตั้งค่าโครงงาน (แก้ตรงนี้ได้เลย)
# ============================================================
MODEL_PATH = "best.pt"          # ต้องอยู่โฟลเดอร์เดียวกับไฟล์นี้
DEFAULT_CONF = 0.4              # ค่าความมั่นใจเริ่มต้น
MAX_SIDE = 1280                 # ย่อภาพใหญ่ๆ เพื่อประหยัด RAM บนเซิร์ฟเวอร์

PROJECT_TITLE = "ระบบตรวจจับกุ้งด้วย AI"
PROJECT_SUBTITLE = "อัปโหลดภาพกุ้ง แล้วให้ AI ตรวจจับตำแหน่ง นับจำนวน และจำแนกชนิดให้ทันที"
TEAM_NAME = "ชื่อผู้จัดทำ / ชื่อสถานศึกษา"   # <-- แก้เป็นชื่อของคุณ
# ============================================================

print("กำลังโหลดโมเดล...")
model = YOLO(MODEL_PATH)
CLASS_NAMES = model.names
print(f"โหลดสำเร็จ! รู้จัก {len(CLASS_NAMES)} class: {list(CLASS_NAMES.values())}")

# สีกรอบ (BGR สำหรับ OpenCV)
CLASS_COLORS = [
    (100, 255, 100),
    (100, 100, 255),
    (255, 200, 100),
    (255, 100, 255),
    (100, 255, 255),
]
FONT = cv2.FONT_HERSHEY_SIMPLEX


def get_color(class_id):
    return CLASS_COLORS[class_id % len(CLASS_COLORS)]


def limit_size(img_bgr):
    h, w = img_bgr.shape[:2]
    longest = max(h, w)
    if longest <= MAX_SIDE:
        return img_bgr
    scale = MAX_SIDE / longest
    return cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def draw_box(img, xyxy, label, color):
    x1, y1, x2, y2 = xyxy
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
    (tw, th), base = cv2.getTextSize(label, FONT, 0.55, 1)
    top = max(y1 - th - base - 6, 0)
    cv2.rectangle(img, (x1, top), (x1 + tw + 8, top + th + base + 6), color, -1)
    cv2.putText(img, label, (x1 + 4, top + th + 2), FONT, 0.55, (0, 0, 0), 1, cv2.LINE_AA)


def stat_cards(total, n_classes, avg_conf):
    return f"""
    <div class="stat-row">
      <div class="stat"><div class="stat-num">{total}</div><div class="stat-label">กุ้งที่ตรวจพบ (ตัว)</div></div>
      <div class="stat"><div class="stat-num">{n_classes}</div><div class="stat-label">ชนิดที่พบ</div></div>
      <div class="stat"><div class="stat-num">{avg_conf}</div><div class="stat-label">ความมั่นใจเฉลี่ย</div></div>
    </div>
    """


EMPTY_STATS = stat_cards("-", "-", "-")
EMPTY_TABLE = "_ผลสรุปจะแสดงที่นี่หลังกดตรวจจับ_"


def detect_shrimp(input_image, conf_threshold):
    """รับภาพ (RGB numpy) -> คืนภาพที่วาดกรอบ, การ์ดสถิติ, ตารางสรุป"""
    if input_image is None:
        gr.Warning("กรุณาอัปโหลดภาพก่อนครับ")
        return None, EMPTY_STATS, EMPTY_TABLE

    # Gradio ส่งมาเป็น RGB แต่ OpenCV ใช้ BGR
    image_bgr = limit_size(cv2.cvtColor(input_image, cv2.COLOR_RGB2BGR))
    result = model.predict(source=image_bgr, conf=conf_threshold, verbose=False)[0]

    annotated = image_bgr.copy()
    stats = {}  # ชื่อ class -> [จำนวน, ผลรวมความมั่นใจ]
    for box in result.boxes:
        xyxy = tuple(map(int, box.xyxy[0]))
        class_id = int(box.cls[0])
        name = CLASS_NAMES[class_id]
        conf = float(box.conf[0])
        draw_box(annotated, xyxy, f"{name} {conf:.2f}", get_color(class_id))
        entry = stats.setdefault(name, [0, 0.0])
        entry[0] += 1
        entry[1] += conf

    annotated_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)

    total = sum(v[0] for v in stats.values())
    if total == 0:
        return annotated_rgb, stat_cards(0, 0, "-"), "**ไม่พบกุ้งในภาพนี้** ลองลดค่าความมั่นใจ หรือใช้ภาพที่ชัดขึ้นดูครับ"

    avg_conf = sum(v[1] for v in stats.values()) / total
    rows = ["| ชนิด | จำนวน (ตัว) | ความมั่นใจเฉลี่ย |", "|---|---|---|"]
    for name, (count, conf_sum) in sorted(stats.items(), key=lambda kv: -kv[1][0]):
        rows.append(f"| {name} | {count} | {conf_sum / count * 100:.1f}% |")

    return annotated_rgb, stat_cards(total, len(stats), f"{avg_conf * 100:.0f}%"), "\n".join(rows)


def clear_all():
    return None, DEFAULT_CONF, None, EMPTY_STATS, EMPTY_TABLE


# ============================================================
# หน้าตาเว็บ
# ============================================================
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;500;600;700&display=swap');

.gradio-container {
    max-width: 1100px !important;
    margin: 0 auto !important;
    font-family: 'Noto Sans Thai', system-ui, sans-serif !important;
}
footer { display: none !important; }

.hero {
    background: linear-gradient(135deg, #0f766e 0%, #0e7490 50%, #1e3a8a 100%);
    color: #fff;
    border-radius: 20px;
    padding: 44px 32px;
    text-align: center;
    margin-bottom: 20px;
}
.hero h1 { font-size: 2.3rem; font-weight: 700; margin: 0 0 10px; color: #fff; }
.hero p { font-size: 1.05rem; margin: 0 auto; max-width: 640px; opacity: .92; color: #fff; }
.badges { margin-top: 18px; display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; }
.badge {
    background: rgba(255,255,255,.18);
    border: 1px solid rgba(255,255,255,.35);
    padding: 4px 14px; border-radius: 999px; font-size: .85rem; color: #fff;
}

.steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 20px; }
.step {
    background: var(--block-background-fill);
    border: 1px solid var(--border-color-primary);
    border-radius: 14px; padding: 16px 18px;
}
.step-num {
    display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 50%;
    background: #f97316; color: #fff; font-weight: 700; margin-bottom: 8px;
}
.step h4 { margin: 0 0 4px; font-size: 1rem; }
.step p { margin: 0; font-size: .9rem; opacity: .75; }

.stat-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 6px 0; }
.stat {
    background: var(--block-background-fill);
    border: 1px solid var(--border-color-primary);
    border-radius: 12px; padding: 12px 8px; text-align: center;
}
.stat-num { font-size: 1.8rem; font-weight: 700; color: #f97316; line-height: 1.2; }
.stat-label { font-size: .8rem; opacity: .7; }

.about {
    background: var(--block-background-fill);
    border: 1px solid var(--border-color-primary);
    border-radius: 14px; padding: 18px 22px; margin-top: 20px;
}
.about h3 { margin-top: 0; }
.about ul { margin-bottom: 0; }
.about .badge { background: #0e7490; border-color: #0e7490; margin: 2px 2px; display: inline-block; }

.site-footer { text-align: center; padding: 22px 0 6px; font-size: .88rem; opacity: .65; }

@media (max-width: 720px) {
    .hero { padding: 32px 18px; }
    .hero h1 { font-size: 1.7rem; }
    .steps { grid-template-columns: 1fr; }
}
"""

THEME = gr.themes.Soft(
    primary_hue="orange",
    secondary_hue="teal",
    font=[gr.themes.GoogleFont("Noto Sans Thai"), "system-ui", "sans-serif"],
)

# Gradio เวอร์ชันใหม่ย้าย theme/css ไปไว้ที่ launch() ส่วนเวอร์ชันเก่าอยู่ที่ Blocks()
# โค้ดนี้ตรวจให้อัตโนมัติ จึงใช้ได้ทั้งสองแบบ
STYLE_KWARGS = dict(theme=THEME, css=CSS)
STYLE_IN_LAUNCH = "css" in inspect.signature(gr.Blocks.launch).parameters
BLOCKS_KWARGS = {} if STYLE_IN_LAUNCH else STYLE_KWARGS

class_list = " ".join(f'<span class="badge">{n}</span>' for n in CLASS_NAMES.values())

with gr.Blocks(title=PROJECT_TITLE, **BLOCKS_KWARGS) as demo:

    # ---------- ส่วนหัว ----------
    gr.HTML(f"""
    <div class="hero">
      <h1>🦐 {PROJECT_TITLE}</h1>
      <p>{PROJECT_SUBTITLE}</p>
      <div class="badges">
        <span class="badge">YOLO Object Detection</span>
        <span class="badge">ตรวจจับภายในไม่กี่วินาที</span>
        <span class="badge">ใช้งานฟรี ไม่ต้องติดตั้ง</span>
      </div>
    </div>
    """)

    # ---------- วิธีใช้ ----------
    gr.HTML("""
    <div class="steps">
      <div class="step"><div class="step-num">1</div><h4>อัปโหลดภาพ</h4><p>ลากไฟล์มาวาง คลิกเลือกไฟล์ หรือถ่ายภาพจากกล้องได้เลย</p></div>
      <div class="step"><div class="step-num">2</div><h4>ปรับความมั่นใจ</h4><p>เลื่อนแถบเพื่อกำหนดว่าจะให้ AI เข้มงวดแค่ไหน (ไม่ปรับก็ได้)</p></div>
      <div class="step"><div class="step-num">3</div><h4>ดูผลลัพธ์</h4><p>กด "ตรวจจับ" แล้วดูตำแหน่ง จำนวน และชนิดของกุ้งทางด้านขวา</p></div>
    </div>
    """)

    # ---------- ส่วนใช้งานหลัก ----------
    with gr.Row(equal_height=False):
        with gr.Column(scale=1):
            input_image = gr.Image(label="📷 ภาพกุ้งที่ต้องการตรวจจับ", type="numpy", height=380)
            conf_slider = gr.Slider(
                minimum=0.1, maximum=0.9, value=DEFAULT_CONF, step=0.05,
                label="ความมั่นใจขั้นต่ำ (Confidence)",
                info="ต่ำ = เจอกุ้งมากขึ้นแต่อาจมีพลาด | สูง = แม่นยำขึ้นแต่อาจตกหล่นบางตัว",
            )
            with gr.Row():
                clear_btn = gr.Button("ล้างค่า", variant="secondary")
                detect_btn = gr.Button("🔍 ตรวจจับกุ้ง", variant="primary", scale=2)

        with gr.Column(scale=1):
            output_image = gr.Image(label="🎯 ผลการตรวจจับ", height=380)
            stats_html = gr.HTML(EMPTY_STATS)
            summary_md = gr.Markdown(EMPTY_TABLE)

    detect_btn.click(detect_shrimp, [input_image, conf_slider], [output_image, stats_html, summary_md])
    clear_btn.click(clear_all, None, [input_image, conf_slider, output_image, stats_html, summary_md])

    # ---------- เกี่ยวกับโครงงาน ----------
    gr.HTML(f"""
    <div class="about">
      <h3>📘 เกี่ยวกับโครงงาน</h3>
      <p>ระบบนี้ใช้โมเดลปัญญาประดิษฐ์ตระกูล YOLO ที่ฝึกด้วยภาพกุ้งเพื่อค้นหาตำแหน่งของกุ้งในภาพ
      นับจำนวน และจำแนกชนิดโดยอัตโนมัติ ช่วยลดเวลาและความคลาดเคลื่อนจากการนับด้วยมือ</p>
      <p><b>ชนิดที่โมเดลรู้จัก:</b><br>{class_list}</p>
      <ul>
        <li>ภาพที่ชัด แสงพอดี และเห็นตัวกุ้งเต็มตัว จะให้ผลแม่นยำที่สุด</li>
        <li>ผลลัพธ์เป็นการประมาณของ AI ควรใช้ประกอบการตัดสินใจ ไม่ใช่ค่าที่แน่นอน 100%</li>
        <li>เซิร์ฟเวอร์ฟรีจะหลับเมื่อไม่มีคนใช้ การเปิดครั้งแรกอาจใช้เวลารอประมาณ 1 นาที</li>
      </ul>
    </div>
    <div class="site-footer">จัดทำโดย {TEAM_NAME}</div>
    """)


if __name__ == "__main__":
    launch_kwargs = dict(
        server_name="0.0.0.0",                          # Render ต้องการให้ฟังที่ 0.0.0.0
        server_port=int(os.environ.get("PORT", 7860)),  # และใช้พอร์ตจากตัวแปร PORT
    )
    if STYLE_IN_LAUNCH:
        launch_kwargs.update(STYLE_KWARGS)
    demo.queue(max_size=8).launch(**launch_kwargs)
