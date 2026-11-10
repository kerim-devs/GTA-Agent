# measurement aid: angles (clock) at which route-coloured pixels cross the near/far circles
import sys, json, math
import numpy as np
crops=np.load('data/crops.npy', mmap_mode='r')
g={e['id']:e for e in json.load(open('data/golden.json'))}
def mask(c,col):
    r,gg,b=[c[...,i].astype(int) for i in range(3)]
    if col=='yellow':
        return (r>170)&(gg>170)&(b<140)&(r-b>80)&(abs(r-gg)<50)
    else:
        return (b>150)&(b-gg>40)&(r-gg>10)&(b-r>10)
def run(a,col):
    parts=a.split(':'); id_=parts[0]
    cx,cy=(float(parts[1]),float(parts[2])) if len(parts)>1 else (123.0,117.0)
    k=int(id_[1:]) if id_.startswith('k') else g[id_]['k']
    c=np.asarray(crops[k]); m=mask(c,col)
    ys,xs=np.nonzero(m)
    # restrict to map area
    keep=(xs>=30)&(xs<=218)&(ys>=24)&(ys<=144)
    xs,ys=xs[keep],ys[keep]
    d=np.hypot(xs-cx,ys-cy)
    ang=(np.degrees(np.arctan2(xs-cx,-(ys-cy)))+360)%360
    print(id_,col,'n=',len(xs),'maxdist=%.0f'%(d.max() if len(d) else -1))
    for R in (30,60):
        sel=np.abs(d-R)<=1.5
        if not sel.any(): print('  R',R,'none'); continue
        a_=np.sort(ang[sel])
        # cluster
        cl=[[a_[0]]]
        for v in a_[1:]:
            if v-cl[-1][-1]>8: cl.append([v])
            else: cl[-1].append(v)
        if len(cl)>1 and (cl[0][0]+360-cl[-1][-1])<=8:
            cl[0]=[v-360 for v in cl[-1]]+cl[0]; cl.pop()
        out=[]
        for cc in cl:
            mean=float(np.mean(cc)); out.append('%.0fdeg=%.2fh(n%d,%0.f..%.0f)'%(mean%360,((mean%360)/30) or 12,len(cc),min(cc),max(cc)))
        print('  R',R,' | '.join(out))
    # far-most point
    if len(d):
        i=d.argmax(); print('  farthest: d=%.0f ang=%.0f=%.2fh'%(d[i],ang[i],ang[i]/30))
for a in sys.argv[2:]: run(a,sys.argv[1])
