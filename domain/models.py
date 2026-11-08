"""
המודל: השפה המשותפת של כל התחנות.
הפרסר מייצר AttendanceReport, הטרנספורמציה מקבלת ומחזירה אותו, והגנרוט קורא ממנו.
המודל לא יודע כלום על OCR, על PDF או על HTML.
"""
from dataclasses import dataclass
from datetime import date, time
from enum import Enum


class ReportType(Enum):
    TYPE_A = "TYPE_A"   # הדו"ח הפשוט (n_r_*.pdf): כניסה, יציאה, סה"כ, הערות. סיכום למעלה: מחיר לשעה ולתשלום
    TYPE_B = "TYPE_B"   # הדו"ח המפורט (a_r_*.pdf): מקום, הפסקה, 100%/125%/150%, שבת. שורת סכומים למטה


@dataclass(frozen=True)
class AttendanceRow:
    # --- משותף לשני הסוגים ---
    work_date: date
    day_name: str                      # כפי שמופיע במקור: "שני" (A) או "יום שני" (B)
    entry_time: time | None            # None בשבת, בחג, או כשהשעה לא נקראה
    exit_time: time | None
    total_hours: float
    note: str = ""
    # --- סוג B בלבד (נשארים None בסוג A) ---
    location: str | None = None
    break_minutes: int | None = None
    hours_100: float | None = None
    hours_125: float | None = None
    hours_150: float | None = None
    shabbat_hours: float | None = None

    @property
    def is_work_day(self) -> bool:
        return self.entry_time is not None and self.exit_time is not None


@dataclass(frozen=True)
class ReportSummary:
    total_days: int
    total_hours: float
    month_label: str = ""              # "ספטמבר 2022"
    company_name: str = ""             # סוג B: שם חברת כוח האדם
    # --- קלט מהדו"ח (סוג A) ---
    hourly_rate: float | None = None
    # --- מחושבים מהשורות ---
    total_pay: float | None = None
    hours_100: float | None = None
    hours_125: float | None = None
    hours_150: float | None = None
    shabbat_hours: float | None = None
    total_break_minutes: int | None = None


@dataclass(frozen=True)
class AttendanceReport:
    report_type: ReportType
    rows: tuple[AttendanceRow, ...]
    summary: ReportSummary
    date_style: str = "dd/mm/yy"       # איך התאריכים כתובים במקור, כדי שהפלט ייראה אותו דבר
