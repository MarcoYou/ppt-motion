#!/usr/bin/env python3
"""Local, reproducible PDF/PPTX to faithful animated SVG presentation workflow."""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import http.server
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz
from lxml import etree as ET

from svg_geometry import SVG, NUM, svg_geometry, trans, mul

VERSION = '0.3.0'
ASSETS = Path(__file__).resolve().parents[1] / 'assets'
KINDS = {'fade', 'tile', 'bar-x', 'bar-y', 'line', 'star', 'wipe', 'radial'}
PARSER = ET.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fail(message):
    raise ValueError(message)


def node(tag, **attrs):
    return ET.Element('{' + SVG + '}' + tag, {k.replace('_', '-'): str(v) for k, v in attrs.items()})


def parse_svg(path):
    return ET.fromstring(Path(path).read_bytes(), parser=PARSER)


def numbers(value, length, label):
    if not isinstance(value, list) or len(value) != length or any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        fail(f'{label}: expected {length} finite numbers')
    return value


def rectangle(value, label):
    x, y, x2, y2 = numbers(value, 4, label)
    if x2 <= x or y2 <= y:
        fail(f'{label}: right/bottom must exceed left/top')
    return value


def timing(rule):
    for key, default, maximum in [('duration', 900, 10000), ('delay', 0, 10000)]:
        value = rule.get(key, default)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum:
            fail(f'{key}: expected milliseconds in [0, {maximum}]')
    if rule.get('duration', 900) < 1:
        fail('duration must be at least 1 ms')


def radial_parameters(rule):
    """Page-space reveal geometry is explicit and shared across selected slices."""
    center = numbers(rule.get('center'), 2, 'radial center')
    radius = numbers([rule.get('radius')], 1, 'radial radius')[0]
    if radius <= 0:
        fail('radial radius must be positive')
    start = numbers([rule.get('startAngle', -90)], 1, 'radial startAngle')[0]
    sweep = numbers([rule.get('sweepAngle', 360)], 1, 'radial sweepAngle')[0]
    if sweep == 0 or not -360 <= sweep <= 360:
        fail('radial sweepAngle must be nonzero and in [-360,360]')
    attrs = {'data-center': ','.join(str(v) for v in center), 'data-radius': str(radius),
             'data-start-angle': str(start), 'data-sweep-angle': str(sweep)}
    if 'trackColor' in rule:
        color = rule['trackColor']
        if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            fail('radial trackColor must be #RRGGBB')
        attrs['data-track-color'] = color
    return attrs


def split_rectangles(root):
    """Split disjoint closed rectangular subpaths without changing paint order."""
    count = 0
    for e in list(root.iter('{' + SVG + '}path')):
        if any(ET.QName(p).localname == 'defs' for p in e.iterancestors()):
            continue
        d = e.get('d', '')
        parts = re.findall(r'M[^M]+', d)
        if len(parts) < 2 or ''.join(parts) != d:
            continue
        bounds = []
        for part in parts:
            commands = re.findall(r'[A-DF-Za-df-z]', part)
            if len(commands) != 5 or commands[0] != 'M' or commands[-1] != 'Z' or any(c not in ('L', 'H', 'V') for c in commands[1:-1]):
                break
            pts = []
            x = y = 0
            valid = True
            for command, coordinates in re.findall(r'([MLHV])([^MLHVZ]+)', part):
                vals = list(map(float, re.findall(NUM, coordinates)))
                if len(vals) != (2 if command in ('M','L') else 1):
                    valid = False
                    break
                if command in ('M','L'):x,y = vals
                elif command == 'H':x = vals[0]
                else:y = vals[0]
                pts.append((x,y))
            if not valid:break
            xs, ys = sorted(set(p[0] for p in pts)), sorted(set(p[1] for p in pts))
            if len(xs) != 2 or len(ys) != 2 or len(set(pts)) != 4:
                break
            if any(a[0] != b[0] and a[1] != b[1] for a, b in zip(pts, pts[1:] + pts[:1])):
                break
            bounds.append([xs[0], ys[0], xs[1], ys[1]])
        if len(bounds) != len(parts):
            continue
        if any(min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]) for i, a in enumerate(bounds) for b in bounds[i + 1:]):
            continue
        parent = e.getparent()
        index = parent.index(e)
        for offset, part in enumerate(parts):
            child = copy.deepcopy(e)
            child.set('d', part)
            child.set('data-rectangle', 'true')
            parent.insert(index + offset, child)
        parent.remove(e)
        count += len(parts)
    return count


def parse_pages(spec, total):
    if not spec:
        return list(range(1, total + 1))
    pages = []
    for part in spec.split(','):
        ends = part.split('-')
        if len(ends) == 1:
            pages.append(int(part))
        elif len(ends) == 2:
            a, b = map(int, ends)
            if a > b:
                fail('Page ranges must be ascending')
            pages.extend(range(a, b + 1))
        else:
            fail('Pages use 1,3,5-7 syntax')
    if not pages or len(set(pages)) != len(pages) or min(pages) < 1 or max(pages) > total:
        fail(f'Pages must be unique and in 1..{total}')
    return pages


def init_job(args):
    job = Path(args.out).expanduser().resolve()
    if job.exists():
        fail(f'Output already exists: {job}. Use a new job directory; existing work is never overwritten by init.')
    pdf_arg = args.pdf or (str(Path(args.pptx).expanduser().with_suffix('.pdf')) if args.pptx else None)
    if not pdf_arg:
        fail('Provide --pdf, or --pptx with a matching same-name PDF beside it. Run doctor --pptx /path/deck.pptx for export guidance.')
    pdf_path = Path(pdf_arg).expanduser().resolve()
    if not pdf_path.is_file():
        fail(f'PDF missing: {pdf_path}. Export a matching PDF from PowerPoint (File > Export/Save As > PDF), then retry. Run doctor --pptx /path/deck.pptx for available tools.')
    doc = fitz.open(pdf_path)
    if doc.needs_pass:
        fail('Password-protected PDF: provide an unlocked visual reference')
    pages = parse_pages(args.pages, len(doc))
    job.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.ppt-motion-init-', dir=job.parent))
    try:
        for dirname in ['source', 'extracted', 'reference']:
            (staging / dirname).mkdir()
        shutil.copyfile(pdf_path, staging / 'source/deck.pdf')
        hashes = {'source/deck.pdf': digest(staging / 'source/deck.pdf')}
        pptx_result = None
        if args.pptx:
            from pptx_inventory import read_pptx
            pptx_path = Path(args.pptx).expanduser().resolve()
            pptx_result = read_pptx(pptx_path)
            shutil.copyfile(pptx_path, staging / 'source/deck.pptx')
            hashes['source/deck.pptx'] = digest(staging / 'source/deck.pptx')
            write_json(staging / 'pptx-inventory.json', pptx_result)
        inventory = []
        warnings = []
        proposals = []
        slides = []
        extracted_hashes = {}
        for page_number in pages:
            page = doc[page_number - 1]
            root = ET.fromstring(page.get_svg_image(text_as_path=True).encode(), parser=PARSER)
            splits = split_rectangles(root)
            geometry_warning = None
            try:
                elements = svg_geometry(root, page_number)
            except (ValueError, KeyError) as error:
                geometry_warning = f'Page {page_number}: element geometry unsupported ({error}); original SVG preserved as a static page.'
                warnings.append(geometry_warning)
                elements = []
                for e in root.iter():
                    for key in ('data-leaf', 'data-bbox', 'data-visible-bbox', 'data-parent-matrix'):
                        e.attrib.pop(key, None)
            width, height = page.rect.width, page.rect.height
            # Path geometry stays intact; accessible descriptions preserve source text.
            title = node('title', id=f'page-title-{page_number}')
            title.text = f'Page {page_number}'
            desc = node('desc', id=f'page-desc-{page_number}')
            desc.text = page.get_text()
            root.insert(0, title)
            root.insert(1, desc)
            root.set('role', 'img')
            root.set('aria-labelledby', f'{title.get("id")} {desc.get("id")}')
            root.set('data-source-page', str(page_number))
            name = f'page-{page_number:03d}'
            rel = f'extracted/{name}.svg'
            (staging / rel).write_bytes(ET.tostring(root, encoding='utf-8'))
            extracted_hashes[rel] = digest(staging / rel)
            page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(staging / 'reference' / f'{name}.png')
            row = {'page': page_number, 'width': width, 'height': height, 'text': page.get_text(), 'elements': elements, 'splitRectangles': splits}
            if geometry_warning:
                row['geometryWarning'] = geometry_warning
            inventory.append(row)
            slides.append({'page': page_number, 'title': f'{page_number}페이지', 'message': '', 'motions': [], 'remove': [], 'adjust': [], 'emphasis': []})
            hints = {'possibleTilesOrBars': [], 'possibleTraces': [], 'rasterImages': []}
            for item in elements:
                bbox = item['bboxPt']
                if not bbox or item.get('text') is not None:
                    continue
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
                if item['type'] == 'image':
                    hints['rasterImages'].append(item['id'])
                elif item['type'] == 'path':
                    if item.get('pathCommands') == 5 and item['fill'] not in (None, 'none', '#ffffff') and w > 1 and h > 1:
                        hints['possibleTilesOrBars'].append(item['id'])
                    if item['stroke'] and item.get('pathNumbers', 0) >= 8 and w > width * .07 and h > 2:
                        hints['possibleTraces'].append(item['id'])
            proposals.append({'page': page_number, **hints})
        renderer_warnings = fitz.TOOLS.mupdf_warnings()
        if renderer_warnings:
            warnings.append('PDF renderer reported: ' + renderer_warnings)
        write_json(staging / 'extraction-report.json', {'warnings': warnings, 'pages': pages})
        write_json(staging / 'inventory.json', {'schemaVersion': 1, 'pages': inventory})
        write_json(staging / 'proposals.json', {'note': 'Geometric candidates only; axes, tables and logos can match. Review before adding effects. No motions applied automatically.', 'pages': proposals})
        write_json(staging / 'deck.json', {'schemaVersion': 1, 'title': args.title or pdf_path.stem, 'sourceHashes': hashes, 'slides': slides})
        locked = {**hashes, **extracted_hashes}
        for relative in ['inventory.json', 'proposals.json', 'extraction-report.json'] + (['pptx-inventory.json'] if pptx_result else []):
            locked[relative] = digest(staging / relative)
        for file in (staging / 'reference').glob('*.png'):
            locked[file.relative_to(staging).as_posix()] = digest(file)
        write_json(staging / 'source-lock.json', {'toolVersion': VERSION, 'pymupdfVersion': fitz.__version__, 'hashes': locked})
        staging.rename(job)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        doc.close()
    print(json.dumps({'job': str(job), 'pages': pages, 'warnings': warnings, 'next': 'Run plan JOB for title/text/table/chart components, review effects, apply-plan, then build.'}, ensure_ascii=False))


def load_job(job):
    job = Path(job).expanduser().resolve()
    lock = read_json(job / 'source-lock.json')
    for relative, expected in lock['hashes'].items():
        path = job / relative
        if not path.is_file() or digest(path) != expected:
            fail(f'Input changed: {relative}. Create a new job and review selectors instead of reusing stale IDs.')
    config = read_json(job / 'deck.json')
    if not isinstance(config, dict) or config.get('schemaVersion') != 1:
        fail('Unsupported deck.json schemaVersion')
    if config.get('sourceHashes') != {k: v for k, v in lock['hashes'].items() if k.startswith('source/')}:
        fail('deck.json sourceHashes differs from source-lock.json')
    inventory = {p['page']: p for p in read_json(job / 'inventory.json')['pages']}
    if not isinstance(config.get('title'), str) or not isinstance(config.get('slides'), list) or not config['slides']:
        fail('deck.json needs title and at least one slide')
    for slide in config['slides']:
        if not isinstance(slide, dict):
            fail('Each slide must be an object')
        for field in ('motions', 'adjust', 'emphasis'):
            if not isinstance(slide.get(field, []), list) or any(not isinstance(rule, dict) for rule in slide.get(field, [])):
                fail(f'slide {field} must be an array of objects')
    pages = [s.get('page') for s in config['slides']]
    if any(type(p) is not int or p not in inventory for p in pages) or len(set(pages)) != len(pages):
        fail('Each slide must reference a unique extracted PDF page')
    return job, config, inventory


def selectors(rule, elements, label):
    ids = rule.get('ids')
    if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
        fail(f'{label}: ids must be a nonempty unique list')
    for key in ids:
        if key not in elements:
            fail(f'{label}: unknown element {key}')
    return ids


def apply_source_changes(root, slide, elements):
    by_id = {e.get('data-leaf'): e for e in root.iter() if e.get('data-leaf')}
    removed = slide.get('remove', [])
    if not isinstance(removed, list) or len(set(removed)) != len(removed) or any(key not in elements for key in removed):
        fail(f'Page {slide["page"]}: invalid removal IDs')
    for key in removed:
        e = by_id[key]
        e.getparent().remove(e)
    adjusted = set()
    for rule in slide.get('adjust', []):
        ids = selectors(rule, elements, 'adjust')
        dx, dy = numbers([rule.get('dx'), rule.get('dy')], 2, 'adjust dx/dy')
        if not rule.get('reason'):
            fail('Every layout adjustment needs a reason')
        for key in ids:
            if key in removed or key in adjusted:
                fail(f'{key}: duplicate adjustment or adjustment of removed element')
            adjusted.add(key)
            a, b, c, d, _, _ = elements[key]['parentMatrix']
            det = a * d - b * c
            if abs(det) < 1e-12:
                fail(f'{key}: noninvertible parent transform')
            lx, ly = (d * dx - c * dy) / det, (-b * dx + a * dy) / det
            e = by_id[key]
            e.set('transform', f'translate({lx} {ly}) ' + e.get('transform', ''))
            bbox = elements[key]['bboxPt']
            if bbox:
                e.set('data-bbox', ','.join(str(v) for v in [bbox[0] + dx, bbox[1] + dy, bbox[2] + dx, bbox[3] + dy]))
    return by_id, set(removed)


def compile_slide(job, slide, page):
    root = parse_svg(job / f'extracted/page-{slide["page"]:03d}.svg')
    elements = {e['id']: e for e in page['elements']}
    by_id, removed = apply_source_changes(root, slide, elements)
    seen = set()
    counts = collections.Counter()
    for rule in slide.get('motions', []):
        ids = selectors(rule, elements, 'motion')
        kind = rule.get('kind')
        if kind not in KINDS:
            fail(f'Unknown motion kind: {kind}')
        timing(rule)
        radial_attrs = radial_parameters(rule) if kind == 'radial' else {}
        for key in ids:
            if key in removed or key in seen:
                fail(f'{key}: removed element animated or duplicate motion rules')
            seen.add(key)
            source = by_id[key]
            item = elements[key]
            if kind == 'line' and (item['type'] != 'path' or not item.get('stroke') or item.get('fill') not in (None, 'none')):
                fail(f'{key}: line requires a stroked unfilled path; use wipe/fade for filled/raster charts')
            if kind in ('bar-x', 'bar-y', 'star', 'wipe'):
                matrix = item['parentMatrix']
                if abs(matrix[1]) > 1e-8 or abs(matrix[2]) > 1e-8 or abs(matrix[0] * matrix[3]) < 1e-12:
                    fail(f'{key}: rotated/skewed ancestor unsupported for this effect; use fade')
                if not item.get('bboxPt'):
                    fail(f'{key}: effect requires a bounding box')
            if kind == 'radial':
                if not item.get('bboxPt'):
                    fail(f'{key}: effect requires a bounding box')
                a, b, c, d, _, _ = numbers(item.get('parentMatrix'), 6, 'radial parent transform')
                determinant = a * d - b * c
                if not math.isfinite(determinant) or abs(determinant) < 1e-12:
                    fail(f'{key}: noninvertible parent transform')
                source.attrib.update(radial_attrs)
            origin = rule.get('origin')
            if kind.startswith('bar-') and origin is None:
                fail(f'{key}: bar effects require the actual chart zero as origin [x,y]')
            if kind == 'star' and origin is None:
                x, y, x2, y2 = map(float, source.get('data-bbox').split(','))
                origin = [(x + x2) / 2, (y + y2) / 2]
            if origin is not None:
                numbers(origin, 2, 'origin')
                source.set('data-origin', ','.join(str(v) for v in origin))
            source.set('data-motion', kind)
            source.set('data-duration', str(rule.get('duration', 900)))
            source.set('data-delay', str(rule.get('delay', 0)))
            counts[kind] += 1
    overlay = node('g', data_emphasis='true', pointer_events='none')
    for i, mark in enumerate(slide.get('emphasis', [])):
        x, y, x2, y2 = rectangle(mark.get('box'), 'emphasis box')
        if x < 0 or y < 0 or x2 > page['width'] or y2 > page['height']:
            fail('Emphasis must lie inside the slide')
        kind = mark.get('kind')
        color = mark.get('color', '#ff0000')
        if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            fail('emphasis color must be #RRGGBB')
        width = mark.get('width', 1.5)
        numbers([width], 1, 'emphasis width')
        if not 0 < width <= 20:
            fail('emphasis width must be in (0,20]')
        timing(mark)
        if kind == 'outline':
            e = node('path', d=f'M {x} {y} H {x2} V {y2} H {x} Z', fill='none', stroke=color, stroke_width=width)
        elif kind == 'underline':
            e = node('path', d=f'M {x} {y2} H {x2}', fill='none', stroke=color, stroke_width=width)
        elif kind == 'band':
            opacity = mark.get('opacity', .12)
            numbers([opacity], 1, 'band opacity')
            if not 0 < opacity <= 1:
                fail('band opacity must be in (0,1]')
            e = node('rect', x=x, y=y, width=x2-x, height=y2-y, fill=color, opacity=opacity)
        else:
            fail(f'Unknown emphasis kind: {kind}')
        e.set('data-bbox', ','.join(str(v) for v in [x, y, x2, y2]))
        e.set('data-parent-matrix', '1,0,0,1,0,0')
        if mark.get('animate', True):
            e.set('data-motion', 'fade' if kind == 'band' else 'line')
            e.set('data-duration', str(mark.get('duration', 1150)))
            e.set('data-delay', str(mark.get('delay', 0)))
        overlay.append(e)
    if len(overlay):
        root.append(overlay)
    return root, {'page': slide['page'], 'motions': dict(counts), 'removed': sorted(removed), 'adjustments': len(slide.get('adjust', [])), 'emphasis': len(overlay)}


def strip_motion(root):
    for overlay in list(root.xpath('//*[@data-emphasis]')):
        overlay.getparent().remove(overlay)
    for e in root.iter():
        for key in list(e.attrib):
            if key in ('data-motion', 'data-duration', 'data-delay', 'data-origin',
                       'data-center', 'data-radius', 'data-start-angle', 'data-sweep-angle', 'data-track-color'):
                del e.attrib[key]
    return ET.tostring(root, method='c14n')


def verify_geometry(job, config, inventory, output):
    for slide in config['slides']:
        page_number = slide['page']
        expected = parse_svg(job / f'extracted/page-{page_number:03d}.svg')
        elements = {e['id']: e for e in inventory[page_number]['elements']}
        apply_source_changes(expected, slide, elements)
        actual = parse_svg(output / f'assets/page-{page_number:03d}.svg')
        if strip_motion(expected) != strip_motion(actual):
            fail(f'Page {page_number}: unexpected source geometry or paint-order change')


def build_job(args):
    job, config, inventory = load_job(args.job)
    out = job / 'dist'
    if out.exists() and not (out / 'build-manifest.json').is_file():
        fail('dist exists but is not a managed build; move it before building')
    stage = Path(tempfile.mkdtemp(prefix='.ppt-motion-build-', dir=job))
    try:
        (stage / 'assets').mkdir()
        (stage / 'reference').mkdir()
        slides, reports = [], []
        for slide in config['slides']:
            page_number = slide['page']
            page = inventory[page_number]
            if not isinstance(slide.get('title', ''), str) or not isinstance(slide.get('message', ''), str):
                fail('Slide title/message must be strings')
            root, report = compile_slide(job, slide, page)
            relative = f'assets/page-{page_number:03d}.svg'
            (stage / relative).write_bytes(ET.tostring(root, encoding='utf-8'))
            reference = f'reference/page-{page_number:03d}.png'
            shutil.copyfile(job / reference, stage / reference)
            slides.append({'page': page_number, 'title': slide.get('title', ''), 'message': slide.get('message', ''), 'width': page['width'], 'height': page['height'], 'svg': relative, 'reference': reference, 'components': slide.get('components', [])})
            reports.append(report)
        for asset in ['index.html', 'viewer.js', 'viewer.css']:
            shutil.copyfile(ASSETS / asset, stage / asset)
        write_json(stage / 'deck.json', {'title': config['title'], 'slides': slides})
        verify_geometry(job, config, inventory, stage)
        files = {p.relative_to(stage).as_posix(): digest(p) for p in sorted(stage.rglob('*')) if p.is_file()}
        manifest = {'toolVersion': VERSION, 'configSha256': digest(job / 'deck.json'), 'sourceLockSha256': digest(job / 'source-lock.json'), 'files': files, 'slides': reports, 'geometryCheck': 'passed', 'visualReview': 'Browser comparison required; structural checks do not prove visual fidelity.'}
        write_json(stage / 'build-manifest.json', manifest)
        backup = job / '.previous-dist'
        if backup.exists():
            fail('.previous-dist exists; inspect it before rebuilding')
        if out.exists():
            out.rename(backup)
        try:
            stage.rename(out)
        except BaseException:
            if backup.exists():
                backup.rename(out)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print(json.dumps({'output': str(out), 'slides': reports, 'geometryCheck': 'passed'}, ensure_ascii=False))


def check_job(args):
    job, config, inventory = load_job(args.job)
    out = job / 'dist'
    manifest = read_json(out / 'build-manifest.json')
    if manifest['configSha256'] != digest(job / 'deck.json') or manifest['sourceLockSha256'] != digest(job / 'source-lock.json'):
        fail('Build is stale; run build after changing configuration')
    for relative, expected in manifest['files'].items():
        if not (out / relative).is_file() or digest(out / relative) != expected:
            fail(f'Built artifact changed: {relative}')
    verify_geometry(job, config, inventory, out)
    print(json.dumps({'status': 'passed', 'slides': len(config['slides']), 'checks': ['source hashes', 'extraction hashes', 'config hash', 'artifact hashes', 'source geometry and paint order'], 'visualReview': 'Review the browser comparison and animation start/mid/end separately.'}))


def inspect_job(args):
    job, config, inventory = load_job(args.job)
    if args.page not in inventory:
        fail(f'Page {args.page} was not extracted')
    page = inventory[args.page]
    rows = page['elements']
    if args.box:
        box = rectangle(list(map(float, args.box.split(','))), '--box')
        rows = [e for e in rows if e['bboxPt'] and box[0] <= (e['bboxPt'][0] + e['bboxPt'][2]) / 2 <= box[2] and box[1] <= (e['bboxPt'][1] + e['bboxPt'][3]) / 2 <= box[3]]
    if args.type:
        rows = [e for e in rows if e['type'] == args.type]
    if args.paint:
        rows = [e for e in rows if args.paint in (e['fill'], e['stroke'])]
    print(json.dumps({'page': args.page, 'width': page['width'], 'height': page['height'], 'count': len(rows), 'elements': rows}, ensure_ascii=False, indent=2))


def serve_job(args):
    job, _, _ = load_job(args.job)
    if not (job / 'dist/index.html').is_file():
        fail('Run build first')
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(job / 'dist'), **kw)
    with http.server.ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        print(f'Preview: http://127.0.0.1:{server.server_port}/ (Ctrl-C to stop)', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def plan_job(args):
    from motion_plan import make_plan
    job, config, inventory = load_job(args.job)
    target = Path(args.out).expanduser().resolve() if args.out else job / 'motion-plan.json'
    if target.exists():
        fail(f'Plan already exists: {target}. Edit it, or use --out for a separate plan; handwritten decisions are preserved.')
    pptx_path = job / 'pptx-inventory.json'
    pptx = read_json(pptx_path) if pptx_path.is_file() else None
    # Re-read stored PPTX when an older extraction lacks semantic roles. The
    # immutable old inventory is not rewritten and still passes its source lock.
    if pptx and (job / 'source/deck.pptx').is_file():
        from pptx_inventory import read_pptx
        pptx = read_pptx(job / 'source/deck.pptx')
    pages = {s['page']: inventory[s['page']] for s in config['slides']}
    plan = make_plan(job, config, pages, pptx, args.profile, args.slide_map,
                     digest(job / 'source-lock.json'), digest(job / 'deck.json'))
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json(target, plan)
    print(json.dumps({'plan': str(target), 'profile': args.profile,
                      'slides': len(plan['slides']), 'components': sum(len(s['components']) for s in plan['slides']),
                      'warnings': plan['warnings'], 'next': 'Review component effect/ids/message; apply-plan JOB; build JOB.'}, ensure_ascii=False))


def apply_plan_job(args):
    from motion_plan import apply_to_config
    job, config, inventory = load_job(args.job)
    path = Path(args.plan).expanduser().resolve() if args.plan else job / 'motion-plan.json'
    plan = read_json(path)
    if plan.get('sourceLockSha256') != digest(job / 'source-lock.json'):
        fail('Plan source differs from this job; regenerate it from the current source.')
    if plan.get('deckSha256') != digest(job / 'deck.json'):
        fail('Plan is stale because deck.json changed. Generate a new plan and review it; existing edits were preserved.')
    proposed = apply_to_config(plan, config, inventory)
    # Validate all effects and geometry before replacing the editable config.
    for slide in proposed['slides']:
        compile_slide(job, slide, inventory[slide['page']])
    history = job / 'history'
    history.mkdir(exist_ok=True)
    backup = history / f'deck-before-plan-{digest(job / "deck.json")[:16]}.json'
    if not backup.exists():
        shutil.copyfile(job / 'deck.json', backup)
    candidate = job / '.deck-plan-tmp.json'
    if candidate.exists():
        fail('An unfinished .deck-plan-tmp.json exists; inspect it before applying another plan.')
    try:
        write_json(candidate, proposed)
        candidate.replace(job / 'deck.json')
    finally:
        candidate.unlink(missing_ok=True)
    print(json.dumps({'config': str(job / 'deck.json'), 'backup': str(backup), 'slides': len(proposed['slides']), 'next': 'build then check; compare the final frame in the browser.'}, ensure_ascii=False))


def doctor(args):
    report = {'python': sys.version.split()[0], 'pymupdf': fitz.__version__,
              'lxml': '.'.join(map(str, ET.LXML_VERSION)),
              'powerpointInstalled': Path('/Applications/Microsoft PowerPoint.app').is_dir(),
              'libreoffice': shutil.which('libreoffice') or shutil.which('soffice'),
              'output': 'HTML presentation; original PPTX is not modified.',
              'pdfExport': 'Use PowerPoint File > Export/Save As > PDF with the intended fonts. Other renderers require visual comparison. No exporter runs automatically.'}
    if args.pptx:
        from pptx_inventory import read_pptx
        path = Path(args.pptx).expanduser().resolve()
        inventory = read_pptx(path)
        pdf = path.with_suffix('.pdf')
        report.update(pptx=str(path), slides=len(inventory['slides']),
                      hiddenSlides=[s['order'] for s in inventory['slides'] if s['hidden']],
                      matchingPdf=str(pdf) if pdf.is_file() else None)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def export_pdf(args):
    source = Path(args.pptx).expanduser().resolve()
    target = Path(args.out).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != '.pptx':
        fail('export-pdf requires an existing .pptx file')
    if target.exists() or target.suffix.lower() != '.pdf':
        fail('Choose a new .pdf output path; existing files are never overwritten')
    source_sha = digest(source)
    binary = shutil.which('libreoffice') or shutil.which('soffice')
    if not binary:
        fail('LibreOffice is not installed. Export PDF in PowerPoint with the intended fonts, then run init --pdf. doctor shows local export options.')
    with tempfile.TemporaryDirectory(prefix='ppt-motion-export-') as tmp:
        root = Path(tmp)
        # A separate profile avoids reusing a running office session or its state.
        cmd = [binary, '-env:UserInstallation=' + (root/'profile').as_uri(),
               '--headless', '--convert-to', 'pdf:impress_pdf_Export', '--outdir', str(root), str(source)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            fail('PDF export timed out after 180 seconds; source and destination were not modified')
        produced = root / (source.stem + '.pdf')
        if result.returncode or not produced.is_file():
            fail('LibreOffice did not create a PDF: ' + (result.stderr or result.stdout).strip()[:1500])
        with fitz.open(produced) as document:
            count = len(document)
            if not count: fail('Exported PDF has no pages')
        if digest(source) != source_sha:
            fail('The PPTX changed during conversion; inspect the source before retrying')
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation is also safe if another process created target meanwhile.
        with target.open('xb') as output, produced.open('rb') as incoming:
            shutil.copyfileobj(incoming, output)
    print(json.dumps({'pdf': str(target), 'pages': count, 'renderer': 'LibreOffice',
                      'sourceUnchanged': True, 'visualReviewRequired': 'Check fonts, chart labels, line wrapping and hidden-slide inclusion against PowerPoint before treating this PDF as the reference.'}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    subs = parser.add_subparsers(dest='command', required=True)
    init = subs.add_parser('init', help='Extract a new job from a matching PDF and optional PPTX')
    init.add_argument('--pdf', help='Matching PDF; optional when --pptx has a same-name PDF beside it')
    init.add_argument('--pptx')
    init.add_argument('--out', required=True)
    init.add_argument('--title')
    init.add_argument('--pages', help='Original PDF page numbers, e.g. 1,5-7,16')
    init.set_defaults(run=init_job)
    p = subs.add_parser('doctor', help='Show runtime/export options without modifying or exporting a deck')
    p.add_argument('--pptx')
    p.set_defaults(run=doctor)
    p = subs.add_parser('export-pdf', help='Export PPTX with installed LibreOffice; review fidelity before init')
    p.add_argument('--pptx', required=True)
    p.add_argument('--out', required=True, help='New PDF path; never overwrites an existing file')
    p.set_defaults(run=export_pdf)
    p = subs.add_parser('plan', help='Create a reviewable plan with title/text/table/chart regions')
    p.add_argument('job')
    p.add_argument('--out', help='New plan file; an existing plan is never overwritten')
    p.add_argument('--profile', choices=['research', 'explain', 'static'], default='research')
    p.add_argument('--slide-map', help='Confirmed PDF-page=PPTX-slide pairs, e.g. 1=1,2=3')
    p.set_defaults(run=plan_job)
    p = subs.add_parser('apply-plan', help='Validate a component plan and apply it with a config backup')
    p.add_argument('job')
    p.add_argument('--plan', help='Plan file; defaults to JOB/motion-plan.json')
    p.set_defaults(run=apply_plan_job)
    for name, function in [('build', build_job), ('check', check_job), ('inspect', inspect_job), ('serve', serve_job)]:
        p = subs.add_parser(name)
        p.add_argument('job')
        p.set_defaults(run=function)
        if name == 'inspect':
            p.add_argument('--page', type=int, required=True)
            p.add_argument('--box', help='Center-inside filter: left,top,right,bottom in PDF points')
            p.add_argument('--type', choices=['path', 'use', 'image', 'rect', 'circle'])
            p.add_argument('--paint', help='Exact fill or stroke, e.g. #ff0000')
        if name == 'serve':
            p.add_argument('--port', type=int, default=4319)
    args = parser.parse_args()
    try:
        args.run(args)
    except (ValueError, OSError, KeyError, TypeError, ET.XMLSyntaxError) as error:
        parser.exit(2, f'ppt-motion: {error}\n')


if __name__ == '__main__':
    main()
