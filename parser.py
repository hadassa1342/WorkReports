import os
import re
import csv
from abc import ABC, abstractmethod
from datetime import datetime
import pdfplumber
from domain.models import ReportARow, ReportBRow, ReportResult

# weekday(): 0=שני ... 5=שבת, 6=ראשון
DAY_NAMES = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
MONTH_NAMES = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
               "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
_REVERSED_DAYS = {d[::-1] for d in DAY_NAMES}

_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
_DEC_RE = re.compile(r"^\d+\.\d{1,2}$")
_NUM_RE = re.compile(r"^[\d,]+(\.\d+)?$")


def parse_date(text):
    """'01/09/22' או '01/09/2022' -> datetime. None אם לא תקין."""
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(text).strip(), fmt)
        except ValueError:
            continue
    return None


def date_sort_key(date_text):
    """מיון לפי תאריך אמיתי ולא לפי מחרוזת (אחרת 01/10 יוצא לפני 02/09)."""
    return parse_date(date_text) or datetime.max


def read_word_lines(page):
    """מחזיר שורות מהעמוד, מלמעלה למטה. בכל שורה המילים (dict עם text ו-x0/x1) מימין לשמאל."""
    words = page.extract_words()
    if not words:
        return []
    lines = {}
    for w in words:
        line_y = round(w['top'] / 7) * 7
        lines.setdefault(line_y, []).append(w)
    result = []
    for line_y in sorted(lines):
        line_words = sorted(lines[line_y], key=lambda x: x['x0'], reverse=True)
        result.append(line_words)
    return result


def read_lines(page):
    """כמו read_word_lines אבל רק הטקסטים."""
    return [[w['text'] for w in line] for line in read_word_lines(page)]


class BaseParser(ABC):
    @abstractmethod
    def parse(self, pdf_path: str) -> ReportResult:
        """פונקציית פענוח אבסטרקטית המשותפת לכלל הפרסרים בפרויקט"""
        pass

    def fix_hebrew(self, val):
        """לוגיקה משותפת לתיקון כיווניות עברית במחלקות היורשות"""
        if not val:
            return ""
        s = str(val).strip()
        if any('\u0590' <= c <= '\u05FF' for c in s):
            return s[::-1]
        return s

    def safe_float(self, val):
        """המרת ערכים מספריים באופן בטוח למניעת שגיאות ריצה"""
        if not val:
            return 0.0
        cleaned = str(val).replace('₪', '').replace(',', '').strip()
        try:
            return float(cleaned)
        except ValueError:
            return 0.0


class TypeAParser(BaseParser):
    def parse(self, pdf_path: str) -> ReportResult:
        rows = []
        summary = {}

        days_hebrew = {
            0: "יום שני",
            1: "יום שלישי",
            2: "יום רביעי",
            3: "יום חמישי",
            4: "יום שישי",
            5: "יום שבת",
            6: "יום ראשון"
        }

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                words = page.extract_words()
                if not words:
                    continue

                lines_dict = {}
                for w in words:
                    line_y = round(w['top'] / 7) * 7
                    if line_y not in lines_dict:
                        lines_dict[line_y] = []
                    lines_dict[line_y].append(w)

                for line_y in sorted(lines_dict.keys()):
                    line_words = sorted(lines_dict[line_y], key=lambda x: x['x0'], reverse=True)
                    tokens = [w['text'] for w in line_words]

                    if not tokens:
                        continue

                    date_val = None
                    date_idx = -1
                    for idx, token in enumerate(tokens):
                        if '/' in token and len(token) >= 8 and any(char.isdigit() for char in token):
                            date_val = token
                            date_idx = idx
                            break

                    if not date_val or date_idx == -1:
                        continue

                    try:
                        try:
                            dt_obj = datetime.strptime(date_val.strip(), "%d/%m/%Y")
                            day = days_hebrew.get(dt_obj.weekday(), "")
                        except Exception:
                            day = "יום כלשהו"

                        location = "משרד ראשי"

                        entry_time = tokens[date_idx + 2] if date_idx + 2 < len(tokens) and ":" in tokens[
                            date_idx + 2] else "08:00"
                        exit_time = tokens[date_idx + 3] if date_idx + 3 < len(tokens) and ":" in tokens[
                            date_idx + 3] else "16:00"
                        break_time = tokens[date_idx + 4] if date_idx + 4 < len(tokens) else "00:30"

                        total_hours = self.safe_float(tokens[date_idx + 5]) if date_idx + 5 < len(tokens) and tokens[
                            date_idx + 5].replace('.', '', 1).isdigit() else 7.5
                        hours_100 = total_hours
                        hours_125 = 0.0
                        hours_150 = 0.0
                        shabbat_hours = 0.0

                        row_obj = ReportARow(
                            date=date_val,
                            day=day,
                            location=location,
                            entry_time=entry_time,
                            exit_time=exit_time,
                            break_time=break_time,
                            total_hours=total_hours,
                            hours_100=hours_100,
                            hours_125=hours_125,
                            hours_150=hours_150,
                            shabbat_hours=shabbat_hours
                        )
                        rows.append(row_obj)
                    except Exception:
                        continue

        return ReportResult(report_type="A", rows=rows, summary_data=summary)


class TypeBParser(BaseParser):
    """
    סוג B. שורה בפורמט:  תאריך | יום | כניסה | יציאה | סה"כ | הערות
    שורה של שבת/חג: תאריך | יום | הערות  (בלי שעות) - נשמרת עם שעות ריקות.
    למעלה: חודש, ואחריו לתשלום / מחיר לשעה / שעות חודשיות / ימי עבודה.
    """

    def parse(self, pdf_path: str) -> ReportResult:
        rows = []
        summary = {}
        header_words = []
        seen_row = False

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for line in read_word_lines(page):
                    tokens = [w['text'] for w in line]
                    date_tok = next((t for t in tokens if _DATE_RE.match(t)), None)

                    if date_tok is None:
                        if not seen_row:
                            self._read_header_line(line, summary, header_words)
                        continue

                    seen_row = True
                    row = self._parse_row(tokens, date_tok)
                    if row is not None:
                        rows.append(row)

        self._finish_summary(summary, header_words)
        return ReportResult(report_type="B", rows=rows, summary_data=summary)

    # ---------- כותרת עליונה ----------
    # תוויות הכרטיסים (מילת מפתח -> שדה). מזהים לפי מיקום אופקי, לא לפי סדר,
    # כי סדר הכרטיסים ב-PDF לא בהכרח זהה לסדר הקריאה.
    _LABELS = {"לתשלום": "payment", "מחיר": "rate", "חודשיות": "monthly", "ימי": "days"}

    def _read_header_line(self, line, summary, header_words):
        tokens = [w['text'] for w in line]

        month = None
        for t in tokens:
            if t in MONTH_NAMES:
                month = t
            elif t[::-1] in MONTH_NAMES:
                month = t[::-1]
        if month:
            year = next((t for t in tokens if re.match(r"^\d{4}$", t)), "")
            summary["month_year"] = f"{month} {year}".strip()
            return

        for w in line:
            t = w['text']
            center = (w['x0'] + w['x1']) / 2
            key = self._LABELS.get(t) or self._LABELS.get(t[::-1])
            if key:
                header_words.append(("label", key, center))
                continue
            cleaned = t.replace("₪", "").strip()
            if cleaned and _NUM_RE.match(cleaned):
                header_words.append(("num", float(cleaned.replace(",", "")), center))

    def _finish_summary(self, summary, header_words):
        labels = [(k, c) for kind, k, c in header_words if kind == "label"]
        nums = [(v, c) for kind, v, c in header_words if kind == "num"]
        found = {}
        for value, center in nums:
            if labels:
                key = min(labels, key=lambda lc: abs(lc[1] - center))[0]
                found.setdefault(key, value)

        if "rate" in found:
            summary["hourly_rate"] = found["rate"]
        if "payment" in found:
            summary["original_payment"] = found["payment"]
        if "monthly" in found:
            summary["original_monthly_hours"] = found["monthly"]
        if "days" in found:
            summary["original_work_days"] = int(found["days"])

        # אם המחיר לשעה לא נקרא אבל יש תשלום ושעות - מחשבים
        if not summary.get("hourly_rate") and found.get("payment") and found.get("monthly"):
            summary["hourly_rate"] = round(found["payment"] / found["monthly"], 2)

    # ---------- שורה ----------
    def _parse_row(self, tokens, date_tok):
        dt = parse_date(date_tok)
        day_of_week = DAY_NAMES[dt.weekday()] if dt else ""

        # אם ה-PDF נקרא בסדר ויזואלי, האותיות בכל מילה הפוכות
        visual = any(t in _REVERSED_DAYS for t in tokens)

        times = [t for t in tokens if _TIME_RE.match(t)]
        total_tok = next((t for t in tokens if _DEC_RE.match(t)), None)

        other = [t for t in tokens
                 if t != date_tok and not _TIME_RE.match(t) and not _DEC_RE.match(t)]
        words = [t[::-1] if visual else t for t in other]
        for i, w in enumerate(words):      # מסירים את שם היום, מה שנשאר הוא הערה
            if w in DAY_NAMES:
                del words[i]
                break
        notes = " ".join(words).strip()

        if len(times) >= 2:
            entry_time, exit_time = times[0], times[1]
            if total_tok is not None:
                total_hours = float(total_tok)
            else:
                h1, m1 = map(int, entry_time.split(":"))
                h2, m2 = map(int, exit_time.split(":"))
                total_hours = round(((h2 * 60 + m2) - (h1 * 60 + m1)) / 60, 2)
        else:
            # שבת/חג: בלי שעות
            entry_time, exit_time, total_hours = "", "", 0.0

        return ReportBRow(
            date=date_tok,
            day_of_week=day_of_week,
            entry_time=entry_time,
            exit_time=exit_time,
            total_hours=total_hours,
            notes=notes,
        )


class ReportParserFactory:
    @staticmethod
    def detect_report_type(pdf_path: str) -> str:
        filename = os.path.basename(pdf_path).lower()
        if 'b' in filename:
            return 'B'
        if 'a' in filename:
            return 'A'

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if "נוכחות" in text or "כרטסת" in text or "הערות" in text:
                    return 'B'
        return 'A'

    @staticmethod
    def get_parser(pdf_path: str) -> BaseParser:
        report_type = ReportParserFactory.detect_report_type(pdf_path)
        print(f"זיהוי אוטומטי: זוהה דוח מסוג [{report_type}]")

        parsers_map = {
            'A': TypeAParser,
            'B': TypeBParser
        }

        parser_class = parsers_map.get(report_type, TypeAParser)
        return parser_class()

    @staticmethod
    def process_and_generate(pdf_path: str, output_path: str = "data/outputs/output_report.csv"):
        parser = ReportParserFactory.get_parser(pdf_path)
        result = parser.parse(pdf_path)

        # מיון לפי תאריך אמיתי (לא לפי מחרוזת)
        result.rows.sort(key=lambda r: (date_sort_key(r.date), getattr(r, 'entry_time', '')))

        total_hours = sum(row.total_hours for row in result.rows)
        result.summary_data["calculated_total_hours"] = total_hours

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        with open(output_path, mode='w', newline='', encoding='utf-8-sig') as file:
            writer = csv.writer(file)
            if result.report_type == "A":
                writer.writerow([
                    "תאריך", "יום", "מקום", "כניסה", "יציאה", "הפסקה",
                    "סה\"כ שעות", "100%", "125%", "150%", "שבת"
                ])
                for row in result.rows:
                    writer.writerow([
                        row.date, row.day, row.location, row.entry_time, row.exit_time,
                        row.break_time, row.total_hours, row.hours_100, row.hours_125,
                        row.hours_150, row.shabbat_hours
                    ])
            elif result.report_type == "B":
                writer.writerow([
                    "תאריך", "יום בשבוע", "שעת כניסה", "שעת יציאה", "סה\"כ שעות", "הערות"
                ])
                for row in result.rows:
                    writer.writerow([
                        row.date, row.day_of_week, row.entry_time, row.exit_time,
                        row.total_hours, row.notes
                    ])

        print(f"התהליך הסתיים בהצלחה! סך שעות: {total_hours}, קובץ נשמר בנתיב: {output_path}")
        return result
