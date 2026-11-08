"""
הקצה השני של "מחרוזות רק בקצוות": כאן, ורק כאן, time חוזר להיות '8:30' ו-date חוזר להיות '01/09/22'.
"""
from datetime import date, time


def format_date(d: date, style: str) -> str:
    """style כמו במקור: 'dd/mm/yy', 'd/m/yyyy' וכו'."""
    day_s, month_s, year_s = style.split("/")
    day = f"{d.day:02d}" if day_s == "dd" else str(d.day)
    month = f"{d.month:02d}" if month_s == "mm" else str(d.month)
    year = str(d.year) if year_s == "yyyy" else f"{d.year % 100:02d}"
    return f"{day}/{month}/{year}"


def format_time(t: time, time_format: str) -> str:
    return f"{t.hour:02d}:{t.minute:02d}" if time_format == "hh:mm" else f"{t.hour}:{t.minute:02d}"


def format_value(value, kind: str, time_format: str = "hh:mm", date_style: str = "dd/mm/yy") -> str:
    if value is None:
        return ""
    if kind == "date":
        return format_date(value, date_style)
    if kind == "time":
        return format_time(value, time_format)
    if kind == "minutes":
        return f"{value // 60:02d}:{value % 60:02d}"
    if kind == "hours":
        return f"{value:.2f}"
    if kind == "money":
        return f"₪ {value:,.2f}"
    return str(value)
