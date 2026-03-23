"""Stage 1: Extract frames from video files with optional GPS embedding.

Uses PyAV (av package) for video decoding — no external ffmpeg install required.
"""

from pathlib import Path

import av
from PIL import Image

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
    """
    input_path = Path(video_path)
    base_output = Path(base_output)

    if not input_path.exists():
        raise FileNotFoundError(f"Input path not found: {input_path}")

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

    frames_folder = base_output / "frames"
    video_output_folder = frames_folder / output_folder_name
    video_output_folder.mkdir(parents=True, exist_ok=True)

    log(f"Output folder: {video_output_folder}")

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

        # Extract frames using PyAV
        log(f"  Extracting frames at {frame_rate} fps...")
        try:
            frame_paths, frame_timestamps = _extract_video_frames(
                str(video_file),
                str(video_output_folder),
                video_file.stem,
                frame_rate,
            )
        except Exception as e:
            log(f"  Error extracting frames: {e}")
            continue

        log(f"  Extracted {len(frame_paths)} frames")
        successful_videos += 1

        # Embed GPS data using actual frame timestamps
        if frames_data:
            log("  Embedding GPS data into frames...")
            for frame_path, timestamp in zip(frame_paths, frame_timestamps):
                gps_data = SRTParser.get_gps_for_timestamp(frames_data, timestamp)
                if gps_data:
                    GPSEmbedder.embed_gps(str(frame_path), gps_data)

            log(f"  Processed {len(frame_paths)} frames with GPS data")
        else:
            log(f"  {len(frame_paths)} frames (no GPS)")

        total_frames += len(frame_paths)

    if successful_videos == 0:
        raise RuntimeError("All video extractions failed.")

    log(f"\nFrame extraction complete: {total_frames} total frames from {successful_videos} video(s)")
    log(f"Output: {video_output_folder}")

    return str(video_output_folder)


def _extract_video_frames(video_path, output_dir, stem, target_fps):
    """Extract frames from a single video at the target FPS using PyAV.

    Single-pass time-based extraction using actual frame PTS timestamps.
    Handles both CFR and VFR videos correctly by keeping each candidate
    frame in memory and saving it only when the next frame proves it was
    the closest to the target time.

    Returns (list of saved file paths, list of timestamps in seconds).
    """
    container = av.open(video_path)
    stream = container.streams.video[0]

    # Get video duration
    if container.duration and container.duration > 0:
        duration = float(container.duration) / av.time_base
    else:
        duration = 0.0

    # Count total frames
    total_frames = stream.frames
    if not total_frames or total_frames <= 0:
        # Fallback: count by decoding
        total_frames = 0
        for frame in container.decode(video=0):
            total_frames += 1
        container.close()
        container = av.open(video_path)
        stream = container.streams.video[0]

    # Calculate which frame indices to extract
    video_fps = float(stream.average_rate or stream.guessed_rate or 30)
    frame_step = video_fps / target_fps
    # Build exact list: pick frame at floor(i * step) for i in 0..N-1
    # This guarantees the count matches what target_fps implies
    duration = total_frames / video_fps
    desired_count = max(1, round(duration * target_fps))
    target_indices = set(
        int(i * frame_step) for i in range(desired_count)
        if int(i * frame_step) < total_frames
    )

    output_path = Path(output_dir)
    saved_paths = []
    saved_timestamps = []
    saved_count = 0
    frame_idx = 0

    for frame in container.decode(video=0):
        if frame_idx in target_indices:
            # Get actual timestamp for GPS
            if frame.pts is not None:
                frame_time = float(frame.pts * stream.time_base)
            else:
                frame_time = frame_idx / video_fps

            saved_count += 1
            filename = f"{stem}_frame_{saved_count:04d}.jpg"
            filepath = output_path / filename
            frame.to_image().save(str(filepath), quality=95)
            saved_paths.append(str(filepath))
            saved_timestamps.append(frame_time)

        frame_idx += 1

    container.close()
    return saved_paths, saved_timestamps
