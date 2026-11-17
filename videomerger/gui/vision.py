"""MediaPipe/YOLO initialisation and low-level mask helpers.

Split mechanically from the legacy desktop application.  See
``videomerger.gui.runtime`` for shared imports and lazy MoviePy/Pygame setup.
"""
from __future__ import annotations

from .runtime import *  # noqa: F401,F403
from .runtime import (
    HAS_PYGAME,
    _HAAR_CASCADE_PATH,
    _MOVIEPY_LOADED,
    _TkExportProgressLogger,
    _ensure_moviepy,
    _ensure_pygame,
    pygame,
)
from ..config import SEGMENTER_MODEL, YOLO_MODEL


class VisionMixin:
    """MediaPipe/YOLO initialisation and low-level mask helpers."""

    def _init_mediapipe(self):
        self._mp_segmentor = None
        self._mp_available = False
        try:
            import mediapipe as mp  # type: ignore
            model_path = str(SEGMENTER_MODEL) if SEGMENTER_MODEL else ""
            if not model_path or not os.path.exists(model_path):
                print("WARNING: selfie_segmenter.tflite model not found. Gold outline will use GrabCut fallback.")
                return
            BaseOptions = mp.tasks.BaseOptions
            ImageSegmenter = mp.tasks.vision.ImageSegmenter
            ImageSegmenterOptions = mp.tasks.vision.ImageSegmenterOptions
            options = ImageSegmenterOptions(
                base_options=BaseOptions(model_asset_path=model_path),
                running_mode=mp.tasks.vision.RunningMode.IMAGE,
                output_category_mask=True
            )
            self._mp_segmentor = ImageSegmenter.create_from_options(options)
            self._mp_available = True
            print("MediaPipe selfie segmenter loaded successfully.")
        except Exception as e:
            print(f"WARNING: MediaPipe initialization failed: {e}")
            self._mp_segmentor = None
            self._mp_available = False

    def _init_yolo(self):
        self._yolo_model = None
        try:
            if YOLO_MODEL is None:
                print("WARNING: YOLOv8-seg model not found.")
                return
            from ultralytics import YOLO
            self._yolo_model = YOLO(str(YOLO_MODEL))
            print("YOLOv8-seg model loaded successfully.")
            # Suppress noisy GMC optical flow warnings (OpenCV 5.0 bug)
            # Patch the LOGGER object directly — warnings come from multiple trackers
            try:
                from ultralytics.utils import LOGGER as _yl_logger
                _orig_warning = _yl_logger.warning
                def _no_gmc_warning(msg, *a, **kw):
                    if "GMC failed" in str(msg):
                        return
                    return _orig_warning(msg, *a, **kw)
                _yl_logger.warning = _no_gmc_warning
            except Exception:
                pass
        except Exception as e:
            print(f"WARNING: YOLOv8 initialization failed: {e}")
            self._yolo_model = None

    def _yolo_track(self, frame):
        """Run YOLOv8-seg tracking on a frame (video) or detection (image).
        Returns list of dicts for ALL detected objects (not just persons).
        [{'id': track_id, 'class_id': int, 'class_name': str, 'conf': float,
          'mask': ndarray, 'bbox': (x,y,w,h), 'center': (cy,cx), 'area': int}]
        """
        if self._yolo_model is None:
            self._init_yolo()
        if self._yolo_model is None:
            return []

        coco_names = [
            'person','bicycle','car','motorcycle','airplane','bus','train','truck',
            'boat','traffic light','fire hydrant','stop sign','parking meter','bench',
            'bird','cat','dog','horse','sheep','cow','elephant','bear','zebra',
            'giraffe','backpack','umbrella','handbag','tie','suitcase','frisbee',
            'skis','snowboard','sports ball','kite','baseball bat','baseball glove',
            'skateboard','surfboard','tennis racket','bottle','wine glass','cup',
            'fork','knife','spoon','bowl','banana','apple','sandwich','orange',
            'broccoli','carrot','hot dog','pizza','donut','cake','chair','couch',
            'potted plant','bed','dining table','toilet','tv','laptop','mouse',
            'remote','keyboard','cell phone','microwave','oven','toaster','sink',
            'refrigerator','book','clock','vase','scissors','teddy bear',
            'hair drier','toothbrush',
        ]

        try:
            results = self._yolo_model.track(frame, persist=True, verbose=False, conf=0.15)
            detections = []
            has_tracking = (results and results[0].boxes is not None
                            and results[0].boxes.id is not None)
            if has_tracking:
                boxes = results[0].boxes.cpu().numpy()
                track_ids = boxes.id.astype(int)
                xyxy = boxes.xyxy
                clss = boxes.cls.astype(int)
                confs = boxes.conf.astype(float)
                masks_data = results[0].masks
                for i, tid in enumerate(track_ids):
                    x1, y1, x2, y2 = xyxy[i]
                    bw, bh = int(x2 - x1), int(y2 - y1)
                    cid = int(clss[i]) if i < len(clss) else 0
                    cname = coco_names[cid] if cid < len(coco_names) else f'class_{cid}'
                    obj_mask = None
                    sharp_mask = None
                    if masks_data is not None and i < len(masks_data):
                        mask_xy = masks_data.xy[i]
                        if mask_xy is not None and len(mask_xy) > 2:
                            h, w = frame.shape[:2]
                            sharp_mask = np.zeros((h, w), dtype=np.float32)
                            pts = np.array(mask_xy, dtype=np.int32)
                            cv2.fillPoly(sharp_mask, [pts], 1.0)
                            obj_mask = cv2.GaussianBlur(sharp_mask, (5, 5), 0)
                    detections.append({
                        'id': int(tid),
                        'class_id': cid,
                        'class_name': cname,
                        'conf': float(confs[i]) if i < len(confs) else 0.0,
                        'mask': obj_mask,
                        'raw_mask': sharp_mask if sharp_mask is not None else obj_mask,
                        'bbox': (int(x1), int(y1), bw, bh),
                        'center': (int(y1 + bh // 2), int(x1 + bw // 2)),
                        'area': bw * bh,
                    })
            else:
                results = self._yolo_model(frame, verbose=False, conf=0.15)
                if results and results[0].boxes is not None:
                    boxes = results[0].boxes.cpu().numpy()
                    xyxy = boxes.xyxy
                    clss = boxes.cls.astype(int)
                    confs = boxes.conf.astype(float)
                    masks_data = results[0].masks
                    for i in range(len(xyxy)):
                        x1, y1, x2, y2 = xyxy[i]
                        bw, bh = int(x2 - x1), int(y2 - y1)
                        cid = int(clss[i]) if i < len(clss) else 0
                        cname = coco_names[cid] if cid < len(coco_names) else f'class_{cid}'
                        obj_mask = None
                        sharp_mask = None
                        if masks_data is not None and i < len(masks_data):
                            mask_xy = masks_data.xy[i]
                            if mask_xy is not None and len(mask_xy) > 2:
                                h, w = frame.shape[:2]
                                sharp_mask = np.zeros((h, w), dtype=np.float32)
                                pts = np.array(mask_xy, dtype=np.int32)
                                cv2.fillPoly(sharp_mask, [pts], 1.0)
                                obj_mask = cv2.GaussianBlur(sharp_mask, (5, 5), 0)
                        detections.append({
                            'id': i,
                            'class_id': cid,
                            'class_name': cname,
                            'conf': float(confs[i]) if i < len(confs) else 0.0,
                            'mask': obj_mask,
                            'raw_mask': sharp_mask if sharp_mask is not None else obj_mask,
                            'bbox': (int(x1), int(y1), bw, bh),
                            'center': (int(y1 + bh // 2), int(x1 + bw // 2)),
                            'area': bw * bh,
                        })
            return detections
        except Exception as e:
            print(f"YOLO tracking error: {e}")
            return []

    def _get_mediapipe_mask(self, frame):
        if self._mp_segmentor is None:
            self._init_mediapipe()
        if self._mp_segmentor is None:
            return None
        try:
            import mediapipe as mp  # type: ignore
            h, w = frame.shape[:2]
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            result = self._mp_segmentor.segment(mp_img)
            if result.confidence_masks and len(result.confidence_masks) > 0:
                mask = result.confidence_masks[0].numpy_view().astype(np.float32)
                if mask.ndim == 3:
                    mask = mask[..., 0]
                mask = cv2.GaussianBlur(mask, (7, 7), 0)
                mask_uint8 = (mask * 255).astype(np.uint8)
                kernel = np.ones((5, 5), np.uint8)
                mask_uint8 = cv2.morphologyEx(mask_uint8, cv2.MORPH_OPEN, kernel, iterations=1)
                mask_uint8 = cv2.morphologyEx(mask_uint8, cv2.MORPH_CLOSE, kernel, iterations=2)
                num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_uint8, connectivity=8)
                h_m, w_m = mask_uint8.shape
                min_area = (h_m * w_m) * 0.001
                clean = np.zeros_like(mask_uint8)
                for i in range(1, num_labels):
                    if stats[i, cv2.CC_STAT_AREA] >= min_area:
                        clean[labels == i] = mask_uint8[labels == i]
                mask = clean.astype(np.float32) / 255.0
                mask = cv2.GaussianBlur(mask, (5, 5), 0)
                return mask
        except Exception as e:
            print(f"WARNING: MediaPipe segmentation failed: {e}")
        return None

    def _apply_zoom_blur(self, img, center, zoom_factor=1.08, num_steps=25):
        h, w = img.shape[:2]
        result = np.zeros((h, w, 3), dtype=np.float32)
        for i in range(num_steps):
            scale = 1.0 + (zoom_factor - 1.0) * (i / num_steps)
            matrix = cv2.getRotationMatrix2D(center, 0, scale)
            scaled = cv2.warpAffine(img, matrix, (w, h))
            result += scaled
        result = result / num_steps
        return result

    def _smooth_mask_for_outline(self, mask):
        """Smooth a mask to produce clean, flowing outline contours."""
        smooth = cv2.GaussianBlur(mask, (7, 7), 0)
        kernel = np.ones((5, 5), np.uint8)
        smooth_uint8 = (smooth * 255).astype(np.uint8)
        smooth_uint8 = cv2.morphologyEx(smooth_uint8, cv2.MORPH_CLOSE, kernel, iterations=1)
        smooth = cv2.GaussianBlur(smooth_uint8.astype(np.float32) / 255.0, (5, 5), 0)
        return smooth

    def _get_mediapipe_edges(self, frame):
        mask = self._get_mediapipe_mask(frame)
        if mask is None:
            return np.zeros((frame.shape[0], frame.shape[1]), dtype=np.float32)
        mask_uint8 = (mask * 255).astype(np.uint8)
        edges = cv2.Canny(mask_uint8, 30, 90)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
        edges = cv2.GaussianBlur(edges, (3, 3), 0)
        return edges.astype(np.float32) / 255.0

    def _generate_mask_from_bbox(self, frame, bbox):
        """Generate a person mask from a bounding box using GrabCut + contour fallback.
        Used when YOLO and MediaPipe masks are unavailable."""
        h, w = frame.shape[:2]
        x, y, bw, bh = bbox
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(w, x + bw)
        y1 = min(h, y + bh)
        if x1 - x0 < 10 or y1 - y0 < 10:
            return None
        mask_out = np.zeros((h, w), dtype=np.float32)
        try:
            bgd_model = np.zeros((1, 64), np.float64)
            fgd_model = np.zeros((1, 64), np.float64)
            gc_mask = np.zeros((h, w), np.uint8)
            pad_x = int((x1 - x0) * 0.1)
            pad_y = int((y1 - y0) * 0.1)
            rect = (max(0, x0 - pad_x), max(0, y0 - pad_y),
                    min(w, x1 - x0 + 2 * pad_x), min(h, y1 - y0 + 2 * pad_y))
            rect = tuple(max(1, v) for v in rect)
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            cv2.grabCut(frame_bgr, gc_mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT)
            fg_mask = np.where((gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 1.0, 0.0).astype(np.float32)
            fg_region = fg_mask[y0:y1, x0:x1]
            if fg_region.sum() < (x1 - x0) * (y1 - y0) * 0.05:
                raise ValueError("GrabCut too sparse")
            mask_out[y0:y1, x0:x1] = fg_region
            # Smooth the mask to remove jagged edges before any outline drawing
            mask_out = cv2.GaussianBlur(mask_out, (11, 11), 0)
            mask_out = (mask_out > 0.3).astype(np.float32) * mask_out  # tighten threshold then re-blur
            mask_out = cv2.GaussianBlur(mask_out, (7, 7), 0)
            return mask_out
        except Exception:
            pass
        try:
            roi = frame[y0:y1, x0:x1]
            if roi.size == 0:
                return None
            hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
            lower_skin = np.array([0, 20, 70])
            upper_skin = np.array([20, 255, 255])
            skin_mask = cv2.inRange(hsv, lower_skin, upper_skin)
            lower_dark = np.array([0, 0, 0])
            upper_dark = np.array([180, 255, 80])
            dark_mask = cv2.inRange(hsv, lower_dark, upper_dark)
            combined = cv2.bitwise_or(skin_mask, dark_mask)
            kernel = np.ones((5, 5), np.uint8)
            combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=3)
            combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel, iterations=1)
            contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                # Smooth the contour by approximating it
                epsilon = 0.005 * cv2.arcLength(largest, True)
                largest = cv2.approxPolyDP(largest, epsilon, True)
                fill_mask = np.zeros_like(combined)
                cv2.drawContours(fill_mask, [largest], -1, 255, -1)
                mask_out[y0:y1, x0:x1] = fill_mask.astype(np.float32) / 255.0
            else:
                mask_out[y0:y1, x0:x1] = 1.0
            mask_out = cv2.GaussianBlur(mask_out, (11, 11), 0)
            mask_out = (mask_out > 0.3).astype(np.float32) * mask_out
            mask_out = cv2.GaussianBlur(mask_out, (7, 7), 0)
            return mask_out
        except Exception:
            pass
        mask_out[y0:y1, x0:x1] = 1.0
        mask_out = cv2.GaussianBlur(mask_out, (7, 7), 0)
        return mask_out

    def _detect_all_persons(self, frame):
        h, w = frame.shape[:2]
        persons = []
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            hog = cv2.HOGDescriptor()
            hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            rects, weights = hog.detectMultiScale(gray, winStride=(8, 8),
                                                  padding=(4, 4), scale=1.03)
            for (x, y, pw, ph), wt in zip(rects, weights):
                if pw * ph > (h * w) * 0.008:
                    # Filter: people are typically taller than wide (aspect ratio 0.3-0.8)
                    aspect = pw / max(1, ph)
                    if aspect > 1.2 or aspect < 0.15:
                        continue
                    # Filter: must be reasonably sized (at least 30px each dim)
                    if pw < 30 or ph < 30:
                        continue
                    # Filter: weight confidence
                    if float(wt) < 0.3:
                        continue
                    persons.append({
                        'bbox': (int(x), int(y), int(pw), int(ph)),
                        'center': (int(y + ph // 2), int(x + pw // 2)),
                        'weight': float(wt),
                        'area': pw * ph,
                    })
            persons.sort(key=lambda p: p['area'], reverse=True)
        except Exception:
            pass
        if not persons:
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                face_cascade = cv2.CascadeClassifier(
                    _HAAR_CASCADE_PATH
                )
                faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(30, 30))
                for (fx, fy, fw, fh) in faces:
                    # Expand face bbox downward to include upper body (2.5x height)
                    body_h = int(fh * 2.5)
                    persons.append({
                        'bbox': (int(fx), int(fy), int(fw), body_h),
                        'center': (int(fy + body_h // 2), int(fx + fw // 2)),
                        'weight': 1.0,
                        'area': fw * body_h,
                    })
                persons.sort(key=lambda p: p['area'], reverse=True)
            except Exception:
                pass
        if not persons:
            persons.append({
                'bbox': (max(0, w // 2 - w // 8), max(0, h // 4), w // 4, int(h * 0.66)),
                'center': (h // 2, w // 2),
                'weight': 1.0,
                'area': (w // 4) * int(h * 0.66),
            })
        return persons

    def _get_transformed_frame(self, item):
        """Get the frame exactly as displayed in the preview (after rotation,
        auto-rotate, smart-fill). This ensures click coordinates match detection."""
        frame = self._get_preview_frame(item)
        if frame is None:
            return None
        rot = item.get('rotation', 0)
        if rot == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif rot == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif rot == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if item.get('flip_h', False):
            frame = cv2.flip(frame, 1)
        if item.get('flip_v', False):
            frame = cv2.flip(frame, 0)
        h, w = frame.shape[:2]
        is_mobile = (self.format_var.get() == "mobile")
        target_w = 540 if is_mobile else 960
        target_h = 960 if is_mobile else 540
        if self.auto_rotate_var.get():
            if target_w > target_h and w < h:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                h, w = frame.shape[:2]
            elif target_w < target_h and w > h:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                h, w = frame.shape[:2]
        if self.smart_fill_var.get():
            sf = max(target_w / w, target_h / h)
            frame = cv2.resize(frame, (int(w * sf), int(h * sf)), interpolation=cv2.INTER_LINEAR)
            h, w = frame.shape[:2]
            x0 = (w - target_w) // 2
            y0 = (h - target_h) // 2
            frame = frame[y0:y0 + target_h, x0:x0 + target_w]
        else:
            sf = min(target_w / w, target_h / h)
            frame = cv2.resize(frame, (int(w * sf), int(h * sf)), interpolation=cv2.INTER_LINEAR)
        return frame
