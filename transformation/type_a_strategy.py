"""סוג A (הפשוט): מזיזים את המשמרת ושומרים בערך על האורך שלה. סה"כ = יציאה - כניסה."""
import random
from dataclasses import replace

from config.rules import TransformRules
from domain.models import AttendanceRow, ReportSummary
from domain.time_math import hours_between
from domain.totals import sum_field, work_rows
from transformation.base_strategy import BaseTransformationStrategy


class TypeATransformationStrategy(BaseTransformationStrategy):
    def transform_row(self, row: AttendanceRow, rules: TransformRules, rng: random.Random) -> AttendanceRow:
        if not row.is_work_day:
            return row                                   # שבת / חג: לא ממציאים שעות
        entry, exit_ = self._pick_shift(row, rules, rng)
        return replace(row, entry_time=entry, exit_time=exit_, total_hours=hours_between(entry, exit_))

    def build_summary(self, rows: list[AttendanceRow], original: ReportSummary) -> ReportSummary:
        total = sum_field(rows, "total_hours")
        pay = round(total * original.hourly_rate, 2) if original.hourly_rate is not None else None
        return replace(original, total_days=len(work_rows(rows)), total_hours=total, total_pay=pay)
