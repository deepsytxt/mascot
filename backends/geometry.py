                                                                        

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class WorkArea:
    x: int
    y: int
    width: int
    height: int

    def local(self, x: float, y: float) -> tuple[float, float]:
        return x - self.x, y - self.y

    def global_point(self, x: float, y: float) -> tuple[int, int]:
        return round(self.x + x), round(self.y + y)


def inset_workarea(area: WorkArea, insets: dict | None) -> WorkArea:
                                                                               
    insets = insets or {}
    left = min(max(0, int(insets.get("left", 0))), max(0, area.width - 1))
    top = min(max(0, int(insets.get("top", 0))), max(0, area.height - 1))
    right = min(max(0, int(insets.get("right", 0))), max(0, area.width - left - 1))
    bottom = min(max(0, int(insets.get("bottom", 0))), max(0, area.height - top - 1))
    return WorkArea(area.x + left, area.y + top,
                    max(1, area.width - left - right), max(1, area.height - top - bottom))


def clipped_rect(rect, width: int, height: int) -> tuple[int, int, int, int]:
                                                                            
    x, y, w, h = rect
    left = max(0, min(width, math.floor(x)))
    top = max(0, min(height, math.floor(y)))
    right = max(left, min(width, math.ceil(x + max(0, w))))
    bottom = max(top, min(height, math.ceil(y + max(0, h))))
    return left, top, right - left, bottom - top


def bubble_position(x: float, y: float, width: int, height: int,
                    area_width: int, area_height: int) -> tuple[int, int]:
    return (round(max(0, min(x, area_width - width))),
            round(max(0, min(y, area_height - height))))


def monitor_index(monitors, requested, name) -> int:
                                                                                  
    if not monitors:
        return -1
    if isinstance(requested, str) and not requested.isdecimal():
        return next((i for i, monitor in enumerate(monitors)
                     if name(monitor) == requested), 0)
    try:
        index = int(requested)
    except (TypeError, ValueError):
        index = 0
    return index if 0 <= index < len(monitors) else 0


ACTIVITIES = (("Погулять", "walk"), ("Побегать", "sprint"),
              ("Осмотреться", "look"), ("Потянуться", "stretch"),
              ("Зевнуть", "yawn"), ("Спать", "sleep"), ("Проснуться", "wake"))
MUSIC_MODES = (("Танец: автоматически", "auto"),
               ("Танцевать", "on"), ("Не танцевать", "off"))
CHESS_ENTRIES = (("Шахматы: играть / закрыть", "toggle"), ("Шахматы: новая партия", "new"))
