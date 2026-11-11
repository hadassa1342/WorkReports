import logging
from datetime import date, time

import pytest

from domain.exceptions import ParseError
from domain.models import AttendanceReport, ReportType
from parsing.classifier import classify
from parsing.ocr import pages_to_text
from parsing.parser_factory import get_parser
from parsing.type_a_parser import TypeAParser
from parsing.type_b_parser import TypeBParser
from tests.conftest import load_fixture, real_fixtures
from tests.sample_pages import type_a_page, type_b_page, w


# ---------- סוג A ----------
def test_type_a_reads_every_row():
    report = TypeAParser().parse([type_a_page()])
    assert isinstance(report, AttendanceReport)
    assert report.report_type == ReportType.TYPE_A
    assert len(report.rows) == 5


def test_type_a_first_row():
    row = TypeAParser().parse([type_a_page()]).rows[0]
    assert row.work_date == date(2022, 9, 1)
    assert row.day_name == "חמישי"
    assert (row.entry_time, row.exit_time) == (time(8, 10), time(16, 40))
    assert row.total_hours == 8.5
    assert row.location is None and row.break_minutes is None      # שדות של סוג B נשארים ריקים


def test_type_a_holiday_and_shabbat_rows_have_no_hours():
    rows = TypeAParser().parse([type_a_page()]).rows
    assert rows[1].note == "ערב חג" and not rows[1].is_work_day
    assert not rows[2].is_work_day and rows[2].total_hours == 0


def test_type_a_summary_from_header():
    s = TypeAParser().parse([type_a_page()]).summary
    assert (s.hourly_rate, s.total_pay, s.total_days, s.total_hours) == (40.0, 890.0, 3, 22.25)
    assert s.month_label == "ספטמבר 2022"


def test_type_a_keeps_original_date_style():
    assert TypeAParser().parse([type_a_page()]).date_style == "dd/mm/yy"


# ---------- סוג B ----------
def test_type_b_reads_times_by_column_not_by_size():
    """ההפסקה (00:30) היא השעה הקטנה ביותר בשורה, ובכל זאת לא נהיית שעת הכניסה."""
    row = TypeBParser().parse([type_b_page()]).rows[0]
    assert (row.entry_time, row.exit_time, row.break_minutes) == (time(8, 0), time(16, 30), 30)
    assert row.total_hours == 8.0


def test_type_b_overtime_split():
    row = TypeBParser().parse([type_b_page()]).rows[1]
    assert (row.hours_100, row.hours_125, row.hours_150) == (8.0, 2.0, 0.0)


def test_type_b_location_day_and_company():
    report = TypeBParser().parse([type_b_page()])
    assert report.rows[0].location == "גונן"
    assert report.rows[0].day_name == "יום רביעי"
    assert report.summary.company_name == 'ג.ע. הכשר כח אדם בע"מ'


def test_type_b_summary_is_the_sum_of_rows():
    s = TypeBParser().parse([type_b_page()]).summary
    assert (s.total_days, s.total_hours, s.hours_125, s.total_break_minutes) == (3, 26.08, 2.08, 90)


# ---------- משותף ----------
def test_unreadable_row_is_reported_not_turned_into_zero(caplog):
    page = type_a_page() + [w("06/09/22", 520, 200), w("שלישי", 460, 200), w("8:00", 380, 200)]
    with caplog.at_level(logging.WARNING):
        rows = TypeAParser().parse([page]).rows
    assert not rows[-1].is_work_day
    assert "2022-09-06" in caplog.text


def test_two_pages_are_both_read():
    second = [dict(x, top=x["top"], bottom=x["bottom"]) for x in type_a_page()]
    for x in second:                                   # אותו עמוד, עם תאריכים של השבוע הבא
        if x["text"].endswith("/09/22"):
            x["text"] = f"{int(x['text'][:2]) + 7:02d}/09/22"
    rows = TypeAParser().parse([type_a_page(), second]).rows
    assert len(rows) >= 10


def test_page_without_rows_raises():
    with pytest.raises(ParseError):
        TypeAParser().parse([[w("שלום", 100, 100)]])


def test_factory_returns_the_right_parser():
    assert isinstance(get_parser(ReportType.TYPE_A), TypeAParser)
    assert isinstance(get_parser(ReportType.TYPE_B), TypeBParser)


# ---------- על פלט OCR אמיתי: המספרים כמו שהם מודפסים בקבצי הדוגמה ----------
EXPECTED = {
    # קובץ: (סוג, ימי עבודה, סה"כ שעות, מחיר לשעה, לתשלום, 100%, 150%, שבת)
    "n_r_5_n.json": (ReportType.TYPE_A, 24, 84.00, 30.65, 2574.60, None, None, None),
    "n_r_10_n.json": (ReportType.TYPE_A, 21, 63.02, 32.35, 2038.59, None, None, None),
    "a_r_9.json": (ReportType.TYPE_B, 22, 143.00, None, None, 117.0, 6.5, 19.5),
    "a_r_25.json": (ReportType.TYPE_B, 15, 110.50, None, None, 110.5, 0.0, 0.0),
}


@real_fixtures
def test_real_sample_matches_the_printed_totals(fixture_path):
    if fixture_path.name not in EXPECTED:
        pytest.skip("no expected values for this file")
    report_type, days, hours, rate, pay, h100, h150, shabbat = EXPECTED[fixture_path.name]
    pages = load_fixture(fixture_path)
    report = get_parser(classify(pages_to_text(pages))).parse(pages)
    s = report.summary
    assert report.report_type == report_type
    assert s.total_days == days
    assert abs(s.total_hours - hours) <= 0.02          # הכותרת מעגלת מדקות, השורות מעוגלות כל אחת
    assert (s.hourly_rate, s.total_pay) == (rate, pay)
    if h100 is not None:
        assert (s.hours_100, s.hours_150, s.shabbat_hours) == (h100, h150, shabbat)
    assert len({(r.work_date.year, r.work_date.month) for r in report.rows if r.work_date.day > 1}) == 1


# ---------- שגיאות OCR אמיתיות שתוקנו ----------
def test_ocr_letters_in_dates_are_fixed():
    from parsing.text_tools import clean_token
    assert clean_token("os/o9/22") == "05/09/22"
    assert clean_token("o1fog/22") == "01/09/22"
    assert clean_token("[8:30") == "8:30"
    assert clean_token("גונן") == "גונן"            # מילה רגילה לא נוגעים


def test_misread_date_on_the_same_line_does_not_steal_the_row():
    """'21/09/22' נקרא במעבר אחד כ-'2/09/22'. השורה שייכת ל-21, לא ל-2 (יום שישי)."""
    page = type_a_page()
    for i, day in enumerate((6, 7, 8)):
        y = 200 + 20 * i
        page += [w(f"{day:02d}/09/22", 520, y), w("8:01", 380, y), w("16:01", 300, y)]
    page += [w("2/09/22", 520, 241)]                # קריאה שגויה של 08/09/22, באותו גובה
    rows = TypeAParser().parse([page]).rows
    assert rows[1].work_date == date(2022, 9, 2) and not rows[1].is_work_day
    assert rows[-1].work_date == date(2022, 9, 8) and rows[-1].is_work_day


@pytest.mark.parametrize("name", ["n_r_5_n.json", "n_r_10_n.json"])
@pytest.mark.parametrize("shift", [1, -1])
def test_dates_misread_by_one_day_do_not_move_hours_to_shabbat(name, shift):
    """
    ב-OCR של מחשב אחר כל התאריכים יכולים להיקרא יום אחד הצידה. בלי בדיקה, השעות של יום שישי
    היו נרשמות על שבת. התוצאה חייבת להיות זהה לקריאה הנכונה.
    """
    import copy
    from datetime import timedelta
    from parsing.text_tools import DATE_RE, clean_token, parse_date
    from tests.conftest import FIXTURES_DIR

    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip("fixture not saved yet")
    pages = load_fixture(path)
    shifted = copy.deepcopy(pages)
    for word in shifted[0]:
        text = clean_token(word["text"])
        if DATE_RE.match(text) and parse_date(text):
            d = parse_date(text) + timedelta(days=shift)
            word["text"] = f"{d.day}/{d.month}/{d.year % 100}"

    expected = TypeAParser().parse(pages).rows
    rows = TypeAParser().parse(shifted).rows
    assert rows == expected
    assert not [r for r in rows if r.work_date.weekday() == 5 and r.is_work_day]
