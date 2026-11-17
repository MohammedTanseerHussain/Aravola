"""Media probing, frame extraction, thumbnails, filmstrips and waveforms.

Everything in this module is UI-independent and safe to call from an API
worker thread.  MoviePy is imported lazily so that probing an image or a video
does not pay the import cost.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

from .config import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    ffmpeg_binary,
    ffprobe_binary,
)


@dataclass
class MediaInfo:
    path: str
    kind: str
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False
    has_video: bool = False
    codec: str = ""
    audio_codec: str = ""
    size_bytes: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _kind_from_suffix(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    return "unknown"


def _run_ffprobe(path: str) -> dict:
    cmd = [
        ffprobe_binary(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "ffprobe failed").strip())
    return json.loads(result.stdout or "{}")


def _run_ffmpeg_info(path: str) -> dict:
    """ffprobe is not always installed; ``ffmpeg -i`` prints the same facts."""
    result = subprocess.run(
        [ffmpeg_binary(), "-hide_banner", "-i", path],
        capture_output=True,
        text=True,
        timeout=20,
    )
    text = result.stderr or ""
    if not text:
        raise RuntimeError("ffmpeg returned no metadata")

    info: dict = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0,
                  "has_video": "Video:" in text, "has_audio": "Audio:" in text,
                  "codec": "", "audio_codec": ""}
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if match:
        hours, minutes, seconds = match.groups()
        info["duration"] = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    match = re.search(r"Video:\s*([^\s,]+)", text)
    if match:
        info["codec"] = match.group(1)
    match = re.search(r"Audio:\s*([^\s,]+)", text)
    if match:
        info["audio_codec"] = match.group(1)
    match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", text)
    if match:
        info["width"], info["height"] = int(match.group(1)), int(match.group(2))
    match = re.search(r"(\d+(?:\.\d+)?)\s*fps", text)
    if match:
        info["fps"] = float(match.group(1))
    return info


def probe(path: str) -> MediaInfo:
    """Read metadata without decoding frames. Falls back to OpenCV on error."""
    p = Path(path)
    kind = _kind_from_suffix(p.suffix)
    info = MediaInfo(path=str(p), kind=kind, size_bytes=p.stat().st_size if p.exists() else 0)

    if not p.exists():
        info.error = "file not found"
        return info

    if kind == "image":
        try:
            with Image.open(p) as img:
                info.width, info.height = img.size
            return info
        except Exception as exc:  # pragma: no cover - corrupt image
            info.error = str(exc)
            return info

    if kind == "audio":
        try:
            data = _run_ffprobe(str(p))
            fmt = data.get("format", {})
            info.duration = float(fmt.get("duration") or 0.0)
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "audio":
                    info.has_audio = True
                    info.audio_codec = stream.get("codec_name", "")
                    info.codec = stream.get("codec_name", "")
                    break
        except Exception as exc:
            try:
                data = _run_ffmpeg_info(str(p))
                info.duration = float(data.get("duration") or 0.0)
                info.has_audio = bool(data.get("has_audio"))
                info.audio_codec = str(data.get("audio_codec") or "")
                info.codec = info.audio_codec
            except Exception:
                info.error = str(exc)
        return info

    # video: ffprobe first
    try:
        data = _run_ffprobe(str(p))
        fmt = data.get("format", {})
        info.duration = float(fmt.get("duration") or 0.0)
        for stream in data.get("streams", []):
            codec_type = stream.get("codec_type")
            if codec_type == "video" and not info.has_video:
                info.has_video = True
                info.width = int(stream.get("width") or 0)
                info.height = int(stream.get("height") or 0)
                info.codec = stream.get("codec_name", "")
                rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
                try:
                    num, den = rate.split("/")
                    info.fps = float(num) / float(den) if float(den) else 0.0
                except Exception:
                    info.fps = 0.0
            elif codec_type == "audio":
                info.has_audio = True
                info.audio_codec = stream.get("codec_name", "")
        if info.duration <= 0:
            info.duration = float(data.get("format", {}).get("duration") or 0.0)
        if info.has_video:
            return info
    except Exception:
        pass

    # ffmpeg metadata fallback (ffprobe missing from PATH but ffmpeg present).
    try:
        data = _run_ffmpeg_info(str(p))
        info.duration = float(data.get("duration") or 0.0)
        info.has_video = bool(data.get("has_video"))
        info.has_audio = bool(data.get("has_audio"))
        info.width = int(data.get("width") or 0)
        info.height = int(data.get("height") or 0)
        info.fps = float(data.get("fps") or 0.0)
        info.codec = str(data.get("codec") or "")
        info.audio_codec = str(data.get("audio_codec") or "")
        if info.has_video:
            return info
    except Exception:
        pass

    # OpenCV fallback (no ffprobe on PATH)
    try:
        import cv2

        cap = cv2.VideoCapture(str(p))
        if cap.isOpened():
            info.has_video = True
            info.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            info.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            info.fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
            info.duration = frames / info.fps if info.fps > 0 else 0.0
        cap.release()
        if info.duration <= 0:
            from moviepy.editor import VideoFileClip  # lazy

            clip = VideoFileClip(str(p), audio=False)
            try:
                info.duration = float(clip.duration or 0.0)
            finally:
                clip.close()
    except Exception as exc:
        info.error = str(exc)
    return info


class VideoFrameReader:
    """Seekable video reader using OpenCV (no MoviePy overhead)."""

    def __init__(self, path: str):
        import cv2

        self._cv2 = cv2
        self.path = path
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open video: {path}")
        self.fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.duration = self.frame_count / self.fps if self.fps > 0 else 0.0

    def read(self, time: float = 0.0) -> np.ndarray:
        time = max(0.0, float(time))
        if self.duration > 0:
            time = min(time, max(0.0, self.duration - 1.0 / max(1.0, self.fps)))
        self.cap.set(self._cv2.CAP_PROP_POS_MSEC, time * 1000.0)
        ok, frame = self.cap.read()
        if not ok:
            self.cap.set(self._cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError(f"Could not read frame at {time:.3f}s from {self.path}")
        return self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)

    def close(self) -> None:
        try:
            self.cap.release()
        except Exception:
            pass

    def __enter__(self) -> "VideoFrameReader":
        return self

    def __exit__(self, *args) -> None:
        self.close()


def read_frame(path: str, time: float = 0.0) -> np.ndarray:
    """Return one RGB frame from a video or image."""
    kind = _kind_from_suffix(Path(path).suffix)
    if kind == "image":
        with Image.open(path) as img:
            return np.array(img.convert("RGB"))
    with VideoFrameReader(path) as reader:
        return reader.read(time)


def fit_image(
    image: Image.Image,
    width: int,
    height: int,
    *,
    smart_fill: bool = True,
    background: tuple[int, int, int] = (0, 0, 0),
) -> Image.Image:
    """Resize an image to fill (crop) or fit (letterbox) a target canvas."""
    image = image.convert("RGB")
    if width <= 0 or height <= 0:
        return image
    if smart_fill:
        scale = max(width / image.width, height / image.height)
        new_size = (max(1, int(math.ceil(image.width * scale))), max(1, int(math.ceil(image.height * scale))))
        resized = image.resize(new_size, Image.LANCZOS)
        left = (resized.width - width) // 2
        top = (resized.height - height) // 2
        return resized.crop((left, top, left + width, top + height))
    scale = min(width / image.width, height / image.height)
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    resized = image.resize(new_size, Image.LANCZOS)
    canvas = Image.new("RGB", (width, height), background)
    canvas.paste(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
    return canvas


def thumbnail(path: str, time: float = 0.0, size: tuple[int, int] = (320, 180), *, smart_fill: bool = False) -> Image.Image:
    frame = read_frame(path, time)
    img = Image.fromarray(frame)
    if smart_fill:
        return fit_image(img, size[0], size[1], smart_fill=True)
    img.thumbnail((size[0], size[1]), Image.LANCZOS)
    return img


def filmstrip(
    path: str,
    *,
    frames: int = 3,
    thumb_size: tuple[int, int] = (144, 80),
    duration: float | None = None,
) -> Image.Image:
    """Build a horizontal strip of evenly spaced frames."""
    if frames <= 0:
        raise ValueError("frames must be positive")
    info = probe(path)
    dur = float(duration if duration is not None else info.duration)
    if dur <= 0:
        dur = 1.0
    times = np.linspace(0.0, max(0.0, dur - 0.05), frames)
    thumbs: list[Image.Image] = []
    if info.kind == "image":
        base = Image.fromarray(read_frame(path, 0))
        thumbs = [base] * frames
    else:
        with VideoFrameReader(path) as reader:
            for t in times:
                try:
                    thumbs.append(Image.fromarray(reader.read(float(t))))
                except Exception:
                    continue
    if not thumbs:
        thumbs = [Image.new("RGB", thumb_size, (20, 20, 20))]
    tw, th = thumb_size
    strip = Image.new("RGB", (tw * frames, th), (10, 10, 10))
    for index, frame in enumerate(thumbs[:frames]):
        fitted = fit_image(frame, tw, th, smart_fill=True)
        strip.paste(fitted, (index * tw, 0))
    return strip


def waveform_samples(path: str, samples: int = 200) -> list[float]:
    """Return normalised peak samples in [0, 1] for audio or a video's audio."""
    samples = max(8, int(samples))
    try:
        from moviepy.editor import AudioFileClip, VideoFileClip

        info = probe(path)
        audio = None
        holder = None
        try:
            if info.kind == "video":
                holder = VideoFileClip(path, audio=True)
                audio = holder.audio
            else:
                holder = AudioFileClip(path)
                audio = holder
            if audio is None or not audio.duration:
                return [0.0] * samples
            times = np.linspace(0.0, max(0.0, audio.duration - 1.0 / 44100.0), samples)
            values = []
            for t in times:
                frame = np.asarray(audio.get_frame(float(t)), dtype=np.float32)
                if frame.ndim == 2:
                    frame = frame.mean(axis=1)
                values.append(float(np.abs(frame).mean()))
            arr = np.asarray(values, dtype=np.float32)
            peak = float(arr.max())
            if peak > 0:
                arr /= peak
            return [round(float(v), 4) for v in arr]
        finally:
            if holder is not None:
                try:
                    holder.close()
                except Exception:
                    pass
    except Exception:
        return [0.0] * samples


def extract_audio(
    path: str,
    output_path: str,
    *,
    start: float = 0.0,
    duration: float | None = None,
    sample_rate: int = 44100,
) -> str:
    """Decode the audio stream to a WAV file using ffmpeg."""
    cmd = [
        ffmpeg_binary(),
        "-y",
        "-ss",
        f"{max(0.0, start):.3f}",
        "-i",
        path,
        "-vn",
        "-ac",
        "2",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
    ]
    if duration is not None and duration > 0:
        cmd.extend(["-t", f"{duration:.3f}"])
    cmd.append(output_path)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "ffmpeg audio extraction failed").strip())
    return output_path
