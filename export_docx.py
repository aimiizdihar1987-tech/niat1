#!/usr/bin/env python3
"""
Export the RPH (Daily Lesson Plan) as a real .docx file — Python stdlib only.

A .docx is a ZIP of OOXML parts; this module writes the minimal valid set:
[Content_Types].xml, _rels/.rels and word/document.xml. The layout mirrors the
official JPN Perlis template: a plain bordered table with BM field labels and
English lesson content. No colours, no app theme — the exported document must
stay in the standardized plain format.
"""

import io
import zipfile
from xml.sax.saxutils import escape

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _r(text, bold=False, italic=False):
    """One run. Line breaks in `text` become <w:br/>."""
    rpr = "<w:rPr>"
    if bold:
        rpr += "<w:b/>"
    if italic:
        rpr += "<w:i/>"
    rpr += '<w:sz w:val="22"/></w:rPr>'
    parts = []
    for i, seg in enumerate(str(text).split("\n")):
        if i:
            parts.append("<w:br/>")
        parts.append('<w:t xml:space="preserve">{}</w:t>'.format(escape(seg)))
    return "<w:r>{}{}</w:r>".format(rpr, "".join(parts))


def _p(runs, align=None):
    ppr = ""
    if align:
        ppr = '<w:pPr><w:jc w:val="{}"/></w:pPr>'.format(align)
    return "<w:p>{}{}</w:p>".format(ppr, runs)


def _tc(content, width, span=1, bold=False):
    """A table cell. `content` may be plain text or a list of paragraphs."""
    tcpr = '<w:tcPr><w:tcW w:w="{}" w:type="dxa"/>'.format(width)
    if span > 1:
        tcpr += '<w:gridSpan w:val="{}"/>'.format(span)
    tcpr += "</w:tcPr>"
    if isinstance(content, list):
        body = "".join(content) or _p(_r(""))
    else:
        body = _p(_r(content, bold=bold))
    return "<w:tc>{}{}</w:tc>".format(tcpr, body)


def plan_to_docx(plan, school=""):
    """Build the .docx bytes for an RPH plan dict (JPN Perlis plain format)."""
    plan = plan or {}
    g = lambda k: str(plan.get(k, "") or "")
    objektif = plan.get("objektif_pembelajaran", []) or []
    aktiviti = plan.get("aktiviti_pembelajaran", []) or []
    sp = plan.get("standard_pembelajaran", []) or []

    LBL, VAL = 2340, 2340  # 4 equal columns (dxa) = 9360 total

    def pair_row(l1, v1, l2, v2):
        return "<w:tr>{}{}{}{}</w:tr>".format(
            _tc(l1, LBL, bold=True), _tc(v1, VAL),
            _tc(l2, LBL, bold=True), _tc(v2, VAL))

    def full_row(label, content):
        return "<w:tr>{}{}</w:tr>".format(
            _tc(label, LBL, bold=True), _tc(content, VAL, span=3))

    obj_paras = [_p(_r("Pada akhir PdPc, murid boleh :", italic=True))]
    obj_paras += [_p(_r("{}. {}".format(i, o))) for i, o in enumerate(objektif, 1)]
    akt_paras = [_p(_r("{}. {}".format(i, a))) for i, a in enumerate(aktiviti, 1)]
    sp_paras = [_p(_r(s)) for s in sp] or [_p(_r(""))]

    rows = [
        pair_row("MINGGU", g("minggu"), "TARIKH", g("tarikh")),
        pair_row("HARI", g("hari"), "MASA", g("masa")),
        pair_row("TINGKATAN / KELAS", g("tingkatan_kelas"),
                 "MINIMUM JAM SETAHUN", g("minimum_jam_setahun")),
        full_row("MATA PELAJARAN", g("mata_pelajaran")),
        full_row("TEMA / BIDANG", g("tema_bidang")),
        full_row("TAJUK", g("tajuk")),
        full_row("STANDARD KANDUNGAN", g("standard_kandungan")),
        "<w:tr>{}{}</w:tr>".format(
            _tc("STANDARD PEMBELAJARAN", LBL, bold=True), _tc(sp_paras, VAL, span=3)),
        "<w:tr>{}{}</w:tr>".format(
            _tc("OBJEKTIF PEMBELAJARAN", LBL, bold=True), _tc(obj_paras, VAL, span=3)),
        "<w:tr>{}{}</w:tr>".format(
            _tc("AKTIVITI PEMBELAJARAN", LBL, bold=True), _tc(akt_paras, VAL, span=3)),
        full_row("REFLEKSI", g("refleksi") or "\n\n"),
    ]

    border = ('<w:tblBorders>'
              '<w:top w:val="single" w:sz="6" w:color="000000"/>'
              '<w:left w:val="single" w:sz="6" w:color="000000"/>'
              '<w:bottom w:val="single" w:sz="6" w:color="000000"/>'
              '<w:right w:val="single" w:sz="6" w:color="000000"/>'
              '<w:insideH w:val="single" w:sz="6" w:color="000000"/>'
              '<w:insideV w:val="single" w:sz="6" w:color="000000"/>'
              '</w:tblBorders>')
    table = ('<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/>{}</w:tblPr>'
             '<w:tblGrid><w:gridCol w:w="2340"/><w:gridCol w:w="2340"/>'
             '<w:gridCol w:w="2340"/><w:gridCol w:w="2340"/></w:tblGrid>{}'
             '</w:tbl>').format(border, "".join(rows))

    head = ""
    if school:
        head += _p(_r(school.upper(), bold=True), align="center")
    head += _p(_r("RANCANGAN PENGAJARAN HARIAN", bold=True), align="center")
    head += _p(_r(""))

    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="{}"><w:body>{}{}'
                '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
                '<w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080"/>'
                '</w:sectPr></w:body></w:document>').format(W, head, table)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", document)
    return buf.getvalue()
