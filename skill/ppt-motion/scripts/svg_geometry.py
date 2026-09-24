"""Faithful PDF SVG exports with source-geometry metadata (no layout changes)."""
from lxml import etree as ET
import re, math, hashlib, copy
SVG = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'
NS = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
NUM = r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'
IDENTITY = (1,0,0,1,0,0)

def union(boxes):
    boxes=[b for b in boxes if b is not None]
    return [min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)] if boxes else None

def mul(a,b):
    return (a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5])

def trans(t):
    m=IDENTITY
    for name,vals in re.findall(r'(\w+)\s*\(([^)]*)\)',t or ''):
        v=list(map(float,re.findall(NUM,vals)))
        if name=='matrix':n=tuple(v)
        elif name=='translate':n=(1,0,0,1,v[0],v[1] if len(v)>1 else 0)
        elif name=='scale':n=(v[0],0,0,v[1] if len(v)>1 else v[0],0,0)
        elif name=='rotate':
            c=math.cos(math.radians(v[0]));s=math.sin(math.radians(v[0]));n=(c,s,-s,c,0,0)
            if len(v)>2:n=mul(mul((1,0,0,1,v[1],v[2]),n),(1,0,0,1,-v[1],-v[2]))
        elif name=='skewX':n=(1,0,math.tan(math.radians(v[0])),1,0,0)
        elif name=='skewY':n=(1,math.tan(math.radians(v[0])),0,1,0,0)
        else: raise ValueError(f'Unsupported transform {name}')
        m=mul(m,n)
    return m

def map_box(b,m):
    if b is None:return None
    pts=[(m[0]*x+m[2]*y+m[4],m[1]*x+m[3]*y+m[5]) for x,y in [(b[0],b[1]),(b[0],b[3]),(b[2],b[1]),(b[2],b[3])]]
    return [min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts)]

def path_box(d):
    # Control-point hull is conservative for C/Q curves and accurate for line charts.
    ts=re.findall(r'[a-df-zA-DF-Z]|'+NUM,d or '')
    cmd=None;i=0;x=y=sx=sy=0;pts=[]
    counts={'M':2,'L':2,'H':1,'V':1,'C':6,'S':4,'Q':4,'T':2,'A':7,'Z':0}
    while i<len(ts):
        if re.fullmatch('[a-zA-Z]',ts[i]):cmd=ts[i];i+=1
        if cmd is None:raise ValueError('Missing path command')
        op=cmd.upper();n=counts[op]
        if op=='Z':x,y=sx,sy;pts.append((x,y));cmd=None;continue
        vals=list(map(float,ts[i:i+n]));i+=n;relative=cmd.islower();ox=x;oy=y
        if op in ['M','L','T','C','S','Q']:
            pairs=[(vals[j]+(ox if relative else 0),vals[j+1]+(oy if relative else 0)) for j in range(0,n,2)]
            pts.extend(pairs);x,y=pairs[-1]
            if op=='M':sx,sy=x,y;cmd='l' if relative else 'L'
        elif op=='H':x=vals[0]+(x if relative else 0);pts.append((x,y))
        elif op=='V':y=vals[0]+(y if relative else 0);pts.append((x,y))
        elif op=='A':
            # PDF exports use cubic curves; other SVG sources are unsupported.
            raise ValueError('Arc path requires explicit bbox support')
    if not pts:return None
    return [min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts)]

def fingerprint(e):
    clean=copy.deepcopy(e)
    for item in clean.iter():
        for key in list(item.attrib):
            if key.startswith('data-'):del item.attrib[key]
    clean.tail=None
    return hashlib.sha256(ET.tostring(clean,method='c14n')).hexdigest()

def svg_geometry(root,page):
    ids={e.get('id'):e for e in root.iter() if e.get('id')}
    cache={}
    def local(e):
        if e in cache:return cache[e]
        typ=ET.QName(e).localname
        if typ=='path':b=path_box(e.get('d'))
        elif typ=='use':
            ref=e.get('{'+XLINK+'}href',e.get('href','')).lstrip('#');b=local(ids[ref]) if ref in ids else None
            b=map_box(b,(1,0,0,1,float(e.get('x',0)),float(e.get('y',0))))
        elif typ in ['image','rect']:
            x=float(e.get('x',0));y=float(e.get('y',0));b=[x,y,x+float(e.get('width',0)),y+float(e.get('height',0))]
        elif typ in ['circle','ellipse']:
            x=float(e.get('cx',0));y=float(e.get('cy',0));rx=float(e.get('rx',e.get('r',0)));ry=float(e.get('ry',e.get('r',0)));b=[x-rx,y-ry,x+rx,y+ry]
        elif typ=='line':b=[min(float(e.get('x1',0)),float(e.get('x2',0))),min(float(e.get('y1',0)),float(e.get('y2',0))),max(float(e.get('x1',0)),float(e.get('x2',0))),max(float(e.get('y1',0)),float(e.get('y2',0)))]
        elif typ in ['polyline','polygon']:
            pts=list(map(float,re.findall(NUM,e.get('points',''))));b=[min(pts[::2]),min(pts[1::2]),max(pts[::2]),max(pts[1::2])] if pts else None
        elif typ in ['g','clipPath','svg']:b=union([map_box(local(c),trans(c.get('transform'))) for c in e if ET.QName(c).localname!='defs'])
        else:raise ValueError(f'Unsupported SVG tag: {typ}')
        cache[e]=b;return b
    leaves=[]
    def walk(e,m=IDENTITY,clips=(),in_defs=False):
        typ=ET.QName(e).localname
        if typ in ['defs','title','desc','metadata']:return
        parent_matrix=m
        m=mul(m,trans(e.get('transform')))
        c=e.get('clip-path')
        if c:
            ref=re.search(r'#([^)]*)',c).group(1)
            cb=map_box(local(ids[ref]),m)
            if cb:clips=clips+(cb,)
        if typ in ['g','svg']:
            for child in e:walk(child,m,clips)
            return
        b=map_box(local(e),m)
        clipped=b[: ] if b else None
        for cb in clips:
            if clipped:clipped=[max(clipped[0],cb[0]),max(clipped[1],cb[1]),min(clipped[2],cb[2]),min(clipped[3],cb[3])]
        lid=f'p{page:02d}-e{len(leaves):04d}'
        e.set('data-leaf',lid)
        e.set('data-parent-matrix',','.join(str(v) for v in parent_matrix))
        if b:e.set('data-bbox',','.join(f'{v:.3f}' for v in b))
        if clipped:e.set('data-visible-bbox',','.join(f'{v:.3f}' for v in clipped))
        row={'id':lid,'type':typ,'bboxPt':b,'visibleBboxPt':clipped,'fill':e.get('fill'),'stroke':e.get('stroke'),'strokeWidth':e.get('stroke-width'),'text':e.get('data-text'),'transform':e.get('transform'),'clipDepth':len(clips)}
        row.update(matrix=list(m),parentMatrix=list(parent_matrix),fingerprint=fingerprint(e))
        if clipped and (clipped[2]<clipped[0] or clipped[3]<clipped[1]):row['visibleBboxPt']=None
        if typ=='path':
            row['pathCommands']=len(re.findall('[A-DF-Za-df-z]',e.get('d','')))
            row['pathNumbers']=len(re.findall(NUM,e.get('d','')))
        leaves.append(row)
    walk(root)
    return leaves
