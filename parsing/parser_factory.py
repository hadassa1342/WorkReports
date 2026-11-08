"""המקום היחיד בפרויקט שמכיר את מחלקות הפרסרים. סוג חדש = שורה חדשה במילון."""
from domain.exceptions import UnknownReportTypeError
from domain.models import ReportType
from parsing.base_parser import BaseParser
from parsing.type_a_parser import TypeAParser
from parsing.type_b_parser import TypeBParser

_PARSERS: dict[ReportType, type[BaseParser]] = {
    ReportType.TYPE_A: TypeAParser,
    ReportType.TYPE_B: TypeBParser,
}


def get_parser(report_type: ReportType) -> BaseParser:
    if report_type not in _PARSERS:
        raise UnknownReportTypeError(f"No parser registered for {report_type}")
    return _PARSERS[report_type]()
