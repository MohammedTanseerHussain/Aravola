import numpy as np, cv2, traceback
from videomerger.effects import apply_effect
frame = np.full((120,160,3),80,dtype=np.uint8)
mask = np.zeros(frame.shape[:2], dtype=np.float32); cv2.circle(mask,(80,60),35,1.0,-1)
for eid, params, ctx in [
    ('gold_outline', {'opacity':0.8}, {'mask':mask}),
    ('thug_life', {'style':'realistic'}, {'face':(30,10,60,60)}),
    ('three_d_text', {'text':'TEST'}, None),
    ('motion_track', {'name':'SUBJECT'}, {'bbox':(40,20,60,90)}),
]:
    try:
        out = apply_effect(frame, eid, params, time=0.4, context=ctx)
        print(eid, out.shape, out.dtype)
    except Exception:
        print('FAILED', eid)
        traceback.print_exc()
