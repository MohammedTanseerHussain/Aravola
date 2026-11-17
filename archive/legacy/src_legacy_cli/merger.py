import os
from moviepy.editor import VideoFileClip, concatenate_videoclips

class VideoMergerModel:
    def __init__(self, fps=30, transition_duration=1.0):
        self.fps = fps
        self.transition_duration = transition_duration

    def validate_inputs(self, video_paths):
        """Validates that the input list is valid and files exist."""
        if not video_paths:
            raise ValueError("The video paths list cannot be empty.")
        
        for path in video_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Missing file: {path}")

    def merge_with_crossfade(self, video_paths, output_filename):
        """The core processing pipeline."""
        self.validate_inputs(video_paths)
        
        clips = []
        try:
            for i, path in enumerate(video_paths):
                clip = VideoFileClip(path)
                if i > 0:
                    # Apply crossfade to all clips after the first
                    clip = clip.crossfadein(self.transition_duration)
                clips.append(clip)

            # method="compose" is required for visual transitions like crossfades
            final_video = concatenate_videoclips(
                clips, 
                padding=-self.transition_duration, 
                method="compose"
            )
            
            final_video.write_videofile(
                output_filename, 
                codec="libx264", 
                audio_codec="aac",
                fps=self.fps,
                preset="ultrafast" # ultrafast is good for testing, use "medium" for production
            )
            
        finally:
            # Always clean up memory, even if rendering fails
            for clip in clips:
                clip.close()
            if 'final_video' in locals():
                final_video.close()