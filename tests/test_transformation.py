from dataclasses import FrozenInstanceError, replace
from datetime import date, time

import pytest

from config.rules import RULES
from domain.exceptions import TransformationError
from domain.models import AttendanceReport, AttendanceRow, ReportSummary, ReportType
from domain.time_math import hours_between, to_minutes
from parsing.classifier import classify
from parsing.ocr import pages_to_text
from parsing.parser_factory import get_parser
from parsing.type_a_parser import TypeAParser
from parsing.type_b_parser import TypeBParser
from tests.conftest import load_fixture, real_fixtures
from tests.sample_pages import type_a_page, type_b_page
from transformation.base_strategy import BaseTransformationStrategy
from transformation.service import TransformationService
from transformation.type_a_strategy import TypeATransformationStrategy
from transformation.type_b_strategy import TypeBTransformationStrategy
from transformation.validation import validate_row

SERVICE = TransformationService(
    strategies={ReportType.TYPE_A: TypeATransformationStrategy(),
                ReportType.TYPE_B: TypeBTransformationStrategy()},
    rules=RULES,
)


def report_a():
    return TypeAParser().parse([type_a_page()])


def report_b():
    return TypeBParser().parse([type_b_page()])


# ---------- דרישות מפורשות ----------
@pytest.mark.parametrize("make", [report_a, report_b])
def test_same_input_gives_same_output(make):
    assert SERVICE.transform(make()) == SERVICE.transform(make())


@pytest.mark.parametrize("make", [report_a, report_b])
def test_another_seed_gives_another_variation(make):
    assert SERVICE.transform(make(), seed=1).rows != SERVICE.transform(make(), seed=2).rows


@pytest.mark.parametrize("make", [report_a, report_b])
def test_hours_are_actually_changed(make):
    original, new = make(), SERVICE.transform(make())
    changed = [o for o, n in zip(original.rows, new.rows) if o.is_work_day and o.entry_time != n.entry_time]
    assert changed


@pytest.mark.parametrize("make", [report_a, report_b])
def test_original_report_is_not_changed(make):
    report = make()
    before = report.rows
    SERVICE.transform(report)
    assert report.rows == before
    with pytest.raises(FrozenInstanceError):
        report.rows[0].entry_time = time(6, 0)


# ---------- האינווריאנטים מדף העבודה ----------
@pytest.mark.parametrize("make", [report_a, report_b])
@pytest.mark.parametrize("seed", range(20))
def test_invariants(make, seed):
    original = make()
    new = SERVICE.transform(original, seed)
    rules = RULES[new.report_type]
    for o, row in zip(original.rows, new.rows):
        assert (row.work_date, row.day_name) == (o.work_date, o.day_name)       # תאריך ויום לא משתנים
        if not row.is_work_day:
            assert row == o                                                     # שבת/חג נשארים כמו שהם
            continue
        assert row.exit_time > row.entry_time                                   # יציאה אחרי כניסה
        assert rules.work_start <= row.entry_time and row.exit_time <= rules.work_end
        assert row.total_hours == hours_between(row.entry_time, row.exit_time, row.break_minutes or 0)
        assert abs(to_minutes(row.entry_time) - to_minutes(o.entry_time)) <= rules.entry_shift_minutes
        if row.hours_100 is not None:                                           # החלוקה מסתכמת לסה"כ
            parts = row.hours_100 + row.hours_125 + row.hours_150 + row.shabbat_hours
            assert abs(parts - row.total_hours) < 0.011
    s = new.summary                                                             # הסיכום = סכום השורות
    assert abs(s.total_hours - sum(r.total_hours for r in new.rows)) < 0.011
    assert s.total_days == sum(r.is_work_day for r in new.rows)
    if s.hourly_rate is not None:
        assert s.total_pay == round(s.total_hours * s.hourly_rate, 2)
    assert len({(r.work_date.year, r.work_date.month) for r in new.rows}) == 1  # אותו חודש


def test_summary_is_recomputed_after_the_change():
    original, new = report_a(), SERVICE.transform(report_a())
    assert new.summary.total_hours != original.summary.total_hours or new.summary.total_pay == original.summary.total_pay
    assert new.summary.total_pay == round(new.summary.total_hours * 40.0, 2)


def _shabbat_row_b():
    return AttendanceRow(date(2023, 2, 4), "יום שבת", time(8, 0), time(14, 0), 5.5, location="גונן",
                         break_minutes=30, hours_100=0, hours_125=0, hours_150=0, shabbat_hours=5.5)


def test_type_b_no_work_on_shabbat_row_is_removed():
    """בסוג B מופיעים רק ימי עבודה, ולכן שבת שבה לא עובדים לא מופיעה, והסיכום מחושב בלעדיה."""
    sunday = AttendanceRow(date(2023, 2, 5), "יום ראשון", time(8, 0), time(16, 0), 7.5, location="גונן",
                           break_minutes=30, hours_100=7.5, hours_125=0, hours_150=0, shabbat_hours=0)
    report = AttendanceReport(ReportType.TYPE_B, (_shabbat_row_b(), sunday), ReportSummary(2, 13.0))
    new = SERVICE.transform(report)
    assert [r.work_date for r in new.rows] == [date(2023, 2, 5)]
    assert new.summary.total_days == 1 and new.summary.shabbat_hours == 0


def test_type_a_no_work_on_shabbat_row_stays_empty():
    """בסוג A יש שורה לכל יום, ולכן שורת השבת נשארת - בלי שעות."""
    row = AttendanceRow(date(2022, 9, 3), "שבת", time(8, 30), time(12, 0), 3.5)
    report = AttendanceReport(ReportType.TYPE_A, (row,), ReportSummary(1, 3.5, hourly_rate=30.0))
    new = SERVICE.transform(report)
    assert len(new.rows) == 1 and not new.rows[0].is_work_day
    assert (new.summary.total_days, new.summary.total_hours, new.summary.total_pay) == (0, 0, 0)


def test_shabbat_hours_go_to_the_shabbat_column_when_allowed():
    """אם משנים את הכלל ל-work_on_shabbat=True, השעות של שבת נכנסות לעמודת שבת."""
    rules = {t: replace(r, work_on_shabbat=True) for t, r in RULES.items()}
    service = TransformationService(SERVICE._strategies, rules)
    report = AttendanceReport(ReportType.TYPE_B, (_shabbat_row_b(),), ReportSummary(1, 5.5))
    new = service.transform(report).rows[0]
    assert (new.hours_100, new.hours_125, new.hours_150) == (0.0, 0.0, 0.0)
    assert new.shabbat_hours == new.total_hours


@real_fixtures
def test_real_sample_has_no_work_on_shabbat(fixture_path):
    pages = load_fixture(fixture_path)
    new = SERVICE.transform(get_parser(classify(pages_to_text(pages))).parse(pages))
    assert not [r for r in new.rows if r.is_work_day and r.work_date.weekday() == 5]


# ---------- מקרי קצה ----------
@pytest.mark.parametrize("entry,exit_", [(time(6, 30), time(19, 30)), (time(6, 0), time(20, 0)), (time(18, 0), time(18, 40))])
def test_original_outside_working_hours_does_not_crash(entry, exit_):
    row = AttendanceRow(date(2022, 9, 4), "ראשון", entry, exit_, hours_between(entry, exit_))
    report = AttendanceReport(ReportType.TYPE_A, (row,), ReportSummary(1, row.total_hours, hourly_rate=40.0))
    new = SERVICE.transform(report).rows[0]
    assert time(7, 0) <= new.entry_time < new.exit_time <= time(19, 0)


def test_validation_rejects_exit_before_entry():
    row = AttendanceRow(date(2022, 9, 4), "ראשון", time(16, 0), time(8, 0), 8.0)
    with pytest.raises(TransformationError):
        validate_row(row, RULES[ReportType.TYPE_A])


def test_validation_rejects_wrong_split():
    row = AttendanceRow(date(2023, 2, 1), "יום רביעי", time(8, 1), time(16, 31), 8.0, break_minutes=30,
                        hours_100=8.0, hours_125=1.0, hours_150=0.0, shabbat_hours=0.0)
    with pytest.raises(TransformationError):
        validate_row(row, RULES[ReportType.TYPE_B])


def test_service_uses_the_strategy_it_was_given():
    """האסטרטגיות מגיעות מבחוץ, ולכן אפשר להעביר אסטרטגיה מזויפת ולבדוק רק את הלולאה."""
    class KeepEverything(BaseTransformationStrategy):
        calls = 0

        def transform_row(self, row, rules, rng):
            KeepEverything.calls += 1
            return row

        def build_summary(self, rows, original):
            return original

    service = TransformationService({ReportType.TYPE_A: KeepEverything()}, RULES)
    report = report_a()
    assert service.transform(report) == report
    assert KeepEverything.calls == len(report.rows)


@real_fixtures
def test_real_sample_transforms_within_the_rules(fixture_path):
    pages = load_fixture(fixture_path)
    report = get_parser(classify(pages_to_text(pages))).parse(pages)
    assert SERVICE.transform(report) == SERVICE.transform(report)       # service validates every row
