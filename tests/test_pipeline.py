"""Black-box pipeline checks against a generated deck, using synthetic fixtures."""
from __future__ import annotations

import argparse
import base64
import contextlib
import copy
import importlib.util
import io
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import fitz
from lxml import etree as ET

PROJECT = Path(__file__).resolve().parents[1]
CLI = PROJECT / 'skill/ppt-motion/scripts/ppt_motion.py'
ASSETS = PROJECT / 'skill/ppt-motion/assets'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def canonical_without_motion(path):
    tree = ET.fromstring(Path(path).read_bytes())
    for group in tree.xpath('//*[@data-emphasis]'):
        group.getparent().remove(group)
    for node in tree.iter():
        for key in ('data-motion', 'data-duration', 'data-delay', 'data-origin',
                    'data-center', 'data-radius', 'data-start-angle', 'data-sweep-angle', 'data-track-color'):
            node.attrib.pop(key, None)
    return ET.tostring(tree, method='c14n')


def make_pdf(path):
    """Known page-space geometry: positive and negative bars share y=300 zero."""
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((50, 55), 'Synthetic slide: unchanged labels and axes', fontsize=18)
    page.draw_line((70, 300), (500, 300), color=(0, 0, 0), width=1)
    page.draw_rect(fitz.Rect(100, 140, 150, 300), color=None, fill=(0.8, 0.1, 0.1))
    page.draw_rect(fitz.Rect(200, 300, 250, 380), color=None, fill=(0.1, 0.2, 0.8))
    page.draw_polyline([(300, 260), (350, 220), (400, 250), (460, 150)],
                       color=(0.1, 0.6, 0.2), width=2, dashes='[5 3] 0')
    page.draw_rect(fitz.Rect(550, 180, 610, 240), color=None, fill=(0.8, 0.6, 0.2))
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 4, 4), False)
    pixmap.clear_with(128)
    page.insert_image(fitz.Rect(670, 180, 750, 260), stream=pixmap.tobytes('png'))
    page.insert_text((200, 420), 'Negative bar grows downward from zero', fontsize=11)
    second = doc.new_page(width=720, height=540)
    second.insert_text((50, 50), 'Static divider', fontsize=20)
    doc.save(path)
    doc.close()


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        absent = [name for name in ('index.html', 'viewer.js', 'viewer.css') if not (ASSETS/name).is_file()]
        if absent:
            raise RuntimeError(f'Actual viewer assets required for integration tests: {absent}')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='motion pipeline ')
        self.root = Path(self.temp.name)
        self.source = self.root / 'fixture deck.pdf'
        self.job = self.root / 'job'
        make_pdf(self.source)
        self.run_cli('init', '--pdf', self.source, '--out', self.job, '--title', 'Pipeline fixture')
        self.config = load(self.job/'deck.json')
        self.inventory = load(self.job/'inventory.json')['pages'][0]
        self.positive = self.at_box([100,140,150,300])
        self.negative = self.at_box([200,300,250,380])
        self.trace = self.at_box([300,150,460,260])
        self.tile = self.at_box([550,180,610,240])

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args, failure=None):
        result = subprocess.run([sys.executable, str(CLI), *map(str,args)],
                                capture_output=True, text=True, cwd=self.root)
        if failure is None:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return json.loads(result.stdout)
        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        self.assertNotIn('Traceback', result.stderr, result.stderr)
        self.assertIn(failure, result.stderr)
        return result

    def at_box(self, target):
        matches = [row for row in self.inventory['elements']
                   if row['bboxPt'] and all(abs(a-b)<0.02 for a,b in zip(row['bboxPt'],target))]
        self.assertEqual(len(matches), 1, (target, matches))
        return matches[0]['id']

    def configure(self):
        self.config['slides'][0].update({
            'message':'Growth and decline share the same zero baseline.',
            'motions':[
                {'ids':[self.positive,self.negative], 'kind':'bar-y', 'origin':[0,300], 'duration':800},
                {'ids':[self.trace], 'kind':'line', 'duration':900},
                {'ids':[self.tile], 'kind':'tile', 'duration':600},
            ],
            'emphasis':[{'kind':'outline','box':[80,120,270,395],'color':'#ff0000'}],
        })
        save(self.job/'deck.json',self.config)

    def test_standalone_html_preserves_assets_and_escapes_embedded_text(self):
        self.configure()
        self.config['title'] = '한글 </script><script>alert(1)</script> & title'
        self.config['slides'][0]['message'] = 'Literal <text> with \u2028 and \u2029.'
        save(self.job/'deck.json', self.config)
        self.run_cli('build', self.job)
        destination = self.root/'portable slide.html'
        result = self.run_cli('export-html', self.job, '--out', destination)
        self.assertTrue(result['standalone'])
        self.assertEqual(result['sha256'], sha(destination))
        html = ET.HTML(destination.read_bytes())
        self.assertEqual(len(html.xpath('//script')), 2)
        self.assertEqual(html.xpath('//script/@src | //link[@rel="stylesheet"]/@href'), [])
        bundle = json.loads(html.xpath('//script[@id="ppt-motion-bundle"]')[0].text)
        self.assertEqual(bundle['deck'], load(self.job/'dist/deck.json'))
        for slide in bundle['deck']['slides']:
            self.assertEqual(bundle['assets'][slide['svg']], (self.job/'dist'/slide['svg']).read_text(encoding='utf-8'))
            encoded = bundle['assets'][slide['reference']].split(',', 1)[1]
            self.assertEqual(base64.b64decode(encoded), (self.job/'dist'/slide['reference']).read_bytes())
        self.run_cli('check', self.job)

    def test_standalone_export_refuses_stale_tampered_or_existing_output(self):
        self.run_cli('build', self.job)
        destination = self.root/'presentation.html'
        self.run_cli('export-html', self.job, '--out', destination)
        original = destination.read_bytes()
        self.run_cli('export-html', self.job, '--out', destination, failure='already exists')
        self.assertEqual(destination.read_bytes(), original)
        self.config['slides'][0]['message'] = 'Changed after build'
        save(self.job/'deck.json', self.config)
        self.run_cli('export-html', self.job, '--out', self.root/'stale.html', failure='stale')
        self.assertFalse((self.root/'stale.html').exists())
        self.run_cli('build', self.job)
        (self.job/'dist/viewer.css').write_text('modified', encoding='utf-8')
        self.run_cli('export-html', self.job, '--out', self.root/'tampered.html', failure='artifact changed')
        self.assertFalse((self.root/'tampered.html').exists())

    def test_standalone_export_stays_outside_managed_directories(self):
        self.run_cli('build', self.job)
        self.run_cli('export-html', self.job, '--out', self.job/'dist/presentation.html', failure='outside managed')
        self.run_cli('export-html', self.job, '--out', self.root/'presentation.txt', failure='end in .html')

    def test_init_inspect_build_check_preserve_geometry_and_dimensions(self):
        self.assertEqual((self.inventory['width'], self.inventory['height']), (960,540))
        self.assertIn('unchanged labels', self.inventory['text'])
        self.assertTrue(all(row['fingerprint'] for row in self.inventory['elements']))
        self.assertEqual(self.config['slides'][0]['motions'], [])
        self.assertEqual(sha(self.source),sha(self.job/'source/deck.pdf'))
        selected = self.run_cli('inspect', self.job, '--page',1,'--box','195,295,255,385','--type','path')
        self.assertEqual([row['id'] for row in selected['elements']], [self.negative])
        self.configure()
        report = self.run_cli('build', self.job)
        self.assertEqual(report['geometryCheck'],'passed')
        dist = self.job/'dist'
        self.assertEqual(canonical_without_motion(self.job/'extracted/page-001.svg'),
                         canonical_without_motion(dist/'assets/page-001.svg'))
        self.assertEqual(canonical_without_motion(self.job/'extracted/page-002.svg'),
                         canonical_without_motion(dist/'assets/page-002.svg'))
        output = load(dist/'deck.json')
        self.assertEqual([(s['width'],s['height']) for s in output['slides']], [(960,540),(720,540)])
        tree = ET.fromstring((dist/'assets/page-001.svg').read_bytes())
        negative = tree.xpath(f'//*[@data-leaf="{self.negative}"]')[0]
        self.assertEqual(negative.get('data-origin'), '0,300')
        trace = tree.xpath(f'//*[@data-leaf="{self.trace}"]')[0]
        self.assertTrue(trace.get('stroke-dasharray'), 'Source dashes must not be replaced by solid paint.')
        self.assertTrue(tree.xpath('//*[local-name()="image"]'), 'Embedded raster asset must survive.')
        for asset in ('index.html','viewer.js','viewer.css'):
            self.assertEqual((dist/asset).read_bytes(),(ASSETS/asset).read_bytes())
        self.assertEqual(self.run_cli('check',self.job)['status'],'passed')

    def test_negative_bar_requires_explicit_zero_and_failed_build_is_atomic(self):
        self.run_cli('build',self.job)
        before = {p.relative_to(self.job/'dist').as_posix():sha(p) for p in (self.job/'dist').rglob('*') if p.is_file()}
        self.config['slides'][0]['motions'] = [{'ids':[self.negative],'kind':'bar-y'}]
        save(self.job/'deck.json',self.config)
        self.run_cli('build',self.job,failure='actual chart zero')
        after = {p.relative_to(self.job/'dist').as_posix():sha(p) for p in (self.job/'dist').rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        self.assertFalse(list(self.job.glob('.ppt-motion-build-*')))

    def test_declared_removal_allowed_but_accidental_output_edit_detected(self):
        self.config['slides'][0]['remove'] = [self.tile]
        save(self.job/'deck.json',self.config)
        self.run_cli('build',self.job)
        output = self.job/'dist/assets/page-001.svg'
        tree = ET.fromstring(output.read_bytes())
        self.assertFalse(tree.xpath(f'//*[@data-leaf="{self.tile}"]'))
        before = ET.fromstring((self.job/'extracted/page-001.svg').read_bytes())
        original = before.xpath(f'//*[@data-leaf="{self.tile}"]')[0]
        original.getparent().remove(original)
        self.assertEqual(ET.tostring(before,method='c14n'),ET.tostring(tree,method='c14n'))
        self.assertEqual(self.run_cli('check',self.job)['status'],'passed')
        positive = tree.xpath(f'//*[@data-leaf="{self.positive}"]')[0]
        positive.set('fill','#00ffff')
        output.write_bytes(ET.tostring(tree))
        self.run_cli('check',self.job,failure='Built artifact changed')
        # Even if an external process refreshes a file hash, source geometry /
        # paint comparison must independently reject an undeclared edit.
        manifest_path=self.job/'dist/build-manifest.json'
        manifest=load(manifest_path)
        manifest['files']['assets/page-001.svg']=sha(output)
        save(manifest_path,manifest)
        self.run_cli('check',self.job,failure='unexpected source geometry or paint-order change')

    def test_source_and_extraction_hashes_reject_stale_selectors(self):
        self.configure()
        self.run_cli('build',self.job)
        for relative in ('source/deck.pdf','extracted/page-001.svg','inventory.json'):
            with self.subTest(relative=relative):
                path=self.job/relative
                original=path.read_bytes()
                path.write_bytes(original+b'\n')
                self.run_cli('build',self.job,failure=f'Input changed: {relative}')
                self.run_cli('check',self.job,failure=f'Input changed: {relative}')
                path.write_bytes(original)
        self.config['sourceHashes']['source/deck.pdf']='0'*64
        save(self.job/'deck.json',self.config)
        self.run_cli('build',self.job,failure='sourceHashes differs')

    def test_repeat_build_reproducible_and_config_edits_require_rebuild(self):
        self.configure()
        self.run_cli('build',self.job)
        before={p.relative_to(self.job/'dist').as_posix():sha(p) for p in (self.job/'dist').rglob('*') if p.is_file()}
        self.run_cli('build',self.job)
        after={p.relative_to(self.job/'dist').as_posix():sha(p) for p in (self.job/'dist').rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        self.config['slides'][0]['message']='Revised interpretation, unchanged figures.'
        save(self.job/'deck.json',self.config)
        self.run_cli('check',self.job,failure='Build is stale')
        self.run_cli('build',self.job)
        self.assertEqual(self.run_cli('check',self.job)['status'],'passed')

    def test_invalid_motion_rules_fail_clearly(self):
        base=copy.deepcopy(self.config)
        cases=[
            ({'ids':['p01-no-such-leaf'],'kind':'fade'},'unknown element'),
            ({'ids':[self.positive],'kind':'explode'},'Unknown motion kind'),
            ({'ids':[self.positive],'kind':'line'},'line requires a stroked unfilled path'),
            ({'ids':[self.positive],'kind':'fade','duration':0},'duration must be at least 1'),
            ({'ids':[self.positive],'kind':'bar-y','origin':[300]},'origin: expected 2 finite numbers'),
        ]
        for rule,expected in cases:
            with self.subTest(rule=rule):
                config=copy.deepcopy(base)
                config['slides'][0]['motions']=[rule]
                save(self.job/'deck.json',config)
                self.run_cli('build',self.job,failure=expected)

    def test_invalid_slide_container_fails_clearly(self):
        self.config['slides']=['unexpected string instead of a slide']
        save(self.job/'deck.json',self.config)
        self.run_cli('build',self.job,failure='slide')

    def test_radial_slices_share_explicit_center_and_preserve_source_paths(self):
        source = self.root/'donut slices.pdf'
        document = fitz.open()
        page = document.new_page(width=400,height=400)
        for sign, color in ((1,(.1,.4,.7)),(-1,(.8,.3,.2))):
            # Two source annular quarters, with a real hole and independent paths.
            drawing = page.new_shape()
            drawing.draw_bezier((200+80*sign,200),(200+80*sign,155.817),
                                (200+44.183*sign,120),(200,120))
            drawing.draw_line((200,120),(200,155))
            drawing.draw_bezier((200,155),(200+24.853*sign,155),
                                (200+45*sign,175.147),(200+45*sign,200))
            drawing.draw_line((200+45*sign,200),(200+80*sign,200))
            drawing.finish(fill=color,color=None,closePath=True)
            drawing.commit()
        document.save(source)
        document.close()
        job = self.root/'radial-job'
        self.run_cli('init','--pdf',source,'--out',job)
        inventory = load(job/'inventory.json')['pages'][0]
        slices = [e for e in inventory['elements'] if e['type']=='path']
        self.assertEqual(len(slices),2)
        self.assertTrue(all([(e['bboxPt'][0]+e['bboxPt'][2])/2,
                             (e['bboxPt'][1]+e['bboxPt'][3])/2] != [200,200] for e in slices))
        original = (job/'extracted/page-001.svg').read_bytes()
        config = load(job/'deck.json')
        rule = {'kind':'radial','ids':[e['id'] for e in slices],'center':[200,200],
                'radius':82,'startAngle':0,'sweepAngle':-180,'trackColor':'#Dde2E8',
                'duration':1200,'delay':80}
        config['slides'][0]['motions']=[rule]
        save(job/'deck.json',config)
        report = self.run_cli('build',job)
        self.assertEqual(report['slides'][0]['motions'],{'radial':2})
        output = job/'dist/assets/page-001.svg'
        tree = ET.fromstring(output.read_bytes())
        for element in tree.xpath('//*[@data-motion="radial"]'):
            self.assertEqual({name:element.get(name) for name in (
                'data-center','data-radius','data-start-angle','data-sweep-angle','data-track-color')},
                {'data-center':'200,200','data-radius':'82','data-start-angle':'0',
                 'data-sweep-angle':'-180','data-track-color':'#Dde2E8'})
        self.assertEqual((job/'extracted/page-001.svg').read_bytes(),original)
        self.assertEqual(canonical_without_motion(output),canonical_without_motion(job/'extracted/page-001.svg'))
        self.assertEqual(self.run_cli('check',job)['status'],'passed')
        with fitz.open(stream=original,filetype='svg') as expected, \
             fitz.open(stream=output.read_bytes(),filetype='svg') as actual:
            self.assertEqual(expected[0].get_pixmap().samples,actual[0].get_pixmap().samples)

        rule.pop('startAngle');rule.pop('sweepAngle');rule.pop('trackColor')
        save(job/'deck.json',config)
        self.run_cli('build',job)
        defaults = ET.fromstring(output.read_bytes()).xpath('//*[@data-motion="radial"]')
        self.assertTrue(all(e.get('data-start-angle')=='-90' and e.get('data-sweep-angle')=='360'
                            and e.get('data-track-color') is None for e in defaults))
        self.assertEqual(self.run_cli('check',job)['status'],'passed')

    def test_radial_invalid_parameters_fail_without_replacing_build(self):
        self.run_cli('build',self.job)
        before = {p.relative_to(self.job/'dist').as_posix():sha(p)
                  for p in (self.job/'dist').rglob('*') if p.is_file()}
        base = {'ids':[self.tile],'kind':'radial','center':[580,210],'radius':45}
        cases = [('center',None,'radial center'),('center',[580],'radial center'),
                 ('center',[True,210],'radial center'),('center',[float('nan'),210],'radial center'),
                 ('radius',None,'radial radius'),('radius',True,'radial radius'),
                 ('radius',0,'radial radius'),('radius',-1,'radial radius'),
                 ('radius',float('inf'),'radial radius'),('radius','45','radial radius'),
                 ('startAngle',float('nan'),'radial startAngle'),('startAngle',False,'radial startAngle'),
                 ('sweepAngle',0,'radial sweepAngle'),('sweepAngle',361,'radial sweepAngle'),
                 ('sweepAngle',-361,'radial sweepAngle'),('sweepAngle',float('inf'),'radial sweepAngle'),
                 ('trackColor','#ccc','radial trackColor'),('trackColor','gray','radial trackColor'),
                 ('trackColor','#ffffff00','radial trackColor'),('trackColor',None,'radial trackColor')]
        for field, value, error in cases:
            with self.subTest(field=field,value=value):
                self.config['slides'][0]['motions']=[{**base,field:value}]
                save(self.job/'deck.json',self.config)
                self.run_cli('build',self.job,failure=error)
        after = {p.relative_to(self.job/'dist').as_posix():sha(p)
                 for p in (self.job/'dist').rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        self.assertFalse(list(self.job.glob('.ppt-motion-build-*')))

    def test_radial_accepts_rotated_ancestors_and_rejects_missing_geometry(self):
        engine = self.engine_module()
        job = self.root/'transformed-radial'
        (job/'extracted').mkdir(parents=True)
        for transform in ('rotate(25 100 100)','matrix(1 .2 .4 1 30 50)','matrix(-1 0 0 1 300 0)'):
            with self.subTest(transform=transform):
                root = ET.fromstring((f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400">'
                    f'<g transform="{transform}"><path d="M100 100C150 100 150 150 100 150L100 130Z" '
                    'fill="#2288cc"/></g></svg>').encode())
                page = {'width':400,'height':400,'elements':engine.svg_geometry(root,1)}
                (job/'extracted/page-001.svg').write_bytes(ET.tostring(root))
                slide = {'page':1,'motions':[{'kind':'radial','ids':[page['elements'][0]['id']],
                                            'center':[100,100],'radius':100}]}
                compiled, report = engine.compile_slide(job,slide,page)
                self.assertEqual(report['motions'],{'radial':1})
                self.assertEqual(engine.strip_motion(compiled),engine.strip_motion(root))
                singular = copy.deepcopy(page)
                singular['elements'][0]['parentMatrix']=[1,2,2,4,0,0]
                with self.assertRaisesRegex(ValueError,'noninvertible parent transform'):
                    engine.compile_slide(job,slide,singular)
                near_singular = copy.deepcopy(page)
                near_singular['elements'][0]['parentMatrix']=[1e-7,0,0,1e-7,0,0]
                with self.assertRaisesRegex(ValueError,'noninvertible parent transform'):
                    engine.compile_slide(job,slide,near_singular)
                no_bbox = copy.deepcopy(page)
                no_bbox['elements'][0]['bboxPt']=None
                with self.assertRaisesRegex(ValueError,'requires a bounding box'):
                    engine.compile_slide(job,slide,no_bbox)

    @staticmethod
    def engine_module():
        scripts = str(CLI.parent)
        spec = importlib.util.spec_from_file_location('ppt_motion_regression', CLI)
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, scripts)
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(scripts)
        return module

    def test_compound_hv_rectangles_become_individual_bars_at_original_positions(self):
        source = self.root/'compound bars.pdf'
        document = fitz.open()
        page = document.new_page(width=960,height=540)
        drawing = page.new_shape()
        drawing.draw_rect((100,140,150,300))
        drawing.draw_rect((200,300,250,380))
        drawing.finish(fill=(0.5,0.1,0.2),color=None)
        drawing.commit()
        original_svg = page.get_svg_image(text_as_path=True)
        original_root = ET.fromstring(original_svg.encode())
        path_data = [p.get('d','') for p in original_root.xpath('//*[local-name()="path"]')]
        self.assertTrue(any(d.count('M') == 2 and 'H' in d and 'V' in d for d in path_data))
        document.save(source)
        document.close()
        job = self.root/'compound-job'
        self.run_cli('init','--pdf',source,'--out',job)
        inventory = load(job/'inventory.json')['pages'][0]
        self.assertEqual(inventory['splitRectangles'],2)
        bars = [e for e in inventory['elements'] if e['type']=='path']
        self.assertEqual([e['bboxPt'] for e in bars], [[100,140,150,300],[200,300,250,380]])
        self.assertEqual(len({e['id'] for e in bars}),2)
        config = load(job/'deck.json')
        config['slides'][0]['motions']=[{'kind':'bar-y','ids':[e['id'] for e in bars],'origin':[0,300]}]
        save(job/'deck.json',config)
        self.run_cli('build',job)
        self.assertEqual(self.run_cli('check',job)['status'],'passed')
        # On this simple rectangle fixture the SVG renderer provides a useful
        # independent final-frame paint comparison (no PDF masks/fonts involved).
        with fitz.open(stream=original_svg.encode(),filetype='svg') as original, \
             fitz.open(stream=(job/'dist/assets/page-001.svg').read_bytes(),filetype='svg') as current:
            self.assertEqual(original[0].get_pixmap().samples,current[0].get_pixmap().samples)

    def test_overlapping_compound_rectangles_keep_fill_winding(self):
        engine = self.engine_module()
        source = (b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                  b'<path d="M10 10H90V90H10ZM30 30H70V70H30Z" fill="#770000" fill-rule="evenodd"/>'
                  b'</svg>')
        root = ET.fromstring(source)
        original = ET.tostring(root,method='c14n')
        self.assertEqual(engine.split_rectangles(root),0)
        self.assertEqual(ET.tostring(root,method='c14n'),original)
        self.assertEqual(len(root),1,'Splitting nested rectangles would fill the intended hole.')

    def test_unsupported_geometry_preserves_static_content_and_removes_partial_annotations(self):
        engine = self.engine_module()
        job = self.root/'static fallback'
        def unsupported(root, page_number):
            # Simulate an extractor that annotates a few nodes before it meets
            # a previously unseen SVG construct and raises a supported failure.
            leaf = root.xpath('//*[local-name()="path"]')[0]
            for key,value in {'data-leaf':'partial-id','data-bbox':'0,0,1,1',
                              'data-visible-bbox':'0,0,1,1','data-parent-matrix':'1,0,0,1,0,0'}.items():
                leaf.set(key,value)
            raise ValueError('synthetic unsupported geometry')
        args = argparse.Namespace(out=str(job),pdf=str(self.source),pptx=None,pages=None,title='Fallback')
        output = io.StringIO()
        with mock.patch.object(engine,'svg_geometry',side_effect=unsupported), contextlib.redirect_stdout(output):
            engine.init_job(args)
        report = json.loads(output.getvalue())
        self.assertEqual(len(report['warnings']),2)
        self.assertTrue(all('static page' in w for w in report['warnings']))
        inventory = load(job/'inventory.json')
        with fitz.open(self.source) as source:
            for record in inventory['pages']:
                self.assertEqual(record['elements'],[])
                self.assertIn('synthetic unsupported geometry',record['geometryWarning'])
                extracted = ET.fromstring((job/f"extracted/page-{record['page']:03d}.svg").read_bytes())
                self.assertFalse(extracted.xpath('//*[@data-leaf or @data-bbox or @data-visible-bbox or @data-parent-matrix]'))
                # Remove only the documented accessibility wrapper to compare
                # all underlying source shapes, glyphs, images and paint order.
                for child in list(extracted):
                    if ET.QName(child).localname in ('title','desc'):
                        extracted.remove(child)
                for attr in ('role','aria-labelledby','data-source-page'):
                    extracted.attrib.pop(attr,None)
                original = ET.fromstring(source[record['page']-1].get_svg_image(text_as_path=True).encode())
                self.assertEqual(ET.tostring(extracted,method='c14n'),ET.tostring(original,method='c14n'))
        self.run_cli('build',job)
        self.assertEqual(self.run_cli('check',job)['status'],'passed')
        for page in (1,2):
            self.assertEqual((job/f'extracted/page-{page:03d}.svg').read_bytes(),
                             (job/f'dist/assets/page-{page:03d}.svg').read_bytes())

    def test_init_never_overwrites_existing_work(self):
        original=(self.job/'deck.json').read_bytes()
        self.run_cli('init','--pdf',self.source,'--out',self.job,failure='Output already exists')
        self.assertEqual((self.job/'deck.json').read_bytes(),original)


if __name__=='__main__':
    unittest.main()
