from videomerger.models import Project, Clip, AudioTrack
from videomerger.audio import build_audio_mix, mix_audio
from videomerger.render.export import prepare_project, export_project
import os

p = Project(name='audio', width=160, height=120, fps=12)
p.add_clip(Clip(kind='video', path='output/audio_check.mp4', name='a'))
p.add_clip(Clip(kind='video', path='output/src_b.mp4', name='b', transition_duration=0.3))
p.add_audio(AudioTrack(path='output/audio_check.mp4', name='bgm', volume=0.5, start_offset=0.5))
prepare_project(p); p.reflow()
print('dur', p.total_duration())
mix = build_audio_mix(p)
print('mix', mix is not None, getattr(mix,'duration',None))
if mix: mix.close()
print('mix wav', mix_audio(p, 'output/mix_check.wav'))
print('export', export_project(p, 'output/audio_smoke.mp4', fps=12, preset='ultrafast'))
print('size', os.path.getsize('output/audio_smoke.mp4'))
from videomerger.media import probe
print(probe('output/audio_smoke.mp4').to_dict())
