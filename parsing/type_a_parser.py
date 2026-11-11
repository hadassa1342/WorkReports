"""
סוג A: הדו"ח הפשוט (n_r_*.pdf).
שורה:          תאריך | יום בשבוע | שעת כניסה | שעת יציאה | סה"כ שעות | הערות
שבת/חג:        תאריך | יום | הערות  (בלי שעות)
בראש הדו"ח:    ימי עבודה / שעות חודשיות / מחיר לשעה / לתשלום
"""
import calendar
import difflib
import logging
from dataclasses import replace
from datetime import date, time, timedelta
from itertools import product
from statistics import median

from domain.models import AttendanceRow, ReportSummary, ReportType
from domain.time_math import SATURDAY, hours_between
from domain.totals import sum_field, work_rows
from parsing.base_parser import BaseParser
from parsing.text_tools import (DAY_NAMES, MONTH_NAMES, NUM_RE, TIME_RE, clean_note, dominant_month,
                                has_hebrew, hebrew_words, hours_candidates, is_visual_order, month_label,
                                read_shift_with_total, read_times, time_candidates)

log = logging.getLogger(__name__)
MIN_ANCHORS_FOR_GRID = 4      # כמה תאריכים צריך לקרוא נכון כדי לחשב מהם את מיקום כל השורות


class TypeAParser(BaseParser):
    report_type = ReportType.TYPE_A

    def __init__(self):
        self._entry_x = None        # המיקום האופקי של עמודת הכניסה, נלמד מהעמוד עצמו
        self._exit_x = None
        self._uncertain = {}        # תאריך -> (שעה שנקראה בדקות, העמודה שלה, מועמדים לסה"כ)

    def _day_name(self, d: date) -> str:
        return DAY_NAMES[d.weekday()]

    # ---------- איפה השורות ----------
    def _row_positions(self, words, anchors, spacing):
        """
        בסוג A יש שורה לכל יום בחודש, ברצף, ובמרווח קבוע. לכן מספיק לקרוא נכון חלק מהתאריכים
        כדי לחשב איפה נמצאת השורה של כל יום. ה-OCR קורא בדו"ח הזה תאריכים רבים לא נכון
        ('11/1/23' -> '44/1/23'), ובלי זה שורות שלמות היו הולכות לאיבוד או זזות לתאריך הלא נכון.
        """
        year, month = dominant_month(anchors)
        in_month = [a for a in anchors if (a["date"].year, a["date"].month) == (year, month)]
        if len(in_month) < MIN_ANCHORS_FOR_GRID:
            return super()._row_positions(words, anchors, spacing)

        # התאמה ראשונה לפי החציון, ואחריה קו ישר (cy = c0 + step * day) רק על התאריכים שמסתדרים איתה
        offset = median(a["date"].toordinal() - a["cy"] / spacing for a in in_month)
        good = [a for a in in_month if abs(a["date"].toordinal() - offset - a["cy"] / spacing) < 0.4]
        if len(good) >= MIN_ANCHORS_FOR_GRID:
            xs = [a["date"].toordinal() for a in good]
            ys = [a["cy"] for a in good]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            step = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
            c0 = my - step * mx
        else:
            step, c0 = spacing, -offset * spacing

        self._learn_time_columns(words)

        def has_row(cy):
            """שורה מחוץ לטווח התאריכים שנקראו נחשבת רק אם נקרא בה משהו שנראה כמו תאריך."""
            return any("/" in w["text"] and abs(w["cy"] - cy) <= 0.35 * step for w in words)

        first_read = min(a["date"] for a in good or in_month)
        last_read = max(a["date"] for a in good or in_month)
        days_in_month = calendar.monthrange(year, month)[1]
        positions = []
        for k in range(-2, days_in_month + 2):              # +2: הטבלה יכולה להסתיים ב-1 לחודש הבא
            d = date(year, month, 1) + timedelta(days=k)
            cy = c0 + step * d.toordinal()
            if date(year, month, 1) <= d <= last_read or has_row(cy):      # הטבלה מתחילה ב-1 לחודש
                positions.append((d, cy))
            elif d > last_read:
                break
        aligned = self._align_to_shabbat(words, positions, step)
        return [(d, cy) for d, cy in aligned if d >= date(year, month, 1)]   # הטבלה מתחילה ב-1 לחודש

    @staticmethod
    def _align_to_shabbat(words, positions, step):
        """
        בדיקת שפיות: אם התאריכים "זזו" בשורה אחת (כמה תאריכים נקראו לא נכון באותו כיוון), שעות של
        יום שישי היו נרשמות על שבת. בודקים הזזה של -1/0/+1 יום לפי שתי ראיות מהעמוד עצמו:
          - שמות הימים שה-OCR כן קרא ('ראשון', 'שלישי') צריכים להתאים לתאריך;
          - בשורת שבת (מוצללת) אין שעות.
        בוחרים את ההזזה עם הכי הרבה התאמות. בתיקו - בלי הזזה.
        """
        def near(cy):
            return [w for w in words if abs(w["cy"] - cy) <= 0.35 * step]

        rows = [(d, near(cy)) for d, cy in positions]

        def evidence(shift):
            points = 0
            for d, row_words in rows:
                weekday = (d + timedelta(days=shift)).weekday()
                names = {w["text"] for w in row_words if has_hebrew(w["text"])}
                names |= {n[::-1] for n in names}
                if difflib.get_close_matches(DAY_NAMES[weekday], names, n=1, cutoff=0.75):
                    points += 1
                if weekday == SATURDAY and any(TIME_RE.match(w["text"]) for w in row_words):
                    points -= 2
            return points

        best = max((0, -1, 1), key=lambda k: (evidence(k), -abs(k)))
        if best:
            log.warning("dates were shifted by %+d day to match the day names - check the original", best)
            return [(d + timedelta(days=best), cy) for d, cy in positions]
        return positions

    def _learn_time_columns(self, words):
        """שתי עמודות השעות: מקבצים את המיקומים של כל השעות בעמוד לשתי קבוצות. הימנית = כניסה."""
        xs = sorted((w["x0"] + w["x1"]) / 2 for w in words if TIME_RE.match(w["text"]))
        if len(xs) < 10:
            return
        gaps = [(b - a, i) for i, (a, b) in enumerate(zip(xs, xs[1:]))]
        _, split = max(gaps)
        left, right = xs[:split + 1], xs[split + 1:]
        self._exit_x, self._entry_x = median(left), median(right)

    def _column_of(self, x):
        if self._entry_x is None:
            return None
        return "entry" if abs(x - self._entry_x) < abs(x - self._exit_x) else "exit"

    def _total_column(self, line):
        """המילים שמשמאל לעמודת היציאה: רק שם יש סה"כ. ('840' בעמודת הכניסה הוא '8:10' שבור, לא סה"כ.)"""
        if self._exit_x is None:
            return line
        column_gap = self._entry_x - self._exit_x
        return [w for w in line if (w["x0"] + w["x1"]) / 2 < self._exit_x - column_gap / 2]

    def _remember_uncertain(self, work_date, line, total_line):
        """שורה שנקראה בה רק שעה אחת, בלי סה"כ אמין. אולי נשלים אותה מהשעות החודשיות שבכותרת."""
        times = time_candidates(line)
        if len(times) >= 1 and self._entry_x is not None:
            minutes, (_, x) = max(times.items(), key=lambda kv: kv[1][0])
            self._uncertain[work_date] = (minutes, self._column_of(x),
                                          hours_candidates(total_line, with_lookalikes=True))

    def _shift_from_one_time_and_total(self, line, total_line):
        """
        שעה אחת לא נקראה: מחשבים אותה מהשעה השנייה ומעמודת הסה"כ של אותה שורה
        (יציאה = כניסה + סה"כ). זה הכלל של הדו"ח עצמו, לא המצאה.
        """
        totals = hours_candidates(total_line, with_lookalikes=True)
        times = time_candidates(line)
        if not totals or not times or self._entry_x is None:
            return None
        total = max(totals, key=totals.get)
        minutes, (_, x) = max(times.items(), key=lambda kv: kv[1][0])
        length = round(total * 60)
        if self._column_of(x) == "entry":
            entry, exit_ = minutes, minutes + length
        else:
            entry, exit_ = minutes - length, minutes
        if not (0 <= entry < exit_ < 24 * 60):
            return None
        return time(entry // 60, entry % 60), time(exit_ // 60, exit_ % 60)

    # ---------- שורה ----------
    def _parse_row(self, work_date: date, line: list[dict]) -> AttendanceRow:
        tokens = [w["text"] for w in line]
        note = clean_note(" ".join(hebrew_words(tokens, is_visual_order(tokens))))

        entry = exit_ = None
        total = 0.0
        totals = self._total_column(line)
        shift = read_shift_with_total(line, total_line=totals)    # כניסה ויציאה שמסתדרות עם הסה"כ
        if shift is None:
            shift = self._shift_from_one_time_and_total(line, totals)
            if shift:
                log.info("%s: one time was not read - computed from the total column", work_date)
                if max(hours_candidates(totals, with_lookalikes=True).values()) < 2:
                    self._remember_uncertain(work_date, line, totals)     # הסה"כ נקרא רק פעם אחת
            else:
                self._remember_uncertain(work_date, line, totals)
        if shift:
            entry, exit_ = shift
            total = hours_between(entry, exit_)
        else:
            times = read_times(line, 2)         # מימין לשמאל: כניסה, יציאה
            if len(times) == 2 and times[1] > times[0] and not hours_candidates(totals):
                entry, exit_ = times            # אין עמודת סה"כ לבדוק מולה
                total = hours_between(entry, exit_)
            elif times:
                log.warning("%s: entry/exit do not match the total column (%s) - row kept without hours",
                            work_date, ", ".join(t.strftime("%H:%M") for t in times))

        return AttendanceRow(work_date=work_date, day_name=self._day_name(work_date),
                             entry_time=entry, exit_time=exit_, total_hours=total, note=note)

    def _finish_rows(self, rows: list[AttendanceRow], header_lines) -> list[AttendanceRow]:
        rows = self._complete_from_monthly_total(rows, header_lines)
        for r in rows:
            if not r.is_work_day and r.work_date.weekday() not in (4, SATURDAY) and not r.note:
                log.warning("%s: weekday without hours and without a note - check the original", r.work_date)
        return rows

    def _complete_from_monthly_total(self, rows, header_lines):
        """
        שורות לא ודאיות (שעה אחת נקראה, והסה"כ לא נקרא או נקרא רק פעם אחת) נפתרות לפי החשבון של
        הדו"ח עצמו: סכום השורות = השעות החודשיות שבכותרת. בוחרים לכל שורה כזו סה"כ מבין המועמדים
        שנקראו בה, כך שהסכום יתאים. שורה בלי מועמדים בכלל מקבלת את ההפרש, רק אם היא היחידה.
        """
        by_date = {r.work_date: r for r in rows}
        uncertain = {d: u for d, u in self._uncertain.items()
                     if d in by_date and (u[2] or not by_date[d].is_work_day)}
        if not uncertain or len(uncertain) > 3:
            return rows
        monthly = self._match_labels(*self._read_header(header_lines),
                                     sum_field(rows, "total_hours")).get("monthly")
        if not monthly:
            return rows
        need = monthly - sum(r.total_hours for r in rows if r.work_date not in uncertain)

        dates = list(uncertain)
        if len(dates) == 1 and not uncertain[dates[0]][2]:
            choice = {dates[0]: round(need, 2)}
        else:
            choice, best = None, 0.0
            for combo in product(*(sorted(uncertain[d][2].items()) for d in dates)):
                votes = sum(v for _, v in combo)
                if abs(sum(t for t, _ in combo) - need) <= 0.02 and votes > best:
                    choice, best = {d: t for d, (t, _) in zip(dates, combo)}, votes
            if choice is None:
                return rows

        completed = {}
        for d, total in choice.items():
            minutes, column, _ = uncertain[d]
            length = round(total * 60)
            entry, exit_ = (minutes, minutes + length) if column == "entry" else (minutes - length, minutes)
            if not (0 < total <= 24 and 0 <= entry < exit_ < 24 * 60):
                return rows
            completed[d] = (time(entry // 60, entry % 60), time(exit_ // 60, exit_ % 60))
            log.warning("%s: completed from the monthly hours in the header: %s-%s",
                        d, *(t.strftime("%H:%M") for t in completed[d]))
        return [replace(r, entry_time=completed[r.work_date][0], exit_time=completed[r.work_date][1],
                        total_hours=hours_between(*completed[r.work_date]))
                if r.work_date in completed else r for r in rows]

    # ---------- הסיכום שבראש הדו"ח ----------
    _LABELS = {"לתשלום": "payment", "מחיר": "rate", "חודשיות": "monthly", "ימי": "days"}

    def _parse_summary(self, header_lines, rows) -> ReportSummary:
        labels, numbers = self._read_header(header_lines)
        computed_hours = sum_field(rows, "total_hours")
        found = self._match_labels(labels, numbers, computed_hours)

        rate = found.get("rate")
        if rate is None and found.get("payment") and found.get("monthly"):
            rate = round(found["payment"] / found["monthly"], 2)
        if rate is None and found.get("payment") and computed_hours:
            rate = round(found["payment"] / computed_hours, 2)
            log.warning("hourly rate was not read - computed from payment / hours: %s", rate)
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
        """
        קודם לפי החשבון: שלושה מספרים בכותרת שבהם מחיר לשעה × שעות חודשיות = לתשלום.
        זה עובד גם כשה-OCR לא קרא את התוויות העבריות, וגם כשנקראו ליד התוויות מספרים שבורים.
        מבין שני הגורמים, השעות החודשיות הוא זה שקרוב לסכום השורות.
        אם אין שלישייה כזו - כל תווית מקבלת את המספר הקרוב אליה.
        """
        values = sorted({v for v, _, _ in numbers}, reverse=True)
        for payment in values:
            for a in values:
                for b in values:
                    if 0 < b < a < payment and abs(a * b - payment) <= max(0.02, payment * 1e-4):
                        monthly, rate = sorted((a, b), key=lambda v: abs(v - computed_hours))
                        return {"payment": payment, "rate": rate, "monthly": monthly}
        found = {}
        for key, lcx, lcy in labels:
            if key not in found and numbers:
                found[key] = min(numbers, key=lambda n: abs(n[1] - lcx) + 5 * abs(n[2] - lcy))[0]
        return found
