import html
from pathlib import Path

from domain.exceptions import RenderError
from domain.models import AttendanceReport
from generation.base_renderer import BaseRenderer
from generation.formatting import format_value

CSS = """
body {
    font-family: 'David', 'Arial', sans-serif;
    direction: rtl;
    color: #111827;
    margin: 40px;
    background-color: #ffffff;
}
.header-container {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 10px;
}
.report-title {
    font-size: 28px;
    font-weight: bold;
    color: #111827;
    margin: 0;
    text-align: right;
}
.report-month {
    font-size: 18px;
    color: #374151;
    margin-top: 5px;
    text-align: right;
}
.company-name {
    font-size: 14px;
    color: #4b5563;
    margin-top: 5px;
    text-align: right;
}
.header-right {
    text-align: right;
    width: 100%;
}
.employee {
    font-size: 15px;
    margin: 10px 0 15px 0;
    text-align: right;
}
.cards {
    display: flex;
    gap: 12px;
    margin-bottom: 20px;
}
.card {
    flex: 1;
    border: 1px solid #e5e7eb;
    padding: 10px;
    text-align: center;
}
.card-label {
    font-size: 13px;
    color: #4b5563;
}
.card-value {
    font-size: 18px;
    font-weight: bold;
    color: #111827;
    margin-top: 4px;
}
.note {
    font-size: 12px;
    color: #6b7280;
    margin-top: 20px;
    text-align: right;
}
.divider {
    border: none;
    border-top: 1px solid #d1d5db;
    margin: 15px 0 25px 0;
}
table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 10px;
}
th, td {
    border: 1px solid #e5e7eb;
    padding: 8px 10px;
    text-align: center;
    font-size: 13px;
}
th {
    background-color: #16325c;
    color: #ffffff;
    font-weight: bold;
}
tr:nth-child(even) {
    background-color: #f9fafb;
}
.footer-row {
    background-color: #e2e8f0;
    font-weight: bold;
}
.summary-section {
    margin-top: 40px;
    width: 320px;
    float: left;
    border: 1px solid #e5e7eb;
    padding: 15px;
    background-color: #ffffff;
}
.summary-title {
    font-size: 16px;
    font-weight: bold;
    color: #111827;
    margin-bottom: 10px;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 5px;
    text-align: right;
}
.summary-row {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    font-size: 14px;
}
.summary-label {
    color: #4b5563;
}
.summary-value {
    font-weight: bold;
    color: #111827;
}
.clearfix::after {
    content: "";
    clear: both;
    display: table;
}
"""


def _e(text) -> str:
    return html.escape(str(text))


class HtmlRenderer(BaseRenderer):
    """
    בונה HTML מימין לשמאל, באותו מבנה כמו המקור.
    העמודות והסיכום מגיעים מהפריסה (layouts.py) - אין כאן if על סוג הדו"ח, ואין חישובים:
    כל הסכומים כבר נמצאים ב-report.summary.
    """
    file_extension = ".html"

    def render(self, report: AttendanceReport, output_path: Path) -> Path:
        layout = self.layout_for(report)
        s = report.summary

        header_cells = "".join(f"<th>{_e(c.title)}</th>" for c in layout.columns)
        body = "".join(
            "<tr>" + "".join(f"<td>{_e(v)}</td>" for v in self.row_cells(r, layout, report.date_style)) + "</tr>\n"
            for r in report.rows
        )

        totals = ""
        if layout.totals_row:
            cells = []
            for i, c in enumerate(layout.columns):
                if c.total_field:
                    cells.append(format_value(getattr(s, c.total_field), c.kind))
                else:
                    cells.append('סה"כ' if i == 0 else "")
            totals = '<tr class="footer-row">' + "".join(f"<td>{_e(v)}</td>" for v in cells) + "</tr>"

        items = [(i.label, format_value(getattr(s, i.field), i.kind)) for i in layout.summary_items
                 if getattr(s, i.field) is not None]
        if layout.summary_on_top:
            summary_html = '<div class="cards">' + "".join(
                f'<div class="card"><div class="card-label">{_e(k)}</div>'
                f'<div class="card-value">{_e(v)}</div></div>' for k, v in items) + "</div>"
        else:
            summary_html = ('<div class="clearfix"><div class="summary-section">'
                            '<div class="summary-title">סיכום חודשי</div>' + "".join(
                                f'<div class="summary-row"><span class="summary-label">{_e(k)}</span>'
                                f'<span class="summary-value">{_e(v)}</span></div>' for k, v in items)
                            + "</div></div>")

        header_lines = "".join(f'<div class="report-month">{_e((label + " " + getattr(s, f)).strip())}</div>'
                               for label, f in layout.header_fields if getattr(s, f))
        title = f'<div class="report-title">{_e(layout.title)}</div>' if layout.title else ""
        employee = '<div class="employee">שם העובד: ____________________</div>' if layout.employee_line else ""

        page = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<title>{_e(layout.title or "דוח שעות עבודה")}</title>
<style>{CSS}</style>
</head>
<body>
<div class="header-container"><div class="header-right">
{title}
{header_lines}
</div></div>
<hr class="divider">
{employee}
{summary_html if layout.summary_on_top else ""}
<table>
<thead><tr>{header_cells}</tr></thead>
<tbody>
{body}{totals}
</tbody>
</table>
{"" if layout.summary_on_top else summary_html}
</body>
</html>"""
        try:
            output_path.write_text(page, encoding="utf-8")
        except OSError as error:
            raise RenderError(f"Could not write {output_path}: {error}") from error
        return output_path
