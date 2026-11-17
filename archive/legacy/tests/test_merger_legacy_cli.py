import os
import pytest
from moviepy.editor import ColorClip
from src.merger import VideoMergerModel

# --- Setup Dummy Data ---
@pytest.fixture(scope="module")
def setup_dummy_videos():
    """Creates two 1-second dummy videos for testing."""
    os.makedirs("test_assets", exist_ok=True)
    paths = ["test_assets/red.mp4", "test_assets/blue.mp4"]
    
    # Create a Red and Blue clip
    clip1 = ColorClip(size=(640, 480), color=(255, 0, 0), duration=1)
    clip2 = ColorClip(size=(640, 480), color=(0, 0, 255), duration=1)
    
    clip1.write_videofile(paths[0], fps=24, preset="ultrafast")
    clip2.write_videofile(paths[1], fps=24, preset="ultrafast")
    
    yield paths # Hand the paths over to the tests
    
    # Cleanup after tests are done
    for path in paths:
        if os.path.exists(path):
            os.remove(path)
    if os.path.exists("test_assets/output.mp4"):
        os.remove("test_assets/output.mp4")

# --- Tests ---
def test_empty_list_raises_error():
    merger = VideoMergerModel()
    with pytest.raises(ValueError):
        merger.merge_with_crossfade([], "output.mp4")

def test_missing_file_raises_error():
    merger = VideoMergerModel()
    with pytest.raises(FileNotFoundError):
        merger.merge_with_crossfade(["fake_video.mp4"], "output.mp4")

def test_successful_merge(setup_dummy_videos):
    video_paths = setup_dummy_videos
    output_path = "test_assets/output.mp4"
    
    # We use a short transition for short dummy clips
    merger = VideoMergerModel(transition_duration=0.5)
    merger.merge_with_crossfade(video_paths, output_path)
    
    assert os.path.exists(output_path), "The output video was not created!"