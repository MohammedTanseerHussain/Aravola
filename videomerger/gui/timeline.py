"""Timeline hit-testing, trimming and region actions.

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


class TimelineMixin:
    """Timeline hit-testing, trimming and region actions."""

    def _get_clip_bounds(self, ctype, search_idx):
        y_cursor = self.RULER_H + 4
        curr_t = 0.0
        for i, item in enumerate(self.media_queue):
            dur = self._item_duration(item)
            if ctype == 'video' and i == search_idx:
                x_l = self.LABEL_W + int(curr_t * self.PPS)
                x_r = self.LABEL_W + int((curr_t + dur) * self.PPS)
                y_bot = y_cursor + self.TRACK_H
                return x_l, x_r, y_cursor, y_bot
            curr_t += dur

        y_cursor += self.TRACK_H + 14
        for j, aud in enumerate(self.bgm_tracks):
            t_s = aud.get('start_offset', 0.0)
            dur = self._get_bgm_played_dur(aud)
            
            y_bot = y_cursor + 40
            if ctype == 'audio' and j == search_idx:
                x_l = self.LABEL_W + int(t_s * self.PPS)
                x_r = self.LABEL_W + int((t_s + dur) * self.PPS)
                return x_l, x_r, y_cursor, y_bot
            y_cursor = y_bot + 2

        return None

    def _get_clip_at_pos(self, x, y):
        y_cursor = self.RULER_H + 4
        curr_t = 0.0
        for i, item in enumerate(self.media_queue):
            dur = self._item_duration(item)
            x_l = self.LABEL_W + int(curr_t * self.PPS)
            x_r = self.LABEL_W + int((curr_t + dur) * self.PPS)
            y_bot = y_cursor + self.TRACK_H
            if x_l <= x <= x_r and y_cursor <= y <= y_bot:
                return 'video', i, item, x_l, x_r, y_cursor, y_bot
            curr_t += dur

        y_cursor += self.TRACK_H + 14
        for j, aud in enumerate(self.bgm_tracks):
            t_s = aud.get('start_offset', 0.0)
            dur = self._get_bgm_played_dur(aud)
            
            x_l = self.LABEL_W + int(t_s * self.PPS)
            x_r = self.LABEL_W + int((t_s + dur) * self.PPS)
            y_bot = y_cursor + 40
            
            if x_l <= x <= x_r and y_cursor <= y <= y_bot:
                return 'audio', j, aud, x_l, x_r, y_cursor, y_bot
            y_cursor = y_bot + 2

        return None

    def _get_env_pt_at_pos(self, x, y):
        clip_info = self._get_clip_at_pos(x, y)
        if not clip_info: return None
        ctype, cidx, clip, x_l, x_r, y_top, y_bot = clip_info

        env = clip.get("vol_envelope", [])
        MAX_VOL = 2.0
        track_h = y_bot - y_top

        for pt_idx, (t_frac, vol) in enumerate(env):
            kx = x_l + t_frac * (x_r - x_l)
            ky = y_bot - (vol / MAX_VOL) * track_h
            if abs(x - kx) <= 8 and abs(y - ky) <= 8:
                return ctype, cidx, pt_idx
        return None

    def _close_env_popup(self):
        if self._env_pt_popup is not None:
            try: self._env_pt_popup.destroy()
            except: pass
            self._env_pt_popup = None

    def _show_env_pt_vol_popup(self, ctype, cidx, pt_idx, canvas_x, canvas_y):
        """Per-point gain popup.
        The envelope LINE graph is NOT touched — only a per-point gain
        stored in clip["pt_gains"][pt_idx] is changed.  This gain is
        applied as an instantaneous multiplier in the audio renderer so
        it causes a sudden volume drop/rise at that point without
        reshaping the smooth curve between any neighbours.
        """
        self._close_env_popup()
        clip = self.media_queue[cidx] if ctype == "video" else self.bgm_tracks[cidx]
        env  = clip.get("vol_envelope", [])
        if pt_idx >= len(env): return
        t_frac, _ = env[pt_idx]
        # pt_gains is independent of vol_envelope
        if "pt_gains" not in clip:
            clip["pt_gains"] = {}
        cur_gain = float(clip["pt_gains"].get(str(pt_idx), 1.0))

        rx = self.timeline_canvas.winfo_rootx() + int(canvas_x - self.timeline_canvas.canvasx(0)) + 12
        ry = self.timeline_canvas.winfo_rooty() + int(canvas_y - self.timeline_canvas.canvasy(0)) - 85
        popup = tk.Toplevel(self.root)
        popup.wm_overrideredirect(True)
        popup.wm_geometry(f"+{rx}+{ry}")
        popup.configure(bg=C["raised"])
        self._env_pt_popup = popup

        tk.Label(popup, text=f"Point gain (sudden)",
                 bg=C["raised"], fg=C["accent"],
                 font=("Segoe UI", 8, "bold")).pack(padx=8, pady=(5,0))
        tk.Label(popup, text="(does not change curve)",
                 bg=C["raised"], fg=C["text_dim"],
                 font=("Segoe UI", 7)).pack(padx=8)

        gain_var = tk.DoubleVar(value=cur_gain)

        def on_gain_change(v, _ctype=ctype, _cidx=cidx, _idx=pt_idx):
            new_gain = float(v)
            c2 = self.media_queue[_cidx] if _ctype == "video" else self.bgm_tracks[_cidx]
            if "pt_gains" not in c2:
                c2["pt_gains"] = {}
            c2["pt_gains"][str(_idx)] = new_gain
            self.timeline_dirty = True
            self.timeline_canvas.after_idle(self.refresh_timeline)

        tk.Scale(popup, from_=0.0, to=2.0, resolution=0.05, orient=tk.HORIZONTAL,
                 variable=gain_var, command=on_gain_change,
                 bg=C["raised"], fg=C["text"], highlightthickness=0,
                 troughcolor=C["border"], length=130, showvalue=True,
                 font=("Segoe UI", 8)).pack(padx=6, pady=(2,5))

        def on_close():
            self.save_state()
            self._close_env_popup()
        tk.Button(popup, text="✓ Done", bg=C["accent3"], fg=C["bg"],
                  bd=0, font=("Segoe UI", 8, "bold"), padx=4, pady=2,
                  command=on_close).pack(padx=6, pady=(0,5))
        popup.bind("<FocusOut>", lambda e: self._close_env_popup())

    def _show_region_action_popup(self, ctype, cidx, key):
        """Show Delete / Split / Cancel popup after both markers are placed."""
        tA = self._trim_marker_A.get(key, 0.0)
        tB = self._trim_marker_B.get(key, 0.0)
        t_start = min(tA, tB)
        t_end   = max(tA, tB)
        if t_end - t_start < 0.05:
            # Too small — clear markers
            self._trim_marker_A.pop(key, None)
            self._trim_marker_B.pop(key, None)
            self.refresh_timeline()
            return

        popup = tk.Toplevel(self.root)
        popup.wm_overrideredirect(True)
        # Centre on the timeline canvas
        cx = self.timeline_canvas.winfo_rootx() + self.timeline_canvas.winfo_width() // 2
        cy = self.timeline_canvas.winfo_rooty() + self.timeline_canvas.winfo_height() // 2
        popup.wm_geometry(f"+{cx-80}+{cy-40}")
        popup.configure(bg=C["surface"])
        popup.grab_set()

        tk.Label(popup, text=f"Region  {t_start:.2f}s → {t_end:.2f}s",
                 bg=C["surface"], fg=C["accent"], font=("Segoe UI", 9, "bold")).pack(padx=10, pady=(6,4))

        btn_f = tk.Frame(popup, bg=C["surface"])
        btn_f.pack(padx=8, pady=(0,8))

        def do_delete():
            popup.destroy()
            self._region_delete(ctype, cidx, t_start, t_end)
            self._trim_marker_A.pop(key, None)
            self._trim_marker_B.pop(key, None)
            self.refresh_timeline()

        def do_split():
            popup.destroy()
            self._region_split(ctype, cidx, t_start, t_end)
            self._trim_marker_A.pop(key, None)
            self._trim_marker_B.pop(key, None)
            self.refresh_timeline()

        def do_cancel():
            popup.destroy()
            self._trim_marker_A.pop(key, None)
            self._trim_marker_B.pop(key, None)
            self.refresh_timeline()

        tk.Button(btn_f, text="🗑 Delete", bg=C["danger"], fg="white",
                  bd=0, font=("Segoe UI", 9, "bold"), padx=6, pady=3,
                  command=do_delete).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_f, text="✂ Split", bg=C["accent"], fg=C["bg"],
                  bd=0, font=("Segoe UI", 9, "bold"), padx=6, pady=3,
                  command=do_split).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_f, text="✕", bg=C["raised"], fg=C["text_dim"],
                  bd=0, font=("Segoe UI", 9), padx=6, pady=3,
                  command=do_cancel).pack(side=tk.LEFT, padx=3)

    def _clean_bgm_copy(self, bgm):
        """deepcopy a BGM dict after stripping un-picklable Tkinter vars.
        Keys starting with _ (e.g. _vol_var, _mute_var) are Tkinter objects
        added by _refresh_audio_list and cannot be pickled by copy.deepcopy.
        """
        clean = {k: v for k, v in bgm.items() if not k.startswith("_")}
        return copy.deepcopy(clean)

    def _region_delete(self, ctype, cidx, t_start, t_end):
        """Delete the region between t_start and t_end (local clip time)."""
        self.save_state()
        if ctype == "video":
            item = self.media_queue[cidx]
            cs = float(item.get("clip_start", 0.0))
            # Split into part_A (before region) and part_B (after region)
            part_A = copy.deepcopy(item)
            part_B = copy.deepcopy(item)
            try:
                if item["path"] not in self._clip_cache:
                    self._clip_cache_put(item["path"], VideoFileClip(item["path"]))
                file_dur = self._clip_cache[item["path"]].duration
            except:
                file_dur = 999.0
            SAFE = 0.05
            part_A["clip_end"]   = min(cs + t_start, file_dur - SAFE)
            part_B["clip_start"] = min(cs + t_end,   file_dur - SAFE)
            part_B["clip_end"]   = float(item.get("clip_end", 0.0)) or (file_dur - SAFE)
            part_B["mute_regions"] = []
            new_queue = []
            for i, m in enumerate(self.media_queue):
                if i == cidx:
                    dur_A = part_A["clip_end"] - part_A.get("clip_start", 0.0)
                    dur_B = part_B["clip_end"] - part_B["clip_start"]
                    if dur_A > SAFE: new_queue.append(part_A)
                    if dur_B > SAFE: new_queue.append(part_B)
                else:
                    new_queue.append(m)
            self.media_queue = new_queue
            self.selected_idx = None
        else:
            bgm = self.bgm_tracks[cidx]
            try:
                if bgm["path"] not in self._clip_cache:
                    self._clip_cache_put(bgm["path"], AudioFileClip(bgm["path"]))
                file_dur = self._clip_cache[bgm["path"]].duration
            except:
                file_dur = 999.0
            SAFE = 0.05
            # Normalise: clip_end == 0.0 means "play to end of file"
            cs_n  = float(bgm.get("clip_start", 0.0))
            ce_n  = float(bgm.get("clip_end",   0.0))
            if ce_n <= cs_n:
                ce_n = file_dur - SAFE
            base_off = float(bgm.get("start_offset", 0.0))
            # t_start / t_end are LOCAL time within the played portion
            cut_s = cs_n + t_start   # absolute file-time start of cut
            cut_e = cs_n + t_end     # absolute file-time end of cut
            cut_s = min(max(cut_s, cs_n + SAFE), ce_n - SAFE)
            cut_e = min(max(cut_e, cs_n + SAFE), ce_n - SAFE)
            part_A = self._clean_bgm_copy(bgm)
            part_A["clip_start"] = cs_n
            part_A["clip_end"]   = cut_s
            part_A["start_offset"] = base_off
            dur_A = max(0.0, cut_s - cs_n)
            part_B = self._clean_bgm_copy(bgm)
            part_B["clip_start"] = cut_e
            part_B["clip_end"]   = ce_n
            part_B["start_offset"] = base_off + dur_A
            dur_B = max(0.0, ce_n - cut_e)
            new_tracks = []
            for j, b in enumerate(self.bgm_tracks):
                if j == cidx:
                    if dur_A > SAFE: new_tracks.append(part_A)
                    if dur_B > SAFE: new_tracks.append(part_B)
                else:
                    new_tracks.append(b)
            self.bgm_tracks = new_tracks
            self.selected_audio_idx = None
            self._refresh_audio_list()
        self.timeline_dirty = True
        self.refresh_timeline()
        self.update_global_preview()
        self.render_inspector()

    def _region_split(self, ctype, cidx, t_start, t_end):
        """Split at t_start and t_end. If t_start==t_end, split at one point (2 pieces)."""
        self.save_state()
        if ctype == "video":
            item = self.media_queue[cidx]
            cs = float(item.get("clip_start", 0.0))
            try:
                if item["path"] not in self._clip_cache:
                    self._clip_cache_put(item["path"], VideoFileClip(item["path"]))
                file_dur = self._clip_cache[item["path"]].duration
            except:
                file_dur = 999.0
            SAFE = 0.05
            part_A = copy.deepcopy(item)
            part_A["clip_end"]   = min(cs + t_start, file_dur - SAFE)
            part_M = copy.deepcopy(item)
            part_M["clip_start"] = min(cs + t_start, file_dur - SAFE)
            part_M["clip_end"]   = min(cs + t_end, file_dur - SAFE)
            part_B = copy.deepcopy(item)
            part_B["clip_start"] = min(cs + t_end, file_dur - SAFE)
            part_B["clip_end"]   = float(item.get("clip_end", 0.0)) or (file_dur - SAFE)
            part_A["mute_regions"] = []
            part_M["mute_regions"] = []
            part_B["mute_regions"] = []
            new_queue = []
            for i, m in enumerate(self.media_queue):
                if i == cidx:
                    for p in (part_A, part_M, part_B):
                        ce = p.get("clip_end", 0.0); cs2 = p.get("clip_start", 0.0)
                        if ce - cs2 > SAFE: new_queue.append(p)
                else:
                    new_queue.append(m)
            self.media_queue = new_queue
            self.selected_idx = None
        else:
            bgm = self.bgm_tracks[cidx]
            try:
                if bgm["path"] not in self._clip_cache:
                    self._clip_cache_put(bgm["path"], AudioFileClip(bgm["path"]))
                file_dur = self._clip_cache[bgm["path"]].duration
            except:
                file_dur = 999.0
            SAFE = 0.05
            # Normalise: clip_end == 0.0 means "play to end of file"
            cs_n  = float(bgm.get("clip_start", 0.0))
            ce_n  = float(bgm.get("clip_end",   0.0))
            if ce_n <= cs_n:
                ce_n = file_dur - SAFE
            base_off = float(bgm.get("start_offset", 0.0))
            # t_start / t_end are LOCAL time within the played portion
            spl_s = min(max(cs_n + t_start, cs_n + SAFE), ce_n - SAFE)
            spl_e = min(max(cs_n + t_end,   cs_n + SAFE), ce_n - SAFE)
            if spl_e < spl_s: spl_e = spl_s   # single-point split
            part_A = self._clean_bgm_copy(bgm)
            part_A["clip_start"] = cs_n
            part_A["clip_end"]   = spl_s
            part_A["start_offset"] = base_off
            dur_A = max(0.0, spl_s - cs_n)
            part_M = self._clean_bgm_copy(bgm)
            part_M["clip_start"] = spl_s
            part_M["clip_end"]   = spl_e
            part_M["start_offset"] = base_off + dur_A
            dur_M = max(0.0, spl_e - spl_s)
            part_B = self._clean_bgm_copy(bgm)
            part_B["clip_start"] = spl_e
            part_B["clip_end"]   = ce_n
            part_B["start_offset"] = base_off + dur_A + dur_M
            dur_B = max(0.0, ce_n - spl_e)
            new_tracks = []
            for j, b in enumerate(self.bgm_tracks):
                if j == cidx:
                    if dur_A > SAFE: new_tracks.append(part_A)
                    if dur_M > SAFE: new_tracks.append(part_M)
                    if dur_B > SAFE: new_tracks.append(part_B)
                else:
                    new_tracks.append(b)
            self.bgm_tracks = new_tracks
            self.selected_audio_idx = None
            self._refresh_audio_list()
        self.timeline_dirty = True
        self.refresh_timeline()
        self.update_global_preview()
        self.render_inspector()

    def _set_handle_mode(self, mode):
        """Switch between "trim" (A/B region markers) and "extend"
        (clip-edge drag to recover/trim footage). Updates button colours.
        """
        self._handle_mode = mode
        self._update_handle_mode_buttons()
        label = "TRIM MODE: Drag A/B markers to define cut region" if mode == "trim" \
                else "EXTEND MODE: Drag clip edges to expand or trim"
        self.tl_mode_label.config(text=label)
        self.refresh_timeline()

    def _update_handle_mode_buttons(self):
        """Visually highlight the active mode button."""
        try:
            if self._handle_mode == "trim":
                self._btn_trim_mode.config(bg=C["accent"], fg=C["bg"])
                self._btn_extend_mode.config(bg=C["raised"], fg=C["text"])
            else:
                self._btn_trim_mode.config(bg=C["raised"], fg=C["text"])
                self._btn_extend_mode.config(bg=C["accent4"], fg=C["bg"])
        except AttributeError:
            pass   # buttons not yet built on first __init__ call

    def _get_extend_handle_at_pos(self, x, y):
        """Hit-test the clip-edge EXTEND handles (separate from A/B region
        markers). These sit exactly at x_l and x_r of the selected clip and
        let the user drag outward to recover trimmed footage or inward to
        trim further — like dragging clip edges in Premiere/CapCut.
        """
        EDGE_HIT = 7

        def check(ctype, cidx):
            bounds = self._get_clip_bounds(ctype, cidx)
            if not bounds: return None
            x_l, x_r, y_top, y_bot = bounds
            if not (y_top <= y <= y_bot): return None
            if abs(x - x_l) <= EDGE_HIT:
                return ("left", ctype, cidx)
            if abs(x - x_r) <= EDGE_HIT:
                return ("right", ctype, cidx)
            return None

        if self.selected_idx is not None:
            r = check("video", self.selected_idx)
            if r: return r
        if self.selected_audio_idx is not None:
            r = check("audio", self.selected_audio_idx)
            if r: return r
        return None

    def _get_trim_handle_at_pos(self, x, y):
        """Hit-test the two free-floating region markers (A and B).
        Returns (marker_id, ctype, cidx) or None.
        Markers live as t_local values in _trim_marker_A/_trim_marker_B.
        """
        HIT = 8   # pixel hit radius

        def check(ctype, cidx):
            bounds = self._get_clip_bounds(ctype, cidx)
            if not bounds: return None
            x_l, x_r, y_top, y_bot = bounds
            if not (y_top <= y <= y_bot): return None
            key = (ctype, cidx)
            clip_w = max(1, x_r - x_l)
            clip_dur = self._get_clip_display_dur(ctype, cidx)
            for marker_id, store in (("A", self._trim_marker_A), ("B", self._trim_marker_B)):
                if key not in store: continue
                t_local = store[key]
                mx = x_l + int(t_local / max(0.001, clip_dur) * clip_w)
                if abs(x - mx) <= HIT:
                    return (marker_id, ctype, cidx)
            return None

        if self.selected_idx is not None:
            r = check("video", self.selected_idx)
            if r: return r
        if self.selected_audio_idx is not None:
            r = check("audio", self.selected_audio_idx)
            if r: return r
        return None

    def _get_bgm_played_dur(self, aud):
        """Return the actual played duration of a BGM dict, respecting
        clip_start and clip_end (clip_end==0 means play to end of file).
        """
        try:
            if aud["path"] not in self._clip_cache:
                self._clip_cache_put(aud["path"], AudioFileClip(aud["path"]))
            file_dur = self._clip_cache[aud["path"]].duration
        except:
            file_dur = 10.0
        cs = float(aud.get("clip_start", 0.0))
        ce = float(aud.get("clip_end",   0.0))
        if ce <= cs:
            ce = file_dur
        return max(0.0, ce - cs)

    def _get_clip_display_dur(self, ctype, cidx):
        """Return the displayed (trimmed) duration for a clip."""
        if ctype == "video":
            return self._item_duration(self.media_queue[cidx])
        bgm = self.bgm_tracks[cidx]
        try:
            if bgm["path"] not in self._clip_cache:
                self._clip_cache_put(bgm["path"], AudioFileClip(bgm["path"]))
            full = self._clip_cache[bgm["path"]].duration
        except:
            full = 10.0
        cs = float(bgm.get("clip_start", 0.0))
        ce = float(bgm.get("clip_end",   0.0))
        return (ce - cs) if ce > cs else full
