"""Stage 1: Extract frames from video files with optional GPS embedding."""

import subprocess
import sys
from pathlib import Path

_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

from .srt_parser import SRTParser
from .gps_embedder import GPSEmbedder


VIDEO_EXTENSIONS = ["*.mp4", "*.MP4", "*.mov", "*.MOV", "*.avi", "*.AVI"]


def extract_frames(video_path, base_output, frame_rate, log):
    """Extract frames from video file(s) and embed GPS data from SRT files.

    Args:
        video_path: Path to a video file or folder containing videos.
        base_output: Base output directory. Frames go to [base]/frames/[name].
        frame_rate: Extraction frame rate (fps).
        log: Callable(str) for progress messages.

    Returns:
        Path to the output frames directory.

    Raises:
        FileNotFoundError: If input path does not exist or no videos found.
        RuntimeError: If all ffmpeg extractions fail.
    """
    input_path = Path(video_path)
    base_output = Path(base_output)

    if not input_path.exists():
        raise FileNotFoundError(f"Input path not found: {input_path}")

    # Determine if input is a file or folder
    if input_path.is_file():
        video_files = [input_path]
        output_folder_name = input_path.stem
        log(f"Processing single video: {input_path.name}")
    else:
        video_files = []
        for ext in VIDEO_EXTENSIONS:
            video_files.extend(input_path.glob(ext))
        video_files = sorted(video_files)

        if not video_files:
            raise FileNotFoundError(f"No video files found in: {input_path}")

        output_folder_name = "combined"
        log(f"Processing {len(video_files)} videos from folder: {input_path.name}")
        for vf in video_files:
            log(f"  - {vf.name}")

    # Create output folder
    frames_folder = base_output / "frames"
    video_output_folder = frames_folder / output_folder_name
    video_output_folder.mkdir(parents=True, exist_ok=True)

    log(f"Output folder: {video_output_folder}")

    # Process each video
    total_frames = 0
    successful_videos = 0

    for video_idx, video_file in enumerate(video_files, 1):
        log(f"\nVideo {video_idx}/{len(video_files)}: {video_file.name}")

        # Find SRT file
        srt_path = video_file.with_suffix(".SRT")
        if not srt_path.exists():
            srt_path = video_file.with_suffix(".srt")

        frames_data = []
        if srt_path.exists():
            log(f"  Found SRT file: {srt_path.name}")
            frames_data = SRTParser.parse_srt(str(srt_path))
            log(f"  Parsed {len(frames_data)} GPS entries")
        else:
            log("  No SRT file - frames will not have GPS data")

        # Extract frames with FFmpeg
        output_pattern = str(
            video_output_folder / f"{video_file.stem}_frame_%04d.jpg"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_file),
            "-vf", f"fps={frame_rate}",
            "-q:v", "2",
            output_pattern,
        ]

        log(f"  Extracting frames at {frame_rate} fps...")
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=_SUBPROCESS_FLAGS,
        )

        if result.returncode != 0:
            log(f"  FFmpeg error: {result.stderr[:500]}")
            continue

        log("  Frame extraction completed")
        successful_videos += 1

        # Embed GPS data
        extracted_frames = sorted(
            video_output_folder.glob(f"{video_file.stem}_frame_*.jpg")
        )
        if frames_data:
            log("  Embedding GPS data into frames...")
            for idx, frame_path in enumerate(extracted_frames):
                timestamp = idx / frame_rate
                gps_data = SRTParser.get_gps_for_timestamp(frames_data, timestamp)
                if gps_data:
                    GPSEmbedder.embed_gps(str(frame_path), gps_data)

            log(f"  Processed {len(extracted_frames)} frames with GPS data")
        else:
            log(f"  Extracted {len(extracted_frames)} frames (no GPS)")

        total_frames += len(extracted_frames)

    if successful_videos == 0:
        raise RuntimeError("All video extractions failed. Is ffmpeg installed and on PATH?")

    log(f"\nFrame extraction complete: {total_frames} total frames from {successful_videos} video(s)")
    log(f"Output: {video_output_folder}")

    return str(video_output_folder)
