import csv
from pathlib import Path

from domain.exceptions import RenderError
from domain.models import AttendanceReport
from generation.base_renderer import BaseRenderer


class CsvRenderer(BaseRenderer):
    """טבלת השורות כ-CSV (נפתח באקסל). utf-8-sig כדי שאקסל יציג עברית נכון."""
    file_extension = ".csv"

    def render(self, report: AttendanceReport, output_path: Path) -> Path:
        layout = self.layout_for(report)
        try:
            with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([c.title for c in layout.columns])
                for row in report.rows:
                    writer.writerow(self.row_cells(row, layout, report.date_style))
        except OSError as error:
            raise RenderError(f"Could not write {output_path}: {error}") from error
        return output_path
