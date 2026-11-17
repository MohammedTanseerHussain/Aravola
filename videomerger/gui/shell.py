"""Top-level window, toolbar and panel construction.

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


class ShellMixin:
    """Top-level window, toolbar and panel construction."""

    def _build_ui(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure(".", background=C["panel"], foreground=C["text"])
        self.style.configure("TFrame", background=C["panel"])
        self.style.configure("TLabel", background=C["panel"], foreground=C["text"], font=("Segoe UI", 10))
        self.style.configure("Horizontal.TScale", background=C["panel"], troughcolor=C["raised"])

        self.style.configure("TCombobox",
                             fieldbackground="#2a2a2a",
                             background="#2a2a2a",
                             foreground="#ffffff",
                             selectbackground="#00c8ff",
                             selectforeground="#000000",
                             arrowcolor="#ffffff")
        self.style.map("TCombobox",
                       fieldbackground=[("readonly", "#2a2a2a")],
                       foreground=[("readonly", "#ffffff")])

        tb = tk.Frame(self.root, bg=C["surface"], height=44)
        tb.pack(side=tk.TOP, fill=tk.X)
        tb.pack_propagate(False)
        self._build_toolbar(tb)

        status_bar = tk.Frame(self.root, bg=C["surface"], height=22)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        status_bar.pack_propagate(False)
        self.status_label = tk.Label(status_bar, text="Ready.", bg=C["surface"],
                                     fg=C["accent3"], font=("Segoe UI", 9))
        self.status_label.pack(side=tk.LEFT, padx=10)

        self.master_canvas = tk.Canvas(self.root, bg=C["bg"], highlightthickness=0)
        self.master_scroll = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=self.master_canvas.yview)
        self.master_frame = tk.Frame(self.master_canvas, bg=C["bg"])

        self.master_canvas.bind("<Configure>", lambda e: self.master_canvas.itemconfig('master_win', width=e.width))
        self.master_frame.bind("<Configure>", lambda e: self.master_canvas.configure(scrollregion=self.master_canvas.bbox("all")))

        self.master_canvas.create_window((0, 0), window=self.master_frame, anchor="nw", tags="master_win")
        self.master_canvas.configure(yscrollcommand=self.master_scroll.set)

        self.master_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.master_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        def _on_master_mousewheel(event):
            self.master_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.master_canvas.bind("<Enter>", lambda e: self.master_canvas.bind_all("<MouseWheel>", _on_master_mousewheel))
        self.master_canvas.bind("<Leave>", lambda e: self.master_canvas.unbind_all("<MouseWheel>"))

        top_half = tk.Frame(self.master_frame, bg=C["bg"], height=420)
        top_half.pack(side=tk.TOP, fill=tk.X, expand=False, padx=3, pady=(3, 0))
        top_half.pack_propagate(False)

        # Adaptive panel widths based on window size
        win_w = getattr(self, '_win_w', 1500)
        left_w = 300 if win_w < 1200 else 340
        right_w = 280 if win_w < 1200 else 320

        left_panel = tk.Frame(top_half, bg=C["panel"], width=left_w)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 3))
        left_panel.pack_propagate(False)
        self._build_left_panel(left_panel)

        right_panel = tk.Frame(top_half, bg=C["panel"], width=right_w)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(3, 0))
        right_panel.pack_propagate(False)
        self._build_inspector_panel(right_panel)

        center_panel = tk.Frame(top_half, bg="#000000")
        center_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        center_panel.pack_propagate(False)
        self._build_player_panel(center_panel)

        bottom_half = tk.Frame(self.master_frame, bg=C["bg"], height=320)
        bottom_half.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=3, pady=3)
        self._build_timeline_panel(bottom_half)

    def _build_toolbar(self, tb):
        tk.Label(tb, text="🎬 NLE Studio", bg=C["surface"], fg=C["accent"], font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=8)

        tr = tk.Frame(tb, bg=C["surface"])
        tr.pack(side=tk.LEFT, expand=True)

        icon_btn(tr, "⏮", "Go to Start", self.go_to_start).pack(side=tk.LEFT, padx=2)
        icon_btn(tr, "◀◀", "Rewind 5s", self.rewind_5).pack(side=tk.LEFT, padx=2)

        self.play_btn = icon_btn(tr, "▶", "Play / Pause", self.toggle_play, bg=C["accent3"], fg=C["bg"])
        self.play_btn.pack(side=tk.LEFT, padx=4)

        icon_btn(tr, "▶▶", "Forward 5s", self.forward_5).pack(side=tk.LEFT, padx=2)
        icon_btn(tr, "⏭", "Go to End", self.go_to_end).pack(side=tk.LEFT, padx=2)

        self.timecode_var = tk.StringVar(value="00:00.00")
        tk.Label(tr, textvariable=self.timecode_var, bg=C["surface"], fg=C["accent"], font=("Courier", 12, "bold"), width=10).pack(side=tk.LEFT, padx=10)

        zf = tk.Frame(tr, bg=C["surface"])
        zf.pack(side=tk.LEFT, padx=8)

        tk.Label(zf, text="Zoom:", bg=C["surface"], fg=C["text_dim"], font=("Arial", 9)).pack(side=tk.LEFT)
        icon_btn(zf, "－", "Zoom Out", self.zoom_out).pack(side=tk.LEFT, padx=1)
        icon_btn(zf, "＋", "Zoom In", self.zoom_in).pack(side=tk.LEFT, padx=1)
        
        uf = tk.Frame(tr, bg=C["surface"])
        uf.pack(side=tk.LEFT, padx=15)
        icon_btn(uf, "↩", "Undo", self.undo).pack(side=tk.LEFT, padx=2)
        icon_btn(uf, "↪", "Redo", self.redo).pack(side=tk.LEFT, padx=2)

        self.export_btn = icon_btn(tb, "🚀 EXPORT", "Export video", self.start_merge_thread, bg=C["danger"], w=12)
        self.export_btn.pack(side=tk.RIGHT, padx=10, pady=6)

    def _build_left_panel(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill=tk.BOTH, expand=True)

        self.style.configure("TNotebook", background=C["panel"], borderwidth=0)
        self.style.configure("TNotebook.Tab", background=C["raised"], foreground="#cccccc",
                             padding=[12, 6], font=("Segoe UI", 7, "bold"))
        self.style.map("TNotebook.Tab", background=[("selected", C["surface"])],
                        foreground=[("selected", C["accent"])])

        f_media = tk.Frame(nb, bg=C["panel"])
        nb.add(f_media, text="Media")
        c_m, inner_media = create_scroll_canvas(f_media, C["panel"])

        btn_opts = {"bg": "#333", "fg": "white", "bd": 0, "font": ("Segoe UI", 10)}
        tk.Label(inner_media, text="MEDIA IMPORT", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 10, "bold")).pack(pady=10, anchor="w", padx=10)
        tk.Button(inner_media, text="➕ Add Video/Photo", command=self.add_media, **btn_opts).pack(fill=tk.X, padx=10, pady=5, ipady=4)
        tk.Button(inner_media, text="[ ] Add Placeholder", command=self.add_placeholder, **btn_opts).pack(fill=tk.X, padx=10, pady=5, ipady=4)

        tk.Label(inner_media, text="OUTPUT FORMAT", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 10, "bold")).pack(pady=(20, 5), anchor="w", padx=10)
        self.format_var = tk.StringVar(value="desktop")
        tk.Radiobutton(inner_media, text="16:9 Landscape", variable=self.format_var, value="desktop", bg=C["panel"], fg="white", selectcolor=C["raised"]).pack(anchor="w", padx=14)
        tk.Radiobutton(inner_media, text="9:16 Portrait", variable=self.format_var, value="mobile", bg=C["panel"], fg="white", selectcolor=C["raised"]).pack(anchor="w", padx=14)

        self.smart_fill_var = tk.BooleanVar(value=True)
        self.auto_rotate_var = tk.BooleanVar(value=True)
        tk.Checkbutton(inner_media, text="Smart Fill (Crop)", variable=self.smart_fill_var, bg=C["panel"], fg="white", selectcolor=C["raised"]).pack(anchor="w", pady=(5, 0), padx=14)
        tk.Checkbutton(inner_media, text="Auto-Rotate", variable=self.auto_rotate_var, bg=C["panel"], fg="white", selectcolor=C["raised"]).pack(anchor="w", pady=(0, 10), padx=14)

        f_audio = tk.Frame(nb, bg=C["panel"])
        nb.add(f_audio, text="Audio")
        c_a, inner_audio = create_scroll_canvas(f_audio, C["panel"])
        self.audio_scroll_canvas = c_a   # keep ref so _refresh_audio_list can update scrollregion

        tk.Label(inner_audio, text="BACKGROUND MUSIC", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 10, "bold")).pack(pady=10, anchor="w", padx=10)
        tk.Button(inner_audio, text="🎵 Add Audio Track", command=self.add_bgm_track, **btn_opts).pack(fill=tk.X, padx=10, pady=5, ipady=4)
        tk.Label(inner_audio, text="ACTIVE TRACKS", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 10, "bold")).pack(pady=(20, 5), anchor="w", padx=10)

        self.audio_list_frame = tk.Frame(inner_audio, bg=C["panel"])
        self.audio_list_frame.pack(fill=tk.X, anchor="n")

        f_temp = tk.Frame(nb, bg=C["panel"])
        nb.add(f_temp, text="Templates")
        c_t, inner_temp = create_scroll_canvas(f_temp, C["panel"])

        tk.Label(inner_temp, text="TITLE CARDS", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 10, "bold")).pack(pady=10, anchor="w", padx=10)
        tk.Button(inner_temp, text="✨ Add Empty Title Card", command=self.add_title_card, bg="#2196F3", fg="white", bd=0, font=("Segoe UI", 10)).pack(fill=tk.X, padx=10, pady=(0, 10), ipady=4)

        tk.Label(inner_temp, text="PRE-BUILT TEMPLATES", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 10, "bold")).pack(pady=(10, 5), anchor="w", padx=10)
        tk.Button(inner_temp, text="Deep Space + Aurora", bg="#3b0086", fg="white", bd=0, command=lambda: self.apply_template(1)).pack(fill=tk.X, padx=10, pady=3, ipady=3)
        tk.Button(inner_temp, text="Light Burst + Purple Box", bg="#c200ff", fg="white", bd=0, command=lambda: self.apply_template(2)).pack(fill=tk.X, padx=10, pady=3, ipady=3)
        tk.Button(inner_temp, text="Cinematic Flare + Magical", bg="#0088aa", fg="white", bd=0, command=lambda: self.apply_template(3)).pack(fill=tk.X, padx=10, pady=3, ipady=3)
        tk.Button(inner_temp, text="Headlight Flare + News", bg="#1a3a5c", fg="white", bd=0, command=lambda: self.apply_template(4)).pack(fill=tk.X, padx=10, pady=3, ipady=3)

        f_effect = tk.Frame(nb, bg=C["panel"])
        nb.add(f_effect, text="Effects")
        c_ef, inner_effect = create_scroll_canvas(f_effect, C["panel"])
        self._inner_effect = inner_effect

        tk.Label(inner_effect, text="GOLD OUTLINE EFFECT", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 10, "bold")).pack(pady=10, anchor="w", padx=10)

        self.effect_global_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(inner_effect, text="Enable Gold Outline", variable=self.effect_global_enabled, bg=C["panel"], fg="white", selectcolor=C["raised"], font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=5)

        tk.Label(inner_effect, text="", bg=C["panel"]).pack(pady=2)

        self._effect_clip_frame = tk.Frame(inner_effect, bg=C["panel"])
        self._effect_clip_frame.pack(fill=tk.X, padx=10)

        self._effect_no_clip_label = tk.Label(inner_effect, text="Select a clip to configure effect", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 9))
        self._effect_no_clip_label.pack(pady=20)

        self._effect_clip_name = tk.StringVar(value="")
        self._effect_enabled = tk.BooleanVar(value=False)
        self._effect_variation = tk.StringVar(value="ethereal")
        self._effect_opacity = tk.DoubleVar(value=1.0)
        self._effect_glow = tk.DoubleVar(value=1.0)
        self._effect_timing = tk.StringVar(value="full_clip")
        self._effect_start = tk.DoubleVar(value=0.0)
        self._effect_end = tk.DoubleVar(value=5.0)
        self._effect_selected_person = tk.IntVar(value=-1)
        self._detected_persons = []
        self._person_select_mode = False
        self._person_select_is_correction = False
        self._detected_persons_cache = {}
        self._tracking_preview_cache = {}
        self._show_outline_var = tk.BooleanVar(value=False)
        self._outline_preview_cache = {}

        # ─────────────────────────────────────────────
        #  FILTERS TAB  (Color Grading / LUT)
        # ─────────────────────────────────────────────
        f_filter = tk.Frame(nb, bg=C["panel"])
        nb.add(f_filter, text="Filters")
        c_fl, inner_filter = create_scroll_canvas(f_filter, C["panel"])
        self._inner_filter = inner_filter

        tk.Label(inner_filter, text="COLOR FILTERS", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 10, "bold")).pack(pady=10, anchor="w", padx=10)

        self._filter_global_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(inner_filter, text="Enable Color Filter", variable=self._filter_global_enabled,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       font=("Segoe UI", 9, "bold"),
                       command=self._on_filter_changed).pack(anchor="w", padx=10, pady=5)

        tk.Label(inner_filter, text="", bg=C["panel"]).pack(pady=2)

        fl_frame = tk.Frame(inner_filter, bg=C["panel"])
        fl_frame.pack(fill=tk.X, padx=10)

        tk.Label(fl_frame, text="SELECTED CLIP", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(5, 2))
        self._filter_clip_name = tk.StringVar(value="All clips (global)")
        tk.Label(fl_frame, textvariable=self._filter_clip_name, bg=C["panel"], fg=C["accent"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=5)

        self._filter_per_clip = tk.BooleanVar(value=False)
        tk.Checkbutton(fl_frame, text="Apply per-clip (overrides global)", variable=self._filter_per_clip,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       command=self._on_filter_changed).pack(anchor="w", pady=5)

        tk.Label(fl_frame, text="FILTER STYLE", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 2))
        self._filter_style = tk.StringVar(value="Cinematic Warm")
        filter_styles = ["Cinematic Warm", "Golden Hour", "Vintage Film", "Vintage Cam",
                         "BW Memories",
                         "Teal & Orange", "Bleach Bypass", "Cold Blue", "Desaturated", "High Contrast"]
        fl_combo = ttk.Combobox(fl_frame, textvariable=self._filter_style, values=filter_styles,
                                state="readonly", width=28)
        fl_combo.pack(fill=tk.X, padx=5, pady=2)
        fl_combo.bind("<<ComboboxSelected>>", lambda e: self._on_filter_changed())

        self._filter_desc = tk.Label(fl_frame, text="", bg=C["panel"], fg=C["text_dim"],
                                     font=("Segoe UI", 7), wraplength=280, justify=tk.LEFT)
        self._filter_desc.pack(anchor="w", padx=5, pady=(0, 5))
        self._update_filter_desc()

        tk.Label(fl_frame, text="INTENSITY", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 0))
        self._filter_intensity = tk.DoubleVar(value=1.0)
        tk.Scale(fl_frame, variable=self._filter_intensity, from_=0.0, to=1.0, resolution=0.05,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_filter_changed()).pack(fill=tk.X, padx=5)

        tk.Label(fl_frame, text="WARMTH", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 0))
        self._filter_warmth = tk.DoubleVar(value=0.5)
        tk.Scale(fl_frame, variable=self._filter_warmth, from_=0.0, to=1.0, resolution=0.05,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_filter_changed()).pack(fill=tk.X, padx=5)

        tk.Label(fl_frame, text="SATURATION", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 0))
        self._filter_saturation = tk.DoubleVar(value=1.0)
        tk.Scale(fl_frame, variable=self._filter_saturation, from_=0.0, to=2.0, resolution=0.05,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_filter_changed()).pack(fill=tk.X, padx=5)

        tk.Label(fl_frame, text="FADE BLACKS", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 0))
        self._filter_fade_blacks = tk.DoubleVar(value=0.15)
        tk.Scale(fl_frame, variable=self._filter_fade_blacks, from_=0.0, to=0.5, resolution=0.01,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_filter_changed()).pack(fill=tk.X, padx=5)

        fl_desc_frame = tk.Frame(fl_frame, bg=C["raised"], bd=0, relief="flat")
        fl_desc_frame.pack(fill=tk.X, padx=0, pady=(15, 5))
        fl_info = tk.Text(fl_desc_frame, height=6, width=30, bg=C["raised"], fg=C["text_dim"],
                          font=("Segoe UI", 8), wrap=tk.WORD, bd=0, relief="flat")
        fl_info.insert("1.0", """Cinematic Color Filters

Apply movie-style color grading to your clips. Inspired by real film LUTs.

Cinematic Warm — golden amber tone (like the reference image)
Adjust INTENSITY, WARMTH and SATURATION to taste.
Fade Blacks lifts shadows for a vintage film look.""")
        fl_info.config(state=tk.DISABLED)
        fl_info.pack(fill=tk.X, padx=6, pady=6)

        self._build_effect_controls(inner_effect)

    def _build_player_panel(self, parent):
        self.preview_frame = parent
        self.preview_label = tk.Label(parent, bg="#000000",
                                      text="NO MEDIA SELECTED",
                                      fg="#444444", font=("Segoe UI", 24, "bold"))
        self.preview_label.pack(fill=tk.BOTH, expand=True)

    def _build_inspector_panel(self, parent):
        tk.Label(parent, text="INSPECTOR PROPERTIES", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 10, "bold")).pack(pady=10, anchor="w", padx=10)
        self.insp_canvas, self.insp_inner = create_scroll_canvas(parent, C["panel"])

        self.ins_speed = tk.DoubleVar(value=1.0)
        self.ins_vol = tk.DoubleVar(value=1.0)
        self.ins_muted = tk.BooleanVar(value=False)
        self.ins_dur = tk.DoubleVar(value=5.0)
        self.ins_trans = tk.StringVar(value="Crossfade")

        self.ins_mtxt = tk.StringVar(value="")
        self.ins_stxt = tk.StringVar(value="")
        self.ins_theme = tk.StringVar(value="")

        self.ins_txt = tk.StringVar(value="")
        self.ins_t_start = tk.DoubleVar(value=0.0)
        self.ins_t_end = tk.DoubleVar(value=5.0)
        self.ins_ltstyle = tk.StringVar(value="")

        self.ins_offset = tk.DoubleVar(value=0.0)
        self.ins_a_start = tk.DoubleVar(value=0.0)
        self.ins_a_end = tk.DoubleVar(value=10.0)

        self.ins_c_start = tk.DoubleVar(value=0.0)
        self.ins_c_end = tk.DoubleVar(value=10.0)

        self.render_inspector()

    def _build_timeline_panel(self, parent):
        toolbar = tk.Frame(parent, bg="#111", height=35)
        toolbar.pack(fill=tk.X, side=tk.TOP)
        toolbar.pack_propagate(False)

        tk.Label(toolbar, text="TIMELINE (Dbl-Click: Vol | Right-Click: Del Pt | Ctrl+Click: Speech Ease)", bg="#111", fg="#666", font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=6)

        tk.Button(toolbar, text="✂️ Split at Playhead", bg=C["danger"], fg="white", bd=0, font=("Segoe UI", 8, "bold"), command=self.split_at_playhead).pack(side=tk.RIGHT, padx=3, pady=5)
        tk.Button(toolbar, text="✂️ Cut Region", bg=C["danger"], fg="white", bd=0, font=("Segoe UI", 8, "bold"), command=self.execute_cut).pack(side=tk.RIGHT, padx=3, pady=5)
        tk.Button(toolbar, text="🗑 Delete", bg="#b71c1c", fg="white", bd=0, font=("Segoe UI", 8, "bold"), command=self.delete_selected).pack(side=tk.RIGHT, padx=3, pady=5)
        tk.Button(toolbar, text="🔇 Mute", bg=C["clip_mute"], fg="white", bd=0, font=("Segoe UI", 8, "bold"), command=self.start_mute_draw_mode).pack(side=tk.RIGHT, padx=3, pady=5)
        tk.Button(toolbar, text="⚡ Highlight", bg="#00897B", fg="white", bd=0, font=("Segoe UI", 8, "bold"), command=self.start_highlight_draw_mode).pack(side=tk.RIGHT, padx=3, pady=5)

        # Handle mode toggle — right next to Highlight
        self._btn_trim_mode   = tk.Button(toolbar, text="◀▶ Trim",   bd=0, font=("Segoe UI", 8, "bold"),
                                          padx=4, pady=3, cursor="hand2", bg="#444", fg="white",
                                          command=lambda: self._set_handle_mode("trim"))
        self._btn_extend_mode = tk.Button(toolbar, text="⟺ Extend", bd=0, font=("Segoe UI", 8, "bold"),
                                          padx=4, pady=3, cursor="hand2", bg="#444", fg="white",
                                          command=lambda: self._set_handle_mode("extend"))
        self._btn_trim_mode.pack(side=tk.RIGHT, padx=2, pady=5)
        self._btn_extend_mode.pack(side=tk.RIGHT, padx=2, pady=5)
        self._update_handle_mode_buttons()

        tk.Button(toolbar, text="🔗 Speech Ease", bg="#1a8a5c", fg="white", bd=0, font=("Segoe UI", 8, "bold"), command=self.apply_speech_ease).pack(side=tk.RIGHT, padx=3, pady=5)

        self.tl_mode_label = tk.Label(toolbar, text="", bg="#111", fg=C["accent2"], font=("Segoe UI", 9, "bold"))
        self.tl_mode_label.pack(side=tk.LEFT, padx=10)

        self.timeline_canvas = tk.Canvas(parent, bg="#181818", highlightthickness=0, cursor="crosshair")
        self.timeline_scroll = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=self.timeline_canvas.xview)
        self.timeline_vscroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.timeline_canvas.yview)
        self.timeline_canvas.configure(
            xscrollcommand=self.timeline_scroll.set,
            yscrollcommand=self.timeline_vscroll.set
        )

        self.timeline_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.timeline_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.timeline_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Mousewheel scrolls vertically; Shift+wheel scrolls horizontally
        def _tl_mousewheel(event):
            self.timeline_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        def _tl_shift_wheel(event):
            self.timeline_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        self.timeline_canvas.bind("<Enter>", lambda e: (
            self.timeline_canvas.bind_all("<MouseWheel>", _tl_mousewheel),
            self.timeline_canvas.bind_all("<Shift-MouseWheel>", _tl_shift_wheel)
        ))
        self.timeline_canvas.bind("<Leave>", lambda e: (
            self.timeline_canvas.unbind_all("<MouseWheel>"),
            self.timeline_canvas.unbind_all("<Shift-MouseWheel>")
        ))

        self.timeline_canvas.bind("<ButtonPress-1>", self.on_tl_press)
        self.timeline_canvas.bind("<B1-Motion>", self.on_tl_drag)
        self.timeline_canvas.bind("<ButtonRelease-1>", self.on_tl_release)
        self.timeline_canvas.bind("<Double-Button-1>", self.on_tl_double_click)
        self.timeline_canvas.bind("<ButtonPress-3>", self.on_tl_right_click)
