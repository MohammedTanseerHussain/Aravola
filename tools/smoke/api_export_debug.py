import traceback
from videomerger.models import Project, Clip
from videomerger.render.export import prepare_project, export_project
p = Project(name='dbg', width=320, height=240, fps=12)
p.add_clip(Clip(kind='video', path='output/src_a.mp4', name='a', effects={'color_filter': {'style':'BW Memories','intensity':1.0,'enabled':True}}))
prepare_project(p); p.reflow()
try:
    print(export_project(p, 'output/api_smoke_direct.mp4', fps=12, preset='ultrafast'))
except Exception:
    traceback.print_exc()
