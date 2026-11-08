"""
מה כותבים לכל סוג: עמודות, סיכום ומיקום הסיכום. נתונים בלבד, בלי לוגיקה.
הפורמט (איך כותבים: HTML, CSV, PDF) הוא מחלקה; הפריסה (מה כותבים) היא טבלה כאן.
"""
from dataclasses import dataclass

from domain.models import ReportType


@dataclass(frozen=True)
class Column:
    title: str                      # כותרת העמודה, בדיוק כמו במקור
    field: str                      # איזה שדה של AttendanceRow נכנס לעמודה
    kind: str = "text"              # text / date / time / hours / minutes
    total_field: str | None = None  # שדה של ReportSummary לשורת הסכומים (אם יש)


@dataclass(frozen=True)
class SummaryItem:
    label: str
    field: str                      # שדה של ReportSummary
    kind: str = "hours"             # int / hours / money / minutes


@dataclass(frozen=True)
class ReportLayout:
    title: str
    columns: tuple[Column, ...]
    summary_items: tuple[SummaryItem, ...]
    summary_on_top: bool            # A: כרטיסים מעל הטבלה. B: טבלת סיכום מתחת
    totals_row: bool                # B: שורת סכומים בתחתית הטבלה
    time_format: str                # "h:mm" (8:30) או "hh:mm" (08:30), כמו במקור
    header_fields: tuple[str, ...]  # שדות של ReportSummary שמוצגים מתחת לכותרת
    employee_line: bool


LAYOUTS: dict[ReportType, ReportLayout] = {
    ReportType.TYPE_A: ReportLayout(
        title="דוח שעות עבודה",
        columns=(
            Column("תאריך", "work_date", "date"),
            Column("יום בשבוע", "day_name"),
            Column("שעת כניסה", "entry_time", "time"),
            Column("שעת יציאה", "exit_time", "time"),
            Column('סה"כ שעות', "total_hours", "hours"),
            Column("הערות", "note"),
        ),
        summary_items=(
            SummaryItem("לתשלום", "total_pay", "money"),
            SummaryItem("מחיר לשעה", "hourly_rate", "money"),
            SummaryItem("שעות חודשיות", "total_hours", "hours"),
            SummaryItem("ימי עבודה", "total_days", "int"),
        ),
        summary_on_top=True,
        totals_row=False,
        time_format="h:mm",
        header_fields=("month_label",),
        employee_line=True,
    ),
    ReportType.TYPE_B: ReportLayout(
        title='דו"ח שעות עבודה',
        columns=(
            Column("תאריך", "work_date", "date"),
            Column("יום", "day_name"),
            Column("מקום", "location"),
            Column("כניסה", "entry_time", "time"),
            Column("יציאה", "exit_time", "time"),
            Column("הפסקה", "break_minutes", "minutes", "total_break_minutes"),
            Column('סה"כ', "total_hours", "hours", "total_hours"),
            Column("100%", "hours_100", "hours", "hours_100"),
            Column("125%", "hours_125", "hours", "hours_125"),
            Column("150%", "hours_150", "hours", "hours_150"),
            Column("שבת", "shabbat_hours", "hours", "shabbat_hours"),
        ),
        summary_items=(
            SummaryItem("ימי עבודה", "total_days", "int"),
            SummaryItem('סה"כ שעות', "total_hours"),
            SummaryItem("שעות 100%", "hours_100"),
            SummaryItem("שעות 125%", "hours_125"),
            SummaryItem("שעות 150%", "hours_150"),
            SummaryItem("שבת", "shabbat_hours"),
            SummaryItem("מחיר לשעה", "hourly_rate", "money"),
            SummaryItem('סה"כ לתשלום', "total_pay", "money"),
        ),
        summary_on_top=False,
        totals_row=True,
        time_format="hh:mm",
        header_fields=("month_label", "company_name"),
        employee_line=False,
    ),
}
