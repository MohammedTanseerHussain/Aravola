"""Playback transport and preview scheduling.

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


class PlaybackMixin:
    """Playback transport and preview scheduling."""

    def toggle_play(self):
        _ensure_pygame()
        _ensure_moviepy()
        if not HAS_PYGAME:
            messagebox.showwarning("Pygame Required", "Pygame is not installed or failed to initialize. Live audio preview requires Pygame.\n\nPlease run 'pip install pygame' and ensure your audio device is connected.")
            
        if self.is_playing:
            self.is_playing = False
            self.play_btn.config(text="▶", bg=C["accent3"])
            if HAS_PYGAME:
                try: pygame.mixer.music.stop()
                except: pass
        else:
            if self.timeline_dirty and HAS_PYGAME:
                self.status_label.config(text="Mixing Audio...", fg=C["accent4"])
                self.root.update()
                self._build_preview_audio()
                self.timeline_dirty = False
                self.status_label.config(text="Ready.", fg=C["accent3"])

        self.is_playing = True
        self.play_btn.config(text="⏸", bg=C["accent4"])
        self._preview_pending = False
        self._interactive_mode = False
        if self._debounce_job is not None:
            self.root.after_cancel(self._debounce_job)
            self._debounce_job = None
        if self._final_preview_job is not None:
            self.root.after_cancel(self._final_preview_job)
            self._final_preview_job = None
        old_thread = self.play_thread
        if old_thread is not None and old_thread.is_alive():
            old_thread.join(timeout=0.5)
        self.play_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.play_thread.start()

    def _playback_loop(self):
        start_t = self.playhead_t.get()
        max_t = self._total_duration()

        if self.audio_ready and HAS_PYGAME:
            try:
                print(f"[AUDIO] Playing: {self.temp_audio_path} from {start_t}s")
                pygame.mixer.music.load(self.temp_audio_path)
                try:
                    pygame.mixer.music.play(0, start_t) 
                except TypeError:
                    pygame.mixer.music.play() 
            except Exception as e: 
                print("Pygame playback error:", e)

        start_time_sys = time.perf_counter()
        while self.is_playing:
            if self.audio_ready and HAS_PYGAME:
                pos_ms = pygame.mixer.music.get_pos()
                curr_t = start_t + (pos_ms / 1000.0) if pos_ms != -1 else start_t + (time.perf_counter() - start_time_sys)
            else:
                curr_t = start_t + (time.perf_counter() - start_time_sys)

            if curr_t >= max_t:
                self.root.after(0, self._set_playhead, max_t, False)
                break

            self.root.after(0, self._set_playhead, curr_t, False)
            if not self._preview_pending:
                self._preview_pending = True
                self.root.after(0, self._do_preview_update)
            time.sleep(self._playback_preview_interval)

        self.is_playing = False
        self.root.after(0, lambda: self.play_btn.config(text="▶", bg=C["accent3"]))
        if HAS_PYGAME:
            try: pygame.mixer.music.stop()
            except: pass
        # One full-quality render once playback actually stops, so the
        # frame you land on isn't left in the cheaper live-playback mode.
        self.root.after(0, self._run_final_preview)

    def _do_preview_update(self):
        self._preview_pending = False
        # Live playback renders in the same fast/low-res mode as dragging a
        # slider — full quality on every frame at up to 15fps isn't
        # achievable with this pipeline, so match what every NLE does and
        # trade a bit of fidelity for smoothness while actually playing.
        self._interactive_mode = True
        self.update_global_preview()

    def _debounced_preview(self, delay=50, interactive=False):
        """Debounced preview update. Prevents stacking heavy computations
        when sliders are dragged rapidly. interactive=True uses low-res
        mode that skips heavy effects for instant feedback."""
        self._interactive_mode = interactive
        if self._debounce_job is not None:
            self.root.after_cancel(self._debounce_job)
        self._debounce_job = self.root.after(delay, self._run_debounced_preview)
        # Schedule a final full-res preview after interaction settles
        if interactive:
            if self._final_preview_job is not None:
                self.root.after_cancel(self._final_preview_job)
            self._final_preview_job = self.root.after(400, self._run_final_preview)

    def _run_debounced_preview(self):
        self._debounce_job = None
        self.update_global_preview()

    def _run_final_preview(self):
        """Full-res preview after interactive mode settles."""
        self._final_preview_job = None
        self._interactive_mode = False
        self.update_global_preview()

    def _preview_cache_key(self, item, local_t):
        """Generate a cache key for the base preview frame."""
        return (item.get('path', ''), item.get('clip_start', 0.0),
                item.get('clip_end', 0.0), round(local_t, 3),
                item.get('rotation', 0), item.get('flip_h', False),
                item.get('flip_v', False))

    def _get_cached_base_frame(self, item, local_t, get_frame_fn):
        """Return cached base frame or compute + cache it."""
        key = self._preview_cache_key(item, local_t)
        if key in self._preview_base_cache:
            return self._preview_base_cache[key]
        frame = get_frame_fn()
        if frame is not None and len(self._preview_base_cache) >= self._preview_cache_max:
            oldest = next(iter(self._preview_base_cache))
            del self._preview_base_cache[oldest]
        if frame is not None:
            self._preview_base_cache[key] = frame
        return frame

    def _apply_kenburns_zoom_numpy(self, frame, zoom, pan_x, pan_y, t_prog, target_w, target_h):
        """Zooms/pans an already frame-sized (target_w x target_h) RGB
        array — used to apply Ken Burns *after* the 3D text has been
        composited into the frame, so the text zooms/pans together with
        the scene (staying pinned to the same point in it) instead of
        sitting fixed on screen while the video moves underneath it."""
        if zoom <= 1.0001 and pan_x == 0 and pan_y == 0:
            return frame
        img = PIL.Image.fromarray(frame)
        new_w = max(1, int(round(target_w * zoom)))
        new_h = max(1, int(round(target_h * zoom)))
        big = img.resize((new_w, new_h), PIL.Image.LANCZOS)
        offset_x = pan_x * target_w * 0.5 * t_prog
        offset_y = pan_y * target_h * 0.5 * t_prog
        cx = new_w / 2.0 + offset_x
        cy = new_h / 2.0 + offset_y
        left = int(round(cx - target_w / 2.0))
        top = int(round(cy - target_h / 2.0))
        left = max(0, min(left, max(0, new_w - target_w)))
        top = max(0, min(top, max(0, new_h - target_h)))
        cropped = big.crop((left, top, left + target_w, top + target_h))
        if cropped.size != (target_w, target_h):
            canvas = PIL.Image.new("RGB", (target_w, target_h), (0, 0, 0))
            canvas.paste(cropped, (0, 0))
            cropped = canvas
        return np.array(cropped)
