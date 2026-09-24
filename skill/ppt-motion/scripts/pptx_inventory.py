"""Read PPTX metadata without Office, rendering, or executing embedded content.

The PDF/SVG inventory remains the visual authority. Bounding boxes here describe
transformed OOXML shape extents, not glyph ink, shadows, or rendered chart areas.
"""
from __future__ import annotations

import math
import posixpath
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
}
EMU_PER_PT = 12700.0
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
SHAPE_TAGS = {"sp", "pic", "cxnSp", "graphicFrame", "grpSp", "contentPart"}


def _tag(node):
    return node.tag.rsplit("}", 1)[-1]


def _true(value):
    return str(value).lower() in {"1", "true", "on"}


def _mul(left, right):
    a, b, c, d, e, f = left
    g, h, i, j, k, l = right
    return (a*g+c*h, b*g+d*h, a*i+c*j, b*i+d*j, a*k+c*l+e, b*k+d*l+f)


def _point(matrix, x, y):
    a, b, c, d, e, f = matrix
    return a*x+c*y+e, b*x+d*y+f


def _rounded(values):
    return [round(float(v), 6) for v in values]


def _extent(xfrm):
    off, ext = xfrm.find("a:off", NS), xfrm.find("a:ext", NS)
    if off is None or ext is None:
        raise ValueError("transform lacks off/ext")
    x, y = float(off.attrib["x"]), float(off.attrib["y"])
    w, h = float(ext.attrib["cx"]), float(ext.attrib["cy"])
    if w < 0 or h < 0 or not all(math.isfinite(v) for v in (x, y, w, h)):
        raise ValueError("transform has invalid extents")
    return x, y, w, h


def _orientation(xfrm, x, y, w, h):
    # DrawingML uses clockwise positive angles in screen coordinates. Flip the
    # local axes before rotating, both about the shape/group extent centre.
    angle = math.radians(float(xfrm.get("rot", "0")) / 60000.0)
    if not math.isfinite(angle):
        raise ValueError("transform has invalid rotation")
    cosine, sine = math.cos(angle), math.sin(angle)
    sx = -1.0 if _true(xfrm.get("flipH")) else 1.0
    sy = -1.0 if _true(xfrm.get("flipV")) else 1.0
    cx, cy = x+w/2, y+h/2
    return _mul((1, 0, 0, 1, cx, cy), _mul(
        (cosine*sx, sine*sx, -sine*sy, cosine*sy, 0, 0),
        (1, 0, 0, 1, -cx, -cy)))


def _box(matrix, extent):
    x, y, w, h = extent
    corners = [_point(matrix, px, py) for px, py in ((x,y), (x+w,y), (x+w,y+h), (x,y+h))]
    xs, ys = zip(*corners)
    return _rounded(v / EMU_PER_PT for v in (min(xs), min(ys), max(xs), max(ys))), [
        _rounded((px/EMU_PER_PT, py/EMU_PER_PT)) for px, py in corners]


def _xml(archive, name):
    try:
        return ET.fromstring(archive.read(name))
    except KeyError as exc:
        raise ValueError(f"PPTX is missing package part: {name}") from exc
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML in PPTX part {name}: {exc}") from exc


def _target(part, target):
    target = unquote(target)
    if "\\" in target or "\x00" in target:
        raise ValueError(f"Invalid package relationship target in {part}")
    result = posixpath.normpath(target.lstrip("/") if target.startswith("/") else
                               posixpath.join(posixpath.dirname(part), target))
    if result == ".." or result.startswith("../"):
        raise ValueError(f"Package relationship escapes archive root in {part}")
    return result


def _relationships(archive, part):
    name = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part)+".rels")
    if name not in archive.namelist():
        return {}
    result = {}
    for rel in _xml(archive, name):
        if _tag(rel) != "Relationship":
            continue
        attrs = dict(rel.attrib)
        attrs["external"] = attrs.get("TargetMode", "").lower() == "external"
        if not attrs["external"]:
            attrs["part"] = _target(part, attrs.get("Target", ""))
        result[attrs.get("Id", "")] = attrs
    return result


def _text(shape):
    # Only the shape's own text or table text: grouping must not duplicate child text.
    if _tag(shape) == "grpSp":
        return ""
    paragraphs = []
    for paragraph in shape.findall(".//a:p", NS):
        fragments = []
        for node in paragraph.iter():
            if node.tag == f"{{{NS['a']}}}t":
                fragments.append(node.text or "")
            elif node.tag == f"{{{NS['a']}}}br":
                fragments.append("\n")
        paragraphs.append("".join(fragments))
    return "\n".join(paragraphs)


def _table(table):
    """Describe native table cells, including merged continuation cells.

    Row and column indexes follow the stored grid and are zero-based. A merged
    cell's gridSpan is exposed as colSpan; its hMerge/vMerge continuations are
    retained rather than counted as independent text blocks.
    """
    rows = table.findall("a:tr", NS)
    grid = table.findall("a:tblGrid/a:gridCol", NS)
    result = {"rows": len(rows), "columns": len(grid) or max(
        (len(row.findall("a:tc", NS)) for row in rows), default=0),
        "indexBase": 0, "cells": []}
    for row_index, row in enumerate(rows):
        for column_index, cell in enumerate(row.findall("a:tc", NS)):
            item = {"row": row_index, "column": column_index, "text": _text(cell),
                    "hMerge": _true(cell.get("hMerge")), "vMerge": _true(cell.get("vMerge"))}
            for source, target in (("rowSpan", "rowSpan"), ("gridSpan", "colSpan")):
                raw = cell.get(source, "1")
                try:
                    value = int(raw)
                    if value < 1:
                        raise ValueError("span must be positive")
                    item[target] = value
                except ValueError:
                    item[target] = None
                    item.setdefault("warnings", []).append(f"Invalid {source}: {raw}")
            result["cells"].append(item)
    return result


def _cache(container):
    if container is None:
        return None
    result = {"formulas": [node.text or "" for node in container.findall(".//c:f", NS)], "caches": []}
    for node in container.iter():
        kind = _tag(node)
        if kind not in {"strCache", "numCache", "strLit", "numLit", "multiLvlStrCache"}:
            continue
        cache = {"kind": kind}
        count = node.find("c:ptCount", NS)
        if count is not None:
            cache["declaredCount"] = count.get("val")
        fmt = node.find("c:formatCode", NS)
        if fmt is not None:
            cache["formatCode"] = fmt.text or ""
        def points(parent):
            values = []
            for point in parent.findall("c:pt", NS):
                value = point.find("c:v", NS)
                item = {"index": point.get("idx"), "value": value.text if value is not None else None}
                if kind in {"numCache", "numLit"}:
                    try:
                        number = float(item["value"])
                        if math.isfinite(number):
                            item["number"] = number
                    except (TypeError, ValueError):
                        pass
                values.append(item)
            return values
        if kind == "multiLvlStrCache":
            cache["levels"] = [points(level) for level in node.findall("c:lvl", NS)]
        else:
            cache["points"] = points(node)
        result["caches"].append(cache)
    # A literal series title may have no cache.
    direct = container.find("c:v", NS)
    if direct is not None:
        result["literal"] = direct.text or ""
    return result


def _chart(archive, rel_id, relationships):
    result = {"relationshipId": rel_id, "plotTypes": [], "plots": [], "series": []}
    rel = relationships.get(rel_id)
    if rel is None:
        result["unsupportedReason"] = "chart relationship is missing"
        return result
    if rel["external"]:
        result.update(external=True, target=rel.get("Target"), unsupportedReason="external chart was not opened")
        return result
    result["part"] = rel["part"]
    try:
        root = _xml(archive, rel["part"])
    except ValueError as exc:
        result["unsupportedReason"] = str(exc)
        return result
    result["title"] = "".join(node.text or "" for node in root.findall("c:chart/c:title//a:t", NS))
    area = root.find("c:chart/c:plotArea", NS)
    if area is None:
        result["unsupportedReason"] = "chart has no supported plotArea"
        return result
    for plot in area:
        plot_type = _tag(plot)
        if not plot.tag.startswith(f"{{{NS['c']}}}") or not plot_type.endswith("Chart"):
            continue
        metadata = {"chartType": plot_type}
        for source, target in (("barDir", "barDirection"), ("grouping", "grouping")):
            setting = plot.find(f"c:{source}", NS)
            if setting is not None and setting.get("val") is not None:
                metadata[target] = setting.get("val")
        result["plots"].append(metadata)
        if plot_type not in result["plotTypes"]:
            result["plotTypes"].append(plot_type)
        for ser in plot.findall("c:ser", NS):
            idx, order = ser.find("c:idx", NS), ser.find("c:order", NS)
            item = {**metadata, "index": idx.get("val") if idx is not None else None,
                    "order": order.get("val") if order is not None else None}
            for name in ("tx", "cat", "val", "xVal", "yVal", "bubbleSize"):
                cache = _cache(ser.find(f"c:{name}", NS))
                if cache is not None:
                    item[name] = cache
            result["series"].append(item)
    # Convenience fields are unambiguous only when every recorded setting agrees.
    # Combination charts retain each distinct setting under plots and series.
    for key in ("barDirection", "grouping"):
        values = {plot[key] for plot in result["plots"] if key in plot}
        if len(values) == 1:
            result[key] = values.pop()
    result["cacheNotice"] = "Cached workbook values may be stale; formulas are recorded, never evaluated."
    return result


def _shape(archive, shape, parent_matrix, relationships, parent_id=None, ancestor_reason=None):
    kind = _tag(shape)
    props = next((child.find("p:cNvPr", NS) for child in shape
                  if _tag(child).startswith("nv") and child.find("p:cNvPr", NS) is not None), None)
    shape_id = props.get("id") if props is not None else None
    result = {"id": shape_id, "name": props.get("name", "") if props is not None else "",
              "kind": kind, "role": "shape", "text": _text(shape), "parentId": parent_id,
              "hidden": _true(props.get("hidden")) if props is not None else False,
              "bboxPt": None, "bboxReliable": False}
    xfrm = shape.find("p:grpSpPr/a:xfrm", NS) if kind == "grpSp" else (
        shape.find("p:xfrm", NS) if kind == "graphicFrame" else shape.find("p:spPr/a:xfrm", NS))
    child_matrix, child_reason = parent_matrix, ancestor_reason
    if xfrm is None:
        reason = "No direct transform; layout/master placeholder inheritance is not resolved."
        result["unsupportedReason"] = ancestor_reason or reason
        if kind == "grpSp":
            child_reason = reason
    else:
        try:
            extent = _extent(xfrm)
            x, y, w, h = extent
            result["localBoxPt"] = _rounded(v/EMU_PER_PT for v in (x, y, x+w, y+h))
            result["rotationDegrees"] = float(xfrm.get("rot", "0"))/60000.0
            result["flipH"], result["flipV"] = _true(xfrm.get("flipH")), _true(xfrm.get("flipV"))
            oriented = _mul(parent_matrix, _orientation(xfrm, *extent))
            if ancestor_reason:
                result["unsupportedReason"] = ancestor_reason
            else:
                result["bboxPt"], result["cornersPt"] = _box(oriented, extent)
                result["bboxReliable"] = True
                result["bboxKind"] = "transformed-shape-extent"
            if kind == "grpSp":
                off, ext = xfrm.find("a:chOff", NS), xfrm.find("a:chExt", NS)
                if off is None or ext is None:
                    raise ValueError("group transform lacks chOff/chExt")
                cx, cy, cw, ch = (float(off.get("x")), float(off.get("y")),
                                  float(ext.get("cx")), float(ext.get("cy")))
                if cw <= 0 or ch <= 0 or not all(math.isfinite(v) for v in (cx,cy,cw,ch)):
                    raise ValueError("group child extent is zero or invalid")
                child_matrix = _mul(oriented, (w/cw, 0, 0, h/ch, x-cx*w/cw, y-cy*h/ch))
                result["childCoordinateMatrixEmu"] = _rounded(child_matrix)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            result["unsupportedReason"] = f"Unsupported transform: {exc}"
            # A group's own extent can still be valid when child scaling is not.
            if kind == "grpSp":
                child_reason = result["unsupportedReason"]
            else:
                result["bboxPt"], result["bboxReliable"] = None, False
    placeholder = shape.find(".//p:ph", NS) if kind != "grpSp" else None
    if placeholder is not None:
        result["placeholder"] = dict(placeholder.attrib)
        # OOXML's centered-title spelling is ctrTitle, not centerTitle.
        result["placeholderType"] = placeholder.get("type", "obj")
    table = shape.find(".//a:tbl", NS) if kind != "grpSp" else None
    if table is not None:
        result["table"] = _table(table)
    for chart in shape.findall(".//c:chart", NS) if kind != "grpSp" else []:
        result.setdefault("charts", []).append(_chart(archive, chart.get(f"{{{NS['r']}}}id"), relationships))
    if kind == "grpSp":
        result["role"] = "group"
        result["children"] = [_shape(archive, child, child_matrix, relationships, shape_id, child_reason)
                              for child in shape if _tag(child) in SHAPE_TAGS]
    elif table is not None:
        result["role"] = "table"
    elif result.get("charts"):
        result["role"] = "chart"
    elif kind == "pic":
        result["role"] = "image"
    elif result.get("placeholderType") in {"title", "ctrTitle"}:
        result["role"] = "title"
    elif result["text"].strip() or result.get("placeholderType") in {"body", "subTitle", "dt", "ftr", "sldNum"}:
        result["role"] = "text"
    return result


def _walk(shapes):
    for shape in shapes:
        yield shape
        yield from _walk(shape.get("children", []))


def read_pptx(path) -> dict:
    """Return ordered slide metadata and transformed extents, including hidden slides.

    ``slides[].shapes`` is hierarchical. All boxes are [left, top, right, bottom]
    in points; ``localBoxPt`` uses the immediate group's coordinate system.
    Unknown inherited transforms receive a null box and an explicit reason.
    Roles describe native content, not inferred visual importance. Subtitle
    placeholders have role text and placeholderType subTitle. Native table cell
    coordinates are zero-based; chart plot metadata is recorded per plot.
    No PDF page mapping is inferred, including when slide counts happen to match.
    """
    try:
        with ZipFile(path) as archive:
            part = "ppt/presentation.xml"
            root = _xml(archive, part)
            if root.tag != f"{{{NS['p']}}}presentation":
                raise ValueError("Unsupported PPTX presentation namespace; expected transitional OOXML.")
            size = root.find("p:sldSz", NS)
            if size is None:
                raise ValueError("PPTX presentation has no slide size.")
            try:
                width, height = float(size.attrib["cx"])/EMU_PER_PT, float(size.attrib["cy"])/EMU_PER_PT
                if width <= 0 or height <= 0 or not all(math.isfinite(v) for v in (width, height)):
                    raise ValueError("invalid dimensions")
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"PPTX has invalid slide size: {exc}") from exc
            relationships = _relationships(archive, part)
            result = {"filename": Path(path).name, "width": width, "height": height, "units": "pt",
                      "slides": [], "pdfPageMapping": None,
                      "limitations": ["PDF/SVG is the visual authority; this inventory does not render PPTX.",
                       "Bounds describe transformed shape extents and exclude text overflow, strokes, shadows and other effects.",
                       "Master/layout inherited shapes and inherited placeholder transforms are not resolved.",
                       "Hidden slides are included; PDF export may omit them, so page mapping must be confirmed."]}
            for order, entry in enumerate(root.findall("p:sldIdLst/p:sldId", NS), start=1):
                rel_id = entry.get(f"{{{NS['r']}}}id")
                rel = relationships.get(rel_id)
                if rel is None or rel["external"]:
                    raise ValueError(f"Slide {order} has a missing or external relationship: {rel_id}")
                slide_part = rel["part"]
                slide = _xml(archive, slide_part)
                tree = slide.find("p:cSld/p:spTree", NS)
                if tree is None:
                    raise ValueError(f"Slide {order} has no shape tree: {slide_part}")
                slide_rels = _relationships(archive, slide_part)
                shapes = [_shape(archive, child, IDENTITY, slide_rels)
                          for child in tree if _tag(child) in SHAPE_TAGS]
                flattened = list(_walk(shapes))
                unsupported = [s["id"] for s in flattened if not s["bboxReliable"]]
                # AlternateContent can contain version-specific shapes. Do not
                # double-count its Choice/Fallback or silently pretend it was read.
                alternate_count = sum(_tag(node) == "AlternateContent" for node in tree.iter())
                warnings = []
                if alternate_count:
                    warnings.append(f"{alternate_count} AlternateContent container(s) not decoded; inspect PDF for these objects.")
                result["slides"].append({"order": order, "slideId": entry.get("id"),
                    "relationshipId": rel_id, "part": slide_part,
                    "hidden": slide.get("show", "1").lower() in {"0", "false", "off"},
                    "shapes": shapes, "shapeCount": len(flattened),
                    "unsupportedShapeIds": unsupported, "warnings": warnings,
                    "text": "\n".join(s["text"] for s in flattened if s["text"])})
            return result
    except (OSError, BadZipFile) as exc:
        raise ValueError(f"Cannot read PPTX {Path(path).name}: {exc}") from exc
