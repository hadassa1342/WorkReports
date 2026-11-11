"""
השירות מחזיק מילון מסוג לאסטרטגיה, בוחר אחת פעם אחת, ומשם רק קורא לה. אין כאן if על הסוג.
האסטרטגיות והכללים מגיעים מבחוץ (מ-main), ולכן בטסט אפשר להעביר אחרים.
"""
import random
from dataclasses import replace

from config.rules import TransformRules
from domain.models import AttendanceReport, ReportType
from transformation.base_strategy import BaseTransformationStrategy
from transformation.validation import (validate_no_shabbat_work, validate_row, validate_same_dates,
                                       validate_summary)


class TransformationService:
    def __init__(self, strategies: dict[ReportType, BaseTransformationStrategy],
                 rules: dict[ReportType, TransformRules]):
        self._strategies = strategies
        self._rules = rules

    def transform(self, report: AttendanceReport, seed: int = 0) -> AttendanceReport:
        """
        מחזיר דו"ח חדש. המקורי לא משתנה (frozen + replace).
        לכל שורה מחולל מספרים משלו, עם seed שנגזר מהתאריך: אותו קלט נותן תמיד אותו פלט,
        ושורה אחת לא משפיעה על אחרת. seed אחר (מה-CLI) נותן וריאציה אחרת.
        """
        strategy = self._strategies[report.report_type]          # בוחרים פעם אחת
        rules = self._rules[report.report_type]
        new_rows = []
        for row in report.rows:
            rng = random.Random(seed * 1_000_000 + row.work_date.toordinal())
            new_row = strategy.transform_row(row, rules, rng)
            if new_row is None:                                   # שורה שלא מופיעה בווריאציה
                continue
            validate_row(new_row, rules)
            new_rows.append(new_row)
        new_report = replace(report, rows=tuple(new_rows),
                             summary=strategy.build_summary(new_rows, report.summary))
        validate_summary(new_report)
        validate_same_dates(report, new_report)
        validate_no_shabbat_work(new_report, rules)
        return new_report
