"""Fix glasses - tighter crop to just the pixelated sunglasses."""
import cv2
import numpy as np
from PIL import Image
import base64
import io

img = cv2.imread(r'c:\Users\Dell\OneDrive\Pictures\Screenshots 1\Screenshot 2026-07-23 213158.png')
img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

# The pixelated "deal with it" glasses are on Trump's face
# They are black pixel blocks with white checkered reflections
# Looking at the image carefully, they span roughly:
# x: 260-420, y: 225-280

# Tight crop just around the glasses
gx, gy, gw, gh = 255, 215, 175, 75
glasses_crop = img_rgb[gy:gy+gh, gx:gx+gw]
glasses_gray = cv2.cvtColor(glasses_crop, cv2.COLOR_RGB2GRAY)

# The pixelated glasses are very dark (< 60) 
# The face skin is lighter (> 80)
# So threshold at 60 to separate glasses from skin
_, alpha = cv2.threshold(glasses_gray, 60, 255, cv2.THRESH_BINARY)

# Clean up - remove small noise, fill small gaps
kernel = np.ones((3,3), np.uint8)
alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel, iterations=1)
alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, kernel, iterations=1)

# Create RGBA
glasses_rgba = np.dstack([glasses_crop, alpha])
glasses_pil = Image.fromarray(glasses_rgba)

# Crop to content
arr = np.array(glasses_pil)
rows = np.any(arr[:,:,3] > 10, axis=1)
cols = np.any(arr[:,:,3] > 10, axis=0)
rmin, rmax = np.where(rows)[0][[0, -1]]
cmin, cmax = np.where(cols)[0][[0, -1]]
pad = 3
rmin = max(0, rmin - pad)
rmax = min(arr.shape[0]-1, rmax + pad)
cmin = max(0, cmin - pad)
cmax = min(arr.shape[1]-1, cmax + pad)
glasses_clean = Image.fromarray(arr[rmin:rmax+1, cmin:cmax+1], 'RGBA')

glasses_clean.save("final_glasses_v2.png")
print(f"Glasses: {glasses_clean.size}")

# Convert to base64
buffer = io.BytesIO()
glasses_clean.save(buffer, format='PNG', optimize=True)
b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
lines = [b64[i:i+76] for i in range(0, len(b64), 76)]
glasses_b64 = '\n'.join(lines)

with open("final_glasses_b64.txt", "w") as f:
    f.write(glasses_b64)

print(f"Base64 length: {len(glasses_b64)}")
