"""תחנה 5: Generator. Renderer לכל פורמט פלט. כולם מקבלים AttendanceReport בלבד."""
from abc import ABC, abstractmethod
from pathlib import Path

from domain.models import AttendanceReport, AttendanceRow
from generation.formatting import format_value
from generation.layouts import LAYOUTS, ReportLayout


class BaseRenderer(ABC):
    file_extension: str

    @abstractmethod
    def render(self, report: AttendanceReport, output_path: Path) -> Path: ...

    # ---- עזר משותף לכל הפורמטים: מה מופיע בכל תא, לפי הפריסה ----
    @staticmethod
    def layout_for(report: AttendanceReport) -> ReportLayout:
        return LAYOUTS[report.report_type]

    @staticmethod
    def row_cells(row: AttendanceRow, layout: ReportLayout, date_style: str) -> list[str]:
        """בשורה בלי שעות (שבת, חג) עמודות השעות נשארות ריקות, כמו במקור, ולא '0.00'."""
        return ["" if not row.is_work_day and c.kind in _WORK_KINDS
                else format_value(getattr(row, c.field), c.kind, layout.time_format, date_style)
                for c in layout.columns]


_WORK_KINDS = {"time", "hours", "minutes"}
