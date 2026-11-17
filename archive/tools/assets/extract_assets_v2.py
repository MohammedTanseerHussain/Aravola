"""Extract realistic thug life assets from Trump reference image with proper coordinates."""
import cv2
import numpy as np
from PIL import Image
import base64
import io

# Load the reference image
img = cv2.imread(r'c:\Users\Dell\OneDrive\Pictures\Screenshots 1\Screenshot 2026-07-23 213158.png')
h, w = img.shape[:2]
img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

print(f"Image size: {w}x{h}")

# --- EXTRACT GLASSES ---
# The pixelated sunglasses are on Trump's face
# Looking at the image: Trump is seated, glasses are roughly at:
# y: ~200-280, x: ~190-430 (the black pixelated "deal with it" glasses)
gx, gy, gw, gh = 185, 195, 250, 85

glasses_crop = img_rgb[gy:gy+gh, gx:gx+gw]

# The glasses are black with white checkered reflections on a face background
# We need to isolate just the glasses pixels
glasses_gray = cv2.cvtColor(glasses_crop, cv2.COLOR_RGB2GRAY)

# The glasses are very dark (black) - threshold to find them
_, glasses_alpha = cv2.threshold(glasses_gray, 60, 255, cv2.THRESH_BINARY)

# Clean up the mask
kernel = np.ones((3,3), np.uint8)
glasses_alpha = cv2.morphologyEx(glasses_alpha, cv2.MORPH_CLOSE, kernel)
glasses_alpha = cv2.morphologyEx(glasses_alpha, cv2.MORPH_OPEN, kernel)

# Create RGBA
glasses_rgba = np.dstack([glasses_crop, glasses_alpha])
glasses_pil = Image.fromarray(glasses_rgba)
glasses_pil.save("extracted_glasses_v2.png")
print(f"Glasses extracted: {glasses_pil.size}")

# --- EXTRACT CHAIN ---
# The gold chain is around Trump's neck/chest area
# Based on the image: roughly y:280-550, x:230-500
cx, cy, cw, ch = 225, 275, 290, 290

chain_crop = img_rgb[cy:cy+ch, cx:cx+cw]

# Convert to HSV for gold detection
chain_hsv = cv2.cvtColor(chain_crop, cv2.COLOR_RGB2HSV)

# Gold color in HSV: H=15-35, S=80-255, V=120-255
gold_mask = cv2.inRange(chain_hsv, np.array([15, 60, 120]), np.array([38, 255, 255]))

# Also include brighter gold highlights
gold_mask2 = cv2.inRange(chain_hsv, np.array([18, 100, 160]), np.array([32, 255, 255]))
gold_mask = cv2.bitwise_or(gold_mask, gold_mask2)

# Dilate to fill gaps in the chain
kernel = np.ones((5,5), np.uint8)
gold_mask = cv2.dilate(gold_mask, kernel, iterations=2)
gold_mask = cv2.erode(gold_mask, kernel, iterations=1)

# Smooth the alpha
gold_mask = cv2.GaussianBlur(gold_mask, (5, 5), 0)

# Create RGBA
chain_rgba = np.dstack([chain_crop, gold_mask])
chain_pil = Image.fromarray(chain_rgba)
chain_pil.save("extracted_chain_v2.png")
print(f"Chain extracted: {chain_pil.size}")

# --- CLEAN SKIN PIXELS ---
def remove_skin_aggressive(img_array, is_chain=False):
    """Remove skin-colored pixels aggressively."""
    arr = np.array(img_array)
    r, g, b, a = arr[:,:,0].astype(int), arr[:,:,1].astype(int), arr[:,:,2].astype(int), arr[:,:,3]
    
    # Only process opaque pixels
    opaque = a > 30
    
    # Skin detection - very aggressive
    # Covers light to medium to dark skin tones
    skin_mask = opaque & (
        # Light skin
        ((r > 140) & (g > 100) & (b > 70) & (r > g) & (g > b)) |
        # Medium skin  
        ((r > 100) & (g > 60) & (b > 40) & (r > g + 15) & (g > b + 5)) |
        # Darker skin/tan
        ((r > 80) & (r < 180) & (g > 50) & (g < 150) & (b > 30) & (b < 120) & (r > b + 25)) |
        # Reddish skin (face flush)
        ((r > 150) & (g > 80) & (g < 160) & (b > 60) & (b < 140) & (r > g + 20))
    )
    
    # For chain, also remove dark suit pixels (very dark areas that aren't chain)
    if is_chain:
        dark_mask = opaque & (r < 50) & (g < 50) & (b < 50)
        skin_mask = skin_mask | dark_mask
        # Also remove red tie pixels
        red_mask = opaque & (r > 150) & (g < 80) & (b < 80)
        skin_mask = skin_mask | red_mask
    
    # Make skin pixels transparent
    arr[skin_mask, 3] = 0
    
    return Image.fromarray(arr.astype(np.uint8), 'RGBA')

# Clean both assets
glasses_clean = remove_skin_aggressive(glasses_pil, is_chain=False)
chain_clean = remove_skin_aggressive(chain_pil, is_chain=True)

# Save cleaned versions
glasses_clean.save("cleaned_glasses_v2.png")
chain_clean.save("cleaned_chain_v2.png")

# Convert to base64
def img_to_b64(img):
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    lines = [b64[i:i+76] for i in range(0, len(b64), 76)]
    return '\n'.join(lines)

glasses_b64 = img_to_b64(glasses_clean)
chain_b64 = img_to_b64(chain_clean)

print(f"\nCleaned glasses base64 length: {len(glasses_b64)}")
print(f"Cleaned chain base64 length: {len(chain_b64)}")

# Save base64 to files
with open("realistic_glasses_b64.txt", "w") as f:
    f.write(glasses_b64)
with open("realistic_chain_b64.txt", "w") as f:
    f.write(chain_b64)

print("Saved cleaned base64 files")
