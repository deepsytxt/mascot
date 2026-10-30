   

import numpy as np
from scipy import ndimage as ndi


def smoothstep(value):
    value = np.clip(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def sample(grid, source_y, source_x):
    return ndi.map_coordinates(
        grid, [source_y, source_x], order=0, mode="constant", cval=-1,
        prefilter=False,
    ).astype(np.int16)


def deform(grid, *, neck, hips, center, squash=0, head_x=0, head_y=0,
           torso_x=0, x=0, y=0, hands=(0, 0), steps=None):
       
    height, width = grid.shape
    yy, xx = np.mgrid[:height, :width].astype(float)
    neck_weight = 1.0 - smoothstep((yy - neck) / (hips - neck))
    torso_weight = np.sin(np.pi * np.clip((yy - neck) / (hips - neck), 0, 1))
    dx = head_x * neck_weight + torso_x * torso_weight
    dy = (-squash + head_y) * neck_weight

                                                                              
                                                                             
    arm_y = (smoothstep((yy - neck - 2) / 13)
             * (1 - smoothstep((yy - hips + 2) / 3)))
    for side, motion in enumerate(hands):
        outside = (center - xx if side == 0 else xx - center)
        weight = smoothstep((outside - 10) / 9) * arm_y
        dy += motion * weight

    dx += x
    dy += y

    if steps is not None:
        ankle_weight = smoothstep((yy - (hips - 3)) / (height - hips))
        result = np.full_like(grid, -1)
                                                                           
                                                                         
                                                                         
                                                            
        for side, (stride, lift) in enumerate(steps):
            mask = xx < center if side == 0 else xx >= center
            part = np.where(mask, grid, -1)
            posed = warp_fields(part, dx + stride * ankle_weight,
                                dy - lift * ankle_weight)
            result[posed >= 0] = posed[posed >= 0]
        return result
    return warp_fields(grid, dx, dy)


def warp_fields(grid, dx, dy):
    yy, xx = np.mgrid[:grid.shape[0], :grid.shape[1]].astype(float)
    source_y, source_x = yy - dy, xx - dx
                                                                               
                                                                           
    for _ in range(32):
        offset_x = ndi.map_coordinates(dx, [source_y, source_x], order=1,
                                      mode="nearest", prefilter=False)
        offset_y = ndi.map_coordinates(dy, [source_y, source_x], order=1,
                                      mode="nearest", prefilter=False)
        source_x = (source_x + xx - offset_x) * 0.5
        source_y = (source_y + yy - offset_y) * 0.5
    return sample(grid, source_y, source_x)


def normalize_pose(grid, *, source_head, target_head, hips, center):
       
    sx0, sy0, sx1, sy1 = source_head
    tx0, ty0, tx1, ty1 = target_head
    scale_x = (tx1 - tx0) / (sx1 - sx0)
    source_center = (sx0 + sx1 - 1) / 2
    target_center = (tx0 + tx1 - 1) / 2
                                                                               
    def map_x(value):
        return (np.asarray(value) - source_center) * scale_x + target_center

    source_knots = [-1, sy0 - .5, sy1 - .5, hips - .5, grid.shape[0] - .5]
    target_knots = [-1, ty0 - .5, ty1 - .5, hips - .5, grid.shape[0] - .5]

    def map_y(value):
        return np.interp(value, source_knots, target_knots)

    yy, xx = np.mgrid[:grid.shape[0], :grid.shape[1]].astype(float)
    source_y = np.interp(yy, target_knots, source_knots)
    source_x = (xx - target_center) / scale_x + source_center
    return sample(grid, source_y, source_x), map_x, map_y
