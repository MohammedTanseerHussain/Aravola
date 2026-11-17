"""Audio envelopes, preview mixdown and export mixdown.

MoviePy is used only here (and in the exporter); the rest of the package works
with plain NumPy/Pillow/OpenCV.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np

from .models import AudioTrack, Project


def eval_envelope(points: list[list[float]] | list[tuple[float, float]],
                  fraction: float, base_volume: float = 1.0) -> float:
    """Cosine-interpolated gain at ``fraction`` (0..1) of a track."""
    if not points:
        return float(base_volume)
    ordered = sorted(((float(p[0]), float(p[1])) for p in points), key=lambda p: p[0])
    fraction = max(0.0, min(1.0, float(fraction)))
    if fraction <= ordered[0][0]:
        return float(ordered[0][1])
    if fraction >= ordered[-1][0]:
        return float(ordered[-1][1])
    for (t0, v0), (t1, v1) in zip(ordered, ordered[1:]):
        if t0 <= fraction <= t1:
            alpha = (fraction - t0) / max(1e-9, t1 - t0)
            alpha = 0.5 - 0.5 * math.cos(alpha * math.pi)
            return float(v0 + alpha * (v1 - v0))
    return float(base_volume)


def _apply_track_gain(audio_clip, track: AudioTrack, total_duration: float):
    """Apply volume, envelope, per-point gains and mute regions to an AudioClip."""
    base = float(track.volume)
    envelope = track.envelope or []
    pt_gains = track.pt_gains or {}
    mute_regions = track.mute_regions or []
    total = max(1e-6, float(total_duration))

    gain_times: list[tuple[float, float]] = []
    if envelope:
        ordered = sorted(envelope, key=lambda p: float(p[0]))
        for index, (fraction, _) in enumerate(ordered):
            gain = float(pt_gains.get(str(index), 1.0))
            if abs(gain - 1.0) > 0.001:
                gain_times.append((float(fraction) * total, gain))

    def make_frame(get_frame, t):
        data = np.asarray(get_frame(t), dtype=np.float32)
        if data.ndim == 0:
            data = np.array([data, data], dtype=np.float32)
        elif data.ndim == 1 and data.shape[0] == 1:
            data = np.array([data[0], data[0]], dtype=np.float32)

        if isinstance(t, np.ndarray):
            if data.ndim == 1:
                data = np.column_stack([data, data])
            if len(data) < len(t):
                data = np.pad(data, ((0, len(t) - len(data)), (0, 0)), mode="constant")
            elif len(data) > len(t):
                data = data[: len(t)]

            if len(envelope) >= 2:
                gains = np.asarray(
                    [eval_envelope(envelope, float(ti) / total, base) for ti in t],
                    dtype=np.float32,
                )
            else:
                gains = np.full(len(t), base, dtype=np.float32)

            for start, end in mute_regions:
                gains[(t >= float(start)) & (t <= float(end))] = 0.0
            for at, gain in gain_times:
                gains[np.abs(t - at) < (2.0 / 44100.0)] = gain
            return (data.T * gains).T
        else:
            for start, end in mute_regions:
                if float(start) <= float(t) <= float(end):
                    return data * 0.0
            gain = eval_envelope(envelope, float(t) / total, base) if len(envelope) >= 2 else base
            return data * gain

    try:
        return audio_clip.fl(make_frame, keep_duration=True)
    except Exception:
        return audio_clip.volumex(base)


def _zero_outside(audio):
    """Return ``audio`` with silence outside its own time range.

    MoviePy's ``CompositeAudioClip`` evaluates every layer for the whole
    timeline; a layer that starts at 5 s is asked for negative times and the
    ffmpeg reader raises ``IndexError``.  Guarding each layer fixes that.
    """
    duration = float(getattr(audio, "duration", 0.0) or 0.0)
    channels = int(getattr(audio, "nchannels", 2) or 2)

    def make_frame(get_frame, t):
        if isinstance(t, np.ndarray):
            safe = np.clip(t, 0.0, max(0.0, duration - 1e-6))
            data = np.asarray(get_frame(safe), dtype=np.float32)
            mask = ((t >= 0.0) & (t < duration)).astype(np.float32)
            if data.ndim == 2:
                return data * mask[:, None]
            return data * mask
        if float(t) < 0.0 or float(t) >= duration:
            return np.zeros(channels, dtype=np.float32)
        return get_frame(t)

    return audio.fl(make_frame, keep_duration=True)


def _trim_audio(audio, trim_start: float, trim_end: float | None, speed: float):
    source_duration = float(getattr(audio, "duration", 0.0) or 0.0)
    start = max(0.0, float(trim_start))
    end = float(trim_end) if trim_end else source_duration
    if source_duration > 0:
        end = min(end, source_duration)
        start = min(start, max(0.0, source_duration - 0.01))
    if end > start:
        audio = audio.subclip(start, end)
    if speed and abs(speed - 1.0) > 1e-6:
        try:
            from moviepy.audio.fx.all import speedx as audio_speedx

            audio = audio.fx(audio_speedx, float(speed))
        except Exception:
            try:
                from moviepy.video.fx.all import speedx

                audio = audio.fx(speedx, float(speed))
            except Exception:
                pass
    return audio


def build_audio_mix(project: Project):
    """Return a MoviePy CompositeAudioClip for the whole project (or ``None``)."""
    from moviepy.audio.AudioClip import CompositeAudioClip
    from moviepy.editor import AudioFileClip

    from .media import probe

    total = project.total_duration()
    layers = []
    keep_alive = []
    try:
        for clip in project.clips:
            if clip.kind != "video" or not clip.path or clip.muted:
                continue
            try:
                info = probe(clip.path)
                if not info.has_audio:
                    continue
                audio = AudioFileClip(clip.path)
                keep_alive.append(audio)
                audio = _trim_audio(audio, clip.trim_start, clip.trim_end, clip.speed)
                audio = _zero_outside(audio)
                audio = _apply_track_gain(
                    audio,
                    AudioTrack(
                        path=clip.path,
                        volume=clip.volume,
                        envelope=[],
                    ),
                    total,
                )
                audio = _zero_outside(audio)
                layers.append(audio.set_start(float(clip.timeline_start)))
            except Exception:
                continue

        for track in project.audio_tracks:
            if track.muted or not track.path:
                continue
            try:
                info = probe(track.path)
                if not info.has_audio:
                    continue
                audio = AudioFileClip(track.path)
                keep_alive.append(audio)
                audio = _trim_audio(audio, track.trim_start, track.trim_end, track.speed)
                audio = _zero_outside(audio)
                audio = _apply_track_gain(audio, track, total)
                audio = _zero_outside(audio)
                layers.append(audio.set_start(float(track.start_offset)))
            except Exception:
                continue

        if not layers:
            return None
        mix = CompositeAudioClip(layers).set_duration(total)
        # Keep the source clips alive as long as the composite is used.
        mix._source_holders = keep_alive  # type: ignore[attr-defined]
        return mix
    except Exception:
        for holder in keep_alive:
            try:
                holder.close()
            except Exception:
                pass
        raise


def mix_audio(project: Project, output_path: str, *, fps: int = 44100) -> str | None:
    """Render the project's audio to ``output_path``.

    Returns the output path, or ``None`` when the project has no audio.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    mix = build_audio_mix(project)
    if mix is None:
        return None
    try:
        mix.write_audiofile(
            output_path,
            fps=fps,
            nbytes=2,
            codec="pcm_s16le",
            logger=None,
        )
    finally:
        try:
            for holder in getattr(mix, "_source_holders", []):
                holder.close()
            mix.close()
        except Exception:
            pass
    return output_path


def detect_silence(
    path: str,
    *,
    threshold_db: float = -35.0,
    min_silence: float = 0.25,
    samples: int = 600,
) -> list[tuple[float, float]]:
    """Very small energy-based silence detector.

    Useful for the "speech ease" feature: the caller can insert breathing
    spacers between detected pauses.  Returns absolute ``(start, end)`` pairs.
    """
    from .media import probe, waveform_samples

    info = probe(path)
    if info.kind not in {"audio", "video"}:
        return []
    peak = 10 ** (threshold_db / 20.0)
    data = waveform_samples(path, samples=samples)
    if not data:
        return []
    duration = info.duration or 1.0
    step = duration / len(data)
    ranges: list[tuple[float, float]] = []
    start: float | None = None
    for index, value in enumerate(data):
        quiet = value < peak
        t = index * step
        if quiet and start is None:
            start = t
        elif not quiet and start is not None:
            if t - start >= min_silence:
                ranges.append((start, t))
            start = None
    if start is not None and duration - start >= min_silence:
        ranges.append((start, duration))
    return ranges
