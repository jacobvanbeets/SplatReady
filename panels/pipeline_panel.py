"""SplatReady panel - main UI for the plugin."""

import json
import os
import subprocess
import sys
from pathlib import Path

import lichtfeld as lf

from ..core.config import load_config, save_config

# Paths for external process execution
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_RUNNER_SCRIPT = str(_PLUGIN_DIR / "core" / "runner.py")

# Use the plugin venv python (created by LFS during dependency install)
_VENV_PYTHON = _PLUGIN_DIR / ".venv" / "Scripts" / "python.exe"
if not _VENV_PYTHON.exists():
    _VENV_PYTHON = _PLUGIN_DIR / ".venv" / "bin" / "python"  # Linux
if not _VENV_PYTHON.exists():
    _VENV_PYTHON = Path(sys.executable)  # Last resort fallback

_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


RECONSTRUCTION_METHODS = [
    ("colmap", "COLMAP"),
    ("metashape", "Agisoft Metashape"),
    ("realityscan", "RealityScan"),
]


class SplatReadyPanel(lf.ui.Panel):
    """SplatReady - convert video to COLMAP datasets for Gaussian splat training."""

    id = "splat_ready.main_panel"
    label = "SplatReady"
    space = lf.ui.PanelSpace.MAIN_PANEL_TAB
    order = 50
    update_interval_ms = 250

    def __init__(self):
        self._cfg = load_config()

        # External process state (no threads!)
        self._process = None
        self._running = False
        self._log_lines = []
        self._result = None  # (success, message, undistorted_path)
        self._dataset_imported = False
        self._config_file = None
        self._progress = 0.0
        self._progress_label = ""

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _get(self, key):
        return self._cfg.get(key, "")

    def _set(self, key, value):
        self._cfg[key] = value
        save_config(self._cfg)

    def _method_idx(self):
        current = self._get("reconstruction_method")
        for i, (val, _) in enumerate(RECONSTRUCTION_METHODS):
            if val == current:
                return i
        return 0

    @staticmethod
    def _browse_exe(title="Select Executable"):
        """Open a native file dialog to pick an executable."""
        try:
            if sys.platform == "win32":
                ps_script = f'''
                Add-Type -AssemblyName System.Windows.Forms
                $d = New-Object System.Windows.Forms.OpenFileDialog
                $d.Title = "{title}"
                $d.Filter = "Executables (*.exe)|*.exe|All files (*.*)|*.*"
                if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
                    Write-Output $d.FileName
                }}
                '''
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                path = result.stdout.strip()
                return path if path else None
            else:
                try:
                    result = subprocess.run(
                        ["zenity", "--file-selection", "--title", title],
                        capture_output=True, text=True,
                    )
                    if result.returncode == 0:
                        return result.stdout.strip()
                except FileNotFoundError:
                    pass
                return None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Pipeline execution (external process - no threads)
    # ------------------------------------------------------------------

    def _start_pipeline(self):
        """Launch the pipeline as a separate Python process."""
        self._log_lines.clear()
        self._result = None
        self._dataset_imported = False

        # Write config to temp JSON for the runner script
        self._config_file = str(_PLUGIN_DIR / "_run_config.json")
        with open(self._config_file, "w") as f:
            json.dump(self._cfg, f)

        cmd = [str(_VENV_PYTHON), _RUNNER_SCRIPT, self._config_file]
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_SUBPROCESS_FLAGS,
            )
            self._running = True
            self._progress = 0.0
            self._progress_label = "Starting..."
        except Exception as e:
            self._result = (False, f"Failed to start: {e}", None)

    def _poll_process(self):
        """Poll the external process for completion. Called from draw()."""
        if not self._running or self._process is None:
            return

        # Read progress from status file (if it exists)
        progress_file = _PLUGIN_DIR / "_progress.txt"
        if progress_file.exists():
            try:
                data = progress_file.read_text().strip()
                if data:
                    parts = data.split("|", 1)
                    self._progress = float(parts[0]) / 100.0
                    self._progress_label = parts[1] if len(parts) > 1 else ""
            except Exception:
                pass

        ret = self._process.poll()
        if ret is None:
            return

        # Process finished
        self._running = False
        self._process = None

        # Get result path from progress label (runner writes RESULT:path as last progress)
        undistorted_path = None
        if self._progress_label.startswith("RESULT:"):
            undistorted_path = self._progress_label[len("RESULT:"):]

        if ret == 0:
            self._result = (True, "Pipeline completed!", undistorted_path)
        else:
            self._result = (False, "Pipeline failed.", None)

        # Clean up temp files
        for fp in (self._config_file, str(_PLUGIN_DIR / "_progress.txt")):
            try:
                if fp and Path(fp).exists():
                    os.remove(fp)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def draw(self, ui):
        self._poll_process()
        scale = ui.get_dpi_scale()

        # ===== Stage 1: Frame Extraction =====
        if ui.collapsing_header("Stage 1: Frame Extraction", default_open=True):
            changed, val = ui.checkbox(
                "Skip (already extracted)##skip_s1",
                self._cfg.get("skip_extraction", False),
            )
            if changed:
                self._set("skip_extraction", val)

            if not self._cfg.get("skip_extraction"):
                ui.label("Video File/Folder:")
                changed, val = ui.input_text(
                    "##video_path", self._get("video_path")
                )
                if changed:
                    self._set("video_path", val)
                ui.same_line()
                if ui.button("File##browse_video_file", (50 * scale, 0)):
                    path = lf.ui.open_video_file_dialog()
                    if path:
                        self._set("video_path", path)
                ui.same_line()
                if ui.button("Folder##browse_video_folder", (55 * scale, 0)):
                    path = lf.ui.open_folder_dialog(title="Select Video Folder")
                    if path:
                        self._set("video_path", path)

                ui.label("Base Output Folder:")
                changed, val = ui.input_text(
                    "##base_output", self._get("base_output_folder")
                )
                if changed:
                    self._set("base_output_folder", val)
                ui.same_line()
                if ui.button("Browse##browse_output", (60 * scale, 0)):
                    path = lf.ui.open_folder_dialog(
                        title="Select Base Output Folder"
                    )
                    if path:
                        self._set("base_output_folder", path)

                ui.text_disabled("Output: [Base]/frames/[VideoName]")

                changed, val = ui.input_float(
                    "Frame Rate (fps)##fps",
                    float(self._cfg.get("frame_rate", 1.0)),
                    step=0.1,
                    step_fast=1.0,
                    format="%.1f",
                )
                if changed:
                    self._set("frame_rate", max(0.1, val))
            else:
                ui.label("Manual Frames Folder:")
                changed, val = ui.input_text(
                    "##manual_frames", self._get("manual_frames_folder")
                )
                if changed:
                    self._set("manual_frames_folder", val)
                ui.same_line()
                if ui.button("Browse##browse_manual_frames", (60 * scale, 0)):
                    path = lf.ui.open_folder_dialog(
                        title="Select Frames Folder"
                    )
                    if path:
                        self._set("manual_frames_folder", path)

                ui.label("Base Output Folder:")
                changed, val = ui.input_text(
                    "##base_output_skip", self._get("base_output_folder")
                )
                if changed:
                    self._set("base_output_folder", val)
                ui.same_line()
                if ui.button("Browse##browse_output_skip", (60 * scale, 0)):
                    path = lf.ui.open_folder_dialog(
                        title="Select Base Output Folder"
                    )
                    if path:
                        self._set("base_output_folder", path)

        ui.separator()

        # ===== Stage 2: 3D Reconstruction =====
        if ui.collapsing_header(
            "Stage 2: 3D Reconstruction", default_open=True
        ):
            changed, val = ui.checkbox(
                "Skip (already processed)##skip_s2",
                self._cfg.get("skip_reconstruction", False),
            )
            if changed:
                self._set("skip_reconstruction", val)

            if not self._cfg.get("skip_reconstruction"):
                ui.label("Reconstruction Method:")
                method_labels = [m[1] for m in RECONSTRUCTION_METHODS]
                changed, new_idx = ui.combo(
                    "##recon_method", self._method_idx(), method_labels
                )
                if changed:
                    self._set(
                        "reconstruction_method",
                        RECONSTRUCTION_METHODS[new_idx][0],
                    )

                method = self._get("reconstruction_method")

                if method == "colmap":
                    ui.label("COLMAP Executable:")
                    changed, val = ui.input_text(
                        "##colmap_exe", self._get("colmap_exe_path")
                    )
                    if changed:
                        self._set("colmap_exe_path", val)
                    ui.same_line()
                    if ui.button("Browse##browse_colmap", (60 * scale, 0)):
                        path = self._browse_exe("Select COLMAP Executable")
                        if path:
                            self._set("colmap_exe_path", path)

                elif method == "metashape":
                    ui.label("Metashape Executable:")
                    changed, val = ui.input_text(
                        "##metashape_exe", self._get("metashape_exe_path")
                    )
                    if changed:
                        self._set("metashape_exe_path", val)
                    ui.same_line()
                    if ui.button("Browse##browse_metashape", (60 * scale, 0)):
                        path = self._browse_exe("Select Metashape Executable")
                        if path:
                            self._set("metashape_exe_path", path)

                elif method == "realityscan":
                    ui.label("RealityScan Executable:")
                    changed, val = ui.input_text(
                        "##realityscan_exe",
                        self._get("realityscan_exe_path"),
                    )
                    if changed:
                        self._set("realityscan_exe_path", val)
                    ui.same_line()
                    if ui.button("Browse##browse_realityscan", (60 * scale, 0)):
                        path = self._browse_exe("Select RealityScan Executable")
                        if path:
                            self._set("realityscan_exe_path", path)

                ui.text_disabled("Input: [Base]/frames/[VideoName]")
                ui.text_disabled("Output: [Base]/colmap/undistorted")

                if method == "colmap":
                    ui.spacing()
                    changed, val = ui.checkbox(
                        "Use Fisheye Lens Camera Model##fisheye",
                        self._cfg.get("use_fisheye", False),
                    )
                    if changed:
                        self._set("use_fisheye", val)

                    changed, val = ui.input_int(
                        "Max Image Size##max_img",
                        int(self._cfg.get("max_image_size", 2000)),
                        step=100,
                        step_fast=500,
                    )
                    if changed:
                        self._set("max_image_size", max(100, val))

                    changed, val = ui.slider_float(
                        "Min Scale##min_scale",
                        float(self._cfg.get("min_scale", 0.5)),
                        0.2,
                        1.0,
                    )
                    if changed:
                        self._set("min_scale", val)

        ui.separator()

        # ===== Run Pipeline =====
        ui.spacing()

        if self._running:
            ui.begin_disabled()
            ui.button("Running...", (-1, 32 * scale))
            ui.end_disabled()
            if self._progress_label:
                ui.text_disabled(self._progress_label)
            ui.progress_bar(self._progress, width=0)
        else:
            if ui.button_styled(
                "Run Pipeline", "primary", (-1, 32 * scale)
            ):
                self._start_pipeline()

        # Status after completion
        if not self._running and self._result:
            success, msg, undistorted_path = self._result
            if success:
                ui.text_colored(msg, (0.2, 1.0, 0.2, 1.0))
                if undistorted_path:
                    ui.text_disabled(f"Dataset: {undistorted_path}")
                    if not self._dataset_imported:
                        if ui.button_styled(
                            "Import Dataset", "success", (-1, 28 * scale)
                        ):
                            try:
                                # For metashape, import from the sparse/ subfolder
                                import_path = undistorted_path
                                method = self._get("reconstruction_method")
                                if method == "metashape":
                                    sparse_path = Path(undistorted_path) / "sparse"
                                    if sparse_path.exists():
                                        import_path = str(sparse_path)

                                output_dir = str(
                                    Path(undistorted_path).parent.parent / "output"
                                )
                                lf.load_file(
                                    import_path,
                                    is_dataset=True,
                                    output_path=output_dir,
                                )
                                self._dataset_imported = True
                            except Exception:
                                pass
                    else:
                        ui.text_colored(
                            "Dataset imported!",
                            (0.4, 0.8, 1.0, 1.0),
                        )
            else:
                ui.text_colored(f"Error: {msg}", (1.0, 0.3, 0.3, 1.0))

        # ===== Log output =====
        ui.spacing()
        if ui.collapsing_header("Log##pipeline_log", default_open=True):
            if self._log_lines:
                ui.begin_child(
                    "log_scroll", (0, 200 * scale), border=True
                )
                for line in self._log_lines[-100:]:
                    ui.text_wrapped(line)
                ui.set_scroll_here_y(1.0)
                ui.end_child()
            else:
                ui.text_disabled("No log output yet.")
