"""Сборка кадров «как в спрайт-редакторе».

Всё живёт на сетке арт-пикселей (CELL пикселей исходного холста = 1 клетка), цвета — из одной палитры.
Никаких масштабирований с размытием: цельный силуэт сгибается непрерывным полем,
наклоны при перетаскивании — RotSprite (scale2x ×8 → поворот → мода), экспорт — целым множителем PX.
Запуск:  cd tools && python3 frames.py      (нужны pillow, numpy, scipy)
Переменная MASCOT_PX — сколько экранных пикселей на клетку (по умолчанию 2).
"""
import json, math, os, shutil
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
import prep, pix, rig

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PX = int(os.environ.get("MASCOT_PX", "2"))
OUT = "../frames"
CELL = pix.CELL

items = prep.load_all()
W, H, BASE = prep.place(items)
PAL = pix.build_palette(items)
YOFF = (BASE + 1) % CELL
XOFF = 2
GH = (BASE + 1 - YOFF) // CELL
GW = (W - XOFF) // CELL
WHITE = int(np.argmax(PAL.sum(1)))
LT = (BASE - 40 - YOFF) // CELL                               

                                                                               
def to_cell(v, off): return int((v - off) // CELL)

for n, it in items.items():
    it['g'] = pix.despeckle(pix.despeckle(pix.to_index(it['char_img'], PAL, YOFF, XOFF, GH, GW)))
    f = pix.to_index(it['fx_img'], PAL, YOFF, XOFF, GH, GW, min_cov=0.30)
    lab, k = ndi.label(f >= 0, structure=np.ones((3, 3)))
    comps = []
    for i in range(1, k + 1):
        ys, xs = np.where(lab == i)
        if len(ys) < 3: continue
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        a = np.where(lab[y0:y1, x0:x1] == i, f[y0:y1, x0:x1], -1).astype(np.int16)
        comps.append(dict(a=a, x=int(x0), y=int(y0), cx=(x0 + x1) / 2, cy=(y0 + y1) / 2))
    comps.sort(key=lambda c: (c['y'], c['x']))
    if comps:
        gx = sum(c['cx'] for c in comps) / len(comps); gy = sum(c['cy'] for c in comps) / len(comps)
        for c in comps: c['gx'], c['gy'] = gx, gy
    it['comps'] = comps
    it['S'] = int(round((it['split_c'] - YOFF) / CELL))
    it['fcol'] = (it['ox'] + it['fcx'] - XOFF) / CELL
    fc = it['face']
    if fc:
        sx0, sy0, sx1, sy1 = fc['screen']
        fc['screen_g'] = (to_cell(sx0, XOFF), to_cell(sy0, YOFF), to_cell(sx1, XOFF), to_cell(sy1, YOFF))
        fc['glyphs_g'] = [(to_cell(a, XOFF), to_cell(b, YOFF), to_cell(c, XOFF), to_cell(d, YOFF)) for a, b, c, d in fc['glyphs']]
        col = np.array(fc['color'], float)
        fc['scol'] = int(((PAL.astype(float) - col) ** 2).sum(1).argmin())

                                                                               
def blank(h=GH, w=GW): return np.full((h, w), -1, np.int16)

def paste(dst, src, x, y):
    h, w = src.shape
    y0, x0 = max(0, y), max(0, x); y1, x1 = min(dst.shape[0], y + h), min(dst.shape[1], x + w)
    if y0 >= y1 or x0 >= x1: return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    d = dst[y0:y1, x0:x1]
    d[s >= 0] = s[s >= 0]


def head_rect(it):
                                                                           
                                                                         
    _, sy0, _, sy1 = it['face']['screen_g']
    row = it['g'][(sy0 + sy1) // 2]
    xs = np.flatnonzero(row >= 0)
    ys = np.where(it['g'] >= 0)[0]
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), it['S'] + 2


HEAD_RECT = head_rect(items['calm'])
CENTER = int(round(items['calm']['fcol']))
for it in items.values():
    it['g'], map_x, map_y = rig.normalize_pose(
        it['g'], source_head=head_rect(it), target_head=HEAD_RECT,
        hips=LT, center=CENTER,
    )
    it['S'] = HEAD_RECT[3]
    it['fcol'] = CENTER
    fc = it['face']
    def map_rect(rect):
        a, b, c, d = rect
        return tuple(int(round(v)) for v in (map_x(a), map_y(b), map_x(c), map_y(d)))
    fc['screen_g'] = map_rect(fc['screen_g'])
    fc['glyphs_g'] = [map_rect(rect) for rect in fc['glyphs_g']]


def bounds(grid):
    ys, xs = np.where(grid >= 0)
    if not len(xs):
        return [0, 0, 0, 0]
    return [int(xs.min()) * PX, int(ys.min()) * PX,
            int(xs.max() + 1) * PX, int(ys.max() + 1) * PX]


BODY_BOUNDS = {}

_face_cache = {}
def face_grid(it, mode='normal', dx=0, dy=0, s=7):
    key = (id(it), mode, dx, dy, s)
    if key in _face_cache: return _face_cache[key]
    g = it['g'].copy(); fc = it['face']; col = fc['scol']
    sx0, sy0, sx1, sy1 = fc['screen_g']; gl = fc['glyphs_g']
    crops = [g[b:d + 1, a:c + 1].copy() for a, b, c, d in gl]
    for a, b, c, d in gl:
        g[max(sy0, b - 1):min(sy1, d + 1) + 1, max(sx0, a - 1):min(sx1, c + 1) + 1] = col
    ax0 = min(a for a, _, _, _ in gl); ax1 = max(c for _, _, c, _ in gl)
    ay0 = min(b for _, b, _, _ in gl); ay1 = max(d for _, _, _, d in gl)
    dx = max(sx0 + 2 - ax0, min(sx1 - 2 - ax1, dx)); dy = max(sy0 + 2 - ay0, min(sy1 - 2 - ay1, dy))
    for k, ((a, b, c, d), cr) in enumerate(zip(gl, crops)):
        if k == 0 and mode == 'blink':
            yc = (b + d) // 2
            g[yc - 1:yc + 1, a + 1:c] = WHITE
            continue
        if k == 0 and mode == 'o':
            cx, cy = (a + c) // 2, (b + d) // 2; r = s // 2; t = 1 if s <= 5 else 2
            g[cy - r:cy + r + 1, cx - r:cx + r + 1] = WHITE
            g[cy - r + t:cy + r + 1 - t, cx - r + t:cx + r + 1 - t] = col
            continue
        paste(g, cr, a + dx, b + dy)
    _face_cache[key] = g
    return g

def compose(it, sq=0, y=0, x=0, hdx=0, hdy=0, bx=0, face=None, fx=None, hands=(0, 0), base_g=None):
    """sq — на сколько строк торс выше/ниже нормы (+ вытянулся, − присел); y/x — сдвиг всего;
    hdx/hdy — голова относительно торса; bx — торс относительно ног; hands — (лев, прав) сдвиг кистей по вертикали."""
    g = base_g if base_g is not None else (face_grid(it, **face) if face else it['g'])
    out = rig.deform(g, neck=it['S'], hips=LT, center=CENTER,
                     squash=sq, head_x=hdx, head_y=hdy, torso_x=bx,
                     x=x, y=y, hands=hands)
    BODY_BOUNDS[id(out)] = bounds(out)
    if fx:
        for c, op in zip(it['comps'], fx):
            ddx, ddy, vis = op[:3]
            if vis: paste(out, c['a'], c['x'] + ddx + x, c['y'] + ddy + y)
    return out

def radial(c, r):
    vx, vy = c['cx'] - c['gx'], c['cy'] - c['gy']; l = math.hypot(vx, vy) or 1
    return int(round(vx / l * r)), int(round(vy / l * r))

clips = {}
def clip(name, frames, durs, loop=False, nxt=None, **extra):
    if isinstance(durs, int): durs = [durs] * len(frames)
    assert len(frames) == len(durs), (name, len(frames), len(durs))
    clips[name] = dict(frames=frames, durs=list(durs), loop=loop, next=nxt, **extra)

                                                                               
def calm():
    c = items['calm']
                                        
    seq = [dict(), dict(sq=1), dict(sq=1, hands=(-1, -1)), dict(), dict(sq=-1), dict(sq=-1, hdy=0), dict()]
    seq = [dict(), dict(sq=1), dict(sq=1), dict(), dict(sq=-1), dict(sq=-1), dict()]
    clip('calm', [compose(c, **k) for k in seq], [900, 420, 700, 160, 300, 380, 700], loop=True)
    blink = [dict(face=dict(mode='blink'))]
    clip('calm_blink', [compose(c, face=dict(mode='blink'), sq=0), compose(c, face=dict(mode='blink'), sq=0), compose(c)], [90, 110, 60])

def joy():
    it = items['joy']
    P = [dict(sq=-2, y=0, r=0, v=1), dict(sq=-3, y=0, r=0, v=1), dict(sq=1, y=-5, r=2, v=1),
         dict(sq=2, y=-10, r=4, v=1), dict(sq=1, y=-10, r=5, v=0), dict(sq=0, y=-6, r=4, v=1),
         dict(sq=-3, y=0, r=1, v=1), dict(sq=1, y=0, r=0, v=1), dict(sq=0, y=0, r=0, v=1)]
    fr = []
    for i, p in enumerate(P):
        fx = []
        for k, c in enumerate(it['comps']):
            dx, dy = radial(c, p['r']); fx.append((dx, dy + p['y'], (i + k) % 3 != 0 and p['v'] or (i % 2)))
        fr.append(compose(it, sq=p['sq'], y=p['y'], fx=fx))
    clip('joy', fr, [140, 90, 70, 90, 120, 90, 100, 90, 220], loop=True)

def anger():
    it = items['anger']
    P = [(0, 0, 0), (-1, 1, 1), (1, 0, 0), (-1, 1, 1), (1, 0, 0), (0, 1, 1), (0, 0, 0), (0, 0, 0), (0, 0, 0)]
    fr = []
    for i, (dx, hdy, r) in enumerate(P):
        fx = [(radial(c, r)[0], radial(c, r)[1], 1) for c in it['comps']]
        fr.append(compose(it, x=dx, hdy=hdy, fx=fx))
    clip('anger', fr, [160, 55, 55, 55, 55, 90, 140, 380, 260], loop=True)

def sad():
    it = items['sad']
    P = [(0, 0, 0, 1), (1, 1, 1, 1), (2, 1, 3, 1), (3, 2, 6, 1), (3, 2, 10, 1), (3, 2, 0, 0), (2, 1, 0, 0), (1, 0, 0, 0)]
    fr = [compose(it, sq=-s, hdy=h, fx=[(0, d, v) for _ in it['comps']]) for s, h, d, v in P]
    clip('sad', fr, [700, 420, 260, 200, 170, 900, 520, 520], loop=True)

def fear():
    it = items['fear']
    dx = [-1, 1, -1, 1, 0, 1, -1, 1]; yy = [0, -1, 0, 0, -1, 0, -1, 0]
    fr = []
    for i in range(8):
        fx = [(dx[i], 1 if (i + k) % 2 else -1, 1) for k, c in enumerate(it['comps'])]
        fr.append(compose(it, x=dx[i], y=yy[i], fx=fx))
    clip('fear', fr, [50, 45, 60, 45, 55, 50, 70, 45], loop=True)

def surprise():
    it = items['surprise']
    P = [(3, -8, 0, 0), (4, -10, 1, -3), (1, -5, 1, -2), (-2, 0, 1, 0), (-1, 0, 1, 0), (1, 0, 1, 0), (0, 0, 1, 0)]
    fr = [compose(it, sq=s, y=y, fx=[(0, d + (y if v else 0) // 2, v) for _ in it['comps']]) for s, y, v, d in P]
    clip('surprise_in', fr, [60, 70, 80, 80, 90, 80, 90])
    fr = [compose(it, sq=0, fx=[(0, 0, 1) for _ in it['comps']]), compose(it, sq=0, fx=[(0, -1, 1) for _ in it['comps']]),
          compose(it, sq=0, fx=[(0, 0, 1) for _ in it['comps']]), compose(it, sq=-1, fx=[(0, 0, 0) for _ in it['comps']])]
    clip('surprise', fr, [700, 110, 600, 130], loop=True)

def wink():
    it = items['wink']
    vis = [1, 1, 0, 1, 0, 1]
    P = [dict(), dict(sq=-1), dict(sq=-1), dict(sq=0), dict(), dict()]
    fr = [compose(it, fx=[(0, 0, vis[i]) for _ in it['comps']], **P[i]) for i in range(6)]
    clip('wink', fr, [400, 180, 130, 180, 150, 600], loop=True)

def tired():
    it = items['tired']
    sq = [0, 0, -1, -2, -2, -2, -2, -1, 0, 0]; hdy = [0, 0, 1, 2, 3, 3, 3, 2, 1, 0]
    fr = []
    for i in range(10):
        fx = []
        for k, c in enumerate(it['comps']):
            if k == 1: fx.append((0, -i // 2, 1 if i <= 6 else 0))
            else:      fx.append((0, -(i - 2) // 2, 1 if i >= 2 else 0))
        fr.append(compose(it, sq=sq[i], hdy=hdy[i] - 1 if hdy[i] else 0, fx=fx))
    clip('tired', fr, [600, 500, 450, 500, 700, 800, 600, 500, 450, 500], loop=True)

def confused():
    it = items['confused']
    xo = [0, 1, 1, 2, 2, 1, 0, -1, -1, -2, -2, -1]; qy = [0, 0, -1, -1, 0, 0, 0, 0, -1, -1, 0, 0]
    sq = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    fr = [compose(it, sq=sq[i], hdx=xo[i] // 2 if i % 2 == 0 else xo[i] // 2, fx=[(-(xo[i] // 2), qy[i], 1) for _ in it['comps']]) for i in range(12)]
    clip('confused', fr, [260, 140, 140, 360, 140, 140, 260, 140, 140, 360, 140, 140], loop=True)

                                                                                    
def scale2x(a):
    p = np.pad(a, 1, constant_values=-1)
    A, B, C, D = p[:-2, 1:-1], p[1:-1, 2:], p[1:-1, :-2], p[2:, 1:-1]
    P = a
    o1 = np.where((C == A) & (C != D) & (A != B), A, P); o2 = np.where((A == B) & (A != C) & (B != D), B, P)
    o3 = np.where((D == C) & (D != B) & (C != A), C, P); o4 = np.where((B == D) & (B != A) & (D != C), D, P)
    out = np.empty((a.shape[0] * 2, a.shape[1] * 2), a.dtype)
    out[0::2, 0::2] = o1; out[0::2, 1::2] = o2; out[1::2, 0::2] = o3; out[1::2, 1::2] = o4
    return out

def rotsprite(src, pivot, deg, R):
    """src (h,w) индексы, pivot (col,row) в клетках, deg — угол (+ = тело отклонилось вправо), R — радиус холста в клетках."""
    big = src
    for _ in range(3): big = scale2x(big)                     
    S = 8
    th = math.radians(deg); c, s = math.cos(th), math.sin(th)
    n = 2 * R * S
    v, u = np.mgrid[0:n, 0:n]
    dx = u - R * S - S / 2; dy = v - R * S - S / 2
    sx = c * dx - s * dy + pivot[0] * S + S / 2
    sy = s * dx + c * dy + pivot[1] * S + S / 2
    ix = np.floor(sx).astype(int); iy = np.floor(sy).astype(int)
    ok = (ix >= 0) & (ix < big.shape[1]) & (iy >= 0) & (iy < big.shape[0])
    rot = np.full((n, n), -1, np.int16); rot[ok] = big[iy[ok], ix[ok]]
    blk = rot.reshape(2 * R, S, 2 * R, S).transpose(0, 2, 1, 3).reshape(2 * R, 2 * R, S * S)
    cnt = np.stack([(blk == k).sum(-1) for k in range(len(PAL))], -1)
    opq = cnt.sum(-1)
    out = np.where(opq >= S * S * 0.45, cnt.argmax(-1), -1).astype(np.int16)
    return out

ROT_STEP = 3; ROT_MAX = 66

def held_sets():
    base_hang = compose(items['surprise'], sq=1)
    base_flail = compose(items['joy'], sq=1)
    ys, xs = np.where(base_hang >= 0)
    top = ys.min(); fcol = items['calm']['fcol']
    pivot = (int(round(fcol)), int(top + 9))                                               
    far = max(math.hypot(x - pivot[0], y - pivot[1]) for y, x in ((ys.max(), xs.min()), (ys.max(), xs.max()), (ys.min(), xs.min()), (ys.min(), xs.max())))
    R = int(math.ceil(far)) + 3
    sets = {}
    for name, base in (('hang', base_hang), ('flail', base_flail)):
        lst = []
        for deg in range(-ROT_MAX, ROT_MAX + 1, ROT_STEP):
            g = rotsprite(base, pivot, deg, R)
            yy, xx = np.where(g >= 0)
            y0, y1, x0, x1 = yy.min(), yy.max() + 1, xx.min(), xx.max() + 1
            lst.append(dict(deg=deg, g=g[y0:y1, x0:x1], ax=R - x0, ay=R - y0))                                                
        sets[name] = lst
    feet_dy = (GH - pivot[1])                                                                       
    return sets, pivot, feet_dy

                                                                                
def physics():
    fe = items['fear']
    fr = []
    for i in range(6):
        dx = [-1, 1, -1, 1, 0, 1][i]
        fr.append(compose(fe, x=dx, sq=1, fx=[(dx, 1 if (i + k) % 2 else -1, 1) for k, _ in enumerate(fe['comps'])]))
    clip('fall', fr, [55, 55, 55, 55, 55, 55], loop=True)
    c = items['calm']
    clip('land', [compose(c, sq=-5), compose(c, sq=-4), compose(c, sq=-2), compose(c, sq=1), compose(c, sq=0)], [80, 70, 80, 90, 120])
    sp = items['surprise']
    clip('land_hard', [compose(sp, sq=-8, fx=[(0, 0, 1) for _ in sp['comps']]), compose(sp, sq=-8, fx=[(0, 0, 1) for _ in sp['comps']]),
                       compose(sp, sq=-6, fx=[(0, 0, 1) for _ in sp['comps']]), compose(sp, sq=-3, fx=[(0, 0, 1) for _ in sp['comps']]),
                       compose(sp, sq=2, fx=[(0, -1, 1) for _ in sp['comps']]), compose(sp, sq=0)],
         [130, 220, 110, 90, 90, 140])

                                                                                          
def walk_frame(it, ph, d, A=4, lift=2, bob=1, sway=1, lean=0, arms=1):
    steps = []
    for leg in (0, 1):
        phi = (ph + 0.5 * leg) % 1.0
        if phi < 0.5: off = A - 2 * A * (phi / 0.5); up = 0                                                       
        else:
            t = (phi - 0.5) / 0.5; e = t * t * (3 - 2 * t)
            off = -A + 2 * A * e; up = int(round(lift * math.sin(math.pi * t)))
        steps.append((d * off, up))
    sq = -int(round(bob * (1 + math.cos(4 * math.pi * ph)) / 2))
    sx = int(round(-sway * math.sin(2 * math.pi * ph)))
    ha = int(round(arms * math.sin(2 * math.pi * ph)))
    face = dict(mode='normal', dx=2 * d, dy=0)
    out = rig.deform(face_grid(it, **face), neck=it['S'], hips=LT,
                     center=CENTER, squash=sq, head_x=sx + lean,
                     torso_x=lean, hands=(ha, -ha), steps=steps)
    BODY_BOUNDS[id(out)] = bounds(out)
    return out

def locomotion():
    c = items['calm']; N = 8
    for tag, d in (('r', 1), ('l', -1)):
        fr = [walk_frame(c, p / N, d) for p in range(N)]
        clip(f'walk_{tag}', fr, [100] * N, loop=True, stride=2 * 2 * 4 * PX)                                     
        fr = [walk_frame(c, p / N, d, A=6, lift=3, bob=2, sway=1, lean=d, arms=2) for p in range(N)]
        clip(f'sprint_{tag}', fr, [60] * N, loop=True, stride=2 * 2 * 6 * PX)
    clip('walk_end', [compose(c, sq=-1), compose(c, sq=0)], [110, 130])
    clip('walk_start', [compose(c, sq=-1, hdx=1), compose(c, sq=0)], [70, 60])

def idles():
    c, j = items['calm'], items['joy']
    seq = [(0, 0, 0), (-3, 0, -1), (-5, 0, -1), (-5, 0, -1), (-2, 0, 0), (0, 0, 0), (3, 0, 1), (5, 0, 1), (5, 0, 1), (2, 0, 0), (0, -2, 0), (0, -2, 0), (0, 0, 0)]
    clip('look', [compose(c, hdx=h, face=dict(mode='normal', dx=a, dy=b)) for a, b, h in seq],
         [250, 120, 160, 700, 130, 220, 120, 160, 700, 130, 160, 600, 200])
    st = [dict(it=c), dict(it=c, sq=-2), dict(it=j, sq=1, y=-1), dict(it=j, sq=2, y=-3, face=dict(mode='blink')),
          dict(it=j, sq=3, y=-4, face=dict(mode='blink')), dict(it=j, sq=3, y=-4, face=dict(mode='blink'), x=1),
          dict(it=j, sq=3, y=-4, face=dict(mode='blink'), x=-1), dict(it=j, sq=1, y=-1), dict(it=c, sq=-1), dict(it=c)]
    clip('stretch', [compose(k.pop('it'), **k) for k in [dict(x) for x in st]], [200, 160, 120, 140, 500, 70, 70, 160, 200, 200])
    yw = [dict(), dict(face=dict(mode='o', s=5)), dict(face=dict(mode='o', s=7), sq=1), dict(face=dict(mode='o', s=9), sq=2),
          dict(face=dict(mode='o', s=9), sq=3), dict(face=dict(mode='o', s=9), sq=3), dict(face=dict(mode='o', s=7), sq=1),
          dict(face=dict(mode='o', s=5)), dict(face=dict(mode='blink')), dict(face=dict(mode='blink'), sq=-1), dict(face=dict(mode='blink'), sq=-2), dict()]
    clip('yawn', [compose(c, **k) for k in yw], [220, 160, 200, 260, 900, 450, 220, 180, 260, 300, 380, 300])
    xs = [-2, -1, 0, 1, 2, 1, 0, -1]; ys = [0, -2, -3, -2, 0, -2, -3, -2]; sq = [-1, 1, 1, 1, -1, 1, 1, 1]
    fr = []
    for i in range(8):
        r = 2 if i % 2 else 4
        fx = [(radial(k, r)[0], radial(k, r)[1], 1 if (i + n) % 3 else 0) for n, k in enumerate(j['comps'])]
        fr.append(compose(j, sq=sq[i], x=xs[i], y=ys[i], bx=-xs[i] // 2, hdx=xs[i] // 2, fx=fx))
    clip('dance', fr, [150, 110, 90, 110, 150, 110, 90, 110], loop=True)
                                                                        
    fr = [compose(c, hdx=dx, face=dict(mode=mode))
          for dx, mode in ((0, 'normal'), (0, 'blink'), (-1, 'blink'),
                           (-1, 'blink'), (0, 'blink'), (1, 'blink'),
                           (1, 'blink'), (0, 'normal'))]
    clip('pet', fr, [140, 200, 180, 280, 220, 180, 280, 220], loop=True)

                                                                                      
DUST = [(74, 124, 84), (196, 218, 186), (236, 244, 228)]
def dust_clip(r_scale, spread, n, rad):
    B = 2                                                                
    DW, DH = 90, 22; AX, AY = DW // 2, DH - 2                                                     
    frames = []
    for t in range(n):
        cells = set()
        for side in (-1, 1):
            for bx, by, k in ((0, 0, 1.0), (4, -3, .65), (-3, -2, .55)):
                cxp = AX + side * (9 + t * spread + bx); cyp = AY - 3 - t * 0.5 + by
                r = rad[t] * r_scale * k
                for gx in range(int(cxp - r) - 1, int(cxp + r) + 2):
                    for gy in range(int(cyp - r) - 1, int(cyp + r) + 2):
                        if (gx + .5 - cxp) ** 2 + (gy + .5 - cyp) ** 2 <= r * r and gy <= AY and 0 <= gx < DW and 0 <= gy < DH:
                            cells.add((gx, gy))
        full = cells
        if t >= n - 3:                                                                               
            lvl = t - (n - 3)
            if lvl == 0: cells = {c for c in cells if (c[0] + c[1]) % 3 != 0}
            elif lvl == 1: cells = {c for c in cells if (c[0] + c[1]) % 2 == 0}
            else: cells = {c for c in cells if c[0] % 2 == 0 and c[1] % 2 == 0}
        g = blank(DH, DW)
        for gx, gy in cells:
            edge = any((gx + i, gy + j) not in full for i, j in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if edge: g[gy, gx] = 100
            elif (gx, gy + 1) not in full or (gx, gy + 2) not in full: g[gy, gx] = 101
            else: g[gy, gx] = 102
        frames.append(g)
    return frames, (DW, DH, AX, AY)

def render_dust(g):
    h, w = g.shape; a = np.zeros((h, w, 4), np.uint8)
    for k, col in enumerate(DUST):
        m = g == 100 + k; a[m, :3] = col; a[m, 3] = 255
    return Image.fromarray(a, 'RGBA').resize((w * 2 * PX, h * 2 * PX), Image.NEAREST)

                                                                                
for f_ in (calm, joy, anger, sad, fear, surprise, wink, tired, confused, physics, locomotion, idles): f_()
rot_sets, PIVOT, FEET_DY = held_sets()

shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
def save(g, fn):
    im = pix.render(g, PAL, PX); im.save(os.path.join(OUT, fn)); return im

cal = items['calm']
allg = [it['g'] for it in items.values()]
ys = np.concatenate([np.where(g >= 0)[0] for g in allg]); xs = np.concatenate([np.where(g >= 0)[1] for g in allg])
hit = [(xs.min() - 1) * PX, (ys.min() - 1) * PX, (xs.max() + 2) * PX, GH * PX]
meta = {'version': 2, 'size': [GW * PX, GH * PX], 'feet': [CENTER * PX, GH * PX], 'hit': hit, 'px': PX,
        'head': [v * PX for v in HEAD_RECT],
        'pivot': [PIVOT[0] * PX + PX // 2, PIVOT[1] * PX + PX // 2], 'feet_dy': FEET_DY * PX - PX // 2,
        'bounds': {}, 'body_bounds': {}, 'clips': {}}
for name, c in clips.items():
    files = []
    for i, g in enumerate(c['frames']):
        fn = f'{name}_{i:02d}.png'; save(g, fn); files.append(fn)
        meta['bounds'][fn] = bounds(g)
        meta['body_bounds'][fn] = BODY_BOUNDS[id(g)]
    meta['clips'][name] = dict(durs=c['durs'], loop=c['loop'], frames=files, next=c['next'], **({'stride': c['stride']} if 'stride' in c else {}))
meta['rot'] = {'step': ROT_STEP, 'max': ROT_MAX, 'sets': {}}
for name, lst in rot_sets.items():
    out = []
    for e in lst:
        fn = f'rot_{name}_{e["deg"]:+03d}.png'; save(e['g'], fn)
        meta['bounds'][fn] = bounds(e['g'])
        out.append(dict(f=fn, ax=e['ax'] * PX + PX // 2, ay=e['ay'] * PX + PX // 2, w=e['g'].shape[1] * PX, h=e['g'].shape[0] * PX))
    meta['rot']['sets'][name] = out
meta['fx'] = {}
for name, args, dur in (('dust', (1.0, 3, 6, [3, 5, 6.5, 7, 7, 6.5]), [60, 70, 90, 110, 120, 140]),
                        ('dust_s', (0.6, 2, 4, [3, 5, 5.5, 5]), [60, 80, 100, 120])):
    frs, (dw, dh, ax, ay) = dust_clip(*args); files = []
    for i, g in enumerate(frs):
        fn = f'{name}_{i:02d}.png'; render_dust(g).save(os.path.join(OUT, fn)); files.append(fn)
    meta['fx'][name] = dict(durs=dur, frames=files, size=[dw * 2 * PX, dh * 2 * PX], anchor=[ax * 2 * PX, ay * 2 * PX + 2 * PX])
json.dump(meta, open(os.path.join(OUT, 'animations.json'), 'w'), indent=1, default=int)
print('grid', GH, GW, 'frame px', GW * PX, GH * PX, 'pivot', PIVOT, 'feet_dy', FEET_DY)
print({k: len(v['frames']) for k, v in clips.items()})

                                                                                
bg = (24, 24, 30); fw, fh = GW * PX, GH * PX
def strip(names, maxn=12):
    rows = []
    for n in names:
        c = meta['clips'][n]; fl = c['frames'][:maxn]
        s = Image.new('RGB', (fw * maxn, fh), bg)
        for i, f in enumerate(fl):
            im = Image.open(os.path.join(OUT, f)); s.paste(im, (i * fw, 0), im)
        rows.append(s)
    sh = Image.new('RGB', (fw * maxn, fh * len(rows)), bg)
    for i, r in enumerate(rows): sh.paste(r, (0, i * fh))
    return sh
strip(['calm', 'joy', 'anger', 'sad', 'fear', 'surprise_in', 'wink', 'tired', 'confused']).save('dbg_strips.png')
strip(['walk_r', 'walk_l', 'sprint_r', 'look', 'stretch', 'yawn', 'dance', 'land', 'land_hard', 'fall']).save('dbg_strips2.png')


def animation_preview(names, path):
    frames, durations = [], []
    from PIL import ImageDraw
    for name in names:
        for filename, duration in zip(meta['clips'][name]['frames'], meta['clips'][name]['durs']):
            canvas = Image.new('RGB', (fw + 32, fh + 36), bg)
            draw = ImageDraw.Draw(canvas)
            draw.text((8, 6), name, fill=(210, 224, 214))
            draw.line((0, fh + 22, fw + 32, fh + 22), fill=(77, 91, 83))
            with Image.open(os.path.join(OUT, filename)) as sprite:
                canvas.paste(sprite, (16, 22), sprite)
            frames.append(canvas)
            durations.append(duration)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, disposal=2)


animation_preview(['calm', 'walk_r', 'walk_r', 'sprint_r', 'sprint_r',
                   'joy', 'surprise', 'wink', 'pet', 'dance', 'dance', 'look'], '../preview.gif')

os.makedirs('../previews', exist_ok=True)
review_rows = [
    ('Idle', [('calm', i) for i in range(7)]),
    ('Walk', [('walk_r', i) for i in range(8)]),
    ('Sprint', [('sprint_r', i) for i in range(8)]),
    ('Reactions', [(name, 0) for name in ('calm', 'joy', 'anger', 'sad', 'fear', 'surprise', 'wink', 'tired')]),
    ('Petting', [('pet', i) for i in range(8)]),
    ('Dance', [('dance', i) for i in range(8)]),
]
sheet = Image.new('RGB', (fw * 8 + 96, (fh + 24) * len(review_rows)), bg)
draw = ImageDraw.Draw(sheet)
for row, (label, cells) in enumerate(review_rows):
    offset_y = row * (fh + 24)
    draw.text((8, offset_y + 12), label, fill=(210, 224, 214))
    draw.line((96, offset_y + fh, sheet.width, offset_y + fh), fill=(77, 91, 83))
    for col, (name, frame) in enumerate(cells):
        with Image.open(os.path.join(OUT, meta['clips'][name]['frames'][frame])) as sprite:
            sheet.paste(sprite, (96 + col * fw, offset_y), sprite)
sheet.save('../previews/contact_sheet.png')

                                                                             
                                                                            
swing = []
from PIL import ImageDraw
for index in list(range(0, len(rot_sets['hang']), 2)) + list(range(len(rot_sets['hang']) - 1, 0, -2)):
    entry = meta['rot']['sets']['hang'][index]
    canvas = Image.new('RGB', (320, 260), bg)
    with Image.open(os.path.join(OUT, entry['f'])) as sprite:
        canvas.paste(sprite, (160 - entry['ax'], 64 - entry['ay']), sprite)
    ImageDraw.Draw(canvas).ellipse((158, 62, 162, 66), fill=(230, 196, 116))
    swing.append(canvas)
swing[0].save('../preview_swing.gif', save_all=True, append_images=swing[1:],
              duration=65, loop=0, disposal=2)
