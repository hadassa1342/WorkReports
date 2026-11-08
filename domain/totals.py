"""סכומים על שורות. משמש גם את הפרסר (סיכום המקור) וגם את הטרנספורמציה (סיכום הווריאציה)."""
from domain.models import AttendanceRow


def work_rows(rows) -> list[AttendanceRow]:
    return [r for r in rows if r.is_work_day]


def sum_field(rows, field: str) -> float:
    return round(sum(getattr(r, field) or 0 for r in rows), 2)
