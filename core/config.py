"""Persistent configuration for the dataset pipeline plugin."""

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".lichtfeld" / "plugins" / "splat_ready" / "pipeline_config.json"

DEFAULTS = {
    # Stage 1
    "video_path": "",
    "base_output_folder": "",
    "frame_rate": 1.0,
    "skip_extraction": False,
    "manual_frames_folder": "",
    # Stage 2
    "reconstruction_method": "colmap",  # colmap, metashape, realityscan
    "colmap_exe_path": "",
    "metashape_exe_path": "",
    "realityscan_exe_path": "",
    "use_fisheye": False,
    "max_image_size": 2000,
    "min_scale": 0.5,
    "skip_reconstruction": False,
}


def load_config():
    """Load config from disk, returning defaults for missing keys."""
    config = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                saved = json.load(f)
            config.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return config


def save_config(config):
    """Save config to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
