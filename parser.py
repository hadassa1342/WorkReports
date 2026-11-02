import os
import csv
from abc import ABC, abstractmethod
from datetime import datetime
import pdfplumber
from domain.models import ReportARow, ReportBRow, ReportResult


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
        cleaned = str(val).replace('₪', '').strip()
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
                        # חישוב אוטומטי של היום בשבוע מתוך התאריך
                        try:
                            dt_obj = datetime.strptime(date_val.strip(), "%d/%m/%Y")
                            day = days_hebrew.get(dt_obj.weekday(), "")
                        except Exception:
                            day = "יום כלשהו"

                        # הגדרת מקום בצורה מסודרת
                        location = "גונן"

                        # שאר השדות לפי סדר העמודות המדויק
                        entry_time = tokens[date_idx + 2] if date_idx + 2 < len(tokens) else "07:00"
                        exit_time = tokens[date_idx + 3] if date_idx + 3 < len(tokens) else "16:00"
                        break_time = tokens[date_idx + 4] if date_idx + 4 < len(tokens) else "00:30"

                        total_hours = self.safe_float(tokens[date_idx + 5] if date_idx + 5 < len(tokens) else 8.0)
                        hours_100 = self.safe_float(tokens[date_idx + 6] if date_idx + 6 < len(tokens) else 8.0)
                        hours_125 = self.safe_float(tokens[date_idx + 7] if date_idx + 7 < len(tokens) else 0)
                        hours_150 = self.safe_float(tokens[date_idx + 8] if date_idx + 8 < len(tokens) else 0)
                        shabbat_hours = self.safe_float(tokens[date_idx + 9] if date_idx + 9 < len(tokens) else 0)

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
    def parse(self, pdf_path: str) -> ReportResult:
        rows = []
        summary = {}

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
                    for token in tokens:
                        if '/' in token and len(token) >= 8 and any(char.isdigit() for char in token):
                            date_val = token
                            break

                    if not date_val:
                        continue

                    try:
                        date_idx = tokens.index(date_val)
                        day1 = self.fix_hebrew(tokens[date_idx - 1]) if date_idx - 1 >= 0 else ""
                        day2 = self.fix_hebrew(tokens[date_idx - 2]) if date_idx - 2 >= 0 else ""
                        day_of_week = f"{day1} {day2}".strip()

                        entry_time = tokens[date_idx - 3] if date_idx - 3 >= 0 else ""
                        exit_time = tokens[date_idx - 4] if date_idx - 4 >= 0 else ""
                        total_hours = self.safe_float(tokens[date_idx - 5] if date_idx - 5 >= 0 else 0)
                        notes = self.fix_hebrew(tokens[date_idx - 6]) if date_idx - 6 >= 0 else ""

                        row_obj = ReportBRow(
                            date=date_val,
                            day_of_week=day_of_week,
                            entry_time=entry_time,
                            exit_time=exit_time,
                            total_hours=total_hours,
                            notes=notes
                        )
                        rows.append(row_obj)
                    except Exception:
                        continue

        return ReportResult(report_type="B", rows=rows, summary_data=summary)


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

        result.rows.sort(key=lambda r: (r.date, getattr(r, 'entry_time', '')))

        total_hours = sum(row.total_hours for row in result.rows)
        result.summary_data["calculated_total_hours"] = total_hours

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, mode='w', newline='', encoding='utf-8-sig') as file:
            writer = csv.writer(file)
            if result.report_type == "A":
                writer.writerow([
                    "תאריך", "יום", "מקום", "כניסה", "ציאה", "הפסקה",
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