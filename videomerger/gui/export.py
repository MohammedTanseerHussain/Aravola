"""Validation, background export, progress and completion.

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


class ExportMixin:
    """Validation, background export, progress and completion."""

    def _ffprobe_duration(self, path):
        """
        Use ffprobe (bundled with ffmpeg / ImageMagick) to read the video
        duration WITHOUT decoding any frames.  Falls back to opening a
        MoviePy VideoFileClip if ffprobe is unavailable or fails.
        Returns duration in seconds as a float.
        """
        import subprocess, json

        # Candidate ffprobe locations — try the one next to the user's ffmpeg first
        ffprobe_candidates = [
            "ffprobe",
            os.path.join("C:\\", "ffmpeg", "bin", "ffprobe.exe"),
            os.path.join("C:\\", "Program Files", "ffmpeg", "bin", "ffprobe.exe"),
        ]
        # Also try the sibling of wherever MoviePy thinks ffmpeg lives
        try:
            from moviepy.config import get_setting
            ffmpeg_bin = get_setting("FFMPEG_BINARY")
            sibling = os.path.join(os.path.dirname(ffmpeg_bin), "ffprobe.exe")
            ffprobe_candidates.insert(0, sibling)
        except Exception:
            pass

        for probe_bin in ffprobe_candidates:
            try:
                result = subprocess.run(
                    [probe_bin, "-v", "quiet", "-print_format", "json",
                     "-show_format", path],
                    capture_output=True, timeout=10
                )
                if result.returncode == 0:
                    info = json.loads(result.stdout)
                    dur = float(info.get("format", {}).get("duration", 0))
                    if dur > 0:
                        return dur
            except (FileNotFoundError, subprocess.TimeoutExpired,
                    json.JSONDecodeError, ValueError):
                continue

        # ffprobe not found — fall back to MoviePy (may trigger first-frame read)
        try:
            tmp = VideoFileClip(path, audio=False)
            dur = tmp.duration
            tmp.close()
            return dur
        except Exception:
            return 30.0   # safe fallback so export can still attempt

    def _validate_video_files(self):
        """
        Pre-export validation using ffprobe (no frame decoding).
        ffprobe reads container metadata only — it never touches frame data,
        so it never triggers "failed to read first frame".
        Returns a list of (name, error_message) tuples for unreadable files.
        """
        import subprocess, json
        bad = []
        seen = set()
        for item in self.media_queue:
            if item['type'] != 'video' or not item.get('path'):
                continue
            path = item['path']
            if path in seen:
                continue
            seen.add(path)
            if not os.path.exists(path):
                bad.append((os.path.basename(path), "File not found on disk."))
                continue
            # Use _ffprobe_duration — zero frame decoding, purely metadata
            try:
                dur = self._ffprobe_duration(path)
                if dur <= 0:
                    bad.append((os.path.basename(path), "ffprobe reported zero duration."))
            except Exception as exc:
                bad.append((os.path.basename(path), str(exc)))
        return bad

    def start_merge_thread(self):
        _ensure_moviepy()
        save_path = filedialog.asksaveasfilename(
            defaultextension=".mp4", initialfile="final_output.mp4",
            filetypes=[("MP4 Video", "*.mp4")]
        )
        if not save_path:
            return

        for item in self.media_queue:
            if item['type'] == 'placeholder' and not item.get('path'):
                return messagebox.showerror(
                    "Error",
                    "You have unfilled Placeholders! Please fill or delete them before exporting."
                )

        # --- 1. Stop all playback & cancel previews (quick, main thread) ---
        self.is_playing = False
        if getattr(self, '_preview_job', None) is not None:
            self.root.after_cancel(self._preview_job)
            self._preview_job = None

        if HAS_PYGAME:
            _ensure_pygame()
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except:
                pass

        # --- FIX 2: Full cache purge — close EVERY live clip before export ---
        filmstrip_cache = {k: v for k, v in self._clip_cache.items()
                           if str(k).startswith("filmstrip")}
        for k, v in list(self._clip_cache.items()):
            if not str(k).startswith("filmstrip"):
                try:
                    if getattr(v, 'audio', None) is not None:
                        v.audio.close()
                    if hasattr(v, 'close'):
                        v.close()
                except Exception:
                    pass
        self._clip_cache = filmstrip_cache
        self._clip_cache_order = list(filmstrip_cache.keys())
        self._img_cache.clear()

        # --- FIX 1: run ffprobe validation (a subprocess call per video —
        # can take seconds on a big project) in the background thread too,
        # instead of blocking the whole UI on the main thread beforehand. ---
        self.status_label.config(text="Checking media files…", fg=C["accent4"])
        if hasattr(self, 'export_btn'):
            self.export_btn.config(state=tk.DISABLED)

        threading.Thread(target=self._export_worker, args=(save_path,), daemon=True).start()

    def _export_worker(self, save_path):
        _ensure_moviepy()
        bad_files = self._validate_video_files()
        if bad_files:
            msg = "The following video file(s) could not be read by ffmpeg:\n\n"
            for name, err in bad_files:
                msg += f"  • {name}\n    {err}\n\n"
            msg += (
                "Possible fixes:\n"
                "  1. Re-encode the file with HandBrake or ffmpeg.\n"
                "  2. Make sure ffmpeg/ffprobe on your PATH matches the\n"
                "     version MoviePy expects (not the Ubuntu-repo version).\n"
                "  3. Remove or replace the problematic clip and try again."
            )
            self.root.after(0, self._on_export_validate_failed, msg)
            return

        self.root.after(0, lambda: self.status_label.config(
            text="Rendering VFX and Media… Please wait.", fg="green"))

        # --- FIX 3: Longer OS-level delay so Windows fully releases file handles ---
        time.sleep(1.0)
        self.process_merge(save_path)

    def _on_export_validate_failed(self, msg):
        self.status_label.config(text="Export cancelled — bad media file.", fg="red")
        if hasattr(self, 'export_btn'):
            self.export_btn.config(state=tk.NORMAL)
        messagebox.showerror("Media Error", msg)

    def _on_export_progress(self, pct):
        self.status_label.config(text=f"Rendering… {pct}%", fg="green")

    def _apply_highlight_regions_export(self, clip, item, target_w, target_h):
        """Apply highlight effect to a duplicated clip during export.
        Handles slowmo_zoom and reverse effects on the individual clip."""
        effect = item.get('_highlight_effect')
        if not effect:
            return [clip]

        if effect == 'slowmo_zoom':
            speed = max(0.1, item.get('speed', 0.3))
            zoom_level = item.get('_highlight_zoom', 1.5)
            try:
                clip = clip.fx(vfx.speedx, speed)
            except:
                pass
            _zw, _zh = target_w, target_h
            _zoom = zoom_level
            def _zoom_frame(get_frame, tt, _z=_zoom, _dw=_zw, _dh=_zh):
                frame = get_frame(tt)
                h_f, w_f = frame.shape[:2]
                new_w = max(1, int(w_f * _z))
                new_h = max(1, int(h_f * _z))
                scaled = cv2.resize(frame, (new_w, new_h))
                left = (new_w - w_f) // 2
                top = (new_h - h_f) // 2
                return scaled[top:top + h_f, left:left + w_f]
            clip = clip.fl(_zoom_frame)

        elif effect == 'reverse':
            clip = clip.fl_time(lambda t: clip.duration - t)

        return [clip]

    def process_merge(self, save_path):
        is_mobile = (self.format_var.get() == "mobile")
        target_w = 1080 if is_mobile else 1920
        target_h = 1920 if is_mobile else 1080
        smart_fill = self.smart_fill_var.get()
        auto_rotate = self.auto_rotate_var.get()

        final_clips = []
        keep_alive = []

        try:
            for i, item in enumerate(self.media_queue):
                scale_val = item.get('scale', 1.0)
                t_start = item.get('tl_start', 0.0)

                if item['type'] == 'title':
                    clip = self.build_finch_title_card(target_w, target_h, item)
                    clip_dur = clip.duration
                    if item.get('text'):
                        lt_layers = []
                        style = item.get('lt_style', 'News Headline')
                        lt_dur = item.get('text_end', 3.0) - item.get('text_start', 0.0)
                        if lt_dur <= 0:
                            lt_dur = clip_dur
                        if style == 'News Headline':
                            lt_layers = self.build_news_lower_third(item['text'], target_w, target_h, clip_dur, lt_dur)
                        elif style == 'Purple Designer Box':
                            lt_layers = self.build_designer_lower_third(item['text'], target_w, target_h, clip_dur, lt_dur)
                        elif style == 'Static Aurora Tile (Bracket)':
                            lt_layers = self.build_tile_lower_third(item['text'], target_w, target_h, clip_dur, lt_dur)
                        else:
                            lt_layers = self.build_magical_lower_third(item['text'], target_w, target_h, clip_dur, lt_dur)
                        for l in lt_layers:
                            clip = CompositeVideoClip([clip.set_duration(clip_dur), l.set_start(item.get('text_start', 0.0))], size=(target_w, target_h)).set_duration(clip_dur)

                else:
                    if item['type'] == 'image':
                        clip_dur = item.get('value', 5.0)
                        clip = ImageClip(item['path']).set_duration(clip_dur)

                    else:
                        # ── ROBUST VIDEO LOADING ──────────────────────────────────
                        # MoviePy 1.x FFMPEG_VideoReader calls read_frame() during
                        # __init__ to detect resolution — this is where "failed to
                        # read first frame" fires on Windows MP4s, especially after
                        # a split/cut sets clip_end near the true EOF.
                        #
                        # Strategy:
                        #  1. Use ffprobe (ships with ffmpeg) to get duration without
                        #     decoding any frames — totally safe.
                        #  2. Clamp clip_start / clip_end 200ms away from 0 and EOF
                        #     so MoviePy's subclip never seeks to a boundary frame.
                        #  3. Open with audio=False to halve ffmpeg's init work.
                        #  4. Never call get_frame() as a probe — let write_videofile
                        #     do all decoding lazily.
                        # ─────────────────────────────────────────────────────────

                        path = item['path']
                        SAFE = 0.2   # 200ms safety margin — generous but invisible

                        # Step 1: get true duration via ffprobe subprocess
                        orig_dur = self._ffprobe_duration(path)

                        # Step 2: compute safe clip window
                        s = max(0.0, float(item.get('clip_start', 0.0)))
                        e = float(item.get('clip_end', 0.0))

                        safe_end = orig_dur - SAFE
                        if safe_end <= 0: safe_end = orig_dur * 0.99
                        if e <= 0.0 or e > safe_end: e = safe_end
                        s = min(s, safe_end - SAFE)
                        s = max(s, 0.0)

                        # Step 3: open with audio=False (avoid simultaneous A/V seek)
                        try:
                            raw_orig = VideoFileClip(path, audio=False)
                        except Exception as exc:
                            raise RuntimeError(
                                f"Could not open '{os.path.basename(path)}'.\n"
                                f"ffmpeg error: {exc}\n\n"
                                f"Try re-encoding with HandBrake (Web Optimised / Fast Start)."
                            )

                        keep_alive.append(raw_orig)
                        raw = raw_orig

                        # Re-attach audio separately — avoids the dual-seek init crash
                        try:
                            raw_audio = AudioFileClip(path)
                            keep_alive.append(raw_audio)
                            raw = raw.set_audio(raw_audio)
                        except Exception:
                            pass   # no audio track or audio unreadable — fine

                        # Step 4: subclip with clamped safe boundaries
                        if e > s:
                            raw = raw.subclip(s, e)

                        clip_dur = self._item_duration(item)
                        speed = float(item.get('speed', 1.0))

                        if speed != 1.0:
                            try: raw = raw.fx(vfx.speedx, speed)
                            except: pass

                        raw = raw.set_duration(clip_dur)

                        if item.get('muted', False):
                            raw = raw.without_audio()
                        else:
                            if getattr(raw, "audio", None):
                                new_audio = self._apply_audio_filters(raw.audio, item, clip_dur)
                                raw = raw.set_audio(new_audio)
                        clip = raw

                clip = clip.set_duration(clip_dur)
                rot = item.get('rotation', 0)
                flip_h = item.get('flip_h', False)
                flip_v = item.get('flip_v', False)
                clip = self.safe_transform(clip, rot, flip_h, flip_v)
                clip = clip.set_duration(clip_dur)

                if item['type'] != 'title':
                    if auto_rotate:
                        if target_w > target_h and clip.w < clip.h:
                            clip = self.safe_transform(clip, 90, False, False)
                        elif target_w < target_h and clip.w > clip.h:
                            clip = self.safe_transform(clip, -90, False, False)
                    if smart_fill:
                        sf = max(target_w / clip.w, target_h / clip.h) * scale_val
                        clip = clip.fx(vfx.resize, sf)
                        clip = clip.fx(vfx.crop,
                                       x_center=clip.w/2, y_center=clip.h/2,
                                       width=target_w, height=target_h)
                    else:
                        clip = clip.fx(vfx.resize,
                                       min(target_w / clip.w, target_h / clip.h) * scale_val)

                    vlayers = [
                        ColorClip(size=(target_w, target_h), color=(0, 0, 0)).set_duration(clip_dur),
                        clip.set_position("center")
                    ]

                    if item.get('text'):
                        lt_layers = []
                        style = item.get('lt_style', '')
                        lt_dur = item.get('text_end', 3.0) - item.get('text_start', 0.0)
                        if style == 'Purple Designer Box':
                            lt_layers = self.build_designer_lower_third(item['text'], target_w, target_h, clip_dur, lt_dur)
                        elif style == 'Static Aurora Tile (Bracket)':
                            lt_layers = self.build_tile_lower_third(item['text'], target_w, target_h, clip_dur, lt_dur)
                        else:
                            lt_layers = self.build_magical_lower_third(item['text'], target_w, target_h, clip_dur, lt_dur)
                        for l in lt_layers:
                            vlayers.append(l.set_start(item.get('text_start', 0.0)))
                    clip = CompositeVideoClip(vlayers).set_duration(clip_dur)

                else:
                    if rot != 0 or flip_h or flip_v or scale_val != 1.0:
                        if smart_fill:
                            sf = max(target_w / clip.w, target_h / clip.h) * scale_val
                            clip = clip.fx(vfx.resize, sf)
                            clip = clip.fx(vfx.crop,
                                           x_center=clip.w/2, y_center=clip.h/2,
                                           width=target_w, height=target_h)
                        else:
                            clip = clip.fx(vfx.resize,
                                           min(target_w / clip.w, target_h / clip.h) * scale_val)
                        clip = CompositeVideoClip(
                            [ColorClip(size=(target_w, target_h), color=(0, 0, 0)).set_duration(clip_dur),
                             clip.set_position("center")]
                        ).set_duration(clip_dur)

                if item.get('effect') == 'gold_outline' and self.effect_global_enabled.get():
                    clip = clip.fl(lambda gf, tt: self.apply_dreamy_angel_effect(gf(tt), item, tt))

                if item.get('effect_thug_life_enabled', False):
                    clip = clip.fl(lambda gf, tt: self.apply_thug_life_effect(gf(tt), item, tt))

                if item.get('effect_film_burn_enabled', False):
                    clip = clip.fl(lambda gf, tt: self.apply_film_burn_effect(gf(tt), item, tt))

                if item.get('effect_sun_glare_enabled', False):
                    clip = clip.fl(lambda gf, tt: self.apply_sun_glare_effect(gf(tt), item, tt))

                if item.get('effect_x_flare_enabled', False):
                    clip = clip.fl(lambda gf, tt: self.apply_x_flare_effect(gf(tt), item, tt))

                if item.get('effect_light_flash_enabled', False):
                    clip = clip.fl(lambda gf, tt: self.apply_light_flash_effect(gf(tt), item, tt))

                if item.get('effect_canopy_enabled', False):
                    clip = clip.fl(lambda gf, tt: self.apply_canopy_effect(gf(tt), item, tt))

                if item.get('effect_3d_text_enabled', False):
                    clip = clip.fl(lambda gf, tt: self.apply_3d_text_tracking_effect(gf(tt), item, tt))

                if item.get('effect_motion_track_enabled', False):
                    clip = clip.fl(lambda gf, tt: self.apply_motion_track_effect(gf(tt), item, tt))

                # ── COLOR FILTER (export) ─────────────────────────────────
                try:
                    filter_on = self._filter_global_enabled.get()
                    per_clip = item.get('filter_enabled', False)
                    if per_clip:
                        filter_on = True
                    if filter_on:
                        if per_clip:
                            fs = item.get('filter_style', 'Cinematic Warm')
                            fi = item.get('filter_intensity', 1.0)
                            fw = item.get('filter_warmth', 0.5)
                            fsat = item.get('filter_saturation', 1.0)
                            fb = item.get('filter_fade_blacks', 0.15)
                        else:
                            fs = self._filter_style.get()
                            fi = self._filter_intensity.get()
                            fw = self._filter_warmth.get()
                            fsat = self._filter_saturation.get()
                            fb = self._filter_fade_blacks.get()
                        _fs, _fi, _fw, _fsat, _fb = fs, fi, fw, fsat, fb
                        clip = clip.fl(lambda gf, tt, __fs=_fs, __fi=_fi, __fw=_fw, __fsat=_fsat, __fb=_fb:
                                       self.apply_color_filter(gf(tt), __fs, __fi, __fw, __fsat, __fb))
                except Exception:
                    pass
                # ───────────────────────────────────────────────────────────

                # ── HIGHLIGHT CLIP EFFECT (slowmo_zoom / reverse) ──────────
                if item.get('_highlight_effect') and item['type'] == 'video':
                    hl_clips = self._apply_highlight_regions_export(clip, item, target_w, target_h)
                    # Distribute the total start offset across the segments
                    # so each segment follows the previous one in time
                    seg_start = t_start
                    for hc in hl_clips:
                        hc = hc.set_start(seg_start)
                        final_clips.append(hc)
                        seg_start += hc.duration
                else:
                    clip = clip.set_start(t_start)
                    final_clips.append(clip)

            # ── APPLY TRANSITIONS BETWEEN CLIPS ────────────────────────────
            td = self.TRANSITION_DUR
            if td > 0 and len(final_clips) > 1:
                final_clips = self._apply_export_transitions(final_clips, target_w, target_h)
            # ─────────────────────────────────────────────────────────────────

            final_video = CompositeVideoClip(final_clips, size=(target_w, target_h))

            audio_layers = []
            if final_video.audio:
                audio_layers.append(final_video.audio)

            for aud in self.bgm_tracks:
                if aud.get('muted', False):
                    continue
                ac_orig = AudioFileClip(aud['path'])
                keep_alive.append(ac_orig)

                a_clip = ac_orig
                orig_dur = getattr(a_clip, 'duration', 10.0)
                s = max(0.0, float(aud.get('clip_start', 0.0)))
                e = float(aud.get('clip_end', 0.0))

                if orig_dur:
                    if e <= 0.0 or e > orig_dur: e = orig_dur
                    s = min(s, orig_dur - 0.01)

                if e > s:
                    a_clip = a_clip.subclip(s, e)

                target_dur = a_clip.duration
                a_clip = self._apply_audio_filters(a_clip, aud, target_dur)
                a_clip = a_clip.set_start(float(aud.get('start_offset', 0.0)))
                audio_layers.append(a_clip)

            if audio_layers:
                mixed_audio = CompositeAudioClip(audio_layers)
                mixed_audio = mixed_audio.set_duration(final_video.duration)
                final_video = final_video.set_audio(mixed_audio)

            progress_logger = _TkExportProgressLogger(
                lambda pct: self.root.after(0, self._on_export_progress, pct)) if ProgressBarLogger else None
            try:
                final_video.write_videofile(
                    save_path, codec="libx264", audio_codec="aac",
                    fps=30, preset="ultrafast",
                    logger=(progress_logger if progress_logger is not None else 'bar')
                )
            except TypeError:
                # Older/different moviepy build with an incompatible logger signature —
                # fall back to the default so export still completes either way.
                final_video.write_videofile(
                    save_path, codec="libx264", audio_codec="aac",
                    fps=30, preset="ultrafast"
                )
            self.root.after(0, self.on_merge_success, save_path)

        except Exception as e:
            self.root.after(0, self.on_merge_error, str(e))
        finally:
            if 'final_video' in locals():
                try: final_video.close()
                except: pass
            for c in keep_alive:
                try:
                    if getattr(c, 'audio', None): c.audio.close()
                    c.close()
                except: pass

    def on_merge_success(self, save_path):
        self.status_label.config(text="Export complete ✓", fg="green")
        if hasattr(self, 'export_btn'):
            self.export_btn.config(state=tk.NORMAL)
        messagebox.showinfo("Export Success", f"Saved to:\n{save_path}")

    def on_merge_error(self, err):
        self.status_label.config(text="Export failed ✖", fg="red")
        if hasattr(self, 'export_btn'):
            self.export_btn.config(state=tk.NORMAL)
        messagebox.showerror("Error", str(err))
