"""Selected-clip inspector UI and clip transforms.

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


class InspectorMixin:
    """Selected-clip inspector UI and clip transforms."""

    def change_rotation(self, direction):
        if self.selected_idx is None: return
        self.save_state()
        item = self.media_queue[self.selected_idx]
        if direction == 'left':
            item['rotation'] = (item.get('rotation', 0) - 90) % 360
        elif direction == 'right':
            item['rotation'] = (item.get('rotation', 0) + 90) % 360
        elif direction == 'fliph':
            item['flip_h'] = not item.get('flip_h', False)
        elif direction == 'flipv':
            item['flip_v'] = not item.get('flip_v', False)

        self.update_global_preview()

        base_path = item.get('path', '')
        keys_to_delete = [k for k in self._clip_cache.keys() if str(k).startswith(f"filmstrip_v3_{base_path}")]
        for k in keys_to_delete:
            del self._clip_cache[k]

        self.refresh_timeline()

    def render_inspector(self):
        f = self.insp_inner
        for w in f.winfo_children(): w.destroy()

        if self.selected_idx is None and self.selected_audio_idx is None:
            tk.Label(f, text="Select a clip to edit properties.", bg=C["panel"], fg="gray").pack(pady=100)
            return

        is_aud = (self.selected_audio_idx is not None)
        item = self.bgm_tracks[self.selected_audio_idx] if is_aud else self.media_queue[self.selected_idx]

        tk.Label(f, text=f"EDIT: {item.get('type', 'audio').upper()}", bg=C["panel"], fg="#FFD700", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        def make_entry(parent, textvariable):
            return tk.Entry(parent, textvariable=textvariable,
                            bg="#2a2a2a", fg="#ffffff",
                            insertbackground="white",
                            selectbackground=C["accent"],
                            selectforeground="#000000",
                            relief="flat", bd=2)

        def make_combo(parent, textvariable, values, width=22):
            cb = ttk.Combobox(parent, textvariable=textvariable,
                              values=values, width=width,
                              style="TCombobox")
            try:
                cb.tk.eval(f'ttk::style configure TCombobox -foreground white')
            except Exception:
                pass
            return cb

        def row(label, widget_fn):
            r = tk.Frame(f, bg=C["panel"])
            r.pack(fill=tk.X, padx=8, pady=3)
            tk.Label(r, text=label, bg=C["panel"], fg=C["text_dim"], font=("Arial", 8), width=14, anchor="e").pack(side=tk.LEFT)
            widget_fn(r)

        if not is_aud and item['type'] in ('video', 'image', 'placeholder'):
            tk.Button(f, text="📁 Replace Media", bg="#2196F3", fg="white", bd=0, font=("Arial", 9, "bold"), command=self.fill_placeholder).pack(fill=tk.X, padx=10, pady=(0, 10), ipady=4)

        if is_aud:
            self.ins_vol = tk.DoubleVar(value=item.get('volume', 1.0))
            self.ins_offset = tk.DoubleVar(value=item.get('start_offset', 0.0))
            self.ins_a_start = tk.DoubleVar(value=item.get('clip_start', 0.0))
            self.ins_a_end = tk.DoubleVar(value=item.get('clip_end', 10.0))

            tk.Label(f, text="Volume (0-2.0):", bg=C["panel"], fg="white").pack(anchor="w", padx=10)
            tk.Scale(f, variable=self.ins_vol, from_=0.0, to=2.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, padx=10)

            tk.Label(f, text="Timeline Start (s):", bg=C["panel"], fg="white").pack(anchor="w", padx=10)
            tk.Scale(f, variable=self.ins_offset, from_=0.0, to=100.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, padx=10)

            tk.Label(f, text="Trim Audio Start:", bg=C["panel"], fg="white").pack(anchor="w", padx=10)
            tk.Scale(f, variable=self.ins_a_start, from_=0.0, to=100.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, padx=10)

            tk.Label(f, text="Trim Audio End:", bg=C["panel"], fg="white").pack(anchor="w", padx=10)
            tk.Scale(f, variable=self.ins_a_end, from_=0.0, to=100.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, padx=10)

        else:
            self.ins_dur = tk.DoubleVar(value=item.get('value', 5.0))
            self.ins_speed = tk.DoubleVar(value=item.get('speed', 1.0))
            self.ins_trans = tk.StringVar(value=item.get('trans', 'Crossfade'))

            rot_f = tk.Frame(f, bg=C["panel"])
            rot_f.pack(fill=tk.X, padx=10, pady=5)
            tk.Button(rot_f, text="↺ Left", bg="#333", fg="white", bd=0, command=lambda: self.change_rotation('left')).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
            tk.Button(rot_f, text="Right ↻", bg="#333", fg="white", bd=0, command=lambda: self.change_rotation('right')).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
            tk.Button(rot_f, text="↔ Flip H", bg="#333", fg="white", bd=0, command=lambda: self.change_rotation('fliph')).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
            tk.Button(rot_f, text="↕ Flip V", bg="#333", fg="white", bd=0, command=lambda: self.change_rotation('flipv')).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)

            if item['type'] == 'video':
                max_dur = 10.0
                if item.get('path'):
                    try:
                        if item['path'] not in self._clip_cache: self._clip_cache_put(item['path'], VideoFileClip(item['path']))
                        max_dur = self._clip_cache[item['path']].duration
                    except: pass

                self.ins_c_start = tk.DoubleVar(value=item.get('clip_start', 0.0))
                self.ins_c_end = tk.DoubleVar(value=item.get('clip_end', max_dur))

                tk.Label(f, text="Video Properties:", bg=C["panel"], fg=C["accent"]).pack(anchor="w", padx=10, pady=(10, 0))
                row("Speed (x):", lambda r: tk.Scale(r, variable=self.ins_speed, from_=0.1, to=5.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
                row("Cut Start:", lambda r: tk.Scale(r, variable=self.ins_c_start, from_=0, to=max_dur, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
                row("Cut End:", lambda r: tk.Scale(r, variable=self.ins_c_end, from_=0, to=max_dur, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))

                self.ins_muted = tk.BooleanVar(value=item.get('muted', False))
                self.ins_vol = tk.DoubleVar(value=item.get('volume', 1.0))
                tk.Checkbutton(f, text="Mute Original Audio", variable=self.ins_muted, bg=C["panel"], fg="white", selectcolor="#333").pack(anchor="w", padx=10, pady=5)
                row("Volume:", lambda r: tk.Scale(r, variable=self.ins_vol, from_=0.0, to=2.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))

            else:
                row("Duration (s):", lambda r: make_entry(r, self.ins_dur).pack(fill=tk.X, expand=True, ipady=3))

            if item['type'] == 'title':
                self.ins_mtxt = tk.StringVar(value=item.get('main_text', ''))
                self.ins_stxt = tk.StringVar(value=item.get('sub_text', ''))
                self.ins_theme = tk.StringVar(value=item.get('theme', ''))
                self.ins_muted = tk.BooleanVar(value=item.get('muted', False))
                self.ins_txt = tk.StringVar(value=item.get('text', ''))
                self.ins_t_start = tk.DoubleVar(value=item.get('text_start', 0.0))
                self.ins_t_end = tk.DoubleVar(value=item.get('text_end', 3.0))
                self.ins_ltstyle = tk.StringVar(value=item.get('lt_style', 'News Headline'))

                tk.Label(f, text="Title Card:", bg=C["panel"], fg=C["accent"]).pack(anchor="w", padx=10, pady=(10, 0))
                row("Main Text:", lambda r: make_entry(r, self.ins_mtxt).pack(fill=tk.X, expand=True, ipady=3))
                row("Sub Text:", lambda r: make_entry(r, self.ins_stxt).pack(fill=tk.X, expand=True, ipady=3))
                row("Theme:", lambda r: make_combo(r, self.ins_theme, [
                    "Cinematic – Light Speed Starburst",
                    "Cinematic – Deep Space Stars",
                    "Cinematic – Travelling Flare (Dynamic)",
                    "Cinematic – Blue Flare",
                    "Cinematic – Headlight Flare"
                ]).pack(side=tk.LEFT))
                
                tk.Checkbutton(f, text="Mute Title SFX", variable=self.ins_muted, bg=C["panel"], fg="white", selectcolor="#333").pack(anchor="w", padx=10, pady=5)

                tk.Label(f, text="Lower Third Overlay:", bg=C["panel"], fg=C["accent"]).pack(anchor="w", padx=10, pady=(10, 0))
                row("Text:", lambda r: make_entry(r, self.ins_txt).pack(fill=tk.X, expand=True, ipady=3))
                row("Start (s):", lambda r: tk.Scale(r, variable=self.ins_t_start, from_=0.0, to=60.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
                row("End (s):", lambda r: tk.Scale(r, variable=self.ins_t_end, from_=0.0, to=60.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
                row("Style:", lambda r: make_combo(r, self.ins_ltstyle, [
                    "News Headline", "Static Aurora Tile (Bracket)", "Aurora Wave", "Purple Designer Box"
                ]).pack(side=tk.LEFT))
            else:
                self.ins_txt = tk.StringVar(value=item.get('text', ''))
                self.ins_t_start = tk.DoubleVar(value=item.get('text_start', 0.0))
                self.ins_t_end = tk.DoubleVar(value=item.get('text_end', 3.0))
                self.ins_ltstyle = tk.StringVar(value=item.get('lt_style', 'Static Aurora Tile (Bracket)'))

                tk.Label(f, text="Text Overlay:", bg=C["panel"], fg=C["accent"]).pack(anchor="w", padx=10, pady=(10, 0))
                row("Text:", lambda r: make_entry(r, self.ins_txt).pack(fill=tk.X, expand=True, ipady=3))
                row("Start (s):", lambda r: tk.Scale(r, variable=self.ins_t_start, from_=0.0, to=60.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
                row("End (s):", lambda r: tk.Scale(r, variable=self.ins_t_end, from_=0.0, to=60.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
                row("Style:", lambda r: make_combo(r, self.ins_ltstyle, [
                    "Static Aurora Tile (Bracket)", "Aurora Wave", "Purple Designer Box"
                ]).pack(side=tk.LEFT))

            row("Transition:", lambda r: make_combo(r, self.ins_trans, [
                "Crossfade", "Dip to Black", "Hard Cut", "Slide Left", "Slide Up", "Zoom In Fade", "Bright Flash", "Pull and Snap"
            ]).pack(side=tk.LEFT))

            # Per-clip filter
            self.ins_filter_enabled = tk.BooleanVar(value=item.get('filter_enabled', False))
            self.ins_filter_style = tk.StringVar(value=item.get('filter_style', 'Cinematic Warm'))
            self.ins_filter_intensity = tk.DoubleVar(value=item.get('filter_intensity', 1.0))
            self.ins_filter_warmth = tk.DoubleVar(value=item.get('filter_warmth', 0.5))
            self.ins_filter_saturation = tk.DoubleVar(value=item.get('filter_saturation', 1.0))
            self.ins_filter_fade_blacks = tk.DoubleVar(value=item.get('filter_fade_blacks', 0.15))

            sep2 = tk.Frame(f, bg=C["border"], height=1)
            sep2.pack(fill=tk.X, padx=8, pady=8)
            tk.Label(f, text="COLOR FILTER (per-clip)", bg=C["panel"], fg=C["accent4"],
                     font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(0, 5))

            row("Enable Filter:", lambda r: tk.Checkbutton(r, variable=self.ins_filter_enabled,
                     bg=C["panel"], fg="white", selectcolor=C["raised"],
                     command=self._on_inspector_filter_changed).pack(side=tk.LEFT))

            row("Filter Style:", lambda r: make_combo(r, self.ins_filter_style, [
                "Cinematic Warm", "Golden Hour", "Vintage Film", "Teal & Orange",
                "Bleach Bypass", "Cold Blue", "Desaturated", "High Contrast"
            ]).pack(side=tk.LEFT))

            row("Intensity:", lambda r: tk.Scale(r, variable=self.ins_filter_intensity,
                     from_=0.0, to=1.0, resolution=0.05, orient=tk.HORIZONTAL,
                     bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                     troughcolor=C["border"], length=140).pack(side=tk.LEFT))

            row("Warmth:", lambda r: tk.Scale(r, variable=self.ins_filter_warmth,
                     from_=0.0, to=1.0, resolution=0.05, orient=tk.HORIZONTAL,
                     bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                     troughcolor=C["border"], length=140).pack(side=tk.LEFT))

            row("Saturation:", lambda r: tk.Scale(r, variable=self.ins_filter_saturation,
                     from_=0.0, to=2.0, resolution=0.05, orient=tk.HORIZONTAL,
                     bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                     troughcolor=C["border"], length=140).pack(side=tk.LEFT))

            row("Fade Blacks:", lambda r: tk.Scale(r, variable=self.ins_filter_fade_blacks,
                     from_=0.0, to=0.5, resolution=0.01, orient=tk.HORIZONTAL,
                     bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                     troughcolor=C["border"], length=140).pack(side=tk.LEFT))

        tk.Button(f, text="💾 Save Inspector Data", bg=C["accent3"], fg=C["bg"], font=("Segoe UI", 10, "bold"), bd=0, command=self.save_inspector).pack(fill=tk.X, padx=10, pady=20, ipady=5)


        if item.get("mute_regions"):
            sep = tk.Frame(f, bg=C["border"], height=1)
            sep.pack(fill=tk.X, padx=8, pady=4)
            tk.Label(f, text="MUTE REGIONS", bg=C["panel"], fg=C["accent2"], font=("Arial", 8, "bold")).pack(anchor="w", padx=10)
            for idx2, mr in enumerate(item["mute_regions"]):
                mr_row = tk.Frame(f, bg=C["raised"])
                mr_row.pack(fill=tk.X, padx=8, pady=1)
                tk.Label(mr_row, text=f"  {mr[0]:.2f}s → {mr[1]:.2f}s", bg=C["raised"], fg=C["accent2"], font=("Courier", 8)).pack(side=tk.LEFT, padx=4)
                tk.Button(mr_row, text="✕", command=lambda i=idx2: self._remove_mute_region(i), bg=C["raised"], fg="#ff4444", relief="flat", font=("Arial", 9, "bold"), cursor="hand2").pack(side=tk.RIGHT, padx=4)

        if item.get("_highlight_effect"):
            sep = tk.Frame(f, bg=C["border"], height=1)
            sep.pack(fill=tk.X, padx=8, pady=4)
            tk.Label(f, text="HIGHLIGHT CLIP", bg=C["panel"], fg="#00897B", font=("Arial", 9, "bold")).pack(anchor="w", padx=10)
            hl_row = tk.Frame(f, bg=C["raised"])
            hl_row.pack(fill=tk.X, padx=8, pady=4)

            # Effect type
            eff_var = tk.StringVar(value=item.get('_highlight_effect', 'slowmo_zoom'))
            ttk.Combobox(hl_row, textvariable=eff_var, values=['slowmo_zoom', 'reverse'],
                         state="readonly", width=14).pack(side=tk.LEFT, padx=4)
            tk.Label(hl_row, text="Effect", bg=C["raised"], fg="#aaa", font=("Segoe UI", 7)).pack(side=tk.LEFT)

            # Speed slider
            spd_row = tk.Frame(f, bg=C["raised"])
            spd_row.pack(fill=tk.X, padx=8, pady=2)
            self.ins_hl_speed = tk.DoubleVar(value=item.get('speed', 0.3))
            tk.Label(spd_row, text="Speed", bg=C["raised"], fg="#aaa", font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=4)
            tk.Scale(spd_row, variable=self.ins_hl_speed, from_=0.1, to=0.9, resolution=0.1,
                     orient=tk.HORIZONTAL, bg=C["raised"], fg="white", bd=0,
                     highlightthickness=0, troughcolor=C["border"]).pack(side=tk.LEFT, fill=tk.X, expand=True)

            # Zoom slider
            z_row = tk.Frame(f, bg=C["raised"])
            z_row.pack(fill=tk.X, padx=8, pady=2)
            self.ins_hl_zoom = tk.DoubleVar(value=item.get('_highlight_zoom', 1.5))
            tk.Label(z_row, text="Zoom", bg=C["raised"], fg="#aaa", font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=4)
            tk.Scale(z_row, variable=self.ins_hl_zoom, from_=1.0, to=3.0, resolution=0.1,
                     orient=tk.HORIZONTAL, bg=C["raised"], fg="white", bd=0,
                     highlightthickness=0, troughcolor=C["border"]).pack(side=tk.LEFT, fill=tk.X, expand=True)

            def _on_hl_change(_e=None):
                item['_highlight_effect'] = eff_var.get()
                item['speed'] = self.ins_hl_speed.get()
                item['_highlight_zoom'] = self.ins_hl_zoom.get()
                self.timeline_dirty = True
                self.refresh_timeline()
            eff_var.trace_add("write", lambda *_: _on_hl_change())
            self.ins_hl_speed.trace_add("write", lambda *_: _on_hl_change())
            self.ins_hl_zoom.trace_add("write", lambda *_: _on_hl_change())

        tk.Button(f, text="🗑 Delete Selected Clip", bg=C["danger"], fg="white", font=("Segoe UI", 10, "bold"), bd=0, command=self.delete_selected).pack(fill=tk.X, padx=10, pady=5, ipady=5)

    def save_inspector(self):
        self.save_state()
        if self.selected_audio_idx is not None:
            i = self.bgm_tracks[self.selected_audio_idx]
            i['volume'] = self.ins_vol.get()
            i['start_offset'] = self.ins_offset.get()
            i['clip_start'] = self.ins_a_start.get()
            i['clip_end'] = self.ins_a_end.get()
        elif self.selected_idx is not None:
            i = self.media_queue[self.selected_idx]
            i['trans'] = self.ins_trans.get()

            # Save per-clip filter
            if hasattr(self, 'ins_filter_enabled'):
                i['filter_enabled'] = self.ins_filter_enabled.get()
                i['filter_style'] = self.ins_filter_style.get()
                i['filter_intensity'] = self.ins_filter_intensity.get()
                i['filter_warmth'] = self.ins_filter_warmth.get()
                i['filter_saturation'] = self.ins_filter_saturation.get()
                i['filter_fade_blacks'] = self.ins_filter_fade_blacks.get()

            if i['type'] == 'title':
                i['main_text'] = self.ins_mtxt.get()
                i['sub_text'] = self.ins_stxt.get()
                i['theme'] = self.ins_theme.get()
                i['value'] = self.ins_dur.get()
                if hasattr(self, 'ins_muted'):
                    i['muted'] = self.ins_muted.get()
                i['text'] = self.ins_txt.get()
                i['text_start'] = self.ins_t_start.get()
                i['text_end'] = self.ins_t_end.get()
                i['lt_style'] = self.ins_ltstyle.get()
            else:
                i['text'] = self.ins_txt.get()
                i['text_start'] = self.ins_t_start.get()
                i['text_end'] = self.ins_t_end.get()
                i['lt_style'] = self.ins_ltstyle.get()

                if i['type'] == 'video':
                    i['speed'] = self.ins_speed.get()
                    i['muted'] = getattr(self, 'ins_muted', tk.BooleanVar(value=False)).get()
                    i['volume'] = self.ins_vol.get()
                    i['clip_start'] = self.ins_c_start.get()
                    i['clip_end'] = self.ins_c_end.get()
                else:
                    i['value'] = self.ins_dur.get()

            base_path = i.get('path', '')
            keys_to_delete = [k for k in self._clip_cache.keys() if str(k).startswith(f"filmstrip_v4_{base_path}")]
            for k in keys_to_delete:
                del self._clip_cache[k]

        self.timeline_dirty = True
        self.update_global_preview()
        self.refresh_timeline()

    def _on_inspector_filter_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['filter_enabled'] = self.ins_filter_enabled.get()
        item['filter_style'] = self.ins_filter_style.get()
        item['filter_intensity'] = self.ins_filter_intensity.get()
        item['filter_warmth'] = self.ins_filter_warmth.get()
        item['filter_saturation'] = self.ins_filter_saturation.get()
        item['filter_fade_blacks'] = self.ins_filter_fade_blacks.get()
        self._debounced_preview(interactive=True)
