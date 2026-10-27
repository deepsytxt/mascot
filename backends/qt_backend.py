"""Small, transparent desktop window for Windows and X11/XWayland."""

from __future__ import annotations

from functools import lru_cache
import math
import os
from pathlib import Path
import sys
import time

from . import BackendUnavailable
from .style import BUBBLE_BACKGROUND, BUBBLE_FOREGROUND, BUBBLE_BORDER
from .geometry import (ACTIVITIES, MUSIC_MODES, WorkArea, bubble_position,
                       clipped_rect, inset_workarea, monitor_index)


def prepare_platform() -> None:
                                                                                 
                                                                             
    if sys.platform != "linux":
        return
    qpa = os.environ.get("QT_QPA_PLATFORM", "")
    if qpa in ("offscreen", "minimal"):
        return
    if os.environ.get("WAYLAND_DISPLAY") or qpa.startswith("wayland"):
        if not os.environ.get("DISPLAY"):
            raise BackendUnavailable(
                "Qt нужен XWayland (DISPLAY): native Wayland запрещает свободное "
                "перемещение окон. Используйте --backend gtk с gtk4-layer-shell "
                "или включите XWayland / сессию X11."
            )
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    elif not os.environ.get("DISPLAY"):
        raise BackendUnavailable("Нет DISPLAY. Запустите deepsy в графической сессии X11/Wayland.")


def run(engine, frames_dir: Path) -> int:
    prepare_platform()
    try:
        from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
        from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QPixmap, QRegion
        from PySide6.QtWidgets import QApplication, QMenu, QWidget
    except ImportError as exc:
        raise BackendUnavailable("Установите зависимости: python -m pip install -r requirements.txt") from exc

    app = QApplication.instance() or QApplication(["deepsy"])
    if app.platformName().startswith("wayland"):
        raise BackendUnavailable("Qt уже запущен с native Wayland. Перезапустите с QT_QPA_PLATFORM=xcb.")
    app.setApplicationName("deepsy")
    app.setQuitOnLastWindowClosed(False)
    frames_dir = Path(frames_dir)

    @lru_cache(maxsize=128)
    def pixmap(filename):
        result = QPixmap(str(frames_dir / filename))
        if result.isNull():
            raise RuntimeError(f"Не удалось открыть кадр: {frames_dir / filename}")
        return result

    flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
             | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)

    class Bubble(QWidget):
        def __init__(self):
            super().__init__(None, flags | Qt.WindowType.WindowTransparentForInput)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            font = QFont("monospace", 12)
            font.setStyleHint(QFont.StyleHint.Monospace)
            font.setBold(True)
            self.setFont(font)
            self.text = ""

        def display(self, frame, area):
            self.text = str(frame.get("bubble") or "")
            if not self.text:
                self.hide()
                return
            max_width = max(1, min(260, area.width) - 24)
            bounds = self.fontMetrics().boundingRect(
                QRect(0, 0, max_width, 1000), Qt.TextFlag.TextWordWrap, self.text)
            self.resize(min(area.width, max(40, bounds.width() + 24)),
                        min(area.height, max(32, bounds.height() + 18)))
            x, y = bubble_position(frame["bubble_x"] - self.width() / 2,
                                   frame["bubble_y"] - self.height(),
                                   self.width(), self.height(), area.width, area.height)
            self.move(*area.global_point(x, y))
            if not self.isVisible():
                self.show()
            self.update()

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(BUBBLE_FOREGROUND), BUBBLE_BORDER))
            painter.setBrush(QColor(BUBBLE_BACKGROUND))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 3, 3)
            painter.setPen(QColor(BUBBLE_FOREGROUND))
            painter.drawText(self.rect().adjusted(12, 9, -12, -9),
                             Qt.TextFlag.TextWordWrap, self.text)

    class Mascot(QWidget):
        def __init__(self):
            super().__init__(None, flags)
            self.setWindowTitle("deepsy")
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.setMouseTracking(True)
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.area = WorkArea(0, 0, 1, 1)
            self.screen_ref = None
            self.scene = None
            self.image = None
            self.image_offset = (0.0, 0.0)
            self.last_mask = None
            self.menu = None
            self.bubble = Bubble()
            self.last_time = time.monotonic()
            self.error = None
            self.timer = QTimer(self)
            self.timer.setTimerType(Qt.TimerType.PreciseTimer)
            self.timer.timeout.connect(self.advance)
            fps = max(10, min(120, int(engine.cfg.get("fps", 60))))
            self.timer.setInterval(round(1000 / fps))
            app.screenAdded.connect(self.screens_changed)
            app.screenRemoved.connect(self.screens_changed)
            self.screens_changed()

        def screens_changed(self, *_):
            screens = app.screens()
            index = monitor_index(screens, engine.cfg.get("monitor", 0), lambda s: s.name())
            self.screen_ref = screens[index] if index >= 0 else None
            if self.screen_ref is not None and self.windowHandle() is not None:
                self.windowHandle().setScreen(self.screen_ref)
            self.update_area()

        def update_area(self):
            if self.screen_ref is None:
                return False
                                                                                  
            rect = self.screen_ref.availableGeometry()
            self.area = inset_workarea(
                WorkArea(rect.x(), rect.y(), rect.width(), rect.height()),
                engine.cfg.get("workarea_insets"))
            engine.resize(self.area.width, self.area.height)
            return True

        def advance(self):
            try:
                now = time.monotonic()
                dt, self.last_time = min(now - self.last_time, 0.1), now
                if not self.update_area():
                    self.hide()
                    self.bubble.hide()
                    return
                cursor = QCursor.pos()
                engine.pointer_sample(*self.area.local(cursor.x(), cursor.y()))
                engine.tick(dt)
                if engine.quit_requested:
                    app.quit()
                    return
                frame = engine.frame()
                self.image = pixmap(frame["file"])
                self.scene = frame
                                                                                   
                x, y = math.floor(frame["x"]), math.floor(frame["y"])
                self.image_offset = frame["x"] - x, frame["y"] - y
                self.resize(max(1, math.ceil(frame["width"] + self.image_offset[0])),
                            max(1, math.ceil(frame["height"] + self.image_offset[1])))
                self.move(*self.area.global_point(x, y))
                hx, hy, hw, hh = frame["hit"]
                mask = clipped_rect((hx - x, hy - y, hw, hh), self.width(), self.height())
                if mask != self.last_mask:
                    self.setMask(QRegion(QRect(*mask)))
                    self.last_mask = mask
                if not self.isVisible():
                    self.show()
                self.bubble.display(frame, self.area)
                self.update()
            except Exception as exc:
                self.error = exc
                app.exit(1)

        def paintEvent(self, event):
            if self.image is None or self.scene is None:
                return
            painter = QPainter(self)
                                                                             
                                                                         
                                                               
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawPixmap(QRectF(*self.image_offset, self.scene["width"], self.scene["height"]),
                               self.image, QRectF(self.image.rect()))

        def local_point(self, event):
            p = event.globalPosition()
            return self.area.local(p.x(), p.y())

        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                engine.pointer_press(*self.local_point(event), button=1)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

        def mouseMoveEvent(self, event):
            engine.pointer_move(*self.local_point(event))
            event.accept()

        def mouseReleaseEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                engine.pointer_release(*self.local_point(event), button=1)
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()

        def contextMenuEvent(self, event):
            self.menu = QMenu(self)
            for label, activity in ACTIVITIES:
                self.menu.addAction(label, lambda checked=False, a=activity: engine.command({"activity": a}))
            self.menu.addSeparator()
            for label, mode in MUSIC_MODES:
                self.menu.addAction(label, lambda checked=False, m=mode: engine.command({"music_mode": m}))
            self.menu.addSeparator()
            self.menu.addAction("Закрыть deepsy", lambda: engine.command({"quit": True}))
            self.menu.popup(event.globalPos())
            event.accept()

        def closeEvent(self, event):
            engine.command({"quit": True})
            app.quit()
            event.accept()

    window = Mascot()
    window.advance()
    if window.error:
        raise window.error
    window.timer.start()
    result = app.exec()
    window.timer.stop()
    window.bubble.close()
    window.close()
    pixmap.cache_clear()
    if window.error:
        raise window.error
    return result
