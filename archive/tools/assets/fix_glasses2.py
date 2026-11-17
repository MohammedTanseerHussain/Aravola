"""Extract pixelated glasses using color + saturation to separate from skin."""
import cv2
import numpy as np
from PIL import Image
import base64, io

img = cv2.imread(r'c:\Users\Dell\OneDrive\Pictures\Screenshots 1\Screenshot 2026-07-23 213158.png')
img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

# Tight crop around the glasses area
gx, gy, gw, gh = 258, 220, 165, 65
glasses_crop = img_rgb[gy:gy+gh, gx:gx+gw]

# Convert to HSV
hsv_crop = cv2.cvtColor(glasses_crop, cv2.COLOR_RGB2HSV)

# The pixelated glasses have two types of pixels:
# 1. Pure black blocks: R,G,B all < 40, saturation ~0
# 2. White checkered reflections: R,G,B all > 200, saturation ~0
# 
# Skin has: warm hue (0-20 in OpenCV HSV), medium-high saturation

r, g, b = glasses_crop[:,:,0], glasses_crop[:,:,1], glasses_crop[:,:,2]
s = hsv_crop[:,:,1]  # saturation

# Pure black: all channels low AND low saturation (not colored)
is_black = (r < 45) & (g < 45) & (b < 45) & (s < 30)

# Pure white: all channels high AND low saturation
is_white = (r > 210) & (g > 210) & (b > 210) & (s < 40)

# Combined mask
alpha = np.zeros(glasses_crop.shape[:2], dtype=np.uint8)
alpha[is_black | is_white] = 255

# Clean up
kernel = np.ones((2,2), np.uint8)
alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel)

# Create RGBA
glasses_rgba = np.dstack([glasses_crop, alpha])
glasses_pil = Image.fromarray(glasses_rgba)

# Crop to content
arr = np.array(glasses_pil)
rows = np.any(arr[:,:,3] > 10, axis=1)
cols = np.any(arr[:,:,3] > 10, axis=0)
rmin, rmax = np.where(rows)[0][[0, -1]]
cmin, cmax = np.where(cols)[0][[0, -1]]
pad = 2
rmin = max(0, rmin - pad)
rmax = min(arr.shape[0]-1, rmax + pad)
cmin = max(0, cmin - pad)
cmax = min(arr.shape[1]-1, cmax + pad)
glasses_clean = Image.fromarray(arr[rmin:rmax+1, cmin:cmax+1], 'RGBA')

glasses_clean.save("final_glasses_v3.png")
print(f"Glasses: {glasses_clean.size}")

# base64
buffer = io.BytesIO()
glasses_clean.save(buffer, format='PNG', optimize=True)
b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
lines = [b64[i:i+76] for i in range(0, len(b64), 76)]
glasses_b64 = '\n'.join(lines)
with open("final_glasses_b64.txt", "w") as f:
    f.write(glasses_b64)
print(f"Base64 length: {len(glasses_b64)}")
