# -*- coding: utf-8 -*-
"""对标注导出的每个框做识别，输出建议值（需人工确认）"""
import argparse
import csv
import json
import os
import sys
from collections import Counter

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ocr_engine as R

_ap = argparse.ArgumentParser(description="批量识别注记框内的 人数-性别-活动 编码")
_ap.add_argument("--export", required=True, help="标注导出的 JSON")
_ap.add_argument("--images", nargs="+", required=True,
                 help="图 key 与文件对应，如 u1=a.jpg u2=b.jpg")
_ap.add_argument("--out", default=".", help="输出目录")
_ap.add_argument("--scale", type=float, default=3.0, help="裁剪放大倍数（默认 3）")
ARGS = _ap.parse_args()

SRC = {}
for item in ARGS.images:
    if "=" not in item:
        raise SystemExit(f"--images 需写成 key=path，收到：{item}")
    k, v = item.split("=", 1)
    SRC[k] = os.path.abspath(v)
S = ARGS.scale


def crop_obb(img, cx, cy, w, h, ang, pad=0.22):
    M = cv2.getRotationMatrix2D((cx, cy), ang, 1.0)
    rot = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]),
                         flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
    return cv2.getRectSubPix(rot, (max(int(w * (1 + pad)), 10), max(int(h * (1 + pad)), 10)), (cx, cy))


def variants(p):
    out = [p]
    g = cv2.cvtColor(p, cv2.COLOR_BGR2GRAY)
    _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    out.append(cv2.cvtColor(b, cv2.COLOR_GRAY2BGR))
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    out.append(cv2.cvtColor(cv2.morphologyEx(b, cv2.MORPH_OPEN, k), cv2.COLOR_GRAY2BGR))
    h, w = p.shape[:2]
    out.append(cv2.copyMakeBorder(p, 4, 4, int(w * 0.12) + 2, int(w * 0.12) + 2,
                                  cv2.BORDER_CONSTANT, value=(255, 255, 255)))
    return out


def read_box(img, b):
    votes = []
    for pad in (0.15, 0.35):
        c = crop_obb(img, b["cx"], b["cy"], b["w"], b["h"], b["ang"], pad)
        for v in variants(c):
            con, _ = R.read(v, constrain=True)
            t = R.norm(con)
            if t:
                votes.append(t)
    if not votes:
        return "", 0.0
    best, n = Counter(votes).most_common(1)[0]
    return best, round(n / len(votes), 2)


def main():
    data = json.load(open(os.path.abspath(ARGS.export), encoding="utf-8"))
    out_dir = os.path.abspath(ARGS.out)
    os.makedirs(out_dir, exist_ok=True)
    suggest, rows = {}, []

    for key, path in SRC.items():
        if key not in data:
            continue
        img0 = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        img = cv2.resize(img0, None, fx=S, fy=S, interpolation=cv2.INTER_CUBIC)
        sug = {}
        for b in data[key].get("boxes", []):
            ang = b["ang"] % 180
            if ang > 90:
                ang -= 180              # 角度必须归到 [-90,90)，否则字会上下颠倒
            bb = dict(cx=b["cx"] * S, cy=b["cy"] * S, w=b["w"] * S, h=b["h"] * S, ang=ang)
            txt, conf = read_box(img, bb)
            if txt:
                sug[str(b["id"])] = txt
            if b.get("note"):
                txt, conf = b["note"], 1.0
            rows.append([key, b["id"], b.get("seg") or "", txt or "", conf])
        suggest[key] = sug

    csv_path = os.path.join(out_dir, "suggestions.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["image", "box_id", "segment", "reading", "agreement"])
        w.writerows(rows)

    js = os.path.join(out_dir, "suggestions.json")
    json.dump(suggest, open(js, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    total = len(rows)
    ok = sum(1 for r in rows if r[3])
    hi = sum(1 for r in rows if r[3] and r[4] >= 0.6)
    print(f"框 {total} 个，给出建议 {ok} 个（高一致 {hi}）")
    print("建议值：", js)
    print("明细：", csv_path)
    print("下一步：在标注网页里点「导入建议值」，逐条确认。")


if __name__ == "__main__":
    main()
