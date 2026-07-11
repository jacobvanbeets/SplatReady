"""Normalize zero-based COLMAP camera/image IDs to non-zero IDs."""

import struct
from pathlib import Path


_CAMERA_MODEL_PARAM_COUNTS = {
    0: 3,   # SIMPLE_PINHOLE
    1: 4,   # PINHOLE
    2: 4,   # SIMPLE_RADIAL
    3: 5,   # RADIAL
    4: 8,   # OPENCV
    5: 8,   # OPENCV_FISHEYE
    6: 12,  # FULL_OPENCV
    7: 5,   # FOV
    8: 4,   # SIMPLE_RADIAL_FISHEYE
    9: 5,   # RADIAL_FISHEYE
    10: 12, # THIN_PRISM_FISHEYE
}


def normalize_colmap_ids(undistorted_path, log):
    """Normalize IDs in sparse models under an undistorted COLMAP directory."""
    undistorted = Path(undistorted_path)
    sparse_root = undistorted / "sparse"
    if not sparse_root.exists():
        log("  ID normalize skipped: no sparse folder found")
        return

    layout_dirs = [d for d in sparse_root.rglob("*") if d.is_dir()]
    layout_dirs.append(sparse_root)
    layout_dirs = sorted(set(layout_dirs))

    any_changes = False
    for layout in layout_dirs:
        changed = _normalize_layout(layout, log)
        any_changes = any_changes or changed

    if any_changes:
        log("  ID normalization finished")
    else:
        log("  ID normalization: no zero-based IDs detected")


def _normalize_layout(layout, log):
    cameras_txt = layout / "cameras.txt"
    images_txt = layout / "images.txt"
    points3d_txt = layout / "points3D.txt"
    cameras_bin = layout / "cameras.bin"
    images_bin = layout / "images.bin"
    points3d_bin = layout / "points3D.bin"

    camera_map = {}
    image_map = {}
    changed = False

    # Prefer text mappings if available.
    if cameras_txt.exists() and images_txt.exists():
        camera_map, image_map = _build_text_id_maps(cameras_txt, images_txt)
        if camera_map or image_map:
            if camera_map:
                _patch_cameras_txt(cameras_txt, camera_map)
            if camera_map or image_map:
                _patch_images_txt(images_txt, image_map, camera_map)
            if image_map and points3d_txt.exists():
                _patch_points3d_txt(points3d_txt, image_map)
            changed = True

    # If no text mapping, derive from binary metadata.
    if not (camera_map or image_map) and cameras_bin.exists() and images_bin.exists():
        camera_ids = _read_camera_ids_bin(cameras_bin)
        image_ids, image_camera_ids = _read_image_and_camera_ids_bin(images_bin)
        camera_map = _make_nonzero_id_map(camera_ids)
        image_map = _make_nonzero_id_map(image_ids)

        needs_camera_remap = bool(camera_map)
        needs_image_remap = bool(image_map)
        if needs_camera_remap or needs_image_remap:
            if needs_camera_remap:
                _patch_cameras_bin(cameras_bin, camera_map)
            _patch_images_bin(images_bin, image_map, camera_map)
            if needs_image_remap and points3d_bin.exists():
                _patch_points3d_bin(points3d_bin, image_map)
            changed = True

    # Keep text and binary synchronized if both exist and remap occurred.
    if changed:
        if cameras_bin.exists() and camera_map:
            _patch_cameras_bin(cameras_bin, camera_map)
        if images_bin.exists() and (camera_map or image_map):
            _patch_images_bin(images_bin, image_map, camera_map)
        if points3d_bin.exists() and image_map:
            _patch_points3d_bin(points3d_bin, image_map)
        if cameras_txt.exists() and camera_map:
            _patch_cameras_txt(cameras_txt, camera_map)
        if images_txt.exists() and (camera_map or image_map):
            _patch_images_txt(images_txt, image_map, camera_map)
        if points3d_txt.exists() and image_map:
            _patch_points3d_txt(points3d_txt, image_map)
        log(f"  Normalized IDs in {layout}")

    return changed


def _build_text_id_maps(cameras_txt, images_txt):
    camera_ids = []
    with open(cameras_txt, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split()
            if parts:
                try:
                    camera_ids.append(int(parts[0]))
                except ValueError:
                    pass

    image_ids = []
    image_camera_ids = []
    with open(images_txt, "r", encoding="utf-8") as f:
        for line in f:
            parsed = _parse_images_metadata_line(line)
            if parsed is None:
                continue
            image_id, camera_id, _name = parsed
            image_ids.append(image_id)
            image_camera_ids.append(camera_id)

    camera_map = _make_nonzero_id_map(camera_ids)
    image_map = _make_nonzero_id_map(image_ids)

    # Include zero camera refs present only in images metadata.
    if any(cid <= 0 for cid in image_camera_ids) and 0 not in camera_map:
        ordered_ids = sorted(set(camera_ids))
        next_id = 1
        for existing in ordered_ids:
            mapped = camera_map.get(existing, existing)
            if mapped >= next_id:
                next_id = mapped + 1
        camera_map[0] = next_id

    return camera_map, image_map


def _make_nonzero_id_map(ids):
    unique = sorted(set(ids))
    if not unique or min(unique) > 0:
        return {}
    return {old: idx + 1 for idx, old in enumerate(unique)}


def _parse_images_metadata_line(line):
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    parts = s.split(maxsplit=9)
    if len(parts) < 10:
        return None
    try:
        image_id = int(parts[0])
        float(parts[1]); float(parts[2]); float(parts[3]); float(parts[4])
        float(parts[5]); float(parts[6]); float(parts[7])
        camera_id = int(parts[8])
    except ValueError:
        return None
    return image_id, camera_id, parts[9]


def _patch_cameras_txt(path, camera_map):
    out_lines = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                out_lines.append(line)
                continue
            parts = line.rstrip("\n").split()
            try:
                cid = int(parts[0])
            except ValueError:
                out_lines.append(line)
                continue
            if cid in camera_map:
                parts[0] = str(camera_map[cid])
                out_lines.append(" ".join(parts) + "\n")
            else:
                out_lines.append(line)
    path.write_text("".join(out_lines), encoding="utf-8")


def _patch_images_txt(path, image_map, camera_map):
    out_lines = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parsed = _parse_images_metadata_line(line)
            if parsed is None:
                out_lines.append(line)
                continue
            parts = line.rstrip("\n").split(maxsplit=9)
            image_id = int(parts[0])
            camera_id = int(parts[8])
            parts[0] = str(image_map.get(image_id, image_id))
            parts[8] = str(camera_map.get(camera_id, camera_id))
            out_lines.append(" ".join(parts) + "\n")
    path.write_text("".join(out_lines), encoding="utf-8")


def _patch_points3d_txt(path, image_map):
    out_lines = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                out_lines.append(line)
                continue
            parts = line.rstrip("\n").split()
            if len(parts) < 8:
                out_lines.append(line)
                continue
            track = parts[8:]
            for i in range(0, len(track), 2):
                if i + 1 >= len(track):
                    break
                try:
                    old_image_id = int(track[i])
                except ValueError:
                    continue
                if old_image_id in image_map:
                    track[i] = str(image_map[old_image_id])
            out_lines.append(" ".join(parts[:8] + track) + "\n")
    path.write_text("".join(out_lines), encoding="utf-8")


def _read_camera_ids_bin(path):
    data = path.read_bytes()
    count = struct.unpack_from("<Q", data, 0)[0]
    offset = 8
    ids = []
    for _ in range(count):
        camera_id, model_id, _w, _h = struct.unpack_from("<IiQQ", data, offset)
        ids.append(camera_id)
        offset += 24
        nparams = _CAMERA_MODEL_PARAM_COUNTS.get(model_id)
        if nparams is None:
            raise RuntimeError(f"Unknown COLMAP camera model id in cameras.bin: {model_id}")
        offset += 8 * nparams
    return ids


def _read_image_and_camera_ids_bin(path):
    data = path.read_bytes()
    count = struct.unpack_from("<Q", data, 0)[0]
    offset = 8
    image_ids = []
    camera_ids = []
    for _ in range(count):
        image_id = struct.unpack_from("<I", data, offset)[0]
        image_ids.append(image_id)
        camera_id = struct.unpack_from("<I", data, offset + 60)[0]
        camera_ids.append(camera_id)
        offset += 64
        while data[offset] != 0:
            offset += 1
        offset += 1
        npts = struct.unpack_from("<Q", data, offset)[0]
        offset += 8 + npts * 24
    return image_ids, camera_ids


def _patch_cameras_bin(path, camera_map):
    if not camera_map:
        return
    data = bytearray(path.read_bytes())
    count = struct.unpack_from("<Q", data, 0)[0]
    offset = 8
    for _ in range(count):
        camera_id, model_id, _w, _h = struct.unpack_from("<IiQQ", data, offset)
        new_id = camera_map.get(camera_id, camera_id)
        struct.pack_into("<I", data, offset, new_id)
        offset += 24
        nparams = _CAMERA_MODEL_PARAM_COUNTS.get(model_id)
        if nparams is None:
            raise RuntimeError(f"Unknown COLMAP camera model id in cameras.bin: {model_id}")
        offset += 8 * nparams
    path.write_bytes(bytes(data))


def _patch_images_bin(path, image_map, camera_map):
    if not image_map and not camera_map:
        return
    data = bytearray(path.read_bytes())
    count = struct.unpack_from("<Q", data, 0)[0]
    offset = 8
    for _ in range(count):
        image_id = struct.unpack_from("<I", data, offset)[0]
        new_image_id = image_map.get(image_id, image_id)
        struct.pack_into("<I", data, offset, new_image_id)

        camera_id = struct.unpack_from("<I", data, offset + 60)[0]
        new_camera_id = camera_map.get(camera_id, camera_id)
        struct.pack_into("<I", data, offset + 60, new_camera_id)

        offset += 64
        while data[offset] != 0:
            offset += 1
        offset += 1
        npts = struct.unpack_from("<Q", data, offset)[0]
        offset += 8 + npts * 24
    path.write_bytes(bytes(data))


def _patch_points3d_bin(path, image_map):
    if not image_map:
        return
    data = bytearray(path.read_bytes())
    count = struct.unpack_from("<Q", data, 0)[0]
    offset = 8
    for _ in range(count):
        offset += 8 + 24 + 3 + 8
        track_len = struct.unpack_from("<Q", data, offset)[0]
        offset += 8
        for _ in range(track_len):
            image_id = struct.unpack_from("<I", data, offset)[0]
            new_image_id = image_map.get(image_id, image_id)
            struct.pack_into("<I", data, offset, new_image_id)
            offset += 8
    path.write_bytes(bytes(data))
