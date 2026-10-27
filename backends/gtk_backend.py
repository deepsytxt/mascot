"""Wayland layer-shell adapter with a strictly bounded mouse input region."""

from __future__ import annotations

from functools import lru_cache
import math
import os
from pathlib import Path
import time

from . import BackendUnavailable
from .style import BUBBLE_BACKGROUND, BUBBLE_FOREGROUND, BUBBLE_BORDER
from .geometry import (ACTIVITIES, MUSIC_MODES, WorkArea, bubble_position,
                       clipped_rect, inset_workarea, monitor_index)


def run(engine, frames_dir: Path) -> int:
    if not os.environ.get("WAYLAND_DISPLAY"):
        raise BackendUnavailable("GTK backend требует Wayland и compositor с layer-shell. Для X11 используйте --backend qt.")
    os.environ["GDK_BACKEND"] = "wayland"
    try:
                                                                               
                                                                                  
        from ctypes import CDLL, RTLD_GLOBAL
        CDLL("libgtk4-layer-shell.so.0", mode=RTLD_GLOBAL)
        import gi
        gi.require_version("Gtk4LayerShell", "1.0")
        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
        gi.require_version("PangoCairo", "1.0")
        gi.require_foreign("cairo")
                                                                                 
        from gi.repository import Gtk4LayerShell as LS
        from gi.repository import Gdk, Gio, GLib, Gtk, Pango, PangoCairo
        import cairo
    except (ImportError, ValueError, OSError) as exc:
        raise BackendUnavailable(
            "Для GTK backend нужны системные GTK4, PyGObject, pycairo и gtk4-layer-shell. "
            "Создайте venv с --system-site-packages или используйте --backend qt через XWayland."
        ) from exc

    Gtk.init()
    if Gdk.Display.get_default() is None or not LS.is_supported():
        raise BackendUnavailable(
            "Этот Wayland compositor не поддерживает layer-shell. "
            "Используйте --backend qt через XWayland или сессию X11."
        )
    frames_dir = Path(frames_dir)

    @lru_cache(maxsize=128)
    def surface(filename):
        return cairo.ImageSurface.create_from_png(str(frames_dir / filename))

    class Mascot(Gtk.Application):
        def __init__(self):
            super().__init__(application_id="io.deepsy.Mascot", flags=Gio.ApplicationFlags.NON_UNIQUE)
            self.scene = None
            self.area = WorkArea(0, 0, 1, 1)
            self.region = None
            self.error = None
            self.monitor = None
            self.timer_id = None
            self.last_time = time.monotonic()
            self.drag_origin = (0.0, 0.0)
            self.popover = None
            self.monitor_handler = None

        def do_activate(self):
            self.window = Gtk.Window(application=self, title="deepsy")
            self.window.add_css_class("deepsy-mascot")
            self.window.set_decorated(False)
            self.window.set_focusable(False)
            LS.init_for_window(self.window)
            LS.set_namespace(self.window, "deepsy")
            LS.set_layer(self.window, LS.Layer.OVERLAY if engine.cfg.get("layer") == "overlay" else LS.Layer.TOP)
            LS.set_keyboard_mode(self.window, LS.KeyboardMode.NONE)
                                                                                  
            LS.set_exclusive_zone(self.window, 0)
            for edge in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT):
                LS.set_anchor(self.window, edge, True)
            self.monitors = Gdk.Display.get_default().get_monitors()
            self.monitor_handler = self.monitors.connect("items-changed", self.monitors_changed)
            self.monitors_changed()
            css = Gtk.CssProvider()
            css.load_from_data(b"window.deepsy-mascot { background-color: transparent; box-shadow: none; }")
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.canvas = Gtk.DrawingArea()
            self.canvas.set_hexpand(True)
            self.canvas.set_vexpand(True)
            self.canvas.set_cursor_from_name("grab")
            self.canvas.set_draw_func(self.draw)
            self.window.set_child(self.canvas)
            self.window.connect("realize", self.realized)
            self.window.connect("close-request", self.closed)

            drag = Gtk.GestureDrag.new()
            drag.set_button(1)
            drag.connect("drag-begin", self.drag_begin)
            drag.connect("drag-update", self.drag_update)
            drag.connect("drag-end", self.drag_end)
            self.canvas.add_controller(drag)

            motion = Gtk.EventControllerMotion.new()
            motion.connect("motion", self.motion)
            self.canvas.add_controller(motion)
            click = Gtk.GestureClick.new()
            click.set_button(3)
            click.connect("pressed", self.context_menu)
            self.canvas.add_controller(click)
            self.window.set_visible(True)
            fps = max(10, min(120, int(engine.cfg.get("fps", 60))))
            self.timer_id = GLib.timeout_add(round(1000 / fps), self.advance)

        def realized(self, window):
                                                                                   
            window.get_surface().set_input_region(cairo.Region())
            self.region = None

        def monitors_changed(self, *_):
            monitors = [self.monitors.get_item(i) for i in range(self.monitors.get_n_items())]
            index = monitor_index(monitors, engine.cfg.get("monitor", 0),
                                  lambda monitor: monitor.get_connector() or monitor.get_model())
            monitor = monitors[index] if index >= 0 else None
            if monitor != self.monitor:
                self.monitor = monitor
                LS.set_monitor(self.window, monitor)
                self.region = None

        def local_point(self, x, y):
            return self.area.local(x, y)

        def drag_begin(self, gesture, x, y):
            self.drag_origin = x, y
            engine.pointer_press(*self.local_point(x, y), button=1)
            self.canvas.set_cursor_from_name("grabbing")

        def drag_update(self, gesture, dx, dy):
            x, y = self.drag_origin
            engine.pointer_move(*self.local_point(x + dx, y + dy))

        def drag_end(self, gesture, dx, dy):
            x, y = self.drag_origin
            engine.pointer_release(*self.local_point(x + dx, y + dy), button=1)
            self.canvas.set_cursor_from_name("grab")

        def motion(self, controller, x, y):
                                                                                   
                                                                    
            engine.pointer_move(*self.local_point(x, y))

        def context_menu(self, gesture, count, x, y):
            if self.popover is not None:
                self.popover.unparent()
            self.popover = Gtk.Popover()
            self.popover.set_parent(self.canvas)
            pointing = Gdk.Rectangle()
            pointing.x, pointing.y, pointing.width, pointing.height = int(x), int(y), 1, 1
            self.popover.set_pointing_to(pointing)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            for label, activity in ACTIVITIES:
                button = Gtk.Button(label=label)
                button.connect("clicked", self.menu_command, {"activity": activity})
                content.append(button)
            content.append(Gtk.Separator())
            for label, mode in MUSIC_MODES:
                button = Gtk.Button(label=label)
                button.connect("clicked", self.menu_command, {"music_mode": mode})
                content.append(button)
            content.append(Gtk.Separator())
            button = Gtk.Button(label="Закрыть deepsy")
            button.connect("clicked", self.menu_command, {"quit": True})
            content.append(button)
            self.popover.set_child(content)
            self.popover.popup()

        def menu_command(self, button, command):
            self.popover.popdown()
            engine.command(command)

        def closed(self, window):
            engine.command({"quit": True})
            self.quit()
            return False

        def advance(self):
            try:
                now = time.monotonic()
                dt, self.last_time = min(now - self.last_time, 0.1), now
                width, height = self.canvas.get_width(), self.canvas.get_height()
                if width <= 1 or height <= 1:
                    return True
                                                                                
                                                                             
                self.area = inset_workarea(WorkArea(0, 0, width, height),
                                          engine.cfg.get("workarea_insets"))
                engine.resize(self.area.width, self.area.height)
                engine.tick(dt)
                if engine.quit_requested:
                    self.timer_id = None
                    self.quit()
                    return False
                self.scene = engine.frame()
                hx, hy, hw, hh = self.scene["hit"]
                region = clipped_rect((hx + self.area.x, hy + self.area.y, hw, hh), width, height)
                native = self.window.get_surface()
                if native is not None and region != self.region:
                    native.set_input_region(cairo.Region(cairo.RectangleInt(*region)))
                    self.region = region
                self.canvas.queue_draw()
                return True
            except Exception as exc:
                self.error = exc
                self.timer_id = None
                self.quit()
                return False

        def draw(self, area, ctx, width, height):
            if self.scene is None:
                return
            try:
                frame = self.scene
                sprite = surface(frame["file"])
                ctx.save()
                ctx.translate(self.area.x + frame["x"], self.area.y + frame["y"])
                ctx.scale(frame["width"] / sprite.get_width(), frame["height"] / sprite.get_height())
                ctx.set_source_surface(sprite, 0, 0)
                                                                             
                                                                          
                ctx.get_source().set_filter(cairo.FILTER_NEAREST)
                ctx.paint()
                ctx.restore()
                if frame.get("bubble"):
                    self.draw_bubble(ctx, frame)
            except Exception as exc:
                self.error = exc
                self.quit()

        def draw_bubble(self, ctx, frame):
            layout = PangoCairo.create_layout(ctx)
            layout.set_font_description(Pango.FontDescription("Monospace Bold 12"))
            layout.set_text(str(frame["bubble"]), -1)
            layout.set_width(max(1, min(236, self.area.width - 24)) * Pango.SCALE)
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
            text_w, text_h = layout.get_pixel_size()
            width, height = min(self.area.width, text_w + 24), min(self.area.height, text_h + 18)
            x, y = bubble_position(frame["bubble_x"] - width / 2, frame["bubble_y"] - height, width, height,
                                   self.area.width, self.area.height)
            x, y = x + self.area.x, y + self.area.y
            radius = min(3, width / 2, height / 2)
            ctx.new_sub_path()
            for cx, cy, start in ((x + width - radius, y + radius, -math.pi / 2),
                                  (x + width - radius, y + height - radius, 0),
                                  (x + radius, y + height - radius, math.pi / 2),
                                  (x + radius, y + radius, math.pi)):
                ctx.arc(cx, cy, radius, start, start + math.pi / 2)
            ctx.close_path()
            ctx.set_source_rgb(*(int(BUBBLE_BACKGROUND[i:i + 2], 16) / 255 for i in (1, 3, 5)))
            ctx.fill_preserve()
            ctx.set_source_rgb(*(int(BUBBLE_FOREGROUND[i:i + 2], 16) / 255 for i in (1, 3, 5)))
            ctx.set_line_width(BUBBLE_BORDER)
            ctx.stroke()
            ctx.save()
            ctx.rectangle(x + 2, y + 2, max(0, width - 4), max(0, height - 4))
            ctx.clip()
            ctx.move_to(x + 12, y + 9)
            ctx.set_source_rgb(*(int(BUBBLE_FOREGROUND[i:i + 2], 16) / 255 for i in (1, 3, 5)))
            PangoCairo.show_layout(ctx, layout)
            ctx.restore()

        def do_shutdown(self):
            if self.timer_id is not None:
                GLib.source_remove(self.timer_id)
            if self.monitor_handler is not None:
                self.monitors.disconnect(self.monitor_handler)
            if self.popover is not None:
                self.popover.unparent()
            surface.cache_clear()
            Gtk.Application.do_shutdown(self)

    app = Mascot()
    result = app.run([])
    if app.error:
        raise app.error
    return result
