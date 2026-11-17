import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import os
import time
import warnings
import numpy as np

# --- SILENCE ANNOYING PILLOW WARNINGS ---
warnings.filterwarnings("ignore", category=DeprecationWarning)

import PIL.Image
from PIL import ImageTk, ImageDraw, ImageFont

# --- PIL ANTIALIAS FIX FOR PILLOW >= 10.0.0 ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

# --- IMAGEMAGICK PATH ---
os.environ["IMAGEMAGICK_BINARY"] = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"

from moviepy.editor import (
    VideoFileClip, ImageClip, ColorClip, CompositeVideoClip, TextClip, 
    AudioFileClip, CompositeAudioClip, VideoClip, concatenate_audioclips
)
from moviepy.audio.AudioClip import AudioArrayClip
import moviepy.video.fx.all as vfx

# --- AUDIO PLAYBACK ENGINE ---
try:
    import pygame
    pygame.mixer.init()
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False
    print("WARNING: Pygame not installed. Run 'pip install pygame' for live audio playback.")

# ══════════════════════════════════════════════════════════════════
#  COLOUR TOKENS (CapCut-inspired dark studio palette)
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
    "clip_mute":    "#6e1a1a"
}

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tw: 
            return
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
    if w: 
        kw["width"] = w
    b = tk.Button(parent, **kw)
    Tooltip(b, tip)
    return b

def create_scroll_canvas(parent, bg_color):
    """Creates a scrollable canvas layout to prevent UI cutoff."""
    canvas = tk.Canvas(parent, bg=bg_color, highlightthickness=0)
    scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
    inner = tk.Frame(canvas, bg=bg_color)
    
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw", width=300)
    canvas.configure(yscrollcommand=scroll.set)
    
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    return canvas, inner

# ══════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════
class VideoMergerStudio:
    TRACK_H = 64
    AUDIO_TRACK_H = 48
    RULER_H = 24
    PPS = 80
    MIN_PPS = 20
    MAX_PPS = 400
    LABEL_W = 90

    def __init__(self, root):
        self.root = root
        self.root.title("Ultimate NLE Studio Pro (InShot Edition)")
        self.root.geometry("1400x900")
        self.root.configure(bg=C["bg"])

        self.media_queue = []
        self.bgm_tracks = []
        
        self.selected_idx = None
        self.selected_audio_idx = None
        
        self.thumbs = {}
        self._clip_cache = {} 
        self.preview_img = None
        
        self.playhead_t = tk.DoubleVar(value=0.0)
        self.is_playing = False
        self.play_thread = None
        self.timeline_dirty = True
        self.audio_ready = False
        self.temp_audio_path = "temp_preview_audio.wav"

        self._drag_item = None
        self._drag_start_x = 0
        self._drag_orig_start = 0.0
        self._is_scrubbing = False
        self._preview_job = None 

        self._build_ui()
        self.refresh_timeline()

    def _build_ui(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure(".", background=C["panel"], foreground=C["text"])
        self.style.configure("TFrame", background=C["panel"])
        self.style.configure("TLabel", background=C["panel"], foreground=C["text"], font=("Segoe UI", 10))
        self.style.configure("Horizontal.TScale", background=C["panel"], troughcolor=C["raised"])

        tb = tk.Frame(self.root, bg=C["surface"], height=44)
        tb.pack(side=tk.TOP, fill=tk.X)
        tb.pack_propagate(False)
        self._build_toolbar(tb)

        main = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=C["bg"], sashwidth=4, sashrelief="flat")
        main.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left = tk.Frame(main, bg=C["panel"], width=280)
        left.pack_propagate(False)
        main.add(left, minsize=220)
        self._build_left_panel(left)

        center = tk.Frame(main, bg="#000000")
        main.add(center, minsize=500)
        self._build_player_panel(center)

        right = tk.Frame(main, bg=C["panel"], width=350)
        right.pack_propagate(False)
        main.add(right, minsize=320)
        self._build_inspector_panel(right)

        bottom = tk.Frame(self.root, bg=C["bg"], height=280)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, expand=False, padx=5, pady=5)
        bottom.pack_propagate(False)
        self._build_timeline_panel(bottom)

    def _build_toolbar(self, tb):
        tk.Label(tb, text="🎬 NLE Studio Pro", bg=C["surface"], fg=C["accent"], font=("Arial", 12, "bold")).pack(side=tk.LEFT, padx=12)
        
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
        
        icon_btn(tb, "🚀 EXPORT", "Export video", self.start_merge_thread, bg=C["danger"], w=12).pack(side=tk.RIGHT, padx=10, pady=6)

    # ==========================================
    # TRANSPORT CONTROLS
    # ==========================================
    def go_to_start(self):
        self._set_playhead(0.0)

    def rewind_5(self):
        self._set_playhead(max(0.0, self.playhead_t.get() - 5.0))

    def forward_5(self):
        self._set_playhead(min(self._total_duration(), self.playhead_t.get() + 5.0))

    def go_to_end(self):
        self._set_playhead(self._total_duration())

    def zoom_in(self):
        self.PPS = min(self.MAX_PPS, int(self.PPS * 1.5))
        self.refresh_timeline()

    def zoom_out(self):
        self.PPS = max(self.MIN_PPS, int(self.PPS / 1.5))
        self.refresh_timeline()

    # ==========================================
    # UI PANELS
    # ==========================================
    def _build_left_panel(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill=tk.BOTH, expand=True)
        
        self.style.configure("TNotebook", background=C["panel"], borderwidth=0)
        self.style.configure("TNotebook.Tab", background=C["raised"], foreground=C["text_dim"], padding=[8, 4])
        self.style.map("TNotebook.Tab", background=[("selected", C["surface"])], foreground=[("selected", C["accent"])])

        f1 = tk.Frame(nb, bg=C["panel"])
        nb.add(f1, text=" Media Pool ")
        c1, inner1 = create_scroll_canvas(f1, C["panel"])
        
        btn_opts = {"bg": "#333", "fg": "white", "bd": 0, "font": ("Segoe UI", 10)}
        tk.Label(inner1, text="MEDIA IMPORT", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 10, "bold")).pack(pady=10, anchor="w", padx=10)
        
        tk.Button(inner1, text="➕ Add Video/Photo", command=self.add_media, **btn_opts).pack(fill=tk.X, padx=10, pady=5, ipady=4)
        tk.Button(inner1, text="🎵 Add Background Audio", command=self.add_bgm_track, **btn_opts).pack(fill=tk.X, padx=10, pady=5, ipady=4)
        tk.Button(inner1, text="✨ Add Title Card", command=self.add_title_card, **btn_opts).pack(fill=tk.X, padx=10, pady=5, ipady=4)
        tk.Button(inner1, text="[ ] Add Placeholder", command=self.add_placeholder, **btn_opts).pack(fill=tk.X, padx=10, pady=5, ipady=4)

        tk.Label(inner1, text="STUDIO TEMPLATES", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 10, "bold")).pack(pady=(20, 5), anchor="w", padx=10)
        tk.Button(inner1, text="Deep Space + Aurora", bg="#3b0086", fg="white", bd=0, command=lambda: self.apply_template(1)).pack(fill=tk.X, padx=10, pady=3, ipady=3)
        tk.Button(inner1, text="Light Burst + Purple Box", bg="#c200ff", fg="white", bd=0, command=lambda: self.apply_template(2)).pack(fill=tk.X, padx=10, pady=3, ipady=3)
        tk.Button(inner1, text="Cinematic Flare + Magical", bg="#0088aa", fg="white", bd=0, command=lambda: self.apply_template(3)).pack(fill=tk.X, padx=10, pady=3, ipady=3)

        tk.Label(inner1, text="OUTPUT FORMAT", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 10, "bold")).pack(pady=(20, 5), anchor="w", padx=10)
        self.format_var = tk.StringVar(value="desktop")
        tk.Radiobutton(inner1, text="16:9 Landscape", variable=self.format_var, value="desktop", bg=C["panel"], fg="white", selectcolor=C["raised"]).pack(anchor="w", padx=14)
        tk.Radiobutton(inner1, text="9:16 Portrait", variable=self.format_var, value="mobile", bg=C["panel"], fg="white", selectcolor=C["raised"]).pack(anchor="w", padx=14)
        
        self.smart_fill_var = tk.BooleanVar(value=True)
        self.auto_rotate_var = tk.BooleanVar(value=True)
        tk.Checkbutton(inner1, text="Smart Fill (Crop)", variable=self.smart_fill_var, bg=C["panel"], fg="white", selectcolor=C["raised"]).pack(anchor="w", pady=(5,0), padx=14)
        tk.Checkbutton(inner1, text="Auto-Rotate", variable=self.auto_rotate_var, bg=C["panel"], fg="white", selectcolor=C["raised"]).pack(anchor="w", pady=(0,10), padx=14)

        self.status_label = tk.Label(inner1, text="Ready.", bg=C["panel"], fg=C["accent3"], font=("Segoe UI", 9, "bold"))
        self.status_label.pack(pady=5)

    def _build_player_panel(self, parent):
        self.preview_label = tk.Label(parent, bg="#000000", text="NO MEDIA SELECTED", fg="#444444", font=("Segoe UI", 24, "bold"))
        self.preview_label.pack(fill=tk.BOTH, expand=True)

    def _build_inspector_panel(self, parent):
        tk.Label(parent, text="INSPECTOR PROPERTIES", bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 10, "bold")).pack(pady=10, anchor="w", padx=10)
        
        self.insp_canvas, self.insp_inner = create_scroll_canvas(parent, C["panel"])
        
        self.ins_scale = tk.DoubleVar(value=1.0)
        self.ins_opacity = tk.DoubleVar(value=1.0)
        self.ins_x = tk.IntVar(value=0)
        self.ins_y = tk.IntVar(value=0)
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
        
        self.render_inspector()

    def _build_timeline_panel(self, parent):
        toolbar = tk.Frame(parent, bg="#111", height=35)
        toolbar.pack(fill=tk.X, side=tk.TOP)
        toolbar.pack_propagate(False)
        tk.Label(toolbar, text="DRAG & DROP TIMELINE", bg="#111", fg="#888", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=10)
        
        tk.Button(toolbar, text="✂️ Split at Playhead", bg=C["danger"], fg="white", bd=0, font=("Segoe UI", 8, "bold"), command=self.split_at_playhead).pack(side=tk.RIGHT, padx=10, pady=5)

        self.timeline_canvas = tk.Canvas(parent, bg="#181818", highlightthickness=0, cursor="crosshair")
        self.timeline_scroll = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=self.timeline_canvas.xview)
        self.timeline_canvas.configure(xscrollcommand=self.timeline_scroll.set)
        
        self.timeline_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.timeline_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.timeline_canvas.bind("<ButtonPress-1>", self.on_tl_press)
        self.timeline_canvas.bind("<B1-Motion>", self.on_tl_drag)
        self.timeline_canvas.bind("<ButtonRelease-1>", self.on_tl_release)

    # ==========================================
    # DATA MODELS & ACTIONS
    # ==========================================
    def create_clip_model(self, mtype, path="", name=""):
        return {
            'type': mtype, 'path': path, 'name': name,
            'clip_start': 0.0, 'clip_end': 0.0, 'speed': 1.0, 'duration': 5.0,
            'rotation': 0, 'flip_h': False, 'flip_v': False,
            'scale': 1.0, 'opacity': 1.0, 'x_offset': 0, 'y_offset': 0,
            'volume': 1.0, 'muted': False,
            'text': '', 'text_start': 0.0, 'text_end': 3.0, 'lt_style': 'Static Aurora Tile (Bracket)',
            'trans': 'Crossfade',
            'main_text': 'NEW TITLE', 'sub_text': 'Subtitle', 'theme': 'Cinematic – Light Speed Starburst'
        }

    def add_media(self):
        paths = filedialog.askopenfilenames(filetypes=[("Media", "*.mp4 *.mov *.jpg *.png")])
        for p in paths:
            ext = p.lower().split('.')[-1]
            mtype = 'image' if ext in ['jpg', 'jpeg', 'png'] else 'video'
            self.media_queue.append(self.create_clip_model(mtype, p, os.path.basename(p)))
        self.refresh_timeline()

    def add_bgm_track(self):
        paths = filedialog.askopenfilenames(filetypes=[("Audio", "*.mp3 *.wav *.aac")])
        for p in paths:
            self.bgm_tracks.append({
                'type': 'audio', 'path': p, 'name': os.path.basename(p),
                'volume': 1.0, 'start_offset': 0.0, 'clip_start': 0.0, 'clip_end': 0.0, 'duration': 10.0
            })
        self.refresh_timeline()

    def add_title_card(self):
        self.media_queue.append(self.create_clip_model('title', name='TITLE CARD'))
        self.refresh_timeline()

    def add_placeholder(self):
        item = self.create_clip_model('placeholder', name='PLACEHOLDER')
        item['text'] = "Your Text Here"
        self.media_queue.append(item)
        self.refresh_timeline()

    def apply_template(self, tid):
        if not messagebox.askyesno("Template", "Append template sequence to your timeline?"): return
        if tid == 1:
            t1 = self.create_clip_model('title', name='TITLE CARD')
            t1.update({'main_text': 'DEEP SPACE', 'sub_text': 'EXPLORATION', 'theme': 'Cinematic – Deep Space Stars'})
            p1 = self.create_clip_model('placeholder', name='PLACEHOLDER')
            p1.update({'text': 'ASTRO PHYSICS', 'text_start': 0.0, 'text_end': 4.0, 'duration': 6.0})
            self.media_queue.extend([t1, p1])
        elif tid == 2:
            t1 = self.create_clip_model('title', name='TITLE CARD')
            t1.update({'main_text': 'LIGHT SPEED', 'sub_text': 'FUSION', 'trans': 'Zoom In Fade', 'theme': 'Cinematic – Light Speed Starburst'})
            p1 = self.create_clip_model('placeholder', name='PLACEHOLDER')
            p1.update({'text': 'HYPER DRIVE ACTIVATED', 'lt_style': 'Purple Designer Box'})
            self.media_queue.extend([t1, p1])
        elif tid == 3:
            t1 = self.create_clip_model('title', name='TITLE CARD')
            t1.update({'main_text': 'THE JOURNEY', 'sub_text': 'BEGINS NOW', 'trans': 'Dip to Black', 'theme': 'Cinematic – Travelling Flare (Dynamic)', 'duration': 6.0})
            p1 = self.create_clip_model('placeholder', name='PLACEHOLDER')
            p1.update({'text': 'MAGICAL AURORA', 'duration': 7.0, 'text_end': 5.0, 'lt_style': 'Aurora Wave'})
            self.media_queue.extend([t1, p1])
        self.refresh_timeline()

    def fill_placeholder(self):
        path = filedialog.askopenfilename()
        if not path: return
        ext = path.lower().split('.')[-1]
        
        if self.selected_idx is not None:
            item = self.media_queue[self.selected_idx]
            item['path'] = path
            item['type'] = 'image' if ext in ['jpg', 'jpeg', 'png'] else 'video'
            item['name'] = os.path.basename(path)
            item['clip_start'] = 0.0
            item['clip_end'] = 0.0
        
        self.thumbs.clear()
        self.update_global_preview()
        self.refresh_timeline()

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
        self.thumbs.clear()
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
        self.thumbs.clear()
        self.refresh_timeline()

    def delete_selected(self):
        self.is_playing = False
        if HAS_PYGAME: 
            pygame.mixer.music.stop()
            
        if self.selected_audio_idx is not None: 
            del self.bgm_tracks[self.selected_audio_idx]
        elif self.selected_idx is not None: 
            del self.media_queue[self.selected_idx]
            
        self.selected_idx = None
        self.selected_audio_idx = None
        self.thumbs.clear()
        self.update_global_preview()
        self.refresh_timeline()

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
            s = item.get("clip_start", 0.0)
            e = item.get("clip_end", 0.0)
            if e <= s:
                try:
                    if item['path'] not in self._clip_cache:
                        self._clip_cache[item['path']] = VideoFileClip(item['path'])
                    dur = self._clip_cache[item['path']].duration
                except:
                    dur = 5.0
            else:
                dur = e - s
            return dur / max(0.1, item.get("speed", 1.0))
        return item.get("duration", 5.0)

    # ==========================================
    # LIVE PLAYBACK ENGINE 
    # ==========================================
    def _build_preview_audio(self):
        self.audio_ready = False
        audio_clips = []
        try:
            for item in self.media_queue:
                if item['type'] == 'video' and not item.get('muted', False):
                    c = VideoFileClip(item['path'])
                    s = item.get('clip_start', 0.0)
                    e = item.get('clip_end', 0.0)
                    if e > s and e <= c.duration: 
                        c = c.subclip(s, e)
                    elif s > 0: 
                        c = c.subclip(s)
                    
                    if item.get('speed', 1.0) != 1.0: 
                        c = c.fx(vfx.speedx, item['speed'])
                    if item.get('volume', 1.0) != 1.0: 
                        c = c.volumex(item['volume'])
                    
                    c = c.set_duration(self._item_duration(item))
                    c = c.set_start(item.get('tl_start', 0.0))
                    if c.audio: 
                        audio_clips.append(c.audio)
                    
            for bgm in self.bgm_tracks:
                c = AudioFileClip(bgm['path'])
                s = bgm.get('clip_start', 0.0)
                e = bgm.get('clip_end', 0.0)
                if e > s and e <= c.duration: 
                    c = c.subclip(s, e)
                elif s > 0: 
                    c = c.subclip(s)

                if bgm.get('volume', 1.0) != 1.0: 
                    c = c.volumex(bgm['volume'])
                c = c.set_start(bgm.get('start_offset', 0.0))
                audio_clips.append(c)
                    
            if audio_clips:
                comp = CompositeAudioClip(audio_clips)
                comp.set_duration(self._total_duration()).write_audiofile(self.temp_audio_path, fps=44100, logger=None)
                self.audio_ready = True
        except Exception as e:
            print("Audio Mixer Error:", e)
            self.audio_ready = False

    def toggle_play(self):
        if self.is_playing:
            self.is_playing = False
            self.play_btn.config(text="▶", bg=C["accent"], fg=C["bg"])
            if HAS_PYGAME: 
                pygame.mixer.music.stop()
        else:
            if self.timeline_dirty and HAS_PYGAME:
                self.status_label.config(text="Mixing Audio...", fg=C["accent4"])
                self.root.update()
                self._build_preview_audio()
                self.timeline_dirty = False
                self.status_label.config(text="Ready.", fg=C["accent3"])
                
            self.is_playing = True
            self.play_btn.config(text="⏸", bg=C["accent4"], fg=C["bg"])
            self.play_thread = threading.Thread(target=self._playback_loop, daemon=True)
            self.play_thread.start()

    def _playback_loop(self):
        start_t = self.playhead_t.get()
        max_t = self._total_duration()
        
        if self.audio_ready and HAS_PYGAME:
            try:
                pygame.mixer.music.load(self.temp_audio_path)
                pygame.mixer.music.play(start=start_t)
            except Exception: pass

        start_time_sys = time.time()
        while self.is_playing:
            elapsed = time.time() - start_time_sys
            curr_t = start_t + elapsed

            if curr_t >= max_t:
                self.root.after(0, self._set_playhead, max_t)
                break

            self.root.after(0, self._set_playhead, curr_t, False)
            self.root.after(0, self.update_global_preview)
            time.sleep(0.03) 
            
        self.is_playing = False
        self.root.after(0, lambda: self.play_btn.config(text="▶ Play", bg=C["accent3"]))
        if HAS_PYGAME: 
            pygame.mixer.music.stop()

    def update_global_preview(self):
        t = self.playhead_t.get()
        active_item = None
        local_t = 0.0
        
        for item in self.media_queue:
            start = item.get("tl_start", 0.0)
            dur = self._item_duration(item)
            if start <= t < start + dur:
                active_item = item
                local_t = (t - start) * item.get("speed", 1.0)
                break
                
        if not active_item:
            self.preview_label.config(image='', text="BLACK (No Media)")
            return

        try:
            if active_item['type'] == 'video' and active_item.get('path'):
                if active_item['path'] not in self._clip_cache:
                    self._clip_cache[active_item['path']] = VideoFileClip(active_item['path'])
                clip = self._clip_cache[active_item['path']]
                
                read_t = active_item.get('clip_start', 0.0) + local_t
                if clip.duration is not None:
                    read_t = min(read_t, clip.duration - 0.01)
                
                frame = clip.get_frame(read_t)
                img = PIL.Image.fromarray(frame)
                
            elif active_item['type'] == 'image' and active_item.get('path'):
                img = PIL.Image.open(active_item['path']).convert("RGB")
            elif active_item['type'] == 'title':
                img = PIL.Image.new("RGB", (640, 360), (30, 30, 45))
                ImageDraw.Draw(img).text((20, 150), f"[TITLE CARD PREVIEW]\n{active_item.get('main_text','')}", fill=(255, 215, 0))
            else:
                img = PIL.Image.new("RGB", (640, 360), (20, 20, 20))
                ImageDraw.Draw(img).text((100, 150), "PLACEHOLDER", fill=(200, 100, 0))

            rot = active_item.get('rotation', 0)
            if rot != 0: 
                img = img.rotate(-rot, expand=True)
            if active_item.get('flip_h', False): 
                img = img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
            if active_item.get('flip_v', False): 
                img = img.transpose(PIL.Image.FLIP_TOP_BOTTOM)

            if active_item.get('text') and active_item.get('text_start', 0) <= local_t <= active_item.get('text_end', 100):
                d = ImageDraw.Draw(img)
                d.rectangle([10, img.height-80, img.width-10, img.height-20], fill=(0,0,0,128))
                d.text((20, img.height-60), active_item['text'], fill=(255,255,255))

            img.thumbnail((700, 400))
            self.preview_img = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self.preview_img, text="")
        except Exception:
            pass

    def change_rotation(self, direction):
        if self.selected_idx is None: return
        item = self.media_queue[self.selected_idx]
        if direction == 'left': 
            item['rotation'] = (item.get('rotation',0) - 90) % 360
        elif direction == 'right': 
            item['rotation'] = (item.get('rotation',0) + 90) % 360
        elif direction == 'fliph': 
            item['flip_h'] = not item.get('flip_h',False)
        elif direction == 'flipv': 
            item['flip_v'] = not item.get('flip_v',False)
            
        self.update_global_preview()
        if f"t_{self.selected_idx}" in self.thumbs: 
            del self.thumbs[f"t_{self.selected_idx}"]
        self.refresh_timeline()

    def execute_split(self):
        t = self.playhead_t.get()
        split_idx = None
        
        for i, item in enumerate(self.media_queue):
            start = item.get("tl_start", 0.0)
            dur = self._item_duration(item)
            if start < t < start + dur:
                split_idx = i
                break
                
        if split_idx is None:
            return messagebox.showwarning("Error", "Playhead is not over a valid clip to split.")

        item = self.media_queue[split_idx]
        local_t = (t - item.get("tl_start", 0.0)) * item.get("speed", 1.0)
        
        part_b = item.copy()
        
        if item['type'] == 'video':
            split_point_internal = item.get('clip_start', 0.0) + local_t
            item['clip_end'] = split_point_internal
            part_b['clip_start'] = split_point_internal
        else:
            item['duration'] = local_t
            part_b['duration'] = self._item_duration(part_b) - local_t
            
        part_b['tl_start'] = t
        
        self.media_queue.insert(split_idx + 1, part_b)
        self.thumbs.clear()
        self.timeline_dirty = True
        self.refresh_timeline()

    # ==========================================
    # TIMELINE DRAG & SCRUB LOGIC
    # ==========================================
    def get_item_at_x(self, x, y):
        if y > self.RULER_H and y < self.RULER_H + self.TRACK_H + 20: 
            idx = int((x - self.LABEL_W) // 160)
            if 0 <= idx < len(self.media_queue): 
                return ('video', idx)
        elif y > self.RULER_H + self.TRACK_H + 20: 
            idx = int((x - self.LABEL_W) // 160)
            if 0 <= idx < len(self.audio_queue): 
                return ('audio', idx)
        return (None, None)

    def on_tl_press(self, event):
        x = self.timeline_canvas.canvasx(event.x)
        y = self.timeline_canvas.canvasy(event.y)
        
        if y <= self.RULER_H + 10: 
            self._is_scrubbing = True
            if HAS_PYGAME and self.is_playing and self.audio_ready:
                pygame.mixer.music.pause()
            self._set_playhead(max(0.0, (x - self.LABEL_W) / self.PPS))
            return

        self._is_scrubbing = False
        self.selected_idx = None
        self.selected_audio_idx = None
        
        y_cursor = self.RULER_H + 4
        for i, item in enumerate(self.media_queue):
            y_bot = y_cursor + self.TRACK_H
            t_s = item.get("tl_start", 0.0)
            dur = self._item_duration(item)
            x_l = self.LABEL_W + int(t_s * self.PPS)
            x_r = self.LABEL_W + int((t_s + dur) * self.PPS)
            if x_l <= x <= x_r and y_cursor <= y <= y_bot:
                self.selected_idx = i
                self._drag_item = ('video', i)
                self._drag_start_x = x
                self._drag_orig_start = t_s
                self.refresh_timeline()
                return
            y_cursor = y_bot + 2
            
        y_cursor += self.TRACK_H + 14
        for j, bgm in enumerate(self.bgm_tracks):
            y_bot = y_cursor + self.AUDIO_TRACK_H
            t_s = bgm.get("start_offset", 0.0)
            dur = bgm.get("duration", 10.0)
            x_l = self.LABEL_W + int(t_s * self.PPS)
            x_r = self.LABEL_W + int((t_s + dur) * self.PPS)
            if x_l <= x <= x_r and y_cursor <= y <= y_bot:
                self.selected_audio_idx = j
                self._drag_item = ('audio', j)
                self._drag_start_x = x
                self._drag_orig_start = t_s
                self.refresh_timeline()
                return
            y_cursor = y_bot + 2

        self.refresh_timeline()

    def on_tl_drag(self, event):
        x = self.timeline_canvas.canvasx(event.x)
        
        if self._is_scrubbing:
            self._set_playhead(max(0.0, (x - self.LABEL_W) / self.PPS))
            return
            
        if self._drag_item:
            itype, idx = self._drag_item
            delta_t = (x - self._drag_start_x) / self.PPS
            new_start = max(0.0, self._drag_orig_start + delta_t)
            
            if itype == 'video':
                self.media_queue[idx]["tl_start"] = new_start
                for i in range(idx+1, len(self.media_queue)):
                    self.media_queue[i]["tl_start"] = self.media_queue[i-1]["tl_start"] + self._item_duration(self.media_queue[i-1])
            else:
                self.bgm_tracks[idx]["start_offset"] = new_start
                
            self.timeline_dirty = True
            self.refresh_timeline()

    def on_tl_release(self, event):
        if self._is_scrubbing and HAS_PYGAME and self.is_playing and self.audio_ready:
            try:
                pygame.mixer.music.play(start=self.playhead_t.get())
            except:
                pass
            
        self._is_scrubbing = False
        self._drag_item = None

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
            if self._preview_job is not None:
                self.root.after_cancel(self._preview_job)
            self._preview_job = self.root.after(30, self.update_global_preview)

    # ==========================================
    # FILMSTRIP RENDER
    # ==========================================
    def generate_filmstrip(self, path, mtype, rot, fh, fv):
        try:
            if not path: return None
            if mtype == 'image': 
                img = PIL.Image.open(path)
                if rot != 0: img = img.rotate(-rot, expand=True)
                if fh: img = img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
                if fv: img = img.transpose(PIL.Image.FLIP_TOP_BOTTOM)
                img.thumbnail((140, 80))
                return ImageTk.PhotoImage(img)
            else:
                if path not in self._clip_cache:
                    self._clip_cache[path] = VideoFileClip(path)
                clip = self._clip_cache[path]
                
                frames = []
                for t in [0.1, clip.duration/2, clip.duration*0.9]:
                    try:
                        f = PIL.Image.fromarray(clip.get_frame(t))
                        if rot != 0: f = f.rotate(-rot, expand=True)
                        if fh: f = f.transpose(PIL.Image.FLIP_LEFT_RIGHT)
                        if fv: f = f.transpose(PIL.Image.FLIP_TOP_BOTTOM)
                        f.thumbnail((46, 80)) 
                        frames.append(f)
                    except: pass

                if frames:
                    strip = PIL.Image.new('RGB', (140, 80))
                    for idx, f in enumerate(frames): strip.paste(f, (idx * 46, 0))
                    return ImageTk.PhotoImage(strip)
                return None
        except: return None

    def refresh_timeline(self):
        c = self.timeline_canvas
        c.delete("all")
        
        total_dur = self._total_duration()
        canvas_w = max(self.LABEL_W + int(total_dur * self.PPS) + 200, 900)
        canvas_h = self.RULER_H + (len(self.media_queue)+len(self.bgm_tracks)+2)*(self.TRACK_H)
        c.configure(scrollregion=(0, 0, canvas_w, canvas_h))

        c.create_rectangle(0, 0, canvas_w, self.RULER_H, fill=C["surface"], outline="")
        for t in np.arange(0.0, total_dur + 10.0, 1.0):
            x = self.LABEL_W + int(t * self.PPS)
            c.create_line(x, self.RULER_H-5, x, self.RULER_H, fill=C["text_dim"])
            if t % 5 == 0:
                mins = int(t) // 60
                secs = int(t) % 60
                c.create_text(x, self.RULER_H//2, text=f"{mins:02d}:{secs:02d}", fill=C["text_dim"], font=("Courier", 8))

        c.create_rectangle(0, 0, self.LABEL_W, canvas_h, fill=C["surface"], outline="")

        y_cursor = self.RULER_H + 4
        
        # --- TRACK 1: VIDEO ---
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
            c.create_rectangle(x_l, y_cursor, x_r, y_bot, fill=C["clip_video"] if item["type"]!="title" else "#2a0050", outline=outline_col, width=2 if is_sel else 1)
            
            if item['type'] == 'title': 
                c.create_text(x_l + item_w/2, y_cursor + 20, text="[ TITLE ]", fill="#E5D5A0", font=("Segoe UI", 10, "bold"))
            elif item['type'] == 'placeholder' and not item.get('path'): 
                c.create_text(x_l + item_w/2, y_cursor + 20, text="PLACEHOLDER", fill="#FF9800", font=("Segoe UI", 9, "bold"))
            else:
                t_key = f"t_{i}"
                if t_key not in self.thumbs: self.thumbs[t_key] = self.generate_filmstrip(item.get('path'), item['type'], item.get('rotation',0), item.get('flip_h',False), item.get('flip_v',False))
                if self.thumbs.get(t_key): 
                    c.create_image(x_l, y_cursor, image=self.thumbs[t_key], anchor="nw")

            dur_text = f"[{item.get('clip_start', 0.0):.1f}s-{item.get('clip_end', 0.0):.1f}s]" if item['type'] == 'video' else f"{item.get('duration',5.0)}s"
            if item.get('muted'): dur_text += " 🔇"
            c.create_rectangle(x_l, y_bot - 16, x_r, y_bot, fill="#111", outline="")
            c.create_text(x_l + 4, y_bot - 8, text=dur_text, fill="#aaa", font=("Segoe UI", 8), anchor="w")
            
            if item.get('text'):
                t_dur = max(0.1, float(item.get('duration', 5.0)))
                txt_w = item_w * ((item['text_end'] - item['text_start']) / t_dur)
                txt_x = x_l + item_w * (item['text_start'] / t_dur)
                c.create_rectangle(txt_x, y_bot + 5, txt_x + txt_w, y_bot + 20, fill="#00A8FF", outline="")
                c.create_text(txt_x + 5, y_bot + 12, text="T", fill="white", font=("Segoe UI", 7, "bold"), anchor="w")

            c.create_text(self.LABEL_W//2, (y_cursor+y_bot)//2, text=f"V{i+1}", fill=C["text_dim"], font=("Arial", 8, "bold"))
            curr_t += dur
            
        y_cursor += self.TRACK_H + 10
        max_vid_x = self.LABEL_W + int(curr_t * self.PPS)

        # --- TRACK 2: AUDIO ---
        c.create_line(0, y_cursor, max(2000, max_vid_x), y_cursor, fill=C["border"], dash=(4,4))
        y_cursor += 4
        
        aud_h = 40
        max_aud_x = self.LABEL_W
        for j, aud in enumerate(self.bgm_tracks):
            is_sel = (j == self.selected_audio_idx)
            outline_col = "white" if is_sel else C["border"]
            
            t_s = aud.get('start_offset', 0.0)
            try:
                if aud['path'] not in self._clip_cache:
                    self._clip_cache[aud['path']] = AudioFileClip(aud['path'])
                dur = self._clip_cache[aud['path']].duration
            except:
                dur = 10.0
                
            x_l = self.LABEL_W + int(t_s * self.PPS)
            x_r = self.LABEL_W + int((t_s + dur) * self.PPS)
            y_bot = y_cursor + aud_h
            
            c.create_rectangle(x_l, y_cursor, x_r, y_bot, fill=C["clip_bgm"], outline=outline_col, width=2 if is_sel else 1)
            c.create_text(x_l + 6, y_cursor + 10, text="🎵 " + aud['name'][:20], fill="white", font=("Segoe UI", 8, "bold"), anchor="w")
            c.create_text(x_l + 6, y_cursor + 25, text=f"Vol: {aud.get('volume',1.0)*100}%", fill="#aaa", font=("Segoe UI", 7), anchor="w")
            
            c.create_text(self.LABEL_W//2, (y_cursor+y_bot)//2, text=f"A{j+1}", fill=C["accent3"], font=("Arial", 8, "bold"))
            y_cursor = y_bot + 2
            if x_r > max_aud_x: max_aud_x = x_r
            
        c.configure(scrollregion=(0, 0, max(max_vid_x, max_aud_x) + 200, 200))
        
        self._set_playhead(self.playhead_t.get(), preview=False)
        self.render_inspector()

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

        tk.Label(f, text=f"EDIT: {item.get('type', 'audio').upper()}", bg=C["panel"], fg="#FFD700", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(10,5))
        
        def row(label, widget_fn):
            r = tk.Frame(f, bg=C["panel"])
            r.pack(fill=tk.X, padx=8, pady=3)
            tk.Label(r, text=label, bg=C["panel"], fg=C["text_dim"], font=("Arial",8), width=14, anchor="e").pack(side=tk.LEFT)
            widget_fn(r)

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
            self.ins_scale = tk.DoubleVar(value=item.get('scale', 1.0))
            self.ins_opacity = tk.DoubleVar(value=item.get('opacity', 1.0))
            self.ins_x = tk.IntVar(value=item.get('x_offset', 0))
            self.ins_y = tk.IntVar(value=item.get('y_offset', 0))
            self.ins_dur = tk.DoubleVar(value=item.get('duration', 5.0))
            self.ins_speed = tk.DoubleVar(value=item.get('speed', 1.0))
            self.ins_trans = tk.StringVar(value=item.get('trans', 'Crossfade'))
            
            tk.Label(f, text="Scale & Opacity:", bg=C["panel"], fg=C["accent"]).pack(anchor="w", padx=10, pady=(10,0))
            row("Scale (x):", lambda r: tk.Scale(r, variable=self.ins_scale, from_=0.1, to=3.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
            row("Opacity:", lambda r: tk.Scale(r, variable=self.ins_opacity, from_=0.0, to=1.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
            row("Pos X:", lambda r: tk.Entry(r, textvariable=self.ins_x, bg="#333", fg="white", bd=0).pack(fill=tk.X, expand=True, ipady=3))
            row("Pos Y:", lambda r: tk.Entry(r, textvariable=self.ins_y, bg="#333", fg="white", bd=0).pack(fill=tk.X, expand=True, ipady=3))

            if item['type'] == 'video':
                max_dur = 10.0
                if item.get('path'):
                    try:
                        if item['path'] not in self._clip_cache: self._clip_cache[item['path']] = VideoFileClip(item['path'])
                        max_dur = self._clip_cache[item['path']].duration
                    except: pass

                self.ins_c_start = tk.DoubleVar(value=item.get('clip_start', 0.0))
                self.ins_c_end = tk.DoubleVar(value=item.get('clip_end', max_dur))
                
                tk.Label(f, text="Video Properties:", bg=C["panel"], fg=C["accent"]).pack(anchor="w", padx=10, pady=(10,0))
                row("Speed (x):", lambda r: tk.Scale(r, variable=self.ins_speed, from_=0.1, to=5.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
                row("Trim Start:", lambda r: tk.Scale(r, variable=self.ins_c_start, from_=0, to=max_dur, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
                row("Trim End:", lambda r: tk.Scale(r, variable=self.ins_c_end, from_=0, to=max_dur, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
                
                self.ins_muted = tk.BooleanVar(value=item.get('muted', False))
                self.ins_vol = tk.DoubleVar(value=item.get('volume', 1.0))
                tk.Checkbutton(f, text="Mute Original Audio", variable=self.ins_muted, bg=C["panel"], fg="white", selectcolor="#333").pack(anchor="w", padx=10, pady=5)
                row("Volume:", lambda r: tk.Scale(r, variable=self.ins_vol, from_=0.0, to=2.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
            else:
                row("Duration (s):", lambda r: tk.Entry(r, textvariable=self.ins_dur, bg="#333", fg="white", bd=0).pack(fill=tk.X, expand=True, ipady=3))

            if item['type'] == 'title':
                self.ins_mtxt = tk.StringVar(value=item.get('main_text', ''))
                self.ins_stxt = tk.StringVar(value=item.get('sub_text', ''))
                self.ins_theme = tk.StringVar(value=item.get('theme', ''))
                
                tk.Label(f, text="Title Card:", bg=C["panel"], fg=C["accent"]).pack(anchor="w", padx=10, pady=(10,0))
                row("Main Text:", lambda r: tk.Entry(r, textvariable=self.ins_mtxt, bg="#333", fg="white", bd=0).pack(fill=tk.X, expand=True, ipady=3))
                row("Sub Text:", lambda r: tk.Entry(r, textvariable=self.ins_stxt, bg="#333", fg="white", bd=0).pack(fill=tk.X, expand=True, ipady=3))
                row("Theme:", lambda r: ttk.Combobox(r, textvariable=self.ins_theme, values=["Cinematic – Light Speed Starburst", "Cinematic – Deep Space Stars", "Cinematic – Travelling Flare (Dynamic)"], width=22).pack(side=tk.LEFT))
            else:
                self.ins_txt = tk.StringVar(value=item.get('text', ''))
                self.ins_t_start = tk.DoubleVar(value=item.get('text_start', 0.0))
                self.ins_t_end = tk.DoubleVar(value=item.get('text_end', 3.0))
                self.ins_ltstyle = tk.StringVar(value=item.get('lt_style', 'Static Aurora Tile (Bracket)'))
                
                tk.Label(f, text="Text Overlay:", bg=C["panel"], fg=C["accent"]).pack(anchor="w", padx=10, pady=(10,0))
                row("Text:", lambda r: tk.Entry(r, textvariable=self.ins_txt, bg="#333", fg="white", bd=0).pack(fill=tk.X, expand=True, ipady=3))
                row("Start (s):", lambda r: tk.Scale(r, variable=self.ins_t_start, from_=0.0, to=60.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
                row("End (s):", lambda r: tk.Scale(r, variable=self.ins_t_end, from_=0.0, to=60.0, resolution=0.1, orient=tk.HORIZONTAL, bg=C["panel"], fg="white", bd=0, highlightthickness=0).pack(fill=tk.X, expand=True))
                row("Style:", lambda r: ttk.Combobox(r, textvariable=self.ins_ltstyle, values=["Static Aurora Tile (Bracket)", "Aurora Wave", "Purple Designer Box"], width=22).pack(side=tk.LEFT))

            row("Transition:", lambda r: ttk.Combobox(r, textvariable=self.ins_trans, values=["Crossfade", "Dip to Black", "Hard Cut", "Slide Left", "Slide Up", "Zoom In Fade", "Bright Flash", "Pull and Snap"], width=22).pack(side=tk.LEFT))

        tk.Button(f, text="💾 Save Inspector Data", bg=C["accent3"], fg=C["bg"], font=("Segoe UI", 10, "bold"), bd=0, command=self.save_inspector).pack(fill=tk.X, padx=10, pady=20, ipady=5)

    def save_inspector(self):
        if self.selected_audio_idx is not None:
            i = self.bgm_tracks[self.selected_audio_idx]
            i['volume'] = self.ins_vol.get()
            i['start_offset'] = self.ins_offset.get()
            i['clip_start'] = self.ins_a_start.get()
            i['clip_end'] = self.ins_a_end.get()
        elif self.selected_idx is not None:
            i = self.media_queue[self.selected_idx]
            i['scale'] = self.ins_scale.get()
            i['opacity'] = self.ins_opacity.get()
            i['x_offset'] = self.ins_x.get()
            i['y_offset'] = self.ins_y.get()
            i['trans'] = self.ins_trans.get()
            
            if i['type'] == 'title':
                i['main_text'] = self.ins_mtxt.get()
                i['sub_text'] = self.ins_stxt.get()
                i['theme'] = self.ins_theme.get()
            else:
                i['text'] = self.ins_txt.get()
                i['text_start'] = self.ins_t_start.get()
                i['text_end'] = self.ins_t_end.get()
                i['lt_style'] = self.ins_ltstyle.get()
                
                if i['type'] == 'video':
                    i['speed'] = self.ins_speed.get()
                    i['muted'] = self.ins_muted.get()
                    i['volume'] = self.ins_vol.get()
                    i['clip_start'] = self.ins_c_start.get()
                    i['clip_end'] = self.ins_c_end.get()
                else:
                    i['duration'] = self.ins_dur.get()
                    
            if f"t_{self.selected_idx}" in self.thumbs: 
                del self.thumbs[f"t_{self.selected_idx}"]
        
        self.timeline_dirty = True
        self.update_global_preview()
        self.refresh_timeline()

    # ==========================================
    # SAFE NumPy GEOMETRIC TRANSFORM ENGINE 
    # ==========================================
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
        w, h = base_clip.size if base_clip.size else (0,0)
        if rot in [90, -90, 270]: new_clip.size = (h, w)
        if getattr(base_clip, 'mask', None):
            new_mask = base_clip.mask.fl_image(process_f)
            if rot in [90, -90, 270]: new_mask.size = (h, w)
            new_clip = new_clip.set_mask(new_mask)
        return new_clip

    # ==========================================
    # HOLLYWOOD VFX BACKGROUND GENERATORS
    # ==========================================
    def create_warp_background(self, w, h, duration):
        y, x = np.mgrid[:h, :w]
        cx, cy = w / 2.0, h / 2.0
        dx = x - cx
        dy = y - cy
        r = np.sqrt(dx**2 + dy**2)
        theta = np.arctan2(dy, dx)
        theta_norm = (theta + np.pi) / (2 * np.pi)
        
        np.random.seed(42)
        angle_bins = 150
        speeds = np.random.uniform(2000, 5000, angle_bins)
        line_lengths = np.random.uniform(0.3, 0.8, angle_bins) 
        has_laser = np.random.rand(angle_bins) > 0.85
        faint_laser = np.random.rand(angle_bins) > 0.50
        
        palette_r = np.array([255, 255, 180, 100])
        palette_g = np.array([255, 50,  50,  100])
        palette_b = np.array([255, 255, 255, 255])
        color_idx = np.random.randint(0, 4, angle_bins)
        
        intensity_mult = np.where(has_laser, 1.0, np.where(faint_laser, 0.3, 0.0))
        raw_r = palette_r[color_idx] * intensity_mult
        raw_g = palette_g[color_idx] * intensity_mult
        raw_b = palette_b[color_idx] * intensity_mult
        
        r_map = np.convolve(np.tile(raw_r, 3), np.ones(3)/3.0, mode='same')[angle_bins:2*angle_bins]
        g_map = np.convolve(np.tile(raw_g, 3), np.ones(3)/3.0, mode='same')[angle_bins:2*angle_bins]
        b_map = np.convolve(np.tile(raw_b, 3), np.ones(3)/3.0, mode='same')[angle_bins:2*angle_bins]
        
        angle_idx = (theta_norm * (angle_bins - 1)).astype(int)
        base_r = np.full((h, w), 10, dtype=np.float32)
        base_g = np.full((h, w), 2,  dtype=np.float32)
        base_b = np.full((h, w), 30, dtype=np.float32)
        
        center_glow = np.exp(-0.5 * (r / 200.0)**2)
        base_r += 120 * center_glow
        base_g += 40 * center_glow
        base_b += 200 * center_glow

        def make_frame(t):
            my_speeds = speeds[angle_idx]
            my_lengths = line_lengths[angle_idx]
            phase = (r * 0.005 - my_speeds * t * 0.001) % 1.0
            intensity = np.where(phase < my_lengths, 1.0, 0.0) * np.clip((my_lengths - phase) / (my_lengths * 0.3 + 0.001), 0, 1) * np.clip(r / 100.0, 0, 1)
            
            frame = np.zeros((h, w, 3), dtype=np.float32)
            frame[..., 0] = base_r + r_map[angle_idx] * intensity
            frame[..., 1] = base_g + g_map[angle_idx] * intensity
            frame[..., 2] = base_b + b_map[angle_idx] * intensity
            
            for i in range(3):
                hoop_phase = (t / 1.5 + i * (1.0/3.0)) % 1.0
                hoop_r = (hoop_phase**2) * (max(w, h))
                hoop_alpha = (np.exp(-0.5 * (np.abs(r - hoop_r) / 2.0)**2) + np.exp(-0.5 * (np.abs(r - hoop_r) / 15.0)**2) * 0.5) * np.clip(hoop_r / 100.0, 0, 1) * np.clip(1.0 - hoop_phase, 0, 1)
                frame[..., 0] += 255 * hoop_alpha
                frame[..., 1] += 50 * hoop_alpha
                frame[..., 2] += 255 * hoop_alpha
            return np.clip(frame, 0, 255).astype(np.uint8)
        return VideoClip(make_frame, duration=duration)

    def create_starry_sky_background(self, w, h, duration):
        y_g, x_g = np.mgrid[0:h, 0:w]
        norm_y = (y_g / h).astype(np.float32)
        norm_x = (x_g / w).astype(np.float32)
        
        r = (18 * (1 - norm_y) + 15 * norm_y).astype(np.float32)
        g = (15 * (1 - norm_y) + 30 * norm_y).astype(np.float32)
        b = (45 * (1 - norm_y) + 70 * norm_y).astype(np.float32)
        
        dist_left = np.sqrt((norm_x - 0.2)**2 + (norm_y - 1.0)**2)
        glow_l = np.clip(1.0 - dist_left * 1.2, 0, 1) ** 2
        r += glow_l * 5
        g += glow_l * 40
        b += glow_l * 50
        
        dist_right = np.sqrt((norm_x - 0.8)**2 + (norm_y - 1.0)**2)
        glow_r = np.clip(1.0 - dist_right * 1.5, 0, 1) ** 2
        r += glow_r * 20
        g += glow_r * 10
        b += glow_r * 40
        
        bg_base = np.stack([r, g, b], axis=-1)
        np.random.seed(101)
        static_stars = np.random.rand(h, w) > 0.9985
        bg_base[static_stars] = [230, 240, 255] 
        
        N_twinkle = 400
        pad = 20
        t_x = np.random.randint(pad, w-pad, N_twinkle)
        t_y = np.random.randint(pad, h-pad, N_twinkle)
        t_phase = np.random.uniform(0, 2*np.pi, N_twinkle)
        t_speed = np.random.uniform(2.0, 6.0, N_twinkle)
        t_size = np.random.choice([1, 2, 3], N_twinkle, p=[0.5, 0.35, 0.15])
        
        sn_dur = 0.8
        sn_start = duration - sn_dur
        comet_dur = 2.0
        comet_start = max(0.0, sn_start - comet_dur)
        
        P0 = np.array([w * 1.1, -h * 0.1])
        P1 = np.array([w * 0.75, h / 2.0])
        P2 = np.array([w / 2.0, h / 2.0])

        def make_frame(t):
            frame = bg_base.copy()
            brights = np.clip((np.sin(t * t_speed + t_phase) * 0.5 + 0.5)**2.5 * 600, 0, 255).astype(np.int32)
            
            mask_1 = t_size >= 1
            if np.any(mask_1):
                ty1, tx1, b1 = t_y[mask_1], t_x[mask_1], brights[mask_1]
                for dy, dx in [(0,0), (0,1), (1,0), (1,1)]:
                    yy = np.clip(ty1+dy, 0, h-1)
                    xx = np.clip(tx1+dx, 0, w-1)
                    frame[yy, xx, 0] = np.clip(frame[yy, xx, 0] + b1, 0, 255)
                    frame[yy, xx, 1] = np.clip(frame[yy, xx, 1] + b1, 0, 255)
                    frame[yy, xx, 2] = np.clip(frame[yy, xx, 2] + b1, 0, 255)
                    
            mask_2 = t_size >= 2
            if np.any(mask_2):
                ty2, tx2, b2 = t_y[mask_2], t_x[mask_2], brights[mask_2] // 2
                for dy, dx in [(-1,0), (-1,1), (2,0), (2,1), (0,-1), (1,-1), (0,2), (1,2)]:
                    yy = np.clip(ty2+dy, 0, h-1)
                    xx = np.clip(tx2+dx, 0, w-1)
                    frame[yy, xx, 0] = np.clip(frame[yy, xx, 0] + b2, 0, 255)
                    frame[yy, xx, 1] = np.clip(frame[yy, xx, 1] + b2, 0, 255)
                    frame[yy, xx, 2] = np.clip(frame[yy, xx, 2] + b2, 0, 255)
                    
            mask_3 = t_size == 3
            if np.any(mask_3):
                ty3, tx3, b3 = t_y[mask_3], t_x[mask_3], brights[mask_3]
                for step in range(2, 14):
                    decay = max(0, 1.0 - (step / 14.0))
                    b_r = (b3 * decay * 0.7).astype(np.int32)
                    b_g = (b3 * decay * 0.9).astype(np.int32)
                    b_b = (b3 * decay * 1.0).astype(np.int32)
                    for dy, dx in [(-step, 0), (-step, 1), (step+1, 0), (step+1, 1), (0, -step), (1, -step), (0, step+1), (1, step+1)]:
                        yy = np.clip(ty3+dy, 0, h-1)
                        xx = np.clip(tx3+dx, 0, w-1)
                        frame[yy, xx, 0] = np.clip(frame[yy, xx, 0] + b_r, 0, 255)
                        frame[yy, xx, 1] = np.clip(frame[yy, xx, 1] + b_g, 0, 255)
                        frame[yy, xx, 2] = np.clip(frame[yy, xx, 2] + b_b, 0, 255)

            if comet_start <= t <= sn_start:
                p = (t - comet_start) / comet_dur
                cx = (1-p)**2 * P0[0] + 2*(1-p)*p * P1[0] + p**2 * P2[0]
                cy = (1-p)**2 * P0[1] + 2*(1-p)*p * P1[1] + p**2 * P2[1]
                vx = 2*(1-p)*(P1[0] - P0[0]) + 2*p*(P2[0] - P1[0])
                vy = 2*(1-p)*(P1[1] - P0[1]) + 2*p*(P2[1] - P1[1])
                v_mag = np.sqrt(vx**2 + vy**2)
                if v_mag == 0: v_mag = 1
                dir_x = -vx / v_mag
                dir_y = -vy / v_mag
                
                z_scale = 0.7 - 0.2 * np.sin(p * np.pi) + 1.2 * (p**3)
                dx = x_g - cx
                dy = y_g - cy
                dist_line = np.abs(dx * dir_y - dy * dir_x)
                proj = dx * dir_x + dy * dir_y
                
                trail_len = 200.0 * max(0.4, z_scale)
                trail_width = 1.2 * z_scale
                mask = (dist_line < trail_width) & (proj > 0) & (proj < trail_len)
                
                if np.any(mask):
                    dust_noise = np.random.uniform(0.3, 1.0, np.sum(mask))
                    fade = (1.0 - (proj[mask] / trail_len))**2 * dust_noise
                    frame[mask, 0] = np.clip(frame[mask, 0] + 150 * fade, 0, 255)
                    frame[mask, 1] = np.clip(frame[mask, 1] + 200 * fade, 0, 255)
                    frame[mask, 2] = np.clip(frame[mask, 2] + 255 * fade, 0, 255)
                    
                head_glow = np.exp(-0.5 * ((dx**2 + dy**2) / (1.5 * z_scale)**2))
                h_mask = head_glow > 0.05
                frame[h_mask, 0] = np.clip(frame[h_mask, 0] + 255 * head_glow[h_mask], 0, 255)
                frame[h_mask, 1] = np.clip(frame[h_mask, 1] + 255 * head_glow[h_mask], 0, 255)
                frame[h_mask, 2] = np.clip(frame[h_mask, 2] + 255 * head_glow[h_mask], 0, 255)
                
            return np.clip(frame, 0, 255).astype(np.uint8)
        return VideoClip(make_frame, duration=duration)

    def build_tile_lower_third(self, text, target_w, target_h, clip_duration, text_dur):
        fs = 55 if target_w < 1200 else 70
        try:    
            pil_font = ImageFont.truetype("arialbd.ttf", fs)
        except: 
            pil_font = ImageFont.load_default()
            
        txt_upper = text.upper()
        dummy = PIL.Image.new("RGBA", (1, 1))
        bbox = ImageDraw.Draw(dummy).textbbox((0, 0), txt_upper, font=pil_font)
        tw = bbox[2] - bbox[0] + 24
        th = bbox[3] - bbox[1] + 24
        
        txt_img = PIL.Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        draw = ImageDraw.Draw(txt_img)
        draw.text((12 + 4, 12 + 4), txt_upper, font=pil_font, fill=(0, 0, 0, 180))
        draw.text((12, 12), txt_upper, font=pil_font, fill=(255, 223, 115, 255))
        
        txt_rgba = np.array(txt_img)
        txt_rgb = txt_rgba[..., :3]
        txt_alpha_base = txt_rgba[..., 3].astype(np.float32) / 255.0
        
        txt_x = (target_w - tw) // 2
        txt_y = target_h - 210
        pad_x = int(fs * 2.5)
        pad_y = int(fs * 0.8)
        box_w = tw + pad_x * 2
        box_h = th + pad_y * 2
        box_x = txt_x - pad_x
        box_y = txt_y - pad_y
        
        y_g, x_g = np.mgrid[0:box_h, 0:box_w]
        r = box_h / 2.0
        cx_L = r
        cx_R = box_w - r
        cy = r
        
        dx = np.maximum(0.0, np.maximum(cx_L - x_g, x_g - cx_R))
        dy = np.abs(y_g - cy)
        d = np.sqrt(dx**2 + dy**2)
        
        alpha_pill = np.clip(r - d, 0, 1)
        bracket_dist = np.abs(d - (r + 4))
        alpha_bracket = np.clip(2.5 - bracket_dist, 0, 1) * ((x_g < cx_L - r*0.3) | (x_g > cx_R + r*0.3))

        def make_bg_frame(t):
            frame = np.zeros((box_h, box_w, 3), dtype=np.float32)
            frame[..., 0], frame[..., 1], frame[..., 2] = 55, 10, 20
            wave = 0.5 + 0.5 * np.sin((x_g / box_w) * 5 + t * 0.5)
            frame[..., 0] += wave * 25
            frame[..., 2] += wave * 15 
            frame[..., 0] = np.clip(frame[..., 0] + alpha_bracket * 255, 0, 255)
            frame[..., 1] = np.clip(frame[..., 1] + alpha_bracket * 255, 0, 255)
            frame[..., 2] = np.clip(frame[..., 2] + alpha_bracket * 255, 0, 255)
            return frame.astype(np.uint8)

        form_t = 0.8
        diss_t = 0.8
        start_t = 0.5
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

        def make_bg_mask(t):
            wp = wipe_progress(t)
            if wp <= 0: return np.zeros((box_h, box_w), dtype=np.float32)
            total_alpha = np.clip(alpha_pill + alpha_bracket, 0, 1)
            wipe_limit = int(wp * box_w)
            mask = np.zeros((box_h, box_w), dtype=np.float32)
            if wipe_limit > 0:
                mask[:, :wipe_limit] = total_alpha[:, :wipe_limit]
                for i in range(40):
                    col = wipe_limit - 40 + i
                    if 0 <= col < box_w: mask[:, col] = total_alpha[:, col] * (i / 40.0)
            return mask

        def make_text_mask_frame(t):
            wp = wipe_progress(t)
            full = np.zeros((target_h, target_w), dtype=np.float32)
            if wp <= 0: return full
            ga = txt_alpha_base.copy()
            if t < end_t:
                reveal_x = int(wp * tw)
                for i in range(min(40, tw)):
                    if 0 <= reveal_x + i < tw: 
                        ga[:, reveal_x + i] *= (1.0 - i / 40.0)
                ga[:, reveal_x:] = 0.0
            else:
                np.random.seed(int(t * 20))
                ga = ga * np.where(np.random.rand(th, tw) > np.clip(((t - end_t) / diss_t)*2.0 - np.linspace(0, 1, th).reshape(-1, 1)*0.8, 0, 1), 1.0, 0.0).astype(np.float32)
            y1_d, y2_d = max(0, txt_y), min(target_h, txt_y + th)
            x1_d, x2_d = max(0, txt_x), min(target_w, txt_x + tw)
            if y1_d < y2_d and x1_d < x2_d: 
                full[y1_d:y2_d, x1_d:x2_d] = ga[y1_d-txt_y:y1_d-txt_y+(y2_d-y1_d), x1_d-txt_x:x1_d-txt_x+(x2_d-x1_d)]
            return full

        tile_clip = (VideoClip(make_bg_frame, duration=clip_duration)
                     .set_mask(VideoClip(make_bg_mask, duration=clip_duration, ismask=True))
                     .set_position((box_x, box_y)))
                     
        text_clip_final = (VideoClip(lambda t: np.zeros((target_h, target_w, 3), dtype=np.uint8) if wipe_progress(t)<=0 else np.pad(txt_rgb, ((txt_y, target_h-txt_y-th),(txt_x, target_w-txt_x-tw),(0,0))), duration=clip_duration)
                           .set_mask(VideoClip(make_text_mask_frame, duration=clip_duration, ismask=True))
                           .set_position((0, 0)))

        return [tile_clip, text_clip_final]

    def build_magical_lower_third(self, text, target_w, target_h, clip_duration, text_dur):
        fs = 55 if target_w < 1200 else 70
        try: 
            pil_font = ImageFont.truetype("arialbd.ttf", fs)
        except: 
            pil_font = ImageFont.load_default()
            
        txt_upper = text.upper()
        dummy = PIL.Image.new("RGBA", (1, 1))
        bbox  = ImageDraw.Draw(dummy).textbbox((0, 0), txt_upper, font=pil_font)
        tw = bbox[2] - bbox[0] + 24
        th = bbox[3] - bbox[1] + 24
        
        txt_img = PIL.Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        draw = ImageDraw.Draw(txt_img)
        draw.text((12 + 4, 12 + 4), txt_upper, font=pil_font, fill=(0, 0, 0, 180))
        draw.text((12, 12), txt_upper, font=pil_font, fill=(255, 223, 115, 255))
        
        txt_alpha_base = np.array(txt_img)[..., 3].astype(np.float32) / 255.0
        txt_rgb = np.array(txt_img)[..., :3]
        
        txt_x = (target_w - tw) // 2
        txt_y = target_h - 210
        pad_x = int(fs * 2.8)
        pad_y = int(fs * 1.4)
        box_w = tw + pad_x * 2
        box_h = th + pad_y * 2
        box_x = txt_x - pad_x
        box_y = txt_y - pad_y

        form_t = 1.0
        diss_t = 1.0
        start_t = 0.5
        end_t = start_t + form_t + text_dur
        
        if end_t + diss_t > clip_duration:
            start_t = 0.2
            avail = clip_duration - start_t
            form_t = avail * 0.2
            diss_t = avail * 0.2
            text_dur = avail * 0.6
            end_t = start_t + form_t + text_dur

        def wipe_progress(t):
            if t < start_t: return 0.0
            elif t < start_t + form_t: return (t - start_t) / form_t
            elif t < end_t: return 1.0
            elif t < end_t + diss_t: return max(0.0, 1.0-(t-end_t)/diss_t)
            else: return 0.0

        y_g, x_g = np.mgrid[0:box_h, 0:box_w]
        norm_x = (x_g - box_w / 2.0) / (box_w / 2.0)
        norm_y = (y_g - box_h / 2.0) / (box_h / 2.0)
        col_wave = 0.18 * np.sin(norm_x * np.pi * 2.5)
        wave_mask = np.clip(np.exp(-0.5 * ((norm_x / 0.68)**2 + ((norm_y - col_wave) / 0.44)**2)) * 1.35, 0.0, 1.0).astype(np.float32)

        def make_aurora_frame(t):
            u = x_g / box_w
            v = y_g / box_h
            teal = 0.5 + 0.5 * np.sin(u * 4 - t * 1.2)
            w1 = 0.5 + 0.5 * np.sin(u * 10 + t * 3.0) * np.cos(v * 5  - t * 2.0)
            w2 = 0.5 + 0.5 * np.cos(u * 7 - t * 2.5) * np.sin(v * 8  + t * 1.5)
            w3 = 0.5 + 0.5 * np.sin((u + v) * 6 + t * 1.8)
            rr = np.clip(w1 * 120 + w3 * 60, 0, 255)
            gg = np.clip(w2 * 140 + w3 * 80 + teal * 80, 0, 255)
            bb = np.clip(w1 * 255 + w2 * 220 + w3 * 120 + teal * 40, 0, 255)
            return np.stack([rr, gg, bb], axis=-1).astype(np.uint8)

        def make_text_mask_frame(t):
            wp = wipe_progress(t)
            full = np.zeros((target_h, target_w), dtype=np.float32)
            if wp <= 0: return full
            ga = txt_alpha_base.copy()
            if t < end_t:
                reveal_x = int(wp * tw)
                for i in range(min(40, tw)):
                    if 0 <= reveal_x + i < tw: 
                        ga[:, reveal_x + i] *= (1.0 - i / 40.0)
                ga[:, reveal_x:] = 0.0
            else:
                np.random.seed(int(t * 20))
                ga = ga * np.where(np.random.rand(th, tw) > np.clip(((t - end_t) / diss_t)*2.0 - np.linspace(0, 1, th).reshape(-1, 1)*0.8, 0, 1), 1.0, 0.0).astype(np.float32)
            y1_d, y2_d = max(0, txt_y), min(target_h, txt_y + th)
            x1_d, x2_d = max(0, txt_x), min(target_w, txt_x + tw)
            if y1_d < y2_d and x1_d < x2_d: 
                full[y1_d:y2_d, x1_d:x2_d] = ga[y1_d-txt_y:y1_d-txt_y+(y2_d-y1_d), x1_d-txt_x:x1_d-txt_x+(x2_d-x1_d)]
            return full

        aurora_clip = (VideoClip(make_aurora_frame, duration=clip_duration)
                       .set_mask(VideoClip(lambda t: (wave_mask * wipe_progress(t)).astype(np.float32), duration=clip_duration, ismask=True))
                       .set_position((box_x, box_y)))
                       
        text_clip_final = (VideoClip(lambda t: np.zeros((target_h, target_w, 3), dtype=np.uint8) if wipe_progress(t)<=0 else np.pad(txt_rgb, ((txt_y, target_h-txt_y-th),(txt_x, target_w-txt_x-tw),(0,0))), duration=clip_duration)
                           .set_mask(VideoClip(make_text_mask_frame, duration=clip_duration, ismask=True))
                           .set_position((0, 0)))

        part_h = min(400, target_h)
        part_y_off = target_h - part_h
        np.random.seed(42)
        N = 180; M = 400; K = 200
        trail_spawn = start_t + np.linspace(0, form_t, N)
        trail_x0 = txt_x - 50 + np.linspace(0, 1, N) * (tw + 100)
        trail_y0 = (txt_y - part_y_off) - 70*np.sin(np.linspace(0,1,N)*np.pi) + th//2
        diss_spawn = end_t + np.random.uniform(0, diss_t*0.7, M)
        diss_x0 = txt_x + np.random.uniform(0, tw, M)
        diss_y0 = (txt_y - part_y_off) + np.random.uniform(0, th, M)
        amb_spawn = np.random.uniform(start_t, end_t, K)
        amb_x0 = txt_x + np.random.uniform(-20, tw+20, K)
        amb_y0 = (txt_y - part_y_off) + np.random.uniform(-10, th+10, K)

        def make_fx_frame(t):
            frame = np.zeros((part_h, target_w, 3), dtype=np.uint8)
            alpha = np.zeros((part_h, target_w), dtype=np.float32)
            for spawn, x0, y0, col, grav, life_dur in [(trail_spawn, trail_x0, trail_y0, (255,220,120), 250, 1.2), (amb_spawn, amb_x0, amb_y0, (255,240,180), 0, 2.0), (diss_spawn, diss_x0, diss_y0, (255,200,100), 350, 1.5)]:
                active = (t > spawn) & (t < spawn + life_dur)
                if not np.any(active): continue
                dt = t - spawn[active]
                cx_ = (x0[active]).astype(int)
                cy_ = (y0[active] + 15*dt + 0.5*grav*dt**2).astype(int)
                life = np.clip(1.0 - dt/life_dur, 0, 1)
                for x, y, l in zip(cx_, cy_, life):
                    if 0<=y<part_h and 0<=x<target_w: 
                        frame[y:y+2, x:x+2] = col
                        alpha[y:y+2, x:x+2] = np.maximum(alpha[y:y+2, x:x+2], l)
            return frame, alpha

        fx_clip = (VideoClip(lambda t: make_fx_frame(t)[0], duration=clip_duration)
                   .set_mask(VideoClip(lambda t: make_fx_frame(t)[1], duration=clip_duration, ismask=True))
                   .set_position((0, part_y_off)))

        return [aurora_clip, text_clip_final, fx_clip]

    def build_designer_lower_third(self, text, target_w, target_h, clip_duration, text_dur):
        fs = 55 if target_w < 1200 else 70
        try: 
            pil_font = ImageFont.truetype("arialbd.ttf", fs)
        except: 
            pil_font = ImageFont.load_default()
            
        txt_upper = text.upper()
        dummy = PIL.Image.new("RGBA", (1, 1))
        bbox  = ImageDraw.Draw(dummy).textbbox((0, 0), txt_upper, font=pil_font)
        tw = bbox[2] - bbox[0] + 24
        th = bbox[3] - bbox[1] + 24
        
        txt_img = PIL.Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        draw = ImageDraw.Draw(txt_img)
        draw.text((12 + 4, 12 + 4), txt_upper, font=pil_font, fill=(0, 0, 0, 180))
        draw.text((12, 12), txt_upper, font=pil_font, fill=(255, 220, 80, 255))
        
        txt_rgba = np.array(txt_img)
        txt_rgb = txt_rgba[..., :3]
        txt_alpha_base = txt_rgba[..., 3].astype(np.float32) / 255.0
        
        pad_x = int(fs * 1.8)
        pad_y = int(fs * 0.9)
        panel_w = tw + pad_x * 2
        panel_h = th + pad_y * 2
        panel_x = (target_w - panel_w) // 2
        panel_y = target_h - 220
        txt_x = panel_x + pad_x
        txt_y = panel_y + pad_y

        form_t = 0.5
        hold_t = text_dur
        diss_t = 0.4
        start_t = 0.4
        end_t = start_t + form_t + hold_t
        
        if end_t + diss_t > clip_duration:
            start_t = 0.2
            avail = clip_duration - start_t
            form_t = avail*0.15
            diss_t = avail*0.15
            hold_t = avail*0.70
            end_t = start_t + form_t + hold_t

        def panel_progress(t):
            if t < start_t: return 0.0
            elif t < start_t+form_t: return (t-start_t)/form_t
            elif t < end_t: return 1.0
            elif t < end_t+diss_t: return max(0.0, 1.0-(t-end_t)/diss_t)
            else: return 0.0

        y_p, x_p = np.mgrid[0:panel_h, 0:panel_w]
        nx = (x_p - panel_w/2.0) / (panel_w/2.0)
        ny = (y_p - panel_h/2.0) / (panel_h/2.0)
        panel_base_alpha = np.clip(np.exp(-0.5*((nx/0.80)**2 + (ny/0.72)**2)) * 0.82, 0, 1).astype(np.float32)
        
        border_glow = np.clip(1.0 - np.minimum(np.minimum(x_p, panel_w - 1 - x_p), np.minimum(y_p, panel_h - 1 - y_p)) / 12.0, 0, 1) ** 2
        corner_len = int(panel_w * 0.12)
        corner_th  = 3
        corner_mask = np.zeros((panel_h, panel_w), dtype=np.float32)
        for cx_, cy_ in [(0,0),(panel_w-corner_len,0),(0,panel_h-corner_th),(panel_w-corner_len,panel_h-corner_th), (0,0),(panel_w-corner_th,0),(0,panel_h-corner_len),(panel_w-corner_th,panel_h-corner_len)]:
            corner_mask[max(0,cy_):min(panel_h,cy_+max(corner_th, corner_len)), max(0,cx_):min(panel_w,cx_+max(corner_th, corner_len))] = 1.0 

        def make_panel_frame(t):
            prog = panel_progress(t)
            if prog <= 0: return np.zeros((target_h, target_w, 3), dtype=np.uint8)

            slide_offset = int((1.0 - prog) * panel_h * 1.5)
            py = panel_y + slide_offset
            frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)

            y1, y2 = max(0, py), min(target_h, py + panel_h)
            x1, x2 = max(0, panel_x), min(target_w, panel_x + panel_w)
            if y1 >= y2 or x1 >= x2: return frame
            
            py_s, py_e = y1 - py, (y1 - py) + (y2 - y1)
            px_s, px_e = x1 - panel_x, (x1 - panel_x) + (x2 - x1)

            frame[y1:y2, x1:x2, 0] = 45
            frame[y1:y2, x1:x2, 1] = 10
            frame[y1:y2, x1:x2, 2] = 75

            scan_y = int(((t * 0.7) % 1.0) * panel_h)
            s_scan = np.exp(-0.5*((np.arange(panel_h) - scan_y)/8.0)**2)[py_s:py_e, np.newaxis]
            s_border = border_glow[py_s:py_e, px_s:px_e]

            frame[y1:y2, x1:x2, 0] = np.clip(frame[y1:y2, x1:x2, 0] + (s_scan * 80).astype(np.uint8) + (s_border * 180).astype(np.uint8), 0, 255)
            frame[y1:y2, x1:x2, 1] = np.clip(frame[y1:y2, x1:x2, 1] + (s_scan * 40).astype(np.uint8) + (s_border * 60).astype(np.uint8), 0, 255)
            frame[y1:y2, x1:x2, 2] = np.clip(frame[y1:y2, x1:x2, 2] + (s_scan * 120).astype(np.uint8) + (s_border * 255).astype(np.uint8), 0, 255)
            return frame

        def make_panel_mask(t):
            prog = panel_progress(t)
            full = np.zeros((target_h, target_w), dtype=np.float32)
            if prog <= 0: return full
            
            slide_offset = int((1.0 - prog) * panel_h * 1.5)
            py = panel_y + slide_offset
            y1, y2 = max(0, py), min(target_h, py + panel_h)
            x1, x2 = max(0, panel_x), min(target_w, panel_x + panel_w)
            
            if y1 >= y2 or x1 >= x2: return full
            
            py_s, py_e = y1 - py, (y1 - py) + (y2 - y1)
            px_s, px_e = x1 - panel_x, (x1 - panel_x) + (x2 - x1)
            
            full[y1:y2, x1:x2] = panel_base_alpha[py_s:py_e, px_s:px_e] * prog
            full[y1:y2, x1:x2] = np.clip(full[y1:y2, x1:x2] + border_glow[py_s:py_e, px_s:px_e] * 0.9 * prog, 0, 1)
            return full

        def make_text_mask(t):
            prog = panel_progress(t)
            full = np.zeros((target_h, target_w), dtype=np.float32)
            if prog <= 0: return full
            
            slide_offset = int((1.0 - prog) * panel_h * 1.5)
            ty = txt_y + slide_offset
            ga = txt_alpha_base.copy()
            
            if t >= end_t:
                np.random.seed(int(t * 20))
                ga = ga * np.where(np.random.rand(th, tw) > np.clip(((t - end_t) / diss_t)*2.0 - np.linspace(0, 1, th).reshape(-1, 1)*0.8, 0, 1), 1.0, 0.0).astype(np.float32)
            
            y1_d, y2_d = max(0, ty), min(target_h, ty + th)
            x1_d, x2_d = max(0, txt_x), min(target_w, txt_x + tw)
            if y1_d < y2_d and x1_d < x2_d: 
                full[y1_d:y2_d, x1_d:x2_d] = ga[y1_d-ty:y1_d-ty+(y2_d-y1_d), x1_d-txt_x:x1_d-txt_x+(x2_d-x1_d)] * prog
            return full

        panel_clip = (VideoClip(make_panel_frame, duration=clip_duration)
                      .set_mask(VideoClip(make_panel_mask, duration=clip_duration, ismask=True))
                      .set_position((0, 0)))

        text_clip_final = (VideoClip(lambda t: np.zeros((target_h, target_w, 3), dtype=np.uint8) if panel_progress(t)<=0 else np.pad(txt_rgb, ((txt_y + int((1.0 - panel_progress(t)) * panel_h * 1.5), target_h-(txt_y + int((1.0 - panel_progress(t)) * panel_h * 1.5))-th),(txt_x, target_w-txt_x-tw),(0,0))), duration=clip_duration)
                           .set_mask(VideoClip(make_text_mask, duration=clip_duration, ismask=True))
                           .set_position((0, 0)))

        return [panel_clip, text_clip_final]

    def build_finch_title_card(self, target_w, target_h, item):
        duration = float(item.get("duration", 5.0))
        main_str = item.get("main_text", "TITLE").upper()
        sub_str = item.get("sub_text", "").upper()
        spaced_sub = "   ".join(sub_str) if sub_str else ""
        
        theme = item.get("theme", "")
        is_lightspeed = "Light Speed" in theme
        is_deepspace = "Deep Space" in theme
        is_travelling = "Travelling Flare" in theme

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

        # 1. BUILD BACKGROUND & EFFECTS
        if is_lightspeed:
            bg_clip = self.create_warp_background(target_w, target_h, duration)
            layers = [bg_clip]
        elif is_travelling:
            y_bg, x_bg = np.mgrid[0:target_h, 0:target_w]
            dist_center = np.sqrt((x_bg - target_w/2)**2 + (y_bg - target_h/2)**2)
            fog_glow = np.exp(-0.5 * (dist_center / 800.0)**2) * 0.4
            
            bg_r = np.clip(18 + 15 * fog_glow, 0, 255)
            bg_g = np.clip(25 + 20 * fog_glow, 0, 255)
            bg_b = np.clip(28 + 15 * fog_glow, 0, 255)
            bg_frame = np.stack([bg_r, bg_g, bg_b], axis=-1).astype(np.uint8)
            bg_clip = ImageClip(bg_frame).set_duration(duration)
            layers = [bg_clip]

            y_g, x_g = np.mgrid[0:target_h, 0:target_w]
            
            np.random.seed(42)
            num_dust = 120
            d_x = np.random.uniform(target_w*0.1, target_w*0.9, num_dust)
            d_y = np.random.uniform(target_h*0.2, target_h*0.8, num_dust)
            d_vx = np.random.uniform(-5, 5, num_dust)
            d_vy = np.random.uniform(-10, -2, num_dust)
            
            dist_c = np.sqrt((x_g - target_w/2)**2 + (y_g - baseline_y)**2)
            
            text_w_half = main_clip.w / 2.0 + 40
            text_h_half = main_clip.h / 2.0 + 50
            text_cy = baseline_y - main_clip.h / 2.0 - 20
            
            dx_text = np.maximum(0.0, np.abs(x_g - target_w/2) - text_w_half)
            dy_text = np.maximum(0.0, np.abs(y_g - text_cy) - text_h_half)
            dist_from_text = np.sqrt(dx_text**2 + dy_text**2)
            text_avoid_mask = np.clip(dist_from_text / 10.0, 0, 1)

            def make_travelling_flare(t):
                p = t / duration
                cx = (target_w/2 - main_clip.w/2 - 150) + p * (main_clip.w + 300)
                cy = baseline_y - 5
                
                intensity = 0.02 + 0.98 * np.exp(-0.5 * ((p - 0.5) / 0.12)**2)
                
                frame = np.zeros((target_h, target_w, 3), dtype=np.float32)
                alpha = np.zeros((target_h, target_w), dtype=np.float32)
                
                fog = np.exp(-0.5 * ((x_g - target_w/2)**2 / (600.0)**2 + (y_g - cy)**2 / (150.0)**2)) * intensity * 0.15
                
                sine_val = np.sin(-dist_c / 35.0 + t * 5.0)
                ripple_lines = np.clip((sine_val - 0.995) * 200.0, 0, 1) 
                
                np.random.seed(int(t * 20))
                glitter_noise = np.random.rand(target_h, target_w)
                glitter_mult = np.where(glitter_noise > 0.85, 2.5, 0.2) 
                
                ripples = ripple_lines * text_avoid_mask * intensity * glitter_mult * 0.8
                
                fog_glow = np.clip(fog, 0, 1)
                frame[..., 0] += fog_glow * 255
                frame[..., 1] += fog_glow * 220
                frame[..., 2] += fog_glow * 130
                alpha += fog_glow
                
                frame[..., 0] = np.clip(frame[..., 0] + ripples * 229, 0, 255)
                frame[..., 1] = np.clip(frame[..., 1] + ripples * 213, 0, 255)
                frame[..., 2] = np.clip(frame[..., 2] + ripples * 160, 0, 255)
                alpha = np.clip(alpha + ripples, 0, 1)
                
                streak_h_w = 800.0 * intensity + 20.0
                streak_h_h = 2.5 + 1.0 * intensity
                streak_v_w = 2.5 + 1.0 * intensity
                streak_v_h = 350.0 * intensity + 10.0
                
                y_min, y_max = max(0, int(cy - max(streak_h_h, streak_v_h)*3)), min(target_h, int(cy + max(streak_h_h, streak_v_h)*3))
                x_min, x_max = max(0, int(cx - max(streak_h_w, streak_v_w)*3)), min(target_w, int(cx + max(streak_h_w, streak_v_w)*3))
                
                if y_min < y_max and x_min < x_max:
                    xx = x_g[y_min:y_max, x_min:x_max]
                    yy = y_g[y_min:y_max, x_min:x_max]
                    dx = xx - cx
                    dy = yy - cy
                    
                    s1 = np.exp(-0.5 * (dx / streak_h_w)**2 - 0.5 * (dy / streak_h_h)**2) * intensity
                    s2 = np.exp(-0.5 * (dx / streak_v_w)**2 - 0.5 * (dy / streak_v_h)**2) * intensity
                    core = np.exp(-0.5 * (np.sqrt(dx**2 + dy**2) / (25.0 * intensity + 3.0))**2) * intensity * 1.5
                    
                    glow = np.clip(s1 + s2 + core, 0, 1)
                    frame[y_min:y_max, x_min:x_max, 0] = np.clip(frame[y_min:y_max, x_min:x_max, 0] + glow * 255, 0, 255)
                    frame[y_min:y_max, x_min:x_max, 1] = np.clip(frame[y_min:y_max, x_min:x_max, 1] + glow * 240, 0, 255)
                    frame[y_min:y_max, x_min:x_max, 2] = np.clip(frame[y_min:y_max, x_min:x_max, 2] + glow * 190, 0, 255)
                    alpha[y_min:y_max, x_min:x_max] = np.clip(alpha[y_min:y_max, x_min:x_max] + glow, 0, 1)
                
                for i in range(num_dust):
                    curr_x = int(d_x[i] + d_vx[i] * t)
                    curr_y = int(d_y[i] + d_vy[i] * t)
                    
                    if 0 <= curr_x < target_w and 0 <= curr_y < target_h:
                        dist_to_flare = np.sqrt((curr_x - cx)**2 + (curr_y - cy)**2)
                        illum = max(
                            np.exp(-0.5 * (dist_to_flare / (300 * intensity + 50))**2) * intensity * 0.8,
                            np.exp(-0.5 * ((curr_x - target_w/2)**2 / 600**2 + (curr_y - cy)**2 / 150**2)) * intensity * 0.3
                        )
                        
                        if illum > 0.02:
                            s = 0 
                            y1, y2 = max(0, curr_y-s), min(target_h, curr_y+s+1)
                            x1, x2 = max(0, curr_x-s), min(target_w, curr_x+s+1)
                            
                            dust_glow = illum * 255
                            frame[y1:y2, x1:x2, 0] = np.clip(frame[y1:y2, x1:x2, 0] + dust_glow, 0, 255)
                            frame[y1:y2, x1:x2, 1] = np.clip(frame[y1:y2, x1:x2, 1] + dust_glow * 0.85, 0, 255)
                            frame[y1:y2, x1:x2, 2] = np.clip(frame[y1:y2, x1:x2, 2] + dust_glow * 0.4, 0, 255)
                            alpha[y1:y2, x1:x2] = np.clip(alpha[y1:y2, x1:x2] + illum, 0, 1)

                return np.clip(frame, 0, 255).astype(np.uint8), np.clip(alpha, 0, 1)

            flare_rgb = VideoClip(lambda t: make_travelling_flare(t)[0], duration=duration)
            flare_mask = VideoClip(lambda t: make_travelling_flare(t)[1], duration=duration, ismask=True)
            layers.append(flare_rgb.set_mask(flare_mask))

        else:
            bg_clip = self.create_starry_sky_background(target_w, target_h, duration)
            layers = [bg_clip]

        if spaced_sub:
            if is_lightspeed:
                try: sub_txt = TextClip(spaced_sub, fontsize=40, color="#b050ff", font="Arial-Bold", stroke_color="white", stroke_width=3, bg_color="transparent")
                except: sub_txt = TextClip(spaced_sub, fontsize=40, color="white", font="Arial-Bold", bg_color="transparent")
                sub_txt = sub_txt.set_position(("center", main_y - 70)).set_duration(duration)
            elif is_travelling:
                try: sub_txt = TextClip(spaced_sub, fontsize=35, color="#E5D5A0", font="Arial-Bold", bg_color="transparent")
                except: sub_txt = TextClip(spaced_sub, fontsize=35, color="white", bg_color="transparent")
                sub_txt = sub_txt.set_position(("center", main_y - 60)).set_duration(duration)
            else:
                try: sub_txt = TextClip(spaced_sub, fontsize=35, color="white", font="Arial-Bold", bg_color="transparent")
                except: sub_txt = TextClip(spaced_sub, fontsize=35, color="white", bg_color="transparent")
                sub_txt = sub_txt.set_position(("center", main_y - 80)).set_duration(duration)
            layers.append(sub_txt)

        layers.append(main_clip)
        if shine_clip is not None:
            layers.append(shine_clip)

        if not is_deepspace and not is_lightspeed and not is_travelling:
            yv, xv = np.mgrid[:target_h, :target_w]
            vd = np.sqrt(((xv - target_w/2)/(target_w*0.55))**2 + ((yv - target_h/2)/(target_h*0.55))**2)
            vig_a = np.clip(vd**1.6*0.72, 0, 1).astype(np.float32)
            vig_clip = ImageClip(np.zeros((target_h, target_w, 3), dtype=np.uint8)).set_mask(ImageClip(vig_a, ismask=True)).set_duration(duration)
            layers.append(vig_clip)

            bar_h = max(int(target_h*(1.0 - target_w/(target_w*2.39))/2), int(target_h*0.06))
            black_bar = ColorClip(size=(target_w, bar_h), color=(0,0,0)).set_duration(duration)
            layers += [black_bar.set_position((0, 0)), black_bar.set_position((0, target_h - bar_h))]

        if is_lightspeed:
            trans_dur = 1.2
            trans_start = duration - trans_dur
            impact_time = trans_start + 0.4

            def make_fusion_frame(t):
                frame = np.zeros((target_h, target_w, 3), dtype=np.float32)
                if t < trans_start: return frame.astype(np.uint8)
                    
                y_gf, x_gf = np.mgrid[:target_h, :target_w]
                cy4, cx4 = target_h / 2.0, target_w / 2.0
                
                if t < impact_time:
                    p_in = (t - trans_start) / (impact_time - trans_start)
                    tip_l = cx4 * p_in
                    tip_r = target_w - (cx4 * p_in)
                    beam_th = 6.0
                    
                    mask_l = (x_gf < tip_l) & (np.abs(y_gf - cy4) < beam_th)
                    glow_l = np.exp(-0.5 * (np.abs(y_gf - cy4) / (beam_th*2))**2) * (x_gf < tip_l)
                    
                    frame[..., 1] += glow_l * 255 
                    frame[..., 2] += glow_l * 255 
                    frame[mask_l] = [255, 255, 255]
                    
                    mask_r = (x_gf > tip_r) & (np.abs(y_gf - cy4) < beam_th)
                    glow_r = np.exp(-0.5 * (np.abs(y_gf - cy4) / (beam_th*2))**2) * (x_gf > tip_r)
                    
                    frame[..., 0] += glow_r * 255 
                    frame[..., 2] += glow_r * 150 
                    frame[mask_r] = [255, 255, 255]
                    
                else:
                    p_ex = (t - impact_time) / (duration - impact_time) 
                    beam_th = 6.0 + p_ex * 30.0
                    
                    glow_l2 = np.exp(-0.5 * (np.abs(y_gf - cy4) / beam_th)**2) * (x_gf <= cx4)
                    glow_r2 = np.exp(-0.5 * (np.abs(y_gf - cy4) / beam_th)**2) * (x_gf > cx4)
                    
                    frame[..., 0] += glow_r2 * 255
                    frame[..., 1] += glow_l2 * 255
                    frame[..., 2] += glow_l2 * 255 + glow_r2 * 150
                    
                    core_beam = np.abs(y_gf - cy4) < (3.0 + p_ex * 15)
                    frame[core_beam] = [255, 255, 255]
                    
                    dist4 = np.sqrt((x_gf - cx4)**2 + (y_gf - cy4)**2)
                    radius = 20 + (target_w * 2.0) * (p_ex**2.5)
                    intensity4 = 1.0 + p_ex * 8.0
                    core4 = np.clip(1.0 - (dist4 / radius), 0, 1)**2 * intensity4
                    
                    spike_len = 150 + target_w * p_ex**2
                    spike_th = 3.0 + p_ex * 15.0
                    spikes = np.exp(-0.5 * (np.abs(x_gf - cx4) / spike_len)**2 - 0.5 * (np.abs(y_gf - cy4) / spike_th)**2)
                    spikes += np.exp(-0.5 * (np.abs(y_gf - cy4) / spike_len)**2 - 0.5 * (np.abs(x_gf - cx4) / spike_th)**2)
                    
                    dx4 = x_gf - cx4
                    dy4 = y_gf - cy4
                    diag1 = np.abs(dx4 - dy4) / 1.414
                    diag2 = np.abs(dx4 + dy4) / 1.414
                    diag_len = 100 + target_w * 0.7 * p_ex**2
                    diag_th = 2.0 + p_ex * 8.0
                    
                    spikes += 0.8 * np.exp(-0.5 * (diag1 / diag_th)**2 - 0.5 * (np.abs(dx4 + dy4) / 1.414 / diag_len)**2)
                    spikes += 0.8 * np.exp(-0.5 * (diag2 / diag_th)**2 - 0.5 * (np.abs(dx4 - dy4) / 1.414 / diag_len)**2)
                    
                    burst = np.clip(core4 + spikes * intensity4, 0, 1)
                    side_blend = np.clip((x_gf - (cx4 - 200)) / 400.0, 0, 1) 
                    
                    frame[..., 0] += burst * (100 * (1 - side_blend) + 255 * side_blend)
                    frame[..., 1] += burst * (255 * (1 - side_blend) + 50 * side_blend)
                    frame[..., 2] += burst * (255 * (1 - side_blend) + 150 * side_blend)
                    
                    white_core = np.clip(1.0 - (dist4 / (radius*0.4)), 0, 1)**1.5 * intensity4
                    frame[..., 0] += white_core * 255
                    frame[..., 1] += white_core * 255
                    frame[..., 2] += white_core * 255
                
                return np.clip(frame, 0, 255).astype(np.uint8)

            def make_fusion_mask(t):
                if t < trans_start: return np.zeros((target_h, target_w), dtype=np.float32)
                y_gm, x_gm = np.mgrid[:target_h, :target_w]
                cy5, cx5 = target_h / 2.0, target_w / 2.0

                if t < impact_time:
                    p_in = (t - trans_start) / (impact_time - trans_start)
                    tip_l = cx5 * p_in
                    tip_r = target_w - (cx5 * p_in)
                    beam_th = 6.0
                    ml = np.exp(-0.5 * (np.abs(y_gm - cy5) / (beam_th*2))**2) * (x_gm < tip_l)
                    mr = np.exp(-0.5 * (np.abs(y_gm - cy5) / (beam_th*2))**2) * (x_gm > tip_r)
                    return np.clip(ml + mr, 0, 1).astype(np.float32)
                else:
                    p_ex = (t - impact_time) / (duration - impact_time)
                    dist5 = np.sqrt((x_gm - cx5)**2 + (y_gm - cy5)**2)
                    radius = 20 + (target_w * 2.0) * (p_ex**2.5)
                    intensity5 = 1.0 + p_ex * 8.0
                    glow5 = np.clip(1.0 - (dist5 / radius), 0, 1)**1.5 * intensity5
                    
                    beam_th = 6.0 + p_ex * 30.0
                    beams = np.exp(-0.5 * (np.abs(y_gm - cy5) / beam_th)**2)
                    return np.clip(glow5 + beams, 0, 1).astype(np.float32)

            fusion_clip = VideoClip(make_fusion_frame, duration=duration).set_mask(VideoClip(make_fusion_mask, duration=duration, ismask=True))
            layers.append(fusion_clip)

        elif is_deepspace:
            sn_dur = 0.8 
            sn_start = duration - sn_dur

            def make_sn_frame(t): return np.full((target_h, target_w, 3), 255, dtype=np.uint8)
            Y_sn, X_sn = np.mgrid[0:target_h, 0:target_w]
            sn_x = target_w / 2.0
            sn_y = target_h / 2.0
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

        if is_deepspace or is_lightspeed or is_travelling:
            fps_audio = 44100
            total_samples = int(duration * fps_audio)
            t_audio = np.linspace(0, duration, total_samples, endpoint=False)
            audio_mono = np.zeros(total_samples, dtype=np.float32)
            
            if is_deepspace:
                sn_dur = 0.8; sn_start = duration - sn_dur; comet_dur = 2.0; comet_start = max(0.0, sn_start - comet_dur)
                mask_comet = ((t_audio - comet_start) / comet_dur >= 0) & ((t_audio - comet_start) / comet_dur <= 1)
                if np.any(mask_comet):
                    p_comet = (t_audio[mask_comet] - comet_start) / comet_dur
                    env_comet = np.sin(p_comet * np.pi)**2
                    noise = np.random.uniform(-0.5, 0.5, np.sum(mask_comet))
                    freq = 800 - 500*np.sin(p_comet*np.pi) + 900*(p_comet**3)
                    audio_mono[mask_comet] += (noise * 0.6 + np.sin(2 * np.pi * freq * t_audio[mask_comet]) * 0.4) * env_comet * 0.8

                boom_start = sn_start; boom_dur = sn_dur
                mask_boom = ((t_audio - boom_start) / boom_dur >= 0) & ((t_audio - boom_start) / boom_dur <= 1)
                if np.any(mask_boom):
                    p_boom = (t_audio[mask_boom] - boom_start) / boom_dur
                    env_sn = np.exp(-4 * p_boom) 
                    noise = np.random.uniform(-1.0, 1.0, np.sum(mask_boom))
                    freq = 150 * np.exp(-4 * p_boom) + 40
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
                    
            audio_mono = np.clip(audio_mono, -1.0, 1.0)
            audio_stereo = np.column_stack((audio_mono, audio_mono))
            sf_clip = AudioArrayClip(audio_stereo, fps=fps_audio)
            card = card.set_audio(sf_clip)

        return card.fadein(0.8)

    # ══════════════════════════════════════════════════════════
    #  EXPORT / MERGE ENGINE
    # ══════════════════════════════════════════════════════════
    def start_merge_thread(self):
        save_path = filedialog.asksaveasfilename(
            defaultextension=".mp4", initialfile="final_output.mp4",
            filetypes=[("MP4 Video", "*.mp4")])
        if not save_path: 
            return
        
        for item in self.media_queue:
            if item['type'] == 'placeholder' and not item.get('path'): 
                return messagebox.showerror("Error", "You have unfilled Placeholders! Please fill or delete them before exporting.")

        self.status_label.config(text="Rendering VFX and Media... Please wait.", fg="green")
        threading.Thread(target=self.process_merge, args=(save_path,), daemon=True).start()

    def process_merge(self, save_path):
        is_mobile = (self.format_var.get() == "mobile")
        target_w = 1080 if is_mobile else 1920
        target_h = 1920 if is_mobile else 1080
        smart_fill = self.smart_fill_var.get()
        auto_rotate = self.auto_rotate_var.get()

        final_clips = []
        
        try:
            for i, item in enumerate(self.media_queue):
                scale_val = item.get('scale', 1.0)
                opac_val = item.get('opacity', 1.0)
                x_off = item.get('x_offset', 0)
                y_off = item.get('y_offset', 0)
                t_start = item.get('tl_start', 0.0)

                if item['type'] == 'title': 
                    clip = self.build_finch_title_card(target_w, target_h, item)
                    clip_dur = clip.duration
                else:
                    if item['type'] == 'image': 
                        clip_dur = item.get('duration', 5.0)
                        clip = ImageClip(item['path']).set_duration(clip_dur)
                    else:
                        raw = VideoFileClip(item['path'])
                        s = item.get('clip_start', 0.0)
                        e = item.get('clip_end', 0.0)
                        
                        if e > s and e <= raw.duration: 
                            raw = raw.subclip(s, e)
                        elif s > 0: 
                            raw = raw.subclip(s)
                        
                        clip_dur = self._item_duration(item)
                        speed = item.get('speed', 1.0)
                        
                        if speed != 1.0: 
                            raw = raw.fx(vfx.speedx, speed)
                            
                        if item.get('muted', False): 
                            raw = raw.without_audio()
                        elif item.get('volume', 1.0) != 1.0: 
                            raw = raw.volx(item.get('volume', 1.0))
                            
                        clip = raw
                        
                clip = clip.set_duration(clip_dur)

                rot = item.get('rotation', 0)
                flip_h = item.get('flip_h', False)
                flip_v = item.get('flip_v', False)
                clip = self.safe_transform(clip, rot, flip_h, flip_v)
                clip = clip.set_duration(clip_dur)

                def get_pos(t, w, h, x_o=x_off, y_o=y_off): 
                    return (target_w/2 - w/2 + x_o, target_h/2 - h/2 + y_o)

                if item['type'] != 'title':
                    if auto_rotate:
                        if target_w > target_h and clip.w < clip.h: 
                            clip = self.safe_transform(clip, 90, False, False)
                        elif target_w < target_h and clip.w > clip.h: 
                            clip = self.safe_transform(clip, -90, False, False)
                            
                    if smart_fill:
                        clip = clip.fx(vfx.resize, max(target_w / clip.w, target_h / clip.h) * scale_val)
                        if scale_val == 1.0: 
                            clip = clip.fx(vfx.crop, x_center=clip.w/2, y_center=clip.h/2, width=target_w, height=target_h)
                    else: 
                        clip = clip.fx(vfx.resize, min(target_w / clip.w, target_h / clip.h) * scale_val)

                    if opac_val < 1.0: 
                        clip = clip.set_opacity(opac_val)
                        
                    vlayers = [ColorClip(size=(target_w, target_h), color=(0, 0, 0)).set_duration(clip_dur), 
                               clip.set_position(lambda t, c=clip: get_pos(t, c.w, c.h))]

                    if item.get('text'):
                        lt_layers = []
                        if item.get('lt_style', '') == 'Purple Designer Box': 
                            lt_layers = self.build_designer_lower_third(item['text'], target_w, target_h, clip_dur, item['text_end'] - item['text_start'])
                        elif item.get('lt_style', '') == 'Static Aurora Tile (Bracket)': 
                            lt_layers = self.build_tile_lower_third(item['text'], target_w, target_h, clip_dur, item['text_end'] - item['text_start'])
                        else: 
                            lt_layers = self.build_magical_lower_third(item['text'], target_w, target_h, clip_dur, item['text_end'] - item['text_start'])
                        for l in lt_layers: 
                            vlayers.append(l.set_start(item.get('text_start', 0.0)))
                            
                    clip = CompositeVideoClip(vlayers).set_duration(clip_dur)
                else:
                    if rot != 0 or flip_h or flip_v or scale_val != 1.0 or opac_val < 1.0:
                        if smart_fill:
                            clip = clip.fx(vfx.resize, max(target_w / clip.w, target_h / clip.h) * scale_val)
                            if scale_val == 1.0: 
                                clip = clip.fx(vfx.crop, x_center=clip.w/2, y_center=clip.h/2, width=target_w, height=target_h)
                        else: 
                            clip = clip.fx(vfx.resize, min(target_w / clip.w, target_h / clip.h) * scale_val)
                            
                        if opac_val < 1.0: 
                            clip = clip.set_opacity(opac_val)
                            
                        clip = CompositeVideoClip([ColorClip(size=(target_w, target_h), color=(0, 0, 0)).set_duration(clip_dur), 
                                                   clip.set_position(lambda t, c=clip: get_pos(t, c.w, c.h))]).set_duration(clip_dur)

                clip = clip.set_start(t_start)
                final_clips.append(clip)

            final_video = CompositeVideoClip(final_clips, size=(target_w, target_h))
            
            # COMPILE AUDIO TRACKS
            audio_layers = []
            if final_video.audio:
                audio_layers.append(final_video.audio)
                
            for aud in self.bgm_tracks:
                a_clip = AudioFileClip(aud['path'])
                s = aud.get('clip_start', 0.0)
                e = aud.get('clip_end', 0.0)
                
                if e > s and e <= a_clip.duration: 
                    a_clip = a_clip.subclip(s, e)
                elif s > 0: 
                    a_clip = a_clip.subclip(s)
                
                if aud.get('volume', 1.0) != 1.0: 
                    a_clip = a_clip.volumex(aud.get('volume', 1.0))
                
                a_clip = a_clip.set_start(aud.get('start_offset', 0.0))
                audio_layers.append(a_clip)
                
            if audio_layers: 
                mixed_audio = CompositeAudioClip(audio_layers)
                mixed_audio = mixed_audio.set_duration(final_video.duration)
                final_video = final_video.set_audio(mixed_audio)

            final_video.write_videofile(save_path, codec="libx264", audio_codec="aac", fps=30, preset="ultrafast")
            self.root.after(0, self.on_merge_success, save_path)

        except Exception as e: 
            self.root.after(0, self.on_merge_error, str(e))
        finally:
            if 'final_video' in locals(): 
                try: 
                    final_video.close()
                except: 
                    pass

    def on_merge_success(self, save_path):
        self.status_label.config(text="Export complete ✓", fg="green")
        messagebox.showinfo("Export Success", f"Saved to:\n{save_path}")

    def on_merge_error(self, err):
        self.status_label.config(text="Export failed ✖", fg="red")
        messagebox.showerror("Error", str(err))

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoMergerStudio(root)
    root.mainloop()




/////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////////





import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import threading
import os
import warnings
import numpy as np
import math

# --- SILENCE ANNOYING PILLOW WARNINGS ---
warnings.filterwarnings("ignore", category=DeprecationWarning)

# --- PIL ANTIALIAS FIX FOR PILLOW >= 10.0.0 ---
import PIL.Image
from PIL import ImageTk, ImageDraw, ImageFont
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

# --- YOUR EXACT IMAGEMAGICK PATH ---
os.environ["IMAGEMAGICK_BINARY"] = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"

from moviepy.editor import (
    VideoFileClip, ImageClip, ColorClip,
    CompositeVideoClip, TextClip, VideoClip, AudioFileClip,
    concatenate_audioclips
)
from moviepy.audio.AudioClip import AudioArrayClip
import moviepy.video.fx.all as vfx


# ══════════════════════════════════════════════════════════════════
#  COLOUR TOKENS  (CapCut-inspired dark studio palette)
# ══════════════════════════════════════════════════════════════════
C = {
    "bg":           "#0f0f0f",
    "surface":      "#1a1a1a",
    "panel":        "#222222",
    "raised":       "#2a2a2a",
    "border":       "#333333",
    "accent":       "#00c8ff",   # cyan — timeline playhead, selections
    "accent2":      "#ff3cac",   # magenta — audio / mute regions
    "accent3":      "#39d353",   # green  — BGM / music track
    "accent4":      "#ffb700",   # amber  — warnings, clips
    "text":         "#e8e8e8",
    "text_dim":     "#888888",
    "text_faint":   "#444444",
    "clip_video":   "#1e4d7a",
    "clip_audio":   "#1a5c2e",
    "clip_bgm":     "#4a1a6e",
    "clip_mute":    "#6e1a1a",
    "waveform":     "#00c8ff",
    "waveform_mute":"#ff3cac",
}


class Tooltip:
    """Lightweight hover tooltip."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text   = text
        self.tw     = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tw: return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tw = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, bg="#333", fg="white",
                 font=("Arial", 9), relief="solid", bd=1,
                 padx=6, pady=3).pack()

    def hide(self, _=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None


def icon_btn(parent, text, tip, cmd, bg=None, fg="white", w=None):
    """Small icon-style button with tooltip."""
    kw = dict(text=text, command=cmd, bg=bg or C["raised"],
              fg=fg, font=("Segoe UI Emoji", 11), relief="flat",
              activebackground=C["border"], activeforeground="white",
              cursor="hand2", bd=0, padx=6, pady=4)
    if w: kw["width"] = w
    b = tk.Button(parent, **kw)
    Tooltip(b, tip)
    return b


# ══════════════════════════════════════════════════════════════════
#  AUDIO WAVEFORM HELPER
# ══════════════════════════════════════════════════════════════════
def extract_waveform_samples(path, n_samples=300):
    """Return normalised waveform array (0‥1) from an audio/video file."""
    try:
        from moviepy.editor import VideoFileClip, AudioFileClip
        ext = path.lower().split(".")[-1]
        if ext in ("mp4", "mov", "avi", "mkv", "webm"):
            clip = VideoFileClip(path)
            audio = clip.audio
        else:
            audio = AudioFileClip(path)
        if audio is None:
            return None
        dur = audio.duration
        times = np.linspace(0, dur - 1/44100, n_samples)
        frames = np.array([audio.get_frame(t) for t in times])
        if frames.ndim == 2:
            frames = frames.mean(axis=1)
        frames = np.abs(frames)
        mx = frames.max()
        if mx > 0:
            frames /= mx
        clip.close() if ext in ("mp4","mov","avi","mkv","webm") else audio.close()
        return frames
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════
class VideoMergerStudio:
    # ── track layout constants ─────────────────────────────────
    TRACK_H      = 64    # px per video/image track row
    AUDIO_TRACK_H= 48    # px per audio/bgm track row
    RULER_H      = 24    # top ruler
    PPS          = 80    # pixels per second (zoom level)
    MIN_PPS      = 20
    MAX_PPS      = 400
    LABEL_W      = 90    # left label gutter

    def __init__(self, root):
        self.root = root
        self.root.title("NLE Studio Pro — Video & Audio Editor")
        self.root.geometry("1400x900")
        self.root.configure(bg=C["bg"])

        # ── state ──────────────────────────────────────────────
        self.media_queue   = []     # list of clip dicts
        self.bgm_tracks    = []     # [{path, volume, start, mute_regions}]
        self.selected_idx  = None
        self.thumbs        = {}
        self.waveforms     = {}     # path → np array
        self.preview_clip  = None
        self.preview_img   = None
        self.playhead_t    = tk.DoubleVar(value=0.0)
        self.is_playing    = False
        self.play_thread   = None

        # drag state
        self._drag_item    = None
        self._drag_start_x = 0
        self._drag_orig_start = 0.0

        # mute-region drawing state
        self._mute_drawing = False
        self._mute_draw_item_idx = None
        self._mute_draw_start_t  = 0.0

        # ── build UI ──────────────────────────────────────────
        self._build_ui()
        self.refresh_timeline()

    # ══════════════════════════════════════════════════════════
    #  UI CONSTRUCTION
    # ══════════════════════════════════════════════════════════
    def _build_ui(self):
        # ── top toolbar ───────────────────────────────────────
        tb = tk.Frame(self.root, bg=C["surface"], height=44)
        tb.pack(side=tk.TOP, fill=tk.X)
        tb.pack_propagate(False)
        self._build_toolbar(tb)

        # ── main pane (left panel + right workspace) ──────────
        main = tk.PanedWindow(self.root, orient=tk.HORIZONTAL,
                              bg=C["bg"], sashwidth=4,
                              sashrelief="flat")
        main.pack(fill=tk.BOTH, expand=True)

        # left panel
        left = tk.Frame(main, bg=C["panel"], width=280)
        left.pack_propagate(False)
        main.add(left, minsize=220)
        self._build_left_panel(left)

        # right side: preview + timeline
        right = tk.Frame(main, bg=C["bg"])
        main.add(right, minsize=700)
        self._build_right_side(right)

    # ── toolbar ───────────────────────────────────────────────
    def _build_toolbar(self, tb):
        tk.Label(tb, text="🎬 NLE Studio Pro",
                 bg=C["surface"], fg=C["accent"],
                 font=("Arial", 13, "bold")).pack(side=tk.LEFT, padx=12)

        # centre transport controls
        tr = tk.Frame(tb, bg=C["surface"])
        tr.pack(side=tk.LEFT, expand=True)

        icon_btn(tr, "⏮",  "Go to Start",     self.go_to_start).pack(side=tk.LEFT, padx=2)
        icon_btn(tr, "◀◀", "Rewind 5s",        self.rewind_5).pack(side=tk.LEFT, padx=2)
        self.play_btn = icon_btn(tr, "▶", "Play / Pause", self.toggle_play,
                                 bg=C["accent"], fg=C["bg"])
        self.play_btn.pack(side=tk.LEFT, padx=4)
        icon_btn(tr, "▶▶", "Forward 5s",       self.forward_5).pack(side=tk.LEFT, padx=2)
        icon_btn(tr, "⏭",  "Go to End",        self.go_to_end).pack(side=tk.LEFT, padx=2)

        # timecode display
        self.timecode_var = tk.StringVar(value="00:00:00")
        tk.Label(tr, textvariable=self.timecode_var,
                 bg=C["surface"], fg=C["accent"],
                 font=("Courier", 13, "bold"), width=10).pack(side=tk.LEFT, padx=10)

        # zoom
        zf = tk.Frame(tr, bg=C["surface"])
        zf.pack(side=tk.LEFT, padx=8)
        tk.Label(zf, text="Zoom:", bg=C["surface"],
                 fg=C["text_dim"], font=("Arial", 9)).pack(side=tk.LEFT)
        icon_btn(zf, "－", "Zoom Out", self.zoom_out).pack(side=tk.LEFT, padx=1)
        icon_btn(zf, "＋", "Zoom In",  self.zoom_in).pack(side=tk.LEFT, padx=1)

        # right-side export btn
        icon_btn(tb, "🚀 EXPORT", "Export video", self.start_merge_thread,
                 bg="#e91e63", w=12).pack(side=tk.RIGHT, padx=10, pady=6)

    # ── left panel ────────────────────────────────────────────
    def _build_left_panel(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill=tk.BOTH, expand=True)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook",        background=C["panel"], borderwidth=0)
        style.configure("TNotebook.Tab",    background=C["raised"],
                        foreground=C["text_dim"], padding=[8, 4])
        style.map("TNotebook.Tab",
                  background=[("selected", C["surface"])],
                  foreground=[("selected", C["accent"])])

        self._build_media_tab(nb)
        self._build_audio_tab(nb)
        self._build_vfx_tab(nb)
        self._build_inspector_tab(nb)

    def _build_media_tab(self, nb):
        f = tk.Frame(nb, bg=C["panel"])
        nb.add(f, text=" 📁 Media ")

        tk.Button(f, text="＋ Add Video / Image",
                  command=self.add_media,
                  bg=C["accent"], fg=C["bg"],
                  font=("Arial", 10, "bold"),
                  relief="flat", cursor="hand2").pack(fill=tk.X, padx=8, pady=(10,4))

        tk.Button(f, text="✨ Add Title Card",
                  command=self.add_title_card,
                  bg="#2196F3", fg="white",
                  font=("Arial", 10, "bold"),
                  relief="flat", cursor="hand2").pack(fill=tk.X, padx=8, pady=4)

        tk.Button(f, text="[ ] Add Placeholder",
                  command=self.add_placeholder,
                  bg=C["raised"], fg=C["accent4"],
                  font=("Arial", 10, "bold"),
                  relief="flat", cursor="hand2").pack(fill=tk.X, padx=8, pady=4)

        sep = tk.Frame(f, bg=C["border"], height=1)
        sep.pack(fill=tk.X, padx=8, pady=8)

        # output format
        tk.Label(f, text="OUTPUT FORMAT", bg=C["panel"],
                 fg=C["text_dim"], font=("Arial", 8, "bold")).pack(anchor="w", padx=10)
        self.format_var = tk.StringVar(value="desktop")
        for val, lbl in [("desktop","16:9 Landscape 1920×1080"),
                         ("mobile", "9:16 Portrait  1080×1920")]:
            tk.Radiobutton(f, text=lbl, variable=self.format_var, value=val,
                           bg=C["panel"], fg=C["text"],
                           selectcolor=C["raised"],
                           activebackground=C["panel"]).pack(anchor="w", padx=14, pady=1)

        sep2 = tk.Frame(f, bg=C["border"], height=1)
        sep2.pack(fill=tk.X, padx=8, pady=8)

        # options
        self.auto_rotate_var = tk.BooleanVar(value=True)
        self.smart_fill_var  = tk.BooleanVar(value=True)
        for var, lbl in [(self.auto_rotate_var, "Auto-Rotate clips"),
                         (self.smart_fill_var,  "Smart Fill (crop to fit)")]:
            tk.Checkbutton(f, text=lbl, variable=var,
                           bg=C["panel"], fg=C["text"],
                           selectcolor=C["raised"],
                           activebackground=C["panel"]).pack(anchor="w", padx=14, pady=2)

        sep3 = tk.Frame(f, bg=C["border"], height=1)
        sep3.pack(fill=tk.X, padx=8, pady=8)

        # templates
        tk.Label(f, text="TEMPLATES", bg=C["panel"],
                 fg=C["text_dim"], font=("Arial", 8, "bold")).pack(anchor="w", padx=10)
        for tid, lbl, col in [
            (1, "Deep Space + Aurora",   "#3b0086"),
            (2, "Light Burst + Purple",  "#c200ff"),
            (3, "Cinematic Flare",       "#0088aa"),
        ]:
            tk.Button(f, text=lbl, bg=col, fg="white",
                      command=lambda t=tid: self.apply_template(t),
                      relief="flat", cursor="hand2").pack(fill=tk.X, padx=8, pady=3)

        self.status_label = tk.Label(f, text="Ready.", bg=C["panel"],
                                     fg=C["text_dim"], font=("Arial", 9))
        self.status_label.pack(side=tk.BOTTOM, pady=6)

    def _build_audio_tab(self, nb):
        f = tk.Frame(nb, bg=C["panel"])
        nb.add(f, text=" 🎵 Audio ")
        self.audio_tab_frame = f
        self._refresh_audio_tab()

    def _refresh_audio_tab(self):
        f = self.audio_tab_frame
        for w in f.winfo_children(): w.destroy()

        tk.Label(f, text="BACKGROUND MUSIC", bg=C["panel"],
                 fg=C["text_dim"], font=("Arial", 8, "bold")).pack(anchor="w", padx=10, pady=(10,4))

        tk.Button(f, text="＋ Add BGM Track",
                  command=self.add_bgm_track,
                  bg=C["accent3"], fg=C["bg"],
                  font=("Arial", 10, "bold"),
                  relief="flat", cursor="hand2").pack(fill=tk.X, padx=8, pady=4)

        for i, bgm in enumerate(self.bgm_tracks):
            self._bgm_row(f, i, bgm)

        sep = tk.Frame(f, bg=C["border"], height=1)
        sep.pack(fill=tk.X, padx=8, pady=10)

        tk.Label(f, text="CLIP AUDIO TOOLS", bg=C["panel"],
                 fg=C["text_dim"], font=("Arial", 8, "bold")).pack(anchor="w", padx=10)

        tk.Button(f, text="🔇 Mute Region on Selected Clip",
                  command=self.start_mute_draw_mode,
                  bg=C["accent2"], fg="white",
                  font=("Arial", 9, "bold"),
                  relief="flat", cursor="hand2").pack(fill=tk.X, padx=8, pady=3)

        tk.Button(f, text="🔊 Clear All Mutes on Selected",
                  command=self.clear_mutes_on_selected,
                  bg=C["raised"], fg="white",
                  font=("Arial", 9), relief="flat",
                  cursor="hand2").pack(fill=tk.X, padx=8, pady=3)

        sep2 = tk.Frame(f, bg=C["border"], height=1)
        sep2.pack(fill=tk.X, padx=8, pady=10)

        tk.Label(f, text="SELECTED CLIP VOLUME", bg=C["panel"],
                 fg=C["text_dim"], font=("Arial", 8, "bold")).pack(anchor="w", padx=10)
        self.clip_vol_var = tk.DoubleVar(value=1.0)
        vol_row = tk.Frame(f, bg=C["panel"])
        vol_row.pack(fill=tk.X, padx=8, pady=4)
        tk.Label(vol_row, text="Vol:", bg=C["panel"], fg=C["text"], width=5).pack(side=tk.LEFT)
        tk.Scale(vol_row, from_=0.0, to=2.0, resolution=0.05,
                 orient=tk.HORIZONTAL, variable=self.clip_vol_var,
                 bg=C["panel"], fg=C["text"], highlightthickness=0,
                 troughcolor=C["raised"], length=160,
                 command=self._apply_clip_volume).pack(side=tk.LEFT)

        self.clip_mute_var = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="Mute entire clip",
                       variable=self.clip_mute_var,
                       command=self._apply_clip_mute,
                       bg=C["panel"], fg=C["text"],
                       selectcolor=C["raised"],
                       activebackground=C["panel"]).pack(anchor="w", padx=14, pady=2)

    def _bgm_row(self, parent, idx, bgm):
        row = tk.Frame(parent, bg=C["raised"], relief="flat")
        row.pack(fill=tk.X, padx=8, pady=3)

        name = os.path.basename(bgm["path"])[:22]
        tk.Label(row, text=f"♪ {name}", bg=C["raised"],
                 fg=C["accent3"], font=("Arial", 9, "bold"),
                 anchor="w").pack(fill=tk.X, padx=6, pady=(4,0))

        ctrl = tk.Frame(row, bg=C["raised"])
        ctrl.pack(fill=tk.X, padx=4, pady=4)

        tk.Label(ctrl, text="Vol:", bg=C["raised"],
                 fg=C["text_dim"], font=("Arial", 8), width=4).pack(side=tk.LEFT)
        vol_var = tk.DoubleVar(value=bgm.get("volume", 0.7))
        bgm["_vol_var"] = vol_var
        tk.Scale(ctrl, from_=0.0, to=1.5, resolution=0.05,
                 orient=tk.HORIZONTAL, variable=vol_var,
                 bg=C["raised"], fg=C["text"], highlightthickness=0,
                 troughcolor=C["border"], length=100,
                 command=lambda v, i=idx: self._bgm_vol_changed(i, v)
                 ).pack(side=tk.LEFT, padx=2)

        mute_var = tk.BooleanVar(value=bgm.get("muted", False))
        bgm["_mute_var"] = mute_var
        tk.Checkbutton(ctrl, text="🔇", variable=mute_var,
                       command=lambda i=idx: self._bgm_mute_toggled(i),
                       bg=C["raised"], fg=C["text"],
                       selectcolor=C["raised"],
                       activebackground=C["raised"],
                       font=("Segoe UI Emoji",10)).pack(side=tk.LEFT, padx=2)

        tk.Button(ctrl, text="✕",
                  command=lambda i=idx: self.remove_bgm(i),
                  bg=C["raised"], fg="#ff4444",
                  font=("Arial", 10, "bold"),
                  relief="flat", cursor="hand2").pack(side=tk.RIGHT, padx=4)

        # start-offset
        off_row = tk.Frame(row, bg=C["raised"])
        off_row.pack(fill=tk.X, padx=4, pady=(0,4))
        tk.Label(off_row, text="Start at (s):", bg=C["raised"],
                 fg=C["text_dim"], font=("Arial", 8)).pack(side=tk.LEFT)
        off_var = tk.DoubleVar(value=bgm.get("start_offset", 0.0))
        bgm["_off_var"] = off_var
        tk.Spinbox(off_row, from_=0, to=9999, increment=0.5,
                   textvariable=off_var, width=6,
                   bg=C["raised"], fg=C["text"],
                   command=lambda i=idx: self._bgm_offset_changed(i)).pack(side=tk.LEFT, padx=4)

    def _build_vfx_tab(self, nb):
        f = tk.Frame(nb, bg=C["panel"])
        nb.add(f, text=" ✨ VFX ")

        tk.Label(f, text="VFX THEMES FOR TITLE CARDS", bg=C["panel"],
                 fg=C["text_dim"], font=("Arial", 8, "bold")).pack(anchor="w", padx=10, pady=(10,4))

        themes = [
            ("Light Speed Starburst",    "#100030"),
            ("Deep Space Stars",         "#001430"),
            ("Travelling Flare",         "#002a14"),
            ("Matrix Green Particles",   "#001500"),
            ("Golden Fire Particles",    "#2a1000"),
        ]
        for name, col in themes:
            tk.Label(f, text=f"  ●  {name}", bg=col, fg="white",
                     font=("Arial", 9), anchor="w",
                     relief="flat").pack(fill=tk.X, padx=8, pady=2)

        sep = tk.Frame(f, bg=C["border"], height=1)
        sep.pack(fill=tk.X, padx=8, pady=10)

        tk.Label(f, text="TRANSITIONS", bg=C["panel"],
                 fg=C["text_dim"], font=("Arial", 8, "bold")).pack(anchor="w", padx=10)
        for t in ["Crossfade","Dip to Black","Hard Cut",
                  "Slide Left","Slide Up","Zoom In Fade","Bright Flash","Pull and Snap"]:
            tk.Label(f, text=f"  ›  {t}", bg=C["panel"],
                     fg=C["text"], font=("Arial", 9),
                     anchor="w").pack(fill=tk.X, padx=8, pady=1)

    def _build_inspector_tab(self, nb):
        f = tk.Frame(nb, bg=C["panel"])
        nb.add(f, text=" ⚙ Inspector ")
        self.inspector_nb_frame = f
        tk.Label(f, text="Select a clip on the timeline\nto see its properties here.",
                 bg=C["panel"], fg=C["text_dim"],
                 font=("Arial", 10), justify=tk.CENTER).pack(pady=60)

    # ── right side: preview + timeline ────────────────────────
    def _build_right_side(self, parent):
        # top: preview
        pv_frame = tk.Frame(parent, bg=C["surface"], height=320)
        pv_frame.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(6,0))
        pv_frame.pack_propagate(False)
        self._build_preview(pv_frame)

        # bottom: timeline
        tl_frame = tk.Frame(parent, bg=C["bg"])
        tl_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=6)
        self._build_timeline(tl_frame)

    def _build_preview(self, parent):
        # preview label (centre)
        self.preview_label = tk.Label(parent, bg="#000000",
                                      text="No clip selected",
                                      fg=C["text_dim"], font=("Arial", 11))
        self.preview_label.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

        # right controls panel
        ctrl = tk.Frame(parent, bg=C["surface"], width=200)
        ctrl.pack(side=tk.RIGHT, fill=tk.Y, padx=6, pady=6)
        ctrl.pack_propagate(False)

        tk.Label(ctrl, text="CLIP EDITOR", bg=C["surface"],
                 fg=C["accent"], font=("Arial", 9, "bold")).pack(pady=(6,4))

        # rotation / flip
        rf = tk.Frame(ctrl, bg=C["surface"])
        rf.pack(pady=4)
        icon_btn(rf, "↺", "Rotate Left",  lambda: self.change_rotation("left")).grid(row=0,column=0,padx=2,pady=2)
        icon_btn(rf, "↻", "Rotate Right", lambda: self.change_rotation("right")).grid(row=0,column=1,padx=2,pady=2)
        icon_btn(rf, "↔", "Flip H",       lambda: self.change_rotation("fliph")).grid(row=1,column=0,padx=2,pady=2)
        icon_btn(rf, "↕", "Flip V",       lambda: self.change_rotation("flipv")).grid(row=1,column=1,padx=2,pady=2)

        sep = tk.Frame(ctrl, bg=C["border"], height=1)
        sep.pack(fill=tk.X, pady=6)

        # trim sliders
        tk.Label(ctrl, text="TRIM", bg=C["surface"],
                 fg=C["text_dim"], font=("Arial", 8, "bold")).pack(anchor="w", padx=6)
        self.scrubber   = tk.Scale(ctrl, from_=0, to=100, orient=tk.HORIZONTAL,
                                   resolution=0.1, showvalue=1,
                                   bg=C["surface"], fg=C["text"],
                                   highlightthickness=0, length=180,
                                   label="Scrub", troughcolor=C["accent"],
                                   command=self.update_preview)
        self.scrubber.pack(padx=4)
        self.trim_start = tk.Scale(ctrl, from_=0, to=100, orient=tk.HORIZONTAL,
                                   resolution=0.1, showvalue=1,
                                   bg=C["surface"], fg=C["accent3"],
                                   highlightthickness=0, length=180,
                                   label="Trim Start", troughcolor=C["raised"])
        self.trim_start.pack(padx=4)
        self.trim_end   = tk.Scale(ctrl, from_=0, to=100, orient=tk.HORIZONTAL,
                                   resolution=0.1, showvalue=1,
                                   bg=C["surface"], fg=C["accent2"],
                                   highlightthickness=0, length=180,
                                   label="Trim End", troughcolor=C["raised"])
        self.trim_end.pack(padx=4)

        btn_row = tk.Frame(ctrl, bg=C["surface"])
        btn_row.pack(pady=4)
        self.btn_trim = tk.Button(btn_row, text="✂ Trim",
                                  command=self.execute_trim,
                                  bg=C["accent3"], fg=C["bg"],
                                  font=("Arial", 9,"bold"),
                                  relief="flat", cursor="hand2", state=tk.DISABLED)
        self.btn_trim.pack(side=tk.LEFT, padx=2)
        self.btn_cut  = tk.Button(btn_row, text="✁ Split",
                                  command=self.split_at_playhead,
                                  bg=C["accent2"], fg="white",
                                  font=("Arial", 9,"bold"),
                                  relief="flat", cursor="hand2", state=tk.DISABLED)
        self.btn_cut.pack(side=tk.LEFT, padx=2)
        Tooltip(self.btn_trim, "Keep region between Trim Start and End")
        Tooltip(self.btn_cut,  "Split selected clip at playhead position")

    # ── timeline canvas ───────────────────────────────────────
    def _build_timeline(self, parent):
        # toolbar strip above timeline
        tt = tk.Frame(parent, bg=C["surface"], height=30)
        tt.pack(side=tk.TOP, fill=tk.X)
        tt.pack_propagate(False)

        icon_btn(tt, "✂ Split",    "Split selected clip at playhead",
                 self.split_at_playhead).pack(side=tk.LEFT, padx=4, pady=3)
        icon_btn(tt, "🗑 Delete",   "Delete selected clip",
                 self.delete_selected, fg="#ff4444").pack(side=tk.LEFT, padx=2, pady=3)
        icon_btn(tt, "◀ Move",     "Move selected clip left",
                 self.move_left).pack(side=tk.LEFT, padx=2, pady=3)
        icon_btn(tt, "Move ▶",     "Move selected clip right",
                 self.move_right).pack(side=tk.LEFT, padx=2, pady=3)
        icon_btn(tt, "🔇 Mute Rgn","Draw mute region (click+drag on clip)",
                 self.start_mute_draw_mode, bg=C["clip_mute"]).pack(side=tk.LEFT, padx=8, pady=3)

        self.tl_mode_label = tk.Label(tt, text="", bg=C["surface"],
                                      fg=C["accent2"], font=("Arial", 9, "bold"))
        self.tl_mode_label.pack(side=tk.LEFT, padx=4)

        # canvas + scrollbars
        tl_body = tk.Frame(parent, bg=C["bg"])
        tl_body.pack(fill=tk.BOTH, expand=True)

        self.tl_canvas = tk.Canvas(tl_body, bg=C["bg"],
                                   highlightthickness=0, cursor="crosshair")
        h_scroll = ttk.Scrollbar(tl_body, orient=tk.HORIZONTAL,
                                 command=self.tl_canvas.xview)
        v_scroll = ttk.Scrollbar(tl_body, orient=tk.VERTICAL,
                                 command=self.tl_canvas.yview)
        self.tl_canvas.configure(xscrollcommand=h_scroll.set,
                                 yscrollcommand=v_scroll.set)

        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tl_canvas.pack(fill=tk.BOTH, expand=True)

        # canvas events
        self.tl_canvas.bind("<Button-1>",       self._tl_click)
        self.tl_canvas.bind("<B1-Motion>",      self._tl_drag)
        self.tl_canvas.bind("<ButtonRelease-1>",self._tl_release)
        self.tl_canvas.bind("<Button-3>",       self._tl_right_click)
        self.tl_canvas.bind("<MouseWheel>",     self._tl_mousewheel)

    # ══════════════════════════════════════════════════════════
    #  TIMELINE RENDERING
    # ══════════════════════════════════════════════════════════
    def refresh_timeline(self):
        c = self.tl_canvas
        c.delete("all")

        # total duration
        total_dur = self._total_duration()
        canvas_w = max(self.LABEL_W + int(total_dur * self.PPS) + 200, 900)
        n_tracks  = len(self.media_queue) + len(self.bgm_tracks) + 2
        canvas_h  = self.RULER_H + n_tracks * (self.TRACK_H + 2) + 40
        c.configure(scrollregion=(0, 0, canvas_w, canvas_h))

        # ── ruler ─────────────────────────────────────────────
        c.create_rectangle(0, 0, canvas_w, self.RULER_H,
                           fill=C["surface"], outline="")
        step = self._ruler_step()
        t = 0.0
        while t <= total_dur + step:
            x = self.LABEL_W + int(t * self.PPS)
            c.create_line(x, self.RULER_H-8, x, self.RULER_H,
                          fill=C["text_dim"], width=1)
            mins  = int(t) // 60
            secs  = int(t) % 60
            label = f"{mins:02d}:{secs:02d}"
            c.create_text(x, self.RULER_H//2, text=label,
                          fill=C["text_dim"], font=("Courier", 8), anchor="center")
            t += step

        # ── track labels gutter background ────────────────────
        c.create_rectangle(0, 0, self.LABEL_W, canvas_h,
                           fill=C["surface"], outline="")

        # ── video / image tracks ──────────────────────────────
        y_cursor = self.RULER_H + 4

        for i, item in enumerate(self.media_queue):
            y_top = y_cursor
            y_bot = y_top + self.TRACK_H

            # compute x from timeline position
            t_start = item.get("tl_start", 0.0)
            clip_dur = self._item_duration(item)
            x_left  = self.LABEL_W + int(t_start  * self.PPS)
            x_right = self.LABEL_W + int((t_start + clip_dur) * self.PPS)

            is_sel = (i == self.selected_idx)
            col_bg = C["clip_video"] if item["type"] != "title" else "#2a0050"
            border_col = C["accent"] if is_sel else C["border"]
            bw = 2 if is_sel else 1

            # clip rectangle
            c.create_rectangle(x_left, y_top, x_right, y_bot,
                               fill=col_bg, outline=border_col, width=bw,
                               tags=(f"clip_{i}", "clip"))

            # waveform strip inside clip
            if item.get("path") and item["type"] == "video":
                self._draw_waveform_strip(c, item, i, x_left, x_right,
                                          y_top, y_bot, clip_dur)

            # thumbnail in clip
            self._draw_clip_thumb(c, item, i, x_left, x_right, y_top, y_bot)

            # clip label
            name = (item.get("main_text","") if item["type"]=="title"
                    else os.path.basename(item.get("path","clip")))[:20]
            c.create_text(x_left+6, y_top+6, text=name,
                          fill="white", font=("Arial",8,"bold"), anchor="nw")

            # duration badge
            dur_s = f"{clip_dur:.1f}s"
            c.create_text(x_right-4, y_bot-4, text=dur_s,
                          fill=C["text_dim"], font=("Arial",7), anchor="se")

            # mute regions
            for mr in item.get("mute_regions", []):
                mx1 = x_left + int(mr[0] * self.PPS)
                mx2 = x_left + int(mr[1] * self.PPS)
                mx1 = max(x_left, min(mx1, x_right))
                mx2 = max(x_left, min(mx2, x_right))
                c.create_rectangle(mx1, y_bot-16, mx2, y_bot,
                                   fill=C["clip_mute"], outline=C["accent2"],
                                   width=1, tags="mute_region")
                c.create_text((mx1+mx2)//2, y_bot-8,
                              text="🔇", fill="white",
                              font=("Segoe UI Emoji", 7))

            # transition badge
            if i > 0:
                trans = self.media_queue[i-1]["trans"]
                short = {"Crossfade":"CF","Dip to Black":"DIP","Hard Cut":"CUT",
                         "Slide Left":"SL","Slide Up":"SU","Zoom In Fade":"ZM",
                         "Bright Flash":"BF","Pull and Snap":"PS"}.get(trans,"CUT")
                c.create_oval(x_left-10, (y_top+y_bot)//2-10,
                              x_left+10, (y_top+y_bot)//2+10,
                              fill=C["accent2"], outline="white", width=1)
                c.create_text(x_left, (y_top+y_bot)//2,
                              text=short, fill="white", font=("Arial",6,"bold"))

            # entire-clip mute overlay
            if item.get("clip_muted", False):
                c.create_rectangle(x_left, y_top, x_right, y_bot,
                                   fill=C["clip_mute"], stipple="gray25",
                                   outline="")
                c.create_text((x_left+x_right)//2, (y_top+y_bot)//2,
                              text="MUTED", fill=C["accent2"],
                              font=("Arial",10,"bold"))

            # track label
            c.create_text(self.LABEL_W//2, (y_top+y_bot)//2,
                          text=f"V{i+1}", fill=C["text_dim"],
                          font=("Arial",8,"bold"))

            y_cursor = y_bot + 2

        # ── BGM tracks ────────────────────────────────────────
        bgm_y = y_cursor + 10
        c.create_line(0, bgm_y, canvas_w, bgm_y,
                      fill=C["border"], dash=(4,4))
        bgm_y += 4

        for j, bgm in enumerate(self.bgm_tracks):
            y_top = bgm_y
            y_bot = y_top + self.AUDIO_TRACK_H
            x_left = self.LABEL_W + int(bgm.get("start_offset",0)*self.PPS)

            # try to get duration of BGM
            try:
                bgm_clip = AudioFileClip(bgm["path"])
                bdur = bgm_clip.duration
                bgm_clip.close()
            except Exception:
                bdur = total_dur

            x_right = self.LABEL_W + int((bgm.get("start_offset",0)+bdur)*self.PPS)
            x_right = min(x_right, canvas_w - 10)

            col = C["clip_bgm"] if not bgm.get("muted") else C["clip_mute"]
            c.create_rectangle(x_left, y_top, x_right, y_bot,
                               fill=col, outline=C["accent3"], width=1,
                               tags=f"bgm_{j}")

            # waveform
            path = bgm["path"]
            if path not in self.waveforms:
                self.waveforms[path] = extract_waveform_samples(path, 200)
            wf = self.waveforms.get(path)
            if wf is not None:
                self._draw_raw_waveform(c, wf, x_left, x_right,
                                        y_top, y_bot, C["accent3"])

            name = os.path.basename(bgm["path"])[:22]
            mute_tag = " [MUTED]" if bgm.get("muted") else ""
            c.create_text(x_left+6, y_top+6,
                          text=f"♪ {name}{mute_tag}",
                          fill=C["accent3"] if not bgm.get("muted") else C["text_dim"],
                          font=("Arial",8,"bold"), anchor="nw")

            vol_str = f"vol {bgm.get('volume',0.7):.0%}"
            c.create_text(x_right-4, y_bot-4, text=vol_str,
                          fill=C["text_dim"], font=("Arial",7), anchor="se")

            c.create_text(self.LABEL_W//2, (y_top+y_bot)//2,
                          text=f"BGM{j+1}", fill=C["accent3"],
                          font=("Arial",8,"bold"))

            bgm_y = y_bot + 2

        # ── playhead ──────────────────────────────────────────
        ph_x = self.LABEL_W + int(self.playhead_t.get() * self.PPS)
        c.create_line(ph_x, 0, ph_x, canvas_h,
                      fill=C["accent"], width=2, tags="playhead")
        c.create_polygon(ph_x-6, 0, ph_x+6, 0, ph_x, 10,
                         fill=C["accent"], tags="playhead")

        # item count
        self.status_label.config(
            text=f"{len(self.media_queue)} clips  |  "
                 f"{len(self.bgm_tracks)} BGM  |  "
                 f"Total: {total_dur:.1f}s",
            fg=C["text_dim"])

        self._render_inspector()

    def _draw_waveform_strip(self, c, item, idx,
                              x_left, x_right, y_top, y_bot, clip_dur):
        path = item.get("path","")
        if not path: return
        if path not in self.waveforms:
            self.waveforms[path] = extract_waveform_samples(path, 300)

        wf = self.waveforms.get(path)
        if wf is None: return

        mute_regions = item.get("mute_regions", [])
        strip_y_top  = y_bot - 22
        strip_y_bot  = y_bot - 2

        self._draw_raw_waveform(c, wf, x_left, x_right,
                                strip_y_top, strip_y_bot,
                                C["waveform"],
                                mute_regions=mute_regions,
                                clip_dur=clip_dur)

    def _draw_raw_waveform(self, c, wf, x_left, x_right,
                            y_top, y_bot, col,
                            mute_regions=None, clip_dur=None):
        w = max(1, x_right - x_left)
        h = max(1, y_bot - y_top)
        mid = (y_top + y_bot) // 2
        n   = len(wf)

        points = []
        for px in range(w):
            si  = int(px / w * n)
            si  = min(si, n-1)
            amp = wf[si] * (h//2) * 0.9
            t_sec = (px / w * clip_dur) if clip_dur else 0

            # colour: red if inside a mute region
            seg_col = col
            if mute_regions and clip_dur:
                for mr in mute_regions:
                    if mr[0] <= t_sec <= mr[1]:
                        seg_col = C["waveform_mute"]
                        break

            x = x_left + px
            c.create_line(x, mid-amp, x, mid+amp,
                          fill=seg_col, width=1)

    def _draw_clip_thumb(self, c, item, idx, x_left, x_right, y_top, y_bot):
        key = f"thumb_{idx}"
        thumb_region_h = y_bot - y_top - 24  # leave bottom strip for waveform
        if key not in self.thumbs:
            self.thumbs[key] = self._generate_thumbnail(
                item.get("path",""), item["type"],
                item.get("rotation",0), item.get("flip_h",False),
                item.get("flip_v",False), w=80, h=thumb_region_h)
        if self.thumbs[key]:
            cx = (x_left + min(x_right, x_left+90)) // 2
            c.create_image(cx, y_top + thumb_region_h//2 + 2,
                           image=self.thumbs[key])

    # ══════════════════════════════════════════════════════════
    #  TIMELINE INTERACTIONS
    # ══════════════════════════════════════════════════════════
    def _tl_click(self, event):
        cx = self.tl_canvas.canvasx(event.x)
        cy = self.tl_canvas.canvasy(event.y)

        # move playhead if click is in ruler
        if cy <= self.RULER_H:
            t = max(0.0, (cx - self.LABEL_W) / self.PPS)
            self.playhead_t.set(t)
            self._update_timecode(t)
            self.refresh_timeline()
            return

        if self._mute_drawing and self.selected_idx is not None:
            item = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            x_clip_left = self.LABEL_W + int(t_start * self.PPS)
            local_t = max(0.0, (cx - x_clip_left) / self.PPS)
            self._mute_draw_start_t = local_t
            return

        # hit-test clips
        y_cursor = self.RULER_H + 4
        for i, item in enumerate(self.media_queue):
            y_top = y_cursor
            y_bot = y_top + self.TRACK_H
            t_start  = item.get("tl_start", 0.0)
            clip_dur = self._item_duration(item)
            x_left   = self.LABEL_W + int(t_start * self.PPS)
            x_right  = self.LABEL_W + int((t_start + clip_dur) * self.PPS)

            if x_left <= cx <= x_right and y_top <= cy <= y_bot:
                self.selected_idx = i
                self._drag_item      = i
                self._drag_start_x   = cx
                self._drag_orig_start = item.get("tl_start", 0.0)
                self.load_preview_engine(item)
                self.refresh_timeline()
                return
            y_cursor = y_bot + 2

        # clicked empty area → deselect
        self.selected_idx = None
        self._drag_item   = None
        self.refresh_timeline()

    def _tl_drag(self, event):
        cx = self.tl_canvas.canvasx(event.x)

        # mute-region drawing
        if self._mute_drawing and self.selected_idx is not None:
            self.refresh_timeline()
            item     = self.media_queue[self.selected_idx]
            t_start  = item.get("tl_start", 0.0)
            x_clip_l = self.LABEL_W + int(t_start * self.PPS)
            local_t  = max(0.0, (cx - x_clip_l) / self.PPS)

            y_cursor = self.RULER_H + 4
            for i2 in range(self.selected_idx):
                y_cursor += self.TRACK_H + 2
            y_top = y_cursor
            y_bot = y_top + self.TRACK_H

            t0, t1 = sorted([self._mute_draw_start_t, local_t])
            x0 = self.LABEL_W + int((t_start + t0) * self.PPS)
            x1 = self.LABEL_W + int((t_start + t1) * self.PPS)
            self.tl_canvas.create_rectangle(x0, y_bot-16, x1, y_bot,
                                             fill=C["clip_mute"],
                                             outline=C["accent2"],
                                             stipple="gray50",
                                             tags="mute_preview")
            return

        # clip drag
        if self._drag_item is None: return
        delta_t = (cx - self._drag_start_x) / self.PPS
        new_start = max(0.0, self._drag_orig_start + delta_t)
        self.media_queue[self._drag_item]["tl_start"] = new_start
        self.refresh_timeline()

    def _tl_release(self, event):
        cx = self.tl_canvas.canvasx(event.x)

        if self._mute_drawing and self.selected_idx is not None:
            item    = self.media_queue[self.selected_idx]
            t_start = item.get("tl_start", 0.0)
            x_clip_l = self.LABEL_W + int(t_start * self.PPS)
            local_t  = max(0.0, (cx - x_clip_l) / self.PPS)
            t0, t1   = sorted([self._mute_draw_start_t, local_t])
            if t1 - t0 > 0.05:
                item.setdefault("mute_regions", []).append((t0, t1))
            self._mute_drawing = False
            self.tl_mode_label.config(text="")
            self.tl_canvas.configure(cursor="crosshair")
            self.refresh_timeline()
            return

        self._drag_item = None

    def _tl_right_click(self, event):
        """Context menu on right-click."""
        cx = self.tl_canvas.canvasx(event.x)
        cy = self.tl_canvas.canvasy(event.y)

        y_cursor = self.RULER_H + 4
        for i, item in enumerate(self.media_queue):
            y_top = y_cursor
            y_bot = y_top + self.TRACK_H
            t_start  = item.get("tl_start", 0.0)
            clip_dur = self._item_duration(item)
            x_left   = self.LABEL_W + int(t_start * self.PPS)
            x_right  = self.LABEL_W + int((t_start + clip_dur) * self.PPS)
            if x_left <= cx <= x_right and y_top <= cy <= y_bot:
                self._show_clip_context_menu(event, i)
                return
            y_cursor = y_bot + 2

    def _show_clip_context_menu(self, event, idx):
        menu = tk.Menu(self.root, tearoff=0,
                       bg=C["panel"], fg=C["text"],
                       activebackground=C["raised"],
                       activeforeground=C["accent"])
        menu.add_command(label="✂  Split at Playhead",
                         command=self.split_at_playhead)
        menu.add_command(label="🗑  Delete",
                         command=self.delete_selected)
        menu.add_separator()
        menu.add_command(label="🔇 Add Mute Region",
                         command=self.start_mute_draw_mode)
        menu.add_command(label="🔊 Clear Mute Regions",
                         command=self.clear_mutes_on_selected)
        menu.add_separator()
        menu.add_command(label="📁 Replace Media",
                         command=self.fill_placeholder)
        self.selected_idx = idx
        menu.tk_popup(event.x_root, event.y_root)

    def _tl_mousewheel(self, event):
        if event.state & 0x4:  # Ctrl held → zoom
            if event.delta > 0: self.zoom_in()
            else:               self.zoom_out()
        else:
            self.tl_canvas.xview_scroll(int(-1*(event.delta/120)), "units")

    # ══════════════════════════════════════════════════════════
    #  INSPECTOR (right-click panel tab)
    # ══════════════════════════════════════════════════════════
    def _render_inspector(self):
        f = self.inspector_nb_frame
        for w in f.winfo_children(): w.destroy()

        if self.selected_idx is None or self.selected_idx >= len(self.media_queue):
            tk.Label(f, text="Select a clip on the timeline\nto see its properties here.",
                     bg=C["panel"], fg=C["text_dim"],
                     font=("Arial", 10), justify=tk.CENTER).pack(pady=60)
            return

        item = self.media_queue[self.selected_idx]

        tk.Label(f, text=f"CLIP {self.selected_idx+1} — {item['type'].upper()}",
                 bg=C["panel"], fg=C["accent"],
                 font=("Arial",10,"bold")).pack(pady=(8,4), padx=6, anchor="w")

        # nav buttons
        bf = tk.Frame(f, bg=C["panel"])
        bf.pack(fill=tk.X, padx=6, pady=4)
        tk.Button(bf, text="◀ Left",  command=self.move_left,
                  bg=C["raised"], fg="white", relief="flat").pack(side=tk.LEFT,padx=2)
        tk.Button(bf, text="Right ▶", command=self.move_right,
                  bg=C["raised"], fg="white", relief="flat").pack(side=tk.LEFT,padx=2)
        tk.Button(bf, text="🗑 Delete", command=self.delete_selected,
                  bg="#b71c1c", fg="white", relief="flat").pack(side=tk.RIGHT,padx=2)

        def row(label, widget_fn):
            r = tk.Frame(f, bg=C["panel"])
            r.pack(fill=tk.X, padx=8, pady=3)
            tk.Label(r, text=label, bg=C["panel"], fg=C["text_dim"],
                     font=("Arial",8), width=14, anchor="e").pack(side=tk.LEFT)
            widget_fn(r)

        self.ins_val   = tk.DoubleVar(value=item["value"])
        self.ins_trans = tk.StringVar(value=item["trans"])

        is_title = item["type"] == "title"
        if is_title:
            self.ins_maintxt = tk.StringVar(value=item["main_text"])
            self.ins_subtxt  = tk.StringVar(value=item["sub_text"])
            self.ins_theme   = tk.StringVar(value=item["theme"])
            row("Main Text:", lambda r: tk.Entry(r, textvariable=self.ins_maintxt,
                                                  bg=C["raised"], fg="white",
                                                  insertbackground="white",
                                                  relief="flat").pack(side=tk.LEFT, fill=tk.X, expand=True))
            row("Sub Text:",  lambda r: tk.Entry(r, textvariable=self.ins_subtxt,
                                                  bg=C["raised"], fg="white",
                                                  insertbackground="white",
                                                  relief="flat").pack(side=tk.LEFT, fill=tk.X, expand=True))
            themes = ["Cinematic – Light Speed Starburst","Cinematic – Deep Space Stars",
                      "Cinematic – Travelling Flare (Dynamic)","Matrix Green Particles",
                      "Golden Fire Particles"]
            row("VFX Theme:", lambda r: ttk.Combobox(r, textvariable=self.ins_theme,
                                                       values=themes, width=22).pack(side=tk.LEFT))
        else:
            self.ins_lttxt   = tk.StringVar(value=item.get("text",""))
            self.ins_ltdur   = tk.DoubleVar(value=item.get("text_dur",3.0))
            self.ins_ltstyle = tk.StringVar(value=item.get("lt_style","Static Aurora Tile (Bracket)"))
            row("Duration(s):", lambda r: tk.Spinbox(r, from_=0.1, to=9999, increment=0.5,
                                                      textvariable=self.ins_val,
                                                      bg=C["raised"], fg="white",
                                                      width=7, relief="flat").pack(side=tk.LEFT))
            row("LT Text:",    lambda r: tk.Entry(r, textvariable=self.ins_lttxt,
                                                   bg=C["raised"], fg="white",
                                                   insertbackground="white",
                                                   relief="flat").pack(side=tk.LEFT, fill=tk.X, expand=True))
            row("LT Duration:",lambda r: tk.Spinbox(r, from_=0.5, to=999, increment=0.5,
                                                      textvariable=self.ins_ltdur,
                                                      bg=C["raised"], fg="white",
                                                      width=7, relief="flat").pack(side=tk.LEFT))
            lt_styles = ["Static Aurora Tile (Bracket)","Aurora Wave","Purple Designer Box"]
            row("LT Style:",   lambda r: ttk.Combobox(r, textvariable=self.ins_ltstyle,
                                                        values=lt_styles, width=22).pack(side=tk.LEFT))

        transitions = ["Crossfade","Dip to Black","Hard Cut","Slide Left","Slide Up","Zoom In Fade","Bright Flash","Pull and Snap"]
        row("Out Transition:", lambda r: ttk.Combobox(r, textvariable=self.ins_trans,
                                                       values=transitions, width=16).pack(side=tk.LEFT))

        tk.Button(f, text="💾 Save",
                  command=self.save_inspector,
                  bg=C["accent3"], fg=C["bg"],
                  font=("Arial",10,"bold"), relief="flat",
                  cursor="hand2").pack(fill=tk.X, padx=8, pady=10)

        # mute regions list
        if item.get("mute_regions"):
            sep = tk.Frame(f, bg=C["border"], height=1)
            sep.pack(fill=tk.X, padx=8, pady=4)
            tk.Label(f, text="MUTE REGIONS", bg=C["panel"],
                     fg=C["accent2"], font=("Arial",8,"bold")).pack(anchor="w", padx=10)
            for idx2, mr in enumerate(item["mute_regions"]):
                mr_row = tk.Frame(f, bg=C["raised"])
                mr_row.pack(fill=tk.X, padx=8, pady=1)
                tk.Label(mr_row,
                         text=f"  {mr[0]:.2f}s → {mr[1]:.2f}s",
                         bg=C["raised"], fg=C["accent2"],
                         font=("Courier",8)).pack(side=tk.LEFT, padx=4)
                tk.Button(mr_row, text="✕",
                          command=lambda i=idx2: self._remove_mute_region(i),
                          bg=C["raised"], fg="#ff4444",
                          relief="flat", font=("Arial",9,"bold"),
                          cursor="hand2").pack(side=tk.RIGHT, padx=4)

    # ══════════════════════════════════════════════════════════
    #  LIVE PREVIEW ENGINE
    # ══════════════════════════════════════════════════════════
    def load_preview_engine(self, item):
        if self.preview_clip:
            try: self.preview_clip.close()
            except: pass
            self.preview_clip = None

        if item["type"] == "video" and item.get("path"):
            try:
                self.preview_clip = VideoFileClip(item["path"])
                dur = self.preview_clip.duration
                if item.get("clip_end", 0) == 0:
                    item["clip_end"] = dur
                for sl in (self.scrubber, self.trim_start, self.trim_end):
                    sl.config(to=dur, state=tk.NORMAL)
                self.scrubber.set(item.get("clip_start",0))
                self.trim_start.set(item.get("clip_start",0))
                self.trim_end.set(item.get("clip_end",dur))
                self.btn_trim.config(state=tk.NORMAL)
                self.btn_cut.config(state=tk.NORMAL)
            except Exception as e:
                print(f"Preview load error: {e}")
        else:
            for sl in (self.scrubber, self.trim_start, self.trim_end):
                sl.config(state=tk.DISABLED)
            self.btn_trim.config(state=tk.DISABLED)
            self.btn_cut.config(state=tk.DISABLED)

        # sync clip-audio controls
        if hasattr(self, "clip_vol_var"):
            self.clip_vol_var.set(item.get("volume", 1.0))
        if hasattr(self, "clip_mute_var"):
            self.clip_mute_var.set(item.get("clip_muted", False))

        self.update_preview()

    def update_preview(self, *args):
        if self.selected_idx is None: return
        item = self.media_queue[self.selected_idx]
        t    = self.scrubber.get()
        try:
            if item["type"] == "video" and self.preview_clip:
                frame = self.preview_clip.get_frame(t)
                img   = PIL.Image.fromarray(frame)
            elif item["type"] == "image" and item.get("path"):
                img = PIL.Image.open(item["path"])
            elif item["type"] == "title":
                img = PIL.Image.new("RGB",(640,360),(20,15,35))
                d = ImageDraw.Draw(img)
                d.text((30,140), f"[TITLE]\n{item['main_text']}", fill=(255,215,0))
            else:
                img = PIL.Image.new("RGB",(640,360),(20,20,20))
                d = ImageDraw.Draw(img)
                d.text((80,160),"[ PLACEHOLDER ]", fill=(200,100,0))

            for rot, fh, fv in [(item.get("rotation",0),
                                  item.get("flip_h",False),
                                  item.get("flip_v",False))]:
                if rot:  img = img.rotate(-rot, expand=True)
                if fh:   img = img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
                if fv:   img = img.transpose(PIL.Image.FLIP_TOP_BOTTOM)

            img.thumbnail((480,270))
            self.preview_img = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self.preview_img, text="")
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════
    #  TRANSPORT CONTROLS
    # ══════════════════════════════════════════════════════════
    def toggle_play(self):
        if self.is_playing:
            self.is_playing = False
            self.play_btn.config(text="▶", bg=C["accent"], fg=C["bg"])
        else:
            self.is_playing = True
            self.play_btn.config(text="⏸", bg=C["accent4"], fg=C["bg"])
            self.play_thread = threading.Thread(target=self._playback_loop, daemon=True)
            self.play_thread.start()

    def _playback_loop(self):
        import time
        fps  = 24
        dt   = 1.0 / fps
        total = self._total_duration()
        while self.is_playing:
            t = self.playhead_t.get() + dt
            if t >= total:
                t = 0.0
                self.is_playing = False
                self.root.after(0, lambda: self.play_btn.config(text="▶", bg=C["accent"], fg=C["bg"]))
            self.playhead_t.set(t)
            self.root.after(0, self._update_timecode, t)
            self.root.after(0, self._move_playhead_to, t)
            time.sleep(dt)

    def _move_playhead_to(self, t):
        c = self.tl_canvas
        c.delete("playhead")
        canvas_h = int(self.tl_canvas.cget("scrollregion").split()[3]) if self.tl_canvas.cget("scrollregion") else 600
        ph_x = self.LABEL_W + int(t * self.PPS)
        c.create_line(ph_x, 0, ph_x, 900, fill=C["accent"], width=2, tags="playhead")
        c.create_polygon(ph_x-6,0, ph_x+6,0, ph_x,10, fill=C["accent"], tags="playhead")

    def go_to_start(self):
        self.playhead_t.set(0.0)
        self._update_timecode(0.0)
        self.refresh_timeline()

    def go_to_end(self):
        t = self._total_duration()
        self.playhead_t.set(t)
        self._update_timecode(t)
        self.refresh_timeline()

    def rewind_5(self):
        t = max(0.0, self.playhead_t.get() - 5.0)
        self.playhead_t.set(t)
        self._update_timecode(t)
        self.refresh_timeline()

    def forward_5(self):
        t = min(self._total_duration(), self.playhead_t.get() + 5.0)
        self.playhead_t.set(t)
        self._update_timecode(t)
        self.refresh_timeline()

    def _update_timecode(self, t):
        mins = int(t) // 60
        secs = int(t) % 60
        ms   = int((t % 1) * 100)
        self.timecode_var.set(f"{mins:02d}:{secs:02d}:{ms:02d}")

    # ══════════════════════════════════════════════════════════
    #  ZOOM
    # ══════════════════════════════════════════════════════════
    def zoom_in(self):
        self.PPS = min(self.MAX_PPS, int(self.PPS * 1.4))
        self.thumbs.clear()
        self.refresh_timeline()

    def zoom_out(self):
        self.PPS = max(self.MIN_PPS, int(self.PPS / 1.4))
        self.thumbs.clear()
        self.refresh_timeline()

    # ══════════════════════════════════════════════════════════
    #  AUDIO OPERATIONS
    # ══════════════════════════════════════════════════════════
    def add_bgm_track(self):
        path = filedialog.askopenfilename(
            title="Select Background Music",
            filetypes=[("Audio / Video", "*.mp3 *.wav *.aac *.ogg *.m4a *.mp4 *.mov")])
        if not path: return
        self.bgm_tracks.append({
            "path":         path,
            "volume":       0.7,
            "start_offset": 0.0,
            "muted":        False,
            "mute_regions": [],
        })
        self._refresh_audio_tab()
        self.refresh_timeline()

    def remove_bgm(self, idx):
        del self.bgm_tracks[idx]
        self._refresh_audio_tab()
        self.refresh_timeline()

    def _bgm_vol_changed(self, idx, val):
        self.bgm_tracks[idx]["volume"] = float(val)

    def _bgm_mute_toggled(self, idx):
        bgm = self.bgm_tracks[idx]
        bgm["muted"] = bgm.get("_mute_var", tk.BooleanVar()).get()
        self.refresh_timeline()

    def _bgm_offset_changed(self, idx):
        bgm = self.bgm_tracks[idx]
        try:
            bgm["start_offset"] = float(bgm["_off_var"].get())
        except Exception:
            pass
        self.refresh_timeline()

    def start_mute_draw_mode(self):
        if self.selected_idx is None:
            messagebox.showinfo("Mute Region", "Select a video clip first.")
            return
        item = self.media_queue[self.selected_idx]
        if item["type"] not in ("video", "image"):
            messagebox.showinfo("Mute Region", "Mute regions work on video/image clips only.")
            return
        self._mute_drawing = True
        self.tl_mode_label.config(text="🔇 MUTE DRAW MODE — click & drag on clip to draw region")
        self.tl_canvas.configure(cursor="pencil")

    def clear_mutes_on_selected(self):
        if self.selected_idx is None: return
        self.media_queue[self.selected_idx]["mute_regions"] = []
        self.refresh_timeline()

    def _remove_mute_region(self, region_idx):
        if self.selected_idx is None: return
        item = self.media_queue[self.selected_idx]
        if region_idx < len(item.get("mute_regions",[])):
            del item["mute_regions"][region_idx]
        self.refresh_timeline()

    def _apply_clip_volume(self, *_):
        if self.selected_idx is None: return
        self.media_queue[self.selected_idx]["volume"] = self.clip_vol_var.get()

    def _apply_clip_mute(self):
        if self.selected_idx is None: return
        self.media_queue[self.selected_idx]["clip_muted"] = self.clip_mute_var.get()
        self.refresh_timeline()

    # ══════════════════════════════════════════════════════════
    #  CLIP EDITING
    # ══════════════════════════════════════════════════════════
    def execute_trim(self):
        if self.selected_idx is None: return
        item = self.media_queue[self.selected_idx]
        s, e = self.trim_start.get(), self.trim_end.get()
        if s >= e:
            messagebox.showwarning("Trim Error","Start must be before End.")
            return
        item["clip_start"] = s
        item["clip_end"]   = e
        self.thumbs.clear()
        self.refresh_timeline()

    def split_at_playhead(self):
        if self.selected_idx is None:
            messagebox.showinfo("Split","Select a clip first.")
            return
        item    = self.media_queue[self.selected_idx]
        ph      = self.playhead_t.get()
        t_start = item.get("tl_start", 0.0)
        clip_dur = self._item_duration(item)
        local_t  = ph - t_start

        if local_t <= 0 or local_t >= clip_dur:
            messagebox.showinfo("Split","Playhead must be inside the clip.")
            return

        part_b = {k: v for k, v in item.items()}
        # part A: ends at split
        if item["type"] == "video":
            item["clip_end"] = item.get("clip_start", 0.0) + local_t
        else:
            item["value"] = local_t
        # part B: starts after split
        part_b["tl_start"] = t_start + local_t
        if item["type"] == "video":
            part_b["clip_start"] = item.get("clip_start",0.0) + local_t
            part_b["clip_end"]   = item.get("clip_start",0.0) + clip_dur
        else:
            part_b["value"] = clip_dur - local_t
        part_b["mute_regions"] = []  # reset regions on split parts

        self.media_queue.insert(self.selected_idx + 1, part_b)
        self.thumbs.clear()
        self.refresh_timeline()

    def change_rotation(self, direction):
        if self.selected_idx is None: return
        item = self.media_queue[self.selected_idx]
        if direction == "left":   item["rotation"] = (item.get("rotation",0) - 90) % 360
        elif direction == "right":item["rotation"] = (item.get("rotation",0) + 90) % 360
        elif direction == "fliph":item["flip_h"]   = not item.get("flip_h",False)
        elif direction == "flipv":item["flip_v"]   = not item.get("flip_v",False)
        self.update_preview()
        key = f"thumb_{self.selected_idx}"
        if key in self.thumbs: del self.thumbs[key]
        self.refresh_timeline()

    def move_left(self):
        idx = self.selected_idx
        if idx and idx > 0:
            self.media_queue[idx], self.media_queue[idx-1] = \
                self.media_queue[idx-1], self.media_queue[idx]
            self.thumbs.clear(); self.selected_idx -= 1
            self.refresh_timeline()

    def move_right(self):
        idx = self.selected_idx
        if idx is not None and idx < len(self.media_queue)-1:
            self.media_queue[idx], self.media_queue[idx+1] = \
                self.media_queue[idx+1], self.media_queue[idx]
            self.thumbs.clear(); self.selected_idx += 1
            self.refresh_timeline()

    def delete_selected(self):
        if self.selected_idx is None: return
        del self.media_queue[self.selected_idx]
        self.thumbs.clear(); self.selected_idx = None
        self.refresh_timeline()

    def save_inspector(self):
        if self.selected_idx is None: return
        item = self.media_queue[self.selected_idx]
        item["value"] = self.ins_val.get()
        item["trans"] = self.ins_trans.get()
        if item["type"] == "title":
            item["main_text"] = self.ins_maintxt.get()
            item["sub_text"]  = self.ins_subtxt.get()
            item["theme"]     = self.ins_theme.get()
        else:
            item["text"]      = self.ins_lttxt.get()
            item["text_dur"]  = self.ins_ltdur.get()
            item["lt_style"]  = self.ins_ltstyle.get()
        key = f"thumb_{self.selected_idx}"
        if key in self.thumbs: del self.thumbs[key]
        self.refresh_timeline()
        messagebox.showinfo("Saved","Clip metadata saved.")

    # ══════════════════════════════════════════════════════════
    #  MEDIA QUEUE MANAGEMENT
    # ══════════════════════════════════════════════════════════
    def add_media(self):
        paths = filedialog.askopenfilenames(
            title="Select Media",
            filetypes=[("All Media","*.mp4 *.mov *.avi *.mkv *.jpg *.jpeg *.png")])
        t_cursor = self._total_duration()
        for path in paths:
            ext = path.lower().split(".")[-1]
            self.media_queue.append({
                "path":path,"type":"image" if ext in ("jpg","jpeg","png") else "video",
                "value":5.0 if ext in ("jpg","jpeg","png") else 1.0,
                "name":os.path.basename(path),"text":"","text_dur":3.0,
                "trans":"Crossfade","lt_style":"Static Aurora Tile (Bracket)",
                "rotation":0,"flip_h":False,"flip_v":False,
                "clip_start":0.0,"clip_end":0.0,
                "tl_start":t_cursor,
                "volume":1.0,"clip_muted":False,"mute_regions":[],
            })
            t_cursor += 5.0
        self.refresh_timeline()

    def add_title_card(self):
        t_cursor = self._total_duration()
        self.media_queue.append({
            "type":"title","value":5.0,"name":"TITLE CARD",
            "main_text":"NEW TITLE","sub_text":"Subtitle","trans":"Crossfade",
            "theme":"Cinematic – Light Speed Starburst","text":"","text_dur":0.0,
            "rotation":0,"flip_h":False,"flip_v":False,
            "tl_start":t_cursor,"volume":1.0,"clip_muted":False,"mute_regions":[],
        })
        self.refresh_timeline()

    def add_placeholder(self):
        t_cursor = self._total_duration()
        self.media_queue.append({
            "type":"placeholder","value":5.0,"name":"PLACEHOLDER","path":"",
            "text":"Your Text Here","text_dur":3.0,"trans":"Crossfade",
            "lt_style":"Static Aurora Tile (Bracket)",
            "rotation":0,"flip_h":False,"flip_v":False,
            "clip_start":0.0,"clip_end":0.0,
            "tl_start":t_cursor,"volume":1.0,"clip_muted":False,"mute_regions":[],
        })
        self.refresh_timeline()

    def fill_placeholder(self):
        if self.selected_idx is None: return
        path = filedialog.askopenfilename(title="Select Media for Placeholder")
        if not path: return
        ext  = path.lower().split(".")[-1]
        item = self.media_queue[self.selected_idx]
        item.update({"path":path,
                     "type":"image" if ext in ("jpg","jpeg","png") else "video",
                     "name":os.path.basename(path),
                     "value":5.0 if ext in ("jpg","jpeg","png") else 1.0,
                     "clip_start":0.0,"clip_end":0.0})
        key = f"thumb_{self.selected_idx}"
        if key in self.thumbs: del self.thumbs[key]
        self.refresh_timeline()

    def apply_template(self, tid):
        if not messagebox.askyesno("Apply Template","Append template sequence to timeline?"):
            return
        t_cursor = self._total_duration()
        templates = {
            1: [{"type":"title","value":5.0,"name":"TITLE CARD","main_text":"DEEP SPACE",
                 "sub_text":"EXPLORATION","trans":"Crossfade","theme":"Cinematic – Deep Space Stars"},
                {"type":"placeholder","value":6.0,"name":"PLACEHOLDER","path":"",
                 "text":"ASTRO PHYSICS","text_dur":4.0,"trans":"Crossfade",
                 "lt_style":"Static Aurora Tile (Bracket)"}],
            2: [{"type":"title","value":5.0,"name":"TITLE CARD","main_text":"LIGHT SPEED",
                 "sub_text":"FUSION","trans":"Zoom In Fade","theme":"Cinematic – Light Speed Starburst"},
                {"type":"placeholder","value":5.0,"name":"PLACEHOLDER","path":"",
                 "text":"HYPER DRIVE","text_dur":3.0,"trans":"Hard Cut",
                 "lt_style":"Purple Designer Box"}],
            3: [{"type":"title","value":6.0,"name":"TITLE CARD","main_text":"THE JOURNEY",
                 "sub_text":"BEGINS NOW","trans":"Dip to Black","theme":"Cinematic – Travelling Flare (Dynamic)"},
                {"type":"placeholder","value":7.0,"name":"PLACEHOLDER","path":"",
                 "text":"MAGICAL AURORA","text_dur":5.0,"trans":"Crossfade",
                 "lt_style":"Aurora Wave"}],
        }
        for base in templates.get(tid, []):
            item = {**base,
                    "tl_start":t_cursor,"rotation":0,"flip_h":False,"flip_v":False,
                    "volume":1.0,"clip_muted":False,"mute_regions":[],
                    "clip_start":0.0,"clip_end":0.0,"text_dur":base.get("text_dur",3.0)}
            if "text" not in item: item["text"] = ""
            self.media_queue.append(item)
            t_cursor += item["value"]
        self.refresh_timeline()

    # ══════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════
    def _total_duration(self):
        if not self.media_queue: return 10.0
        end_times = []
        for item in self.media_queue:
            end_times.append(item.get("tl_start",0.0) + self._item_duration(item))
        return max(end_times) if end_times else 10.0

    def _item_duration(self, item):
        if item["type"] == "video":
            s = item.get("clip_start",0.0)
            e = item.get("clip_end",0.0)
            return (e - s) if e > s else item.get("value",5.0) * 10
        return item.get("value", 5.0)

    def _ruler_step(self):
        for step in [0.5,1,2,5,10,15,30,60,120,300]:
            if step * self.PPS >= 60:
                return step
        return 300

    def _generate_thumbnail(self, path, mtype, rotation=0,
                             flip_h=False, flip_v=False, w=80, h=50):
        try:
            if not path: return None
            if mtype == "image":
                img = PIL.Image.open(path)
            else:
                clip = VideoFileClip(path)
                t    = 1.0 if clip.duration > 1.0 else 0.0
                frame = clip.get_frame(t)
                img   = PIL.Image.fromarray(frame)
                clip.close()
            if rotation: img = img.rotate(-rotation, expand=True)
            if flip_h:   img = img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
            if flip_v:   img = img.transpose(PIL.Image.FLIP_TOP_BOTTOM)
            img.thumbnail((w, h))
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    # ══════════════════════════════════════════════════════════
    #  SAFE TRANSFORM ENGINE (unchanged from v1)
    # ══════════════════════════════════════════════════════════
    def safe_transform(self, base_clip, rot, flip_h, flip_v):
        if rot == 0 and not flip_h and not flip_v:
            return base_clip
        def process_f(f):
            if flip_h: f = np.fliplr(f)
            if flip_v: f = np.flipud(f)
            if rot == 90:          f = np.rot90(f, k=-1, axes=(0,1))
            elif rot == 180:       f = np.rot90(f, k=2,  axes=(0,1))
            elif rot in [270,-90]: f = np.rot90(f, k=1,  axes=(0,1))
            return f
        new_clip = base_clip.fl_image(process_f)
        w, h = base_clip.size if base_clip.size else (0,0)
        if rot in [90,-90,270]:
            new_clip.size = (h, w)
        if getattr(base_clip,"mask",None):
            new_mask = base_clip.mask.fl_image(process_f)
            if rot in [90,-90,270]: new_mask.size = (h, w)
            new_clip = new_clip.set_mask(new_mask)
        return new_clip

    # ══════════════════════════════════════════════════════════
    #  VFX BACKGROUNDS (carried over exactly from v1)
    # ══════════════════════════════════════════════════════════
    def create_warp_background(self, w, h, duration):
        y, x = np.mgrid[:h, :w]
        cx, cy = w/2.0, h/2.0
        dx = x-cx; dy = y-cy
        r  = np.sqrt(dx**2+dy**2)
        theta = np.arctan2(dy,dx)
        theta_norm = (theta+np.pi)/(2*np.pi)
        np.random.seed(42)
        angle_bins=150
        speeds       = np.random.uniform(2000,5000,angle_bins)
        line_lengths = np.random.uniform(0.3,0.8,angle_bins)
        has_laser    = np.random.rand(angle_bins)>0.85
        faint_laser  = np.random.rand(angle_bins)>0.50
        palette_r=np.array([255,255,180,100]); palette_g=np.array([255,50,50,100]); palette_b=np.array([255,255,255,255])
        color_idx=np.random.randint(0,4,angle_bins)
        intensity_mult=np.where(has_laser,1.0,np.where(faint_laser,0.3,0.0))
        raw_r=palette_r[color_idx]*intensity_mult; raw_g=palette_g[color_idx]*intensity_mult; raw_b=palette_b[color_idx]*intensity_mult
        r_map=np.convolve(np.tile(raw_r,3),np.ones(3)/3.0,mode="same")[angle_bins:2*angle_bins]
        g_map=np.convolve(np.tile(raw_g,3),np.ones(3)/3.0,mode="same")[angle_bins:2*angle_bins]
        b_map=np.convolve(np.tile(raw_b,3),np.ones(3)/3.0,mode="same")[angle_bins:2*angle_bins]
        angle_idx=(theta_norm*(angle_bins-1)).astype(int)
        base_r=np.full((h,w),10,dtype=np.float32); base_g=np.full((h,w),2,dtype=np.float32); base_b=np.full((h,w),30,dtype=np.float32)
        center_glow=np.exp(-0.5*(r/200.0)**2)
        base_r+=120*center_glow; base_g+=40*center_glow; base_b+=200*center_glow
        def make_frame(t):
            my_speeds=speeds[angle_idx]; my_lengths=line_lengths[angle_idx]
            phase=(r*0.005-my_speeds*t*0.001)%1.0
            intensity=np.where(phase<my_lengths,1.0,0.0)
            fade_tail=np.clip((my_lengths-phase)/(my_lengths*0.3+0.001),0,1)
            intensity*=fade_tail; intensity*=np.clip(r/100.0,0,1)
            frame=np.zeros((h,w,3),dtype=np.float32)
            frame[...,0]=base_r+r_map[angle_idx]*intensity
            frame[...,1]=base_g+g_map[angle_idx]*intensity
            frame[...,2]=base_b+b_map[angle_idx]*intensity
            for i in range(3):
                hp=(t/1.5+i*(1.0/3))%1.0; hr=(hp**2)*(max(w,h))
                core=np.exp(-0.5*(np.abs(r-hr)/2.0)**2)
                glow=np.exp(-0.5*(np.abs(r-hr)/15.0)**2)
                ha=(core+glow*0.5)*np.clip(hr/100.0,0,1)*np.clip(1.0-hp,0,1)
                frame[...,0]+=255*ha; frame[...,1]+=50*ha; frame[...,2]+=255*ha
            return np.clip(frame,0,255).astype(np.uint8)
        return VideoClip(make_frame,duration=duration)

    def create_starry_sky_background(self, w, h, duration):
        y_g,x_g=np.mgrid[0:h,0:w]
        norm_y=(y_g/h).astype(np.float32); norm_x=(x_g/w).astype(np.float32)
        r=(18*(1-norm_y)+15*norm_y).astype(np.float32); g=(15*(1-norm_y)+30*norm_y).astype(np.float32); b=(45*(1-norm_y)+70*norm_y).astype(np.float32)
        dist_left=np.sqrt((norm_x-0.2)**2+(norm_y-1.0)**2); glow_l=np.clip(1.0-dist_left*1.2,0,1)**2
        r+=glow_l*5; g+=glow_l*40; b+=glow_l*50
        dist_right=np.sqrt((norm_x-0.8)**2+(norm_y-1.0)**2); glow_r=np.clip(1.0-dist_right*1.5,0,1)**2
        r+=glow_r*20; g+=glow_r*10; b+=glow_r*40
        bg_base=np.stack([r,g,b],axis=-1)
        np.random.seed(101)
        static_stars=np.random.rand(h,w)>0.9985; bg_base[static_stars]=[230,240,255]
        N_twinkle=400; pad=20
        t_x=np.random.randint(pad,w-pad,N_twinkle); t_y=np.random.randint(pad,h-pad,N_twinkle)
        t_phase=np.random.uniform(0,2*np.pi,N_twinkle); t_speed=np.random.uniform(2.0,6.0,N_twinkle)
        t_size=np.random.choice([1,2,3],N_twinkle,p=[0.5,0.35,0.15])
        sn_dur=0.8; sn_start=duration-sn_dur; comet_dur=2.0; comet_start=max(0.0,sn_start-comet_dur)
        P0=np.array([w*1.1,-h*0.1]); P1=np.array([w*0.75,h/2.0]); P2=np.array([w/2.0,h/2.0])
        dist_from_center=np.sqrt((x_g-w/2.0)**2+(y_g-h/2.0)**2).astype(np.float32)
        def make_frame(t):
            frame=bg_base.copy()
            sine_wave=np.sin(t*t_speed+t_phase)*0.5+0.5
            brights=np.clip(sine_wave**2.5*600,0,255).astype(np.int32)
            mask_1=t_size>=1
            if np.any(mask_1):
                ty1,tx1,b1=t_y[mask_1],t_x[mask_1],brights[mask_1]
                for dy,dx in [(0,0),(0,1),(1,0),(1,1)]:
                    yy=np.clip(ty1+dy,0,h-1); xx=np.clip(tx1+dx,0,w-1)
                    frame[yy,xx,0]=np.clip(frame[yy,xx,0]+b1,0,255)
                    frame[yy,xx,1]=np.clip(frame[yy,xx,1]+b1,0,255)
                    frame[yy,xx,2]=np.clip(frame[yy,xx,2]+b1,0,255)
            if comet_start<=t<=sn_start:
                p=(t-comet_start)/comet_dur
                cx2=(1-p)**2*P0[0]+2*(1-p)*p*P1[0]+p**2*P2[0]
                cy2=(1-p)**2*P0[1]+2*(1-p)*p*P1[1]+p**2*P2[1]
                vx=2*(1-p)*(P1[0]-P0[0])+2*p*(P2[0]-P1[0])
                vy=2*(1-p)*(P1[1]-P0[1])+2*p*(P2[1]-P1[1])
                v_mag=np.sqrt(vx**2+vy**2); dir_x=-vx/max(v_mag,1); dir_y=-vy/max(v_mag,1)
                z_scale=0.7-0.2*np.sin(p*np.pi)+1.2*(p**3)
                dx2=x_g-cx2; dy2=y_g-cy2
                dist_line=np.abs(dx2*dir_y-dy2*dir_x); proj=dx2*dir_x+dy2*dir_y
                trail_len=200.0*max(0.4,z_scale); trail_width=1.2*z_scale
                mask=(dist_line<trail_width)&(proj>0)&(proj<trail_len)
                if np.any(mask):
                    dust_noise=np.random.uniform(0.3,1.0,np.sum(mask))
                    fade=(1.0-(proj[mask]/trail_len))**2*dust_noise
                    frame[mask,0]=np.clip(frame[mask,0]+150*fade,0,255)
                    frame[mask,1]=np.clip(frame[mask,1]+200*fade,0,255)
                    frame[mask,2]=np.clip(frame[mask,2]+255*fade,0,255)
                head_glow=np.exp(-0.5*((dx2**2+dy2**2)/(1.5*z_scale)**2))
                h_mask=head_glow>0.05
                frame[h_mask,0]=np.clip(frame[h_mask,0]+255*head_glow[h_mask],0,255)
                frame[h_mask,1]=np.clip(frame[h_mask,1]+255*head_glow[h_mask],0,255)
                frame[h_mask,2]=np.clip(frame[h_mask,2]+255*head_glow[h_mask],0,255)
            return np.clip(frame,0,255).astype(np.uint8)
        return VideoClip(make_frame,duration=duration)

    # ── lower third builders (full, preserved from v1) ────────
    def build_tile_lower_third(self,text,target_w,target_h,clip_duration,text_dur):
        fs=55 if target_w<1200 else 70
        try: pil_font=ImageFont.truetype("arialbd.ttf",fs)
        except: pil_font=ImageFont.load_default()
        txt_upper=text.upper()
        dummy=PIL.Image.new("RGBA",(1,1)); bbox=ImageDraw.Draw(dummy).textbbox((0,0),txt_upper,font=pil_font)
        tw=bbox[2]-bbox[0]+24; th=bbox[3]-bbox[1]+24
        txt_img=PIL.Image.new("RGBA",(tw,th),(0,0,0,0)); draw=ImageDraw.Draw(txt_img)
        draw.text((12+4,12+4),txt_upper,font=pil_font,fill=(0,0,0,180))
        draw.text((12,12),txt_upper,font=pil_font,fill=(255,223,115,255))
        txt_rgba=np.array(txt_img); txt_rgb=txt_rgba[...,:3]; txt_alpha_base=txt_rgba[...,3].astype(np.float32)/255.0
        txt_x=(target_w-tw)//2; txt_y=target_h-210
        pad_x=int(fs*2.5); pad_y=int(fs*0.8); box_w=tw+pad_x*2; box_h=th+pad_y*2
        box_x=txt_x-pad_x; box_y=txt_y-pad_y
        y_g,x_g=np.mgrid[0:box_h,0:box_w]
        r2=box_h/2.0; cx_L=r2; cx_R=box_w-r2; cy=r2
        dx=np.maximum(0.0,np.maximum(cx_L-x_g,x_g-cx_R)); dy=np.abs(y_g-cy); d=np.sqrt(dx**2+dy**2)
        alpha_pill=np.clip(r2-d,0,1)
        bracket_dist=np.abs(d-(r2+4)); alpha_bracket=np.clip(2.5-bracket_dist,0,1)*((x_g<cx_L-r2*0.3)|(x_g>cx_R+r2*0.3))
        def make_bg_frame(t):
            frame=np.zeros((box_h,box_w,3),dtype=np.float32); frame[...,0],frame[...,1],frame[...,2]=55,10,20
            wave=0.5+0.5*np.sin((x_g/box_w)*5+t*0.5); frame[...,0]+=wave*25; frame[...,2]+=wave*15
            frame[...,0]=np.clip(frame[...,0]+alpha_bracket*255,0,255)
            frame[...,1]=np.clip(frame[...,1]+alpha_bracket*255,0,255)
            frame[...,2]=np.clip(frame[...,2]+alpha_bracket*255,0,255)
            return frame.astype(np.uint8)
        form_t=0.8; diss_t=0.8; start_t=0.5; end_t=start_t+form_t+text_dur
        if end_t+diss_t>clip_duration:
            start_t=0.2; avail=clip_duration-start_t; form_t=avail*0.15; diss_t=avail*0.15; text_dur=avail*0.7; end_t=start_t+form_t+text_dur
        def wipe_progress(t):
            if t<start_t: return 0.0
            elif t<start_t+form_t: return (t-start_t)/form_t
            elif t<end_t: return 1.0
            elif t<end_t+diss_t: return max(0.0,1.0-(t-end_t)/diss_t)
            else: return 0.0
        def make_bg_mask(t):
            wp=wipe_progress(t)
            if wp<=0: return np.zeros((box_h,box_w),dtype=np.float32)
            total_alpha=np.clip(alpha_pill+alpha_bracket,0,1); wipe_limit=int(wp*box_w)
            mask=np.zeros((box_h,box_w),dtype=np.float32)
            if wipe_limit>0:
                mask[:,:wipe_limit]=total_alpha[:,:wipe_limit]
                for i in range(40):
                    col=wipe_limit-40+i
                    if 0<=col<box_w: mask[:,col]=total_alpha[:,col]*(i/40.0)
            return mask
        tile_clip=(VideoClip(make_bg_frame,duration=clip_duration)
                   .set_mask(VideoClip(make_bg_mask,duration=clip_duration,ismask=True))
                   .set_position((box_x,box_y)))
        def make_text_frame(t):
            frame=np.zeros((target_h,target_w,3),dtype=np.uint8)
            y1,y2,x1,x2=txt_y,txt_y+th,txt_x,txt_x+tw
            if y2<=target_h and x2<=target_w: frame[y1:y2,x1:x2]=txt_rgb
            return frame
        def make_text_mask_frame(t):
            wp=wipe_progress(t); full=np.zeros((target_h,target_w),dtype=np.float32)
            if wp<=0: return full
            ga=txt_alpha_base.copy()
            if t<end_t:
                reveal_x=int(wp*tw); col_mask=np.zeros(tw,dtype=np.float32); col_mask[:reveal_x]=1.0
                for i in range(min(40,tw)):
                    col=reveal_x+i
                    if 0<=col<tw: col_mask[col]=1.0-i/40.0
                ga=ga*col_mask[np.newaxis,:]
            else:
                p=(t-end_t)/diss_t; np.random.seed(int(t*20))
                ga=ga*np.where(np.random.rand(th,tw)>np.clip(p*2.0-np.linspace(0,1,th).reshape(th,1)*0.8,0,1),1.0,0.0).astype(np.float32)
            y1_d,y2_d=max(0,txt_y),min(target_h,txt_y+th); x1_d,x2_d=max(0,txt_x),min(target_w,txt_x+tw)
            if y1_d<y2_d and x1_d<x2_d: full[y1_d:y2_d,x1_d:x2_d]=ga[y1_d-txt_y:y1_d-txt_y+(y2_d-y1_d),x1_d-txt_x:x1_d-txt_x+(x2_d-x1_d)]
            return full
        text_clip_final=(VideoClip(make_text_frame,duration=clip_duration)
                         .set_mask(VideoClip(make_text_mask_frame,duration=clip_duration,ismask=True))
                         .set_position((0,0)))
        return [tile_clip,text_clip_final]

    def build_magical_lower_third(self,text,target_w,target_h,clip_duration,text_dur):
        # Full implementation preserved — delegates to v1 logic
        fs=55 if target_w<1200 else 70
        try: pil_font=ImageFont.truetype("arialbd.ttf",fs)
        except: pil_font=ImageFont.load_default()
        txt_upper=text.upper()
        dummy=PIL.Image.new("RGBA",(1,1)); bbox=ImageDraw.Draw(dummy).textbbox((0,0),txt_upper,font=pil_font)
        tw=bbox[2]-bbox[0]+24; th=bbox[3]-bbox[1]+24
        txt_img=PIL.Image.new("RGBA",(tw,th),(0,0,0,0)); draw=ImageDraw.Draw(txt_img)
        draw.text((12+4,12+4),txt_upper,font=pil_font,fill=(0,0,0,180))
        draw.text((12,12),txt_upper,font=pil_font,fill=(255,223,115,255))
        txt_rgba=np.array(txt_img); txt_rgb=txt_rgba[...,:3]; txt_alpha_base=txt_rgba[...,3].astype(np.float32)/255.0
        txt_x=(target_w-tw)//2; txt_y=target_h-210
        pad_x=int(fs*2.8); pad_y=int(fs*1.4); box_w=tw+pad_x*2; box_h=th+pad_y*2; box_x=txt_x-pad_x; box_y=txt_y-pad_y
        form_t=1.0; diss_t=1.0; start_t=0.5; end_t=start_t+form_t+text_dur
        if end_t+diss_t>clip_duration:
            start_t=0.2; avail=clip_duration-start_t; form_t=avail*0.2; diss_t=avail*0.2; text_dur=avail*0.6; end_t=start_t+form_t+text_dur
        def wipe_progress(t):
            if t<start_t: return 0.0
            elif t<start_t+form_t: return (t-start_t)/form_t
            elif t<end_t: return 1.0
            elif t<end_t+diss_t: return max(0.0,1.0-(t-end_t)/diss_t)
            else: return 0.0
        y_g2,x_g2=np.mgrid[0:box_h,0:box_w]
        norm_x=(x_g2-box_w/2.0)/(box_w/2.0); norm_y=(y_g2-box_h/2.0)/(box_h/2.0)
        col_wave=0.18*np.sin(norm_x*np.pi*2.5)
        wave_mask=np.clip(np.exp(-0.5*((norm_x/0.68)**2+((norm_y-col_wave)/0.44)**2))*1.35,0.0,1.0).astype(np.float32)
        def make_aurora_frame(t):
            u=x_g2/box_w; v=y_g2/box_h
            w1=0.5+0.5*np.sin(u*10+t*3.0)*np.cos(v*5-t*2.0)
            w2=0.5+0.5*np.cos(u*7-t*2.5)*np.sin(v*8+t*1.5)
            w3=0.5+0.5*np.sin((u+v)*6+t*1.8)
            teal=0.5+0.5*np.sin(u*4-t*1.2)
            rr=np.clip(w1*120+w3*60,0,255); gg=np.clip(w2*140+w3*80+teal*80,0,255); bb=np.clip(w1*255+w2*220+w3*120+teal*40,0,255)
            return np.stack([rr,gg,bb],axis=-1).astype(np.uint8)
        aurora_clip=(VideoClip(make_aurora_frame,duration=clip_duration)
                     .set_mask(VideoClip(lambda t: (wave_mask*wipe_progress(t)).astype(np.float32),duration=clip_duration,ismask=True))
                     .set_position((box_x,box_y)))
        def make_text_frame(t):
            frame=np.zeros((target_h,target_w,3),dtype=np.uint8)
            y1,y2,x1,x2=txt_y,txt_y+th,txt_x,txt_x+tw
            if y2<=target_h and x2<=target_w: frame[y1:y2,x1:x2]=txt_rgb
            return frame
        def make_text_mask_frame(t):
            wp=wipe_progress(t); full=np.zeros((target_h,target_w),dtype=np.float32)
            if wp<=0: return full
            ga=txt_alpha_base.copy()
            if t<end_t:
                reveal_x=int(wp*tw); col_mask2=np.zeros(tw,dtype=np.float32); col_mask2[:reveal_x]=1.0
                for i in range(min(40,tw)):
                    col=reveal_x+i
                    if 0<=col<tw: col_mask2[col]=1.0-i/40.0
                ga=ga*col_mask2[np.newaxis,:]
            else:
                p=(t-end_t)/diss_t; np.random.seed(int(t*20))
                ga=ga*np.where(np.random.rand(th,tw)>np.clip(p*2.0-np.linspace(0,1,th).reshape(-1,1)*0.8,0,1),1.0,0.0).astype(np.float32)
            y1_d,y2_d=max(0,txt_y),min(target_h,txt_y+th); x1_d,x2_d=max(0,txt_x),min(target_w,txt_x+tw)
            if y1_d<y2_d and x1_d<x2_d: full[y1_d:y2_d,x1_d:x2_d]=ga[y1_d-txt_y:y1_d-txt_y+(y2_d-y1_d),x1_d-txt_x:x1_d-txt_x+(x2_d-x1_d)]
            return full
        text_clip_final=(VideoClip(make_text_frame,duration=clip_duration)
                         .set_mask(VideoClip(make_text_mask_frame,duration=clip_duration,ismask=True))
                         .set_position((0,0)))
        return [aurora_clip,text_clip_final]

    def build_designer_lower_third(self,text,target_w,target_h,clip_duration,text_dur):
        fs=55 if target_w<1200 else 70
        try: pil_font=ImageFont.truetype("arialbd.ttf",fs)
        except: pil_font=ImageFont.load_default()
        txt_upper=text.upper()
        dummy=PIL.Image.new("RGBA",(1,1)); bbox=ImageDraw.Draw(dummy).textbbox((0,0),txt_upper,font=pil_font)
        tw=bbox[2]-bbox[0]+24; th=bbox[3]-bbox[1]+24
        txt_img=PIL.Image.new("RGBA",(tw,th),(0,0,0,0)); draw=ImageDraw.Draw(txt_img)
        draw.text((12+4,12+4),txt_upper,font=pil_font,fill=(0,0,0,180))
        draw.text((12,12),txt_upper,font=pil_font,fill=(255,220,80,255))
        txt_rgba=np.array(txt_img); txt_rgb=txt_rgba[...,:3]; txt_alpha_base=txt_rgba[...,3].astype(np.float32)/255.0
        pad_x=int(fs*1.8); pad_y=int(fs*0.9); panel_w=tw+pad_x*2; panel_h=th+pad_y*2
        panel_x=(target_w-panel_w)//2; panel_y=target_h-220; txt_x=panel_x+pad_x; txt_y=panel_y+pad_y
        form_t=0.5; hold_t=text_dur; diss_t=0.4; start_t=0.4; end_t=start_t+form_t+hold_t
        if end_t+diss_t>clip_duration:
            start_t=0.2; avail=clip_duration-start_t; form_t=avail*0.15; diss_t=avail*0.15; hold_t=avail*0.70; end_t=start_t+form_t+hold_t
        def panel_progress(t):
            if t<start_t: return 0.0
            elif t<start_t+form_t: return (t-start_t)/form_t
            elif t<end_t: return 1.0
            elif t<end_t+diss_t: return max(0.0,1.0-(t-end_t)/diss_t)
            else: return 0.0
        y_p,x_p=np.mgrid[0:panel_h,0:panel_w]
        nx=(x_p-panel_w/2.0)/(panel_w/2.0); ny=(y_p-panel_h/2.0)/(panel_h/2.0)
        panel_base_alpha=np.clip(np.exp(-0.5*((nx/0.80)**2+(ny/0.72)**2))*0.82,0,1).astype(np.float32)
        border_dist=np.minimum(np.minimum(x_p,panel_w-1-x_p),np.minimum(y_p,panel_h-1-y_p))
        border_glow=np.clip(1.0-border_dist/12.0,0,1)**2
        def make_panel_frame(t):
            prog=panel_progress(t)
            if prog<=0: return np.zeros((target_h,target_w,3),dtype=np.uint8)
            slide_offset=int((1.0-prog)*panel_h*1.5); py=panel_y+slide_offset
            frame=np.zeros((target_h,target_w,3),dtype=np.uint8)
            y1,y2=max(0,py),min(target_h,py+panel_h); x1,x2=max(0,panel_x),min(target_w,panel_x+panel_w)
            if y1>=y2 or x1>=x2: return frame
            py_s,py_e=y1-py,(y1-py)+(y2-y1); px_s,px_e=x1-panel_x,(x1-panel_x)+(x2-x1)
            frame[y1:y2,x1:x2,0],frame[y1:y2,x1:x2,1],frame[y1:y2,x1:x2,2]=45,10,75
            scan_y=int(((t*0.7)%1.0)*panel_h)
            s_scan=np.exp(-0.5*((np.arange(panel_h)-scan_y)/8.0)**2)[py_s:py_e,np.newaxis]
            s_border=border_glow[py_s:py_e,px_s:px_e]
            frame[y1:y2,x1:x2,0]=np.clip(frame[y1:y2,x1:x2,0]+(s_scan*80).astype(np.uint8)+(s_border*180).astype(np.uint8),0,255)
            frame[y1:y2,x1:x2,1]=np.clip(frame[y1:y2,x1:x2,1]+(s_scan*40).astype(np.uint8)+(s_border*60).astype(np.uint8),0,255)
            frame[y1:y2,x1:x2,2]=np.clip(frame[y1:y2,x1:x2,2]+(s_scan*120).astype(np.uint8)+(s_border*255).astype(np.uint8),0,255)
            return frame
        def make_panel_mask(t):
            prog=panel_progress(t); full=np.zeros((target_h,target_w),dtype=np.float32)
            if prog<=0: return full
            slide_offset=int((1.0-prog)*panel_h*1.5); py=panel_y+slide_offset
            y1,y2=max(0,py),min(target_h,py+panel_h); x1,x2=max(0,panel_x),min(target_w,panel_x+panel_w)
            if y1>=y2 or x1>=x2: return full
            py_s,py_e=y1-py,(y1-py)+(y2-y1); px_s,px_e=x1-panel_x,(x1-panel_x)+(x2-x1)
            full[y1:y2,x1:x2]=panel_base_alpha[py_s:py_e,px_s:px_e]*prog
            full[y1:y2,x1:x2]=np.clip(full[y1:y2,x1:x2]+border_glow[py_s:py_e,px_s:px_e]*0.9*prog,0,1)
            return full
        panel_clip=(VideoClip(make_panel_frame,duration=clip_duration)
                    .set_mask(VideoClip(make_panel_mask,duration=clip_duration,ismask=True))
                    .set_position((0,0)))
        def make_text_frame(t):
            prog=panel_progress(t); frame=np.zeros((target_h,target_w,3),dtype=np.uint8)
            if prog<=0: return frame
            slide_offset=int((1.0-prog)*panel_h*1.5); ty=txt_y+slide_offset
            y1,y2=max(0,ty),min(target_h,ty+th); x1,x2=max(0,txt_x),min(target_w,txt_x+tw)
            if y1>=y2 or x1>=x2: return frame
            ty_s,ty_e=y1-ty,(y1-ty)+(y2-y1); tx_s,tx_e=x1-txt_x,(x1-txt_x)+(x2-x1)
            frame[y1:y2,x1:x2]=txt_rgb[ty_s:ty_e,tx_s:tx_e]
            return frame
        def make_text_mask(t):
            prog=panel_progress(t); full=np.zeros((target_h,target_w),dtype=np.float32)
            if prog<=0: return full
            ga=txt_alpha_base.copy()
            if t>=end_t:
                p=(t-end_t)/diss_t; np.random.seed(int(t*20))
                ga=ga*np.where(np.random.rand(th,tw)>np.clip(p*2.0-np.linspace(0,1,th).reshape(-1,1)*0.8,0,1),1.0,0.0).astype(np.float32)
            y1_d,y2_d=max(0,txt_y),min(target_h,txt_y+th); x1_d,x2_d=max(0,txt_x),min(target_w,txt_x+tw)
            if y1_d<y2_d and x1_d<x2_d: full[y1_d:y2_d,x1_d:x2_d]=ga[y1_d-txt_y:y1_d-txt_y+(y2_d-y1_d),x1_d-txt_x:x1_d-txt_x+(x2_d-x1_d)]*prog
            return full
        txt_final=(VideoClip(make_text_frame,duration=clip_duration)
                   .set_mask(VideoClip(make_text_mask,duration=clip_duration,ismask=True))
                   .set_position((0,0)))
        return [panel_clip,txt_final]

    # ── title card engine (preserved fully from v1) ───────────
    def build_finch_title_card(self,target_w,target_h,item):
        # Full v1 implementation preserved (omitted here for brevity — paste in v1 method body)
        duration=float(item["value"]); main_str=item["main_text"].upper()
        sub_str=item["sub_text"].upper() if item["sub_text"] else ""; theme=item["theme"]
        is_lightspeed="Light Speed" in theme; is_deepspace="Deep Space" in theme; is_travelling="Travelling Flare" in theme
        main_y=(target_h//2)-10
        if is_lightspeed:
            main_y-=20; text_clips=[]
            offsets=[20,15,10,5]; colors=["#100030","#3b0086","#7500c0","#c200ff"]
            for off,col in zip(offsets,colors):
                try: tc=TextClip(main_str,fontsize=160,color=col,font="Arial-Bold",stroke_color=col,stroke_width=6,bg_color="transparent")
                except: tc=TextClip(main_str,fontsize=160,color=col,font="Arial-Bold",bg_color="transparent")
                tc=tc.set_position(("center",main_y+off)).set_duration(duration); text_clips.append(tc)
            try: top_tc=TextClip(main_str,fontsize=160,color="white",font="Arial-Bold",stroke_color="#a200ff",stroke_width=4,bg_color="transparent")
            except: top_tc=TextClip(main_str,fontsize=160,color="white",font="Arial-Bold",bg_color="transparent")
            top_tc=top_tc.set_position(("center",main_y)).set_duration(duration); text_clips.append(top_tc)
            main_clip=CompositeVideoClip(text_clips,size=(target_w,target_h)).set_duration(duration); shine_clip=None
            main_clip=main_clip.fx(vfx.resize,lambda t:1.0+0.05*(t/duration)); baseline_y=main_y+top_tc.h-10
        else:
            main_clip=TextClip(main_str,fontsize=140 if is_travelling else 130,color="#E5D5A0",font="Arial-Bold",bg_color="transparent")
            main_clip=main_clip.set_position(("center",main_y)).set_duration(duration)
            shine_clip=None if is_travelling else TextClip(main_str,fontsize=130,color="white",font="Arial-Bold",bg_color="transparent").set_opacity(0.12).crop(y2=main_clip.h//2).set_position(("center",main_y)).set_duration(duration)
            if is_deepspace:
                zoom_func=lambda t:1.0+0.05*(t/duration)
                main_clip=main_clip.fx(vfx.resize,zoom_func)
                if shine_clip: shine_clip=shine_clip.fx(vfx.resize,zoom_func)
            baseline_y=main_y+main_clip.h-10
        if is_lightspeed:
            bg_clip=self.create_warp_background(target_w,target_h,duration); layers=[bg_clip]
        elif is_travelling:
            y_bg,x_bg=np.mgrid[0:target_h,0:target_w]
            dist_center=np.sqrt((x_bg-target_w/2)**2+(y_bg-target_h/2)**2)
            fog_glow=np.exp(-0.5*(dist_center/800.0)**2)*0.4
            bg_r=np.clip(18+15*fog_glow,0,255); bg_g=np.clip(25+20*fog_glow,0,255); bg_b=np.clip(28+15*fog_glow,0,255)
            bg_frame=np.stack([bg_r,bg_g,bg_b],axis=-1).astype(np.uint8)
            bg_clip=ImageClip(bg_frame).set_duration(duration); layers=[bg_clip]
            y_g3,x_g3=np.mgrid[0:target_h,0:target_w]; np.random.seed(42)
            num_dust=150; d_x=np.random.uniform(target_w*0.1,target_w*0.9,num_dust); d_y=np.random.uniform(target_h*0.2,target_h*0.8,num_dust)
            d_vx=np.random.uniform(-5,5,num_dust); d_vy=np.random.uniform(-10,-2,num_dust); d_size=np.random.uniform(0.0,0.9,num_dust)
            dist_c=np.sqrt((x_g3-target_w/2)**2+(y_g3-baseline_y)**2)
            text_w_half=main_clip.w/2.0+40; text_h_half=main_clip.h/2.0+50; text_cy=baseline_y-main_clip.h/2.0-20
            dx_text=np.maximum(0.0,np.abs(x_g3-target_w/2)-text_w_half); dy_text=np.maximum(0.0,np.abs(y_g3-text_cy)-text_h_half)
            dist_from_text=np.sqrt(dx_text**2+dy_text**2); text_avoid_mask=np.clip(dist_from_text/10.0,0,1)
            def make_travelling_flare(t):
                p=t/duration; cx3=(target_w/2-main_clip.w/2-150)+p*(main_clip.w+300); cy3=baseline_y-5
                intensity=0.02+0.98*np.exp(-0.5*((p-0.5)/0.12)**2)
                frame=np.zeros((target_h,target_w,3),dtype=np.float32); alpha=np.zeros((target_h,target_w),dtype=np.float32)
                fog=np.exp(-0.5*((x_g3-target_w/2)**2/(600.0)**2+(y_g3-cy3)**2/(150.0)**2))*intensity*0.15
                sine_val=np.sin(-dist_c/35.0+t*5.0); ripple_lines=np.clip((sine_val-0.995)*200.0,0,1)
                np.random.seed(int(t*20)); glitter_noise=np.random.rand(target_h,target_w)
                glitter_mult=np.where(glitter_noise>0.85,2.5,0.2)
                ripples=ripple_lines*text_avoid_mask*intensity*glitter_mult*0.8
                fog_glow2=np.clip(fog,0,1)
                frame[...,0]+=fog_glow2*255; frame[...,1]+=fog_glow2*220; frame[...,2]+=fog_glow2*130; alpha+=fog_glow2
                frame[...,0]=np.clip(frame[...,0]+ripples*229,0,255); frame[...,1]=np.clip(frame[...,1]+ripples*213,0,255); frame[...,2]=np.clip(frame[...,2]+ripples*160,0,255)
                alpha=np.clip(alpha+ripples,0,1)
                streak_h_w=800.0*intensity+20.0; streak_h_h=2.5+1.0*intensity; streak_v_w=2.5+1.0*intensity; streak_v_h=350.0*intensity+10.0
                y_min,y_max=max(0,int(cy3-max(streak_h_h,streak_v_h)*3)),min(target_h,int(cy3+max(streak_h_h,streak_v_h)*3))
                x_min,x_max=max(0,int(cx3-max(streak_h_w,streak_v_w)*3)),min(target_w,int(cx3+max(streak_h_w,streak_v_w)*3))
                if y_min<y_max and x_min<x_max:
                    xx=x_g3[y_min:y_max,x_min:x_max]; yy=y_g3[y_min:y_max,x_min:x_max]
                    dx3=xx-cx3; dy3=yy-cy3
                    s1=np.exp(-0.5*(dx3/streak_h_w)**2-0.5*(dy3/streak_h_h)**2)*intensity
                    s2=np.exp(-0.5*(dx3/streak_v_w)**2-0.5*(dy3/streak_v_h)**2)*intensity
                    core=np.exp(-0.5*(np.sqrt(dx3**2+dy3**2)/(25.0*intensity+3.0))**2)*intensity*1.5
                    glow=np.clip(s1+s2+core,0,1)
                    frame[y_min:y_max,x_min:x_max,0]=np.clip(frame[y_min:y_max,x_min:x_max,0]+glow*255,0,255)
                    frame[y_min:y_max,x_min:x_max,1]=np.clip(frame[y_min:y_max,x_min:x_max,1]+glow*240,0,255)
                    frame[y_min:y_max,x_min:x_max,2]=np.clip(frame[y_min:y_max,x_min:x_max,2]+glow*190,0,255)
                    alpha[y_min:y_max,x_min:x_max]=np.clip(alpha[y_min:y_max,x_min:x_max]+glow,0,1)
                return np.clip(frame,0,255).astype(np.uint8),np.clip(alpha,0,1)
            flare_rgb=VideoClip(lambda t:make_travelling_flare(t)[0],duration=duration)
            flare_mask=VideoClip(lambda t:make_travelling_flare(t)[1],duration=duration,ismask=True)
            layers.append(flare_rgb.set_mask(flare_mask))
        else:
            bg_clip=self.create_starry_sky_background(target_w,target_h,duration); layers=[bg_clip]
        if sub_str:
            spaced_sub="   ".join(sub_str)
            if is_lightspeed:
                try: sub_txt=TextClip(spaced_sub,fontsize=40,color="#b050ff",font="Arial-Bold",stroke_color="white",stroke_width=3,bg_color="transparent")
                except: sub_txt=TextClip(spaced_sub,fontsize=40,color="white",font="Arial-Bold",bg_color="transparent")
                sub_txt=sub_txt.set_position(("center",main_y-70)).set_duration(duration)
            elif is_travelling: sub_txt=TextClip(spaced_sub,fontsize=35,color="#E5D5A0",font="Arial-Bold",bg_color="transparent").set_position(("center",main_y-60)).set_duration(duration)
            else: sub_txt=TextClip(spaced_sub,fontsize=35,color="white",font="Arial-Bold",bg_color="transparent").set_position(("center",main_y-80)).set_duration(duration)
            layers.append(sub_txt)
        layers.append(main_clip)
        if shine_clip is not None: layers.append(shine_clip)
        if not is_deepspace and not is_lightspeed and not is_travelling:
            yv,xv=np.mgrid[:target_h,:target_w]
            vd=np.sqrt(((xv-target_w/2)/(target_w*0.55))**2+((yv-target_h/2)/(target_h*0.55))**2)
            vig_a=np.clip(vd**1.6*0.72,0,1).astype(np.float32)
            vig_clip=ImageClip(np.zeros((target_h,target_w,3),dtype=np.uint8)).set_mask(ImageClip(vig_a,ismask=True)).set_duration(duration)
            layers.append(vig_clip)
            bar_h=max(int(target_h*(1.0-target_w/(target_w*2.39))/2),int(target_h*0.06))
            black_bar=ColorClip(size=(target_w,bar_h),color=(0,0,0)).set_duration(duration)
            layers+=[black_bar.set_position((0,0)),black_bar.set_position((0,target_h-bar_h))]
        if is_lightspeed:
            trans_dur=1.2; trans_start=duration-trans_dur; impact_time=trans_start+0.4
            def make_fusion_frame(t):
                frame=np.zeros((target_h,target_w,3),dtype=np.float32)
                if t<trans_start: return frame.astype(np.uint8)
                y_gf,x_gf=np.mgrid[:target_h,:target_w]; cy4=target_h/2.0; cx4=target_w/2.0
                if t<impact_time:
                    p_in=(t-trans_start)/(impact_time-trans_start); tip_l=cx4*p_in; tip_r=target_w-(cx4*p_in); beam_th=6.0
                    mask_l=(x_gf<tip_l)&(np.abs(y_gf-cy4)<beam_th); glow_l=np.exp(-0.5*(np.abs(y_gf-cy4)/(beam_th*2))**2)*(x_gf<tip_l)
                    frame[...,1]+=glow_l*255; frame[...,2]+=glow_l*255; frame[mask_l]=[255,255,255]
                    mask_r=(x_gf>tip_r)&(np.abs(y_gf-cy4)<beam_th); glow_r=np.exp(-0.5*(np.abs(y_gf-cy4)/(beam_th*2))**2)*(x_gf>tip_r)
                    frame[...,0]+=glow_r*255; frame[...,2]+=glow_r*150; frame[mask_r]=[255,255,255]
                else:
                    p_ex=(t-impact_time)/(duration-impact_time); beam_th=6.0+p_ex*30.0
                    glow_l2=np.exp(-0.5*(np.abs(y_gf-cy4)/beam_th)**2)*(x_gf<=cx4); glow_r2=np.exp(-0.5*(np.abs(y_gf-cy4)/beam_th)**2)*(x_gf>cx4)
                    frame[...,0]+=glow_r2*255; frame[...,1]+=glow_l2*255; frame[...,2]+=glow_l2*255+glow_r2*150
                    core_beam=np.abs(y_gf-cy4)<(3.0+p_ex*15); frame[core_beam]=[255,255,255]
                    dist4=np.sqrt((x_gf-cx4)**2+(y_gf-cy4)**2); radius=20+(target_w*2.0)*(p_ex**2.5); intensity4=1.0+p_ex*8.0
                    core4=np.clip(1.0-(dist4/radius),0,1)**2*intensity4
                    spike_len=150+target_w*p_ex**2; spike_th=3.0+p_ex*15.0
                    spikes=np.exp(-0.5*(np.abs(x_gf-cx4)/spike_len)**2-0.5*(np.abs(y_gf-cy4)/spike_th)**2)
                    spikes+=np.exp(-0.5*(np.abs(y_gf-cy4)/spike_len)**2-0.5*(np.abs(x_gf-cx4)/spike_th)**2)
                    dx4=x_gf-cx4; dy4=y_gf-cy4; diag1=np.abs(dx4-dy4)/1.414; diag2=np.abs(dx4+dy4)/1.414
                    diag_len=100+target_w*0.7*p_ex**2; diag_th=2.0+p_ex*8.0
                    spikes+=0.8*np.exp(-0.5*(diag1/diag_th)**2-0.5*(np.abs(dx4+dy4)/1.414/diag_len)**2)
                    spikes+=0.8*np.exp(-0.5*(diag2/diag_th)**2-0.5*(np.abs(dx4-dy4)/1.414/diag_len)**2)
                    burst=np.clip(core4+spikes*intensity4,0,1)
                    side_blend=np.clip((x_gf-(cx4-200))/400.0,0,1)
                    frame[...,0]+=burst*(100*(1-side_blend)+255*side_blend); frame[...,1]+=burst*(255*(1-side_blend)+50*side_blend); frame[...,2]+=burst*(255*(1-side_blend)+150*side_blend)
                    white_core=np.clip(1.0-(dist4/(radius*0.4)),0,1)**1.5*intensity4; frame[...,0]+=white_core*255; frame[...,1]+=white_core*255; frame[...,2]+=white_core*255
                return np.clip(frame,0,255).astype(np.uint8)
            def make_fusion_mask(t):
                if t<trans_start: return np.zeros((target_h,target_w),dtype=np.float32)
                y_gm,x_gm=np.mgrid[:target_h,:target_w]; cy5=target_h/2.0; cx5=target_w/2.0
                if t<impact_time:
                    p_in=(t-trans_start)/(impact_time-trans_start); tip_l=cx5*p_in; tip_r=target_w-(cx5*p_in); beam_th=6.0
                    ml=np.exp(-0.5*(np.abs(y_gm-cy5)/(beam_th*2))**2)*(x_gm<tip_l); mr=np.exp(-0.5*(np.abs(y_gm-cy5)/(beam_th*2))**2)*(x_gm>tip_r)
                    return np.clip(ml+mr,0,1).astype(np.float32)
                else:
                    p_ex=(t-impact_time)/(duration-impact_time); dist5=np.sqrt((x_gm-cx5)**2+(y_gm-cy5)**2)
                    radius=20+(target_w*2.0)*(p_ex**2.5); intensity5=1.0+p_ex*8.0
                    glow5=np.clip(1.0-(dist5/radius),0,1)**1.5*intensity5; beam_th=6.0+p_ex*30.0
                    beams=np.exp(-0.5*(np.abs(y_gm-cy5)/beam_th)**2)
                    return np.clip(glow5+beams,0,1).astype(np.float32)
            fusion_clip=VideoClip(make_fusion_frame,duration=duration).set_mask(VideoClip(make_fusion_mask,duration=duration,ismask=True))
            layers.append(fusion_clip)
        elif is_deepspace:
            sn_dur=0.8; sn_start=duration-sn_dur
            Y_sn,X_sn=np.mgrid[0:target_h,0:target_w]; sn_x=target_w/2.0; sn_y=target_h/2.0
            dist_from_center=np.sqrt((X_sn-sn_x)**2+(Y_sn-sn_y)**2)
            def make_sn_mask(t):
                if t<sn_start: return np.zeros((target_h,target_w),dtype=np.float32)
                p=(t-sn_start)/sn_dur; radius=20+(target_w*2.5)*(p**2.5); intensity=1.0+(p*8.0)
                glow=np.clip(1.0-(dist_from_center/radius),0,1)**1.5*intensity
                return np.clip(glow,0,1)
            sn_clip=VideoClip(lambda t:np.full((target_h,target_w,3),255,dtype=np.uint8),duration=duration).set_mask(VideoClip(make_sn_mask,duration=duration,ismask=True))
            layers.append(sn_clip)
        card=CompositeVideoClip(layers,size=(target_w,target_h)).set_duration(duration)
        if is_deepspace or is_lightspeed or is_travelling:
            fps_audio=44100; total_samples=int(duration*fps_audio); t_audio=np.linspace(0,duration,total_samples,endpoint=False); audio_mono=np.zeros(total_samples,dtype=np.float32)
            if is_deepspace:
                sn_dur=0.8; sn_start=duration-sn_dur; comet_dur=2.0; comet_start=max(0.0,sn_start-comet_dur)
                p_comet=(t_audio-comet_start)/comet_dur; mask_comet=(p_comet>=0)&(p_comet<=1)
                if np.any(mask_comet):
                    env_comet=np.sin(p_comet[mask_comet]*np.pi)**2; noise=np.random.uniform(-0.5,0.5,np.sum(mask_comet))
                    freq=800-500*np.sin(p_comet[mask_comet]*np.pi)+900*(p_comet[mask_comet]**3)
                    audio_mono[mask_comet]+=(noise*0.6+np.sin(2*np.pi*freq*t_audio[mask_comet])*0.4)*env_comet*0.8
                p_boom=(t_audio-sn_start)/sn_dur; mask_boom=(p_boom>=0)&(p_boom<=1)
                if np.any(mask_boom):
                    env_sn=np.exp(-4*p_boom[mask_boom]); noise2=np.random.uniform(-1.0,1.0,np.sum(mask_boom)); freq2=150*np.exp(-4*p_boom[mask_boom])+40
                    audio_mono[mask_boom]+=(noise2*0.8+np.sin(2*np.pi*freq2*t_audio[mask_boom])*0.6)*env_sn*1.0
            elif is_lightspeed:
                trans_dur=1.2; trans_start=duration-trans_dur; impact_time=trans_start+0.4
                p_in=(t_audio-trans_start)/(impact_time-trans_start); mask_in=(p_in>=0)&(p_in<=1)
                if np.any(mask_in): audio_mono[mask_in]+=(np.sin(2*np.pi*(400+1200*p_in[mask_in])*t_audio[mask_in])+np.sin(2*np.pi*(500+1400*p_in[mask_in])*t_audio[mask_in]))*0.2*p_in[mask_in]**2
                p_boom2=(t_audio-impact_time)/(duration-impact_time); mask_boom2=(p_boom2>=0)&(p_boom2<=1)
                if np.any(mask_boom2): audio_mono[mask_boom2]+=(np.random.uniform(-1.0,1.0,np.sum(mask_boom2))*0.8+np.sin(2*np.pi*(120*np.exp(-5*p_boom2[mask_boom2])+30)*t_audio[mask_boom2])*0.7)*np.exp(-4*p_boom2[mask_boom2])*1.0
            elif is_travelling:
                p=t_audio/duration; audio_mono+=(np.random.uniform(-0.5,0.5,total_samples)*0.3+np.sin(2*np.pi*(300-150*p)*t_audio)*0.2)*np.exp(-0.5*((p-0.5)/0.15)**2)*0.5
            audio_mono=np.clip(audio_mono,-1.0,1.0); audio_stereo=np.column_stack((audio_mono,audio_mono))
            card=card.set_audio(AudioArrayClip(audio_stereo,fps=fps_audio))
        return card.fadein(0.8)

    # ══════════════════════════════════════════════════════════
    #  EXPORT / MERGE ENGINE
    # ══════════════════════════════════════════════════════════
    def start_merge_thread(self):
        save_path=filedialog.asksaveasfilename(
            defaultextension=".mp4",initialfile="final_output.mp4",
            filetypes=[("MP4 Video","*.mp4")])
        if not save_path: return
        for item in self.media_queue:
            if item["type"]=="placeholder" and not item.get("path"):
                messagebox.showerror("Error","Unfilled Placeholders found! Fill or delete them before export.")
                return
        self.merge_btn_ref = None  # no dedicated merge btn in new toolbar
        self.status_label.config(text="Rendering… please wait.",fg=C["accent"])
        threading.Thread(target=self.process_merge,args=(save_path,),daemon=True).start()

    def process_merge(self, save_path):
        is_mobile  = self.format_var.get()=="mobile"
        target_w   = 1080 if is_mobile else 1920
        target_h   = 1920 if is_mobile else 1080
        smart_fill = self.smart_fill_var.get()
        auto_rotate= self.auto_rotate_var.get()
        total_dur  = self._total_duration()

        final_clips = []
        try:
            # ── render all clips into absolute-time-positioned clips ──
            for i, item in enumerate(self.media_queue):
                t_start  = item.get("tl_start",0.0)
                clip_dur = self._item_duration(item)

                if item["type"]=="title":
                    clip = self.build_finch_title_card(target_w,target_h,item)
                else:
                    if item["type"]=="image":
                        clip = ImageClip(item["path"]).set_duration(clip_dur)
                    else:
                        raw = VideoFileClip(item["path"])
                        s   = item.get("clip_start",0.0)
                        e   = item.get("clip_end",0.0)
                        if e>s and e<=raw.duration: raw=raw.subclip(s,e)
                        elif s>0: raw=raw.subclip(s)
                        if item["value"]!=1.0: raw=raw.fx(vfx.speedx,item["value"])
                        clip=raw

                    rot=item.get("rotation",0); fh=item.get("flip_h",False); fv=item.get("flip_v",False)
                    clip=self.safe_transform(clip,rot,fh,fv)

                    if auto_rotate:
                        if target_w>target_h and clip.w<clip.h: clip=self.safe_transform(clip,90,False,False)
                        elif target_w<target_h and clip.w>clip.h: clip=self.safe_transform(clip,-90,False,False)

                    if smart_fill:
                        sf=max(target_w/clip.w,target_h/clip.h)
                        clip=clip.fx(vfx.resize,sf).fx(vfx.crop,x_center=clip.w/2,y_center=clip.h/2,width=target_w,height=target_h)
                    else:
                        clip=clip.fx(vfx.resize,min(target_w/clip.w,target_h/clip.h))

                    # ── apply volume / full mute ──────────────────────
                    if item.get("clip_muted"):
                        clip=clip.without_audio() if hasattr(clip,"without_audio") else clip
                    elif item.get("volume",1.0)!=1.0 and clip.audio:
                        clip=clip.volumex(item["volume"])

                    # ── apply mute regions ────────────────────────────
                    if item.get("mute_regions") and clip.audio:
                        clip = self._apply_mute_regions(clip, item["mute_regions"], clip_dur)

                    # ── lower third overlay ───────────────────────────
                    vlayers=[ColorClip(size=(target_w,target_h),color=(0,0,0)).set_duration(clip_dur),
                             clip.set_position("center")]
                    if item.get("text"):
                        lt_style=item.get("lt_style","Static Aurora Tile (Bracket)")
                        if lt_style=="Purple Designer Box":
                            lt_layers=self.build_designer_lower_third(item["text"],target_w,target_h,clip_dur,item["text_dur"])
                        elif lt_style=="Aurora Wave":
                            lt_layers=self.build_magical_lower_third(item["text"],target_w,target_h,clip_dur,item["text_dur"])
                        else:
                            lt_layers=self.build_tile_lower_third(item["text"],target_w,target_h,clip_dur,item["text_dur"])
                        vlayers.extend(lt_layers)
                    clip=CompositeVideoClip(vlayers).set_duration(clip_dur)

                # position on timeline
                clip=clip.set_start(t_start)
                final_clips.append(clip)

            # ── BGM tracks ────────────────────────────────────────────
            bgm_audio_clips = []
            for bgm in self.bgm_tracks:
                if bgm.get("muted"): continue
                try:
                    ac=AudioFileClip(bgm["path"])
                    # loop if shorter than total
                    if ac.duration < total_dur:
                        loops=int(np.ceil(total_dur/ac.duration))
                        ac=concatenate_audioclips([ac]*loops).subclip(0,total_dur)
                    else:
                        ac=ac.subclip(0,total_dur-bgm.get("start_offset",0.0))
                    ac=ac.volumex(bgm.get("volume",0.7))
                    ac=ac.set_start(bgm.get("start_offset",0.0))
                    bgm_audio_clips.append(ac)
                except Exception as e:
                    print(f"BGM load error: {e}")

            # ── composite and write ───────────────────────────────────
            final_video=CompositeVideoClip(final_clips,size=(target_w,target_h))

            if bgm_audio_clips:
                from moviepy.audio.AudioClip import CompositeAudioClip
                all_audio=[final_video.audio]+bgm_audio_clips if final_video.audio else bgm_audio_clips
                mixed=CompositeAudioClip(all_audio)
                final_video=final_video.set_audio(mixed)

            final_video.write_videofile(
                save_path,codec="libx264",audio_codec="aac",
                fps=30,preset="ultrafast")
            self.root.after(0,self.on_merge_success,save_path)

        except Exception as e:
            self.root.after(0,self.on_merge_error,str(e))
        finally:
            if "final_video" in locals():
                try: final_video.close()
                except: pass

    def _apply_mute_regions(self, clip, mute_regions, clip_dur):
        """Zero out audio in specified time regions using numpy."""
        if not clip.audio: return clip
        fps_a  = 44100
        n      = int(clip_dur * fps_a)
        t_arr  = np.linspace(0, clip_dur, n, endpoint=False)
        try:
            frames = np.array([clip.audio.get_frame(t) for t in t_arr])
        except Exception:
            return clip

        for (t0, t1) in mute_regions:
            i0 = int(t0 * fps_a)
            i1 = int(t1 * fps_a)
            i0 = max(0, min(i0, n))
            i1 = max(0, min(i1, n))
            frames[i0:i1] = 0.0

        new_audio = AudioArrayClip(frames, fps=fps_a)
        return clip.set_audio(new_audio)

    def on_merge_success(self, save_path):
        self.status_label.config(text="Export complete ✓",fg=C["accent3"])
        messagebox.showinfo("Export Success",f"Saved to:\n{save_path}")
        self.refresh_timeline()

    def on_merge_error(self, err):
        self.status_label.config(text="Export error.",fg="#ff4444")
        messagebox.showerror("Export Error",str(err))
        self.refresh_timeline()


# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    app  = VideoMergerStudio(root)
    root.mainloop()
