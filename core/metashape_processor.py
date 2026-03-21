"""Stage 2: Agisoft Metashape reconstruction pipeline."""

import shutil
import subprocess
import sys
from pathlib import Path

_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def process_metashape(images_dir, base_output, metashape_exe, log):
    images_dir = Path(images_dir)
    base_output = Path(base_output)
    project_dir = base_output / "colmap"

    if not images_dir.exists():
        raise FileNotFoundError(f"Images folder not found: {images_dir}")
    if not Path(metashape_exe).exists():
        raise FileNotFoundError(f"Metashape executable not found: {metashape_exe}")

    log(f"Metashape project folder: {project_dir}")
    log(f"Input images folder: {images_dir}")

    undistorted_output_dir = project_dir / "undistorted"
    undistorted_images_dir = undistorted_output_dir / "images"
    undistorted_sparse_dir = undistorted_output_dir / "sparse"

    for d in [undistorted_images_dir, undistorted_sparse_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Generate the exact same script as the original automated_pipeline.py
    metashape_script = project_dir / "metashape_process.py"
    script_content = f'''import Metashape
import sys
from pathlib import Path

doc = Metashape.Document()
chunk = doc.addChunk()

image_folder = Path(r"{images_dir}")
image_files = [str(p) for p in image_folder.glob("*.jpg")] + [str(p) for p in image_folder.glob("*.png")]
print(f"Adding {{len(image_files)}} images...")
chunk.addPhotos(image_files)

print("Aligning photos in HIGH quality mode...")
chunk.matchPhotos(downscale=0, generic_preselection=True, reference_preselection=False)
chunk.alignCameras()

print(f"Aligned {{len(chunk.cameras)}} cameras")

undistorted_dir = Path(r"{undistorted_output_dir}")
images_out_dir = undistorted_dir / "images"
sparse_out_dir = undistorted_dir / "sparse"

images_out_dir.mkdir(parents=True, exist_ok=True)
sparse_out_dir.mkdir(parents=True, exist_ok=True)

project_path = undistorted_dir / "metashape_project.psx"
doc.save(str(project_path))

print("Exporting cameras using Metashape's native COLMAP format...")
try:
    colmap_file = sparse_out_dir / "cameras.txt"
    chunk.exportCameras(path=str(colmap_file), format=Metashape.CamerasFormatColmap)
    print(f"  SUCCESS: Exported using native COLMAP format")
except Exception as e:
    print(f"  ERROR: Native COLMAP export failed: {{e}}")
    raise RuntimeError(f"Failed to export cameras in COLMAP format: {{e}}")

print("Exporting point cloud...")
points_txt = sparse_out_dir / "points3D.txt"
with open(points_txt, 'w') as f:
    f.write("# 3D point list\\n")
    f.write("# POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[]\\n")

    if hasattr(chunk, 'tie_points') and chunk.tie_points and len(chunk.tie_points.points) > 0:
        tie_points = chunk.tie_points.points
        print(f"  Exporting {{len(tie_points)}} tie points...")

        for point_id, point in enumerate(tie_points, 1):
            x, y, z = point.coord.x, point.coord.y, point.coord.z

            if hasattr(point, 'color') and point.color:
                r, g, b = int(point.color[0]), int(point.color[1]), int(point.color[2])
            else:
                r, g, b = 128, 128, 128

            f.write(f"{{point_id}} {{x:.6f}} {{y:.6f}} {{z:.6f}} {{r}} {{g}} {{b}} 0.0\\n")

print("Copying images...")
exported_count = 0
for camera in chunk.cameras:
    if camera.transform is None:
        continue

    label = camera.label
    if not label.lower().endswith(('.jpg', '.jpeg', '.png')):
        label = f"{{label}}.jpg"

    out_path = images_out_dir / label
    try:
        image = camera.photo.image()
        image.save(str(out_path))
        exported_count += 1
    except Exception as e:
        print(f"  Failed to export {{label}}: {{e}}")

print(f"  Exported {{exported_count}} images")

print("Metashape processing complete!")
print(f"Output in: {{undistorted_dir}}")
'''

    metashape_script.parent.mkdir(parents=True, exist_ok=True)
    with open(metashape_script, "w") as f:
        f.write(script_content)

    log(f"Created Metashape script: {metashape_script}")
    log("Running Metashape (this may take a while)...")
    cmd = [metashape_exe, "-r", str(metashape_script)]
    log(f"Command: {' '.join(cmd)}")

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
        raise RuntimeError(f"Metashape failed with exit code {process.returncode}")

    # Fix folder structure: LFS needs sparse/0/ not sparse/
    # Metashape may put files in sparse/ or sparse/sparse/0/ etc.
    # Find cameras.txt, images.txt, points3D.txt and ensure they're in sparse/0/
    log("Fixing folder structure for LFS...")
    sparse_0 = undistorted_sparse_dir / "0"
    sparse_0.mkdir(parents=True, exist_ok=True)

    for txt_name in ("cameras.txt", "images.txt", "points3D.txt"):
        if (sparse_0 / txt_name).exists():
            continue
        found = list(undistorted_sparse_dir.rglob(txt_name))
        for f in found:
            if f.parent != sparse_0:
                shutil.copy2(str(f), str(sparse_0 / txt_name))
                log(f"  Copied {txt_name} to sparse/0/")
                break

    log(f"Metashape processing complete!")
    log(f"Undistorted output: {undistorted_output_dir}")

    return str(undistorted_output_dir)
