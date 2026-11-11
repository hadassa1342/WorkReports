"""
תחנה 4: Transformer (Strategy).
ממשק אחד, "דרך לשנות שורה ולסכם", ולכל סוג מחלקה משלו.
ההגרלה עצמה (הזזה בתוך הכללים) משותפת לשני הסוגים ולכן כתובה כאן, פעם אחת.
"""
import random
from abc import ABC, abstractmethod
from datetime import time

from config.rules import TransformRules
from domain.exceptions import TransformationError
from domain.models import AttendanceRow, ReportSummary
from domain.time_math import SATURDAY, from_minutes, to_minutes
from transformation.validation import is_acceptable_shift


class BaseTransformationStrategy(ABC):
    @abstractmethod
    def transform_row(self, row: AttendanceRow, rules: TransformRules,
                      rng: random.Random) -> AttendanceRow | None:
        """מחזיר שורה חדשה, או None אם השורה לא מופיעה בווריאציה (שבת בסוג B)."""

    @abstractmethod
    def build_summary(self, rows: list[AttendanceRow], original: ReportSummary) -> ReportSummary: ...

    # ---------- שבת, משותף ----------
    @staticmethod
    def _works_on_shabbat(row: AttendanceRow, rules: TransformRules) -> bool:
        """יום עבודה בשבת, כשהכללים לא מתירים עבודה בשבת."""
        return row.is_work_day and row.work_date.weekday() == SATURDAY and not rules.work_on_shabbat

    # ---------- הגרלת משמרת, משותף ----------
    @staticmethod
    def _pick_shift(row: AttendanceRow, rules: TransformRules, rng: random.Random,
                    break_minutes: int = 0) -> tuple[time, time]:
        """
        מזיז כניסה ויציאה סביב המקור, עד שהמשמרת עומדת בכל הכללים.
        קודם מכניסים את המקור לטווח המותר (כניסה 06:30 -> 07:00), אחרת אף הזזה קטנה לא תעמוד בכללים.
        """
        start, end = to_minutes(rules.work_start), to_minutes(rules.work_end)
        min_len = break_minutes + int(rules.min_daily_hours * 60)
        orig_entry, orig_exit = to_minutes(row.entry_time), to_minutes(row.exit_time)

        if rules.keep_shift_length:
            max_len = min(end - start - 2 * rules.entry_shift_minutes,
                          break_minutes + int(rules.max_daily_hours * 60))
            length = _clamp(orig_exit - orig_entry, min_len + rules.length_jitter_minutes, max_len)
            base_entry = _clamp(orig_entry, start, end - length)
        else:
            base_entry = _clamp(orig_entry, start, end - min_len)
            base_exit = _clamp(orig_exit, base_entry + min_len, end)

        for _ in range(rules.max_attempts):
            entry = base_entry + rng.randint(-rules.entry_shift_minutes, rules.entry_shift_minutes)
            if rules.keep_shift_length:
                exit_ = entry + length + rng.randint(-rules.length_jitter_minutes, rules.length_jitter_minutes)
            else:
                exit_ = base_exit + rng.randint(-rules.exit_shift_minutes, rules.exit_shift_minutes)
            if is_acceptable_shift(entry, exit_, break_minutes, rules):
                return from_minutes(entry), from_minutes(exit_)
        raise TransformationError(f"{row.work_date}: no shift within the rules was found "
                                  f"for {row.entry_time}-{row.exit_time}")


def _clamp(value, low, high):
    return max(low, min(value, high))
