"""Extruded 3D-text texture and projection helpers.

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


class EffectsText3DMixin:
    """Extruded 3D-text texture and projection helpers."""

    def _load_3d_text_font(self, px):
        for name in ("arialbd.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(name, px)
            except Exception:
                continue
        try:
            return ImageFont.truetype("C:\\Windows\\Fonts\\arialbd.ttf", px)
        except Exception:
            return ImageFont.load_default()

    def _get_3d_text_texture_cached(self, text, color_name, depth, style, time_factor):
        """Text drawing (up to 40 extruded layers) is the expensive part of
        this effect, but it only depends on text/color/depth/style/time —
        not on the quad. While the user drags the quad around, none of
        those change, so we cache the rendered texture and only redo the
        (cheap) perspective warp each frame. This is what keeps corner
        drag/resize/rotate feeling responsive instead of janky."""
        # Glow style animates with time; round time_factor coarsely so we still
        # get cache hits during a drag (where time_factor is constant) without
        # letting the cache grow unbounded during playback.
        t_key = round(time_factor, 2) if style == 'Glow' else 0.0
        key = (text, color_name, round(depth, 3), style, t_key)
        cache = self._3d_text_texture_cache
        cached = cache.get(key)
        if cached is not None:
            return cached
        texture = self._render_3d_text_texture(text, color_name, depth, style, time_factor)
        if len(cache) > 12:
            cache.pop(next(iter(cache)))
        cache[key] = texture
        return texture

    def _render_3d_text_texture(self, text, color_name, depth, style, time_factor):
        """Renders extruded/beveled 3D text onto its own transparent RGBA
        canvas (not tied to any frame position or size). This canonical
        texture is later perspective-warped onto the quad the user placed
        on the preview, which is what actually gives the text its on-screen
        position, size, and orientation."""
        colors = self._3D_TEXT_COLORS.get(color_name, self._3D_TEXT_COLORS['Orange'])
        face_color, side_color = colors[0], colors[1]

        font_px = self._3D_TEXT_CANON_FONT_PX
        font = self._load_3d_text_font(font_px)

        tmp = PIL.Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        bbox = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
        text_w = max(1, bbox[2] - bbox[0])
        text_h = max(1, bbox[3] - bbox[1])

        pixel_depth = max(0, int(depth * font_px * 0.5))
        pad = int(font_px * 0.35) + pixel_depth + 4
        canvas_w = text_w + pad * 2
        canvas_h = text_h + pad * 2
        canvas = PIL.Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        ax = pad - bbox[0]
        ay = pad - bbox[1]

        # --- extrusion layers (back to front, for the chunky 3D side) ---
        if pixel_depth > 0 and depth > 0:
            n_layers = min(max(1, pixel_depth), 40)
            for layer_idx in range(n_layers - 1, -1, -1):
                tt = layer_idx / max(1, n_layers)
                lx = ax + layer_idx
                ly = ay + layer_idx
                r = int(side_color[0] * (0.4 + 0.6 * (1.0 - tt)))
                g = int(side_color[1] * (0.4 + 0.6 * (1.0 - tt)))
                b = int(side_color[2] * (0.4 + 0.6 * (1.0 - tt)))

                if style == 'Metallic':
                    spec = max(0, 1.0 - abs(tt - 0.3) * 3.0) * 60
                    r, g, b = min(255, r + int(spec)), min(255, g + int(spec)), min(255, b + int(spec))
                elif style == 'Glossy':
                    edge = max(0, 1.0 - abs(tt - 0.5) * 4.0) * 50
                    r, g, b = min(255, r + int(edge)), min(255, g + int(edge)), min(255, b + int(edge))
                elif style == 'Glow':
                    glow = 0.3 + 0.2 * math.sin(time_factor * 2.0 + tt * 3.0)
                    r, g, b = min(255, int(r * (1.0 + glow))), min(255, int(g * (1.0 + glow))), min(255, int(b * (1.0 + glow)))

                draw.text((lx, ly), text, fill=(r, g, b, 255), font=font)

        # --- front face ---
        r, g, b = face_color
        if style == 'Glow':
            pulse = 0.8 + 0.2 * math.sin(time_factor * 1.5)
            r, g, b = min(255, int(r * pulse)), min(255, int(g * pulse)), min(255, int(b * pulse))
        highlight = (min(255, r + 50), min(255, g + 50), min(255, b + 50), 255)
        shadow_c = (max(0, r - 50), max(0, g - 50), max(0, b - 50), 255)
        draw.text((ax, ay), text, fill=(r, g, b, 255), font=font)
        draw.text((ax - 1, ay - 1), text, fill=highlight, font=font)
        draw.text((ax + 1, ay + 1), text, fill=shadow_c, font=font)

        return canvas

    def _make_3d_text_ground_shadow(self, warped_rgba, shadow_opacity, dst_pts_px):
        """Derives a soft ground shadow from the already-warped text's alpha
        mask, nudged along the quad's own 'down' direction so it reads as
        being cast onto the surface the text sits on rather than floating."""
        if shadow_opacity <= 0:
            return None
        alpha = warped_rgba[:, :, 3].astype(np.float32)
        if alpha.max() <= 0:
            return None
        ys = [p[1] for p in dst_pts_px]
        quad_h = max(1.0, max(ys) - min(ys))
        # average of the two side edges (TL->BL, TR->BR) gives the quad's local "down" direction
        down_x = ((dst_pts_px[3][0] - dst_pts_px[0][0]) + (dst_pts_px[2][0] - dst_pts_px[1][0])) / 2.0
        down_y = ((dst_pts_px[3][1] - dst_pts_px[0][1]) + (dst_pts_px[2][1] - dst_pts_px[1][1])) / 2.0
        down_len = max(1e-4, math.hypot(down_x, down_y))
        off = max(4.0, quad_h * 0.16)
        ox, oy = down_x / down_len * off, down_y / down_len * off

        M = np.float32([[1, 0, ox], [0, 1, oy]])
        shifted = cv2.warpAffine(alpha, M, (alpha.shape[1], alpha.shape[0]),
                                  flags=cv2.INTER_LINEAR, borderValue=0)
        k = max(3, int(quad_h * 0.06)) | 1
        shifted = cv2.GaussianBlur(shifted, (k, k), 0)
        return (shifted / 255.0) * shadow_opacity * 0.7

    def _project_3d_text_quad(self, item, t, frame_w, frame_h):
        """Compute the on-screen quad by applying perspective growth to the
        user's manually placed anchor quad.  The anchor defines where the
        text sits at t=0.  As the virtual camera moves forward, each corner
        scales outward from the vanishing point (frame center) so that:
          - text below camera height expands downward
          - text at camera height expands through the center
          - text above camera height expands upward
          - left/right offset expands laterally

        Returns None when the camera has moved past the text (near-plane clip)."""
        cam_speed = float(item.get('3d_cam_speed', 8.0))

        anchor = self._get_3d_text_quad(item)
        if not anchor or len(anchor) != 4:
            return self._default_3d_text_quad()

        if cam_speed <= 0:
            return anchor

        text_z = 25.0
        cam_z = cam_speed * t
        if cam_z >= text_z - 0.05:
            return None

        scale = text_z / (text_z - cam_z)

        vpx, vpy = 0.5, 0.5

        new_quad = []
        for px, py in anchor:
            dx = px - vpx
            dy = py - vpy
            new_quad.append([vpx + dx * scale, vpy + dy * scale])

        return new_quad

    def _create_3d_text_tracking(self, frame, text='TRACKING', color_name='Orange',
                                  depth=0.4, shadow_opacity=0.5, style='Solid Matte',
                                  time_factor=0.0, quad=None):
        h, w = frame.shape[:2]
        if h == 0 or w == 0 or not text:
            return frame
        if quad is None or len(quad) != 4:
            quad = self._default_3d_text_quad()

        texture = self._get_3d_text_texture_cached(text, color_name, depth, style, time_factor)
        tex_np = np.array(texture)
        th, tw = tex_np.shape[:2]

        src_pts = np.float32([[0, 0], [tw, 0], [tw, th], [0, th]])
        dst_pts_px = [[p[0] * w, p[1] * h] for p in quad]
        M = cv2.getPerspectiveTransform(src_pts, np.float32(dst_pts_px))
        warped = cv2.warpPerspective(tex_np, M, (w, h), flags=cv2.INTER_LINEAR,
                                      borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

        out = frame.astype(np.float32)

        shadow_a = self._make_3d_text_ground_shadow(warped, shadow_opacity, dst_pts_px)
        if shadow_a is not None:
            out = out * (1.0 - shadow_a[..., np.newaxis])

        alpha = warped[:, :, 3:4].astype(np.float32) / 255.0
        rgb = warped[:, :, :3].astype(np.float32)
        out = out * (1.0 - alpha) + rgb * alpha

        return np.clip(out, 0, 255).astype(np.uint8)

    def apply_3d_text_tracking_effect(self, frame, item, t):
        if not item.get('effect_3d_text_enabled', False):
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame

        fade_alpha = 1.0
        if not item.get('3d_text_full_clip', True):
            t_start = float(item.get('3d_text_start', 0.0))
            t_end = max(t_start + 0.05, float(item.get('3d_text_end', 3.0)))
            fade = max(0.0, float(item.get('3d_text_fade', 0.3)))
            if t < t_start - fade or t > t_end + fade:
                return frame  # outside the visible window — text isn't there at all
            if fade > 0.0:
                if t < t_start:
                    fade_alpha = max(0.0, 1.0 - (t_start - t) / fade)
                elif t > t_end:
                    fade_alpha = max(0.0, 1.0 - (t - t_end) / fade)
            elif t < t_start or t > t_end:
                return frame
            if fade_alpha <= 0.0:
                return frame

        # --- 3D perspective projection (always) ---
        quad = self._project_3d_text_quad(item, t, w, h)

        if quad is None:
            return frame  # camera has moved past the text (near-plane clip)

        result = self._create_3d_text_tracking(
            frame,
            text=item.get('3d_text_content', 'TRACKING'),
            color_name=item.get('3d_text_color', 'Orange'),
            depth=item.get('3d_text_depth', 0.4),
            shadow_opacity=item.get('3d_text_shadow', 0.5),
            style=item.get('3d_text_style', 'Solid Matte'),
            time_factor=t,
            quad=quad
        )
        if fade_alpha < 1.0:
            result = (frame.astype(np.float32) * (1.0 - fade_alpha)
                      + result.astype(np.float32) * fade_alpha).astype(np.uint8)
        return result
