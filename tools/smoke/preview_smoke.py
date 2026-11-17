from videomerger.models import Project, Clip
from videomerger.render.export import prepare_project
from videomerger.render.frame import FrameRenderer

p = Project(name='preview', width=320, height=240, fps=12)
p.add_clip(Clip(kind='video', path='output/src_a.mp4', name='a', effects={'film_burn': {'intensity':0.8}}))
p.add_clip(Clip(kind='video', path='output/src_b.mp4', name='b', transition_duration=0.5))
prepare_project(p); p.reflow()
r = FrameRenderer(p)
for t in (0.0, 1.0, 2.2, 3.5):
    im = r.render(t)
    print(t, im.size, im.mode, int(__import__('numpy').array(im).mean()))
r.close()
im.save('output/preview.png')
print('saved')
