import os
import re
import csv
from abc import ABC, abstractmethod
from datetime import datetime
import pdfplumber
from ocr_words import page_words
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


_BIDI_MARKS = dict.fromkeys(map(ord, "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"))


def clean_token(text):
    """מסיר תווי כיווניות נסתרים (RLM וכו') שנדבקים לתאריכים ומספרים."""
    return str(text).translate(_BIDI_MARKS).strip()


def read_word_lines(page):
    """
    מחזיר שורות מהעמוד, מלמעלה למטה. בכל שורה המילים (dict עם text, x0, x1, top, bottom)
    מימין לשמאל. קיבוץ לפי מרכז אנכי: מילה שייכת לשורה אם היא קרובה אנכית למילה
    הקודמת, כך שגם סריקה מעט עקומה לא מפצלת שורה.
    """
    words = []
    for w in page_words(page):
        text = clean_token(w["text"])
        if not text or not any(c.isalnum() for c in text):    # קווי טבלה ('|') וכו'
            continue
        w = dict(w)
        w["text"] = text
        w["cy"] = (w["top"] + w.get("bottom", w["top"])) / 2
        words.append(w)
    if not words:
        return []

    heights = sorted(w.get("bottom", w["top"]) - w["top"] for w in words)
    median_h = heights[len(heights) // 2] or 8
    tol = 0.6 * median_h

    words.sort(key=lambda w: w["cy"])
    lines = [[words[0]]]
    for w in words[1:]:
        if w["cy"] - lines[-1][-1]["cy"] > tol:
            lines.append([w])
        else:
            lines[-1].append(w)
    return [sorted(line, key=lambda x: x["x0"], reverse=True) for line in lines]


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


def _has_hebrew(text):
    return any('\u0590' <= c <= '\u05FF' for c in text)


def _to_hours(token):
    """'6.50' -> 6.5, '6,50' -> 6.5, '650' (נקודה שאבדה ב-OCR) -> 6.5. אחרת None."""
    cleaned = re.sub(r"[^\d.,]", "", token)
    if re.fullmatch(r"\d+[.,]\d{1,2}", cleaned):
        return float(cleaned.replace(",", "."))
    if re.fullmatch(r"\d{3}", cleaned):
        return int(cleaned) / 100
    return None


def _split_hours_rule(total, weekday):
    """גיבוי כשהחלוקה לא נקראה: שבת -> הכול לשבת. אחרת עד 8 ב-100%, שעתיים ב-125%, השאר 150%."""
    if weekday == 5:
        return 0.0, 0.0, 0.0, total
    h125 = round(float(min(max(total - 8, 0), 2)), 2)
    h150 = round(float(max(total - 10, 0)), 2)
    return round(total - h125 - h150, 2), h125, h150, 0.0


class TypeAParser(BaseParser):
    """
    סוג A. עמודות (מימין לשמאל):
    תאריך | יום | מקום | כניסה | יציאה | הפסקה | סה"כ | 100% | 125% | 150% | שבת

    כל שורה מזוהה לפי התאריך שבה. כניסה/יציאה/הפסקה נלקחות משלוש השעות בשורה
    (לפי סדר, מימין לשמאל), והיום מחושב מהתאריך. הסה"כ מחושב מהשעות ולא נקרא
    מה-OCR, שמפספס לפעמים נקודה עשרונית.
    """

    def parse(self, pdf_path: str) -> ReportResult:
        rows = []
        locations = []

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for line in read_word_lines(page):
                    tokens = [w["text"] for w in line]
                    date_tok = next((t for t in tokens if _DATE_RE.match(t)), None)
                    if date_tok is None:
                        continue
                    parsed = self._parse_row(tokens, date_tok)
                    if parsed is None:
                        continue
                    row, location = parsed
                    rows.append(row)
                    if location:
                        locations.append(location)

        # המקום זהה בדרך כלל בכל השורות, ולכן לוקחים את הנפוץ ביותר (מסנן רעש של OCR)
        common_location = "משרד ראשי"
        if locations:
            common_location = max(set(locations), key=locations.count)
        for row in rows:
            row.location = common_location

        summary = {}
        months = [(parse_date(r.date).year, parse_date(r.date).month) for r in rows if parse_date(r.date)]
        if months:
            year, month = max(set(months), key=months.count)
            summary["month_year"] = f"{MONTH_NAMES[month - 1]} {year}"

        return ReportResult(report_type="A", rows=rows, summary_data=summary)

    def _parse_row(self, tokens, date_tok):
        dt = parse_date(date_tok)
        if dt is None:
            return None
        weekday = dt.weekday()
        day = f"יום {DAY_NAMES[weekday]}"

        visual = any(t in _REVERSED_DAYS for t in tokens)

        times = [t for t in tokens if _TIME_RE.match(t)]
        entry_time = exit_time = break_time = ""
        total = 0.0
        if len(times) >= 2:
            e, x = times[0], times[1]
            b = times[2] if len(times) >= 3 else "00:30"
            e_m, x_m, b_m = (self._minutes(v) for v in (e, x, b))
            total = round((x_m - e_m - b_m) / 60, 2)
            if total > 0:
                entry_time, exit_time, break_time = e, x, b
            else:
                total = 0.0    # שעות לא הגיוניות (שגיאת OCR): נשארות ריקות, ה-generator יגריל

        # חלוקה ל-100/125/150/שבת: אם נקראו 5 ערכים שמסתדרים עם הסה"כ - משתמשים בהם
        values = []
        for t in tokens:
            if t == date_tok or _TIME_RE.match(t) or "/" in t or _has_hebrew(t):
                continue
            v = _to_hours(t)
            if v is not None:
                values.append(v)
        split = None
        if total > 0 and len(values) == 5:
            if abs(values[0] - total) < 0.011 and abs(sum(values[1:]) - total) < 0.011:
                split = tuple(values[1:])
        if split is None:
            split = _split_hours_rule(total, weekday)
        h100, h125, h150, shabbat = split

        words = [t[::-1] if visual else t for t in tokens if _has_hebrew(t)]
        words = [w for w in words if w != "יום" and w not in DAY_NAMES]
        location = " ".join(words).strip()

        row = ReportARow(
            date=date_tok,
            day=day,
            location="",
            entry_time=entry_time,
            exit_time=exit_time,
            break_time=break_time,
            total_hours=total,
            hours_100=h100,
            hours_125=h125,
            hours_150=h150,
            shabbat_hours=shabbat,
        )
        return row, location

    @staticmethod
    def _minutes(hhmm):
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)


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
        # הערות הן טקסט עברי בלבד; זבל של OCR (אותיות לועזיות/סימנים) נזרק
        words = [w for w in words if any('\u0590' <= c <= '\u05FF' for c in w)]
        notes = " ".join(words).strip()

        if len(times) >= 2:
            entry_time, exit_time = times[0], times[1]
            # הסה"כ תמיד מחושב מהשעות (ולא נלקח מהטקסט), כדי ש-OCR שטעה בספרה לא ישפיע
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
        """זיהוי לפי כותרות העמודות (גם בקובץ סרוק, דרך OCR). שם הקובץ רק כגיבוי."""
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            if pdf.pages:
                text = " ".join(w["text"] for w in page_words(pdf.pages[0]))

        def has(*keys):
            return any(k in text or k[::-1] in text for k in keys)

        if has("הפסקה", "מקום"):          # עמודות שקיימות רק בסוג A
            return 'A'
        if has("הערות", "שעת", "חודשיות"):  # כותרות שקיימות רק בסוג B
            return 'B'

        filename = os.path.basename(pdf_path).lower()
        if 'b' in filename:
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
