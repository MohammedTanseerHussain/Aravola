"""Clip creation, media import, templates and clip-level edits.

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


class MediaMixin:
    """Clip creation, media import, templates and clip-level edits."""

    def create_clip_model(self, mtype, path="", name=""):
        return {
            'type': mtype, 'path': path, 'name': name,
            'clip_start': 0.0, 'clip_end': 0.0, 'speed': 1.0, 'value': 5.0,
            'rotation': 0, 'flip_h': False, 'flip_v': False,
            'volume': 1.0, 'muted': False, 'mute_regions': [],
            'vol_envelope': [(0.0, 1.0), (1.0, 1.0)],
            'ease_mode': 'none',
            'text': '', 'text_start': 0.0, 'text_end': 3.0, 'lt_style': 'Static Aurora Tile (Bracket)',
            'trans': 'Crossfade',
            'main_text': 'NEW TITLE', 'sub_text': 'Subtitle', 'theme': 'Cinematic – Light Speed Starburst',
            'effect': 'none',
            'effect_variation': 'ethereal',
            'effect_color_variation': 'Gold (Default)',
            'effect_opacity': 1.0,
            'effect_glow': 1.0,
            'effect_timing': 'full_clip',
            'effect_start': 0.0,
            'effect_end': 5.0,
            'effect_selected_person': -1,
            'effect_selected_class': None,
            'effect_yolo_locked': False,
            'effect_person_tracks': {},
            'effect_tracking_keyframes': {},
            'effect_mask_painting': None,
            'effect_mask_user_edited': False,
            'effect_person_template': None,
            'effect_face_buffer': [],
            'effect_drawn_mask': None,
            'effect_editing_base_mask': None,
            'effect_thug_life_enabled': False,
            'effect_film_burn_enabled': False,
            'film_burn_intensity': 1.0,
            'film_burn_speed': 1.0,
            'effect_sun_glare_enabled': False,
            'sun_glare_variation': 'Cinematic',
            'sun_glare_position': 'Top Left',
            'sun_glare_intensity': 1.0,
            'sun_glare_size': 1.0,
            'sun_glare_speed': 0.3,
            'effect_x_flare_enabled': False,
            'x_flare_variation': 'Blue White',
            'x_flare_position': 'Center',
            'x_flare_intensity': 1.0,
            'x_flare_size': 1.0,
            'x_flare_speed': 0.3,
            'effect_light_flash_enabled': False,
            'light_flash_variation': 'White Flash',
            'light_flash_position': 'Center',
            'light_flash_intensity': 1.0,
            'light_flash_size': 1.0,
            'light_flash_speed': 1.0,
            'light_flash_density': 6,
            'filter_enabled': False,
            'filter_style': 'Cinematic Warm',
            'filter_intensity': 1.0,
            'filter_warmth': 0.5,
            'filter_saturation': 1.0,
            'filter_fade_blacks': 0.15,
            'ken_burns_enabled': False,
            'ken_burns_zoom_in': 1.0,
            'ken_burns_zoom_out': 1.3,
            'ken_burns_pan_x': 0.0,
            'ken_burns_pan_y': 0.0,
            'effect_3d_text_enabled': False,
            '3d_text_content': 'TRACKING',
            '3d_text_color': 'Orange',
            '3d_text_depth': 0.4,
            '3d_text_quad': None,   # None => resolved to a default ground-plane quad on first use
            '3d_text_shadow': 0.5,
            '3d_text_style': 'Solid Matte',
            '3d_text_full_clip': True,   # False => only visible between 3d_text_start/3d_text_end
            '3d_text_start': 0.0,
            '3d_text_end': 3.0,
            '3d_text_fade': 0.3,
            '3d_text_track': None,   # set by "Track Forward From Here" (AR auto-tracking)
            '3d_cam_speed': 8.0,     # world units per second (forward along Z)
        }

    def add_media(self):
        _ensure_moviepy()
        paths = filedialog.askopenfilenames(filetypes=[("Media", "*.mp4 *.mov *.jpg *.png")])
        if paths: self.save_state()
        for p in paths:
            ext = p.lower().split('.')[-1]
            mtype = 'image' if ext in ['jpg', 'jpeg', 'png'] else 'video'
            self.media_queue.append(self.create_clip_model(mtype, p, os.path.basename(p)))
        if paths:
            self.selected_idx = len(self.media_queue) - 1
            self.playhead_t.set(0.0)
            self.update_global_preview()
            self.refresh_timeline()

    def add_title_card(self):
        _ensure_moviepy()
        self.save_state()
        self.media_queue.append(self.create_clip_model('title', name='TITLE CARD'))
        self.refresh_timeline()

    def add_placeholder(self):
        self.save_state()
        item = self.create_clip_model('placeholder', name='PLACEHOLDER')
        item['text'] = "Your Text Here"
        self.media_queue.append(item)
        self.refresh_timeline()

    def apply_template(self, tid):
        _ensure_moviepy()
        if not messagebox.askyesno("Template", "Append template sequence to your timeline?"): return
        self.save_state()
        if tid == 1:
            t1 = self.create_clip_model('title', name='TITLE CARD')
            t1.update({'main_text': 'DEEP SPACE', 'sub_text': 'EXPLORATION', 'theme': 'Cinematic – Deep Space Stars'})
            p1 = self.create_clip_model('placeholder', name='PLACEHOLDER')
            p1.update({'text': 'ASTRO PHYSICS', 'text_start': 0.0, 'text_end': 4.0, 'value': 6.0})
            self.media_queue.extend([t1, p1])
        elif tid == 2:
            t1 = self.create_clip_model('title', name='TITLE CARD')
            t1.update({'main_text': 'LIGHT SPEED', 'sub_text': 'FUSION', 'trans': 'Zoom In Fade', 'theme': 'Cinematic – Light Speed Starburst'})
            p1 = self.create_clip_model('placeholder', name='PLACEHOLDER')
            p1.update({'text': 'HYPER DRIVE ACTIVATED', 'lt_style': 'Purple Designer Box'})
            self.media_queue.extend([t1, p1])
        elif tid == 3:
            t1 = self.create_clip_model('title', name='TITLE CARD')
            t1.update({'main_text': 'THE JOURNEY', 'sub_text': 'BEGINS NOW', 'trans': 'Dip to Black', 'theme': 'Cinematic – Travelling Flare (Dynamic)', 'value': 6.0})
            p1 = self.create_clip_model('placeholder', name='PLACEHOLDER')
            p1.update({'text': 'MAGICAL AURORA', 'value': 7.0, 'text_end': 5.0, 'lt_style': 'Aurora Wave'})
            self.media_queue.extend([t1, p1])
        elif tid == 4:
            t1 = self.create_clip_model('title', name='TITLE CARD')
            t1.update({'main_text': 'IN OUR DARKEST HOUR', 'sub_text': 'HEADLINE', 'theme': 'Cinematic – Headlight Flare', 'lt_style': 'News Headline'})
            p1 = self.create_clip_model('placeholder', name='PLACEHOLDER')
            p1.update({'text': 'HEADLINE NEWS', 'lt_style': 'News Headline'})
            self.media_queue.extend([t1, p1])
        self.refresh_timeline()

    def fill_placeholder(self):
        path = filedialog.askopenfilename()
        if not path: return
        self.save_state()
        ext = path.lower().split('.')[-1]

        if self.selected_idx is not None:
            item = self.media_queue[self.selected_idx]
            item['path'] = path
            item['type'] = 'image' if ext in ['jpg', 'jpeg', 'png'] else 'video'
            item['name'] = os.path.basename(path)
            item['clip_start'] = 0.0
            item['clip_end'] = 0.0

        self.update_global_preview()
        self.refresh_timeline()
        self.render_inspector()

    def start_mute_draw_mode(self):
        if self.selected_idx is None:
            return messagebox.showwarning("Error", "Select a video clip first.")
        if self.media_queue[self.selected_idx]['type'] != 'video':
            return messagebox.showwarning("Error", "Mute regions only apply to video clips.")

        self._mute_drawing = True
        self.tl_mode_label.config(text="DRAW MUTE: Click & drag over timeline clip")

    def start_highlight_draw_mode(self):
        if self.selected_idx is None:
            return messagebox.showwarning("Error", "Select a video clip first.")
        if self.media_queue[self.selected_idx]['type'] != 'video':
            return messagebox.showwarning("Error", "Highlight regions only apply to video clips.")

        self._highlight_drawing = True
        self.tl_mode_label.config(text="DRAW HIGHLIGHT: Click & drag over timeline clip")

    def clear_mutes_on_selected(self):
        if self.selected_idx is not None:
            self.save_state()
            self.media_queue[self.selected_idx]["mute_regions"] = []
            self.refresh_timeline()
            self.render_inspector()

    def _remove_mute_region(self, region_idx):
        if self.selected_idx is None: return
        self.save_state()
        item = self.media_queue[self.selected_idx]
        if "mute_regions" in item and region_idx < len(item["mute_regions"]):
            del item["mute_regions"][region_idx]
            self.timeline_dirty = True
            self.refresh_timeline()
            self.render_inspector()
            self.update_global_preview()

    def _split_and_duplicate_highlight(self, idx, t0, t1):
        """Duplicate only the highlighted portion of a clip as a separate clip
        with speed/reverse controls. Original clip stays intact."""
        import copy as _copy
        item = self.media_queue[idx]
        clip_dur = self._item_duration(item)

        # Convert timeline-local times to source-clip local times
        local_t0 = max(0.0, min(t0, clip_dur))
        local_t1 = max(0.0, min(t1, clip_dur))
        if local_t1 - local_t0 < 0.05:
            return

        if item['type'] == 'video':
            try:
                if item['path'] not in self._clip_cache:
                    self._clip_cache_put(item['path'], VideoFileClip(item['path']))
                true_dur = self._clip_cache[item['path']].duration
            except:
                true_dur = 999.0

            SAFE = 0.05
            cs = item.get('clip_start', 0.0)
            ce = item.get('clip_end', 0.0)
            if ce <= cs:
                ce = true_dur

            # Highlight boundaries in source-file time
            hl_start = min(cs + local_t0, true_dur - SAFE)
            hl_end = min(cs + local_t1, true_dur - SAFE)
            hl_start = max(hl_start, cs + SAFE)
            hl_end = max(hl_end, hl_start + SAFE)

            # Create only the highlighted duplicate
            dup = _copy.deepcopy(item)
            dup['clip_start'] = hl_start
            dup['clip_end'] = hl_end
            dup['mute_regions'] = []
            dup['speed'] = 0.3
            dup['name'] = item.get('name', '') + ' (highlight)'
            dup['_highlight_effect'] = 'slowmo_zoom'
            dup['_highlight_zoom'] = 1.5

            # Insert the duplicate right after the original
            self.media_queue.insert(idx + 1, dup)

        else:
            # For non-video, just duplicate the portion
            dup = _copy.deepcopy(item)
            dup['value'] = local_t1 - local_t0
            dup['mute_regions'] = []
            dup['speed'] = 0.3
            dup['name'] = item.get('name', '') + ' (highlight)'
            dup['_highlight_effect'] = 'slowmo_zoom'
            dup['_highlight_zoom'] = 1.5

            self.media_queue.insert(idx + 1, dup)

        self.selected_idx = idx + 1  # Select the highlight duplicate
        self.timeline_dirty = True
        self.refresh_timeline()
        self.render_inspector()
        self.update_global_preview()

    def move_left(self):
        if self.selected_audio_idx is not None:
            idx = self.selected_audio_idx
            if idx > 0:
                self.bgm_tracks[idx], self.bgm_tracks[idx-1] = self.bgm_tracks[idx-1], self.bgm_tracks[idx]
                self.selected_audio_idx -= 1
        elif self.selected_idx is not None:
            idx = self.selected_idx
            if idx > 0:
                self.media_queue[idx], self.media_queue[idx-1] = self.media_queue[idx-1], self.media_queue[idx]
                self.selected_idx -= 1
        self.refresh_timeline()

    def move_right(self):
        if self.selected_audio_idx is not None:
            idx = self.selected_audio_idx
            if idx < len(self.bgm_tracks) - 1:
                self.bgm_tracks[idx], self.bgm_tracks[idx+1] = self.bgm_tracks[idx+1], self.bgm_tracks[idx]
                self.selected_audio_idx += 1
        elif self.selected_idx is not None:
            idx = self.selected_idx
            if idx < len(self.media_queue) - 1:
                self.media_queue[idx], self.media_queue[idx+1] = self.media_queue[idx+1], self.media_queue[idx]
                self.selected_idx += 1
        self.refresh_timeline()

    def delete_selected(self):
        _ensure_pygame()
        if self.selected_audio_idx is None and self.selected_idx is None: return
        self.save_state()
        self.is_playing = False
        if HAS_PYGAME:
            try: pygame.mixer.music.stop()
            except: pass

        if self.selected_audio_idx is not None:
            del self.bgm_tracks[self.selected_audio_idx]
            self._refresh_audio_list()
        elif self.selected_idx is not None:
            item_to_del = self.media_queue[self.selected_idx]
            if item_to_del.get('path'):
                self._close_cached_clip_for(item_to_del['path'])
            del self.media_queue[self.selected_idx]

        self.selected_idx = None
        self.selected_audio_idx = None
        self.timeline_dirty = True
        self.update_global_preview()
        self.refresh_timeline()
        self.render_inspector()

    def split_at_playhead(self):
        t = self.playhead_t.get()

        # Check audio track first if one is selected
        if self.selected_audio_idx is not None:
            cidx = self.selected_audio_idx
            bgm  = self.bgm_tracks[cidx]
            t_s  = float(bgm.get("start_offset", 0.0))
            try:
                if bgm["path"] not in self._clip_cache:
                    self._clip_cache_put(bgm["path"], AudioFileClip(bgm["path"]))
                file_dur = self._clip_cache[bgm["path"]].duration
            except:
                file_dur = 10.0
            # Played duration (respects clip_start / clip_end trimming)
            cs_n = float(bgm.get("clip_start", 0.0))
            ce_n = float(bgm.get("clip_end",   0.0))
            if ce_n <= cs_n: ce_n = file_dur
            played_dur = ce_n - cs_n
            if t_s < t < t_s + played_dur:
                # local_t = time within the played portion (0 … played_dur)
                local_t = t - t_s
                SAFE = 0.05
                local_t = min(max(local_t, SAFE), played_dur - SAFE)
                # Pass same value for t_start and t_end → single-point split
                self._region_split("audio", cidx, local_t, local_t)
                return
            return messagebox.showwarning("Error", "Playhead is not over the selected audio track.")

        split_idx = None
        for i, item in enumerate(self.media_queue):
            start = item.get("tl_start", 0.0)
            dur = self._item_duration(item)
            if start < t < start + dur:
                split_idx = i
                break

        if split_idx is None:
            return messagebox.showwarning("Error", "Playhead is not over a valid clip to split.")

        self.save_state()
        item = self.media_queue[split_idx]
        local_t = (t - item.get("tl_start", 0.0)) * item.get("speed", 1.0)

        part_b = copy.deepcopy(item)

        if item['type'] == 'video':
            # FIX: Get the true file duration so we can clamp safely
            try:
                if item['path'] not in self._clip_cache:
                    self._clip_cache_put(item['path'], VideoFileClip(item['path']))
                true_dur = self._clip_cache[item['path']].duration
            except:
                true_dur = 999.0

            split_point_internal = item.get('clip_start', 0.0) + local_t

            # FIX: clamp split point — never let clip_end sit exactly on or past
            # the file's real duration (leaves <50ms margin so subclip never overruns)
            SAFE_MARGIN = 0.05
            split_point_internal = min(split_point_internal, true_dur - SAFE_MARGIN)
            split_point_internal = max(split_point_internal, item.get('clip_start', 0.0) + SAFE_MARGIN)

            item['clip_end'] = split_point_internal
            part_b['clip_start'] = split_point_internal

            if part_b['clip_end'] == 0.0:
                # FIX: clamp part_b clip_end away from the real EOF too
                part_b['clip_end'] = max(part_b['clip_start'] + SAFE_MARGIN,
                                         true_dur - SAFE_MARGIN)
            else:
                # existing clip_end from a previous split — clamp it too
                part_b['clip_end'] = min(float(part_b['clip_end']), true_dur - SAFE_MARGIN)
                part_b['clip_end'] = max(part_b['clip_end'], part_b['clip_start'] + SAFE_MARGIN)
        else:
            item['value'] = local_t
            part_b['value'] = self._item_duration(part_b) - local_t

        part_b['tl_start'] = t
        part_b['mute_regions'] = []

        self.media_queue.insert(split_idx + 1, part_b)
        self.timeline_dirty = True

        if self.selected_idx is not None:
            self.selected_idx += 1

        self.refresh_timeline()
