"""Split the legacy ``gui_merger.py`` class into feature mixins.

This is a one-off refactor helper.  It reads the legacy monolith, mechanically
copies each method into a named feature module, and writes the package entry
points.  It deliberately keeps the method bodies byte-for-byte (apart from
dedenting) so behaviour is preserved.
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "gui_merger.py"
PACKAGE = ROOT / "videomerger" / "gui"

# Method-name -> module.  Every unique method in the legacy class must appear
# exactly once; the script asserts that below.
GROUPS: dict[str, list[str]] = {
    "core": [
        "__init__",
        "_preload_heavy_deps",
        "_clip_cache_put",
        "_clip_cache_clear",
        "_close_cached_clip_for",
        "save_state",
        "undo",
        "redo",
        "go_to_start",
        "rewind_5",
        "forward_5",
        "go_to_end",
        "zoom_in",
        "zoom_out",
        "_total_duration",
        "_item_duration",
        "_bind_scroll_children",
    ],
    "shell": [
        "_build_ui",
        "_build_toolbar",
        "_build_left_panel",
        "_build_player_panel",
        "_build_inspector_panel",
        "_build_timeline_panel",
    ],
    "media": [
        "create_clip_model",
        "add_media",
        "add_title_card",
        "add_placeholder",
        "apply_template",
        "fill_placeholder",
        "start_mute_draw_mode",
        "start_highlight_draw_mode",
        "clear_mutes_on_selected",
        "_remove_mute_region",
        "_split_and_duplicate_highlight",
        "move_left",
        "move_right",
        "delete_selected",
        "split_at_playhead",
    ],
    "audio": [
        "add_bgm_track",
        "remove_bgm",
        "_bgm_vol_changed",
        "_bgm_mute_toggled",
        "_apply_ease_to_envelope",
        "_detect_breathing_pattern",
        "_bgm_ease_changed",
        "_resize_speech_pause",
        "apply_speech_ease",
        "_video_ease_changed",
        "_refresh_audio_list",
    ],
    "audio_render": [
        "_cut_audio_region",
        "execute_cut",
        "_eval_vol_envelope",
        "_apply_audio_filters",
        "_build_preview_audio",
    ],
    "playback": [
        "toggle_play",
        "_playback_loop",
        "_do_preview_update",
        "_debounced_preview",
        "_run_debounced_preview",
        "_run_final_preview",
        "_preview_cache_key",
        "_get_cached_base_frame",
        "_apply_kenburns_zoom_numpy",
    ],
    "preview": [
        "update_global_preview",
        "_render_clip_frame",
    ],
    "transitions": [
        "_apply_transition_blend",
        "_apply_export_transitions",
    ],
    "inspector": [
        "change_rotation",
        "render_inspector",
        "save_inspector",
        "_on_inspector_filter_changed",
    ],
    "effects_ui": [
        "_build_effect_controls",
        "_update_filter_desc",
        "_on_filter_changed",
        "_refresh_thug_person_label",
        "_update_variation_desc",
        "refresh_effects_tab",
    ],
    "effects_settings": [
        "_on_effect_timing_changed",
        "_on_effect_setting_changed",
        "_on_kb_changed",
        "_on_thug_life_changed",
        "_on_film_burn_changed",
        "_on_sun_glare_changed",
        "_on_x_flare_changed",
        "_on_light_flash_changed",
        "_on_canopy_changed",
        "_on_3d_text_tracking_changed",
        "_on_motion_track_changed",
        "_nudge_thug_accessory",
        "_reset_thug_accessory",
    ],
    "tracking_ui": [
        "_start_person_correct_mode",
        "_start_person_select_mode",
        "_on_person_click",
        "_draw_selection_feedback",
        "_get_preview_frame",
        "_update_person_buttons",
        "_on_person_selected",
        "_deselect_person",
        "_toggle_outline_preview",
        "_toggle_mask_edit_mode",
        "_on_mask_paint_start",
        "_on_mask_paint_drag",
        "_on_mask_paint_draw",
        "_on_mask_paint_end",
        "_clear_mask_painting",
    ],
    "text3d_ui": [
        "_default_3d_text_quad",
        "_get_3d_text_quad",
        "_3d_text_quad_disp_pts",
        "_3d_text_rotate_handle_disp",
        "_3d_text_edge_midpoints_disp",
        "_point_in_quad",
        "_toggle_3d_text_drag",
        "_on_3d_text_transform_start",
        "_on_3d_text_transform_move",
        "_on_3d_text_transform_end",
        "_draw_3d_text_handles",
        "_3d_text_fit_mapping",
        "_get_3d_text_quad_at",
        "_start_3d_text_autotrack",
        "_3d_text_quad_signed_area",
        "_3d_text_quad_is_convex",
        "_3d_text_homography_is_sane",
        "_3d_text_smooth_track",
        "_run_3d_text_autotrack",
        "_on_3d_text_autotrack_progress",
        "_on_3d_text_autotrack_done",
        "_on_3d_text_autotrack_error",
        "_clear_3d_text_autotrack",
    ],
    "timeline": [
        "_get_clip_bounds",
        "_get_clip_at_pos",
        "_get_env_pt_at_pos",
        "_close_env_popup",
        "_show_env_pt_vol_popup",
        "_show_region_action_popup",
        "_clean_bgm_copy",
        "_region_delete",
        "_region_split",
        "_set_handle_mode",
        "_update_handle_mode_buttons",
        "_get_extend_handle_at_pos",
        "_get_trim_handle_at_pos",
        "_get_bgm_played_dur",
        "_get_clip_display_dur",
    ],
    "timeline_drag": [
        "on_tl_press",
        "on_tl_double_click",
        "on_tl_right_click",
        "_throttled_refresh_timeline",
        "_flush_timeline_refresh",
        "on_tl_drag",
        "on_tl_release",
        "_set_playhead",
    ],
    "timeline_render": [
        "get_filmstrip_image",
        "_placeholder_photo",
        "_schedule_filmstrip_bg",
        "_render_filmstrip",
        "_draw_waveform",
        "_extract_waveform_async",
        "_draw_vol_envelope_on_track",
        "refresh_timeline",
        "_draw_trim_handles",
    ],
    "vision": [
        "_init_mediapipe",
        "_init_yolo",
        "_yolo_track",
        "_get_mediapipe_mask",
        "_apply_zoom_blur",
        "_smooth_mask_for_outline",
        "_get_mediapipe_edges",
        "_generate_mask_from_bbox",
        "_detect_all_persons",
        "_get_transformed_frame",
    ],
    "tracking_impl": [
        "_anchor_tracking_at",
        "_extract_track_template_patch",
        "_template_track_local",
        "_verify_local_context",
        "_maybe_refresh_track_template",
        "_get_person_appearance",
        "_match_person_to_template",
    ],
    "masks": [
        "_get_selected_person_mask",
        "_color_segment_person",
        "_clean_person_mask",
        "_refine_mask_grabcut",
        "_predict_person_position",
        "_update_tracking_keyframe",
        "_trim_mask_overlap",
        "_make_person_bbox_mask",
        "_track_person_across_frames",
        "_get_tracked_center_for_frame",
        "_detect_subject_center",
    ],
    "effects_filters": ["apply_color_filter"],
    "effects_gold": [
        "_create_god_ray_effect",
        "_create_ethereal_effect",
        "_create_divine_effect",
        "_create_brilliance_effect",
        "_create_kaka_effect",
        "_find_head_position",
        "_create_holy_aura_effect",
        "apply_dreamy_angel_effect",
        "_get_person_outline_edges",
        "_get_subject_mask",
        "_get_person_edges",
        "_get_person_gradient",
        "_get_subject_outline",
        "_get_outline_from_mask",
        "_generate_god_rays",
        "_generate_gold_rays",
        "_apply_gold_rim",
        "_apply_gold_glow",
        "_apply_gold_halo",
    ],
    "effects_film": [
        "_create_film_burn_effect",
        "apply_film_burn_effect",
        "_create_sun_glare_effect",
        "apply_sun_glare_effect",
    ],
    "effects_flare": [
        "_create_x_flare_effect",
        "apply_x_flare_effect",
        "_light_flash_pseudo_random",
        "_create_light_flash_effect",
        "apply_light_flash_effect",
    ],
    "effects_canopy": [
        "_create_canopy_effect",
        "apply_canopy_effect",
    ],
    "effects_text3d": [
        "_load_3d_text_font",
        "_get_3d_text_texture_cached",
        "_render_3d_text_texture",
        "_make_3d_text_ground_shadow",
        "_project_3d_text_quad",
        "_create_3d_text_tracking",
        "apply_3d_text_tracking_effect",
    ],
    "effects_motion": [
        "_get_motion_track_position",
        "apply_motion_track_effect",
    ],
    "effects_thug": [
        "_load_thug_asset",
        "_draw_thug_glasses",
        "_draw_gold_chain",
        "_draw_thug_cap",
        "_overlay_at_center",
        "_thug_entry_transform",
        "_find_eye_center",
        "_find_thug_face_box",
        "_thug_ease_out_back",
        "_thug_ease_out_bounce",
        "_create_thug_life_effect",
        "apply_thug_life_effect",
    ],
    "titles": [
        "safe_transform",
        "create_warp_background",
        "create_starry_sky_background",
        "build_tile_lower_third",
        "build_magical_lower_third",
        "build_designer_lower_third",
        "build_news_lower_third",
    ],
    "title_cards": ["build_finch_title_card"],
    "export": [
        "_ffprobe_duration",
        "_validate_video_files",
        "start_merge_thread",
        "_export_worker",
        "_on_export_validate_failed",
        "_on_export_progress",
        "_apply_highlight_regions_export",
        "process_merge",
        "on_merge_success",
        "on_merge_error",
    ],
}

CLASS_NAMES = {
    "core": "CoreMixin",
    "shell": "ShellMixin",
    "media": "MediaMixin",
    "audio": "AudioMixin",
    "audio_render": "AudioRenderMixin",
    "playback": "PlaybackMixin",
    "preview": "PreviewMixin",
    "transitions": "TransitionsMixin",
    "inspector": "InspectorMixin",
    "effects_ui": "EffectsUIMixin",
    "effects_settings": "EffectsSettingsMixin",
    "tracking_ui": "TrackingUIMixin",
    "text3d_ui": "Text3DUIMixin",
    "timeline": "TimelineMixin",
    "timeline_drag": "TimelineDragMixin",
    "timeline_render": "TimelineRenderMixin",
    "vision": "VisionMixin",
    "tracking_impl": "TrackingImplMixin",
    "masks": "MasksMixin",
    "effects_filters": "EffectsFiltersMixin",
    "effects_gold": "EffectsGoldMixin",
    "effects_film": "EffectsFilmMixin",
    "effects_flare": "EffectsFlareMixin",
    "effects_canopy": "EffectsCanopyMixin",
    "effects_text3d": "EffectsText3DMixin",
    "effects_motion": "EffectsMotionMixin",
    "effects_thug": "EffectsThugMixin",
    "titles": "TitlesMixin",
    "title_cards": "TitleCardsMixin",
    "export": "ExportMixin",
}

DOCS = {
    "core": "Application lifecycle, undo history, clip cache and navigation.",
    "shell": "Top-level window, toolbar and panel construction.",
    "media": "Clip creation, media import, templates and clip-level edits.",
    "audio": "Background music tracks, envelopes and speech easing.",
    "audio_render": "Audio cutting and MoviePy preview-mix construction.",
    "playback": "Playback transport and preview scheduling.",
    "preview": "Full-resolution preview and clip-frame composition.",
    "transitions": "Preview and export transition blending.",
    "inspector": "Selected-clip inspector UI and clip transforms.",
    "effects_ui": "Effect controls, filter controls and effect-tab refresh.",
    "effects_settings": "Callbacks for individual effect parameter widgets.",
    "tracking_ui": "Person selection and mask-painting interaction.",
    "text3d_ui": "3D-text placement, transform handles and auto-tracking UI.",
    "timeline": "Timeline hit-testing, trimming and region actions.",
    "timeline_drag": "Timeline pointer dragging, scrubbing and playhead moves.",
    "timeline_render": "Timeline drawing: filmstrips, waveform and envelopes.",
    "vision": "MediaPipe/YOLO initialisation and low-level mask helpers.",
    "tracking_impl": "Template matching and subject tracking across frames.",
    "masks": "Person mask extraction, refinement and keyframe handling.",
    "effects_filters": "Colour-filter application.",
    "effects_gold": "God-ray, aura and gold-outline effect rendering.",
    "effects_film": "Film burn and sun-glare rendering.",
    "effects_flare": "Anamorphic X-flare and light-flash rendering.",
    "effects_canopy": "Fog and volumetric canopy rendering.",
    "effects_text3d": "Extruded 3D-text texture and projection helpers.",
    "effects_motion": "Motion-track arrow and label rendering.",
    "effects_thug": "Thug-life glasses, chain and cap rendering.",
    "titles": "Background generators and lower-third title builders.",
    "title_cards": "Large animated title-card builder.",
    "export": "Validation, background export, progress and completion.",
}

HEADER = '''"""{doc}

Split mechanically from the legacy desktop application.  See
``videomerger.gui.runtime`` for shared imports and lazy MoviePy/Pygame setup.
"""
from __future__ import annotations

from .runtime import *  # noqa: F401,F403
from .runtime import (
    HAS_PYGAME,
    _HAAR_CASCADE_PATH,
    _MOVIEPY_LOADED,
    _TkExportProgressLogger,
    _ensure_moviepy,
    _ensure_pygame,
    pygame,
)


class {class_name}:
    """{doc}"""

'''

THUG_LOADER = '''    def _load_thug_asset(self, key):
        """Load (and cache) a thug-life accessory from ``assets/accessories``.

        Valid keys: 'glasses', 'chain' (pixel-art), 'glasses_real',
        'chain_real', 'cap' (photographic-style).
        """
        if not hasattr(self, "_thug_asset_cache"):
            self._thug_asset_cache = {}
        if key in self._thug_asset_cache:
            return self._thug_asset_cache[key]

        from ..config import CAP, CHAIN_PIXEL, CHAIN_REAL, GLASSES_PIXEL, GLASSES_REAL
        from PIL import Image

        paths = {
            "glasses": GLASSES_PIXEL,
            "chain": CHAIN_PIXEL,
            "glasses_real": GLASSES_REAL,
            "chain_real": CHAIN_REAL,
            "cap": CAP,
        }
        img = None
        path = paths.get(key)
        if path is not None:
            try:
                img = Image.open(path).convert("RGBA")
            except Exception as e:
                print(f"WARNING: failed to load thug-life '{key}' asset: {e}")
        self._thug_asset_cache[key] = img
        return img
'''


def method_block(lines: list[str], item: ast.FunctionDef) -> str:
    decorator_lines = [d.lineno for d in item.decorator_list]
    start = min([item.lineno, *decorator_lines]) - 1
    block = "\n".join(lines[start : item.end_lineno])
    # Keep the original four-space class-body indentation.
    return block.rstrip() + "\n"


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    studio = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "VideoMergerStudio"
    )
    methods: dict[str, ast.FunctionDef] = {}
    for item in studio.body:
        if isinstance(item, ast.FunctionDef):
            methods[item.name] = item  # later definitions win, as in Python

    grouped = [name for names in GROUPS.values() for name in names]
    missing = sorted(set(methods) - set(grouped))
    unknown = sorted(set(grouped) - set(methods))
    duplicates = sorted({name for name in grouped if grouped.count(name) > 1})
    if missing or unknown or duplicates:
        raise SystemExit(
            f"grouping mismatch: missing={missing} unknown={unknown} duplicates={duplicates}"
        )

    PACKAGE.mkdir(parents=True, exist_ok=True)

    # Shared class-level tables (effect variations, colours, timeline sizes).
    constant_blocks = []
    for item in studio.body:
        if not isinstance(item, ast.Assign):
            continue
        names = [target.id for target in item.targets if isinstance(target, ast.Name)]
        if any(name.startswith("_THUG_") and name.endswith("_B64") for name in names):
            continue
        block = "\n".join(lines[item.lineno - 1 : item.end_lineno])
        constant_blocks.append(textwrap.dedent(block).rstrip())

    constants_source = '''"""Class-level tables used by the desktop feature mixins."""
from __future__ import annotations


class GuiConstants:
    """Timeline sizing, effect palettes and other shared class attributes."""

''' + "\n\n".join("    " + block.replace("\n", "\n    ") for block in constant_blocks) + "\n"
    (PACKAGE / "constants.py").write_text(constants_source, encoding="utf-8")

    for module_name, names in GROUPS.items():
        blocks = []
        for name in names:
            if module_name == "effects_thug" and name == "_load_thug_asset":
                blocks.append(THUG_LOADER)
                continue
            block = method_block(lines, methods[name]).replace(
                "os.path.dirname(os.path.abspath(__file__))", "PROJECT_ROOT"
            )
            blocks.append(block)

        class_name = CLASS_NAMES[module_name]
        content = HEADER.format(doc=DOCS[module_name], class_name=class_name)
        content += "\n".join(blocks)
        if not content.endswith("\n"):
            content += "\n"
        (PACKAGE / f"{module_name}.py").write_text(content, encoding="utf-8")

    # Fail loudly if an embedded asset reference survived extraction.
    for path in PACKAGE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "_THUG_" in text and "_B64" in text:
            raise SystemExit(f"embedded thug asset reference left in {path}")

    print(f"wrote {len(GROUPS)} feature modules and {len(constant_blocks)} constants to {PACKAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
