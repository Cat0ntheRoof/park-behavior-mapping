# -*- coding: utf-8 -*-
"""生成一张合成的手绘风格公园平面图，用于演示与自测

输出：
  demo/park1.png      —— 带方格纸、路网、注记的"扫描件"
  demo/truth.json     —— 每个注记的真值（框 + 编码），可用于验收
"""
import json
import os
import random

import cv2
import numpy as np

random.seed(7)
np.random.seed(7)

W, H = 1600, 1000
OUT = os.path.dirname(os.path.abspath(__file__))

img = np.full((H, W, 3), 255, np.uint8)

# ---- 方格纸 ----
for x in range(0, W, 22):
    cv2.line(img, (x, 0), (x, H), (232, 220, 244), 1)
for y in range(0, H, 22):
    cv2.line(img, (0, y), (W, y), (232, 220, 244), 1)


def hand_line(pts, color=(40, 40, 40), width=3, jitter=1.6):
    """把折线画得像手绘：插值 + 抖动"""
    out = []
    for i in range(len(pts) - 1):
        p, q = np.array(pts[i], float), np.array(pts[i + 1], float)
        n = max(int(np.linalg.norm(q - p) / 6), 2)
        for t in np.linspace(0, 1, n):
            out.append(p + (q - p) * t + np.random.randn(2) * jitter)
    out.append(np.array(pts[-1], float))
    cv2.polylines(img, [np.array(out, np.int32)], False, color, width, cv2.LINE_AA)


def hand_text(s, center, ang, scale=0.85):
    """旋转写一行字，模拟手写标注"""
    w, h = 150, 42
    patch = np.full((h, w, 3), 255, np.uint8)
    cv2.putText(patch, s, (4, 30), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, scale, (35, 35, 35), 2, cv2.LINE_AA)
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
    patch = cv2.warpAffine(patch, M, (w, h), borderValue=(255, 255, 255))
    mask = (patch.min(axis=2) < 200)
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return
    dx0, dy0 = int(center[0] - w / 2), int(center[1] - h / 2)
    for y, x in zip(ys, xs):
        X, Y = dx0 + x, dy0 + y
        if 0 <= X < W and 0 <= Y < H:
            img[Y, X] = patch[y, x]


# ---- 园路（两条主环 + 几条支路）----
ring1 = [(180, 720), (330, 560), (560, 470), (800, 450), (1000, 470), (1160, 560), (1260, 700)]
ring2 = [(260, 800), (520, 760), (820, 740), (1080, 760), (1240, 820)]
spurs = [
    [(560, 470), (520, 300), (600, 200)],
    [(800, 450), (820, 260), (900, 160)],
    [(1000, 470), (1080, 320)],
    [(330, 560), (240, 430)],
    [(1260, 700), (1400, 640)],
    [(820, 740), (840, 880)],
]
for pts in [ring1, ring2] + spurs:
    hand_line(pts)
    hand_line(pts, width=2)

# ---- 注记 ----
codes = []
for _ in range(22):
    n = random.choice([1, 1, 1, 2, 3, 4, 5, 8, 10, 12])
    g = random.choice([1, 2, 2, 3])
    a = random.choice([1, 1, 1, 2, 4, 5, 6, 8, 10, 11])
    codes.append(f"{n}-{g}-{a}")

anchors = []
for pts in [ring1, ring2] + spurs:
    for i in range(1, len(pts) - 1):
        anchors.append(pts[i])
anchors += ring1 + ring2
random.shuffle(anchors)

truth = []
for i, code in enumerate(codes):
    c = anchors[i % len(anchors)]
    center = (c[0] + random.randint(-30, 40), c[1] + random.randint(-46, 30))
    ang = random.uniform(-14, 14)
    hand_text(code, center, ang)
    truth.append({"id": i + 1, "code": code, "cx": float(center[0]), "cy": float(center[1]),
                  "w": 108.0, "h": 26.0, "ang": float(ang)})

# ---- 几根指向线（制造真实的干扰）----
for _ in range(8):
    p = random.choice(anchors)
    q = (p[0] + random.randint(-60, 60), p[1] + random.randint(40, 110))
    hand_line([p, q], width=1, jitter=2.2)

# ---- 轻微扫描噪声 ----
img = np.clip(img.astype(np.int16) + np.random.randint(-6, 6, img.shape), 0, 255).astype(np.uint8)

cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tofile(os.path.join(OUT, "park1.jpg"))
json.dump({"image": "park1.jpg", "boxes": truth},
          open(os.path.join(OUT, "truth.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("demo/park1.jpg", img.shape, "注记", len(truth))
