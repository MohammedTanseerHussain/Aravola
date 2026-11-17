"""Background music tracks, envelopes and speech easing.

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


class AudioMixin:
    """Background music tracks, envelopes and speech easing."""

    def add_bgm_track(self):
        _ensure_moviepy()
        paths = filedialog.askopenfilenames(filetypes=[("Audio", "*.mp3 *.wav *.aac")])
        if paths: self.save_state()
        for p in paths:
            # Auto-place: start at the end of the last existing BGM track
            # so new audio continues in flow. User can drag it anywhere after.
            auto_offset = 0.0
            if self.bgm_tracks:
                last = self.bgm_tracks[-1]
                last_start = float(last.get('start_offset', 0.0))
                last_dur = self._get_bgm_played_dur(last)
                auto_offset = last_start + last_dur
            self.bgm_tracks.append({
                'type': 'audio', 'path': p, 'name': os.path.basename(p),
                'volume': 1.0, 'start_offset': auto_offset,
                'clip_start': 0.0, 'clip_end': 0.0,
                'duration': 10.0, 'vol_envelope': [(0.0, 1.0), (1.0, 1.0)],
                'ease_mode': 'none'
            })
        self._refresh_audio_list()
        self.refresh_timeline()

    def remove_bgm(self, idx):
        self.save_state()
        del self.bgm_tracks[idx]
        self._refresh_audio_list()
        self.refresh_timeline()

    def _bgm_vol_changed(self, idx, val):
        self.bgm_tracks[idx]["volume"] = float(val)
        self.timeline_dirty = True

    def _bgm_mute_toggled(self, idx):
        self.save_state()
        bgm = self.bgm_tracks[idx]
        bgm["muted"] = bgm.get("_mute_var", tk.BooleanVar()).get()
        self.timeline_dirty = True
        self.refresh_timeline()

    def _apply_ease_to_envelope(self, clip_dict):
        """Rewrite vol_envelope keypoints to match the chosen ease_mode shape.
        Only the START and END anchor points are rewritten — any user-placed
        interior points are left untouched so manual edits are preserved.
        The envelope is evaluated lazily by _eval_vol_envelope (cosine interp),
        so just placing keypoints at the right positions gives the correct curve.
        Never overwrites a track that has a Speech Ease transition applied.
        """
        # Never overwrite a custom Speech Ease envelope
        if clip_dict.get('speech_ease_applied'):
            return
        mode = clip_dict.get('ease_mode', 'none')
        vol  = float(clip_dict.get('volume', 1.0))

        if mode == 'none':
            # flat line at current volume
            clip_dict['vol_envelope'] = [(0.0, vol), (1.0, vol)]

        elif mode == 'ease_in':
            # fade UP from 0 → vol  (ramp in over first ~30% then hold)
            clip_dict['vol_envelope'] = [
                (0.0,  0.0),
                (0.3,  vol),
                (1.0,  vol),
            ]

        elif mode == 'ease_out':
            # hold vol then fade DOWN to 0 over last ~30%
            clip_dict['vol_envelope'] = [
                (0.0,  vol),
                (0.7,  vol),
                (1.0,  0.0),
            ]

        elif mode == 'ease_in_out':
            # X cross-fade shape: fade in from 0, hold, fade out to 0
            clip_dict['vol_envelope'] = [
                (0.0,  0.0),
                (0.25, vol),
                (0.75, vol),
                (1.0,  0.0),
            ]

        elif mode == 'speech_pause':
            # Speech Pause no longer touches this track's envelope at all.
            # The track plays at full volume right to its natural end.
            # The pause itself (a separate spacer clip) is what carries the
            # effect — see _bgm_ease_changed, which inserts a low-noise-floor
            # spacer instead of editing this track's volume curve.
            clip_dict['vol_envelope'] = [
                (0.0, vol),
                (1.0, vol),
            ]

        self.timeline_dirty = True
        self.refresh_timeline()

    def _detect_breathing_pattern(self, path, clip_start=0.0, clip_end=0.0,
                                   n_samples=200):
        """Analyse the source audio to extract a breathing amplitude envelope.
        Returns a 1-D numpy array of n_samples amplitude values (0–1) that
        captures the slow rise/fall rhythm of breath cycles in the recording.
        Steps:
          1. Load audio, compute RMS in short frames (30 ms)
          2. Low-pass smooth to isolate the breath-rate envelope (0.1–1 Hz)
          3. Normalise to 0–1 and resample to n_samples for playback use
        Falls back to a synthesised sine-based breath pattern if the file
        cannot be opened or has no detectable variation.
        """
        FPS     = 44100
        FRAME   = int(FPS * 0.03)   # 30 ms RMS frame
        SMOOTH  = 80                # smoothing window (frames ~= 2.4 s)

        try:
            from moviepy.editor import AudioFileClip as _AFC
            ac = _AFC(path)
            cs = max(0.0, float(clip_start))
            ce = float(clip_end)
            if ce <= cs:
                ce = ac.duration
            # Limit analysis to first 30 s to keep it fast
            ce = min(ce, cs + 30.0)
            ac = ac.subclip(cs, ce)
            dur = ac.duration

            n_frames = max(1, int(dur * FPS / FRAME))
            times = np.linspace(0, dur - FRAME / FPS, n_frames)
            rms = np.array([
                np.sqrt(np.mean(np.array(ac.get_frame(t), dtype=np.float32) ** 2))
                for t in times
            ], dtype=np.float32)
            ac.close()

            # Low-pass smooth with a uniform window to extract breath envelope
            if len(rms) >= SMOOTH:
                kernel = np.ones(SMOOTH, dtype=np.float32) / SMOOTH
                env = np.convolve(rms, kernel, mode='same')
            else:
                env = rms.copy()

            # Normalise 0–1
            lo, hi = env.min(), env.max()
            if hi - lo > 1e-6:
                env = (env - lo) / (hi - lo)
            else:
                raise ValueError("flat signal — no breath variation detected")

            # Resample to n_samples
            idx_f = np.linspace(0, len(env) - 1, n_samples)
            left  = np.floor(idx_f).astype(int)
            right = np.minimum(left + 1, len(env) - 1)
            alpha = idx_f - left
            pattern = env[left] * (1 - alpha) + env[right] * alpha
            return pattern.astype(np.float32)

        except Exception:
            # Fallback: synthesised double-sine breath shape
            t = np.linspace(0, 4 * np.pi, n_samples)
            pattern = (0.5 - 0.5 * np.cos(t)) ** 1.4
            return pattern.astype(np.float32)

    def _bgm_ease_changed(self, idx, mode):
        """Called when a user ticks/unticks an ease option for a BGM track.
        For speech_pause: inserts/removes an adjustable silent-ish spacer clip
        immediately after this track. The source track's audio is left
        completely untouched — no fade, no cliff. The spacer carries a very
        light noise floor (not pure digital silence) so the pause doesn't
        sound like a hard mute, then the next track continues normally.
        """
        self.save_state()
        bgm = self.bgm_tracks[idx]
        prev_mode = bgm.get('ease_mode', 'none')
        new_mode = 'none' if prev_mode == mode else mode
        bgm['ease_mode'] = new_mode

        if mode == 'speech_pause':
            track_end = float(bgm.get('start_offset', 0.0)) + self._get_bgm_played_dur(bgm)
            PAUSE_DUR = float(bgm.get('_last_pause_dur', 1.0))   # remembers last used length

            if new_mode == 'speech_pause':
                # Leave this track's envelope completely flat/untouched
                self._apply_ease_to_envelope(bgm)
                # Detect breathing pattern from source clip in background
                breath_pat = self._detect_breathing_pattern(
                    bgm['path'],
                    clip_start=bgm.get('clip_start', 0.0),
                    clip_end=bgm.get('clip_end', 0.0)
                )
                spacer = {
                    'type': 'audio',
                    'path': bgm['path'],
                    'name': '[pause]',
                    'volume': 1.0,
                    'start_offset': track_end,
                    'clip_start': 0.0,
                    'clip_end': PAUSE_DUR,
                    'duration': PAUSE_DUR,
                    'muted': False,
                    'vol_envelope': [(0.0, 1.0), (1.0, 1.0)],
                    'ease_mode': 'none',
                    'is_speech_pause_spacer': True,
                    'breathing_pattern': breath_pat,  # detected from source clip
                    'breath_vol': 0.12,               # controllable 0–1
                    'owner_idx': idx,
                }
                self.bgm_tracks.insert(idx + 1, spacer)
                for j in range(idx + 2, len(self.bgm_tracks)):
                    self.bgm_tracks[j]['start_offset'] = (
                        float(self.bgm_tracks[j].get('start_offset', 0.0)) + PAUSE_DUR
                    )
            else:
                spacer_idx = None
                for j, b in enumerate(self.bgm_tracks):
                    if b.get('is_speech_pause_spacer') and b.get('owner_idx') == idx:
                        spacer_idx = j
                        break
                if spacer_idx is not None:
                    PAUSE_DUR = self._get_bgm_played_dur(self.bgm_tracks[spacer_idx])
                    del self.bgm_tracks[spacer_idx]
                    for j in range(spacer_idx, len(self.bgm_tracks)):
                        self.bgm_tracks[j]['start_offset'] = (
                            float(self.bgm_tracks[j].get('start_offset', 0.0)) - PAUSE_DUR
                        )
                vol = float(bgm.get('volume', 1.0))
                bgm['vol_envelope'] = [(0.0, vol), (1.0, vol)]
        else:
            self._apply_ease_to_envelope(bgm)

        try:
            bgm['_ease_in_var'].set(bgm['ease_mode'] == 'ease_in')
            bgm['_ease_out_var'].set(bgm['ease_mode'] == 'ease_out')
            bgm['_ease_io_var'].set(bgm['ease_mode'] == 'ease_in_out')
            bgm['_ease_sp_var'].set(bgm['ease_mode'] == 'speech_pause')
        except Exception:
            pass
        self.timeline_dirty = True
        self._refresh_audio_list()
        self.refresh_timeline()

    def _resize_speech_pause(self, owner_idx, new_dur):
        """Resize an existing speech-pause spacer (called from the inspector
        slider). Shifts all subsequent tracks to match the new length.
        """
        spacer_idx = None
        for j, b in enumerate(self.bgm_tracks):
            if b.get('is_speech_pause_spacer') and b.get('owner_idx') == owner_idx:
                spacer_idx = j
                break
        if spacer_idx is None: return
        spacer = self.bgm_tracks[spacer_idx]
        old_dur = self._get_bgm_played_dur(spacer)
        new_dur = max(0.1, float(new_dur))
        spacer['clip_end'] = new_dur
        spacer['duration'] = new_dur
        delta = new_dur - old_dur
        for j in range(spacer_idx + 1, len(self.bgm_tracks)):
            self.bgm_tracks[j]['start_offset'] = (
                float(self.bgm_tracks[j].get('start_offset', 0.0)) + delta
            )
        # Remember this length for next time speech_pause is toggled on this owner
        if owner_idx < len(self.bgm_tracks):
            self.bgm_tracks[owner_idx]['_last_pause_dur'] = new_dur
        self.timeline_dirty = True
        self.refresh_timeline()

    def apply_speech_ease(self):
        """Apply Speech Ease between two Ctrl+Clicked tracks.
        Rules:
        - Track 1 (outgoing): add DROP at its END only. Never touch its start.
        - Track 2 (incoming): add RISE at its START only. Never touch its end.
        - A middle track selected as both outgoing (in one pair) and incoming
          (in another pair) ends up with RISE at start AND DROP at end — both
          preserved independently.
        The envelope is stored as a list of (frac, vol) points. We splice only
        the tail points for a DROP and only the head points for a RISE, leaving
        the rest of the envelope completely untouched.
        """
        if len(self._audio_multiselect) != 2:
            return messagebox.showwarning(
                "Speech Ease",
                "Ctrl+Click exactly 2 audio tracks on the timeline first\n"
                "(1st click = outgoing track with drop, 2nd = incoming track with rise)."
            )
        self.save_state()
        idx1, idx2 = self._audio_multiselect[0], self._audio_multiselect[1]
        bgm1 = self.bgm_tracks[idx1]
        bgm2 = self.bgm_tracks[idx2]

        def _apply_drop(bgm):
            """Splice a steep 3-point drop onto the TAIL of bgm's envelope,
            keeping whatever is at the head completely untouched."""
            vol = float(bgm.get('volume', 1.0))
            env = bgm.get('vol_envelope', [(0.0, vol), (1.0, vol)])
            # Remove any existing points at frac >= 0.90 (the tail zone)
            env_head = [(f, v) for (f, v) in env if f < 0.90]
            if not env_head:
                env_head = [(0.0, vol)]
            # Append the drop tail
            env_head += [
                (0.92, vol),          # hold full until 92%
                (0.96, vol * 0.45),   # sharp step to ~45% at 96%
                (1.0,  0.12),         # sharp step to low at end
            ]
            bgm['vol_envelope'] = env_head
            bgm['ease_mode'] = 'none'
            bgm['speech_ease_applied'] = True
            bgm['speech_ease_has_drop'] = True

        def _apply_rise(bgm):
            """Splice a steep 3-point rise onto the HEAD of bgm's envelope,
            keeping whatever is at the tail completely untouched."""
            vol = float(bgm.get('volume', 1.0))
            env = bgm.get('vol_envelope', [(0.0, vol), (1.0, vol)])
            # Remove any existing points at frac <= 0.10 (the head zone)
            env_tail = [(f, v) for (f, v) in env if f > 0.10]
            if not env_tail:
                env_tail = [(1.0, vol)]
            # Prepend the rise head
            rise_head = [
                (0.0,  0.12),         # start at low
                (0.04, vol * 0.45),   # sharp step to ~45% at 4%
                (0.08, vol),          # snap to full at 8%
            ]
            bgm['vol_envelope'] = rise_head + env_tail
            bgm['ease_mode'] = 'none'
            bgm['speech_ease_applied'] = True
            bgm['speech_ease_has_rise'] = True

        _apply_drop(bgm1)   # outgoing: drop at its end
        _apply_rise(bgm2)   # incoming: rise at its start

        # Clear multiselect — user picks a fresh pair for the next transition
        self._audio_multiselect = []
        self.timeline_dirty = True
        self._refresh_audio_list()
        self.refresh_timeline()
        self.status_label.config(
            text="Speech Ease applied. Ctrl+Click next pair for another transition.",
            fg=C["accent3"]
        )

    def _video_ease_changed(self, idx, mode):
        """Called when a user ticks/unticks an ease option for a video clip."""
        self.save_state()
        item = self.media_queue[idx]
        if item.get('ease_mode', 'none') == mode:
            item['ease_mode'] = 'none'
        else:
            item['ease_mode'] = mode
        self._apply_ease_to_envelope(item)

    def _refresh_audio_list(self):
        for w in self.audio_list_frame.winfo_children():
            w.destroy()
        # Force scroll region update after content rebuild
        self.audio_list_frame.update_idletasks()
        # Bind mousewheel on every child widget so scrolling works
        # regardless of which widget the mouse happens to be over
        self._bind_scroll_children(self.audio_list_frame, self.audio_scroll_canvas)

        for i, bgm in enumerate(self.bgm_tracks):
            if bgm.get('is_speech_pause_spacer'): continue   # hidden in list UI
            row = tk.Frame(self.audio_list_frame, bg=C["raised"], relief="flat")
            row.pack(fill=tk.X, padx=10, pady=3)

            tk.Label(row, text=f"♪ {os.path.basename(bgm['path'])[:20]}", bg=C["raised"], fg=C["accent3"], font=("Arial", 9, "bold"), anchor="w").pack(fill=tk.X, padx=6, pady=(4, 0))

            ctrl = tk.Frame(row, bg=C["raised"])
            ctrl.pack(fill=tk.X, padx=4, pady=4)

            tk.Label(ctrl, text="Vol:", bg=C["raised"], fg=C["text_dim"], font=("Arial", 8)).pack(side=tk.LEFT)
            vol_var = tk.DoubleVar(value=bgm.get("volume", 0.7))
            bgm["_vol_var"] = vol_var
            
            tk.Scale(ctrl, from_=0.0, to=1.5, resolution=0.05, orient=tk.HORIZONTAL, variable=vol_var, bg=C["raised"], fg=C["text"], highlightthickness=0, troughcolor=C["border"], length=80, command=lambda v, idx=i: self._bgm_vol_changed(idx, v)).pack(side=tk.LEFT, padx=2)

            mute_var = tk.BooleanVar(value=bgm.get("muted", False))
            bgm["_mute_var"] = mute_var
            tk.Checkbutton(ctrl, text="🔇", variable=mute_var, command=lambda idx=i: self._bgm_mute_toggled(idx), bg=C["raised"], fg=C["text"], selectcolor=C["raised"]).pack(side=tk.LEFT, padx=2)

            # ── Ease tick options — row 1: fade effects ──────────────────
            ease_row1 = tk.Frame(row, bg=C["raised"])
            ease_row1.pack(fill=tk.X, padx=6, pady=(2, 0))

            # ── Ease tick options — row 2: speech pause ───────────────────
            ease_row2 = tk.Frame(row, bg=C["raised"])
            ease_row2.pack(fill=tk.X, padx=6, pady=(0, 4))

            cur_mode = bgm.get('ease_mode', 'none')
            ei_var  = tk.BooleanVar(value=(cur_mode == 'ease_in'))
            eo_var  = tk.BooleanVar(value=(cur_mode == 'ease_out'))
            eio_var = tk.BooleanVar(value=(cur_mode == 'ease_in_out'))
            esp_var = tk.BooleanVar(value=(cur_mode == 'speech_pause'))
            bgm['_ease_in_var']  = ei_var
            bgm['_ease_out_var'] = eo_var
            bgm['_ease_io_var']  = eio_var
            bgm['_ease_sp_var']  = esp_var

            ck_kw = dict(bg=C["raised"], fg=C["accent"], selectcolor=C["raised"],
                         activebackground=C["raised"], activeforeground=C["accent"],
                         font=("Segoe UI", 7), relief="flat", bd=0)

            # Row 1: short labels so all 3 fit in the 280px panel
            tk.Checkbutton(ease_row1, text="↗ In",    variable=ei_var,
                           command=lambda idx=i: self._bgm_ease_changed(idx, 'ease_in'),
                           **ck_kw).pack(side=tk.LEFT, padx=(0,2))
            tk.Checkbutton(ease_row1, text="↘ Out",   variable=eo_var,
                           command=lambda idx=i: self._bgm_ease_changed(idx, 'ease_out'),
                           **ck_kw).pack(side=tk.LEFT, padx=2)
            tk.Checkbutton(ease_row1, text="✕ X-fade", variable=eio_var,
                           command=lambda idx=i: self._bgm_ease_changed(idx, 'ease_in_out'),
                           **ck_kw).pack(side=tk.LEFT, padx=2)

            # Row 2: speech pause — gold colour, own line, always fully visible
            tk.Checkbutton(ease_row2, text="🎙 Speech Pause", variable=esp_var,
                           command=lambda idx=i: self._bgm_ease_changed(idx, 'speech_pause'),
                           fg="#FFD700", bg=C["raised"], selectcolor=C["raised"],
                           activebackground=C["raised"], activeforeground="#FFD700",
                           font=("Segoe UI", 7), relief="flat", bd=0
                           ).pack(side=tk.LEFT, padx=(0,2))

            # If a pause is currently active on this track, show a length slider
            if cur_mode == 'speech_pause':
                spacer = None
                for b in self.bgm_tracks:
                    if b.get('is_speech_pause_spacer') and b.get('owner_idx') == i:
                        spacer = b
                        break
                if spacer is not None:
                    ctrl_row = tk.Frame(row, bg=C["raised"])
                    ctrl_row.pack(fill=tk.X, padx=6, pady=(0, 4))
                    # Pause length
                    tk.Label(ctrl_row, text="Len:", bg=C["raised"],
                             fg="#FFD700", font=("Segoe UI", 7)).pack(side=tk.LEFT)
                    cur_dur = self._get_bgm_played_dur(spacer)
                    pause_var = tk.DoubleVar(value=cur_dur)
                    tk.Scale(ctrl_row, from_=0.2, to=5.0, resolution=0.1,
                             orient=tk.HORIZONTAL, variable=pause_var,
                             bg=C["raised"], fg="#FFD700", highlightthickness=0,
                             troughcolor=C["border"], length=70, showvalue=True,
                             font=("Segoe UI", 7),
                             command=lambda v, idx=i: self._resize_speech_pause(idx, float(v))
                             ).pack(side=tk.LEFT, padx=2)
                    # Breath volume
                    tk.Label(ctrl_row, text="Breath:", bg=C["raised"],
                             fg="#FFD700", font=("Segoe UI", 7)).pack(side=tk.LEFT)
                    cur_bvol = float(spacer.get("breath_vol", 0.12))
                    bvol_var = tk.DoubleVar(value=cur_bvol)
                    spacer["_bvol_var"] = bvol_var
                    def on_bvol(v, sp=spacer):
                        sp["breath_vol"] = float(v)
                        self.timeline_dirty = True
                    tk.Scale(ctrl_row, from_=0.0, to=0.5, resolution=0.01,
                             orient=tk.HORIZONTAL, variable=bvol_var,
                             bg=C["raised"], fg="#FFD700", highlightthickness=0,
                             troughcolor=C["border"], length=70, showvalue=True,
                             font=("Segoe UI", 7),
                             command=on_bvol
                             ).pack(side=tk.LEFT, padx=2)
