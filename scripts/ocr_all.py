"""Run RapidOCR on every KYC image and save the raw text lines to analysis/ocr_raw.json.

Usage: .venv/Scripts/python scripts/ocr_all.py
"""
import json
import time
from pathlib import Path

import cv2
import numpy as np
from rapidocr import RapidOCR

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "data" / "kyc_documents"
OUT = ROOT / "analysis" / "ocr_raw.json"


def remove_watermark(path):
    """The pink 'SYNTHETIC SPECIMEN' watermark hides values printed under it; turn pink pixels white."""
    im = cv2.imread(str(path)).astype(int)
    b, g, r = im[..., 0], im[..., 1], im[..., 2]
    pink = (r - g > 25) & (r - b > 15) & (r > 150)
    im[pink] = 255
    return im.astype(np.uint8)


def tilt_degrees(res):
    """Median slope of the top edge of wide text boxes; 0 for a straight scan."""
    angles = []
    for box in res.boxes:
        (x0, y0), (x1, y1) = box[0], box[1]
        if x1 - x0 > 80:
            angles.append(np.degrees(np.arctan2(y1 - y0, x1 - x0)))
    return float(np.median(angles)) if angles else 0.0


def straighten(image, degrees):
    h, w = image.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return cv2.warpAffine(image, m, (w, h), borderValue=(255, 255, 255))


def main():
    engine = RapidOCR()
    results = {}
    for img in sorted(DOCS.glob("*.png")):
        start = time.time()
        image = remove_watermark(img)
        res = engine(image)
        tilt = tilt_degrees(res)
        if 1.0 < abs(tilt) < 15.0:  # tilted photo/scan: straighten and read again (big values = blur noise)
            res = engine(straighten(image, tilt))
        lines = []
        for box, txt, score in zip(res.boxes, res.txts, res.scores):
            # box = 4 corner points; keep top-left y/x so lines can be re-ordered into rows later
            lines.append({"text": txt, "score": round(float(score), 3),
                          "x": round(float(box[0][0])), "y": round(float(box[0][1]))})
        results[img.name] = {"seconds": round(time.time() - start, 2), "tilt": round(tilt, 1), "lines": lines}
        print(f"{img.name}: {len(lines)} lines, {results[img.name]['seconds']}s")
    OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print("saved", OUT)


if __name__ == "__main__":
    main()
