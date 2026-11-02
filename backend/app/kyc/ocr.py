"""Read text from a document photo with RapidOCR, running locally (documents never leave our server).

Before reading: shadows are evened out, the pink "SYNTHETIC SPECIMEN" watermark is whitened (it hides values printed under it)
and very large phone photos are scaled down. A tilted photo is straightened and read again.
A photo taken sideways or upside down can be read again turned (see documents.read_document).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

MAX_SIDE = 2000          # phone photos are often 4000 px; OCR is slower and no better above this
BLUR_LIMIT = 100.0       # Laplacian variance below this = too blurred to trust (sharp specimens score 900+)
_engine = None
_lock = threading.Lock()  # one OCR run at a time: keeps memory flat on a small free server


class NotAnImage(ValueError):
    pass


@dataclass
class OcrLine:
    text: str
    score: float
    x: int        # top-left corner of the text box
    y: int
    h: int        # box height, used to decide which words sit on the same row


@dataclass
class OcrResult:
    lines: list[OcrLine]
    tilt: float           # degrees the photo was straightened by (0 if not)
    sharpness: float
    seconds: float
    turned: int = 0       # quarter turns applied before reading (0-3)
    tall_text: float = 0.0  # share of text boxes taller than wide: most of them = the photo is sideways
    image: np.ndarray | None = field(default=None, repr=False)  # cleaned image the boxes refer to; never stored

    @property
    def blurred(self) -> bool:
        return self.sharpness < BLUR_LIMIT


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr import RapidOCR  # slow import (loads ONNX models): only when the first document arrives
        _engine = RapidOCR()
    return _engine


def decode(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None
    if image is None:
        raise NotAnImage("file is not a readable image")
    h, w = image.shape[:2]
    if max(h, w) > MAX_SIDE:
        scale = MAX_SIDE / max(h, w)
        image = cv2.resize(image, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    return image


def sharpness(image: np.ndarray) -> float:
    return round(float(cv2.Laplacian(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()), 1)


def even_lighting(image: np.ndarray) -> np.ndarray:
    """Divide out the paper's brightness (estimated by a wide max filter), so shadows and dim rooms look like a scan."""
    paper = cv2.medianBlur(cv2.dilate(image, np.ones((15, 15), np.uint8)), 31)
    return np.clip(image.astype(float) / np.maximum(paper, 1) * 250, 0, 255).astype(np.uint8)


def remove_watermark(image: np.ndarray) -> np.ndarray:
    """Even out the lighting, then whiten the pink watermark (thresholds tuned on shadowed and JPEG copies,
    see scripts/stress_kyc.py)."""
    out = even_lighting(image)
    im = out.astype(int)
    b, g, r = im[..., 0], im[..., 1], im[..., 2]
    out[(r - g > 20) & (r - b > 10) & (r > 140)] = 255
    return out


def _tilt_degrees(res) -> float:
    """Median slope of the top edge of wide text boxes; 0 for a straight scan."""
    angles = [np.degrees(np.arctan2(b[1][1] - b[0][1], b[1][0] - b[0][0]))
              for b in (res.boxes if res.boxes is not None else []) if b[1][0] - b[0][0] > 80]
    return float(np.median(angles)) if angles else 0.0


def _straighten(image: np.ndarray, degrees: float) -> np.ndarray:
    h, w = image.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return cv2.warpAffine(image, m, (w, h), borderValue=(255, 255, 255))


TURNS = {1: cv2.ROTATE_90_COUNTERCLOCKWISE, 2: cv2.ROTATE_180, 3: cv2.ROTATE_90_CLOCKWISE}


def read_image(data: bytes, turned: int = 0) -> OcrResult:
    start = time.time()
    image = decode(data)
    if turned % 4:
        image = cv2.rotate(image, TURNS[turned % 4])
    sharp = sharpness(image)
    clean = remove_watermark(image)
    with _lock:
        engine = _get_engine()
        res = engine(clean)
        tilt = _tilt_degrees(res)
        if 1.0 < abs(tilt) < 15.0:  # tilted photo: straighten and read again (bigger angles come from blur noise)
            clean = _straighten(clean, tilt)
            res = engine(clean)
        else:
            tilt = 0.0
    lines, tall = [], 0
    if res.boxes is not None:
        for box, txt, score in zip(res.boxes, res.txts, res.scores):
            lines.append(OcrLine(txt.strip(), round(float(score), 3), round(float(box[0][0])),
                                 round(float(box[0][1])), max(1, round(float(box[3][1] - box[0][1])))))
            tall += abs(box[2][1] - box[0][1]) > abs(box[2][0] - box[0][0])
    return OcrResult(lines, round(tilt, 1), sharp, round(time.time() - start, 2), turned % 4,
                     round(tall / max(len(lines), 1), 2), cv2.cvtColor(clean, cv2.COLOR_BGR2GRAY))


def ink(gray: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> float:
    """Share of dark pixels in a box of the cleaned image: about 0 for an empty field, 0.05+ for printed text."""
    h, w = gray.shape
    box = gray[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]
    return float((box < 150).mean()) if box.size else 0.0


def read_region(gray: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> str:
    """Read one small box again, enlarged: the page-level text finder sometimes skips a value next to a shadow."""
    h, w = gray.shape
    box = gray[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]
    if not box.size:
        return ""
    box = cv2.copyMakeBorder(cv2.resize(box, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC),
                             20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    with _lock:
        res = _get_engine()(cv2.cvtColor(box, cv2.COLOR_GRAY2BGR))
    return " ".join(t.strip() for t in (res.txts or ()) if t.strip())
