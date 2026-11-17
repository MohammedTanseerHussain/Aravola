"""Background generators and lower-third title builders.

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


class TitlesMixin:
    """Background generators and lower-third title builders."""

    def safe_transform(self, base_clip, rot, flip_h, flip_v):
        if rot == 0 and not flip_h and not flip_v: return base_clip
        def process_f(f):
            if flip_h: f = np.fliplr(f)
            if flip_v: f = np.flipud(f)
            if rot == 90: f = np.rot90(f, k=-1, axes=(0, 1))
            elif rot == 180: f = np.rot90(f, k=2, axes=(0, 1))
            elif rot in [270, -90]: f = np.rot90(f, k=1, axes=(0, 1))
            return f
        new_clip = base_clip.fl_image(process_f)
        w, h = base_clip.size if base_clip.size else (0, 0)
        if rot in [90, -90, 270]: new_clip.size = (h, w)
        if getattr(base_clip, 'mask', None):
            new_mask = base_clip.mask.fl_image(process_f)
            if rot in [90, -90, 270]: new_mask.size = (h, w)
            new_clip = new_clip.set_mask(new_mask)
        return new_clip

    def create_warp_background(self, w, h, duration):
        y, x = np.mgrid[:h, :w]; cx, cy = w / 2.0, h / 2.0; dx = x - cx; dy = y - cy; r = np.sqrt(dx**2 + dy**2); theta = np.arctan2(dy, dx); theta_norm = (theta + np.pi) / (2 * np.pi)
        np.random.seed(42); angle_bins = 150; speeds = np.random.uniform(2000, 5000, angle_bins); line_lengths = np.random.uniform(0.3, 0.8, angle_bins)
        has_laser = np.random.rand(angle_bins) > 0.85; faint_laser = np.random.rand(angle_bins) > 0.50
        palette_r = np.array([255, 255, 180, 100]); palette_g = np.array([255, 50, 50, 100]); palette_b = np.array([255, 255, 255, 255]); color_idx = np.random.randint(0, 4, angle_bins)
        intensity_mult = np.where(has_laser, 1.0, np.where(faint_laser, 0.3, 0.0))
        raw_r = palette_r[color_idx] * intensity_mult; raw_g = palette_g[color_idx] * intensity_mult; raw_b = palette_b[color_idx] * intensity_mult
        r_map = np.convolve(np.tile(raw_r, 3), np.ones(3)/3.0, mode='same')[angle_bins:2*angle_bins]; g_map = np.convolve(np.tile(raw_g, 3), np.ones(3)/3.0, mode='same')[angle_bins:2*angle_bins]; b_map = np.convolve(np.tile(raw_b, 3), np.ones(3)/3.0, mode='same')[angle_bins:2*angle_bins]
        angle_idx = (theta_norm * (angle_bins - 1)).astype(int); base_r = np.full((h, w), 10, dtype=np.float32); base_g = np.full((h, w), 2, dtype=np.float32); base_b = np.full((h, w), 30, dtype=np.float32)
        center_glow = np.exp(-0.5 * (r / 200.0)**2); base_r += 120 * center_glow; base_g += 40 * center_glow; base_b += 200 * center_glow
        def make_frame(t):
            my_speeds = speeds[angle_idx]; my_lengths = line_lengths[angle_idx]; phase = (r * 0.005 - my_speeds * t * 0.001) % 1.0; intensity = np.where(phase < my_lengths, 1.0, 0.0) * np.clip((my_lengths - phase) / (my_lengths * 0.3 + 0.001), 0, 1) * np.clip(r / 100.0, 0, 1)
            frame = np.zeros((h, w, 3), dtype=np.float32)
            frame[..., 0] = base_r + r_map[angle_idx] * intensity; frame[..., 1] = base_g + g_map[angle_idx] * intensity; frame[..., 2] = base_b + b_map[angle_idx] * intensity
            for i in range(3):
                hoop_phase = (t / 1.5 + i * (1.0/3.0)) % 1.0; hoop_r = (hoop_phase**2) * (max(w, h)); hoop_alpha = (np.exp(-0.5 * (np.abs(r - hoop_r) / 2.0)**2) + np.exp(-0.5 * (np.abs(r - hoop_r) / 15.0)**2) * 0.5) * np.clip(hoop_r / 100.0, 0, 1) * np.clip(1.0 - hoop_phase, 0, 1)
                frame[..., 0] += 255 * hoop_alpha; frame[..., 1] += 50 * hoop_alpha; frame[..., 2] += 255 * hoop_alpha
            return np.clip(frame, 0, 255).astype(np.uint8)
        return VideoClip(make_frame, duration=duration)

    def create_starry_sky_background(self, w, h, duration):
        y_g, x_g = np.mgrid[0:h, 0:w]; norm_y = (y_g / h).astype(np.float32); norm_x = (x_g / w).astype(np.float32)
        r = (18 * (1 - norm_y) + 15 * norm_y).astype(np.float32); g = (15 * (1 - norm_y) + 30 * norm_y).astype(np.float32); b = (45 * (1 - norm_y) + 70 * norm_y).astype(np.float32)
        dist_left = np.sqrt((norm_x - 0.2)**2 + (norm_y - 1.0)**2); glow_l = np.clip(1.0 - dist_left * 1.2, 0, 1) ** 2
        r += glow_l * 5; g += glow_l * 40; b += glow_l * 50
        dist_right = np.sqrt((norm_x - 0.8)**2 + (norm_y - 1.0)**2); glow_r = np.clip(1.0 - dist_right * 1.5, 0, 1) ** 2
        r += glow_r * 20; g += glow_r * 10; b += glow_r * 40
        bg_base = np.stack([r, g, b], axis=-1); np.random.seed(101); bg_base[np.random.rand(h, w) > 0.9985] = [230, 240, 255]
        N_twinkle = 400; pad = 20; t_x = np.random.randint(pad, w-pad, N_twinkle); t_y = np.random.randint(pad, h-pad, N_twinkle); t_phase = np.random.uniform(0, 2*np.pi, N_twinkle); t_speed = np.random.uniform(2.0, 6.0, N_twinkle); t_size = np.random.choice([1, 2, 3], N_twinkle, p=[0.5, 0.35, 0.15])
        sn_dur = 0.8; sn_start = duration - sn_dur; comet_dur = 2.0; comet_start = max(0.0, sn_start - comet_dur)
        P0 = np.array([w * 1.1, -h * 0.1]); P1 = np.array([w * 0.75, h / 2.0]); P2 = np.array([w / 2.0, h / 2.0])
        def make_frame(t):
            frame = bg_base.copy(); brights = np.clip((np.sin(t * t_speed + t_phase) * 0.5 + 0.5)**2.5 * 600, 0, 255).astype(np.int32)
            mask_1 = t_size >= 1
            if np.any(mask_1):
                ty1, tx1, b1 = t_y[mask_1], t_x[mask_1], brights[mask_1]
                for dy, dx in [(0,0), (0,1), (1,0), (1,1)]:
                    yy = np.clip(ty1+dy, 0, h-1); xx = np.clip(tx1+dx, 0, w-1); frame[yy, xx, 0] = np.clip(frame[yy, xx, 0] + b1, 0, 255); frame[yy, xx, 1] = np.clip(frame[yy, xx, 1] + b1, 0, 255); frame[yy, xx, 2] = np.clip(frame[yy, xx, 2] + b1, 0, 255)
            mask_2 = t_size >= 2
            if np.any(mask_2):
                ty2, tx2, b2 = t_y[mask_2], t_x[mask_2], brights[mask_2] // 2
                for dy, dx in [(-1,0), (-1,1), (2,0), (2,1), (0,-1), (1,-1), (0,2), (1,2)]:
                    yy = np.clip(ty2+dy, 0, h-1); xx = np.clip(tx2+dx, 0, w-1); frame[yy, xx, 0] = np.clip(frame[yy, xx, 0] + b2, 0, 255); frame[yy, xx, 1] = np.clip(frame[yy, xx, 1] + b2, 0, 255); frame[yy, xx, 2] = np.clip(frame[yy, xx, 2] + b2, 0, 255)
            mask_3 = t_size == 3
            if np.any(mask_3):
                ty3, tx3, b3 = t_y[mask_3], t_x[mask_3], brights[mask_3]
                for step in range(2, 14):
                    decay = max(0, 1.0 - (step / 14.0)); b_r = (b3 * decay * 0.7).astype(np.int32); b_g = (b3 * decay * 0.9).astype(np.int32); b_b = (b3 * decay * 1.0).astype(np.int32)
                    for dy, dx in [(-step, 0), (-step, 1), (step+1, 0), (step+1, 1), (0, -step), (1, -step), (0, step+1), (1, step+1)]:
                        yy = np.clip(ty3+dy, 0, h-1); xx = np.clip(tx3+dx, 0, w-1); frame[yy, xx, 0] = np.clip(frame[yy, xx, 0] + b_r, 0, 255); frame[yy, xx, 1] = np.clip(frame[yy, xx, 1] + b_g, 0, 255); frame[yy, xx, 2] = np.clip(frame[yy, xx, 2] + b_b, 0, 255)
            if comet_start <= t <= sn_start:
                p = (t - comet_start) / comet_dur
                cx = (1-p)**2 * P0[0] + 2*(1-p)*p * P1[0] + p**2 * P2[0]; cy = (1-p)**2 * P0[1] + 2*(1-p)*p * P1[1] + p**2 * P2[1]
                vx = 2*(1-p)*(P1[0] - P0[0]) + 2*p*(P2[0] - P1[0]); vy = 2*(1-p)*(P1[1] - P0[1]) + 2*p*(P2[1] - P1[1])
                v_mag = np.sqrt(vx**2 + vy**2); dir_x = -vx / max(v_mag, 1); dir_y = -vy / max(v_mag, 1)
                z_scale = 0.7 - 0.2 * np.sin(p * np.pi) + 1.2 * (p**3)
                dx = x_g - cx; dy = y_g - cy; proj = dx * dir_x + dy * dir_y
                trail_len = 200.0 * max(0.4, z_scale); trail_width = 1.2 * z_scale
                mask = (np.abs(dx * dir_y - dy * dir_x) < trail_width) & (proj > 0) & (proj < trail_len)
                fade = (1.0 - (proj[mask] / trail_len))**2 * np.random.uniform(0.3, 1.0, np.sum(mask))
                frame[mask, 0] = np.clip(frame[mask, 0] + 150 * fade, 0, 255); frame[mask, 1] = np.clip(frame[mask, 1] + 200 * fade, 0, 255); frame[mask, 2] = np.clip(frame[mask, 2] + 255 * fade, 0, 255)
                head_glow = np.exp(-0.5 * ((dx**2 + dy**2) / (1.5 * z_scale)**2)); h_mask = head_glow > 0.05
                frame[h_mask, 0] = np.clip(frame[h_mask, 0] + 255 * head_glow[h_mask], 0, 255); frame[h_mask, 1] = np.clip(frame[h_mask, 1] + 255 * head_glow[h_mask], 0, 255); frame[h_mask, 2] = np.clip(frame[h_mask, 2] + 255 * head_glow[h_mask], 0, 255)
            return np.clip(frame, 0, 255).astype(np.uint8)
        return VideoClip(make_frame, duration=duration)

    def build_tile_lower_third(self, text, target_w, target_h, clip_duration, text_dur):
        fs = 55 if target_w < 1200 else 70
        try: pil_font = ImageFont.truetype("arialbd.ttf", fs)
        except: pil_font = ImageFont.load_default()
        txt_upper = text.upper(); dummy = PIL.Image.new("RGBA", (1, 1)); bbox = ImageDraw.Draw(dummy).textbbox((0, 0), txt_upper, font=pil_font)
        tw = bbox[2] - bbox[0] + 24; th = bbox[3] - bbox[1] + 24
        txt_img = PIL.Image.new("RGBA", (tw, th), (0, 0, 0, 0)); draw = ImageDraw.Draw(txt_img)
        draw.text((12 + 4, 12 + 4), txt_upper, font=pil_font, fill=(0, 0, 0, 180)); draw.text((12, 12), txt_upper, font=pil_font, fill=(255, 223, 115, 255))
        txt_rgba = np.array(txt_img); txt_rgb = txt_rgba[..., :3]; txt_alpha_base = txt_rgba[..., 3].astype(np.float32) / 255.0
        txt_x = (target_w - tw) // 2; txt_y = target_h - 210
        pad_x = int(fs * 2.5); pad_y = int(fs * 0.8); box_w = tw + pad_x * 2; box_h = th + pad_y * 2; box_x = txt_x - pad_x; box_y = txt_y - pad_y
        y_g, x_g = np.mgrid[0:box_h, 0:box_w]; r = box_h / 2.0; cx_L = r; cx_R = box_w - r; cy = r
        dx = np.maximum(0.0, np.maximum(cx_L - x_g, x_g - cx_R)); dy = np.abs(y_g - cy); d = np.sqrt(dx**2 + dy**2)
        alpha_pill = np.clip(r - d, 0, 1); alpha_bracket = np.clip(2.5 - np.abs(d - (r + 4)), 0, 1) * ((x_g < cx_L - r*0.3) | (x_g > cx_R + r*0.3))
        def make_bg_frame(t):
            frame = np.zeros((box_h, box_w, 3), dtype=np.float32); frame[..., 0], frame[..., 1], frame[..., 2] = 55, 10, 20
            wave = 0.5 + 0.5 * np.sin((x_g / box_w) * 5 + t * 0.5); frame[..., 0] += wave * 25; frame[..., 2] += wave * 15
            frame[..., 0] = np.clip(frame[..., 0] + alpha_bracket * 255, 0, 255); frame[..., 1] = np.clip(frame[..., 1] + alpha_bracket * 255, 0, 255); frame[..., 2] = np.clip(frame[..., 2] + alpha_bracket * 255, 0, 255)
            return frame.astype(np.uint8)
        form_t = 0.8; diss_t = 0.8; start_t = 0.5; end_t = start_t + form_t + text_dur
        if end_t + diss_t > clip_duration:
            start_t = 0.2; avail = clip_duration - start_t; form_t = avail * 0.15; diss_t = avail * 0.15; text_dur = avail * 0.7; end_t = start_t + form_t + text_dur
        def wipe_progress(t):
            if t < start_t: return 0.0
            elif t < start_t + form_t: return (t - start_t) / form_t
            elif t < end_t: return 1.0
            elif t < end_t + diss_t: return max(0.0, 1.0 - (t - end_t) / diss_t)
            else: return 0.0
        def make_bg_mask(t):
            wp = wipe_progress(t); full = np.zeros((box_h, box_w), dtype=np.float32); limit = int(wp * box_w)
            if limit > 0:
                full[:, :limit] = np.clip(alpha_pill + alpha_bracket, 0, 1)[:, :limit]
                for i in range(40):
                    if 0 <= limit - 40 + i < box_w: full[:, limit - 40 + i] *= (i / 40.0)
            return full
        def make_text_mask_frame(t):
            wp = wipe_progress(t); full = np.zeros((target_h, target_w), dtype=np.float32)
            if wp <= 0: return full
            ga = txt_alpha_base.copy()
            if t < end_t:
                reveal_x = int(wp * tw)
                for i in range(min(40, tw)):
                    if 0 <= reveal_x + i < tw: ga[:, reveal_x + i] *= (1.0 - i / 40.0)
                ga[:, reveal_x:] = 0.0
            else:
                p = (t - end_t) / diss_t
                np.random.seed(int(t * 20))
                ga = ga * np.where(np.random.rand(th, tw) > np.clip(p*2.0 - np.linspace(0, 1, th).reshape(-1, 1)*0.8, 0, 1), 1.0, 0.0).astype(np.float32)
            y1_d, y2_d = max(0, txt_y), min(target_h, txt_y + th); x1_d, x2_d = max(0, txt_x), min(target_w, txt_x + tw)
            if y1_d < y2_d and x1_d < x2_d: full[y1_d:y2_d, x1_d:x2_d] = ga[y1_d-txt_y:y1_d-txt_y+(y2_d-y1_d), x1_d-txt_x:x1_d-txt_x+(x2_d-x1_d)]
            return full
        _txt_rgb_t = txt_rgb.copy()
        def make_text_frame_t(t):
            if wipe_progress(t) <= 0: return np.zeros((target_h, target_w, 3), dtype=np.uint8)
            frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            y1 = max(0, txt_y); y2 = min(target_h, txt_y + th)
            x1 = max(0, txt_x); x2 = min(target_w, txt_x + tw)
            if y1 < y2 and x1 < x2:
                sy1 = y1 - txt_y; sy2 = sy1 + (y2 - y1)
                sx1 = x1 - txt_x; sx2 = sx1 + (x2 - x1)
                frame[y1:y2, x1:x2] = _txt_rgb_t[sy1:sy2, sx1:sx2]
            return frame
        return [(VideoClip(make_bg_frame, duration=clip_duration).set_mask(VideoClip(make_bg_mask, duration=clip_duration, ismask=True)).set_position((box_x, box_y))), (VideoClip(make_text_frame_t, duration=clip_duration).set_mask(VideoClip(make_text_mask_frame, duration=clip_duration, ismask=True)).set_position((0, 0)))]

    def build_magical_lower_third(self, text, target_w, target_h, clip_duration, text_dur):
        fs = 55 if target_w < 1200 else 70
        try: pil_font = ImageFont.truetype("arialbd.ttf", fs)
        except: pil_font = ImageFont.load_default()
        txt_upper = text.upper(); dummy = PIL.Image.new("RGBA", (1, 1)); bbox = ImageDraw.Draw(dummy).textbbox((0, 0), txt_upper, font=pil_font)
        tw = bbox[2] - bbox[0] + 24; th = bbox[3] - bbox[1] + 24
        txt_img = PIL.Image.new("RGBA", (tw, th), (0, 0, 0, 0)); draw = ImageDraw.Draw(txt_img)
        draw.text((12 + 4, 12 + 4), txt_upper, font=pil_font, fill=(0, 0, 0, 180)); draw.text((12, 12), txt_upper, font=pil_font, fill=(255, 223, 115, 255))
        txt_alpha_base = np.array(txt_img)[..., 3].astype(np.float32) / 255.0; txt_rgb = np.array(txt_img)[..., :3]
        txt_x = (target_w - tw) // 2; txt_y = target_h - 210
        pad_x = int(fs * 2.8); pad_y = int(fs * 1.4); box_w = tw + pad_x * 2; box_h = th + pad_y * 2; box_x = txt_x - pad_x; box_y = txt_y - pad_y
        form_t = 1.0; diss_t = 1.0; start_t = 0.5; end_t = start_t + form_t + text_dur
        if end_t + diss_t > clip_duration:
            start_t = 0.2; avail = clip_duration - start_t; form_t = avail * 0.2; diss_t = avail * 0.2; text_dur = avail * 0.6; end_t = start_t + form_t + text_dur
        def wipe_progress(t):
            if t < start_t: return 0.0
            elif t < start_t + form_t: return (t - start_t) / form_t
            elif t < end_t: return 1.0
            elif t < end_t + diss_t: return max(0.0, 1.0-(t-end_t)/diss_t)
            else: return 0.0
        y_g, x_g = np.mgrid[0:box_h, 0:box_w]
        norm_x = (x_g - box_w / 2.0) / (box_w / 2.0); norm_y = (y_g - box_h / 2.0) / (box_h / 2.0)
        col_wave = 0.18 * np.sin(norm_x * np.pi * 2.5)
        wave_mask = np.clip(np.exp(-0.5 * ((norm_x / 0.68)**2 + ((norm_y - col_wave) / 0.44)**2)) * 1.35, 0.0, 1.0).astype(np.float32)
        def make_aurora_frame(t):
            u = x_g / box_w; v = y_g / box_h; teal = 0.5 + 0.5 * np.sin(u * 4 - t * 1.2)
            w1 = 0.5 + 0.5 * np.sin(u * 10 + t * 3.0) * np.cos(v * 5 - t * 2.0); w2 = 0.5 + 0.5 * np.cos(u * 7 - t * 2.5) * np.sin(v * 8 + t * 1.5); w3 = 0.5 + 0.5 * np.sin((u + v) * 6 + t * 1.8)
            return np.stack([np.clip(w1 * 120 + w3 * 60, 0, 255), np.clip(w2 * 140 + w3 * 80 + teal * 80, 0, 255), np.clip(w1 * 255 + w2 * 220 + w3 * 120 + teal * 40, 0, 255)], axis=-1).astype(np.uint8)
        def make_text_mask_frame(t):
            wp = wipe_progress(t); full = np.zeros((target_h, target_w), dtype=np.float32)
            if wp <= 0: return full
            ga = txt_alpha_base.copy()
            if t < end_t:
                reveal_x = int(wp * tw)
                for i in range(min(40, tw)):
                    if 0 <= reveal_x + i < tw: ga[:, reveal_x + i] *= (1.0 - i / 40.0)
                ga[:, reveal_x:] = 0.0
            else:
                p = (t - end_t) / diss_t
                np.random.seed(int(t * 20))
                ga = ga * np.where(np.random.rand(th, tw) > np.clip(p*2.0 - np.linspace(0, 1, th).reshape(-1, 1)*0.8, 0, 1), 1.0, 0.0).astype(np.float32)
            y1_d, y2_d = max(0, txt_y), min(target_h, txt_y + th); x1_d, x2_d = max(0, txt_x), min(target_w, txt_x + tw)
            if y1_d < y2_d and x1_d < x2_d: full[y1_d:y2_d, x1_d:x2_d] = ga[y1_d-txt_y:y1_d-txt_y+(y2_d-y1_d), x1_d-txt_x:x1_d-txt_x+(x2_d-x1_d)]
            return full
        aurora_clip = (VideoClip(make_aurora_frame, duration=clip_duration).set_mask(VideoClip(lambda t: (wave_mask * wipe_progress(t)).astype(np.float32), duration=clip_duration, ismask=True)).set_position((box_x, box_y)))
        _txt_rgb_m = txt_rgb.copy()
        def make_text_frame_m(t):
            if wipe_progress(t) <= 0: return np.zeros((target_h, target_w, 3), dtype=np.uint8)
            frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            y1 = max(0, txt_y); y2 = min(target_h, txt_y + th)
            x1 = max(0, txt_x); x2 = min(target_w, txt_x + tw)
            if y1 < y2 and x1 < x2:
                sy1 = y1 - txt_y; sy2 = sy1 + (y2 - y1)
                sx1 = x1 - txt_x; sx2 = sx1 + (x2 - x1)
                frame[y1:y2, x1:x2] = _txt_rgb_m[sy1:sy2, sx1:sx2]
            return frame
        text_clip_final = (VideoClip(make_text_frame_m, duration=clip_duration).set_mask(VideoClip(make_text_mask_frame, duration=clip_duration, ismask=True)).set_position((0, 0)))
        part_h = min(400, target_h); part_y_off = target_h - part_h
        np.random.seed(42); N = 180; M = 400; K = 200
        trail_spawn = start_t + np.linspace(0, form_t, N); trail_x0 = txt_x - 50 + np.linspace(0, 1, N) * (tw + 100); trail_y0 = (txt_y - part_y_off) - 70*np.sin(np.linspace(0,1,N)*np.pi) + th//2
        diss_spawn = end_t + np.random.uniform(0, diss_t*0.7, M); diss_x0 = txt_x + np.random.uniform(0, tw, M); diss_y0 = (txt_y - part_y_off) + np.random.uniform(0, th, M)
        amb_spawn = np.random.uniform(start_t, end_t, K); amb_x0 = txt_x + np.random.uniform(-20, tw+20, K); amb_y0 = (txt_y - part_y_off) + np.random.uniform(-10, th+10, K)
        def make_fx_frame(t):
            frame = np.zeros((part_h, target_w, 3), dtype=np.uint8); alpha = np.zeros((part_h, target_w), dtype=np.float32)
            for spawn, x0, y0, col, grav, life_dur in [(trail_spawn, trail_x0, trail_y0, (255,220,120), 250, 1.2), (amb_spawn, amb_x0, amb_y0, (255,240,180), 0, 2.0), (diss_spawn, diss_x0, diss_y0, (255,200,100), 350, 1.5)]:
                active = (t > spawn) & (t < spawn + life_dur)
                if not np.any(active): continue
                dt = t - spawn[active]; cx_ = (x0[active]).astype(int); cy_ = (y0[active] + 15*dt + 0.5*grav*dt**2).astype(int); life = np.clip(1.0 - dt/life_dur, 0, 1)
                for x, y, l in zip(cx_, cy_, life):
                    if 0<=y<part_h and 0<=x<target_w: frame[y:y+2, x:x+2] = col; alpha[y:y+2, x:x+2] = np.maximum(alpha[y:y+2, x:x+2], l)
            return frame, alpha
        fx_clip = (VideoClip(lambda t: make_fx_frame(t)[0], duration=clip_duration).set_mask(VideoClip(lambda t: make_fx_frame(t)[1], duration=clip_duration, ismask=True)).set_position((0, part_y_off)))
        return [aurora_clip, text_clip_final, fx_clip]

    def build_designer_lower_third(self, text, target_w, target_h, clip_duration, text_dur):
        fs = 55 if target_w < 1200 else 70
        try: pil_font = ImageFont.truetype("arialbd.ttf", fs)
        except: pil_font = ImageFont.load_default()
        txt_upper = text.upper(); dummy = PIL.Image.new("RGBA", (1, 1)); bbox = ImageDraw.Draw(dummy).textbbox((0, 0), txt_upper, font=pil_font)
        tw = bbox[2] - bbox[0] + 24; th = bbox[3] - bbox[1] + 24
        txt_img = PIL.Image.new("RGBA", (tw, th), (0, 0, 0, 0)); draw = ImageDraw.Draw(txt_img)
        draw.text((12 + 4, 12 + 4), txt_upper, font=pil_font, fill=(0, 0, 0, 180)); draw.text((12, 12), txt_upper, font=pil_font, fill=(255, 220, 80, 255))
        txt_rgba = np.array(txt_img); txt_rgb = txt_rgba[..., :3]; txt_alpha_base = txt_rgba[..., 3].astype(np.float32) / 255.0
        pad_x = int(fs * 1.8); pad_y = int(fs * 0.9); panel_w = tw + pad_x * 2; panel_h = th + pad_y * 2
        panel_x = (target_w - panel_w) // 2; panel_y = target_h - 220; txt_x = panel_x + pad_x; txt_y = panel_y + pad_y
        form_t = 0.5; hold_t = text_dur; diss_t = 0.4; start_t = 0.4; end_t = start_t + form_t + hold_t
        if end_t + diss_t > clip_duration:
            start_t = 0.2; avail = clip_duration - start_t; form_t = avail*0.15; diss_t = avail*0.15; hold_t = avail*0.70; end_t = start_t + form_t + hold_t
        def panel_progress(t):
            if t < start_t: return 0.0
            elif t < start_t+form_t: return (t-start_t)/form_t
            elif t < end_t: return 1.0
            elif t < end_t+diss_t: return max(0.0, 1.0-(t-end_t)/diss_t)
            else: return 0.0
        y_p, x_p = np.mgrid[0:panel_h, 0:panel_w]
        nx = (x_p - panel_w/2.0) / (panel_w/2.0); ny = (y_p - panel_h/2.0) / (panel_h/2.0)
        panel_base_alpha = np.clip(np.exp(-0.5*((nx/0.80)**2 + (ny/0.72)**2)) * 0.82, 0, 1).astype(np.float32)
        border_glow = np.clip(1.0 - np.minimum(np.minimum(x_p, panel_w - 1 - x_p), np.minimum(y_p, panel_h - 1 - y_p)) / 12.0, 0, 1) ** 2
        corner_len = int(panel_w * 0.12); corner_th = 3; corner_mask = np.zeros((panel_h, panel_w), dtype=np.float32)
        for cx_, cy_ in [(0,0),(panel_w-corner_len,0),(0,panel_h-corner_th),(panel_w-corner_len,panel_h-corner_th),(0,0),(panel_w-corner_th,0),(0,panel_h-corner_len),(panel_w-corner_th,panel_h-corner_len)]:
            corner_mask[max(0,cy_):min(panel_h,cy_+max(corner_th, corner_len)), max(0,cx_):min(panel_w,cx_+max(corner_th, corner_len))] = 1.0
        def make_panel_frame(t):
            prog = panel_progress(t)
            if prog <= 0: return np.zeros((target_h, target_w, 3), dtype=np.uint8)
            py = panel_y + int((1.0 - prog) * panel_h * 1.5); frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            y1, y2 = max(0, py), min(target_h, py + panel_h); x1, x2 = max(0, panel_x), min(target_w, panel_x + panel_w)
            if y1 >= y2 or x1 >= x2: return frame
            py_s, py_e = y1 - py, (y1 - py) + (y2 - y1); px_s, px_e = x1 - panel_x, (x1 - panel_x) + (x2 - x1)
            frame[y1:y2, x1:x2, 0], frame[y1:y2, x1:x2, 1], frame[y1:y2, x1:x2, 2] = 45, 10, 75
            s_scan = np.exp(-0.5*((np.arange(panel_h) - int(((t * 0.7) % 1.0) * panel_h))/8.0)**2)[py_s:py_e, np.newaxis]
            s_border = border_glow[py_s:py_e, px_s:px_e]
            frame[y1:y2, x1:x2, 0] = np.clip(frame[y1:y2, x1:x2, 0] + (s_scan * 80).astype(np.uint8) + (s_border * 180).astype(np.uint8), 0, 255)
            frame[y1:y2, x1:x2, 1] = np.clip(frame[y1:y2, x1:x2, 1] + (s_scan * 40).astype(np.uint8) + (s_border * 60).astype(np.uint8), 0, 255)
            frame[y1:y2, x1:x2, 2] = np.clip(frame[y1:y2, x1:x2, 2] + (s_scan * 120).astype(np.uint8) + (s_border * 255).astype(np.uint8), 0, 255)
            return frame
        def make_panel_mask(t):
            prog = panel_progress(t); full = np.zeros((target_h, target_w), dtype=np.float32)
            if prog <= 0: return full
            py = panel_y + int((1.0 - prog) * panel_h * 1.5)
            y1, y2 = max(0, py), min(target_h, py + panel_h); x1, x2 = max(0, panel_x), min(target_w, panel_x + panel_w)
            if y1 >= y2 or x1 >= x2: return full
            py_s, py_e = y1 - py, (y1 - py) + (y2 - y1); px_s, px_e = x1 - panel_x, (x1 - panel_x) + (x2 - x1)
            full[y1:y2, x1:x2] = panel_base_alpha[py_s:py_e, px_s:px_e] * prog
            full[y1:y2, x1:x2] = np.clip(full[y1:y2, x1:x2] + border_glow[py_s:py_e, px_s:px_e] * 0.9 * prog, 0, 1)
            return full
        def make_text_mask(t):
            prog = panel_progress(t); full = np.zeros((target_h, target_w), dtype=np.float32)
            if prog <= 0: return full
            ty = txt_y + int((1.0 - prog) * panel_h * 1.5)
            ga = txt_alpha_base.copy()
            if t >= end_t:
                p = (t - end_t) / diss_t
                np.random.seed(int(t * 20))
                ga = ga * np.where(np.random.rand(th, tw) > np.clip(p*2.0 - np.linspace(0, 1, th).reshape(-1, 1)*0.8, 0, 1), 1.0, 0.0).astype(np.float32)
            y1_d, y2_d = max(0, ty), min(target_h, ty + th); x1_d, x2_d = max(0, txt_x), min(target_w, txt_x + tw)
            if y1_d < y2_d and x1_d < x2_d: full[y1_d:y2_d, x1_d:x2_d] = ga[y1_d-ty:y1_d-ty+(y2_d-y1_d), x1_d-txt_x:x1_d-txt_x+(x2_d-x1_d)] * prog
            return full
        panel_clip = (VideoClip(make_panel_frame, duration=clip_duration).set_mask(VideoClip(make_panel_mask, duration=clip_duration, ismask=True)).set_position((0, 0)))
        _txt_rgb_d = txt_rgb.copy()
        def make_text_frame_d(t):
            if panel_progress(t) <= 0: return np.zeros((target_h, target_w, 3), dtype=np.uint8)
            frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            ty = txt_y + int((1.0 - panel_progress(t)) * panel_h * 1.5)
            y1 = max(0, ty); y2 = min(target_h, ty + th)
            x1 = max(0, txt_x); x2 = min(target_w, txt_x + tw)
            if y1 < y2 and x1 < x2:
                sy1 = y1 - ty; sy2 = sy1 + (y2 - y1)
                sx1 = x1 - txt_x; sx2 = sx1 + (x2 - x1)
                frame[y1:y2, x1:x2] = _txt_rgb_d[sy1:sy2, sx1:sx2]
            return frame
        text_clip_final = (VideoClip(make_text_frame_d, duration=clip_duration).set_mask(VideoClip(make_text_mask, duration=clip_duration, ismask=True)).set_position((0, 0)))
        return [panel_clip, text_clip_final]

    def build_news_lower_third(self, text, target_w, target_h, clip_duration, text_dur):
        fs = 44 if target_w < 1200 else 56
        try: pil_font = ImageFont.truetype("arialbd.ttf", fs)
        except: pil_font = ImageFont.load_default()
        txt_upper = text.upper()
        dummy = PIL.Image.new("RGBA", (1, 1))
        bbox = ImageDraw.Draw(dummy).textbbox((0, 0), txt_upper, font=pil_font)
        tw = bbox[2] - bbox[0] + 60
        th = bbox[3] - bbox[1] + 20
        bar_h = th + int(fs * 1.0)
        bar_w = int(target_w * 0.55)
        chevron = int(bar_h * 0.55)
        bar_x = (target_w - bar_w) // 2
        bar_y = target_h - int(target_h * 0.20)
        txt_x = bar_x + (bar_w - tw) // 2
        txt_y = bar_y + (bar_h - th) // 2
        form_t = 0.4
        diss_t = 0.4
        start_t = 0.3
        end_t = start_t + form_t + text_dur
        if end_t + diss_t > clip_duration:
            start_t = 0.2
            avail = clip_duration - start_t
            form_t = avail * 0.15
            diss_t = avail * 0.15
            text_dur = avail * 0.7
            end_t = start_t + form_t + text_dur
        def wipe_progress(t):
            if t < start_t: return 0.0
            elif t < start_t + form_t: return (t - start_t) / form_t
            elif t < end_t: return 1.0
            elif t < end_t + diss_t: return max(0.0, 1.0 - (t - end_t) / diss_t)
            else: return 0.0
        y_g, x_g = np.mgrid[0:bar_h, 0:bar_w]
        nx = x_g.astype(np.float32) / bar_w
        ny = y_g.astype(np.float32) / bar_h
        cy = bar_h / 2.0
        in_chev_L = (x_g < chevron) & (y_g > (cy - (x_g * cy / chevron))) & (y_g < (cy + (x_g * cy / chevron)))
        in_chev_R = (x_g > bar_w - 1 - chevron) & (y_g > (cy - ((bar_w - 1 - x_g) * cy / chevron))) & (y_g < (cy + ((bar_w - 1 - x_g) * cy / chevron)))
        in_body = (x_g >= chevron) & (x_g <= bar_w - 1 - chevron)
        inner_mask = np.where(in_body | in_chev_L | in_chev_R, 1.0, 0.0).astype(np.float32)
        edge_dist = np.minimum(np.minimum(nx, 1.0 - nx), np.minimum(ny, 1.0 - ny))
        glow_edge = np.exp(-edge_dist / 0.04).astype(np.float32) * inner_mask
        scan_pattern = ((y_g % 4) == 0).astype(np.float32) * 0.08 * inner_mask
        np.random.seed(42)
        noise_pattern = np.random.rand(bar_h, bar_w).astype(np.float32) * 0.06 * inner_mask
        circuit_h = ((x_g % 12) < 1).astype(np.float32) * 0.15
        circuit_v = ((y_g % 16) < 1).astype(np.float32) * 0.15
        circuit = np.clip((circuit_h + circuit_v) * inner_mask, 0, 1)
        pad = 5
        outer_h = bar_h + pad * 2
        outer_w = bar_w + pad * 2 + chevron
        outer_y = bar_y - pad
        outer_x = bar_x - pad - chevron // 2
        oy_g, ox_g = np.mgrid[0:outer_h, 0:outer_w]
        ony = oy_g.astype(np.float32) / outer_h
        ocy = outer_h / 2.0
        o_chevron = chevron + pad
        in_o_chev_L = (ox_g < o_chevron) & (oy_g > (ocy - (ox_g * ocy / o_chevron))) & (oy_g < (ocy + (ox_g * ocy / o_chevron)))
        in_o_chev_R = (ox_g > outer_w - 1 - o_chevron) & (oy_g > (ocy - ((outer_w - 1 - ox_g) * ocy / o_chevron))) & (oy_g < (ocy + ((outer_w - 1 - ox_g) * ocy / o_chevron)))
        in_o_body = (ox_g >= o_chevron) & (ox_g <= outer_w - 1 - o_chevron)
        outer_mask = np.where(in_o_body | in_o_chev_L | in_o_chev_R, 1.0, 0.0).astype(np.float32)
        onx = ox_g.astype(np.float32) / outer_w
        o_edge_dist = np.minimum(np.minimum(onx, 1.0 - onx), np.minimum(ony, 1.0 - ony))
        outer_glow_edge = np.exp(-o_edge_dist / 0.03).astype(np.float32) * outer_mask
        def make_bar_frame(t):
            prog = wipe_progress(t)
            if prog <= 0: return np.zeros((target_h, target_w, 3), dtype=np.uint8)
            outer_frame = np.zeros((outer_h, outer_w, 3), dtype=np.float32)
            outer_frame[..., 0] = 8 + outer_glow_edge * 20
            outer_frame[..., 1] = 10 + outer_glow_edge * 80
            outer_frame[..., 2] = 18 + outer_glow_edge * 120
            scan_pos = ((t * 1.5) % 1.0)
            o_scan = np.exp(-0.5 * ((ony - scan_pos) / 0.02)**2) * outer_mask * 0.3
            outer_frame[..., 0] += o_scan * 20
            outer_frame[..., 1] += o_scan * 160
            outer_frame[..., 2] += o_scan * 255
            inner_frame = np.zeros((bar_h, bar_w, 3), dtype=np.float32)
            gr = np.clip(8 + 40 * nx, 0, 255)
            gg = np.clip(50 + 130 * nx, 0, 255)
            gb = np.clip(120 + 100 * nx, 0, 255)
            inner_frame[..., 0] = gr
            inner_frame[..., 1] = gg
            inner_frame[..., 2] = gb
            inner_frame[..., 0] += glow_edge * 40
            inner_frame[..., 1] += glow_edge * 220
            inner_frame[..., 2] += glow_edge * 255
            inner_frame[..., 0] += circuit * 15
            inner_frame[..., 1] += circuit * 100
            inner_frame[..., 2] += circuit * 180
            inner_frame *= (1.0 + scan_pattern + noise_pattern)[..., np.newaxis]
            flicker = 1.0 + 0.04 * np.sin(t * 8.0)
            inner_frame *= flicker
            inner_frame *= prog
            outer_frame *= prog
            result = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            oy1 = max(0, outer_y); oy2 = min(target_h, outer_y + outer_h)
            ox1 = max(0, outer_x); ox2 = min(target_w, outer_x + outer_w)
            if oy1 < oy2 and ox1 < ox2:
                result[oy1:oy2, ox1:ox2] = outer_frame[oy1 - outer_y:oy2 - outer_y, ox1 - outer_x:ox2 - outer_x].astype(np.uint8)
            iy1 = max(0, bar_y); iy2 = min(target_h, bar_y + bar_h)
            ix1 = max(0, bar_x); ix2 = min(target_w, bar_x + bar_w)
            if iy1 < iy2 and ix1 < ix2:
                result[iy1:iy2, ix1:ix2] = np.clip(
                    result[iy1:iy2, ix1:ix2].astype(np.float32) +
                    inner_frame[iy1 - bar_y:iy2 - bar_y, ix1 - bar_x:ix2 - bar_x], 0, 255).astype(np.uint8)
            return result
        def make_bar_mask(t):
            prog = wipe_progress(t)
            if prog <= 0: return np.zeros((target_h, target_w), dtype=np.float32)
            full = np.zeros((target_h, target_w), dtype=np.float32)
            oy1 = max(0, outer_y); oy2 = min(target_h, outer_y + outer_h)
            ox1 = max(0, outer_x); ox2 = min(target_w, outer_x + outer_w)
            if oy1 < oy2 and ox1 < ox2:
                full[oy1:oy2, ox1:ox2] = outer_mask[oy1 - outer_y:oy2 - outer_y, ox1 - outer_x:ox2 - outer_x] * prog
            return full
        txt_img = PIL.Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        draw = ImageDraw.Draw(txt_img)
        draw.text((30 + 2, 10 + 2), txt_upper, font=pil_font, fill=(0, 0, 0, 200))
        draw.text((30, 10), txt_upper, font=pil_font, fill=(255, 255, 255, 255))
        txt_rgba = np.array(txt_img)
        _txt_rgb = txt_rgba[..., :3].copy()
        txt_alpha_base = txt_rgba[..., 3].astype(np.float32) / 255.0
        _tw, _th = tw, th
        def make_text_mask(t):
            prog = wipe_progress(t)
            full = np.zeros((target_h, target_w), dtype=np.float32)
            if prog <= 0: return full
            ga = txt_alpha_base.copy()
            if t >= end_t:
                p = (t - end_t) / diss_t
                np.random.seed(int(t * 20))
                ga = ga * np.where(np.random.rand(_th, _tw) > np.clip(p * 2.0 - np.linspace(0, 1, _th).reshape(-1, 1) * 0.8, 0, 1), 1.0, 0.0).astype(np.float32)
            y1_d, y2_d = max(0, txt_y), min(target_h, txt_y + _th)
            x1_d, x2_d = max(0, txt_x), min(target_w, txt_x + _tw)
            if y1_d < y2_d and x1_d < x2_d:
                full[y1_d:y2_d, x1_d:x2_d] = ga[y1_d - txt_y:y1_d - txt_y + (y2_d - y1_d), x1_d - txt_x:x1_d - txt_x + (x2_d - x1_d)] * prog
            return full
        def make_text_frame(t):
            if wipe_progress(t) <= 0: return np.zeros((target_h, target_w, 3), dtype=np.uint8)
            frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            y1 = max(0, txt_y); y2 = min(target_h, txt_y + _th)
            x1 = max(0, txt_x); x2 = min(target_w, txt_x + _tw)
            if y1 < y2 and x1 < x2:
                frame[y1:y2, x1:x2] = _txt_rgb[y1 - txt_y:y1 - txt_y + (y2 - y1), x1 - txt_x:x1 - txt_x + (x2 - x1)]
            return frame
        bar_clip = (VideoClip(make_bar_frame, duration=clip_duration)
                    .set_mask(VideoClip(make_bar_mask, duration=clip_duration, ismask=True))
                    .set_position((0, 0)))
        text_clip_final = (VideoClip(make_text_frame, duration=clip_duration)
                           .set_mask(VideoClip(make_text_mask, duration=clip_duration, ismask=True))
                           .set_position((0, 0)))
        return [bar_clip, text_clip_final]
