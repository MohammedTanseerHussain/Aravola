"""Person segmentation and detection.

Two independent backends are used:

* MediaPipe Selfie Segmenter — fast, single-person, returns a soft mask.
* YOLOv8-seg — multi-person, bounding boxes + optional masks.

Models are loaded lazily and cached for the lifetime of the process.  If a
model is missing the functions return ``None``/an empty list rather than
crashing the API.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..config import HAAR_CASCADE, SEGMENTER_MODEL, YOLO_MODEL

_lock = threading.Lock()
_segmenter = None
_segmenter_failed = False
_yolo = None
_yolo_failed = False
_haar = None


# ---------------------------------------------------------------------------
# MediaPipe
# ---------------------------------------------------------------------------
def _get_segmenter():
    global _segmenter, _segmenter_failed
    if _segmenter is not None or _segmenter_failed:
        return _segmenter
    with _lock:
        if _segmenter is not None or _segmenter_failed:
            return _segmenter
        if SEGMENTER_MODEL is None:
            _segmenter_failed = True
            return None
        try:
            import mediapipe as mp

            options = mp.tasks.vision.ImageSegmenterOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(SEGMENTER_MODEL)),
                running_mode=mp.tasks.vision.RunningMode.IMAGE,
                output_category_mask=True,
                output_confidence_masks=True,
            )
            _segmenter = mp.tasks.vision.ImageSegmenter.create_from_options(options)
        except Exception:
            _segmenter_failed = True
            _segmenter = None
    return _segmenter


def segment_person(frame: np.ndarray) -> np.ndarray | None:
    """Return a soft (H,W) float32 person mask in [0,1]."""
    segmenter = _get_segmenter()
    if segmenter is None or frame is None or frame.size == 0:
        return None
    try:
        import mediapipe as mp

        rgb = np.ascontiguousarray(frame[:, :, :3].astype(np.uint8))
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = segmenter.segment(image)
        masks = getattr(result, "confidence_masks", None)
        if masks:
            mask = masks[0].numpy_view().astype(np.float32)
        else:
            mask = result.category_mask.numpy_view().astype(np.float32)
        if mask.ndim == 3:
            mask = mask[..., 0]
        if mask.shape[:2] != frame.shape[:2]:
            import cv2

            mask = cv2.resize(mask, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_LINEAR)
        if mask.max() > 1.0:
            mask = mask / 255.0
        return np.clip(mask, 0.0, 1.0)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# YOLO
# ---------------------------------------------------------------------------
def _get_yolo():
    global _yolo, _yolo_failed
    if _yolo is not None or _yolo_failed:
        return _yolo
    with _lock:
        if _yolo is not None or _yolo_failed:
            return _yolo
        if YOLO_MODEL is None:
            _yolo_failed = True
            return None
        try:
            from ultralytics import YOLO

            _yolo = YOLO(str(YOLO_MODEL))
        except Exception:
            _yolo_failed = True
            _yolo = None
    return _yolo


@dataclass
class Person:
    id: int
    bbox: tuple[int, int, int, int]  # x, y, w, h
    confidence: float
    center: tuple[int, int]  # cy, cx
    mask: np.ndarray | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bbox": list(self.bbox),
            "confidence": round(float(self.confidence), 4),
            "center": list(self.center),
        }


def detect_persons(frame: np.ndarray, confidence: float = 0.25) -> list[Person]:
    """Detect people (class 0) with YOLOv8-seg."""
    model = _get_yolo()
    if model is None or frame is None or frame.size == 0:
        return []
    try:
        results = model.predict(frame, conf=confidence, classes=[0], verbose=False)
    except Exception:
        return []
    people: list[Person] = []
    if not results:
        return people
    result = results[0]
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return people
    xyxy = boxes.xyxy.detach().cpu().numpy()
    confs = boxes.conf.detach().cpu().numpy()
    ids = boxes.id
    track_ids = ids.detach().cpu().numpy().astype(int) if ids is not None else None
    masks = getattr(result, "masks", None)
    mask_data = None
    if masks is not None and getattr(masks, "data", None) is not None:
        mask_data = masks.data.detach().cpu().numpy()
    h, w = frame.shape[:2]
    for index, (box, conf) in enumerate(zip(xyxy, confs)):
        x1, y1, x2, y2 = [int(round(float(v))) for v in box]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        bw, bh = max(1, x2 - x1), max(1, y2 - y1)
        mask = None
        if mask_data is not None and index < len(mask_data):
            import cv2

            mask = mask_data[index]
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
            mask = np.clip((mask > 0.5).astype(np.float32), 0, 1)
        people.append(
            Person(
                id=int(track_ids[index]) if track_ids is not None else index,
                bbox=(x1, y1, bw, bh),
                confidence=float(conf),
                center=(y1 + bh // 2, x1 + bw // 2),
                mask=mask,
            )
        )
    return people


class PersonTracker:
    """Persistent tracker for frame-by-frame export pipelines.

    Uses YOLO tracking when available, otherwise falls back to per-frame
    detection with greedy IoU matching.
    """

    def __init__(self, confidence: float = 0.25):
        self.confidence = confidence
        self._last: list[Person] = []
        self._next_id = 1
        self._track_model = None

    def _get_track_model(self):
        if self._track_model is not None:
            return self._track_model
        model = _get_yolo()
        if model is None:
            return None
        self._track_model = model
        return model

    def track(self, frame: np.ndarray) -> list[Person]:
        model = self._get_track_model()
        if model is not None:
            try:
                results = model.track(
                    frame,
                    conf=self.confidence,
                    classes=[0],
                    persist=True,
                    verbose=False,
                )
                if results:
                    people = _people_from_result(results[0], frame.shape[:2])
                    if people:
                        self._last = people
                        return people
            except Exception:
                pass
        people = detect_persons(frame, self.confidence)
        people = self._match(people)
        self._last = people
        return people

    def _match(self, current: list[Person]) -> list[Person]:
        if not self._last:
            for person in current:
                person.id = self._next_id
                self._next_id += 1
            return current
        used: set[int] = set()
        for person in current:
            best = None
            best_iou = 0.0
            for old in self._last:
                if old.id in used:
                    continue
                iou = _iou(person.bbox, old.bbox)
                if iou > best_iou:
                    best_iou = iou
                    best = old
            if best is not None and best_iou > 0.2:
                person.id = best.id
                used.add(best.id)
            else:
                person.id = self._next_id
                self._next_id += 1
        return current


def _people_from_result(result, shape: tuple[int, int]) -> list[Person]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []
    xyxy = boxes.xyxy.detach().cpu().numpy()
    confs = boxes.conf.detach().cpu().numpy()
    ids = boxes.id
    track_ids = ids.detach().cpu().numpy().astype(int) if ids is not None else None
    masks = getattr(result, "masks", None)
    mask_data = None
    if masks is not None and getattr(masks, "data", None) is not None:
        mask_data = masks.data.detach().cpu().numpy()
    h, w = shape
    people = []
    for index, (box, conf) in enumerate(zip(xyxy, confs)):
        x1, y1, x2, y2 = [int(round(float(v))) for v in box]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        bw, bh = max(1, x2 - x1), max(1, y2 - y1)
        mask = None
        if mask_data is not None and index < len(mask_data):
            import cv2

            mask = cv2.resize(mask_data[index], (w, h), interpolation=cv2.INTER_LINEAR)
            mask = (mask > 0.5).astype(np.float32)
        people.append(
            Person(
                id=int(track_ids[index]) if track_ids is not None else index,
                bbox=(x1, y1, bw, bh),
                confidence=float(conf),
                center=(y1 + bh // 2, x1 + bw // 2),
                mask=mask,
            )
        )
    return people


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
# Selection / masks
# ---------------------------------------------------------------------------
def select_person(
    frame: np.ndarray,
    point: tuple[int, int] | None = None,
    *,
    index: int = 0,
) -> Person | None:
    people = detect_persons(frame)
    if not people:
        return None
    if point is not None:
        py, px = point
        inside = [
            p for p in people
            if p.bbox[0] <= px <= p.bbox[0] + p.bbox[2]
            and p.bbox[1] <= py <= p.bbox[1] + p.bbox[3]
        ]
        if inside:
            return max(inside, key=lambda p: p.confidence)
        return min(people, key=lambda p: (p.center[0] - py) ** 2 + (p.center[1] - px) ** 2)
    return people[min(max(0, index), len(people) - 1)]


def person_mask(
    frame: np.ndarray,
    *,
    point: tuple[int, int] | None = None,
    index: int = 0,
) -> np.ndarray | None:
    """Return a person mask using YOLO, falling back to MediaPipe/GrabCut."""
    person = select_person(frame, point, index=index)
    if person is not None and person.mask is not None:
        return person.mask
    if point is None and index == 0:
        mask = segment_person(frame)
        if mask is not None and mask.max() > 0.01:
            return mask
    if person is not None:
        return grabcut_mask(frame, person.bbox)
    return segment_person(frame)


def grabcut_mask(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray | None:
    """GrabCut fallback for a single bounding box."""
    if frame is None or frame.size == 0:
        return None
    try:
        import cv2

        h, w = frame.shape[:2]
        x, y, bw, bh = bbox
        x, y = max(0, x), max(0, y)
        bw, bh = min(w - x, max(2, bw)), min(h - y, max(2, bh))
        mask = np.zeros((h, w), np.uint8)
        bgd = np.zeros((1, 65), np.float64)
        fgd = np.zeros((1, 65), np.float64)
        rect = (x, y, bw, bh)
        cv2.grabCut(frame, mask, rect, bgd, fgd, 4, cv2.GC_INIT_WITH_RECT)
        out = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1.0, 0.0).astype(np.float32)
        return out
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Face detection (for accessories)
# ---------------------------------------------------------------------------
def _get_haar():
    global _haar
    if _haar is None and HAAR_CASCADE is not None:
        try:
            import cv2

            _haar = cv2.CascadeClassifier(str(HAAR_CASCADE))
            if _haar.empty():
                _haar = None
        except Exception:
            _haar = None
    return _haar


def detect_faces(frame: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Return face boxes ``(x, y, w, h)`` using the bundled Haar cascade."""
    cascade = _get_haar()
    if cascade is None or frame is None:
        return []
    try:
        import cv2

        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        return [tuple(int(v) for v in face) for face in faces]
    except Exception:
        return []


def largest_face(frame: np.ndarray) -> tuple[int, int, int, int] | None:
    faces = detect_faces(frame)
    if not faces:
        return None
    return max(faces, key=lambda box: box[2] * box[3])
