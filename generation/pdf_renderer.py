from pathlib import Path

from domain.exceptions import RenderError
from domain.models import AttendanceReport
from generation.base_renderer import BaseRenderer
from generation.html_renderer import HtmlRenderer


class PdfRenderer(BaseRenderer):
    """מייצר HTML וממיר אותו ל-PDF עם WeasyPrint (התקנה אופציונלית, ראו README)."""
    file_extension = ".pdf"

    def render(self, report: AttendanceReport, output_path: Path) -> Path:
        try:
            from weasyprint import HTML
        except (ImportError, OSError) as error:
            raise RenderError("PDF output needs WeasyPrint (pip install weasyprint). "
                              "Alternatively use --format html and print to PDF from the browser.") from error
        html_path = HtmlRenderer().render(report, output_path.with_suffix(".html"))
        HTML(filename=str(html_path)).write_pdf(str(output_path))
        return output_path
