"""
כל המספרים של הפרויקט, במקום אחד ועם שם.
שינוי של טווח או של סף = שורה אחת כאן.
"""
from dataclasses import dataclass
from datetime import time

from domain.models import ReportType


@dataclass(frozen=True)
class TransformRules:
    entry_shift_minutes: int            # הכניסה זזה עד +/- הערך הזה
    exit_shift_minutes: int             # היציאה זזה עד +/- הערך הזה (כשלא שומרים על אורך המשמרת)
    keep_shift_length: bool = False     # True: היציאה נגזרת מהכניסה + אורך המשמרת המקורי
    length_jitter_minutes: int = 0      # כשמשמרים אורך: בכמה דקות מותר לשנות אותו
    break_shift_minutes: int = 0        # בכמה דקות מותר להזיז את ההפסקה
    work_start: time = time(7, 0)       # אף שעה לא לפני
    work_end: time = time(19, 0)        # אף שעה לא אחרי
    min_daily_hours: float = 1.0
    max_daily_hours: float = 12.0
    avoid_round_minutes: int = 15       # לא לייצר שעות "עגולות מדי" (08:00, 08:15...). 0 = לא לבדוק
    work_on_shabbat: bool = False       # False: בווריאציה העובד לא עובד בשבת, גם אם במקור עבד
    max_attempts: int = 1000


RULES: dict[ReportType, TransformRules] = {
    # הפשוט: שומרים על אורך המשמרת, כדי שסה"כ החודשי והתשלום יישארו קרובים למקור
    ReportType.TYPE_A: TransformRules(entry_shift_minutes=25, exit_shift_minutes=25,
                                      keep_shift_length=True, length_jitter_minutes=15),
    # המפורט: כניסה ויציאה זזות בנפרד, ההפסקה נשארת כמו במקור
    ReportType.TYPE_B: TransformRules(entry_shift_minutes=25, exit_shift_minutes=25),
}

# שעות נוספות (סוג B): עד 8 שעות 100%, השעתיים הבאות 125%, מעבר לזה 150%
REGULAR_HOURS = 8.0
OVERTIME_125_UNTIL = 10.0

# פרסור
MAX_BREAK_MINUTES = 180         # שעה קצרה מזה בשורה של סוג B היא הפסקה, לא כניסה/יציאה
DEFAULT_BREAK_MINUTES = 30      # רק כשההפסקה לא נקראה מה-OCR. נרשמת אזהרה
