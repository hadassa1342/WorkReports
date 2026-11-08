"""
תחנה 3: Parser (Template Method).
parse() כתובה פעם אחת ומגדירה את סדר הפעולות לכל הסוגים. כל יורש ממלא רק את מה ששונה אצלו:
איך קוראים שורה (_parse_row) ואיך קוראים את הסיכום (_parse_summary).
"""
import logging
from abc import ABC, abstractmethod
from datetime import date, timedelta

from config.rules import MAX_MISSING_DAYS_TO_FILL
from domain.exceptions import ParseError
from domain.models import AttendanceReport, AttendanceRow, ReportSummary, ReportType
from domain.time_math import SATURDAY
from parsing.text_tools import date_style, parse_date, read_table

log = logging.getLogger(__name__)


class BaseParser(ABC):
    report_type: ReportType

    def parse(self, pages: list[list[dict]]) -> AttendanceReport:
        header_lines = []
        rows = []
        style = None
        for page in pages:
            header, table_rows = read_table(page)
            if not rows and header:
                header_lines = header            # הכותרת של העמוד הראשון שיש בו טבלה
            for date_text, line in table_rows:
                work_date = parse_date(date_text)
                style = style or date_style(date_text)
                row = self._parse_row(work_date, line)
                if row is None:
                    log.warning("%s: row could not be read and was skipped", work_date)
                    continue
                rows.append(row)

        rows = self._finish_rows(self._fill_missing_dates(_one_row_per_date(rows)))
        if not rows:
            raise ParseError(f"No attendance rows found ({self.report_type.value})")
        summary = self._parse_summary(header_lines, rows)
        return AttendanceReport(self.report_type, tuple(rows), summary, style or "dd/mm/yy")

    # ---- כל יורש ממלא רק את מה ששונה ----
    @abstractmethod
    def _parse_row(self, work_date: date, line: list[dict]) -> AttendanceRow | None: ...

    @abstractmethod
    def _parse_summary(self, header_lines: list[list[dict]], rows: list[AttendanceRow]) -> ReportSummary: ...

    def _finish_rows(self, rows: list[AttendanceRow]) -> list[AttendanceRow]:
        """צעד אופציונלי אחרי קריאת כל השורות. ברירת המחדל: כלום."""
        return rows

    @abstractmethod
    def _day_name(self, d: date) -> str:
        """שם היום כפי שהוא כתוב בסוג הזה ("שני" / "יום שני")."""

    # ---- משותף: תאריך שלא נקרא ----
    def _fill_missing_dates(self, rows: list[AttendanceRow]) -> list[AttendanceRow]:
        """
        פער קצר בין תאריכים = שורה שה-OCR לא קרא. השורה קיימת במקור, ולכן משלימים אותה
        בלי שעות (לא ממציאים שעות), ומדווחים אם זה יום חול.
        """
        filled = []
        for prev, cur in zip(rows, rows[1:]):
            filled.append(prev)
            gap = (cur.work_date - prev.work_date).days - 1
            for i in range(1, gap + 1 if gap <= MAX_MISSING_DAYS_TO_FILL else 1):
                d = prev.work_date + timedelta(days=i)
                filled.append(AttendanceRow(d, self._day_name(d), None, None, 0.0))
                if d.weekday() != SATURDAY:
                    log.warning("%s: row was not read - added without hours", d)
            if gap > MAX_MISSING_DAYS_TO_FILL:
                log.warning("%s - %s: %d rows were not read", prev.work_date, cur.work_date, gap)
        if rows:
            filled.append(rows[-1])
            first = rows[0].work_date
            if first.day > 1 + MAX_MISSING_DAYS_TO_FILL:
                log.warning("rows before %s were not read", first)
            elif first.day > 1:                         # תחילת החודש: אותה השלמה
                start = [first.replace(day=d) for d in range(1, first.day)]
                for d in start:
                    if d.weekday() != SATURDAY:
                        log.warning("%s: row was not read - added without hours", d)
                filled = [AttendanceRow(d, self._day_name(d), None, None, 0.0) for d in start] + filled
        return filled


def _one_row_per_date(rows: list[AttendanceRow]) -> list[AttendanceRow]:
    """אותו תאריך שנקרא פעמיים (שני עמודים, או קריאה כפולה) - שורה אחת, עדיף זו שיש בה שעות."""
    by_date = {}
    for row in rows:
        old = by_date.get(row.work_date)
        if old is None or (not old.is_work_day and row.is_work_day):
            by_date[row.work_date] = row
    return [by_date[d] for d in sorted(by_date)]
