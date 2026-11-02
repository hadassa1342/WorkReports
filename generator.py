import os
import random

from domain.models import ReportResult

# ---------- כללי השינוי ----------
WORK_START = 7 * 60          # 07:00 בדקות מחצות
WORK_END = 19 * 60           # 19:00
MAX_SHIFT = 25               # בכמה דקות מותר להזיז שעה מהמקור, לכל כיוון
LEN_JITTER = 15              # סוג B: שינוי מותר באורך המשמרת, בדקות
MIN_WORK = 60                # משמרת קצרה משעה לא הגיונית
BREAK_A = 30                 # הפסקה בסוג A (בסוג B אין עמודת הפסקה)


def to_minutes(text):
    """'08:30' -> 510. מחזיר None אם המחרוזת לא שעה תקינה."""
    try:
        h, m = str(text).strip().split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def to_hhmm(minutes):
    """סוג A: 08:30"""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def to_h_mm(minutes):
    """סוג B (כמו במקור): 8:30"""
    return f"{minutes // 60}:{minutes % 60:02d}"


def _valid(entry, exit_, break_minutes):
    if not (WORK_START <= entry < exit_ <= WORK_END):
        return False
    if exit_ - entry - break_minutes < MIN_WORK:
        return False
    if entry % 15 == 0 or exit_ % 15 == 0:      # לא שעה "עגולה מדי"
        return False
    return True


def random_shift(rng, original_entry, original_exit, break_minutes):
    """
    סוג A. מגריל כניסה ויציאה שעומדות בכל הכללים:
      - שתיהן בין 07:00 ל-19:00
      - היציאה אחרי הכניסה, ונשארת לפחות שעת עבודה אחרי ההפסקה
      - לא שעה "עגולה מדי" (08:00, 08:15, 08:30, 08:45)
    אם יש שעות במקור - מזיזים סביבן. אם אין - מגרילים בכל הטווח.
    """
    for _ in range(1000):
        if original_entry is not None and original_exit is not None:
            entry = original_entry + rng.randint(-MAX_SHIFT, MAX_SHIFT)
            exit_ = original_exit + rng.randint(-MAX_SHIFT, MAX_SHIFT)
        else:
            entry = rng.randint(WORK_START, 10 * 60)
            exit_ = entry + break_minutes + rng.randint(4 * 60, 9 * 60)

        if _valid(entry, exit_, break_minutes):
            return entry, exit_
    raise ValueError("לא נמצאו שעות שעומדות בכללים")


def random_shift_keep_length(rng, original_entry, original_exit, break_minutes=0):
    """
    סוג B. מזיזים את הכניסה, ומשנים מעט את אורך המשמרת,
    כך שהסך החודשי (והתשלום) נשארים קרובים למקור.
    """
    orig_len = original_exit - original_entry
    for _ in range(1000):
        entry = original_entry + rng.randint(-MAX_SHIFT, MAX_SHIFT)
        exit_ = entry + orig_len + rng.randint(-LEN_JITTER, LEN_JITTER)
        if _valid(entry, exit_, break_minutes):
            return entry, exit_
    raise ValueError("לא נמצאו שעות שעומדות בכללים")


def split_hours_a(total, day_text):
    """סוג A: שבת -> הכול לשבת. אחרת: עד 8 שעות 100%, השעתיים הבאות 125%, השאר 150%."""
    if "שבת" in str(day_text):
        return 0.0, 0.0, 0.0, total
    h125 = round(min(max(total - 8, 0), 2), 2)
    h150 = round(max(total - 10, 0), 2)
    h100 = round(total - h125 - h150, 2)      # כהפרש, כדי שהחלוקה תסתכם בדיוק לסה"כ
    return h100, h125, h150, 0.0


class ReportHtmlPdfGenerator:
    @staticmethod
    def generate_like_original(result: ReportResult, output_pdf_path: str, seed: int = 1):
        """
        seed: אותו seed -> אותו פלט בכל הרצה (דטרמיניסטי).
        """
        os.makedirs(os.path.dirname(output_pdf_path) or ".", exist_ok=True)
        rng = random.Random(seed)

        is_type_b = (result.report_type == "B")
        break_minutes = 0 if is_type_b else BREAK_A

        company_name = result.summary_data.get("company_name", "ג.ע. הכשר כח אדם בע\"מ")
        if is_type_b:
            report_month = result.summary_data.get("month_year", "")
        else:
            report_month = result.summary_data.get("month_year", "פברואר 2023")

        # ---------- כותרות טבלה ----------
        if not is_type_b:
            headers_html = """
                <tr>
                    <th>תאריך</th>
                    <th>יום</th>
                    <th>מקום</th>
                    <th>כניסה</th>
                    <th>יציאה</th>
                    <th>הפסקה</th>
                    <th>סה&quot;כ</th>
                    <th>100%</th>
                    <th>125%</th>
                    <th>150%</th>
                    <th>שבת</th>
                </tr>
            """
        else:
            headers_html = """
                <tr>
                    <th>תאריך</th>
                    <th>יום בשבוע</th>
                    <th>שעת כניסה</th>
                    <th>שעת יציאה</th>
                    <th>סה&quot;כ שעות</th>
                    <th>הערות</th>
                </tr>
            """

        # ---------- שורות ----------
        rows_html = ""
        work_days = 0
        sum_total = sum_100 = sum_125 = sum_150 = sum_shabbat = 0.0
        sum_break = 0

        for row in result.rows:
            orig_entry = to_minutes(row.entry_time)
            orig_exit = to_minutes(row.exit_time)

            if is_type_b:
                notes = getattr(row, "notes", "") or ""

                # שורה בלי שעות במקור = שבת או חג. נשארת ריקה ולא נספרת.
                if orig_entry is None or orig_exit is None:
                    rows_html += f"""
                    <tr>
                        <td>{row.date}</td>
                        <td>{row.day_of_week}</td>
                        <td></td>
                        <td></td>
                        <td></td>
                        <td>{notes}</td>
                    </tr>
                    """
                    continue

                entry_m, exit_m = random_shift_keep_length(rng, orig_entry, orig_exit)
                row_total = round((exit_m - entry_m) / 60, 2)

                work_days += 1
                sum_total += row_total

                rows_html += f"""
                    <tr>
                        <td>{row.date}</td>
                        <td>{row.day_of_week}</td>
                        <td>{to_h_mm(entry_m)}</td>
                        <td>{to_h_mm(exit_m)}</td>
                        <td>{row_total:.2f}</td>
                        <td>{notes}</td>
                    </tr>
                """
            else:
                entry_m, exit_m = random_shift(rng, orig_entry, orig_exit, break_minutes)
                entry, exit_t, break_t = to_hhmm(entry_m), to_hhmm(exit_m), to_hhmm(break_minutes)

                # הכלל: סה"כ = יציאה - כניסה - הפסקה
                row_total = round((exit_m - entry_m - break_minutes) / 60, 2)

                work_days += 1
                sum_total += row_total
                sum_break += break_minutes

                h100, h125, h150, shabbat = split_hours_a(row_total, row.day)
                sum_100 += h100
                sum_125 += h125
                sum_150 += h150
                sum_shabbat += shabbat
                rows_html += f"""
                    <tr>
                        <td>{row.date}</td>
                        <td>{row.day}</td>
                        <td>{row.location}</td>
                        <td>{entry}</td>
                        <td>{exit_t}</td>
                        <td>{break_t}</td>
                        <td>{row_total:.2f}</td>
                        <td>{h100:.2f}</td>
                        <td>{h125:.2f}</td>
                        <td>{h150:.2f}</td>
                        <td>{shabbat:.2f}</td>
                    </tr>
                """

        # הכלל: סה"כ שעות = סכום העמודה (מסכמים את הערכים המעוגלים שמוצגים בשורות)
        sum_total = round(sum_total, 2)
        sum_100, sum_125 = round(sum_100, 2), round(sum_125, 2)
        sum_150, sum_shabbat = round(sum_150, 2), round(sum_shabbat, 2)

        hourly_rate = result.summary_data.get("hourly_rate")
        rate = float(hourly_rate) if hourly_rate else 0.0
        payment = round(sum_total * rate, 2)      # סה"כ לתשלום = שעות חודשיות * מחיר לשעה

        # ---------- חלקים שתלויים בסוג ----------
        if not is_type_b:
            title_html = f"דו&quot;ח שעות עבודה (סוג {result.report_type})"
            top_html = ""
            footer_html = f"""
                <tr class="footer-row">
                    <td>סה&quot;כ</td><td></td><td></td><td></td><td></td>
                    <td>{to_hhmm(sum_break)}</td>
                    <td>{sum_total:.2f}</td>
                    <td>{sum_100:.2f}</td>
                    <td>{sum_125:.2f}</td>
                    <td>{sum_150:.2f}</td>
                    <td>{sum_shabbat:.2f}</td>
                </tr>
            """

            payment_html = ""
            if hourly_rate:
                payment_html = f"""
                    <div class="summary-row">
                        <span class="summary-label">מחיר לשעה</span>
                        <span class="summary-value">{rate:,.2f} ₪</span>
                    </div>
                    <div class="summary-row">
                        <span class="summary-label">סה&quot;כ לתשלום</span>
                        <span class="summary-value">{payment:,.2f} ₪</span>
                    </div>
                """

            bottom_html = f"""
            <div class="clearfix">
                <div class="summary-section">
                    <div class="summary-title">סיכום חודשי</div>
                    <div class="summary-row">
                        <span class="summary-label">ימי עבודה</span>
                        <span class="summary-value">{work_days}</span>
                    </div>
                    <div class="summary-row">
                        <span class="summary-label">סה&quot;כ שעות</span>
                        <span class="summary-value">{sum_total:.2f}</span>
                    </div>
                    <div class="summary-row">
                        <span class="summary-label">שעות 100%</span>
                        <span class="summary-value">{sum_100:.2f}</span>
                    </div>
                    <div class="summary-row">
                        <span class="summary-label">שעות 125%</span>
                        <span class="summary-value">{sum_125:.2f}</span>
                    </div>
                    <div class="summary-row">
                        <span class="summary-label">שעות 150%</span>
                        <span class="summary-value">{sum_150:.2f}</span>
                    </div>
                    <div class="summary-row">
                        <span class="summary-label">שבת</span>
                        <span class="summary-value">{sum_shabbat:.2f}</span>
                    </div>
                    {payment_html}
                </div>
            </div>
            """
        else:
            # סוג B: כמו במקור - סיכום למעלה, בלי שורת סיכום בטבלה, בלי חלוקה ל-100/125/150
            title_html = "דוח שעות עבודה"
            footer_html = ""
            top_html = f"""
            <div class="employee">שם העובד: ____________________</div>
            <div class="cards">
                <div class="card"><div class="card-label">לתשלום</div><div class="card-value">₪ {payment:,.2f}</div></div>
                <div class="card"><div class="card-label">מחיר לשעה</div><div class="card-value">₪ {rate:,.2f}</div></div>
                <div class="card"><div class="card-label">שעות חודשיות</div><div class="card-value">{sum_total:.2f}</div></div>
                <div class="card"><div class="card-label">ימי עבודה</div><div class="card-value">{work_days}</div></div>
            </div>
            """
            bottom_html = '<p class="note">נתוני הסיכום הועתקו מהמסמך המקורי.</p>'

        # שמירת הסיכום בתוך result, כדי שטסטים יוכלו לבדוק אותו
        result.summary_data.update({
            "calculated_total_hours": sum_total,
            "calculated_payment": payment,
            "work_days": work_days,
        })

        company_html = "" if is_type_b else f'<div class="company-name">{company_name}</div>'
        month_html = f'<div class="report-month">{report_month}</div>' if report_month else ""

        html_content = f"""
        <!DOCTYPE html>
        <html lang="he" dir="rtl">
        <head>
            <meta charset="UTF-8">
            <title>דוח שעות עבודה</title>
            <style>
                body {{
                    font-family: 'David', 'Arial', sans-serif;
                    direction: rtl;
                    color: #111827;
                    margin: 40px;
                    background-color: #ffffff;
                }}
                .header-container {{
                    display: flex;
                    justify-content: space-between;
                    align-items: flex-start;
                    margin-bottom: 10px;
                }}
                .report-title {{
                    font-size: 28px;
                    font-weight: bold;
                    color: #111827;
                    margin: 0;
                    text-align: right;
                }}
                .report-month {{
                    font-size: 18px;
                    color: #374151;
                    margin-top: 5px;
                    text-align: right;
                }}
                .company-name {{
                    font-size: 14px;
                    color: #4b5563;
                    margin-top: 5px;
                    text-align: right;
                }}
                .header-right {{
                    text-align: right;
                    width: 100%;
                }}
                .employee {{
                    font-size: 15px;
                    margin: 10px 0 15px 0;
                    text-align: right;
                }}
                .cards {{
                    display: flex;
                    gap: 12px;
                    margin-bottom: 20px;
                }}
                .card {{
                    flex: 1;
                    border: 1px solid #e5e7eb;
                    padding: 10px;
                    text-align: center;
                }}
                .card-label {{
                    font-size: 13px;
                    color: #4b5563;
                }}
                .card-value {{
                    font-size: 18px;
                    font-weight: bold;
                    color: #111827;
                    margin-top: 4px;
                }}
                .note {{
                    font-size: 12px;
                    color: #6b7280;
                    margin-top: 20px;
                    text-align: right;
                }}
                .divider {{
                    border: none;
                    border-top: 1px solid #d1d5db;
                    margin: 15px 0 25px 0;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 10px;
                }}
                th, td {{
                    border: 1px solid #e5e7eb;
                    padding: 8px 10px;
                    text-align: center;
                    font-size: 13px;
                }}
                th {{
                    background-color: #16325c;
                    color: #ffffff;
                    font-weight: bold;
                }}
                tr:nth-child(even) {{
                    background-color: #f9fafb;
                }}
                .footer-row {{
                    background-color: #e2e8f0;
                    font-weight: bold;
                }}
                .summary-section {{
                    margin-top: 40px;
                    width: 320px;
                    float: left;
                    border: 1px solid #e5e7eb;
                    padding: 15px;
                    background-color: #ffffff;
                }}
                .summary-title {{
                    font-size: 16px;
                    font-weight: bold;
                    color: #111827;
                    margin-bottom: 10px;
                    border-bottom: 1px solid #e5e7eb;
                    padding-bottom: 5px;
                    text-align: right;
                }}
                .summary-row {{
                    display: flex;
                    justify-content: space-between;
                    padding: 4px 0;
                    font-size: 14px;
                }}
                .summary-label {{
                    color: #4b5563;
                }}
                .summary-value {{
                    font-weight: bold;
                    color: #111827;
                }}
                .clearfix::after {{
                    content: "";
                    clear: both;
                    display: table;
                }}
            </style>
        </head>
        <body>
            <div class="header-container">
                <div class="header-right">
                    <div class="report-title">{title_html}</div>
                    {month_html}
                    {company_html}
                </div>
            </div>

            <hr class="divider">

            {top_html}

            <table>
                <thead>
                    {headers_html}
                </thead>
                <tbody>
                    {rows_html}
                    {footer_html}
                </tbody>
            </table>

            {bottom_html}
        </body>
        </html>
        """

        output_html_path = output_pdf_path.replace(".pdf", ".html")
        with open(output_html_path, "w", encoding="utf-8-sig") as f:
            f.write(html_content)
        return output_html_path