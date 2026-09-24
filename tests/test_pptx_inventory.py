"""Public-contract tests for PPTX metadata; no PowerPoint dependency."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

SCRIPT = Path(__file__).resolve().parents[1] / 'skill/ppt-motion/scripts/pptx_inventory.py'
SPEC = importlib.util.spec_from_file_location('pptx_inventory', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
read_pptx = MODULE.read_pptx
P = MODULE.NS['p']
A = MODULE.NS['a']
R = MODULE.NS['r']
C = MODULE.NS['c']
E = 12700


def xfrm(x, y, w, h, *, group=None, attrs=''):
    s = f'<a:xfrm {attrs}><a:off x="{x*E}" y="{y*E}"/><a:ext cx="{w*E}" cy="{h*E}"/>'
    if group is not None:
        cx, cy, cw, ch = group
        s += f'<a:chOff x="{cx*E}" y="{cy*E}"/><a:chExt cx="{cw*E}" cy="{ch*E}"/>'
    return s + '</a:xfrm>'


def shape(shape_id, transform='', text='', placeholder=None):
    ph = f'<p:nvPr><p:ph type="{placeholder}"/></p:nvPr>' if placeholder is not None else ''
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="Shape {shape_id}"/>{ph}</p:nvSpPr>'
            f'<p:spPr>{transform}</p:spPr><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p>'
            '</p:txBody></p:sp>')


def group(shape_id, transform, children):
    return (f'<p:grpSp><p:nvGrpSpPr><p:cNvPr id="{shape_id}" name="Group {shape_id}"/></p:nvGrpSpPr>'
            f'<p:grpSpPr>{transform}</p:grpSpPr>{children}</p:grpSp>')


def slide(shapes, hidden=False):
    return (f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}" xmlns:c="{C}" show="{0 if hidden else 1}">'
            f'<p:cSld><p:spTree>{shapes}</p:spTree></p:cSld></p:sld>')


def make_fixture(path):
    nested = group('12', xfrm(20, 30, 10, 10, group=(0,0,10,10)), shape('13', xfrm(0,0,5,5), 'Nested'))
    shapes = group('10', xfrm(100,50,200,100,group=(10,20,100,50)),
                   shape('11', xfrm(20,30,10,10), 'Scaled') + nested)
    shapes += group('20', xfrm(100,50,200,100,group=(10,20,100,50), attrs='rot="5400000"'),
                    shape('21', xfrm(20,30,10,10), 'Rotated'))
    shapes += group('30', xfrm(10,10,100,100,group=(0,0,0,10)), shape('31', xfrm(0,0,5,5)))
    shapes += shape('40', text='Inherited placeholder')
    shapes += shape('41', xfrm(10,20,40,20,attrs='rot="5400000" flipH="1"'), 'Flip + rotate')
    shapes += ('<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="50" name="Chart"/></p:nvGraphicFramePr>'
               '<p:xfrm><a:off x="0" y="0"/><a:ext cx="1270000" cy="1270000"/></p:xfrm>'
               '<a:graphic><a:graphicData><c:chart r:id="chart1"/></a:graphicData></a:graphic></p:graphicFrame>')
    shapes += ('<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="51" name="External chart"/></p:nvGraphicFramePr>'
               '<a:graphic><a:graphicData><c:chart r:id="externalChart"/></a:graphicData></a:graphic></p:graphicFrame>')
    shapes += shape('60', xfrm(20,20,300,45), 'Slide title', placeholder='title')
    shapes += shape('61', text='Centered title', placeholder='ctrTitle')
    shapes += shape('62', xfrm(20,75,300,25), 'Short subtitle', placeholder='subTitle')
    shapes += shape('63', xfrm(20,110,300,40), 'Body paragraph', placeholder='body')
    shapes += shape('64', placeholder='body')
    shapes += ('<p:pic><p:nvPicPr><p:cNvPr id="65" name="Picture"/></p:nvPicPr>'
               f'<p:spPr>{xfrm(500,20,100,60)}</p:spPr></p:pic>')
    def cell(text='', attrs=''):
        return f'<a:tc {attrs}><a:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></a:txBody></a:tc>'
    table = ('<a:tbl><a:tblGrid><a:gridCol w="1270000"/><a:gridCol w="1270000"/>'
             '<a:gridCol w="1270000"/></a:tblGrid><a:tr h="508000">' +
             cell('Merged heading', 'rowSpan="2" gridSpan="2"') +
             cell('', 'rowSpan="2" hMerge="1"') + cell('Amount') + '</a:tr><a:tr h="508000">' +
             cell('', 'gridSpan="2" vMerge="true"') + cell('', 'hMerge="1" vMerge="1"') +
             cell('0') + '</a:tr></a:tbl>')
    shapes += ('<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="70" name="Native table"/></p:nvGraphicFramePr>'
               '<p:xfrm><a:off x="254000" y="2540000"/><a:ext cx="3810000" cy="1016000"/></p:xfrm>'
               f'<a:graphic><a:graphicData uri="{A}/table">{table}</a:graphicData></a:graphic></p:graphicFrame>')
    presentation = (f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst>'
                    '<p:sldId id="101" r:id="rSecond"/><p:sldId id="102" r:id="rFirst"/>'
                    '</p:sldIdLst><p:sldSz cx="12192000" cy="6858000"/></p:presentation>')
    rel_header = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    rels = rel_header + ('<Relationship Id="rFirst" Target="slides/slide1.xml"/>'
                        '<Relationship Id="rSecond" Target="slides/slide2.xml"/></Relationships>')
    slide_rels = rel_header + ('<Relationship Id="chart1" Target="../charts/chart1.xml"/>'
        '<Relationship Id="externalChart" Target="https://example.invalid/do-not-fetch" TargetMode="External"/></Relationships>')
    chart = (f'<c:chartSpace xmlns:c="{C}" xmlns:a="{A}"><c:chart><c:plotArea><c:lineChart>'
             '<c:grouping val="standard"/><c:ser>'
             '<c:idx val="9"/><c:order val="0"/><c:tx><c:v>Sales</c:v></c:tx>'
             '<c:cat><c:strRef><c:f>Sheet1!$A$2:$A$3</c:f><c:strCache><c:ptCount val="2"/>'
             '<c:pt idx="0"><c:v>2025</c:v></c:pt><c:pt idx="1"><c:v>2026</c:v></c:pt></c:strCache></c:strRef></c:cat>'
             '<c:val><c:numRef><c:f>Sheet1!$B$2:$B$3</c:f><c:numCache><c:formatCode>0.0</c:formatCode>'
             '<c:ptCount val="2"/><c:pt idx="0"><c:v>0</c:v></c:pt><c:pt idx="1"><c:v>12.5</c:v></c:pt>'
             '</c:numCache></c:numRef></c:val></c:ser></c:lineChart>'
             '<c:barChart><c:barDir val="bar"/><c:grouping val="stacked"/><c:ser>'
             '<c:idx val="10"/><c:order val="1"/><c:tx><c:v>Costs</c:v></c:tx>'
             '<c:val><c:numLit><c:ptCount val="2"/><c:pt idx="0"><c:v>2</c:v></c:pt>'
             '<c:pt idx="1"><c:v>-3</c:v></c:pt></c:numLit></c:val></c:ser></c:barChart>'
             '<c:catAx><c:axId val="100"/></c:catAx></c:plotArea></c:chart></c:chartSpace>')
    with ZipFile(path, 'w') as archive:
        for name, value in {
            'ppt/presentation.xml': presentation, 'ppt/_rels/presentation.xml.rels': rels,
            'ppt/slides/slide1.xml': slide(shape('1', xfrm(1,2,3,4), 'First file')),
            'ppt/slides/slide2.xml': slide(shapes, hidden=True),
            'ppt/slides/_rels/slide2.xml.rels': slide_rels, 'ppt/charts/chart1.xml': chart,
        }.items():
            archive.writestr(name, value)


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'fixture.pptx'
        make_fixture(self.path)
        self.result = read_pptx(self.path)
        self.shapes = {s['id']: s for s in MODULE._walk(self.result['slides'][0]['shapes'])}

    def tearDown(self):
        self.temp.cleanup()

    def test_presentation_order_hidden_dimensions(self):
        self.assertEqual((self.result['width'], self.result['height']), (960,540))
        self.assertEqual([s['part'] for s in self.result['slides']],
                         ['ppt/slides/slide2.xml', 'ppt/slides/slide1.xml'])
        self.assertEqual([s['hidden'] for s in self.result['slides']], [True,False])
        self.assertIsNone(self.result['pdfPageMapping'])

    def test_nested_nonzero_child_origins_and_scaling(self):
        self.assertEqual(self.shapes['11']['bboxPt'], [120,70,140,90])
        self.assertEqual(self.shapes['13']['bboxPt'], [120,70,130,80])
        self.assertEqual(self.shapes['13']['parentId'], '12')
        self.assertEqual(self.shapes['13']['localBoxPt'], [0,0,5,5])
        self.assertEqual(self.result['slides'][0]['text'].count('Nested'), 1)

    def test_rotation_and_flip(self):
        self.assertEqual(self.shapes['20']['bboxPt'], [150,0,250,200])
        self.assertEqual(self.shapes['21']['bboxPt'], [210,20,230,40])
        self.assertEqual(self.shapes['41']['bboxPt'], [20,10,40,50])
        # Flip first, then rotate clockwise: original top-left ends at (40, 50).
        self.assertEqual(self.shapes['41']['cornersPt'][0], [40,50])

    def test_unknown_geometry_is_explicit(self):
        self.assertIsNone(self.shapes['40']['bboxPt'])
        self.assertIn('inheritance', self.shapes['40']['unsupportedReason'])
        self.assertIsNone(self.shapes['31']['bboxPt'])
        self.assertFalse(self.shapes['31']['bboxReliable'])
        self.assertIn('zero', self.shapes['31']['unsupportedReason'])
        # Group own rectangle remains known when its child mapping is invalid.
        self.assertEqual(self.shapes['30']['bboxPt'], [10,10,110,110])

    def test_chart_cache_zero_value_and_external_link(self):
        chart = self.shapes['50']['charts'][0]
        self.assertEqual(chart['part'], 'ppt/charts/chart1.xml')
        ser = chart['series'][0]
        self.assertEqual(ser['chartType'], 'lineChart')
        self.assertEqual(ser['tx']['literal'], 'Sales')
        self.assertEqual(ser['val']['formulas'], ['Sheet1!$B$2:$B$3'])
        self.assertEqual([p['number'] for p in ser['val']['caches'][0]['points']], [0,12.5])
        external = self.shapes['51']['charts'][0]
        self.assertTrue(external['external'])
        self.assertIn('not opened', external['unsupportedReason'])

    def test_native_content_roles_and_title_placeholders(self):
        self.assertEqual(self.shapes['60']['role'], 'title')
        self.assertEqual(self.shapes['60']['placeholderType'], 'title')
        self.assertEqual(self.shapes['61']['role'], 'title')
        self.assertEqual(self.shapes['61']['placeholderType'], 'ctrTitle')
        self.assertEqual(self.shapes['61']['placeholder'], {'type': 'ctrTitle'})
        self.assertFalse(self.shapes['61']['bboxReliable'])
        self.assertEqual(self.shapes['62']['role'], 'text')
        self.assertEqual(self.shapes['62']['placeholderType'], 'subTitle')
        self.assertEqual(self.shapes['63']['role'], 'text')
        self.assertEqual(self.shapes['64']['role'], 'text')  # Empty body placeholder.
        self.assertEqual(self.shapes['11']['role'], 'text')  # Ordinary text box.
        self.assertEqual(self.shapes['31']['role'], 'shape')
        self.assertEqual(self.shapes['10']['role'], 'group')
        self.assertEqual(self.shapes['65']['role'], 'image')
        self.assertEqual(self.shapes['50']['role'], 'chart')
        self.assertEqual(self.shapes['51']['role'], 'chart')  # External is still a native chart.

    def test_native_table_preserves_grid_merges_and_text(self):
        shape = self.shapes['70']
        self.assertEqual(shape['kind'], 'graphicFrame')
        self.assertEqual(shape['role'], 'table')
        self.assertEqual(shape['bboxPt'], [20,200,320,280])
        table = shape['table']
        self.assertEqual((table['rows'],table['columns'],table['indexBase']), (2,3,0))
        cells = {(c['row'],c['column']):c for c in table['cells']}
        self.assertEqual(len(cells), 6)
        self.assertEqual(cells[0,0], {'row':0,'column':0,'text':'Merged heading',
                                     'rowSpan':2,'colSpan':2,'hMerge':False,'vMerge':False})
        self.assertTrue(cells[0,1]['hMerge'])
        self.assertEqual(cells[0,1]['rowSpan'], 2)
        self.assertTrue(cells[1,0]['vMerge'])
        self.assertEqual(cells[1,0]['colSpan'], 2)
        self.assertTrue(cells[1,1]['hMerge'] and cells[1,1]['vMerge'])
        self.assertEqual(cells[1,2]['text'], '0')
        self.assertEqual((cells[1,2]['rowSpan'],cells[1,2]['colSpan']), (1,1))
        self.assertEqual(self.result['slides'][0]['text'].count('Merged heading'), 1)

    def test_combo_chart_settings_remain_per_plot(self):
        chart = self.shapes['50']['charts'][0]
        self.assertEqual(chart['plotTypes'], ['lineChart','barChart'])
        self.assertEqual(chart['plots'], [{'chartType':'lineChart','grouping':'standard'},
                                        {'chartType':'barChart','barDirection':'bar','grouping':'stacked'}])
        self.assertEqual(chart['barDirection'], 'bar')
        self.assertNotIn('grouping', chart)  # A combination chart has no one shared grouping.
        self.assertEqual(chart['series'][0]['grouping'], 'standard')
        self.assertEqual(chart['series'][1]['grouping'], 'stacked')
        self.assertEqual(chart['series'][1]['barDirection'], 'bar')
        self.assertEqual([p['number'] for p in chart['series'][1]['val']['caches'][0]['points']], [2,-3])
        self.assertEqual(self.shapes['51']['charts'][0]['plotTypes'], [])

    def test_invalid_table_span_is_not_silently_repaired(self):
        table = MODULE.ET.fromstring(f'<a:tbl xmlns:a="{A}"><a:tr><a:tc rowSpan="0" gridSpan="bad"/></a:tr></a:tbl>')
        result = MODULE._table(table)
        self.assertEqual((result['rows'],result['columns']), (1,1))
        cell = result['cells'][0]
        self.assertIsNone(cell['rowSpan'])
        self.assertIsNone(cell['colSpan'])
        self.assertEqual(len(cell['warnings']), 2)

    def test_bad_zip_and_missing_part_have_meaningful_errors(self):
        bad = Path(self.temp.name) / 'bad.pptx'
        bad.write_text('not a zip')
        with self.assertRaisesRegex(ValueError, 'Cannot read PPTX'):
            read_pptx(bad)
        with ZipFile(bad, 'w') as archive:
            archive.writestr('other.xml', '<a/>')
        with self.assertRaisesRegex(ValueError, 'missing package part'):
            read_pptx(bad)



if __name__ == '__main__':
    unittest.main()
