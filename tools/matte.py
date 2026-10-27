"""Stage 1: чистое вырезание фона + разделение на персонажа и эффекты."""
from PIL import Image
import numpy as np
from scipy import ndimage as ndi

import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'source.png')
NAMES = ['calm','joy','anger','sad','fear','surprise','wink','tired','confused']
COLS = [(0,418),(418,836),(836,1254)]
ROWS = [(50,398),(455,778),(830,1150)]

def lum(a): return 0.299*a[...,0]+0.587*a[...,1]+0.114*a[...,2]

def matte(c):
    c = c.astype(np.float64)
    near_white = c.min(axis=2) > 226
    lab,_ = ndi.label(near_white)
    edge_labels = np.unique(np.concatenate([lab[0],lab[-1],lab[:,0],lab[:,-1]]))
    bg = np.isin(lab, edge_labels[edge_labels>0]) & near_white
    fg = ~bg
    fg = ndi.binary_opening(fg, iterations=1) | (fg & ~ndi.binary_dilation(bg, iterations=3))                              
    dist = ndi.distance_transform_edt(fg)
    core = dist > 3.2
    band = fg & ~core
                            
    d_core, idx = ndi.distance_transform_edt(~core, return_indices=True)
    core_col = c[idx[0], idx[1]]
                                                                                 
    lab_fg,n = ndi.label(fg)
    out_col = c.copy()
    comp_col = {}
    for i in range(1,n+1):
        m = lab_fg==i
        px = c[m]; L = lum(px)
        k = max(1,int(len(px)*0.4))
        comp_col[i] = np.median(px[np.argsort(L)[:k]],axis=0)
    fallback = np.zeros_like(c)
    for i,col in comp_col.items(): fallback[lab_fg==i] = col
    use_fb = band & (d_core > 5)
    base = np.where(use_fb[...,None], fallback, core_col)
    Lc = lum(base); Lp = lum(c)
    a = np.clip((250 - Lp)/np.maximum(250 - Lc, 25), 0, 1)
    keep = np.where(band, a > 0.55, True) & fg
    col = np.where(band[...,None], base, c)
    alpha = np.where(keep,255,0).astype(np.uint8)
                               
    alpha = (ndi.binary_opening(alpha>0, structure=np.ones((2,2))) | (ndi.binary_closing(alpha>0)&False)).astype(np.uint8)*255
                                                                                                               
    solid = alpha>0
    _, ii = ndi.distance_transform_edt(~solid, return_indices=True)
    col_full = col[ii[0], ii[1]]
    return np.dstack([np.clip(col_full,0,255).astype(np.uint8), alpha])

def split(rgba):
    a = rgba[...,3]>0
    lab,n = ndi.label(a, structure=np.ones((3,3)))
    areas = ndi.sum(a, lab, range(1,n+1))
    main = 1+int(np.argmax(areas))
    ys,xs = np.where(lab==main); bb = (xs.min(),ys.min(),xs.max(),ys.max())
    char = np.zeros(a.shape,bool); info=[]
    for i in range(1,n+1):
        m = lab==i
        if areas[i-1] < 60: continue
        yy,xx = np.where(m)
        inside = xx.min()>=bb[0]-5 and xx.max()<=bb[2]+5 and yy.min()>=bb[1]-5 and yy.max()<=bb[3]+5
        info.append((i,int(areas[i-1]),(xx.min(),yy.min(),xx.max(),yy.max()),inside))
        if i==main or (inside and areas[i-1]>400): char |= m
    fx = a & ~char
                       
    flab,fn = ndi.label(fx, structure=np.ones((3,3)))
    for i in range(1,fn+1):
        if (flab==i).sum() < 60: fx[flab==i]=False
    return char, fx, info

def run():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    src = np.array(Image.open(SRC).convert('RGB'))
    res={}
    for k,n in enumerate(NAMES):
        (x0,x1),(y0,y1)=COLS[k%3],ROWS[k//3]
        rgba = matte(src[y0:y1,x0:x1])
        char,fx,info = split(rgba)
        print(n, [(a,b[:4] if False else b,ins) for _,a,b,ins in info])
        np.save(f'{n}_rgba.npy', rgba); np.save(f'{n}_char.npy', char); np.save(f'{n}_fx.npy', fx)
        res[n]=(rgba,char,fx)
                           
    W=420;H=350
    sheet = Image.new('RGB',(W*3,H*3),(22,22,26))
    for k,n in enumerate(NAMES):
        rgba=res[n][0]; im=Image.fromarray(rgba,'RGBA')
        sheet.paste(im,((k%3)*W+5,(k//3)*H+5),im)
    sheet.save('dbg_matte.png')


if __name__=='__main__':
    run()
