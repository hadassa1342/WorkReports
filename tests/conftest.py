import json
from pathlib import Path

import pytest

from domain.models import ReportType

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_FILES = sorted(FIXTURES_DIR.glob("*.json"))

# לפי מה שהוסכם בכיתה: n_r_* = סוג A (הפשוט), a_r_* = סוג B (המפורט)
EXPECTED_TYPE = {"n_": ReportType.TYPE_A, "a_": ReportType.TYPE_B}


def expected_type(path: Path) -> ReportType:
    return next(t for prefix, t in EXPECTED_TYPE.items() if path.name.startswith(prefix))


def load_fixture(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# פרמטר לטסטים שרצים על פלט OCR אמיתי. אם עוד לא נשמרו fixtures - הטסט מדולג, עם הסבר.
real_fixtures = pytest.mark.parametrize(
    "fixture_path",
    FIXTURE_FILES or [pytest.param(None, marks=pytest.mark.skip(
        reason="no OCR fixtures yet: run  python -m tools.save_ocr_fixture"))],
    ids=lambda p: p.name if p else "no-fixtures",
)
