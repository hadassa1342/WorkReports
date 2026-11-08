"""
האינווריאנטים מדף העבודה, כקוד. פונקציה אחת לכל הסוגים.
is_acceptable_shift - שאלה ("האם המשמרת הזו מותרת?"), בשימוש בזמן ההגרלה.
validate_row / validate_summary - בדיקה אחרי ההגרלה: אם משהו לא תקין, נזרקת שגיאה במקום לשקר.
"""
from config.rules import TransformRules
from domain.exceptions import TransformationError
from domain.models import AttendanceReport, AttendanceRow
from domain.time_math import hours_between, to_minutes
from domain.totals import sum_field, work_rows

_TOLERANCE = 0.011    # עיגול לשתי ספרות


def is_acceptable_shift(entry_m: int, exit_m: int, break_m: int, rules: TransformRules) -> bool:
    start, end = to_minutes(rules.work_start), to_minutes(rules.work_end)
    if not (start <= entry_m < exit_m <= end):
        return False
    hours = (exit_m - entry_m - break_m) / 60
    if not (rules.min_daily_hours <= hours <= rules.max_daily_hours):
        return False
    step = rules.avoid_round_minutes
    if step and (entry_m % step == 0 or exit_m % step == 0):
        return False
    return True


def validate_row(row: AttendanceRow, rules: TransformRules) -> None:
    if not row.is_work_day:
        if row.total_hours:
            raise TransformationError(f"{row.work_date}: no entry/exit but total is {row.total_hours}")
        return
    if row.exit_time <= row.entry_time:
        raise TransformationError(f"{row.work_date}: exit {row.exit_time} is not after entry {row.entry_time}")
    if not (rules.work_start <= row.entry_time and row.exit_time <= rules.work_end):
        raise TransformationError(f"{row.work_date}: {row.entry_time}-{row.exit_time} is outside working hours")
    if not (rules.min_daily_hours <= row.total_hours <= rules.max_daily_hours):
        raise TransformationError(f"{row.work_date}: {row.total_hours} hours is outside the allowed range")
    expected = hours_between(row.entry_time, row.exit_time, row.break_minutes or 0)
    if abs(row.total_hours - expected) > _TOLERANCE:
        raise TransformationError(f"{row.work_date}: total {row.total_hours} != exit - entry - break ({expected})")
    if row.hours_100 is not None:
        split_total = row.hours_100 + row.hours_125 + row.hours_150 + (row.shabbat_hours or 0)
        if abs(split_total - row.total_hours) > _TOLERANCE:
            raise TransformationError(f"{row.work_date}: 100/125/150/shabbat add up to {split_total:.2f}, "
                                      f"not {row.total_hours}")


def validate_summary(report: AttendanceReport) -> None:
    s = report.summary
    if abs(s.total_hours - sum_field(report.rows, "total_hours")) > _TOLERANCE:
        raise TransformationError(f"summary total {s.total_hours} != sum of rows")
    if s.total_days != len(work_rows(report.rows)):
        raise TransformationError("summary work days != number of work rows")
    if s.hourly_rate is not None and s.total_pay is not None \
            and abs(s.total_pay - round(s.total_hours * s.hourly_rate, 2)) > _TOLERANCE:
        raise TransformationError("total pay != total hours * hourly rate")
    months = {(r.work_date.year, r.work_date.month) for r in report.rows}
    if len(months) > 1:
        raise TransformationError(f"rows belong to more than one month: {sorted(months)}")
