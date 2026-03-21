# SplatReady
<img width="340" height="649" alt="image" src="https://github.com/user-attachments/assets/07b1e922-d345-4065-982f-d8f203118b54" />

https://www.youtube.com/watch?v=5uP29nmTIus

**Convert video to COLMAP datasets ready for Gaussian splat training** — a plugin for [LichtFeld Studio](https://lichtfeld.studio).

SplatReady automates the full pipeline from drone/camera video to a training-ready dataset:

1. **Frame Extraction** — Extract frames from video files using FFmpeg, with automatic GPS embedding from DJI SRT files
2. **3D Reconstruction** — Align images and produce a COLMAP-compatible dataset using your choice of reconstruction tool
3. **Import** — One-click import into LichtFeld Studio to start training

## Requirements

- **[LichtFeld Studio](https://lichtfeld.studio)** v0.4.2 or later
- **[FFmpeg](https://ffmpeg.org/download.html)** — must be on your system PATH (used for frame extraction)
- **One of the following reconstruction tools:**

### COLMAP (free, open source)
- Download from [colmap.github.io](https://colmap.github.io/)
- Windows: download the pre-built binary, the executable is at `colmap-x64-windows-cuda/bin/colmap.exe`

### Agisoft Metashape (commercial)
- Download from [agisoft.com](https://www.agisoft.com/downloads/installer/)
- Default install path: `C:\Program Files\Agisoft\Metashape Pro\metashape.exe`
- Requires a Professional license for headless/scripted processing

### RealityScan (free from Epic Games)
- Download via the [Epic Games Launcher](https://store.epicgames.com/) — search for "RealityScan"
- Default install path: `C:\Program Files\Epic Games\RealityScan_2.0\RealityScan.exe`

## Installation

Copy the `splat_ready` folder into your LichtFeld Studio plugins directory:

```
~/.lichtfeld/plugins/splat_ready/
```

Or install from this repo:

```
git clone https://github.com/jacobvanbeets/SplatReady.git ~/.lichtfeld/plugins/splat_ready
```

LichtFeld Studio will automatically install the plugin dependencies (Pillow, piexif) on first load.

## Usage

1. Open LichtFeld Studio — the **SplatReady** tab appears in the main panel
2. **Stage 1: Frame Extraction**
   - Select a video file (or folder of videos) and an output folder
   - Set the frame rate (e.g., 0.5 fps for drone footage)
   - If you have DJI SRT files alongside your videos, GPS data will be embedded into the extracted frames automatically
3. **Stage 2: 3D Reconstruction**
   - Choose your reconstruction method (COLMAP, Metashape, or RealityScan)
   - Browse to the executable
   - For COLMAP: optionally enable fisheye mode and adjust max image size / min scale
4. Click **Run Pipeline**
   - A progress bar shows the current stage
   - When finished, click **Import Dataset** to load directly into LFS for training

### Tips

- You can skip Stage 1 if you already have extracted frames — just check "Skip" and point to your frames folder
- You can skip Stage 2 if you already have a COLMAP dataset — just check "Skip"
- All settings are saved between sessions

## Output Structure

The plugin produces a standard COLMAP dataset layout:

```
[Base Output]/
├── frames/
│   └── [VideoName]/          # Extracted JPEG frames with GPS EXIF
└── colmap/
    └── undistorted/
        ├── images/           # Undistorted images
        └── sparse/
            └── 0/
                ├── cameras.txt
                ├── images.txt
                └── points3D.txt
```

## License

MIT

## Credits

Built for [LichtFeld Studio](https://lichtfeld.studio) by Jacob van Beets.

Co-Authored-By: Oz <oz-agent@warp.dev>
