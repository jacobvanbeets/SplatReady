"""SplatReady Plugin for LichtFeld Studio.

Convert video to COLMAP datasets ready for Gaussian splat training.
"""

import lichtfeld as lf

from .panels.pipeline_panel import SplatReadyPanel

_classes = [SplatReadyPanel]


def on_load():
    """Called when plugin loads."""
    for cls in _classes:
        lf.register_class(cls)
    lf.log.info("SplatReady plugin loaded")


def on_unload():
    """Called when plugin unloads."""
    for cls in reversed(_classes):
        lf.unregister_class(cls)
    lf.log.info("SplatReady plugin unloaded")
