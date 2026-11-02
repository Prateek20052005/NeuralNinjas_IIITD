"""Make phone-like copies of KYC specimens (tilted, sideways, blurry JPEG, small, dark, shadowed, on a table)
and check the OCR pipeline still finds the document type and the same fields as on the clean image.

Usage: .venv/Scripts/python scripts/stress_kyc.py [applicant ...]     (default K03 K07; about 3 s per image)
Writes analysis/stress_kyc.json.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.app.kyc.documents import parse_document, read_document  # noqa: E402
from backend.app.kyc.ocr import read_image  # noqa: E402


def rotate(im, deg):
    h, w = im.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(im, m, (nw, nh), borderValue=(235, 235, 235))


def jpeg(im, q):
    return cv2.imdecode(cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)


def shrink(im, side):
    s = side / max(im.shape[:2])
    return cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)


def dark(im):
    noisy = im.astype(float) * 0.55 + np.random.default_rng(1).normal(0, 8, im.shape)
    return np.clip(noisy, 0, 255).astype(np.uint8)


def shadow(im):
    ramp = np.linspace(1.0, 0.45, im.shape[1])[None, :, None]
    return (im.astype(float) * ramp).astype(np.uint8)


def keystone(im):
    h, w = im.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[w * .04, h * .03], [w * .96, 0], [w, h], [0, h * .97]])
    return cv2.warpPerspective(im, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=(200, 190, 170))


def on_table(im):
    h, w = im.shape[:2]
    out = cv2.copyMakeBorder(im, h // 5, h // 5, w // 6, w // 6, cv2.BORDER_CONSTANT, value=(60, 90, 120))
    return jpeg(rotate(out, 3), 70)


VARIANTS = {
    "tilt_5": lambda im: rotate(im, 5), "tilt_12": lambda im: rotate(im, 12),
    "sideways": lambda im: cv2.rotate(im, cv2.ROTATE_90_CLOCKWISE), "upside_down": lambda im: cv2.rotate(im, cv2.ROTATE_180),
    "jpeg_30": lambda im: jpeg(im, 30), "small_900px": lambda im: shrink(im, 900), "dark_noisy": dark,
    "shadow": shadow, "keystone": keystone, "on_table": on_table,
}


def main():
    applicants = sys.argv[1:] or ["K03", "K07"]
    results, summary = [], {v: [0, 0, 0] for v in VARIANTS}   # type ok, fields ok, fields total
    for img in sorted(p for a in applicants for p in (ROOT / "data" / "kyc_documents").glob(f"{a}_*.png")):
        doc_type = img.stem[4:]
        base = parse_document(doc_type, read_image(img.read_bytes()))
        im = cv2.imread(str(img))
        for name, fn in VARIANTS.items():
            data = cv2.imencode(".png", fn(im))[1].tobytes()
            got = read_document(doc_type, data)
            same = [k for k, v in base.fields.items() if got.fields.get(k) == v]
            diff = {k: [v, got.fields.get(k)] for k, v in base.fields.items() if got.fields.get(k) != v}
            ok_type = got.detected_type == doc_type
            summary[name][0] += ok_type
            summary[name][1] += len(same)
            summary[name][2] += len(base.fields)
            results.append({"doc": img.stem, "variant": name, "type_ok": ok_type, "blurred": got.blurred,
                            "sharpness": got.sharpness, "tilt": got.tilt, "seconds": got.seconds, "diff": diff})
            print(f"{img.stem:<26} {name:<12} type={'ok' if ok_type else got.detected_type} "
                  f"fields={len(same)}/{len(base.fields)} sharp={got.sharpness} blurred={got.blurred} "
                  f"{got.seconds}s {diff if diff else ''}", flush=True)
    n_docs = len(results) // len(VARIANTS)
    print("\nvariant       type   fields")
    for name, (t, f, total) in summary.items():
        print(f"{name:<12} {t}/{n_docs}   {f}/{total} ({100 * f / max(total, 1):.0f}%)")
    (ROOT / "analysis" / "stress_kyc.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
