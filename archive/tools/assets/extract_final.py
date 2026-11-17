"""Final extraction - tighter crops, aggressive skin removal."""
import cv2
import numpy as np
from PIL import Image
import base64
import io

img = cv2.imread(r'c:\Users\Dell\OneDrive\Pictures\Screenshots 1\Screenshot 2026-07-23 213158.png')
h, w = img.shape[:2]
img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# --- GLASSES ---
# Pixelated "deal with it" sunglasses - they're the black checkered blocks
# Let me find them by looking for very dark rectangular blocky regions
# on the face area

# The glasses are black with sharp pixel edges
# Crop the face region first
face_region = img_rgb[180:310, 160:460]
face_gray = cv2.cvtColor(face_region, cv2.COLOR_RGB2GRAY)

# The pixelated glasses are very dark (< 40 gray) with very sharp edges
# They form distinct rectangular blocks
_, glass_mask = cv2.threshold(face_gray, 50, 255, cv2.THRESH_BINARY_INV)

# Remove small noise
kernel = np.ones((5,5), np.uint8)
glass_mask = cv2.morphologyEx(glass_mask, cv2.MORPH_OPEN, kernel)

# Find contours and keep only rectangular ones that look like pixel-art blocks
contours, _ = cv2.findContours(glass_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# The pixelated glasses form a connected region across the eyes
# Find the bounding box of all significant dark regions in the eye area
eye_area_mask = np.zeros_like(glass_mask)
for cnt in contours:
    x, y, cw, ch = cv2.boundingRect(cnt)
    area = cw * ch
    # Pixel blocks are roughly square-ish
    if area > 100:
        eye_area_mask[y:y+ch, x:x+cw] = 255

# Dilate slightly to connect nearby blocks
eye_area_mask = cv2.dilate(eye_area_mask, np.ones((3,3), np.uint8), iterations=2)

# Find the overall bounding box of the connected glasses region
contours_final, _ = cv2.findContours(eye_area_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
if contours_final:
    # Get the largest contour (should be the glasses)
    largest = max(contours_final, key=cv2.contourArea)
    x, y, cw, ch = cv2.boundingRect(largest)
    
    # Add small padding
    pad = 5
    x = max(0, x - pad)
    y = max(0, y - pad)
    cw = min(face_region.shape[1] - x, cw + 2*pad)
    ch = min(face_region.shape[0] - y, ch + 2*pad)
    
    glasses_crop = face_region[y:y+ch, x:x+cw]
    glasses_alpha = eye_area_mask[y:y+ch, x:x+cw]
    
    # Offset back to full image coords
    print(f"Glasses at face-offset ({x},{y}), size: {cw}x{ch}")
else:
    # Fallback manual
    glasses_crop = img_rgb[215:265, 210:395]
    glasses_gray = cv2.cvtColor(glasses_crop, cv2.COLOR_RGB2GRAY)
    _, glasses_alpha = cv2.threshold(glasses_gray, 50, 255, cv2.THRESH_BINARY_INV)

glasses_rgba = np.dstack([glasses_crop, glasses_alpha])
glasses_pil = Image.fromarray(glasses_rgba)

# --- CHAIN ---
# Gold chain - extract using HSV gold detection, tight crop
# Chain is around y:300-560, x:240-510
chain_crop = img_rgb[290:570, 230:520]
chain_hsv = cv2.cvtColor(chain_crop, cv2.COLOR_RGB2HSV)

# Gold detection
gold_lower = np.array([15, 50, 120])
gold_upper = np.array([40, 255, 255])
gold_mask = cv2.inRange(chain_hsv, gold_lower, gold_upper)

# Clean up
kernel = np.ones((3,3), np.uint8)
gold_mask = cv2.morphologyEx(gold_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
gold_mask = cv2.morphologyEx(gold_mask, cv2.MORPH_OPEN, kernel, iterations=1)
gold_mask = cv2.GaussianBlur(gold_mask, (3, 3), 0)

chain_rgba = np.dstack([chain_crop, gold_mask])
chain_pil = Image.fromarray(chain_rgba)

# --- AGGRESSIVE SKIN REMOVAL ---
def remove_all_non_chain(img_array):
    """Keep ONLY gold pixels. Remove everything else."""
    arr = np.array(img_array).copy()
    r, g, b, a = arr[:,:,0].astype(int), arr[:,:,1].astype(int), arr[:,:,2].astype(int), arr[:,:,3]
    
    opaque = a > 20
    
    # Gold pixels: high R, medium-high G, low-mid B, R>G>B
    is_gold = opaque & (r > 140) & (g > 100) & (b < 140) & (r >= g) & ((r - b) > 30)
    
    # Also keep bright gold highlights
    is_gold_highlight = opaque & (r > 200) & (g > 170) & (b < 120) & (r > g)
    
    is_chain = is_gold | is_gold_highlight
    
    # Make everything that's NOT chain transparent
    arr[~is_chain, 3] = 0
    
    return Image.fromarray(arr.astype(np.uint8), 'RGBA')

def remove_all_non_glasses(img_array):
    """Keep ONLY the dark pixelated glasses blocks."""
    arr = np.array(img_array).copy()
    r, g, b, a = arr[:,:,0].astype(int), arr[:,:,1].astype(int), arr[:,:,2].astype(int), arr[:,:,3]
    
    opaque = a > 20
    
    # The glasses are very dark (black) pixel blocks
    is_glass = opaque & (r < 70) & (g < 70) & (b < 70)
    
    # Also keep the white checkered reflections
    is_reflection = opaque & (r > 200) & (g > 200) & (b > 200)
    
    keep = is_glass | is_reflection
    
    arr[~keep, 3] = 0
    
    return Image.fromarray(arr.astype(np.uint8), 'RGBA')

glasses_clean = remove_all_non_glasses(glasses_pil)
chain_clean = remove_all_non_chain(chain_pil)

# Crop to content bounds
def crop_to_content(img_arr):
    arr = np.array(img_arr)
    alpha = arr[:,:,3]
    rows = np.any(alpha > 10, axis=1)
    cols = np.any(alpha > 10, axis=0)
    if not rows.any() or not cols.any():
        return img_arr
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    pad = 5
    rmin = max(0, rmin - pad)
    rmax = min(arr.shape[0] - 1, rmax + pad)
    cmin = max(0, cmin - pad)
    cmax = min(arr.shape[1] - 1, cmax + pad)
    return Image.fromarray(arr[rmin:rmax+1, cmin:cmax+1], 'RGBA')

glasses_clean = crop_to_content(glasses_clean)
chain_clean = crop_to_content(chain_clean)

glasses_clean.save("final_glasses.png")
chain_clean.save("final_chain.png")
print(f"Final glasses: {glasses_clean.size}")
print(f"Final chain: {chain_clean.size}")

# Convert to base64
def img_to_b64(img):
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    lines = [b64[i:i+76] for i in range(0, len(b64), 76)]
    return '\n'.join(lines)

glasses_b64 = img_to_b64(glasses_clean)
chain_b64 = img_to_b64(chain_clean)

with open("final_glasses_b64.txt", "w") as f:
    f.write(glasses_b64)
with open("final_chain_b64.txt", "w") as f:
    f.write(chain_b64)

print(f"Glasses b64 length: {len(glasses_b64)}")
print(f"Chain b64 length: {len(chain_b64)}")
