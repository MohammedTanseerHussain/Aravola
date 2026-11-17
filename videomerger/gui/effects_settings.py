"""Callbacks for individual effect parameter widgets.

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


class EffectsSettingsMixin:
    """Callbacks for individual effect parameter widgets."""

    def _on_effect_timing_changed(self):
        if self._effect_timing.get() == "custom":
            for w in self._effect_custom_frame.winfo_children():
                w.pack_configure()
        else:
            for w in self._effect_custom_frame.winfo_children():
                w.pack_forget()

    def _on_effect_setting_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect'] = 'gold_outline' if self._effect_enabled.get() else 'none'
        item['effect_variation'] = self._effect_variation.get()
        item['effect_color_variation'] = self._color_variation.get()
        item['effect_opacity'] = self._effect_opacity.get()
        item['effect_glow'] = self._effect_glow.get()
        item['effect_timing'] = self._effect_timing.get()
        item['effect_start'] = self._effect_start.get()
        item['effect_end'] = self._effect_end.get()
        self._update_variation_desc()
        self._debounced_preview(interactive=True)

    def _on_kb_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['ken_burns_enabled'] = self._kb_enabled.get()
        item['ken_burns_zoom_in'] = self._kb_zoom_in.get()
        item['ken_burns_zoom_out'] = self._kb_zoom_out.get()
        item['ken_burns_pan_x'] = self._kb_pan_x.get()
        item['ken_burns_pan_y'] = self._kb_pan_y.get()
        self._debounced_preview(interactive=True)

    def _on_thug_life_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_thug_life_enabled'] = self._thug_life_enabled.get()
        item['thug_style'] = self._thug_style.get()
        item['thug_cap_enabled'] = self._thug_cap_enabled.get()
        item['thug_entry'] = self._thug_entry.get()
        self._debounced_preview(interactive=True)

    def _on_film_burn_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_film_burn_enabled'] = self._film_burn_enabled.get()
        item['film_burn_intensity'] = self._film_burn_intensity.get()
        item['film_burn_speed'] = self._film_burn_speed.get()
        self._debounced_preview(interactive=True)

    def _on_sun_glare_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_sun_glare_enabled'] = self._sun_glare_enabled.get()
        item['sun_glare_variation'] = self._sun_glare_variation.get()
        item['sun_glare_position'] = self._sun_glare_position.get()
        item['sun_glare_intensity'] = self._sun_glare_intensity.get()
        item['sun_glare_size'] = self._sun_glare_size.get()
        item['sun_glare_speed'] = self._sun_glare_speed.get()
        self._debounced_preview(interactive=True)

    def _on_x_flare_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_x_flare_enabled'] = self._x_flare_enabled.get()
        item['x_flare_variation'] = self._x_flare_variation.get()
        item['x_flare_position'] = self._x_flare_position.get()
        item['x_flare_intensity'] = self._x_flare_intensity.get()
        item['x_flare_size'] = self._x_flare_size.get()
        item['x_flare_speed'] = self._x_flare_speed.get()
        self._debounced_preview(interactive=True)

    def _on_light_flash_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_light_flash_enabled'] = self._light_flash_enabled.get()
        item['light_flash_variation'] = self._light_flash_variation.get()
        item['light_flash_position'] = self._light_flash_position.get()
        item['light_flash_intensity'] = self._light_flash_intensity.get()
        item['light_flash_size'] = self._light_flash_size.get()
        item['light_flash_speed'] = self._light_flash_speed.get()
        item['light_flash_density'] = self._light_flash_density.get()
        self._debounced_preview(interactive=True)

    def _on_canopy_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_canopy_enabled'] = self._canopy_enabled.get()
        item['canopy_light_style'] = self._canopy_light_style.get()
        item['canopy_light_dir'] = self._canopy_light_dir.get()
        item['canopy_fog_density'] = self._canopy_fog_density.get()
        item['canopy_fog_height'] = self._canopy_fog_height.get()
        item['canopy_ray_intensity'] = self._canopy_ray_intensity.get()
        item['canopy_ray_width'] = self._canopy_ray_width.get()
        item['canopy_warmth'] = self._canopy_warmth.get()
        item['canopy_shimmer'] = self._canopy_shimmer.get()
        item['canopy_show_light_source'] = self._canopy_show_light_source.get()
        self._debounced_preview(interactive=True)

    def _on_3d_text_tracking_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_3d_text_enabled'] = self._3d_text_enabled.get()
        item['3d_text_content'] = self._3d_text_content.get()
        item['3d_text_color'] = self._3d_text_color.get()
        item['3d_text_depth'] = self._3d_text_depth.get()
        item['3d_text_shadow'] = self._3d_text_shadow.get()
        item['3d_text_style'] = self._3d_text_style.get()
        item['3d_text_full_clip'] = self._3d_text_full_clip.get()
        try:
            item['3d_text_start'] = max(0.0, float(self._3d_text_start.get()))
        except (tk.TclError, ValueError):
            pass
        try:
            item['3d_text_end'] = max(0.05, float(self._3d_text_end.get()))
        except (tk.TclError, ValueError):
            pass
        try:
            item['3d_text_fade'] = max(0.0, float(self._3d_text_fade.get()))
        except (tk.TclError, ValueError):
            pass
        # --- Camera speed ---
        try:
            item['3d_cam_speed'] = max(0.0, float(self._3d_cam_speed.get()))
        except (tk.TclError, ValueError):
            pass
        self._debounced_preview(interactive=True)

    def _on_motion_track_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_motion_track_enabled'] = self._motion_track_enabled.get()
        item['motion_track_mode'] = self._motion_track_mode.get()
        item['motion_track_name'] = self._motion_track_name.get()
        item['motion_track_color'] = self._motion_track_color.get()
        item['motion_track_text_color'] = self._motion_track_text_color.get()
        item['motion_track_arrow_size'] = self._motion_track_arrow_size.get()
        item['motion_track_arrow_len'] = self._motion_track_arrow_len.get()
        item['motion_track_text_size'] = self._motion_track_text_size.get()
        item['motion_track_offset_y'] = self._motion_track_offset_y.get()
        self._debounced_preview(interactive=True)

    def _nudge_thug_accessory(self, dx=0.0, dy=0.0, scale_mult=1.0, rotate_delta=0.0,
                               toggle_flip_h=False, toggle_flip_v=False):
        """Apply a manual adjustment to whichever accessory is currently
        selected in the Thug Life panel's 'Editing:' dropdown. Adjustments
        are layered on top of the auto-detected position and persist with
        the clip (saved into item['thug_<accessory>_override'])."""
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        target = self._thug_adjust_target.get()
        key = f'thug_{target}_override'
        ov = dict(item.get(key) or {'dx': 0.0, 'dy': 0.0, 'scale': 1.0, 'rotation': 0.0,
                                     'flip_h': False, 'flip_v': False})
        ov['dx'] = ov.get('dx', 0.0) + dx
        ov['dy'] = ov.get('dy', 0.0) + dy
        ov['scale'] = max(0.1, min(5.0, ov.get('scale', 1.0) * scale_mult))
        ov['rotation'] = ov.get('rotation', 0.0) + rotate_delta
        if toggle_flip_h:
            ov['flip_h'] = not ov.get('flip_h', False)
        if toggle_flip_v:
            ov['flip_v'] = not ov.get('flip_v', False)
        item[key] = ov
        self._debounced_preview(interactive=True)

    def _reset_thug_accessory(self):
        """Clear the manual override for whichever accessory is currently
        selected, reverting it to pure auto-detected placement."""
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        target = self._thug_adjust_target.get()
        item[f'thug_{target}_override'] = None
        self._debounced_preview(interactive=True)
