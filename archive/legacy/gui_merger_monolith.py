import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import os
import time
import warnings
import numpy as np
import math
import copy
import traceback
import cv2

# --- SILENCE ANNOYING PILLOW WARNINGS ---
warnings.filterwarnings("ignore", category=DeprecationWarning)

import PIL.Image
from PIL import ImageTk, ImageDraw, ImageFont, ImageFilter

# --- PIL ANTIALIAS FIX FOR PILLOW >= 10.0.0 ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

# --- IMAGEMAGICK PATH ---
os.environ["IMAGEMAGICK_BINARY"] = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"

# --- HAAR CASCADE PATH (OpenCV 5.0 pip package ships without data files) ---
_HAAR_CASCADE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "")
_HAAR_CASCADE_PATH = os.path.join(_HAAR_CASCADE_DIR, "haarcascade_frontalface_default.xml")
if not os.path.isfile(_HAAR_CASCADE_PATH):
    # Fallback: try cv2.data path
    try:
        import cv2.data
        _cv2_cascade = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        if os.path.isfile(_cv2_cascade):
            _HAAR_CASCADE_PATH = _cv2_cascade
    except Exception:
        pass

# --- LAZY LOADING: moviepy & pygame imported on first use for fast startup ---
VideoFileClip = None
ImageClip = None
ColorClip = None
CompositeVideoClip = None
TextClip = None
AudioFileClip = None
CompositeAudioClip = None
VideoClip = None
concatenate_audioclips = None
AudioArrayClip = None
vfx = None
_MOVIEPY_LOADED = False

def _ensure_moviepy():
    global _MOVIEPY_LOADED, VideoFileClip, ImageClip, ColorClip, CompositeVideoClip
    global TextClip, AudioFileClip, CompositeAudioClip, VideoClip
    global concatenate_audioclips, AudioArrayClip, vfx
    if _MOVIEPY_LOADED:
        return
    from moviepy.editor import (
        VideoFileClip as _VFC, ImageClip as _IC, ColorClip as _CC,
        CompositeVideoClip as _CVC, TextClip as _TC,
        AudioFileClip as _AFC, CompositeAudioClip as _CAC,
        VideoClip as _VC, concatenate_audioclips as _concat
    )
    from moviepy.audio.AudioClip import AudioArrayClip as _AAC
    import moviepy.video.fx.all as _vfx
    VideoFileClip = _VFC
    ImageClip = _IC
    ColorClip = _CC
    CompositeVideoClip = _CVC
    TextClip = _TC
    AudioFileClip = _AFC
    CompositeAudioClip = _CAC
    VideoClip = _VC
    concatenate_audioclips = _concat
    AudioArrayClip = _AAC
    vfx = _vfx
    _MOVIEPY_LOADED = True

HAS_PYGAME = False
pygame = None

def _ensure_pygame():
    global HAS_PYGAME, pygame
    if HAS_PYGAME:
        return
    try:
        import pygame as _pg
        _pg.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
        pygame = _pg
        HAS_PYGAME = True
    except Exception as e:
        HAS_PYGAME = False
        print("WARNING: Pygame initialization failed. Live audio preview will be disabled.", e)

# --- LIVE EXPORT PROGRESS (hooks moviepy's proglog system back into the Tk UI) ---
try:
    from proglog import ProgressBarLogger
except Exception:
    ProgressBarLogger = None


class _TkExportProgressLogger(ProgressBarLogger if ProgressBarLogger else object):
    """Feeds moviepy's write_videofile progress back to the app so the
    status label can show a live percentage instead of a static 'please
    wait' message. on_progress(pct:int) is called from moviepy's render
    thread, so it must itself hop back to the Tk main thread."""

    def __init__(self, on_progress):
        if ProgressBarLogger:
            super().__init__()
        self.on_progress = on_progress
        self._last_pct = -1

    def bars_callback(self, bar, attr, value, old_value=None):
        try:
            total = self.bars[bar].get('total') or 0
            if attr == 'index' and total:
                pct = max(0, min(100, int(100 * value / total)))
                if pct != self._last_pct:
                    self._last_pct = pct
                    self.on_progress(pct)
        except Exception:
            pass

# ══════════════════════════════════════════════════════════════════
#  COLOUR TOKENS (Dark Studio Palette)
# ══════════════════════════════════════════════════════════════════
C = {
    "bg":           "#121212",
    "surface":      "#1a1a1a",
    "panel":        "#1e1e1e",
    "raised":       "#2a2a2a",
    "border":       "#333333",
    "accent":       "#00c8ff",
    "accent2":      "#ff3cac",
    "accent3":      "#39d353",
    "accent4":      "#FF9800",
    "danger":       "#E91E63",
    "text":         "#ffffff",
    "text_dim":     "#aaaaaa",
    "clip_video":   "#1e4d7a",
    "clip_bgm":     "#4a1a6e",
    "clip_mute":    "#8B0000",
    "waveform":     "#00c8ff"
}

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tw: return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tw, text=self.text, bg="#333", fg="white", font=("Arial", 9), relief="solid", bd=1, padx=6, pady=3).pack()

    def hide(self, _=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None

def icon_btn(parent, text, tip, cmd, bg=None, fg="white", w=None):
    kw = dict(text=text, command=cmd, bg=bg or C["raised"], fg=fg, font=("Segoe UI Emoji", 11), relief="flat", activebackground=C["border"], activeforeground="white", cursor="hand2", bd=0, padx=6, pady=4)
    if w: kw["width"] = w
    b = tk.Button(parent, **kw)
    Tooltip(b, tip)
    return b

def create_scroll_canvas(parent, bg_color):
    canvas = tk.Canvas(parent, bg=bg_color, highlightthickness=0)
    scroll = tk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview,
                          bg="#555555", troughcolor="#222222", activebackground="#888888",
                          width=16, bd=0, highlightthickness=0,
                          relief="flat")
    inner = tk.Frame(canvas, bg=bg_color)

    def _update_scrollregion(e=None):
        canvas.configure(scrollregion=canvas.bbox("all"))
    inner.bind("<Configure>", _update_scrollregion)
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scroll.set)

    def _on_configure(e):
        canvas.itemconfig("all", width=e.width)
        _update_scrollregion()
    canvas.bind("<Configure>", _on_configure)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_wheel(e):
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
    def _unbind_wheel(e):
        canvas.unbind_all("<MouseWheel>")
    canvas.bind("<Enter>", _bind_wheel)
    canvas.bind("<Leave>", _unbind_wheel)
    inner.bind("<Enter>",  _bind_wheel)
    inner.bind("<Leave>",  _unbind_wheel)
    parent.bind("<Enter>", _bind_wheel)
    parent.bind("<Leave>", _unbind_wheel)

    return canvas, inner

def extract_waveform_samples(path, n_samples=200):
    if not _MOVIEPY_LOADED:
        return None
    try:
        ext = path.lower().split(".")[-1]
        if ext in ("mp4", "mov", "avi", "mkv", "webm"):
            clip = VideoFileClip(path)
            audio = clip.audio
        else:
            audio = AudioFileClip(path)

        if audio is None: return None

        dur = audio.duration
        times = np.linspace(0, dur - 1/44100, n_samples)
        frames = np.array([audio.get_frame(t) for t in times])

        if frames.ndim == 2: frames = frames.mean(axis=1)
        frames = np.abs(frames)
        mx = frames.max()
        if mx > 0: frames /= mx

        if ext in ("mp4", "mov", "avi", "mkv", "webm"): clip.close()
        else: audio.close()

        return frames
    except Exception:
        return None

# ══════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════
class VideoMergerStudio:
    TRACK_H = 56
    AUDIO_TRACK_H = 40
    RULER_H = 20
    PPS = 80
    MIN_PPS = 20
    MAX_PPS = 400
    LABEL_W = 70
    TRANSITION_DUR = 0.75  # duration of transitions in seconds

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

    # ---------------------------------------------------------
    # CLIP CACHE MANAGEMENT (LRU eviction)
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # STATE MANAGEMENT (UNDO / REDO)
    # ---------------------------------------------------------
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

    def go_to_start(self): self._set_playhead(0.0)
    def rewind_5(self): self._set_playhead(max(0.0, self.playhead_t.get() - 5.0))
    def forward_5(self): self._set_playhead(min(self._total_duration(), self.playhead_t.get() + 5.0))
    def go_to_end(self): self._set_playhead(self._total_duration())
    def zoom_in(self): self.PPS = min(self.MAX_PPS, int(self.PPS * 1.5)); self.refresh_timeline()
    def zoom_out(self): self.PPS = max(self.MIN_PPS, int(self.PPS / 1.5)); self.refresh_timeline()

    # ==========================================
    # UI PANELS
    # ==========================================
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

    def apply_color_filter(self, frame, style="Cinematic Warm", intensity=1.0,
                           warmth=0.5, saturation=1.0, fade_blacks=0.15):
        """Apply a color grading filter to a numpy RGB frame.
        Returns the filtered frame as uint8."""

        def _draw_line(r0, c0, r1, c1, max_r, max_c):
            """Bresenham's line algorithm - returns (rows, cols) arrays."""
            rows = []
            cols = []
            dr = abs(r1 - r0)
            dc = abs(c1 - c0)
            sr = 1 if r0 < r1 else -1
            sc = 1 if c0 < c1 else -1
            err = dr - dc
            r, c = r0, c0
            while True:
                if 0 <= r < max_r and 0 <= c < max_c:
                    rows.append(r)
                    cols.append(c)
                if r == r1 and c == c1:
                    break
                e2 = 2 * err
                if e2 > -dc:
                    err -= dc
                    r += sr
                if e2 < dr:
                    err += dr
                    c += sc
            return np.array(rows, dtype=np.intp), np.array(cols, dtype=np.intp)
        if intensity <= 0:
            return frame
        f = frame.astype(np.float32)
        h, w = f.shape[:2]

        r, g, b = f[:,:,0], f[:,:,1], f[:,:,2]
        lum = 0.299 * r + 0.587 * g + 0.114 * b

        if style == "Cinematic Warm":
            # Based on the reference image: strong warm amber
            # Shadows: R+20%, G+5%, B-30%
            # Midtones: R+25%, G+5%, B-45%
            # Highlights: R+10%, G+5%, B-20%
            shadow_mask = np.clip(1.0 - lum / 85.0, 0, 1)
            mid_mask = np.exp(-((lum - 128)**2) / (2 * 50**2))
            high_mask = np.clip((lum - 170) / 85.0, 0, 1)

            r += (shadow_mask * 50 + mid_mask * 65 + high_mask * 25) * warmth
            g += (shadow_mask * 10 + mid_mask * 12 + high_mask * 10) * warmth
            b -= (shadow_mask * 80 + mid_mask * 115 + high_mask * 50) * warmth

        elif style == "Golden Hour":
            r += 30 * warmth
            g += 15 * warmth
            b -= 40 * warmth
            # Soft glow
            blur = cv2.GaussianBlur(f, (0, 0), 15)
            f = f * 0.7 + blur * 0.3

        elif style == "Vintage Film":
            r = r * 0.9 + 20
            g = g * 0.85 + 10
            b = b * 0.8 + 5
            # Lift blacks
            r = r * 0.85 + 30
            g = g * 0.85 + 25
            b = b * 0.85 + 20

        elif style == "Vintage Cam":
            # Keep original colors, add light leaks from corners + dark vignette
            Y, X = np.ogrid[:h, :w]

            # ── Light leaks from each corner (colored overlays) ──
            # Top-right: warm yellow/orange
            tr_x = np.clip(1.0 - X.astype(np.float32) / (w * 0.7), 0, 1)
            tr_y = np.clip(Y.astype(np.float32) / (h * 0.7), 0, 1)
            tr_mask = (tr_x * tr_y) ** 1.5
            r += tr_mask * 120 * warmth
            g += tr_mask * 50 * warmth
            b -= tr_mask * 20 * warmth

            # Bottom-right: strong red/orange
            br_x = np.clip(1.0 - X.astype(np.float32) / (w * 0.6), 0, 1)
            br_y = np.clip(1.0 - Y.astype(np.float32) / (h * 0.6), 0, 1)
            br_mask = (br_x * br_y) ** 1.3
            r += br_mask * 150 * warmth
            g += br_mask * 30 * warmth
            b -= br_mask * 40 * warmth

            # Top-left: pinkish/red
            tl_x = np.clip(X.astype(np.float32) / (w * 0.6), 0, 1)
            tl_y = np.clip(Y.astype(np.float32) / (h * 0.6), 0, 1)
            tl_mask = (tl_x * tl_y) ** 1.6
            r += tl_mask * 100 * warmth
            g -= tl_mask * 10 * warmth
            b += tl_mask * 20 * warmth

            # Bottom-left: warm yellow/green
            bl_x = np.clip(X.astype(np.float32) / (w * 0.7), 0, 1)
            bl_y = np.clip(1.0 - Y.astype(np.float32) / (h * 0.7), 0, 1)
            bl_mask = (bl_x * bl_y) ** 1.5
            r += bl_mask * 80 * warmth
            g += bl_mask * 60 * warmth
            b -= bl_mask * 30 * warmth

            # ── Dark vignette (darkens corners) ──
            cx, cy = w / 2.0, h / 2.0
            max_dist = np.sqrt(cx**2 + cy**2)
            dist = np.sqrt((X - cx)**2 + (Y - cy)**2) / max_dist
            vignette_mask = np.clip(dist ** 1.2, 0, 1)
            r -= vignette_mask * 50 * warmth
            g -= vignette_mask * 50 * warmth
            b -= vignette_mask * 45 * warmth

            # ── Very slight warm wash (preserve original colors) ──
            r += 8 * warmth
            g += 3 * warmth
            b -= 8 * warmth

            f[:,:,0] = r
            f[:,:,1] = g
            f[:,:,2] = b
            f = np.clip(f, 0, 255)

            # Convert to uint8 for reliable cv2 drawing, then back
            f_u8 = np.clip(f, 0, 255).astype(np.uint8)

            # Seed changes ~every 10 frames (at 30fps, 10 frames ≈ 0.33s)
            frame_seed = int(time.time() * 3) % (2**31)
            rng = np.random.RandomState(frame_seed)

            # ── Single straight vertical scratch (dark at top, fading to light at bottom) ──
            cx_pos = int(rng.randint(int(w * 0.1), int(w * 0.9)))
            brightness_top = int(rng.choice([140, 160, 180]))
            overlay = f_u8.copy()
            cv2.line(overlay, (cx_pos, 0), (cx_pos, h),
                     (brightness_top, brightness_top, brightness_top), 1, cv2.LINE_AA)
            # Gradient mask: 1.0 at top -> 0.0 at bottom
            grad = np.linspace(1.0, 0.0, h).astype(np.float32).reshape(h, 1)
            grad_mask3 = np.stack([grad] * 3, axis=-1)
            alpha_base = rng.uniform(0.45, 0.7)
            f_u8 = (overlay.astype(np.float32) * grad_mask3 * alpha_base +
                    f_u8.astype(np.float32) * (1.0 - grad_mask3 * alpha_base))
            f_u8 = np.clip(f_u8, 0, 255).astype(np.uint8)

            # ── Small C-shaped and crooked scratches (lightly visible) ──
            num_small = rng.randint(2, 5)
            for _ in range(num_small):
                sx = int(rng.randint(0, w))
                sy = int(rng.randint(0, h))
                scr_len = rng.randint(15, 50)
                brightness_s = int(rng.choice([170, 190, 210, 230]))
                if rng.randint(0, 2) == 0:
                    num_arc = rng.randint(3, 6)
                    radius = rng.randint(8, scr_len)
                    start_angle = rng.uniform(0, 2 * np.pi)
                    arc_span = rng.uniform(np.pi * 0.5, np.pi * 1.5)
                    pts = []
                    for a in range(num_arc):
                        angle = start_angle + (a / (num_arc - 1)) * arc_span
                        px = int(np.clip(sx + radius * np.cos(angle), 0, w - 1))
                        py = int(np.clip(sy + radius * np.sin(angle), 0, h - 1))
                        pts.append([px, py])
                    pts_arr = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
                else:
                    num_seg = rng.randint(2, 5)
                    pts = [[sx, sy]]
                    for _ in range(num_seg - 1):
                        angle = rng.uniform(0, 2 * np.pi)
                        seg_len = rng.randint(5, 20)
                        nx = int(np.clip(pts[-1][0] + seg_len * np.cos(angle), 0, w - 1))
                        ny = int(np.clip(pts[-1][1] + seg_len * np.sin(angle), 0, h - 1))
                        pts.append([nx, ny])
                    pts_arr = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
                overlay2 = f_u8.copy()
                cv2.polylines(overlay2, [pts_arr], False,
                              (brightness_s, brightness_s, brightness_s), 1, cv2.LINE_AA)
                alpha_s = rng.uniform(0.3, 0.5)
                f_u8 = cv2.addWeighted(overlay2, alpha_s, f_u8, 1.0 - alpha_s, 0)

            # ── Film grain (subtle) ──
            grain = rng.normal(0, 6, f_u8.shape).astype(np.int16)
            f_out = f_u8.astype(np.int16) + grain
            f = np.clip(f_out, 0, 255).astype(np.float32)
            # Sync r,g,b so the post-style block doesn't overwrite scratches
            r = f[:,:,0].copy()
            g = f[:,:,1].copy()
            b = f[:,:,2].copy()

        elif style == "BW Memories":
            # Convert to grayscale
            gray = (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float32)
            # Slight contrast boost
            gray = (gray - 128) * 1.15 + 128
            # Lift blacks slightly for faded film look
            gray = gray * 0.9 + 25
            r = gray.copy()
            g = gray.copy()
            b = gray.copy()
            f[:,:,0] = r
            f[:,:,1] = g
            f[:,:,2] = b
            f = np.clip(f, 0, 255)

            f_u8 = np.clip(f, 0, 255).astype(np.uint8)

            # Grain changes every frame
            grain_seed = int(time.time() * 1000000) % (2**31)
            rng_grain = np.random.RandomState(grain_seed)
            grain = rng_grain.normal(0, 10, f_u8.shape).astype(np.int16)
            f_u8 = np.clip(f_u8.astype(np.int16) + grain, 0, 255).astype(np.uint8)

            # Scratches + black dots change every 3 frames (~0.1s at 30fps)
            scratch_seed = int(time.time() * 10) % (2**31)
            rng = np.random.RandomState(scratch_seed)

            # ── Single straight vertical scratch (dark top, fading bottom) ──
            cx_pos = int(rng.randint(int(w * 0.1), int(w * 0.9)))
            brightness_top = int(rng.choice([180, 200, 220]))
            overlay = f_u8.copy()
            cv2.line(overlay, (cx_pos, 0), (cx_pos, h),
                     (brightness_top, brightness_top, brightness_top), 1, cv2.LINE_AA)
            grad = np.linspace(1.0, 0.0, h).astype(np.float32).reshape(h, 1)
            grad_mask3 = np.stack([grad] * 3, axis=-1)
            alpha_base = rng.uniform(0.4, 0.65)
            f_u8 = (overlay.astype(np.float32) * grad_mask3 * alpha_base +
                    f_u8.astype(np.float32) * (1.0 - grad_mask3 * alpha_base))
            f_u8 = np.clip(f_u8, 0, 255).astype(np.uint8)

            # ── Small C-shaped and crooked scratches (2-3) ──
            num_small = rng.randint(2, 4)
            for _ in range(num_small):
                sx = int(rng.randint(0, w))
                sy = int(rng.randint(0, h))
                scr_len = rng.randint(15, 50)
                brightness_s = int(rng.choice([170, 190, 210]))
                if rng.randint(0, 2) == 0:
                    num_arc = rng.randint(3, 6)
                    radius = rng.randint(8, scr_len)
                    start_angle = rng.uniform(0, 2 * np.pi)
                    arc_span = rng.uniform(np.pi * 0.5, np.pi * 1.5)
                    pts = []
                    for a in range(num_arc):
                        angle = start_angle + (a / (num_arc - 1)) * arc_span
                        px = int(np.clip(sx + radius * np.cos(angle), 0, w - 1))
                        py = int(np.clip(sy + radius * np.sin(angle), 0, h - 1))
                        pts.append([px, py])
                    pts_arr = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
                else:
                    num_seg = rng.randint(2, 5)
                    pts = [[sx, sy]]
                    for _ in range(num_seg - 1):
                        angle = rng.uniform(0, 2 * np.pi)
                        seg_len = rng.randint(5, 20)
                        nx = int(np.clip(pts[-1][0] + seg_len * np.cos(angle), 0, w - 1))
                        ny = int(np.clip(pts[-1][1] + seg_len * np.sin(angle), 0, h - 1))
                        pts.append([nx, ny])
                    pts_arr = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
                overlay2 = f_u8.copy()
                cv2.polylines(overlay2, [pts_arr], False,
                              (brightness_s, brightness_s, brightness_s), 1, cv2.LINE_AA)
                alpha_s = rng.uniform(0.3, 0.5)
                f_u8 = cv2.addWeighted(overlay2, alpha_s, f_u8, 1.0 - alpha_s, 0)

            # ── Black dust spots (grain-sized, change every 3 frames) ──
            num_dots = rng.randint(12, 25)
            for _ in range(num_dots):
                dx = int(rng.randint(0, w))
                dy = int(rng.randint(0, h))
                dc = int(rng.randint(10, 60))
                overlay3 = f_u8.copy()
                cv2.circle(overlay3, (dx, dy), 1, (dc, dc, dc), -1, cv2.LINE_AA)
                alpha_d = rng.uniform(0.25, 0.5)
                f_u8 = cv2.addWeighted(overlay3, alpha_d, f_u8, 1.0 - alpha_d, 0)

            f = f_u8.astype(np.float32)
            r = f[:,:,0].copy()
            g = f[:,:,1].copy()
            b = f[:,:,2].copy()

        elif style == "Teal & Orange":
            shadow_mask = np.clip(1.0 - lum / 100.0, 0, 1)
            highlight_mask = np.clip((lum - 155) / 100.0, 0, 1)
            # Teal shadows
            b += shadow_mask * 25 * warmth
            g += shadow_mask * 10 * warmth
            r -= shadow_mask * 10 * warmth
            # Orange highlights
            r += highlight_mask * 35 * warmth
            g += highlight_mask * 10 * warmth
            b -= highlight_mask * 25 * warmth

        elif style == "Bleach Bypass":
            gray = lum
            r = r * 0.5 + gray * 0.5
            g = g * 0.5 + gray * 0.5
            b = b * 0.5 + gray * 0.5
            # Increase contrast
            r = (r - 128) * 1.4 + 128
            g = (g - 128) * 1.4 + 128
            b = (b - 128) * 1.4 + 128

        elif style == "Cold Blue":
            r -= 15 * warmth
            g -= 5 * warmth
            b += 30 * warmth

        elif style == "Desaturated":
            r = r * 0.6 + lum * 0.4
            g = g * 0.6 + lum * 0.4
            b = b * 0.6 + lum * 0.4
            r += 5 * warmth
            b -= 5 * warmth

        elif style == "High Contrast":
            r = (r - 128) * 1.5 + 128
            g = (g - 128) * 1.5 + 128
            b = (b - 128) * 1.5 + 128
            r += 10 * warmth
            b -= 10 * warmth

        # Apply saturation
        if saturation != 1.0:
            gray = lum
            r = r * saturation + gray * (1 - saturation)
            g = g * saturation + gray * (1 - saturation)
            b = b * saturation + gray * (1 - saturation)

        # Fade blacks (lift shadows)
        if fade_blacks > 0:
            lift = fade_blacks * 255
            shadow_mask = np.clip(1.0 - lum / 128.0, 0, 1)
            r += shadow_mask * lift
            g += shadow_mask * lift * 0.9
            b += shadow_mask * lift * 0.8

        f[:,:,0] = r
        f[:,:,1] = g
        f[:,:,2] = b
        f = np.clip(f, 0, 255)

        # Blend with original based on intensity
        result = frame.astype(np.float32) * (1 - intensity) + f * intensity
        return np.clip(result, 0, 255).astype(np.uint8)

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

    def _on_effect_timing_changed(self):
        if self._effect_timing.get() == "custom":
            for w in self._effect_custom_frame.winfo_children():
                w.pack_configure()
        else:
            for w in self._effect_custom_frame.winfo_children():
                w.pack_forget()

    _VARIATION_DESCRIPTIONS = {
        'ethereal':       'Ethereal: volumetric light rays shoot outward from behind the subject using zoom blur. Classic dramatic backlight.',
        'neon':           'Neon: soft glowing aura surrounds the person with gentle light rays. Dreamy and otherworldly.',
        'spacy_game_rays':'Spacy Game Rays: heavenly backlit glow & light wrap. Smoky haze of light radiates from the subject with HDR overexposed gold-to-white bloom.',
        'gabriel_rays':   'Gabriel Rays: radiant golden-white bloom along the silhouette with volumetric light shafts and HDR tone-mapped glow.',
        'angel_rays':     'Angel Rays: pulsating concentric rings of golden light radiate outward from the subject. Heavenly glow with layered halo.',
    }

    def _update_variation_desc(self):
        var = self._effect_variation.get()
        desc = self._VARIATION_DESCRIPTIONS.get(var, '')
        try:
            self._variation_desc_label.config(text=desc)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════
    #  3D TEXT — INTERACTIVE ON-PREVIEW TRANSFORM (move / resize / rotate)
    #  The text sits on a 4-corner quad (TL, TR, BR, BL) stored as
    #  fractions of the frame. Dragging inside the quad moves it, dragging
    #  a corner handle reshapes/resizes it (this is also how you match the
    #  quad to a receding floor/wall so the text looks camera-tracked),
    #  and dragging the handle above the top edge rotates it.
    # ══════════════════════════════════════════════════════════════════

    _3D_TEXT_HANDLE_R = 14      # px, hit-test radius for corner/rotate handles (in preview display space)
    _3D_TEXT_ROT_HANDLE_LEN = 36  # px, how far the rotate handle sits above the top edge

    def _default_3d_text_quad(self):
        """A gentle ground-plane trapezoid: narrower/higher at the back,
        wider/lower at the front — a reasonable starting point that the
        user reshapes by dragging corners to match their footage."""
        return [[0.32, 0.40], [0.70, 0.40], [0.82, 0.62], [0.20, 0.62]]

    def _get_3d_text_quad(self, item):
        """Returns the item's 4-point quad (TL, TR, BR, BL) as fractions
        of the frame, migrating from the old single-point placement if
        that's all that's stored, else falling back to a default quad."""
        q = item.get('3d_text_quad')
        if q and len(q) == 4:
            return [list(p) for p in q]
        cx = item.get('3d_text_pos_x', 0.5)
        cy = item.get('3d_text_pos_y', 0.5)
        if '3d_text_pos_x' in item or '3d_text_pos_y' in item:
            fs = item.get('3d_text_font_size', 0.14)
            hw, hh = fs * 1.6, fs * 0.6
            return [[cx - hw * 0.85, cy - hh], [cx + hw * 0.85, cy - hh],
                    [cx + hw, cy + hh], [cx - hw, cy + hh]]
        return self._default_3d_text_quad()

    def _3d_text_quad_disp_pts(self, quad, disp_w, disp_h):
        return [(p[0] * disp_w, p[1] * disp_h) for p in quad]

    def _3d_text_rotate_handle_disp(self, corner_pts_disp):
        cx = sum(p[0] for p in corner_pts_disp) / 4.0
        cy = sum(p[1] for p in corner_pts_disp) / 4.0
        top_mid = ((corner_pts_disp[0][0] + corner_pts_disp[1][0]) / 2.0,
                   (corner_pts_disp[0][1] + corner_pts_disp[1][1]) / 2.0)
        dx, dy = top_mid[0] - cx, top_mid[1] - cy
        dist = max(1e-4, math.hypot(dx, dy))
        return (top_mid[0] + dx / dist * self._3D_TEXT_ROT_HANDLE_LEN,
                top_mid[1] + dy / dist * self._3D_TEXT_ROT_HANDLE_LEN), top_mid, (cx, cy)

    # Quad point order is [TL, TR, BR, BL]. Each edge handle is a single
    # drag gesture that moves that edge's two corners together along ONE
    # axis only — this is what makes tilting the text (top edge) or
    # angling it onto a side wall (left/right edge) a single comfortable
    # drag instead of having to nudge two corners independently.
    _3D_TEXT_EDGES = {
        'top':    ((0, 1), 'y'),   # drag vertically -> tilt (pitch)
        'bottom': ((3, 2), 'y'),
        'left':   ((0, 3), 'x'),   # drag horizontally -> angle onto a side wall
        'right':  ((1, 2), 'x'),
    }

    def _3d_text_edge_midpoints_disp(self, corner_pts_disp):
        mids = {}
        for name, (idxs, _axis) in self._3D_TEXT_EDGES.items():
            i, j = idxs
            mids[name] = ((corner_pts_disp[i][0] + corner_pts_disp[j][0]) / 2.0,
                          (corner_pts_disp[i][1] + corner_pts_disp[j][1]) / 2.0)
        return mids

    @staticmethod
    def _point_in_quad(x, y, pts):
        inside = False
        n = len(pts)
        j = n - 1
        for i in range(n):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-9) + xi):
                inside = not inside
            j = i
        return inside

    def _toggle_3d_text_drag(self):
        if self.selected_idx is None:
            return messagebox.showwarning("3D Text", "Select a clip first.")
        item = self.media_queue[self.selected_idx]
        if item['type'] not in ('video', 'image', 'placeholder', 'title'):
            return
        if not item.get('effect_3d_text_enabled', False):
            self._3d_text_enabled.set(True)
            item['effect_3d_text_enabled'] = True
        if item.get('3d_text_quad') is None:
            item['3d_text_quad'] = self._get_3d_text_quad(item)
        self._3d_text_place_active = not self._3d_text_place_active
        if self._3d_text_place_active:
            self._3d_text_place_btn.config(text="Stop Editing", bg="#b71c1c")
            self._3d_text_status.config(
                text="Move=inside • Resize=corner • Tilt/wall=yellow dot • Rotate=red dot", fg=C["accent"])
            self.preview_label.config(cursor="fleur")
            self.preview_label.bind("<ButtonPress-1>", self._on_3d_text_transform_start)
            self.preview_label.bind("<B1-Motion>", self._on_3d_text_transform_move)
            self.preview_label.bind("<ButtonRelease-1>", self._on_3d_text_transform_end)
            self._debounced_preview(interactive=True)
        else:
            self._3d_text_place_btn.config(text="Edit Text on Preview", bg=C["accent"])
            self._3d_text_status.config(
                text="Drag inside=move • corner=resize • yellow dot=tilt/wall • red dot=rotate",
                fg=C["text_dim"])
            self.preview_label.config(cursor="")
            self.preview_label.unbind("<ButtonPress-1>")
            self.preview_label.unbind("<B1-Motion>")
            self.preview_label.unbind("<ButtonRelease-1>")
            self.update_global_preview()

    def _on_3d_text_transform_start(self, event):
        if not self._3d_text_place_active or self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        disp_w = getattr(self, '_preview_disp_w', None)
        disp_h = getattr(self, '_preview_disp_h', None)
        if not disp_w or not disp_h:
            return
        ox = getattr(self, '_preview_offset_x', 0)
        oy = getattr(self, '_preview_offset_y', 0)
        tx, ty = event.x - ox, event.y - oy

        quad = self._get_3d_text_quad(item)
        corner_pts = self._3d_text_quad_disp_pts(quad, disp_w, disp_h)
        rot_handle, _, centroid = self._3d_text_rotate_handle_disp(corner_pts)
        edge_mids = self._3d_text_edge_midpoints_disp(corner_pts)

        mode, corner_idx, edge_name = None, None, None
        r = self._3D_TEXT_HANDLE_R
        if (tx - rot_handle[0]) ** 2 + (ty - rot_handle[1]) ** 2 <= (r + 4) ** 2:
            mode = 'rotate'
        else:
            for i, (hx, hy) in enumerate(corner_pts):
                if (tx - hx) ** 2 + (ty - hy) ** 2 <= r ** 2:
                    mode, corner_idx = 'corner', i
                    break
        if mode is None:
            for name, (mx, my) in edge_mids.items():
                if (tx - mx) ** 2 + (ty - my) ** 2 <= r ** 2:
                    mode, edge_name = 'edge', name
                    break
        if mode is None:
            if self._point_in_quad(tx, ty, corner_pts):
                mode = 'move'
            else:
                return  # clicked outside the text — ignore, don't start a drag

        self._3d_text_dragging = True
        self._3d_text_drag_mode = mode
        self._3d_text_drag_corner_idx = corner_idx
        self._3d_text_drag_edge_name = edge_name
        self._3d_text_drag_start_evt = (event.x, event.y)
        self._3d_text_drag_start_quad = quad
        self._3d_text_drag_start_centroid_frac = (centroid[0] / disp_w, centroid[1] / disp_h)
        self._3d_text_drag_start_angle = math.atan2(ty - centroid[1], tx - centroid[0])

    def _on_3d_text_transform_move(self, event):
        if not getattr(self, '_3d_text_dragging', False) or self.selected_idx is None:
            return
        disp_w = getattr(self, '_preview_disp_w', None)
        disp_h = getattr(self, '_preview_disp_h', None)
        if not disp_w or not disp_h:
            return
        ox = getattr(self, '_preview_offset_x', 0)
        oy = getattr(self, '_preview_offset_y', 0)
        quad0 = self._3d_text_drag_start_quad
        mode = self._3d_text_drag_mode

        if mode == 'move':
            dx = (event.x - self._3d_text_drag_start_evt[0]) / disp_w
            dy = (event.y - self._3d_text_drag_start_evt[1]) / disp_h
            new_quad = [[p[0] + dx, p[1] + dy] for p in quad0]

        elif mode == 'corner':
            nx = (event.x - ox) / disp_w
            ny = (event.y - oy) / disp_h
            new_quad = [list(p) for p in quad0]
            new_quad[self._3d_text_drag_corner_idx] = [nx, ny]

        elif mode == 'edge':
            # One clean, axis-locked drag per edge: top/bottom edges only
            # tilt (move vertically), left/right edges only angle the text
            # onto a side wall (move horizontally) — so you can't
            # accidentally warp the other axis while you're just trying
            # to tilt it.
            idxs, axis = self._3D_TEXT_EDGES[self._3d_text_drag_edge_name]
            new_quad = [list(p) for p in quad0]
            if axis == 'y':
                dy = (event.y - self._3d_text_drag_start_evt[1]) / disp_h
                for i in idxs:
                    new_quad[i][1] = quad0[i][1] + dy
            else:
                dx = (event.x - self._3d_text_drag_start_evt[0]) / disp_w
                for i in idxs:
                    new_quad[i][0] = quad0[i][0] + dx

        elif mode == 'rotate':
            cx_f, cy_f = self._3d_text_drag_start_centroid_frac
            cx, cy = cx_f * disp_w, cy_f * disp_h
            tx, ty = event.x - ox, event.y - oy
            ang = math.atan2(ty - cy, tx - cx)
            dtheta = ang - self._3d_text_drag_start_angle
            cos_a, sin_a = math.cos(dtheta), math.sin(dtheta)
            new_quad = []
            for p in quad0:
                px, py = p[0] * disp_w - cx, p[1] * disp_h - cy
                rx = px * cos_a - py * sin_a
                ry = px * sin_a + py * cos_a
                new_quad.append([(rx + cx) / disp_w, (ry + cy) / disp_h])
        else:
            return

        item = self.media_queue[self.selected_idx]
        item['3d_text_quad'] = new_quad
        self._debounced_preview(interactive=True)

    def _on_3d_text_transform_end(self, event):
        if not getattr(self, '_3d_text_dragging', False):
            return
        self._3d_text_dragging = False
        label = {'move': 'Moved', 'corner': 'Resized', 'edge': 'Tilted', 'rotate': 'Rotated'}.get(
            self._3d_text_drag_mode, 'Updated')
        self._3d_text_drag_mode = None
        self._3d_text_status.config(text=f"{label} ✓  —  drag again to keep adjusting", fg=C["accent3"])
        self.update_global_preview()

    def _draw_3d_text_handles(self, img, item):
        """Draws the quad outline plus its move/corner/edge/rotate handles
        onto the (still full frame-resolution) preview image, so the user
        can see exactly what they're about to drag."""
        w, h = img.size
        quad = self._get_3d_text_quad(item)
        pts = [(p[0] * w, p[1] * h) for p in quad]
        rot_handle, top_mid, centroid = self._3d_text_rotate_handle_disp(pts)
        edge_mids = self._3d_text_edge_midpoints_disp(pts)

        out = img.convert("RGB").copy()
        draw = ImageDraw.Draw(out)

        draw.line(pts + [pts[0]], fill=(0, 200, 255), width=2)
        draw.line([top_mid, rot_handle], fill=(0, 200, 255), width=2)

        hr = 8
        for (hx, hy) in pts:
            draw.rectangle([hx - hr, hy - hr, hx + hr, hy + hr],
                            fill=(0, 200, 255), outline=(255, 255, 255), width=2)

        er = 7
        for (ex, ey) in edge_mids.values():
            draw.ellipse([ex - er, ey - er, ex + er, ey + er],
                          fill=(255, 210, 0), outline=(255, 255, 255), width=2)

        rr = 9
        draw.ellipse([rot_handle[0] - rr, rot_handle[1] - rr, rot_handle[0] + rr, rot_handle[1] + rr],
                      fill=(255, 60, 60), outline=(255, 255, 255), width=2)

        return out

    # ══════════════════════════════════════════════════════════════════
    #  3D TEXT — AR AUTO-TRACKING (BETA)
    #  Tracks real feature points in the actual video around where the
    #  text was placed, using optical flow + a per-frame homography back
    #  to the anchor placement. This is what makes the text behave like an
    #  AR anchor planted in the scene — it moves/scales with the camera's
    #  real motion instead of a synthetic zoom, and simply stops being
    #  rendered once the camera has moved far enough that tracking can no
    #  longer follow it (i.e. once you've moved past it).
    # ══════════════════════════════════════════════════════════════════

    def _3d_text_fit_mapping(self, clip_w, clip_h, is_mobile, smart_fill, scale_val):
        """Pure-math mapping between (a) fractions of the composed output
        canvas — the space the quad is stored/edited in — and (b) pixel
        coordinates of the raw source video frame — the space optical flow
        tracking runs in. Mirrors the fit/crop math in update_global_preview
        so a quad placed on the preview lines up with the real footage."""
        target_w = 1080 if is_mobile else 1920
        target_h = 1920 if is_mobile else 1080
        if smart_fill:
            base_sf = max(target_w / clip_w, target_h / clip_h) * scale_val
        else:
            base_sf = min(target_w / clip_w, target_h / clip_h) * scale_val
        base_sf = max(1e-6, base_sf)
        new_w, new_h = clip_w * base_sf, clip_h * base_sf
        if smart_fill:
            off_x, off_y = (new_w - target_w) / 2.0, (new_h - target_h) / 2.0

            def frac_to_raw(fx, fy):
                return (fx * target_w + off_x) / base_sf, (fy * target_h + off_y) / base_sf

            def raw_to_frac(rx, ry):
                return (rx * base_sf - off_x) / target_w, (ry * base_sf - off_y) / target_h
        else:
            off_x, off_y = (target_w - new_w) / 2.0, (target_h - new_h) / 2.0

            def frac_to_raw(fx, fy):
                return (fx * target_w - off_x) / base_sf, (fy * target_h - off_y) / base_sf

            def raw_to_frac(rx, ry):
                return (rx * base_sf + off_x) / target_w, (ry * base_sf + off_y) / target_h
        return frac_to_raw, raw_to_frac

    def _get_3d_text_quad_at(self, item, t):
        """The quad to render at local time t: the live AR-tracked quad if
        this clip has been auto-tracked (and t is within the tracked
        range), otherwise the plain static anchor quad. Returns None when
        tracking has run out (camera has moved past the anchored point) —
        the caller should render nothing in that case."""
        if (getattr(self, '_3d_text_place_active', False) and self.selected_idx is not None
                and self.selected_idx < len(self.media_queue) and self.media_queue[self.selected_idx] is item):
            return self._get_3d_text_quad(item)  # editing always shows/edits the raw anchor

        track = item.get('3d_text_track')
        if not track:
            return self._get_3d_text_quad(item)
        quads = track.get('quads') or {}
        if not quads:
            return self._get_3d_text_quad(item)

        anchor_t = track.get('anchor_t', 0.0)
        dt = track.get('local_dt_per_step') or (1.0 / max(1.0, track.get('fps', 30.0)))
        rel = (t - anchor_t) / max(1e-6, dt)
        if rel < -1.0:
            return self._get_3d_text_quad(item)  # before the anchor point — not tracked yet, show it static

        int_keys = sorted(int(k) for k in quads.keys())
        max_step = int_keys[-1]
        if rel > max_step + 1.0:
            return None  # tracking ran out here — the camera has moved past it

        k0 = max(0, min(max_step, int(math.floor(rel))))
        while k0 not in quads and k0 > 0:
            k0 -= 1
        k1 = k0 + 1 if (k0 + 1) in quads else k0
        alpha = max(0.0, min(1.0, rel - k0)) if k1 != k0 else 0.0

        mp = track.get('map_params', {})
        frac_to_raw, raw_to_frac = self._3d_text_fit_mapping(
            mp.get('clip_w', 1920), mp.get('clip_h', 1080), mp.get('is_mobile', False),
            mp.get('smart_fill', False), mp.get('scale_val', 1.0))

        q0 = np.float32(quads[k0] if k0 in quads else quads[str(k0)])
        if k1 == k0:
            q = q0
        else:
            q1 = np.float32(quads[k1] if k1 in quads else quads[str(k1)])
            q = q0 * (1.0 - alpha) + q1 * alpha

        # Defensive second layer: even though bad fits are rejected/smoothed
        # out at tracking time, reject a flipped/self-intersecting/degenerate
        # quad here too rather than ever render one.
        anchor_quad = self._get_3d_text_quad(item)
        anchor_raw = np.float32([frac_to_raw(p[0], p[1]) for p in anchor_quad])
        ref_area = abs(self._3d_text_quad_signed_area(anchor_raw))
        ref_sign = self._3d_text_quad_signed_area(anchor_raw) > 0
        area = self._3d_text_quad_signed_area(q)
        if (not np.all(np.isfinite(q))
                or abs(area) < 1.0
                or (area > 0) != ref_sign
                or not self._3d_text_quad_is_convex(q)
                or abs(area) / max(1e-6, ref_area) > 20.0
                or abs(area) / max(1e-6, ref_area) < 1.0 / 20.0):
            return None

        return [list(raw_to_frac(px, py)) for px, py in q]

    def _start_3d_text_autotrack(self):
        if self.selected_idx is None:
            return messagebox.showwarning("AR Tracking", "Select a clip first.")
        item = self.media_queue[self.selected_idx]
        if item['type'] != 'video' or not item.get('path'):
            return messagebox.showwarning("AR Tracking", "Auto-tracking works on video clips only.")
        if not item.get('effect_3d_text_enabled', False):
            return messagebox.showwarning("AR Tracking", "Enable 3D Text and place it on the preview first.")
        if item.get('ken_burns_enabled', False):
            return messagebox.showwarning(
                "AR Tracking",
                "Turn off Ken Burns Pan & Zoom on this clip first — auto-tracking follows the "
                "camera's real motion, so the two can't be used together.")
        if item.get('rotation', 0) or item.get('flip_h', False) or item.get('flip_v', False):
            return messagebox.showwarning(
                "AR Tracking", "Auto-tracking doesn't support rotated or flipped clips yet.")

        anchor_t = self.playhead_t.get()
        anchor_quad = self._get_3d_text_quad(item)
        end_limit = None
        if not item.get('3d_text_full_clip', True):
            end_limit = float(item.get('3d_text_end', anchor_t + 10.0))
        clip_dur = self._item_duration(item)
        clip_start = float(item.get('clip_start', 0.0))
        speed = max(0.1, float(item.get('speed', 1.0)))
        is_mobile = (self.format_var.get() == "mobile")
        smart_fill = self.smart_fill_var.get()
        scale_val = item.get('scale', 1.0)

        if hasattr(self, '_3d_text_track_status'):
            self._3d_text_track_status.config(text="Tracking… 0%", fg=C["accent"])
        if hasattr(self, '_3d_text_track_btn'):
            self._3d_text_track_btn.config(state=tk.DISABLED)

        threading.Thread(
            target=self._run_3d_text_autotrack,
            args=(item, item['path'], anchor_t, anchor_quad, end_limit, clip_dur,
                  clip_start, speed, smart_fill, scale_val, is_mobile),
            daemon=True
        ).start()

    @staticmethod
    def _3d_text_quad_signed_area(pts):
        x, y = pts[:, 0], pts[:, 1]
        return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))

    @staticmethod
    def _3d_text_quad_is_convex(pts):
        n = len(pts)
        sign = None
        for i in range(n):
            p0, p1, p2 = pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
            v1, v2 = p1 - p0, p2 - p1
            cross = v1[0] * v2[1] - v1[1] * v2[0]
            if abs(cross) < 1e-6:
                continue
            s = cross > 0
            if sign is None:
                sign = s
            elif s != sign:
                return False
        return True

    def _3d_text_homography_is_sane(self, H, anchor_pts, ref_area, ref_sign):
        """Rejects homographies that would produce visual garbage: a
        self-intersecting quad, a mirror-image reflection, or one whose
        size relative to the original placement is wildly implausible.
        RANSAC can return a "successful" fit (enough inliers) that is still
        geometrically nonsensical for real camera motion — this is what
        catches that instead of rendering the broken result. Note a plain
        180° rotation does NOT flip the sign checked here (rotations are
        orientation-preserving) — that case is caught separately, frame to
        frame, via the edge-angle jump check in the tracking loop.
        Cumulative growth vs. the anchor is allowed to be large (up to 20x)
        since the whole point is the text growing a lot as the camera
        closes in — this only rejects truly degenerate fits."""
        try:
            warped = cv2.perspectiveTransform(anchor_pts.reshape(-1, 1, 2), H).reshape(-1, 2)
        except Exception:
            return False, None, None, None
        if not np.all(np.isfinite(warped)):
            return False, None, None, None
        area = self._3d_text_quad_signed_area(warped)
        if abs(area) < 1.0:
            return False, None, None, None
        if (area > 0) != ref_sign:
            return False, None, None, None  # mirror-image reflection — not real camera motion
        if not self._3d_text_quad_is_convex(warped):
            return False, None, None, None
        if abs(area) / max(1e-6, ref_area) > 20.0 or abs(area) / max(1e-6, ref_area) < 1.0 / 20.0:
            return False, None, None, None  # implausible vs. the original placement size
        edge = warped[1] - warped[0]
        angle = math.atan2(edge[1], edge[0])
        return True, area, angle, warped

    def _3d_text_smooth_track(self, quad_seq, window=9):
        """quad_seq: (n,4,2) array of tracked quad corners, one per step,
        with NO gaps (dense_fill handles that before calling this).
        Optical-flow-derived homographies are independently estimated each
        frame from noisy point correspondences, so even smooth real camera
        motion comes out slightly jittery step to step. A short temporal
        Gaussian smoothing pass removes that jitter while preserving the
        overall approach/pass-by trend, since that trend is much slower
        than the jitter itself."""
        n = quad_seq.shape[0]
        if n < 5:
            return quad_seq
        window = min(window, n - (1 - n % 2))  # keep it odd and <= n
        window = max(3, window if window % 2 == 1 else window - 1)
        sigma = window / 4.0
        xs = np.arange(window) - window // 2
        kernel = np.exp(-0.5 * (xs / sigma) ** 2)
        kernel /= kernel.sum()
        flat = quad_seq.reshape(n, 8).astype(np.float64)
        pad = window // 2
        padded = np.pad(flat, ((pad, pad), (0, 0)), mode='edge')
        smoothed = np.empty_like(flat)
        for c in range(8):
            smoothed[:, c] = np.convolve(padded[:, c], kernel, mode='valid')
        return smoothed.reshape(n, 4, 2)

    def _run_3d_text_autotrack(self, item, path, anchor_t, anchor_quad, end_limit, clip_dur,
                                clip_start, speed, smart_fill, scale_val, is_mobile):
        cap = None
        try:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                self.root.after(0, self._on_3d_text_autotrack_error, item, "Couldn't open the video file.")
                return
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            clip_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            clip_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if clip_w <= 0 or clip_h <= 0:
                self.root.after(0, self._on_3d_text_autotrack_error, item, "Couldn't read the video's dimensions.")
                return

            frac_to_raw, _raw_to_frac = self._3d_text_fit_mapping(clip_w, clip_h, is_mobile, smart_fill, scale_val)
            anchor_raw = np.float32([frac_to_raw(p[0], p[1]) for p in anchor_quad])
            ref_area = abs(self._3d_text_quad_signed_area(anchor_raw))
            ref_sign = self._3d_text_quad_signed_area(anchor_raw) > 0
            prev_area = ref_area
            ref_edge = anchor_raw[1] - anchor_raw[0]
            prev_angle = math.atan2(ref_edge[1], ref_edge[0])

            anchor_raw_t = clip_start + anchor_t * speed
            anchor_frame_idx = int(round(anchor_raw_t * fps))
            max_local_t = min(clip_dur, end_limit) if end_limit else clip_dur
            max_raw_t = clip_start + max_local_t * speed
            max_frame_idx = int(round(max_raw_t * fps))
            max_frame_idx = min(max_frame_idx, anchor_frame_idx + int(fps * 60))  # hard cap: 60s of footage
            local_dt_per_step = (1.0 / fps) / speed

            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, anchor_frame_idx))
            ok, frame0 = cap.read()
            if not ok:
                self.root.after(0, self._on_3d_text_autotrack_error, item, "Couldn't read the starting frame.")
                return
            gray0 = cv2.cvtColor(frame0, cv2.COLOR_BGR2GRAY)

            # Track features from the local area the text sits on/near (more
            # robust than the whole frame — follows that surface specifically).
            xs, ys = anchor_raw[:, 0], anchor_raw[:, 1]
            mx, my = (xs.max() - xs.min()) * 0.6, (ys.max() - ys.min()) * 0.6
            x0, x1 = max(0, xs.min() - mx), min(clip_w, xs.max() + mx)
            y0, y1 = max(0, ys.min() - my), min(clip_h, ys.max() + my)
            roi_mask = np.zeros((clip_h, clip_w), dtype=np.uint8)
            roi_mask[int(y0):int(y1), int(x0):int(x1)] = 255

            pts0 = cv2.goodFeaturesToTrack(gray0, maxCorners=200, qualityLevel=0.01,
                                            minDistance=7, mask=roi_mask, blockSize=7)
            if pts0 is None or len(pts0) < 8:
                self.root.after(0, self._on_3d_text_autotrack_error, item,
                                 "Not enough visual detail there to track — try a spot with more texture.")
                return

            lk_params = dict(winSize=(21, 21), maxLevel=3,
                              criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))

            raw_quads = {0: anchor_raw.copy()}
            anchor_pts = pts0
            prev_pts = pts0
            prev_gray = gray0
            last_good_step = 0
            last_good_H = np.eye(3, dtype=np.float32)
            consecutive_bad = 0
            # Tolerate a run of shaky/noisy frames before giving up — a single
            # bad optical-flow or RANSAC fit shouldn't kill the whole track;
            # only genuinely losing the surface (e.g. camera turns away) should.
            MAX_CONSECUTIVE_BAD = 12
            total_steps = max(1, max_frame_idx - anchor_frame_idx)

            for step in range(1, total_steps + 1):
                ok, frame = cap.read()
                if not ok:
                    break
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                new_pts, status, _err = cv2.calcOpticalFlowPyrLK(prev_gray, gray, prev_pts, None, **lk_params)
                good_new = good_anchor = None
                if new_pts is not None and status is not None:
                    status = status.reshape(-1)
                    gn = new_pts[status == 1]
                    ga = anchor_pts[status == 1]
                    if len(gn) >= 8:
                        good_new, good_anchor = gn, ga

                if good_new is None:
                    # Flow failed or too few points survived — try to recover
                    # by detecting fresh features and re-anchoring them via
                    # the last known-good transform, rather than giving up.
                    fresh = cv2.goodFeaturesToTrack(gray, maxCorners=200, qualityLevel=0.01,
                                                     minDistance=7, mask=roi_mask, blockSize=7)
                    if fresh is not None and len(fresh) >= 8:
                        Hinv = np.linalg.inv(last_good_H)
                        good_new = fresh
                        good_anchor = cv2.perspectiveTransform(fresh, Hinv)
                    else:
                        consecutive_bad += 1
                        prev_gray = gray
                        if consecutive_bad >= MAX_CONSECUTIVE_BAD:
                            break
                        continue

                H, inliers = cv2.findHomography(good_anchor, good_new, cv2.RANSAC, 4.0)
                step_recorded = False
                if H is not None and inliers is not None and int(inliers.sum()) >= 8:
                    is_sane, area, angle, warped = self._3d_text_homography_is_sane(H, anchor_raw, ref_area, ref_sign)
                    if is_sane:
                        step_ratio = area / max(1e-6, prev_area)
                        dtheta = (angle - prev_angle + math.pi) % (2 * math.pi) - math.pi
                        # Generous per-frame bounds — real "flying toward it" motion
                        # can grow the quad fast; this mainly rejects wild jumps
                        # (a completely different/bad match) or a flipped fit.
                        if (1.0 / 4.0) <= step_ratio <= 4.0 and abs(dtheta) <= math.radians(45):
                            raw_quads[step] = warped
                            last_good_step = step
                            last_good_H = H
                            prev_area = area
                            prev_angle = angle
                            step_recorded = True

                consecutive_bad = 0 if step_recorded else consecutive_bad + 1

                # Point tracking itself keeps going even through a frame whose
                # *homography* we didn't trust — an isolated bad fit shouldn't
                # stop the underlying feature tracking from recovering next frame.
                anchor_pts = good_anchor
                prev_pts = good_new
                prev_gray = gray

                if consecutive_bad >= MAX_CONSECUTIVE_BAD:
                    break

                if len(prev_pts) < 40:
                    fresh = cv2.goodFeaturesToTrack(gray, maxCorners=200, qualityLevel=0.01,
                                                     minDistance=7, mask=roi_mask, blockSize=7)
                    if fresh is not None:
                        Hinv = np.linalg.inv(last_good_H)
                        fresh_anchor = cv2.perspectiveTransform(fresh, Hinv)
                        prev_pts = np.concatenate([prev_pts, fresh], axis=0)
                        anchor_pts = np.concatenate([anchor_pts, fresh_anchor.astype(np.float32)], axis=0)

                if step % 10 == 0:
                    pct = int(100 * step / total_steps)
                    self.root.after(0, self._on_3d_text_autotrack_progress, pct)

            if last_good_step < 3:
                self.root.after(0, self._on_3d_text_autotrack_error, item,
                                 "Lost tracking almost immediately — try a spot with more visual detail.")
                return

            # Fill any skipped steps by interpolating between the nearest
            # recorded ones, then smooth the whole sequence to remove the
            # frame-to-frame jitter inherent to independently-estimated
            # optical-flow homographies (the "shaking" you'd otherwise see).
            recorded_steps = sorted(raw_quads.keys())
            dense_steps = list(range(0, last_good_step + 1))
            dense_quads = []
            for s in dense_steps:
                if s in raw_quads:
                    dense_quads.append(raw_quads[s])
                else:
                    lo = max((k for k in recorded_steps if k <= s), default=recorded_steps[0])
                    hi = min((k for k in recorded_steps if k >= s), default=recorded_steps[-1])
                    if hi == lo:
                        dense_quads.append(raw_quads[lo])
                    else:
                        a = (s - lo) / float(hi - lo)
                        dense_quads.append(raw_quads[lo] * (1.0 - a) + raw_quads[hi] * a)
            smoothed = self._3d_text_smooth_track(np.array(dense_quads))
            quads_by_step = {dense_steps[i]: smoothed[i].tolist() for i in range(len(dense_steps))}

            track = {
                'anchor_t': anchor_t,
                'fps': float(fps),
                'local_dt_per_step': local_dt_per_step,
                'quads': quads_by_step,
                'tracked_until_t': anchor_t + last_good_step * local_dt_per_step,
                'map_params': {'clip_w': clip_w, 'clip_h': clip_h, 'is_mobile': is_mobile,
                               'smart_fill': smart_fill, 'scale_val': scale_val},
            }
            self.root.after(0, self._on_3d_text_autotrack_done, item, track)
        except Exception as ex:
            traceback.print_exc()
            self.root.after(0, self._on_3d_text_autotrack_error, item, f"Tracking failed: {ex}")
        finally:
            if cap is not None:
                cap.release()

    def _on_3d_text_autotrack_progress(self, pct):
        if hasattr(self, '_3d_text_track_status'):
            self._3d_text_track_status.config(text=f"Tracking… {pct}%", fg=C["accent"])

    def _on_3d_text_autotrack_done(self, item, track):
        item['3d_text_track'] = track
        item['3d_text_full_clip'] = False
        item['3d_text_start'] = track['anchor_t']
        item['3d_text_end'] = track['tracked_until_t']
        dur = track['tracked_until_t'] - track['anchor_t']
        if hasattr(self, '_3d_text_track_status'):
            self._3d_text_track_status.config(
                text=f"Tracking locked ✓ ({dur:.1f}s — fades out once it moves out of view)", fg=C["accent3"])
        if hasattr(self, '_3d_text_track_btn'):
            self._3d_text_track_btn.config(state=tk.NORMAL)
        if self.selected_idx is not None and self.media_queue[self.selected_idx] is item:
            self._3d_text_full_clip.set(False)
            self._3d_text_start.set(track['anchor_t'])
            self._3d_text_end.set(track['tracked_until_t'])
        self.update_global_preview()

    def _on_3d_text_autotrack_error(self, item, msg):
        if hasattr(self, '_3d_text_track_status'):
            self._3d_text_track_status.config(text=msg, fg="#ff6b6b")
        if hasattr(self, '_3d_text_track_btn'):
            self._3d_text_track_btn.config(state=tk.NORMAL)

    def _clear_3d_text_autotrack(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        if '3d_text_track' in item:
            del item['3d_text_track']
        if hasattr(self, '_3d_text_track_status'):
            self._3d_text_track_status.config(text="Track cleared — text is fixed in place again", fg=C["text_dim"])
        self.update_global_preview()

    def _start_person_correct_mode(self):
        """Like _start_person_select_mode, but the next click CORRECTS the
        already-selected object's position at the CURRENT frame instead of
        starting a brand new selection: earlier frames' already-tracked
        positions are left untouched, and the tracking chain re-anchors
        from this frame forward using the corrected point."""
        self._person_select_is_correction = True
        self._start_person_select_mode()
        try:
            self._person_status_label.config(
                text="Click the correct position for this frame onward...", fg=C["accent"])
        except Exception:
            pass

    def _start_person_select_mode(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        if item['type'] not in ('video', 'image', 'placeholder') or not item.get('path'):
            return
        self._person_select_mode = True
        self._person_status_label.config(
            text="Click on any object in the preview...", fg=C["accent"])
        try:
            self.preview_label.config(cursor="crosshair")
            self.preview_label.bind("<ButtonPress-1>", self._on_person_click)
        except Exception:
            pass

    def _on_person_click(self, event):
        if not self._person_select_mode or self.selected_idx is None:
            return
        self._person_select_mode = False
        self.preview_label.config(cursor="")
        self.preview_label.unbind("<ButtonPress-1>")
        is_correction = getattr(self, '_person_select_is_correction', False)
        self._person_select_is_correction = False

        item = self.media_queue[self.selected_idx]
        if item['type'] not in ('video', 'image', 'placeholder') or not item.get('path'):
            return

        try:
            # Force a preview render NOW so _preview_full_frame is fresh
            # and matches exactly what the user sees on screen.
            self.update_global_preview()
            self.root.update_idletasks()

            frame = getattr(self, '_preview_full_frame', None)
            if frame is None:
                self._person_status_label.config(text="Could not read frame.", fg=C["danger"])
                return
            h_frame, w_frame = frame.shape[:2]

            # Use stored display dimensions from the last preview render
            disp_w = getattr(self, '_preview_disp_w', None)
            disp_h = getattr(self, '_preview_disp_h', None)
            ox = getattr(self, '_preview_offset_x', 0)
            oy = getattr(self, '_preview_offset_y', 0)

            if disp_w is None or disp_h is None:
                pw = max(self.preview_label.winfo_width(), 320)
                ph = max(self.preview_label.winfo_height(), 180)
                img_aspect = w_frame / max(1, h_frame)
                label_aspect = pw / max(1, ph)
                if img_aspect > label_aspect:
                    disp_w = pw
                    disp_h = int(pw / img_aspect)
                else:
                    disp_h = ph
                    disp_w = int(ph * img_aspect)
                ox = (pw - disp_w) // 2
                oy = (ph - disp_h) // 2

            # Map click from label → thumbnail → frame
            thumb_x = event.x - ox
            thumb_y = event.y - oy
            if thumb_x < 0 or thumb_x > disp_w or thumb_y < 0 or thumb_y > disp_h:
                self._person_status_label.config(text="Click inside the image.", fg=C["danger"])
                return
            click_x = int((thumb_x / max(1, disp_w)) * w_frame)
            click_y = int((thumb_y / max(1, disp_h)) * h_frame)

            print(f"[PERSON-SELECT] frame={w_frame}x{h_frame} disp={disp_w}x{disp_h} offset=({ox},{oy}) click_label=({event.x},{event.y}) click_frame=({click_x},{click_y})")

            # ── Also probe a NATIVE-RESOLUTION frame for tiny/distant subjects ──
            # The on-screen preview (and everything the live tracker compares
            # against later) works in a capped canvas size (e.g. 960x540). A
            # player who is small and distant in a wide broadcast shot can
            # shrink to just a handful of pixels there, too few to detect
            # reliably. Running YOLO a SECOND time on the full native-
            # resolution frame catches those -- but its boxes come back in
            # native pixel space, so they're converted back into the SAME
            # canvas coordinate space as everything below before being used.
            # (Using the native-res coordinates directly, unconverted, is
            # what caused the tracked arrow to drift to a neighbouring
            # person right after selection -- the stored position and the
            # live tracker's frame were in two different pixel scales.)
            hires_candidates = []
            try:
                no_transform = (
                    item.get('rotation', 0) == 0
                    and not item.get('flip_h', False)
                    and not item.get('flip_v', False)
                    and float(item.get('scale', 1.0)) == 1.0
                    and not item.get('ken_burns_enabled', False)
                    and not self.smart_fill_var.get()
                )
                if no_transform:
                    hi_frame = self._get_preview_frame(item)
                    if hi_frame is not None:
                        hi_h, hi_w = hi_frame.shape[:2]
                        fit_sf = min(w_frame / hi_w, h_frame / hi_h)
                        pad_x = (w_frame - hi_w * fit_sf) / 2.0
                        pad_y = (h_frame - hi_h * fit_sf) / 2.0
                        for p in self._yolo_track(hi_frame):
                            hx, hy, hw, hh = p['bbox']
                            cbw = max(1, int(hw * fit_sf))
                            cbh = max(1, int(hh * fit_sf))
                            cbx = int(hx * fit_sf + pad_x)
                            cby = int(hy * fit_sf + pad_y)
                            hires_candidates.append({
                                **p,
                                'bbox': (cbx, cby, cbw, cbh),
                                'center': (int(cby + cbh / 2), int(cbx + cbw / 2)),
                                'area': cbw * cbh,
                                'raw_mask': None,  # regenerate from the canvas frame, not the hi-res one
                                'mask': None,
                            })
                        if hires_candidates:
                            print(f"[PERSON-SELECT] native-res pass ({hi_w}x{hi_h}) found {len(hires_candidates)} candidate(s), mapped back to canvas space")
            except Exception as _hi_ex:
                print("Native-res detection pass skipped:", _hi_ex)
            # ─────────────────────────────────────────────────────────────

            # Find the object AT the click using YOLO-seg instance masks.
            # Prefer an object whose bounding box actually CONTAINS the
            # click point -- this is what fixes clicks landing on the wrong
            # nearby player. Comparing only to each object's CENTER (the
            # old behaviour) would happily jump to a neighbouring person
            # whenever their center happened to be closer than the person
            # whose body was actually clicked on.
            yolo_objects = self._yolo_track(frame) + hires_candidates
            if yolo_objects:
                containing = []
                for i, p in enumerate(yolo_objects):
                    bx, by, bw, bh = p['bbox']
                    pad = max(2, int(min(bw, bh) * 0.05))
                    if (bx - pad) <= click_x <= (bx + bw + pad) and (by - pad) <= click_y <= (by + bh + pad):
                        containing.append(i)

                best_idx = -1
                best_dist = float('inf')
                if containing:
                    # Several people can overlap on screen -- the SMALLEST
                    # containing box is almost always the one actually
                    # clicked (a bigger box behind/around them just also
                    # happens to cover the same point).
                    best_idx = min(containing, key=lambda ci: yolo_objects[ci]['bbox'][2] * yolo_objects[ci]['bbox'][3])
                else:
                    for i, p in enumerate(yolo_objects):
                        pcx, pcy = p['center'][1], p['center'][0]
                        dist = ((click_x - pcx) ** 2 + (click_y - pcy) ** 2) ** 0.5
                        if dist < best_dist:
                            best_dist = dist
                            best_idx = i

                # Nothing actually contained the click, and the nearest
                # object is still far away -- don't silently snap to it.
                # Let this fall through to the next detector (or the
                # "click closer" message) instead of confidently landing
                # the arrow on someone on the other side of the frame.
                max_click_dist = max(h_frame, w_frame) * 0.10
                if not containing and best_idx >= 0 and best_dist > max_click_dist:
                    print(f"[OBJ-SELECT] rejected: nearest object is {best_dist:.0f}px away (limit {max_click_dist:.0f}px) — falling through")
                    best_idx = -1

                for i, p in enumerate(yolo_objects):
                    pcx, pcy = p['center'][1], p['center'][0]
                    dist = ((click_x - pcx) ** 2 + (click_y - pcy) ** 2) ** 0.5
                    cname = p.get('class_name', 'object')
                    print(f"[OBJ-SELECT]   obj[{i}] id={p.get('id','?')} class={cname} conf={p.get('conf',0):.2f} center=({pcx},{pcy}) bbox={p['bbox']} dist={dist:.1f} contains_click={i in containing}")
                if best_idx >= 0:
                    chosen = yolo_objects[best_idx]
                    # Use YOLO's own instance mask — clean, per-person, no background bleed
                    if chosen.get('raw_mask') is not None:
                        person_mask = chosen['raw_mask'].copy()
                        if person_mask.shape[:2] != (h_frame, w_frame):
                            person_mask = cv2.resize(person_mask, (w_frame, h_frame), interpolation=cv2.INTER_LINEAR)
                    else:
                        person_mask = self._make_person_bbox_mask(frame, chosen['bbox'])

                    full_bbox = chosen['bbox']
                    full_center = chosen['center']

                    item['effect_selected_person'] = chosen.get('id', 0)
                    item['effect_yolo_locked'] = True
                    self._effect_selected_person.set(chosen.get('id', 0))
                    item['effect_person_mask_template'] = person_mask
                    item['effect_selected_class'] = chosen.get('class_name', 'object')

                    template = self._get_person_appearance(frame, full_bbox)
                    if template is None:
                        # Fallback: create minimal template from bbox region
                        x, y, bw, bh = full_bbox
                        x0, y0 = max(0, x), max(0, y)
                        x1, y1 = min(w_frame, x + bw), min(h_frame, y + bh)
                        if x1 - x0 > 2 and y1 - y0 > 2:
                            region = frame[y0:y1, x0:x1]
                            hsv_obj = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
                            obj_hist = cv2.calcHist([hsv_obj], [0, 1], None, [12, 8], [0, 180, 0, 256])
                            cv2.normalize(obj_hist, obj_hist, 0, 1, cv2.NORM_MINMAX)
                            gray_obj = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
                            edges = cv2.Canny(gray_obj, 50, 150)
                            edge_template = cv2.resize(edges, (48, 80), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
                            template = {
                                'face_hist': None, 'face_embedding': None, 'face_rect': None,
                                'body_hist': obj_hist, 'edge_template': edge_template,
                                'bbox': full_bbox, 'center': full_center,
                                'size': (bw, bh), 'area': bw * bh,
                            }
                    if template is not None:
                        item['effect_person_template'] = template
                        item['effect_face_buffer'] = [template]

                    # Anchor the tracking chain here. A brand new selection
                    # discards any previous tracking history; a correction
                    # (re-click while already tracking) leaves earlier
                    # frames' positions untouched and only clears the
                    # trajectory from this frame onward.
                    frame_idx0 = self._anchor_tracking_at(item, frame, full_center, full_bbox, is_correction)

                    cname = chosen.get('class_name', 'object')
                    self.update_global_preview()
                    self._person_status_label.config(
                        text=f"{cname.title()} selected (YOLO ID:{chosen.get('id','?')}). Instance mask active.",
                        fg=C["accent3"])
                    self.status_label.config(
                        text=f"{cname.title()} selected via YOLO-seg. Instance mask active.",
                        fg=C["accent3"])
                    return

            # Fallback: MediaPipe if YOLO finds nothing
            mp_mask = self._get_mediapipe_mask(frame)
            if mp_mask is not None and mp_mask.max() > 0.01:
                binary = (mp_mask > 0.3).astype(np.uint8)
                num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
                best_label = -1
                best_dist = float('inf')
                click_label = 0
                if 0 <= click_y < labels.shape[0] and 0 <= click_x < labels.shape[1]:
                    click_label = labels[click_y, click_x]
                if click_label > 0 and stats[click_label, cv2.CC_STAT_AREA] >= 500:
                    # The click pixel itself falls inside this blob -- use
                    # it directly instead of guessing from centroid distance.
                    best_label = click_label
                else:
                    for i in range(1, num_labels):
                        area = stats[i, cv2.CC_STAT_AREA]
                        if area < 500:
                            continue
                        cx, cy = centroids[i]
                        dist = ((click_x - cx) ** 2 + (click_y - cy) ** 2) ** 0.5
                        if dist < best_dist:
                            best_dist = dist
                            best_label = i
                    max_click_dist = max(h_frame, w_frame) * 0.10
                    if best_label > 0 and best_dist > max_click_dist:
                        best_label = -1
                if best_label > 0:
                    person_mask = self._color_segment_person(frame, click_x, click_y)

                    ys, xs = np.where(person_mask > 0.1)
                    if len(xs) > 0 and len(ys) > 0:
                        bx0, by0 = int(xs.min()), int(ys.min())
                        bx1, by1 = int(xs.max()), int(ys.max())
                        full_bbox = (bx0, by0, bx1 - bx0, by1 - by0)
                        full_center = (by0 + (by1 - by0) // 2, bx0 + (bx1 - bx0) // 2)
                    else:
                        full_bbox = (0, 0, w_frame, h_frame)
                        full_center = (h_frame // 2, w_frame // 2)

                    item['effect_selected_person'] = -2  # sentinel: selected via fallback (no YOLO ID)
                    item['effect_yolo_locked'] = False
                    self._effect_selected_person.set(-2)
                    item['effect_person_mask_template'] = person_mask
                    item['effect_selected_class'] = 'object'

                    template = self._get_person_appearance(frame, full_bbox)
                    if template is not None:
                        item['effect_person_template'] = template
                        item['effect_face_buffer'] = [template]

                    # Anchor the tracking chain here -- see the note in the
                    # YOLO branch above for full vs. correction behaviour.
                    frame_idx0 = self._anchor_tracking_at(item, frame, full_center, full_bbox, is_correction)

                    self.update_global_preview()
                    self._person_status_label.config(
                        text=f"Object selected! Full body outline active.",
                        fg=C["accent3"])
                    self.status_label.config(
                        text=f"Object selected. Outline rendering.",
                        fg=C["accent3"])
                    return

            # Fallback: HOG / face detection if MediaPipe fails
            persons = self._detect_all_persons(frame)
            if not persons:
                self._person_status_label.config(
                    text="No objects detected. Try clicking closer to an object.", fg=C["danger"])
                return

            containing = []
            for i, p in enumerate(persons):
                bx, by, bw, bh = p['bbox']
                pad = max(2, int(min(bw, bh) * 0.05))
                if (bx - pad) <= click_x <= (bx + bw + pad) and (by - pad) <= click_y <= (by + bh + pad):
                    containing.append(i)

            best_idx = 0
            best_dist = float('inf')
            if containing:
                best_idx = min(containing, key=lambda ci: persons[ci]['bbox'][2] * persons[ci]['bbox'][3])
            else:
                for i, p in enumerate(persons):
                    pcx, pcy = p['center'][1], p['center'][0]
                    dist = ((click_x - pcx) ** 2 + (click_y - pcy) ** 2) ** 0.5
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = i

            # This is the last detector in the chain -- if nothing actually
            # contained the click and even the nearest person is far away,
            # say so plainly instead of grabbing whoever happens to be
            # closest, however far across the frame that is.
            max_click_dist = max(h_frame, w_frame) * 0.10
            if not containing and best_dist > max_click_dist:
                self._person_status_label.config(
                    text="Nothing detected right at that spot — click closer to the center of the person/object.",
                    fg=C["danger"])
                return

            chosen = persons[best_idx]
            item['effect_selected_person'] = -2  # sentinel: selected via fallback (no YOLO ID)
            item['effect_yolo_locked'] = False
            self._effect_selected_person.set(-2)
            item['effect_selected_class'] = 'person'

            mask = self._generate_mask_from_bbox(frame, chosen['bbox'])
            if mask is not None:
                item['effect_person_mask_template'] = mask

            template = self._get_person_appearance(frame, chosen['bbox'])
            if template is not None:
                item['effect_person_template'] = template
                item['effect_face_buffer'] = [template]

            frame_idx0 = self._anchor_tracking_at(item, frame, chosen['center'], chosen['bbox'], is_correction)
            self.update_global_preview()
            bx, by, bw, bh = chosen['bbox']
            self._person_status_label.config(
                text=f"Object selected! ({bw}x{bh}px). Gold outline active.",
                fg=C["accent3"])
            if hasattr(self, '_mt_person_status'):
                self._mt_person_status.config(
                    text=f"Object tracked (ID: {item.get('effect_selected_person', -1)}). Enable Motion Track above.",
                    fg=C["accent3"])
            self.status_label.config(
                text=f"Object selected at ({bx},{by}). Outline rendering.",
                fg=C["accent3"])

        except Exception as ex:
            print("Person selection error:", ex)
            import traceback; traceback.print_exc()
            self._person_status_label.config(text="Selection failed. Try again.", fg=C["danger"])

    def _draw_selection_feedback(self, frame, bbox, label):
        """Draw a colored bounding box on the preview to show who was selected."""
        try:
            import PIL.ImageDraw, PIL.ImageFont
            h_frame, w_frame = frame.shape[:2]
            img = PIL.Image.fromarray(frame)
            pw = getattr(self, '_preview_label_w', max(self.preview_label.winfo_width(), 320))
            ph = getattr(self, '_preview_label_h', max(self.preview_label.winfo_height(), 180))
            img.thumbnail((pw, ph), PIL.Image.LANCZOS)
            disp_w, disp_h = img.size
            ox = getattr(self, '_preview_offset_x', 0)
            oy = getattr(self, '_preview_offset_y', 0)
            draw = ImageDraw.Draw(img)
            # Scale bbox from frame coords to display coords
            sx = disp_w / max(1, w_frame)
            sy = disp_h / max(1, h_frame)
            x, y, bw, bh = bbox
            dx = int(x * sx)
            dy = int(y * sy)
            dbw = int(bw * sx)
            dbh = int(bh * sy)
            for offset in range(3):
                draw.rectangle(
                    [dx - offset, dy - offset, dx + dbw + offset, dy + dbh + offset],
                    outline=(0, 255, 0))
            try:
                font = PIL.ImageFont.truetype("arial.ttf", 14)
            except Exception:
                font = PIL.ImageFont.load_default()
            try:
                bbox_text = draw.textbbox((0, 0), label, font=font)
                text_w = bbox_text[2] - bbox_text[0]
                text_h = bbox_text[3] - bbox_text[1]
            except Exception:
                text_w, text_h = len(label) * 8, 14
            draw.rectangle([dx, dy - text_h - 6, dx + text_w + 8, dy], fill=(0, 200, 0))
            draw.text((dx + 4, dy - text_h - 4), label, fill=(0, 0, 0), font=font)
            self.preview_img = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self.preview_img, text="")
        except Exception as ex:
            print("Selection feedback error:", ex)

    def _get_preview_frame(self, item):
        if item['type'] == 'image':
            try:
                img = PIL.Image.open(item['path']).convert('RGB')
                return np.array(img)
            except Exception:
                return None
        elif item['type'] == 'video':
            try:
                if item['path'] not in self._clip_cache:
                    from moviepy.editor import VideoFileClip as _VFC
                    self._clip_cache_put(item['path'], _VFC(item['path']))
                clip = self._clip_cache[item['path']]
                t = self.playhead_t.get()
                cs = float(item.get('clip_start', 0.0))
                ce = float(item.get('clip_end', 0.0))
                if ce > cs:
                    t = cs + (t % max(0.1, ce - cs))
                else:
                    t = min(t, clip.duration - 0.01)
                frame = clip.get_frame(t)
                return frame
            except Exception:
                return None
        return None

    def _update_person_buttons(self):
        for w in self._person_btn_frame.winfo_children():
            w.destroy()
        persons = self._detected_persons
        sel = self._effect_selected_person.get()
        if not persons:
            tk.Label(self._person_btn_frame, text="No persons detected", bg=C["panel"],
                     fg=C["text_dim"], font=("Segoe UI", 7)).pack(anchor="w")
            return
        for i, p in enumerate(persons):
            if 'id' in p:
                label = f"ID:{p['id']}"
            else:
                label = f"Person {i + 1}"
            is_sel = (p.get('id', i) == sel)
            bg = C["accent"] if is_sel else C["raised"]
            btn = tk.Button(self._person_btn_frame, text=label, bg=bg, fg="white", bd=0,
                           font=("Segoe UI", 7, "bold" if is_sel else "normal"),
                           command=lambda idx=i, pid=p.get('id', i): self._on_person_selected(pid))
            btn.pack(side=tk.LEFT, padx=2, pady=1)

    def _on_person_selected(self, person_id):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_selected_person'] = person_id
        has_yolo = any('id' in p for p in self._detected_persons) if self._detected_persons else False
        item['effect_yolo_locked'] = has_yolo
        self._effect_selected_person.set(person_id)
        self._update_person_buttons()
        # Store appearance template for the selected person
        t = self.playhead_t.get()
        frame_idx = int(t * 30)
        if self._detected_persons:
            if has_yolo:
                # person_id is a YOLO track ID — find matching person
                matched = None
                for p in self._detected_persons:
                    if p.get('id') == person_id:
                        matched = p
                        break
                if matched is None and self._detected_persons:
                    matched = self._detected_persons[0]
                if matched is not None:
                    self._track_person_across_frames(
                        item, frame_idx, [matched], 0)
            else:
                # person_id is an index
                if person_id < len(self._detected_persons):
                    self._track_person_across_frames(
                        item, frame_idx, self._detected_persons, person_id)
        self.update_global_preview()

    def _deselect_person(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_selected_person'] = -1
        item['effect_yolo_locked'] = False
        item['effect_tracking_keyframes'] = {}
        item['effect_person_template'] = None
        item['effect_face_buffer'] = []
        item['effect_mask_user_edited'] = False
        item['effect_selected_class'] = None
        self._effect_selected_person.set(-1)
        self._detected_persons = []
        self._update_person_buttons()
        self._person_status_label.config(text="Object deselected — auto-detect active", fg=C["text_dim"])
        if hasattr(self, '_mt_person_status'):
                self._mt_person_status.config(text="Object deselected — auto-detect active", fg=C["text_dim"])
        self.update_global_preview()

    def _toggle_outline_preview(self):
        self._show_outline_var.set(not self._show_outline_var.get())
        if self._show_outline_var.get():
            self._outline_toggle_btn.config(text="Hide Outline (Preview Mask)", bg="#4a148c")
        else:
            self._outline_toggle_btn.config(text="Show Outline (Preview Mask)", bg="#1a237e")
        self.update_global_preview()

    def _toggle_mask_edit_mode(self):
        if self.selected_idx is None:
            return
        self._mask_edit_active = not self._mask_edit_active
        if self._mask_edit_active:
            item = self.media_queue[self.selected_idx]
            # Use transformed frame (matches preview) so mask aligns correctly
            frame = self._get_transformed_frame(item)
            if frame is None:
                # Fallback to raw frame
                frame = self._get_preview_frame(item)
            if frame is None:
                self._mask_edit_active = False
                return
            h_raw, w_raw = frame.shape[:2]

            # Compute display resolution (same as update_global_preview)
            is_mobile = (self.format_var.get() == "mobile")
            target_w = 540 if is_mobile else 960
            target_h = 960 if is_mobile else 540

            if item.get('effect_mask_painting') is None:
                # Always generate mask from the CURRENT frame so outline
                # matches the displayed frame (not the stale selection-time frame)
                selected_id = int(item.get('effect_selected_person', -1))
                if selected_id >= 0 or selected_id == -2:
                    mp_mask = self._get_selected_person_mask(frame, item)
                else:
                    mp_mask = self._get_mediapipe_mask(frame)
                if mp_mask is not None and mp_mask.max() > 0:
                    mp_mask = cv2.resize(mp_mask, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
                    item['effect_mask_painting'] = mp_mask.copy()
                else:
                    item['effect_mask_painting'] = np.zeros((target_h, target_w), dtype=np.float32)
            if item.get('effect_drawn_mask') is None:
                item['effect_drawn_mask'] = np.zeros((target_h, target_w), dtype=np.float32)
            # Cache the base person mask at display resolution for stable editing preview
            painting = item.get('effect_mask_painting')
            if painting is not None:
                item['effect_editing_base_mask'] = painting.copy()
            else:
                item['effect_editing_base_mask'] = np.ones((target_h, target_w), dtype=np.float32)

            # Ensure mask is at display resolution (re-init if wrong size)
            painting = item.get('effect_mask_painting')
            if painting is not None:
                ph, pw = painting.shape[:2]
                if ph != target_h or pw != target_w:
                    painting = cv2.resize(painting, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
                    item['effect_mask_painting'] = painting

            h, w = target_h, target_w
            self._mask_edit_btn.config(text="Stop Editing Outline", bg="#b71c1c")
            self._show_outline_var.set(True)
            self._outline_toggle_btn.config(text="Hide Outline (Preview Mask)", bg="#4a148c")
            pw = max(self.preview_label.winfo_width(), 320)
            ph = max(self.preview_label.winfo_height(), 180)
            tmp_img = PIL.Image.new("RGB", (w, h))
            tmp_img.thumbnail((pw, ph), PIL.Image.LANCZOS)
            disp_w, disp_h = tmp_img.size
            self._mask_offset_x = (pw - disp_w) // 2
            self._mask_offset_y = (ph - disp_h) // 2
            self._mask_scale_x = w / max(1, disp_w)
            self._mask_scale_y = h / max(1, disp_h)
            self._mask_frame_w = w
            self._mask_frame_h = h
            self.preview_label.config(cursor="circle")
            self.preview_label.bind("<ButtonPress-1>", self._on_mask_paint_start)
            self.preview_label.bind("<B1-Motion>", self._on_mask_paint_drag)
            self.preview_label.bind("<ButtonRelease-1>", self._on_mask_paint_end)
            self.update_global_preview()
            self.status_label.config(text="Editing outline mask — drag on preview to erase/draw", fg=C["accent4"])
        else:
            self._mask_edit_btn.config(text="Start Editing Outline", bg="#e65100")
            self.preview_label.config(cursor="")
            self.preview_label.unbind("<ButtonPress-1>")
            self.preview_label.unbind("<B1-Motion>")
            self.preview_label.unbind("<ButtonRelease-1>")
            self._show_outline_var.set(False)
            self._outline_toggle_btn.config(text="Show Outline (Preview Mask)", bg="#1a237e")
            self.update_global_preview()
            self.status_label.config(text="Outline mask editing stopped", fg=C["accent3"])

    def _on_mask_paint_start(self, event):
        self._mask_last_x = event.x
        self._mask_last_y = event.y
        self._on_mask_paint_draw(event.x, event.y)

    def _on_mask_paint_drag(self, event):
        self._on_mask_paint_draw(event.x, event.y)

    def _on_mask_paint_draw(self, ex, ey):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        mask = item.get('effect_mask_painting')
        if mask is None:
            return
        item['effect_mask_user_edited'] = True
        h, w = mask.shape[:2]
        disp_w = getattr(self, '_preview_disp_w', None)
        disp_h = getattr(self, '_preview_disp_h', None)
        ox = getattr(self, '_preview_offset_x', 0)
        oy = getattr(self, '_preview_offset_y', 0)
        if disp_w is None or disp_h is None:
            pw = max(self.preview_label.winfo_width(), 320)
            ph = max(self.preview_label.winfo_height(), 180)
            img_aspect = w / max(1, h)
            if pw / max(1, ph) > img_aspect:
                disp_h = ph
                disp_w = int(ph * img_aspect)
            else:
                disp_w = pw
                disp_h = int(pw / img_aspect)
            disp_w = max(1, disp_w)
            disp_h = max(1, disp_h)
            ox = (pw - disp_w) // 2
            oy = (ph - disp_h) // 2
        sx = w / max(1, disp_w)
        sy = h / max(1, disp_h)
        cx = int((ex - ox) * sx)
        cy = int((ey - oy) * sy)
        radius = self._mask_brush_size.get()
        erase = self._mask_erase_mode.get() == "erase"
        tip_r = max(2, radius // 6)
        if erase:
            cv2.circle(mask, (cx, cy), tip_r, 0.0, -1)
            if hasattr(self, '_mask_last_x'):
                lx = int((self._mask_last_x - ox) * sx)
                ly = int((self._mask_last_y - oy) * sy)
                cv2.line(mask, (lx, ly), (cx, cy), 0.0, max(1, tip_r))
            drawn = item.get('effect_drawn_mask')
            if drawn is not None and drawn.shape[:2] == (h, w):
                cv2.circle(drawn, (cx, cy), tip_r, 0.0, -1)
                if hasattr(self, '_mask_last_x'):
                    lx = int((self._mask_last_x - ox) * sx)
                    ly = int((self._mask_last_y - oy) * sy)
                    cv2.line(drawn, (lx, ly), (cx, cy), 0.0, max(1, tip_r))
        else:
            cv2.circle(mask, (cx, cy), tip_r, 1.0, -1)
            if hasattr(self, '_mask_last_x'):
                lx = int((self._mask_last_x - ox) * sx)
                ly = int((self._mask_last_y - oy) * sy)
                cv2.line(mask, (lx, ly), (cx, cy), 1.0, max(1, tip_r))
            drawn = item.get('effect_drawn_mask')
            if drawn is not None and drawn.shape[:2] == (h, w):
                cv2.circle(drawn, (cx, cy), tip_r, 1.0, -1)
                if hasattr(self, '_mask_last_x'):
                    lx = int((self._mask_last_x - ox) * sx)
                    ly = int((self._mask_last_y - oy) * sy)
                    cv2.line(drawn, (lx, ly), (cx, cy), 1.0, max(1, tip_r))
        self._mask_last_x = ex
        self._mask_last_y = ey
        self._debounced_preview(interactive=True)

    def _on_mask_paint_end(self, event):
        pass

    def _clear_mask_painting(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_mask_painting'] = None
        item['effect_drawn_mask'] = None
        item['effect_mask_user_edited'] = False
        self.update_global_preview()
        self.status_label.config(text="Outline mask cleared", fg=C["accent3"])

    def _on_effect_setting_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect'] = 'gold_outline' if self._effect_enabled.get() else 'none'
        item['effect_variation'] = self._effect_variation.get()
        item['effect_color_variation'] = self._color_variation.get()
        item['effect_opacity'] = self._effect_opacity.get()
        item['effect_glow'] = self._effect_glow.get()
        item['effect_timing'] = self._effect_timing.get()
        item['effect_start'] = self._effect_start.get()
        item['effect_end'] = self._effect_end.get()
        self._update_variation_desc()
        self._debounced_preview(interactive=True)

    def _on_kb_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['ken_burns_enabled'] = self._kb_enabled.get()
        item['ken_burns_zoom_in'] = self._kb_zoom_in.get()
        item['ken_burns_zoom_out'] = self._kb_zoom_out.get()
        item['ken_burns_pan_x'] = self._kb_pan_x.get()
        item['ken_burns_pan_y'] = self._kb_pan_y.get()
        self._debounced_preview(interactive=True)

    def _on_thug_life_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_thug_life_enabled'] = self._thug_life_enabled.get()
        item['thug_style'] = self._thug_style.get()
        item['thug_cap_enabled'] = self._thug_cap_enabled.get()
        item['thug_entry'] = self._thug_entry.get()
        self._debounced_preview(interactive=True)

    def _on_film_burn_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_film_burn_enabled'] = self._film_burn_enabled.get()
        item['film_burn_intensity'] = self._film_burn_intensity.get()
        item['film_burn_speed'] = self._film_burn_speed.get()
        self._debounced_preview(interactive=True)

    def _on_sun_glare_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_sun_glare_enabled'] = self._sun_glare_enabled.get()
        item['sun_glare_variation'] = self._sun_glare_variation.get()
        item['sun_glare_position'] = self._sun_glare_position.get()
        item['sun_glare_intensity'] = self._sun_glare_intensity.get()
        item['sun_glare_size'] = self._sun_glare_size.get()
        item['sun_glare_speed'] = self._sun_glare_speed.get()
        self._debounced_preview(interactive=True)

    def _on_x_flare_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_x_flare_enabled'] = self._x_flare_enabled.get()
        item['x_flare_variation'] = self._x_flare_variation.get()
        item['x_flare_position'] = self._x_flare_position.get()
        item['x_flare_intensity'] = self._x_flare_intensity.get()
        item['x_flare_size'] = self._x_flare_size.get()
        item['x_flare_speed'] = self._x_flare_speed.get()
        self._debounced_preview(interactive=True)

    def _on_light_flash_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_light_flash_enabled'] = self._light_flash_enabled.get()
        item['light_flash_variation'] = self._light_flash_variation.get()
        item['light_flash_position'] = self._light_flash_position.get()
        item['light_flash_intensity'] = self._light_flash_intensity.get()
        item['light_flash_size'] = self._light_flash_size.get()
        item['light_flash_speed'] = self._light_flash_speed.get()
        item['light_flash_density'] = self._light_flash_density.get()
        self._debounced_preview(interactive=True)

    def _on_canopy_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_canopy_enabled'] = self._canopy_enabled.get()
        item['canopy_light_style'] = self._canopy_light_style.get()
        item['canopy_light_dir'] = self._canopy_light_dir.get()
        item['canopy_fog_density'] = self._canopy_fog_density.get()
        item['canopy_fog_height'] = self._canopy_fog_height.get()
        item['canopy_ray_intensity'] = self._canopy_ray_intensity.get()
        item['canopy_ray_width'] = self._canopy_ray_width.get()
        item['canopy_warmth'] = self._canopy_warmth.get()
        item['canopy_shimmer'] = self._canopy_shimmer.get()
        item['canopy_show_light_source'] = self._canopy_show_light_source.get()
        self._debounced_preview(interactive=True)

    def _on_3d_text_tracking_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_3d_text_enabled'] = self._3d_text_enabled.get()
        item['3d_text_content'] = self._3d_text_content.get()
        item['3d_text_color'] = self._3d_text_color.get()
        item['3d_text_depth'] = self._3d_text_depth.get()
        item['3d_text_shadow'] = self._3d_text_shadow.get()
        item['3d_text_style'] = self._3d_text_style.get()
        item['3d_text_full_clip'] = self._3d_text_full_clip.get()
        try:
            item['3d_text_start'] = max(0.0, float(self._3d_text_start.get()))
        except (tk.TclError, ValueError):
            pass
        try:
            item['3d_text_end'] = max(0.05, float(self._3d_text_end.get()))
        except (tk.TclError, ValueError):
            pass
        try:
            item['3d_text_fade'] = max(0.0, float(self._3d_text_fade.get()))
        except (tk.TclError, ValueError):
            pass
        # --- Camera speed ---
        try:
            item['3d_cam_speed'] = max(0.0, float(self._3d_cam_speed.get()))
        except (tk.TclError, ValueError):
            pass
        self._debounced_preview(interactive=True)

    def _on_motion_track_changed(self):
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        item['effect_motion_track_enabled'] = self._motion_track_enabled.get()
        item['motion_track_mode'] = self._motion_track_mode.get()
        item['motion_track_name'] = self._motion_track_name.get()
        item['motion_track_color'] = self._motion_track_color.get()
        item['motion_track_text_color'] = self._motion_track_text_color.get()
        item['motion_track_arrow_size'] = self._motion_track_arrow_size.get()
        item['motion_track_arrow_len'] = self._motion_track_arrow_len.get()
        item['motion_track_text_size'] = self._motion_track_text_size.get()
        item['motion_track_offset_y'] = self._motion_track_offset_y.get()
        self._debounced_preview(interactive=True)

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

    def _nudge_thug_accessory(self, dx=0.0, dy=0.0, scale_mult=1.0, rotate_delta=0.0,
                               toggle_flip_h=False, toggle_flip_v=False):
        """Apply a manual adjustment to whichever accessory is currently
        selected in the Thug Life panel's 'Editing:' dropdown. Adjustments
        are layered on top of the auto-detected position and persist with
        the clip (saved into item['thug_<accessory>_override'])."""
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        target = self._thug_adjust_target.get()
        key = f'thug_{target}_override'
        ov = dict(item.get(key) or {'dx': 0.0, 'dy': 0.0, 'scale': 1.0, 'rotation': 0.0,
                                     'flip_h': False, 'flip_v': False})
        ov['dx'] = ov.get('dx', 0.0) + dx
        ov['dy'] = ov.get('dy', 0.0) + dy
        ov['scale'] = max(0.1, min(5.0, ov.get('scale', 1.0) * scale_mult))
        ov['rotation'] = ov.get('rotation', 0.0) + rotate_delta
        if toggle_flip_h:
            ov['flip_h'] = not ov.get('flip_h', False)
        if toggle_flip_v:
            ov['flip_v'] = not ov.get('flip_v', False)
        item[key] = ov
        self._debounced_preview(interactive=True)

    def _reset_thug_accessory(self):
        """Clear the manual override for whichever accessory is currently
        selected, reverting it to pure auto-detected placement."""
        if self.selected_idx is None:
            return
        item = self.media_queue[self.selected_idx]
        target = self._thug_adjust_target.get()
        item[f'thug_{target}_override'] = None
        self._debounced_preview(interactive=True)

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

    # ==========================================
    # DATA MODELS
    # ==========================================
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

    # ==========================================
    #  SPLIT AND CUT LOGIC
    # ==========================================
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

    # ==========================================
    # TIMELINE MATH & LOGIC
    # ==========================================
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

    # ==========================================
    # LIVE PLAYBACK ENGINE
    # ==========================================
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

    def update_global_preview(self):
        if not _MOVIEPY_LOADED:
            return
        t = self.playhead_t.get()
        active_item = None
        local_t = 0.0

        for item in self.media_queue:
            start = item.get("tl_start", 0.0)
            dur = self._item_duration(item)
            if start <= t < start + dur:
                active_item = item
                # For highlight clips, don't apply speed here — handle it below
                if item.get('_highlight_effect'):
                    local_t = t - start
                else:
                    local_t = (t - start) * item.get("speed", 1.0)
                break

        if not active_item:
            self.preview_label.config(image='', text="● PLAYBACK  (No clip at this position)", fg="#333333")
            return

        try:
            is_mobile = (self.format_var.get() == "mobile")
            # Low-res mode for interactive slider dragging — half the normal res
            if self._interactive_mode:
                target_w = 270 if is_mobile else 480
                target_h = 480 if is_mobile else 270
            else:
                target_w = 540 if is_mobile else 960
                target_h = 960 if is_mobile else 540
            scale_val = active_item.get('scale', 1.0)
            text_3d_enabled = active_item.get('effect_3d_text_enabled', False)

            if active_item['type'] == 'title':
                clip = self.build_finch_title_card(target_w, target_h, active_item, preview_mode=True)
                clip_dur = clip.duration
                if active_item.get('text'):
                    t_start = active_item.get('text_start', 0.0)
                    t_end = active_item.get('text_end', 3.0)
                    if t_start <= local_t <= t_end:
                        lt_t = local_t - t_start
                        lt_dur = t_end - t_start
                        lt_style = active_item.get('lt_style', 'News Headline')
                        if lt_style == 'News Headline':
                            lt_layers = self.build_news_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                        elif lt_style == 'Purple Designer Box':
                            lt_layers = self.build_designer_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                        elif lt_style == 'Static Aurora Tile (Bracket)':
                            lt_layers = self.build_tile_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                        else:
                            lt_layers = self.build_magical_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                        comp = CompositeVideoClip([clip.set_duration(clip_dur)] + [l.set_start(0.0) for l in lt_layers], size=(target_w, target_h)).set_duration(clip_dur)
                        frame_array = comp.get_frame(min(lt_t, comp.duration - 0.01))
                        comp.close()
                    else:
                        frame_array = clip.get_frame(min(local_t, clip.duration - 0.01))
                else:
                    frame_array = clip.get_frame(min(local_t, clip.duration - 0.01))
                img = PIL.Image.fromarray(frame_array)
                clip.close()
            else:
                if active_item['type'] == 'video' and active_item.get('path'):
                    if active_item['path'] not in self._clip_cache:
                        self._clip_cache_put(active_item['path'], VideoFileClip(active_item['path']))
                    raw = self._clip_cache[active_item['path']]
                    read_t = active_item.get('clip_start', 0.0) + local_t

                    # --- HIGHLIGHT CLIP EFFECT (PREVIEW) ---
                    hl_effect = active_item.get('_highlight_effect')
                    if hl_effect == 'reverse':
                        # Show reversed time within the clip
                        clip_dur = self._item_duration(active_item)
                        read_t = active_item.get('clip_start', 0.0) + (clip_dur - local_t)
                    elif hl_effect == 'slowmo_zoom':
                        speed = max(0.1, active_item.get('speed', 0.3))
                        read_t = active_item.get('clip_start', 0.0) + local_t * speed

                    if raw.duration is not None:
                        read_t = max(0.0, min(read_t, raw.duration - 0.01))
                    read_t = max(0.0, read_t)
                    frame = raw.get_frame(read_t)
                    base_img = PIL.Image.fromarray(frame)

                    # Apply slowmo_zoom visual zoom effect (skip in interactive/low-res mode)
                    if hl_effect == 'slowmo_zoom' and not self._interactive_mode:
                        zoom_level = active_item.get('_highlight_zoom', 1.5)
                        clip_dur = self._item_duration(active_item)
                        if clip_dur > 0.01:
                            region_progress = local_t / clip_dur
                            current_zoom = 1.0 + (zoom_level - 1.0) * min(1.0, region_progress * 1.5)
                            w, h = base_img.size
                            new_w = max(1, int(w * current_zoom))
                            new_h = max(1, int(h * current_zoom))
                            zoomed = base_img.resize((new_w, new_h), PIL.Image.BILINEAR)
                            left = (new_w - w) // 2
                            top = (new_h - h) // 2
                            base_img = zoomed.crop((left, top, left + w, top + h))

                    rot = active_item.get('rotation', 0)
                    if rot != 0: base_img = base_img.rotate(-rot, expand=True)
                    if active_item.get('flip_h', False): base_img = base_img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
                    if active_item.get('flip_v', False): base_img = base_img.transpose(PIL.Image.FLIP_TOP_BOTTOM)

                    base_clip = ImageClip(np.array(base_img))
                    if self.auto_rotate_var.get():
                        if target_w > target_h and base_clip.w < base_clip.h: base_clip = self.safe_transform(base_clip, 90, False, False)
                        elif target_w < target_h and base_clip.w > base_clip.h: base_clip = self.safe_transform(base_clip, -90, False, False)

                    ken_burns = active_item.get('ken_burns_enabled', False)
                    if self.smart_fill_var.get():
                        base_sf = max(target_w / base_clip.w, target_h / base_clip.h) * scale_val
                    else:
                        base_sf = min(target_w / base_clip.w, target_h / base_clip.h) * scale_val

                    if ken_burns:
                        clip_dur = max(self._item_duration(active_item), 0.01)
                        t_prog = min(local_t / clip_dur, 1.0)
                        kb_zoom_in = float(active_item.get('ken_burns_zoom_in', 1.0))
                        kb_zoom_out = float(active_item.get('ken_burns_zoom_out', 1.3))
                        kb_pan_x = float(active_item.get('ken_burns_pan_x', 0.0))
                        kb_pan_y = float(active_item.get('ken_burns_pan_y', 0.0))
                        zoom = kb_zoom_in + (kb_zoom_out - kb_zoom_in) * t_prog

                        fit_w = int(base_clip.w * base_sf)
                        fit_h = int(base_clip.h * base_sf)
                        ref_clip = base_clip.fx(vfx.resize, base_sf).fx(
                            vfx.crop, x_center=fit_w / 2, y_center=fit_h / 2, width=target_w, height=target_h)
                        ref_frame = ref_clip.get_frame(0)
                        ref_clip.close()

                        # NOTE: 3D text is intentionally NOT composited here — it's
                        # applied later, on the already-zoomed final frame, at a
                        # fixed size/position. That keeps it a flat, fixed-size
                        # marker (like an AR doodle) instead of scaling up with
                        # the Ken Burns zoom.
                        zoomed = self._apply_kenburns_zoom_numpy(
                            ref_frame, zoom, kb_pan_x, kb_pan_y, t_prog, target_w, target_h)
                        base_clip = ImageClip(zoomed)
                    elif self.smart_fill_var.get():
                        new_w = int(base_clip.w * base_sf)
                        new_h = int(base_clip.h * base_sf)
                        base_clip = base_clip.fx(vfx.resize, base_sf).fx(vfx.crop, x_center=new_w/2, y_center=new_h/2, width=target_w, height=target_h)
                    else:
                        base_clip = base_clip.fx(vfx.resize, base_sf)

                    vlayers = [ColorClip(size=(target_w, target_h), color=(0, 0, 0)).set_duration(1.0), base_clip.set_position("center")]

                    lt_t = 0.0
                    if active_item.get('text'):
                        t_start = active_item.get('text_start', 0.0)
                        t_end = active_item.get('text_end', 3.0)
                        if t_start <= local_t <= t_end:
                            lt_t = local_t - t_start
                            lt_dur = t_end - t_start
                            lt_style = active_item.get('lt_style', 'Static Aurora Tile (Bracket)')
                            if lt_style == 'Purple Designer Box':
                                lt_layers = self.build_designer_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                            elif lt_style == 'Static Aurora Tile (Bracket)':
                                lt_layers = self.build_tile_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                            else:
                                lt_layers = self.build_magical_lower_third(active_item['text'], target_w, target_h, lt_dur, lt_dur)
                            vlayers.extend([l.set_start(0.0) for l in lt_layers])

                    comp = CompositeVideoClip(vlayers, size=(target_w, target_h))
                    frame_array = comp.get_frame(lt_t)
                    img = PIL.Image.fromarray(frame_array)
                    comp.close()
                    base_clip.close()

                elif active_item['type'] == 'image' and active_item.get('path'):
                    img_path = active_item['path']
                    if img_path not in self._img_cache:
                        self._img_cache[img_path] = PIL.Image.open(img_path).convert("RGB").copy()
                        if len(self._img_cache) > 20:
                            first_key = next(iter(self._img_cache))
                            del self._img_cache[first_key]
                    base_img = self._img_cache[img_path].copy()
                    rot = active_item.get('rotation', 0)
                    if rot != 0: base_img = base_img.rotate(-rot, expand=True)
                    if active_item.get('flip_h', False): base_img = base_img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
                    if active_item.get('flip_v', False): base_img = base_img.transpose(PIL.Image.FLIP_TOP_BOTTOM)
                    ken_burns = active_item.get('ken_burns_enabled', False)
                    if self.smart_fill_var.get():
                        base_sf = max(target_w / base_img.width, target_h / base_img.height) * scale_val
                    else:
                        base_sf = min(target_w / base_img.width, target_h / base_img.height) * scale_val

                    if ken_burns:
                        clip_dur = max(self._item_duration(active_item), 0.01)
                        t_prog = min(local_t / clip_dur, 1.0)
                        kb_zoom_in = float(active_item.get('ken_burns_zoom_in', 1.0))
                        kb_zoom_out = float(active_item.get('ken_burns_zoom_out', 1.3))
                        kb_pan_x = float(active_item.get('ken_burns_pan_x', 0.0))
                        kb_pan_y = float(active_item.get('ken_burns_pan_y', 0.0))
                        zoom = kb_zoom_in + (kb_zoom_out - kb_zoom_in) * t_prog

                        fit_w = max(1, int(round(base_img.width * base_sf)))
                        fit_h = max(1, int(round(base_img.height * base_sf)))
                        fitted = base_img.resize((fit_w, fit_h), PIL.Image.LANCZOS)
                        ref_canvas = PIL.Image.new("RGB", (target_w, target_h), (0, 0, 0))
                        ref_canvas.paste(fitted, ((target_w - fit_w) // 2, (target_h - fit_h) // 2))
                        ref_frame = np.array(ref_canvas)

                        # NOTE: 3D text is intentionally NOT composited here — it's
                        # applied later, on the already-zoomed final frame, at a
                        # fixed size/position. That keeps it a flat, fixed-size
                        # marker (like an AR doodle) instead of scaling up with
                        # the Ken Burns zoom.
                        zoomed = self._apply_kenburns_zoom_numpy(
                            ref_frame, zoom, kb_pan_x, kb_pan_y, t_prog, target_w, target_h)
                        base_img = PIL.Image.fromarray(zoomed)
                    elif self.smart_fill_var.get():
                        sf = base_sf
                        base_img = base_img.resize((int(base_img.width * sf), int(base_img.height * sf)), PIL.Image.LANCZOS)
                        left = (base_img.width - target_w) // 2
                        top = (base_img.height - target_h) // 2
                        base_img = base_img.crop((left, top, left + target_w, top + target_h))
                    else:
                        sf = base_sf
                        base_img = base_img.resize((int(base_img.width * sf), int(base_img.height * sf)), PIL.Image.LANCZOS)
                    img = base_img

                else:
                    base_img = PIL.Image.new("RGB", (target_w, target_h), (20, 20, 20))
                    ImageDraw.Draw(base_img).text((100, 150), "PLACEHOLDER", fill=(200, 100, 0))
                    img = base_img

            if self._mask_edit_active or self._show_outline_var.get() or (active_item.get('effect') == 'gold_outline' and self.effect_global_enabled.get()):
                if self._show_outline_var.get():
                    frame_arr = np.array(img)
                    h_f, w_f = frame_arr.shape[:2]
                    painting = active_item.get('effect_mask_painting')
                    if painting is not None:
                        ph_p, pw_p = painting.shape[:2]
                        if ph_p != h_f or pw_p != w_f:
                            paint_resized = cv2.resize(painting, (w_f, h_f), interpolation=cv2.INTER_LINEAR)
                        else:
                            paint_resized = painting
                    else:
                        paint_resized = np.ones((h_f, w_f), dtype=np.float32)
                    erase_edges = np.zeros((h_f, w_f), dtype=np.float32)
                    draw_edges = np.zeros((h_f, w_f), dtype=np.float32)
                    if self._mask_edit_active and painting is not None:
                        person_mask = active_item.get('effect_editing_base_mask')
                        if person_mask is not None and person_mask.max() > 0:
                            if person_mask.shape[:2] != (h_f, w_f):
                                person_mask = cv2.resize(person_mask, (w_f, h_f), interpolation=cv2.INTER_LINEAR)
                            orig_uint8 = (np.clip(person_mask, 0, 1) * 255).astype(np.uint8)
                            erase_edges = cv2.Canny(orig_uint8, 30, 90)
                            erase_edges = cv2.dilate(erase_edges, np.ones((3, 3), np.uint8), iterations=1)
                            erase_edges = cv2.GaussianBlur(erase_edges, (3, 3), 0).astype(np.float32) / 255.0
                            erase_edges = erase_edges * np.clip(paint_resized, 0, 1)
                    drawn = active_item.get('effect_drawn_mask')
                    if drawn is not None:
                        dw, ddh = drawn.shape[:2]
                        if ddh != h_f or dw != w_f:
                            drawn_resized = cv2.resize(drawn, (w_f, h_f), interpolation=cv2.INTER_LINEAR)
                        else:
                            drawn_resized = drawn
                        drawn_uint8 = (np.clip(drawn_resized, 0, 1) * 255).astype(np.uint8)
                        draw_edges = cv2.Canny(drawn_uint8, 30, 90)
                        draw_edges = cv2.dilate(draw_edges, np.ones((3, 3), np.uint8), iterations=1)
                        draw_edges = cv2.GaussianBlur(draw_edges, (3, 3), 0).astype(np.float32) / 255.0
                    edges = np.maximum(erase_edges, draw_edges)
                    overlay = frame_arr.copy().astype(np.float32)
                    green = np.array([0.0, 1.0, 0.0], dtype=np.float32).reshape(1, 1, 3)
                    overlay = overlay + edges[..., np.newaxis] * green * 250.0
                    overlay = np.clip(overlay, 0, 255).astype(np.uint8)
                    img = PIL.Image.fromarray(overlay)
                else:
                    frame_arr = np.array(img)
                    frame_arr = self.apply_dreamy_angel_effect(frame_arr, active_item, local_t)
                    img = PIL.Image.fromarray(frame_arr)

            thug_enabled = active_item.get('effect_thug_life_enabled', False)
            if thug_enabled and not self._interactive_mode:
                frame_arr = np.array(img)
                frame_arr = self.apply_thug_life_effect(frame_arr, active_item, local_t)
                img = PIL.Image.fromarray(frame_arr)

            film_burn_enabled = active_item.get('effect_film_burn_enabled', False)
            if film_burn_enabled and not self._interactive_mode:
                frame_arr = np.array(img)
                frame_arr = self.apply_film_burn_effect(frame_arr, active_item, local_t)
                img = PIL.Image.fromarray(frame_arr)

            sun_glare_enabled = active_item.get('effect_sun_glare_enabled', False)
            if sun_glare_enabled and not self._interactive_mode:
                frame_arr = np.array(img)
                frame_arr = self.apply_sun_glare_effect(frame_arr, active_item, local_t)
                img = PIL.Image.fromarray(frame_arr)

            x_flare_enabled = active_item.get('effect_x_flare_enabled', False)
            if x_flare_enabled and not self._interactive_mode:
                frame_arr = np.array(img)
                frame_arr = self.apply_x_flare_effect(frame_arr, active_item, local_t)
                img = PIL.Image.fromarray(frame_arr)

            light_flash_enabled = active_item.get('effect_light_flash_enabled', False)
            if light_flash_enabled and not self._interactive_mode:
                frame_arr = np.array(img)
                frame_arr = self.apply_light_flash_effect(frame_arr, active_item, local_t)
                img = PIL.Image.fromarray(frame_arr)

            canopy_enabled = active_item.get('effect_canopy_enabled', False)
            if canopy_enabled:
                frame_arr = np.array(img)
                frame_arr = self.apply_canopy_effect(frame_arr, active_item, local_t)
                img = PIL.Image.fromarray(frame_arr)

            # ── 3D TEXT TRACKING ──────────────────────────────────────────
            # Always applied on the final (already-zoomed/panned) frame, at a
            # fixed size and position — a flat AR-doodle-style marker that
            # doesn't scale with any Ken Burns zoom on the clip. Whether it's
            # visible right now is decided inside apply_3d_text_tracking_effect
            # (the "WHEN IT'S VISIBLE" start/end/fade settings).
            try:
                if text_3d_enabled:
                    frame_arr = np.array(img)
                    frame_arr = self.apply_3d_text_tracking_effect(frame_arr, active_item, local_t)
                    img = PIL.Image.fromarray(frame_arr)
            except Exception as ex:
                print("3D Text Tracking error:", ex)
                import traceback; traceback.print_exc()

            # Draw the move/resize/rotate handles when actively editing this clip's text
            try:
                if (getattr(self, '_3d_text_place_active', False) and self.selected_idx is not None
                        and self.media_queue[self.selected_idx] is active_item):
                    img = self._draw_3d_text_handles(img, active_item)
            except Exception:
                pass
            # ─────────────────────────────────────────────────────────────────

            # ── MOTION TRACK (arrow + name tracking) ────────────────────────
            try:
                if active_item.get('effect_motion_track_enabled', False):
                    frame_arr = np.array(img)
                    frame_arr = self.apply_motion_track_effect(frame_arr, active_item, local_t)
                    img = PIL.Image.fromarray(frame_arr)
            except Exception as ex:
                print("Motion Track error:", ex)
                import traceback; traceback.print_exc()
            # ─────────────────────────────────────────────────────────────────

            # ── COLOR FILTER ────────────────────────────────────────────────
            try:
                filter_enabled = self._filter_global_enabled.get()
                per_clip = active_item.get('filter_enabled', False)
                if per_clip:
                    filter_enabled = True
                if filter_enabled:
                    frame_arr = np.array(img)
                    if per_clip:
                        fs = active_item.get('filter_style', 'Cinematic Warm')
                        fi = active_item.get('filter_intensity', 1.0)
                        fw = active_item.get('filter_warmth', 0.5)
                        fsat = active_item.get('filter_saturation', 1.0)
                        fb = active_item.get('filter_fade_blacks', 0.15)
                    else:
                        fs = self._filter_style.get()
                        fi = self._filter_intensity.get()
                        fw = self._filter_warmth.get()
                        fsat = self._filter_saturation.get()
                        fb = self._filter_fade_blacks.get()
                    frame_arr = self.apply_color_filter(frame_arr, fs, fi, fw, fsat, fb)
                    img = PIL.Image.fromarray(frame_arr)
            except Exception:
                pass
            # ─────────────────────────────────────────────────────────────────

            # ── TRANSITION BLENDING ──────────────────────────────────────────
            try:
                img = self._apply_transition_blend(img, t, target_w, target_h)
            except Exception:
                pass
            # ─────────────────────────────────────────────────────────────────

            # Cache full-res frame BEFORE thumbnailing — used by person click
            # detection so YOLO runs on the exact same frame the user sees.
            self._preview_full_frame = np.array(img)

            pw = max(self.preview_label.winfo_width(), 320)
            ph = max(self.preview_label.winfo_height(), 180)
            img.thumbnail((pw, ph), PIL.Image.LANCZOS)
            # Store actual display dimensions for click/box coordinate mapping
            self._preview_disp_w, self._preview_disp_h = img.size
            self._preview_label_w = pw
            self._preview_label_h = ph
            self._preview_offset_x = (pw - self._preview_disp_w) // 2
            self._preview_offset_y = (ph - self._preview_disp_h) // 2

            self.preview_img = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self.preview_img, text="")
        except Exception as ex:
            print("PREVIEW ERROR:", ex)
            traceback.print_exc()

    # ──────────────────────────────────────────────────────────────────────
    #  TRANSITION RENDERING
    # ──────────────────────────────────────────────────────────────────────
    def _render_clip_frame(self, item, local_t, target_w, target_h, is_mobile):
        """Render a single frame from *item* at *local_t* into a PIL Image
        sized to (target_w, target_h).  Handles video, image, and title clips
        including rotation, flip, scale, smart-fill and Ken Burns."""
        scale_val = item.get('scale', 1.0)
        if item['type'] == 'title':
            clip = self.build_finch_title_card(target_w, target_h, item, preview_mode=True)
            clip_dur = clip.duration if clip.duration is not None else 5.0
            if item.get('text'):
                t_start = item.get('text_start', 0.0)
                t_end = item.get('text_end', 3.0)
                if t_start <= local_t <= t_end:
                    lt_t = local_t - t_start
                    lt_dur = t_end - t_start
                    lt_style = item.get('lt_style', 'News Headline')
                    if lt_style == 'News Headline':
                        lt_layers = self.build_news_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                    elif lt_style == 'Purple Designer Box':
                        lt_layers = self.build_designer_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                    elif lt_style == 'Static Aurora Tile (Bracket)':
                        lt_layers = self.build_tile_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                    else:
                        lt_layers = self.build_magical_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                    comp = CompositeVideoClip([clip.set_duration(clip_dur)] + [l.set_start(0.0) for l in lt_layers], size=(target_w, target_h)).set_duration(clip_dur)
                    comp_dur = comp.duration if comp.duration is not None else clip_dur
                    frame_array = comp.get_frame(min(lt_t, max(0.01, comp_dur) - 0.01))
                    comp.close()
                else:
                    frame_array = clip.get_frame(min(max(0, local_t), max(0.01, clip_dur) - 0.01))
            else:
                frame_array = clip.get_frame(min(max(0, local_t), max(0.01, clip_dur) - 0.01))
            img = PIL.Image.fromarray(frame_array)
            clip.close()
            return img

        if item['type'] == 'video' and item.get('path'):
            if item['path'] not in self._clip_cache:
                self._clip_cache_put(item['path'], VideoFileClip(item['path']))
            raw = self._clip_cache[item['path']]
            read_t = item.get('clip_start', 0.0) + local_t
            if raw.duration is not None:
                read_t = min(read_t, raw.duration - 0.01)
            frame = raw.get_frame(max(0, read_t))
            base_img = PIL.Image.fromarray(frame)
        elif item['type'] == 'image' and item.get('path'):
            img_path = item['path']
            if img_path not in self._img_cache:
                self._img_cache[img_path] = PIL.Image.open(img_path).convert("RGB").copy()
                if len(self._img_cache) > 20:
                    first_key = next(iter(self._img_cache))
                    del self._img_cache[first_key]
            base_img = self._img_cache[img_path].copy()
        else:
            base_img = PIL.Image.new("RGB", (target_w, target_h), (20, 20, 20))
            ImageDraw.Draw(base_img).text((100, 150), "PLACEHOLDER", fill=(200, 100, 0))
            return base_img

        rot = item.get('rotation', 0)
        if rot != 0:
            base_img = base_img.rotate(-rot, expand=True)
        if item.get('flip_h', False):
            base_img = base_img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
        if item.get('flip_v', False):
            base_img = base_img.transpose(PIL.Image.FLIP_TOP_BOTTOM)

        base_clip = ImageClip(np.array(base_img))
        if self.auto_rotate_var.get():
            if target_w > target_h and base_clip.w < base_clip.h:
                base_clip = self.safe_transform(base_clip, 90, False, False)
            elif target_w < target_h and base_clip.w > base_clip.h:
                base_clip = self.safe_transform(base_clip, -90, False, False)

        if self.smart_fill_var.get():
            base_sf = max(target_w / base_clip.w, target_h / base_clip.h) * scale_val
        else:
            base_sf = min(target_w / base_clip.w, target_h / base_clip.h) * scale_val

        ken_burns = item.get('ken_burns_enabled', False)
        clip_dur = max(self._item_duration(item), 0.01)
        if ken_burns:
            t_prog = min(local_t / clip_dur, 1.0)
            kb_zoom_in = float(item.get('ken_burns_zoom_in', 1.0))
            kb_zoom_out = float(item.get('ken_burns_zoom_out', 1.3))
            kb_pan_x = float(item.get('ken_burns_pan_x', 0.0))
            kb_pan_y = float(item.get('ken_burns_pan_y', 0.0))
            zoom = kb_zoom_in + (kb_zoom_out - kb_zoom_in) * t_prog
            total_sf = base_sf * zoom
            new_w = int(base_clip.w * total_sf)
            new_h = int(base_clip.h * total_sf)
            offset_x = kb_pan_x * target_w * 0.5 * t_prog
            offset_y = kb_pan_y * target_h * 0.5 * t_prog
            cx = new_w / 2 + offset_x
            cy = new_h / 2 + offset_y
            base_clip = base_clip.fx(vfx.resize, total_sf).fx(vfx.crop, x_center=cx, y_center=cy, width=target_w, height=target_h)
        elif self.smart_fill_var.get():
            new_w = int(base_clip.w * base_sf)
            new_h = int(base_clip.h * base_sf)
            base_clip = base_clip.fx(vfx.resize, base_sf).fx(vfx.crop, x_center=new_w/2, y_center=new_h/2, width=target_w, height=target_h)
        else:
            base_clip = base_clip.fx(vfx.resize, base_sf)

        vlayers = [ColorClip(size=(target_w, target_h), color=(0, 0, 0)).set_duration(clip_dur), base_clip.set_position("center")]
        if item.get('text'):
            t_start = item.get('text_start', 0.0)
            t_end = item.get('text_end', 3.0)
            if t_start <= local_t <= t_end:
                lt_dur = t_end - t_start
                lt_style = item.get('lt_style', 'Static Aurora Tile (Bracket)')
                if lt_style == 'Purple Designer Box':
                    lt_layers = self.build_designer_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                elif lt_style == 'Static Aurora Tile (Bracket)':
                    lt_layers = self.build_tile_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                else:
                    lt_layers = self.build_magical_lower_third(item['text'], target_w, target_h, lt_dur, lt_dur)
                vlayers.extend([l.set_start(0.0) for l in lt_layers])
        comp = CompositeVideoClip(vlayers, size=(target_w, target_h))
        comp_dur = comp.duration if comp.duration is not None else clip_dur
        frame_array = comp.get_frame(min(max(0, local_t), max(0.01, comp_dur) - 0.01))
        img = PIL.Image.fromarray(frame_array)
        comp.close()
        base_clip.close()
        return img

    def _apply_transition_blend(self, img, t, target_w, target_h):
        """If the playhead is inside a transition zone between two adjacent
        clips, blend the outgoing and incoming frames according to the
        transition type.  Returns the (possibly blended) PIL Image."""
        td = self.TRANSITION_DUR
        if td <= 0:
            return img

        is_mobile = (self.format_var.get() == "mobile")

        for idx in range(len(self.media_queue) - 1):
            item_a = self.media_queue[idx]
            item_b = self.media_queue[idx + 1]
            a_start = item_a.get("tl_start", 0.0)
            a_dur = self._item_duration(item_a)
            a_end = a_start + a_dur
            b_start = item_b.get("tl_start", 0.0)

            trans = item_a.get("trans", "Crossfade")
            if trans == "Hard Cut":
                continue

            overlap = max(0.0, a_end - b_start)
            zone = min(td, overlap / 2.0) if overlap > 0 else td

            in_a_tail = (a_end - zone) <= t < a_end
            in_b_head = b_start <= t < (b_start + zone)

            if in_a_tail or in_b_head:
                if in_a_tail:
                    progress = (t - (a_end - zone)) / zone
                else:
                    progress = (t - b_start) / zone + 1.0
                progress = max(0.0, min(1.0, progress))

                local_a = self._item_duration(item_a) - zone + (t - (a_end - zone)) if in_a_tail else self._item_duration(item_a)
                local_a = max(0.0, min(local_a, self._item_duration(item_a) - 0.01))
                if in_b_head:
                    local_b = t - b_start
                else:
                    local_b = 0.0
                local_b = max(0.0, min(local_b, self._item_duration(item_b) - 0.01))

                frame_a = self._render_clip_frame(item_a, local_a, target_w, target_h, is_mobile)
                frame_b = self._render_clip_frame(item_b, local_b, target_w, target_h, is_mobile)

                arr_a = np.array(frame_a).astype(np.float32)
                arr_b = np.array(frame_b).astype(np.float32)

                if arr_a.shape != arr_b.shape:
                    return img

                p = progress

                if trans == "Crossfade":
                    blended = arr_a * (1 - p) + arr_b * p

                elif trans == "Dip to Black":
                    if p < 0.5:
                        blended = arr_a * (1 - p * 2)
                    else:
                        blended = arr_b * ((p - 0.5) * 2)

                elif trans == "Slide Left":
                    shift = int(p * target_w)
                    left_a = arr_a[:, shift:]
                    pad_a = np.zeros((target_h, shift, 3), dtype=np.float32)
                    slide_a = np.concatenate([left_a, pad_a], axis=1)
                    right_b = arr_b[:, :target_w - shift]
                    pad_b = np.zeros((target_h, target_w - right_b.shape[1], 3), dtype=np.float32)
                    slide_b = np.concatenate([pad_b, right_b], axis=1)
                    blended = slide_a * (1 - p) + slide_b * p

                elif trans == "Slide Up":
                    shift = int(p * target_h)
                    top_a = arr_a[shift:]
                    pad_a = np.zeros((shift, target_w, 3), dtype=np.float32)
                    slide_a = np.concatenate([top_a, pad_a], axis=0)
                    bot_b = arr_b[:target_h - shift]
                    pad_b = np.zeros((target_h - bot_b.shape[0], target_w, 3), dtype=np.float32)
                    slide_b = np.concatenate([pad_b, bot_b], axis=0)
                    blended = slide_a * (1 - p) + slide_b * p

                elif trans == "Zoom In Fade":
                    if p < 0.4:
                        fade = p / 0.4
                        blended = arr_a * (1 - fade)
                    else:
                        fade = (p - 0.4) / 0.6
                        scale = 1.0 + fade * 0.15
                        zw = int(target_w * scale)
                        zh = int(target_h * scale)
                        b_zoomed = cv2.resize(arr_b, (zw, zh))
                        x0 = (zw - target_w) // 2
                        y0 = (zh - target_h) // 2
                        b_cropped = b_zoomed[y0:y0 + target_h, x0:x0 + target_w]
                        blended = b_cropped * fade

                elif trans == "Bright Flash":
                    Y, X = np.mgrid[0:target_h, 0:target_w].astype(np.float32)
                    h, w = target_h, target_w
                    flare_positions = [
                        (0.18, 0.22), (0.75, 0.15), (0.50, 0.50),
                        (0.25, 0.78), (0.80, 0.70), (0.12, 0.55),
                        (0.88, 0.38), (0.42, 0.18), (0.62, 0.85),
                    ]
                    flare_scale = min(w, h) * 0.018
                    combined = np.zeros((h, w), dtype=np.float32)

                    for fi, (fx, fy) in enumerate(flare_positions):
                        px, py = fx * w, fy * h
                        dx, dy = X - px, Y - py
                        d = np.sqrt(dx**2 + dy**2)
                        arm_len = flare_scale * (2.5 + 1.5 * np.sin(fi * 1.7))
                        falloff = np.exp(-d**2 / (2 * arm_len**2))
                        da = np.abs(dy - dx)
                        db = np.abs(dy + dx)
                        arm_w = flare_scale * 0.6
                        xshape = np.maximum(np.clip(1.0 - da / arm_w, 0, 1),
                                             np.clip(1.0 - db / arm_w, 0, 1))
                        star = falloff * xshape

                        if p < 0.10:
                            appear = p / 0.10
                            twinkle = (np.sin(fi * 3.14 + p * 60.0) * 0.5 + 0.5)
                            intensity = appear * twinkle * 0.35
                        elif p < 0.30:
                            appear = (p - 0.10) / 0.20
                            twinkle = (np.sin(fi * 3.14 + p * 80.0) * 0.5 + 0.5)
                            intensity = (0.35 + appear * 0.55) * twinkle
                        elif p < 0.45:
                            grow = (p - 0.30) / 0.15
                            intensity = 0.9 + grow * 0.1
                            if fi == 4:
                                intensity = 1.0 + grow * 2.0
                                falloff2 = np.exp(-d**2 / (2 * (arm_len * (1 + grow * 4))**2))
                                star = falloff2 * xshape
                            else:
                                star = falloff * xshape * (1 + grow)
                        else:
                            intensity = 0.0

                        combined = np.maximum(combined, star * min(intensity, 3.0))

                    combined = np.clip(combined, 0, 1)

                    if p < 0.45:
                        blended = arr_a * (1 - combined[..., np.newaxis]) + 255.0 * (combined[..., np.newaxis])
                    elif p < 0.55:
                        blended = np.full_like(arr_a, 255.0)
                    else:
                        fade = (p - 0.55) / 0.45
                        ease = fade * fade * (3 - 2 * fade)
                        blended = arr_b * ease + 255.0 * (1 - ease)

                elif trans == "Pull and Snap":
                    # ── PULL AND SNAP: SCALE + SHAKE + BLINK + FLIP ──

                    PULL_DUR_FRAC = 0.50
                    SETTLE_DUR_FRAC = 0.50

                    def _center_fit(scaled_arr, tw, th):
                        sh, sw = scaled_arr.shape[:2]
                        sx = max(0, (sw - tw) // 2)
                        sy = max(0, (sh - th) // 2)
                        cw = min(sw, tw)
                        ch = min(sh, th)
                        dx = (tw - cw) // 2
                        dy = (th - ch) // 2
                        out = np.zeros((th, tw, 3), dtype=scaled_arr.dtype)
                        out[dy:dy + ch, dx:dx + cw] = scaled_arr[sy:sy + ch, sx:sx + cw]
                        return out

                    def _shake(arr, sx, sy):
                        return np.roll(np.roll(arr, int(sy), axis=0), int(sx), axis=1)

                    def _blink(arr, t, freq, white_level):
                        """Fast on/off blink — alternates between frame and bright flash."""
                        # Square wave: 1 = frame, 0 = bright flash
                        on = (math.sin(t * freq) > 0.0)
                        if on:
                            return arr
                        else:
                            f = arr.astype(np.float32)
                            f += white_level * 255.0
                            return np.clip(f, 0, 255).astype(arr.dtype)

                    def _blink_multi(arr, t, base_freq, strength):
                        """Ultra-fast strobe blink — multiple freq layers."""
                        # Combine two frequencies for irregular strobe
                        v = math.sin(t * base_freq) + math.sin(t * base_freq * 1.7)
                        on = v > 0.0
                        if not on:
                            f = arr.astype(np.float32)
                            f += strength * 255.0
                            return np.clip(f, 0, 255).astype(arr.dtype)
                        return arr

                    def _skew(arr, px):
                        if abs(px) < 0.5:
                            return arr
                        h, w = arr.shape[:2]
                        out = np.zeros_like(arr)
                        for row in range(h):
                            s = int(px * (row / h - 0.5))
                            if s >= 0:
                                out[row, s:] = arr[row, :w - s]
                            else:
                                out[row, :w + s] = arr[row, -s:]
                        return out

                    if p < PULL_DUR_FRAC:
                        # ── PART 1: THE PULL (shrink + flip + blink) ──
                        local_p = p / PULL_DUR_FRAC
                        ease_in = local_p * local_p

                        # Scale: 100% → 65%
                        scale_a = 1.0 - 0.35 * ease_in

                        # Shake: violent ramp-up
                        shake_amp = ease_in * ease_in * 20.0
                        shake_x = math.sin(local_p * 80.0) * shake_amp
                        shake_y = math.cos(local_p * 65.0) * shake_amp * 0.9

                        # Flip: starts flickering/flipping as shrink intensifies
                        do_flip = local_p > 0.20 and int(local_p * 40) % 2 == 0

                        # Blink: ultra-fast strobe, intensifies toward cut
                        blink_str = ease_in * 0.8

                        # Skew: increasing whip
                        skew_val = ease_in * 15.0 * math.sin(local_p * 35.0)

                        zw = max(1, int(target_w * scale_a))
                        zh = max(1, int(target_h * scale_a))
                        a_scaled = cv2.resize(arr_a, (zw, zh))
                        result = _center_fit(a_scaled, target_w, target_h)
                        result = _shake(result, shake_x, shake_y)
                        result = _skew(result, skew_val)
                        if do_flip:
                            result = result[:, ::-1].copy()
                        result = _blink_multi(result, local_p, 55.0, blink_str)
                        blended = result

                    else:
                        # ── PART 2+3: SNAP + SETTLE ──
                        local_p = (p - PULL_DUR_FRAC) / (1.0 - PULL_DUR_FRAC)

                        # Scale: 140% → 100% with bounce
                        if local_p < 0.01:
                            scale_b = 1.40
                        else:
                            settle_p = min(1.0, (local_p - 0.01) / 0.99)
                            bounce = math.sin(settle_p * math.pi * 3.0) * math.exp(-5.0 * settle_p)
                            scale_b = 1.0 + 0.40 * (1.0 - settle_p) + bounce * 0.08

                        # Flip: rapid strobe flip during first 40%
                        do_flip = local_p < 0.40 and int(local_p * 35) % 2 == 0

                        # Shake: violent slam, fast decay
                        impact = math.exp(-18.0 * local_p)
                        shake_x = math.sin(local_p * 130.0) * impact * 20.0
                        shake_y = math.cos(local_p * 110.0) * impact * 15.0

                        # Blink: fast strobe fading out
                        blink_str = math.exp(-6.0 * local_p) * 1.0

                        # Skew: whip snap
                        skew_val = math.exp(-10.0 * local_p) * 18.0 * math.sin(local_p * 55.0)

                        zw = max(1, int(target_w * scale_b))
                        zh = max(1, int(target_h * scale_b))
                        b_scaled = cv2.resize(arr_b, (zw, zh))
                        result = _center_fit(b_scaled, target_w, target_h)
                        result = _shake(result, shake_x, shake_y)
                        result = _skew(result, skew_val)
                        if do_flip:
                            result = result[:, ::-1].copy()
                        result = _blink_multi(result, local_p, 80.0, blink_str)
                        blended = result

                else:
                    blended = arr_a * (1 - p) + arr_b * p

                blended = np.clip(blended, 0, 255).astype(np.uint8)
                return PIL.Image.fromarray(blended)

        return img

    def _apply_export_transitions(self, clips, target_w, target_h):
        """Apply transitions between consecutive clips during export.
        For 'Pull and Snap', applies scale transforms to each clip independently.
        For all other transitions, uses moviepy crossfadein."""
        td = self.TRANSITION_DUR
        if td <= 0 or len(clips) < 2:
            return clips

        PULL_DUR_FRAC = 0.50
        SETTLE_DUR_FRAC = 0.50

        def _center_fit_exp(scaled_arr, tw, th):
            sh, sw = scaled_arr.shape[:2]
            sx = max(0, (sw - tw) // 2)
            sy = max(0, (sh - th) // 2)
            cw = min(sw, tw)
            ch = min(sh, th)
            dx = (tw - cw) // 2
            dy = (th - ch) // 2
            out = np.zeros((th, tw, 3), dtype=scaled_arr.dtype)
            out[dy:dy + ch, dx:dx + cw] = scaled_arr[sy:sy + ch, sx:sx + cw]
            return out

        def _shake_exp(arr, sx, sy):
            return np.roll(np.roll(arr, int(sy), axis=0), int(sx), axis=1)

        def _blink_multi_exp(arr, t, base_freq, strength):
            v = math.sin(t * base_freq) + math.sin(t * base_freq * 1.7)
            if v <= 0.0:
                f = arr.astype(np.float32)
                f += strength * 255.0
                return np.clip(f, 0, 255).astype(arr.dtype)
            return arr

        def _skew_exp(arr, px):
            if abs(px) < 0.5:
                return arr
            h, w = arr.shape[:2]
            out = np.zeros_like(arr)
            for row in range(h):
                s = int(px * (row / h - 0.5))
                if s >= 0:
                    out[row, s:] = arr[row, :w - s]
                else:
                    out[row, :w + s] = arr[row, -s:]
            return out

        final = []
        for idx, clip in enumerate(clips):
            item_prev = self.media_queue[idx - 1] if idx >= 1 and idx - 1 < len(self.media_queue) else None
            trans = item_prev.get("trans", "Crossfade") if item_prev else "Crossfade"

            if idx == 0:
                final.append(clip)
                continue

            if trans == "Hard Cut":
                final.append(clip.set_start(clip.start))
            elif trans == "Pull and Snap":
                clip_b = clip
                clip_a = final[-1]

                def _pull_frame(get_frame_a, tt, _clip_dur):
                    frame = get_frame_a(tt)
                    if tt >= _clip_dur - td:
                        zone_tt = tt - (_clip_dur - td)
                        local_p = min(1.0, zone_tt / (td * PULL_DUR_FRAC))
                        ease_in = local_p * local_p
                        scale_a = 1.0 - 0.35 * ease_in
                        arr = frame.astype(np.float32)
                        zw = max(1, int(target_w * scale_a))
                        zh = max(1, int(target_h * scale_a))
                        scaled = cv2.resize(arr, (zw, zh))
                        result = _center_fit_exp(scaled, target_w, target_h)
                        shake_amp = ease_in * ease_in * 20.0
                        result = _shake_exp(result, math.sin(local_p * 80.0) * shake_amp,
                                            math.cos(local_p * 65.0) * shake_amp * 0.9)
                        result = _skew_exp(result, ease_in * 15.0 * math.sin(local_p * 35.0))
                        if local_p > 0.20 and int(local_p * 40) % 2 == 0:
                            result = result[:, ::-1].copy()
                        result = _blink_multi_exp(result, local_p, 55.0, ease_in * 0.8)
                        return np.clip(result, 0, 255).astype(np.uint8)
                    return frame

                def _snap_settle_frame(get_frame_b, tt):
                    snap_settle_dur = td * SETTLE_DUR_FRAC
                    if tt < snap_settle_dur:
                        local_p = tt / snap_settle_dur
                        if local_p < 0.01:
                            scale_b = 1.40
                        else:
                            settle_p = min(1.0, (local_p - 0.01) / 0.99)
                            bounce = math.sin(settle_p * math.pi * 3.0) * math.exp(-5.0 * settle_p)
                            scale_b = 1.0 + 0.40 * (1.0 - settle_p) + bounce * 0.08
                        frame = get_frame_b(tt)
                        arr = frame.astype(np.float32)
                        zw = max(1, int(target_w * scale_b))
                        zh = max(1, int(target_h * scale_b))
                        scaled = cv2.resize(arr, (zw, zh))
                        result = _center_fit_exp(scaled, target_w, target_h)
                        impact = math.exp(-18.0 * local_p)
                        result = _shake_exp(result, math.sin(local_p * 130.0) * impact * 20.0,
                                            math.cos(local_p * 110.0) * impact * 15.0)
                        result = _skew_exp(result, math.exp(-10.0 * local_p) * 18.0 * math.sin(local_p * 55.0))
                        if local_p < 0.40 and int(local_p * 35) % 2 == 0:
                            result = result[:, ::-1].copy()
                        result = _blink_multi_exp(result, local_p, 80.0, math.exp(-6.0 * local_p) * 1.0)
                        return np.clip(result, 0, 255).astype(np.uint8)
                    return get_frame_b(tt)

                _cad = clip_a.duration
                clip_a_modified = clip_a.fl(lambda gf, tt, _d=_cad: _pull_frame(gf, tt, _d))
                final[-1] = clip_a_modified

                clip_b_modified = clip_b.fl(lambda gf, tt: _snap_settle_frame(gf, tt))
                clip_b_modified = clip_b_modified.set_start(clip_a.end)
                final.append(clip_b_modified)
            else:
                final.append(clip.crossfadein(td))

        return final

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

    # ==========================================
    # TIMELINE HELPERS & HIT-TESTING
    # ==========================================
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

    # ==========================================
    # TIMELINE DRAG & SCRUB LOGIC
    # ==========================================

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

    def on_tl_press(self, event):
        _ensure_pygame()
        x = self.timeline_canvas.canvasx(event.x)
        y = self.timeline_canvas.canvasy(event.y)

        self._drag_state_saved = False
        self._trim_state_saved = False
        self._close_env_popup()

        if y <= self.RULER_H + 20:
            self._is_scrubbing = True
            if HAS_PYGAME and self.is_playing and self.audio_ready:
                try: pygame.mixer.music.pause()
                except: pass
            self._set_playhead(max(0.0, (x - self.LABEL_W) / self.PPS))
            return

        if self._mute_drawing and self.selected_idx is not None:
            item = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            local_t = max(0.0, (x - self.LABEL_W) / self.PPS - t_start)
            self._mute_draw_start_t = local_t
            return

        if self._highlight_drawing and self.selected_idx is not None:
            item = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            local_t = max(0.0, (x - self.LABEL_W) / self.PPS - t_start)
            self._highlight_draw_start_t = local_t
            return

        # Only activate the handle type that matches the current mode button.
        # This prevents the two systems from interfering at the clip edges.
        if self._handle_mode == "extend":
            extend_hit = self._get_extend_handle_at_pos(x, y)
            if extend_hit:
                self._extend_drag = extend_hit
                self._extend_state_saved = False
                self._drag_item = None
                self._drag_env_pt = None
                self._trim_drag = None
                self._is_scrubbing = False
                return
        else:   # "trim" mode (default)
            trim_hit = self._get_trim_handle_at_pos(x, y)
            if trim_hit:
                self._trim_drag = trim_hit
                self._drag_item = None
                self._drag_env_pt = None
                self._is_scrubbing = False
                return

        pt_hit = self._get_env_pt_at_pos(x, y)
        if pt_hit:
            self._drag_env_pt = pt_hit
            self._is_scrubbing = False
            self._drag_item = None
            ctype, cidx, pt_idx = pt_hit
            self._show_env_pt_vol_popup(ctype, cidx, pt_idx, x, y)
            return

        self._drag_env_pt = None
        self._is_scrubbing = False

        # Ctrl+Click on an audio track = multiselect for Speech Ease (max 2)
        ctrl_held = bool(event.state & 0x0004)
        if ctrl_held:
            clip_info = self._get_clip_at_pos(x, y)
            if clip_info and clip_info[0] == "audio":
                cidx = clip_info[1]
                if cidx in self._audio_multiselect:
                    self._audio_multiselect.remove(cidx)
                else:
                    self._audio_multiselect.append(cidx)
                    if len(self._audio_multiselect) > 2:
                        self._audio_multiselect = self._audio_multiselect[-2:]
                self.refresh_timeline()
                return

        self.selected_idx = None
        self.selected_audio_idx = None

        clip_info = self._get_clip_at_pos(x, y)
        if clip_info:
            ctype, cidx, clip, x_l, x_r, y_top, y_bot = clip_info
            if ctype == "video":
                self.selected_idx = cidx
                self._drag_item = ("video", cidx)
                self._drag_start_x = x
                self._drag_orig_start = clip.get("tl_start", 0.0)
            else:
                self.selected_audio_idx = cidx
                self._drag_item = ("audio", cidx)
                self._drag_start_x = x
                self._drag_orig_start = clip.get("start_offset", 0.0)
            # Auto-place markers at the clip edges on selection
            key = (ctype, cidx)
            clip_dur = self._get_clip_display_dur(ctype, cidx)
            self._trim_marker_A[key] = 0.0
            self._trim_marker_B[key] = clip_dur
            self.render_inspector()
            self.refresh_effects_tab()
            self.refresh_timeline()
            return

        self.render_inspector()
        self.refresh_effects_tab()
        self.refresh_timeline()

    def on_tl_double_click(self, event):
        x = self.timeline_canvas.canvasx(event.x)
        y = self.timeline_canvas.canvasy(event.y)
        
        clip_info = self._get_clip_at_pos(x, y)
        if clip_info:
            self.save_state() 
            ctype, cidx, clip, x_l, x_r, y_top, y_bot = clip_info
            
            t_frac = float(np.clip((x - x_l) / max(1, x_r - x_l), 0.0, 1.0))
            vol = float(np.clip(2.0 * (y_bot - y) / max(1, y_bot - y_top), 0.0, 2.0))
            
            active_clip = self.media_queue[cidx] if ctype == 'video' else self.bgm_tracks[cidx]
            
            if "vol_envelope" not in active_clip or not active_clip["vol_envelope"]:
                active_clip["vol_envelope"] = [(0.0, 1.0), (1.0, 1.0)]
                
            active_clip["vol_envelope"].append((t_frac, vol))
            active_clip["vol_envelope"].sort(key=lambda p: p[0])
            
            self.timeline_dirty = True
            self.refresh_timeline()

    def on_tl_right_click(self, event):
        x = self.timeline_canvas.canvasx(event.x)
        y = self.timeline_canvas.canvasy(event.y)
        
        pt_hit = self._get_env_pt_at_pos(x, y)
        if pt_hit:
            self.save_state()
            ctype, cidx, pt_idx = pt_hit
            clip = self.media_queue[cidx] if ctype == 'video' else self.bgm_tracks[cidx]
            env = clip["vol_envelope"]
            
            if len(env) > 2:
                del env[pt_idx]
                self.timeline_dirty = True
                self.refresh_timeline()

    def _throttled_refresh_timeline(self, min_interval=0.033):
        """Same visual result as refresh_timeline(), but collapses rapid
        calls (e.g. every pixel of a mouse drag) to roughly 30fps, since
        refresh_timeline() redraws every clip/thumbnail/waveform on the
        timeline from scratch. Without this, dragging a clip, an envelope
        point, or a trim handle redraws the whole timeline on every single
        mouse-move tick, which is what makes dragging feel laggy/fiddly."""
        now = time.perf_counter()
        last = getattr(self, '_last_timeline_refresh', 0.0)
        if now - last >= min_interval:
            self._last_timeline_refresh = now
            pending = getattr(self, '_timeline_refresh_pending', None)
            if pending is not None:
                self.root.after_cancel(pending)
                self._timeline_refresh_pending = None
            self.refresh_timeline()
        elif getattr(self, '_timeline_refresh_pending', None) is None:
            delay_ms = max(1, int((min_interval - (now - last)) * 1000))
            self._timeline_refresh_pending = self.root.after(delay_ms, self._flush_timeline_refresh)

    def _flush_timeline_refresh(self):
        self._timeline_refresh_pending = None
        self._last_timeline_refresh = time.perf_counter()
        self.refresh_timeline()

    def on_tl_drag(self, event):
        x = self.timeline_canvas.canvasx(event.x)
        y = self.timeline_canvas.canvasy(event.y)

        if getattr(self, '_is_scrubbing', False):
            self._set_playhead(max(0.0, (x - self.LABEL_W) / self.PPS))
            return

        # Handle extend/shrink edge-drag (recover trimmed footage or trim further)
        if getattr(self, "_extend_drag", None):
            side, ctype, cidx = self._extend_drag
            if not self._extend_state_saved:
                self.save_state()
                self._extend_state_saved = True
            t_cursor = max(0.0, (x - self.LABEL_W) / self.PPS)
            SAFE = 0.05
            if ctype == "video":
                item = self.media_queue[cidx]
                tl_start = item.get("tl_start", 0.0)
                try:
                    if item["path"] not in self._clip_cache:
                        self._clip_cache_put(item["path"], VideoFileClip(item["path"]))
                    file_dur = self._clip_cache[item["path"]].duration
                except Exception:
                    file_dur = 999.0
                cur_cs = float(item.get("clip_start", 0.0))
                cur_ce = float(item.get("clip_end", 0.0)) or file_dur
                if side == "left":
                    # Dragging left edge: local time before tl_start moves clip_start
                    new_local = t_cursor - tl_start
                    new_cs = cur_cs + new_local   # new_local is negative when dragging outward(left)
                    item["clip_start"] = max(0.0, min(new_cs, cur_ce - SAFE))
                else:
                    new_local = t_cursor - tl_start
                    new_ce = cur_cs + new_local
                    item["clip_end"] = max(cur_cs + SAFE, min(new_ce, file_dur - SAFE))
            else:
                bgm = self.bgm_tracks[cidx]
                try:
                    if bgm["path"] not in self._clip_cache:
                        self._clip_cache_put(bgm["path"], AudioFileClip(bgm["path"]))
                    file_dur = self._clip_cache[bgm["path"]].duration
                except Exception:
                    file_dur = 999.0
                cur_cs = float(bgm.get("clip_start", 0.0))
                cur_ce = float(bgm.get("clip_end", 0.0)) or file_dur
                base_off = float(bgm.get("start_offset", 0.0))
                if side == "left":
                    new_local = t_cursor - base_off
                    new_cs = cur_cs + new_local
                    new_cs = max(0.0, min(new_cs, cur_ce - SAFE))
                    # Keep the visual start_offset anchored to where the edge is dragged to
                    delta_cs = new_cs - cur_cs
                    bgm["clip_start"] = new_cs
                    bgm["start_offset"] = base_off + delta_cs
                else:
                    new_local = t_cursor - base_off
                    new_ce = cur_cs + new_local
                    bgm["clip_end"] = max(cur_cs + SAFE, min(new_ce, file_dur - SAFE))
            self.timeline_dirty = True
            self._throttled_refresh_timeline()
            return

        # Handle trim-handle dragging
        if getattr(self, "_trim_drag", None):
            # Drag a free-floating region marker (A or B) within the clip
            marker_id, ctype, cidx = self._trim_drag
            bounds = self._get_clip_bounds(ctype, cidx)
            if bounds:
                x_l, x_r, y_top, y_bot = bounds
                clip_dur = self._get_clip_display_dur(ctype, cidx)
                # Convert canvas x → local time within the clip
                t_local = max(0.0, min(clip_dur, (x - x_l) / max(1, x_r - x_l) * clip_dur))
                key = (ctype, cidx)
                if marker_id == "A":
                    self._trim_marker_A[key] = t_local
                else:
                    self._trim_marker_B[key] = t_local
                self._throttled_refresh_timeline()   # redraw markers only, no data change
            return

        if getattr(self, '_mute_drawing', False) and self.selected_idx is not None:
            self._throttled_refresh_timeline()
            self.timeline_canvas.delete("mute_preview")
            item = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            local_t = max(0.0, (x - self.LABEL_W) / self.PPS - t_start)

            t0, t1 = sorted([self._mute_draw_start_t, local_t])
            x0 = self.LABEL_W + int((t_start + t0) * self.PPS)
            x1 = self.LABEL_W + int((t_start + t1) * self.PPS)

            y_bot = self.RULER_H + 4 + self.TRACK_H
            self.timeline_canvas.create_rectangle(x0, self.RULER_H + 4, x1, y_bot, fill=C["danger"], stipple="gray50", tags="mute_preview")
            return

        if getattr(self, '_highlight_drawing', False) and self.selected_idx is not None:
            self._throttled_refresh_timeline()
            self.timeline_canvas.delete("highlight_preview")
            item = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            local_t = max(0.0, (x - self.LABEL_W) / self.PPS - t_start)

            t0, t1 = sorted([self._highlight_draw_start_t, local_t])
            x0 = self.LABEL_W + int((t_start + t0) * self.PPS)
            x1 = self.LABEL_W + int((t_start + t1) * self.PPS)

            y_bot = self.RULER_H + 4 + self.TRACK_H
            self.timeline_canvas.create_rectangle(x0, self.RULER_H + 4, x1, y_bot, fill="#00897B", stipple="gray50", tags="highlight_preview")
            return

        if (self._drag_env_pt or self._drag_item) and not self._drag_state_saved:
            self.save_state()
            self._drag_state_saved = True

        if hasattr(self, '_drag_env_pt') and self._drag_env_pt:
            ctype, cidx, pt_idx = self._drag_env_pt
            clip = self.media_queue[cidx] if ctype == 'video' else self.bgm_tracks[cidx]
            
            clip_info = self._get_clip_bounds(ctype, cidx)
            if not clip_info: return
            x_l, x_r, y_top, y_bot = clip_info

            t_frac = np.clip((x - x_l) / max(1, x_r - x_l), 0.0, 1.0)
            vol = np.clip(2.0 * (y_bot - y) / max(1, y_bot - y_top), 0.0, 2.0)

            env = clip["vol_envelope"]
            
            if pt_idx == 0: t_frac = 0.0
            if pt_idx == len(env) - 1 and env[-1][0] == 1.0: t_frac = 1.0

            prev_t = env[pt_idx-1][0] if pt_idx > 0 else 0.0
            next_t = env[pt_idx+1][0] if pt_idx < len(env)-1 else 1.0
            t_frac = np.clip(t_frac, prev_t, next_t)

            env[pt_idx] = (t_frac, vol)

            self.timeline_dirty = True
            self._throttled_refresh_timeline()
            return

        if self._drag_item:
            itype, idx = self._drag_item

            if itype == 'video':
                t_cursor = max(0.0, (x - self.LABEL_W) / self.PPS)
                new_idx = idx
                for i, item in enumerate(self.media_queue):
                    if i == idx: continue
                    s = item.get("tl_start", 0.0)
                    e = s + self._item_duration(item)
                    if s <= t_cursor <= e:
                        new_idx = i
                        break

                if new_idx != idx:
                    item = self.media_queue.pop(idx)
                    self.media_queue.insert(new_idx, item)
                    self._drag_item = ('video', new_idx)
                    self.selected_idx = new_idx
                    self.timeline_dirty = True
                    self._throttled_refresh_timeline()
            else:
                delta_t = (x - self._drag_start_x) / self.PPS
                new_start = max(0.0, self._drag_orig_start + delta_t)
                self.bgm_tracks[idx]["start_offset"] = new_start
                self.timeline_dirty = True
                self._throttled_refresh_timeline()

    def on_tl_release(self, event):
        _ensure_pygame()
        x = self.timeline_canvas.canvasx(event.x)
        if getattr(self, '_is_scrubbing', False) and HAS_PYGAME and self.is_playing and self.audio_ready:
            try: pygame.mixer.music.unpause()
            except: pass

        if getattr(self, '_mute_drawing', False) and self.selected_idx is not None:
            item = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            local_t = max(0.0, (x - self.LABEL_W) / self.PPS - t_start)

            t0, t1 = sorted([self._mute_draw_start_t, local_t])
            if t1 - t0 > 0.05:
                self.save_state() 
                item.setdefault("mute_regions", []).append((t0, t1))
            self._mute_drawing = False
            self.tl_mode_label.config(text="")
            self.timeline_dirty = True
            self.refresh_timeline()
            self.render_inspector()
            return

        if getattr(self, '_highlight_drawing', False) and self.selected_idx is not None:
            item = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            local_t = max(0.0, (x - self.LABEL_W) / self.PPS - t_start)

            t0, t1 = sorted([self._highlight_draw_start_t, local_t])
            self._highlight_drawing = False
            self.tl_mode_label.config(text="")
            if t1 - t0 > 0.1:
                self.save_state()
                self._split_and_duplicate_highlight(self.selected_idx, t0, t1)
            else:
                self.refresh_timeline()
            return

        self._is_scrubbing = False
        was_dragging = bool(self._drag_item or self._drag_env_pt or self._trim_drag or self._extend_drag)
        self._drag_item = None
        self._drag_env_pt = None
        self._drag_state_saved = False
        self._trim_drag = None
        self._trim_state_saved = False
        self._extend_drag = None
        self._extend_state_saved = False
        if was_dragging:
            # Guarantee the final position is drawn immediately — in-drag
            # redraws are throttled for smoothness, so the very last one
            # might otherwise still be sitting in a pending `after()` call.
            if getattr(self, '_timeline_refresh_pending', None) is not None:
                self.root.after_cancel(self._timeline_refresh_pending)
                self._timeline_refresh_pending = None
            self.refresh_timeline()

    def _set_playhead(self, t, preview=True):
        self.playhead_t.set(t)

        mins = int(t) // 60
        secs = int(t) % 60
        ms = int((t % 1) * 100)
        self.timecode_var.set(f"{mins:02d}:{secs:02d}.{ms:02d}")

        c = self.timeline_canvas
        c.delete("playhead_line")
        c.delete("playhead_poly")

        ph_x = self.LABEL_W + int(t * self.PPS)
        c.create_line(ph_x, 0, ph_x, 2000, fill=C["accent"], width=2, tags="playhead_line")
        c.create_polygon(ph_x-6, 0, ph_x+6, 0, ph_x, 10, fill=C["accent"], tags="playhead_poly")

        if preview:
            self._interactive_mode = True
            if self._preview_job is not None:
                self.root.after_cancel(self._preview_job)
            self._preview_job = self.root.after(16, self.update_global_preview)
            # Settle to a full-quality render shortly after scrubbing stops,
            # same pattern used for slider drags and 3D-text editing.
            if self._final_preview_job is not None:
                self.root.after_cancel(self._final_preview_job)
            self._final_preview_job = self.root.after(350, self._run_final_preview)

    def get_filmstrip_image(self, item, item_w, item_h):
        path = item.get('path')
        if not path and item['type'] != 'title': return None

        # Show placeholder while moviepy is loading in background
        if not _MOVIEPY_LOADED and item['type'] in ('video', 'title'):
            return self._placeholder_photo(item, item_w, item_h)

        num_frames = min(15, max(1, int(item_w / 60)))
        cache_key = f"filmstrip_v4_{path}_{num_frames}_{item.get('rotation',0)}_{item.get('flip_h',False)}_{item.get('flip_v',False)}_{item_w}x{item_h}_{item.get('theme', '')}_{item.get('main_text', '')}"
        
        if cache_key in self._clip_cache:
            return self._clip_cache[cache_key]

        # Filmstrip not cached yet — queue for background generation
        self._placeholder_photo(item, item_w, item_h)
        self._pending_filmstrips.append((item, item_w, item_h, cache_key, num_frames))
        self._schedule_filmstrip_bg()
        return None

    def _placeholder_photo(self, item, item_w, item_h):
        """Return a small placeholder PhotoImage for a clip not yet rendered."""
        label = item.get('name', item['type'])[:6].upper()
        ph_key = f"ph_{item.get('path','')}{item_w}x{item_h}"
        if ph_key in self._clip_cache:
            return self._clip_cache[ph_key]
        try:
            img = PIL.Image.new('RGB', (max(1, int(item_w)), int(item_h)), (30, 30, 45))
            d = ImageDraw.Draw(img)
            d.text((8, item_h // 2 - 6), label, fill=(140, 140, 160))
            photo = ImageTk.PhotoImage(img)
            self._clip_cache[ph_key] = photo
            return photo
        except Exception:
            return None

    def _schedule_filmstrip_bg(self):
        """Process pending filmstrips in a single background thread (batched)."""
        if self._filmstrip_bg_active:
            return
        self._filmstrip_bg_active = True

        def _worker():
            try:
                while self._pending_filmstrips:
                    item, item_w, item_h, cache_key, num_frames = self._pending_filmstrips.pop(0)
                    if cache_key in self._clip_cache:
                        continue
                    try:
                        self._render_filmstrip(item, item_w, item_h, cache_key, num_frames)
                    except Exception:
                        pass
            except Exception as ex:
                print("COLOR FILTER ERROR:", ex)
                import traceback; traceback.print_exc()
                self.root.after(0, self.refresh_timeline)
            finally:
                self._filmstrip_bg_active = False

        threading.Thread(target=_worker, daemon=True).start()

    def _render_filmstrip(self, item, item_w, item_h, cache_key, num_frames):
        """Render a single filmstrip (runs in background thread)."""
        path = item.get('path')
        frame_w = max(1, int(item_w / num_frames))
        strip_img = PIL.Image.new('RGB', (int(item_w), int(item_h)), (20, 20, 35))

        if item['type'] == 'image':
            img = PIL.Image.open(path).convert('RGB')
            rot = item.get('rotation', 0)
            if rot != 0: img = img.rotate(-rot, expand=True)
            if item.get('flip_h'): img = img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
            if item.get('flip_v'): img = img.transpose(PIL.Image.FLIP_TOP_BOTTOM)
            img = img.resize((frame_w, int(item_h)), PIL.Image.LANCZOS)
            for i in range(num_frames):
                strip_img.paste(img, (i * frame_w, 0))

        elif item['type'] == 'title':
            try:
                tc = self.build_finch_title_card(426, 240, item, preview_mode=True)
                sample_t = float(item.get('value', 5.0)) / 2.0
                f_arr = tc.get_frame(min(sample_t, tc.duration - 0.01))
                tc.close()
                base_thumb = PIL.Image.fromarray(f_arr)
                base_thumb = base_thumb.resize((frame_w, int(item_h)), PIL.Image.LANCZOS)
                for i in range(num_frames):
                    strip_img.paste(base_thumb, (i * frame_w, 0))
            except Exception:
                pass

        else:
            clip = VideoFileClip(path)
            dur = clip.duration if clip.duration and clip.duration > 0 else 1.0
            for i in range(num_frames):
                t = (i + 0.5) * (dur / num_frames)
                try:
                    f_img = PIL.Image.fromarray(clip.get_frame(t))
                    rot = item.get('rotation', 0)
                    if rot != 0: f_img = f_img.rotate(-rot, expand=True)
                    if item.get('flip_h'): f_img = f_img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
                    if item.get('flip_v'): f_img = f_img.transpose(PIL.Image.FLIP_TOP_BOTTOM)
                    f_img = f_img.resize((frame_w, int(item_h)), PIL.Image.LANCZOS)
                    strip_img.paste(f_img, (i * frame_w, 0))
                except Exception:
                    pass
            clip.close()

        photo = ImageTk.PhotoImage(strip_img)
        self._clip_cache[cache_key] = photo

    def _draw_waveform(self, c, item, x_left, x_right, y_top, y_bot, col):
        path = item.get("path")
        if not path: return
        w_key = f"wave_{path}"
        if w_key not in self.waveforms:
            self._extract_waveform_async(item, w_key)
        wf = self.waveforms.get(w_key)
        if wf is not None and len(wf) > 0:
            step_w = max(1, (x_right - x_left) / len(wf))
            mid_y = (y_top + y_bot) / 2
            amp_max = (y_bot - y_top) / 2 - 2
            pts = []
            for k, v in enumerate(wf):
                pts.append((x_left + k * step_w, mid_y - v * amp_max))
            for k, v in reversed(list(enumerate(wf))):
                pts.append((x_left + k * step_w, mid_y + v * amp_max))
            c.create_polygon(pts, fill=col, outline="")
        elif _MOVIEPY_LOADED:
            # Waveform not yet extracted — draw a flat line as placeholder
            mid_y = (y_top + y_bot) / 2
            c.create_line(x_left, mid_y, x_right, mid_y, fill=col, dash=(2, 4))

    def _extract_waveform_async(self, item, w_key):
        """Extract waveform samples in a background thread."""
        def _worker():
            try:
                samples = extract_waveform_samples(item.get("path", ""), 200)
                self.waveforms[w_key] = samples
                self.root.after(0, self.refresh_timeline)
            except Exception:
                self.waveforms[w_key] = None
        threading.Thread(target=_worker, daemon=True).start()

    def _draw_vol_envelope_on_track(self, c, clip_dict, x_l, x_r, y_top, y_bot):
        env = clip_dict.get("vol_envelope", [])
        if not env or len(env) < 2:
            base_vol = clip_dict.get("volume", 1.0)
            env = [(0.0, base_vol), (1.0, base_vol)]
            clip_dict["vol_envelope"] = env

        MAX_VOL = 2.0
        env_s = sorted(env, key=lambda p: p[0])
        track_h = y_bot - y_top
        ease_mode = clip_dict.get('ease_mode', 'none')

        def kp_to_xy(t_frac, vol):
            kx = x_l + t_frac * (x_r - x_l)
            ky = y_bot - (vol / MAX_VOL) * track_h
            return kx, ky

        # Draw smooth curve: sample many points between each pair of keypoints
        # using the same cosine interpolation as _eval_vol_envelope so the
        # visual line matches what the audio actually does.
        STEPS = 30   # segments per keypoint span
        line_col = "#FFD700"

        for seg in range(len(env_s) - 1):
            t0, v0 = env_s[seg]
            t1, v1 = env_s[seg + 1]
            seg_pts = []
            for step in range(STEPS + 1):
                alpha_raw = step / STEPS
                # cosine ease (matches _eval_vol_envelope exactly)
                alpha = 0.5 - 0.5 * math.cos(alpha_raw * math.pi)
                vol   = v0 + alpha * (v1 - v0)
                t_frac = t0 + alpha_raw * (t1 - t0)
                seg_pts.append(kp_to_xy(t_frac, vol))
            if len(seg_pts) >= 2:
                flat = [coord for xy in seg_pts for coord in xy]
                c.create_line(*flat, fill=line_col, width=2, smooth=True)

        # Draw pt_gain ticks — red vertical spike at points with a sudden gain != 1.0
        pt_gains = clip_dict.get("pt_gains", {})
        for pt_idx, (t_frac, vol) in enumerate(env_s):
            gain = float(pt_gains.get(str(pt_idx), 1.0))
            if abs(gain - 1.0) > 0.02:   # only draw if actually changed
                kx, ky = kp_to_xy(t_frac, vol)
                spike_col = "#ff4444" if gain < 1.0 else "#44ff88"
                # Vertical spike above/below the point
                spike_h = int(track_h * 0.35)
                c.create_line(kx, ky - spike_h, kx, ky + spike_h,
                              fill=spike_col, width=2)
                c.create_text(kx + 5, ky - spike_h + 2,
                              text=f"x{gain:.2f}", fill=spike_col,
                              font=("Segoe UI", 7), anchor="w")

        # Draw keypoint markers — shape reflects ease mode
        for pt_idx, (t_frac, vol) in enumerate(env_s):
            kx, ky = kp_to_xy(t_frac, vol)
            is_anchor = (pt_idx == 0 or pt_idx == len(env_s) - 1)

            if ease_mode == 'none':
                # Default: filled circle
                c.create_oval(kx-4, ky-4, kx+4, ky+4,
                              fill=C["accent2"], outline="white", width=1)

            elif ease_mode == 'ease_in':
                if is_anchor and t_frac <= 0.01:
                    # Start point: upward-pointing triangle (ramp begins here)
                    c.create_polygon(kx, ky-6, kx-5, ky+4, kx+5, ky+4,
                                     fill="#39d353", outline="white", width=1)
                elif is_anchor and t_frac >= 0.99:
                    # End point: square (held level)
                    c.create_rectangle(kx-4, ky-4, kx+4, ky+4,
                                       fill=C["accent2"], outline="white", width=1)
                else:
                    c.create_oval(kx-4, ky-4, kx+4, ky+4,
                                  fill="#39d353", outline="white", width=1)

            elif ease_mode == 'ease_out':
                if is_anchor and t_frac <= 0.01:
                    # Start point: square (held level)
                    c.create_rectangle(kx-4, ky-4, kx+4, ky+4,
                                       fill=C["accent2"], outline="white", width=1)
                elif is_anchor and t_frac >= 0.99:
                    # End point: downward triangle (ramp ends here)
                    c.create_polygon(kx, ky+6, kx-5, ky-4, kx+5, ky-4,
                                     fill=C["accent4"], outline="white", width=1)
                else:
                    c.create_oval(kx-4, ky-4, kx+4, ky+4,
                                  fill=C["accent4"], outline="white", width=1)

            elif ease_mode == 'ease_in_out':
                if is_anchor and t_frac <= 0.01:
                    # Left arm of X — upward triangle
                    c.create_polygon(kx, ky-6, kx-5, ky+4, kx+5, ky+4,
                                     fill="#39d353", outline="white", width=1)
                elif is_anchor and t_frac >= 0.99:
                    # Right arm of X — downward triangle
                    c.create_polygon(kx, ky+6, kx-5, ky-4, kx+5, ky-4,
                                     fill=C["accent4"], outline="white", width=1)
                else:
                    # Interior hold points: diamond shape
                    c.create_polygon(kx, ky-6, kx+6, ky, kx, ky+6, kx-6, ky,
                                     fill=C["accent"], outline="white", width=1)

    def refresh_timeline(self):
        c = self.timeline_canvas
        c.delete("all")

        total_dur = self._total_duration()
        canvas_w = max(self.LABEL_W + int(total_dur * self.PPS) + 200, 900)
        canvas_h = self.RULER_H + (len(self.media_queue)+len(self.bgm_tracks)+2)*(self.TRACK_H)
        c.configure(scrollregion=(0, 0, canvas_w, canvas_h))

        c.create_rectangle(0, 0, canvas_w, self.RULER_H, fill=C["surface"], outline="")

        step = 5
        if self.PPS > 150: step = 1
        elif self.PPS < 40: step = 10

        t = 0.0
        while t <= total_dur + 10.0:
            x = self.LABEL_W + int(t * self.PPS)
            c.create_line(x, self.RULER_H-5, x, self.RULER_H, fill=C["text_dim"])
            mins = int(t) // 60
            secs = int(t) % 60
            c.create_text(x, self.RULER_H//2, text=f"{mins:02d}:{secs:02d}", fill=C["text_dim"], font=("Courier", 8))
            t += step

        c.create_rectangle(0, 0, self.LABEL_W, canvas_h, fill=C["surface"], outline="")

        y_cursor = self.RULER_H + 4

        curr_t = 0.0
        for i, item in enumerate(self.media_queue):
            item["tl_start"] = curr_t
            dur = self._item_duration(item)

            x_l = self.LABEL_W + int(curr_t * self.PPS)
            x_r = self.LABEL_W + int((curr_t + dur) * self.PPS)
            item_w = max(1, x_r - x_l)
            y_bot = y_cursor + self.TRACK_H

            is_sel = (i == self.selected_idx)
            outline_col = "white" if is_sel else C["border"]
            c.create_rectangle(x_l, y_cursor, x_r, y_bot, fill=C["clip_video"] if item["type"] != "title" else "#2a0050", outline=outline_col, width=2 if is_sel else 1)

            if item['type'] == 'placeholder' and not item.get('path'):
                c.create_text(x_l + item_w/2, y_cursor + 20, text="PLACEHOLDER", fill="#FF9800", font=("Segoe UI", 9, "bold"))
            else:
                fs_photo = self.get_filmstrip_image(item, item_w, self.TRACK_H)
                if fs_photo:
                    c.create_image(x_l, y_cursor, image=fs_photo, anchor="nw")
                if item['type'] == 'video' and not item.get('muted'):
                    self._draw_waveform(c, item, x_l, x_r, y_bot - 20, y_bot, C["waveform"])

            if item.get("mute_regions"):
                for (start, end) in item["mute_regions"]:
                    mx_l = x_l + int((start / dur) * item_w)
                    mx_r = x_l + int((end / dur) * item_w)
                    c.create_rectangle(mx_l, y_cursor, mx_r, y_bot, fill=C["clip_mute"], stipple="gray50", outline="")

            # Show highlight effect indicator on the clip
            hl_effect = item.get('_highlight_effect')
            if hl_effect:
                h_color = "#FF6F00" if hl_effect == 'slowmo_zoom' else "#7B1FA2"
                h_label = "🐌" if hl_effect == 'slowmo_zoom' else "⏪"
                # Draw colored border around the clip
                c.create_rectangle(x_l, y_cursor, x_r, y_bot, outline=h_color, width=3)
                c.create_text((x_l + x_r) // 2, y_cursor + 12, text=h_label,
                              fill="white", font=("Segoe UI Emoji", 10, "bold"), anchor="center")

            if item['type'] == 'video':
                self._draw_vol_envelope_on_track(c, item, x_l, x_r, y_cursor, y_bot)

            dur_text = f"[{item.get('clip_start', 0.0):.1f}s-{item.get('clip_end', 0.0):.1f}s]" if item['type'] == 'video' else f"{item.get('value',5.0)}s"
            if item.get('muted'): dur_text += " 🔇"
            c.create_rectangle(x_l, y_bot - 16, x_r, y_bot, fill="#111", outline="")
            c.create_text(x_l + 4, y_bot - 8, text=dur_text, fill="#aaa", font=("Segoe UI", 8), anchor="w")

            if item.get('text'):
                t_dur = max(0.1, float(item.get('value', 5.0)))
                txt_w = item_w * ((item['text_end'] - item['text_start']) / t_dur)
                txt_x = x_l + item_w * (item['text_start'] / t_dur)
                c.create_rectangle(txt_x, y_bot + 5, txt_x + txt_w, y_bot + 20, fill="#00A8FF", outline="")
                c.create_text(txt_x + 5, y_bot + 12, text="T", fill="white", font=("Segoe UI", 7, "bold"), anchor="w")

            c.create_text(self.LABEL_W//2, (y_cursor+y_bot)//2, text=f"V{i+1}", fill=C["text_dim"], font=("Arial", 8, "bold"))
            curr_t += dur

        y_cursor += self.TRACK_H + 10
        max_vid_x = self.LABEL_W + int(curr_t * self.PPS)

        c.create_line(0, y_cursor, max(2000, max_vid_x), y_cursor, fill=C["border"], dash=(4, 4))
        y_cursor += 4

        aud_h = 40
        max_aud_x = self.LABEL_W
        for j, aud in enumerate(self.bgm_tracks):
            is_spacer = aud.get('is_speech_pause_spacer', False)
            is_sel = (j == self.selected_audio_idx)
            is_multisel = (j in self._audio_multiselect)
            outline_col = "white" if is_sel else C["border"]

            t_s = aud.get('start_offset', 0.0)
            dur = self._get_bgm_played_dur(aud)

            x_l = self.LABEL_W + int(t_s * self.PPS)
            x_r = self.LABEL_W + int((t_s + dur) * self.PPS)
            y_bot = y_cursor + aud_h

            if is_spacer:
                # Draw speech-pause spacer as a hatched grey gap
                c.create_rectangle(x_l, y_cursor, x_r, y_bot,
                                   fill="#2a2a2a", outline="#555", width=1, dash=(3,3))
                mid_x = (x_l + x_r) // 2
                mid_y = (y_cursor + y_bot) // 2
                c.create_text(mid_x, mid_y, text="🎙 PAUSE",
                              fill="#FFD700", font=("Segoe UI", 7, "bold"), anchor="center")
            else:
                c.create_rectangle(x_l, y_cursor, x_r, y_bot, fill=C["clip_bgm"], outline=outline_col, width=2 if is_sel else 1)
                self._draw_waveform(c, aud, x_l, x_r, y_cursor, y_bot, C["waveform"])
                self._draw_vol_envelope_on_track(c, aud, x_l, x_r, y_cursor, y_bot)
                c.create_text(x_l + 6, y_cursor + 10, text="🎵 " + aud['name'][:20], fill="white", font=("Segoe UI", 8, "bold"), anchor="w")
                c.create_text(x_l + 6, y_cursor + 25, text=f"Vol: {aud.get('volume',1.0)*100:.0f}%", fill="#aaa", font=("Segoe UI", 7), anchor="w")
                c.create_text(self.LABEL_W//2, (y_cursor+y_bot)//2, text=f"A{j+1}", fill=C["accent3"], font=("Arial", 8, "bold"))
                if is_multisel:
                    sel_num = self._audio_multiselect.index(j) + 1
                    c.create_rectangle(x_l, y_cursor, x_r, y_bot, outline="#39d353", width=3, dash=(6,3))
                    c.create_text(x_r - 12, y_cursor + 10, text=f"⛓{sel_num}",
                                  fill="#39d353", font=("Segoe UI", 9, "bold"), anchor="e")

            y_cursor = y_bot + 2
            if x_r > max_aud_x: max_aud_x = x_r

        c.configure(scrollregion=(0, 0, max(max_vid_x, max_aud_x) + 200, y_cursor + 40))

        self._set_playhead(self.playhead_t.get(), preview=False)

        # Draw trim handles on the selected clip
        self._draw_trim_handles(c)

    def _draw_trim_handles(self, c):
        """Draw two free-floating region markers (A/B) inside the selected clip
        plus two EXTEND/SHRINK handles right at the clip's outer edges.
        The region between A/B is shaded so the user can see what will be
        deleted or split.
        """
        def draw_extend_handles(x_l, x_r, y_top, y_bot):
            # Bracket-style handles at the very edge — cyan, easy to grab,
            # visually distinct from the orange/pink A/B cut markers.
            EH = 6
            mid_y = (y_top + y_bot) // 2
            half_h = (y_bot - y_top) * 0.3
            # Left bracket "["
            c.create_line(x_l+EH, mid_y-half_h, x_l, mid_y-half_h, x_l, mid_y+half_h, x_l+EH, mid_y+half_h,
                          fill=C["accent"], width=3, tags="trim_handle")
            # Right bracket "]"
            c.create_line(x_r-EH, mid_y-half_h, x_r, mid_y-half_h, x_r, mid_y+half_h, x_r-EH, mid_y+half_h,
                          fill=C["accent"], width=3, tags="trim_handle")

        def draw_for(ctype, cidx):
            bounds = self._get_clip_bounds(ctype, cidx)
            if not bounds: return
            x_l, x_r, y_top, y_bot = bounds
            # Only draw the handles that belong to the active mode
            if self._handle_mode == "extend":
                draw_extend_handles(x_l, x_r, y_top, y_bot)
            clip_dur = self._get_clip_display_dur(ctype, cidx)
            key = (ctype, cidx)
            if self._handle_mode != "trim":
                return   # skip A/B marker drawing in extend mode

            def t_to_x(t_local):
                return x_l + int(t_local / max(0.001, clip_dur) * (x_r - x_l))

            # Draw shaded region if both markers exist
            if key in self._trim_marker_A and key in self._trim_marker_B:
                tA = self._trim_marker_A[key]
                tB = self._trim_marker_B[key]
                xA = t_to_x(min(tA, tB))
                xB = t_to_x(max(tA, tB))
                c.create_rectangle(xA, y_top, xB, y_bot,
                                   fill=C["danger"], stipple="gray25",
                                   outline="", tags="trim_handle")

            # Draw marker A
            if key in self._trim_marker_A:
                mx = t_to_x(self._trim_marker_A[key])
                c.create_line(mx, y_top, mx, y_bot,
                              fill=C["accent4"], width=3, tags="trim_handle")
                c.create_polygon(mx-5, y_top, mx+5, y_top, mx, y_top+10,
                                 fill=C["accent4"], outline="white", width=1,
                                 tags="trim_handle")
                c.create_text(mx, y_top + 14, text="A",
                              fill="white", font=("Segoe UI", 7, "bold"),
                              tags="trim_handle")

            # Draw marker B
            if key in self._trim_marker_B:
                mx = t_to_x(self._trim_marker_B[key])
                c.create_line(mx, y_top, mx, y_bot,
                              fill="#ff3cac", width=3, tags="trim_handle")
                c.create_polygon(mx-5, y_top, mx+5, y_top, mx, y_top+10,
                                 fill="#ff3cac", outline="white", width=1,
                                 tags="trim_handle")
                c.create_text(mx, y_top + 14, text="B",
                              fill="white", font=("Segoe UI", 7, "bold"),
                              tags="trim_handle")

        if self.selected_idx is not None:
            draw_for("video", self.selected_idx)
        if self.selected_audio_idx is not None:
            draw_for("audio", self.selected_audio_idx)

    # ==========================================
    # INSPECTOR PANEL
    # ==========================================
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

    # ══════════════════════════════════════════════════════════════════
    #  ETHEREAL EFFECT  (MediaPipe segmentation + Zoom Blur God Rays)
    # ══════════════════════════════════════════════════════════════════
    EFFECT_VARIATIONS = {
        'ethereal':        'Ethereal',
        'neon':            'Neon',
        'spacy_game_rays': 'Spacy Game Rays',
        'gabriel_rays':    'Gabriel Rays',
        'angel_rays':      'Angel Rays',
    }

    COLOR_PALETTE = {
        'Gold (Default)':       ((255, 200, 50), (200, 140, 20)),
        # Whites (7) — each is a gradient pair (inner_core, outer_aura)
        'Pure White':           ((255, 255, 255), (200, 210, 220)),
        'Glacial Blue':         ((200, 230, 255), (80, 150, 220)),
        'Golden Cream':         ((255, 240, 190), (220, 170, 60)),
        'Silver Steel':         ((200, 210, 220), (120, 130, 150)),
        'Rose Blush':           ((255, 210, 220), (190, 130, 150)),
        'Violet Haze':          ((230, 215, 255), (160, 120, 210)),
        'Seafoam':              ((210, 255, 220), (110, 200, 150)),
        # Oranges (4)
        'Vibrant Orange':       ((255, 140, 0), (200, 90, 0)),
        'Deep Orange':          ((255, 100, 0), (180, 60, 0)),
        'Amber':                ((255, 190, 0), (200, 130, 0)),
        'Tangerine':            ((255, 160, 50), (200, 110, 20)),
        # Pink-Purple (4)
        'Hot Pink':             ((255, 50, 150), (200, 20, 110)),
        'Magenta':              ((255, 0, 200), (190, 0, 150)),
        'Violet':               ((200, 100, 255), (140, 60, 200)),
        'Lavender':             ((200, 150, 255), (150, 100, 210)),
        # Yellows (4)
        'Bright Yellow':        ((255, 255, 0), (200, 200, 0)),
        'Lemon Yellow':         ((255, 240, 50), (200, 190, 20)),
        'Canary Yellow':        ((255, 220, 60), (200, 170, 30)),
        'Golden Yellow':        ((255, 215, 0), (200, 160, 0)),
        # Neons (5)
        'Neon Cyan':            ((0, 255, 255), (0, 200, 200)),
        'Neon Green':           ((50, 255, 50), (20, 200, 20)),
        'Neon Blue':            ((50, 100, 255), (20, 60, 200)),
        'Neon Pink':            ((255, 20, 147), (200, 10, 110)),
        'Neon Purple':          ((180, 50, 255), (130, 20, 200)),
        # Golds (7)
        'Classic Gold':         ((255, 200, 50), (200, 140, 20)),
        'Rich Gold':            ((255, 180, 0), (200, 120, 0)),
        'Rose Gold':            ((255, 180, 150), (200, 130, 100)),
        'White Gold':           ((255, 245, 220), (200, 190, 170)),
        'Antique Gold':         ((200, 160, 50), (150, 110, 20)),
        'Bright Gold':          ((255, 220, 80), (200, 170, 40)),
        'Pale Gold':            ((255, 230, 180), (200, 180, 130)),
    }

    def _init_mediapipe(self):
        self._mp_segmentor = None
        self._mp_available = False
        try:
            import mediapipe as mp  # type: ignore
            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selfie_segmenter.tflite")
            if not os.path.exists(model_path):
                model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "selfie_segmenter.tflite")
            if not os.path.exists(model_path):
                print("WARNING: selfie_segmenter.tflite model not found. Gold outline will use GrabCut fallback.")
                return
            BaseOptions = mp.tasks.BaseOptions
            ImageSegmenter = mp.tasks.vision.ImageSegmenter
            ImageSegmenterOptions = mp.tasks.vision.ImageSegmenterOptions
            options = ImageSegmenterOptions(
                base_options=BaseOptions(model_asset_path=model_path),
                running_mode=mp.tasks.vision.RunningMode.IMAGE,
                output_category_mask=True
            )
            self._mp_segmentor = ImageSegmenter.create_from_options(options)
            self._mp_available = True
            print("MediaPipe selfie segmenter loaded successfully.")
        except Exception as e:
            print(f"WARNING: MediaPipe initialization failed: {e}")
            self._mp_segmentor = None
            self._mp_available = False

    def _init_yolo(self):
        self._yolo_model = None
        try:
            from ultralytics import YOLO
            self._yolo_model = YOLO("yolov8n-seg.pt")
            print("YOLOv8-seg model loaded successfully.")
            # Suppress noisy GMC optical flow warnings (OpenCV 5.0 bug)
            # Patch the LOGGER object directly — warnings come from multiple trackers
            try:
                from ultralytics.utils import LOGGER as _yl_logger
                _orig_warning = _yl_logger.warning
                def _no_gmc_warning(msg, *a, **kw):
                    if "GMC failed" in str(msg):
                        return
                    return _orig_warning(msg, *a, **kw)
                _yl_logger.warning = _no_gmc_warning
            except Exception:
                pass
        except Exception as e:
            print(f"WARNING: YOLOv8 initialization failed: {e}")
            self._yolo_model = None

    def _yolo_track(self, frame):
        """Run YOLOv8-seg tracking on a frame (video) or detection (image).
        Returns list of dicts for ALL detected objects (not just persons).
        [{'id': track_id, 'class_id': int, 'class_name': str, 'conf': float,
          'mask': ndarray, 'bbox': (x,y,w,h), 'center': (cy,cx), 'area': int}]
        """
        if self._yolo_model is None:
            self._init_yolo()
        if self._yolo_model is None:
            return []

        coco_names = [
            'person','bicycle','car','motorcycle','airplane','bus','train','truck',
            'boat','traffic light','fire hydrant','stop sign','parking meter','bench',
            'bird','cat','dog','horse','sheep','cow','elephant','bear','zebra',
            'giraffe','backpack','umbrella','handbag','tie','suitcase','frisbee',
            'skis','snowboard','sports ball','kite','baseball bat','baseball glove',
            'skateboard','surfboard','tennis racket','bottle','wine glass','cup',
            'fork','knife','spoon','bowl','banana','apple','sandwich','orange',
            'broccoli','carrot','hot dog','pizza','donut','cake','chair','couch',
            'potted plant','bed','dining table','toilet','tv','laptop','mouse',
            'remote','keyboard','cell phone','microwave','oven','toaster','sink',
            'refrigerator','book','clock','vase','scissors','teddy bear',
            'hair drier','toothbrush',
        ]

        try:
            results = self._yolo_model.track(frame, persist=True, verbose=False, conf=0.15)
            detections = []
            has_tracking = (results and results[0].boxes is not None
                            and results[0].boxes.id is not None)
            if has_tracking:
                boxes = results[0].boxes.cpu().numpy()
                track_ids = boxes.id.astype(int)
                xyxy = boxes.xyxy
                clss = boxes.cls.astype(int)
                confs = boxes.conf.astype(float)
                masks_data = results[0].masks
                for i, tid in enumerate(track_ids):
                    x1, y1, x2, y2 = xyxy[i]
                    bw, bh = int(x2 - x1), int(y2 - y1)
                    cid = int(clss[i]) if i < len(clss) else 0
                    cname = coco_names[cid] if cid < len(coco_names) else f'class_{cid}'
                    obj_mask = None
                    sharp_mask = None
                    if masks_data is not None and i < len(masks_data):
                        mask_xy = masks_data.xy[i]
                        if mask_xy is not None and len(mask_xy) > 2:
                            h, w = frame.shape[:2]
                            sharp_mask = np.zeros((h, w), dtype=np.float32)
                            pts = np.array(mask_xy, dtype=np.int32)
                            cv2.fillPoly(sharp_mask, [pts], 1.0)
                            obj_mask = cv2.GaussianBlur(sharp_mask, (5, 5), 0)
                    detections.append({
                        'id': int(tid),
                        'class_id': cid,
                        'class_name': cname,
                        'conf': float(confs[i]) if i < len(confs) else 0.0,
                        'mask': obj_mask,
                        'raw_mask': sharp_mask if sharp_mask is not None else obj_mask,
                        'bbox': (int(x1), int(y1), bw, bh),
                        'center': (int(y1 + bh // 2), int(x1 + bw // 2)),
                        'area': bw * bh,
                    })
            else:
                results = self._yolo_model(frame, verbose=False, conf=0.15)
                if results and results[0].boxes is not None:
                    boxes = results[0].boxes.cpu().numpy()
                    xyxy = boxes.xyxy
                    clss = boxes.cls.astype(int)
                    confs = boxes.conf.astype(float)
                    masks_data = results[0].masks
                    for i in range(len(xyxy)):
                        x1, y1, x2, y2 = xyxy[i]
                        bw, bh = int(x2 - x1), int(y2 - y1)
                        cid = int(clss[i]) if i < len(clss) else 0
                        cname = coco_names[cid] if cid < len(coco_names) else f'class_{cid}'
                        obj_mask = None
                        sharp_mask = None
                        if masks_data is not None and i < len(masks_data):
                            mask_xy = masks_data.xy[i]
                            if mask_xy is not None and len(mask_xy) > 2:
                                h, w = frame.shape[:2]
                                sharp_mask = np.zeros((h, w), dtype=np.float32)
                                pts = np.array(mask_xy, dtype=np.int32)
                                cv2.fillPoly(sharp_mask, [pts], 1.0)
                                obj_mask = cv2.GaussianBlur(sharp_mask, (5, 5), 0)
                        detections.append({
                            'id': i,
                            'class_id': cid,
                            'class_name': cname,
                            'conf': float(confs[i]) if i < len(confs) else 0.0,
                            'mask': obj_mask,
                            'raw_mask': sharp_mask if sharp_mask is not None else obj_mask,
                            'bbox': (int(x1), int(y1), bw, bh),
                            'center': (int(y1 + bh // 2), int(x1 + bw // 2)),
                            'area': bw * bh,
                        })
            return detections
        except Exception as e:
            print(f"YOLO tracking error: {e}")
            return []

    def _get_mediapipe_mask(self, frame):
        if self._mp_segmentor is None:
            self._init_mediapipe()
        if self._mp_segmentor is None:
            return None
        try:
            import mediapipe as mp  # type: ignore
            h, w = frame.shape[:2]
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            result = self._mp_segmentor.segment(mp_img)
            if result.confidence_masks and len(result.confidence_masks) > 0:
                mask = result.confidence_masks[0].numpy_view().astype(np.float32)
                if mask.ndim == 3:
                    mask = mask[..., 0]
                mask = cv2.GaussianBlur(mask, (7, 7), 0)
                mask_uint8 = (mask * 255).astype(np.uint8)
                kernel = np.ones((5, 5), np.uint8)
                mask_uint8 = cv2.morphologyEx(mask_uint8, cv2.MORPH_OPEN, kernel, iterations=1)
                mask_uint8 = cv2.morphologyEx(mask_uint8, cv2.MORPH_CLOSE, kernel, iterations=2)
                num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_uint8, connectivity=8)
                h_m, w_m = mask_uint8.shape
                min_area = (h_m * w_m) * 0.001
                clean = np.zeros_like(mask_uint8)
                for i in range(1, num_labels):
                    if stats[i, cv2.CC_STAT_AREA] >= min_area:
                        clean[labels == i] = mask_uint8[labels == i]
                mask = clean.astype(np.float32) / 255.0
                mask = cv2.GaussianBlur(mask, (5, 5), 0)
                return mask
        except Exception as e:
            print(f"WARNING: MediaPipe segmentation failed: {e}")
        return None

    def _apply_zoom_blur(self, img, center, zoom_factor=1.08, num_steps=25):
        h, w = img.shape[:2]
        result = np.zeros((h, w, 3), dtype=np.float32)
        for i in range(num_steps):
            scale = 1.0 + (zoom_factor - 1.0) * (i / num_steps)
            matrix = cv2.getRotationMatrix2D(center, 0, scale)
            scaled = cv2.warpAffine(img, matrix, (w, h))
            result += scaled
        result = result / num_steps
        return result

    def _smooth_mask_for_outline(self, mask):
        """Smooth a mask to produce clean, flowing outline contours."""
        smooth = cv2.GaussianBlur(mask, (7, 7), 0)
        kernel = np.ones((5, 5), np.uint8)
        smooth_uint8 = (smooth * 255).astype(np.uint8)
        smooth_uint8 = cv2.morphologyEx(smooth_uint8, cv2.MORPH_CLOSE, kernel, iterations=1)
        smooth = cv2.GaussianBlur(smooth_uint8.astype(np.float32) / 255.0, (5, 5), 0)
        return smooth

    def _create_god_ray_effect(self, frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask=None, drawn_edges=None):
        h, w = frame.shape[:2]
        base = original_mask if original_mask is not None else mask
        # Compute edges from the original mask to preserve fine details (fingers, gaps)
        base_u8 = (np.clip(base, 0, 1) * 255).astype(np.uint8)
        edges = cv2.Canny(base_u8, 20, 80)
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
        edge_mask = cv2.GaussianBlur(edges, (5, 5), 0).astype(np.float32) / 255.0
        outer_edge = cv2.dilate(edges, np.ones((7, 7), np.uint8), iterations=1)
        outer_edge = cv2.GaussianBlur(outer_edge, (11, 11), 0).astype(np.float32) / 255.0
        # Thick ring from lightly smoothed base (preserves finger contours)
        base_smooth = cv2.GaussianBlur(base, (5, 5), 0)
        base_smooth_u8 = (np.clip(base_smooth, 0, 1) * 255).astype(np.uint8)
        thick_ring = cv2.dilate(base_smooth_u8, np.ones((7, 7), np.uint8), iterations=2)
        thick_ring_inner = cv2.erode(base_smooth_u8, np.ones((3, 3), np.uint8), iterations=1)
        thick_ring = np.clip(thick_ring.astype(np.float32) - thick_ring_inner.astype(np.float32), 0, 255) / 255.0
        thick_ring = cv2.GaussianBlur(thick_ring, (5, 5), 0)
        # Erode base to open narrow gaps (e.g., between fingers) so light passes through
        base_eroded = cv2.erode(base_u8, np.ones((3, 3), np.uint8), iterations=1)
        inv_mask = 1.0 - base_eroded.astype(np.float32) / 255.0
        inv_mask = cv2.GaussianBlur(inv_mask, (7, 7), 0)
        # Incorporate drawn edges with same styling as regular edge_mask
        if drawn_edges is not None and drawn_edges.max() > 0:
            de = cv2.GaussianBlur(drawn_edges, (5, 5), 0).astype(np.float32)
            edge_mask = np.maximum(edge_mask, de)
            de_outer = cv2.dilate((drawn_edges * 255).astype(np.uint8), np.ones((7, 7), np.uint8), iterations=1)
            de_outer = cv2.GaussianBlur(de_outer, (11, 11), 0).astype(np.float32) / 255.0
            outer_edge = np.maximum(outer_edge, de_outer)
        # Bright inner edge glow (inner color)
        edge_layer = np.zeros_like(frame, dtype=np.float32)
        edge_layer[:] = color_inner
        edge_layer *= edge_mask[..., np.newaxis] * glow * time_factor * 3.0
        # Thick outline ring (inner color)
        ring_layer = np.zeros_like(frame, dtype=np.float32)
        ring_layer[:] = color_inner
        ring_layer *= thick_ring[..., np.newaxis] * glow * time_factor * 2.5
        # Soft outer glow (outer color)
        glow_layer = np.zeros_like(frame, dtype=np.float32)
        glow_layer[:] = color_outer
        glow_layer *= outer_edge[..., np.newaxis] * glow * time_factor * 2.0
        glow_layer = cv2.GaussianBlur(glow_layer, (15, 15), 0)
        glow_layer *= inv_mask[..., np.newaxis]
        edge_layer *= inv_mask[..., np.newaxis]
        ring_layer *= inv_mask[..., np.newaxis]
        combined = frame.astype(np.float32)
        combined += glow_layer * opacity
        combined += edge_layer * opacity
        combined += ring_layer * opacity
        dark_mask = np.exp(-((np.arange(h)[:, None] - h*0.5)**2 + (np.arange(w)[None, :] - w*0.5)**2) / (2 * (max(h,w)*0.6)**2))
        crush = 1.0 - (1.0 - dark_mask[..., np.newaxis]) * 0.3 * opacity * time_factor
        combined *= crush
        return np.clip(combined, 0, 255).astype(np.uint8)

    def _create_ethereal_effect(self, frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask=None, drawn_edges=None):
        h, w = frame.shape[:2]
        base = original_mask if original_mask is not None else mask
        # Compute edges from the original mask to preserve fine details (fingers, gaps)
        base_u8 = (np.clip(base, 0, 1) * 255).astype(np.uint8)
        edges = cv2.Canny(base_u8, 20, 80)
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
        edge_mask = cv2.GaussianBlur(edges, (7, 7), 0).astype(np.float32) / 255.0
        outer_edge = cv2.dilate(edges, np.ones((9, 9), np.uint8), iterations=1)
        outer_edge = cv2.GaussianBlur(outer_edge, (17, 17), 0).astype(np.float32) / 255.0
        # Thick ring from lightly smoothed base (preserves finger contours)
        base_smooth = cv2.GaussianBlur(base, (5, 5), 0)
        base_smooth_u8 = (np.clip(base_smooth, 0, 1) * 255).astype(np.uint8)
        thick_ring = cv2.dilate(base_smooth_u8, np.ones((9, 9), np.uint8), iterations=2)
        thick_ring_inner = cv2.erode(base_smooth_u8, np.ones((3, 3), np.uint8), iterations=1)
        thick_ring = np.clip(thick_ring.astype(np.float32) - thick_ring_inner.astype(np.float32), 0, 255) / 255.0
        thick_ring = cv2.GaussianBlur(thick_ring, (7, 7), 0)
        # Erode base to open narrow gaps (e.g., between fingers) so light passes through
        base_eroded = cv2.erode(base_u8, np.ones((3, 3), np.uint8), iterations=1)
        inv_mask = 1.0 - base_eroded.astype(np.float32) / 255.0
        inv_mask = cv2.GaussianBlur(inv_mask, (7, 7), 0)
        # Incorporate drawn edges with same styling as regular edge_mask
        if drawn_edges is not None and drawn_edges.max() > 0:
            de = cv2.GaussianBlur(drawn_edges, (7, 7), 0).astype(np.float32)
            edge_mask = np.maximum(edge_mask, de)
            de_outer = cv2.dilate((drawn_edges * 255).astype(np.uint8), np.ones((9, 9), np.uint8), iterations=1)
            de_outer = cv2.GaussianBlur(de_outer, (17, 17), 0).astype(np.float32) / 255.0
            outer_edge = np.maximum(outer_edge, de_outer)
        # Bright inner edge (inner color)
        edge_layer = np.zeros_like(frame, dtype=np.float32)
        edge_layer[:] = color_inner
        edge_layer *= edge_mask[..., np.newaxis] * glow * time_factor * 3.5
        # Thick outline ring (inner color)
        ring_layer = np.zeros_like(frame, dtype=np.float32)
        ring_layer[:] = color_inner
        ring_layer *= thick_ring[..., np.newaxis] * glow * time_factor * 3.0
        # Soft outer glow (outer color)
        glow_layer = np.zeros_like(frame, dtype=np.float32)
        glow_layer[:] = color_outer
        glow_layer *= outer_edge[..., np.newaxis] * glow * time_factor * 2.5
        glow_layer = cv2.GaussianBlur(glow_layer, (21, 21), 0)
        glow_layer *= inv_mask[..., np.newaxis]
        edge_layer *= inv_mask[..., np.newaxis]
        ring_layer *= inv_mask[..., np.newaxis]
        combined = frame.astype(np.float32)
        combined += glow_layer * opacity
        combined += edge_layer * opacity
        combined += ring_layer * opacity
        dark_mask = np.exp(-((np.arange(h)[:, None] - h*0.5)**2 + (np.arange(w)[None, :] - w*0.5)**2) / (2 * (max(h,w)*0.5)**2))
        crush = 1.0 - (1.0 - dark_mask[..., np.newaxis]) * 0.4 * opacity * time_factor
        combined *= crush
        return np.clip(combined, 0, 255).astype(np.uint8)

    def _create_divine_effect(self, frame, mask, ray_color, opacity, glow, time_factor, original_mask=None, drawn_edges=None):
        h, w = frame.shape[:2]
        base = original_mask if original_mask is not None else mask

        # Distance-based edge detection on original mask (preserves finger gaps)
        base_uint8 = (np.clip(base, 0, 1) * 255).astype(np.uint8)
        dist = cv2.distanceTransform(base_uint8, cv2.DIST_L2, 5)
        dist_norm = np.clip(dist / max(dist.max(), 1), 0, 1).astype(np.float32)

        # Thin edge from distance gradient (peak at the boundary)
        edge_inner = np.clip(dist_norm - 0.5, 0, 0.5) * 2.0
        edge_outer = np.clip(0.5 - dist_norm, 0, 0.5) * 2.0
        thin_edge = np.clip(edge_inner + edge_outer, 0, 1)

        # Thicker ring from smoothed mask (for smooth glow contours)
        smooth_mask = self._smooth_mask_for_outline(mask)
        smooth_uint8 = (smooth_mask * 255).astype(np.uint8)
        dilate_k = np.ones((11, 11), np.uint8)
        erode_k = np.ones((5, 5), np.uint8)
        dilated = cv2.dilate(smooth_uint8, dilate_k, iterations=1)
        eroded = cv2.erode(smooth_uint8, erode_k, iterations=1)
        thick_ring = np.clip(dilated.astype(np.float32) - eroded.astype(np.float32), 0, 255) / 255.0
        thick_ring = cv2.GaussianBlur(thick_ring, (9, 9), 0)

        # Soft outer glow from distance field of original mask
        outer_glow = np.clip(1.0 - dist_norm, 0, 1)
        outer_glow = cv2.GaussianBlur(outer_glow, (21, 21), 0)

        base_eroded = cv2.erode(base_uint8, np.ones((3, 3), np.uint8), iterations=1)
        inv_mask = 1.0 - cv2.GaussianBlur(base_eroded.astype(np.float32) / 255.0, (7, 7), 0)

        combined = frame.astype(np.float32)

        # Thin bright edge
        edge_layer = np.zeros_like(frame, dtype=np.float32)
        edge_layer[:] = ray_color
        edge_layer *= thin_edge[..., np.newaxis] * glow * time_factor * 4.0

        # Thick gold ring
        ring_layer = np.zeros_like(frame, dtype=np.float32)
        ring_layer[:] = ray_color
        ring_layer *= thick_ring[..., np.newaxis] * glow * time_factor * 3.5

        # Soft outer glow
        glow_layer = np.zeros_like(frame, dtype=np.float32)
        glow_layer[:] = ray_color
        glow_layer *= outer_glow[..., np.newaxis] * glow * time_factor * 2.5

        edge_layer *= inv_mask[..., np.newaxis]
        ring_layer *= inv_mask[..., np.newaxis]
        glow_layer *= inv_mask[..., np.newaxis]

        combined += edge_layer * opacity
        combined += ring_layer * opacity
        combined += glow_layer * opacity
        return np.clip(combined, 0, 255).astype(np.uint8)

    def _create_brilliance_effect(self, frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask=None, drawn_edges=None):
        h, w = frame.shape[:2]
        base = original_mask if original_mask is not None else mask

        # Convert RGB to BGR for OpenCV (inner = core, outer = halo/wrap)
        GOLD_BGR = np.array([color_inner[2], color_inner[1], color_inner[0]], dtype=np.float32)
        OUTER_BGR = np.array([color_outer[2], color_outer[1], color_outer[0]], dtype=np.float32)

        # ════════════════════════════════════════════════════════════════
        # STEP 1: MASK PRE-PROCESSING — Clean the Emitter
        # ════════════════════════════════════════════════════════════════
        base_uint8 = (np.clip(base, 0, 1) * 255).astype(np.uint8)
        _, binary = cv2.threshold(base_uint8, 30, 255, cv2.THRESH_BINARY)
        kernel_clean = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_clean)
        clean_mask_u8 = binary

        soft_mask = cv2.GaussianBlur(binary, (11, 11), 0)
        mask_f32 = soft_mask.astype(np.float32) / 255.0
        mask_3ch = cv2.merge([mask_f32, mask_f32, mask_f32])

        # ════════════════════════════════════════════════════════════════
        # STEP 2: EMISSIVE LIGHT SOURCE — golden on black canvas
        # ════════════════════════════════════════════════════════════════
        gold_emissive = np.zeros((h, w, 3), dtype=np.float32)
        gold_emissive[:, :] = GOLD_BGR / 255.0
        light_source = gold_emissive * mask_3ch

        # ════════════════════════════════════════════════════════════════
        # STEP 3: FIND ORIGIN — upper chest/head area
        # ════════════════════════════════════════════════════════════════
        ys, xs = np.where(clean_mask_u8 > 0)
        if len(xs) > 0:
            center = (
                int(np.mean(xs)),
                int(np.min(ys) + (np.max(ys) - np.min(ys)) * 0.25)
            )
        else:
            center = (w // 2, h // 3)

        # ════════════════════════════════════════════════════════════════
        # STEP 4: VOLUMETRIC ACCUMULATION LOOP (The God Rays)
        # ════════════════════════════════════════════════════════════════
        ray_buffer = np.zeros_like(light_source)
        N = 100
        wgt = 0.05
        decay = 0.96

        for i in range(N):
            scale = 1.0 + i * 0.004
            M = cv2.getRotationMatrix2D(center, 0.0, scale)
            warped = cv2.warpAffine(
                light_source, M, (w, h),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0)
            )
            ray_buffer += warped * wgt
            wgt *= decay

        # ════════════════════════════════════════════════════════════════
        # STEP 5: CORE HALO & OVEREXPOSURE (HDR Bloom Simulation)
        # ════════════════════════════════════════════════════════════════
        halo = cv2.GaussianBlur(mask_3ch, (81, 81), 0)
        gold_halo = halo * (OUTER_BGR / 255.0)
        white_core = np.clip((halo ** 3) * 1.5, 0.0, 1.0)

        total_light = ray_buffer + gold_halo + white_core
        total_light_u8 = np.clip(total_light * 255.0, 0, 255).astype(np.uint8)
        total_light_u8 = cv2.GaussianBlur(total_light_u8, (15, 15), 0)

        eff = float(opacity * glow * time_factor)
        total_light_u8 = cv2.convertScaleAbs(total_light_u8, alpha=eff)

        # ════════════════════════════════════════════════════════════════
        # STEP 6: FINAL COMPOSITING STACK
        # ════════════════════════════════════════════════════════════════
        bg_darkened = cv2.convertScaleAbs(frame, alpha=0.5, beta=0)
        glowing_bg = cv2.add(bg_darkened, total_light_u8)

        subject = cv2.bitwise_and(frame, frame, mask=clean_mask_u8)
        inv_mask = cv2.bitwise_not(clean_mask_u8)
        final_bg = cv2.bitwise_and(glowing_bg, glowing_bg, mask=inv_mask)
        output = cv2.add(final_bg, subject)

        # ════════════════════════════════════════════════════════════════
        # STEP 7: LIGHT WRAP — bleed light over subject's edges
        # ════════════════════════════════════════════════════════════════
        wrap_mask = cv2.GaussianBlur(clean_mask_u8, (11, 11), 0)
        edge_spill = cv2.bitwise_and(wrap_mask, inv_mask)
        edge_f = edge_spill.astype(np.float32) / 255.0
        light_wrap = cv2.merge([
            (edge_f * OUTER_BGR[0]).astype(np.uint8),
            (edge_f * OUTER_BGR[1]).astype(np.uint8),
            (edge_f * OUTER_BGR[2]).astype(np.uint8),
        ])
        final_frame = cv2.add(output, light_wrap)

        if drawn_edges is not None and drawn_edges.max() > 0:
            de = cv2.GaussianBlur(drawn_edges, (5, 5), 0).astype(np.float32)
            de_layer = np.zeros((h, w, 3), dtype=np.float32)
            de_layer[:] = GOLD_BGR / 255.0
            de_layer *= de[..., np.newaxis] * glow * time_factor * 3.0
            de_layer = np.clip(de_layer * 255, 0, 255).astype(np.uint8)
            final_frame = cv2.add(final_frame, de_layer)

        return final_frame

    def _create_kaka_effect(self, frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask=None, drawn_edges=None):
        h, w = frame.shape[:2]
        frame_f = frame.astype(np.float32)
        mask = self._smooth_mask_for_outline(mask)
        base = original_mask if original_mask is not None else mask
        base = np.clip(base, 0, 1)
        GOLD_INNER = np.array(color_inner, dtype=np.float32)
        GOLD_OUTER = np.array(color_outer, dtype=np.float32)
        diag = float(np.sqrt(w * w + h * h))

        # --- 1. MASK EXTRACTION ---
        subj = base.copy()

        # --- 2. BASE AURA (Glow) ---
        # Gaussian blur on the mask, tinted golden yellow #FFC832
        aura = cv2.GaussianBlur(subj, (31, 31), 0)
        aura = cv2.GaussianBlur(aura, (0, 0), sigmaX=15.0)
        aura = np.clip(aura, 0, 1)
        base_aura = aura[..., np.newaxis] * GOLD_INNER * glow * time_factor * 2.5

        # --- 3. GOD RAYS (Volumetric Light Scattering / Zoom Blur) ---
        # Center point = center of the subject
        ys, xs = np.where(subj > 0.3)
        if len(xs) > 0 and len(ys) > 0:
            cy, cx = int(np.mean(ys)), int(np.mean(xs))
        else:
            cy, cx = h // 2, w // 2

        Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
        dy = Y - cy
        dx = X - cx

        # Accumulation loop: Color_rays = sum_{i=0}^{N} Texture(UV_scaled_i) * Weight * Decay^i
        N = 64
        decay = 0.92
        weight = 0.08
        scale_step = 0.025
        accumulator = np.zeros((h, w), dtype=np.float32)

        for i in range(N):
            scale = 1.0 + i * scale_step
            # Map each pixel back to the source position under this zoom scale
            src_y = cy + dy / scale
            src_x = cx + dx / scale
            # Clamp to valid range
            src_y = np.clip(src_y, 0, h - 1)
            src_x = np.clip(src_x, 0, w - 1)
            # Sample the mask at the scaled position (bilinear would be better but nearest is fine for mask)
            sy_f = np.floor(src_y).astype(np.int32)
            sx_f = np.floor(src_x).astype(np.int32)
            sy_f = np.clip(sy_f, 0, h - 1)
            sx_f = np.clip(sx_f, 0, w - 1)
            sample = subj[sy_f, sx_f]
            accumulator += sample * weight * (decay ** i)

        # Normalize and soften the ray accumulation
        god_rays = np.clip(accumulator, 0, 1)
        god_rays = cv2.GaussianBlur(god_rays, (5, 5), 0)
        rays_colored = god_rays[..., np.newaxis] * GOLD_OUTER * glow * time_factor * 4.0

        # --- 5. BACKGROUND PROCESSING ---
        bg = frame_f.copy()
        bg_lum = bg[..., 0] * 0.299 + bg[..., 1] * 0.587 + bg[..., 2] * 0.114
        bg_mean = bg_lum.mean()
        contrast_factor = 0.70
        for c in range(3):
            bg[..., c] = bg_mean + (bg[..., c] - bg_mean) * contrast_factor
        bg *= 0.65
        bg = np.clip(bg, 0, 255)

        # --- 6. ADDITIVE BLENDING ---
        # C_final = C_bg + C_glow  (strict additive, no alpha blending)
        glow_all = base_aura + rays_colored
        result = bg + glow_all * opacity
        result = np.clip(result, 0, 255)

        # --- 7. FINAL COMPOSITE ---
        subj_3ch = subj[..., np.newaxis]
        result = result * (1.0 - subj_3ch) + frame_f * subj_3ch
        result = np.clip(result, 0, 255)

        if drawn_edges is not None and drawn_edges.max() > 0:
            de = cv2.GaussianBlur(drawn_edges, (5, 5), 0).astype(np.float32)
            result_f = result.astype(np.float32)
            result_f += de[..., np.newaxis] * GOLD_INNER * glow * time_factor * 3.0
            result = np.clip(result_f, 0, 255)

        return result.astype(np.uint8)

    def _find_head_position(self, frame, mask_bool, cy, cx, bbox=None):
        h, w = frame.shape[:2]

        # Priority 1: Face detection via Haar cascade (handles tilted heads well)
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            face_cascade = cv2.CascadeClassifier(
                _HAAR_CASCADE_PATH)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(30, 30))
            if len(faces) > 0:
                largest = max(faces, key=lambda f: f[2] * f[3])
                fx, fy, fw, fh = largest
                return (fy + fh // 2, fx + fw // 2)
        except Exception:
            pass

        # Priority 2: YOLO bounding box — use top-center of the bbox
        if bbox is not None:
            bx, by, bw, bh = bbox
            head_cx = bx + bw // 2
            head_cy = by + max(5, int(bh * 0.12))
            return (head_cy, head_cx)

        # Priority 3: Mask-based head detection — find head by scanning top of mask
        ys, xs = np.where(mask_bool)
        if len(ys) < 10:
            return (cy, cx)

        y_min, y_max = int(ys.min()), int(ys.max())
        person_height = y_max - y_min
        if person_height < 30:
            return (cy, cx)

        # Scan only the top 30% of the person (head + shoulders region)
        scan_limit = y_min + int(person_height * 0.30)
        last_span = None
        neck_row = y_min

        for row_y in range(y_min, min(scan_limit, y_max)):
            row_pixels = xs[ys == row_y]
            if len(row_pixels) < 5:
                continue
            span = row_pixels.max() - row_pixels.min()
            if last_span is not None and span > last_span * 1.6 and span > 40:
                neck_row = row_y
                break
            last_span = span

        # If no clear widening found, use the top region centroid
        if neck_row == y_min:
            neck_row = y_min + int(scan_limit - y_min) // 3

        head_cy = (y_min + neck_row) // 2

        # Head center X: median of mask pixels in the head band (more robust than mean)
        head_band = (ys >= y_min) & (ys <= neck_row)
        hxs = xs[head_band]
        head_cx = int(np.median(hxs)) if len(hxs) > 10 else cx

        return (head_cy, head_cx)

    def _create_holy_aura_effect(self, frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask=None, bbox=None, drawn_edges=None):
        h, w = frame.shape[:2]
        mask = self._smooth_mask_for_outline(mask)
        base = original_mask if original_mask is not None else mask
        mask_bool = base > 0.3

        ys, xs = np.where(mask_bool)
        if len(xs) > 0 and len(ys) > 0:
            cy = int(np.mean(ys))
            cx = int(np.mean(xs))
        else:
            cy, cx = h // 2, w // 2

        inv_uint8 = (np.clip(1.0 - base, 0, 1) * 255).astype(np.uint8)
        dist_outside = cv2.distanceTransform(inv_uint8, cv2.DIST_L2, 5).astype(np.float32)

        head_cy, head_cx = self._find_head_position(frame, mask_bool, cy, cx, bbox)

        Y, X = np.mgrid[:h, :w]
        head_dx = (X - head_cx).astype(np.float32)
        head_dy = (Y - head_cy).astype(np.float32)
        head_dist = np.sqrt(head_dx**2 + head_dy**2)
        head_angle = np.arctan2(head_dy, head_dx)
        diag = np.sqrt(w * w + h * h)

        outside_mask = 1.0 - cv2.GaussianBlur(base, (5, 5), 0)
        inside_mask = cv2.GaussianBlur(base, (5, 5), 0)

        golden_layer = np.zeros_like(frame, dtype=np.float32)

        color_inner_f = np.array(color_inner, dtype=np.float32)
        color_outer_f = np.array(color_outer, dtype=np.float32)

        # 1. Center bloom behind head (inner color — vibrant core)
        bloom_r = diag * 0.06
        bloom = np.clip(1.0 - head_dist / bloom_r, 0, 1) ** 0.8
        bloom *= outside_mask
        golden_layer += bloom[..., np.newaxis] * color_inner_f * glow * time_factor * 8.0

        # 2. Warm glow expanding outward (outer color — aura)
        glow_r = diag * 0.12
        warm_glow = np.clip(1.0 - head_dist / glow_r, 0, 1) ** 1.5
        warm_glow *= outside_mask
        golden_layer += warm_glow[..., np.newaxis] * color_outer_f * glow * time_factor * 4.0

        # 3. Wide soft rays (outer color — light beams)
        num_rays = 16
        ray_mask = np.zeros((h, w), dtype=np.float32)
        for i in range(num_rays):
            ray_angle = (2.0 * np.pi * i) / num_rays
            angular_diff = np.abs(np.arctan2(np.sin(head_angle - ray_angle), np.cos(head_angle - ray_angle)))
            ray_cone = np.clip(1.0 - angular_diff / 0.12, 0, 1) ** 2.0
            ray_mask += ray_cone
        ray_mask = np.clip(ray_mask, 0, 1)
        ray_mask *= np.clip(1.0 - (head_dist / (diag * 0.50)) ** 0.5, 0, 1)
        ray_mask *= outside_mask
        ray_mask = cv2.GaussianBlur(ray_mask, (11, 11), 0)
        golden_layer += ray_mask[..., np.newaxis] * color_outer_f * glow * time_factor * 3.0

        # 4. Outer atmospheric haze (outer color)
        haze_r = diag * 0.22
        haze = np.clip(1.0 - head_dist / haze_r, 0, 1) ** 2.0
        haze *= outside_mask
        haze = cv2.GaussianBlur(haze, (25, 25), 0)
        golden_layer += haze[..., np.newaxis] * color_outer_f * glow * time_factor * 1.2

        # 5. Soft outline around person body (inner color — sharp edge)
        edge_width = 8.0
        edge_out = np.clip(dist_outside / edge_width, 0, 1)
        edge_out = 1.0 - edge_out
        edge_out = np.clip(edge_out, 0, 1)
        edge_out = cv2.GaussianBlur(edge_out, (5, 5), 0)
        golden_layer += edge_out[..., np.newaxis] * color_inner_f * glow * time_factor * 4.0

        # COMPOSITE
        combined = frame.astype(np.float32)

        # Gentle background darkening — keep background visible
        bg_darken = np.clip(dist_outside / (diag * 0.40), 0, 1) ** 1.5
        bg_darken = 0.45 + 0.55 * bg_darken
        bg_factor = inside_mask * 1.0 + (1.0 - inside_mask) * bg_darken
        combined *= bg_factor[..., np.newaxis]

        # Add golden light to background only
        combined += golden_layer * opacity * outside_mask[..., np.newaxis]

        if drawn_edges is not None and drawn_edges.max() > 0:
            de = cv2.GaussianBlur(drawn_edges, (5, 5), 0).astype(np.float32)
            combined += de[..., np.newaxis] * color_inner_f * glow * time_factor * 3.0

        return np.clip(combined, 0, 255).astype(np.uint8)

    # ══════════════════════════════════════════════════════════════════
    #  FILM BURN OVERLAY EFFECT  (Scorching light flares)
    #  Simulates vintage film stock burning with warm orange-red light
    #  leaks and animated flare spots sweeping across the frame.
    # ══════════════════════════════════════════════════════════════════

    def _create_film_burn_effect(self, frame, intensity=1.0, speed=1.0, time_factor=0.0):
        h, w = frame.shape[:2]
        combined = frame.astype(np.float32)
        t = time_factor * speed

        # Multiple flare centers that sweep across the frame dynamically
        flare1_x = int(w * (0.1 + 0.8 * ((t * 0.7) % 1.0)))
        flare1_y = int(h * (0.3 + 0.3 * np.sin(t * np.pi * 2.2)))
        flare2_x = int(w * (0.9 - 0.7 * ((t * 0.5) % 1.0)))
        flare2_y = int(h * (0.7 + 0.2 * np.cos(t * np.pi * 3.1)))
        flare3_x = int(w * (0.5 + 0.35 * np.sin(t * np.pi * 1.3)))
        flare3_y = int(h * (0.1 + 0.8 * ((t * 0.35) % 1.0)))
        flare4_x = int(w * (0.2 + 0.6 * np.cos(t * np.pi * 1.8 + 1.0)))
        flare4_y = int(h * (0.5 + 0.4 * np.sin(t * np.pi * 2.7 + 0.5)))

        yy, xx = np.mgrid[0:h, 0:w]

        # --- Flare 1: Large warm orange core ---
        r1 = np.sqrt(((xx - flare1_x) / (w * 0.4))**2 + ((yy - flare1_y) / (h * 0.5))**2)
        flare1 = np.clip(1.0 - r1, 0, 1) ** 1.5
        flare1_color = np.array([255, 150, 20], dtype=np.float32)

        # --- Flare 2: Medium red-hot streak ---
        r2 = np.sqrt(((xx - flare2_x) / (w * 0.3))**2 + ((yy - flare2_y) / (h * 0.35))**2)
        flare2 = np.clip(1.0 - r2, 0, 1) ** 2.0
        flare2_color = np.array([255, 50, 5], dtype=np.float32)

        # --- Flare 3: Small bright yellow-white hotspot ---
        r3 = np.sqrt(((xx - flare3_x) / (w * 0.18))**2 + ((yy - flare3_y) / (h * 0.22))**2)
        flare3 = np.clip(1.0 - r3, 0, 1) ** 2.5
        flare3_color = np.array([255, 230, 100], dtype=np.float32)

        # --- Flare 4: Extra moving flare for more dynamism ---
        r4 = np.sqrt(((xx - flare4_x) / (w * 0.25))**2 + ((yy - flare4_y) / (h * 0.3))**2)
        flare4 = np.clip(1.0 - r4, 0, 1) ** 1.8
        flare4_color = np.array([255, 100, 10], dtype=np.float32)

        # --- Horizontal anamorphic light leak streak ---
        streak_y = int(h * (0.35 + 0.3 * np.sin(t * np.pi * 2.8)))
        streak_mask = np.exp(-((yy - streak_y).astype(np.float32)**2) / (2 * (h * 0.1)**2))
        streak_x_mask = np.clip(1.0 - np.abs(xx - w // 2).astype(np.float32) / (w * 0.5), 0, 1)
        streak = streak_mask * streak_x_mask ** 1.3
        streak_color = np.array([255, 180, 50], dtype=np.float32)

        # --- Edge burn (film burns brightest at edges) ---
        cx, cy = w / 2, h / 2
        dist_from_center = np.sqrt(((xx - cx) / cx)**2 + ((yy - cy) / cy)**2)
        edge_burn = np.clip(dist_from_center - 0.4, 0, 1) ** 1.1
        edge_burn_color = np.array([220, 90, 10], dtype=np.float32)

        # --- Compose all layers (boosted multipliers for brightness) ---
        film_layer = np.zeros_like(combined)
        film_layer += flare1[..., np.newaxis] * flare1_color * (0.9 * intensity)
        film_layer += flare2[..., np.newaxis] * flare2_color * (0.7 * intensity)
        film_layer += flare3[..., np.newaxis] * flare3_color * (1.1 * intensity)
        film_layer += flare4[..., np.newaxis] * flare4_color * (0.65 * intensity)
        film_layer += streak[..., np.newaxis] * streak_color * (0.55 * intensity)
        film_layer += edge_burn[..., np.newaxis] * edge_burn_color * (0.45 * intensity)

        # --- Glow blur for soft diffusion ---
        blur_ksize = max(3, int(min(h, w) * 0.07)) | 1
        film_layer = cv2.GaussianBlur(film_layer, (blur_ksize, blur_ksize), 0)

        # --- Screen blend: brighten without crushing blacks ---
        film_norm = film_layer / 255.0
        base_norm = combined / 255.0
        screen = 1.0 - (1.0 - base_norm) * (1.0 - film_norm * 0.85)
        combined = screen * 255.0

        # --- Warm color grade: push midtones toward amber ---
        combined[:, :, 0] = combined[:, :, 0] * 1.12   # boost red
        combined[:, :, 2] = combined[:, :, 2] * 0.85    # reduce blue

        # --- Fade in/out envelope using intensity as opacity proxy ---
        blend = np.clip(intensity * 0.75, 0.0, 1.0)
        combined = frame.astype(np.float32) * (1.0 - blend) + combined * blend

        return np.clip(combined, 0, 255).astype(np.uint8)

    def apply_film_burn_effect(self, frame, item, t):
        if not item.get('effect_film_burn_enabled', False):
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame
        intensity = item.get('film_burn_intensity', 1.0)
        speed = item.get('film_burn_speed', 1.0)
        return self._create_film_burn_effect(frame, intensity=intensity, speed=speed, time_factor=t)


    # ══════════════════════════════════════════════════════════════════
    #  SUN GLARE EFFECT  (Corner sun with radiating rays, trailing a
    #  diagonal chain of soft hexagonal anamorphic lens flares — the
    #  classic warm "shooting into the sun" cinematic look. Works
    #  identically on a single still image or every frame of a video.)
    # ══════════════════════════════════════════════════════════════════

    _SUN_GLARE_POSITIONS = {
        'top left':     (0.10, 0.10),
        'top right':    (0.90, 0.10),
        'bottom left':  (0.10, 0.90),
        'bottom right': (0.90, 0.90),
        'center':       (0.50, 0.50),
    }

    def _create_sun_glare_effect(self, frame, variation='Cinematic', position='Top Left',
                                  intensity=1.0, size=1.0, speed=0.3, time_factor=0.0):
        h, w = frame.shape[:2]
        combined = frame.astype(np.float32)
        diag = float(np.hypot(w, h))
        t = time_factor * speed

        key = str(position).strip().lower().replace('_', ' ')
        sx_f, sy_f = self._SUN_GLARE_POSITIONS.get(key, (0.10, 0.10))
        sun_x, sun_y = sx_f * w, sy_f * h
        opp_x, opp_y = w - sun_x, h - sun_y

        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        dx = xx - sun_x
        dy = yy - sun_y
        dist = np.sqrt(dx * dx + dy * dy)

        glare_layer = np.zeros_like(combined)

        if variation == 'Golden Hour':
            # --- GOLDEN HOUR (image 2): soft warm golden glow, subtle horizontal flare ---
            haze_r = diag * 0.7 * size
            haze_ell = np.sqrt((dx / (haze_r * 1.3)) ** 2 + (dy / (haze_r * 0.8)) ** 2)
            haze = np.clip(1.0 - haze_ell, 0, 1) ** 2.5
            haze_color = np.array([220, 160, 80], dtype=np.float32)
            glare_layer += haze[..., np.newaxis] * haze_color * (0.55 * intensity)

            glow_r = diag * 0.28 * size
            glow_ell = np.sqrt((dx / (glow_r * 1.05)) ** 2 + (dy / (glow_r * 0.95)) ** 2)
            glow = np.clip(1.0 - glow_ell, 0, 1) ** 2.0
            glow_color = np.array([255, 200, 120], dtype=np.float32)
            glare_layer += glow[..., np.newaxis] * glow_color * (0.6 * intensity)

            angle = np.arctan2(dy, dx)
            n_rays = 12
            ray_layer = np.zeros((h, w), dtype=np.float32)
            for i in range(n_rays):
                ray_angle = (2.0 * np.pi * i / n_rays) + t * 0.2
                ang_diff = np.abs(np.arctan2(np.sin(angle - ray_angle), np.cos(angle - ray_angle)))
                ray_w = 0.04 + 0.02 * np.sin(t * 0.3 + i * 1.3)
                spoke = np.clip(1.0 - ang_diff / ray_w, 0, 1) ** 1.5
                falloff = np.clip(1.0 - dist / (diag * 0.55 * size), 0, 1) ** 1.0
                ray_layer += spoke * falloff * (0.5 + 0.5 * np.sin(t * 0.3 + i * 0.7))
            ray_color = np.array([255, 210, 140], dtype=np.float32)
            glare_layer += ray_layer[..., np.newaxis] * ray_color * (0.25 * intensity)

            core_r = diag * 0.06 * size
            pulse = 1.0 + 0.02 * np.sin(t * np.pi * 1.0)
            r_outer = np.sqrt((dx / (core_r * pulse * 2.0)) ** 2 + (dy / (core_r * pulse * 1.8)) ** 2)
            core_outer = np.clip(1.0 - r_outer, 0, 1) ** 1.6
            core_outer_col = np.array([255, 210, 130], dtype=np.float32)
            glare_layer += core_outer[..., np.newaxis] * core_outer_col * (0.7 * intensity)
            r_inner = np.sqrt((dx / (core_r * pulse * 0.9)) ** 2 + (dy / (core_r * pulse * 0.8)) ** 2)
            core_inner = np.clip(1.0 - r_inner, 0, 1) ** 2.2
            core_inner_col = np.array([255, 245, 220], dtype=np.float32)
            glare_layer += core_inner[..., np.newaxis] * core_inner_col * (0.85 * intensity)

            flare_y = sun_y
            flare_dy = np.abs(yy - flare_y)
            flare_width = max(h * 0.008 * size, 2)
            flare_line = np.clip(1.0 - flare_dy / flare_width, 0, 1) ** 2.0
            flare_falloff = np.clip(1.0 - np.abs(xx - sun_x) / (w * 0.8), 0, 1) ** 1.5
            flare_layer = flare_line * flare_falloff
            flare_color = np.array([255, 220, 150], dtype=np.float32)
            glare_layer += flare_layer[..., np.newaxis] * flare_color * (0.35 * intensity)

            blur_k = max(3, int(min(h, w) * 0.025)) | 1
            glare_layer = cv2.GaussianBlur(glare_layer, (blur_k, blur_k), 0)

        elif variation == 'Natural':
            # --- NATURAL: bright white midday sun with white rays & circle bokeh spots ---
            # Cool white ambient haze
            haze_r = diag * 0.55 * size
            haze_ell = np.sqrt((dx / (haze_r * 1.15)) ** 2 + (dy / (haze_r * 0.85)) ** 2)
            haze = np.clip(1.0 - haze_ell, 0, 1) ** 2.4
            haze_color = np.array([200, 200, 210], dtype=np.float32)
            glare_layer += haze[..., np.newaxis] * haze_color * (0.40 * intensity)

            # White outer glow
            glow_r = diag * 0.25 * size
            glow_ell = np.sqrt((dx / (glow_r * 1.05)) ** 2 + (dy / (glow_r * 0.95)) ** 2)
            glow = np.clip(1.0 - glow_ell, 0, 1) ** 2.0
            glow_color = np.array([255, 255, 255], dtype=np.float32)
            glare_layer += glow[..., np.newaxis] * glow_color * (0.50 * intensity)

            # Crisp white radiating rays — many, thin, bright
            angle = np.arctan2(dy, dx)
            n_rays = 24
            ray_layer = np.zeros((h, w), dtype=np.float32)
            for i in range(n_rays):
                ray_angle = (2.0 * np.pi * i / n_rays) + t * 0.15
                ang_diff = np.abs(np.arctan2(np.sin(angle - ray_angle), np.cos(angle - ray_angle)))
                ray_w = 0.012 + 0.008 * np.sin(t * 0.5 + i * 0.9)
                spoke = np.clip(1.0 - ang_diff / ray_w, 0, 1) ** 2.5
                falloff = np.clip(1.0 - dist / (diag * 0.6 * size), 0, 1) ** 0.7
                ray_layer += spoke * falloff * (0.5 + 0.5 * np.sin(t * 0.4 + i * 1.1))
            ray_color = np.array([255, 255, 255], dtype=np.float32)
            glare_layer += ray_layer[..., np.newaxis] * ray_color * (0.45 * intensity)

            # Bright white sun core — tight, intense
            core_r = diag * 0.045 * size
            pulse = 1.0 + 0.02 * np.sin(t * np.pi * 1.2)
            r_outer = np.sqrt((dx / (core_r * pulse * 1.6)) ** 2 + (dy / (core_r * pulse * 1.5)) ** 2)
            core_outer = np.clip(1.0 - r_outer, 0, 1) ** 2.0
            core_outer_col = np.array([255, 255, 255], dtype=np.float32)
            glare_layer += core_outer[..., np.newaxis] * core_outer_col * (0.85 * intensity)
            r_inner = np.sqrt((dx / (core_r * pulse * 0.7)) ** 2 + (dy / (core_r * pulse * 0.65)) ** 2)
            core_inner = np.clip(1.0 - r_inner, 0, 1) ** 3.0
            core_inner_col = np.array([255, 255, 255], dtype=np.float32)
            glare_layer += core_inner[..., np.newaxis] * core_inner_col * (1.0 * intensity)

            # Circle bokeh spots along light axis — round, white-to-warm, varied sizes
            axis_dx = opp_x - sun_x
            axis_dy = opp_y - sun_y
            axis_len = max(np.sqrt(axis_dx ** 2 + axis_dy ** 2), 1e-3)

            circle_bokeh = [
                (0.22, 0.030, (220, 230, 255), 0.25),
                (0.38, 0.020, (255, 255, 255), 0.18),
                (0.50, 0.045, (200, 220, 255), 0.35),
                (0.65, 0.025, (255, 255, 255), 0.20),
                (0.78, 0.038, (210, 225, 255), 0.28),
            ]

            circle_mask = np.zeros((h, w), dtype=np.float32)
            circle_colour = np.zeros((h, w, 3), dtype=np.float32)

            for i, (t_pos, r_frac, color, alpha_base) in enumerate(circle_bokeh):
                cx = sun_x + axis_dx * t_pos + 1.5 * np.sin(t * 0.3 + i * 0.7)
                cy = sun_y + axis_dy * t_pos + 1.2 * np.cos(t * 0.25 + i * 0.5)
                radius = max(diag * r_frac * size, 3)

                d_dist = np.sqrt((cx - sun_x) ** 2 + (cy - sun_y) ** 2)
                fade = np.clip(1.0 - d_dist / (diag * 1.0), 0.3, 1.0)
                alpha = np.clip(alpha_base * fade * intensity, 0.0, 1.0)

                cv2.circle(circle_mask, (int(cx), int(cy)), int(radius), alpha, -1, lineType=cv2.LINE_AA)
                cv2.circle(circle_colour, (int(cx), int(cy)), int(radius), color, -1, lineType=cv2.LINE_AA)

            cblur = max(int(min(h, w) * 0.010) | 1, 3)
            circle_mask = cv2.GaussianBlur(circle_mask, (cblur, cblur), 0)
            circle_colour = cv2.GaussianBlur(circle_colour, (cblur, cblur), 0)
            cmask3 = circle_mask[..., np.newaxis]
            glare_layer += circle_colour * cmask3

            blur_k = max(3, int(min(h, w) * 0.018)) | 1
            glare_layer = cv2.GaussianBlur(glare_layer, (blur_k, blur_k), 0)

        elif variation == 'Sky Burst':
            # --- SKY BURST: natural long-ray sunburst with creamish yellow tones ---
            haze_r = diag * 0.8 * size
            haze_ell = np.sqrt((dx / (haze_r * 1.1)) ** 2 + (dy / (haze_r * 0.9)) ** 2)
            haze = np.clip(1.0 - haze_ell, 0, 1) ** 2.6
            haze_color = np.array([255, 235, 180], dtype=np.float32)
            glare_layer += haze[..., np.newaxis] * haze_color * (0.45 * intensity)

            glow_r = diag * 0.18 * size
            glow_ell = np.sqrt((dx / (glow_r * 1.0)) ** 2 + (dy / (glow_r * 1.0)) ** 2)
            glow = np.clip(1.0 - glow_ell, 0, 1) ** 2.0
            glow_color = np.array([255, 240, 200], dtype=np.float32)
            glare_layer += glow[..., np.newaxis] * glow_color * (0.65 * intensity)

            angle = np.arctan2(dy, dx)
            n_rays = 16
            ray_layer = np.zeros((h, w), dtype=np.float32)
            for i in range(n_rays):
                ray_angle = (2.0 * np.pi * i / n_rays) + t * 0.25
                ang_diff = np.abs(np.arctan2(np.sin(angle - ray_angle), np.cos(angle - ray_angle)))
                ray_w = 0.008 + 0.005 * np.sin(t * 0.4 + i * 1.1)
                spoke = np.clip(1.0 - ang_diff / ray_w, 0, 1) ** 2.8
                falloff = np.clip(1.0 - dist / (diag * 0.85 * size), 0, 1) ** 0.6
                ray_layer += spoke * falloff * (0.5 + 0.5 * np.sin(t * 0.35 + i * 0.8))
            ray_color = np.array([255, 225, 150], dtype=np.float32)
            glare_layer += ray_layer[..., np.newaxis] * ray_color * (0.55 * intensity)

            core_r = diag * 0.05 * size
            pulse = 1.0 + 0.015 * np.sin(t * np.pi * 1.0)
            r_outer = np.sqrt((dx / (core_r * pulse * 1.5)) ** 2 + (dy / (core_r * pulse * 1.5)) ** 2)
            core_outer = np.clip(1.0 - r_outer, 0, 1) ** 2.0
            core_outer_col = np.array([255, 245, 200], dtype=np.float32)
            glare_layer += core_outer[..., np.newaxis] * core_outer_col * (0.85 * intensity)
            r_inner = np.sqrt((dx / (core_r * pulse * 0.6)) ** 2 + (dy / (core_r * pulse * 0.6)) ** 2)
            core_inner = np.clip(1.0 - r_inner, 0, 1) ** 3.0
            core_inner_col = np.array([255, 255, 240], dtype=np.float32)
            glare_layer += core_inner[..., np.newaxis] * core_inner_col * (1.0 * intensity)

            blur_k = max(3, int(min(h, w) * 0.015)) | 1
            glare_layer = cv2.GaussianBlur(glare_layer, (blur_k, blur_k), 0)

        else:
            # --- CINEMATIC (image 1): dramatic rays, orange hex bokeh, teal accents ---
            glow_r = diag * 0.35 * size
            glow_elliptical = np.sqrt((dx / (glow_r * 1.1)) ** 2 + (dy / (glow_r * 0.9)) ** 2)
            glow = np.clip(1.0 - glow_elliptical, 0, 1) ** 2.2
            glow_color = np.array([255, 145, 35], dtype=np.float32)
            glare_layer += glow[..., np.newaxis] * glow_color * (0.7 * intensity)

            haze_r = diag * 0.6 * size
            haze_elliptical = np.sqrt((dx / (haze_r * 1.2)) ** 2 + (dy / (haze_r * 0.85)) ** 2)
            haze = np.clip(1.0 - haze_elliptical, 0, 1) ** 2.8
            haze_color = np.array([180, 70, 15], dtype=np.float32)
            glare_layer += haze[..., np.newaxis] * haze_color * (0.45 * intensity)

            angle = np.arctan2(dy, dx)
            n_rays = 18
            ray_layer_r = np.zeros((h, w), dtype=np.float32)
            for i in range(n_rays):
                ray_angle = (2.0 * np.pi * i / n_rays) + t * 0.4
                ang_diff = np.abs(np.arctan2(np.sin(angle - ray_angle), np.cos(angle - ray_angle)))
                ray_w = 0.02 + 0.015 * np.sin(t * 0.7 + i * 1.1)
                spoke = np.clip(1.0 - ang_diff / ray_w, 0, 1) ** 2.0
                falloff = np.clip(1.0 - dist / (diag * 0.5 * size), 0, 1) ** 0.8
                ray_layer_r += spoke * falloff * (0.4 + 0.6 * np.sin(t * 0.5 + i * 0.9))
            ray_color = np.array([255, 200, 110], dtype=np.float32)
            glare_layer += ray_layer_r[..., np.newaxis] * ray_color * (0.35 * intensity)

            core_r = diag * 0.055 * size
            pulse = 1.0 + 0.03 * np.sin(t * np.pi * 1.5)
            r_outer = np.sqrt((dx / (core_r * pulse * 1.8)) ** 2 + (dy / (core_r * pulse * 1.6)) ** 2)
            core_outer = np.clip(1.0 - r_outer, 0, 1) ** 1.8
            core_outer_col = np.array([255, 180, 60], dtype=np.float32)
            glare_layer += core_outer[..., np.newaxis] * core_outer_col * (0.8 * intensity)
            r_inner = np.sqrt((dx / (core_r * pulse)) ** 2 + (dy / (core_r * pulse * 0.9)) ** 2)
            core_inner = np.clip(1.0 - r_inner, 0, 1) ** 2.5
            core_inner_col = np.array([255, 240, 210], dtype=np.float32)
            glare_layer += core_inner[..., np.newaxis] * core_inner_col * (0.9 * intensity)

            axis_dx = opp_x - sun_x
            axis_dy = opp_y - sun_y
            axis_len = max(np.sqrt(axis_dx ** 2 + axis_dy ** 2), 1e-3)

            bokeh = [
                (0.20, 0.035, (255, 200,  90), 0.30),
                (0.30, 0.060, (255, 140,  50), 0.40),
                (0.38, 0.030, (255, 220, 130), 0.28),
                (0.46, 0.075, (230,  90,  30), 0.45),
                (0.54, 0.025, (255, 170,  70), 0.25),
                (0.62, 0.065, (255, 130,  45), 0.42),
                (0.70, 0.040, (255, 200, 110), 0.32),
                (0.78, 0.080, (240, 100,  35), 0.50),
                (0.86, 0.045, (255, 180,  90), 0.35),
            ]

            hex_mask = np.zeros((h, w), dtype=np.float32)
            hex_colour = np.zeros((h, w, 3), dtype=np.float32)

            for i, (t_pos, r_frac, color, alpha_base) in enumerate(bokeh):
                cx = sun_x + axis_dx * t_pos + 2.0 * np.sin(t * 0.4 + i * 0.8)
                cy = sun_y + axis_dy * t_pos + 1.5 * np.cos(t * 0.35 + i * 0.6)
                radius = max(diag * r_frac * size, 4)
                rot = t * 1.0 + i * 0.35

                pts = []
                for v in range(6):
                    a = np.radians(60 * v + rot)
                    pts.append([int(cx + radius * np.cos(a)),
                                int(cy + radius * np.sin(a))])
                pts = np.array(pts, dtype=np.int32)

                d = np.sqrt((cx - sun_x) ** 2 + (cy - sun_y) ** 2)
                fade = np.clip(1.0 - d / (diag * 1.1), 0.3, 1.0)
                alpha = np.clip(alpha_base * fade * intensity, 0.0, 1.0)

                cv2.fillPoly(hex_mask, [pts], alpha, lineType=cv2.LINE_AA)
                cv2.fillPoly(hex_colour, [pts], color, lineType=cv2.LINE_AA)

            blur_r = max(int(min(h, w) * 0.008) | 1, 3)
            hex_mask = cv2.GaussianBlur(hex_mask, (blur_r, blur_r), 0)
            hex_colour = cv2.GaussianBlur(hex_colour, (blur_r, blur_r), 0)
            mask3 = hex_mask[..., np.newaxis]
            glare_layer += hex_colour * mask3

            flare_y = sun_y
            flare_dy = np.abs(yy - flare_y)
            flare_width = max(h * 0.003 * size, 1)
            flare_line = np.clip(1.0 - flare_dy / flare_width, 0, 1) ** 3.0
            flare_falloff = np.clip(1.0 - np.abs(xx - sun_x) / (w * 0.9), 0, 1) ** 2.0
            flare_layer = flare_line * flare_falloff
            flare_color = np.array([255, 180, 80], dtype=np.float32)
            glare_layer += flare_layer[..., np.newaxis] * flare_color * (0.45 * intensity)

            teal_x, teal_y = opp_x * 0.4 + sun_x * 0.6, opp_y * 0.3 + sun_y * 0.7
            teal_dx = xx - teal_x
            teal_dy = yy - teal_y
            teal_r = diag * 0.18 * size
            teal_ell = np.sqrt((teal_dx / (teal_r * 1.4)) ** 2 + (teal_dy / (teal_r * 0.7)) ** 2)
            teal = np.clip(1.0 - teal_ell, 0, 1) ** 2.0
            teal_color = np.array([60, 200, 210], dtype=np.float32)
            glare_layer += teal[..., np.newaxis] * teal_color * (0.20 * intensity)

            blur_k = max(3, int(min(h, w) * 0.020)) | 1
            glare_layer = cv2.GaussianBlur(glare_layer, (blur_k, blur_k), 0)

        # Screen blend onto the frame — adds light, never crushes blacks
        glare_norm = glare_layer / 255.0
        base_norm = combined / 255.0
        screen = 1.0 - (1.0 - base_norm) * (1.0 - glare_norm)
        combined = screen * 255.0

        return np.clip(combined, 0, 255).astype(np.uint8)

    def apply_sun_glare_effect(self, frame, item, t):
        if not item.get('effect_sun_glare_enabled', False):
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame
        variation = item.get('sun_glare_variation', 'Cinematic')
        position = item.get('sun_glare_position', 'Top Left')
        intensity = item.get('sun_glare_intensity', 1.0)
        size = item.get('sun_glare_size', 1.0)
        speed = item.get('sun_glare_speed', 0.3)
        return self._create_sun_glare_effect(frame, variation=variation, position=position,
                                              intensity=intensity, size=size, speed=speed,
                                              time_factor=t)

    # ══════════════════════════════════════════════════════════════════
    #  X FLARE EFFECT  (Anamorphic cross / X-shaped lens flare)
    # ══════════════════════════════════════════════════════════════════

    _X_FLARE_POSITIONS = {
        'top left':     (0.15, 0.15),
        'top right':    (0.85, 0.15),
        'bottom left':  (0.15, 0.85),
        'bottom right': (0.85, 0.85),
        'center':       (0.50, 0.50),
    }

    _X_FLARE_COLORS = {
        'Blue White':   {'ray': (200, 220, 255), 'core': (255, 255, 255), 'glow': (140, 180, 255), 'fringe': (180, 140, 255)},
        'Purple Haze':  {'ray': (200, 160, 255), 'core': (240, 220, 255), 'glow': (180, 100, 255), 'fringe': (255, 120, 200)},
        'Golden Cross': {'ray': (255, 230, 160), 'core': (255, 250, 230), 'glow': (255, 200, 100), 'fringe': (255, 180, 80)},
        'Ice White':    {'ray': (230, 240, 255), 'core': (255, 255, 255), 'glow': (200, 220, 255), 'fringe': (160, 200, 240)},
    }

    def _create_x_flare_effect(self, frame, variation='Blue White', position='Center',
                               intensity=1.0, size=1.0, speed=0.3, time_factor=0.0):
        h, w = frame.shape[:2]
        combined = frame.astype(np.float32)
        diag = float(np.hypot(w, h))
        t = time_factor * speed

        # Camera flash flicker — rapid irregular brightness pulses
        flicker = (0.7
                   + 0.30 * np.sin(t * 18.0)
                   + 0.15 * np.sin(t * 31.0)
                   + 0.10 * np.sin(t * 47.0)
                   + 0.08 * np.sin(t * 73.0))
        flicker = max(flicker, 0.15)
        intensity = intensity * flicker

        key = str(position).strip().lower().replace('_', ' ')
        fx_f, fy_f = self._X_FLARE_POSITIONS.get(key, (0.50, 0.50))
        cx, cy = fx_f * w, fy_f * h

        colors = self._X_FLARE_COLORS.get(variation, self._X_FLARE_COLORS['Blue White'])
        ray_col = np.array(colors['ray'], dtype=np.float32)
        core_col = np.array(colors['core'], dtype=np.float32)
        glow_col = np.array(colors['glow'], dtype=np.float32)
        fringe_col = np.array(colors['fringe'], dtype=np.float32)

        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        dx = xx - cx
        dy = yy - cy
        dist = np.sqrt(dx * dx + dy * dy)

        glare_layer = np.zeros_like(combined)
        angle = np.arctan2(dy, dx)

        # --- 4 glowing X rays — bright near source, fading to tips ---
        arm_angles = [np.pi / 4, 3 * np.pi / 4, 5 * np.pi / 4, 7 * np.pi / 4]
        ray_len = diag * 0.42 * size
        ray_half_w = 0.022 * size
        ray_glow_w = 0.06 * size

        ray_layer = np.zeros((h, w), dtype=np.float32)
        glow_layer = np.zeros((h, w), dtype=np.float32)

        for arm_a in arm_angles:
            ang_diff = np.abs(np.arctan2(np.sin(angle - arm_a), np.cos(angle - arm_a)))
            ray_core = np.clip(1.0 - ang_diff / ray_half_w, 0, 1) ** 1.5
            ray_soft = np.clip(1.0 - ang_diff / ray_glow_w, 0, 1) ** 2.0
            radial_fade = np.clip(1.0 - dist / ray_len, 0, 1) ** 0.8
            ray_layer = np.maximum(ray_layer, ray_core * radial_fade)
            glow_layer = np.maximum(glow_layer, ray_soft * radial_fade)

        glare_layer += glow_layer[..., np.newaxis] * glow_col * (0.35 * intensity)
        glare_layer += ray_layer[..., np.newaxis] * ray_col * (0.75 * intensity)

        # --- Purple fringing on ray edges ---
        fringe_layer = np.zeros((h, w), dtype=np.float32)
        for arm_a in arm_angles:
            ang_diff = np.abs(np.arctan2(np.sin(angle - arm_a), np.cos(angle - arm_a)))
            fringe_mask = np.clip(1.0 - ang_diff / ray_glow_w, 0, 1) ** 2.0
            fringe_inner = np.clip(1.0 - ang_diff / ray_half_w, 0, 1) ** 1.5
            fringe_band = np.clip(fringe_mask - fringe_inner, 0, 1)
            radial_fade = np.clip(1.0 - dist / ray_len, 0, 1) ** 0.8
            fringe_layer = np.maximum(fringe_layer, fringe_band * radial_fade)
        glare_layer += fringe_layer[..., np.newaxis] * fringe_col * (0.50 * intensity)

        # --- Bright glowing center source ---
        core_r = diag * 0.022 * size
        r_wide = np.sqrt((dx / (core_r * 4.0)) ** 2 + (dy / (core_r * 4.0)) ** 2)
        core_wide = np.clip(1.0 - r_wide, 0, 1) ** 1.4
        glare_layer += core_wide[..., np.newaxis] * glow_col * (0.6 * intensity)
        r_mid = np.sqrt((dx / (core_r * 2.0)) ** 2 + (dy / (core_r * 2.0)) ** 2)
        core_mid = np.clip(1.0 - r_mid, 0, 1) ** 1.8
        glare_layer += core_mid[..., np.newaxis] * core_col * (0.85 * intensity)
        r_inner = np.sqrt((dx / core_r) ** 2 + (dy / core_r) ** 2)
        core_inner = np.clip(1.0 - r_inner, 0, 1) ** 2.2
        glare_layer += core_inner[..., np.newaxis] * core_col * (1.0 * intensity)

        blur_k = max(3, int(min(h, w) * 0.010)) | 1
        glare_layer = cv2.GaussianBlur(glare_layer, (blur_k, blur_k), 0)

        # Screen blend
        glare_norm = glare_layer / 255.0
        base_norm = combined / 255.0
        screen = 1.0 - (1.0 - base_norm) * (1.0 - glare_norm)
        combined = screen * 255.0

        return np.clip(combined, 0, 255).astype(np.uint8)

    def apply_x_flare_effect(self, frame, item, t):
        if not item.get('effect_x_flare_enabled', False):
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame
        variation = item.get('x_flare_variation', 'Blue White')
        position = item.get('x_flare_position', 'Center')
        intensity = item.get('x_flare_intensity', 1.0)
        size = item.get('x_flare_size', 1.0)
        speed = item.get('x_flare_speed', 0.3)
        return self._create_x_flare_effect(frame, variation=variation, position=position,
                                           intensity=intensity, size=size, speed=speed,
                                           time_factor=t)

    # ══════════════════════════════════════════════════════════════════
    #  LIGHT FLASH EFFECT (Multiple Random Camera Flash X-Crosses)
    # ══════════════════════════════════════════════════════════════════

    _LIGHT_FLASH_POSITIONS = {
        'top left':     (0.18, 0.18),
        'top right':    (0.82, 0.18),
        'bottom left':  (0.18, 0.82),
        'bottom right': (0.82, 0.82),
        'center':       (0.50, 0.50),
        'diagonal tl→br': 'diagonal_tl_br',
        'diagonal bl→tr': 'diagonal_bl_tr',
        'full image':   'full_image',
    }

    _LIGHT_FLASH_COLORS = {
        'White Flash':   {'ray': (220, 235, 255), 'core': (255, 255, 255), 'glow': (140, 170, 255), 'fringe': (160, 120, 255)},
        'Warm Paparazzi':{'ray': (255, 235, 200), 'core': (255, 250, 240), 'glow': (255, 180, 100), 'fringe': (255, 140, 80)},
        'Cool Studio':   {'ray': (200, 230, 255), 'core': (255, 255, 255), 'glow': (120, 170, 255), 'fringe': (100, 140, 240)},
        'Neon Burst':    {'ray': (160, 255, 240), 'core': (255, 255, 255), 'glow': (80, 255, 200), 'fringe': (60, 220, 180)},
        'Golden Gala':   {'ray': (255, 230, 150), 'core': (255, 250, 220), 'glow': (255, 200, 80), 'fringe': (255, 170, 50)},
    }

    def _light_flash_pseudo_random(self, seed):
        """Deterministic pseudo-random float in [0, 1) from an integer seed."""
        x = np.sin(seed * 127.1 + 311.7) * 43758.5453
        return x - np.floor(x)

    def _create_light_flash_effect(self, frame, variation='White Flash', position='Center',
                                    intensity=1.0, size=1.0, speed=1.0, density=6,
                                    time_factor=0.0):
        """Multiple random camera-flash X-crosses that pop in and out within an area."""
        h, w = frame.shape[:2]
        combined = frame.astype(np.float32)
        diag = float(np.hypot(w, h))
        t = time_factor * speed

        key = str(position).strip().lower().replace('_', ' ')
        pos_val = self._LIGHT_FLASH_POSITIONS.get(key, (0.50, 0.50))

        is_diagonal_tl_br = (pos_val == 'diagonal_tl_br')
        is_diagonal_bl_tr = (pos_val == 'diagonal_bl_tr')
        is_full_image = (pos_val == 'full_image')

        if is_full_image:
            area_cx, area_cy = 0.5 * w, 0.5 * h
        elif is_diagonal_tl_br or is_diagonal_bl_tr:
            area_cx, area_cy = 0.5 * w, 0.5 * h
        else:
            fx_f, fy_f = pos_val
            area_cx, area_cy = fx_f * w, fy_f * h

        colors = self._LIGHT_FLASH_COLORS.get(variation, self._LIGHT_FLASH_COLORS['White Flash'])
        ray_col = np.array(colors['ray'], dtype=np.float32)
        core_col = np.array(colors['core'], dtype=np.float32)
        glow_col = np.array(colors['glow'], dtype=np.float32)
        fringe_col = np.array(colors['fringe'], dtype=np.float32)

        area_r = diag * 0.18 * size
        n_flashes = max(3, min(20, int(density * 1.8)))
        CYCLE_LEN = 3.0 / max(0.3, speed)

        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        glare_layer = np.zeros((h, w, 3), dtype=np.float32)

        arm_cos = np.array([np.cos(a) for a in [np.pi/4, 3*np.pi/4, 5*np.pi/4, 7*np.pi/4]], dtype=np.float32)
        arm_sin = np.array([np.sin(a) for a in [np.pi/4, 3*np.pi/4, 5*np.pi/4, 7*np.pi/4]], dtype=np.float32)

        tmp_dx = np.empty((h, w), dtype=np.float32)
        tmp_dy = np.empty((h, w), dtype=np.float32)
        tmp_dist = np.empty((h, w), dtype=np.float32)
        tmp_angle = np.empty((h, w), dtype=np.float32)
        tmp_ray = np.empty((h, w), dtype=np.float32)

        for i in range(n_flashes):
            r1 = self._light_flash_pseudo_random(i * 3 + 1)
            r2 = self._light_flash_pseudo_random(i * 3 + 2)
            r3 = self._light_flash_pseudo_random(i * 3 + 3)
            r4 = self._light_flash_pseudo_random(i * 3 + 4)
            r5 = self._light_flash_pseudo_random(i * 3 + 5)

            if is_full_image:
                sx = r1 * w
                sy = r2 * h
            elif is_diagonal_tl_br:
                frac = r1
                sx = frac * w
                sy = frac * h
                sx += (r2 - 0.5) * diag * 0.08 * size
                sy += (r2 - 0.5) * diag * 0.08 * size
            elif is_diagonal_bl_tr:
                frac = r1
                sx = frac * w
                sy = (1.0 - frac) * h
                sx += (r2 - 0.5) * diag * 0.08 * size
                sy += (r2 - 0.5) * diag * 0.08 * size
            else:
                theta = r1 * 6.2831853
                rad = np.sqrt(r2) * area_r
                sx = area_cx + rad * np.cos(theta)
                sy = area_cy + rad * np.sin(theta)

            local_t = (t + r3 * CYCLE_LEN) % CYCLE_LEN
            life = local_t / CYCLE_LEN

            if life < 0.08:
                bright_env = life / 0.08
            elif life < 0.25:
                bright_env = 1.0
            elif life < 0.40:
                bright_env = 1.0 - (life - 0.25) / 0.15
            else:
                continue

            flicker = (0.7 + 0.30 * np.sin(local_t * 40.0 + r4 * 10.0)
                       + 0.15 * np.sin(local_t * 67.0 + r5 * 10.0))
            brightness = bright_env * flicker * intensity
            if brightness < 0.02:
                continue

            flash_size = size * (0.5 + r4)

            np.subtract(xx, sx, out=tmp_dx)
            np.subtract(yy, sy, out=tmp_dy)
            np.sqrt(tmp_dx * tmp_dx + tmp_dy * tmp_dy, out=tmp_dist)
            np.arctan2(tmp_dy, tmp_dx, out=tmp_angle)

            ray_len = diag * 0.55 * max(flash_size, 0.8)
            ray_half_w = 0.032 * max(flash_size, 0.7)
            ray_glow_w = 0.065 * max(flash_size, 0.7)

            np.maximum(tmp_dist, 0.001, out=tmp_dist)
            radial = np.clip(1.0 - tmp_dist / ray_len, 0, 1)
            np.power(radial, 0.7, out=radial)

            for ai in range(4):
                ad = np.abs(np.arctan2(np.sin(tmp_angle - arm_cos[ai]), np.cos(tmp_angle - arm_cos[ai])))
                np.clip(1.0 - ad / ray_half_w, 0, 1, out=tmp_ray)
                np.power(tmp_ray, 1.8, out=tmp_ray)
                np.multiply(tmp_ray, radial, out=tmp_ray)
                glare_layer[..., 0] += tmp_ray * ray_col[0] * (1.0 * brightness)
                glare_layer[..., 1] += tmp_ray * ray_col[1] * (1.0 * brightness)
                glare_layer[..., 2] += tmp_ray * ray_col[2] * (1.0 * brightness)

                np.clip(1.0 - ad / ray_glow_w, 0, 1, out=tmp_ray)
                np.power(tmp_ray, 2.2, out=tmp_ray)
                np.multiply(tmp_ray, radial, out=tmp_ray)
                glare_layer[..., 0] += tmp_ray * glow_col[0] * (0.30 * brightness)
                glare_layer[..., 1] += tmp_ray * glow_col[1] * (0.30 * brightness)
                glare_layer[..., 2] += tmp_ray * glow_col[2] * (0.30 * brightness)

            core_r = diag * 0.016 * flash_size
            r_inv = 1.0 / max(core_r, 0.1)
            r_wide_inv = 1.0 / max(core_r * 5.0, 0.1)
            core_wide = np.clip(1.0 - tmp_dist * r_wide_inv, 0, 1)
            np.power(core_wide, 1.2, out=core_wide)
            core_mid = np.clip(1.0 - tmp_dist * (r_inv * 0.4), 0, 1)
            np.power(core_mid, 1.8, out=core_mid)
            core_inner = np.clip(1.0 - tmp_dist * r_inv, 0, 1)
            np.power(core_inner, 2.5, out=core_inner)

            glare_layer[..., 0] += core_wide * glow_col[0] * (0.50 * brightness)
            glare_layer[..., 1] += core_wide * glow_col[1] * (0.50 * brightness)
            glare_layer[..., 2] += core_wide * glow_col[2] * (0.50 * brightness)
            glare_layer[..., 0] += core_mid * core_col[0] * (0.85 * brightness)
            glare_layer[..., 1] += core_mid * core_col[1] * (0.85 * brightness)
            glare_layer[..., 2] += core_mid * core_col[2] * (0.85 * brightness)
            glare_layer[..., 0] += core_inner * core_col[0] * brightness
            glare_layer[..., 1] += core_inner * core_col[1] * brightness
            glare_layer[..., 2] += core_inner * core_col[2] * brightness

        ambient = (0.6 + 0.4 * np.sin(t * 8.0) * np.sin(t * 13.0)) * intensity
        if is_full_image:
            ambient_r = diag * 0.6
        elif is_diagonal_tl_br or is_diagonal_bl_tr:
            ambient_r = diag * 0.4
        else:
            ambient_r = area_r * 1.5
        np.subtract(xx, area_cx, out=tmp_dx)
        np.subtract(yy, area_cy, out=tmp_dy)
        np.sqrt(tmp_dx * tmp_dx + tmp_dy * tmp_dy, out=tmp_dist)
        ambient_mask = np.clip(1.0 - tmp_dist / ambient_r, 0, 1)
        np.power(ambient_mask, 2.0, out=ambient_mask)
        glare_layer[..., 0] += ambient_mask * glow_col[0] * (0.06 * ambient)
        glare_layer[..., 1] += ambient_mask * glow_col[1] * (0.06 * ambient)
        glare_layer[..., 2] += ambient_mask * glow_col[2] * (0.06 * ambient)

        blur_k = max(3, int(min(h, w) * 0.010)) | 1
        glare_layer = cv2.GaussianBlur(glare_layer, (blur_k, blur_k), 0)

        glare_norm = glare_layer / 255.0
        base_norm = combined / 255.0
        screen = 1.0 - (1.0 - base_norm) * (1.0 - glare_norm)
        combined = screen * 255.0

        return np.clip(combined, 0, 255).astype(np.uint8)

    def apply_light_flash_effect(self, frame, item, t):
        if not item.get('effect_light_flash_enabled', False):
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame
        variation = item.get('light_flash_variation', 'White Flash')
        position = item.get('light_flash_position', 'Center')
        intensity = item.get('light_flash_intensity', 1.0)
        size = item.get('light_flash_size', 1.0)
        speed = item.get('light_flash_speed', 1.0)
        density = item.get('light_flash_density', 6)
        return self._create_light_flash_effect(frame, variation=variation, position=position,
                                               intensity=intensity, size=size, speed=speed,
                                                density=density, time_factor=t)

    # ══════════════════════════════════════════════════════════════════
    #  CANOPY EFFECT  (fog banks + volumetric god rays from above/behind)
    # ══════════════════════════════════════════════════════════════════

    _CANOPY_LIGHT_DIRS = {
        'top left':     (0.20, 0.05),
        'top right':    (0.80, 0.05),
        'top center':   (0.50, 0.0),
        'behind':       (0.50, 0.30),
        'side left':    (0.05, 0.45),
        'side right':   (0.95, 0.45),
    }

    def _create_canopy_effect(self, frame, light_dir='Top Left', light_style='Soft Atmosphere',
                              fog_density=0.7, fog_height=0.5, ray_intensity=1.0, ray_width=1.0,
                              warmth=0.7, shimmer=0.3, time_factor=0.0,
                              person_mask=None, show_light_source=True):
        h, w = frame.shape[:2]
        combined = frame.astype(np.float32)

        key = str(light_dir).strip().lower().replace('_', ' ')
        lx, ly = self._CANOPY_LIGHT_DIRS.get(key, (0.20, 0.05))
        src_x, src_y = lx * w, ly * h

        t = time_factor
        diag = float(np.hypot(w, h))

        flicker = 1.0
        if shimmer > 0:
            flicker = (1.0
                       + shimmer * 0.08 * np.sin(t * 3.7)
                       + shimmer * 0.05 * np.sin(t * 7.1)
                       + shimmer * 0.03 * np.sin(t * 13.3))

        # ── WARM LIGHT COLOR (shifts with warmth slider) ──
        warm_r = min(255, int(220 + warmth * 35))
        warm_g = min(255, int(200 + warmth * 40))
        warm_b = min(255, int(180 + warmth * 30))
        ray_color = np.array([warm_r, warm_g, warm_b], dtype=np.float32)

        # ── COORDINATE GRID ──
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        dx = xx - src_x
        dy = yy - src_y
        dist = np.sqrt(dx**2 + dy**2)

        # ════════════════════════════════════════════════════════════════
        #  LAYERED FOG — multiple depth bands like mountain valleys
        # ════════════════════════════════════════════════════════════════
        fog_y = yy / h

        # Deep valley fog (bottom third, dense)
        fog_deep = np.clip((fog_y - (1.0 - fog_height * 0.5)) / (fog_height * 0.5), 0, 1) ** 1.8

        # Mid-level mist (middle band, wispy)
        mid_band = np.clip(1.0 - np.abs(fog_y - 0.55) / 0.20, 0, 1)
        fog_mid = mid_band ** 2.0

        # High-altitude haze (thin, near top)
        high_band = np.clip(1.0 - np.abs(fog_y - 0.25) / 0.15, 0, 1)
        fog_high = high_band ** 2.5 * 0.4

        # Horizontal wisps (sinusoidal variation across width)
        wisp1 = 0.5 + 0.5 * np.sin(xx * 2 * np.pi / max(w * 0.35, 1.0) + 1.2)
        wisp2 = 0.5 + 0.5 * np.sin(xx * 2 * np.pi / max(w * 0.55, 1.0) + 3.8)
        wisp3 = 0.5 + 0.5 * np.sin(xx * 2 * np.pi / max(w * 0.2, 1.0) - 0.5)

        fog_mask = (fog_deep * (0.65 + 0.35 * wisp1) +
                    fog_mid * (0.5 + 0.5 * wisp2) * 0.55 +
                    fog_high * (0.7 + 0.3 * wisp3))

        # Attenuate fog near the light source (light burns through)
        light_dist_norm = np.clip(dist / diag, 0, 1)
        fog_mask *= np.clip(1.0 - np.exp(-light_dist_norm ** 2 / (2 * 0.25**2)), 0.2, 1.0)

        fog_t = np.clip(fog_mask * fog_density, 0, 1)
        # Color gradient: lighter near light source, darker in shadows
        fog_near = np.array([min(255, warm_r + 10), min(255, warm_g + 5), min(255, warm_b)], dtype=np.float32)
        fog_far = np.array([140, 150, 170], dtype=np.float32)
        fog_proximity = np.clip(1.0 - light_dist_norm * 0.7, 0, 1)
        fog_color = fog_far.reshape(1, 1, 3) * (1.0 - fog_proximity[..., np.newaxis]) + \
                    fog_near.reshape(1, 1, 3) * fog_proximity[..., np.newaxis]
        fog_layer = fog_color * fog_t[..., np.newaxis]
        fog_alpha = np.clip(fog_t * 0.6 * fog_density, 0, 0.6)
        combined = combined * (1.0 - fog_alpha[..., np.newaxis]) + fog_layer * fog_alpha[..., np.newaxis]

        # ════════════════════════════════════════════════════════════════
        #  GOD RAYS — style-dependent ray rendering
        # ════════════════════════════════════════════════════════════════
        is_behind = 'behind' in key
        if is_behind:
            base_angle = np.pi * 0.5
        elif 'left' in key and 'side' not in key:
            base_angle = np.pi * 0.38
        elif 'right' in key and 'side' not in key:
            base_angle = np.pi * 0.62
        elif 'side left' in key:
            base_angle = np.pi * 0.15
        elif 'side right' in key:
            base_angle = np.pi * 0.85
        else:
            base_angle = np.pi * 0.45

        is_forest = (light_style == 'Forest Rays')

        if is_forest:
            num_rays = 12
            spread_total = 2.6 * ray_width
        else:
            num_rays = 14
            spread_total = 1.1 * ray_width

        ray_layer = np.zeros((h, w, 3), dtype=np.float32)
        ray_strength = np.zeros((h, w), dtype=np.float32)
        ray_spread_angles = np.linspace(-spread_total / 2, spread_total / 2, num_rays)

        for i in range(num_rays):
            ray_angle = base_angle + ray_spread_angles[i]
            rdx = np.cos(ray_angle)
            rdy = np.sin(ray_angle)
            cross = dx * rdy - dy * rdx

            if is_forest:
                ray_w_px = (45 + (i % 4) * 20) * ray_width
                ray_falloff = np.exp(-0.5 * (np.abs(cross) / max(ray_w_px, 1.0))**2.0)
                intensity = 1.0 if i % 4 == 0 else (0.6 if i % 4 == 1 else (0.85 if i % 4 == 2 else 0.4))
            else:
                ray_w_px = (20 + i * 6) * ray_width
                ray_falloff = np.exp(-0.5 * (np.abs(cross) / max(ray_w_px, 1.0))**2)
                intensity = [0.6, 1.0, 0.8, 0.5, 0.9, 0.7, 1.0, 0.6, 0.8, 0.7, 1.0, 0.5, 0.9, 0.6][i]

            along = dx * rdx + dy * rdy
            along_clipped = np.clip(along, 0, diag)

            if is_forest:
                dist_fade = np.clip(1.0 / (1.0 + (along_clipped / (diag * 0.40))**1.2), 0, 1)
                fog_absorb = np.clip(1.0 - fog_mask * 0.35, 0.08, 1.0)
            else:
                dist_fade = np.clip(1.0 / (1.0 + along_clipped / (diag * 0.35)), 0, 1)
                fog_absorb = np.clip(1.0 - fog_mask * 0.35, 0.15, 1.0)

            this_ray = ray_falloff * dist_fade * fog_absorb * flicker * intensity
            ray_strength = np.maximum(ray_strength, this_ray)
            if is_forest:
                col_var = ray_color * (0.92 + 0.08 * np.sin(i * 1.7))
            else:
                col_var = ray_color * (0.85 + 0.15 * np.sin(i * 1.7))
            ray_layer += this_ray[..., np.newaxis] * col_var.reshape(1, 1, 3)

        # ── Composite rays onto frame (additive, safe) ──
        ray_strength = np.clip(ray_strength, 0, 1)
        if is_forest:
            ray_alpha = np.clip(ray_strength * ray_intensity * 0.85, 0, 0.95)
        else:
            ray_alpha = np.clip(ray_strength * ray_intensity * 0.55, 0, 0.7)

        ray_rgb = np.clip(ray_layer, 0, 255)
        combined = np.clip(combined + ray_rgb * ray_alpha[..., np.newaxis], 0, 255)

        # ── Core glow (light source — bright hot center like real sun) ──
        if show_light_source:
            if is_forest:
                core_r = diag * 0.06
                core_pow = 2.2
            else:
                core_r = diag * 0.05
                core_pow = 2.5
            core_dist = np.sqrt((dx / max(core_r * 2.0, 1.0))**2 + (dy / max(core_r * 1.4, 1.0))**2)
            core_mask = np.clip(1.0 - core_dist, 0, 1) ** core_pow

            # Bright white-hot center (like real sun), transitioning to warm gold
            hot_center = np.clip(1.0 - core_dist * 0.6, 0, 1) ** 3.0
            hot_color = np.array([255.0, 248.0, 220.0], dtype=np.float32)
            warm_color = np.array([min(255, warm_r + 20), min(255, warm_g + 15), min(255, warm_b + 8)], dtype=np.float32)
            # Inner white-hot glow layer
            combined += hot_center[..., np.newaxis] * hot_color.reshape(1, 1, 3) * 0.7 * ray_intensity * flicker
            # Outer warm glow layer
            core_strength = core_mask * ray_intensity * flicker
            combined += core_strength[..., np.newaxis] * warm_color.reshape(1, 1, 3) * 0.3
            combined = np.clip(combined, 0, 255)

            # ── Wide warm haze around light source ──
            haze_r = diag * 0.20
            haze_dist = np.sqrt((dx / max(haze_r, 1.0))**2 + (dy / max(haze_r, 1.0))**2)
            haze_mask = np.clip(1.0 - haze_dist, 0, 1) ** 1.5
            haze_color = np.array([min(255, warm_r + 12), min(255, warm_g + 8), min(255, warm_b)], dtype=np.float32)
            haze_alpha = haze_mask * 0.15 * ray_intensity * flicker
            combined = np.clip(combined + haze_alpha[..., np.newaxis] * haze_color.reshape(1, 1, 3), 0, 255)

        # ── Atmospheric depth tint ──
        depth_tint = np.array([0.03, 0.03, 0.05], dtype=np.float32)
        combined = combined * 0.92 + (combined + depth_tint.reshape(1, 1, 3) * 255.0) * 0.08

        # ════════════════════════════════════════════════════════════════
        #  PERSON INTEGRATION — light wraps around borders from behind
        # ════════════════════════════════════════════════════════════════
        if person_mask is not None and person_mask.max() > 0.01:
            pm = person_mask
            if pm.shape[:2] != (h, w):
                pm = cv2.resize(pm, (w, h), interpolation=cv2.INTER_LINEAR)

            pm_u8 = (np.clip(pm, 0, 1) * 255).astype(np.uint8)
            person_edges = cv2.Canny(pm_u8, 25, 85)
            person_edges = cv2.dilate(person_edges, np.ones((2, 2), np.uint8), iterations=1)
            person_edges = cv2.GaussianBlur(person_edges, (5, 5), 0).astype(np.float32) / 255.0

            # Dilated outer edge (soft glow zone around the person)
            outer_dilated = cv2.dilate(pm_u8, np.ones((11, 11), np.uint8), iterations=1)
            outer_glow = cv2.GaussianBlur(outer_dilated, (21, 21), 0).astype(np.float32) / 255.0
            outer_glow = outer_glow * (1.0 - pm)

            # Person centroid for ray origin
            ys, xs = np.where(pm > 0.3)
            if len(xs) > 0:
                cy_p = int(np.mean(ys))
                cx_p = int(np.mean(xs))
            else:
                cy_p, cx_p = h // 2, w // 2

            bg_mask = (1.0 - pm)[..., np.newaxis]

            # ── RIM LIGHT — light source direction wraps around person ──
            # Compute signed distance from light direction through person center
            rim_angle = np.arct2(src_y - cy_p, src_x - cx_p)
            rim_dir_x = np.cos(rim_angle)
            rim_dir_y = np.sin(rim_angle)

            Y_r, X_r = np.mgrid[:h, :w].astype(np.float32)
            # Positive = facing light source (lit side), negative = away (shadow side)
            rim_dot = (X_r - cx_p) * rim_dir_x + (Y_r - cy_p) * rim_dir_y
            rim_sdf = cv2.GaussianBlur(rim_dot.astype(np.float32), (0, 0), 15)
            rim_lit = np.clip(rim_sdf, 0, 1)
            rim_shadow = np.clip(-rim_sdf, 0, 1)

            # Inner edge rim — warm light on the lit side of the silhouette
            rim_inner = rim_lit * person_edges * 1.5
            rim_inner = np.clip(rim_inner, 0, 1)
            rim_color = np.array([min(255, warm_r + 10), min(255, warm_g + 5), warm_b], dtype=np.float32)
            combined += rim_inner[..., np.newaxis] * rim_color.reshape(1, 1, 3) * 0.3 * ray_intensity * flicker

            # Outer edge rim — soft golden glow on lit side outline
            outer_edges = cv2.dilate(pm_u8, np.ones((7, 7), np.uint8), iterations=1)
            outer_edges = cv2.GaussianBlur(outer_edges, (9, 9), 0).astype(np.float32) / 255.0
            outer_edges *= (1.0 - pm)
            rim_outer = outer_edges * rim_lit * 1.2
            gold_rim = np.array([1.0, 0.82, 0.0], dtype=np.float32)
            combined += rim_outer[..., np.newaxis] * gold_rim.reshape(1, 1, 3) * 80.0 * ray_intensity * flicker * bg_mask

            # Subtle shadow-side darkening for depth
            shadow_depth = rim_shadow * pm * 0.15 * ray_intensity
            combined *= (1.0 - shadow_depth[..., np.newaxis])

            # ── BEHIND MODE — light emanates from borders of the person ──
            if is_behind:
                # Soft backlit rim along the silhouette edge
                backlit_rim = person_edges * 1.8
                backlit_rim = np.clip(backlit_rim, 0, 1)
                backlight_color = np.array([min(255, warm_r + 15), min(255, warm_g + 8), min(255, warm_b + 3)], dtype=np.float32)
                combined += backlit_rim[..., np.newaxis] * backlight_color.reshape(1, 1, 3) * 0.5 * ray_intensity * flicker

                # Wider soft glow around the silhouette
                wide_glow = cv2.dilate(pm_u8, np.ones((15, 15), np.uint8), iterations=1)
                wide_glow = cv2.GaussianBlur(wide_glow, (25, 25), 0).astype(np.float32) / 255.0
                wide_glow *= (1.0 - pm)
                combined += wide_glow[..., np.newaxis] * gold_rim.reshape(1, 1, 3) * 60.0 * ray_intensity * flicker * bg_mask

                # Soft rays emanating outward from silhouette
                Y_p, X_p = np.mgrid[:h, :w].astype(np.float32)
                pdx = X_p - cx_p
                pdy = Y_p - cy_p
                p_diag = np.hypot(w, h)

                edge_rays = np.zeros((h, w, 3), dtype=np.float32)
                num_edge_rays = 12
                for j in range(num_edge_rays):
                    pa = (j / num_edge_rays) * 2 * np.pi
                    rdx_j = np.cos(pa)
                    rdy_j = np.sin(pa)
                    cross_j = pdx * rdx_j - pdy * rdy_j
                    pw_j = 15 + 8 * np.sin(j * 2.1)
                    falloff_j = np.exp(-0.5 * (cross_j / max(pw_j, 1.0))**2)
                    along_j = np.clip(pdx * rdx_j + pdy * rdy_j, 0, p_diag)
                    fade_j = np.clip(1.0 - along_j / (p_diag * 0.35), 0, 1) ** 0.7
                    outside_mask = (1.0 - pm)
                    edge_rays += (falloff_j * fade_j * outside_mask)[..., np.newaxis] * ray_color.reshape(1, 1, 3)

                combined += edge_rays * 20.0 * ray_intensity * flicker

                # Soft bloom behind the person
                bloom_y = max(0, cy_p - int(h * 0.1))
                bloom_dx = X_p - cx_p
                bloom_dy = Y_p - bloom_y
                bloom_dist = np.sqrt(bloom_dx**2 + bloom_dy**2)
                bloom_r = diag * 0.15
                bloom_mask = np.clip(1.0 - bloom_dist / bloom_r, 0, 1) ** 2.0
                bloom_mask *= outside_mask
                bloom_color = np.array([min(255, warm_r + 5), min(255, warm_g + 3), warm_b], dtype=np.float32)
                combined += bloom_mask[..., np.newaxis] * bloom_color.reshape(1, 1, 3) * 15.0 * ray_intensity * flicker

        return np.clip(combined, 0, 255).astype(np.uint8)

    def apply_canopy_effect(self, frame, item, t):
        if not item.get('effect_canopy_enabled', False):
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame

        # Get person mask if a person is selected on this clip
        person_mask = None
        selected_id = int(item.get('effect_selected_person', -1))
        if selected_id >= 0 or selected_id == -2:
            try:
                mask = self._get_selected_person_mask(frame, item, t=t)
                if mask is not None and mask.max() > 0.01:
                    person_mask = mask
            except Exception:
                pass

        return self._create_canopy_effect(
            frame,
            light_dir=item.get('canopy_light_dir', 'Top Left'),
            light_style=item.get('canopy_light_style', 'Soft Atmosphere'),
            fog_density=item.get('canopy_fog_density', 0.7),
            fog_height=item.get('canopy_fog_height', 0.5),
            ray_intensity=item.get('canopy_ray_intensity', 1.0),
            ray_width=item.get('canopy_ray_width', 1.0),
            warmth=item.get('canopy_warmth', 0.7),
            shimmer=item.get('canopy_shimmer', 0.3),
            time_factor=t,
            person_mask=person_mask,
            show_light_source=item.get('canopy_show_light_source', True))

    # ══════════════════════════════════════════════════════════════════
    #  3D TEXT TRACKING EFFECT
    #  Places 3D extruded text in the scene that stays anchored as the
    #  camera moves. Text has depth, perspective, and casts shadows.
    # ══════════════════════════════════════════════════════════════════

    _3D_TEXT_COLORS = {
        'Orange': ((255, 120, 0), (200, 80, 0), (160, 60, 0)),
        'White':  ((255, 255, 255), (220, 220, 220), (180, 180, 180)),
        'Gold':   ((255, 215, 0), (218, 165, 32), (180, 130, 20)),
        'Red':    ((230, 40, 40), (180, 20, 20), (130, 10, 10)),
        'Blue':   ((40, 100, 230), (20, 60, 180), (10, 40, 130)),
        'Cyan':   ((0, 220, 240), (0, 170, 190), (0, 120, 140)),
        'Green':  ((40, 200, 60), (20, 150, 30), (10, 100, 15)),
        'Purple': ((160, 50, 220), (120, 30, 170), (80, 15, 120)),
        'Black':  ((60, 60, 60), (40, 40, 40), (25, 25, 25)),
    }

    _3D_TEXT_CANON_FONT_PX = 220  # fixed high-res render size; the quad warp does the actual on-screen scaling

    def _load_3d_text_font(self, px):
        for name in ("arialbd.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(name, px)
            except Exception:
                continue
        try:
            return ImageFont.truetype("C:\\Windows\\Fonts\\arialbd.ttf", px)
        except Exception:
            return ImageFont.load_default()

    def _get_3d_text_texture_cached(self, text, color_name, depth, style, time_factor):
        """Text drawing (up to 40 extruded layers) is the expensive part of
        this effect, but it only depends on text/color/depth/style/time —
        not on the quad. While the user drags the quad around, none of
        those change, so we cache the rendered texture and only redo the
        (cheap) perspective warp each frame. This is what keeps corner
        drag/resize/rotate feeling responsive instead of janky."""
        # Glow style animates with time; round time_factor coarsely so we still
        # get cache hits during a drag (where time_factor is constant) without
        # letting the cache grow unbounded during playback.
        t_key = round(time_factor, 2) if style == 'Glow' else 0.0
        key = (text, color_name, round(depth, 3), style, t_key)
        cache = self._3d_text_texture_cache
        cached = cache.get(key)
        if cached is not None:
            return cached
        texture = self._render_3d_text_texture(text, color_name, depth, style, time_factor)
        if len(cache) > 12:
            cache.pop(next(iter(cache)))
        cache[key] = texture
        return texture

    def _render_3d_text_texture(self, text, color_name, depth, style, time_factor):
        """Renders extruded/beveled 3D text onto its own transparent RGBA
        canvas (not tied to any frame position or size). This canonical
        texture is later perspective-warped onto the quad the user placed
        on the preview, which is what actually gives the text its on-screen
        position, size, and orientation."""
        colors = self._3D_TEXT_COLORS.get(color_name, self._3D_TEXT_COLORS['Orange'])
        face_color, side_color = colors[0], colors[1]

        font_px = self._3D_TEXT_CANON_FONT_PX
        font = self._load_3d_text_font(font_px)

        tmp = PIL.Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        bbox = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
        text_w = max(1, bbox[2] - bbox[0])
        text_h = max(1, bbox[3] - bbox[1])

        pixel_depth = max(0, int(depth * font_px * 0.5))
        pad = int(font_px * 0.35) + pixel_depth + 4
        canvas_w = text_w + pad * 2
        canvas_h = text_h + pad * 2
        canvas = PIL.Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        ax = pad - bbox[0]
        ay = pad - bbox[1]

        # --- extrusion layers (back to front, for the chunky 3D side) ---
        if pixel_depth > 0 and depth > 0:
            n_layers = min(max(1, pixel_depth), 40)
            for layer_idx in range(n_layers - 1, -1, -1):
                tt = layer_idx / max(1, n_layers)
                lx = ax + layer_idx
                ly = ay + layer_idx
                r = int(side_color[0] * (0.4 + 0.6 * (1.0 - tt)))
                g = int(side_color[1] * (0.4 + 0.6 * (1.0 - tt)))
                b = int(side_color[2] * (0.4 + 0.6 * (1.0 - tt)))

                if style == 'Metallic':
                    spec = max(0, 1.0 - abs(tt - 0.3) * 3.0) * 60
                    r, g, b = min(255, r + int(spec)), min(255, g + int(spec)), min(255, b + int(spec))
                elif style == 'Glossy':
                    edge = max(0, 1.0 - abs(tt - 0.5) * 4.0) * 50
                    r, g, b = min(255, r + int(edge)), min(255, g + int(edge)), min(255, b + int(edge))
                elif style == 'Glow':
                    glow = 0.3 + 0.2 * math.sin(time_factor * 2.0 + tt * 3.0)
                    r, g, b = min(255, int(r * (1.0 + glow))), min(255, int(g * (1.0 + glow))), min(255, int(b * (1.0 + glow)))

                draw.text((lx, ly), text, fill=(r, g, b, 255), font=font)

        # --- front face ---
        r, g, b = face_color
        if style == 'Glow':
            pulse = 0.8 + 0.2 * math.sin(time_factor * 1.5)
            r, g, b = min(255, int(r * pulse)), min(255, int(g * pulse)), min(255, int(b * pulse))
        highlight = (min(255, r + 50), min(255, g + 50), min(255, b + 50), 255)
        shadow_c = (max(0, r - 50), max(0, g - 50), max(0, b - 50), 255)
        draw.text((ax, ay), text, fill=(r, g, b, 255), font=font)
        draw.text((ax - 1, ay - 1), text, fill=highlight, font=font)
        draw.text((ax + 1, ay + 1), text, fill=shadow_c, font=font)

        return canvas

    def _make_3d_text_ground_shadow(self, warped_rgba, shadow_opacity, dst_pts_px):
        """Derives a soft ground shadow from the already-warped text's alpha
        mask, nudged along the quad's own 'down' direction so it reads as
        being cast onto the surface the text sits on rather than floating."""
        if shadow_opacity <= 0:
            return None
        alpha = warped_rgba[:, :, 3].astype(np.float32)
        if alpha.max() <= 0:
            return None
        ys = [p[1] for p in dst_pts_px]
        quad_h = max(1.0, max(ys) - min(ys))
        # average of the two side edges (TL->BL, TR->BR) gives the quad's local "down" direction
        down_x = ((dst_pts_px[3][0] - dst_pts_px[0][0]) + (dst_pts_px[2][0] - dst_pts_px[1][0])) / 2.0
        down_y = ((dst_pts_px[3][1] - dst_pts_px[0][1]) + (dst_pts_px[2][1] - dst_pts_px[1][1])) / 2.0
        down_len = max(1e-4, math.hypot(down_x, down_y))
        off = max(4.0, quad_h * 0.16)
        ox, oy = down_x / down_len * off, down_y / down_len * off

        M = np.float32([[1, 0, ox], [0, 1, oy]])
        shifted = cv2.warpAffine(alpha, M, (alpha.shape[1], alpha.shape[0]),
                                  flags=cv2.INTER_LINEAR, borderValue=0)
        k = max(3, int(quad_h * 0.06)) | 1
        shifted = cv2.GaussianBlur(shifted, (k, k), 0)
        return (shifted / 255.0) * shadow_opacity * 0.7

    def _project_3d_text_quad(self, item, t, frame_w, frame_h):
        """Compute the on-screen quad by applying perspective growth to the
        user's manually placed anchor quad.  The anchor defines where the
        text sits at t=0.  As the virtual camera moves forward, each corner
        scales outward from the vanishing point (frame center) so that:
          - text below camera height expands downward
          - text at camera height expands through the center
          - text above camera height expands upward
          - left/right offset expands laterally

        Returns None when the camera has moved past the text (near-plane clip)."""
        cam_speed = float(item.get('3d_cam_speed', 8.0))

        anchor = self._get_3d_text_quad(item)
        if not anchor or len(anchor) != 4:
            return self._default_3d_text_quad()

        if cam_speed <= 0:
            return anchor

        text_z = 25.0
        cam_z = cam_speed * t
        if cam_z >= text_z - 0.05:
            return None

        scale = text_z / (text_z - cam_z)

        vpx, vpy = 0.5, 0.5

        new_quad = []
        for px, py in anchor:
            dx = px - vpx
            dy = py - vpy
            new_quad.append([vpx + dx * scale, vpy + dy * scale])

        return new_quad

    def _create_3d_text_tracking(self, frame, text='TRACKING', color_name='Orange',
                                  depth=0.4, shadow_opacity=0.5, style='Solid Matte',
                                  time_factor=0.0, quad=None):
        h, w = frame.shape[:2]
        if h == 0 or w == 0 or not text:
            return frame
        if quad is None or len(quad) != 4:
            quad = self._default_3d_text_quad()

        texture = self._get_3d_text_texture_cached(text, color_name, depth, style, time_factor)
        tex_np = np.array(texture)
        th, tw = tex_np.shape[:2]

        src_pts = np.float32([[0, 0], [tw, 0], [tw, th], [0, th]])
        dst_pts_px = [[p[0] * w, p[1] * h] for p in quad]
        M = cv2.getPerspectiveTransform(src_pts, np.float32(dst_pts_px))
        warped = cv2.warpPerspective(tex_np, M, (w, h), flags=cv2.INTER_LINEAR,
                                      borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

        out = frame.astype(np.float32)

        shadow_a = self._make_3d_text_ground_shadow(warped, shadow_opacity, dst_pts_px)
        if shadow_a is not None:
            out = out * (1.0 - shadow_a[..., np.newaxis])

        alpha = warped[:, :, 3:4].astype(np.float32) / 255.0
        rgb = warped[:, :, :3].astype(np.float32)
        out = out * (1.0 - alpha) + rgb * alpha

        return np.clip(out, 0, 255).astype(np.uint8)

    def apply_3d_text_tracking_effect(self, frame, item, t):
        if not item.get('effect_3d_text_enabled', False):
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame

        fade_alpha = 1.0
        if not item.get('3d_text_full_clip', True):
            t_start = float(item.get('3d_text_start', 0.0))
            t_end = max(t_start + 0.05, float(item.get('3d_text_end', 3.0)))
            fade = max(0.0, float(item.get('3d_text_fade', 0.3)))
            if t < t_start - fade or t > t_end + fade:
                return frame  # outside the visible window — text isn't there at all
            if fade > 0.0:
                if t < t_start:
                    fade_alpha = max(0.0, 1.0 - (t_start - t) / fade)
                elif t > t_end:
                    fade_alpha = max(0.0, 1.0 - (t - t_end) / fade)
            elif t < t_start or t > t_end:
                return frame
            if fade_alpha <= 0.0:
                return frame

        # --- 3D perspective projection (always) ---
        quad = self._project_3d_text_quad(item, t, w, h)

        if quad is None:
            return frame  # camera has moved past the text (near-plane clip)

        result = self._create_3d_text_tracking(
            frame,
            text=item.get('3d_text_content', 'TRACKING'),
            color_name=item.get('3d_text_color', 'Orange'),
            depth=item.get('3d_text_depth', 0.4),
            shadow_opacity=item.get('3d_text_shadow', 0.5),
            style=item.get('3d_text_style', 'Solid Matte'),
            time_factor=t,
            quad=quad
        )
        if fade_alpha < 1.0:
            result = (frame.astype(np.float32) * (1.0 - fade_alpha)
                      + result.astype(np.float32) * fade_alpha).astype(np.uint8)
        return result

    # ══════════════════════════════════════════════════════════════════
    #  MOTION TRACK EFFECT  (Arrow + Name tracking a person)
    # ══════════════════════════════════════════════════════════════════

    MOTION_TRACK_COLORS = {
        "Yellow":  (0, 255, 255),
        "Red":     (0, 0, 255),
        "Green":   (0, 255, 0),
        "Blue":    (255, 0, 0),
        "White":   (255, 255, 255),
        "Orange":  (0, 165, 255),
        "Cyan":    (255, 255, 0),
        "Magenta": (255, 0, 255),
        "Lime":    (0, 255, 128),
        "Gold":    (0, 215, 255),
    }

    def _get_motion_track_position(self, frame, item, t):
        """Get the tracked object's center and bbox. Uses YOLO detection,
        position prediction, appearance matching, and keyframe interpolation.
        Returns (cx, cy, bbox, matched)."""
        h, w = frame.shape[:2]
        selected_id = int(item.get('effect_selected_person', -1))
        has_template = item.get('effect_person_template') is not None
        has_keyframes = len(item.get('effect_tracking_keyframes', {})) > 0
        selected_class = item.get('effect_selected_class', None)
        person_selected = selected_id >= 0 or selected_id == -2

        # Run YOLO detection
        yolo_objects = self._yolo_track(frame)

        # ── No object selected AND no template: pick closest to frame center ──
        if not person_selected and not has_template:
            if yolo_objects:
                cy_mid, cx_mid = h // 2, w // 2
                best = min(yolo_objects, key=lambda p: (
                    (p['center'][0] - cy_mid)**2 + (p['center'][1] - cx_mid)**2))
                return (best['center'][1], best['center'][0], best['bbox'], True)
            return (None, None, None, False)

        # ── Object selected (or template exists): use full tracking pipeline ──
        predicted_center, predicted_bbox = self._predict_person_position(item, cur_w=w, cur_h=h)
        template = item.get('effect_person_template', None)
        face_buffer = item.get('effect_face_buffer', [])
        max_dim = max(h, w)

        # ── EXACT KEYFRAME: this frame has a known-correct position ─────
        # already stored -- either the original selection click, or a
        # manual correction (Correct Here). Use it directly rather than
        # re-deriving it via search, so the selection/correction point
        # itself is always pixel-exact, never second-guessed.
        frame_idx_now = int(round(t * 30))
        exact_kf = item.get('effect_tracking_keyframes', {}).get(str(frame_idx_now))
        if exact_kf is not None:
            ex_center, ex_bbox = exact_kf.get('center'), exact_kf.get('bbox')
            ex_ref_w, ex_ref_h = exact_kf.get('ref_w'), exact_kf.get('ref_h')
            if ex_ref_w and ex_ref_h and (ex_ref_w != w or ex_ref_h != h):
                sx, sy = w / ex_ref_w, h / ex_ref_h
                ex_center = (ex_center[0] * sy, ex_center[1] * sx)
                ex_bbox = (ex_bbox[0] * sx, ex_bbox[1] * sy, ex_bbox[2] * sx, ex_bbox[3] * sy)
            ex_cy, ex_cx = ex_center
            item['effect_track_miss_streak'] = 0
            item['effect_last_match_frame_idx'] = frame_idx_now
            return (ex_cx, ex_cy, ex_bbox, True)

        # ── STAGE 1: LOCAL correlation tracking (primary) ───────────────
        # Search only a small window around the predicted position for the
        # exact pixel pattern grabbed at selection time (or last refreshed).
        # A lookalike neighbour standing even a short distance away never
        # enters this window, so it structurally cannot be picked here --
        # unlike Stage 2 below, which searches the whole frame and can be
        # fooled by near-identical appearance (e.g. teammates in the same
        # kit). Stage 2 only runs when Stage 1 doesn't find a confident
        # match -- e.g. right after selection (no patch refresh yet isn't
        # the case, selection already seeds one), after a big timeline
        # jump/scrub, or once the tracked object reappears from an absence.
        template_patch = item.get('effect_track_template_patch')
        if template_patch is not None and predicted_center is not None:
            # The patch may have been captured at a DIFFERENT resolution
            # than this frame -- preview renders at a fixed small canvas
            # while export renders at the actual output resolution, so a
            # patch grabbed during preview is the wrong physical size for
            # matching against an export-resolution frame. Rescale it (and
            # the inner-offset that locates the real object within it) to
            # match this frame before searching.
            inner_offset = item.get('effect_track_template_inner_offset')
            patch_ref_w, patch_ref_h = item.get('effect_track_template_ref_wh', (None, None))
            match_patch = template_patch
            match_offset = inner_offset
            if patch_ref_w and patch_ref_h and (patch_ref_w != w or patch_ref_h != h):
                psx, psy = w / patch_ref_w, h / patch_ref_h
                new_tw = max(3, int(template_patch.shape[1] * psx))
                new_th = max(3, int(template_patch.shape[0] * psy))
                try:
                    match_patch = cv2.resize(template_patch, (new_tw, new_th), interpolation=cv2.INTER_LINEAR)
                    if inner_offset:
                        match_offset = (int(inner_offset[0] * psx), int(inner_offset[1] * psy),
                                         int(inner_offset[2] * psx), int(inner_offset[3] * psy))
                except Exception:
                    match_patch = template_patch

            obj_w, obj_h = (predicted_bbox[2], predicted_bbox[3]) if predicted_bbox else (
                (match_offset[2], match_offset[3]) if match_offset else (match_patch.shape[1], match_patch.shape[0]))
            # Tight radius: real frame-to-frame motion is small (a few px
            # at typical framerates). The old 2.5x multiplier produced a
            # ~140px-wide window for a 15px player -- easily wide enough
            # to reach a neighbour standing nearby, which is what let the
            # arrow hop between people. A big jump (fast pan, scrub) will
            # simply miss here and fall through to Stage 2 instead, which
            # is the right behaviour -- Stage 1 should only claim "same
            # person" when the evidence is tight, not stretch to cover
            # cases it can't reliably distinguish.
            #
            # That said, a SHORT run of consecutive misses (motion blur on
            # a fast movement, a brief partial occlusion) shouldn't force
            # a drop to the weaker Stage 2 on every single one of those
            # frames -- each additional consecutive miss widens the search
            # a bit further (capped), so a brief rough patch can still be
            # bridged by the strong, context-aware Stage 1 match instead of
            # repeatedly falling back or eventually hiding the arrow. It
            # snaps back to the tight radius the moment a match succeeds.
            miss_streak = int(item.get('effect_track_miss_streak', 0))
            widen = 1.0 + min(miss_streak, 6) * 0.35
            search_radius = int(max(min(int(max(obj_w, obj_h) * 1.1), 80), 9) * widen)
            pcy, pcx = predicted_center
            local_hit = self._template_track_local(frame, match_patch, (pcx, pcy), search_radius)
            LOCAL_MATCH_THRESHOLD = 0.42
            if local_hit is not None and local_hit['score'] >= LOCAL_MATCH_THRESHOLD:
                px, py, pw, ph = local_hit['bbox']  # position of the (padded, context-including) patch
                if match_offset:
                    ox, oy, obw, obh = match_offset
                    bx, by, bw, bh = px + ox, py + oy, obw, obh  # the object's own tight bbox
                else:
                    bx, by, bw, bh = px, py, pw, ph
                cx, cy = bx + bw / 2.0, by + bh / 2.0
                print(f"[LOCAL-TRACK] score={local_hit['score']:.3f} pos=({cx:.0f},{cy:.0f}) window_r={search_radius} miss_streak={miss_streak}")
                item['effect_track_miss_streak'] = 0
                self._update_tracking_keyframe(item, frame, (cy, cx), (bx, by, bw, bh), match_score=local_hit['score'], t=t)
                return (cx, cy, (bx, by, bw, bh), True)
            elif local_hit is not None:
                print(f"[LOCAL-TRACK] below threshold: score={local_hit['score']:.3f} < {LOCAL_MATCH_THRESHOLD} -- falling back to detector")
            item['effect_track_miss_streak'] = min(int(item.get('effect_track_miss_streak', 0)) + 1, 6)
        # ── STAGE 2: detector + appearance reacquisition (fallback) ─────

        if yolo_objects:
            # Filter by same class if we know what we're tracking
            if selected_class:
                same_class = [p for p in yolo_objects if p.get('class_name') == selected_class]
                search_pool = same_class if same_class else yolo_objects
            else:
                search_pool = yolo_objects

            # Score candidates by distance to predicted position
            scored = []
            for p in search_pool:
                if predicted_center is not None:
                    pcx, pcy = predicted_center[1], predicted_center[0]
                    cx, cy = p['center'][1], p['center'][0]
                    pos_dist = ((pcx - cx) ** 2 + (pcy - cy) ** 2) ** 0.5
                else:
                    pos_dist = 0
                # Boost score for same YOLO track ID (strong identity signal)
                id_bonus = 0
                if person_selected and p.get('id') == selected_id:
                    id_bonus = max_dim * 0.15
                scored.append((p, max(0, pos_dist - id_bonus)))
            scored.sort(key=lambda x: x[1])

            # Tight, SIZE-AWARE tolerance: a real person can't jump more
            # than a few multiples of their own on-screen size between two
            # frames a fraction of a second apart. Gating on a fixed
            # fraction of the WHOLE frame (the old behaviour: 40-50%) is far
            # too loose in a wide shot crowded with small, similarly-
            # dressed subjects — it lets appearance-match noise on a tiny
            # crop pick a completely different person clear across the
            # pitch, which is exactly what was happening.
            ref_w, ref_h = (predicted_bbox[2], predicted_bbox[3]) if predicted_bbox else (None, None)
            if ref_w and ref_h:
                ref_diag = (ref_w ** 2 + ref_h ** 2) ** 0.5
            else:
                ref_diag = max_dim * 0.04
            max_close_dist = min(max(ref_diag * 4.0, max_dim * 0.05), max_dim * 0.16)
            close_candidates = [(p, d) for p, d in scored if d < max_close_dist]
            if not close_candidates:
                close_candidates = scored[:3]

            if has_template and close_candidates:
                cand_list = [p for p, _ in close_candidates]
                best_idx, app_score = self._match_person_to_template(
                    frame, cand_list, template,
                    last_center=predicted_center, face_buffer=face_buffer,
                    max_spatial_dist=max_close_dist)
                if best_idx >= 0:
                    matched = cand_list[best_idx]
                    cx, cy = matched['center'][1], matched['center'][0]
                    # VETO: a colour histogram alone can be fooled by a
                    # similarly-dressed neighbour. Re-check this exact
                    # candidate against the context-rich local patch before
                    # accepting it as the new chain anchor.
                    verify_score = self._verify_local_context(item, frame, (cx, cy))
                    if verify_score is not None and verify_score < 0.25:
                        print(f"[MOTION-TRACK] REJECTED class_match: app_score={app_score:.3f} but context_score={verify_score:.3f} < 0.25 -- likely wrong person")
                    else:
                        print(f"[MOTION-TRACK] class_match={matched.get('class_name','?')} app_score={app_score:.3f} context_score={verify_score} pos=({cx},{cy})")
                        item['effect_track_miss_streak'] = 0
                        self._update_tracking_keyframe(item, frame, matched['center'], matched['bbox'], match_score=app_score, t=t)
                        return (cx, cy, matched['bbox'], True)
                else:
                    print(f"[MOTION-TRACK] no_app_match class={selected_class} candidates={len(close_candidates)}")

            # Fallback: when a person is selected, prefer same-class detections
            # and use YOLO ID as tiebreaker to avoid jumping to wrong person
            if scored:
                if person_selected and selected_class:
                    same_class_scored = [(p, d) for p, d in scored if p.get('class_name') == selected_class]
                    if same_class_scored:
                        scored = same_class_scored
                # Among equal-distance candidates, prefer matching YOLO ID
                best_p = scored[0][0]
                for p, d in scored[:5]:
                    if person_selected and p.get('id') == selected_id:
                        best_p = p
                        break
                cx, cy = best_p['center'][1], best_p['center'][0]
                # This fallback has NO appearance confirmation at all -- it's
                # the weakest signal in the whole pipeline, so require the
                # local-context check to pass before accepting it.
                verify_score = self._verify_local_context(item, frame, (cx, cy))
                if verify_score is not None and verify_score < 0.25:
                    print(f"[MOTION-TRACK] REJECTED pos_fallback: context_score={verify_score:.3f} < 0.25 -- likely wrong person")
                else:
                    print(f"[MOTION-TRACK] pos_fallback class={best_p.get('class_name','?')} id={best_p.get('id','?')} context_score={verify_score} pos=({cx},{cy})")
                    item['effect_track_miss_streak'] = 0
                    self._update_tracking_keyframe(item, frame, best_p['center'], best_p['bbox'], match_score=0.0, t=t)
                    return (cx, cy, best_p['bbox'], True)

        # ── No YOLO detections: use prediction + keyframe interpolation ──
        if predicted_center is not None:
            bbox = predicted_bbox if predicted_bbox is not None else None
            if bbox is None and has_keyframes:
                frame_idx = int(t * 30)
                _, interp_bbox = self._get_tracked_center_for_frame(item, frame_idx)
                bbox = interp_bbox if interp_bbox else None
            return (predicted_center[1], predicted_center[0], bbox, False)

        # ── Last resort: use keyframe interpolation ──
        if has_keyframes:
            frame_idx = int(t * 30)
            interp_center, interp_bbox = self._get_tracked_center_for_frame(item, frame_idx)
            if interp_center is not None:
                return (interp_center[1], interp_center[0], interp_bbox, False)

        return (None, None, None, False)

    def apply_motion_track_effect(self, frame, item, t):
        """Draw a colored arrow + optional name label tracking a person.
        Uses the full tracking pipeline: YOLO detection, position prediction,
        appearance matching (face + clothing color + edge template), and
        keyframe interpolation for frame-to-frame continuity."""
        if not item.get('effect_motion_track_enabled', False):
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame

        cx, cy, bbox, matched = self._get_motion_track_position(frame, item, t)

        if cx is None or cy is None:
            return frame

        # ── PRESENCE GATE ──────────────────────────────────────────────
        # `matched` is True only when the tracked object was genuinely
        # detected in THIS frame (appearance match or same-class YOLO
        # fallback). When it's False, cx/cy/bbox came only from velocity
        # prediction or keyframe interpolation -- a guess, not a sighting.
        # Keep drawing through a short grace window so a single missed
        # detection doesn't cause 1-frame flicker, but once the person/
        # object has genuinely left the shot for longer than that, hide
        # the arrow instead of letting it drift on a stale guess.
        frame_idx = int(round(t * 30))
        GRACE_FRAMES = 10  # ~0.33s at 30fps
        if matched:
            item['effect_track_miss_streak'] = 0
            item['effect_last_match_frame_idx'] = frame_idx
        else:
            last_match = item.get('effect_last_match_frame_idx', None)
            if last_match is None or abs(frame_idx - last_match) > GRACE_FRAMES:
                return frame
        # ─────────────────────────────────────────────────────────────────
        # Get settings
        mode = item.get('motion_track_mode', 'arrow_and_name')
        name = item.get('motion_track_name', '')
        color_name = item.get('motion_track_color', 'Yellow')
        text_color_name = item.get('motion_track_text_color', 'Yellow')
        arrow_size = float(item.get('motion_track_arrow_size', 1.0))
        arrow_len = float(item.get('motion_track_arrow_len', 1.0))
        text_size = float(item.get('motion_track_text_size', 1.0))
        offset_y = float(item.get('motion_track_offset_y', 0.0))

        arrow_bgr = self.MOTION_TRACK_COLORS.get(color_name, (0, 255, 255))
        text_bgr = self.MOTION_TRACK_COLORS.get(text_color_name, (0, 255, 255))

        # Convert BGR to RGB for numpy drawing
        arrow_rgb = (arrow_bgr[2], arrow_bgr[1], arrow_bgr[0])
        text_rgb = (text_bgr[2], text_bgr[1], text_bgr[0])

        # Calculate arrow dimensions based on frame size
        base_dim = min(h, w)
        arrow_head_h = int(base_dim * 0.06 * arrow_size)
        arrow_head_w = int(base_dim * 0.04 * arrow_size)
        arrow_shaft_w = int(base_dim * 0.008 * arrow_size)
        arrow_shaft_h = int(base_dim * 0.12 * arrow_len)
        gap = int(base_dim * 0.01) + int(offset_y)

        # Arrow tip points at the person's top
        person_top_y = int(cy)
        if bbox is not None:
            person_top_y = int(bbox[1])

        tip_y = person_top_y - gap
        tip_x = int(cx)

        # Shaft top
        shaft_top_y = tip_y - arrow_head_h - arrow_shaft_h
        shaft_bot_y = tip_y - arrow_head_h

        # Draw on a copy
        result = frame.copy()

        # Draw shaft (vertical line) with slight glow
        cv2.line(result, (tip_x, shaft_top_y), (tip_x, shaft_bot_y),
                 arrow_rgb, arrow_shaft_w + 2, cv2.LINE_AA)
        cv2.line(result, (tip_x, shaft_top_y), (tip_x, shaft_bot_y),
                 arrow_rgb, arrow_shaft_w, cv2.LINE_AA)

        # Draw arrowhead (triangle pointing down) with outline for visibility
        pts = np.array([
            [tip_x, tip_y],
            [tip_x - arrow_head_w // 2, tip_y - arrow_head_h],
            [tip_x + arrow_head_w // 2, tip_y - arrow_head_h]
        ], dtype=np.int32)
        # Dark outline for contrast on any background
        cv2.polylines(result, [pts], True, (0, 0, 0), max(2, arrow_shaft_w), cv2.LINE_AA)
        cv2.fillPoly(result, [pts], arrow_rgb, cv2.LINE_AA)

        # Draw name label if mode is arrow_and_name and name is not empty
        if mode == 'arrow_and_name' and name.strip():
            font_scale = 0.7 * text_size
            thickness = max(1, int(2 * text_size))
            (tw, th), baseline = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)

            text_x = tip_x - tw // 2
            text_y = shaft_top_y - int(base_dim * 0.015)

            # Background rectangle with rounded look
            pad = int(base_dim * 0.01)
            cv2.rectangle(result,
                          (text_x - pad, text_y - th - pad),
                          (text_x + tw + pad, text_y + pad),
                          (0, 0, 0), -1, cv2.LINE_AA)
            cv2.rectangle(result,
                          (text_x - pad, text_y - th - pad),
                          (text_x + tw + pad, text_y + pad),
                          text_rgb, max(2, int(2 * text_size)), cv2.LINE_AA)

            # Text with dark outline for readability
            cv2.putText(result, name, (text_x, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0),
                        thickness + 2, cv2.LINE_AA)
            cv2.putText(result, name, (text_x, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_rgb,
                        thickness, cv2.LINE_AA)

        return result

    # ══════════════════════════════════════════════════════════════════
    #  THUG LIFE EFFECT  (Animated Sunglasses + Gold Chain)
    #  Pixel-art sunglasses + dollar-chain assets below were extracted
    #  directly from the reference artwork so the on-screen result matches
    #  it exactly (not a redrawn approximation). They are embedded as
    #  base64 PNGs so the effect works standalone with no extra asset
    #  files to ship alongside this script.
    # ══════════════════════════════════════════════════════════════════

    _THUG_GLASSES_PNG_B64 = """
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
"""

    _THUG_CHAIN_PNG_B64 = """
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
SUVORK5CYII=
"""

    # Realistic-style accessory assets (extracted from a photographic
    # reference) — an alternative to the pixel-art set above, selectable via
    # the Thug Life style option.
    _THUG_GLASSES_REAL_PNG_B64 = """
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
"""

    _THUG_CHAIN_REAL_PNG_B64 = """
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
"""

    _THUG_CAP_PNG_B64 = """
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
"""

    def _load_thug_asset(self, key):
        """Decode (and cache) an embedded thug-life accessory PNG. Valid keys:
        'glasses', 'chain' (pixel-art), 'glasses_real', 'chain_real', 'cap'
        (photographic-style)."""
        if not hasattr(self, '_thug_asset_cache'):
            self._thug_asset_cache = {}
        if key in self._thug_asset_cache:
            return self._thug_asset_cache[key]
        import base64, io
        from PIL import Image
        b64_map = {
            'glasses': self._THUG_GLASSES_PNG_B64,
            'chain': self._THUG_CHAIN_PNG_B64,
            'glasses_real': self._THUG_GLASSES_REAL_PNG_B64,
            'chain_real': self._THUG_CHAIN_REAL_PNG_B64,
            'cap': self._THUG_CAP_PNG_B64,
        }
        b64_data = b64_map.get(key)
        img = None
        if b64_data is not None:
            try:
                raw = base64.b64decode(b64_data, validate=False)
                img = Image.open(io.BytesIO(raw)).convert('RGBA')
            except Exception as e:
                print(f"WARNING: failed to decode embedded thug-life '{key}' asset: {e}")
        self._thug_asset_cache[key] = img
        return img

    def _draw_thug_glasses(self, width, height, style='pixel'):
        """Return the sunglasses scaled to `width` px wide (native aspect kept).
        style='pixel' uses nearest-neighbour scaling for a crisp 8-bit look;
        style='realistic' uses smooth (LANCZOS) scaling for the photographic asset."""
        if width < 10:
            return None
        src = self._load_thug_asset('glasses_real' if style == 'realistic' else 'glasses')
        if src is None:
            return None
        from PIL import Image
        sw, sh = src.size
        scale = max(width / sw, 0.01)
        new_w = max(1, int(round(sw * scale)))
        new_h = max(1, int(round(sh * scale)))
        resample = Image.LANCZOS if style == 'realistic' else Image.NEAREST
        return src.resize((new_w, new_h), resample)

    def _draw_gold_chain(self, width, height, style='pixel'):
        """Return the gold chain scaled to `width` px wide (native aspect kept).
        style='pixel' uses nearest-neighbour scaling for a crisp 8-bit look;
        style='realistic' uses smooth (LANCZOS) scaling for the photographic asset."""
        if width < 10:
            return None
        src = self._load_thug_asset('chain_real' if style == 'realistic' else 'chain')
        if src is None:
            return None
        from PIL import Image
        sw, sh = src.size
        scale = max(width / sw, 0.01)
        new_w = max(1, int(round(sw * scale)))
        new_h = max(1, int(round(sh * scale)))
        resample = Image.LANCZOS if style == 'realistic' else Image.NEAREST
        return src.resize((new_w, new_h), resample)

    def _draw_thug_cap(self, width, height):
        """Return the flat-brim cap scaled to `width` px wide (native aspect kept)."""
        if width < 10:
            return None
        src = self._load_thug_asset('cap')
        if src is None:
            return None
        from PIL import Image
        sw, sh = src.size
        scale = max(width / sw, 0.01)
        new_w = max(1, int(round(sw * scale)))
        new_h = max(1, int(round(sh * scale)))
        return src.resize((new_w, new_h), Image.LANCZOS)

    def _overlay_at_center(self, frame_np, overlay_pil, center_x, center_y, angle=0, scale=1.0,
                            opacity=1.0, flip_h=False, flip_v=False):
        if overlay_pil is None:
            return frame_np
        from PIL import Image
        if flip_h:
            overlay_pil = overlay_pil.transpose(Image.FLIP_LEFT_RIGHT)
        if flip_v:
            overlay_pil = overlay_pil.transpose(Image.FLIP_TOP_BOTTOM)
        if scale != 1.0:
            sw = max(1, int(round(overlay_pil.width * scale)))
            sh = max(1, int(round(overlay_pil.height * scale)))
            overlay_pil = overlay_pil.resize((sw, sh), Image.NEAREST)
        if angle != 0:
            overlay_pil = overlay_pil.rotate(
                angle, expand=True, resample=Image.BICUBIC,
                center=(overlay_pil.width // 2, overlay_pil.height // 2),
                fillcolor=(0, 0, 0, 0)
            )
        if opacity < 1.0:
            opacity = max(0.0, min(1.0, opacity))
            arr = np.array(overlay_pil)
            arr[..., 3] = (arr[..., 3].astype(np.float32) * opacity).astype(np.uint8)
            overlay_pil = Image.fromarray(arr, 'RGBA')
        x = int(center_x - overlay_pil.width // 2)
        y = int(center_y - overlay_pil.height // 2)
        frame_pil = Image.fromarray(frame_np).convert('RGBA')
        frame_pil.paste(overlay_pil, (x, y), overlay_pil)
        return np.array(frame_pil.convert('RGB'))

    def _thug_entry_transform(self, entry, p, base_w, base_h):
        """Given an entry style and animation progress p in [0,1] (0=start,
        1=settled), return (dx, dy, extra_angle, scale) offsets to layer on
        top of an accessory's resting position/size. dx/dy are directional
        offsets away from the resting spot (positive = right/down)."""
        eased = self._thug_ease_out_back(p)
        remaining = 1.0 - min(eased, 1.0)
        settle = min(eased, 1.0)
        if entry == 'left':
            dx = remaining * (base_w * 3.0 + 140)
            dy = 0.0
            extra_angle = remaining * -300.0
            scale = max(0.05, 0.3 + 0.7 * settle)
        elif entry == 'right':
            dx = -remaining * (base_w * 3.0 + 140)
            dy = 0.0
            extra_angle = remaining * 300.0
            scale = max(0.05, 0.3 + 0.7 * settle)
        elif entry == 'bottom':
            dx = 0.0
            dy = remaining * (base_h * 4.0 + 100)
            extra_angle = remaining * 300.0
            scale = max(0.05, 0.3 + 0.7 * settle)
        elif entry == 'rush':
            dx = 0.0
            dy = 0.0
            extra_angle = 0.0
            scale = max(0.05, 0.06 + 0.94 * settle)
        elif entry == 'bounce':
            bounced = self._thug_ease_out_bounce(p)
            dx = 0.0
            dy = (1.0 - bounced) * (base_h * 4.0 + 100)
            extra_angle = 0.0
            scale = max(0.1, 0.4 + 0.6 * min(bounced, 1.0))
        else:  # 'top' (classic drop-and-spin)
            dx = 0.0
            dy = remaining * (base_h * 4.0 + 60)
            extra_angle = remaining * -520.0
            scale = max(0.05, 0.25 + 0.75 * settle)
        return dx, dy, extra_angle, scale

    def _find_eye_center(self, frame, head_cy, head_cx, face_w, face_h):
        h, w = frame.shape[:2]
        face_y0 = head_cy - face_h // 2
        face_x0 = head_cx - face_w // 2
        # Eyes sit in the upper-middle band of a Haar face box. Excluding the
        # hairline/forehead sliver at the very top (and the nose/mouth/chin
        # below) stops eyebrows or hair texture from being mistaken for eyes.
        roi_y0 = max(0, face_y0 + int(face_h * 0.12))
        roi_y1 = min(h, face_y0 + int(face_h * 0.62))
        roi_x0 = max(0, face_x0)
        roi_x1 = min(w, face_x0 + face_w)
        if roi_y1 - roi_y0 < 10 or roi_x1 - roi_x0 < 10:
            return None
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            face_roi = gray[roi_y0:roi_y1, roi_x0:roi_x1]
            eye_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_eye.xml")
            if eye_cascade.empty():
                return None
            eyes = eye_cascade.detectMultiScale(face_roi, 1.1, 4, minSize=(6, 6))
            if len(eyes) >= 2:
                eyes = sorted(eyes, key=lambda e: e[0])
                left = eyes[0]
                right = eyes[-1]
                eye_dist = abs((right[0] + right[2] // 2) - (left[0] + left[2] // 2))
                eye_cx = (left[0] + left[2] // 2 + right[0] + right[2] // 2) // 2 + roi_x0
                eye_cy = (left[1] + left[3] // 2 + right[1] + right[3] // 2) // 2 + roi_y0
                left_cy = left[1] + left[3] // 2
                right_cy = right[1] + right[3] // 2
                left_cx = left[0] + left[2] // 2
                right_cx = right[0] + right[2] // 2
                roll_deg = math.degrees(math.atan2(right_cy - left_cy, right_cx - left_cx))
                # Sanity-check the result against the face box it came from —
                # a stray detection (eyebrow, hair shadow, nostril) tends to
                # sit too high/low or be an implausible distance apart.
                rel_y = (eye_cy - face_y0) / max(face_h, 1)
                if not (0.15 <= rel_y <= 0.65):
                    return None
                if not (0.25 * face_w <= eye_dist <= 0.95 * face_w):
                    return None
                return eye_cy, eye_cx, max(eye_dist, face_w // 4), roll_deg
        except Exception:
            pass
        return None

    def _find_thug_face_box(self, frame, search_bbox=None):
        """Haar-cascade frontal face detection over the FULL frame — returns
        (fx, fy, fw, fh) for the best candidate, or None. Detection always runs
        on the whole image (not a tight crop) because for wide poses — arms
        raised overhead, etc. — a bbox/silhouette crop is mostly background,
        and equalising/searching just that region is *less* reliable than the
        full photo. When `search_bbox` (x, y, w, h) is given, it's used only to
        prefer the candidate face located inside that person's region — so a
        blurry crowd/background face isn't picked over the actual subject —
        falling back to the largest face overall if none fall inside it."""
        h, w = frame.shape[:2]
        try:
            gray_full = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            min_dim = max(20, min(h, w) // 12)

            def run_cascades(gray_img):
                found = []
                for cascade_path in (_HAAR_CASCADE_PATH,):
                    face_cascade = cv2.CascadeClassifier(cascade_path)
                    if face_cascade.empty():
                        continue
                    faces = face_cascade.detectMultiScale(
                        gray_img, scaleFactor=1.05, minNeighbors=4, minSize=(min_dim, min_dim))
                    found.extend(tuple(int(v) for v in f) for f in faces)
                return found

            candidates = run_cascades(cv2.equalizeHist(gray_full))
            if not candidates:
                candidates = run_cascades(gray_full)
            if not candidates:
                return None

            if search_bbox is not None:
                bx, by, bw, bh = search_bbox
                pad_x, pad_y = int(bw * 0.2), int(bh * 0.2)
                x0, y0 = bx - pad_x, by - pad_y
                x1, y1 = bx + bw + pad_x, by + bh + pad_y
                inside = [c for c in candidates
                          if x0 <= (c[0] + c[2] / 2) <= x1 and y0 <= (c[1] + c[3] / 2) <= y1]
                if inside:
                    candidates = inside

            return max(candidates, key=lambda f: f[2] * f[3])
        except Exception:
            return None

    @staticmethod
    def _thug_ease_out_back(p):
        c1, c3 = 1.70158, 2.70158
        p = min(max(p, 0.0), 1.0)
        return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2

    @staticmethod
    def _thug_ease_out_bounce(p):
        n1, d1 = 7.5625, 2.75
        p = min(max(p, 0.0), 1.0)
        if p < 1 / d1:
            return n1 * p * p
        elif p < 2 / d1:
            p -= 1.5 / d1
            return n1 * p * p + 0.75
        elif p < 2.5 / d1:
            p -= 2.25 / d1
            return n1 * p * p + 0.9375
        else:
            p -= 2.625 / d1
            return n1 * p * p + 0.984375

    def _create_thug_life_effect(self, frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask=None, bbox=None, drawn_edges=None, clip_t=0.0,
                                  style='pixel', entry='top', cap_enabled=False,
                                  glasses_override=None, chain_override=None, cap_override=None):
        h, w = frame.shape[:2]
        base = original_mask if original_mask is not None else mask
        mask_bool = (base > 0.3) if base is not None else np.zeros((h, w), dtype=bool)

        # Restrict to the selected person's region when we have one, so a
        # raised arm, a bystander, or crowd in the background can't get
        # mistaken for the subject.
        if bbox is not None:
            bx, by, bw, bh = bbox
            region = np.zeros((h, w), dtype=bool)
            region[max(0, by):min(h, by + bh), max(0, bx):min(w, bx + bw)] = True
            mask_bool = mask_bool & region

        ys, xs = np.where(mask_bool)
        if len(ys) > 10:
            y_top, y_bot = int(ys.min()), int(ys.max())
            person_h = max(y_bot - y_top, 1)
            person_w = max(int(xs.max()) - int(xs.min()), 1)
            median_x = int(np.median(xs))
        elif bbox is not None:
            bx, by, bw, bh = bbox
            y_top, y_bot = by, by + bh
            person_h, person_w = max(bh, 1), max(bw, 1)
            median_x = bx + bw // 2
        else:
            y_top, y_bot = 0, h
            person_h, person_w = h, w
            median_x = w // 2

        # ── Locate the face precisely so glasses fit the actual eyes. Search is
        # restricted to the subject's own silhouette so a face in a blurry
        # crowd/background can't be picked up instead. ──
        if bbox is not None:
            search_box = bbox
        elif len(ys) > 10:
            search_box = (int(xs.min()), y_top, person_w, person_h)
        else:
            search_box = None
        face_box = self._find_thug_face_box(frame, search_bbox=search_box)

        if face_box is not None:
            fx, fy, fw, fh = face_box
            head_cy, head_cx = fy + fh // 2, fx + fw // 2
            eyes = self._find_eye_center(frame, head_cy, head_cx, fw, fh)
            if eyes is not None:
                eye_cy, eye_cx, eye_dist, roll_deg = eyes
                eye_y = eye_cy
                glass_w = int(eye_dist * 2.4)          # span both eyes + temples
                base_angle = max(-25.0, min(25.0, roll_deg))  # follow head tilt, clamped to a sane range
            else:
                eye_y = fy + int(fh * 0.42)             # typical eye line on a face
                eye_cx = fx + fw // 2
                glass_w = int(fw * 1.05)
                base_angle = 0.0
            neck_cx = eye_cx
            neck_y = (fy + fh) + int(fh * 0.35)         # chin + neck offset
            cap_cx = eye_cx
            cap_anchor_y = fy + int(fh * 0.15)          # brim sits just above the eyebrows
        else:
            # No face found (steep angle, motion blur, hand over face, etc.) —
            # fall back to the body silhouette, but stay in a narrow column
            # centered on the torso's median so raised/outstretched arms can't
            # be mistaken for the head (their pixels sit outside this band).
            band_half = max(int(person_w * 0.16), 35)
            band_x0, band_x1 = median_x - band_half, median_x + band_half
            in_band = (xs >= band_x0) & (xs <= band_x1)
            band_rows = np.unique(ys[in_band]) if np.any(in_band) else np.array([], dtype=int)
            head_top = int(band_rows.min()) if len(band_rows) > 5 else y_top

            scan_bottom = min(y_bot, head_top + max(int(person_h * 0.30), 1))
            widths = []
            for row_y in range(head_top, scan_bottom):
                row_pixels = xs[(ys == row_y) & in_band]
                if len(row_pixels) >= 3:
                    widths.append(row_pixels.max() - row_pixels.min())
            head_w_est = int(np.median(widths)) if widths else max(int(w * 0.09), 50)
            head_w_est = max(head_w_est, 50)
            head_h_est = int(head_w_est * 1.3)          # typical face width:height ratio

            eye_cx = median_x
            eye_y = head_top + int(head_h_est * 0.45)   # eyes ~45% down from crown
            neck_cx = eye_cx
            neck_y = head_top + int(head_h_est * 1.15)  # just below the chin
            glass_w = int(head_w_est * 1.05)
            base_angle = 0.0
            cap_cx = eye_cx
            cap_anchor_y = head_top

        glass_w = max(glass_w, 60)
        chain_w = int(glass_w * (1.9 if style == 'pixel' else 1.15))
        cap_w = int(glass_w * 1.5)

        glasses_img = self._draw_thug_glasses(glass_w, glass_w, style=style)
        chain_img = self._draw_gold_chain(chain_w, chain_w, style=style)
        cap_img = self._draw_thug_cap(cap_w, cap_w) if cap_enabled else None
        glass_h = glasses_img.height if glasses_img is not None else int(glass_w * 0.2)
        chain_h = chain_img.height if chain_img is not None else int(chain_w * 0.84)
        cap_h = cap_img.height if cap_img is not None else int(cap_w * 0.6)
        cap_cy = cap_anchor_y - cap_h // 2

        result = frame.copy()
        t = max(0.0, float(clip_t))

        def anim(local_t, anim_dur, base_w, base_h):
            p = min(max(local_t, 0.0) / anim_dur, 1.0) if anim_dur > 0 else 1.0
            adx, ady, aangle, ascale = self._thug_entry_transform(entry, p, base_w, base_h)
            aopacity = min(max(local_t, 0.0) / (anim_dur * 0.4), 1.0) if local_t > 0 else 0.0
            return adx, ady, aangle, ascale, aopacity

        def with_override(cx, cy, angle, scale, override):
            fh_, fv_ = False, False
            if override:
                cx = cx + override.get('dx', 0.0)
                cy = cy + override.get('dy', 0.0)
                angle = angle + override.get('rotation', 0.0)
                scale = scale * override.get('scale', 1.0)
                fh_ = bool(override.get('flip_h', False))
                fv_ = bool(override.get('flip_v', False))
            return cx, cy, angle, scale, fh_, fv_

        # ── Cap: leads the entrance (if enabled) ──
        if cap_img is not None:
            cdx, cdy, cangle, cscale, copac = anim(t, 0.5, cap_w, cap_h)
            cx, cy, cang, csc, cfh, cfv = with_override(
                cap_cx + cdx, cap_cy + cdy, base_angle + cangle, cscale, cap_override)
            result = self._overlay_at_center(result, cap_img, cx, cy, angle=cang, scale=csc,
                                              opacity=copac, flip_h=cfh, flip_v=cfv)

        # ── Glasses: land exactly on the eyes ──
        gdx, gdy, gangle, gscale, gopac = anim(t - 0.10, 0.5, glass_w, glass_h)
        gx, gy, gang, gsc, gfh, gfv = with_override(
            eye_cx + gdx, eye_y + gdy, base_angle + gangle, gscale, glasses_override)
        if glasses_img is not None:
            result = self._overlay_at_center(result, glasses_img, gx, gy, angle=gang, scale=gsc,
                                              opacity=gopac, flip_h=gfh, flip_v=gfv)

        # ── Chain: settles around the neck last ──
        chdx, chdy, changle, chscale, chopac = anim(t - 0.22, 0.55, chain_w, chain_h)
        chx, chy, chang, chsc, chfh, chfv = with_override(
            neck_cx + chdx, neck_y + chdy, base_angle + changle, chscale, chain_override)
        if chain_img is not None and chopac > 0:
            result = self._overlay_at_center(result, chain_img, chx, chy, angle=chang, scale=chsc,
                                              opacity=chopac, flip_h=chfh, flip_v=chfv)

        return result

    def apply_dreamy_angel_effect(self, frame, item, t):
        if item.get('effect', 'none') != 'gold_outline':
            return frame
        if not self.effect_global_enabled.get():
            return frame

        opacity = float(item.get('effect_opacity', 0.7))
        glow = float(item.get('effect_glow', 0.7))
        variation = item.get('effect_variation', 'ethereal')
        if opacity <= 0 and glow <= 0:
            return frame

        timing = item.get('effect_timing', 'full_clip')
        eff_start = float(item.get('effect_start', 0.0))
        eff_end = float(item.get('effect_end', 5.0))

        if timing == 'custom':
            if t < eff_start or t > eff_end:
                return frame
            eff_dur = eff_end - eff_start
            local_t = t - eff_start
            fade_in = eff_dur * 0.20
            fade_out = eff_dur * 0.20
            if local_t < fade_in:
                time_factor = local_t / fade_in if fade_in > 0 else 0.0
            elif local_t > (eff_dur - fade_out):
                remain = eff_dur - local_t
                time_factor = remain / fade_out if fade_out > 0 else 0.0
            else:
                time_factor = 1.0
        else:
            time_factor = 1.0

        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame

        # Use person-specific mask when a person is selected,
        # otherwise fall back to full MediaPipe segmentation mask
        selected_id = int(item.get('effect_selected_person', -1))
        if selected_id >= 0 or selected_id == -2:
            mask = self._get_selected_person_mask(frame, item, t=t)
        else:
            mask = self._get_mediapipe_mask(frame)
            # If MediaPipe unavailable, auto-detect center person and generate mask
            if mask is None:
                persons = self._detect_all_persons(frame)
                if persons:
                    # Pick the person closest to frame center
                    cy, cx = h // 2, w // 2
                    best = min(persons, key=lambda p: (
                        (p['center'][0] - cy) ** 2 + (p['center'][1] - cx) ** 2))
                    mask = self._generate_mask_from_bbox(frame, best['bbox'])

        if mask is None:
            return frame

        # Skip effect if mask is empty (person not found in this frame)
        if mask.max() < 0.01:
            return frame

        # Ensure mask matches frame size
        if mask.shape[:2] != (h, w):
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)

        original_mask = mask.copy()
        painting = item.get('effect_mask_painting')
        if painting is not None and item.get('effect_mask_user_edited', False):
            ph, pw = painting.shape[:2]
            if ph != h or pw != w:
                paint_resized = cv2.resize(painting, (w, h), interpolation=cv2.INTER_LINEAR)
            else:
                paint_resized = painting
            mask = mask * np.clip(paint_resized, 0, 1)

        color_name = item.get('effect_color_variation', 'Gold (Default)')
        palette_entry = self.COLOR_PALETTE.get(color_name, ((255, 200, 50), (200, 140, 20)))
        color_inner, color_outer = palette_entry

        if variation == 'ethereal':
            result = self._create_god_ray_effect(frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask)
        elif variation == 'neon':
            result = self._create_ethereal_effect(frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask)
        elif variation == 'spacy_game_rays':
            result = self._create_brilliance_effect(frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask)
        elif variation == 'gabriel_rays':
            result = self._create_kaka_effect(frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask)
        elif variation == 'angel_rays':
            bbox = None
            if selected_id >= 0:
                yolo_persons = self._yolo_track(frame)
                if yolo_persons:
                    for p in yolo_persons:
                        if p['id'] == selected_id:
                            bbox = p['bbox']
                            break
            result = self._create_holy_aura_effect(frame, mask, color_inner, color_outer, opacity, glow, time_factor, original_mask, bbox)
        else:
            return frame

        # Overlay drawn mask edges on top of result (outside inv_mask, so always visible)
        drawn = item.get('effect_drawn_mask')
        if drawn is not None and item.get('effect_mask_user_edited', False):
            dh, dw = drawn.shape[:2]
            if dh != h or dw != w:
                drawn_resized = cv2.resize(drawn, (w, h), interpolation=cv2.INTER_LINEAR)
            else:
                drawn_resized = drawn
            drawn_u8 = (np.clip(drawn_resized, 0, 1) * 255).astype(np.uint8)
            de = cv2.Canny(drawn_u8, 20, 80)
            de = cv2.dilate(de, np.ones((2, 2), np.uint8), iterations=1)
            if de.max() > 0:
                de_f = cv2.GaussianBlur(de, (5, 5), 0).astype(np.float32) / 255.0
                result_f = result.astype(np.float32)
                color_f = np.array(color_inner, dtype=np.float32)
                result_f += de_f[..., np.newaxis] * color_f * float(glow) * float(time_factor) * 3.0
                result = np.clip(result_f, 0, 255).astype(np.uint8)

        return result

    def apply_thug_life_effect(self, frame, item, t):
        if not item.get('effect_thug_life_enabled', False):
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame
        selected_id = int(item.get('effect_selected_person', -1))
        if selected_id >= 0 or selected_id == -2:
            mask = self._get_selected_person_mask(frame, item, t=t)
        else:
            mask = self._get_mediapipe_mask(frame)
            if mask is None:
                persons = self._detect_all_persons(frame)
                if persons:
                    cy_mid, cx_mid = h // 2, w // 2
                    best = min(persons, key=lambda p: (
                        (p['center'][0] - cy_mid) ** 2 + (p['center'][1] - cx_mid) ** 2))
                    mask = self._generate_mask_from_bbox(frame, best['bbox'])
        if mask is None or mask.max() < 0.01:
            return frame
        if mask.shape[:2] != (h, w):
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
        original_mask = mask.copy()
        bbox = None
        if selected_id >= 0:
            yolo_persons = self._yolo_track(frame)
            if yolo_persons:
                for p in yolo_persons:
                    if p['id'] == selected_id:
                        bbox = p['bbox']
                        break
        result = self._create_thug_life_effect(
            frame, mask, None, None, 0, 0, 1.0, original_mask, bbox=bbox, clip_t=t,
            style=item.get('thug_style', 'realistic'),
            entry=item.get('thug_entry', 'top'),
            cap_enabled=item.get('thug_cap_enabled', True),
            glasses_override=item.get('thug_glasses_override'),
            chain_override=item.get('thug_chain_override'),
            cap_override=item.get('thug_cap_override'))
        return result

    def _get_mediapipe_edges(self, frame):
        mask = self._get_mediapipe_mask(frame)
        if mask is None:
            return np.zeros((frame.shape[0], frame.shape[1]), dtype=np.float32)
        mask_uint8 = (mask * 255).astype(np.uint8)
        edges = cv2.Canny(mask_uint8, 30, 90)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
        edges = cv2.GaussianBlur(edges, (3, 3), 0)
        return edges.astype(np.float32) / 255.0

    def _generate_mask_from_bbox(self, frame, bbox):
        """Generate a person mask from a bounding box using GrabCut + contour fallback.
        Used when YOLO and MediaPipe masks are unavailable."""
        h, w = frame.shape[:2]
        x, y, bw, bh = bbox
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(w, x + bw)
        y1 = min(h, y + bh)
        if x1 - x0 < 10 or y1 - y0 < 10:
            return None
        mask_out = np.zeros((h, w), dtype=np.float32)
        try:
            bgd_model = np.zeros((1, 64), np.float64)
            fgd_model = np.zeros((1, 64), np.float64)
            gc_mask = np.zeros((h, w), np.uint8)
            pad_x = int((x1 - x0) * 0.1)
            pad_y = int((y1 - y0) * 0.1)
            rect = (max(0, x0 - pad_x), max(0, y0 - pad_y),
                    min(w, x1 - x0 + 2 * pad_x), min(h, y1 - y0 + 2 * pad_y))
            rect = tuple(max(1, v) for v in rect)
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            cv2.grabCut(frame_bgr, gc_mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT)
            fg_mask = np.where((gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 1.0, 0.0).astype(np.float32)
            fg_region = fg_mask[y0:y1, x0:x1]
            if fg_region.sum() < (x1 - x0) * (y1 - y0) * 0.05:
                raise ValueError("GrabCut too sparse")
            mask_out[y0:y1, x0:x1] = fg_region
            # Smooth the mask to remove jagged edges before any outline drawing
            mask_out = cv2.GaussianBlur(mask_out, (11, 11), 0)
            mask_out = (mask_out > 0.3).astype(np.float32) * mask_out  # tighten threshold then re-blur
            mask_out = cv2.GaussianBlur(mask_out, (7, 7), 0)
            return mask_out
        except Exception:
            pass
        try:
            roi = frame[y0:y1, x0:x1]
            if roi.size == 0:
                return None
            hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
            lower_skin = np.array([0, 20, 70])
            upper_skin = np.array([20, 255, 255])
            skin_mask = cv2.inRange(hsv, lower_skin, upper_skin)
            lower_dark = np.array([0, 0, 0])
            upper_dark = np.array([180, 255, 80])
            dark_mask = cv2.inRange(hsv, lower_dark, upper_dark)
            combined = cv2.bitwise_or(skin_mask, dark_mask)
            kernel = np.ones((5, 5), np.uint8)
            combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=3)
            combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel, iterations=1)
            contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                # Smooth the contour by approximating it
                epsilon = 0.005 * cv2.arcLength(largest, True)
                largest = cv2.approxPolyDP(largest, epsilon, True)
                fill_mask = np.zeros_like(combined)
                cv2.drawContours(fill_mask, [largest], -1, 255, -1)
                mask_out[y0:y1, x0:x1] = fill_mask.astype(np.float32) / 255.0
            else:
                mask_out[y0:y1, x0:x1] = 1.0
            mask_out = cv2.GaussianBlur(mask_out, (11, 11), 0)
            mask_out = (mask_out > 0.3).astype(np.float32) * mask_out
            mask_out = cv2.GaussianBlur(mask_out, (7, 7), 0)
            return mask_out
        except Exception:
            pass
        mask_out[y0:y1, x0:x1] = 1.0
        mask_out = cv2.GaussianBlur(mask_out, (7, 7), 0)
        return mask_out

    def _detect_all_persons(self, frame):
        h, w = frame.shape[:2]
        persons = []
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            hog = cv2.HOGDescriptor()
            hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            rects, weights = hog.detectMultiScale(gray, winStride=(8, 8),
                                                  padding=(4, 4), scale=1.03)
            for (x, y, pw, ph), wt in zip(rects, weights):
                if pw * ph > (h * w) * 0.008:
                    # Filter: people are typically taller than wide (aspect ratio 0.3-0.8)
                    aspect = pw / max(1, ph)
                    if aspect > 1.2 or aspect < 0.15:
                        continue
                    # Filter: must be reasonably sized (at least 30px each dim)
                    if pw < 30 or ph < 30:
                        continue
                    # Filter: weight confidence
                    if float(wt) < 0.3:
                        continue
                    persons.append({
                        'bbox': (int(x), int(y), int(pw), int(ph)),
                        'center': (int(y + ph // 2), int(x + pw // 2)),
                        'weight': float(wt),
                        'area': pw * ph,
                    })
            persons.sort(key=lambda p: p['area'], reverse=True)
        except Exception:
            pass
        if not persons:
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                face_cascade = cv2.CascadeClassifier(
                    _HAAR_CASCADE_PATH
                )
                faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(30, 30))
                for (fx, fy, fw, fh) in faces:
                    # Expand face bbox downward to include upper body (2.5x height)
                    body_h = int(fh * 2.5)
                    persons.append({
                        'bbox': (int(fx), int(fy), int(fw), body_h),
                        'center': (int(fy + body_h // 2), int(fx + fw // 2)),
                        'weight': 1.0,
                        'area': fw * body_h,
                    })
                persons.sort(key=lambda p: p['area'], reverse=True)
            except Exception:
                pass
        if not persons:
            persons.append({
                'bbox': (max(0, w // 2 - w // 8), max(0, h // 4), w // 4, int(h * 0.66)),
                'center': (h // 2, w // 2),
                'weight': 1.0,
                'area': (w // 4) * int(h * 0.66),
            })
        return persons

    def _get_transformed_frame(self, item):
        """Get the frame exactly as displayed in the preview (after rotation,
        auto-rotate, smart-fill). This ensures click coordinates match detection."""
        frame = self._get_preview_frame(item)
        if frame is None:
            return None
        rot = item.get('rotation', 0)
        if rot == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif rot == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif rot == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if item.get('flip_h', False):
            frame = cv2.flip(frame, 1)
        if item.get('flip_v', False):
            frame = cv2.flip(frame, 0)
        h, w = frame.shape[:2]
        is_mobile = (self.format_var.get() == "mobile")
        target_w = 540 if is_mobile else 960
        target_h = 960 if is_mobile else 540
        if self.auto_rotate_var.get():
            if target_w > target_h and w < h:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                h, w = frame.shape[:2]
            elif target_w < target_h and w > h:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                h, w = frame.shape[:2]
        if self.smart_fill_var.get():
            sf = max(target_w / w, target_h / h)
            frame = cv2.resize(frame, (int(w * sf), int(h * sf)), interpolation=cv2.INTER_LINEAR)
            h, w = frame.shape[:2]
            x0 = (w - target_w) // 2
            y0 = (h - target_h) // 2
            frame = frame[y0:y0 + target_h, x0:x0 + target_w]
        else:
            sf = min(target_w / w, target_h / h)
            frame = cv2.resize(frame, (int(w * sf), int(h * sf)), interpolation=cv2.INTER_LINEAR)
        return frame

    # ─────────────────────────────────────────────────────────────────────
    # LOCAL correlation tracking -- the primary frame-to-frame continuity
    # mechanism for Motion Track / outline effects.
    #
    # The previous approach re-detected every candidate object in the WHOLE
    # frame each time and picked whichever one's appearance (a color
    # histogram) best matched the selected target. In a scene with many
    # small, similarly-dressed subjects (e.g. teammates in identical kits,
    # each only a dozen-odd pixels tall in a wide broadcast shot), that
    # histogram carries almost no distinguishing information, so it would
    # regularly "match" the wrong, nearby person just as confidently as the
    # right one.
    #
    # This searches for the exact pixel pattern of the originally-selected
    # patch, but ONLY within a small window around where the object is
    # predicted to be right now. A lookalike neighbour standing even a
    # short distance away simply never enters the search window, so it
    # can't be picked -- this rules it out by construction, not by tuning
    # a similarity threshold. YOLO detection is still used for the initial
    # selection, for periodically validating/re-anchoring box size, and for
    # re-acquiring the target after it's briefly out of frame or occluded.
    # ─────────────────────────────────────────────────────────────────────

    def _anchor_tracking_at(self, item, frame, center, bbox, is_correction):
        """(Re)anchor the tracking chain at the CURRENT frame with the
        given center/bbox.

        If `is_correction`: this is a manual fix to an ALREADY-selected,
        already-tracked object. Keyframes BEFORE this frame are left
        untouched -- whatever arrow position earlier frames already have
        stays exactly as it was -- while keyframes AT OR AFTER this frame
        are cleared, since they were derived from the trajectory this
        correction is fixing, and the chain needs to continue fresh from
        the corrected point onward.

        If not a correction (a brand new selection of a person/object):
        the entire tracking history is discarded and replaced with just
        this one keyframe, since carrying over history from a DIFFERENT
        previous selection would corrupt the new one's tracking.

        Returns the frame_idx this was anchored at."""
        frame_idx0 = int(self.playhead_t.get() * 30)
        existing = item.get('effect_tracking_keyframes', {}) if is_correction else {}
        if is_correction:
            existing = {k: v for k, v in existing.items() if int(k) < frame_idx0}
        existing[str(frame_idx0)] = {
            'center': center,
            'bbox': bbox,
            'time': self.playhead_t.get(),
            'ref_w': frame.shape[1],
            'ref_h': frame.shape[0],
        }
        item['effect_tracking_keyframes'] = existing
        item['effect_track_miss_streak'] = 0
        item['effect_last_match_frame_idx'] = frame_idx0
        item['effect_track_template_patch'], item['effect_track_template_inner_offset'] = self._extract_track_template_patch(frame, bbox)
        item['effect_track_template_ref_wh'] = (frame.shape[1], frame.shape[0])
        return frame_idx0

    def _extract_track_template_patch(self, frame, bbox, pad_frac=0.6):
        """Grab a grayscale patch around `bbox`, expanded by `pad_frac` on
        each side, to use as the local tracking template.

        The padding matters: a tight crop of a sports jersey is close to
        a single flat color, which carries almost no information to tell
        two similarly-dressed players apart. The area immediately around
        the person -- the specific patch of grass, a line marking, a
        shadow -- is far more spatially unique, and correlating against
        that context is what actually anchors the match to the right
        individual instead of any similarly-colored blob nearby.

        Returns (patch_gray, inner_offset), where inner_offset =
        (ox, oy, obw, obh) locates the ORIGINAL (unpadded) bbox within
        the returned patch, so a later match on the padded patch can be
        converted back to the object's own tight bbox. Returns (None,
        None) if the region is degenerate."""
        try:
            x, y, bw, bh = bbox
            h, w = frame.shape[:2]
            pad_x = max(4, int(bw * pad_frac))
            pad_y = max(4, int(bh * pad_frac))
            x0, y0 = max(0, int(x - pad_x)), max(0, int(y - pad_y))
            x1, y1 = min(w, int(x + bw + pad_x)), min(h, int(y + bh + pad_y))
            if x1 - x0 < 6 or y1 - y0 < 6:
                return None, None
            patch = frame[y0:y1, x0:x1]
            gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY) if patch.ndim == 3 else patch
            inner_offset = (int(x - x0), int(y - y0), int(bw), int(bh))
            return gray.copy(), inner_offset
        except Exception as _e:
            print("[LOCAL-TRACK] template extraction error:", _e)
            return None, None

    def _template_track_local(self, frame, template_gray, search_center, search_radius, upsample=3):
        """Locate `template_gray` inside a SMALL window around
        `search_center` (cx, cy) using normalized cross-correlation, biased
        toward the window's center. Without that bias, a same-coloured
        neighbour who has drifted into the edge of the (small) search
        window can still occasionally out-correlate the actual tracked
        object if lighting/pose happens to line up better there -- the
        bias keeps the match "pinned" to where the object is predicted to
        be unless the edge candidate is a MUCH better match, not just a
        marginally better one.

        `upsample`: both the window and template are enlarged by this
        factor (cubic interpolation) before correlating. For a small
        object (a dozen-odd px), the native pixel grid only offers that
        many discrete candidate positions -- upsampling recovers
        meaningfully finer (near sub-pixel) localization instead of being
        capped by raw pixel resolution. The returned bbox is in ORIGINAL
        (non-upsampled) pixel coordinates.

        Returns {'bbox': (x,y,w,h), 'score': float} or None.
        `score` is the RAW (unbiased) correlation, roughly [-1, 1]."""
        if template_gray is None or template_gray.size == 0:
            return None
        th, tw = template_gray.shape[:2]
        if th < 3 or tw < 3:
            return None
        h, w = frame.shape[:2]
        cx, cy = search_center
        win_half_w = int(tw / 2 + search_radius)
        win_half_h = int(th / 2 + search_radius)
        x0 = max(0, int(cx - win_half_w))
        y0 = max(0, int(cy - win_half_h))
        x1 = min(w, int(cx + win_half_w))
        y1 = min(h, int(cy + win_half_h))
        if x1 - x0 < tw or y1 - y0 < th:
            return None
        try:
            window = frame[y0:y1, x0:x1]
            window_gray = cv2.cvtColor(window, cv2.COLOR_RGB2GRAY) if window.ndim == 3 else window

            up = max(1, int(upsample))
            if up > 1:
                window_up = cv2.resize(window_gray, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC)
                template_up = cv2.resize(template_gray, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC)
            else:
                window_up, template_up = window_gray, template_gray
            tuh, tuw = template_up.shape[:2]
            if window_up.shape[0] < tuh or window_up.shape[1] < tuw:
                window_up, template_up, up = window_gray, template_gray, 1
                tuh, tuw = template_up.shape[:2]

            result = cv2.matchTemplate(window_up, template_up, cv2.TM_CCOEFF_NORMED)
            rh, rw = result.shape
            # result[i, j] is the match score for the (upsampled) template's
            # top-left placed at upsampled-window-local (j, i). Bias toward
            # the predicted top-left position (also in upsampled units)
            # before picking the winner -- but scale the bias so its max
            # penalty (at the window's edge) is a fixed, modest amount
            # regardless of window size. A flat per-pixel rate is fine for
            # a large window, but for the small windows used on small
            # objects (the common case here) it becomes strong enough to
            # outweigh genuine motion entirely, punishing the object for
            # actually moving and anchoring the tracker to one spot instead
            # of following it.
            pred_x = ((cx - x0) - tw / 2.0) * up
            pred_y = ((cy - y0) - th / 2.0) * up
            yy, xx = np.mgrid[0:rh, 0:rw]
            dist = np.sqrt((xx - pred_x) ** 2 + (yy - pred_y) ** 2) / up
            bias_coeff = 0.10 / max(search_radius, 1)
            biased = result - bias_coeff * dist
            my, mx = np.unravel_index(np.argmax(biased), biased.shape)
            score = float(result[my, mx])
            bbox = (int(round(x0 + mx / up)), int(round(y0 + my / up)), tw, th)
            return {'bbox': bbox, 'score': score}
        except Exception as _e:
            print("[LOCAL-TRACK] template match error:", _e)
            return None

    def _verify_local_context(self, item, frame, position, radius=14):
        """Quick correlation check: does the immediate surroundings at
        `position` (cx, cy) actually match the stored tracking patch?

        Used as a VETO on Stage 2 (whole-frame YOLO + appearance-histogram)
        matches. A colour histogram on a tiny, near-flat-coloured crop
        can't reliably tell two similarly-dressed people apart -- that's
        exactly what let Stage 2 occasionally lock onto the wrong nearby
        person on the rare frame where Stage 1's tight local search missed
        (motion blur, a fast movement, brief occlusion) and control fell
        back to the weaker whole-frame path. This re-checks the candidate
        Stage 2 picked against the same context-rich patch Stage 1 uses --
        the specific surrounding grass/lines/shadows at the WRONG person's
        position generally won't correlate well even when their jersey
        colour does.

        The radius here is deliberately a bit looser than Stage 1's own
        search: a YOLO detection's center is coarser than a correlation
        match, so a genuinely correct Stage 2 candidate can legitimately
        sit a few pixels from the "ideal" spot -- too tight a radius here
        would fail correct matches, not just wrong ones, causing the arrow
        to disappear more than it should.

        Returns a correlation score in roughly [-1, 1], or None if there's
        no stored patch to check against (e.g. right after selection)."""
        template_patch = item.get('effect_track_template_patch')
        if template_patch is None:
            return None
        h, w = frame.shape[:2]
        patch_ref_w, patch_ref_h = item.get('effect_track_template_ref_wh', (None, None))
        match_patch = template_patch
        if patch_ref_w and patch_ref_h and (patch_ref_w != w or patch_ref_h != h):
            psx, psy = w / patch_ref_w, h / patch_ref_h
            new_tw = max(3, int(template_patch.shape[1] * psx))
            new_th = max(3, int(template_patch.shape[0] * psy))
            try:
                match_patch = cv2.resize(template_patch, (new_tw, new_th), interpolation=cv2.INTER_LINEAR)
            except Exception:
                match_patch = template_patch
        hit = self._template_track_local(frame, match_patch, position, search_radius=radius, upsample=3)
        return hit['score'] if hit else None

    def _maybe_refresh_track_template(self, item, frame, bbox, score=None):
        """Adaptively refresh the local-tracking patch on confident matches
        so it keeps up with gradual pose/scale/lighting changes. Only
        refreshes on a strong score so a marginal/uncertain match can't
        slowly drag the template toward the wrong object."""
        if score is not None and score < 0.55:
            return
        new_patch, new_offset = self._extract_track_template_patch(frame, bbox)
        if new_patch is not None:
            item['effect_track_template_patch'] = new_patch
            item['effect_track_template_inner_offset'] = new_offset
            item['effect_track_template_ref_wh'] = (frame.shape[1], frame.shape[0])

    def _get_person_appearance(self, frame, bbox):
        """Extract appearance features of an object from a bounding box.
        Returns a dict with color histogram, edge pattern, face features (if person),
        and spatial info used for matching across frames."""
        h, w = frame.shape[:2]
        x, y, bw, bh = bbox
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(w, x + bw)
        y1 = min(h, y + bh)
        if x1 - x0 < 5 or y1 - y0 < 5:
            return None

        obj_region = frame[y0:y1, x0:x1]

        # --- Face detection inside the object bbox (works for people, optional) ---
        face_hist = None
        face_rect = None
        face_embedding = None
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            face_cascade = cv2.CascadeClassifier(_HAAR_CASCADE_PATH)
            faces = face_cascade.detectMultiScale(gray[y0:y1, x0:x1], 1.1, 4, minSize=(20, 20))
            if len(faces) > 0:
                fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                face_rect = (x0 + fx, y0 + fy, fw, fh)
                face_region = frame[y0 + fy:y0 + fy + fh, x0 + fx:x0 + fx + fw]
                if face_region.size > 0:
                    hsv_face = cv2.cvtColor(face_region, cv2.COLOR_RGB2HSV)
                    face_hist = cv2.calcHist([hsv_face], [0, 1, 2], None, [16, 8, 4], [0, 180, 0, 256, 0, 256])
                    cv2.normalize(face_hist, face_hist, 0, 1, cv2.NORM_MINMAX)
                    gray_face = cv2.cvtColor(face_region, cv2.COLOR_RGB2GRAY)
                    face_embedding = cv2.resize(gray_face, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        except Exception:
            pass

        # --- Full object color histogram (works for ANY object: ball, car, person, etc.) ---
        obj_hist = None
        if obj_region.size > 0:
            hsv_obj = cv2.cvtColor(obj_region, cv2.COLOR_RGB2HSV)
            obj_hist = cv2.calcHist([hsv_obj], [0, 1], None, [12, 8], [0, 180, 0, 256])
            cv2.normalize(obj_hist, obj_hist, 0, 1, cv2.NORM_MINMAX)

        # --- Edge shape template ---
        gray_obj = cv2.cvtColor(obj_region, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray_obj, 50, 150)
        edge_template = cv2.resize(edges, (48, 80), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

        return {
            'face_hist': face_hist,
            'face_embedding': face_embedding,
            'face_rect': face_rect,
            'body_hist': obj_hist,
            'edge_template': edge_template,
            'bbox': bbox,
            'center': (y0 + (y1 - y0) // 2, x0 + (x1 - x0) // 2),
            'size': (bw, bh),
            'area': bw * bh,
        }

    def _match_person_to_template(self, frame, candidates, template, last_center=None, face_buffer=None, max_spatial_dist=None):
        """Match detected person candidates against stored appearance template.
        Returns the best matching index and its confidence score.
        last_center: (cy, cx) of the person's position in the previous frame,
        used for spatial continuity — rejects matches that jump too far.
        max_spatial_dist: override for how far (in px) a candidate may be
        from last_center and still be considered. Callers should pass a
        SIZE-AWARE value — a fixed fraction of the whole frame is far too
        permissive in a wide shot with many small, similarly-dressed
        subjects (e.g. a football broadcast angle): it lets a same-team
        player on the other side of the pitch outscore the actual tracked
        person just by having a marginally better colour-histogram match on
        a tiny, low-detail crop.
        face_buffer: list of past face appearance samples for multi-scale matching."""
        if template is None or not candidates:
            return -1, 0.0

        if face_buffer is None:
            face_buffer = []

        h, w = frame.shape[:2]
        if max_spatial_dist is None:
            max_spatial_dist = max(h, w) * 0.4

        best_idx = -1
        best_score = -1.0

        for i, person in enumerate(candidates):
            app = self._get_person_appearance(frame, person['bbox'])
            if app is None:
                continue

            score = 0.0
            n_features = 0
            feature_scores = []

            # Face embedding: match against ALL buffer entries, take best
            if app.get('face_embedding') is not None:
                best_face_emb_sim = -1.0
                # Check main template
                if template.get('face_embedding') is not None:
                    t_fe = template['face_embedding'].flatten()
                    c_fe = app['face_embedding'].flatten()
                    sim = float(np.sum(t_fe * c_fe)) / max(1.0, float(np.sqrt(np.sum(t_fe**2) * np.sum(c_fe**2))))
                    best_face_emb_sim = max(best_face_emb_sim, sim)
                # Check all buffer entries (different scales/angles)
                for buf_entry in face_buffer:
                    if buf_entry.get('face_embedding') is not None:
                        t_fe = buf_entry['face_embedding'].flatten()
                        c_fe = app['face_embedding'].flatten()
                        sim = float(np.sum(t_fe * c_fe)) / max(1.0, float(np.sqrt(np.sum(t_fe**2) * np.sum(c_fe**2))))
                        best_face_emb_sim = max(best_face_emb_sim, sim)
                if best_face_emb_sim >= 0:
                    feature_scores.append(('face_emb', best_face_emb_sim, 0.40))
                    n_features += 1

            # Face histogram: match against ALL buffer entries, take best
            if app.get('face_hist') is not None:
                best_face_sim = -1.0
                if template.get('face_hist') is not None:
                    sim = cv2.compareHist(
                        template['face_hist'].astype(np.float32),
                        app['face_hist'].astype(np.float32),
                        cv2.HISTCMP_CORREL)
                    best_face_sim = max(best_face_sim, sim)
                for buf_entry in face_buffer:
                    if buf_entry.get('face_hist') is not None:
                        sim = cv2.compareHist(
                            buf_entry['face_hist'].astype(np.float32),
                            app['face_hist'].astype(np.float32),
                            cv2.HISTCMP_CORREL)
                        best_face_sim = max(best_face_sim, sim)
                if best_face_sim >= 0:
                    feature_scores.append(('face', best_face_sim, 0.25))
                    n_features += 1

            # Body histogram similarity
            if template.get('body_hist') is not None and app.get('body_hist') is not None:
                body_sim = cv2.compareHist(
                    template['body_hist'].astype(np.float32),
                    app['body_hist'].astype(np.float32),
                    cv2.HISTCMP_CORREL)
                feature_scores.append(('body', body_sim, 0.20))
                n_features += 1

            # Edge template similarity
            if template.get('edge_template') is not None and app.get('edge_template') is not None:
                t_edges = template['edge_template']
                c_edges = app['edge_template']
                edge_sim = float(np.sum(t_edges * c_edges)) / max(1.0, float(np.sqrt(np.sum(t_edges**2) * np.sum(c_edges**2))))
                feature_scores.append(('edge', edge_sim, 0.15))
                n_features += 1

            if n_features < 1:
                continue

            total_weight = sum(w for _, _, w in feature_scores)
            for _, sim, weight in feature_scores:
                score += sim * (weight / total_weight)

            # Spatial continuity bonus: closer to prediction = higher score
            if last_center is not None:
                pcx, pcy = person['center'][1], person['center'][0]
                dy = last_center[0] - pcy
                dx = last_center[1] - pcx
                dist = (dx ** 2 + dy ** 2) ** 0.5
                if dist > max_spatial_dist:
                    continue
                spatial_bonus = 0.6 * (1.0 - dist / max_spatial_dist)
                score += spatial_bonus

            if score > best_score:
                best_score = score
                best_idx = i

        return best_idx, best_score

    def _get_selected_person_mask(self, frame, item, t=None):
        """Get a mask for the selected person across ALL frames.
        Strategy: position-first tracking with appearance tie-breaking.
        Position is the strongest signal — the person can't teleport."""
        selected_id = int(item.get('effect_selected_person', -1))
        if selected_id < 0 and selected_id != -2:
            mask = self._get_mediapipe_mask(frame)
            if mask is not None:
                return mask
            return self._generate_mask_from_bbox(frame, (
                frame.shape[1] // 4, frame.shape[0] // 4,
                frame.shape[1] // 2, frame.shape[0] // 2))

        h, w = frame.shape[:2]
        empty_mask = np.zeros((h, w), dtype=np.float32)

        def _ready_mask(raw_mask, center, bbox):
            m = raw_mask
            if m.shape[:2] != (h, w):
                m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
            return self._trim_mask_overlap(m, center, bbox)

        predicted_center, predicted_bbox = self._predict_person_position(item, cur_w=w, cur_h=h)
        template = item.get('effect_person_template', None)
        has_previous_tracking = len(item.get('effect_tracking_keyframes', {})) > 0

        # ── EXACT KEYFRAME: this frame has a known-correct position ─────
        # already stored -- either the original selection click, or a
        # manual correction (Correct Here). Use it directly rather than
        # re-deriving it via search.
        t_now = t if t is not None else self.playhead_t.get()
        frame_idx_now = int(round(t_now * 30))
        exact_kf = item.get('effect_tracking_keyframes', {}).get(str(frame_idx_now))
        if exact_kf is not None:
            ex_center, ex_bbox = exact_kf.get('center'), exact_kf.get('bbox')
            ex_ref_w, ex_ref_h = exact_kf.get('ref_w'), exact_kf.get('ref_h')
            if ex_ref_w and ex_ref_h and (ex_ref_w != w or ex_ref_h != h):
                sx, sy = w / ex_ref_w, h / ex_ref_h
                ex_center = (ex_center[0] * sy, ex_center[1] * sx)
                ex_bbox = (ex_bbox[0] * sx, ex_bbox[1] * sy, ex_bbox[2] * sx, ex_bbox[3] * sy)
            item['effect_track_miss_streak'] = 0
            item['effect_last_match_frame_idx'] = frame_idx_now
            return self._make_person_bbox_mask(frame, ex_bbox)

        # ── STAGE 1: LOCAL correlation tracking (primary) ────────────────
        # See the note in _get_motion_track_position -- searching only a
        # small window around the predicted position means a similarly-
        # dressed neighbour can't be picked, and unlike YOLO-based
        # reacquisition below, it also works in frames where YOLO itself
        # doesn't detect anything nearby.
        template_patch = item.get('effect_track_template_patch')
        if template_patch is not None and predicted_center is not None:
            # Rescale the patch (and its inner offset) if it was captured
            # at a different resolution than this frame (e.g. preview vs.
            # export) -- see the matching note in _get_motion_track_position.
            inner_offset = item.get('effect_track_template_inner_offset')
            patch_ref_w, patch_ref_h = item.get('effect_track_template_ref_wh', (None, None))
            match_patch = template_patch
            match_offset = inner_offset
            if patch_ref_w and patch_ref_h and (patch_ref_w != w or patch_ref_h != h):
                psx, psy = w / patch_ref_w, h / patch_ref_h
                new_tw = max(3, int(template_patch.shape[1] * psx))
                new_th = max(3, int(template_patch.shape[0] * psy))
                try:
                    match_patch = cv2.resize(template_patch, (new_tw, new_th), interpolation=cv2.INTER_LINEAR)
                    if inner_offset:
                        match_offset = (int(inner_offset[0] * psx), int(inner_offset[1] * psy),
                                         int(inner_offset[2] * psx), int(inner_offset[3] * psy))
                except Exception:
                    match_patch = template_patch

            obj_w, obj_h = (predicted_bbox[2], predicted_bbox[3]) if predicted_bbox else (
                (match_offset[2], match_offset[3]) if match_offset else (match_patch.shape[1], match_patch.shape[0]))
            miss_streak = int(item.get('effect_track_miss_streak', 0))
            widen = 1.0 + min(miss_streak, 6) * 0.35
            search_radius = int(max(min(int(max(obj_w, obj_h) * 1.1), 80), 9) * widen)
            pcy, pcx = predicted_center
            local_hit = self._template_track_local(frame, match_patch, (pcx, pcy), search_radius)
            if local_hit is not None and local_hit['score'] >= 0.42:
                px, py, pw, ph = local_hit['bbox']
                if match_offset:
                    ox, oy, obw, obh = match_offset
                    bx, by, bw, bh = px + ox, py + oy, obw, obh
                else:
                    bx, by, bw, bh = px, py, pw, ph
                cy_hit, cx_hit = by + bh / 2.0, bx + bw / 2.0
                item['effect_track_miss_streak'] = 0
                self._update_tracking_keyframe(item, frame, (cy_hit, cx_hit), (bx, by, bw, bh), match_score=local_hit['score'], t=t)
                return self._make_person_bbox_mask(frame, (bx, by, bw, bh))
            else:
                item['effect_track_miss_streak'] = min(miss_streak + 1, 6)
        # ── STAGE 2: detector + appearance reacquisition (fallback) ──────

        yolo_persons = self._yolo_track(frame)
        if not yolo_persons:
            stored = item.get('effect_person_mask_template')
            if stored is not None and stored.max() > 0:
                if stored.shape[:2] != (h, w):
                    stored = cv2.resize(stored, (w, h), interpolation=cv2.INTER_LINEAR)
                return stored
            return empty_mask

        def _reidentify_and_return(matched_person, match_score=None):
            # VETO: re-check this candidate against the context-rich local
            # patch before accepting it. A colour histogram alone can be
            # fooled by a similarly-dressed neighbour; the specific
            # surrounding grass/lines/shadows at the wrong person's
            # position generally won't correlate well even when their
            # jersey colour does.
            mcy, mcx = matched_person['center']
            verify_score = self._verify_local_context(item, frame, (mcx, mcy))
            if verify_score is not None and verify_score < 0.25:
                print(f"[MASK-TRACK] REJECTED candidate: context_score={verify_score:.3f} < 0.25 -- likely wrong person, keeping last known mask")
                stored = item.get('effect_person_mask_template')
                if stored is not None and stored.max() > 0:
                    if stored.shape[:2] != (h, w):
                        stored = cv2.resize(stored, (w, h), interpolation=cv2.INTER_LINEAR)
                    return stored
                return empty_mask
            self._update_tracking_keyframe(item, frame, matched_person['center'], matched_person['bbox'], match_score=match_score, t=t)
            item['effect_track_miss_streak'] = 0
            if matched_person.get('raw_mask') is not None:
                return _ready_mask(matched_person['raw_mask'], matched_person['center'], matched_person['bbox'])
            return self._make_person_bbox_mask(frame, matched_person['bbox'])

        # Compute distance from each candidate to predicted position
        scored = []
        for p in yolo_persons:
            if predicted_center is not None:
                pcx, pcy = predicted_center[1], predicted_center[0]
                cx, cy = p['center'][1], p['center'][0]
                pos_dist = ((pcx - cx) ** 2 + (pcy - cy) ** 2) ** 0.5
            else:
                pos_dist = 0
            scored.append((p, pos_dist))

        scored.sort(key=lambda x: x[1])

        # Tight, SIZE-AWARE tolerance -- see the note in
        # _get_motion_track_position for why a fixed frame-fraction gate
        # (the old 30-40%) is far too loose for crowded, small-subject
        # scenes and lets the wrong, similarly-dressed person win.
        max_dim = max(h, w)
        ref_w, ref_h = (predicted_bbox[2], predicted_bbox[3]) if predicted_bbox else (None, None)
        ref_diag = (ref_w ** 2 + ref_h ** 2) ** 0.5 if (ref_w and ref_h) else max_dim * 0.04
        max_close_dist = min(max(ref_diag * 4.0, max_dim * 0.05), max_dim * 0.16)
        close_candidates = [(p, d) for p, d in scored if d < max_close_dist]

        if template is not None and len(close_candidates) >= 1:
            face_buffer = item.get('effect_face_buffer', [])
            best_match, best_score = self._match_person_to_template(
                frame, [p for p, _ in close_candidates], template,
                last_center=predicted_center, face_buffer=face_buffer,
                max_spatial_dist=max_close_dist)
            if best_match >= 0 and best_score > 0.15:
                return _reidentify_and_return(close_candidates[best_match][0], best_score)

        if len(close_candidates) == 1:
            return _reidentify_and_return(close_candidates[0][0])

        # Wider search with appearance -- still gated, just a looser radius
        top_candidates = scored[:min(5, len(scored))]
        if template is not None and top_candidates:
            face_buffer = item.get('effect_face_buffer', [])
            best_match, best_score = self._match_person_to_template(
                frame, [p for p, _ in top_candidates], template,
                last_center=predicted_center, face_buffer=face_buffer,
                max_spatial_dist=max_close_dist * 2.0)
            if best_match >= 0 and best_score > 0.25:
                return _reidentify_and_return(top_candidates[best_match][0], best_score)

        # Low confidence — keep using stored template mask instead of switching
        stored = item.get('effect_person_mask_template')
        if stored is not None and stored.max() > 0:
            if stored.shape[:2] != (h, w):
                stored = cv2.resize(stored, (w, h), interpolation=cv2.INTER_LINEAR)
            return stored

        # Absolute last resort: closest person
        matched = scored[0][0]
        return _reidentify_and_return(matched)

    def _color_segment_person(self, frame, click_x, click_y, radius=None):
        """Build a person mask by sampling colors around the click point and
        using HSV back-projection + GrabCut. This avoids MediaPipe noise entirely."""
        h, w = frame.shape[:2]
        if radius is None:
            radius = max(30, min(h, w) // 10)

        # Sample colors from a small patch around the click point
        x0 = max(0, click_x - radius)
        y0 = max(0, click_y - radius)
        x1 = min(w, click_x + radius)
        y1 = min(h, click_y + radius)
        sample_patch = frame[y0:y1, x0:x1]
        if sample_patch.size == 0:
            return np.zeros((h, w), dtype=np.float32)

        # Build 2D HSV histogram (H+S) from the sample patch
        hsv_sample = cv2.cvtColor(sample_patch, cv2.COLOR_RGB2HSV)
        hist = cv2.calcHist([hsv_sample], [0, 1], None, [30, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 255, cv2.NORM_MINMAX)

        # Back-project onto full frame
        hsv_full = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
        back_proj = cv2.calcBackProject([hsv_full], [0, 1], hist, [0, 180, 0, 256], 1.0)

        # Threshold to get binary mask
        _, mask = cv2.threshold(back_proj, 30, 255, cv2.THRESH_BINARY)

        # Morphological cleanup
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=3)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
        mask = cv2.medianBlur(mask, 7)

        # Find connected components, keep the one nearest to click
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        best_label = -1
        best_dist = float('inf')
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 500:
                continue
            cx, cy = centroids[i]
            dist = ((click_x - cx) ** 2 + (click_y - cy) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_label = i
        if best_label < 0:
            return np.zeros((h, w), dtype=np.float32)

        clean = np.zeros((h, w), dtype=np.uint8)
        clean[labels == best_label] = 255

        # GrabCut refinement using the color mask as guide
        comp_x = stats[best_label, cv2.CC_STAT_LEFT]
        comp_y = stats[best_label, cv2.CC_STAT_TOP]
        comp_w = stats[best_label, cv2.CC_STAT_WIDTH]
        comp_h = stats[best_label, cv2.CC_STAT_HEIGHT]
        pad_x = max(15, int(comp_w * 0.15))
        pad_y = max(15, int(comp_h * 0.15))
        rx0 = max(0, comp_x - pad_x)
        ry0 = max(0, comp_y - pad_y)
        rx1 = min(w, comp_x + comp_w + pad_x)
        ry1 = min(h, comp_y + comp_h + pad_y)
        if rx1 - rx0 >= 30 and ry1 - ry0 >= 30:
            try:
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                gc_mask = np.zeros((h, w), np.uint8)
                gc_mask[:] = cv2.GC_BGD
                gc_mask[rx0:rx1, ry0:ry1] = cv2.GC_PR_FGD
                gc_mask[clean > 200] = cv2.GC_FGD
                bgd_model = np.zeros((1, 64), np.float64)
                fgd_model = np.zeros((1, 64), np.float64)
                rect = (rx0, ry0, rx1 - rx0, ry1 - ry0)
                cv2.grabCut(frame_bgr, gc_mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_MASK)
                clean = np.where((gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
            except Exception:
                pass

        result = clean.astype(np.float32) / 255.0
        result = cv2.GaussianBlur(result, (5, 5), 0)
        return result

    def _clean_person_mask(self, mask, reference_center=None, bbox=None, frame=None):
        """Remove noise and produce a tight person mask.
        Uses morphological cleanup, connected-component filtering, and optionally
        GrabCut (when frame+bbox provided) to separate person from background using color."""
        h, w = mask.shape[:2]
        mask_uint8 = (mask * 255).astype(np.uint8)

        # --- Stage 1: Morphological cleanup ---
        erode_k = np.ones((7, 7), np.uint8)
        mask_uint8 = cv2.erode(mask_uint8, erode_k, iterations=3)
        open_k = np.ones((5, 5), np.uint8)
        mask_uint8 = cv2.morphologyEx(mask_uint8, cv2.MORPH_OPEN, open_k, iterations=2)
        mask_uint8 = cv2.medianBlur(mask_uint8, 7)

        # --- Stage 2: Connected-component spatial filter ---
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_uint8, connectivity=8)
        if num_labels <= 1:
            return np.zeros((h, w), dtype=np.float32)

        best_label = -1
        best_score = -1
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 150:
                continue
            cx, cy = centroids[i]
            if bbox is not None:
                bx, by, bw, bh = bbox
                pad_x = int(bw * 0.3)
                pad_y = int(bh * 0.3)
                bx0, by0 = max(0, bx - pad_x), max(0, by - pad_y)
                bx1, by1 = min(w, bx + bw + pad_x), min(h, by + bh + pad_y)
                if cx < bx0 or cx > bx1 or cy < by0 or cy > by1:
                    continue
            if reference_center is not None:
                rcx, rcy = reference_center[1], reference_center[0]
                dist = ((cx - rcx) ** 2 + (cy - rcy) ** 2) ** 0.5
                score = area - dist * 100
            else:
                score = area
            if score > best_score:
                best_score = score
                best_label = i

        if best_label < 0:
            return np.zeros((h, w), dtype=np.float32)

        clean = np.zeros_like(mask_uint8)
        clean[labels == best_label] = mask_uint8[labels == best_label]

        # --- Stage 3: GrabCut refinement (separate person from background by color) ---
        if frame is not None and bbox is not None:
            refined = self._refine_mask_grabcut(frame, clean, bbox)
            if refined is not None:
                clean = refined

        # --- Stage 4: Final polish ---
        close_k = np.ones((9, 9), np.uint8)
        clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, close_k, iterations=2)
        result = clean.astype(np.float32) / 255.0
        result = cv2.GaussianBlur(result, (5, 5), 0)
        return result

    def _refine_mask_grabcut(self, frame, mask_uint8, bbox):
        """Use GrabCut in RECT-ONLY mode to separate person from background by color.
        First erodes aggressively to find the person's core, then uses that tight
        bbox for GrabCut so background objects outside the core are excluded."""
        h, w = frame.shape[:2]

        # Step 1: Erode aggressively to find the person's inner core
        core = cv2.erode(mask_uint8, np.ones((11, 11), np.uint8), iterations=5)
        core = cv2.medianBlur(core, 7)
        core_binary = (core > 127).astype(np.uint8)

        # Step 2: Find the core's bbox (tight around the person only)
        ys, xs = np.where(core_binary > 0)
        if len(xs) < 100 or len(ys) < 100:
            return None
        cx0, cy0 = int(xs.min()), int(ys.min())
        cx1, cy1 = int(xs.max()), int(ys.max())
        core_w = cx1 - cx0
        core_h = cy1 - cy0
        if core_w < 15 or core_h < 15:
            return None

        # Step 3: Expand core bbox with padding for GrabCut context
        pad_x = max(15, int(core_w * 0.2))
        pad_y = max(15, int(core_h * 0.2))
        rx0 = max(0, cx0 - pad_x)
        ry0 = max(0, cy0 - pad_y)
        rx1 = min(w, cx1 + pad_x)
        ry1 = min(h, cy1 + pad_y)
        if rx1 - rx0 < 30 or ry1 - ry0 < 30:
            return None

        try:
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            bgd_model = np.zeros((1, 64), np.float64)
            fgd_model = np.zeros((1, 64), np.float64)
            rect = (rx0, ry0, rx1 - rx0, ry1 - ry0)
            gc_mask = np.zeros((h, w), np.uint8)
            # Pure rectangle mode — GrabCut figures out person by color
            cv2.grabCut(frame_bgr, gc_mask, rect, bgd_model, fgd_model, 8, cv2.GC_INIT_WITH_RECT)
            result = np.where((gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)

            # Step 4: Keep only the largest component overlapping the core center
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(result, connectivity=8)
            core_cx = (cx0 + cx1) // 2
            core_cy = (cy0 + cy1) // 2
            best_label = -1
            best_area = 0
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                if area < 300:
                    continue
                ccx = stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] // 2
                ccy = stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT] // 2
                dist = ((ccx - core_cx) ** 2 + (ccy - core_cy) ** 2) ** 0.5
                max_dist = max(core_w, core_h) * 0.7
                if dist < max_dist and area > best_area:
                    best_area = area
                    best_label = i
            if best_label > 0:
                refined = np.zeros_like(result)
                refined[labels == best_label] = 255
                return refined
        except Exception as e:
            print(f"GrabCut refinement failed: {e}")
        return None

    def _predict_person_position(self, item, cur_w=None, cur_h=None):
        """Chain-reaction position: returns the MOST RECENTLY CONFIRMED
        position, rescaled to the current frame's resolution if needed.
        Each frame's real, matched position becomes the search anchor for
        the next frame -- deliberately NOT velocity-extrapolated. An
        extrapolation guess is a second thing that can be wrong on top of
        the matcher itself, and with the tight local search window used
        elsewhere, the last real position is already a better anchor than
        a guess about where the object "should" be next.
        Returns (predicted_center, predicted_bbox) or (None, None).

        `cur_w`/`cur_h`: dimensions of the frame this will be used
        against. Preview renders at a fixed small canvas (e.g. 960x540)
        while export renders at the actual output resolution (e.g.
        1920x1080) -- a position captured during one and used unscaled
        against the other would be off by exactly that ratio. The latest
        keyframe remembers the (ref_w, ref_h) of the frame it was
        captured at, so it gets rescaled into `cur_w`/`cur_h` space here.
        If `cur_w`/`cur_h` aren't given, the position is returned as
        originally stored (unscaled)."""
        keyframes = item.get('effect_tracking_keyframes', {})
        if not keyframes:
            return None, None
        sorted_keys = sorted(keyframes.keys(), key=lambda k: int(k))
        if len(sorted_keys) == 0:
            return None, None

        kf = keyframes[sorted_keys[-1]]
        center, bbox = kf.get('center'), kf.get('bbox')
        ref_w, ref_h = kf.get('ref_w'), kf.get('ref_h')
        if not (cur_w and cur_h and ref_w and ref_h) or (ref_w == cur_w and ref_h == cur_h):
            return center, bbox
        sx, sy = cur_w / ref_w, cur_h / ref_h
        rc = (center[0] * sy, center[1] * sx) if center else None
        rb = (bbox[0] * sx, bbox[1] * sy, bbox[2] * sx, bbox[3] * sy) if bbox else None
        return rc, rb

    def _update_tracking_keyframe(self, item, frame, center, bbox, match_score=None, t=None):
        """Store or update the latest tracking keyframe and face buffer.
        Only updates on high-confidence matches to prevent drift.
        `t`: the actual time (seconds) of the frame being processed.
        IMPORTANT: this must be the frame's own time, not read from the
        live GUI playhead -- during export, frames are rendered one after
        another with no relation to wherever the playhead slider happens
        to be sitting, so relying on it collapses every exported frame's
        keyframe onto the same timestamp, silently breaking velocity
        prediction and the drift-history entirely. Falls back to the
        live playhead only when `t` isn't supplied (e.g. interactive
        mask-painting UI callers that only ever run against the frame
        currently on screen).
        `match_score`, if given, also gates whether the local-tracking
        template patch gets refreshed from this position (see
        _maybe_refresh_track_template) -- a low-confidence fallback match
        shouldn't be allowed to slowly drag that patch toward the wrong
        object.
        Face features are appended to a rolling buffer (not blended),
        so the system remembers the person at different distances/angles."""
        if t is None:
            t = self.playhead_t.get()
        frame_idx = int(round(t * 30))
        keyframes = item.get('effect_tracking_keyframes', {})

        # Sanity-check the new position against where we predicted this
        # object to be, using a SIZE-AWARE radius (see the note in
        # _get_motion_track_position). A wildly-off position isn't just a
        # bad appearance-template update — if it gets written into the
        # keyframe history unconditionally (the old behaviour), it also
        # poisons the velocity prediction used for every frame after this
        # one, letting a single bad match cascade into a runaway drift
        # instead of self-correcting.
        num_keyframes = len(keyframes)
        h, w = frame.shape[:2]
        predicted_center, _ = self._predict_person_position(item, cur_w=w, cur_h=h)
        max_dim = max(h, w)
        bw, bh = bbox[2], bbox[3]
        ref_diag = (bw ** 2 + bh ** 2) ** 0.5 if (bw and bh) else max_dim * 0.04
        max_drift = min(max(ref_diag * 4.0, max_dim * 0.05), max_dim * 0.16)

        if predicted_center is not None and num_keyframes > 3:
            pcx, pcy = predicted_center[1], predicted_center[0]
            cx, cy = center[1], center[0]
            dist = ((pcx - cx) ** 2 + (pcy - cy) ** 2) ** 0.5
            if dist > max_drift:
                return  # don't let a far-off match corrupt the tracking history

        key = str(frame_idx)
        keyframes[key] = {
            'center': center,
            'bbox': bbox,
            'time': t,
            'ref_w': w,
            'ref_h': h,
        }
        # Keep only last 60 keyframes
        if len(keyframes) > 60:
            sorted_keys = sorted(keyframes.keys(), key=lambda k: int(k))
            for old_key in sorted_keys[:-60]:
                del keyframes[old_key]
        item['effect_tracking_keyframes'] = keyframes
        self._maybe_refresh_track_template(item, frame, bbox, score=match_score)

        # Extract appearance features
        new_app = self._get_person_appearance(frame, bbox)
        if new_app is None:
            return

        # Append new face features to rolling buffer (NOT blended)
        # This preserves distinctive face features at different distances/angles
        face_buffer = item.get('effect_face_buffer', [])
        if new_app.get('face_embedding') is not None or new_app.get('face_hist') is not None:
            face_buffer.append(new_app)
        # Keep max 12 face samples — enough for multi-scale matching, not too old
        if len(face_buffer) > 12:
            face_buffer = face_buffer[-12:]
        item['effect_face_buffer'] = face_buffer

        # Also keep main template updated with body histogram (body changes slowly, blend is fine)
        old_template = item.get('effect_person_template')
        if old_template is not None and new_app.get('body_hist') is not None and old_template.get('body_hist') is not None:
            new_app['body_hist'] = old_template['body_hist'] * 0.8 + new_app['body_hist'] * 0.2
        item['effect_person_template'] = new_app

    def _trim_mask_overlap(self, mask, center, bbox):
        """Light cleanup to remove edge bleed from nearby people.
        Trims overlapping edges and keeps only the main person blob."""
        h, w = mask.shape[:2]
        mask_uint8 = (mask * 255).astype(np.uint8) if mask.dtype != np.uint8 else mask

        # Light erosion to trim thin overlapping edges
        erode_k = np.ones((3, 3), np.uint8)
        trimmed = cv2.erode(mask_uint8, erode_k, iterations=1)

        # Keep only the largest connected component near the person's center
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(trimmed, connectivity=8)
        if num_labels <= 1:
            return mask  # nothing to trim

        cx, cy = center[1], center[0]
        best_label = -1
        best_score = -1
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 200:
                continue
            ccx, ccy = centroids[i]
            dist = ((cx - ccx) ** 2 + (cy - ccy) ** 2) ** 0.5
            # Score: large area + close to center = best
            score = area - dist * 30
            if score > best_score:
                best_score = score
                best_label = i

        if best_label < 0:
            return mask

        clean = np.zeros_like(mask_uint8)
        clean[labels == best_label] = mask_uint8[labels == best_label]
        result = clean.astype(np.float32) / 255.0
        result = cv2.GaussianBlur(result, (3, 3), 0)
        return result

    def _make_person_bbox_mask(self, frame, bbox, full_mask=None):
        """Create a person mask by isolating a bbox region from a full mask,
        or generating a GrabCut mask when no full mask is available."""
        h, w = frame.shape[:2]
        x, y, bw, bh = bbox
        pad_x = int(bw * 0.15)
        pad_y = int(bh * 0.10)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_y)
        x1 = min(w, x + bw + pad_x)
        y1 = min(h, y + bh + pad_y)
        if full_mask is not None:
            person_mask = np.zeros((h, w), dtype=np.float32)
            person_mask[y0:y1, x0:x1] = full_mask[y0:y1, x0:x1]
            # Clean up: keep only the largest connected component in the bbox
            binary = (person_mask > 0.3).astype(np.uint8)
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
            if num_labels > 1:
                # Find largest component that overlaps the bbox center
                cx, cy = x0 + (x1 - x0) // 2, y0 + (y1 - y0) // 2
                best_label = -1
                best_area = 0
                for i in range(1, num_labels):
                    area = stats[i, cv2.CC_STAT_AREA]
                    lx = stats[i, cv2.CC_STAT_LEFT]
                    ly = stats[i, cv2.CC_STAT_TOP]
                    lw = stats[i, cv2.CC_STAT_WIDTH]
                    lh = stats[i, cv2.CC_STAT_HEIGHT]
                    # Check if component center is near the bbox center
                    ccx = lx + lw // 2
                    ccy = ly + lh // 2
                    dist = ((ccx - cx) ** 2 + (ccy - cy) ** 2) ** 0.5
                    max_dist = max(bw, bh) * 0.8
                    if dist < max_dist and area > best_area:
                        best_area = area
                        best_label = i
                if best_label > 0:
                    person_mask = np.zeros((h, w), dtype=np.float32)
                    person_mask[labels == best_label] = full_mask[labels == best_label]
            # Clean and smooth edges
            ref_center = (y0 + (y1 - y0) // 2, x0 + (x1 - x0) // 2)
            person_mask = self._clean_person_mask(person_mask, ref_center, (x, y, bw, bh), frame)
            if person_mask.max() > 0.01:
                return person_mask
        return self._generate_mask_from_bbox(frame, bbox)

    def _track_person_across_frames(self, item, frame_idx, persons, selected_id):
        """Store initial tracking keyframe and template when person is first selected."""
        if selected_id < 0 or selected_id >= len(persons):
            selected_id = 0
        chosen = persons[selected_id]
        frame = self._get_preview_frame(item)
        fw, fh = (frame.shape[1], frame.shape[0]) if frame is not None else (None, None)
        # Start a FRESH tracking history for this newly-selected object.
        # Carrying over keyframes left behind by a PREVIOUS selection
        # corrupts the velocity prediction used every frame afterwards and
        # can pull the tracker toward the old target instead of the one
        # just picked.
        item['effect_tracking_keyframes'] = {
            str(frame_idx): {
                'center': chosen['center'],
                'bbox': chosen['bbox'],
                'person_id': selected_id,
                'time': self.playhead_t.get(),
                'ref_w': fw,
                'ref_h': fh,
            }
        }
        item['effect_track_miss_streak'] = 0
        item['effect_last_match_frame_idx'] = frame_idx
        # Store appearance template for cross-frame tracking
        if frame is not None:
            new_app = self._get_person_appearance(frame, chosen['bbox'])
            if new_app is not None:
                item['effect_person_template'] = new_app
            item['effect_track_template_patch'], item['effect_track_template_inner_offset'] = self._extract_track_template_patch(frame, chosen['bbox'])
            item['effect_track_template_ref_wh'] = (fw, fh)

    def _get_tracked_center_for_frame(self, item, frame_idx):
        keyframes = item.get('effect_tracking_keyframes', {})
        key = str(frame_idx)
        if key in keyframes:
            return keyframes[key]['center'], keyframes[key]['bbox']
        sorted_keys = sorted(keyframes.keys(), key=lambda k: int(k))
        if not sorted_keys:
            return None, None
        before = [k for k in sorted_keys if int(k) <= frame_idx]
        after = [k for k in sorted_keys if int(k) > frame_idx]
        if before and after:
            k0, k1 = before[-1], after[0]
            t0, t1 = int(k0), int(k1)
            alpha = (frame_idx - t0) / max(1, t1 - t0)
            c0 = keyframes[k0]['center']
            c1 = keyframes[k1]['center']
            cy = int(c0[0] + alpha * (c1[0] - c0[0]))
            cx = int(c0[1] + alpha * (c1[1] - c0[1]))
            b0 = keyframes[k0]['bbox']
            bw = int(b0[2] + alpha * (keyframes[k1]['bbox'][2] - b0[2]))
            bh = int(b0[3] + alpha * (keyframes[k1]['bbox'][3] - b0[3]))
            bx = int(cx - bw // 2)
            by = int(cy - bh // 2)
            return (cy, cx), (bx, by, bw, bh)
        elif before:
            k0 = before[-1]
            return keyframes[k0]['center'], keyframes[k0]['bbox']
        else:
            k0 = after[0]
            return keyframes[k0]['center'], keyframes[k0]['bbox']

    def _detect_subject_center(self, frame):
        h, w = frame.shape[:2]
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            face_cascade = cv2.CascadeClassifier(
                _HAAR_CASCADE_PATH
            )
            faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(30, 30))
            if len(faces) > 0:
                largest = max(faces, key=lambda f: f[2] * f[3])
                fx, fy, fw, fh = largest
                return (fy + fh // 2, fx + fw // 2)
        except Exception:
            pass
        gray = frame.mean(axis=2).astype(np.float32)
        Y, X = np.mgrid[:h, :w]
        center_bias = np.exp(-0.5 * (((X - w / 2) / (w * 0.3)) ** 2 + ((Y - h / 2) / (h * 0.3)) ** 2))
        weighted = gray * center_bias
        total = weighted.sum()
        if total > 0:
            cy = int((Y * weighted).sum() / total)
            cx = int((X * weighted).sum() / total)
            return (cy, cx)
        return (h // 2, w // 2)

    def _get_person_outline_edges(self, frame, bbox):
        h, w = frame.shape[:2]
        return self._get_mediapipe_edges(frame)

    def _get_subject_mask(self, frame, cy, cx, bbox=None):
        mask = self._get_mediapipe_mask(frame)
        if mask is not None:
            return mask
        h, w = frame.shape[:2]
        mask = np.zeros((h, w), dtype=np.float32)
        cx_r, cy_r = w // 2, h // 2
        ax, ay = max(1.0, w * 0.25), max(1.0, h * 0.35)
        Y_m, X_m = np.mgrid[:h, :w]
        ellipse = ((X_m - cx_r) / ax) ** 2 + ((Y_m - cy_r) / ay) ** 2
        mask = np.exp(-ellipse / 2.0).astype(np.float32)
        return mask

    def _get_person_edges(self, frame, bbox, cy=None, cx=None):
        return self._get_mediapipe_edges(frame)

    def _get_person_gradient(self, h, w, cy, cx, bbox=None):
        Y, X = np.mgrid[:h, :w]
        diag = np.sqrt(w * w + h * h)
        dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2) / (diag * 0.2)
        person_grad = np.exp(-dist ** 2 / 2.0)
        return person_grad

    def _get_subject_outline(self, subject_mask, frame=None, bbox=None):
        return self._get_mediapipe_edges(frame) if frame is not None else np.zeros_like(subject_mask)

    def _get_outline_from_mask(self, mask, expand=20, blur=8):
        mask_uint8 = (np.clip(mask, 0, 1) * 255).astype(np.uint8)
        edges = cv2.Canny(mask_uint8, 30, 90)
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=max(1, expand // 4))
        if blur > 0:
            edges = cv2.GaussianBlur(edges, (blur * 2 + 1, blur * 2 + 1), 0)
        return edges.astype(np.float32) / 255.0

    def _generate_god_rays(self, h, w, cy, cx, intensity=1.0, num_rays=24, spread=1.0):
        return np.zeros((h, w), dtype=np.float32)

    def _generate_gold_rays(self, h, w, cy, cx, intensity=1.0, num_rays=18):
        return np.zeros((h, w), dtype=np.float32)

    def _apply_gold_rim(self, img, frame, h, w, cy, cx, subject_mask, person_edges, opacity, glow, time_factor):
        return img

    def _apply_gold_glow(self, img, frame, h, w, cy, cx, subject_mask, person_edges, opacity, glow, time_factor):
        return img

    def _apply_gold_halo(self, img, frame, h, w, cy, cx, subject_mask, person_edges, opacity, glow, time_factor):
        return img

    def _apply_gold_glow(self, img, frame, h, w, cy, cx, subject_mask, person_edges, opacity, glow, time_factor):
        bg_mask = (1.0 - subject_mask[..., np.newaxis])
        person_grad = self._get_person_gradient(h, w, cy, cx, None)
        glow_color = np.array([1.0, 0.85, 0.0], dtype=np.float32).reshape(1, 1, 3)
        img = img + person_grad[..., np.newaxis] * glow_color * 180.0 * glow * time_factor * bg_mask

        rays = self._generate_gold_rays(h, w, cy, cx, intensity=glow * time_factor * 0.5, num_rays=14)
        ray_color = np.array([1.0, 0.84, 0.0], dtype=np.float32).reshape(1, 1, 3)
        rays_3ch = rays[..., np.newaxis] * ray_color * 100.0
        img = img + rays_3ch * bg_mask

        gold_color = np.array([1.0, 0.84, 0.0], dtype=np.float32).reshape(1, 1, 3)
        img = img + person_edges[..., np.newaxis] * gold_color * 350.0 * glow * time_factor

        return img

    def _apply_gold_halo(self, img, frame, h, w, cy, cx, subject_mask, person_edges, opacity, glow, time_factor):
        bg_mask = (1.0 - subject_mask[..., np.newaxis])
        Y, X = np.mgrid[:h, :w]
        dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
        diag = np.sqrt(w * w + h * h)
        dist_norm = dist / (diag * 0.5)
        dark_mask = np.exp(-dist_norm ** 2 / (2 * 0.3 ** 2))[..., np.newaxis]
        crush = 1.0 - (1.0 - dark_mask) * 0.5 * opacity * time_factor
        img = img * crush

        halo_y = int(cy * 0.6)
        dx = (X - cx).astype(np.float32)
        dy = (Y - halo_y).astype(np.float32)
        halo_dist = np.sqrt(dx ** 2 + dy ** 2)
        halo_dist_norm = halo_dist / (diag * 0.25)
        halo_ring = np.exp(-((halo_dist_norm - 0.45) ** 2) / (2 * 0.08 ** 2))
        halo_color = np.array([1.0, 0.85, 0.0], dtype=np.float32).reshape(1, 1, 3)
        img = img + halo_ring[..., np.newaxis] * halo_color * 280.0 * glow * time_factor * bg_mask

        gold_color = np.array([1.0, 0.84, 0.0], dtype=np.float32).reshape(1, 1, 3)
        img = img + person_edges[..., np.newaxis] * gold_color * 400.0 * glow * time_factor

        return img

    # ══════════════════════════════════════════════════════════
    #  SAFE NumPy GEOMETRIC TRANSFORM ENGINE
    # ══════════════════════════════════════════════════════════
    def safe_transform(self, base_clip, rot, flip_h, flip_v):
        if rot == 0 and not flip_h and not flip_v: return base_clip
        def process_f(f):
            if flip_h: f = np.fliplr(f)
            if flip_v: f = np.flipud(f)
            if rot == 90: f = np.rot90(f, k=-1, axes=(0, 1))
            elif rot == 180: f = np.rot90(f, k=2, axes=(0, 1))
            elif rot in [270, -90]: f = np.rot90(f, k=1, axes=(0, 1))
            return f
        new_clip = base_clip.fl_image(process_f)
        w, h = base_clip.size if base_clip.size else (0, 0)
        if rot in [90, -90, 270]: new_clip.size = (h, w)
        if getattr(base_clip, 'mask', None):
            new_mask = base_clip.mask.fl_image(process_f)
            if rot in [90, -90, 270]: new_mask.size = (h, w)
            new_clip = new_clip.set_mask(new_mask)
        return new_clip

    # ══════════════════════════════════════════════════════════════════
    #  HOLLYWOOD VFX BACKGROUND GENERATORS 
    # ══════════════════════════════════════════════════════════════════
    def create_warp_background(self, w, h, duration):
        y, x = np.mgrid[:h, :w]; cx, cy = w / 2.0, h / 2.0; dx = x - cx; dy = y - cy; r = np.sqrt(dx**2 + dy**2); theta = np.arctan2(dy, dx); theta_norm = (theta + np.pi) / (2 * np.pi)
        np.random.seed(42); angle_bins = 150; speeds = np.random.uniform(2000, 5000, angle_bins); line_lengths = np.random.uniform(0.3, 0.8, angle_bins)
        has_laser = np.random.rand(angle_bins) > 0.85; faint_laser = np.random.rand(angle_bins) > 0.50
        palette_r = np.array([255, 255, 180, 100]); palette_g = np.array([255, 50, 50, 100]); palette_b = np.array([255, 255, 255, 255]); color_idx = np.random.randint(0, 4, angle_bins)
        intensity_mult = np.where(has_laser, 1.0, np.where(faint_laser, 0.3, 0.0))
        raw_r = palette_r[color_idx] * intensity_mult; raw_g = palette_g[color_idx] * intensity_mult; raw_b = palette_b[color_idx] * intensity_mult
        r_map = np.convolve(np.tile(raw_r, 3), np.ones(3)/3.0, mode='same')[angle_bins:2*angle_bins]; g_map = np.convolve(np.tile(raw_g, 3), np.ones(3)/3.0, mode='same')[angle_bins:2*angle_bins]; b_map = np.convolve(np.tile(raw_b, 3), np.ones(3)/3.0, mode='same')[angle_bins:2*angle_bins]
        angle_idx = (theta_norm * (angle_bins - 1)).astype(int); base_r = np.full((h, w), 10, dtype=np.float32); base_g = np.full((h, w), 2, dtype=np.float32); base_b = np.full((h, w), 30, dtype=np.float32)
        center_glow = np.exp(-0.5 * (r / 200.0)**2); base_r += 120 * center_glow; base_g += 40 * center_glow; base_b += 200 * center_glow
        def make_frame(t):
            my_speeds = speeds[angle_idx]; my_lengths = line_lengths[angle_idx]; phase = (r * 0.005 - my_speeds * t * 0.001) % 1.0; intensity = np.where(phase < my_lengths, 1.0, 0.0) * np.clip((my_lengths - phase) / (my_lengths * 0.3 + 0.001), 0, 1) * np.clip(r / 100.0, 0, 1)
            frame = np.zeros((h, w, 3), dtype=np.float32)
            frame[..., 0] = base_r + r_map[angle_idx] * intensity; frame[..., 1] = base_g + g_map[angle_idx] * intensity; frame[..., 2] = base_b + b_map[angle_idx] * intensity
            for i in range(3):
                hoop_phase = (t / 1.5 + i * (1.0/3.0)) % 1.0; hoop_r = (hoop_phase**2) * (max(w, h)); hoop_alpha = (np.exp(-0.5 * (np.abs(r - hoop_r) / 2.0)**2) + np.exp(-0.5 * (np.abs(r - hoop_r) / 15.0)**2) * 0.5) * np.clip(hoop_r / 100.0, 0, 1) * np.clip(1.0 - hoop_phase, 0, 1)
                frame[..., 0] += 255 * hoop_alpha; frame[..., 1] += 50 * hoop_alpha; frame[..., 2] += 255 * hoop_alpha
            return np.clip(frame, 0, 255).astype(np.uint8)
        return VideoClip(make_frame, duration=duration)

    def create_starry_sky_background(self, w, h, duration):
        y_g, x_g = np.mgrid[0:h, 0:w]; norm_y = (y_g / h).astype(np.float32); norm_x = (x_g / w).astype(np.float32)
        r = (18 * (1 - norm_y) + 15 * norm_y).astype(np.float32); g = (15 * (1 - norm_y) + 30 * norm_y).astype(np.float32); b = (45 * (1 - norm_y) + 70 * norm_y).astype(np.float32)
        dist_left = np.sqrt((norm_x - 0.2)**2 + (norm_y - 1.0)**2); glow_l = np.clip(1.0 - dist_left * 1.2, 0, 1) ** 2
        r += glow_l * 5; g += glow_l * 40; b += glow_l * 50
        dist_right = np.sqrt((norm_x - 0.8)**2 + (norm_y - 1.0)**2); glow_r = np.clip(1.0 - dist_right * 1.5, 0, 1) ** 2
        r += glow_r * 20; g += glow_r * 10; b += glow_r * 40
        bg_base = np.stack([r, g, b], axis=-1); np.random.seed(101); bg_base[np.random.rand(h, w) > 0.9985] = [230, 240, 255]
        N_twinkle = 400; pad = 20; t_x = np.random.randint(pad, w-pad, N_twinkle); t_y = np.random.randint(pad, h-pad, N_twinkle); t_phase = np.random.uniform(0, 2*np.pi, N_twinkle); t_speed = np.random.uniform(2.0, 6.0, N_twinkle); t_size = np.random.choice([1, 2, 3], N_twinkle, p=[0.5, 0.35, 0.15])
        sn_dur = 0.8; sn_start = duration - sn_dur; comet_dur = 2.0; comet_start = max(0.0, sn_start - comet_dur)
        P0 = np.array([w * 1.1, -h * 0.1]); P1 = np.array([w * 0.75, h / 2.0]); P2 = np.array([w / 2.0, h / 2.0])
        def make_frame(t):
            frame = bg_base.copy(); brights = np.clip((np.sin(t * t_speed + t_phase) * 0.5 + 0.5)**2.5 * 600, 0, 255).astype(np.int32)
            mask_1 = t_size >= 1
            if np.any(mask_1):
                ty1, tx1, b1 = t_y[mask_1], t_x[mask_1], brights[mask_1]
                for dy, dx in [(0,0), (0,1), (1,0), (1,1)]:
                    yy = np.clip(ty1+dy, 0, h-1); xx = np.clip(tx1+dx, 0, w-1); frame[yy, xx, 0] = np.clip(frame[yy, xx, 0] + b1, 0, 255); frame[yy, xx, 1] = np.clip(frame[yy, xx, 1] + b1, 0, 255); frame[yy, xx, 2] = np.clip(frame[yy, xx, 2] + b1, 0, 255)
            mask_2 = t_size >= 2
            if np.any(mask_2):
                ty2, tx2, b2 = t_y[mask_2], t_x[mask_2], brights[mask_2] // 2
                for dy, dx in [(-1,0), (-1,1), (2,0), (2,1), (0,-1), (1,-1), (0,2), (1,2)]:
                    yy = np.clip(ty2+dy, 0, h-1); xx = np.clip(tx2+dx, 0, w-1); frame[yy, xx, 0] = np.clip(frame[yy, xx, 0] + b2, 0, 255); frame[yy, xx, 1] = np.clip(frame[yy, xx, 1] + b2, 0, 255); frame[yy, xx, 2] = np.clip(frame[yy, xx, 2] + b2, 0, 255)
            mask_3 = t_size == 3
            if np.any(mask_3):
                ty3, tx3, b3 = t_y[mask_3], t_x[mask_3], brights[mask_3]
                for step in range(2, 14):
                    decay = max(0, 1.0 - (step / 14.0)); b_r = (b3 * decay * 0.7).astype(np.int32); b_g = (b3 * decay * 0.9).astype(np.int32); b_b = (b3 * decay * 1.0).astype(np.int32)
                    for dy, dx in [(-step, 0), (-step, 1), (step+1, 0), (step+1, 1), (0, -step), (1, -step), (0, step+1), (1, step+1)]:
                        yy = np.clip(ty3+dy, 0, h-1); xx = np.clip(tx3+dx, 0, w-1); frame[yy, xx, 0] = np.clip(frame[yy, xx, 0] + b_r, 0, 255); frame[yy, xx, 1] = np.clip(frame[yy, xx, 1] + b_g, 0, 255); frame[yy, xx, 2] = np.clip(frame[yy, xx, 2] + b_b, 0, 255)
            if comet_start <= t <= sn_start:
                p = (t - comet_start) / comet_dur
                cx = (1-p)**2 * P0[0] + 2*(1-p)*p * P1[0] + p**2 * P2[0]; cy = (1-p)**2 * P0[1] + 2*(1-p)*p * P1[1] + p**2 * P2[1]
                vx = 2*(1-p)*(P1[0] - P0[0]) + 2*p*(P2[0] - P1[0]); vy = 2*(1-p)*(P1[1] - P0[1]) + 2*p*(P2[1] - P1[1])
                v_mag = np.sqrt(vx**2 + vy**2); dir_x = -vx / max(v_mag, 1); dir_y = -vy / max(v_mag, 1)
                z_scale = 0.7 - 0.2 * np.sin(p * np.pi) + 1.2 * (p**3)
                dx = x_g - cx; dy = y_g - cy; proj = dx * dir_x + dy * dir_y
                trail_len = 200.0 * max(0.4, z_scale); trail_width = 1.2 * z_scale
                mask = (np.abs(dx * dir_y - dy * dir_x) < trail_width) & (proj > 0) & (proj < trail_len)
                fade = (1.0 - (proj[mask] / trail_len))**2 * np.random.uniform(0.3, 1.0, np.sum(mask))
                frame[mask, 0] = np.clip(frame[mask, 0] + 150 * fade, 0, 255); frame[mask, 1] = np.clip(frame[mask, 1] + 200 * fade, 0, 255); frame[mask, 2] = np.clip(frame[mask, 2] + 255 * fade, 0, 255)
                head_glow = np.exp(-0.5 * ((dx**2 + dy**2) / (1.5 * z_scale)**2)); h_mask = head_glow > 0.05
                frame[h_mask, 0] = np.clip(frame[h_mask, 0] + 255 * head_glow[h_mask], 0, 255); frame[h_mask, 1] = np.clip(frame[h_mask, 1] + 255 * head_glow[h_mask], 0, 255); frame[h_mask, 2] = np.clip(frame[h_mask, 2] + 255 * head_glow[h_mask], 0, 255)
            return np.clip(frame, 0, 255).astype(np.uint8)
        return VideoClip(make_frame, duration=duration)

    def build_tile_lower_third(self, text, target_w, target_h, clip_duration, text_dur):
        fs = 55 if target_w < 1200 else 70
        try: pil_font = ImageFont.truetype("arialbd.ttf", fs)
        except: pil_font = ImageFont.load_default()
        txt_upper = text.upper(); dummy = PIL.Image.new("RGBA", (1, 1)); bbox = ImageDraw.Draw(dummy).textbbox((0, 0), txt_upper, font=pil_font)
        tw = bbox[2] - bbox[0] + 24; th = bbox[3] - bbox[1] + 24
        txt_img = PIL.Image.new("RGBA", (tw, th), (0, 0, 0, 0)); draw = ImageDraw.Draw(txt_img)
        draw.text((12 + 4, 12 + 4), txt_upper, font=pil_font, fill=(0, 0, 0, 180)); draw.text((12, 12), txt_upper, font=pil_font, fill=(255, 223, 115, 255))
        txt_rgba = np.array(txt_img); txt_rgb = txt_rgba[..., :3]; txt_alpha_base = txt_rgba[..., 3].astype(np.float32) / 255.0
        txt_x = (target_w - tw) // 2; txt_y = target_h - 210
        pad_x = int(fs * 2.5); pad_y = int(fs * 0.8); box_w = tw + pad_x * 2; box_h = th + pad_y * 2; box_x = txt_x - pad_x; box_y = txt_y - pad_y
        y_g, x_g = np.mgrid[0:box_h, 0:box_w]; r = box_h / 2.0; cx_L = r; cx_R = box_w - r; cy = r
        dx = np.maximum(0.0, np.maximum(cx_L - x_g, x_g - cx_R)); dy = np.abs(y_g - cy); d = np.sqrt(dx**2 + dy**2)
        alpha_pill = np.clip(r - d, 0, 1); alpha_bracket = np.clip(2.5 - np.abs(d - (r + 4)), 0, 1) * ((x_g < cx_L - r*0.3) | (x_g > cx_R + r*0.3))
        def make_bg_frame(t):
            frame = np.zeros((box_h, box_w, 3), dtype=np.float32); frame[..., 0], frame[..., 1], frame[..., 2] = 55, 10, 20
            wave = 0.5 + 0.5 * np.sin((x_g / box_w) * 5 + t * 0.5); frame[..., 0] += wave * 25; frame[..., 2] += wave * 15
            frame[..., 0] = np.clip(frame[..., 0] + alpha_bracket * 255, 0, 255); frame[..., 1] = np.clip(frame[..., 1] + alpha_bracket * 255, 0, 255); frame[..., 2] = np.clip(frame[..., 2] + alpha_bracket * 255, 0, 255)
            return frame.astype(np.uint8)
        form_t = 0.8; diss_t = 0.8; start_t = 0.5; end_t = start_t + form_t + text_dur
        if end_t + diss_t > clip_duration:
            start_t = 0.2; avail = clip_duration - start_t; form_t = avail * 0.15; diss_t = avail * 0.15; text_dur = avail * 0.7; end_t = start_t + form_t + text_dur
        def wipe_progress(t):
            if t < start_t: return 0.0
            elif t < start_t + form_t: return (t - start_t) / form_t
            elif t < end_t: return 1.0
            elif t < end_t + diss_t: return max(0.0, 1.0 - (t - end_t) / diss_t)
            else: return 0.0
        def make_bg_mask(t):
            wp = wipe_progress(t); full = np.zeros((box_h, box_w), dtype=np.float32); limit = int(wp * box_w)
            if limit > 0:
                full[:, :limit] = np.clip(alpha_pill + alpha_bracket, 0, 1)[:, :limit]
                for i in range(40):
                    if 0 <= limit - 40 + i < box_w: full[:, limit - 40 + i] *= (i / 40.0)
            return full
        def make_text_mask_frame(t):
            wp = wipe_progress(t); full = np.zeros((target_h, target_w), dtype=np.float32)
            if wp <= 0: return full
            ga = txt_alpha_base.copy()
            if t < end_t:
                reveal_x = int(wp * tw)
                for i in range(min(40, tw)):
                    if 0 <= reveal_x + i < tw: ga[:, reveal_x + i] *= (1.0 - i / 40.0)
                ga[:, reveal_x:] = 0.0
            else:
                p = (t - end_t) / diss_t
                np.random.seed(int(t * 20))
                ga = ga * np.where(np.random.rand(th, tw) > np.clip(p*2.0 - np.linspace(0, 1, th).reshape(-1, 1)*0.8, 0, 1), 1.0, 0.0).astype(np.float32)
            y1_d, y2_d = max(0, txt_y), min(target_h, txt_y + th); x1_d, x2_d = max(0, txt_x), min(target_w, txt_x + tw)
            if y1_d < y2_d and x1_d < x2_d: full[y1_d:y2_d, x1_d:x2_d] = ga[y1_d-txt_y:y1_d-txt_y+(y2_d-y1_d), x1_d-txt_x:x1_d-txt_x+(x2_d-x1_d)]
            return full
        _txt_rgb_t = txt_rgb.copy()
        def make_text_frame_t(t):
            if wipe_progress(t) <= 0: return np.zeros((target_h, target_w, 3), dtype=np.uint8)
            frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            y1 = max(0, txt_y); y2 = min(target_h, txt_y + th)
            x1 = max(0, txt_x); x2 = min(target_w, txt_x + tw)
            if y1 < y2 and x1 < x2:
                sy1 = y1 - txt_y; sy2 = sy1 + (y2 - y1)
                sx1 = x1 - txt_x; sx2 = sx1 + (x2 - x1)
                frame[y1:y2, x1:x2] = _txt_rgb_t[sy1:sy2, sx1:sx2]
            return frame
        return [(VideoClip(make_bg_frame, duration=clip_duration).set_mask(VideoClip(make_bg_mask, duration=clip_duration, ismask=True)).set_position((box_x, box_y))), (VideoClip(make_text_frame_t, duration=clip_duration).set_mask(VideoClip(make_text_mask_frame, duration=clip_duration, ismask=True)).set_position((0, 0)))]

    def build_magical_lower_third(self, text, target_w, target_h, clip_duration, text_dur):
        fs = 55 if target_w < 1200 else 70
        try: pil_font = ImageFont.truetype("arialbd.ttf", fs)
        except: pil_font = ImageFont.load_default()
        txt_upper = text.upper(); dummy = PIL.Image.new("RGBA", (1, 1)); bbox = ImageDraw.Draw(dummy).textbbox((0, 0), txt_upper, font=pil_font)
        tw = bbox[2] - bbox[0] + 24; th = bbox[3] - bbox[1] + 24
        txt_img = PIL.Image.new("RGBA", (tw, th), (0, 0, 0, 0)); draw = ImageDraw.Draw(txt_img)
        draw.text((12 + 4, 12 + 4), txt_upper, font=pil_font, fill=(0, 0, 0, 180)); draw.text((12, 12), txt_upper, font=pil_font, fill=(255, 223, 115, 255))
        txt_alpha_base = np.array(txt_img)[..., 3].astype(np.float32) / 255.0; txt_rgb = np.array(txt_img)[..., :3]
        txt_x = (target_w - tw) // 2; txt_y = target_h - 210
        pad_x = int(fs * 2.8); pad_y = int(fs * 1.4); box_w = tw + pad_x * 2; box_h = th + pad_y * 2; box_x = txt_x - pad_x; box_y = txt_y - pad_y
        form_t = 1.0; diss_t = 1.0; start_t = 0.5; end_t = start_t + form_t + text_dur
        if end_t + diss_t > clip_duration:
            start_t = 0.2; avail = clip_duration - start_t; form_t = avail * 0.2; diss_t = avail * 0.2; text_dur = avail * 0.6; end_t = start_t + form_t + text_dur
        def wipe_progress(t):
            if t < start_t: return 0.0
            elif t < start_t + form_t: return (t - start_t) / form_t
            elif t < end_t: return 1.0
            elif t < end_t + diss_t: return max(0.0, 1.0-(t-end_t)/diss_t)
            else: return 0.0
        y_g, x_g = np.mgrid[0:box_h, 0:box_w]
        norm_x = (x_g - box_w / 2.0) / (box_w / 2.0); norm_y = (y_g - box_h / 2.0) / (box_h / 2.0)
        col_wave = 0.18 * np.sin(norm_x * np.pi * 2.5)
        wave_mask = np.clip(np.exp(-0.5 * ((norm_x / 0.68)**2 + ((norm_y - col_wave) / 0.44)**2)) * 1.35, 0.0, 1.0).astype(np.float32)
        def make_aurora_frame(t):
            u = x_g / box_w; v = y_g / box_h; teal = 0.5 + 0.5 * np.sin(u * 4 - t * 1.2)
            w1 = 0.5 + 0.5 * np.sin(u * 10 + t * 3.0) * np.cos(v * 5 - t * 2.0); w2 = 0.5 + 0.5 * np.cos(u * 7 - t * 2.5) * np.sin(v * 8 + t * 1.5); w3 = 0.5 + 0.5 * np.sin((u + v) * 6 + t * 1.8)
            return np.stack([np.clip(w1 * 120 + w3 * 60, 0, 255), np.clip(w2 * 140 + w3 * 80 + teal * 80, 0, 255), np.clip(w1 * 255 + w2 * 220 + w3 * 120 + teal * 40, 0, 255)], axis=-1).astype(np.uint8)
        def make_text_mask_frame(t):
            wp = wipe_progress(t); full = np.zeros((target_h, target_w), dtype=np.float32)
            if wp <= 0: return full
            ga = txt_alpha_base.copy()
            if t < end_t:
                reveal_x = int(wp * tw)
                for i in range(min(40, tw)):
                    if 0 <= reveal_x + i < tw: ga[:, reveal_x + i] *= (1.0 - i / 40.0)
                ga[:, reveal_x:] = 0.0
            else:
                p = (t - end_t) / diss_t
                np.random.seed(int(t * 20))
                ga = ga * np.where(np.random.rand(th, tw) > np.clip(p*2.0 - np.linspace(0, 1, th).reshape(-1, 1)*0.8, 0, 1), 1.0, 0.0).astype(np.float32)
            y1_d, y2_d = max(0, txt_y), min(target_h, txt_y + th); x1_d, x2_d = max(0, txt_x), min(target_w, txt_x + tw)
            if y1_d < y2_d and x1_d < x2_d: full[y1_d:y2_d, x1_d:x2_d] = ga[y1_d-txt_y:y1_d-txt_y+(y2_d-y1_d), x1_d-txt_x:x1_d-txt_x+(x2_d-x1_d)]
            return full
        aurora_clip = (VideoClip(make_aurora_frame, duration=clip_duration).set_mask(VideoClip(lambda t: (wave_mask * wipe_progress(t)).astype(np.float32), duration=clip_duration, ismask=True)).set_position((box_x, box_y)))
        _txt_rgb_m = txt_rgb.copy()
        def make_text_frame_m(t):
            if wipe_progress(t) <= 0: return np.zeros((target_h, target_w, 3), dtype=np.uint8)
            frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            y1 = max(0, txt_y); y2 = min(target_h, txt_y + th)
            x1 = max(0, txt_x); x2 = min(target_w, txt_x + tw)
            if y1 < y2 and x1 < x2:
                sy1 = y1 - txt_y; sy2 = sy1 + (y2 - y1)
                sx1 = x1 - txt_x; sx2 = sx1 + (x2 - x1)
                frame[y1:y2, x1:x2] = _txt_rgb_m[sy1:sy2, sx1:sx2]
            return frame
        text_clip_final = (VideoClip(make_text_frame_m, duration=clip_duration).set_mask(VideoClip(make_text_mask_frame, duration=clip_duration, ismask=True)).set_position((0, 0)))
        part_h = min(400, target_h); part_y_off = target_h - part_h
        np.random.seed(42); N = 180; M = 400; K = 200
        trail_spawn = start_t + np.linspace(0, form_t, N); trail_x0 = txt_x - 50 + np.linspace(0, 1, N) * (tw + 100); trail_y0 = (txt_y - part_y_off) - 70*np.sin(np.linspace(0,1,N)*np.pi) + th//2
        diss_spawn = end_t + np.random.uniform(0, diss_t*0.7, M); diss_x0 = txt_x + np.random.uniform(0, tw, M); diss_y0 = (txt_y - part_y_off) + np.random.uniform(0, th, M)
        amb_spawn = np.random.uniform(start_t, end_t, K); amb_x0 = txt_x + np.random.uniform(-20, tw+20, K); amb_y0 = (txt_y - part_y_off) + np.random.uniform(-10, th+10, K)
        def make_fx_frame(t):
            frame = np.zeros((part_h, target_w, 3), dtype=np.uint8); alpha = np.zeros((part_h, target_w), dtype=np.float32)
            for spawn, x0, y0, col, grav, life_dur in [(trail_spawn, trail_x0, trail_y0, (255,220,120), 250, 1.2), (amb_spawn, amb_x0, amb_y0, (255,240,180), 0, 2.0), (diss_spawn, diss_x0, diss_y0, (255,200,100), 350, 1.5)]:
                active = (t > spawn) & (t < spawn + life_dur)
                if not np.any(active): continue
                dt = t - spawn[active]; cx_ = (x0[active]).astype(int); cy_ = (y0[active] + 15*dt + 0.5*grav*dt**2).astype(int); life = np.clip(1.0 - dt/life_dur, 0, 1)
                for x, y, l in zip(cx_, cy_, life):
                    if 0<=y<part_h and 0<=x<target_w: frame[y:y+2, x:x+2] = col; alpha[y:y+2, x:x+2] = np.maximum(alpha[y:y+2, x:x+2], l)
            return frame, alpha
        fx_clip = (VideoClip(lambda t: make_fx_frame(t)[0], duration=clip_duration).set_mask(VideoClip(lambda t: make_fx_frame(t)[1], duration=clip_duration, ismask=True)).set_position((0, part_y_off)))
        return [aurora_clip, text_clip_final, fx_clip]

    def build_designer_lower_third(self, text, target_w, target_h, clip_duration, text_dur):
        fs = 55 if target_w < 1200 else 70
        try: pil_font = ImageFont.truetype("arialbd.ttf", fs)
        except: pil_font = ImageFont.load_default()
        txt_upper = text.upper(); dummy = PIL.Image.new("RGBA", (1, 1)); bbox = ImageDraw.Draw(dummy).textbbox((0, 0), txt_upper, font=pil_font)
        tw = bbox[2] - bbox[0] + 24; th = bbox[3] - bbox[1] + 24
        txt_img = PIL.Image.new("RGBA", (tw, th), (0, 0, 0, 0)); draw = ImageDraw.Draw(txt_img)
        draw.text((12 + 4, 12 + 4), txt_upper, font=pil_font, fill=(0, 0, 0, 180)); draw.text((12, 12), txt_upper, font=pil_font, fill=(255, 220, 80, 255))
        txt_rgba = np.array(txt_img); txt_rgb = txt_rgba[..., :3]; txt_alpha_base = txt_rgba[..., 3].astype(np.float32) / 255.0
        pad_x = int(fs * 1.8); pad_y = int(fs * 0.9); panel_w = tw + pad_x * 2; panel_h = th + pad_y * 2
        panel_x = (target_w - panel_w) // 2; panel_y = target_h - 220; txt_x = panel_x + pad_x; txt_y = panel_y + pad_y
        form_t = 0.5; hold_t = text_dur; diss_t = 0.4; start_t = 0.4; end_t = start_t + form_t + hold_t
        if end_t + diss_t > clip_duration:
            start_t = 0.2; avail = clip_duration - start_t; form_t = avail*0.15; diss_t = avail*0.15; hold_t = avail*0.70; end_t = start_t + form_t + hold_t
        def panel_progress(t):
            if t < start_t: return 0.0
            elif t < start_t+form_t: return (t-start_t)/form_t
            elif t < end_t: return 1.0
            elif t < end_t+diss_t: return max(0.0, 1.0-(t-end_t)/diss_t)
            else: return 0.0
        y_p, x_p = np.mgrid[0:panel_h, 0:panel_w]
        nx = (x_p - panel_w/2.0) / (panel_w/2.0); ny = (y_p - panel_h/2.0) / (panel_h/2.0)
        panel_base_alpha = np.clip(np.exp(-0.5*((nx/0.80)**2 + (ny/0.72)**2)) * 0.82, 0, 1).astype(np.float32)
        border_glow = np.clip(1.0 - np.minimum(np.minimum(x_p, panel_w - 1 - x_p), np.minimum(y_p, panel_h - 1 - y_p)) / 12.0, 0, 1) ** 2
        corner_len = int(panel_w * 0.12); corner_th = 3; corner_mask = np.zeros((panel_h, panel_w), dtype=np.float32)
        for cx_, cy_ in [(0,0),(panel_w-corner_len,0),(0,panel_h-corner_th),(panel_w-corner_len,panel_h-corner_th),(0,0),(panel_w-corner_th,0),(0,panel_h-corner_len),(panel_w-corner_th,panel_h-corner_len)]:
            corner_mask[max(0,cy_):min(panel_h,cy_+max(corner_th, corner_len)), max(0,cx_):min(panel_w,cx_+max(corner_th, corner_len))] = 1.0
        def make_panel_frame(t):
            prog = panel_progress(t)
            if prog <= 0: return np.zeros((target_h, target_w, 3), dtype=np.uint8)
            py = panel_y + int((1.0 - prog) * panel_h * 1.5); frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            y1, y2 = max(0, py), min(target_h, py + panel_h); x1, x2 = max(0, panel_x), min(target_w, panel_x + panel_w)
            if y1 >= y2 or x1 >= x2: return frame
            py_s, py_e = y1 - py, (y1 - py) + (y2 - y1); px_s, px_e = x1 - panel_x, (x1 - panel_x) + (x2 - x1)
            frame[y1:y2, x1:x2, 0], frame[y1:y2, x1:x2, 1], frame[y1:y2, x1:x2, 2] = 45, 10, 75
            s_scan = np.exp(-0.5*((np.arange(panel_h) - int(((t * 0.7) % 1.0) * panel_h))/8.0)**2)[py_s:py_e, np.newaxis]
            s_border = border_glow[py_s:py_e, px_s:px_e]
            frame[y1:y2, x1:x2, 0] = np.clip(frame[y1:y2, x1:x2, 0] + (s_scan * 80).astype(np.uint8) + (s_border * 180).astype(np.uint8), 0, 255)
            frame[y1:y2, x1:x2, 1] = np.clip(frame[y1:y2, x1:x2, 1] + (s_scan * 40).astype(np.uint8) + (s_border * 60).astype(np.uint8), 0, 255)
            frame[y1:y2, x1:x2, 2] = np.clip(frame[y1:y2, x1:x2, 2] + (s_scan * 120).astype(np.uint8) + (s_border * 255).astype(np.uint8), 0, 255)
            return frame
        def make_panel_mask(t):
            prog = panel_progress(t); full = np.zeros((target_h, target_w), dtype=np.float32)
            if prog <= 0: return full
            py = panel_y + int((1.0 - prog) * panel_h * 1.5)
            y1, y2 = max(0, py), min(target_h, py + panel_h); x1, x2 = max(0, panel_x), min(target_w, panel_x + panel_w)
            if y1 >= y2 or x1 >= x2: return full
            py_s, py_e = y1 - py, (y1 - py) + (y2 - y1); px_s, px_e = x1 - panel_x, (x1 - panel_x) + (x2 - x1)
            full[y1:y2, x1:x2] = panel_base_alpha[py_s:py_e, px_s:px_e] * prog
            full[y1:y2, x1:x2] = np.clip(full[y1:y2, x1:x2] + border_glow[py_s:py_e, px_s:px_e] * 0.9 * prog, 0, 1)
            return full
        def make_text_mask(t):
            prog = panel_progress(t); full = np.zeros((target_h, target_w), dtype=np.float32)
            if prog <= 0: return full
            ty = txt_y + int((1.0 - prog) * panel_h * 1.5)
            ga = txt_alpha_base.copy()
            if t >= end_t:
                p = (t - end_t) / diss_t
                np.random.seed(int(t * 20))
                ga = ga * np.where(np.random.rand(th, tw) > np.clip(p*2.0 - np.linspace(0, 1, th).reshape(-1, 1)*0.8, 0, 1), 1.0, 0.0).astype(np.float32)
            y1_d, y2_d = max(0, ty), min(target_h, ty + th); x1_d, x2_d = max(0, txt_x), min(target_w, txt_x + tw)
            if y1_d < y2_d and x1_d < x2_d: full[y1_d:y2_d, x1_d:x2_d] = ga[y1_d-ty:y1_d-ty+(y2_d-y1_d), x1_d-txt_x:x1_d-txt_x+(x2_d-x1_d)] * prog
            return full
        panel_clip = (VideoClip(make_panel_frame, duration=clip_duration).set_mask(VideoClip(make_panel_mask, duration=clip_duration, ismask=True)).set_position((0, 0)))
        _txt_rgb_d = txt_rgb.copy()
        def make_text_frame_d(t):
            if panel_progress(t) <= 0: return np.zeros((target_h, target_w, 3), dtype=np.uint8)
            frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            ty = txt_y + int((1.0 - panel_progress(t)) * panel_h * 1.5)
            y1 = max(0, ty); y2 = min(target_h, ty + th)
            x1 = max(0, txt_x); x2 = min(target_w, txt_x + tw)
            if y1 < y2 and x1 < x2:
                sy1 = y1 - ty; sy2 = sy1 + (y2 - y1)
                sx1 = x1 - txt_x; sx2 = sx1 + (x2 - x1)
                frame[y1:y2, x1:x2] = _txt_rgb_d[sy1:sy2, sx1:sx2]
            return frame
        text_clip_final = (VideoClip(make_text_frame_d, duration=clip_duration).set_mask(VideoClip(make_text_mask, duration=clip_duration, ismask=True)).set_position((0, 0)))
        return [panel_clip, text_clip_final]

    def build_news_lower_third(self, text, target_w, target_h, clip_duration, text_dur):
        fs = 44 if target_w < 1200 else 56
        try: pil_font = ImageFont.truetype("arialbd.ttf", fs)
        except: pil_font = ImageFont.load_default()
        txt_upper = text.upper()
        dummy = PIL.Image.new("RGBA", (1, 1))
        bbox = ImageDraw.Draw(dummy).textbbox((0, 0), txt_upper, font=pil_font)
        tw = bbox[2] - bbox[0] + 60
        th = bbox[3] - bbox[1] + 20
        bar_h = th + int(fs * 1.0)
        bar_w = int(target_w * 0.55)
        chevron = int(bar_h * 0.55)
        bar_x = (target_w - bar_w) // 2
        bar_y = target_h - int(target_h * 0.20)
        txt_x = bar_x + (bar_w - tw) // 2
        txt_y = bar_y + (bar_h - th) // 2
        form_t = 0.4
        diss_t = 0.4
        start_t = 0.3
        end_t = start_t + form_t + text_dur
        if end_t + diss_t > clip_duration:
            start_t = 0.2
            avail = clip_duration - start_t
            form_t = avail * 0.15
            diss_t = avail * 0.15
            text_dur = avail * 0.7
            end_t = start_t + form_t + text_dur
        def wipe_progress(t):
            if t < start_t: return 0.0
            elif t < start_t + form_t: return (t - start_t) / form_t
            elif t < end_t: return 1.0
            elif t < end_t + diss_t: return max(0.0, 1.0 - (t - end_t) / diss_t)
            else: return 0.0
        y_g, x_g = np.mgrid[0:bar_h, 0:bar_w]
        nx = x_g.astype(np.float32) / bar_w
        ny = y_g.astype(np.float32) / bar_h
        cy = bar_h / 2.0
        in_chev_L = (x_g < chevron) & (y_g > (cy - (x_g * cy / chevron))) & (y_g < (cy + (x_g * cy / chevron)))
        in_chev_R = (x_g > bar_w - 1 - chevron) & (y_g > (cy - ((bar_w - 1 - x_g) * cy / chevron))) & (y_g < (cy + ((bar_w - 1 - x_g) * cy / chevron)))
        in_body = (x_g >= chevron) & (x_g <= bar_w - 1 - chevron)
        inner_mask = np.where(in_body | in_chev_L | in_chev_R, 1.0, 0.0).astype(np.float32)
        edge_dist = np.minimum(np.minimum(nx, 1.0 - nx), np.minimum(ny, 1.0 - ny))
        glow_edge = np.exp(-edge_dist / 0.04).astype(np.float32) * inner_mask
        scan_pattern = ((y_g % 4) == 0).astype(np.float32) * 0.08 * inner_mask
        np.random.seed(42)
        noise_pattern = np.random.rand(bar_h, bar_w).astype(np.float32) * 0.06 * inner_mask
        circuit_h = ((x_g % 12) < 1).astype(np.float32) * 0.15
        circuit_v = ((y_g % 16) < 1).astype(np.float32) * 0.15
        circuit = np.clip((circuit_h + circuit_v) * inner_mask, 0, 1)
        pad = 5
        outer_h = bar_h + pad * 2
        outer_w = bar_w + pad * 2 + chevron
        outer_y = bar_y - pad
        outer_x = bar_x - pad - chevron // 2
        oy_g, ox_g = np.mgrid[0:outer_h, 0:outer_w]
        ony = oy_g.astype(np.float32) / outer_h
        ocy = outer_h / 2.0
        o_chevron = chevron + pad
        in_o_chev_L = (ox_g < o_chevron) & (oy_g > (ocy - (ox_g * ocy / o_chevron))) & (oy_g < (ocy + (ox_g * ocy / o_chevron)))
        in_o_chev_R = (ox_g > outer_w - 1 - o_chevron) & (oy_g > (ocy - ((outer_w - 1 - ox_g) * ocy / o_chevron))) & (oy_g < (ocy + ((outer_w - 1 - ox_g) * ocy / o_chevron)))
        in_o_body = (ox_g >= o_chevron) & (ox_g <= outer_w - 1 - o_chevron)
        outer_mask = np.where(in_o_body | in_o_chev_L | in_o_chev_R, 1.0, 0.0).astype(np.float32)
        onx = ox_g.astype(np.float32) / outer_w
        o_edge_dist = np.minimum(np.minimum(onx, 1.0 - onx), np.minimum(ony, 1.0 - ony))
        outer_glow_edge = np.exp(-o_edge_dist / 0.03).astype(np.float32) * outer_mask
        def make_bar_frame(t):
            prog = wipe_progress(t)
            if prog <= 0: return np.zeros((target_h, target_w, 3), dtype=np.uint8)
            outer_frame = np.zeros((outer_h, outer_w, 3), dtype=np.float32)
            outer_frame[..., 0] = 8 + outer_glow_edge * 20
            outer_frame[..., 1] = 10 + outer_glow_edge * 80
            outer_frame[..., 2] = 18 + outer_glow_edge * 120
            scan_pos = ((t * 1.5) % 1.0)
            o_scan = np.exp(-0.5 * ((ony - scan_pos) / 0.02)**2) * outer_mask * 0.3
            outer_frame[..., 0] += o_scan * 20
            outer_frame[..., 1] += o_scan * 160
            outer_frame[..., 2] += o_scan * 255
            inner_frame = np.zeros((bar_h, bar_w, 3), dtype=np.float32)
            gr = np.clip(8 + 40 * nx, 0, 255)
            gg = np.clip(50 + 130 * nx, 0, 255)
            gb = np.clip(120 + 100 * nx, 0, 255)
            inner_frame[..., 0] = gr
            inner_frame[..., 1] = gg
            inner_frame[..., 2] = gb
            inner_frame[..., 0] += glow_edge * 40
            inner_frame[..., 1] += glow_edge * 220
            inner_frame[..., 2] += glow_edge * 255
            inner_frame[..., 0] += circuit * 15
            inner_frame[..., 1] += circuit * 100
            inner_frame[..., 2] += circuit * 180
            inner_frame *= (1.0 + scan_pattern + noise_pattern)[..., np.newaxis]
            flicker = 1.0 + 0.04 * np.sin(t * 8.0)
            inner_frame *= flicker
            inner_frame *= prog
            outer_frame *= prog
            result = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            oy1 = max(0, outer_y); oy2 = min(target_h, outer_y + outer_h)
            ox1 = max(0, outer_x); ox2 = min(target_w, outer_x + outer_w)
            if oy1 < oy2 and ox1 < ox2:
                result[oy1:oy2, ox1:ox2] = outer_frame[oy1 - outer_y:oy2 - outer_y, ox1 - outer_x:ox2 - outer_x].astype(np.uint8)
            iy1 = max(0, bar_y); iy2 = min(target_h, bar_y + bar_h)
            ix1 = max(0, bar_x); ix2 = min(target_w, bar_x + bar_w)
            if iy1 < iy2 and ix1 < ix2:
                result[iy1:iy2, ix1:ix2] = np.clip(
                    result[iy1:iy2, ix1:ix2].astype(np.float32) +
                    inner_frame[iy1 - bar_y:iy2 - bar_y, ix1 - bar_x:ix2 - bar_x], 0, 255).astype(np.uint8)
            return result
        def make_bar_mask(t):
            prog = wipe_progress(t)
            if prog <= 0: return np.zeros((target_h, target_w), dtype=np.float32)
            full = np.zeros((target_h, target_w), dtype=np.float32)
            oy1 = max(0, outer_y); oy2 = min(target_h, outer_y + outer_h)
            ox1 = max(0, outer_x); ox2 = min(target_w, outer_x + outer_w)
            if oy1 < oy2 and ox1 < ox2:
                full[oy1:oy2, ox1:ox2] = outer_mask[oy1 - outer_y:oy2 - outer_y, ox1 - outer_x:ox2 - outer_x] * prog
            return full
        txt_img = PIL.Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        draw = ImageDraw.Draw(txt_img)
        draw.text((30 + 2, 10 + 2), txt_upper, font=pil_font, fill=(0, 0, 0, 200))
        draw.text((30, 10), txt_upper, font=pil_font, fill=(255, 255, 255, 255))
        txt_rgba = np.array(txt_img)
        _txt_rgb = txt_rgba[..., :3].copy()
        txt_alpha_base = txt_rgba[..., 3].astype(np.float32) / 255.0
        _tw, _th = tw, th
        def make_text_mask(t):
            prog = wipe_progress(t)
            full = np.zeros((target_h, target_w), dtype=np.float32)
            if prog <= 0: return full
            ga = txt_alpha_base.copy()
            if t >= end_t:
                p = (t - end_t) / diss_t
                np.random.seed(int(t * 20))
                ga = ga * np.where(np.random.rand(_th, _tw) > np.clip(p * 2.0 - np.linspace(0, 1, _th).reshape(-1, 1) * 0.8, 0, 1), 1.0, 0.0).astype(np.float32)
            y1_d, y2_d = max(0, txt_y), min(target_h, txt_y + _th)
            x1_d, x2_d = max(0, txt_x), min(target_w, txt_x + _tw)
            if y1_d < y2_d and x1_d < x2_d:
                full[y1_d:y2_d, x1_d:x2_d] = ga[y1_d - txt_y:y1_d - txt_y + (y2_d - y1_d), x1_d - txt_x:x1_d - txt_x + (x2_d - x1_d)] * prog
            return full
        def make_text_frame(t):
            if wipe_progress(t) <= 0: return np.zeros((target_h, target_w, 3), dtype=np.uint8)
            frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            y1 = max(0, txt_y); y2 = min(target_h, txt_y + _th)
            x1 = max(0, txt_x); x2 = min(target_w, txt_x + _tw)
            if y1 < y2 and x1 < x2:
                frame[y1:y2, x1:x2] = _txt_rgb[y1 - txt_y:y1 - txt_y + (y2 - y1), x1 - txt_x:x1 - txt_x + (x2 - x1)]
            return frame
        bar_clip = (VideoClip(make_bar_frame, duration=clip_duration)
                    .set_mask(VideoClip(make_bar_mask, duration=clip_duration, ismask=True))
                    .set_position((0, 0)))
        text_clip_final = (VideoClip(make_text_frame, duration=clip_duration)
                           .set_mask(VideoClip(make_text_mask, duration=clip_duration, ismask=True))
                           .set_position((0, 0)))
        return [bar_clip, text_clip_final]

    def build_finch_title_card(self, target_w, target_h, item, preview_mode=False):
        _ensure_moviepy()
        duration = float(item.get("value", 5.0))
        main_str = item.get("main_text", "TITLE").upper()
        sub_str = item.get("sub_text", "").upper()
        spaced_sub = "   ".join(sub_str) if sub_str else ""
        theme = item.get("theme", "")

        is_lightspeed = "Light Speed" in theme
        is_deepspace = "Deep Space" in theme
        is_travelling = "Travelling Flare" in theme
        is_blueflare = "Blue Flare" in theme
        is_headlight = "Headlight" in theme

        main_y = (target_h // 2) - 10

        if is_lightspeed:
            main_y -= 20
            text_clips = []
            offsets = [20, 15, 10, 5]
            colors = ["#100030", "#3b0086", "#7500c0", "#c200ff"]
            for off, col in zip(offsets, colors):
                try: tc = TextClip(main_str, fontsize=160, color=col, font="Arial-Bold", stroke_color=col, stroke_width=6, bg_color="transparent")
                except: tc = TextClip(main_str, fontsize=160, color=col, font="Arial-Bold", bg_color="transparent")
                tc = tc.set_position(("center", main_y + off)).set_duration(duration)
                text_clips.append(tc)
            try: top_tc = TextClip(main_str, fontsize=160, color="white", font="Arial-Bold", stroke_color="#a200ff", stroke_width=4, bg_color="transparent")
            except: top_tc = TextClip(main_str, fontsize=160, color="white", font="Arial-Bold", bg_color="transparent")
            top_tc = top_tc.set_position(("center", main_y)).set_duration(duration)
            text_clips.append(top_tc)
            main_clip = CompositeVideoClip(text_clips, size=(target_w, target_h)).set_duration(duration)
            shine_clip = None
            main_clip = main_clip.fx(vfx.resize, lambda t: 1.0 + 0.05 * (t / duration))
            baseline_y = main_y + top_tc.h - 10
        else:
            if is_blueflare:
                main_clip = TextClip(main_str, fontsize=120, color="#c8dde8", font="Arial-Bold", stroke_color="#0a2a4a", stroke_width=3, bg_color="transparent")
                main_clip = main_clip.set_position(("center", main_y)).set_duration(duration)
                shine_clip = TextClip(main_str, fontsize=120, color="white", font="Arial-Bold", bg_color="transparent")
                shine_clip = shine_clip.set_opacity(0.12).crop(y2=main_clip.h // 2)
                shine_clip = shine_clip.set_position(("center", main_y)).set_duration(duration)
            elif is_headlight:
                main_clip = TextClip(main_str, fontsize=60, color="#c0c8d0", font="Arial-Bold", stroke_color="black", stroke_width=4, bg_color="transparent")
                main_clip = main_clip.set_position(("center", main_y)).set_duration(duration)
                shine_clip = TextClip(main_str, fontsize=60, color="white", font="Arial-Bold", bg_color="transparent")
                shine_clip = shine_clip.set_opacity(0.2).crop(y2=main_clip.h // 2)
                shine_clip = shine_clip.set_position(("center", main_y)).set_duration(duration)
            else:
                main_clip = TextClip(main_str, fontsize=140 if is_travelling else 130, color="#E5D5A0", font="Arial-Bold", bg_color="transparent")
                main_clip = main_clip.set_position(("center", main_y)).set_duration(duration)
                if is_travelling:
                    shine_clip = None
                else:
                    shine_clip = TextClip(main_str, fontsize=130, color="white", font="Arial-Bold", bg_color="transparent")
                    shine_clip = shine_clip.set_opacity(0.12).crop(y2=main_clip.h // 2)
                    shine_clip = shine_clip.set_position(("center", main_y)).set_duration(duration)
            if is_deepspace:
                def zoom_func(t): return 1.0 + 0.05 * (t / duration)
                main_clip = main_clip.fx(vfx.resize, zoom_func)
                if shine_clip: shine_clip = shine_clip.fx(vfx.resize, zoom_func)
            baseline_y = main_y + main_clip.h - 10

        if is_lightspeed:
            bg_clip = self.create_warp_background(target_w, target_h, duration)
            layers = [bg_clip]
        elif is_travelling:
            y_bg, x_bg = np.mgrid[0:target_h, 0:target_w]
            dist_center = np.sqrt((x_bg - target_w/2)**2 + (y_bg - target_h/2)**2)
            fog_glow = np.exp(-0.5 * (dist_center / 800.0)**2) * 0.4
            bg_r = np.clip(18 + 15 * fog_glow, 0, 255); bg_g = np.clip(25 + 20 * fog_glow, 0, 255); bg_b = np.clip(28 + 15 * fog_glow, 0, 255)
            bg_frame = np.stack([bg_r, bg_g, bg_b], axis=-1).astype(np.uint8)
            bg_clip = ImageClip(bg_frame).set_duration(duration)
            layers = [bg_clip]
            y_g, x_g = np.mgrid[0:target_h, 0:target_w]
            np.random.seed(42)
            num_dust = 120
            d_x = np.random.uniform(target_w*0.1, target_w*0.9, num_dust); d_y = np.random.uniform(target_h*0.2, target_h*0.8, num_dust)
            d_vx = np.random.uniform(-5, 5, num_dust); d_vy = np.random.uniform(-10, -2, num_dust); d_size = np.zeros(num_dust)
            dist_c = np.sqrt((x_g - target_w/2)**2 + (y_g - baseline_y)**2)
            text_w_half = main_clip.w / 2.0 + 40; text_h_half = main_clip.h / 2.0 + 50; text_cy = baseline_y - main_clip.h / 2.0 - 20
            dx_text = np.maximum(0.0, np.abs(x_g - target_w/2) - text_w_half); dy_text = np.maximum(0.0, np.abs(y_g - text_cy) - text_h_half)
            dist_from_text = np.sqrt(dx_text**2 + dy_text**2); text_avoid_mask = np.clip(dist_from_text / 10.0, 0, 1)
            def make_travelling_flare(t):
                p = t / duration; cx = (target_w/2 - main_clip.w/2 - 150) + p * (main_clip.w + 300); cy = baseline_y - 5
                intensity = 0.02 + 0.98 * np.exp(-0.5 * ((p - 0.5) / 0.12)**2)
                frame = np.zeros((target_h, target_w, 3), dtype=np.float32); alpha = np.zeros((target_h, target_w), dtype=np.float32)
                fog = np.exp(-0.5 * ((x_g - target_w/2)**2 / (600.0)**2 + (y_g - cy)**2 / (150.0)**2)) * intensity * 0.15
                sine_val = np.sin(-dist_c / 35.0 + t * 5.0); ripple_lines = np.clip((sine_val - 0.995) * 200.0, 0, 1)
                np.random.seed(int(t * 20)); glitter_noise = np.random.rand(target_h, target_w); glitter_mult = np.where(glitter_noise > 0.85, 2.5, 0.2)
                ripples = ripple_lines * text_avoid_mask * intensity * glitter_mult * 0.8
                fog_glow = np.clip(fog, 0, 1); frame[..., 0] += fog_glow * 255; frame[..., 1] += fog_glow * 220; frame[..., 2] += fog_glow * 130; alpha += fog_glow
                frame[..., 0] = np.clip(frame[..., 0] + ripples * 229, 0, 255); frame[..., 1] = np.clip(frame[..., 1] + ripples * 213, 0, 255); frame[..., 2] = np.clip(frame[..., 2] + ripples * 160, 0, 255); alpha = np.clip(alpha + ripples, 0, 1)
                streak_h_w = 800.0 * intensity + 20.0; streak_h_h = 2.5 + 1.0 * intensity; streak_v_w = 2.5 + 1.0 * intensity; streak_v_h = 350.0 * intensity + 10.0
                y_min, y_max = max(0, int(cy - max(streak_h_h, streak_v_h)*3)), min(target_h, int(cy + max(streak_h_h, streak_v_h)*3))
                x_min, x_max = max(0, int(cx - max(streak_h_w, streak_v_w)*3)), min(target_w, int(cx + max(streak_h_w, streak_v_w)*3))
                if y_min < y_max and x_min < x_max:
                    xx = x_g[y_min:y_max, x_min:x_max]; yy = y_g[y_min:y_max, x_min:x_max]; dx = xx - cx; dy = yy - cy
                    s1 = np.exp(-0.5 * (dx / streak_h_w)**2 - 0.5 * (dy / streak_h_h)**2) * intensity; s2 = np.exp(-0.5 * (dx / streak_v_w)**2 - 0.5 * (dy / streak_v_h)**2) * intensity
                    core = np.exp(-0.5 * (np.sqrt(dx**2 + dy**2) / (25.0 * intensity + 3.0))**2) * intensity * 1.5; glow = np.clip(s1 + s2 + core, 0, 1)
                    frame[y_min:y_max, x_min:x_max, 0] = np.clip(frame[y_min:y_max, x_min:x_max, 0] + glow * 255, 0, 255); frame[y_min:y_max, x_min:x_max, 1] = np.clip(frame[y_min:y_max, x_min:x_max, 1] + glow * 240, 0, 255); frame[y_min:y_max, x_min:x_max, 2] = np.clip(frame[y_min:y_max, x_min:x_max, 2] + glow * 190, 0, 255); alpha[y_min:y_max, x_min:x_max] = np.clip(alpha[y_min:y_max, x_min:x_max] + glow, 0, 1)
                for i in range(num_dust):
                    curr_x = int(d_x[i] + d_vx[i] * t); curr_y = int(d_y[i] + d_vy[i] * t)
                    if 0 <= curr_x < target_w and 0 <= curr_y < target_h:
                        dist_to_flare = np.sqrt((curr_x - cx)**2 + (curr_y - cy)**2)
                        illum = max(np.exp(-0.5 * (dist_to_flare / (300 * intensity + 50))**2) * intensity * 0.8, np.exp(-0.5 * ((curr_x - target_w/2)**2 / 600**2 + (curr_y - cy)**2 / 150**2)) * intensity * 0.3)
                        if illum > 0.02:
                            s = 0; y1, y2 = max(0, curr_y-s), min(target_h, curr_y+s+1); x1, x2 = max(0, curr_x-s), min(target_w, curr_x+s+1)
                            dust_glow = illum * 255; frame[y1:y2, x1:x2, 0] = np.clip(frame[y1:y2, x1:x2, 0] + dust_glow, 0, 255); frame[y1:y2, x1:x2, 1] = np.clip(frame[y1:y2, x1:x2, 1] + dust_glow * 0.85, 0, 255); frame[y1:y2, x1:x2, 2] = np.clip(frame[y1:y2, x1:x2, 2] + dust_glow * 0.4, 0, 255); alpha[y1:y2, x1:x2] = np.clip(alpha[y1:y2, x1:x2] + illum, 0, 1)
                return np.clip(frame, 0, 255).astype(np.uint8), np.clip(alpha, 0, 1)
            flare_rgb = VideoClip(lambda t: make_travelling_flare(t)[0], duration=duration)
            flare_mask = VideoClip(lambda t: make_travelling_flare(t)[1], duration=duration, ismask=True)
            layers.append(flare_rgb.set_mask(flare_mask))
        elif is_blueflare:
            y_bg, x_bg = np.mgrid[0:target_h, 0:target_w]
            norm_y = (y_bg / target_h).astype(np.float32)
            norm_x = (x_bg / target_w).astype(np.float32)
            bg_r = np.clip(6 + 8 * (1 - norm_y), 0, 255).astype(np.float32)
            bg_g = np.clip(8 + 10 * (1 - norm_y), 0, 255).astype(np.float32)
            bg_b = np.clip(15 + 20 * (1 - norm_y), 0, 255).astype(np.float32)
            flare_cy = target_h * 0.52
            flare_h_w = target_w * 0.55
            flare_h_h = 2.5
            flare_v_w = 2.0
            flare_v_h = target_h * 0.12
            dx_flare = x_bg - target_w / 2.0
            dy_flare = y_bg - flare_cy
            h_streak = np.exp(-0.5 * (dx_flare / flare_h_w)**2 - 0.5 * (dy_flare / flare_h_h)**2)
            v_streak = np.exp(-0.5 * (dx_flare / flare_v_w)**2 - 0.5 * (dy_flare / flare_v_h)**2)
            core = np.exp(-0.5 * (np.sqrt(dx_flare**2 + dy_flare**2) / (8.0))**2)
            flare_total = np.clip(h_streak * 0.85 + v_streak * 0.6 + core * 1.2, 0, 1)
            flare_rgb_frame = np.zeros((target_h, target_w, 3), dtype=np.float32)
            flare_rgb_frame[..., 0] = flare_total * 80
            flare_rgb_frame[..., 1] = flare_total * 160
            flare_rgb_frame[..., 2] = flare_total * 255
            flare_alpha_frame = flare_total.astype(np.float32)
            bg_r += flare_total * 80; bg_g += flare_total * 160; bg_b += flare_total * 255
            bg_frame = np.stack([bg_r, bg_g, bg_b], axis=-1).astype(np.uint8)
            bg_clip = ImageClip(bg_frame).set_duration(duration)
            layers = [bg_clip]
            ambient = np.exp(-0.5 * (np.sqrt((x_bg - target_w/2)**2 + (y_bg - flare_cy)**2) / (target_w * 0.4))**2) * 0.08
            ambient_frame = np.stack([ambient * 40, ambient * 80, ambient * 140], axis=-1).astype(np.float32)
            ambient_clip = ImageClip(np.clip(ambient_frame, 0, 255).astype(np.uint8)).set_duration(duration)
            layers.append(ambient_clip)
            def make_blueflare_flare(t):
                pulse = 1.0 + 0.06 * np.sin(t * 1.8)
                drift = 3.0 * np.sin(t * 0.4)
                shifted = np.roll(flare_rgb_frame.astype(np.float32), int(drift), axis=1)
                shifted *= pulse
                return np.clip(shifted, 0, 255).astype(np.uint8)
            def make_blueflare_mask(t):
                pulse = 1.0 + 0.06 * np.sin(t * 1.8)
                drift = 3.0 * np.sin(t * 0.4)
                shifted = np.roll(flare_alpha_frame, int(drift), axis=1)
                shifted *= pulse
                return np.clip(shifted, 0, 1).astype(np.float32)
            flare_clip = VideoClip(make_blueflare_flare, duration=duration).set_mask(VideoClip(make_blueflare_mask, duration=duration, ismask=True))
            layers.append(flare_clip)
        elif is_headlight:
            y_bg, x_bg = np.mgrid[0:target_h, 0:target_w]
            norm_y = (y_bg / target_h).astype(np.float32)
            norm_x = (x_bg / target_w).astype(np.float32)
            bg_r = np.clip(5 + 4 * (1 - norm_y), 0, 255).astype(np.float32)
            bg_g = np.clip(6 + 5 * (1 - norm_y), 0, 255).astype(np.float32)
            bg_b = np.clip(12 + 10 * (1 - norm_y), 0, 255).astype(np.float32)
            flare_cy = target_h * 0.52
            beam_y_L = (y_bg - flare_cy).astype(np.float32)
            beam_y_R = (y_bg - flare_cy).astype(np.float32)
            mask_L = np.clip(1.0 - norm_x / 0.42, 0, 1).astype(np.float32)
            mask_R = np.clip(1.0 - (1.0 - norm_x) / 0.42, 0, 1).astype(np.float32)
            core_L = np.exp(-0.5 * ((norm_x / 0.015)**2 + ((norm_y - 0.52) / 0.01)**2)) * mask_L
            core_R = np.exp(-0.5 * (((1.0 - norm_x) / 0.015)**2 + ((norm_y - 0.52) / 0.01)**2)) * mask_R
            glow_L = np.exp(-0.5 * ((norm_x / 0.05)**2 + ((norm_y - 0.52) / 0.04)**2)) * mask_L
            glow_R = np.exp(-0.5 * (((1.0 - norm_x) / 0.05)**2 + ((norm_y - 0.52) / 0.04)**2)) * mask_R
            ray_narrow_L = np.exp(-0.5 * (beam_y_L / (target_h * 0.002))**2) * np.exp(-0.5 * ((norm_x / 0.18)**2)) * mask_L
            ray_narrow_R = np.exp(-0.5 * (beam_y_R / (target_h * 0.002))**2) * np.exp(-0.5 * (((1.0 - norm_x) / 0.18)**2)) * mask_R
            ray_wide_L = np.exp(-0.5 * (beam_y_L / (target_h * 0.012))**2) * np.exp(-0.5 * ((norm_x / 0.28)**2)) * mask_L
            ray_wide_R = np.exp(-0.5 * (beam_y_R / (target_h * 0.012))**2) * np.exp(-0.5 * (((1.0 - norm_x) / 0.28)**2)) * mask_R
            flare_total = np.clip(
                core_L * 2.5 + core_R * 2.5 +
                glow_L * 1.5 + glow_R * 1.5 +
                ray_narrow_L * 1.2 + ray_narrow_R * 1.2 +
                ray_wide_L * 0.5 + ray_wide_R * 0.5, 0, 1)
            flare_rgb_frame = np.zeros((target_h, target_w, 3), dtype=np.float32)
            flare_rgb_frame[..., 0] = flare_total * 80
            flare_rgb_frame[..., 1] = flare_total * 160
            flare_rgb_frame[..., 2] = flare_total * 240
            flare_alpha_frame = flare_total.astype(np.float32)
            bg_r += flare_total * 80; bg_g += flare_total * 160; bg_b += flare_total * 240
            vignette = 1.0 - np.clip(np.sqrt(((norm_x - 0.5) / 0.75)**2 + ((norm_y - 0.5) / 0.65)**2) - 0.25, 0, 1) * 0.85
            bg_r *= vignette; bg_g *= vignette; bg_b *= vignette
            bg_frame = np.stack([bg_r, bg_g, bg_b], axis=-1).astype(np.uint8)
            bg_clip = ImageClip(bg_frame).set_duration(duration)
            layers = [bg_clip]
            np.random.seed(77)
            n_dust = 300
            dust_x0 = np.random.uniform(0, target_w, n_dust).astype(np.float32)
            dust_y0 = np.random.uniform(0, target_h, n_dust).astype(np.float32)
            dust_vx = np.random.uniform(-8, 8, n_dust).astype(np.float32)
            dust_vy = np.random.uniform(-3, 3, n_dust).astype(np.float32)
            dust_phase = np.random.uniform(0, 2 * np.pi, n_dust).astype(np.float32)
            dust_size = np.random.choice([1, 2, 3], n_dust, p=[0.6, 0.3, 0.1]).astype(np.int32)
            def make_dust_frame(t):
                frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
                alpha = np.zeros((target_h, target_w), dtype=np.float32)
                cx_L = 0; cy_L = flare_cy; cx_R = target_w; cy_R = flare_cy
                for i in range(n_dust):
                    px = int(dust_x0[i] + dust_vx[i] * t) % target_w
                    py = int(dust_y0[i] + dust_vy[i] * t + 2.0 * np.sin(t * 1.5 + dust_phase[i])) % target_h
                    dist_L = np.sqrt((px - cx_L)**2 + (py - cy_L)**2)
                    dist_R = np.sqrt((px - cx_R)**2 + (py - cy_R)**2)
                    brightness = max(
                        np.exp(-0.5 * (dist_L / (target_w * 0.4))**2),
                        np.exp(-0.5 * (dist_R / (target_w * 0.4))**2))
                    flicker = 0.5 + 0.5 * np.sin(t * 3.0 + dust_phase[i])
                    b = brightness * flicker * 0.6
                    if b > 0.02:
                        s = dust_size[i]
                        y1, y2 = max(0, py - s), min(target_h, py + s + 1)
                        x1, x2 = max(0, px - s), min(target_w, px + s + 1)
                        if y1 < y2 and x1 < x2:
                            frame[y1:y2, x1:x2, 0] = np.clip(frame[y1:y2, x1:x2, 0] + b * 180, 0, 255)
                            frame[y1:y2, x1:x2, 1] = np.clip(frame[y1:y2, x1:x2, 1] + b * 200, 0, 255)
                            frame[y1:y2, x1:x2, 2] = np.clip(frame[y1:y2, x1:x2, 2] + b * 240, 0, 255)
                            alpha[y1:y2, x1:x2] = np.clip(alpha[y1:y2, x1:x2] + b, 0, 1)
                return frame, alpha
            def make_dust_rgb(t):
                return make_dust_frame(t)[0]
            def make_dust_alpha(t):
                return make_dust_frame(t)[1]
            dust_clip = VideoClip(make_dust_rgb, duration=duration).set_mask(VideoClip(make_dust_alpha, duration=duration, ismask=True))
            layers.append(dust_clip)
            def make_headlight_flare(t):
                pulse = 1.0 + 0.03 * np.sin(t * 1.0)
                flicker = 1.0 + 0.02 * np.sin(t * 2.5)
                frame = flare_rgb_frame.copy().astype(np.float32) * pulse * flicker
                return np.clip(frame, 0, 255).astype(np.uint8)
            def make_headlight_mask(t):
                pulse = 1.0 + 0.03 * np.sin(t * 1.0)
                return np.clip(flare_alpha_frame * pulse, 0, 1).astype(np.float32)
            flare_clip = VideoClip(make_headlight_flare, duration=duration).set_mask(VideoClip(make_headlight_mask, duration=duration, ismask=True))
            layers.append(flare_clip)
        else:
            bg_clip = self.create_starry_sky_background(target_w, target_h, duration)
            layers = [bg_clip]

        if spaced_sub:
            if is_lightspeed:
                try: sub_txt = TextClip(spaced_sub, fontsize=40, color="#b050ff", font="Arial-Bold", stroke_color="white", stroke_width=3, bg_color="transparent")
                except: sub_txt = TextClip(spaced_sub, fontsize=40, color="white", font="Arial-Bold", bg_color="transparent")
                layers.append(sub_txt.set_position(("center", main_y - 70)).set_duration(duration))
            elif is_travelling:
                try: sub_txt = TextClip(spaced_sub, fontsize=35, color="#E5D5A0", font="Arial-Bold", bg_color="transparent")
                except: sub_txt = TextClip(spaced_sub, fontsize=35, color="white", bg_color="transparent")
                layers.append(sub_txt.set_position(("center", main_y - 60)).set_duration(duration))
            elif is_blueflare:
                try: sub_txt = TextClip(spaced_sub, fontsize=36, color="#6aafcc", font="Arial-Bold", bg_color="transparent")
                except: sub_txt = TextClip(spaced_sub, fontsize=36, color="white", bg_color="transparent")
                layers.append(sub_txt.set_position(("center", main_y - 70)).set_duration(duration))
            elif is_headlight:
                try: sub_txt = TextClip(spaced_sub, fontsize=28, color="#8899aa", font="Arial-Bold", bg_color="transparent")
                except: sub_txt = TextClip(spaced_sub, fontsize=28, color="white", bg_color="transparent")
                layers.append(sub_txt.set_position(("center", main_y - 50)).set_duration(duration))
            else:
                try: sub_txt = TextClip(spaced_sub, fontsize=35, color="white", font="Arial-Bold", bg_color="transparent")
                except: sub_txt = TextClip(spaced_sub, fontsize=35, color="white", bg_color="transparent")
                layers.append(sub_txt.set_position(("center", main_y - 80)).set_duration(duration))

        if is_blueflare:
            def zoom_func_blueflare(t): return 1.0 + 0.03 * (t / duration)
            main_clip = main_clip.fx(vfx.resize, zoom_func_blueflare)
            if shine_clip: shine_clip = shine_clip.fx(vfx.resize, zoom_func_blueflare)

        if is_headlight:
            def zoom_func_headlight(t): return 1.0 + 0.02 * (t / duration)
            main_clip = main_clip.fx(vfx.resize, zoom_func_headlight)
            if shine_clip: shine_clip = shine_clip.fx(vfx.resize, zoom_func_headlight)

        layers.append(main_clip)
        if shine_clip is not None: layers.append(shine_clip)

        if not is_deepspace and not is_lightspeed and not is_travelling and not is_blueflare and not is_headlight:
            yv, xv = np.mgrid[:target_h, :target_w]
            vd = np.sqrt(((xv - target_w/2)/(target_w*0.55))**2 + ((yv - target_h/2)/(target_h*0.55))**2)
            vig_a = np.clip(vd**1.6*0.72, 0, 1).astype(np.float32)
            vig_clip = ImageClip(np.zeros((target_h, target_w, 3), dtype=np.uint8)).set_mask(ImageClip(vig_a, ismask=True)).set_duration(duration)
            layers.append(vig_clip)

        if is_lightspeed:
            trans_dur = 1.2
            trans_start = duration - trans_dur
            impact_time = trans_start + 0.4

            def make_fusion_frame(t):
                frame = np.zeros((target_h, target_w, 3), dtype=np.float32)
                if t < trans_start: return frame.astype(np.uint8)
                    
                y_g, x_g = np.mgrid[:target_h, :target_w]
                cy, cx = target_h / 2.0, target_w / 2.0
                
                if t < impact_time:
                    p_in = (t - trans_start) / (impact_time - trans_start)
                    tip_l = cx * p_in
                    beam_len = 200 + 400 * p_in
                    tail_l = max(0, tip_l - beam_len)
                    beam_th = 8.0
                    
                    mask_l = (x_g < tip_l) & (x_g > tail_l) & (np.abs(y_g - cy) < beam_th)
                    glow_l = np.exp(-0.5 * (np.abs(y_g - cy) / (beam_th*2))**2) * (x_g < tip_l) * (x_g > tail_l)
                    
                    frame[..., 1] += glow_l * 255 
                    frame[..., 2] += glow_l * 255 
                    frame[mask_l] = [255, 255, 255]
                    
                    tip_r = target_w - (cx * p_in)
                    tail_r = min(target_w, tip_r + beam_len)
                    
                    mask_r = (x_g > tip_r) & (x_g < tail_r) & (np.abs(y_g - cy) < beam_th)
                    glow_r = np.exp(-0.5 * (np.abs(y_g - cy) / (beam_th*2))**2) * (x_g > tip_r) * (x_g < tail_r)
                    
                    frame[..., 0] += glow_r * 255 
                    frame[..., 2] += glow_r * 150 
                    frame[mask_r] = [255, 255, 255]
                    
                else:
                    p_ex = (t - impact_time) / (duration - impact_time) 
                    
                    beam_th = 6.0 + p_ex * 30.0
                    glow_l = np.exp(-0.5 * (np.abs(y_g - cy) / beam_th)**2) * (x_g <= cx)
                    glow_r = np.exp(-0.5 * (np.abs(y_g - cy) / beam_th)**2) * (x_g > cx)
                    
                    frame[..., 0] += glow_r * 255
                    frame[..., 1] += glow_l * 255
                    frame[..., 2] += glow_l * 255 + glow_r * 150
                    
                    core_beam = np.abs(y_g - cy) < (3.0 + p_ex * 15)
                    frame[core_beam] = [255, 255, 255]
                    
                    dist = np.sqrt((x_g - cx)**2 + (y_g - cy)**2)
                    radius = 20 + (target_w * 2.0) * (p_ex**2.5)
                    intensity = 1.0 + p_ex * 8.0
                    core = np.clip(1.0 - (dist / radius), 0, 1)**2 * intensity
                    
                    spike_len = 150 + target_w * p_ex**2
                    spike_th = 3.0 + p_ex * 15.0
                    spikes = np.exp(-0.5 * (np.abs(x_g - cx)/spike_len)**2 - 0.5 * (np.abs(y_g - cy)/spike_th)**2)
                    spikes += np.exp(-0.5 * (np.abs(y_g - cy)/spike_len)**2 - 0.5 * (np.abs(x_g - cx)/spike_th)**2)
                    
                    dx = x_g - cx
                    dy = y_g - cy
                    diag1 = np.abs(dx - dy) / 1.414
                    diag2 = np.abs(dx + dy) / 1.414
                    diag_len = 100 + target_w * 0.7 * p_ex**2
                    diag_th = 2.0 + p_ex * 8.0
                    spikes += 0.8 * np.exp(-0.5 * (diag1/diag_th)**2 - 0.5 * (np.abs(dx+dy)/1.414/diag_len)**2)
                    spikes += 0.8 * np.exp(-0.5 * (diag2/diag_th)**2 - 0.5 * (np.abs(dx-dy)/1.414/diag_len)**2)
                    
                    burst = np.clip(core + spikes * intensity, 0, 1)
                    
                    side_blend = np.clip((x_g - (cx - 200)) / 400.0, 0, 1) 
                    r_burst = 100 * (1 - side_blend) + 255 * side_blend
                    g_burst = 255 * (1 - side_blend) + 50 * side_blend
                    b_burst = 255 * (1 - side_blend) + 150 * side_blend
                    
                    frame[..., 0] += burst * r_burst
                    frame[..., 1] += burst * g_burst
                    frame[..., 2] += burst * b_burst
                    
                    white_core = np.clip(1.0 - (dist / (radius*0.4)), 0, 1)**1.5 * intensity
                    frame[..., 0] += white_core * 255
                    frame[..., 1] += white_core * 255
                    frame[..., 2] += white_core * 255
                
                return np.clip(frame, 0, 255).astype(np.uint8)

            def make_fusion_mask(t):
                if t < trans_start: return np.zeros((target_h, target_w), dtype=np.float32)
                y_g, x_g = np.mgrid[:target_h, :target_w]
                cy, cx = target_h / 2.0, target_w / 2.0

                if t < impact_time:
                    p_in = (t - trans_start) / (impact_time - trans_start)
                    tip_l = cx * p_in
                    beam_len = 200 + 400 * p_in
                    tail_l = max(0, tip_l - beam_len)
                    
                    tip_r = target_w - (cx * p_in)
                    tail_r = min(target_w, tip_r + beam_len)
                    beam_th = 8.0
                    
                    mask_l = np.exp(-0.5 * (np.abs(y_g - cy) / (beam_th*2))**2) * (x_g < tip_l) * (x_g > tail_l)
                    mask_r = np.exp(-0.5 * (np.abs(y_g - cy) / (beam_th*2))**2) * (x_g > tip_r) * (x_g < tail_r)
                    return np.clip(mask_l + mask_r, 0, 1).astype(np.float32)
                else:
                    p_ex = (t - impact_time) / (duration - impact_time)
                    dist = np.sqrt((x_g - cx)**2 + (y_g - cy)**2)
                    radius = 20 + (target_w * 2.0) * (p_ex**2.5)
                    intensity = 1.0 + p_ex * 8.0
                    glow = np.clip(1.0 - (dist / radius), 0, 1)**1.5 * intensity
                    
                    beam_th = 6.0 + p_ex * 30.0
                    beams = np.exp(-0.5 * (np.abs(y_g - cy) / beam_th)**2)
                    return np.clip(glow + beams, 0, 1).astype(np.float32)

            fusion_clip = VideoClip(make_fusion_frame, duration=duration).set_mask(VideoClip(make_fusion_mask, duration=duration, ismask=True))
            layers.append(fusion_clip)

        elif is_deepspace:
            sn_dur = 0.8 
            sn_start = duration - sn_dur

            def make_sn_frame(t): return np.full((target_h, target_w, 3), 255, dtype=np.uint8)
            Y_sn, X_sn = np.mgrid[0:target_h, 0:target_w]
            sn_x = target_w / 2.0; sn_y = target_h / 2.0
            dist_from_center = np.sqrt((X_sn - sn_x)**2 + (Y_sn - sn_y)**2)
            
            def make_sn_mask(t):
                if t < sn_start: return np.zeros((target_h, target_w), dtype=np.float32)
                p = (t - sn_start) / sn_dur 
                radius = 20 + (target_w * 2.5) * (p**2.5) 
                intensity = 1.0 + (p * 8.0) 
                glow = np.clip(1.0 - (dist_from_center / radius), 0, 1)**1.5 * intensity
                return np.clip(glow, 0, 1)

            sn_clip = VideoClip(make_sn_frame, duration=duration).set_mask(VideoClip(make_sn_mask, duration=duration, ismask=True))
            layers.append(sn_clip)

        card = CompositeVideoClip(layers, size=(target_w, target_h)).set_duration(duration)

        if not preview_mode and (is_deepspace or is_lightspeed or is_travelling) and not item.get("muted", False):
            fps_audio = 44100; total_samples = int(duration * fps_audio); t_audio = np.linspace(0, duration, total_samples, endpoint=False); audio_mono = np.zeros(total_samples, dtype=np.float32)
            if is_deepspace:
                sn_dur = 0.8; sn_start = duration - sn_dur; comet_dur = 2.0; comet_start = max(0.0, sn_start - comet_dur)
                mask_comet = ((t_audio - comet_start) / comet_dur >= 0) & ((t_audio - comet_start) / comet_dur <= 1)
                if np.any(mask_comet):
                    p_comet = (t_audio[mask_comet] - comet_start) / comet_dur; env_comet = np.sin(p_comet * np.pi)**2; noise = np.random.uniform(-0.5, 0.5, np.sum(mask_comet)); freq = 800 - 500*np.sin(p_comet*np.pi) + 900*(p_comet**3)
                    audio_mono[mask_comet] += (noise * 0.6 + np.sin(2 * np.pi * freq * t_audio[mask_comet]) * 0.4) * env_comet * 0.8
                boom_start = sn_start; boom_dur = sn_dur; mask_boom = ((t_audio - boom_start) / boom_dur >= 0) & ((t_audio - boom_start) / boom_dur <= 1)
                if np.any(mask_boom):
                    p_boom = (t_audio[mask_boom] - boom_start) / boom_dur; env_sn = np.exp(-4 * p_boom); noise = np.random.uniform(-1.0, 1.0, np.sum(mask_boom)); freq = 150 * np.exp(-4 * p_boom) + 40
                    audio_mono[mask_boom] += (noise * 0.8 + np.sin(2 * np.pi * freq * t_audio[mask_boom]) * 0.6) * env_sn * 1.0
            elif is_lightspeed:
                trans_dur = 1.2; trans_start = duration - trans_dur; impact_time = trans_start + 0.4
                mask_in = ((t_audio - trans_start) / 0.4 >= 0) & ((t_audio - trans_start) / 0.4 <= 1)
                if np.any(mask_in):
                    p_in = (t_audio[mask_in] - trans_start) / 0.4
                    audio_mono[mask_in] += (np.sin(2 * np.pi * (400 + 1200 * p_in) * t_audio[mask_in]) + np.sin(2 * np.pi * (500 + 1400 * p_in) * t_audio[mask_in])) * 0.2 * (p_in**2)
                mask_boom = ((t_audio - impact_time) / (duration - impact_time) >= 0) & ((t_audio - impact_time) / (duration - impact_time) <= 1)
                if np.any(mask_boom):
                    p_boom = (t_audio[mask_boom] - impact_time) / (duration - impact_time)
                    audio_mono[mask_boom] += (np.random.uniform(-1.0, 1.0, np.sum(mask_boom)) * 0.8 + np.sin(2 * np.pi * (120 * np.exp(-5 * p_boom) + 30) * t_audio[mask_boom]) * 0.7) * np.exp(-4 * p_boom) * 1.0
            elif is_travelling:
                p = t_audio / duration
                audio_mono += (np.random.uniform(-0.5, 0.5, total_samples) * 0.3 + np.sin(2 * np.pi * (300 - 150 * p) * t_audio) * 0.2) * np.exp(-0.5 * ((p - 0.5) / 0.15)**2) * 0.5
            audio_mono = np.clip(audio_mono, -1.0, 1.0); audio_stereo = np.column_stack((audio_mono, audio_mono))
            card = card.set_audio(AudioArrayClip(audio_stereo, fps=fps_audio))

        return card.fadein(0.8) if not preview_mode else card

    # ══════════════════════════════════════════════════════════
    # EXPORT MERGING ENGINE  ← ALL FIXES ARE IN THIS SECTION
    # ══════════════════════════════════════════════════════════
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


if __name__ == "__main__":
    root = tk.Tk()
    app = VideoMergerStudio(root)
    root.mainloop()