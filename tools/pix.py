"""Перевод арта в настоящую пиксельную сетку: общая палитра, ячейка = CELL пикселей холста."""
import numpy as np
from PIL import Image
from scipy.cluster.vq import kmeans2

CELL = 4
NPAL = 12

def build_palette(items, seed=3):
    px = []
    for it in items.values():
        for k in ('char_img', 'fx_img'):
            a = np.array(it[k]).astype(int); m = a[..., 3] > 250
            c = a[..., :3]
            solid = m.copy()
            for dy, dx in ((1,0),(-1,0),(0,1),(0,-1),(2,0),(-2,0),(0,2),(0,-2)):
                sh = np.roll(np.roll(c, dy, 0), dx, 1)
                solid &= (np.abs(c - sh).sum(-1) < 40)
            px.append(c[solid])
    px = np.concatenate(px).astype(float)
    rng = np.random.default_rng(seed)
    sub = px[rng.choice(len(px), min(60000, len(px)), replace=False)]
    np.random.seed(seed)
    cent, lab = kmeans2(sub, NPAL, minit='++', seed=seed)
    cnt = np.bincount(lab, minlength=NPAL)
    cent = cent[cnt > 0]; cnt = cnt[cnt > 0]
                                                                          
    keep = []
    for i in np.argsort(-cnt):
        for j in keep:
            if np.abs(cent[i] - cent[j]).sum() < 40:
                break
        else:
            keep.append(i)
    cent = cent[keep]
    cent = cent[np.argsort(cent.sum(1))]
    return np.round(cent).astype(np.uint8)

def to_index(img, pal, yoff, xoff, gh, gw, min_cov=0.40):
    """RGBA холст -> массив индексов палитры (gh, gw), -1 = прозрачно."""
    a = np.array(img).astype(float)
    H, W = a.shape[:2]
    big = np.zeros((gh * CELL, gw * CELL, 4)); 
    ys, xs = max(0, yoff), max(0, xoff)
    sub = a[ys:ys + gh * CELL, xs:xs + gw * CELL]
    big[:sub.shape[0], :sub.shape[1]] = sub
    op = big[..., 3] > 128
    d = ((big[..., None, :3] - pal[None, None].astype(float)) ** 2).sum(-1)
    q = d.argmin(-1)
    q = np.where(op, q, -1)
    out = -np.ones((gh, gw), np.int16)
    for gy in range(gh):
        for gx in range(gw):
            blk = q[gy*CELL:(gy+1)*CELL, gx*CELL:(gx+1)*CELL].ravel()
            o = blk[blk >= 0]
            if len(o) >= min_cov * CELL * CELL:
                out[gy, gx] = np.bincount(o, minlength=len(pal)).argmax()
    return out

def despeckle(g):
    """убрать одиночные клетки-шум: клетка, у которой все 4 соседа одного цвета, а она другая."""
    g = g.copy(); H, W = g.shape
    for y in range(1, H-1):
        for x in range(1, W-1):
            n = [g[y-1,x], g[y+1,x], g[y,x-1], g[y,x+1]]
            if n[0] == n[1] == n[2] == n[3] and g[y,x] != n[0]:
                g[y,x] = n[0]
    return g

def render(g, pal, scale=3):
    H, W = g.shape
    a = np.zeros((H, W, 4), np.uint8)
    m = g >= 0
    a[m, :3] = pal[g[m]]; a[m, 3] = 255
    im = Image.fromarray(a, 'RGBA')
    return im.resize((W*scale, H*scale), Image.NEAREST)
