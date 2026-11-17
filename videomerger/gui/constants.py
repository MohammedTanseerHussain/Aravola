"""Class-level tables used by the desktop feature mixins."""
from __future__ import annotations


class GuiConstants:
    """Timeline sizing, effect palettes and other shared class attributes."""

    TRACK_H = 56

    AUDIO_TRACK_H = 40

    RULER_H = 20

    PPS = 80

    MIN_PPS = 20

    MAX_PPS = 400

    LABEL_W = 70

    TRANSITION_DUR = 0.75  # duration of transitions in seconds

    _VARIATION_DESCRIPTIONS = {
        'ethereal':       'Ethereal: volumetric light rays shoot outward from behind the subject using zoom blur. Classic dramatic backlight.',
        'neon':           'Neon: soft glowing aura surrounds the person with gentle light rays. Dreamy and otherworldly.',
        'spacy_game_rays':'Spacy Game Rays: heavenly backlit glow & light wrap. Smoky haze of light radiates from the subject with HDR overexposed gold-to-white bloom.',
        'gabriel_rays':   'Gabriel Rays: radiant golden-white bloom along the silhouette with volumetric light shafts and HDR tone-mapped glow.',
        'angel_rays':     'Angel Rays: pulsating concentric rings of golden light radiate outward from the subject. Heavenly glow with layered halo.',
    }

    _3D_TEXT_HANDLE_R = 14      # px, hit-test radius for corner/rotate handles (in preview display space)

    _3D_TEXT_ROT_HANDLE_LEN = 36  # px, how far the rotate handle sits above the top edge

    _3D_TEXT_EDGES = {
        'top':    ((0, 1), 'y'),   # drag vertically -> tilt (pitch)
        'bottom': ((3, 2), 'y'),
        'left':   ((0, 3), 'x'),   # drag horizontally -> angle onto a side wall
        'right':  ((1, 2), 'x'),
    }

    EFFECT_VARIATIONS = {
        'ethereal':        'Ethereal',
        'neon':            'Neon',
        'spacy_game_rays': 'Spacy Game Rays',
        'gabriel_rays':    'Gabriel Rays',
        'angel_rays':      'Angel Rays',
    }

    COLOR_PALETTE = {
        'Gold (Default)':       ((255, 200, 50), (200, 140, 20)),
        # Whites (7) — each is a gradient pair (inner_core, outer_aura)
        'Pure White':           ((255, 255, 255), (200, 210, 220)),
        'Glacial Blue':         ((200, 230, 255), (80, 150, 220)),
        'Golden Cream':         ((255, 240, 190), (220, 170, 60)),
        'Silver Steel':         ((200, 210, 220), (120, 130, 150)),
        'Rose Blush':           ((255, 210, 220), (190, 130, 150)),
        'Violet Haze':          ((230, 215, 255), (160, 120, 210)),
        'Seafoam':              ((210, 255, 220), (110, 200, 150)),
        # Oranges (4)
        'Vibrant Orange':       ((255, 140, 0), (200, 90, 0)),
        'Deep Orange':          ((255, 100, 0), (180, 60, 0)),
        'Amber':                ((255, 190, 0), (200, 130, 0)),
        'Tangerine':            ((255, 160, 50), (200, 110, 20)),
        # Pink-Purple (4)
        'Hot Pink':             ((255, 50, 150), (200, 20, 110)),
        'Magenta':              ((255, 0, 200), (190, 0, 150)),
        'Violet':               ((200, 100, 255), (140, 60, 200)),
        'Lavender':             ((200, 150, 255), (150, 100, 210)),
        # Yellows (4)
        'Bright Yellow':        ((255, 255, 0), (200, 200, 0)),
        'Lemon Yellow':         ((255, 240, 50), (200, 190, 20)),
        'Canary Yellow':        ((255, 220, 60), (200, 170, 30)),
        'Golden Yellow':        ((255, 215, 0), (200, 160, 0)),
        # Neons (5)
        'Neon Cyan':            ((0, 255, 255), (0, 200, 200)),
        'Neon Green':           ((50, 255, 50), (20, 200, 20)),
        'Neon Blue':            ((50, 100, 255), (20, 60, 200)),
        'Neon Pink':            ((255, 20, 147), (200, 10, 110)),
        'Neon Purple':          ((180, 50, 255), (130, 20, 200)),
        # Golds (7)
        'Classic Gold':         ((255, 200, 50), (200, 140, 20)),
        'Rich Gold':            ((255, 180, 0), (200, 120, 0)),
        'Rose Gold':            ((255, 180, 150), (200, 130, 100)),
        'White Gold':           ((255, 245, 220), (200, 190, 170)),
        'Antique Gold':         ((200, 160, 50), (150, 110, 20)),
        'Bright Gold':          ((255, 220, 80), (200, 170, 40)),
        'Pale Gold':            ((255, 230, 180), (200, 180, 130)),
    }

    _SUN_GLARE_POSITIONS = {
        'top left':     (0.10, 0.10),
        'top right':    (0.90, 0.10),
        'bottom left':  (0.10, 0.90),
        'bottom right': (0.90, 0.90),
        'center':       (0.50, 0.50),
    }

    _X_FLARE_POSITIONS = {
        'top left':     (0.15, 0.15),
        'top right':    (0.85, 0.15),
        'bottom left':  (0.15, 0.85),
        'bottom right': (0.85, 0.85),
        'center':       (0.50, 0.50),
    }

    _X_FLARE_COLORS = {
        'Blue White':   {'ray': (200, 220, 255), 'core': (255, 255, 255), 'glow': (140, 180, 255), 'fringe': (180, 140, 255)},
        'Purple Haze':  {'ray': (200, 160, 255), 'core': (240, 220, 255), 'glow': (180, 100, 255), 'fringe': (255, 120, 200)},
        'Golden Cross': {'ray': (255, 230, 160), 'core': (255, 250, 230), 'glow': (255, 200, 100), 'fringe': (255, 180, 80)},
        'Ice White':    {'ray': (230, 240, 255), 'core': (255, 255, 255), 'glow': (200, 220, 255), 'fringe': (160, 200, 240)},
    }

    _LIGHT_FLASH_POSITIONS = {
        'top left':     (0.18, 0.18),
        'top right':    (0.82, 0.18),
        'bottom left':  (0.18, 0.82),
        'bottom right': (0.82, 0.82),
        'center':       (0.50, 0.50),
        'diagonal tl→br': 'diagonal_tl_br',
        'diagonal bl→tr': 'diagonal_bl_tr',
        'full image':   'full_image',
    }

    _LIGHT_FLASH_COLORS = {
        'White Flash':   {'ray': (220, 235, 255), 'core': (255, 255, 255), 'glow': (140, 170, 255), 'fringe': (160, 120, 255)},
        'Warm Paparazzi':{'ray': (255, 235, 200), 'core': (255, 250, 240), 'glow': (255, 180, 100), 'fringe': (255, 140, 80)},
        'Cool Studio':   {'ray': (200, 230, 255), 'core': (255, 255, 255), 'glow': (120, 170, 255), 'fringe': (100, 140, 240)},
        'Neon Burst':    {'ray': (160, 255, 240), 'core': (255, 255, 255), 'glow': (80, 255, 200), 'fringe': (60, 220, 180)},
        'Golden Gala':   {'ray': (255, 230, 150), 'core': (255, 250, 220), 'glow': (255, 200, 80), 'fringe': (255, 170, 50)},
    }

    _CANOPY_LIGHT_DIRS = {
        'top left':     (0.20, 0.05),
        'top right':    (0.80, 0.05),
        'top center':   (0.50, 0.0),
        'behind':       (0.50, 0.30),
        'side left':    (0.05, 0.45),
        'side right':   (0.95, 0.45),
    }

    _3D_TEXT_COLORS = {
        'Orange': ((255, 120, 0), (200, 80, 0), (160, 60, 0)),
        'White':  ((255, 255, 255), (220, 220, 220), (180, 180, 180)),
        'Gold':   ((255, 215, 0), (218, 165, 32), (180, 130, 20)),
        'Red':    ((230, 40, 40), (180, 20, 20), (130, 10, 10)),
        'Blue':   ((40, 100, 230), (20, 60, 180), (10, 40, 130)),
        'Cyan':   ((0, 220, 240), (0, 170, 190), (0, 120, 140)),
        'Green':  ((40, 200, 60), (20, 150, 30), (10, 100, 15)),
        'Purple': ((160, 50, 220), (120, 30, 170), (80, 15, 120)),
        'Black':  ((60, 60, 60), (40, 40, 40), (25, 25, 25)),
    }

    _3D_TEXT_CANON_FONT_PX = 220  # fixed high-res render size; the quad warp does the actual on-screen scaling

    MOTION_TRACK_COLORS = {
        "Yellow":  (0, 255, 255),
        "Red":     (0, 0, 255),
        "Green":   (0, 255, 0),
        "Blue":    (255, 0, 0),
        "White":   (255, 255, 255),
        "Orange":  (0, 165, 255),
        "Cyan":    (255, 255, 0),
        "Magenta": (255, 0, 255),
        "Lime":    (0, 255, 128),
        "Gold":    (0, 215, 255),
    }
