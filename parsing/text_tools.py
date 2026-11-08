"""
כלים משותפים לשני הפרסרים: ניקוי מילים מה-OCR, קיבוץ לשורות, ומציאת תאריך, שעה, יום ומספר.
כל מה שכאן נכתב פעם אחת ומשמש את שני הסוגים.
"""
import difflib
import re
from collections import Counter
from datetime import date, datetime, time

DAY_NAMES = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]   # לפי date.weekday()
MONTH_NAMES = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
               "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
REVERSED_DAYS = {d[::-1] for d in DAY_NAMES}   # בשכבת טקסט של PDF עברית מגיעה לפעמים הפוכה

DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
DECIMAL_RE = re.compile(r"^\d+\.\d{1,2}$")
NUM_RE = re.compile(r"^[\d,]+(\.\d+)?$")

# ---------- ניקוי ----------
# תווי כיווניות בלתי נראים שמגיעים משכבת הטקסט של PDF ומפרקים השוואות ('\u200f8:30' != '8:30')
_BIDI_MARKS = dict.fromkeys(map(ord, "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"))
# קווי טבלה וסימנים שה-OCR מדביק לקצה של מילה: '[8:30' -> '8:30', '|16:45' -> '16:45'
_EDGE_JUNK = re.compile(r"^[\[\](){}|,;'\"“”‘’`´]+|[\[\](){}|,;'\"“”‘’`´]+$")


# אותיות שה-OCR קורא במקום ספרות בתאריכים: 'os/o9/22' -> '05/09/22', 'o1fog/22' -> '01/09/22'
_DATE_LOOKALIKES = str.maketrans({"o": "0", "O": "0", "Q": "0", "g": "9", "s": "5", "S": "5",
                                  "l": "1", "I": "1", "|": "1", "f": "/"})
_DATE_LIKE = re.compile(r"^[\doOQgsSlI|f]{1,2}[/f][\doOQgsSlI|f]{1,2}[/f]\d{2,4}$")


def clean_token(text: str) -> str:
    text = _EDGE_JUNK.sub("", str(text).translate(_BIDI_MARKS).strip()).strip()
    return fix_date_token(text)


def fix_date_token(text: str) -> str:
    """מתקן אותיות-במקום-ספרות רק בטוקן שנראה כמו תאריך, ורק אם התוצאה היא תאריך תקין."""
    if DATE_RE.match(text) or not _DATE_LIKE.match(text):
        return text
    fixed = text.translate(_DATE_LOOKALIKES)
    return fixed if DATE_RE.match(fixed) and parse_date(fixed) else text


def has_hebrew(text: str) -> bool:
    return any("\u0590" <= c <= "\u05FF" for c in text)


def is_visual_order(tokens) -> bool:
    """True אם העברית בשורה הפוכה (שם יום הפוך מופיע בה)."""
    return any(t in REVERSED_DAYS for t in tokens)


def logical(text: str, visual: bool) -> str:
    return text[::-1] if visual else text


# ---------- תאריכים ----------
def parse_date(text) -> date | None:
    """'01/09/22' או '1/9/2022' -> date. None אם לא תקין."""
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(text).strip(), fmt).date()
        except ValueError:
            continue
    return None


def date_style(text: str) -> str:
    """איך התאריך כתוב במקור: '01/09/22' -> 'dd/mm/yy', '1/9/2022' -> 'd/m/yyyy'."""
    day, month, year = str(text).split("/")
    return "/".join(("dd" if len(day) == 2 else "d",
                     "mm" if len(month) == 2 else "m",
                     "yyyy" if len(year) == 4 else "yy"))


def month_label(dates) -> str:
    """החודש הנפוץ בין התאריכים, למשל 'ספטמבר 2022'."""
    months = Counter((d.year, d.month) for d in dates)
    if not months:
        return ""
    (year, month), _ = months.most_common(1)[0]
    return f"{MONTH_NAMES[month - 1]} {year}"


# ---------- מילים -> שורות ----------
def _clean_words(words) -> list[dict]:
    """מילים נקיות (עם מרכז אנכי cy). אותה מילה באותו מקום מכמה מעברי OCR מאוחדת,
    ו-n סופר בכמה מעברים היא נקראה - זה ה"קול" שלה בבחירה בין קריאות שונות."""
    cleaned = []
    for w in words:
        text = clean_token(w["text"])
        if not text or not any(c.isalnum() for c in text):    # קווי טבלה ('|') וכו'
            continue
        w = dict(w)
        w["text"] = text
        w["cy"] = (w["top"] + w.get("bottom", w["top"])) / 2
        w["n"] = 1
        cleaned.append(w)

    unique = []
    for w in cleaned:
        for u in unique:
            if u["text"] == w["text"] and abs(u["cy"] - w["cy"]) < 3 and abs(u["x0"] - w["x0"]) < 8:
                u["n"] += 1
                break
        else:
            unique.append(w)
    return unique


def _cluster(words) -> list[list[dict]]:
    """קיבוץ מילים לשורות לפי מרכז אנכי. כל שורה ממוינת מימין לשמאל."""
    if not words:
        return []
    heights = sorted(w.get("bottom", w["top"]) - w["top"] for w in words)
    tolerance = 0.6 * (heights[len(heights) // 2] or 8)
    words = sorted(words, key=lambda w: w["cy"])
    lines = [[words[0]]]
    for w in words[1:]:
        if w["cy"] - lines[-1][-1]["cy"] > tolerance:
            lines.append([w])
        else:
            lines[-1].append(w)
    return [sorted(line, key=lambda x: x["x0"], reverse=True) for line in lines]


def read_word_lines(words) -> list[list[dict]]:
    """שורות מהעמוד, מלמעלה למטה, ובכל שורה המילים מימין לשמאל."""
    return _cluster(_clean_words(words))


def read_table(words):
    """
    קורא עמוד של טבלת נוכחות. מחזיר (header_lines, rows):
      header_lines - שורות הכותרת שמעל הטבלה
      rows         - רשימה של (date_text, words): שורה לכל תאריך שנקרא

    כל שורה נקבעת לפי התאריך שבה: מילה שייכת לתאריך הקרוב אליה אנכית.
    זה עמיד לסריקה עקומה ולמילים שנקראו כמה פעמים בכמה מעברי OCR, שבהם קיבוץ
    לפי שורות עלול למזג שורות שכנות.
    """
    words = _clean_words(words)
    anchors = [w for w in words if DATE_RE.match(w["text"]) and parse_date(w["text"])]
    if not anchors:
        return _cluster(words), []

    anchors.sort(key=lambda w: w["cy"])
    # מרווח בין שורות, לפי תאריכים סמוכים (הפרש בימים), כך שכפילויות של אותה שורה לא מקטינות אותו
    per_day = []
    for a, b in zip(anchors, anchors[1:]):
        days = (parse_date(b["text"]) - parse_date(a["text"])).days
        dy = b["cy"] - a["cy"]
        if 1 <= days <= 3 and dy > 3:
            per_day.append(dy / days)
    per_day.sort()
    if per_day:
        spacing = per_day[len(per_day) // 2]
    else:
        diffs = sorted(b["cy"] - a["cy"] for a, b in zip(anchors, anchors[1:]) if b["cy"] - a["cy"] > 3)
        spacing = diffs[len(diffs) // 2] if diffs else 12.0

    # שני "תאריכים" קרובים מדי = אותה שורה שנקראה פעמיים בצורה שונה ('21/09/22' וגם '2/09/22').
    # משאירים את זה שמתאים לסדר התאריכים (אחרי השורה הקודמת), ובתיקו - את הנפוץ
    def preference(w, prev):
        fits = prev is None or parse_date(w["text"]) > parse_date(prev["text"])
        return fits, w["n"]

    merged = []
    for w in anchors:
        if merged and w["cy"] - merged[-1]["cy"] < 0.45 * spacing:
            prev = merged[-2] if len(merged) > 1 else None
            if preference(w, prev) > preference(merged[-1], prev):
                merged[-1] = w
        else:
            merged.append(w)
    anchors = merged

    groups = [[a] for a in anchors]
    header = []
    max_dist = 0.45 * spacing
    first_cy = anchors[0]["cy"]
    anchor_ids = {id(a) for a in anchors}
    for w in words:
        if id(w) in anchor_ids:
            continue
        i = min(range(len(anchors)), key=lambda k: abs(anchors[k]["cy"] - w["cy"]))
        if abs(anchors[i]["cy"] - w["cy"]) <= max_dist:
            groups[i].append(w)
        elif w["cy"] < first_cy - 0.5 * spacing:
            header.append(w)

    rows = [(a["text"], sorted(g, key=lambda x: x["x0"], reverse=True)) for a, g in zip(anchors, groups)]
    return _cluster(header), rows


# ---------- ערכים מתוך שורה ----------
def read_times(line, count: int) -> list[time]:
    """
    עד `count` שעות מהשורה, לפי סדר העמודות מימין לשמאל.

    1. בוחרים אילו שעות: ב-OCR מרובה-מעברים אותה שעה נקראת כמה פעמים, ולפעמים כשגיאה
       ('72:00', '8:50'). לכן לוקחים את הערכים שנקראו הכי הרבה פעמים, ומתעלמים משעות לא חוקיות.
    2. מסדרים אותן לפי המיקום שלהן בעמוד, לא לפי הגודל: הקטנה היא לא בהכרח הכניסה
       (בסוג B ההפסקה, 00:30, היא הקטנה ביותר).
    """
    votes = {}     # minutes -> [votes, sum of x-center * votes]
    for w in line:
        text = w["text"]
        if not TIME_RE.match(text):
            continue
        h, m = map(int, text.split(":"))
        if h > 23 or m > 59:
            continue
        n = w.get("n", 1)
        entry = votes.setdefault(h * 60 + m, [0, 0.0])
        entry[0] += n
        entry[1] += n * (w["x0"] + w.get("x1", w["x0"])) / 2
    chosen = sorted(votes.items(), key=lambda kv: (-kv[1][0], kv[0]))[:count]
    chosen.sort(key=lambda kv: kv[1][1] / kv[1][0], reverse=True)     # מימין לשמאל
    return [time(minutes // 60, minutes % 60) for minutes, _ in chosen]


def to_hours(token: str) -> float | None:
    """'6.50' -> 6.5, '6,50' -> 6.5, '650' (נקודה שאבדה ב-OCR) -> 6.5. אחרת None."""
    cleaned = re.sub(r"[^\d.,]", "", token)
    if re.fullmatch(r"\d+[.,]\d{1,2}", cleaned):
        return float(cleaned.replace(",", "."))
    if re.fullmatch(r"\d{3}", cleaned):
        return int(cleaned) / 100
    return None


def hebrew_words(tokens, visual: bool) -> list[str]:
    """המילים העבריות בשורה, בלי המילה 'יום' ובלי שם היום."""
    words = [logical(t, visual) for t in tokens if has_hebrew(t)]
    return [w for w in words if w != "יום" and w not in DAY_NAMES]


# ביטויי הערות מוכרים. ה-OCR יוצר רעש בעמודת ההערות, ולכן משאירים רק מה שמזהים.
_NOTE_VOCAB = sorted([
    "ערב ראש השנה", "ראש השנה", "ערב יום כיפור", "יום כיפור", "ערב סוכות", "סוכות",
    "חול המועד", "שמיני עצרת", "שמחת תורה", "ערב פסח", "פסח", "ערב שבועות", "שבועות",
    "פורים", "חנוכה", "תשעה באב", "ערב חג", "חג", "מחלה", "חופשה", "מילואים", "היעדרות",
], key=len, reverse=True)


def clean_note(text: str) -> str:
    """משאיר הערה רק אם היא מזוהה (בדיוק או בקירוב) כביטוי מוכר. אחרת - ריק."""
    text = " ".join(w for w in text.split() if len(w) >= 2)
    if not text:
        return ""
    for phrase in _NOTE_VOCAB:
        if phrase in text:
            return phrase
    close = difflib.get_close_matches(text, _NOTE_VOCAB, n=1, cutoff=0.75)
    return close[0] if close else ""
