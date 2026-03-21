"""Standalone pipeline runner - executed as a separate process outside LFS.

Usage: python runner.py <config.json>

Reads pipeline config, runs Stage 1 and Stage 2, prints progress to stdout.
Exit code 0 = success, 1 = error.
The last line of stdout starting with "RESULT:" contains the undistorted path.
"""

import json
import sys
from pathlib import Path

# Add parent so we can import sibling modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.frame_extractor import extract_frames
from core.colmap_processor import process_colmap
from core.metashape_processor import process_metashape
from core.realityscan_processor import process_realityscan


_status_file = None


def log(msg):
    print(msg, flush=True)


def set_progress(pct, step_name):
    """Write progress to status file for the panel to read."""
    if _status_file:
        try:
            with open(_status_file, "w") as f:
                f.write(f"{pct}|{step_name}")
        except Exception:
            pass


def main():
    global _status_file

    if len(sys.argv) < 2:
        print("Usage: python runner.py <config.json>", flush=True)
        sys.exit(1)

    config_path = sys.argv[1]
    with open(config_path, "r") as f:
        cfg = json.load(f)

    # Status file sits next to the config
    _status_file = config_path.replace("_run_config.json", "_progress.txt")

    try:
        base_output = cfg.get("base_output_folder", "")
        if not base_output:
            raise ValueError("Base output folder is required")

        images_dir = None

        # ---- Stage 1: Frame Extraction ----
        if not cfg.get("skip_extraction"):
            set_progress(0, "Extracting frames...")

            video_path = cfg.get("video_path", "")
            if not video_path:
                raise ValueError("Video file/folder is required")

            frame_rate = float(cfg.get("frame_rate", 1.0))
            images_dir = extract_frames(video_path, base_output, frame_rate, log)
            set_progress(40, "Frame extraction complete")
        else:
            manual = cfg.get("manual_frames_folder", "")
            if manual:
                images_dir = manual
            else:
                video_path = cfg.get("video_path", "")
                if video_path:
                    input_path = Path(video_path)
                    if input_path.is_file():
                        images_dir = str(Path(base_output) / "frames" / input_path.stem)
                    else:
                        images_dir = str(Path(base_output) / "frames" / "combined")

        # ---- Stage 2: 3D Reconstruction ----
        undistorted_path = None

        if not cfg.get("skip_reconstruction"):
            method = cfg.get("reconstruction_method", "colmap")
            set_progress(45, f"Starting {method} reconstruction...")

            if not images_dir:
                raise ValueError(
                    "No images directory available. Run Stage 1 or set a manual frames folder."
                )

            if method == "colmap":
                colmap_exe = cfg.get("colmap_exe_path", "")
                if not colmap_exe:
                    raise ValueError("COLMAP executable path is required")
                options = {
                    "use_fisheye": cfg.get("use_fisheye", False),
                    "max_image_size": cfg.get("max_image_size", 2000),
                    "min_scale": cfg.get("min_scale", 0.5),
                }
                undistorted_path = process_colmap(
                    images_dir, base_output, colmap_exe, options, log
                )
            elif method == "metashape":
                metashape_exe = cfg.get("metashape_exe_path", "")
                if not metashape_exe:
                    raise ValueError("Metashape executable path is required")
                undistorted_path = process_metashape(
                    images_dir, base_output, metashape_exe, log
                )
            elif method == "realityscan":
                realityscan_exe = cfg.get("realityscan_exe_path", "")
                if not realityscan_exe:
                    raise ValueError("RealityScan executable path is required")
                undistorted_path = process_realityscan(
                    images_dir, base_output, realityscan_exe, log
                )
            set_progress(95, "Reconstruction complete")
        else:
            undistorted_path = str(Path(base_output) / "colmap" / "undistorted")

        # ---- Done ----
        if undistorted_path:
            set_progress(100, f"RESULT:{undistorted_path}")
        else:
            set_progress(100, "Done")

    except Exception as e:
        log(f"\nERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
