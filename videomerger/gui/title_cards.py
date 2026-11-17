"""Large animated title-card builder.

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


class TitleCardsMixin:
    """Large animated title-card builder."""

    def build_finch_title_card(self, target_w, target_h, item, preview_mode=False):
        _ensure_moviepy()
        duration = float(item.get("value", 5.0))
        main_str = item.get("main_text", "TITLE").upper()
        sub_str = item.get("sub_text", "").upper()
        spaced_sub = "   ".join(sub_str) if sub_str else ""
        theme = item.get("theme", "")

        is_lightspeed = "Light Speed" in theme
        is_deepspace = "Deep Space" in theme
        is_travelling = "Travelling Flare" in theme
        is_blueflare = "Blue Flare" in theme
        is_headlight = "Headlight" in theme

        main_y = (target_h // 2) - 10

        if is_lightspeed:
            main_y -= 20
            text_clips = []
            offsets = [20, 15, 10, 5]
            colors = ["#100030", "#3b0086", "#7500c0", "#c200ff"]
            for off, col in zip(offsets, colors):
                try: tc = TextClip(main_str, fontsize=160, color=col, font="Arial-Bold", stroke_color=col, stroke_width=6, bg_color="transparent")
                except: tc = TextClip(main_str, fontsize=160, color=col, font="Arial-Bold", bg_color="transparent")
                tc = tc.set_position(("center", main_y + off)).set_duration(duration)
                text_clips.append(tc)
            try: top_tc = TextClip(main_str, fontsize=160, color="white", font="Arial-Bold", stroke_color="#a200ff", stroke_width=4, bg_color="transparent")
            except: top_tc = TextClip(main_str, fontsize=160, color="white", font="Arial-Bold", bg_color="transparent")
            top_tc = top_tc.set_position(("center", main_y)).set_duration(duration)
            text_clips.append(top_tc)
            main_clip = CompositeVideoClip(text_clips, size=(target_w, target_h)).set_duration(duration)
            shine_clip = None
            main_clip = main_clip.fx(vfx.resize, lambda t: 1.0 + 0.05 * (t / duration))
            baseline_y = main_y + top_tc.h - 10
        else:
            if is_blueflare:
                main_clip = TextClip(main_str, fontsize=120, color="#c8dde8", font="Arial-Bold", stroke_color="#0a2a4a", stroke_width=3, bg_color="transparent")
                main_clip = main_clip.set_position(("center", main_y)).set_duration(duration)
                shine_clip = TextClip(main_str, fontsize=120, color="white", font="Arial-Bold", bg_color="transparent")
                shine_clip = shine_clip.set_opacity(0.12).crop(y2=main_clip.h // 2)
                shine_clip = shine_clip.set_position(("center", main_y)).set_duration(duration)
            elif is_headlight:
                main_clip = TextClip(main_str, fontsize=60, color="#c0c8d0", font="Arial-Bold", stroke_color="black", stroke_width=4, bg_color="transparent")
                main_clip = main_clip.set_position(("center", main_y)).set_duration(duration)
                shine_clip = TextClip(main_str, fontsize=60, color="white", font="Arial-Bold", bg_color="transparent")
                shine_clip = shine_clip.set_opacity(0.2).crop(y2=main_clip.h // 2)
                shine_clip = shine_clip.set_position(("center", main_y)).set_duration(duration)
            else:
                main_clip = TextClip(main_str, fontsize=140 if is_travelling else 130, color="#E5D5A0", font="Arial-Bold", bg_color="transparent")
                main_clip = main_clip.set_position(("center", main_y)).set_duration(duration)
                if is_travelling:
                    shine_clip = None
                else:
                    shine_clip = TextClip(main_str, fontsize=130, color="white", font="Arial-Bold", bg_color="transparent")
                    shine_clip = shine_clip.set_opacity(0.12).crop(y2=main_clip.h // 2)
                    shine_clip = shine_clip.set_position(("center", main_y)).set_duration(duration)
            if is_deepspace:
                def zoom_func(t): return 1.0 + 0.05 * (t / duration)
                main_clip = main_clip.fx(vfx.resize, zoom_func)
                if shine_clip: shine_clip = shine_clip.fx(vfx.resize, zoom_func)
            baseline_y = main_y + main_clip.h - 10

        if is_lightspeed:
            bg_clip = self.create_warp_background(target_w, target_h, duration)
            layers = [bg_clip]
        elif is_travelling:
            y_bg, x_bg = np.mgrid[0:target_h, 0:target_w]
            dist_center = np.sqrt((x_bg - target_w/2)**2 + (y_bg - target_h/2)**2)
            fog_glow = np.exp(-0.5 * (dist_center / 800.0)**2) * 0.4
            bg_r = np.clip(18 + 15 * fog_glow, 0, 255); bg_g = np.clip(25 + 20 * fog_glow, 0, 255); bg_b = np.clip(28 + 15 * fog_glow, 0, 255)
            bg_frame = np.stack([bg_r, bg_g, bg_b], axis=-1).astype(np.uint8)
            bg_clip = ImageClip(bg_frame).set_duration(duration)
            layers = [bg_clip]
            y_g, x_g = np.mgrid[0:target_h, 0:target_w]
            np.random.seed(42)
            num_dust = 120
            d_x = np.random.uniform(target_w*0.1, target_w*0.9, num_dust); d_y = np.random.uniform(target_h*0.2, target_h*0.8, num_dust)
            d_vx = np.random.uniform(-5, 5, num_dust); d_vy = np.random.uniform(-10, -2, num_dust); d_size = np.zeros(num_dust)
            dist_c = np.sqrt((x_g - target_w/2)**2 + (y_g - baseline_y)**2)
            text_w_half = main_clip.w / 2.0 + 40; text_h_half = main_clip.h / 2.0 + 50; text_cy = baseline_y - main_clip.h / 2.0 - 20
            dx_text = np.maximum(0.0, np.abs(x_g - target_w/2) - text_w_half); dy_text = np.maximum(0.0, np.abs(y_g - text_cy) - text_h_half)
            dist_from_text = np.sqrt(dx_text**2 + dy_text**2); text_avoid_mask = np.clip(dist_from_text / 10.0, 0, 1)
            def make_travelling_flare(t):
                p = t / duration; cx = (target_w/2 - main_clip.w/2 - 150) + p * (main_clip.w + 300); cy = baseline_y - 5
                intensity = 0.02 + 0.98 * np.exp(-0.5 * ((p - 0.5) / 0.12)**2)
                frame = np.zeros((target_h, target_w, 3), dtype=np.float32); alpha = np.zeros((target_h, target_w), dtype=np.float32)
                fog = np.exp(-0.5 * ((x_g - target_w/2)**2 / (600.0)**2 + (y_g - cy)**2 / (150.0)**2)) * intensity * 0.15
                sine_val = np.sin(-dist_c / 35.0 + t * 5.0); ripple_lines = np.clip((sine_val - 0.995) * 200.0, 0, 1)
                np.random.seed(int(t * 20)); glitter_noise = np.random.rand(target_h, target_w); glitter_mult = np.where(glitter_noise > 0.85, 2.5, 0.2)
                ripples = ripple_lines * text_avoid_mask * intensity * glitter_mult * 0.8
                fog_glow = np.clip(fog, 0, 1); frame[..., 0] += fog_glow * 255; frame[..., 1] += fog_glow * 220; frame[..., 2] += fog_glow * 130; alpha += fog_glow
                frame[..., 0] = np.clip(frame[..., 0] + ripples * 229, 0, 255); frame[..., 1] = np.clip(frame[..., 1] + ripples * 213, 0, 255); frame[..., 2] = np.clip(frame[..., 2] + ripples * 160, 0, 255); alpha = np.clip(alpha + ripples, 0, 1)
                streak_h_w = 800.0 * intensity + 20.0; streak_h_h = 2.5 + 1.0 * intensity; streak_v_w = 2.5 + 1.0 * intensity; streak_v_h = 350.0 * intensity + 10.0
                y_min, y_max = max(0, int(cy - max(streak_h_h, streak_v_h)*3)), min(target_h, int(cy + max(streak_h_h, streak_v_h)*3))
                x_min, x_max = max(0, int(cx - max(streak_h_w, streak_v_w)*3)), min(target_w, int(cx + max(streak_h_w, streak_v_w)*3))
                if y_min < y_max and x_min < x_max:
                    xx = x_g[y_min:y_max, x_min:x_max]; yy = y_g[y_min:y_max, x_min:x_max]; dx = xx - cx; dy = yy - cy
                    s1 = np.exp(-0.5 * (dx / streak_h_w)**2 - 0.5 * (dy / streak_h_h)**2) * intensity; s2 = np.exp(-0.5 * (dx / streak_v_w)**2 - 0.5 * (dy / streak_v_h)**2) * intensity
                    core = np.exp(-0.5 * (np.sqrt(dx**2 + dy**2) / (25.0 * intensity + 3.0))**2) * intensity * 1.5; glow = np.clip(s1 + s2 + core, 0, 1)
                    frame[y_min:y_max, x_min:x_max, 0] = np.clip(frame[y_min:y_max, x_min:x_max, 0] + glow * 255, 0, 255); frame[y_min:y_max, x_min:x_max, 1] = np.clip(frame[y_min:y_max, x_min:x_max, 1] + glow * 240, 0, 255); frame[y_min:y_max, x_min:x_max, 2] = np.clip(frame[y_min:y_max, x_min:x_max, 2] + glow * 190, 0, 255); alpha[y_min:y_max, x_min:x_max] = np.clip(alpha[y_min:y_max, x_min:x_max] + glow, 0, 1)
                for i in range(num_dust):
                    curr_x = int(d_x[i] + d_vx[i] * t); curr_y = int(d_y[i] + d_vy[i] * t)
                    if 0 <= curr_x < target_w and 0 <= curr_y < target_h:
                        dist_to_flare = np.sqrt((curr_x - cx)**2 + (curr_y - cy)**2)
                        illum = max(np.exp(-0.5 * (dist_to_flare / (300 * intensity + 50))**2) * intensity * 0.8, np.exp(-0.5 * ((curr_x - target_w/2)**2 / 600**2 + (curr_y - cy)**2 / 150**2)) * intensity * 0.3)
                        if illum > 0.02:
                            s = 0; y1, y2 = max(0, curr_y-s), min(target_h, curr_y+s+1); x1, x2 = max(0, curr_x-s), min(target_w, curr_x+s+1)
                            dust_glow = illum * 255; frame[y1:y2, x1:x2, 0] = np.clip(frame[y1:y2, x1:x2, 0] + dust_glow, 0, 255); frame[y1:y2, x1:x2, 1] = np.clip(frame[y1:y2, x1:x2, 1] + dust_glow * 0.85, 0, 255); frame[y1:y2, x1:x2, 2] = np.clip(frame[y1:y2, x1:x2, 2] + dust_glow * 0.4, 0, 255); alpha[y1:y2, x1:x2] = np.clip(alpha[y1:y2, x1:x2] + illum, 0, 1)
                return np.clip(frame, 0, 255).astype(np.uint8), np.clip(alpha, 0, 1)
            flare_rgb = VideoClip(lambda t: make_travelling_flare(t)[0], duration=duration)
            flare_mask = VideoClip(lambda t: make_travelling_flare(t)[1], duration=duration, ismask=True)
            layers.append(flare_rgb.set_mask(flare_mask))
        elif is_blueflare:
            y_bg, x_bg = np.mgrid[0:target_h, 0:target_w]
            norm_y = (y_bg / target_h).astype(np.float32)
            norm_x = (x_bg / target_w).astype(np.float32)
            bg_r = np.clip(6 + 8 * (1 - norm_y), 0, 255).astype(np.float32)
            bg_g = np.clip(8 + 10 * (1 - norm_y), 0, 255).astype(np.float32)
            bg_b = np.clip(15 + 20 * (1 - norm_y), 0, 255).astype(np.float32)
            flare_cy = target_h * 0.52
            flare_h_w = target_w * 0.55
            flare_h_h = 2.5
            flare_v_w = 2.0
            flare_v_h = target_h * 0.12
            dx_flare = x_bg - target_w / 2.0
            dy_flare = y_bg - flare_cy
            h_streak = np.exp(-0.5 * (dx_flare / flare_h_w)**2 - 0.5 * (dy_flare / flare_h_h)**2)
            v_streak = np.exp(-0.5 * (dx_flare / flare_v_w)**2 - 0.5 * (dy_flare / flare_v_h)**2)
            core = np.exp(-0.5 * (np.sqrt(dx_flare**2 + dy_flare**2) / (8.0))**2)
            flare_total = np.clip(h_streak * 0.85 + v_streak * 0.6 + core * 1.2, 0, 1)
            flare_rgb_frame = np.zeros((target_h, target_w, 3), dtype=np.float32)
            flare_rgb_frame[..., 0] = flare_total * 80
            flare_rgb_frame[..., 1] = flare_total * 160
            flare_rgb_frame[..., 2] = flare_total * 255
            flare_alpha_frame = flare_total.astype(np.float32)
            bg_r += flare_total * 80; bg_g += flare_total * 160; bg_b += flare_total * 255
            bg_frame = np.stack([bg_r, bg_g, bg_b], axis=-1).astype(np.uint8)
            bg_clip = ImageClip(bg_frame).set_duration(duration)
            layers = [bg_clip]
            ambient = np.exp(-0.5 * (np.sqrt((x_bg - target_w/2)**2 + (y_bg - flare_cy)**2) / (target_w * 0.4))**2) * 0.08
            ambient_frame = np.stack([ambient * 40, ambient * 80, ambient * 140], axis=-1).astype(np.float32)
            ambient_clip = ImageClip(np.clip(ambient_frame, 0, 255).astype(np.uint8)).set_duration(duration)
            layers.append(ambient_clip)
            def make_blueflare_flare(t):
                pulse = 1.0 + 0.06 * np.sin(t * 1.8)
                drift = 3.0 * np.sin(t * 0.4)
                shifted = np.roll(flare_rgb_frame.astype(np.float32), int(drift), axis=1)
                shifted *= pulse
                return np.clip(shifted, 0, 255).astype(np.uint8)
            def make_blueflare_mask(t):
                pulse = 1.0 + 0.06 * np.sin(t * 1.8)
                drift = 3.0 * np.sin(t * 0.4)
                shifted = np.roll(flare_alpha_frame, int(drift), axis=1)
                shifted *= pulse
                return np.clip(shifted, 0, 1).astype(np.float32)
            flare_clip = VideoClip(make_blueflare_flare, duration=duration).set_mask(VideoClip(make_blueflare_mask, duration=duration, ismask=True))
            layers.append(flare_clip)
        elif is_headlight:
            y_bg, x_bg = np.mgrid[0:target_h, 0:target_w]
            norm_y = (y_bg / target_h).astype(np.float32)
            norm_x = (x_bg / target_w).astype(np.float32)
            bg_r = np.clip(5 + 4 * (1 - norm_y), 0, 255).astype(np.float32)
            bg_g = np.clip(6 + 5 * (1 - norm_y), 0, 255).astype(np.float32)
            bg_b = np.clip(12 + 10 * (1 - norm_y), 0, 255).astype(np.float32)
            flare_cy = target_h * 0.52
            beam_y_L = (y_bg - flare_cy).astype(np.float32)
            beam_y_R = (y_bg - flare_cy).astype(np.float32)
            mask_L = np.clip(1.0 - norm_x / 0.42, 0, 1).astype(np.float32)
            mask_R = np.clip(1.0 - (1.0 - norm_x) / 0.42, 0, 1).astype(np.float32)
            core_L = np.exp(-0.5 * ((norm_x / 0.015)**2 + ((norm_y - 0.52) / 0.01)**2)) * mask_L
            core_R = np.exp(-0.5 * (((1.0 - norm_x) / 0.015)**2 + ((norm_y - 0.52) / 0.01)**2)) * mask_R
            glow_L = np.exp(-0.5 * ((norm_x / 0.05)**2 + ((norm_y - 0.52) / 0.04)**2)) * mask_L
            glow_R = np.exp(-0.5 * (((1.0 - norm_x) / 0.05)**2 + ((norm_y - 0.52) / 0.04)**2)) * mask_R
            ray_narrow_L = np.exp(-0.5 * (beam_y_L / (target_h * 0.002))**2) * np.exp(-0.5 * ((norm_x / 0.18)**2)) * mask_L
            ray_narrow_R = np.exp(-0.5 * (beam_y_R / (target_h * 0.002))**2) * np.exp(-0.5 * (((1.0 - norm_x) / 0.18)**2)) * mask_R
            ray_wide_L = np.exp(-0.5 * (beam_y_L / (target_h * 0.012))**2) * np.exp(-0.5 * ((norm_x / 0.28)**2)) * mask_L
            ray_wide_R = np.exp(-0.5 * (beam_y_R / (target_h * 0.012))**2) * np.exp(-0.5 * (((1.0 - norm_x) / 0.28)**2)) * mask_R
            flare_total = np.clip(
                core_L * 2.5 + core_R * 2.5 +
                glow_L * 1.5 + glow_R * 1.5 +
                ray_narrow_L * 1.2 + ray_narrow_R * 1.2 +
                ray_wide_L * 0.5 + ray_wide_R * 0.5, 0, 1)
            flare_rgb_frame = np.zeros((target_h, target_w, 3), dtype=np.float32)
            flare_rgb_frame[..., 0] = flare_total * 80
            flare_rgb_frame[..., 1] = flare_total * 160
            flare_rgb_frame[..., 2] = flare_total * 240
            flare_alpha_frame = flare_total.astype(np.float32)
            bg_r += flare_total * 80; bg_g += flare_total * 160; bg_b += flare_total * 240
            vignette = 1.0 - np.clip(np.sqrt(((norm_x - 0.5) / 0.75)**2 + ((norm_y - 0.5) / 0.65)**2) - 0.25, 0, 1) * 0.85
            bg_r *= vignette; bg_g *= vignette; bg_b *= vignette
            bg_frame = np.stack([bg_r, bg_g, bg_b], axis=-1).astype(np.uint8)
            bg_clip = ImageClip(bg_frame).set_duration(duration)
            layers = [bg_clip]
            np.random.seed(77)
            n_dust = 300
            dust_x0 = np.random.uniform(0, target_w, n_dust).astype(np.float32)
            dust_y0 = np.random.uniform(0, target_h, n_dust).astype(np.float32)
            dust_vx = np.random.uniform(-8, 8, n_dust).astype(np.float32)
            dust_vy = np.random.uniform(-3, 3, n_dust).astype(np.float32)
            dust_phase = np.random.uniform(0, 2 * np.pi, n_dust).astype(np.float32)
            dust_size = np.random.choice([1, 2, 3], n_dust, p=[0.6, 0.3, 0.1]).astype(np.int32)
            def make_dust_frame(t):
                frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
                alpha = np.zeros((target_h, target_w), dtype=np.float32)
                cx_L = 0; cy_L = flare_cy; cx_R = target_w; cy_R = flare_cy
                for i in range(n_dust):
                    px = int(dust_x0[i] + dust_vx[i] * t) % target_w
                    py = int(dust_y0[i] + dust_vy[i] * t + 2.0 * np.sin(t * 1.5 + dust_phase[i])) % target_h
                    dist_L = np.sqrt((px - cx_L)**2 + (py - cy_L)**2)
                    dist_R = np.sqrt((px - cx_R)**2 + (py - cy_R)**2)
                    brightness = max(
                        np.exp(-0.5 * (dist_L / (target_w * 0.4))**2),
                        np.exp(-0.5 * (dist_R / (target_w * 0.4))**2))
                    flicker = 0.5 + 0.5 * np.sin(t * 3.0 + dust_phase[i])
                    b = brightness * flicker * 0.6
                    if b > 0.02:
                        s = dust_size[i]
                        y1, y2 = max(0, py - s), min(target_h, py + s + 1)
                        x1, x2 = max(0, px - s), min(target_w, px + s + 1)
                        if y1 < y2 and x1 < x2:
                            frame[y1:y2, x1:x2, 0] = np.clip(frame[y1:y2, x1:x2, 0] + b * 180, 0, 255)
                            frame[y1:y2, x1:x2, 1] = np.clip(frame[y1:y2, x1:x2, 1] + b * 200, 0, 255)
                            frame[y1:y2, x1:x2, 2] = np.clip(frame[y1:y2, x1:x2, 2] + b * 240, 0, 255)
                            alpha[y1:y2, x1:x2] = np.clip(alpha[y1:y2, x1:x2] + b, 0, 1)
                return frame, alpha
            def make_dust_rgb(t):
                return make_dust_frame(t)[0]
            def make_dust_alpha(t):
                return make_dust_frame(t)[1]
            dust_clip = VideoClip(make_dust_rgb, duration=duration).set_mask(VideoClip(make_dust_alpha, duration=duration, ismask=True))
            layers.append(dust_clip)
            def make_headlight_flare(t):
                pulse = 1.0 + 0.03 * np.sin(t * 1.0)
                flicker = 1.0 + 0.02 * np.sin(t * 2.5)
                frame = flare_rgb_frame.copy().astype(np.float32) * pulse * flicker
                return np.clip(frame, 0, 255).astype(np.uint8)
            def make_headlight_mask(t):
                pulse = 1.0 + 0.03 * np.sin(t * 1.0)
                return np.clip(flare_alpha_frame * pulse, 0, 1).astype(np.float32)
            flare_clip = VideoClip(make_headlight_flare, duration=duration).set_mask(VideoClip(make_headlight_mask, duration=duration, ismask=True))
            layers.append(flare_clip)
        else:
            bg_clip = self.create_starry_sky_background(target_w, target_h, duration)
            layers = [bg_clip]

        if spaced_sub:
            if is_lightspeed:
                try: sub_txt = TextClip(spaced_sub, fontsize=40, color="#b050ff", font="Arial-Bold", stroke_color="white", stroke_width=3, bg_color="transparent")
                except: sub_txt = TextClip(spaced_sub, fontsize=40, color="white", font="Arial-Bold", bg_color="transparent")
                layers.append(sub_txt.set_position(("center", main_y - 70)).set_duration(duration))
            elif is_travelling:
                try: sub_txt = TextClip(spaced_sub, fontsize=35, color="#E5D5A0", font="Arial-Bold", bg_color="transparent")
                except: sub_txt = TextClip(spaced_sub, fontsize=35, color="white", bg_color="transparent")
                layers.append(sub_txt.set_position(("center", main_y - 60)).set_duration(duration))
            elif is_blueflare:
                try: sub_txt = TextClip(spaced_sub, fontsize=36, color="#6aafcc", font="Arial-Bold", bg_color="transparent")
                except: sub_txt = TextClip(spaced_sub, fontsize=36, color="white", bg_color="transparent")
                layers.append(sub_txt.set_position(("center", main_y - 70)).set_duration(duration))
            elif is_headlight:
                try: sub_txt = TextClip(spaced_sub, fontsize=28, color="#8899aa", font="Arial-Bold", bg_color="transparent")
                except: sub_txt = TextClip(spaced_sub, fontsize=28, color="white", bg_color="transparent")
                layers.append(sub_txt.set_position(("center", main_y - 50)).set_duration(duration))
            else:
                try: sub_txt = TextClip(spaced_sub, fontsize=35, color="white", font="Arial-Bold", bg_color="transparent")
                except: sub_txt = TextClip(spaced_sub, fontsize=35, color="white", bg_color="transparent")
                layers.append(sub_txt.set_position(("center", main_y - 80)).set_duration(duration))

        if is_blueflare:
            def zoom_func_blueflare(t): return 1.0 + 0.03 * (t / duration)
            main_clip = main_clip.fx(vfx.resize, zoom_func_blueflare)
            if shine_clip: shine_clip = shine_clip.fx(vfx.resize, zoom_func_blueflare)

        if is_headlight:
            def zoom_func_headlight(t): return 1.0 + 0.02 * (t / duration)
            main_clip = main_clip.fx(vfx.resize, zoom_func_headlight)
            if shine_clip: shine_clip = shine_clip.fx(vfx.resize, zoom_func_headlight)

        layers.append(main_clip)
        if shine_clip is not None: layers.append(shine_clip)

        if not is_deepspace and not is_lightspeed and not is_travelling and not is_blueflare and not is_headlight:
            yv, xv = np.mgrid[:target_h, :target_w]
            vd = np.sqrt(((xv - target_w/2)/(target_w*0.55))**2 + ((yv - target_h/2)/(target_h*0.55))**2)
            vig_a = np.clip(vd**1.6*0.72, 0, 1).astype(np.float32)
            vig_clip = ImageClip(np.zeros((target_h, target_w, 3), dtype=np.uint8)).set_mask(ImageClip(vig_a, ismask=True)).set_duration(duration)
            layers.append(vig_clip)

        if is_lightspeed:
            trans_dur = 1.2
            trans_start = duration - trans_dur
            impact_time = trans_start + 0.4

            def make_fusion_frame(t):
                frame = np.zeros((target_h, target_w, 3), dtype=np.float32)
                if t < trans_start: return frame.astype(np.uint8)
                    
                y_g, x_g = np.mgrid[:target_h, :target_w]
                cy, cx = target_h / 2.0, target_w / 2.0
                
                if t < impact_time:
                    p_in = (t - trans_start) / (impact_time - trans_start)
                    tip_l = cx * p_in
                    beam_len = 200 + 400 * p_in
                    tail_l = max(0, tip_l - beam_len)
                    beam_th = 8.0
                    
                    mask_l = (x_g < tip_l) & (x_g > tail_l) & (np.abs(y_g - cy) < beam_th)
                    glow_l = np.exp(-0.5 * (np.abs(y_g - cy) / (beam_th*2))**2) * (x_g < tip_l) * (x_g > tail_l)
                    
                    frame[..., 1] += glow_l * 255 
                    frame[..., 2] += glow_l * 255 
                    frame[mask_l] = [255, 255, 255]
                    
                    tip_r = target_w - (cx * p_in)
                    tail_r = min(target_w, tip_r + beam_len)
                    
                    mask_r = (x_g > tip_r) & (x_g < tail_r) & (np.abs(y_g - cy) < beam_th)
                    glow_r = np.exp(-0.5 * (np.abs(y_g - cy) / (beam_th*2))**2) * (x_g > tip_r) * (x_g < tail_r)
                    
                    frame[..., 0] += glow_r * 255 
                    frame[..., 2] += glow_r * 150 
                    frame[mask_r] = [255, 255, 255]
                    
                else:
                    p_ex = (t - impact_time) / (duration - impact_time) 
                    
                    beam_th = 6.0 + p_ex * 30.0
                    glow_l = np.exp(-0.5 * (np.abs(y_g - cy) / beam_th)**2) * (x_g <= cx)
                    glow_r = np.exp(-0.5 * (np.abs(y_g - cy) / beam_th)**2) * (x_g > cx)
                    
                    frame[..., 0] += glow_r * 255
                    frame[..., 1] += glow_l * 255
                    frame[..., 2] += glow_l * 255 + glow_r * 150
                    
                    core_beam = np.abs(y_g - cy) < (3.0 + p_ex * 15)
                    frame[core_beam] = [255, 255, 255]
                    
                    dist = np.sqrt((x_g - cx)**2 + (y_g - cy)**2)
                    radius = 20 + (target_w * 2.0) * (p_ex**2.5)
                    intensity = 1.0 + p_ex * 8.0
                    core = np.clip(1.0 - (dist / radius), 0, 1)**2 * intensity
                    
                    spike_len = 150 + target_w * p_ex**2
                    spike_th = 3.0 + p_ex * 15.0
                    spikes = np.exp(-0.5 * (np.abs(x_g - cx)/spike_len)**2 - 0.5 * (np.abs(y_g - cy)/spike_th)**2)
                    spikes += np.exp(-0.5 * (np.abs(y_g - cy)/spike_len)**2 - 0.5 * (np.abs(x_g - cx)/spike_th)**2)
                    
                    dx = x_g - cx
                    dy = y_g - cy
                    diag1 = np.abs(dx - dy) / 1.414
                    diag2 = np.abs(dx + dy) / 1.414
                    diag_len = 100 + target_w * 0.7 * p_ex**2
                    diag_th = 2.0 + p_ex * 8.0
                    spikes += 0.8 * np.exp(-0.5 * (diag1/diag_th)**2 - 0.5 * (np.abs(dx+dy)/1.414/diag_len)**2)
                    spikes += 0.8 * np.exp(-0.5 * (diag2/diag_th)**2 - 0.5 * (np.abs(dx-dy)/1.414/diag_len)**2)
                    
                    burst = np.clip(core + spikes * intensity, 0, 1)
                    
                    side_blend = np.clip((x_g - (cx - 200)) / 400.0, 0, 1) 
                    r_burst = 100 * (1 - side_blend) + 255 * side_blend
                    g_burst = 255 * (1 - side_blend) + 50 * side_blend
                    b_burst = 255 * (1 - side_blend) + 150 * side_blend
                    
                    frame[..., 0] += burst * r_burst
                    frame[..., 1] += burst * g_burst
                    frame[..., 2] += burst * b_burst
                    
                    white_core = np.clip(1.0 - (dist / (radius*0.4)), 0, 1)**1.5 * intensity
                    frame[..., 0] += white_core * 255
                    frame[..., 1] += white_core * 255
                    frame[..., 2] += white_core * 255
                
                return np.clip(frame, 0, 255).astype(np.uint8)

            def make_fusion_mask(t):
                if t < trans_start: return np.zeros((target_h, target_w), dtype=np.float32)
                y_g, x_g = np.mgrid[:target_h, :target_w]
                cy, cx = target_h / 2.0, target_w / 2.0

                if t < impact_time:
                    p_in = (t - trans_start) / (impact_time - trans_start)
                    tip_l = cx * p_in
                    beam_len = 200 + 400 * p_in
                    tail_l = max(0, tip_l - beam_len)
                    
                    tip_r = target_w - (cx * p_in)
                    tail_r = min(target_w, tip_r + beam_len)
                    beam_th = 8.0
                    
                    mask_l = np.exp(-0.5 * (np.abs(y_g - cy) / (beam_th*2))**2) * (x_g < tip_l) * (x_g > tail_l)
                    mask_r = np.exp(-0.5 * (np.abs(y_g - cy) / (beam_th*2))**2) * (x_g > tip_r) * (x_g < tail_r)
                    return np.clip(mask_l + mask_r, 0, 1).astype(np.float32)
                else:
                    p_ex = (t - impact_time) / (duration - impact_time)
                    dist = np.sqrt((x_g - cx)**2 + (y_g - cy)**2)
                    radius = 20 + (target_w * 2.0) * (p_ex**2.5)
                    intensity = 1.0 + p_ex * 8.0
                    glow = np.clip(1.0 - (dist / radius), 0, 1)**1.5 * intensity
                    
                    beam_th = 6.0 + p_ex * 30.0
                    beams = np.exp(-0.5 * (np.abs(y_g - cy) / beam_th)**2)
                    return np.clip(glow + beams, 0, 1).astype(np.float32)

            fusion_clip = VideoClip(make_fusion_frame, duration=duration).set_mask(VideoClip(make_fusion_mask, duration=duration, ismask=True))
            layers.append(fusion_clip)

        elif is_deepspace:
            sn_dur = 0.8 
            sn_start = duration - sn_dur

            def make_sn_frame(t): return np.full((target_h, target_w, 3), 255, dtype=np.uint8)
            Y_sn, X_sn = np.mgrid[0:target_h, 0:target_w]
            sn_x = target_w / 2.0; sn_y = target_h / 2.0
            dist_from_center = np.sqrt((X_sn - sn_x)**2 + (Y_sn - sn_y)**2)
            
            def make_sn_mask(t):
                if t < sn_start: return np.zeros((target_h, target_w), dtype=np.float32)
                p = (t - sn_start) / sn_dur 
                radius = 20 + (target_w * 2.5) * (p**2.5) 
                intensity = 1.0 + (p * 8.0) 
                glow = np.clip(1.0 - (dist_from_center / radius), 0, 1)**1.5 * intensity
                return np.clip(glow, 0, 1)

            sn_clip = VideoClip(make_sn_frame, duration=duration).set_mask(VideoClip(make_sn_mask, duration=duration, ismask=True))
            layers.append(sn_clip)

        card = CompositeVideoClip(layers, size=(target_w, target_h)).set_duration(duration)

        if not preview_mode and (is_deepspace or is_lightspeed or is_travelling) and not item.get("muted", False):
            fps_audio = 44100; total_samples = int(duration * fps_audio); t_audio = np.linspace(0, duration, total_samples, endpoint=False); audio_mono = np.zeros(total_samples, dtype=np.float32)
            if is_deepspace:
                sn_dur = 0.8; sn_start = duration - sn_dur; comet_dur = 2.0; comet_start = max(0.0, sn_start - comet_dur)
                mask_comet = ((t_audio - comet_start) / comet_dur >= 0) & ((t_audio - comet_start) / comet_dur <= 1)
                if np.any(mask_comet):
                    p_comet = (t_audio[mask_comet] - comet_start) / comet_dur; env_comet = np.sin(p_comet * np.pi)**2; noise = np.random.uniform(-0.5, 0.5, np.sum(mask_comet)); freq = 800 - 500*np.sin(p_comet*np.pi) + 900*(p_comet**3)
                    audio_mono[mask_comet] += (noise * 0.6 + np.sin(2 * np.pi * freq * t_audio[mask_comet]) * 0.4) * env_comet * 0.8
                boom_start = sn_start; boom_dur = sn_dur; mask_boom = ((t_audio - boom_start) / boom_dur >= 0) & ((t_audio - boom_start) / boom_dur <= 1)
                if np.any(mask_boom):
                    p_boom = (t_audio[mask_boom] - boom_start) / boom_dur; env_sn = np.exp(-4 * p_boom); noise = np.random.uniform(-1.0, 1.0, np.sum(mask_boom)); freq = 150 * np.exp(-4 * p_boom) + 40
                    audio_mono[mask_boom] += (noise * 0.8 + np.sin(2 * np.pi * freq * t_audio[mask_boom]) * 0.6) * env_sn * 1.0
            elif is_lightspeed:
                trans_dur = 1.2; trans_start = duration - trans_dur; impact_time = trans_start + 0.4
                mask_in = ((t_audio - trans_start) / 0.4 >= 0) & ((t_audio - trans_start) / 0.4 <= 1)
                if np.any(mask_in):
                    p_in = (t_audio[mask_in] - trans_start) / 0.4
                    audio_mono[mask_in] += (np.sin(2 * np.pi * (400 + 1200 * p_in) * t_audio[mask_in]) + np.sin(2 * np.pi * (500 + 1400 * p_in) * t_audio[mask_in])) * 0.2 * (p_in**2)
                mask_boom = ((t_audio - impact_time) / (duration - impact_time) >= 0) & ((t_audio - impact_time) / (duration - impact_time) <= 1)
                if np.any(mask_boom):
                    p_boom = (t_audio[mask_boom] - impact_time) / (duration - impact_time)
                    audio_mono[mask_boom] += (np.random.uniform(-1.0, 1.0, np.sum(mask_boom)) * 0.8 + np.sin(2 * np.pi * (120 * np.exp(-5 * p_boom) + 30) * t_audio[mask_boom]) * 0.7) * np.exp(-4 * p_boom) * 1.0
            elif is_travelling:
                p = t_audio / duration
                audio_mono += (np.random.uniform(-0.5, 0.5, total_samples) * 0.3 + np.sin(2 * np.pi * (300 - 150 * p) * t_audio) * 0.2) * np.exp(-0.5 * ((p - 0.5) / 0.15)**2) * 0.5
            audio_mono = np.clip(audio_mono, -1.0, 1.0); audio_stereo = np.column_stack((audio_mono, audio_mono))
            card = card.set_audio(AudioArrayClip(audio_stereo, fps=fps_audio))

        return card.fadein(0.8) if not preview_mode else card
