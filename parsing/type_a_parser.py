"""
סוג A: הדו"ח הפשוט (n_r_*.pdf).
שורה:          תאריך | יום בשבוע | שעת כניסה | שעת יציאה | סה"כ שעות | הערות
שבת/חג:        תאריך | יום | הערות  (בלי שעות)
בראש הדו"ח:    ימי עבודה / שעות חודשיות / מחיר לשעה / לתשלום
"""
import logging
from datetime import date

from domain.models import AttendanceRow, ReportSummary, ReportType
from domain.time_math import SATURDAY, hours_between
from domain.totals import sum_field, work_rows
from parsing.base_parser import BaseParser
from parsing.text_tools import (DAY_NAMES, MONTH_NAMES, NUM_RE, clean_note, hebrew_words,
                                is_visual_order, month_label, read_times)

log = logging.getLogger(__name__)


class TypeAParser(BaseParser):
    report_type = ReportType.TYPE_A

    # ---------- שורה ----------
    def _parse_row(self, work_date: date, line: list[dict]) -> AttendanceRow:
        tokens = [w["text"] for w in line]
        note = clean_note(" ".join(hebrew_words(tokens, is_visual_order(tokens))))

        entry = exit_ = None
        total = 0.0
        times = read_times(line, 2)                  # מימין לשמאל: כניסה, יציאה
        if len(times) == 2 and times[1] > times[0]:
            entry, exit_ = times
            total = hours_between(entry, exit_)
        elif times:
            log.warning("%s: could not read entry/exit (%s) - row kept without hours",
                        work_date, ", ".join(t.strftime("%H:%M") for t in times))

        return AttendanceRow(work_date=work_date, day_name=self._day_name(work_date),
                             entry_time=entry, exit_time=exit_, total_hours=total, note=note)

    def _day_name(self, d: date) -> str:
        return DAY_NAMES[d.weekday()]

    def _finish_rows(self, rows: list[AttendanceRow]) -> list[AttendanceRow]:
        for r in rows:
            if not r.is_work_day and r.work_date.weekday() != SATURDAY and not r.note:
                log.warning("%s: weekday without hours and without a note", r.work_date)
        return rows

    # ---------- הסיכום שבראש הדו"ח ----------
    _LABELS = {"לתשלום": "payment", "מחיר": "rate", "חודשיות": "monthly", "ימי": "days"}

    def _parse_summary(self, header_lines, rows) -> ReportSummary:
        labels, numbers = self._read_header(header_lines)
        computed_hours = sum_field(rows, "total_hours")
        found = self._match_labels(labels, numbers, computed_hours)

        rate = found.get("rate")
        if rate is None and found.get("payment") and found.get("monthly"):
            rate = round(found["payment"] / found["monthly"], 2)
        if rate is None:
            log.warning("hourly rate was not found in the report header")
        original_hours = found.get("monthly")
        if original_hours and abs(original_hours - computed_hours) > 0.01:
            log.warning("monthly hours in the header (%s) differ from the rows (%s): check for missing rows",
                        original_hours, computed_hours)

        return ReportSummary(
            total_days=len(work_rows(rows)),
            total_hours=computed_hours,
            month_label=month_label(r.work_date for r in rows),
            hourly_rate=rate,
            total_pay=found.get("payment"),
        )

    def _read_header(self, header_lines):
        labels, numbers = [], []
        for line in header_lines:
            tokens = [w["text"] for w in line]
            if any(t in MONTH_NAMES or t[::-1] in MONTH_NAMES for t in tokens):
                continue                                   # שורת החודש
            for w in line:
                t = w["text"]
                cx = (w["x0"] + w["x1"]) / 2
                key = self._LABELS.get(t) or self._LABELS.get(t[::-1])
                if key:
                    labels.append((key, cx, w["cy"]))
                    continue
                cleaned = t.replace("₪", "").strip()
                if cleaned and NUM_RE.match(cleaned):
                    numbers.append((float(cleaned.replace(",", "")), cx, w["cy"]))
        return labels, numbers

    @staticmethod
    def _match_labels(labels, numbers, computed_hours) -> dict:
        """כל תווית מקבלת את המספר הקרוב אליה. אם התוויות לא נקראו - לפי היחס תשלום/מחיר = שעות."""
        found = {}
        for key, lcx, lcy in labels:
            if key not in found and numbers:
                found[key] = min(numbers, key=lambda n: abs(n[1] - lcx) + 5 * abs(n[2] - lcy))[0]
        if found or not numbers:
            return found

        values = sorted({v for v, _, _ in numbers}, reverse=True)
        payment = values[0]
        for v in values[1:]:
            if v > 0 and computed_hours and abs(payment / v - computed_hours) <= 0.1 * computed_hours:
                found.update(payment=payment, rate=v, monthly=round(payment / v, 2))
                break
        days = [v for v in values if float(v).is_integer() and 0 < v <= 31]
        if days and "payment" in found:
            found["days"] = days[0]
        return found
