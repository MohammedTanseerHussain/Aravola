"""Extract and clean realistic thug life assets from the Trump reference image."""
import cv2
import numpy as np
from PIL import Image
import base64
import io

# Load the reference image
img = cv2.imread(r'c:\Users\Dell\OneDrive\Pictures\Screenshots 1\Screenshot 2026-07-23 213158.png')
if img is None:
    print("ERROR: Could not load image")
    exit(1)

print(f"Image shape: {img.shape}")
h, w = img.shape[:2]

# Convert to RGB for PIL
img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

# The Trump image has the accessories at specific locations
# Let me analyze the image to find the glasses, cap, and chain

# Convert to HSV for color analysis
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# --- EXTRACT GLASSES ---
# The pixelated sunglasses are in the upper portion of the face
# They appear to be around y=80-150, x=130-320 based on typical Trump thug life memes
# Let me find the dark rectangular area (the glasses)

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# Find dark regions (glasses are black)
_, dark_mask = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)

# Find contours of dark regions
contours, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# Look for rectangular contours that could be glasses
glasses_candidates = []
for cnt in contours:
    x, y, cw, ch = cv2.boundingRect(cnt)
    area = cw * ch
    if area > 500 and area < 50000:  # Reasonable size for glasses
        aspect = cw / max(ch, 1)
        if 1.5 < aspect < 6.0:  # Wide rectangular shape
            glasses_candidates.append((x, y, cw, ch, area))
            print(f"Glasses candidate: x={x}, y={y}, w={cw}, h={ch}, area={area}, aspect={aspect:.2f}")

# Sort by area and pick the most likely one
glasses_candidates.sort(key=lambda c: c[4], reverse=True)

if glasses_candidates:
    gx, gy, gw, gh = glasses_candidates[0][:4]
    # Add some padding
    pad = 10
    gx = max(0, gx - pad)
    gy = max(0, gy - pad)
    gw = min(w - gx, gw + 2*pad)
    gh = min(h - gy, gh + 2*pad)
    
    glasses_crop = img_rgb[gy:gy+gh, gx:gx+gw]
    
    # Create alpha mask - make non-glasses pixels transparent
    glasses_gray = cv2.cvtColor(glasses_crop, cv2.COLOR_RGB2GRAY)
    _, alpha = cv2.threshold(glasses_gray, 100, 255, cv2.THRESH_BINARY)
    
    # Create RGBA image
    glasses_rgba = np.dstack([glasses_crop, alpha])
    glasses_pil = Image.fromarray(glasses_rgba)
    
    print(f"Glasses extracted: {glasses_pil.size}")
    glasses_pil.save("extracted_glasses.png")
else:
    print("No glasses candidates found, using manual coordinates")
    # Manual extraction based on typical Trump thug life image
    gx, gy, gw, gh = 130, 80, 190, 60
    glasses_crop = img_rgb[gy:gy+gh, gx:gx+gw]
    glasses_gray = cv2.cvtColor(glasses_crop, cv2.COLOR_RGB2GRAY)
    _, alpha = cv2.threshold(glasses_gray, 100, 255, cv2.THRESH_BINARY)
    glasses_rgba = np.dstack([glasses_crop, alpha])
    glasses_pil = Image.fromarray(glasses_rgba)
    glasses_pil.save("extracted_glasses.png")

# --- EXTRACT CHAIN ---
# The gold chain is around the neck area, lower portion
# Look for gold/yellow colors in HSV
# Gold in HSV: H=20-35, S=100-255, V=150-255
gold_mask = cv2.inRange(hsv, np.array([15, 80, 150]), np.array([35, 255, 255]))

# Also include darker gold/bronze tones
gold_mask2 = cv2.inRange(hsv, np.array([10, 50, 100]), np.array([40, 255, 255]))
gold_mask = cv2.bitwise_or(gold_mask, gold_mask2)

# Find contours of gold regions
contours, _ = cv2.findContours(gold_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# Look for chain-shaped contours
chain_candidates = []
for cnt in contours:
    x, y, cw, ch = cv2.boundingRect(cnt)
    area = cw * ch
    if area > 1000 and area < 100000:  # Reasonable size for chain
        aspect = cw / max(ch, 1)
        if 0.5 < aspect < 3.0:  # Various aspect ratios
            chain_candidates.append((x, y, cw, ch, area))
            print(f"Chain candidate: x={x}, y={y}, w={cw}, h={ch}, area={area}, aspect={aspect:.2f}")

# Sort by area
chain_candidates.sort(key=lambda c: c[4], reverse=True)

if chain_candidates:
    cx, cy, cw, ch = chain_candidates[0][:4]
    # Add padding
    pad = 15
    cx = max(0, cx - pad)
    cy = max(0, cy - pad)
    cw = min(w - cx, cw + 2*pad)
    ch = min(h - cy, ch + 2*pad)
    
    chain_crop = img_rgb[cy:cy+ch, cx:cx+cw]
    
    # Create alpha mask from gold color detection
    chain_alpha = gold_mask[cy:cy+ch, cx:cx+cw]
    chain_alpha = cv2.GaussianBlur(chain_alpha, (3, 3), 0)
    
    # Create RGBA image
    chain_rgba = np.dstack([chain_crop, chain_alpha])
    chain_pil = Image.fromarray(chain_rgba)
    
    print(f"Chain extracted: {chain_pil.size}")
    chain_pil.save("extracted_chain.png")
else:
    print("No chain candidates found, using manual coordinates")
    # Manual extraction
    cx, cy, cw, ch = 150, 180, 160, 200
    chain_crop = img_rgb[cy:cy+ch, cx:cx+cw]
    chain_alpha = gold_mask[cy:cy+ch, cx:cx+cw]
    chain_rgba = np.dstack([chain_crop, chain_alpha])
    chain_pil = Image.fromarray(chain_rgba)
    chain_pil.save("extracted_chain.png")

# --- CLEAN SKIN PIXELS ---
def remove_skin(img_array):
    """Remove skin-colored pixels from an RGBA image."""
    arr = np.array(img_array)
    r, g, b, a = arr[:,:,0], arr[:,:,1], arr[:,:,2], arr[:,:,3]
    
    # Skin color ranges (in RGB)
    # Light skin: R>150, G>100, B>80, R>G>B
    # Medium skin: R>120, G>80, B>60
    # Dark skin: R>80, G>50, B>40
    
    skin_mask = (
        ((r > 150) & (g > 100) & (b > 80) & (r > g) & (g > b)) |  # Light
        ((r > 120) & (g > 80) & (b > 60) & (r > g + 10)) |  # Medium
        ((r > 80) & (g > 50) & (b > 40) & (r > b + 20) & (g > b))  # Dark
    )
    
    # Only remove from opaque pixels
    skin_mask = skin_mask & (a > 50)
    
    # Make skin pixels transparent
    arr[skin_mask, 3] = 0
    
    return Image.fromarray(arr, 'RGBA')

# Clean both assets
glasses_clean = remove_skin(glasses_pil)
chain_clean = remove_skin(chain_pil)

# Save cleaned versions
glasses_clean.save("cleaned_glasses.png")
chain_clean.save("cleaned_chain.png")

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

print("\nSaved cleaned base64 files")
