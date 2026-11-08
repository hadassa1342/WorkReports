"""סוג B (המפורט): מזיזים כניסה, יציאה והפסקה, ומחלקים מחדש ל-100/125/150/שבת."""
import random
from dataclasses import replace

from config.rules import MAX_BREAK_MINUTES, OVERTIME_125_UNTIL, REGULAR_HOURS, TransformRules
from domain.models import AttendanceRow, ReportSummary
from domain.time_math import SATURDAY, hours_between, split_overtime
from domain.totals import sum_field, work_rows
from transformation.base_strategy import BaseTransformationStrategy


class TypeBTransformationStrategy(BaseTransformationStrategy):
    def transform_row(self, row: AttendanceRow, rules: TransformRules, rng: random.Random) -> AttendanceRow:
        if not row.is_work_day:
            return row
        brk = row.break_minutes or 0
        if rules.break_shift_minutes:
            brk = max(0, min(brk + rng.randint(-rules.break_shift_minutes, rules.break_shift_minutes),
                             MAX_BREAK_MINUTES - 1))
        entry, exit_ = self._pick_shift(row, rules, rng, break_minutes=brk)
        total = hours_between(entry, exit_, brk)
        h100, h125, h150, shabbat = split_overtime(total, row.work_date.weekday() == SATURDAY,
                                                   REGULAR_HOURS, OVERTIME_125_UNTIL)
        return replace(row, entry_time=entry, exit_time=exit_, break_minutes=brk, total_hours=total,
                       hours_100=h100, hours_125=h125, hours_150=h150, shabbat_hours=shabbat)

    def build_summary(self, rows: list[AttendanceRow], original: ReportSummary) -> ReportSummary:
        worked = work_rows(rows)
        total = sum_field(rows, "total_hours")
        pay = round(total * original.hourly_rate, 2) if original.hourly_rate is not None else None
        return replace(
            original,
            total_days=len(worked),
            total_hours=total,
            total_pay=pay,
            hours_100=sum_field(rows, "hours_100"),
            hours_125=sum_field(rows, "hours_125"),
            hours_150=sum_field(rows, "hours_150"),
            shabbat_hours=sum_field(rows, "shabbat_hours"),
            total_break_minutes=sum(r.break_minutes or 0 for r in worked),
        )
