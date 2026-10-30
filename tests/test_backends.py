                                                                    

import os
import importlib.util
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

import backends
from backends.geometry import (WorkArea, bubble_position, clipped_rect,
                               inset_workarea, monitor_index)
from backends.qt_backend import prepare_platform


class DesktopGeometryTests(unittest.TestCase):
    def test_negative_monitor_origin_roundtrips_pointer_coordinates(self):
        area = WorkArea(-1920, -400, 1920, 1040)
        self.assertEqual(area.global_point(120, 1000), (-1800, 600))
        self.assertEqual(area.local(-1800, 600), (120, 1000))

    def test_panel_insets_affect_origin_and_floor(self):
        area = inset_workarea(WorkArea(-1920, 0, 1920, 1080),
                              {"left": 40, "top": 25, "bottom": 60})
        self.assertEqual(area, WorkArea(-1880, 25, 1880, 995))
        self.assertEqual(area.global_point(0, area.height), (-1880, 1020))

    def test_oversized_insets_cannot_create_negative_workarea(self):
        area = inset_workarea(WorkArea(0, 0, 100, 80),
                              {"left": 500, "right": 500, "top": 500, "bottom": 500})
        self.assertEqual(area, WorkArea(99, 79, 1, 1))

    def test_hit_region_is_clipped_and_fractional_edges_are_not_lost(self):
        self.assertEqual(clipped_rect((-4.4, 10.1, 20.2, 100), 80, 60), (0, 10, 16, 50))
        self.assertEqual(clipped_rect((150, 200, 20, 20), 80, 60), (80, 60, 0, 0))
        self.assertEqual(clipped_rect((10.3, 12.2, 30.4, 20.6), 80, 60), (10, 12, 31, 21))

    def test_bubble_stays_inside_workarea(self):
        self.assertEqual(bubble_position(1000, -40, 200, 80, 800, 600), (600, 0))

    def test_monitor_disconnect_falls_back(self):
        names = ["DP-1", "HDMI-1"]
        self.assertEqual(monitor_index(names, "HDMI-1", str), 1)
        self.assertEqual(monitor_index(names[:1], "HDMI-1", str), 0)
        self.assertEqual(monitor_index(names, 99, str), 0)
        self.assertEqual(monitor_index([], 0, str), -1)


class BackendSelectionTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    @patch("backends.sys.platform", "win32")
    def test_windows_uses_qt_without_display_environment(self):
        self.assertEqual(backends.select_backend(), "qt")
        prepare_platform()

    @patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":1"}, clear=True)
    @patch("backends.sys.platform", "linux")
    @patch("backends.layer_shell_available", return_value=True)
    def test_native_layer_shell_is_preferred(self, probe):
        self.assertEqual(backends.select_backend(), "gtk")

    @patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":1",
                             "QT_QPA_PLATFORM": "wayland"}, clear=True)
    @patch("backends.sys.platform", "linux")
    @patch("backends.layer_shell_available", return_value=False)
    def test_gnome_wayland_falls_back_to_xwayland(self, probe):
        self.assertEqual(backends.select_backend(), "qt")
        prepare_platform()
        self.assertEqual(os.environ["QT_QPA_PLATFORM"], "xcb")

    @patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-1"}, clear=True)
    @patch("backends.sys.platform", "linux")
    @patch("backends.layer_shell_available", return_value=False)
    def test_wayland_without_any_supported_protocol_fails_actionably(self, probe):
        with self.assertRaisesRegex(backends.BackendUnavailable, "XWayland"):
            backends.select_backend()
        with self.assertRaisesRegex(backends.BackendUnavailable, "XWayland"):
            prepare_platform()

    @patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}, clear=True)
    @patch("backends.sys.platform", "linux")
    def test_offscreen_smoke_is_allowed_without_a_desktop(self):
        self.assertEqual(backends.select_backend(), "qt")
        prepare_platform()
        self.assertEqual(os.environ["QT_QPA_PLATFORM"], "offscreen")


class QtInputSmokeTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("PySide6"), "optional PySide6 is not installed")
    def test_pointer_mapping_hit_mask_and_click_through_bubble(self):
                                                                              
                                                                               
        script = textwrap.dedent('''
            import tempfile
            from pathlib import Path
            from PySide6.QtCore import QPoint, Qt, QTimer
            from PySide6.QtGui import QColor, QImage
            from PySide6.QtTest import QTest
            from PySide6.QtWidgets import QApplication
            from backends.qt_backend import run
            app = QApplication(['deepsy-test'])
            class Engine:
                cfg = {'workarea_insets': {'left': 23, 'top': 17}}
                quit_requested = False
                pressed = released = None
                def resize(self, w, h): pass
                def tick(self, dt): pass
                def frame(self):
                    return dict(file='test.png', x=20., y=30., width=64., height=80.,
                                hit=(25., 38., 50., 60.), bubble='Привет!',
                                bubble_x=-100., bubble_y=-100.)
                def pointer_sample(self, x, y): pass
                def pointer_move(self, x, y): pass
                def pointer_press(self, x, y, button=1): self.pressed = (x, y, button)
                def pointer_release(self, x, y, button=1): self.released = (x, y, button)
                def command(self, command): self.quit_requested = command.get('quit', False)
            engine = Engine()
            failures = []
            def inspect():
                try:
                    window = next(w for w in app.topLevelWidgets() if w.windowTitle() == 'deepsy')
                    assert window.mask().contains(QPoint(6, 9))
                    assert not window.mask().contains(QPoint(1, 1))
                    bubble = window.bubble
                    assert bubble.windowFlags() & Qt.WindowType.WindowTransparentForInput
                    assert bubble.pos() == QPoint(window.area.x, window.area.y)
                    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=QPoint(10, 15))
                    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=QPoint(10, 15))
                    assert engine.pressed == (30., 45., 1), engine.pressed
                    assert engine.released == (30., 45., 1), engine.released
                except Exception as exc:
                    failures.append(repr(exc))
                app.quit()
            QTimer.singleShot(50, inspect)
            QTimer.singleShot(3000, app.quit)
            with tempfile.TemporaryDirectory() as directory:
                image = QImage(64, 80, QImage.Format.Format_ARGB32)
                image.fill(QColor('orange'))
                assert image.save(str(Path(directory) / 'test.png'))
                assert run(engine, Path(directory)) == 0
            assert not failures, failures
            assert engine.pressed is not None, 'inspection timer did not run'
        ''')
        result = subprocess.run([sys.executable, "-c", script],
                                cwd=Path(__file__).resolve().parents[1],
                                env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
