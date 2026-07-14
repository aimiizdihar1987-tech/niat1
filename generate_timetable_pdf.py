#!/usr/bin/env python3
"""
Generate a "Jadual Waktu" (weekly timetable) PDF matching the official JPN
Perlis-style layout used for Cikgu Aimi's jadualwaktu.pdf: title, teacher
name, school name, a Masa x Isnin-Jumaat grid with a REHAT row, and a
"Jumlah Waktu Seminggu" summary table. fpdf2 only (already installed).

Usage as a library:
    from generate_timetable_pdf import build_timetable_pdf
    build_timetable_pdf(
        out_path="jadualwaktuAlvin.pdf",
        teacher_name="Dr Alvin Auh",
        school="Sekolah Menengah Kebangsaan Kuala Perlis",
        rows=[...],           # see ROWS shape below
        classes=["3 Amber", "3 Kristal", "3 Opal"],
    )
"""
from fpdf import FPDF

HEADER_GREEN = (198, 224, 180)
REHAT_PINK = (244, 199, 199)
BORDER_GRAY = (60, 60, 60)

# Each row: (time_label, {day: class_or_None}), special rows use is_rehat=True
DAYS = ["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat"]


def build_timetable_pdf(out_path, teacher_name, school, rows, classes, totals_override=None):
    """rows: list of dicts, each either
         {"time": "7.40 - 8.40", "cells": {"Isnin": "3 Amber", ...}}
       or
         {"time": "10.10 - 10.30", "rehat": True}
    classes: list of class names, in the order to show in the summary table.
    totals_override: optional {class_name: weekly_total} to print in the
    summary table AS-IS instead of counting grid occurrences — use this when
    faithfully reproducing a source document whose printed summary doesn't
    necessarily match its own grid (e.g. jadualwaktuAimi.pdf: the grid shows
    5 occurrences per class but the printed summary says 8 for each).
    """
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(15, 15, 15)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "JADUAL WAKTU", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, teacher_name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, school, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # ---- Main grid ----
    time_w = 32
    day_w = (210 - 30 - time_w) / 5  # page width minus margins minus time col
    row_h = 12

    pdf.set_draw_color(*BORDER_GRAY)
    pdf.set_line_width(0.3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(*HEADER_GREEN)
    pdf.cell(time_w, row_h, "Masa", border=1, align="C", fill=True)
    for d in DAYS:
        pdf.cell(day_w, row_h, d, border=1, align="C", fill=True)
    pdf.ln(row_h)

    pdf.set_font("Helvetica", "", 10)
    for row in rows:
        if row.get("rehat"):
            pdf.set_fill_color(*REHAT_PINK)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(time_w, row_h, row["time"], border=1, align="C", fill=True)
            for _ in DAYS:
                pdf.cell(day_w, row_h, "REHAT", border=1, align="C", fill=True)
            pdf.ln(row_h)
            pdf.set_font("Helvetica", "", 10)
            continue
        pdf.set_fill_color(255, 255, 255)
        pdf.cell(time_w, row_h, row["time"], border=1, align="C")
        for d in DAYS:
            pdf.cell(day_w, row_h, row["cells"].get(d) or "-", border=1, align="C")
        pdf.ln(row_h)

    pdf.ln(10)

    # ---- Summary table ----
    if totals_override is not None:
        totals = dict(totals_override)
    else:
        totals = {c: 0 for c in classes}
        for row in rows:
            if row.get("rehat"):
                continue
            for d, c in row["cells"].items():
                if c in totals:
                    totals[c] += 1

    sum_label_w = 90
    sum_val_w = 60
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(*HEADER_GREEN)
    pdf.cell(sum_label_w, row_h, "Kelas", border=1, align="C", fill=True)
    pdf.cell(sum_val_w, row_h, "Jumlah Waktu Seminggu", border=1, align="C", fill=True)
    pdf.ln(row_h)

    pdf.set_font("Helvetica", "", 10)
    total_all = 0
    for c in classes:
        pdf.set_fill_color(255, 255, 255)
        pdf.cell(sum_label_w, row_h, c, border=1, align="C")
        pdf.cell(sum_val_w, row_h, str(totals[c]), border=1, align="C")
        pdf.ln(row_h)
        total_all += totals[c]

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(sum_label_w, row_h, "Jumlah Keseluruhan", border=1, align="C")
    pdf.cell(sum_val_w, row_h, str(total_all), border=1, align="C")
    pdf.ln(row_h)

    pdf.output(out_path)
    return out_path


if __name__ == "__main__":
    # Alvin's timetable = jadualwaktuAimi.pdf's ACTUAL grid (extracted via
    # pypdf, verified directly from the source file), 1:1 class-name swap
    # only. Day/time layout is untouched, exactly as instructed:
    #   3 Delima  -> 3 Kristal
    #   3 Zamrud  -> 3 Amber
    #   3 Berlian -> 3 Opal
    # The source PDF's own summary table prints 8/8/8/24 even though its
    # grid only shows 5 occurrences per class (a pre-existing inconsistency
    # in Aimi's original file) — reproduced as-is via totals_override,
    # since only class names and the teacher name were asked to change.
    classes = ["3 Kristal", "3 Amber", "3 Opal"]
    KRISTAL, AMBER, OPAL = "3 Kristal", "3 Amber", "3 Opal"

    rows = [
        {"time": "7.40 - 8.40", "cells": {
            "Isnin": KRISTAL, "Selasa": None, "Rabu": AMBER,
            "Khamis": None, "Jumaat": OPAL}},
        {"time": "8.40 - 10.10", "cells": {
            "Isnin": None, "Selasa": OPAL, "Rabu": None,
            "Khamis": KRISTAL, "Jumaat": None}},
        {"time": "10.10 - 10.30", "rehat": True},
        {"time": "10.30 - 11.30", "cells": {
            "Isnin": AMBER, "Selasa": None, "Rabu": OPAL,
            "Khamis": None, "Jumaat": KRISTAL}},
        {"time": "11.30 - 1.00", "cells": {
            "Isnin": None, "Selasa": KRISTAL, "Rabu": None,
            "Khamis": AMBER, "Jumaat": None}},
        {"time": "1.00 - 2.00", "cells": {
            "Isnin": OPAL, "Selasa": None, "Rabu": KRISTAL,
            "Khamis": None, "Jumaat": AMBER}},
        {"time": "2.00 - 2.30", "cells": {
            "Isnin": None, "Selasa": None, "Rabu": None,
            "Khamis": None, "Jumaat": None}},
    ]

    build_timetable_pdf(
        out_path="jadualwaktuAlvin.pdf",
        teacher_name="Cikgu Alvin",
        school="Sekolah Menengah Kebangsaan Kuala Perlis",
        rows=rows,
        classes=classes,
        totals_override={"3 Kristal": 8, "3 Amber": 8, "3 Opal": 8},
    )
    print("Saved jadualwaktuAlvin.pdf")
