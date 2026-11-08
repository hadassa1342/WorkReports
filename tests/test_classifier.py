import pytest

from domain.exceptions import UnknownReportTypeError
from domain.models import ReportType
from parsing.classifier import classify
from parsing.ocr import pages_to_text
from tests.conftest import expected_type, load_fixture, real_fixtures
from tests.sample_pages import type_a_page, type_b_page


def test_simple_report_is_type_a():
    assert classify(pages_to_text([type_a_page()])) == ReportType.TYPE_A


def test_detailed_report_is_type_b():
    assert classify(pages_to_text([type_b_page()])) == ReportType.TYPE_B


def test_one_garbled_word_is_not_enough_to_fail():
    text = "תאריך יום מקום כניסה יציאה הפסקה 125%"     # "150%" ו-"100%" שובשו, עדיין מספיק
    assert classify(text) == ReportType.TYPE_B


def test_reversed_hebrew_from_pdf_text_layer():
    assert classify("םולשתל תויִשדוח") == ReportType.TYPE_A


def test_not_an_attendance_report_raises():
    with pytest.raises(UnknownReportTypeError):
        classify("invoice number 12345 total 99.00")


def test_tie_raises():
    with pytest.raises(UnknownReportTypeError):
        classify("לתשלום הפסקה")


@real_fixtures
def test_every_sample_file_is_classified_correctly(fixture_path):
    assert classify(pages_to_text(load_fixture(fixture_path))) == expected_type(fixture_path)
