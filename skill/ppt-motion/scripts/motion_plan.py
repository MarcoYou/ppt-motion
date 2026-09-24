"""Deck-independent, reviewable object plans; PDF/SVG remain the visual authority."""
from __future__ import annotations

import copy
import difflib
import re
import unicodedata

import fitz

ROLES = {'title', 'text', 'table', 'bar-chart', 'line-chart', 'donut-chart', 'pie-chart', 'gauge', 'chart', 'heatmap', 'image', 'annotation', 'shape'}
EFFECTS = {'static', 'fade', 'bar-x', 'bar-y', 'line', 'tile', 'star', 'wipe', 'radial', 'outline', 'underline', 'band'}
PROFILES = {'research', 'explain', 'static'}


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


def walk(shapes):
    for shape in shapes:
        yield shape
        yield from walk(shape.get('children', []))


def contains(box, element):
    b = element.get('visibleBboxPt') or element.get('bboxPt')
    return bool(b and box[0] <= (b[0]+b[2])/2 <= box[2] and box[1] <= (b[1]+b[3])/2 <= box[3])


def candidates(elements, box, role):
    inside = [e for e in elements if contains(box, e)]
    if role in {'title', 'text'}:
        return [e['id'] for e in inside if e.get('text') is not None]
    if role == 'image':
        return [e['id'] for e in inside if e['type'] == 'image']
    if role == 'line-chart':
        return [e['id'] for e in inside if e['type']=='path' and e.get('stroke') and e.get('fill') in (None,'none') and e.get('pathNumbers',0)>=8]
    if role in {'bar-chart', 'heatmap'}:
        return [e['id'] for e in inside if e['type']=='path' and e.get('pathCommands')==5 and e.get('fill') not in (None,'none','#ffffff')]
    return []


def text_blocks(page):
    result = []
    for block in page.get_text('dict')['blocks']:
        if block['type'] != 0:
            continue
        spans = [span for line in block['lines'] for span in line['spans']]
        text = '\n'.join(''.join(s['text'] for s in line['spans']) for line in block['lines']).strip()
        if text:
            result.append({'text':text,'box':[round(v,3) for v in block['bbox']],
                           'maxFontSize':max((s['size'] for s in spans),default=0)})
    return result


def slide_mapping(pages, pptx, explicit):
    """Unique text agreement, never slide-count equality, establishes candidates."""
    if not pptx:
        if explicit: raise ValueError('--slide-map requires PPTX metadata')
        return {}, []
    slides = {s['order']:s for s in pptx['slides']}
    mapping, warnings = {}, []
    if explicit:
        used = set()
        for pair in explicit.split(','):
            try: p, s = map(int, pair.split('='))
            except ValueError: raise ValueError('--slide-map uses PDF-page=PPTX-slide, e.g. 1=1,2=3')
            if p not in pages or s not in slides or p in mapping or s in used:
                raise ValueError('Invalid, duplicate, or unavailable page in --slide-map')
            mapping[p] = {'slide':s,'method':'explicit'};used.add(s)
    for number, page in pages.items():
        if number in mapping: continue
        target = normalized(page['text'])
        if len(target)<16: continue
        ranked = []
        for order, s in slides.items():
            source = normalized(s['text'])
            if len(source)<16: continue
            ranked.append((difflib.SequenceMatcher(None,target,source,autojunk=False).ratio(),order))
        ranked.sort(reverse=True)
        if ranked and ranked[0][0]>=.82 and (len(ranked)==1 or ranked[0][0]-ranked[1][0]>=.12):
            mapping[number]={'slide':ranked[0][1],'method':'unique-text-match','score':round(ranked[0][0],3)}
    counts = {}
    for p,m in mapping.items(): counts.setdefault(m['slide'],[]).append(p)
    for s, same in counts.items():
        if len(same)>1:
            for p in same:
                if mapping[p]['method']!='explicit': del mapping[p]
            warnings.append(f'PPTX slide {s} matched multiple PDF pages; ambiguous automatic matches were discarded.')
    for p in pages:
        if p not in mapping: warnings.append(f'PDF page {p}: PPTX mapping unresolved; PDF text blocks only. Use --slide-map after checking order.')
    return mapping,warnings


def shape_role(shape):
    if shape.get('role') == 'chart' or shape.get('charts'):
        kinds={series.get('chartType') for c in shape.get('charts',[]) for series in c.get('series',[])}
        kinds.update(kind for c in shape.get('charts',[]) for kind in c.get('plotTypes',[]))
        if kinds=={'barChart'}:return 'bar-chart'
        if kinds=={'lineChart'}:return 'line-chart'
        if kinds=={'doughnutChart'}:return 'donut-chart'
        if kinds=={'pieChart'}:return 'pie-chart'
        return 'chart'
    role=shape.get('role')
    if role in ROLES:return role
    placeholder=shape.get('placeholder',{}).get('type')
    if placeholder in {'title','ctrTitle'}:return 'title'
    if shape.get('table'):return 'table'
    if shape.get('kind')=='pic':return 'image'
    if shape.get('text'):return 'text'
    return 'shape'


def make_plan(job, config, pages, pptx, profile, explicit, source_hash, deck_hash):
    if profile not in PROFILES:raise ValueError('Unknown profile')
    mapping,warnings=slide_mapping(pages,pptx,explicit)
    pptx_slides={s['order']:s for s in pptx['slides']} if pptx else {}
    plan={'schemaVersion':1,'profile':profile,'sourceLockSha256':source_hash,'deckSha256':deck_hash,
          'instructions':'Review named components against the PDF. Set effect and exact ids, or add emphasis with a box. Bars require the real zero origin. Tables stay static unless explicitly highlighted. apply-plan validates before changing deck.json.',
          'warnings':warnings,'slides':[]}
    with fitz.open(job/'source/deck.pdf') as doc:
        for slide in config['slides']:
            p=slide['page'];page=pages[p];elements=page['elements'];blocks=text_blocks(doc[p-1])
            top_blocks=[b for b in blocks if b['box'][1]<page['height']*.22]
            title_block=max(top_blocks,key=lambda b:(b['maxFontSize'],-b['box'][1]),default=None)
            components=[];match=mapping.get(p);covered=[]
            compatible=bool(match and abs(pptx['width']-page['width'])<1 and abs(pptx['height']-page['height'])<1)
            if match and not compatible:
                warnings.append(f'PDF page {p}: PPTX/PDF dimensions differ; shape bounds not transferred.')
            if compatible:
                for shape in walk(pptx_slides[match['slide']]['shapes']):
                    if shape.get('kind')=='grpSp' or shape.get('hidden'):continue
                    role=shape_role(shape);box=shape.get('bboxPt')
                    if role=='shape' or not box or not shape.get('bboxReliable'):continue
                    if box[0]<0 or box[1]<0 or box[2]>page['width'] or box[3]>page['height']:continue
                    if shape.get('rotationDegrees',0)%360 or shape.get('flipH') or shape.get('flipV'):
                        warnings.append(f'PDF page {p}, shape {shape["id"]}: rotated/flipped bounds require manual selection.');continue
                    if role=='text' and title_block:
                        tb=title_block['box'];cx=(tb[0]+tb[2])/2;cy=(tb[1]+tb[3])/2
                        if box[0]<=cx<=box[2] and box[1]<=cy<=box[3]:role='title'
                    ids=candidates(elements,box,role)
                    suggestion={'bar-chart':'bar-y','line-chart':'line','donut-chart':'radial',
                                'pie-chart':'radial','gauge':'radial','image':'fade'}.get(role,'static')
                    if role=='bar-chart' and {c.get('barDirection') for c in shape.get('charts',[])}=={'bar'}:suggestion='bar-x'
                    # Treat short labels and footer furniture conservatively.
                    # A human can still opt any such text block into a fade.
                    narrative=(role=='text' and len(normalized(shape.get('text','')))>=20
                               and box[1]<page['height']*.85
                               and shape.get('placeholderType') not in {'dt','ftr','hdr','sldNum'})
                    components.append({'id':f'p{p}-shape-{shape["id"]}','role':role,
                       'label':shape.get('text','').strip()[:120] or shape.get('name') or role,'box':box,'ids':ids,
                       'effect':'fade' if profile=='explain' and narrative and ids else 'static',
                       'suggestedEffect':suggestion,
                       'review':'Shape bounds/candidate IDs need visual review; axes and labels remain static.',
                       'pptxShapeId':shape['id']})
                    covered.append(box)
            # Inherited placeholders, PDF-only files, and unsupported mappings still
            # get usable whole-text selections, never a title inferred from page number.
            for i,b in enumerate(blocks):
                cx=(b['box'][0]+b['box'][2])/2;cy=(b['box'][1]+b['box'][3])/2
                if any(x<=cx<=r and y<=cy<=bottom for x,y,r,bottom in covered):continue
                role='title' if b is title_block else 'text'
                # Text blocks may extend just outside a cropped PDF page.
                b['box']=[max(0,b['box'][0]),max(0,b['box'][1]),min(page['width'],b['box'][2]),min(page['height'],b['box'][3])]
                if b['box'][2]<=b['box'][0] or b['box'][3]<=b['box'][1]:continue
                ids=candidates(elements,b['box'],role)
                components.append({'id':f'p{p}-text-{i+1}','role':role,'label':b['text'][:120],'box':b['box'],'ids':ids,
                                   'effect':'static',
                                   'suggestedEffect':'static','review':'PDF text block; confirm that this is one intended reading unit.'})
            titles=[c['label'] for c in components if c['role']=='title']
            title=slide.get('title','')
            if re.fullmatch(r'\d+페이지',title) and titles:title=titles[0].replace('\n',' ')
            # Replanning the same source carries prior object choices forward.
            # The next apply replaces only rules owned by those component IDs.
            prior={c['id']:c for c in slide.get('components',[])}
            components=[{**c,**copy.deepcopy(prior.pop(c['id'],{}))} for c in components]
            components.extend(copy.deepcopy(list(prior.values())))
            plan['slides'].append({'page':p,'title':title,'message':slide.get('message',''),
                                   'pptxMapping':match,'components':components})
    return plan


def apply_to_config(plan, config, pages):
    """Compile reviewed semantic objects to the existing low-level effects contract."""
    if not isinstance(plan,dict) or plan.get('schemaVersion')!=1 or not isinstance(plan.get('slides'),list):
        raise ValueError('Invalid motion plan schema')
    proposed=copy.deepcopy(config);slides={s['page']:s for s in proposed['slides']};seen_pages=set()
    for item in plan['slides']:
        page_no=item.get('page')
        if type(page_no)is not int or page_no not in slides or page_no in seen_pages:raise ValueError('Invalid/duplicate plan page')
        seen_pages.add(page_no);slide=slides[page_no];page=pages[page_no];known={e['id']:e for e in page['elements']}
        for key in ('title','message'):
            if not isinstance(item.get(key,''),str):raise ValueError(f'Plan {key} must be text')
            slide[key]=item.get(key,slide.get(key,''))
        components=item.get('components',[])
        if not isinstance(components,list):raise ValueError('Plan components must be a list')
        edited_ids={c.get('id') for c in components if isinstance(c,dict) and isinstance(c.get('id'),str)}
        for key in ('motions','emphasis'):
            slide[key]=[rule for rule in slide.get(key,[]) if rule.get('componentId') not in edited_ids]
        seen=set();summaries=[]
        for c in components:
            if not isinstance(c,dict) or not isinstance(c.get('id'),str) or not c['id'] or c['id'] in seen:raise ValueError('Each component needs a unique id')
            seen.add(c['id']);role=c.get('role');effect=c.get('effect','static');box=c.get('box')
            if role not in ROLES or effect not in EFFECTS:raise ValueError(f'{c["id"]}: unsupported role/effect')
            if not isinstance(box,list) or len(box)!=4 or any(type(v)not in(int,float) for v in box):raise ValueError('Component box needs 4 numeric PDF coordinates')
            import math
            if not all(math.isfinite(v) for v in box) or not (0<=box[0]<box[2]<=page['width'] and 0<=box[1]<box[3]<=page['height']):raise ValueError('Component box must be inside the PDF page')
            ids=c.get('ids',[])
            if not isinstance(ids,list) or any(not isinstance(x,str) or x not in known for x in ids) or len(ids)!=len(set(ids)):raise ValueError(f'{c["id"]}: invalid element IDs')
            if any(not contains(box,known[x]) for x in ids):raise ValueError(f'{c["id"]}: selected element is outside its region')
            if not isinstance(c.get('label',''),str):raise ValueError('Component label must be text')
            summaries.append(copy.deepcopy(c))
            if effect=='static':continue
            if effect in {'outline','underline','band'}:
                mark={'kind':effect,'box':box,'color':c.get('color','#c93434'),'duration':c.get('duration',900),'delay':c.get('delay',0),'componentId':c['id']}
                for key in ('opacity','width','animate'):
                    if key in c:mark[key]=c[key]
                slide.setdefault('emphasis',[]).append(mark);continue
            if role=='table':raise ValueError('Tables stay static; use a separate row/cell annotation with band, outline or underline')
            if not ids:raise ValueError(f'{c["id"]}: select actual source ids before applying {effect}')
            if effect in {'bar-x','bar-y','line','tile','star','wipe','radial'} and any(known[x].get('text') is not None for x in ids):raise ValueError('Chart effects cannot target text labels; keep them static or use fade')
            if role in {'title','text'} and effect!='fade':raise ValueError('Title/text motion uses fade; use an annotation for emphasis')
            rule={'kind':effect,'ids':ids,'duration':c.get('duration',450 if effect=='fade' else 900),'delay':c.get('delay',0),'componentId':c['id']}
            if 'origin' in c:rule['origin']=c['origin']
            if effect=='radial':
                for key in ('center','radius','startAngle','sweepAngle','trackColor'):
                    if key in c:rule[key]=copy.deepcopy(c[key])
            slide.setdefault('motions',[]).append(rule)
        # Existing object metadata is retained, with this plan's IDs updating their own entries.
        merged={c['id']:c for c in slide.get('components',[])};merged.update({c['id']:c for c in summaries})
        slide['components']=list(merged.values())
    return proposed
