"""Stage 2: COLMAP reconstruction pipeline."""

import shutil
import subprocess
import sys
from pathlib import Path

_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def process_colmap(images_dir, base_output, colmap_exe, options, log):
    """Run the full COLMAP pipeline on extracted frames.

    Args:
        images_dir: Path to directory containing input images.
        base_output: Base output directory. COLMAP output goes to [base]/colmap.
        colmap_exe: Path to the COLMAP executable.
        options: Dict with keys: use_fisheye, max_image_size, min_scale.
        log: Callable(str) for progress messages.

    Returns:
        Path to the undistorted output directory ([base]/colmap/undistorted).

    Raises:
        FileNotFoundError: If images directory not found.
        RuntimeError: If any COLMAP step fails.
    """
    images_dir = Path(images_dir)
    base_output = Path(base_output)
    project_dir = base_output / "colmap"

    if not images_dir.exists():
        raise FileNotFoundError(f"Images folder not found: {images_dir}")

    log(f"COLMAP project folder: {project_dir}")
    log(f"Input images folder: {images_dir}")

    # Create project subdirectories
    db_path = project_dir / "database" / "database.db"
    sparse_model_dir = project_dir / "sparse"
    scaled_model_dir = project_dir / "scaled"
    undistorted_output_dir = project_dir / "undistorted"
    exported_model_dir = project_dir / "exported"

    # Clean and create directories
    for d in [
        db_path.parent,
        sparse_model_dir,
        scaled_model_dir,
        undistorted_output_dir,
        exported_model_dir,
    ]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    # Step 1: Feature Extraction
    log("Step 1/6: Feature Extraction...")
    cmd = [
        colmap_exe, "feature_extractor",
        "--database_path", str(db_path),
        "--image_path", str(images_dir),
        "--ImageReader.single_camera", "1",
    ]
    if options.get("use_fisheye"):
        cmd.extend(["--ImageReader.camera_model", "OPENCV_FISHEYE"])

    _run_colmap(cmd, "Feature extraction")
    log("  Feature extraction completed")

    # Step 2: Feature Matching
    log("Step 2/6: Feature Matching...")
    cmd = [colmap_exe, "exhaustive_matcher", "--database_path", str(db_path)]
    _run_colmap(cmd, "Feature matching")
    log("  Feature matching completed")

    # Step 3: Sparse Reconstruction
    log("Step 3/6: Sparse Reconstruction...")
    cmd = [
        colmap_exe, "mapper",
        "--database_path", str(db_path),
        "--image_path", str(images_dir),
        "--output_path", str(sparse_model_dir),
        "--Mapper.multiple_models", "0",
    ]
    _run_colmap(cmd, "Sparse reconstruction")
    log("  Sparse reconstruction completed")

    # Find the output model
    model_dirs = sorted(
        [d for d in sparse_model_dir.iterdir() if d.is_dir()], reverse=True
    )
    if not model_dirs:
        raise RuntimeError("No sparse model was generated")

    unscaled_model_path = model_dirs[0]
    final_model_path = unscaled_model_path

    # Step 4: Model Alignment (optional, uses GPS if available)
    log("Step 4/6: Model Alignment...")
    cmd = [
        colmap_exe, "model_aligner",
        "--input_path", str(unscaled_model_path),
        "--output_path", str(scaled_model_dir),
        "--database_path", str(db_path),
        "--ref_is_gps", "1",
        "--alignment_type", "ENU",
        "--alignment_max_error", "10.0",
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        creationflags=_SUBPROCESS_FLAGS,
    )
    if result.returncode == 0 and (scaled_model_dir / "cameras.bin").exists():
        final_model_path = scaled_model_dir
        log("  Model alignment completed")
    else:
        log("  Model alignment skipped (no GPS data)")

    # Step 5: Image Undistortion
    log("Step 5/6: Image Undistortion...")
    cmd = [
        colmap_exe, "image_undistorter",
        "--image_path", str(images_dir),
        "--input_path", str(final_model_path),
        "--output_path", str(undistorted_output_dir),
        "--output_type", "COLMAP",
        "--max_image_size", str(options.get("max_image_size", 2000)),
        "--min_scale", str(options.get("min_scale", 0.5)),
        "--blank_pixels", "1",
    ]
    _run_colmap(cmd, "Image undistortion")
    log("  Image undistortion completed")

    # Step 6: Ensure sparse/0/ structure
    # COLMAP image_undistorter puts files in sparse/ directly.
    # LFS expects them in sparse/0/.
    log("Step 6/6: Organizing output...")
    undistorted_sparse_path = undistorted_output_dir / "sparse"
    sparse_0_dir = undistorted_sparse_path / "0"
    sparse_0_dir.mkdir(parents=True, exist_ok=True)

    # Move any .bin or .txt files from sparse/ into sparse/0/
    for ext in ("*.bin", "*.txt"):
        for f in undistorted_sparse_path.glob(ext):
            dest = sparse_0_dir / f.name
            shutil.move(str(f), str(dest))

    # Also export TXT format into sparse/0/
    cmd = [
        colmap_exe, "model_converter",
        "--input_path", str(sparse_0_dir),
        "--output_path", str(sparse_0_dir),
        "--output_type", "TXT",
    ]
    # This may fail if files are already TXT, that's fine
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        creationflags=_SUBPROCESS_FLAGS,
    )
    if result.returncode == 0:
        log("  Converted model to TXT format")
    else:
        log("  Model already in TXT format or conversion skipped")

    log(f"\nCOLMAP processing complete!")
    log(f"Undistorted output: {undistorted_output_dir}")

    return str(undistorted_output_dir)


def _run_colmap(cmd, step_name):
    """Run a COLMAP command and raise on failure."""
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        creationflags=_SUBPROCESS_FLAGS,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{step_name} failed (exit code {result.returncode}): {result.stderr[:500]}"
        )
