"""
תחנה 3: Parser (Template Method).
parse() כתובה פעם אחת ומגדירה את סדר הפעולות לכל הסוגים. כל יורש ממלא רק את מה ששונה אצלו:
איפה השורות בעמוד (_row_positions), איך קוראים שורה (_parse_row) ואיך קוראים את הסיכום (_parse_summary).
"""
import logging
from abc import ABC, abstractmethod
from datetime import date

from domain.exceptions import ParseError
from domain.models import AttendanceReport, AttendanceRow, ReportSummary, ReportType
from parsing.text_tools import date_style, find_anchors, group_rows

log = logging.getLogger(__name__)


class BaseParser(ABC):
    report_type: ReportType

    def parse(self, pages: list[list[dict]]) -> AttendanceReport:
        header_lines = []
        rows = []
        date_texts = []
        for page in pages:
            words, anchors, spacing = find_anchors(page)
            if not anchors:
                continue
            date_texts += [a["text"] for a in anchors]
            header, table_rows = group_rows(words, self._row_positions(words, anchors, spacing), spacing)
            if not rows and header:
                header_lines = header            # הכותרת של העמוד הראשון שיש בו טבלה
            for work_date, line in table_rows:
                row = self._parse_row(work_date, line)
                if row is None:
                    log.warning("%s: row could not be read and was skipped", work_date)
                    continue
                rows.append(row)

        rows = self._finish_rows(_one_row_per_date(rows), header_lines)
        if not rows:
            raise ParseError(f"No attendance rows found ({self.report_type.value})")
        summary = self._parse_summary(header_lines, rows)
        return AttendanceReport(self.report_type, tuple(rows), summary, date_style(date_texts))

    # ---- כל יורש ממלא רק את מה ששונה ----
    @abstractmethod
    def _parse_row(self, work_date: date, line: list[dict]) -> AttendanceRow | None: ...

    @abstractmethod
    def _parse_summary(self, header_lines: list[list[dict]], rows: list[AttendanceRow]) -> ReportSummary: ...

    @abstractmethod
    def _day_name(self, d: date) -> str:
        """שם היום כפי שהוא כתוב בסוג הזה ("שני" / "יום שני")."""

    def _row_positions(self, words, anchors, spacing) -> list[tuple[date, float]]:
        """איפה כל שורה בעמוד: (תאריך, גובה). ברירת המחדל: לפי התאריך שנקרא בכל שורה."""
        return [(a["date"], a["cy"]) for a in anchors]

    def _finish_rows(self, rows: list[AttendanceRow], header_lines) -> list[AttendanceRow]:
        """צעד אופציונלי אחרי קריאת כל השורות (אפשר להיעזר בכותרת). ברירת המחדל: כלום."""
        return rows


def _one_row_per_date(rows: list[AttendanceRow]) -> list[AttendanceRow]:
    """אותו תאריך שנקרא פעמיים (שני עמודים, או קריאה כפולה) - שורה אחת, עדיף זו שיש בה שעות."""
    by_date = {}
    for row in rows:
        old = by_date.get(row.work_date)
        if old is None or (not old.is_work_day and row.is_work_day):
            by_date[row.work_date] = row
    return [by_date[d] for d in sorted(by_date)]
