"""
เว็บแอปตรวจจับกุ้ง (Gradio) - สำหรับ deploy บน Render
"""

import os

import cv2
import gradio as gr
import numpy as np
from ultralytics import YOLO

MODEL_PATH = "best.pt"  # ต้องอยู่โฟลเดอร์เดียวกับไฟล์นี้เสมอ
CONFIDENCE = 0.4

print("กำลังโหลดโมเดล...")
model = YOLO(MODEL_PATH)
CLASS_NAMES = model.names
print(f"โหลดสำเร็จ! รู้จัก {len(CLASS_NAMES)} class: {list(CLASS_NAMES.values())}")

CLASS_COLORS = [
    (100, 255, 100),
    (100, 100, 255),
    (255, 200, 100),
    (255, 100, 255),
    (100, 255, 255),
]


def get_color(class_id):
    return CLASS_COLORS[class_id % len(CLASS_COLORS)]


def detect_shrimp(input_image):
    """รับภาพจากผู้ใช้ (numpy array, RGB) -> คืนภาพที่วาดกรอบแล้ว + สรุปข้อความ"""
    if input_image is None:
        return None, "กรุณาอัปโหลดภาพก่อนครับ"

    # Gradio ส่งภาพมาเป็น RGB, OpenCV ใช้ BGR ต้องแปลงก่อน
    image_bgr = cv2.cvtColor(input_image, cv2.COLOR_RGB2BGR)

    results = model.predict(source=image_bgr, conf=CONFIDENCE, verbose=False)
    result = results[0]

    class_counts = {}
    annotated = image_bgr.copy()
    for box in result.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        class_id = int(box.cls[0])
        name = CLASS_NAMES[class_id]
        conf = float(box.conf[0])
        color = get_color(class_id)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label = f"{name} {conf:.2f}"
        cv2.putText(
            annotated,
            label,
            (x1, max(y1 - 8, 15)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2,
            cv2.LINE_AA,
        )
        class_counts[name] = class_counts.get(name, 0) + 1

    # แปลงกลับเป็น RGB ก่อนส่งคืนให้ Gradio แสดงผล
    annotated_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)

    total = sum(class_counts.values())
    summary_lines = [f"**พบกุ้งทั้งหมด: {total} ตัว**", ""]
    for name, count in class_counts.items():
        summary_lines.append(f"- {name}: {count} ตัว")
    summary = "\n".join(summary_lines) if total > 0 else "ไม่พบกุ้งในภาพนี้"

    return annotated_rgb, summary


demo = gr.Interface(
    fn=detect_shrimp,
    inputs=gr.Image(label="อัปโหลดภาพกุ้ง"),
    outputs=[
        gr.Image(label="ผลการตรวจจับ"),
        gr.Markdown(),
    ],
    title="🦐 ระบบตรวจจับกุ้ง AI",
    description="อัปโหลดภาพกุ้งเพื่อตรวจจับตำแหน่งและจำแนกชนิด",
)

if __name__ == "__main__":
    # Render กำหนดพอร์ตผ่านตัวแปร PORT และต้องฟังที่ 0.0.0.0
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
    )
