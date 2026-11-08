"""
תחנה 2: Classifier. מקבל את הטקסט מה-OCR ומחזיר את סוג הדו"ח. לא קורא שורות.

לכל סוג כמה מילות מפתח, וכל אחת שווה ניקוד: אם ה-OCR שיבש מילה אחת, האחרות עדיין שם.
בלי מספיק ראיות, או בתיקו, נזרקת שגיאה במקום לנחש.
"""
from domain.exceptions import UnknownReportTypeError
from domain.models import ReportType

# מילה -> ניקוד. בודקים גם את המילה ההפוכה, כי בשכבת טקסט של PDF עברית מגיעה לפעמים הפוכה.
_EVIDENCE: dict[ReportType, dict[str, int]] = {
    ReportType.TYPE_A: {"לתשלום": 3, "חודשיות": 2, "הערות": 2, "מחיר": 1, "שעת": 1},
    ReportType.TYPE_B: {"הפסקה": 3, "125%": 3, "150%": 2, "מקום": 2, "100%": 1},
}
MIN_SCORE = 3


def score(raw_text: str) -> dict[ReportType, int]:
    return {
        report_type: sum(points for phrase, points in evidence.items()
                         if phrase in raw_text or phrase[::-1] in raw_text)
        for report_type, evidence in _EVIDENCE.items()
    }


def classify(raw_text: str) -> ReportType:
    scores = score(raw_text)
    ranked = sorted(scores.values(), reverse=True)
    best = max(scores, key=scores.get)
    if scores[best] < MIN_SCORE:
        raise UnknownReportTypeError(f"Not enough evidence to classify the report: "
                                     f"{ {t.value: s for t, s in scores.items()} }")
    if len(ranked) > 1 and ranked[0] == ranked[1]:
        raise UnknownReportTypeError(f"Tie between report types: { {t.value: s for t, s in scores.items()} }")
    return best
