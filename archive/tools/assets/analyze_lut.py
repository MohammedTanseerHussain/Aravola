import cv2
import numpy as np

img = cv2.imread(r'c:\Users\Dell\OneDrive\Pictures\movielut.jpeg')
img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)
h, w = img.shape[:2]
r, g, b = img[:,:,0], img[:,:,1], img[:,:,2]
print(f'Size: {w}x{h}')
print(f'R range: {r.min():.0f}-{r.max():.0f}, mean={r.mean():.1f}')
print(f'G range: {g.min():.0f}-{g.max():.0f}, mean={g.mean():.1f}')
print(f'B range: {b.min():.0f}-{b.max():.0f}, mean={b.mean():.1f}')
lum = 0.299*r + 0.587*g + 0.114*b
print(f'Lum range: {lum.min():.0f}-{lum.max():.0f}, mean={lum.mean():.1f}')
for band_name, lo, hi in [('Shadows', 0, 85), ('Midtones', 85, 170), ('Highlights', 170, 255)]:
    mask = (lum >= lo) & (lum < hi)
    if mask.sum() > 0:
        rm, gm, bm = r[mask].mean(), g[mask].mean(), b[mask].mean()
        print(f'{band_name}: R={rm:.1f} G={gm:.1f} B={bm:.1f} (tint R-B={rm-bm:.1f})')
for name, ch in [('R', r), ('G', g), ('B', b)]:
    hist, _ = np.histogram(ch, bins=10, range=(0, 255))
    pcts = hist / hist.sum() * 100
    print(f'{name} hist: {[f"{p:.0f}%" for p in pcts]}')
