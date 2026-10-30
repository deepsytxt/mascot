                                                                           

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


class BackendUnavailable(RuntimeError):
    pass


def layer_shell_available() -> bool:
                                                                                  
    if not os.environ.get("WAYLAND_DISPLAY"):
        return False
    probe = """
from ctypes import CDLL, RTLD_GLOBAL
CDLL('libgtk4-layer-shell.so.0', mode=RTLD_GLOBAL)
import gi
gi.require_version('Gtk4LayerShell', '1.0')
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk4LayerShell as LS
from gi.repository import Gtk
Gtk.init()
raise SystemExit(0 if LS.is_supported() else 1)
"""
    env = dict(os.environ, GDK_BACKEND="wayland")
    try:
        return subprocess.run(
            [sys.executable, "-c", probe], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=8, check=False,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def select_backend(requested: str = "auto") -> str:
    requested = requested.lower()
    if requested not in ("auto", "gtk", "qt"):
        raise ValueError("backend должен быть auto, gtk или qt")
    if requested != "auto":
        return requested
    if sys.platform == "win32":
        return "qt"
    if sys.platform != "linux":
        raise BackendUnavailable("Поддерживаются Linux и Windows.")
    if os.environ.get("QT_QPA_PLATFORM") in ("offscreen", "minimal"):
        return "qt"
    if layer_shell_available():
        return "gtk"
    if os.environ.get("DISPLAY"):
        return "qt"
    raise BackendUnavailable(
        "Нет доступного графического backend. В Wayland установите GTK4, "
        "PyGObject, pycairo и gtk4-layer-shell для compositor с layer-shell; "
        "для GNOME Wayland включите XWayland (DISPLAY) или войдите в X11."
    )


def run(engine, frames_dir: Path, requested: str = "auto") -> int:
    backend = select_backend(requested)
    if backend == "gtk":
        from .gtk_backend import run as run_gui
    else:
        from .qt_backend import run as run_gui
    return run_gui(engine, Path(frames_dir))
