"""Generic deck workflow checks, using generated PDF/PPTX without private presentation files."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from xml.sax.saxutils import escape
from zipfile import ZipFile

import fitz

PROJECT = Path(__file__).resolve().parents[1]
CLI = PROJECT / 'skill/ppt-motion/scripts/ppt_motion.py'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
C = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
TITLE = 'Operating results and the next quarter'
BODY = 'Revenue expanded while costs stayed controlled across both business lines.'
END = 'Discussion: priorities for the next quarter'


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(box, tag='a:xfrm'):
    x, y, right, bottom = box
    return (f'<{tag}><a:off x="{x*12700}" y="{y*12700}"/>'
            f'<a:ext cx="{(right-x)*12700}" cy="{(bottom-y)*12700}"/></{tag}>')


def text_shape(number, text, box, placeholder=None):
    ph = f'<p:nvPr><p:ph type="{placeholder}"/></p:nvPr>' if placeholder else ''
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{number}" name="Text {number}"/>{ph}</p:nvSpPr>'
            f'<p:spPr>{transform(box)}</p:spPr><p:txBody><a:p><a:r><a:t>{escape(text)}</a:t>'
            '</a:r></a:p></p:txBody></p:sp>')


def graphic_shape(number, content, box):
    return (f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{number}" name="Graphic {number}"/>'
            f'</p:nvGraphicFramePr>{transform(box, "p:xfrm")}<a:graphic><a:graphicData>'
            f'{content}</a:graphicData></a:graphic></p:graphicFrame>')


def slide(shapes, hidden=False):
    return (f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}" xmlns:c="{C}" show="{0 if hidden else 1}">'
            f'<p:cSld><p:spTree>{shapes}</p:spTree></p:cSld></p:sld>')


def write_pptx(path, unrelated=False, chart_types=None):
    """One hidden slide precedes two visible ones; order cannot be inferred from page count."""
    table = '<a:tbl><a:tblGrid><a:gridCol w="2286000"/><a:gridCol w="2286000"/></a:tblGrid>'
    for row in [('Region','Revenue'),('North','120')]:
        table += '<a:tr h="508000">'
        for value in row:
            table += f'<a:tc><a:txBody><a:p><a:r><a:t>{value}</a:t></a:r></a:p></a:txBody></a:tc>'
        table += '</a:tr>'
    table += '</a:tbl>'
    content = text_shape(10, TITLE, [40,20,700,65], 'title')
    content += text_shape(11, BODY, [40,80,900,115], 'body')
    content += graphic_shape(12, table, [40,140,400,230])
    content += graphic_shape(13, '<c:chart r:id="line"/>', [460,150,850,320])
    content += graphic_shape(14, '<c:chart r:id="bar"/>', [40,300,400,480])
    slides = [slide(text_shape(1, 'Confidential scratchpad and unpublished assumptions', [40,20,850,65]), True),
              slide(content), slide(text_shape(20, END, [40,20,850,70], 'ctrTitle'))]
    if unrelated:
        # Same slide/page count, but the text disagrees and one native slide is hidden.
        slides = [slide(text_shape(1, 'Legal notices concerning archival access permissions', [40,20,850,65]), True),
                  slide(text_shape(2, 'Meteorological observations from distant mountain ranges', [40,20,850,65]))]
    presentation = (f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst>' +
                    ''.join(f'<p:sldId id="{100+i}" r:id="s{i}"/>' for i in range(1,len(slides)+1)) +
                    '</p:sldIdLst><p:sldSz cx="12192000" cy="6858000"/></p:presentation>')
    rels = f'<Relationships xmlns="{REL}">' + ''.join(
        f'<Relationship Id="s{i}" Target="slides/slide{i}.xml"/>' for i in range(1,len(slides)+1)) + '</Relationships>'
    slide_rels = (f'<Relationships xmlns="{REL}"><Relationship Id="line" Target="../charts/line.xml"/>'
                  '<Relationship Id="bar" Target="../charts/bar.xml"/></Relationships>')
    with ZipFile(path, 'w') as archive:
        archive.writestr('ppt/presentation.xml',presentation)
        archive.writestr('ppt/_rels/presentation.xml.rels',rels)
        for index, value in enumerate(slides,1):
            archive.writestr(f'ppt/slides/slide{index}.xml',value)
        if not unrelated:
            archive.writestr('ppt/slides/_rels/slide2.xml.rels',slide_rels)
            for kind in ('line','bar'):
                chart_type = (chart_types or {}).get(kind,f'{kind}Chart')
                settings = '<c:barDir val="col"/><c:grouping val="clustered"/>' if chart_type=='barChart' else ''
                chart = (f'<c:chartSpace xmlns:c="{C}"><c:chart><c:plotArea><c:{chart_type}>{settings}'
                         '<c:ser><c:idx val="0"/><c:order val="0"/><c:val><c:numLit><c:ptCount val="2"/>'
                         '<c:pt idx="0"><c:v>5</c:v></c:pt><c:pt idx="1"><c:v>-2</c:v></c:pt>'
                         f'</c:numLit></c:val></c:ser></c:{chart_type}></c:plotArea></c:chart></c:chartSpace>')
                archive.writestr(f'ppt/charts/{kind}.xml',chart)


def write_pdf(path):
    document = fitz.open()
    page = document.new_page(width=960,height=540)
    page.insert_text((40,50),TITLE,fontsize=24)
    page.insert_text((40,103),BODY,fontsize=13)
    for row, values in enumerate([('Region','Revenue'),('North','120')]):
        for column, value in enumerate(values):
            x, y = 40+column*180, 140+row*45
            page.draw_rect(fitz.Rect(x,y,x+180,y+45),color=(.4,.4,.4),fill=(.93,.94,.95))
            page.insert_text((x+10,y+28),value,fontsize=12)
    page.draw_line((460,320),(850,320),color=(.4,.4,.4))
    page.draw_polyline([(480,300),(580,250),(680,280),(820,180)],color=(.1,.3,.7),width=2)
    page.draw_line((40,420),(400,420),color=(.4,.4,.4))
    page.draw_rect(fitz.Rect(90,330,150,420),color=None,fill=(.1,.3,.7))
    page.draw_rect(fitz.Rect(220,420,280,470),color=None,fill=(.6,.2,.1))
    page = document.new_page(width=960,height=540)
    page.insert_text((40,55),END,fontsize=24)
    document.save(path)
    document.close()


class MotionPlanTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='generic motion plan ')
        self.root = Path(self.temp.name).resolve()
        self.pdf = self.root/'quarterly review.pdf'
        self.pptx = self.pdf.with_suffix('.pptx')
        self.job = self.root/'job'
        write_pdf(self.pdf)
        write_pptx(self.pptx)
        self.run_cli('init','--pptx',self.pptx,'--out',self.job)
        self.plan_path = self.job/'motion-plan.json'

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self,*args,failure=None):
        result = subprocess.run([sys.executable,str(CLI),*map(str,args)],cwd=self.root,capture_output=True,text=True)
        self.assertEqual(result.returncode,0 if failure is None else 2,result.stdout+result.stderr)
        self.assertNotIn('Traceback',result.stderr)
        if failure is not None:
            self.assertIn(failure,result.stderr)
            return result
        return json.loads(result.stdout)

    def plan(self,profile='research',explicit=True):
        args = ['plan',self.job,'--profile',profile]
        if explicit: args += ['--slide-map','1=2,2=3']
        self.run_cli(*args)
        return load(self.plan_path)

    def component(self,plan,role):
        found = [c for c in plan['slides'][0]['components'] if c['role']==role]
        self.assertEqual(len(found),1,(role,found))
        return found[0]

    def reject_without_changes(self,plan,error):
        before = (self.job/'deck.json').read_bytes()
        save(self.plan_path,plan)
        self.run_cli('apply-plan',self.job,failure=error)
        self.assertEqual((self.job/'deck.json').read_bytes(),before)
        self.assertFalse((self.job/'.deck-plan-tmp.json').exists())

    def test_same_name_pdf_and_doctor_leave_originals_unchanged(self):
        before = {p.name:sha(p) for p in (self.pdf,self.pptx)}
        report = self.run_cli('doctor','--pptx',self.pptx)
        self.assertEqual(report['matchingPdf'],str(self.pdf))
        self.assertEqual(report['hiddenSlides'],[1])
        self.assertEqual(report['slides'],3)
        self.assertEqual(sha(self.pdf),sha(self.job/'source/deck.pdf'))
        self.assertEqual(sha(self.pptx),sha(self.job/'source/deck.pptx'))
        self.assertEqual({p.name:sha(p) for p in (self.pdf,self.pptx)},before)

    def test_research_detects_native_components_but_keeps_everything_static(self):
        plan = self.plan(explicit=False)
        components = plan['slides'][0]['components']
        self.assertEqual({c['role'] for c in components},{'title','text','table','line-chart','bar-chart'})
        self.assertTrue(all(c['effect']=='static' for s in plan['slides'] for c in s['components']))
        self.assertEqual(plan['slides'][0]['pptxMapping']['slide'],2)
        self.assertEqual(plan['slides'][0]['pptxMapping']['method'],'unique-text-match')
        self.assertEqual(plan['slides'][0]['title'],TITLE)
        self.assertGreater(len(self.component(plan,'title')['ids']),5)
        self.assertEqual(len(self.component(plan,'line-chart')['ids']),1)
        self.assertEqual(len(self.component(plan,'bar-chart')['ids']),2)
        self.assertEqual(self.component(plan,'table')['ids'],[])

    def test_native_pie_and_donut_are_static_until_slice_geometry_is_selected(self):
        pptx = self.root/'radial charts.pptx'
        write_pptx(pptx,chart_types={'line':'doughnutChart','bar':'pieChart'})
        job = self.root/'native-radial-job'
        self.run_cli('init','--pptx',pptx,'--pdf',self.pdf,'--out',job)
        self.run_cli('plan',job,'--profile','explain','--slide-map','1=2,2=3')
        plan = load(job/'motion-plan.json')
        for role in ('donut-chart','pie-chart'):
            component = self.component(plan,role)
            self.assertEqual(component['effect'],'static')
            self.assertEqual(component['suggestedEffect'],'radial')
            self.assertEqual(component['ids'],[], 'Chart bounds cannot distinguish slices from chart furniture.')
            self.assertNotIn('center',component, 'A chart shape extent is not the plot center.')

    def test_radial_roles_roundtrip_parameters_and_preserve_unrelated_rules(self):
        initial = self.plan()
        targets = self.component(initial,'bar-chart')['ids'] + self.component(initial,'line-chart')['ids']
        config = load(self.job/'deck.json')
        title = self.component(initial,'title')
        manual = {'kind':'fade','ids':title['ids'],'duration':250}
        config['slides'][0]['motions']=[manual]
        save(self.job/'deck.json',config)
        path = self.job/'radial-plan.json'
        self.run_cli('plan',self.job,'--out',path)
        plan = load(path)
        radial = []
        for index, role in enumerate(('donut-chart','pie-chart','gauge')):
            component = {'id':f'radial-{role}','role':role,'label':role,'box':[0,0,960,540],
                         'ids':[targets[index]],'effect':'radial','center':[440,250],'radius':450,
                         'startAngle':15+index*90,'sweepAngle':-270 if index==0 else 180,
                         'trackColor':'#dDe4E8','duration':1100,'delay':80}
            radial.append(component)
        plan['slides'][0]['components'].extend(radial)
        save(path,plan)
        self.run_cli('apply-plan',self.job,'--plan',path)
        applied = load(self.job/'deck.json')
        self.assertIn(manual,applied['slides'][0]['motions'])
        expected = {}
        for component in radial:
            rule = next(m for m in applied['slides'][0]['motions'] if m.get('componentId')==component['id'])
            expected[component['id']]=rule
            self.assertEqual(rule,{**{key:component[key] for key in (
                'ids','center','radius','startAngle','sweepAngle','trackColor','duration','delay')},
                'kind':'radial','componentId':component['id']})
        self.run_cli('build',self.job)
        self.assertEqual(self.run_cli('check',self.job)['status'],'passed')

        repeated_path = self.job/'radial-repeated.json'
        self.run_cli('plan',self.job,'--profile','explain','--out',repeated_path)
        repeated = load(repeated_path)
        for component in radial:
            self.assertEqual(self.component(repeated,component['role']),component)
        # Reapplying a partial edit keeps the other radial rules and manual fade.
        changed = copy.deepcopy(self.component(repeated,'gauge'))
        changed['sweepAngle']=-180
        repeated['slides']=repeated['slides'][:1]
        repeated['slides'][0]['components']=[changed]
        save(repeated_path,repeated)
        self.run_cli('apply-plan',self.job,'--plan',repeated_path)
        motions = load(self.job/'deck.json')['slides'][0]['motions']
        self.assertEqual(len(motions),4)
        self.assertIn(manual,motions)
        self.assertIn(expected['radial-donut-chart'],motions)
        self.assertIn(expected['radial-pie-chart'],motions)
        self.assertIn({**expected['radial-gauge'],'sweepAngle':-180},motions)

    def test_radial_plan_validation_is_atomic_and_cannot_target_labels(self):
        original = self.plan()
        for params, error in (({},'radial center'),({'center':[100,100]},'radial radius'),
                              ({'center':[100,100],'radius':-2},'radial radius'),
                              ({'center':[100,100],'radius':100,'sweepAngle':0},'radial sweepAngle'),
                              ({'center':[100,100],'radius':100,'trackColor':'silver'},'radial trackColor')):
            with self.subTest(params=params):
                plan = copy.deepcopy(original)
                component = self.component(plan,'bar-chart')
                component.update(role='gauge',effect='radial',**params)
                self.reject_without_changes(plan,error)
        labels = copy.deepcopy(original)
        self.component(labels,'title').update(effect='radial',center=[400,40],radius=400)
        self.reject_without_changes(labels,'Chart effects cannot target text labels')
        self.assertFalse((self.job/'history').exists())

    def test_explain_fades_a_paragraph_as_one_rule_and_preserves_static_table(self):
        plan = self.plan(profile='explain')
        body = self.component(plan,'text')
        self.assertEqual(body['label'],BODY)
        self.assertEqual(body['effect'],'fade')
        self.assertGreater(len(body['ids']),20)
        self.assertEqual(self.component(plan,'title')['effect'],'static')
        self.assertEqual(self.component(plan,'table')['effect'],'static')
        body.update(duration=625,delay=70)
        annotation = {'id':'review-bar-region','role':'annotation','label':'Selected business lines',
                      'box':[80,310,290,480],'ids':[],'effect':'outline','color':'#ff0000','width':2,
                      'duration':850,'delay':30}
        plan['slides'][0]['components'].append(annotation)
        save(self.plan_path,plan)
        self.run_cli('apply-plan',self.job)
        config = load(self.job/'deck.json')
        self.assertEqual(len(config['slides'][0]['motions']),1)
        self.assertEqual(config['slides'][0]['motions'][0]['ids'],body['ids'])
        self.assertEqual(config['slides'][0]['motions'][0]['kind'],'fade')

        # A manual rule and a generated component must survive later reviewed edits
        # independently. Replanning explain must not append a second body fade.
        manual = {'ids':self.component(plan,'line-chart')['ids'],'kind':'line','duration':1200}
        config['slides'][0]['motions'].append(manual)
        save(self.job/'deck.json',config)
        repeated_path = self.job/'repeated-plan.json'
        self.run_cli('plan',self.job,'--profile','explain','--slide-map','1=2,2=3','--out',repeated_path)
        repeated = load(repeated_path)
        self.assertEqual(self.component(repeated,'text')['duration'],625)
        self.assertEqual(self.component(repeated,'text')['delay'],70)
        self.assertEqual(self.component(repeated,'annotation'),annotation)
        self.run_cli('apply-plan',self.job,'--plan',repeated_path)
        config = load(self.job/'deck.json')
        motions = config['slides'][0]['motions']
        self.assertEqual(len(motions),2)
        self.assertIn(manual,motions)
        self.assertEqual(sum(m.get('componentId')==body['id'] for m in motions),1)
        self.assertEqual(len(config['slides'][0]['emphasis']),1)

        # A partial plan that changes only an annotation's colour retains both
        # the earlier generated body rule and the unrelated manual line rule.
        color_path = self.job/'annotation-color.json'
        self.run_cli('plan',self.job,'--out',color_path)
        color_plan = load(color_path)
        changed = self.component(color_plan,'annotation')
        changed['color']='#2233cc'
        color_plan['slides']=color_plan['slides'][:1]
        color_plan['slides'][0]['components']=[changed]
        save(color_path,color_plan)
        self.run_cli('apply-plan',self.job,'--plan',color_path)
        config = load(self.job/'deck.json')
        self.assertEqual(config['slides'][0]['motions'],motions)
        self.assertEqual(len(config['slides'][0]['emphasis']),1)
        self.assertEqual(config['slides'][0]['emphasis'][0]['color'],'#2233cc')

        disabled_path = self.job/'disable-body.json'
        self.run_cli('plan',self.job,'--profile','explain','--out',disabled_path)
        disabled = load(disabled_path)
        self.component(disabled,'text')['effect']='static'
        save(disabled_path,disabled)
        self.run_cli('apply-plan',self.job,'--plan',disabled_path)
        config = load(self.job/'deck.json')
        self.assertEqual(config['slides'][0]['motions'],[manual])
        self.assertEqual(config['slides'][0]['emphasis'][0]['color'],'#2233cc')
        self.run_cli('build',self.job)
        self.assertEqual(self.run_cli('check',self.job)['status'],'passed')

    def test_hidden_slide_counts_do_not_create_mapping_but_explicit_mapping_is_allowed(self):
        other = self.root/'unrelated.pptx'
        write_pptx(other,unrelated=True)
        job = self.root/'unmapped-job'
        self.run_cli('init','--pptx',other,'--pdf',self.pdf,'--out',job)
        self.run_cli('plan',job,'--profile','explain')
        unconfirmed = load(job/'motion-plan.json')
        self.assertTrue(all(s['pptxMapping'] is None for s in unconfirmed['slides']))
        self.assertTrue(any('mapping unresolved' in warning for warning in unconfirmed['warnings']))
        self.assertTrue(all(c['effect']=='static' for s in unconfirmed['slides'] for c in s['components']))
        confirmed_path = job/'confirmed.json'
        self.run_cli('plan',job,'--slide-map','1=2,2=1','--out',confirmed_path)
        confirmed = load(confirmed_path)
        self.assertEqual([s['pptxMapping'] for s in confirmed['slides']],
                         [{'slide':2,'method':'explicit'},{'slide':1,'method':'explicit'}])
        self.run_cli('plan',job,'--slide-map','1=2,2=2','--out',job/'invalid.json',failure='Invalid, duplicate')
        self.assertFalse((job/'invalid.json').exists())

    def test_table_motion_and_bar_without_zero_fail_atomically(self):
        original = self.plan()
        table = copy.deepcopy(original)
        self.component(table,'table')['effect']='fade'
        self.reject_without_changes(table,'Tables stay static')
        bar = copy.deepcopy(original)
        self.component(bar,'bar-chart')['effect']='bar-y'
        self.reject_without_changes(bar,'actual chart zero')
        self.assertFalse((self.job/'history').exists())

    def test_stale_source_or_user_edited_config_rejects_plan(self):
        original = self.plan()
        wrong_source = copy.deepcopy(original)
        wrong_source['sourceLockSha256']='0'*64
        self.reject_without_changes(wrong_source,'Plan source differs')
        config = load(self.job/'deck.json')
        config['slides'][0]['message']='A deliberate edit after planning.'
        save(self.job/'deck.json',config)
        self.reject_without_changes(original,'Plan is stale')

    def test_applying_plan_preserves_existing_motion_and_exact_config_backup(self):
        self.plan()
        original_plan = load(self.plan_path)
        bar_ids = self.component(original_plan,'bar-chart')['ids']
        config = load(self.job/'deck.json')
        existing = {'ids':bar_ids,'kind':'bar-y','origin':[0,420],'duration':700}
        config['slides'][0]['motions']=[existing]
        config['slides'][0]['emphasis']=[{'kind':'outline','box':[450,140,860,330],'color':'#123456'}]
        save(self.job/'deck.json',config)
        before = (self.job/'deck.json').read_bytes()
        fresh_path = self.job/'fresh.json'
        self.run_cli('plan',self.job,'--profile','explain','--slide-map','1=2,2=3','--out',fresh_path)
        report = self.run_cli('apply-plan',self.job,'--plan',fresh_path)
        after = load(self.job/'deck.json')
        self.assertEqual(after['slides'][0]['motions'][0],existing)
        self.assertEqual(len(after['slides'][0]['motions']),2)
        self.assertEqual(after['slides'][0]['emphasis'],config['slides'][0]['emphasis'])
        self.assertEqual(Path(report['backup']).read_bytes(),before)
        self.run_cli('build',self.job)
        self.assertEqual(self.run_cli('check',self.job)['status'],'passed')

    def test_unknown_id_and_known_id_outside_region_rejected(self):
        original = self.plan()
        unknown = copy.deepcopy(original)
        self.component(unknown,'text')['ids']=['p1-not-a-source-element']
        self.reject_without_changes(unknown,'invalid element IDs')
        outside = copy.deepcopy(original)
        self.component(outside,'text')['ids']=self.component(outside,'bar-chart')['ids']
        self.reject_without_changes(outside,'outside its region')

    def test_plan_does_not_overwrite_reviewed_plan(self):
        plan = self.plan()
        plan['slides'][0]['message']='Retain this presenter decision.'
        save(self.plan_path,plan)
        before = self.plan_path.read_bytes()
        self.run_cli('plan',self.job,failure='Plan already exists')
        self.assertEqual(self.plan_path.read_bytes(),before)

    def test_pptx_without_matching_pdf_has_actionable_export_guidance(self):
        self.pdf.unlink()
        report = self.run_cli('doctor','--pptx',self.pptx)
        self.assertIsNone(report['matchingPdf'])
        missing_job = self.root/'missing-pdf-job'
        self.run_cli('init','--pptx',self.pptx,'--out',missing_job,failure='Export a matching PDF')
        self.assertFalse(missing_job.exists())


if __name__=='__main__':
    unittest.main()
