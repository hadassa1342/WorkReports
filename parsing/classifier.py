"""
תחנה 2: Classifier. מקבל את הטקסט מה-OCR ומחזיר את סוג הדו"ח. לא קורא שורות.

שני סוגי ראיות, וכל ראיה שווה ניקוד:
  1. מילות מפתח בעברית. ה-OCR העברי בדו"ח הפשוט חלש ('לחודט' במקום 'לחודש'), ולכן מקבלים גם
     מילה דומה מאוד (difflib), וגם מילה הפוכה (בשכבת טקסט של PDF עברית מגיעה לפעמים הפוכה).
  2. מבנה המספרים, שנקראים טוב גם כשהעברית לא: בדו"ח המפורט התאריכים עם שנה מלאה (02/10/2022)
     ויש עמודות אחוזים; בדו"ח הפשוט השנה מקוצרת (1/9/22).
בלי מספיק ראיות, או בתיקו, נזרקת שגיאה במקום לנחש.
"""
import difflib
import re

from domain.exceptions import UnknownReportTypeError
from domain.models import ReportType

_WORDS: dict[ReportType, dict[str, int]] = {
    ReportType.TYPE_A: {"לתשלום": 3, "חודשיות": 2, "הערות": 2, "בשבוע": 1, "מחיר": 1},
    ReportType.TYPE_B: {"הפסקה": 3, "מקום": 2, "בונוס": 1, "נסיעות": 1},
}
# (ביטוי, כמה פעמים לפחות, ניקוד)
_PATTERNS: dict[ReportType, list[tuple[str, int, int]]] = {
    ReportType.TYPE_A: [(r"(?<![\d/])\d{1,2}/\d{1,2}/\d{2}(?!\d)", 5, 3)],          # 1/9/22
    ReportType.TYPE_B: [(r"(?<![\d/])\d{1,2}/\d{1,2}/\d{4}(?!\d)", 5, 3),           # 02/10/2022
                        (r"\d%", 2, 3)],                                            # 100% 125% 150%
}
MIN_SCORE = 3
_SIMILARITY = 0.8


def _has_word(word: str, tokens: set[str]) -> bool:
    for candidate in (word, word[::-1]):
        if candidate in tokens or difflib.get_close_matches(candidate, tokens, n=1, cutoff=_SIMILARITY):
            return True
    return False


def score(raw_text: str) -> dict[ReportType, int]:
    tokens = set(raw_text.split())
    scores = {}
    for report_type in ReportType:
        points = sum(p for word, p in _WORDS[report_type].items() if _has_word(word, tokens))
        points += sum(p for pattern, minimum, p in _PATTERNS[report_type]
                      if len(re.findall(pattern, raw_text)) >= minimum)
        scores[report_type] = points
    return scores


def classify(raw_text: str) -> ReportType:
    scores = score(raw_text)
    ranked = sorted(scores.values(), reverse=True)
    best = max(scores, key=scores.get)
    readable = {t.value: s for t, s in scores.items()}
    if scores[best] < MIN_SCORE:
        raise UnknownReportTypeError(f"Not enough evidence to classify the report: {readable}")
    if len(ranked) > 1 and ranked[0] == ranked[1]:
        raise UnknownReportTypeError(f"Tie between report types: {readable}")
    return best
