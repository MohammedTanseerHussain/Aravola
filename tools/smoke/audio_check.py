import numpy as np
from moviepy.editor import ColorClip, AudioClip
audio = AudioClip(lambda t: 0.15*np.sin(2*np.pi*440*np.asarray(t)), duration=1.0, fps=44100)
clip = ColorClip((160,120), color=(60,120,200), duration=1.0).set_audio(audio)
clip.write_videofile('output/audio_check.mp4', fps=12, preset='ultrafast', logger=None)
from videomerger.media import probe, waveform_samples
print(probe('output/audio_check.mp4').to_dict())
print(waveform_samples('output/audio_check.mp4', 8))
