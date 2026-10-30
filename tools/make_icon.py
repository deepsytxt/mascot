                                                                         
from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CANVAS = 128
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def reference_icon() -> Image.Image:
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    dark, white, lime = "#005b3f", "#f4faf5", "#8bc744"
    outer = [(32, 18), (96, 18), (96, 22), (104, 22), (104, 28),
             (110, 28), (110, 36), (116, 36), (116, 94), (110, 94),
             (110, 102), (104, 102), (104, 108), (96, 108), (96, 112),
             (32, 112), (32, 108), (24, 108), (24, 102), (18, 102),
             (18, 94), (12, 94), (12, 36), (18, 36), (18, 28),
             (24, 28), (24, 22), (32, 22)]
    draw.polygon(outer, fill=dark)
    draw.rectangle((25, 28, 103, 101), fill=white)
    draw.rectangle((33, 36, 95, 93), fill=dark)
    draw.rectangle((39, 43, 89, 87), fill=lime)
    for x, y in ((30, 31), (90, 31), (30, 91), (90, 91)):
        draw.rectangle((x, y, x + 5, y + 5), fill=lime)
    bird = [(46, 52), (52, 52), (52, 57), (57, 57), (57, 62),
            (62, 62), (62, 68), (57, 68), (57, 73), (52, 73),
            (52, 78), (46, 78), (46, 73), (50, 73), (50, 68),
            (54, 68), (54, 63), (50, 63), (50, 58), (46, 58)]
    draw.polygon(bird, fill=white)
    draw.rectangle((65, 64, 71, 70), fill=white)
    draw.rectangle((71, 68, 77, 74), fill=white)
    draw.rectangle((77, 72, 83, 78), fill=white)
    draw.rectangle((83, 68, 89, 74), fill=white)
    return image.resize((256, 256), Image.Resampling.NEAREST)


                                                        
head_icon = reference_icon


def build(directory: Path = ROOT / "assets") -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    icon = reference_icon()
    png, ico = directory / "mascot.png", directory / "mascot.ico"
    icon.save(png)
    icon.save(ico, format="ICO", sizes=ICO_SIZES)
    return png, ico


if __name__ == "__main__":
    for path in build():
        print(path)
    sys.exit(0)
