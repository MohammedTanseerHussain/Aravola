"""Effect controls, filter controls and effect-tab refresh.

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


class EffectsUIMixin:
    """Effect controls, filter controls and effect-tab refresh."""

    def _build_effect_controls(self, parent):
        f = self._effect_clip_frame
        for w in f.winfo_children():
            w.destroy()

        tk.Label(f, text="SELECTED CLIP", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(5, 2))
        tk.Label(f, textvariable=self._effect_clip_name, bg=C["panel"], fg=C["accent"], font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=5)

        tk.Checkbutton(f, text="Enable on this clip", variable=self._effect_enabled, bg=C["panel"], fg="white", selectcolor=C["raised"], command=self._on_effect_setting_changed).pack(anchor="w", pady=5)

        tk.Label(f, text="EFFECT STYLE", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 2))
        var_names = list(self.EFFECT_VARIATIONS.values())
        var_keys = list(self.EFFECT_VARIATIONS.keys())
        self._variation_combo = ttk.Combobox(f, textvariable=self._effect_variation,
                                             values=var_keys, state="readonly", width=28)
        self._variation_combo.pack(fill=tk.X, padx=5, pady=2)
        self._variation_combo.bind("<<ComboboxSelected>>", lambda e: self._on_effect_setting_changed())

        self._variation_desc_label = tk.Label(f, text="", bg=C["panel"], fg=C["text_dim"],
                                              font=("Segoe UI", 7), wraplength=280, justify=tk.LEFT)
        self._variation_desc_label.pack(anchor="w", padx=5, pady=(0, 5))
        self._update_variation_desc()

        tk.Label(f, text="COLOR VARIATION", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 2))
        self._color_variation = tk.StringVar(value="Gold (Default)")
        self._color_combo = ttk.Combobox(f, textvariable=self._color_variation,
                                         values=list(self.COLOR_PALETTE.keys()), state="readonly", width=28)
        self._color_combo.pack(fill=tk.X, padx=5, pady=2)
        self._color_combo.bind("<<ComboboxSelected>>", lambda e: self._on_effect_setting_changed())

        self._person_frame = tk.Frame(f, bg=C["panel"])
        self._person_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
        tk.Label(self._person_frame, text="HIGHLIGHT PERSON", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._person_btn_frame = tk.Frame(self._person_frame, bg=C["panel"])
        self._person_btn_frame.pack(fill=tk.X, pady=2)
        self._person_status_label = tk.Label(self._person_frame, text="Click preview to select object",
                                             bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7))
        self._person_status_label.pack(anchor="w")
        if self._mp_available:
            mp_status = "MediaPipe: OK"
        else:
            mp_status = "MediaPipe: unavailable (using GrabCut fallback)"
        self._person_detection_label = tk.Label(self._person_frame, text=mp_status,
                                                bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 6))
        self._person_detection_label.pack(anchor="w")
        self._person_select_btn = tk.Button(self._person_frame, text="Click to Select Object",
                                            bg=C["accent"], fg="white", bd=0, font=("Segoe UI", 8, "bold"),
                                            command=self._start_person_select_mode, cursor="crosshair")
        self._person_select_btn.pack(fill=tk.X, pady=3)
        self._person_correct_btn = tk.Button(self._person_frame, text="Correct Position Here (this frame onward)",
                                             bg=C["accent"], fg="white", bd=0, font=("Segoe UI", 8, "bold"),
                                             command=self._start_person_correct_mode, cursor="crosshair")
        self._person_correct_btn.pack(fill=tk.X, pady=2)
        self._person_deselect_btn = tk.Button(self._person_frame, text="Deselect Person (Auto-Detect)",
                                               bg="#b71c1c", fg="white", bd=0, font=("Segoe UI", 8, "bold"),
                                               command=self._deselect_person)
        self._person_deselect_btn.pack(fill=tk.X, pady=2)

        self._outline_toggle_btn = tk.Button(self._person_frame, text="Show Outline (Preview Mask)",
                                               bg="#1a237e", fg="white", bd=0, font=("Segoe UI", 8, "bold"),
                                               command=self._toggle_outline_preview)
        self._outline_toggle_btn.pack(fill=tk.X, pady=2)

        self._mask_edit_frame = tk.Frame(self._person_frame, bg=C["panel"])
        self._mask_edit_frame.pack(fill=tk.X, pady=(6, 0))
        tk.Label(self._mask_edit_frame, text="ERASE / DRAW OUTLINE", bg=C["panel"], fg=C["accent4"], font=("Segoe UI", 8, "bold")).pack(anchor="w")

        self._mask_edit_active = False
        self._mask_brush_size = tk.IntVar(value=8)
        self._mask_erase_mode = tk.StringVar(value="erase")

        self._mask_edit_btn = tk.Button(self._mask_edit_frame, text="Start Editing Outline",
                                         bg="#e65100", fg="white", bd=0, font=("Segoe UI", 8, "bold"),
                                         command=self._toggle_mask_edit_mode)
        self._mask_edit_btn.pack(fill=tk.X, pady=2)

        brush_frame = tk.Frame(self._mask_edit_frame, bg=C["panel"])
        brush_frame.pack(fill=tk.X, pady=2)
        tk.Label(brush_frame, text="Brush Size:", bg=C["panel"], fg="white", font=("Segoe UI", 8)).pack(side=tk.LEFT)
        tk.Scale(brush_frame, variable=self._mask_brush_size, from_=1, to=100, resolution=1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], length=120).pack(side=tk.LEFT, fill=tk.X, expand=True)

        mode_frame = tk.Frame(self._mask_edit_frame, bg=C["panel"])
        mode_frame.pack(fill=tk.X, pady=2)
        tk.Radiobutton(mode_frame, text="Erase Outline", variable=self._mask_erase_mode, value="erase",
                        bg=C["panel"], fg="white", selectcolor=C["raised"]).pack(side=tk.LEFT, padx=2)
        tk.Radiobutton(mode_frame, text="Draw Outline", variable=self._mask_erase_mode, value="draw",
                        bg=C["panel"], fg="white", selectcolor=C["raised"]).pack(side=tk.LEFT, padx=2)

        self._mask_clear_btn = tk.Button(self._mask_edit_frame, text="Clear All Edits",
                                          bg="#4a148c", fg="white", bd=0, font=("Segoe UI", 8),
                                          command=self._clear_mask_painting)
        self._mask_clear_btn.pack(fill=tk.X, pady=2)

        tk.Label(f, text="INTENSITY (Light Strength)", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 0))
        tk.Scale(f, variable=self._effect_opacity, from_=0.0, to=1.0, resolution=0.05, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0, troughcolor=C["border"], command=lambda v: self._on_effect_setting_changed()).pack(fill=tk.X, padx=5)

        tk.Label(f, text="GLOW (Rim & Ray Brightness)", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(10, 0))
        tk.Scale(f, variable=self._effect_glow, from_=0.0, to=1.0, resolution=0.05, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0, troughcolor=C["border"], command=lambda v: self._on_effect_setting_changed()).pack(fill=tk.X, padx=5)

        tk.Label(f, text="TIMING", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(10, 2))
        tk.Radiobutton(f, text="Full Clip Duration", variable=self._effect_timing, value="full_clip", bg=C["panel"], fg="white", selectcolor=C["raised"], command=self._on_effect_timing_changed).pack(anchor="w", padx=5)
        tk.Radiobutton(f, text="Custom Timeframe", variable=self._effect_timing, value="custom", bg=C["panel"], fg="white", selectcolor=C["raised"], command=self._on_effect_timing_changed).pack(anchor="w", padx=5)

        self._effect_custom_frame = tk.Frame(f, bg=C["panel"])
        self._effect_custom_frame.pack(fill=tk.X, padx=5, pady=(5, 0))

        tk.Label(self._effect_custom_frame, text="Start (s):", bg=C["panel"], fg="white", font=("Segoe UI", 8)).pack(anchor="w")
        tk.Scale(self._effect_custom_frame, variable=self._effect_start, from_=0.0, to=60.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0, troughcolor=C["border"], command=lambda v: self._on_effect_setting_changed()).pack(fill=tk.X)

        tk.Label(self._effect_custom_frame, text="End (s):", bg=C["panel"], fg="white", font=("Segoe UI", 8)).pack(anchor="w")
        tk.Scale(self._effect_custom_frame, variable=self._effect_end, from_=0.0, to=60.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0, troughcolor=C["border"], command=lambda v: self._on_effect_setting_changed()).pack(fill=tk.X)

        self._on_effect_timing_changed()

        desc_frame = tk.Frame(f, bg=C["raised"], bd=0, relief="flat")
        desc_frame.pack(fill=tk.X, padx=0, pady=(15, 5))
        desc = tk.Text(desc_frame, height=7, width=30, bg=C["raised"], fg=C["text_dim"], font=("Segoe UI", 8), wrap=tk.WORD, bd=0, relief="flat")
        desc.insert("1.0", """Gold Outline Effect — 5 Styles × 31 Colors

Each style creates a shiny, radiating gold outline around the subject with unique ray patterns and glow intensity. Use Brilliance for HDR heavenly backlit glow with volumetric rays.

COLOR VARIATION — Pick from white, orange, pink-purple, yellow, neon, or gold palettes
INTENSITY — Overall effect strength
GLOW — Outline & ray brightness

Subject outline is traced from actual edges (no blur).""")
        desc.config(state=tk.DISABLED)
        desc.pack(fill=tk.X, padx=6, pady=6)

        # ─────────────────────────────────────────────
        # KEN BURNS EFFECT (camera motion)
        # ─────────────────────────────────────────────
        kb_sep = tk.Frame(f, bg=C["panel"], height=2, bd=0, highlightbackground=C["border"], highlightthickness=1)
        kb_sep.pack(fill=tk.X, padx=5, pady=(20, 5))
        tk.Label(f, text="📷 KEN BURNS EFFECT", bg=C["panel"], fg=C["accent4"], font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5)

        self._kb_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="Enable Ken Burns (Camera Pan & Zoom)", variable=self._kb_enabled,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       command=self._on_kb_changed).pack(anchor="w", padx=5, pady=5)

        self._kb_zoom_in = tk.DoubleVar(value=1.0)
        self._kb_zoom_out = tk.DoubleVar(value=1.3)
        self._kb_pan_x = tk.DoubleVar(value=0.0)
        self._kb_pan_y = tk.DoubleVar(value=0.0)

        tk.Label(f, text="Zoom Start:", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 8)).pack(anchor="w", padx=10)
        tk.Scale(f, variable=self._kb_zoom_in, from_=1.0, to=3.0, resolution=0.05,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_kb_changed()).pack(fill=tk.X, padx=10)

        tk.Label(f, text="Zoom End:", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 8)).pack(anchor="w", padx=10)
        tk.Scale(f, variable=self._kb_zoom_out, from_=1.0, to=3.0, resolution=0.05,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_kb_changed()).pack(fill=tk.X, padx=10)

        tk.Label(f, text="Pan Horizontal:", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 8)).pack(anchor="w", padx=10)
        tk.Scale(f, variable=self._kb_pan_x, from_=-1.0, to=1.0, resolution=0.05,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_kb_changed()).pack(fill=tk.X, padx=10)

        tk.Label(f, text="Pan Vertical:", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 8)).pack(anchor="w", padx=10)
        tk.Scale(f, variable=self._kb_pan_y, from_=-1.0, to=1.0, resolution=0.05,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_kb_changed()).pack(fill=tk.X, padx=10)

        # ─────────────────────────────────────────────
        # THUG LIFE EFFECT (sunglasses + gold chain)
        # ─────────────────────────────────────────────
        tl_sep = tk.Frame(f, bg=C["panel"], height=2, bd=0, highlightbackground=C["border"], highlightthickness=1)
        tl_sep.pack(fill=tk.X, padx=5, pady=(20, 5))
        tk.Label(f, text="THUG LIFE EFFECT", bg=C["panel"], fg=C["accent4"], font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5)

        self._thug_life_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="Enable Thug Life (Sunglasses + Chain)", variable=self._thug_life_enabled,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       command=self._on_thug_life_changed).pack(anchor="w", padx=5, pady=5)

        tk.Label(f, text="Animated sunglasses rotate and fly onto the detected face, while a gold chain slides in around the neck. Uses face detection for precise alignment. Select a person below for best results.",
                 bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), wraplength=280, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 8))

        # ── Accessory style / cap / entry-animation options ──
        thug_opts_frame = tk.Frame(f, bg=C["panel"])
        thug_opts_frame.pack(fill=tk.X, padx=10, pady=(0, 8))

        tk.Label(thug_opts_frame, text="ACCESSORY STYLE", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._thug_style = tk.StringVar(value="realistic")
        thug_style_combo = ttk.Combobox(thug_opts_frame, textvariable=self._thug_style,
                                         values=["pixel", "realistic"], state="readonly", width=26)
        thug_style_combo.pack(fill=tk.X, pady=(0, 4))
        thug_style_combo.bind("<<ComboboxSelected>>", lambda e: self._on_thug_life_changed())

        self._thug_cap_enabled = tk.BooleanVar(value=True)
        tk.Checkbutton(thug_opts_frame, text="Also add a cap", variable=self._thug_cap_enabled,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       command=self._on_thug_life_changed).pack(anchor="w", pady=(0, 4))

        tk.Label(thug_opts_frame, text="ENTRY ANIMATION", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._thug_entry = tk.StringVar(value="top")
        thug_entry_combo = ttk.Combobox(thug_opts_frame, textvariable=self._thug_entry,
                                         values=["top", "left", "right", "bottom", "rush", "bounce"],
                                         state="readonly", width=26)
        thug_entry_combo.pack(fill=tk.X, pady=(0, 2))
        thug_entry_combo.bind("<<ComboboxSelected>>", lambda e: self._on_thug_life_changed())

        thug_person_frame = tk.Frame(f, bg=C["panel"])
        thug_person_frame.pack(fill=tk.X, padx=10, pady=(0, 8))
        tk.Label(thug_person_frame, text="SELECT PERSON (multiple people in frame?)", bg=C["panel"],
                 fg=C["text_dim"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._thug_person_status_label = tk.Label(thug_person_frame, text="Auto-detect (closest to center)",
                                                    bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7))
        self._thug_person_status_label.pack(anchor="w")
        thug_person_btns = tk.Frame(thug_person_frame, bg=C["panel"])
        thug_person_btns.pack(fill=tk.X, pady=2)
        tk.Button(thug_person_btns, text="Click to Select Object", bg=C["accent"], fg="white", bd=0,
                  font=("Segoe UI", 8, "bold"), command=self._start_person_select_mode,
                  cursor="crosshair").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        tk.Button(thug_person_btns, text="Correct Here", bg=C["accent"], fg="white", bd=0,
                  font=("Segoe UI", 8, "bold"), command=self._start_person_correct_mode,
                  cursor="crosshair").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        tk.Button(thug_person_btns, text="Auto-Detect", bg="#b71c1c", fg="white", bd=0,
                  font=("Segoe UI", 8, "bold"), command=self._deselect_person).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
        if not hasattr(self, '_thug_trace_bound'):
            self._effect_selected_person.trace_add('write', lambda *a: self._refresh_thug_person_label())
            self._thug_trace_bound = True
        self._refresh_thug_person_label()

        # ── Manual position/size/rotation/flip adjustment ──
        thug_adjust_frame = tk.Frame(f, bg=C["panel"])
        thug_adjust_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        tk.Label(thug_adjust_frame, text="ADJUST ACCESSORY (fine-tune position/size)", bg=C["panel"],
                 fg=C["text_dim"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(thug_adjust_frame,
                 text="Adjustments are saved with this clip and reapplied on top of auto-detection every time.",
                 bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), wraplength=280,
                 justify=tk.LEFT).pack(anchor="w", pady=(0, 4))

        target_row = tk.Frame(thug_adjust_frame, bg=C["panel"])
        target_row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(target_row, text="Editing:", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7)).pack(side=tk.LEFT)
        self._thug_adjust_target = tk.StringVar(value="glasses")
        thug_target_combo = ttk.Combobox(target_row, textvariable=self._thug_adjust_target,
                                          values=["glasses", "chain", "cap"], state="readonly", width=12)
        thug_target_combo.pack(side=tk.LEFT, padx=(4, 0))

        move_row = tk.Frame(thug_adjust_frame, bg=C["panel"])
        move_row.pack(fill=tk.X, pady=2)
        tk.Label(move_row, text="Move:", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7),
                 width=6, anchor="w").pack(side=tk.LEFT)
        for lbl, kw in [("←", {"dx": -5}), ("→", {"dx": 5}), ("↑", {"dy": -5}), ("↓", {"dy": 5})]:
            tk.Button(move_row, text=lbl, width=3, bg=C["raised"], fg="white", bd=0,
                      command=lambda kw=kw: self._nudge_thug_accessory(**kw)).pack(side=tk.LEFT, padx=1)

        scale_row = tk.Frame(thug_adjust_frame, bg=C["panel"])
        scale_row.pack(fill=tk.X, pady=2)
        tk.Label(scale_row, text="Size:", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7),
                 width=6, anchor="w").pack(side=tk.LEFT)
        tk.Button(scale_row, text="−", width=3, bg=C["raised"], fg="white", bd=0,
                  command=lambda: self._nudge_thug_accessory(scale_mult=0.92)).pack(side=tk.LEFT, padx=1)
        tk.Button(scale_row, text="+", width=3, bg=C["raised"], fg="white", bd=0,
                  command=lambda: self._nudge_thug_accessory(scale_mult=1.08)).pack(side=tk.LEFT, padx=1)
        tk.Label(scale_row, text="Rotate:", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 7)).pack(side=tk.LEFT, padx=(10, 0))
        tk.Button(scale_row, text="↺", width=3, bg=C["raised"], fg="white", bd=0,
                  command=lambda: self._nudge_thug_accessory(rotate_delta=-5)).pack(side=tk.LEFT, padx=1)
        tk.Button(scale_row, text="↻", width=3, bg=C["raised"], fg="white", bd=0,
                  command=lambda: self._nudge_thug_accessory(rotate_delta=5)).pack(side=tk.LEFT, padx=1)

        flip_row = tk.Frame(thug_adjust_frame, bg=C["panel"])
        flip_row.pack(fill=tk.X, pady=2)
        tk.Button(flip_row, text="Flip ↔", bg=C["raised"], fg="white", bd=0, font=("Segoe UI", 7),
                  command=lambda: self._nudge_thug_accessory(toggle_flip_h=True)).pack(side=tk.LEFT, padx=1)
        tk.Button(flip_row, text="Flip ↕", bg=C["raised"], fg="white", bd=0, font=("Segoe UI", 7),
                  command=lambda: self._nudge_thug_accessory(toggle_flip_v=True)).pack(side=tk.LEFT, padx=1)
        tk.Button(flip_row, text="Reset This Accessory", bg="#b71c1c", fg="white", bd=0, font=("Segoe UI", 7),
                  command=self._reset_thug_accessory).pack(side=tk.LEFT, padx=(10, 0))

        # FILM BURN OVERLAY EFFECT
        # ─────────────────────────────────────────────
        fb_sep = tk.Frame(f, bg=C["panel"], height=2, bd=0, highlightbackground=C["border"], highlightthickness=1)
        fb_sep.pack(fill=tk.X, padx=5, pady=(20, 5))
        tk.Label(f, text="FILM BURN OVERLAY", bg=C["panel"], fg="#FF6D00", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5)

        self._film_burn_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="Enable Film Burn (Scorching Light Flares)", variable=self._film_burn_enabled,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       command=self._on_film_burn_changed).pack(anchor="w", padx=5, pady=5)

        tk.Label(f, text="Scorching orange-red light flares sweep across the frame like vintage film stock burning. Bright animated flares move over the image/video.",
                 bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), wraplength=280, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 8))

        fb_opts = tk.Frame(f, bg=C["panel"])
        fb_opts.pack(fill=tk.X, padx=10, pady=(0, 8))

        tk.Label(fb_opts, text="INTENSITY", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._film_burn_intensity = tk.DoubleVar(value=1.0)
        tk.Scale(fb_opts, variable=self._film_burn_intensity, from_=0.1, to=2.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_film_burn_changed()).pack(fill=tk.X, padx=5)

        tk.Label(fb_opts, text="SPEED", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._film_burn_speed = tk.DoubleVar(value=1.0)
        tk.Scale(fb_opts, variable=self._film_burn_speed, from_=0.2, to=3.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_film_burn_changed()).pack(fill=tk.X, padx=5)

        # SUN GLARE EFFECT
        # ─────────────────────────────────────────────
        sg_sep = tk.Frame(f, bg=C["panel"], height=2, bd=0, highlightbackground=C["border"], highlightthickness=1)
        sg_sep.pack(fill=tk.X, padx=5, pady=(20, 5))
        tk.Label(f, text="SUN GLARE", bg=C["panel"], fg="#FFC107", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5)

        self._sun_glare_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="Enable Sun Glare (Cinematic Lens Flare)", variable=self._sun_glare_enabled,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       command=self._on_sun_glare_changed).pack(anchor="w", padx=5, pady=5)

        tk.Label(f, text="A bright sun with radiating rays sits in a corner, trailing a diagonal chain of soft hexagonal lens flares across the frame — warm, cinematic glare that works the same on images and video.",
                 bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), wraplength=280, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 8))

        sg_var_frame = tk.Frame(f, bg=C["panel"])
        sg_var_frame.pack(fill=tk.X, padx=10, pady=(0, 8))
        tk.Label(sg_var_frame, text="VARIATION", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._sun_glare_variation = tk.StringVar(value="Cinematic")
        sg_var_combo = ttk.Combobox(sg_var_frame, textvariable=self._sun_glare_variation,
                                      values=["Cinematic", "Golden Hour", "Natural", "Sky Burst"], state="readonly", width=16)
        sg_var_combo.pack(anchor="w", pady=(0, 2))
        sg_var_combo.bind("<<ComboboxSelected>>", lambda e: self._on_sun_glare_changed())

        sg_opts = tk.Frame(f, bg=C["panel"])
        sg_opts.pack(fill=tk.X, padx=10, pady=(0, 8))

        tk.Label(sg_opts, text="SUN POSITION", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._sun_glare_position = tk.StringVar(value="Top Left")
        sg_pos_combo = ttk.Combobox(sg_opts, textvariable=self._sun_glare_position, state="readonly",
                                     values=["Top Left", "Top Right", "Bottom Left", "Bottom Right", "Center"], width=16)
        sg_pos_combo.pack(anchor="w", pady=(0, 6))
        sg_pos_combo.bind("<<ComboboxSelected>>", lambda e: self._on_sun_glare_changed())

        tk.Label(sg_opts, text="INTENSITY", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._sun_glare_intensity = tk.DoubleVar(value=1.0)
        tk.Scale(sg_opts, variable=self._sun_glare_intensity, from_=0.1, to=2.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_sun_glare_changed()).pack(fill=tk.X, padx=5)

        tk.Label(sg_opts, text="SIZE", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._sun_glare_size = tk.DoubleVar(value=1.0)
        tk.Scale(sg_opts, variable=self._sun_glare_size, from_=0.4, to=2.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_sun_glare_changed()).pack(fill=tk.X, padx=5)

        tk.Label(sg_opts, text="SHIMMER SPEED (subtle animation on video, 0 = static)", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._sun_glare_speed = tk.DoubleVar(value=0.3)
        tk.Scale(sg_opts, variable=self._sun_glare_speed, from_=0.0, to=2.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_sun_glare_changed()).pack(fill=tk.X, padx=5)

        # ─────────────────────────────────────────────
        # X FLARE EFFECT (anamorphic cross flare)
        # ─────────────────────────────────────────────
        xf_sep = tk.Frame(f, bg=C["panel"], height=2, bd=0, highlightbackground=C["border"], highlightthickness=1)
        xf_sep.pack(fill=tk.X, padx=5, pady=(20, 5))
        tk.Label(f, text="X FLARE", bg=C["panel"], fg="#80DEEA", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5)

        self._x_flare_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="Enable X Flare (Anamorphic Cross)", variable=self._x_flare_enabled,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       command=self._on_x_flare_changed).pack(anchor="w", padx=5, pady=5)

        tk.Label(f, text="Bright anamorphic X-shaped cross flare with rays extending from the center. Common in concert and stage lighting.",
                 bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), wraplength=280, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 8))

        xf_opts = tk.Frame(f, bg=C["panel"])
        xf_opts.pack(fill=tk.X, padx=10, pady=(0, 8))

        tk.Label(xf_opts, text="VARIATION", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._x_flare_variation = tk.StringVar(value="Blue White")
        xf_var_combo = ttk.Combobox(xf_opts, textvariable=self._x_flare_variation,
                                    values=["Blue White", "Purple Haze", "Golden Cross", "Ice White"], state="readonly", width=16)
        xf_var_combo.pack(anchor="w", pady=(0, 6))
        xf_var_combo.bind("<<ComboboxSelected>>", lambda e: self._on_x_flare_changed())

        tk.Label(xf_opts, text="POSITION", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._x_flare_position = tk.StringVar(value="Center")
        xf_pos_combo = ttk.Combobox(xf_opts, textvariable=self._x_flare_position, state="readonly",
                                    values=["Top Left", "Top Right", "Bottom Left", "Bottom Right", "Center"], width=16)
        xf_pos_combo.pack(anchor="w", pady=(0, 6))
        xf_pos_combo.bind("<<ComboboxSelected>>", lambda e: self._on_x_flare_changed())

        tk.Label(xf_opts, text="INTENSITY", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._x_flare_intensity = tk.DoubleVar(value=1.0)
        tk.Scale(xf_opts, variable=self._x_flare_intensity, from_=0.1, to=2.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_x_flare_changed()).pack(fill=tk.X, padx=5)

        tk.Label(xf_opts, text="SIZE", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._x_flare_size = tk.DoubleVar(value=1.0)
        tk.Scale(xf_opts, variable=self._x_flare_size, from_=0.3, to=2.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_x_flare_changed()).pack(fill=tk.X, padx=5)

        tk.Label(xf_opts, text="SHIMMER (animation speed, 0 = static)", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._x_flare_speed = tk.DoubleVar(value=0.3)
        tk.Scale(xf_opts, variable=self._x_flare_speed, from_=0.0, to=2.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_x_flare_changed()).pack(fill=tk.X, padx=5)

        # ─────────────────────────────────────────────
        # LIGHT FLASH EFFECT (camera flash X-pattern stars)
        # ─────────────────────────────────────────────
        lf_sep = tk.Frame(f, bg=C["panel"], height=2, bd=0, highlightbackground=C["border"], highlightthickness=1)
        lf_sep.pack(fill=tk.X, padx=5, pady=(20, 5))
        tk.Label(f, text="LIGHT FLASH", bg=C["panel"], fg="#FFFFFF", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5)

        self._light_flash_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="Enable Light Flash (Camera Flash X-Stars)", variable=self._light_flash_enabled,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       command=self._on_light_flash_changed).pack(anchor="w", padx=5, pady=5)

        tk.Label(f, text="Multiple camera-flash stars twinkle in an X formation, flickering on and off like paparazzi going off behind the subject. Bright starbursts cascade along the X arms with rapid flash pulses.",
                 bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), wraplength=280, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 8))

        lf_opts = tk.Frame(f, bg=C["panel"])
        lf_opts.pack(fill=tk.X, padx=10, pady=(0, 8))

        tk.Label(lf_opts, text="VARIATION", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._light_flash_variation = tk.StringVar(value="White Flash")
        lf_var_combo = ttk.Combobox(lf_opts, textvariable=self._light_flash_variation,
                                     values=["White Flash", "Warm Paparazzi", "Cool Studio", "Neon Burst", "Golden Gala"],
                                     state="readonly", width=16)
        lf_var_combo.pack(anchor="w", pady=(0, 6))
        lf_var_combo.bind("<<ComboboxSelected>>", lambda e: self._on_light_flash_changed())

        tk.Label(lf_opts, text="POSITION", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._light_flash_position = tk.StringVar(value="Center")
        lf_pos_combo = ttk.Combobox(lf_opts, textvariable=self._light_flash_position, state="readonly",
                                     values=["Center", "Top Left", "Top Right", "Bottom Left", "Bottom Right",
                                             "Diagonal TL→BR", "Diagonal BL→TR", "Full Image"], width=16)
        lf_pos_combo.pack(anchor="w", pady=(0, 6))
        lf_pos_combo.bind("<<ComboboxSelected>>", lambda e: self._on_light_flash_changed())

        tk.Label(lf_opts, text="INTENSITY", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._light_flash_intensity = tk.DoubleVar(value=1.0)
        tk.Scale(lf_opts, variable=self._light_flash_intensity, from_=0.1, to=2.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_light_flash_changed()).pack(fill=tk.X, padx=5)

        tk.Label(lf_opts, text="SIZE", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._light_flash_size = tk.DoubleVar(value=1.0)
        tk.Scale(lf_opts, variable=self._light_flash_size, from_=0.3, to=2.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_light_flash_changed()).pack(fill=tk.X, padx=5)

        tk.Label(lf_opts, text="FLASH SPEED", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._light_flash_speed = tk.DoubleVar(value=1.0)
        tk.Scale(lf_opts, variable=self._light_flash_speed, from_=0.2, to=3.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_light_flash_changed()).pack(fill=tk.X, padx=5)

        tk.Label(lf_opts, text="STAR DENSITY (number of flash points along X)", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._light_flash_density = tk.IntVar(value=6)
        tk.Scale(lf_opts, variable=self._light_flash_density, from_=3, to=20, resolution=1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_light_flash_changed()).pack(fill=tk.X, padx=5)

        # ─────────────────────────────────────────────
        # CANOPY EFFECT (fog + volumetric light rays)
        # ─────────────────────────────────────────────
        cn_sep = tk.Frame(f, bg=C["panel"], height=2, bd=0, highlightbackground=C["border"], highlightthickness=1)
        cn_sep.pack(fill=tk.X, padx=5, pady=(20, 5))
        tk.Label(f, text="CANOPY EFFECT", bg=C["panel"], fg="#B0BEC5", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5)

        self._canopy_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="Enable Canopy (Fog + Volumetric Rays)", variable=self._canopy_enabled,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       command=self._on_canopy_changed).pack(anchor="w", padx=5, pady=5)

        tk.Label(f, text="Dense fog banks at the bottom with soft light rays streaming from behind and above the subject. Natural canopy atmosphere with volumetric god rays piercing through the mist.",
                 bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), wraplength=280, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 8))

        cn_opts = tk.Frame(f, bg=C["panel"])
        cn_opts.pack(fill=tk.X, padx=10, pady=(0, 8))

        tk.Label(cn_opts, text="LIGHT STYLE", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._canopy_light_style = tk.StringVar(value="Soft Atmosphere")
        cn_style_combo = ttk.Combobox(cn_opts, textvariable=self._canopy_light_style,
                                       values=["Soft Atmosphere", "Forest Rays"],
                                       state="readonly", width=16)
        cn_style_combo.pack(anchor="w", pady=(0, 6))
        cn_style_combo.bind("<<ComboboxSelected>>", lambda e: self._on_canopy_changed())

        tk.Label(cn_opts, text="LIGHT DIRECTION", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._canopy_light_dir = tk.StringVar(value="Top Left")
        cn_dir_combo = ttk.Combobox(cn_opts, textvariable=self._canopy_light_dir,
                                      values=["Top Left", "Top Right", "Top Center", "Behind", "Side Left", "Side Right"],
                                      state="readonly", width=16)
        cn_dir_combo.pack(anchor="w", pady=(0, 6))
        cn_dir_combo.bind("<<ComboboxSelected>>", lambda e: self._on_canopy_changed())

        tk.Label(cn_opts, text="FOG DENSITY", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._canopy_fog_density = tk.DoubleVar(value=0.7)
        tk.Scale(cn_opts, variable=self._canopy_fog_density, from_=0.1, to=2.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_canopy_changed()).pack(fill=tk.X, padx=5)

        tk.Label(cn_opts, text="FOG HEIGHT (how high the fog rises)", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._canopy_fog_height = tk.DoubleVar(value=0.5)
        tk.Scale(cn_opts, variable=self._canopy_fog_height, from_=0.2, to=0.9, resolution=0.05,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_canopy_changed()).pack(fill=tk.X, padx=5)

        tk.Label(cn_opts, text="RAY INTENSITY", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._canopy_ray_intensity = tk.DoubleVar(value=1.0)
        tk.Scale(cn_opts, variable=self._canopy_ray_intensity, from_=0.0, to=3.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_canopy_changed()).pack(fill=tk.X, padx=5)

        tk.Label(cn_opts, text="RAY WIDTH (spread of each ray)", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._canopy_ray_width = tk.DoubleVar(value=1.0)
        tk.Scale(cn_opts, variable=self._canopy_ray_width, from_=0.3, to=2.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_canopy_changed()).pack(fill=tk.X, padx=5)

        tk.Label(cn_opts, text="WARMTH (color temperature)", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._canopy_warmth = tk.DoubleVar(value=0.7)
        tk.Scale(cn_opts, variable=self._canopy_warmth, from_=0.0, to=1.0, resolution=0.05,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_canopy_changed()).pack(fill=tk.X, padx=5)

        tk.Label(cn_opts, text="SHIMMER (subtle flicker, 0 = static)", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._canopy_shimmer = tk.DoubleVar(value=0.3)
        tk.Scale(cn_opts, variable=self._canopy_shimmer, from_=0.0, to=1.0, resolution=0.05,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_canopy_changed()).pack(fill=tk.X, padx=5)

        self._canopy_show_light_source = tk.BooleanVar(value=True)
        tk.Checkbutton(cn_opts, text="Show Light Source (glow at origin)", variable=self._canopy_show_light_source,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       command=self._on_canopy_changed).pack(anchor="w", padx=5, pady=(6, 0))

        # ─────────────────────────────────────────────
        # 3D TEXT TRACKING EFFECT
        # ─────────────────────────────────────────────
        tt_sep = tk.Frame(f, bg=C["panel"], height=2, bd=0, highlightbackground=C["border"], highlightthickness=1)
        tt_sep.pack(fill=tk.X, padx=5, pady=(20, 5))
        tk.Label(f, text="3D TEXT TRACKING", bg=C["panel"], fg="#FF6F00", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5)

        self._3d_text_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="Enable 3D Text Tracking", variable=self._3d_text_enabled,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       command=self._on_3d_text_tracking_changed).pack(anchor="w", padx=5, pady=5)

        tk.Label(f, text="Places a fixed-size 3D text marker at a spot in the video, AR-doodle "
                         "style. Use the sections below to time and position it.",
                 bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), wraplength=280, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 6))

        tt_opts = tk.Frame(f, bg=C["panel"])
        tt_opts.pack(fill=tk.X, padx=10, pady=(0, 8))

        tk.Label(tt_opts, text="TEXT CONTENT", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._3d_text_content = tk.StringVar(value="TRACKING")
        tt_text_entry = tk.Entry(tt_opts, textvariable=self._3d_text_content, bg="#2a2a2a", fg="white",
                                 insertbackground="white", font=("Segoe UI", 10, "bold"), bd=0)
        tt_text_entry.pack(fill=tk.X, pady=(0, 6))
        tt_text_entry.bind("<KeyRelease>", lambda e: self._on_3d_text_tracking_changed())

        tk.Label(tt_opts, text="TEXT COLOR", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._3d_text_color = tk.StringVar(value="Orange")
        tt_color_combo = ttk.Combobox(tt_opts, textvariable=self._3d_text_color,
                                       values=["Orange", "White", "Gold", "Red", "Blue", "Cyan", "Green", "Purple", "Black"],
                                       state="readonly", width=26)
        tt_color_combo.pack(anchor="w", pady=(0, 6))
        tt_color_combo.bind("<<ComboboxSelected>>", lambda e: self._on_3d_text_tracking_changed())

        tk.Label(tt_opts, text="DEPTH (Extrusion Thickness)", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._3d_text_depth = tk.DoubleVar(value=0.4)
        tk.Scale(tt_opts, variable=self._3d_text_depth, from_=0.0, to=2.0, resolution=0.05,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_3d_text_tracking_changed()).pack(fill=tk.X, padx=5)

        tk.Label(tt_opts, text="SHADOW OPACITY", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._3d_text_shadow = tk.DoubleVar(value=0.5)
        tk.Scale(tt_opts, variable=self._3d_text_shadow, from_=0.0, to=1.0, resolution=0.05,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_3d_text_tracking_changed()).pack(fill=tk.X, padx=5)

        tk.Label(tt_opts, text="TEXTURE STYLE", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._3d_text_style = tk.StringVar(value="Solid Matte")
        tt_style_combo = ttk.Combobox(tt_opts, textvariable=self._3d_text_style,
                                       values=["Solid Matte", "Metallic", "Glossy", "Glow"],
                                       state="readonly", width=26)
        tt_style_combo.pack(anchor="w", pady=(0, 2))
        tt_style_combo.bind("<<ComboboxSelected>>", lambda e: self._on_3d_text_tracking_changed())

        tk.Label(tt_opts, text="CAMERA SPEED (forward Z movement)", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 0))
        tk.Label(tt_opts, text="Virtual camera moves toward the text in 3D.\n0 = text stays fixed on screen.",
                 bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), justify=tk.LEFT,
                 wraplength=260).pack(anchor="w", pady=(0, 2))
        self._3d_cam_speed = tk.DoubleVar(value=8.0)
        tk.Scale(tt_opts, variable=self._3d_cam_speed, from_=0.0, to=40.0, resolution=0.5,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_3d_text_tracking_changed()).pack(fill=tk.X, padx=5)

        # When it's visible within the clip — e.g. a drone flying toward text
        # planted on the ground: it should appear as the drone approaches and
        # be gone once the drone has flown past/through it, not stay anchored
        # for the whole clip.
        tk.Label(tt_opts, text="WHEN IT'S VISIBLE", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 2))
        self._3d_text_full_clip = tk.BooleanVar(value=True)
        tk.Checkbutton(tt_opts, text="Show for the entire clip", variable=self._3d_text_full_clip,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       command=self._on_3d_text_tracking_changed).pack(anchor="w")
        tk.Label(tt_opts, text="Uncheck to limit it to part of the clip (e.g. text a drone flies past).",
                 bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), justify=tk.LEFT,
                 wraplength=260).pack(anchor="w", pady=(0, 3))

        start_end_row = tk.Frame(tt_opts, bg=C["panel"])
        start_end_row.pack(fill=tk.X)
        sc = tk.Frame(start_end_row, bg=C["panel"])
        sc.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        tk.Label(sc, text="Start (sec)", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7)).pack(anchor="w")
        self._3d_text_start = tk.DoubleVar(value=0.0)
        tt_start_sb = tk.Spinbox(sc, from_=0.0, to=600.0, increment=0.1, textvariable=self._3d_text_start,
                                  width=8, bg="#2a2a2a", fg="white", bd=0, insertbackground="white",
                                  command=self._on_3d_text_tracking_changed)
        tt_start_sb.pack(fill=tk.X)
        tt_start_sb.bind("<KeyRelease>", lambda e: self._on_3d_text_tracking_changed())

        ec = tk.Frame(start_end_row, bg=C["panel"])
        ec.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        tk.Label(ec, text="End (sec)", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7)).pack(anchor="w")
        self._3d_text_end = tk.DoubleVar(value=3.0)
        tt_end_sb = tk.Spinbox(ec, from_=0.1, to=600.0, increment=0.1, textvariable=self._3d_text_end,
                                width=8, bg="#2a2a2a", fg="white", bd=0, insertbackground="white",
                                command=self._on_3d_text_tracking_changed)
        tt_end_sb.pack(fill=tk.X)
        tt_end_sb.bind("<KeyRelease>", lambda e: self._on_3d_text_tracking_changed())

        tk.Label(tt_opts, text="FADE IN/OUT (sec)", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(4, 0))
        self._3d_text_fade = tk.DoubleVar(value=0.3)
        tk.Scale(tt_opts, variable=self._3d_text_fade, from_=0.0, to=2.0, resolution=0.05,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_3d_text_tracking_changed()).pack(fill=tk.X, padx=5)

        # Mouse transform box (move / resize / rotate directly on the preview)
        tk.Label(tt_opts, text="POSITION, SIZE & ROTATION", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(6, 2))
        self._3d_text_place_btn = tk.Button(tt_opts, text="Edit Text on Preview",
                                             bg=C["accent"], fg="white", bd=0,
                                             font=("Segoe UI", 9, "bold"),
                                             command=self._toggle_3d_text_drag,
                                             cursor="hand2")
        self._3d_text_place_btn.pack(fill=tk.X, pady=3)
        self._3d_text_status = tk.Label(
            tt_opts,
            text="Drag inside=move • corner=resize • yellow dot=tilt/wall • red dot=rotate",
            bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), justify=tk.LEFT, wraplength=260)
        self._3d_text_status.pack(anchor="w", pady=(0, 2))
        self._3d_text_place_active = False

        # AR-style auto-tracking: pins the text to a real point in the
        # footage using optical flow, so it moves/scales with the camera's
        # actual motion and disappears once you've passed it — like an AR
        # doodle planted in the scene, not a fixed on-screen overlay.
        tk.Label(tt_opts, text="AR TRACKING (BETA)", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 2))
        tk.Label(tt_opts,
                 text="Place it above, then track — it follows the camera and\n"
                      "disappears once you pass it. Video clips only.",
                 bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), justify=tk.LEFT,
                 wraplength=260).pack(anchor="w", pady=(0, 3))
        track_btn_row = tk.Frame(tt_opts, bg=C["panel"])
        track_btn_row.pack(fill=tk.X)
        self._3d_text_track_btn = tk.Button(track_btn_row, text="Track Forward From Here",
                                             bg=C["accent"], fg="white", bd=0,
                                             font=("Segoe UI", 9, "bold"),
                                             command=self._start_3d_text_autotrack,
                                             cursor="hand2")
        self._3d_text_track_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        tk.Button(track_btn_row, text="Clear", bg=C["border"], fg="white", bd=0,
                  font=("Segoe UI", 9), command=self._clear_3d_text_autotrack,
                  cursor="hand2").pack(side=tk.LEFT)
        self._3d_text_track_status = tk.Label(
            tt_opts, text="Not tracked — text stays fixed in place for its whole visible window.",
            bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), justify=tk.LEFT, wraplength=260)
        self._3d_text_track_status.pack(anchor="w", pady=(2, 2))

        # ─────────────────────────────────────────────
        # MOTION TRACK EFFECT (arrow + name tracking)
        # ─────────────────────────────────────────────
        mt_sep = tk.Frame(f, bg=C["panel"], height=2, bd=0, highlightbackground=C["border"], highlightthickness=1)
        mt_sep.pack(fill=tk.X, padx=5, pady=(20, 5))
        tk.Label(f, text="MOTION TRACK", bg=C["panel"], fg="#00E676", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5)

        self._motion_track_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="Enable Motion Track (Arrow + Name)", variable=self._motion_track_enabled,
                       bg=C["panel"], fg="white", selectcolor=C["raised"],
                       command=self._on_motion_track_changed).pack(anchor="w", padx=5, pady=5)

        tk.Label(f, text="An arrow tracks a selected person throughout the video with an optional name label. Select a person first, then enable this effect.",
                 bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7), wraplength=280, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 8))

        mt_opts = tk.Frame(f, bg=C["panel"])
        mt_opts.pack(fill=tk.X, padx=10, pady=(0, 8))

        tk.Label(mt_opts, text="DISPLAY MODE", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._motion_track_mode = tk.StringVar(value="arrow_and_name")
        mt_mode_combo = ttk.Combobox(mt_opts, textvariable=self._motion_track_mode,
                                      values=["arrow_and_name", "arrow_only"], state="readonly", width=20)
        mt_mode_combo.pack(anchor="w", pady=(0, 6))
        mt_mode_combo.bind("<<ComboboxSelected>>", lambda e: self._on_motion_track_changed())

        tk.Label(mt_opts, text="NAME LABEL", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._motion_track_name = tk.StringVar(value="")
        mt_name_entry = tk.Entry(mt_opts, textvariable=self._motion_track_name, bg="#2a2a2a", fg="white",
                                  insertbackground="white", font=("Segoe UI", 10, "bold"), bd=0)
        mt_name_entry.pack(fill=tk.X, pady=(0, 6))
        mt_name_entry.bind("<KeyRelease>", lambda e: self._on_motion_track_changed())

        tk.Label(mt_opts, text="ARROW COLOR", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._motion_track_color = tk.StringVar(value="Yellow")
        mt_color_combo = ttk.Combobox(mt_opts, textvariable=self._motion_track_color,
                                       values=["Yellow", "Red", "Green", "Blue", "White", "Orange",
                                               "Cyan", "Magenta", "Lime", "Gold"], state="readonly", width=20)
        mt_color_combo.pack(anchor="w", pady=(0, 6))
        mt_color_combo.bind("<<ComboboxSelected>>", lambda e: self._on_motion_track_changed())

        tk.Label(mt_opts, text="TEXT COLOR", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._motion_track_text_color = tk.StringVar(value="Yellow")
        mt_tcolor_combo = ttk.Combobox(mt_opts, textvariable=self._motion_track_text_color,
                                        values=["Yellow", "White", "Red", "Green", "Blue",
                                                "Orange", "Cyan", "Magenta", "Lime", "Gold"], state="readonly", width=20)
        mt_tcolor_combo.pack(anchor="w", pady=(0, 6))
        mt_tcolor_combo.bind("<<ComboboxSelected>>", lambda e: self._on_motion_track_changed())

        tk.Label(mt_opts, text="ARROW SIZE", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._motion_track_arrow_size = tk.DoubleVar(value=1.0)
        tk.Scale(mt_opts, variable=self._motion_track_arrow_size, from_=0.5, to=3.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_motion_track_changed()).pack(fill=tk.X, padx=5)

        tk.Label(mt_opts, text="ARROW LENGTH", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._motion_track_arrow_len = tk.DoubleVar(value=1.0)
        tk.Scale(mt_opts, variable=self._motion_track_arrow_len, from_=0.5, to=3.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_motion_track_changed()).pack(fill=tk.X, padx=5)

        tk.Label(mt_opts, text="TEXT SIZE", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._motion_track_text_size = tk.DoubleVar(value=1.0)
        tk.Scale(mt_opts, variable=self._motion_track_text_size, from_=0.5, to=3.0, resolution=0.1,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_motion_track_changed()).pack(fill=tk.X, padx=5)

        tk.Label(mt_opts, text="VERTICAL OFFSET (arrow gap above person)", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._motion_track_offset_y = tk.DoubleVar(value=0.0)
        tk.Scale(mt_opts, variable=self._motion_track_offset_y, from_=-200, to=200, resolution=5,
                 orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0,
                 troughcolor=C["border"], command=lambda v: self._on_motion_track_changed()).pack(fill=tk.X, padx=5)

        mt_person_frame = tk.Frame(mt_opts, bg=C["panel"])
        mt_person_frame.pack(fill=tk.X, pady=(6, 0))
        tk.Label(mt_person_frame, text="TRACK PERSON", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._mt_person_status = tk.Label(mt_person_frame, text="Select an object first via Gold Outline or Thug Life panel",
                                          bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 7))
        self._mt_person_status.pack(anchor="w")

        mt_track_btn_row = tk.Frame(mt_opts, bg=C["panel"])
        mt_track_btn_row.pack(fill=tk.X, pady=3)
        tk.Button(mt_track_btn_row, text="Click to Select Object", bg=C["accent"], fg="white", bd=0,
                  font=("Segoe UI", 8, "bold"), command=self._start_person_select_mode,
                  cursor="crosshair").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        tk.Button(mt_track_btn_row, text="Correct Here", bg=C["accent"], fg="white", bd=0,
                  font=("Segoe UI", 8, "bold"), command=self._start_person_correct_mode,
                  cursor="crosshair").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        tk.Button(mt_track_btn_row, text="Auto-Detect", bg="#b71c1c", fg="white", bd=0,
                  font=("Segoe UI", 8, "bold"), command=self._deselect_person).pack(side=tk.LEFT, fill=tk.X, expand=True)

        mt_desc_frame = tk.Frame(mt_opts, bg=C["raised"], bd=0, relief="flat")
        mt_desc_frame.pack(fill=tk.X, padx=0, pady=(10, 5))
        mt_desc = tk.Text(mt_desc_frame, height=5, width=30, bg=C["raised"], fg=C["text_dim"],
                           font=("Segoe UI", 8), wrap=tk.WORD, bd=0, relief="flat")
        mt_desc.insert("1.0", """Motion Track — Arrow + Name Overlay

Draws a colored arrow pointing down at the tracked person with an optional name label. The arrow and text follow the person throughout the video using YOLO tracking.

Select a person using the Click/Auto-Detect buttons above, then enable this effect.""")
        mt_desc.config(state=tk.DISABLED)
        mt_desc.pack(fill=tk.X, padx=6, pady=6)

    def _update_filter_desc(self):
        descs = {
            "Cinematic Warm": "Warm golden amber tone with lifted shadows. Classic cinema look.",
            "Golden Hour": "Soft warm glow like sunset. Rich oranges and gentle highlights.",
            "Vintage Film": "Faded colors with warm tint and grain-like contrast.",
            "Vintage Cam": "Vertical film scratches, dust speckles, hair fibers & dark edge vignette. Old 8mm film camera look.",
            "BW Memories": "Black & white with film grain, vertical scratches & black dust spots. Old cinema projection.",
            "Teal & Orange": "Hollywood blockbuster look. Teal shadows, orange skin tones.",
            "Bleach Bypass": "High contrast, desaturated silver-retention film look.",
            "Cold Blue": "Cool blue cast. Night scenes, moody atmosphere.",
            "Desaturated": "Muted colors with slight warm tint. Documentary style.",
            "High Contrast": "Punchy blacks and bright highlights. Bold and vivid.",
        }
        try:
            self._filter_desc.config(text=descs.get(self._filter_style.get(), ""))
        except Exception:
            pass

    def _on_filter_changed(self):
        self._update_filter_desc()
        if self.selected_idx is not None:
            item = self.media_queue[self.selected_idx]
            item['filter_enabled'] = self._filter_per_clip.get()
            item['filter_style'] = self._filter_style.get()
            item['filter_intensity'] = self._filter_intensity.get()
            item['filter_warmth'] = self._filter_warmth.get()
            item['filter_saturation'] = self._filter_saturation.get()
            item['filter_fade_blacks'] = self._filter_fade_blacks.get()
        self._debounced_preview(interactive=True)

    def _refresh_thug_person_label(self):
        """Keep the Thug Life panel's person-selection status in sync with the
        shared selection state used by the person-picker (same one the gold
        outline effect uses)."""
        label = getattr(self, '_thug_person_status_label', None)
        if label is None:
            return
        try:
            sel = self._effect_selected_person.get()
            if sel is not None and sel >= 0:
                label.config(text=f"Person ID {sel} selected — glasses/chain will track them", fg=C["accent3"])
            else:
                label.config(text="Auto-detect (uses person closest to frame center)", fg=C["text_dim"])
        except Exception:
            pass

    def _update_variation_desc(self):
        var = self._effect_variation.get()
        desc = self._VARIATION_DESCRIPTIONS.get(var, '')
        try:
            self._variation_desc_label.config(text=desc)
        except Exception:
            pass

    def refresh_effects_tab(self):
        if self._mask_edit_active:
            self._mask_edit_active = False
            self.preview_label.config(cursor="")
            self.preview_label.unbind("<ButtonPress-1>")
            self.preview_label.unbind("<B1-Motion>")
            self.preview_label.unbind("<ButtonRelease-1>")
            self._mask_edit_btn.config(text="Start Editing Outline", bg="#e65100")
        if getattr(self, '_3d_text_place_active', False):
            self._3d_text_place_active = False
            self._3d_text_dragging = False
            self.preview_label.config(cursor="")
            self.preview_label.unbind("<ButtonPress-1>")
            self.preview_label.unbind("<B1-Motion>")
            self.preview_label.unbind("<ButtonRelease-1>")
            self._3d_text_place_btn.config(text="Edit Text on Preview", bg=C["accent"])
        if self.selected_idx is None:
            self._effect_no_clip_label.pack(pady=20)
            self._effect_clip_frame.pack_forget()
            return
        item = self.media_queue[self.selected_idx]
        if item['type'] not in ('video', 'image', 'placeholder'):
            self._effect_no_clip_label.pack(pady=20)
            self._effect_clip_frame.pack_forget()
            return

        self._effect_no_clip_label.pack_forget()
        self._effect_clip_frame.pack(fill=tk.X, padx=10)

        self._effect_clip_name.set(item.get('name', 'Unknown'))
        self._effect_enabled.set(item.get('effect', 'none') == 'gold_outline')
        self._effect_variation.set(item.get('effect_variation', 'ethereal'))
        self._color_variation.set(item.get('effect_color_variation', 'Gold (Default)'))
        self._effect_opacity.set(item.get('effect_opacity', 1.0))
        self._effect_glow.set(item.get('effect_glow', 1.0))
        self._effect_timing.set(item.get('effect_timing', 'full_clip'))
        self._effect_start.set(item.get('effect_start', 0.0))
        self._effect_end.set(item.get('effect_end', 5.0))
        self._effect_selected_person.set(int(item.get('effect_selected_person', -1)))
        self._update_variation_desc()
        self._update_person_buttons()
        self._on_effect_timing_changed()
        # Load Ken Burns state
        self._kb_enabled.set(item.get('ken_burns_enabled', False))
        self._kb_zoom_in.set(item.get('ken_burns_zoom_in', 1.0))
        self._kb_zoom_out.set(item.get('ken_burns_zoom_out', 1.3))
        self._kb_pan_x.set(item.get('ken_burns_pan_x', 0.0))
        self._kb_pan_y.set(item.get('ken_burns_pan_y', 0.0))
        # Load Thug Life state
        self._thug_life_enabled.set(item.get('effect_thug_life_enabled', False))
        self._thug_style.set(item.get('thug_style', 'realistic'))
        self._thug_cap_enabled.set(item.get('thug_cap_enabled', True))
        self._thug_entry.set(item.get('thug_entry', 'top'))
        # Load Film Burn state
        self._film_burn_enabled.set(item.get('effect_film_burn_enabled', False))
        self._film_burn_intensity.set(item.get('film_burn_intensity', 1.0))
        self._film_burn_speed.set(item.get('film_burn_speed', 1.0))
        # Load Sun Glare state
        self._sun_glare_enabled.set(item.get('effect_sun_glare_enabled', False))
        self._sun_glare_variation.set(item.get('sun_glare_variation', 'Cinematic'))
        self._sun_glare_position.set(item.get('sun_glare_position', 'Top Left'))
        self._sun_glare_intensity.set(item.get('sun_glare_intensity', 1.0))
        self._sun_glare_size.set(item.get('sun_glare_size', 1.0))
        self._sun_glare_speed.set(item.get('sun_glare_speed', 0.3))
        # Load X Flare state
        self._x_flare_enabled.set(item.get('effect_x_flare_enabled', False))
        self._x_flare_variation.set(item.get('x_flare_variation', 'Blue White'))
        self._x_flare_position.set(item.get('x_flare_position', 'Center'))
        self._x_flare_intensity.set(item.get('x_flare_intensity', 1.0))
        self._x_flare_size.set(item.get('x_flare_size', 1.0))
        self._x_flare_speed.set(item.get('x_flare_speed', 0.3))
        # Load Light Flash state
        self._light_flash_enabled.set(item.get('effect_light_flash_enabled', False))
        self._light_flash_variation.set(item.get('light_flash_variation', 'White Flash'))
        self._light_flash_position.set(item.get('light_flash_position', 'Center'))
        self._light_flash_intensity.set(item.get('light_flash_intensity', 1.0))
        self._light_flash_size.set(item.get('light_flash_size', 1.0))
        self._light_flash_speed.set(item.get('light_flash_speed', 1.0))
        self._light_flash_density.set(item.get('light_flash_density', 6))
        # Load Canopy state
        self._canopy_enabled.set(item.get('effect_canopy_enabled', False))
        self._canopy_light_style.set(item.get('canopy_light_style', 'Soft Atmosphere'))
        self._canopy_light_dir.set(item.get('canopy_light_dir', 'Top Left'))
        self._canopy_fog_density.set(item.get('canopy_fog_density', 0.7))
        self._canopy_fog_height.set(item.get('canopy_fog_height', 0.5))
        self._canopy_ray_intensity.set(item.get('canopy_ray_intensity', 1.0))
        self._canopy_ray_width.set(item.get('canopy_ray_width', 1.0))
        self._canopy_warmth.set(item.get('canopy_warmth', 0.7))
        self._canopy_shimmer.set(item.get('canopy_shimmer', 0.3))
        self._canopy_show_light_source.set(item.get('canopy_show_light_source', True))
        # Load 3D Text Tracking state
        self._3d_text_enabled.set(item.get('effect_3d_text_enabled', False))
        self._3d_text_content.set(item.get('3d_text_content', 'TRACKING'))
        self._3d_text_color.set(item.get('3d_text_color', 'Orange'))
        self._3d_text_depth.set(item.get('3d_text_depth', 0.4))
        self._3d_text_shadow.set(item.get('3d_text_shadow', 0.5))
        self._3d_text_style.set(item.get('3d_text_style', 'Solid Matte'))
        self._3d_text_full_clip.set(item.get('3d_text_full_clip', True))
        self._3d_text_start.set(item.get('3d_text_start', 0.0))
        self._3d_text_end.set(item.get('3d_text_end', 3.0))
        self._3d_text_fade.set(item.get('3d_text_fade', 0.3))
        # --- 3D Camera Track params ---
        if hasattr(self, '_3d_cam_enabled'):
            self._3d_cam_enabled.set(item.get('3d_cam_track_enabled', False))
        if hasattr(self, '_3d_cam_speed'):
            self._3d_cam_speed.set(item.get('3d_cam_speed', 8.0))
        if hasattr(self, '_3d_cam_height'):
            self._3d_cam_height.set(item.get('3d_cam_height', 1.8))
        if hasattr(self, '_3d_focal_length'):
            self._3d_focal_length.set(item.get('3d_focal_length', 1200.0))
        if hasattr(self, '_3d_text_dist'):
            self._3d_text_dist.set(item.get('3d_text_dist', 25.0))
        if hasattr(self, '_3d_text_world_w'):
            self._3d_text_world_w.set(item.get('3d_text_world_w', 4.0))
        if hasattr(self, '_3d_text_world_h'):
            self._3d_text_world_h.set(item.get('3d_text_world_h', 1.4))
        if hasattr(self, '_3d_text_lateral'):
            self._3d_text_lateral.set(item.get('3d_text_lateral', 0.0))
        if hasattr(self, '_3d_text_track_status'):
            track = item.get('3d_text_track')
            if track:
                dur = track.get('tracked_until_t', 0.0) - track.get('anchor_t', 0.0)
                self._3d_text_track_status.config(
                    text=f"Tracking locked ✓ ({dur:.1f}s — fades out once it moves out of view)",
                    fg=C["accent3"])
            else:
                self._3d_text_track_status.config(
                    text="Not tracked — text stays fixed in place for its whole visible window.",
                    fg=C["text_dim"])

        # Load Motion Track state
        self._motion_track_enabled.set(item.get('effect_motion_track_enabled', False))
        self._motion_track_mode.set(item.get('motion_track_mode', 'arrow_and_name'))
        self._motion_track_name.set(item.get('motion_track_name', ''))
        self._motion_track_color.set(item.get('motion_track_color', 'Yellow'))
        self._motion_track_text_color.set(item.get('motion_track_text_color', 'Yellow'))
        self._motion_track_arrow_size.set(item.get('motion_track_arrow_size', 1.0))
        self._motion_track_arrow_len.set(item.get('motion_track_arrow_len', 1.0))
        self._motion_track_text_size.set(item.get('motion_track_text_size', 1.0))
        self._motion_track_offset_y.set(item.get('motion_track_offset_y', 0.0))
