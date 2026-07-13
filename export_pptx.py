#!/usr/bin/env python3
"""
Export the teaching materials (slides) as a real .pptx file — Python stdlib only.

A .pptx is a ZIP of OOXML parts. This module writes the minimal valid set that
PowerPoint, Google Slides and LibreOffice all accept: content types, package
rels, presentation + master + layout + theme, and one slide part per teaching
slide (title + bullet body as plain text boxes, 16:9).
"""

import io
import zipfile
from xml.sax.saxutils import escape

A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
P = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'

EMU_W, EMU_H = 12192000, 6858000  # 16:9

THEME = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
'<a:theme ' + A + ' name="Niat"><a:themeElements>'
'<a:clrScheme name="Niat"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
'<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
'<a:dk2><a:srgbClr val="0F766E"/></a:dk2><a:lt2><a:srgbClr val="F0FDFA"/></a:lt2>'
'<a:accent1><a:srgbClr val="0D9488"/></a:accent1><a:accent2><a:srgbClr val="0891B2"/></a:accent2>'
'<a:accent3><a:srgbClr val="0EA5E9"/></a:accent3><a:accent4><a:srgbClr val="5EEAD4"/></a:accent4>'
'<a:accent5><a:srgbClr val="64748B"/></a:accent5><a:accent6><a:srgbClr val="334155"/></a:accent6>'
'<a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme>'
'<a:fontScheme name="Niat"><a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
'<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
'<a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
'<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
'<a:lnStyleLst><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
'<a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
'<a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
'<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle>'
'<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
'<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
'<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
'</a:fmtScheme></a:themeElements></a:theme>')

MASTER = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
'<p:sldMaster ' + P + ' ' + A + ' ' + R + '>'
'<p:cSld><p:bg><p:bgPr><a:solidFill><a:schemeClr val="lt1"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
'<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
'<p:grpSpPr/></p:spTree></p:cSld>'
'<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
'<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
'</p:sldMaster>')

LAYOUT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
'<p:sldLayout ' + P + ' ' + A + ' ' + R + ' type="blank">'
'<p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
'<p:grpSpPr/></p:spTree></p:cSld>'
'<p:clrMapOvr><a:overrideClrMapping bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" '
'hlink="hlink" folHlink="folHlink"/></p:clrMapOvr></p:sldLayout>')


def _textbox(shape_id, name, x, y, w, h, paras):
    return ('<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{name}"/>'
            '<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            '<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            '<p:txBody><a:bodyPr wrap="square" anchor="t"><a:normAutofit/></a:bodyPr>'
            '<a:lstStyle/>{paras}</p:txBody></p:sp>').format(
        sid=shape_id, name=escape(name), x=x, y=y, w=w, h=h, paras=paras)


def _para(text, size, bold=False, bullet=False, color="000000"):
    ppr = '<a:pPr>'
    if bullet:
        ppr += '<a:buFont typeface="Arial"/><a:buChar char="&#8226;"/>'
    else:
        ppr += '<a:buNone/>'
    ppr += '</a:pPr>'
    return ('<a:p>{ppr}<a:r><a:rPr lang="en-MY" sz="{sz}"{b}>'
            '<a:solidFill><a:srgbClr val="{c}"/></a:solidFill></a:rPr>'
            '<a:t>{t}</a:t></a:r></a:p>').format(
        ppr=ppr, sz=size, b=' b="1"' if bold else "", c=color, t=escape(str(text)))


def _slide_xml(title, points, footer=""):
    shapes = [_textbox(2, "Title", 685800, 365760, 10820400, 1143000,
                       _para(title, 3200, bold=True, color="0F766E"))]
    body = "".join(_para(pt, 2000, bullet=True) for pt in points) or _para("", 2000)
    shapes.append(_textbox(3, "Body", 685800, 1700784, 10820400, 4400000, body))
    if footer:
        shapes.append(_textbox(4, "Footer", 685800, 6290000, 10820400, 400000,
                               _para(footer, 1200, color="64748B")))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld ' + P + ' ' + A + ' ' + R + '><p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr/>' + "".join(shapes) + '</p:spTree></p:cSld>'
            '<p:clrMapOvr><a:overrideClrMapping bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" '
            'accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" '
            'accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
            '</p:clrMapOvr></p:sld>')


def slides_to_pptx(materials, footer=""):
    """Build .pptx bytes from the materials dict ({"slides":[{tajuk, isi[]}...]})."""
    slides = (materials or {}).get("slides", []) or []
    if not slides:
        slides = [{"tajuk": "Niat", "isi": []}]
    n = len(slides)

    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
          '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
          '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
          '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>']
    for i in range(1, n + 1):
        ct.append('<Override PartName="/ppt/slides/slide{}.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'.format(i))
    ct.append('</Types>')

    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
                 '</Relationships>')

    pres_rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>']
    sld_ids = []
    for i in range(1, n + 1):
        rid = "rId{}".format(i + 1)
        pres_rels.append('<Relationship Id="{}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{}.xml"/>'.format(rid, i))
        sld_ids.append('<p:sldId id="{}" r:id="{}"/>'.format(255 + i, rid))
    pres_rels.append('</Relationships>')

    presentation = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<p:presentation ' + P + ' ' + A + ' ' + R + '>'
                    '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                    '<p:sldIdLst>' + "".join(sld_ids) + '</p:sldIdLst>'
                    '<p:sldSz cx="{}" cy="{}"/><p:notesSz cx="6858000" cy="9144000"/>'
                    '</p:presentation>').format(EMU_W, EMU_H)

    master_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
                   '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
                   '</Relationships>')
    layout_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'
                   '</Relationships>')
    slide_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
                  '</Relationships>')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels", root_rels)
        z.writestr("ppt/presentation.xml", presentation)
        z.writestr("ppt/_rels/presentation.xml.rels", "".join(pres_rels))
        z.writestr("ppt/slideMasters/slideMaster1.xml", MASTER)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", master_rels)
        z.writestr("ppt/slideLayouts/slideLayout1.xml", LAYOUT)
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", layout_rels)
        z.writestr("ppt/theme/theme1.xml", THEME)
        for i, s in enumerate(slides, 1):
            title = s.get("tajuk", "") or "Slide {}".format(i)
            points = [str(x) for x in (s.get("isi", []) or [])]
            z.writestr("ppt/slides/slide{}.xml".format(i), _slide_xml(title, points, footer))
            z.writestr("ppt/slides/_rels/slide{}.xml.rels".format(i), slide_rels)
    return buf.getvalue()
