"""Stage 2: RealityScan reconstruction pipeline."""

import subprocess
import sys
from pathlib import Path

_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def process_realityscan(images_dir, base_output, realityscan_exe, log):
    """Run RealityScan in headless mode to align images.

    Args:
        images_dir: Path to directory containing input images.
        base_output: Base output directory. Output goes to [base]/colmap/undistorted.
        realityscan_exe: Path to the RealityScan executable.
        log: Callable(str) for progress messages.

    Returns:
        Path to the undistorted output directory ([base]/colmap/undistorted).

    Raises:
        FileNotFoundError: If images directory or RealityScan exe not found.
        RuntimeError: If RealityScan processing fails.
    """
    images_dir = Path(images_dir)
    base_output = Path(base_output)
    project_dir = base_output / "colmap"

    if not images_dir.exists():
        raise FileNotFoundError(f"Images folder not found: {images_dir}")

    if not Path(realityscan_exe).exists():
        raise FileNotFoundError(
            f"RealityScan executable not found: {realityscan_exe}"
        )

    log(f"RealityScan project folder: {project_dir}")
    log(f"Input images folder: {images_dir}")

    # Create output directories
    # LFS expects: undistorted/images/ + undistorted/sparse/0/
    undistorted_output_dir = project_dir / "undistorted"
    undistorted_images_dir = undistorted_output_dir / "images"
    sparse_0_dir = undistorted_output_dir / "sparse" / "0"

    for d in [undistorted_images_dir, sparse_0_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Create project file path
    project_file = project_dir / "realityscan_project.rsproj"
    # Export registration directly into sparse/0/
    registration_file = sparse_0_dir / "registration.txt"

    # Create an empty points3D.txt as fallback
    points_file = sparse_0_dir / "points3D.txt"
    with open(points_file, "w") as f:
        f.write("# 3D point list with one line of data per point:\n")
        f.write(
            "# POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[] as (IMAGE_ID, POINT2D_IDX)\n"
        )
        f.write("# Number of points: 0\n")

    # Build RealityScan CLI command
    cmd = [
        realityscan_exe,
        "-headless",
        "-newScene",
        "-addFolder", str(images_dir),
        "-set", "appIncSubdirs=false",
        "-align",
        "-selectMaximalComponent",
        "-exportRegistration", str(registration_file),
        "-exportUndistortedImages", str(undistorted_images_dir),
        "-save", str(project_file),
        "-quit",
    ]

    log(f"Input images: {images_dir}")
    log(f"Output: {undistorted_output_dir}")
    log(f"Command: {' '.join(cmd)}")
    log("\nRunning RealityScan (this may take a while)...")

    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            creationflags=_SUBPROCESS_FLAGS,
        )

        for line in process.stdout:
            stripped = line.strip()
            if stripped:
                log(stripped)

        process.wait()

        if process.returncode != 0:
            raise RuntimeError(
                f"RealityScan failed with exit code {process.returncode}"
            )

        # Verify expected outputs
        log("\nChecking exports...")

        if registration_file.exists():
            log("Registration exported successfully")
        else:
            log("Warning: registration.txt was not created")

        if undistorted_images_dir.exists() and list(
            undistorted_images_dir.glob("*")
        ):
            image_count = len(list(undistorted_images_dir.glob("*")))
            log(f"Exported {image_count} undistorted images")
        else:
            log("Warning: No undistorted images were exported")

        log(f"Created empty points3D.txt (RealityScan sparse export skipped)")
        log(f"\nOutput directory: {undistorted_output_dir}")
        log("\nNote: RealityScan exports need manual verification")
        log("  - Check that registration.txt contains camera data")
        log("  - Verify undistorted images were exported correctly")

    except Exception as e:
        log(f"RealityScan error: {str(e)}")
        log("\nTroubleshooting:")
        log("1. Verify RealityScan is properly installed")
        log("2. Check that the executable path is correct")
        log("3. Ensure images are in a supported format (JPG, PNG)")
        log("4. Try running RealityScan GUI manually to test alignment")
        raise

    log(f"\nRealityScan processing complete!")
    return str(undistorted_output_dir)
