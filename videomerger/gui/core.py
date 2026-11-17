"""Application lifecycle, undo history, clip cache and navigation.

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


class CoreMixin:
    """Application lifecycle, undo history, clip cache and navigation."""

    def __init__(self, root):
        self.root = root
        self.root.title("Ultimate NLE Studio Pro")
        # Adaptive window size — fill 90% of screen but cap at 1500x900
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        win_w = min(1500, int(screen_w * 0.92))
        win_h = min(900, int(screen_h * 0.90))
        self.root.geometry(f"{win_w}x{win_h}")
        self.root.configure(bg=C["bg"])
        self.root.minsize(1000, 600)
        self._win_w = win_w

        self.media_queue = []
        self.bgm_tracks = []
        
        # --- UNDO / REDO STATE STACKS ---
        self.undo_stack = []
        self.redo_stack = []

        self.selected_idx = None
        self.selected_audio_idx = None

        self.waveforms = {}
        self._clip_cache = {}
        self._clip_cache_order = []
        self._clip_cache_max = 12
        self._img_cache = {}
        self.preview_img = None
        self._mp_segmentor = None
        self._mp_available = False
        self._yolo_model = None
        self._pending_filmstrips = []
        self._filmstrip_bg_active = False

        # --- FILTER STATE ---
        self._filter_global_enabled = tk.BooleanVar(value=False)
        self._filter_style = tk.StringVar(value="Cinematic Warm")
        self._filter_intensity = tk.DoubleVar(value=1.0)
        self._filter_warmth = tk.DoubleVar(value=0.5)
        self._filter_saturation = tk.DoubleVar(value=1.0)
        self._filter_fade_blacks = tk.DoubleVar(value=0.15)
        self._filter_per_clip = tk.BooleanVar(value=False)
        self._filter_clip_name = tk.StringVar(value="All clips (global)")

        self.playhead_t = tk.DoubleVar(value=0.0)
        self.is_playing = False
        self.play_thread = None
        self.timeline_dirty = True
        self.audio_ready = False
        self.temp_audio_path = f"temp_preview_audio_{int(time.time()*1000)}.wav"

        self._drag_item = None
        self._drag_env_pt = None   
        self._drag_start_x = 0
        self._drag_orig_start = 0.0
        self._is_scrubbing = False
        self._drag_state_saved = False 
        self._preview_job = None

        # --- TIMELINE REDRAW THROTTLE (keeps clip/handle dragging smooth) ---
        self._last_timeline_refresh = 0.0
        self._timeline_refresh_pending = None

        # --- DEBOUNCE / LOW-RES PREVIEW STATE ---
        self._debounce_job = None
        self._final_preview_job = None
        self._interactive_mode = False
        self._preview_base_cache = {}   # {(item_key, local_t): np.ndarray}
        self._preview_cache_max = 6
        self._3d_text_texture_cache = {}   # {(text,color,depth,style,t_key): PIL.Image RGBA}
        self._last_preview_key = None
        self._playback_preview_interval = 0.066  # ~15fps for playback

        self._mute_drawing = False
        self._mute_draw_start_t = 0.0

        # --- HIGHLIGHT REGION DRAW STATE ---
        self._highlight_drawing = False
        self._highlight_draw_start_t = 0.0

        # Region-marker state (two free-floating markers inside a clip)
        self._trim_drag = None        # ('A'|'B', ctype, cidx)
        self._trim_state_saved = False
        self._trim_marker_A = {}      # {(ctype,cidx): t_local}
        self._trim_marker_B = {}      # {(ctype,cidx): t_local}
        self._extend_drag = None      # ('left'|'right', ctype, cidx) — extend/shrink clip edge
        self._extend_state_saved = False
        self._audio_multiselect = []  # list of bgm indices selected with Ctrl+Click (for Speech Ease)
        self._handle_mode = "trim"    # "trim" = A/B cut markers active | "extend" = edge drag active
        self._env_pt_popup = None     # active per-point volume Toplevel

        self._build_ui()
        self.refresh_timeline()

        # Preload heavy dependencies in background — UI stays responsive
        threading.Thread(target=self._preload_heavy_deps, daemon=True).start()

    def _preload_heavy_deps(self):
        _ensure_moviepy()
        _ensure_pygame()
        self.root.after(0, self.refresh_timeline)

    def _clip_cache_put(self, key, clip):
        if key in self._clip_cache:
            self._clip_cache_order.remove(key)
        elif len(self._clip_cache) >= self._clip_cache_max:
            old_key = self._clip_cache_order.pop(0)
            old_clip = self._clip_cache.pop(old_key, None)
            if old_clip is not None:
                try:
                    if getattr(old_clip, 'audio', None): old_clip.audio.close()
                    old_clip.close()
                except: pass
        self._clip_cache[key] = clip
        self._clip_cache_order.append(key)

    def _clip_cache_clear(self):
        for k, v in list(self._clip_cache.items()):
            try:
                if getattr(v, 'audio', None): v.audio.close()
                v.close()
            except: pass
        self._clip_cache.clear()
        self._clip_cache_order.clear()
        self._img_cache.clear()

    def _close_cached_clip_for(self, path):
        if path in self._clip_cache:
            old = self._clip_cache.pop(path, None)
            if path in self._clip_cache_order:
                self._clip_cache_order.remove(path)
            if old is not None:
                try:
                    if getattr(old, 'audio', None): old.audio.close()
                    old.close()
                except: pass

    def save_state(self):
        clean_bgm = [{k: v for k, v in b.items() if not k.startswith('_')} for b in self.bgm_tracks]
        
        state = {
            'media': copy.deepcopy(self.media_queue),
            'bgm': copy.deepcopy(clean_bgm)
        }
        self.undo_stack.append(state)
        self.redo_stack.clear()
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)

    def undo(self):
        if not self.undo_stack:
            return messagebox.showinfo("Undo", "Nothing to undo.")
            
        clean_bgm = [{k: v for k, v in b.items() if not k.startswith('_')} for b in self.bgm_tracks]
        current_state = {
            'media': copy.deepcopy(self.media_queue),
            'bgm': copy.deepcopy(clean_bgm)
        }
        self.redo_stack.append(current_state)
        
        prev_state = self.undo_stack.pop()
        self.media_queue = copy.deepcopy(prev_state['media'])
        self.bgm_tracks = copy.deepcopy(prev_state['bgm'])
        
        self.selected_idx = None
        self.selected_audio_idx = None
        self.timeline_dirty = True
        self.update_global_preview()
        self.render_inspector()
        self.refresh_effects_tab()
        self.refresh_timeline()
        self._refresh_audio_list()

    def redo(self):
        if not self.redo_stack:
            return messagebox.showinfo("Redo", "Nothing to redo.")
            
        clean_bgm = [{k: v for k, v in b.items() if not k.startswith('_')} for b in self.bgm_tracks]
        current_state = {
            'media': copy.deepcopy(self.media_queue),
            'bgm': copy.deepcopy(clean_bgm)
        }
        self.undo_stack.append(current_state)
        
        next_state = self.redo_stack.pop()
        self.media_queue = copy.deepcopy(next_state['media'])
        self.bgm_tracks = copy.deepcopy(next_state['bgm'])
        
        self.selected_idx = None
        self.selected_audio_idx = None
        self.timeline_dirty = True
        self.update_global_preview()
        self.render_inspector()
        self.refresh_effects_tab()
        self.refresh_timeline()
        self._refresh_audio_list()

    def go_to_start(self): self._set_playhead(0.0)

    def rewind_5(self): self._set_playhead(max(0.0, self.playhead_t.get() - 5.0))

    def forward_5(self): self._set_playhead(min(self._total_duration(), self.playhead_t.get() + 5.0))

    def go_to_end(self): self._set_playhead(self._total_duration())

    def zoom_in(self): self.PPS = min(self.MAX_PPS, int(self.PPS * 1.5)); self.refresh_timeline()

    def zoom_out(self): self.PPS = max(self.MIN_PPS, int(self.PPS / 1.5)); self.refresh_timeline()

    def _total_duration(self):
        end_times = [0.0]
        for item in self.media_queue:
            end_times.append(item.get("tl_start", 0.0) + self._item_duration(item))
        for bgm in self.bgm_tracks:
            end_times.append(bgm.get("start_offset", 0.0) + bgm.get("duration", 10.0))
        return max(end_times)

    def _item_duration(self, item):
        if item["type"] == "video":
            s = float(item.get("clip_start", 0.0))
            e = float(item.get("clip_end", 0.0))
            if e <= s:
                try:
                    if item['path'] not in self._clip_cache:
                        self._clip_cache_put(item['path'], VideoFileClip(item['path']))
                    dur = self._clip_cache[item['path']].duration
                except:
                    dur = 5.0
            else:
                dur = e - s
            return dur / max(0.1, float(item.get("speed", 1.0)))
        return float(item.get("value", 5.0))

    def _bind_scroll_children(self, parent, canvas):
        """Recursively bind mousewheel on all children so the audio
        panel scrolls even when the mouse is over a label or button.
        """
        def _scroll(e): canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        def _bind(w):
            try:
                w.bind("<MouseWheel>", _scroll)
                for child in w.winfo_children():
                    _bind(child)
            except Exception:
                pass
        _bind(parent)
