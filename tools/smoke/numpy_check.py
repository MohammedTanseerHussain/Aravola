import numpy as np
from moviepy.editor import ColorClip
c = ColorClip((160, 120), color=(40, 90, 160), duration=0.5)
c.write_videofile('output/numpy_check.mp4', fps=12, preset='ultrafast', logger=None)
print('WROTE')
