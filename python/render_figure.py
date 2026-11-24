# -*- coding: utf-8 -*-
"""干净版：纯线条底图（去除手写数字）+ 路段 + 分段数值"""
import os
import json
import re
import csv
from collections import Counter
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

import argparse

_ap = argparse.ArgumentParser(description="生成线稿版分段统计图与 CSV")
_ap.add_argument("--export", required=True, help="标注导出的 JSON")
_ap.add_argument("--key", required=True, help="取哪张图的数据（如 i1 / m1）")
_ap.add_argument("--image", required=True, help="对应的原始扫描图")
_ap.add_argument("--out", required=True, help="输出 PNG 路径")
_ap.add_argument("--csv", default=None, help="输出 CSV 路径（可省）")
_ap.add_argument("--title", default="Park behavior mapping", help="图题")
_ap.add_argument("--subtitle", default="", help="副标题")
_ap.add_argument("--credit", default="方法：Hon Sytsi　·　风景园林行为观察", help="方法署名（置空可隐藏）")
ARGS = _ap.parse_args()

DATA_JSON = os.path.abspath(ARGS.export)
KEY = ARGS.key
SRC_IMAGE = os.path.abspath(ARGS.image)
OUT_NAME = os.path.abspath(ARGS.out)
CSV_OUT = os.path.abspath(ARGS.csv) if ARGS.csv else None
TITLE1 = ARGS.title
TITLE2 = ARGS.subtitle
CREDIT = ARGS.credit
F_B = "C:/Windows/Fonts/msyhbd.ttc"
F_R = "C:/Windows/Fonts/msyh.ttc"
DWELL = {1: 1, 2: 1, 3: 1, 4: 3, 5: 3, 6: 3, 7: 3, 8: 2, 9: 3, 10: 3, 11: 2, 12: 3, 13: 2}
ACT = {1: "步行/散步", 2: "跑步", 3: "骑行/轮滑", 4: "坐憩/休息", 5: "社交交谈",
       6: "亲子活动", 7: "锻炼/健身", 8: "遛狗", 9: "野餐/饮食", 10: "使用手机/阅读",
       11: "拍照/观景", 12: "文化活动", 13: "其他"}


def parse(t):
    m = re.fullmatch(r"(\d{1,2})-(\d)-(\d{1,2})", str(t).strip())
    if not m:
        return None
    n, g, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return (n, g, a) if g in (1, 2, 3) and 1 <= a <= 13 else None


def stats(d):
    rows = []
    for s in d["segs"]:
        bs = [b for b in d["boxes"] if b.get("seg") == s["id"]]
        n = m = f = mix = 0
        acts, dw = Counter(), Counter()
        for b in bs:
            p = parse(b.get("note"))
            if not p:
                continue
            a, g, act = p
            n += a
            m += a if g == 1 else 0
            f += a if g == 2 else 0
            mix += a if g == 3 else 0
            acts[act] += a
            dw[DWELL.get(act, 2)] += a
        gm = 3 if mix > max(m, f) else (1 if m > f else (2 if f > m else 0))
        dm = max(dw, key=dw.get) if dw else 0
        rows.append(dict(id=s["id"], pts=s["pts"], nb=len(bs), n=n, m=m, f=f, mix=mix,
                         g=gm, d=dm, act=acts.most_common(1)[0][0] if acts else 0,
                         label=f"{n}-{gm}-{dm}" if n else "无记录"))
    return rows


def ink_from(path):
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    b, gg, r = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    blue = (b - r > 10) & (b > 150)
    dark = (r < 155) & (gg < 155) & ~blue
    return np.where(dark, 0, 255).astype(np.uint8)


def quad_of(b):
    """兼容只给 cx/cy/w/h/ang 的框"""
    if b.get("pts"):
        return np.array(b["pts"], np.int32)
    a = np.radians(b.get("ang", 0))
    c, s_ = np.cos(a), np.sin(a)
    hw, hh = b["w"] / 2, b["h"] / 2
    loc = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    return np.array([[b["cx"] + c * x - s_ * y, b["cy"] + s_ * x + c * y] for x, y in loc], np.int32)


def clean_lines(d):
    """读取 ink1.png，擦掉手写数字，去掉细碎笔画"""
    g = ink_from(SRC_IMAGE)
    ink = (g < 128).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
    for b in d["boxes"]:
        poly = quad_of(b)
        m = np.zeros_like(ink)
        cv2.fillPoly(m, [poly], 255)
        m = cv2.dilate(m, k)          # 外扩一圈，带走紧贴的短横与笔尖
        ink[m > 0] = 0
    # 去掉残留碎屑（面积小 / 尺寸小）
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    keep = np.zeros_like(ink)
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a >= 700 and max(w, h) >= 60:
            keep[lab == i] = 255
    return Image.fromarray(255 - keep)          # 黑线白底


def seg_mid(pts):
    L = sum(np.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))
    acc = 0
    for i in range(len(pts) - 1):
        l = np.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        if acc + l >= L / 2:
            t = (L / 2 - acc) / (l or 1)
            return (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t,
                    pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t)
        acc += l
    return tuple(pts[0])


def main(keep_ink=True, out_name="figure.png"):
    d = json.load(open(DATA_JSON, encoding="utf-8"))[KEY]
    rows = stats(d)
    total = sum(r["n"] for r in rows)
    tm, tf, tmx = (sum(r[k] for r in rows) for k in ("m", "f", "mix"))

    inkimg = clean_lines(d)
    SC = 1.75
    a = np.array(inkimg)
    ys, xs = np.where(a < 200)
    x0, y0 = max(xs.min() - 30, 0), max(ys.min() - 30, 0)
    x1, y1 = min(xs.max() + 30, inkimg.width), min(ys.max() + 30, inkimg.height)
    base = inkimg if keep_ink else Image.new("L", inkimg.size, 255)
    if keep_ink:
        base = Image.eval(base, lambda v: 165 + v * 90 // 255)   # 线条压成中灰，突出标注
    base = base.crop((x0, y0, x1, y1))
    base = base.resize((int(base.width * SC), int(base.height * SC)), Image.LANCZOS)
    PAD_R = 980
    canvas = Image.new("RGB", (base.width + PAD_R, base.height), "white")
    canvas.paste(base, (0, 0))
    dr = ImageDraw.Draw(canvas)

    f_id = ImageFont.truetype(F_B, 19)
    f_val = ImageFont.truetype(F_B, 38)
    f_t = ImageFont.truetype(F_B, 40)
    f_st = ImageFont.truetype(F_R, 22)
    f_tb = ImageFont.truetype(F_R, 18)
    f_tbh = ImageFont.truetype(F_B, 20)
    f_lg = ImageFont.truetype(F_R, 19)

    def P(p):
        return ((p[0] - x0) * SC, (p[1] - y0) * SC)

    # 路段
    for r in rows:
        pts = [P(p) for p in r["pts"]]
        dr.line(pts, fill=(120, 165, 145), width=int(22 * SC / 1.75), joint="curve")
        dr.line(pts, fill=(228, 246, 238), width=int(11 * SC / 1.75), joint="curve")
        m = P(seg_mid(r["pts"]))
        dr.text((m[0], m[1] - 12), r["id"], font=f_id, fill=(16, 110, 85),
                anchor="mb", stroke_width=4, stroke_fill="white")

    # 数值
    placed = []
    for r in sorted(rows, key=lambda x: -x["n"]):
        if r["n"] == 0:
            continue
        m = P(seg_mid(r["pts"]))
        txt = r["label"]
        tw = dr.textlength(txt, font=f_val)
        bw, bh = tw + 28, 56
        best = None
        for dx, dy in [(0, -80), (0, 80), (-1, -50), (1, -50), (-1, 50), (1, 50),
                       (0, -150), (0, 150), (-2, -30), (2, -30)]:
            x = m[0] + dx * (bw / 2 + 16) - bw / 2
            y = m[1] + dy - bh / 2
            box = (x, y, x + bw, y + bh)
            if box[0] < 4 or box[1] < 4 or box[2] > base.width - 4 or box[3] > base.height - 4:
                continue
            if any(not (box[2] < o[0] or box[0] > o[2] or box[3] < o[1] or box[1] > o[3]) for o in placed):
                continue
            best = box
            break
        if best is None:
            best = (m[0] - bw / 2, m[1] - 80 - bh / 2, m[0] + bw / 2, m[1] - 80 + bh / 2)
        placed.append(best)
        col = {1: (28, 88, 160), 2: (176, 42, 84), 3: (150, 96, 30), 0: (90, 90, 90)}[r["g"]]
        dr.line([m, ((best[0] + best[2]) / 2, (best[1] + best[3]) / 2)],
                fill=(170, 170, 170), width=2)
        dr.rounded_rectangle(best, radius=9, fill="white", outline=col, width=3)
        dr.text(((best[0] + best[2]) / 2, (best[1] + best[3]) / 2 - 2), txt,
                font=f_val, fill=col, anchor="mm")

    # 右栏
    X = base.width + 40
    y = 40
    dr.text((X, y), TITLE1, font=f_t, fill=(22, 22, 22)); y += 44
    dr.text((X, y), TITLE2, font=f_st, fill=(95, 95, 95)); y += 32
    dr.text((X, y), "行为观察分段统计 · " + ("线稿重绘版" if keep_ink else "纯路段图"), font=f_st, fill=(125, 125, 125)); y += 34
    dr.line([(X, y), (X + 860, y)], fill=(215, 215, 215), width=2); y += 20

    dr.text((X, y), "标注读法", font=f_tbh, fill=(22, 22, 22)); y += 30
    for s in ["总人数 - 主要性别 - 主导停留时长",
              "例  12-1-3 ＝ 12 人 / 男性为主 / 持续活动 ≥5min"]:
        dr.text((X, y), s, font=f_lg, fill=(60, 60, 60)); y += 26
    y += 4
    dr.text((X, y), "性别 1=男 2=女 3=男女均衡 0=持平　停留 1=路过 2=<5min 3=≥5min",
            font=f_tb, fill=(95, 95, 95)); y += 34
    dr.line([(X, y), (X + 860, y)], fill=(215, 215, 215), width=2); y += 18

    dr.text((X, y), "分段统计", font=f_tbh, fill=(22, 22, 22)); y += 28
    heads = [("路段", 8), ("人数", 96), ("男/女/均衡", 158), ("主导活动", 288), ("标注值", 560)]
    for t, dx in heads:
        dr.text((X + dx, y), t, font=f_tb, fill=(145, 145, 145))
    y += 26
    dr.line([(X, y - 6), (X + 880, y - 6)], fill=(238, 238, 238), width=1)
    half = (len(rows) + 1) // 2
    for i, r in enumerate(sorted(rows, key=lambda x: -x["n"])):
        cx = X + (0 if i < half else 450)
        cy = y + (i % half) * 27
        col = {1: (28, 88, 160), 2: (176, 42, 84), 3: (150, 96, 30), 0: (110, 110, 110)}[r["g"]]
        dr.text((cx + 8, cy), r["id"], font=f_tb, fill=(95, 95, 95))
        dr.text((cx + 96, cy), str(r["n"]) if r["n"] else "—", font=f_tb, fill=(35, 35, 35))
        dr.text((cx + 158, cy), f"{r['m']}/{r['f']}/{r['mix']}" if r["n"] else "—",
                font=f_tb, fill=(95, 95, 95))
        dr.text((cx + 288, cy), ACT.get(r["act"], "") if r["n"] else "—", font=f_tb, fill=(95, 95, 95))
        dr.text((cx + 430, cy), r["label"], font=f_tb, fill=col, anchor="ra")
    y += half * 27 + 16
    dr.line([(X, y), (X + 860, y)], fill=(215, 215, 215), width=2); y += 18
    dr.text((X, y), "合计", font=f_tbh, fill=(22, 22, 22)); y += 28
    for s in [f"框 {len(d['boxes'])} 个（{sum(1 for b in d['boxes'] if b.get('seg'))} 个已挂路段）",
              f"累计人数 {total} 人（男 {tm} / 女 {tf} / 均衡 {tmx}）",
              f"路段 {len(rows)} 条，有记录 {sum(1 for r in rows if r['n'])} 条"]:
        dr.text((X, y), s, font=f_lg, fill=(60, 60, 60)); y += 25
    y += 10
    dr.text((X, y), "说明", font=f_tbh, fill=(22, 22, 22)); y += 26
    for s in (["底图为手绘线稿的二值提取，已擦除手写数字，仅保留园界与园路线条。",
               "绿带为所画路段；数字框为该路段的人-性别-停留汇总。"] if keep_ink else
              ["仅保留所画路段，不显示底图笔迹。",
               "绿带为路段；数字框为该路段的人-性别-停留汇总。"]):
        dr.text((X, y), s, font=f_tb, fill=(120, 100, 70)); y += 22

    un = [b for b in d["boxes"] if not str(b.get("note", "")).strip()]
    if un:
        dr.text((X, y), "未读数：" + "、".join(f"#{b['id']}({b.get('seg') or '未挂'})" for b in un) + "，未计入合计",
                font=f_tb, fill=(190, 60, 60)); y += 22

    if CSV_OUT:
        with open(CSV_OUT, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["路段", "折线点数", "框数", "总人数", "男", "女", "均衡", "主要性别",
                        "主导活动", "主导停留等级", "平面图标注"])
            for r in rows:
                w.writerow([r["id"], len(r["pts"]), r["nb"], r["n"], r["m"], r["f"], r["mix"],
                            {1: "男", 2: "女", 3: "均衡", 0: "持平"}[r["g"]],
                            f"A{r['act']} {ACT.get(r['act'], '')}", r["d"], r["label"]])

    canvas.save(OUT_NAME, dpi=(300, 300))
    print("saved", canvas.size, "total", total)


if __name__ == "__main__":
    main(True, OUT_NAME)
