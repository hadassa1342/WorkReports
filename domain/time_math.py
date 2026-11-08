"""חישובי זמן ושעות. פונקציות טהורות: בלי קבצים, בלי OCR ובלי מספרים קבועים."""
from datetime import time

SATURDAY = 5   # date.weekday(): 0=שני ... 5=שבת, 6=ראשון


def to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def from_minutes(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def hours_between(entry: time, exit_: time, break_minutes: int = 0) -> float:
    """סה"כ שעות = יציאה - כניסה - הפסקה."""
    return round((to_minutes(exit_) - to_minutes(entry) - break_minutes) / 60, 2)


def split_overtime(total: float, is_shabbat: bool, regular_hours: float,
                   overtime_125_until: float) -> tuple[float, float, float, float]:
    """
    מחזיר (100%, 125%, 150%, שבת).
    שבת: הכול בעמודת שבת. אחרת: עד regular_hours ב-100%, עד overtime_125_until ב-125%, השאר 150%.
    ה-100% מחושב כהפרש, כדי שהחלוקה תסתכם בדיוק לסה"כ גם אחרי עיגול.
    """
    if is_shabbat:
        return 0.0, 0.0, 0.0, round(total, 2)
    h125 = round(min(max(total - regular_hours, 0.0), overtime_125_until - regular_hours), 2)
    h150 = round(max(total - overtime_125_until, 0.0), 2)
    h100 = round(total - h125 - h150, 2)
    return h100, h125, h150, 0.0
