from dataclasses import dataclass
from typing import Optional, List, Any

@dataclass
class ReportARow:
    date: str
    day: str
    location: str
    entry_time: str
    exit_time: str
    break_time: str
    total_hours: float
    hours_100: float
    hours_125: float
    hours_150: float
    shabbat_hours: float

@dataclass
class ReportBRow:
    date: str
    day_of_week: str
    entry_time: str
    exit_time: str
    total_hours: float
    notes: Optional[str] = None

@dataclass
class ReportResult:
    report_type: str
    rows: List[Any]
    summary_data: dict