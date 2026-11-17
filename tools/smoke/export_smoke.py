from moviepy.editor import ColorClip
from videomerger.models import Project, Clip
from videomerger.render.export import export_project, prepare_project

ColorClip((320,240), color=(30,120,200), duration=2).write_videofile('output/src_a.mp4', fps=12, preset='ultrafast', logger=None)
ColorClip((320,240), color=(200,80,40), duration=2).write_videofile('output/src_b.mp4', fps=12, preset='ultrafast', logger=None)

p = Project(name='smoke', width=320, height=240, fps=12)
p.add_clip(Clip(kind='video', path='output/src_a.mp4', name='a'))
p.add_clip(Clip(kind='video', path='output/src_b.mp4', name='b', transition='Crossfade', transition_duration=0.5))
p.add_clip(Clip(kind='title', name='Title', duration=1.0, title={'main_text':'HELLO','sub_text':'world'}))
prepare_project(p)
p.reflow()
print('duration', p.total_duration())
print('clips', [(c.id, round(c.effective_duration(),2), c.timeline_start) for c in p.clips])
print(export_project(p, 'output/smoke.mp4', fps=12, preset='ultrafast'))
import os; print('size', os.path.getsize('output/smoke.mp4'))
