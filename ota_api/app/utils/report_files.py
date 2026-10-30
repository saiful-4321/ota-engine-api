"""
app/utils/report_files.py

Builds report files from a table (first row = headers): Excel via pandas/openpyxl and PDF via
reportlab. An "Amount" column, when present, gets a total row.
"""

from typing import List

import pandas as pd
from openpyxl.styles import Font, Alignment
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle, SimpleDocTemplate, Spacer


def create_report_excel(file_path: str, title: str, data: list[list]) -> bool:
    if not data or len(data) < 2:
        return False

    headers = data[0]
    rows = data[1:]
    df = pd.DataFrame(rows, columns=headers)

    # create excel writer using openpyxl engine
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Sheet1", index=False, startrow=2)
        ws = writer.sheets["Sheet1"]

        # write title across merged cells in row 1
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        title_cell = ws.cell(row=1, column=1, value=title)
        title_cell.font = Font(size=14, bold=True)
        title_cell.alignment = Alignment(horizontal="center")

        # add total row for "Amount" col if it exists
        amount_col = None
        for idx, col in enumerate(headers):
            if col.lower() == "amount":
                amount_col = idx
                break

        if amount_col is not None:
            total_amount = 0.0
            for val in df.iloc[:, amount_col]:
                try:
                    total_amount += float(val)
                except Exception:
                    pass

            total_row_idx = df.shape[0] + 4  # data rows + header + title + 1
            ws.cell(row=total_row_idx, column=amount_col, value="Total").font = Font(bold=True)
            ws.cell(row=total_row_idx, column=amount_col + 1, value=total_amount).font = Font(bold=True)

    return True

class PageNumCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        Canvas.__init__(self, *args, **kwargs)
        self._page_number = 0
        self._saved_page_states = []

    def showPage(self):
        self._page_number += 1
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        # add page numbers to all pages
        total_pages = self._page_number
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(total_pages)
            Canvas.showPage(self)
        Canvas.save(self)

    def draw_page_number(self, total_pages):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setStrokeColorRGB(0, 0, 0)
        self.setLineWidth(0.5)

        page_width, _ = A4
        margin = 20
        footer_y = 15 * mm
        text = f"Powered By: API  |  Page {self._pageNumber} of {total_pages}"

        self.line(margin, footer_y + 8, page_width - margin, footer_y + 8)
        self.drawRightString(page_width - margin, footer_y, text)
        self.restoreState()

def create_report_pdf(file_path: str, title: str, data: List[List]) -> bool:
    styles = getSampleStyleSheet()

    # custom styles
    normal_small = ParagraphStyle(name='NormalSmall', parent=styles['Normal'], fontSize=8, leading=10)
    right_aligned_small = ParagraphStyle(name='RightSmall', parent=styles['Normal'], fontSize=8, leading=10, alignment=2)
    bold_left_aligned = ParagraphStyle(name='BoldLeft', parent=styles['Title'], fontSize=11, leading=13, alignment=0)
    title_style = ParagraphStyle(name='TitleCentered', parent=styles['Title'], fontSize=12, leading=14, alignment=1)

    if not data or len(data) < 2:
        return False

    raw_headers = data[0]

    # wrap headers
    wrapped_data = [[Paragraph(f"<b>{col}</b>", normal_small) for col in raw_headers]]

    # wrap rows
    for row in data[1:]:
        wrapped_row = [Paragraph(str(cell), normal_small) for cell in row]
        wrapped_data.append(wrapped_row)

    # add total row if "amount" exists
    amount_index = None
    for i, h in enumerate(raw_headers):
        if h.lower() == "amount":
            amount_index = i
            break

    if amount_index is not None:
        total_amount = 0.0
        for row in data[1:]:
            try:
                val = row[amount_index]
                total_amount += float(val) if val else 0.0
            except Exception:
                pass

        total_row = [""] * len(raw_headers)
        total_row[amount_index - 1 if amount_index > 0 else 0] = Paragraph("<b>Total</b>", normal_small)
        total_row[amount_index] = Paragraph(f"<b>{total_amount:.2f}</b>", normal_small)
        wrapped_data.append(total_row)

    # column widths(some has fixed widths, others will share remaining space)
    page_width, page_height = A4
    margin = 20
    usable_width = page_width - margin * 2

    fixed_widths = {
        "sl.": 30,
        "paymenttype": 65,
        "paymentmethod": 75,
        "source": 40,
    }

    dynamic_columns = [h for h in raw_headers if h.lower() not in fixed_widths]
    remaining_width = usable_width - sum(fixed_widths.get(h.lower(), 0) for h in raw_headers)
    dynamic_width = remaining_width / max(1, len(dynamic_columns))

    col_widths = [
        fixed_widths.get(h.lower(), dynamic_width)
        for h in raw_headers
    ]

    # Build document
    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        rightMargin=margin,
        leftMargin=margin,
        topMargin=40,
        bottomMargin=60,
    )

    elements = [
        Paragraph(f"<b>{title}</b>", title_style),
        Spacer(1, 12),
        Table(wrapped_data, colWidths=col_widths, style=TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]),
        ),
    ]

    doc.build(elements, canvasmaker=PageNumCanvas)
    return True
