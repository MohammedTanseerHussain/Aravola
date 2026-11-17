"""Preview and export transition blending.

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


class TransitionsMixin:
    """Preview and export transition blending."""

    def _apply_transition_blend(self, img, t, target_w, target_h):
        """If the playhead is inside a transition zone between two adjacent
        clips, blend the outgoing and incoming frames according to the
        transition type.  Returns the (possibly blended) PIL Image."""
        td = self.TRANSITION_DUR
        if td <= 0:
            return img

        is_mobile = (self.format_var.get() == "mobile")

        for idx in range(len(self.media_queue) - 1):
            item_a = self.media_queue[idx]
            item_b = self.media_queue[idx + 1]
            a_start = item_a.get("tl_start", 0.0)
            a_dur = self._item_duration(item_a)
            a_end = a_start + a_dur
            b_start = item_b.get("tl_start", 0.0)

            trans = item_a.get("trans", "Crossfade")
            if trans == "Hard Cut":
                continue

            overlap = max(0.0, a_end - b_start)
            zone = min(td, overlap / 2.0) if overlap > 0 else td

            in_a_tail = (a_end - zone) <= t < a_end
            in_b_head = b_start <= t < (b_start + zone)

            if in_a_tail or in_b_head:
                if in_a_tail:
                    progress = (t - (a_end - zone)) / zone
                else:
                    progress = (t - b_start) / zone + 1.0
                progress = max(0.0, min(1.0, progress))

                local_a = self._item_duration(item_a) - zone + (t - (a_end - zone)) if in_a_tail else self._item_duration(item_a)
                local_a = max(0.0, min(local_a, self._item_duration(item_a) - 0.01))
                if in_b_head:
                    local_b = t - b_start
                else:
                    local_b = 0.0
                local_b = max(0.0, min(local_b, self._item_duration(item_b) - 0.01))

                frame_a = self._render_clip_frame(item_a, local_a, target_w, target_h, is_mobile)
                frame_b = self._render_clip_frame(item_b, local_b, target_w, target_h, is_mobile)

                arr_a = np.array(frame_a).astype(np.float32)
                arr_b = np.array(frame_b).astype(np.float32)

                if arr_a.shape != arr_b.shape:
                    return img

                p = progress

                if trans == "Crossfade":
                    blended = arr_a * (1 - p) + arr_b * p

                elif trans == "Dip to Black":
                    if p < 0.5:
                        blended = arr_a * (1 - p * 2)
                    else:
                        blended = arr_b * ((p - 0.5) * 2)

                elif trans == "Slide Left":
                    shift = int(p * target_w)
                    left_a = arr_a[:, shift:]
                    pad_a = np.zeros((target_h, shift, 3), dtype=np.float32)
                    slide_a = np.concatenate([left_a, pad_a], axis=1)
                    right_b = arr_b[:, :target_w - shift]
                    pad_b = np.zeros((target_h, target_w - right_b.shape[1], 3), dtype=np.float32)
                    slide_b = np.concatenate([pad_b, right_b], axis=1)
                    blended = slide_a * (1 - p) + slide_b * p

                elif trans == "Slide Up":
                    shift = int(p * target_h)
                    top_a = arr_a[shift:]
                    pad_a = np.zeros((shift, target_w, 3), dtype=np.float32)
                    slide_a = np.concatenate([top_a, pad_a], axis=0)
                    bot_b = arr_b[:target_h - shift]
                    pad_b = np.zeros((target_h - bot_b.shape[0], target_w, 3), dtype=np.float32)
                    slide_b = np.concatenate([pad_b, bot_b], axis=0)
                    blended = slide_a * (1 - p) + slide_b * p

                elif trans == "Zoom In Fade":
                    if p < 0.4:
                        fade = p / 0.4
                        blended = arr_a * (1 - fade)
                    else:
                        fade = (p - 0.4) / 0.6
                        scale = 1.0 + fade * 0.15
                        zw = int(target_w * scale)
                        zh = int(target_h * scale)
                        b_zoomed = cv2.resize(arr_b, (zw, zh))
                        x0 = (zw - target_w) // 2
                        y0 = (zh - target_h) // 2
                        b_cropped = b_zoomed[y0:y0 + target_h, x0:x0 + target_w]
                        blended = b_cropped * fade

                elif trans == "Bright Flash":
                    Y, X = np.mgrid[0:target_h, 0:target_w].astype(np.float32)
                    h, w = target_h, target_w
                    flare_positions = [
                        (0.18, 0.22), (0.75, 0.15), (0.50, 0.50),
                        (0.25, 0.78), (0.80, 0.70), (0.12, 0.55),
                        (0.88, 0.38), (0.42, 0.18), (0.62, 0.85),
                    ]
                    flare_scale = min(w, h) * 0.018
                    combined = np.zeros((h, w), dtype=np.float32)

                    for fi, (fx, fy) in enumerate(flare_positions):
                        px, py = fx * w, fy * h
                        dx, dy = X - px, Y - py
                        d = np.sqrt(dx**2 + dy**2)
                        arm_len = flare_scale * (2.5 + 1.5 * np.sin(fi * 1.7))
                        falloff = np.exp(-d**2 / (2 * arm_len**2))
                        da = np.abs(dy - dx)
                        db = np.abs(dy + dx)
                        arm_w = flare_scale * 0.6
                        xshape = np.maximum(np.clip(1.0 - da / arm_w, 0, 1),
                                             np.clip(1.0 - db / arm_w, 0, 1))
                        star = falloff * xshape

                        if p < 0.10:
                            appear = p / 0.10
                            twinkle = (np.sin(fi * 3.14 + p * 60.0) * 0.5 + 0.5)
                            intensity = appear * twinkle * 0.35
                        elif p < 0.30:
                            appear = (p - 0.10) / 0.20
                            twinkle = (np.sin(fi * 3.14 + p * 80.0) * 0.5 + 0.5)
                            intensity = (0.35 + appear * 0.55) * twinkle
                        elif p < 0.45:
                            grow = (p - 0.30) / 0.15
                            intensity = 0.9 + grow * 0.1
                            if fi == 4:
                                intensity = 1.0 + grow * 2.0
                                falloff2 = np.exp(-d**2 / (2 * (arm_len * (1 + grow * 4))**2))
                                star = falloff2 * xshape
                            else:
                                star = falloff * xshape * (1 + grow)
                        else:
                            intensity = 0.0

                        combined = np.maximum(combined, star * min(intensity, 3.0))

                    combined = np.clip(combined, 0, 1)

                    if p < 0.45:
                        blended = arr_a * (1 - combined[..., np.newaxis]) + 255.0 * (combined[..., np.newaxis])
                    elif p < 0.55:
                        blended = np.full_like(arr_a, 255.0)
                    else:
                        fade = (p - 0.55) / 0.45
                        ease = fade * fade * (3 - 2 * fade)
                        blended = arr_b * ease + 255.0 * (1 - ease)

                elif trans == "Pull and Snap":
                    # ── PULL AND SNAP: SCALE + SHAKE + BLINK + FLIP ──

                    PULL_DUR_FRAC = 0.50
                    SETTLE_DUR_FRAC = 0.50

                    def _center_fit(scaled_arr, tw, th):
                        sh, sw = scaled_arr.shape[:2]
                        sx = max(0, (sw - tw) // 2)
                        sy = max(0, (sh - th) // 2)
                        cw = min(sw, tw)
                        ch = min(sh, th)
                        dx = (tw - cw) // 2
                        dy = (th - ch) // 2
                        out = np.zeros((th, tw, 3), dtype=scaled_arr.dtype)
                        out[dy:dy + ch, dx:dx + cw] = scaled_arr[sy:sy + ch, sx:sx + cw]
                        return out

                    def _shake(arr, sx, sy):
                        return np.roll(np.roll(arr, int(sy), axis=0), int(sx), axis=1)

                    def _blink(arr, t, freq, white_level):
                        """Fast on/off blink — alternates between frame and bright flash."""
                        # Square wave: 1 = frame, 0 = bright flash
                        on = (math.sin(t * freq) > 0.0)
                        if on:
                            return arr
                        else:
                            f = arr.astype(np.float32)
                            f += white_level * 255.0
                            return np.clip(f, 0, 255).astype(arr.dtype)

                    def _blink_multi(arr, t, base_freq, strength):
                        """Ultra-fast strobe blink — multiple freq layers."""
                        # Combine two frequencies for irregular strobe
                        v = math.sin(t * base_freq) + math.sin(t * base_freq * 1.7)
                        on = v > 0.0
                        if not on:
                            f = arr.astype(np.float32)
                            f += strength * 255.0
                            return np.clip(f, 0, 255).astype(arr.dtype)
                        return arr

                    def _skew(arr, px):
                        if abs(px) < 0.5:
                            return arr
                        h, w = arr.shape[:2]
                        out = np.zeros_like(arr)
                        for row in range(h):
                            s = int(px * (row / h - 0.5))
                            if s >= 0:
                                out[row, s:] = arr[row, :w - s]
                            else:
                                out[row, :w + s] = arr[row, -s:]
                        return out

                    if p < PULL_DUR_FRAC:
                        # ── PART 1: THE PULL (shrink + flip + blink) ──
                        local_p = p / PULL_DUR_FRAC
                        ease_in = local_p * local_p

                        # Scale: 100% → 65%
                        scale_a = 1.0 - 0.35 * ease_in

                        # Shake: violent ramp-up
                        shake_amp = ease_in * ease_in * 20.0
                        shake_x = math.sin(local_p * 80.0) * shake_amp
                        shake_y = math.cos(local_p * 65.0) * shake_amp * 0.9

                        # Flip: starts flickering/flipping as shrink intensifies
                        do_flip = local_p > 0.20 and int(local_p * 40) % 2 == 0

                        # Blink: ultra-fast strobe, intensifies toward cut
                        blink_str = ease_in * 0.8

                        # Skew: increasing whip
                        skew_val = ease_in * 15.0 * math.sin(local_p * 35.0)

                        zw = max(1, int(target_w * scale_a))
                        zh = max(1, int(target_h * scale_a))
                        a_scaled = cv2.resize(arr_a, (zw, zh))
                        result = _center_fit(a_scaled, target_w, target_h)
                        result = _shake(result, shake_x, shake_y)
                        result = _skew(result, skew_val)
                        if do_flip:
                            result = result[:, ::-1].copy()
                        result = _blink_multi(result, local_p, 55.0, blink_str)
                        blended = result

                    else:
                        # ── PART 2+3: SNAP + SETTLE ──
                        local_p = (p - PULL_DUR_FRAC) / (1.0 - PULL_DUR_FRAC)

                        # Scale: 140% → 100% with bounce
                        if local_p < 0.01:
                            scale_b = 1.40
                        else:
                            settle_p = min(1.0, (local_p - 0.01) / 0.99)
                            bounce = math.sin(settle_p * math.pi * 3.0) * math.exp(-5.0 * settle_p)
                            scale_b = 1.0 + 0.40 * (1.0 - settle_p) + bounce * 0.08

                        # Flip: rapid strobe flip during first 40%
                        do_flip = local_p < 0.40 and int(local_p * 35) % 2 == 0

                        # Shake: violent slam, fast decay
                        impact = math.exp(-18.0 * local_p)
                        shake_x = math.sin(local_p * 130.0) * impact * 20.0
                        shake_y = math.cos(local_p * 110.0) * impact * 15.0

                        # Blink: fast strobe fading out
                        blink_str = math.exp(-6.0 * local_p) * 1.0

                        # Skew: whip snap
                        skew_val = math.exp(-10.0 * local_p) * 18.0 * math.sin(local_p * 55.0)

                        zw = max(1, int(target_w * scale_b))
                        zh = max(1, int(target_h * scale_b))
                        b_scaled = cv2.resize(arr_b, (zw, zh))
                        result = _center_fit(b_scaled, target_w, target_h)
                        result = _shake(result, shake_x, shake_y)
                        result = _skew(result, skew_val)
                        if do_flip:
                            result = result[:, ::-1].copy()
                        result = _blink_multi(result, local_p, 80.0, blink_str)
                        blended = result

                else:
                    blended = arr_a * (1 - p) + arr_b * p

                blended = np.clip(blended, 0, 255).astype(np.uint8)
                return PIL.Image.fromarray(blended)

        return img

    def _apply_export_transitions(self, clips, target_w, target_h):
        """Apply transitions between consecutive clips during export.
        For 'Pull and Snap', applies scale transforms to each clip independently.
        For all other transitions, uses moviepy crossfadein."""
        td = self.TRANSITION_DUR
        if td <= 0 or len(clips) < 2:
            return clips

        PULL_DUR_FRAC = 0.50
        SETTLE_DUR_FRAC = 0.50

        def _center_fit_exp(scaled_arr, tw, th):
            sh, sw = scaled_arr.shape[:2]
            sx = max(0, (sw - tw) // 2)
            sy = max(0, (sh - th) // 2)
            cw = min(sw, tw)
            ch = min(sh, th)
            dx = (tw - cw) // 2
            dy = (th - ch) // 2
            out = np.zeros((th, tw, 3), dtype=scaled_arr.dtype)
            out[dy:dy + ch, dx:dx + cw] = scaled_arr[sy:sy + ch, sx:sx + cw]
            return out

        def _shake_exp(arr, sx, sy):
            return np.roll(np.roll(arr, int(sy), axis=0), int(sx), axis=1)

        def _blink_multi_exp(arr, t, base_freq, strength):
            v = math.sin(t * base_freq) + math.sin(t * base_freq * 1.7)
            if v <= 0.0:
                f = arr.astype(np.float32)
                f += strength * 255.0
                return np.clip(f, 0, 255).astype(arr.dtype)
            return arr

        def _skew_exp(arr, px):
            if abs(px) < 0.5:
                return arr
            h, w = arr.shape[:2]
            out = np.zeros_like(arr)
            for row in range(h):
                s = int(px * (row / h - 0.5))
                if s >= 0:
                    out[row, s:] = arr[row, :w - s]
                else:
                    out[row, :w + s] = arr[row, -s:]
            return out

        final = []
        for idx, clip in enumerate(clips):
            item_prev = self.media_queue[idx - 1] if idx >= 1 and idx - 1 < len(self.media_queue) else None
            trans = item_prev.get("trans", "Crossfade") if item_prev else "Crossfade"

            if idx == 0:
                final.append(clip)
                continue

            if trans == "Hard Cut":
                final.append(clip.set_start(clip.start))
            elif trans == "Pull and Snap":
                clip_b = clip
                clip_a = final[-1]

                def _pull_frame(get_frame_a, tt, _clip_dur):
                    frame = get_frame_a(tt)
                    if tt >= _clip_dur - td:
                        zone_tt = tt - (_clip_dur - td)
                        local_p = min(1.0, zone_tt / (td * PULL_DUR_FRAC))
                        ease_in = local_p * local_p
                        scale_a = 1.0 - 0.35 * ease_in
                        arr = frame.astype(np.float32)
                        zw = max(1, int(target_w * scale_a))
                        zh = max(1, int(target_h * scale_a))
                        scaled = cv2.resize(arr, (zw, zh))
                        result = _center_fit_exp(scaled, target_w, target_h)
                        shake_amp = ease_in * ease_in * 20.0
                        result = _shake_exp(result, math.sin(local_p * 80.0) * shake_amp,
                                            math.cos(local_p * 65.0) * shake_amp * 0.9)
                        result = _skew_exp(result, ease_in * 15.0 * math.sin(local_p * 35.0))
                        if local_p > 0.20 and int(local_p * 40) % 2 == 0:
                            result = result[:, ::-1].copy()
                        result = _blink_multi_exp(result, local_p, 55.0, ease_in * 0.8)
                        return np.clip(result, 0, 255).astype(np.uint8)
                    return frame

                def _snap_settle_frame(get_frame_b, tt):
                    snap_settle_dur = td * SETTLE_DUR_FRAC
                    if tt < snap_settle_dur:
                        local_p = tt / snap_settle_dur
                        if local_p < 0.01:
                            scale_b = 1.40
                        else:
                            settle_p = min(1.0, (local_p - 0.01) / 0.99)
                            bounce = math.sin(settle_p * math.pi * 3.0) * math.exp(-5.0 * settle_p)
                            scale_b = 1.0 + 0.40 * (1.0 - settle_p) + bounce * 0.08
                        frame = get_frame_b(tt)
                        arr = frame.astype(np.float32)
                        zw = max(1, int(target_w * scale_b))
                        zh = max(1, int(target_h * scale_b))
                        scaled = cv2.resize(arr, (zw, zh))
                        result = _center_fit_exp(scaled, target_w, target_h)
                        impact = math.exp(-18.0 * local_p)
                        result = _shake_exp(result, math.sin(local_p * 130.0) * impact * 20.0,
                                            math.cos(local_p * 110.0) * impact * 15.0)
                        result = _skew_exp(result, math.exp(-10.0 * local_p) * 18.0 * math.sin(local_p * 55.0))
                        if local_p < 0.40 and int(local_p * 35) % 2 == 0:
                            result = result[:, ::-1].copy()
                        result = _blink_multi_exp(result, local_p, 80.0, math.exp(-6.0 * local_p) * 1.0)
                        return np.clip(result, 0, 255).astype(np.uint8)
                    return get_frame_b(tt)

                _cad = clip_a.duration
                clip_a_modified = clip_a.fl(lambda gf, tt, _d=_cad: _pull_frame(gf, tt, _d))
                final[-1] = clip_a_modified

                clip_b_modified = clip_b.fl(lambda gf, tt: _snap_settle_frame(gf, tt))
                clip_b_modified = clip_b_modified.set_start(clip_a.end)
                final.append(clip_b_modified)
            else:
                final.append(clip.crossfadein(td))

        return final
