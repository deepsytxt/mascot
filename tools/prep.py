"""Stage 2a: выравнивание на общий холст, поиск линии «шеи», отделение эффектов."""
from PIL import Image
import numpy as np
from scipy import ndimage as ndi
from matte import NAMES

def longest_run(b):
    best=cur=0
    for v in b:
        cur = cur+1 if v else 0
        best = max(best,cur)
    return best

def find_split(rgba, char):
    h,w = char.shape
    ys,xs = np.where(char); top,bot = ys.min(), ys.max()
    white = (rgba[...,:3].min(axis=2) > 205) & char
    last=None
    for y in range(top, top+int((bot-top)*0.72)):
        if longest_run(white[y]) >= 70: last = y
    return last + 6                                                     

def screen_info(rgba, char, split):
    """bbox экрана (лаймовый) и глифа '>' внутри головы"""
    r,g,b = [rgba[...,i].astype(int) for i in range(3)]
    lime = (g>165)&(r>100)&(r<175)&(b<130)&char
    lime[split:] = False
    lab,n = ndi.label(lime)
    if n==0: return None
    big = 1+int(np.argmax(ndi.sum(lime,lab,range(1,n+1))))
    ys,xs = np.where(lab==big)
    sb = (xs.min(),ys.min(),xs.max(),ys.max())
    inside = np.zeros_like(char); inside[sb[1]:sb[3]+1, sb[0]:sb[2]+1]=True
    glyph = (rgba[...,:3].min(axis=2)>195) & inside & char
    gl,gn = ndi.label(glyph, structure=np.ones((3,3)))
    comps=[]
    for i in range(1,gn+1):
        yy,xx=np.where(gl==i)
        if len(yy)<40: continue
        comps.append((xx.min(),yy.min(),xx.max(),yy.max()))
    comps.sort()
    screen_col = np.median(rgba[...,:3][lab==big],axis=0).astype(np.uint8)
    return dict(screen=sb, glyphs=comps, color=screen_col)

def load_all():
    import os, matte
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.exists(f'{NAMES[0]}_rgba.npy'): matte.run()
    items={}
    for n in NAMES:
        rgba=np.load(f'{n}_rgba.npy'); char=np.load(f'{n}_char.npy'); fx=np.load(f'{n}_fx.npy')
        ys,xs=np.where(char); bot=ys.max()
        feet=np.where(char[bot-25:bot+1].any(axis=0))[0]; fcx=(feet.min()+feet.max())/2
        split=find_split(rgba,char)
        face=screen_info(rgba,char,split)
        items[n]=dict(rgba=rgba,char=char,fx=fx,bot=int(bot),fcx=float(fcx),split=int(split),face=face)
    return items

HEADROOM=66; BOT_M=6; SIDE_M=22

def place(items):
                                            
    minx=miny=1e9; maxx=-1e9
    for n,it in items.items():
        m=it['char']|it['fx']; ys,xs=np.where(m)
        minx=min(minx,xs.min()-it['fcx']); maxx=max(maxx,xs.max()-it['fcx'])
        miny=min(miny,ys.min()-it['bot'])
    left=int(np.floor(minx))-SIDE_M; right=int(np.ceil(maxx))+SIDE_M
    top=int(miny)-HEADROOM
    W=right-left+1; H=-top+BOT_M+1
    base_y=-top                            
    for n,it in items.items():
        ox=int(round(-left-it['fcx'])); oy=int(base_y-it['bot'])
        uy,ux=np.where(it['char']|it['fx']); by0,by1,bx0,bx1=uy.min(),uy.max()+1,ux.min(),ux.max()+1
        def put(mask):
            a=np.zeros((H,W,4),np.uint8)
            sub=it['rgba'].copy(); sub[...,3]=np.where(mask,255,0)
            a[oy+by0:oy+by1, ox+bx0:ox+bx1]=sub[by0:by1,bx0:bx1]
            return Image.fromarray(a,'RGBA')
        it['char_img']=put(it['char']); it['fx_img']=put(it['fx'])
        it['split_c']=it['split']+oy; it['ox']=ox; it['oy']=oy
        if it['face']:
            f=it['face']; f['screen']=(f['screen'][0]+ox,f['screen'][1]+oy,f['screen'][2]+ox,f['screen'][3]+oy)
            f['glyphs']=[(a+ox,b+oy,c+ox,d+oy) for a,b,c,d in f['glyphs']]
    return W,H,base_y

if __name__=='__main__':
    items=load_all(); W,H,base=place(items)
    print('canvas',W,H,'base',base)
    sheet=Image.new('RGB',(W*3,H*3),(22,22,26))
    from PIL import ImageDraw
    for k,n in enumerate(NAMES):
        it=items[n]; im=Image.new('RGBA',(W,H),(0,0,0,0))
        im.alpha_composite(it['char_img']); im.alpha_composite(it['fx_img'])
        d=ImageDraw.Draw(im); d.line([(0,it['split_c']),(W,it['split_c'])],fill=(255,0,255,255),width=1)
        d.line([(0,base),(W,base)],fill=(255,255,0,255),width=1)
        if it['face']:
            for g in it['face']['glyphs']: d.rectangle(g,outline=(255,80,0,255))
        sheet.paste(im,((k%3)*W,(k//3)*H),im)
        print(n,'split',it['split_c'],'glyphs',len(it['face']['glyphs']) if it['face'] else None, 'color',it['face']['color'] if it['face'] else None)
    sheet.save('dbg_prep.png')
