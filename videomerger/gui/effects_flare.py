"""Anamorphic X-flare and light-flash rendering.

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


class EffectsFlareMixin:
    """Anamorphic X-flare and light-flash rendering."""

    def _create_x_flare_effect(self, frame, variation='Blue White', position='Center',
                               intensity=1.0, size=1.0, speed=0.3, time_factor=0.0):
        h, w = frame.shape[:2]
        combined = frame.astype(np.float32)
        diag = float(np.hypot(w, h))
        t = time_factor * speed

        # Camera flash flicker — rapid irregular brightness pulses
        flicker = (0.7
                   + 0.30 * np.sin(t * 18.0)
                   + 0.15 * np.sin(t * 31.0)
                   + 0.10 * np.sin(t * 47.0)
                   + 0.08 * np.sin(t * 73.0))
        flicker = max(flicker, 0.15)
        intensity = intensity * flicker

        key = str(position).strip().lower().replace('_', ' ')
        fx_f, fy_f = self._X_FLARE_POSITIONS.get(key, (0.50, 0.50))
        cx, cy = fx_f * w, fy_f * h

        colors = self._X_FLARE_COLORS.get(variation, self._X_FLARE_COLORS['Blue White'])
        ray_col = np.array(colors['ray'], dtype=np.float32)
        core_col = np.array(colors['core'], dtype=np.float32)
        glow_col = np.array(colors['glow'], dtype=np.float32)
        fringe_col = np.array(colors['fringe'], dtype=np.float32)

        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        dx = xx - cx
        dy = yy - cy
        dist = np.sqrt(dx * dx + dy * dy)

        glare_layer = np.zeros_like(combined)
        angle = np.arctan2(dy, dx)

        # --- 4 glowing X rays — bright near source, fading to tips ---
        arm_angles = [np.pi / 4, 3 * np.pi / 4, 5 * np.pi / 4, 7 * np.pi / 4]
        ray_len = diag * 0.42 * size
        ray_half_w = 0.022 * size
        ray_glow_w = 0.06 * size

        ray_layer = np.zeros((h, w), dtype=np.float32)
        glow_layer = np.zeros((h, w), dtype=np.float32)

        for arm_a in arm_angles:
            ang_diff = np.abs(np.arctan2(np.sin(angle - arm_a), np.cos(angle - arm_a)))
            ray_core = np.clip(1.0 - ang_diff / ray_half_w, 0, 1) ** 1.5
            ray_soft = np.clip(1.0 - ang_diff / ray_glow_w, 0, 1) ** 2.0
            radial_fade = np.clip(1.0 - dist / ray_len, 0, 1) ** 0.8
            ray_layer = np.maximum(ray_layer, ray_core * radial_fade)
            glow_layer = np.maximum(glow_layer, ray_soft * radial_fade)

        glare_layer += glow_layer[..., np.newaxis] * glow_col * (0.35 * intensity)
        glare_layer += ray_layer[..., np.newaxis] * ray_col * (0.75 * intensity)

        # --- Purple fringing on ray edges ---
        fringe_layer = np.zeros((h, w), dtype=np.float32)
        for arm_a in arm_angles:
            ang_diff = np.abs(np.arctan2(np.sin(angle - arm_a), np.cos(angle - arm_a)))
            fringe_mask = np.clip(1.0 - ang_diff / ray_glow_w, 0, 1) ** 2.0
            fringe_inner = np.clip(1.0 - ang_diff / ray_half_w, 0, 1) ** 1.5
            fringe_band = np.clip(fringe_mask - fringe_inner, 0, 1)
            radial_fade = np.clip(1.0 - dist / ray_len, 0, 1) ** 0.8
            fringe_layer = np.maximum(fringe_layer, fringe_band * radial_fade)
        glare_layer += fringe_layer[..., np.newaxis] * fringe_col * (0.50 * intensity)

        # --- Bright glowing center source ---
        core_r = diag * 0.022 * size
        r_wide = np.sqrt((dx / (core_r * 4.0)) ** 2 + (dy / (core_r * 4.0)) ** 2)
        core_wide = np.clip(1.0 - r_wide, 0, 1) ** 1.4
        glare_layer += core_wide[..., np.newaxis] * glow_col * (0.6 * intensity)
        r_mid = np.sqrt((dx / (core_r * 2.0)) ** 2 + (dy / (core_r * 2.0)) ** 2)
        core_mid = np.clip(1.0 - r_mid, 0, 1) ** 1.8
        glare_layer += core_mid[..., np.newaxis] * core_col * (0.85 * intensity)
        r_inner = np.sqrt((dx / core_r) ** 2 + (dy / core_r) ** 2)
        core_inner = np.clip(1.0 - r_inner, 0, 1) ** 2.2
        glare_layer += core_inner[..., np.newaxis] * core_col * (1.0 * intensity)

        blur_k = max(3, int(min(h, w) * 0.010)) | 1
        glare_layer = cv2.GaussianBlur(glare_layer, (blur_k, blur_k), 0)

        # Screen blend
        glare_norm = glare_layer / 255.0
        base_norm = combined / 255.0
        screen = 1.0 - (1.0 - base_norm) * (1.0 - glare_norm)
        combined = screen * 255.0

        return np.clip(combined, 0, 255).astype(np.uint8)

    def apply_x_flare_effect(self, frame, item, t):
        if not item.get('effect_x_flare_enabled', False):
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame
        variation = item.get('x_flare_variation', 'Blue White')
        position = item.get('x_flare_position', 'Center')
        intensity = item.get('x_flare_intensity', 1.0)
        size = item.get('x_flare_size', 1.0)
        speed = item.get('x_flare_speed', 0.3)
        return self._create_x_flare_effect(frame, variation=variation, position=position,
                                           intensity=intensity, size=size, speed=speed,
                                           time_factor=t)

    def _light_flash_pseudo_random(self, seed):
        """Deterministic pseudo-random float in [0, 1) from an integer seed."""
        x = np.sin(seed * 127.1 + 311.7) * 43758.5453
        return x - np.floor(x)

    def _create_light_flash_effect(self, frame, variation='White Flash', position='Center',
                                    intensity=1.0, size=1.0, speed=1.0, density=6,
                                    time_factor=0.0):
        """Multiple random camera-flash X-crosses that pop in and out within an area."""
        h, w = frame.shape[:2]
        combined = frame.astype(np.float32)
        diag = float(np.hypot(w, h))
        t = time_factor * speed

        key = str(position).strip().lower().replace('_', ' ')
        pos_val = self._LIGHT_FLASH_POSITIONS.get(key, (0.50, 0.50))

        is_diagonal_tl_br = (pos_val == 'diagonal_tl_br')
        is_diagonal_bl_tr = (pos_val == 'diagonal_bl_tr')
        is_full_image = (pos_val == 'full_image')

        if is_full_image:
            area_cx, area_cy = 0.5 * w, 0.5 * h
        elif is_diagonal_tl_br or is_diagonal_bl_tr:
            area_cx, area_cy = 0.5 * w, 0.5 * h
        else:
            fx_f, fy_f = pos_val
            area_cx, area_cy = fx_f * w, fy_f * h

        colors = self._LIGHT_FLASH_COLORS.get(variation, self._LIGHT_FLASH_COLORS['White Flash'])
        ray_col = np.array(colors['ray'], dtype=np.float32)
        core_col = np.array(colors['core'], dtype=np.float32)
        glow_col = np.array(colors['glow'], dtype=np.float32)
        fringe_col = np.array(colors['fringe'], dtype=np.float32)

        area_r = diag * 0.18 * size
        n_flashes = max(3, min(20, int(density * 1.8)))
        CYCLE_LEN = 3.0 / max(0.3, speed)

        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        glare_layer = np.zeros((h, w, 3), dtype=np.float32)

        arm_cos = np.array([np.cos(a) for a in [np.pi/4, 3*np.pi/4, 5*np.pi/4, 7*np.pi/4]], dtype=np.float32)
        arm_sin = np.array([np.sin(a) for a in [np.pi/4, 3*np.pi/4, 5*np.pi/4, 7*np.pi/4]], dtype=np.float32)

        tmp_dx = np.empty((h, w), dtype=np.float32)
        tmp_dy = np.empty((h, w), dtype=np.float32)
        tmp_dist = np.empty((h, w), dtype=np.float32)
        tmp_angle = np.empty((h, w), dtype=np.float32)
        tmp_ray = np.empty((h, w), dtype=np.float32)

        for i in range(n_flashes):
            r1 = self._light_flash_pseudo_random(i * 3 + 1)
            r2 = self._light_flash_pseudo_random(i * 3 + 2)
            r3 = self._light_flash_pseudo_random(i * 3 + 3)
            r4 = self._light_flash_pseudo_random(i * 3 + 4)
            r5 = self._light_flash_pseudo_random(i * 3 + 5)

            if is_full_image:
                sx = r1 * w
                sy = r2 * h
            elif is_diagonal_tl_br:
                frac = r1
                sx = frac * w
                sy = frac * h
                sx += (r2 - 0.5) * diag * 0.08 * size
                sy += (r2 - 0.5) * diag * 0.08 * size
            elif is_diagonal_bl_tr:
                frac = r1
                sx = frac * w
                sy = (1.0 - frac) * h
                sx += (r2 - 0.5) * diag * 0.08 * size
                sy += (r2 - 0.5) * diag * 0.08 * size
            else:
                theta = r1 * 6.2831853
                rad = np.sqrt(r2) * area_r
                sx = area_cx + rad * np.cos(theta)
                sy = area_cy + rad * np.sin(theta)

            local_t = (t + r3 * CYCLE_LEN) % CYCLE_LEN
            life = local_t / CYCLE_LEN

            if life < 0.08:
                bright_env = life / 0.08
            elif life < 0.25:
                bright_env = 1.0
            elif life < 0.40:
                bright_env = 1.0 - (life - 0.25) / 0.15
            else:
                continue

            flicker = (0.7 + 0.30 * np.sin(local_t * 40.0 + r4 * 10.0)
                       + 0.15 * np.sin(local_t * 67.0 + r5 * 10.0))
            brightness = bright_env * flicker * intensity
            if brightness < 0.02:
                continue

            flash_size = size * (0.5 + r4)

            np.subtract(xx, sx, out=tmp_dx)
            np.subtract(yy, sy, out=tmp_dy)
            np.sqrt(tmp_dx * tmp_dx + tmp_dy * tmp_dy, out=tmp_dist)
            np.arctan2(tmp_dy, tmp_dx, out=tmp_angle)

            ray_len = diag * 0.55 * max(flash_size, 0.8)
            ray_half_w = 0.032 * max(flash_size, 0.7)
            ray_glow_w = 0.065 * max(flash_size, 0.7)

            np.maximum(tmp_dist, 0.001, out=tmp_dist)
            radial = np.clip(1.0 - tmp_dist / ray_len, 0, 1)
            np.power(radial, 0.7, out=radial)

            for ai in range(4):
                ad = np.abs(np.arctan2(np.sin(tmp_angle - arm_cos[ai]), np.cos(tmp_angle - arm_cos[ai])))
                np.clip(1.0 - ad / ray_half_w, 0, 1, out=tmp_ray)
                np.power(tmp_ray, 1.8, out=tmp_ray)
                np.multiply(tmp_ray, radial, out=tmp_ray)
                glare_layer[..., 0] += tmp_ray * ray_col[0] * (1.0 * brightness)
                glare_layer[..., 1] += tmp_ray * ray_col[1] * (1.0 * brightness)
                glare_layer[..., 2] += tmp_ray * ray_col[2] * (1.0 * brightness)

                np.clip(1.0 - ad / ray_glow_w, 0, 1, out=tmp_ray)
                np.power(tmp_ray, 2.2, out=tmp_ray)
                np.multiply(tmp_ray, radial, out=tmp_ray)
                glare_layer[..., 0] += tmp_ray * glow_col[0] * (0.30 * brightness)
                glare_layer[..., 1] += tmp_ray * glow_col[1] * (0.30 * brightness)
                glare_layer[..., 2] += tmp_ray * glow_col[2] * (0.30 * brightness)

            core_r = diag * 0.016 * flash_size
            r_inv = 1.0 / max(core_r, 0.1)
            r_wide_inv = 1.0 / max(core_r * 5.0, 0.1)
            core_wide = np.clip(1.0 - tmp_dist * r_wide_inv, 0, 1)
            np.power(core_wide, 1.2, out=core_wide)
            core_mid = np.clip(1.0 - tmp_dist * (r_inv * 0.4), 0, 1)
            np.power(core_mid, 1.8, out=core_mid)
            core_inner = np.clip(1.0 - tmp_dist * r_inv, 0, 1)
            np.power(core_inner, 2.5, out=core_inner)

            glare_layer[..., 0] += core_wide * glow_col[0] * (0.50 * brightness)
            glare_layer[..., 1] += core_wide * glow_col[1] * (0.50 * brightness)
            glare_layer[..., 2] += core_wide * glow_col[2] * (0.50 * brightness)
            glare_layer[..., 0] += core_mid * core_col[0] * (0.85 * brightness)
            glare_layer[..., 1] += core_mid * core_col[1] * (0.85 * brightness)
            glare_layer[..., 2] += core_mid * core_col[2] * (0.85 * brightness)
            glare_layer[..., 0] += core_inner * core_col[0] * brightness
            glare_layer[..., 1] += core_inner * core_col[1] * brightness
            glare_layer[..., 2] += core_inner * core_col[2] * brightness

        ambient = (0.6 + 0.4 * np.sin(t * 8.0) * np.sin(t * 13.0)) * intensity
        if is_full_image:
            ambient_r = diag * 0.6
        elif is_diagonal_tl_br or is_diagonal_bl_tr:
            ambient_r = diag * 0.4
        else:
            ambient_r = area_r * 1.5
        np.subtract(xx, area_cx, out=tmp_dx)
        np.subtract(yy, area_cy, out=tmp_dy)
        np.sqrt(tmp_dx * tmp_dx + tmp_dy * tmp_dy, out=tmp_dist)
        ambient_mask = np.clip(1.0 - tmp_dist / ambient_r, 0, 1)
        np.power(ambient_mask, 2.0, out=ambient_mask)
        glare_layer[..., 0] += ambient_mask * glow_col[0] * (0.06 * ambient)
        glare_layer[..., 1] += ambient_mask * glow_col[1] * (0.06 * ambient)
        glare_layer[..., 2] += ambient_mask * glow_col[2] * (0.06 * ambient)

        blur_k = max(3, int(min(h, w) * 0.010)) | 1
        glare_layer = cv2.GaussianBlur(glare_layer, (blur_k, blur_k), 0)

        glare_norm = glare_layer / 255.0
        base_norm = combined / 255.0
        screen = 1.0 - (1.0 - base_norm) * (1.0 - glare_norm)
        combined = screen * 255.0

        return np.clip(combined, 0, 255).astype(np.uint8)

    def apply_light_flash_effect(self, frame, item, t):
        if not item.get('effect_light_flash_enabled', False):
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame
        variation = item.get('light_flash_variation', 'White Flash')
        position = item.get('light_flash_position', 'Center')
        intensity = item.get('light_flash_intensity', 1.0)
        size = item.get('light_flash_size', 1.0)
        speed = item.get('light_flash_speed', 1.0)
        density = item.get('light_flash_density', 6)
        return self._create_light_flash_effect(frame, variation=variation, position=position,
                                               intensity=intensity, size=size, speed=speed,
                                                density=density, time_factor=t)
