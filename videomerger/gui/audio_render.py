"""Audio cutting and MoviePy preview-mix construction.

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


class AudioRenderMixin:
    """Audio cutting and MoviePy preview-mix construction."""

    def _cut_audio_region(self):
        cidx = self.selected_audio_idx
        key  = ("audio", cidx)
        if key not in self._trim_marker_A or key not in self._trim_marker_B:
            return messagebox.showwarning("Cut Region",
                "Select an audio clip first — markers A and B will appear at its edges.\n"
                "Drag the markers inward to define the region to remove.")
        tA = self._trim_marker_A[key]
        tB = self._trim_marker_B[key]
        t_start, t_end = min(tA, tB), max(tA, tB)
        # Guard: must have dragged markers to actually form a region
        clip_dur = self._get_clip_display_dur("audio", cidx)
        if t_end - t_start < 0.1:
            return messagebox.showwarning("Cut Region",
                "Drag the A and B markers inward to define a region to cut.\n"
                "(They currently span the full clip or are too close together.)")
        if t_end - t_start >= clip_dur - 0.1:
            return messagebox.showwarning("Cut Region",
                "Region covers the entire clip. Drag one marker inward to keep part of the audio.")
        self._region_delete("audio", cidx, t_start, t_end)
        self._trim_marker_A.pop(key, None)
        self._trim_marker_B.pop(key, None)

    def execute_cut(self):
        # Handle audio cut via markers
        if self.selected_audio_idx is not None:
            self._cut_audio_region()
            return
        if self.selected_idx is None: return
        # Use A/B markers as cut region boundaries for video
        cidx = self.selected_idx
        key  = ("video", cidx)
        if key in self._trim_marker_A and key in self._trim_marker_B:
            tA = self._trim_marker_A[key]
            tB = self._trim_marker_B[key]
            t_start, t_end = min(tA, tB), max(tA, tB)
            item = self.media_queue[cidx]
            # Convert local marker time to inspector clip_start/clip_end seconds
            cs_offset = float(item.get("clip_start", 0.0))
            self.ins_c_start.set(cs_offset + t_start)
            self.ins_c_end.set(cs_offset + t_end)
        self.save_state()
        item = self.media_queue[self.selected_idx]
        s = self.ins_c_start.get()
        e = self.ins_c_end.get()

        if s >= e: return messagebox.showwarning("Error", "Cut Start must be before Cut End.")

        max_dur = 10.0
        if item['type'] == 'video' and item.get('path'):
            try:
                if item['path'] not in self._clip_cache:
                    self._clip_cache_put(item['path'], VideoFileClip(item['path']))
                max_dur = self._clip_cache[item['path']].duration
            except: pass
        elif item['type'] != 'video':
            max_dur = item.get('value', 5.0)

        part_1 = copy.deepcopy(item)
        part_2 = copy.deepcopy(item)

        # FIX: apply 50ms safety margin on all video clip boundaries so
        # subclip() never lands exactly on or past the real EOF
        SAFE_MARGIN = 0.05
        if item['type'] == 'video':
            safe_max = max_dur - SAFE_MARGIN
            part_1['clip_end'] = min(float(s), safe_max)
            part_2['clip_start'] = min(float(e), safe_max)
            raw_end = max_dur if item.get('clip_end', 0.0) == 0.0 else float(item.get('clip_end'))
            part_2['clip_end'] = min(raw_end, safe_max)
            # guard: clip_end must always exceed clip_start
            if part_1['clip_end'] <= part_1.get('clip_start', 0.0):
                part_1['clip_end'] = part_1.get('clip_start', 0.0) + SAFE_MARGIN
            if part_2['clip_end'] <= part_2['clip_start']:
                part_2['clip_end'] = part_2['clip_start'] + SAFE_MARGIN
        else:
            part_1['value'] = s
            part_2['value'] = max_dur - e

        new_queue = []
        for i, m in enumerate(self.media_queue):
            if i == self.selected_idx:
                if (part_1['type'] == 'video' and part_1['clip_end'] > part_1.get('clip_start', 0.0)) or (part_1['type'] != 'video' and part_1['value'] > 0.1):
                    new_queue.append(part_1)
                if (part_2['type'] == 'video' and part_2['clip_end'] > part_2.get('clip_start', 0.0)) or (part_2['type'] != 'video' and part_2['value'] > 0.1):
                    new_queue.append(part_2)
            else:
                new_queue.append(m)

        self.media_queue = new_queue
        self.selected_idx = None
        self.timeline_dirty = True
        self.refresh_timeline()
        self.update_global_preview()
        self.render_inspector()

    def _eval_vol_envelope(self, clip_dict, time_frac):
        env = clip_dict.get("vol_envelope", [])
        if not env: return float(clip_dict.get("volume", 1.0))
        env_s = sorted(env, key=lambda p: p[0])
        if time_frac <= env_s[0][0]: return float(env_s[0][1])
        if time_frac >= env_s[-1][0]: return float(env_s[-1][1])
        for i in range(len(env_s) - 1):
            t0, v0 = env_s[i]
            t1, v1 = env_s[i+1]
            if t0 <= time_frac <= t1:
                alpha = (time_frac - t0) / max(1e-9, t1 - t0)
                alpha = 0.5 - 0.5 * math.cos(alpha * math.pi)
                return float(v0 + alpha * (v1 - v0))
        return float(clip_dict.get("volume", 1.0))

    def _apply_audio_filters(self, audio_clip, clip_dict, total_dur):
        # ── RADIO-STATIC SPACER ──────────────────────────────────────────────
        # Speech-pause spacers get their audio replaced entirely with band-passed
        # white noise at a very low level — like a radio channel switching.
        # The actual audio from the source file is discarded.
        if clip_dict.get("is_speech_pause_spacer"):
            # ── BREATHING-MIMICKING NOISE GENERATOR ─────────────────────────
            # Uses the detected breathing amplitude pattern from the source
            # clip to modulate soft white noise — so the pause sounds like
            # the speaker breathing rather than static or silence.
            FPS       = 44100
            breath_vol = float(clip_dict.get("breath_vol", 0.12))
            pattern    = clip_dict.get("breathing_pattern", None)

            if pattern is None or len(pattern) < 2:
                # No pattern yet — use a gentle sine-based breath shape
                t_syn = np.linspace(0, 4 * np.pi, 200)
                pattern = (0.5 - 0.5 * np.cos(t_syn)) ** 1.4
                pattern = pattern.astype(np.float32)

            pat_len = len(pattern)

            def make_breath_frame(get_frame, t):
                if isinstance(t, np.ndarray):
                    n = len(t)
                    # Map sample times → pattern indices (tile pattern over duration)
                    frac   = (t / max(1e-9, total_dur)) % 1.0
                    p_idx  = np.clip((frac * pat_len).astype(int), 0, pat_len - 1)
                    breath_env = pattern[p_idx]   # amplitude shape from detected breath

                    # Soft band-limited noise (low-pass below 400 Hz = breath rumble)
                    noise = np.random.uniform(-1.0, 1.0, n).astype(np.float32)
                    # Vectorised cumsum low-pass (integrator) — keeps the low "whoosh"
                    lp = np.cumsum(noise) / max(1, n)
                    lp -= lp.mean()
                    mx = np.abs(lp).max()
                    if mx > 1e-9: lp /= mx

                    # Mix low breath rumble with very faint high hiss
                    hiss = noise * 0.08
                    sig  = (lp * 0.92 + hiss) * breath_env * breath_vol
                    return np.column_stack((sig, sig))
                else:
                    frac    = float(t / max(1e-9, total_dur)) % 1.0
                    p_idx   = int(frac * pat_len) % pat_len
                    env_val = float(pattern[p_idx])
                    val     = float(np.random.uniform(-1.0, 1.0)) * env_val * breath_vol
                    return np.array([val, val], dtype=np.float32)

            return audio_clip.fl(make_breath_frame, keep_duration=False).set_duration(total_dur)
        # ─────────────────────────────────────────────────────────────────────

        env = clip_dict.get("vol_envelope", [])
        mute_regions = clip_dict.get("mute_regions", [])
        base_vol = float(clip_dict.get("volume", 1.0))
        # Build per-point gain lookup: maps time_frac → instantaneous multiplier
        # Applied as a sudden jump at that exact fraction, independent of the curve.
        pt_gains_raw = clip_dict.get("pt_gains", {})
        env_sorted = sorted(env, key=lambda p: p[0]) if env else []
        pt_gain_times = {}  # t_frac → gain value
        for idx_s, (tf, _) in enumerate(env_sorted):
            gain = float(pt_gains_raw.get(str(idx_s), 1.0))
            if abs(gain - 1.0) > 0.001:
                pt_gain_times[tf] = gain
        
        def safe_audio_filter(get_frame, t):
            try:
                f = np.array(get_frame(t), dtype=np.float32)
                if f.ndim == 0:
                    f = np.array([f, f], dtype=np.float32)
            except Exception:
                nch = getattr(audio_clip, 'nchannels', 2)
                if isinstance(t, np.ndarray): return np.zeros((len(t), nch), dtype=np.float32)
                else: return np.zeros(nch, dtype=np.float32)
                
            if isinstance(t, np.ndarray):
                if f.ndim == 1:
                    f = np.column_stack((f, f)) 
                    
                if len(f) < len(t):
                    pad_len = len(t) - len(f)
                    f = np.pad(f, ((0, pad_len), (0, 0)), 'constant')
                elif len(f) > len(t):
                    f = f[:len(t)]
                    
                np.nan_to_num(f, copy=False) 
                    
                if env and len(env) >= 2:
                    vols = np.array([self._eval_vol_envelope(clip_dict, ti / max(1e-9, total_dur)) for ti in t], dtype=np.float32)
                else:
                    vols = np.full(len(t), base_vol, dtype=np.float32)
                    
                if mute_regions:
                    for (m_start, m_end) in mute_regions:
                        vols[(t >= m_start) & (t <= m_end)] = 0.0

                # Apply per-point instantaneous gain jumps (independent of curve)
                if pt_gain_times:
                    for tf, gain in pt_gain_times.items():
                        t_abs = tf * max(1e-9, total_dur)
                        # Apply gain to a 1-sample-wide window around that time
                        mask = np.abs(t - t_abs) < (1.0 / 44100.0 * 2)
                        vols[mask] = gain
                        
                return (f.T * vols).T 
            else:
                if f.ndim == 0:
                    f = np.array([f, f], dtype=np.float32)
                elif f.ndim == 1 and len(f) == 1:
                    f = np.array([f[0], f[0]], dtype=np.float32)
                    
                if mute_regions:
                    for (m_start, m_end) in mute_regions:
                        if m_start <= t <= m_end: return f * 0.0
                        
                v = self._eval_vol_envelope(clip_dict, t / max(1e-9, total_dur)) if env and len(env) >= 2 else base_vol
                return f * v

        return audio_clip.fl(safe_audio_filter, keep_duration=False).set_duration(total_dur)

    def _build_preview_audio(self):
        _ensure_pygame()
        _ensure_moviepy()
        self.audio_ready = False

        if HAS_PYGAME:
            try: pygame.mixer.music.unload()
            except: pass

        for f in os.listdir():
            if f.startswith("temp_preview_audio_") and f.endswith(".wav"):
                try: os.remove(f)
                except: pass

        self.temp_audio_path = f"temp_preview_audio_{int(time.time()*1000)}.wav"

        audio_clips = []
        keep_alive = []
        
        try:
            for item in self.media_queue:
                if item['type'] == 'video' and not item.get('muted', False):
                    print(f"[AUDIO] Loading audio from: {item.get('name', item['path'])}")
                    try:
                        ac_orig = AudioFileClip(item['path'])
                        keep_alive.append(ac_orig)
                    except Exception:
                        continue 
                        
                    c = ac_orig
                    orig_dur = getattr(c, 'duration', 10.0)
                    s = max(0.0, float(item.get('clip_start', 0.0)))
                    e = float(item.get('clip_end', 0.0))
                    
                    if orig_dur:
                        if e <= 0.0 or e > orig_dur: e = orig_dur
                        s = min(s, orig_dur - 0.01)
                    
                    if e > s: 
                        c = c.subclip(s, e)

                    speed = float(item.get('speed', 1.0))
                    if speed != 1.0:
                        try: c = c.fx(vfx.speedx, speed)
                        except: pass
                        
                    target_dur = self._item_duration(item)
                    
                    new_audio = self._apply_audio_filters(c, item, target_dur)
                    new_audio = new_audio.set_start(float(item.get('tl_start', 0.0)))
                    audio_clips.append(new_audio)

            for bgm in self.bgm_tracks:
                if not bgm.get('muted', False):
                    ac_orig = AudioFileClip(bgm['path'])
                    keep_alive.append(ac_orig)
                    
                    ac = ac_orig
                    orig_dur = getattr(ac, 'duration', 10.0)
                    s = max(0.0, float(bgm.get('clip_start', 0.0)))
                    e = float(bgm.get('clip_end', 0.0))
                    
                    if orig_dur:
                        if e <= 0.0 or e > orig_dur: e = orig_dur
                        s = min(s, orig_dur - 0.01)
                        
                    if e > s: 
                        ac = ac.subclip(s, e)
                        
                    target_dur = ac.duration
                    
                    ac = self._apply_audio_filters(ac, bgm, target_dur)
                    ac = ac.set_start(float(bgm.get('start_offset', 0.0)))
                    audio_clips.append(ac)

            if audio_clips:
                comp = CompositeAudioClip(audio_clips)
                print(f"[AUDIO] Writing {len(audio_clips)} audio clips to {self.temp_audio_path}")
                comp.set_duration(self._total_duration()).write_audiofile(
                    self.temp_audio_path, fps=44100, nbytes=2, codec='pcm_s16le', logger=None
                )
                self.audio_ready = True
                print(f"[AUDIO] Audio ready: {self.temp_audio_path}")
            else:
                self.audio_ready = False
                print("[AUDIO] No audio clips found")

        except Exception as e:
            print(f"CRITICAL PREVIEW ERROR: {e}")
            traceback.print_exc()
            self.audio_ready = False
        finally:
            for c in keep_alive:
                try: c.close()
                except: pass
