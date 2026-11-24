# -*- coding: utf-8 -*-
"""PP-OCRv4 识别 + 白名单约束解码（只允许 0-9 和 -）"""
import os
import sys
import numpy as np
import cv2

# OCR 引擎目录：装到哪就指到哪
OCR_PATH = os.environ.get("PBM_OCR_PATH") or os.path.join(os.getcwd(), "ocr")
PKG = os.path.join(OCR_PATH, "rapidocr_onnxruntime")
if not os.path.isdir(PKG):
    raise SystemExit(f"找不到 OCR 引擎：{PKG}\n请先 pip install --target ./ocr rapidocr-onnxruntime，或设置 PBM_OCR_PATH")
sys.path.insert(0, OCR_PATH)

from rapidocr_onnxruntime.utils import read_yaml, OrtInferSession
from rapidocr_onnxruntime.ch_ppocr_rec.text_recognize import TextRecognizer

_cfg = read_yaml(os.path.join(PKG, "config.yaml"))
_cfg["Rec"]["model_path"] = os.path.join(PKG, "models", "ch_PP-OCRv4_rec_infer.onnx")
_rec = TextRecognizer(_cfg["Rec"])
CHARS = _rec.postprocess_op.character
ALLOW = [c for c in "0123456789-"]
ALLOW_IDX = sorted({i for i, c in enumerate(CHARS) if c in ALLOW} | {0})
RAW_IDX = {c: i for i, c in enumerate(CHARS)}
SESSION = _rec.session
IMG_H, IMG_W = 48, 320


def preprocess(img_bgr):
    h, w = img_bgr.shape[:2]
    ratio = w / float(h)
    rw = min(IMG_W, int(np.ceil(IMG_H * ratio)))
    rw = max(rw, 8)
    r = cv2.resize(img_bgr, (rw, IMG_H), interpolation=cv2.INTER_CUBIC)
    r = r.astype(np.float32).transpose(2, 0, 1) / 255.0
    r = (r - 0.5) / 0.5
    pad = np.zeros((3, IMG_H, IMG_W), np.float32)   # 先归一化再补零（与 Paddle 一致）
    pad[:, :, :rw] = r
    return pad[None]


def ctc_decode(seq):
    out = []
    for t in seq:
        if t and (not out or out[-1] != t):
            out.append(t)
    return "".join(CHARS[t] if t < len(CHARS) else "" for t in out)


def read(img_bgr, constrain=True):
    x = preprocess(img_bgr)
    logits = SESSION(x)[0]                      # 1,T,C
    logits = np.asarray(logits)[0]
    if constrain:
        mask = np.full(logits.shape, -1e4, np.float32)
        mask[:, ALLOW_IDX] = 0
        logits = logits + mask
    seq = logits.argmax(1).tolist()
    m = logits - logits.max(1, keepdims=True)
    p = np.exp(m); p /= p.sum(1, keepdims=True)
    keep = [i for i, t in enumerate(seq) if t != 0]
    prob = float(np.mean([p[i].max() for i in keep])) if keep else 0.0
    txt = ctc_decode(seq)
    return txt, prob


def norm(txt):
    """把识别结果规范成 N-G-A 形式；失败返回 ''"""
    s = "".join(c for c in txt if c.isdigit() or c == "-")
    while "--" in s:
        s = s.replace("--", "-")
    s = s.strip("-")
    if s.count("-") != 2:
        return ""
    a, b, c = s.split("-")
    if not (1 <= len(a) <= 2 and len(b) == 1 and 1 <= len(c) <= 2):
        return ""
    return f"{int(a)}-{int(b)}-{int(c)}"


if __name__ == "__main__":
    # 自测：对任意一张图跑一遍约束解码
    import sys
    if len(sys.argv) > 1:
        im = cv2.imdecode(np.fromfile(sys.argv[1], dtype=np.uint8), cv2.IMREAD_COLOR)
        print(read(im, constrain=True))
    else:
        print("用法: python ocr_engine.py <单行文字图>")
