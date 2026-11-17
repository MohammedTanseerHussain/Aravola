# main.py
import argparse
import sys
from src import VideoMergerModel # This works cleanly because of src/__init__.py

def main():
    # 1. Set up the Argument Parser
    parser = argparse.ArgumentParser(
        description="A tool to merge multiple videos smoothly with crossfade transitions."
    )
    
    # 2. Define the command-line arguments
    parser.add_argument(
        "-i", "--inputs", 
        nargs="+", 
        required=True, 
        help="List of video files to merge (e.g., -i vid1.mp4 vid2.mp4)"
    )
    parser.add_argument(
        "-o", "--output", 
        type=str, 
        default="merged_output.mp4", 
        help="Name of the final output file (default: merged_output.mp4)"
    )
    parser.add_argument(
        "-t", "--transition", 
        type=float, 
        default=1.0, 
        help="Duration of the crossfade transition in seconds (default: 1.0)"
    )
    parser.add_argument(
        "--fps", 
        type=int, 
        default=30, 
        help="Frames per second for the output video (default: 30)"
    )

    # 3. Parse the arguments provided by the user
    args = parser.parse_args()

    print("\n--- Video Merger Initialized ---")
    print(f"Inputs: {len(args.inputs)} files detected.")
    print(f"Output: {args.output}")
    print(f"Transition: {args.transition} seconds")
    print(f"FPS: {args.fps}\n")

    # 4. Initialize and run the Model
    try:
        print("Starting the merge process. This may take a few minutes depending on file sizes...")
        merger = VideoMergerModel(fps=args.fps, transition_duration=args.transition)
        merger.merge_with_crossfade(args.inputs, args.output)
        print(f"\nSuccess! Your video has been saved to: {args.output}\n")
        
    except FileNotFoundError as e:
        print(f"\nError: {e}")
        print("Please check your file names and paths and try again.\n")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()