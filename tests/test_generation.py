import csv
import html as html_lib
from dataclasses import replace

from domain.models import ReportType
from generation.csv_renderer import CsvRenderer
from generation.formatting import format_date, format_time
from generation.html_renderer import HtmlRenderer
from generation.layouts import LAYOUTS
from parsing.type_a_parser import TypeAParser
from parsing.type_b_parser import TypeBParser
from tests.sample_pages import type_a_page, type_b_page
from datetime import date, time


def test_html_is_right_to_left_with_the_layout_columns(tmp_path):
    report = TypeBParser().parse([type_b_page()])
    html = HtmlRenderer().render(report, tmp_path / "out.html").read_text(encoding="utf-8")
    assert 'dir="rtl"' in html
    for column in LAYOUTS[ReportType.TYPE_B].columns:
        assert f"<th>{html_lib.escape(column.title)}</th>" in html


def test_generator_shows_the_summary_and_does_not_recompute_it(tmp_path):
    report = TypeAParser().parse([type_a_page()])
    report = replace(report, summary=replace(report.summary, total_hours=123.45))
    html = HtmlRenderer().render(report, tmp_path / "out.html").read_text(encoding="utf-8")
    assert "123.45" in html


def test_csv_has_the_layout_header(tmp_path):
    report = TypeAParser().parse([type_a_page()])
    path = CsvRenderer().render(report, tmp_path / "out.csv")
    with open(path, encoding="utf-8-sig") as f:
        header = next(csv.reader(f))
    assert header == [c.title for c in LAYOUTS[ReportType.TYPE_A].columns]


def test_dates_and_times_look_like_the_original():
    assert format_date(date(2022, 9, 1), "dd/mm/yy") == "01/09/22"
    assert format_date(date(2022, 9, 1), "d/m/yyyy") == "1/9/2022"
    assert format_time(time(8, 5), "h:mm") == "8:05"
    assert format_time(time(8, 5), "hh:mm") == "08:05"


def test_empty_cells_for_shabbat(tmp_path):
    report = TypeAParser().parse([type_a_page()])
    path = CsvRenderer().render(report, tmp_path / "out.csv")
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert rows[3][2:5] == ["", "", ""]          # 03/09/22, שבת
