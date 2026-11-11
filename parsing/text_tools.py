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


def date_style(texts) -> str:
    """
    איך התאריכים כתובים במקור: '01/09/22' -> 'dd/mm/yy', '1/9/2022' -> 'd/m/yyyy'.
    מקבל כמה תאריכים ומצביע: אפס מוביל אפשר לראות רק ביום או בחודש קטנים מ-10.
    """
    day_pad = month_pad = 0
    long_year = 0
    for text in texts:
        day, month, year = str(text).split("/")
        if int(day) < 10:
            day_pad += 1 if len(day) == 2 else -1
        if int(month) < 10:
            month_pad += 1 if len(month) == 2 else -1
        long_year += 1 if len(year) == 4 else -1
    return "/".join(("dd" if day_pad > 0 else "d", "mm" if month_pad > 0 else "m",
                     "yyyy" if long_year > 0 else "yy"))


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


def find_anchors(words):
    """
    מוצא את "עוגני" הטבלה: התאריכים שבעמודת התאריך, כל אחד עם הגובה שלו בעמוד.
    מחזיר (words, anchors, spacing):
      words   - המילים הנקיות של העמוד
      anchors - תאריך שנקרא לכל שורה, ממוין מלמעלה למטה (w["date"] הוא date)
      spacing - המרווח האנכי בין שתי שורות סמוכות בטבלה
    """
    words = _clean_words(words)
    anchors = []
    for w in words:
        d = parse_date(w["text"]) if DATE_RE.match(w["text"]) else None
        if d:
            anchors.append(dict(w, date=d))
    if not anchors:
        return words, [], 12.0
    anchors = _fix_month_misreads(anchors)
    anchors.sort(key=lambda w: w["cy"])

    # מרווח בין שורות, לפי תאריכים סמוכים (הפרש בימים), כך שכפילויות של אותה שורה לא מקטינות אותו
    per_day = []
    for a, b in zip(anchors, anchors[1:]):
        days = (b["date"] - a["date"]).days
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
        fits = prev is None or w["date"] > prev["date"]
        return fits, w["n"]

    merged = []
    for w in anchors:
        if merged and w["cy"] - merged[-1]["cy"] < 0.45 * spacing:
            prev = merged[-2] if len(merged) > 1 else None
            if preference(w, prev) > preference(merged[-1], prev):
                merged[-1] = w
        else:
            merged.append(w)
    return words, merged, spacing


def dominant_month(anchors) -> tuple[int, int] | None:
    votes = Counter()
    for a in anchors:
        votes[(a["date"].year, a["date"].month)] += a.get("n", 1)
    return votes.most_common(1)[0][0] if votes else None


def _fix_month_misreads(anchors):
    """
    ה-OCR קורא 1 כ-4 או כ-7: '1/1/23' נקרא '1/4/23', ושורה של ינואר "קופצת" לאפריל.
    תאריך מחודש רחוק (לא החודש הנפוץ ולא חודש סמוך לו) מקבל את החודש הנפוץ, עם אותו יום.
    חודש סמוך נשאר (טבלה של ספטמבר יכולה להסתיים ב-1/10).
    """
    year, month = dominant_month(anchors)
    base = year * 12 + month
    fixed = []
    for a in anchors:
        d = a["date"]
        if abs(d.year * 12 + d.month - base) <= 1:
            fixed.append(a)
            continue
        try:
            fixed.append(dict(a, date=d.replace(year=year, month=month)))
        except ValueError:
            continue                                   # 31 בחודש של 30 יום: לא תאריך
    return fixed


def group_rows(words, positions, spacing):
    """
    משייך כל מילה לשורה הקרובה אליה אנכית.
    positions - רשימת (date, cy): איפה כל שורה בעמוד.
    מחזיר (header_lines, rows): שורות הכותרת שמעל הטבלה, ו-(date, words) לכל שורה.
    עמיד לסריקה עקומה ולמילים שנקראו כמה פעמים בכמה מעברי OCR.
    """
    if not positions:
        return _cluster(words), []
    max_dist = 0.45 * spacing
    first_cy = min(cy for _, cy in positions)
    groups = [[] for _ in positions]
    header = []
    for w in words:
        i = min(range(len(positions)), key=lambda k: abs(positions[k][1] - w["cy"]))
        if abs(positions[i][1] - w["cy"]) <= max_dist:
            groups[i].append(w)
        elif w["cy"] < first_cy - 0.5 * spacing:
            header.append(w)
    rows = [(d, sorted(g, key=lambda x: x["x0"], reverse=True)) for (d, _), g in zip(positions, groups)]
    return _cluster(header), rows


def read_table(words):
    """כל שורה לפי התאריך שנקרא בה. מחזיר (header_lines, rows) - ראו group_rows."""
    words, anchors, spacing = find_anchors(words)
    return group_rows(words, [(a["date"], a["cy"]) for a in anchors], spacing)


# ---------- ערכים מתוך שורה ----------
# ספרות שה-OCR מחליף בדו"ח הפשוט (גופן מודגש וקטן), כפי שנראו בסריקות:
# '11:05' -> '14:05' / '94:05' (1 נקרא 4, 9, 7), '8:30' -> '6:30', '3.50' -> '8.50' / '850'
_DIGIT_LOOKALIKES = {"4": "1", "7": "1", "9": "1", "6": "8", "8": "3", "3": "8"}
_LOOKALIKE_WEIGHT = 0.3        # קריאה "מתוקנת" שווה פחות מקריאה ישירה
MAX_HOURS_IN_A_DAY = 24


def _variants(text, with_lookalikes):
    """הקריאה עצמה, ואם מבקשים - גם קריאות "מתוקנות": ספרות דומות ('44:01' -> '11:01'),
    ונקודתיים שנבלעו ('4402' -> '44:02' -> '11:02')."""
    yield text, 1.0
    if not with_lookalikes:
        return
    bases = [(text, 1.0)]
    if re.fullmatch(r"\d{3,4}", text):
        bases.append((text[:-2] + ":" + text[-2:], 0.5))
    for base, weight in bases:
        if base != text:
            yield base, weight
        spots = [i for i, ch in enumerate(base) if ch in _DIGIT_LOOKALIKES][:4]
        for k in range(1, 1 << len(spots)):
            chars = list(base)
            for bit, i in enumerate(spots):
                if k >> bit & 1:
                    chars[i] = _DIGIT_LOOKALIKES[chars[i]]
            yield "".join(chars), weight * _LOOKALIKE_WEIGHT


def _x_center(w):
    return (w["x0"] + w.get("x1", w["x0"])) / 2


def time_candidates(line, with_lookalikes=False) -> dict[int, list]:
    """
    כל השעות החוקיות בשורה: דקות -> [קולות, מיקום אופקי ממוצע].
    ב-OCR מרובה-מעברים אותה שעה נקראת כמה פעמים, ולפעמים כשגיאה ('72:00'). כל קריאה היא "קול".
    """
    votes = {}
    for w in line:
        for text, weight in _variants(w["text"], with_lookalikes):
            if not TIME_RE.match(text):
                continue
            h, m = map(int, text.split(":"))
            if h > 23 or m > 59:
                continue
            v = w.get("n", 1) * weight
            entry = votes.setdefault(h * 60 + m, [0.0, 0.0])
            entry[0] += v
            entry[1] += v * _x_center(w)
    return {minutes: [v, xs / v] for minutes, (v, xs) in votes.items()}


def hours_candidates(line, with_lookalikes=False) -> dict[float, float]:
    """כל המספרים העשרוניים בשורה (סה"כ שעות וכו'): ערך -> קולות."""
    votes = {}
    for w in line:
        if "/" in w["text"] or ":" in w["text"]:
            continue
        for text, weight in _variants(w["text"], with_lookalikes):
            value = to_hours(text)
            if value is not None and value <= MAX_HOURS_IN_A_DAY:     # '38.03' הוא '3.03' שנקרא לא נכון
                votes[value] = votes.get(value, 0.0) + w.get("n", 1) * weight
    return votes


def read_times(line, count: int) -> list[time]:
    """
    עד `count` שעות מהשורה, לפי סדר העמודות מימין לשמאל.
    1. בוחרים אילו שעות: את הערכים שנקראו הכי הרבה פעמים.
    2. מסדרים אותן לפי המיקום בעמוד, לא לפי הגודל: הקטנה היא לא בהכרח הכניסה
       (בסוג B ההפסקה, 00:30, היא הקטנה ביותר).
    """
    votes = time_candidates(line)
    chosen = sorted(votes.items(), key=lambda kv: (-kv[1][0], kv[0]))[:count]
    chosen.sort(key=lambda kv: kv[1][1], reverse=True)               # מימין לשמאל
    return [time(minutes // 60, minutes % 60) for minutes, _ in chosen]


def read_shift_with_total(line, break_minutes=0, tolerance=0.011, total_line=None):
    """
    כניסה ויציאה שמסתדרות עם עמודת הסה"כ שבאותה שורה: יציאה - כניסה - הפסקה = סה"כ.
    בודקים כל צירוף (כולל קריאות "מתוקנות" של ספרות דומות) ובוחרים את העקבי שקיבל הכי הרבה קולות.
    הכניסה חייבת להיות מימין ליציאה (סדר העמודות). total_line: רק המילים של עמודת הסה"כ, אם ידועה.
    מחזיר (entry, exit) או None.
    """
    times = time_candidates(line, with_lookalikes=True)
    totals = hours_candidates(line if total_line is None else total_line, with_lookalikes=True)
    best, best_score = None, 0.0
    for e, (ev, ex) in times.items():
        for x, (xv, xx) in times.items():
            if x <= e or ex <= xx:
                continue
            span = (x - e - break_minutes) / 60
            for t, tv in totals.items():
                if abs(span - t) <= tolerance and ev + xv + tv > best_score:
                    best, best_score = (e, x), ev + xv + tv
    if best is None:
        return None
    e, x = best
    return time(e // 60, e % 60), time(x // 60, x % 60)


def column_values(line, gap=15.0) -> list[float]:
    """
    המספרים העשרוניים בשורה, אחד לכל עמודה, מימין לשמאל.
    מקבצים לפי המיקום האופקי (מספרים במרחק פחות מ-gap נקודות = אותה עמודה), ובכל עמודה
    בוחרים את הערך שנקרא הכי הרבה פעמים.
    """
    numbers = []
    for w in line:
        if "/" in w["text"] or ":" in w["text"] or has_hebrew(w["text"]):
            continue
        value = to_hours(w["text"])
        if value is not None:
            numbers.append((_x_center(w), value, w.get("n", 1)))
    numbers.sort(reverse=True)
    columns = []
    for x, value, n in numbers:
        if columns and columns[-1]["x"] - x < gap:
            columns[-1]["votes"][value] = columns[-1]["votes"].get(value, 0) + n
        else:
            columns.append({"x": x, "votes": {value: n}})
    return [max(c["votes"], key=c["votes"].get) for c in columns]


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
