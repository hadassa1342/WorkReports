"""
סוג B: הדו"ח המפורט (a_r_*.pdf).
שורה (מימין לשמאל): תאריך | יום | מקום | כניסה | יציאה | הפסקה | סה"כ | 100% | 125% | 150% | שבת
בתחתית: שורת סכומים.
"""
import logging
from collections import Counter
from dataclasses import replace
from datetime import date

from config.rules import DEFAULT_BREAK_MINUTES, MAX_BREAK_MINUTES, OVERTIME_125_UNTIL, REGULAR_HOURS
from domain.models import AttendanceRow, ReportSummary, ReportType
from domain.time_math import SATURDAY, hours_between, split_overtime, to_minutes
from domain.totals import sum_field, work_rows
from parsing.base_parser import BaseParser
from parsing.text_tools import (DAY_NAMES, column_values, has_hebrew, hebrew_words, is_visual_order,
                                logical, month_label, read_times)

log = logging.getLogger(__name__)
_SPLIT_TOLERANCE = 0.011


class TypeBParser(BaseParser):
    report_type = ReportType.TYPE_B

    # ---------- שורה ----------
    def _parse_row(self, work_date: date, line: list[dict]) -> AttendanceRow:
        tokens = [w["text"] for w in line]
        visual = is_visual_order(tokens)
        location = " ".join(hebrew_words(tokens, visual)).strip()
        day_name = self._day_name(work_date)

        # לפי המיקום בעמודה: כניסה, יציאה, הפסקה (השמאלית מבין השלוש, והיא קצרה מ-3 שעות)
        times = read_times(line, 3)
        break_minutes = None
        if times and to_minutes(times[-1]) < MAX_BREAK_MINUTES:
            break_minutes = to_minutes(times.pop())

        if len(times) < 2:
            if times:
                log.warning("%s: only one time was read - row kept without hours", work_date)
            return AttendanceRow(work_date, day_name, None, None, 0.0, location=location)

        entry, exit_ = times[0], times[1]
        if break_minutes is None:
            log.warning("%s: break was not read - using %d minutes", work_date, DEFAULT_BREAK_MINUTES)
            break_minutes = DEFAULT_BREAK_MINUTES
        total = hours_between(entry, exit_, break_minutes)
        if total <= 0:
            log.warning("%s: exit is not after entry (%s-%s) - row kept without hours", work_date, entry, exit_)
            return AttendanceRow(work_date, day_name, None, None, 0.0, location=location)

        h100, h125, h150, shabbat = self._read_split(line, total) or split_overtime(
            total, work_date.weekday() == SATURDAY, REGULAR_HOURS, OVERTIME_125_UNTIL)
        return AttendanceRow(
            work_date=work_date, day_name=day_name, entry_time=entry, exit_time=exit_,
            total_hours=total, location=location, break_minutes=break_minutes,
            hours_100=h100, hours_125=h125, hours_150=h150, shabbat_hours=shabbat,
        )

    def _day_name(self, d: date) -> str:
        return f"יום {DAY_NAMES[d.weekday()]}"

    @staticmethod
    def _read_split(line, total):
        """
        עמודות המספרים מימין לשמאל: סה"כ, 100%, 125%, 150%, שבת. בכל עמודה - הערך שנקרא הכי הרבה פעמים.
        משתמשים בהן אם הן מסתדרות עם הסה"כ המחושב. כך נשמר יום מיוחד כמו במקור
        (17/10/2022: כל 6.50 השעות ב-150%, למרות שלפי הכלל הרגיל זה היה 100%).
        """
        values = column_values(line)
        if len(values) == 5 and abs(values[0] - total) < _SPLIT_TOLERANCE \
                and abs(sum(values[1:]) - total) < _SPLIT_TOLERANCE:
            return tuple(values[1:])
        return None

    # ---------- מקום: אותו מקום בכל השורות ----------
    def _finish_rows(self, rows, header_lines):
        """המקום זהה בדרך כלל בכל השורות, ולכן לוקחים את הנפוץ ביותר (מסנן רעש של OCR)."""
        locations = Counter(r.location for r in rows if r.location)
        if not locations:
            log.warning("work location was not read")
            return rows
        common = locations.most_common(1)[0][0]
        return [replace(r, location=common) for r in rows]

    # ---------- סיכום ----------
    def _parse_summary(self, header_lines, rows) -> ReportSummary:
        worked = work_rows(rows)
        return ReportSummary(
            total_days=len(worked),
            total_hours=sum_field(rows, "total_hours"),
            month_label=month_label(r.work_date for r in rows),
            company_name=self._company_name(header_lines),
            hours_100=sum_field(rows, "hours_100"),
            hours_125=sum_field(rows, "hours_125"),
            hours_150=sum_field(rows, "hours_150"),
            shabbat_hours=sum_field(rows, "shabbat_hours"),
            total_break_minutes=sum(r.break_minutes or 0 for r in worked),
        )

    @staticmethod
    def _company_name(header_lines) -> str:
        """השורה בכותרת שיש בה 'בע"מ'."""
        for line in header_lines:
            tokens = [w["text"] for w in line]
            if any('בע"מ' in t or 'מ"עב' in t for t in tokens):
                visual = any('מ"עב' in t for t in tokens)
                return " ".join(logical(t, visual) for t in tokens if has_hebrew(t))
        return ""
