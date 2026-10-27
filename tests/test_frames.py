"""Regression checks for the shipped art, independent of generator internals."""

import json
from pathlib import Path

from PIL import Image
import pytest


FRAME_DIR = Path(__file__).resolve().parents[1] / "frames"
META = json.loads((FRAME_DIR / "animations.json").read_text())


def alpha(filename):
    with Image.open(FRAME_DIR / filename) as image:
        assert image.mode == "RGBA", filename
        return image.getchannel("A")


def test_every_frame_has_exact_visible_bounds_and_hard_pixel_alpha():
    files = {f for clip in META["clips"].values() for f in clip["frames"]}
    files.update(entry["f"] for entries in META["rot"]["sets"].values() for entry in entries)
    assert set(META["bounds"]) == files
    for filename in files:
        mask = alpha(filename)
        assert list(mask.getbbox()) == META["bounds"][filename], filename
        assert set(mask.getdata()) <= {0, 255}, filename


def test_common_canvas_and_support_foot_stays_on_floor():
    assert META["feet"][1] == META["size"][1]
    grounded = ("calm", "calm_blink", "walk_l", "walk_r", "sprint_l", "sprint_r",
                "walk_start", "walk_end", "look", "yawn", "pet", "land", "land_hard")
    for clip in META["clips"].values():
        assert len(clip["frames"]) == len(clip["durs"])
        assert all(duration > 0 for duration in clip["durs"])
        for filename in clip["frames"]:
            assert list(alpha(filename).size) == META["size"], filename
    for name in grounded:
        for filename in META["clips"][name]["frames"]:
            assert META["body_bounds"][filename][3] == META["feet"][1], filename


def component_sizes(mask):
                                                                               
                                                                           
    scale = META["px"]
    width, height = mask.size
    pixels = mask.load()
    remaining = {(x // scale, y // scale)
                 for y in range(0, height, scale)
                 for x in range(0, width, scale) if pixels[x, y]}
    sizes = []
    while remaining:
        queue = [remaining.pop()]
        count = 0
        while queue:
            x, y = queue.pop()
            count += 1
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbor = (x + dx, y + dy)
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        queue.append(neighbor)
        sizes.append(count)
    return sizes


@pytest.mark.parametrize("name", ["calm", "calm_blink", "walk_l", "walk_r",
                                  "sprint_l", "sprint_r", "look", "yawn", "pet"])
def test_locomotion_and_idle_have_no_detached_body_parts(name):
    for filename in META["clips"][name]["frames"]:
        assert len(component_sizes(alpha(filename))) == 1, filename


def test_head_width_does_not_shrink_between_reactions_and_drag():
    head_width = META["head"][2] - META["head"][0]
    head_height = META["head"][3] - META["head"][1]
    names = ("calm", "joy", "anger", "sad", "fear", "surprise", "wink", "tired",
             "confused", "walk_r", "sprint_r", "pet")
    for name in names:
        for filename in META["clips"][name]["frames"]:
                                                                              
                                                                             
            mask = alpha(filename)
            top = META["body_bounds"][filename][1]
            row = mask.crop((0, top + head_height // 2, mask.width, top + head_height // 2 + 1))
            runs = []
            length = 0
            for value in row.getdata():
                if value:
                    length += 1
                elif length:
                    runs.append(length)
                    length = 0
            runs.append(length)
            assert max(runs) == head_width, filename
    for entries in META["rot"]["sets"].values():
        upright = entries[META["rot"]["max"] // META["rot"]["step"]]
        mask = alpha(upright["f"])
        row = mask.crop((0, head_height // 2, mask.width, head_height // 2 + 1))
        box = row.getbbox()
        assert box[2] - box[0] == head_width, upright["f"]
