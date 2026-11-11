# מחולל וריאציות לדו"ח נוכחות

מקבל דו"ח נוכחות סרוק (PDF), ומייצר דו"ח חדש שנראה כמו המקור, עם שעות אחרות, והכול עדיין הגיוני:
היציאה אחרי הכניסה, הסכומים מסתדרים, והשעות הנוספות מחושבות נכון. המקור לא משתנה, ואותו קלט נותן תמיד אותו פלט.

## שני סוגי הדו"חות

| | סוג A: הפשוט | סוג B: המפורט |
|---|---|---|
| קבצים לדוגמה | `n_r_5_n.pdf`, `n_r_10_n.pdf` | `a_r_9.pdf`, `a_r_25.pdf` |
| עמודות | תאריך, יום בשבוע, שעת כניסה, שעת יציאה, סה"כ שעות, הערות | תאריך, יום, מקום, כניסה, יציאה, הפסקה, סה"כ, 100%, 125%, 150%, שבת |
| סיכום | למעלה: ימי עבודה, שעות חודשיות, מחיר לשעה, לתשלום | למטה: שורת סכומים + טבלת סיכום |
| שורות | כל יום בחודש, כולל שבת וחג (בלי שעות) | רק ימי עבודה |
| שבת בווריאציה | השורה נשארת, בלי שעות | השורה לא מופיעה (אין עבודה בשבת) |
| סה"כ בשורה | יציאה − כניסה | יציאה − כניסה − הפסקה, ואז חלוקה ל-100/125/150 (בשבת: הכול לשבת; יום חג נשאר בעמודה שלו) |

## התקנה

1. Python 3.10 ומעלה.
2. **Tesseract** עם חבילת העברית:
   - Windows: להתקין מ-https://github.com/UB-Mannheim/tesseract/wiki ולסמן בהתקנה את **Hebrew**.
   - אם Tesseract לא הותקן בנתיב הרגיל (`C:\Program Files\Tesseract-OCR`), להגדיר משתנה סביבה
     `TESSERACT_CMD` עם הנתיב ל-`tesseract.exe`.
   - בדיקה: `tesseract --list-langs` צריך להציג `heb`.
   - Poppler **לא** נדרש: pdfplumber ממיר עמודים לתמונה בעצמו.
3. ספריות:
   ```
   python -m venv .venv
   .venv\Scripts\activate          (Windows)
   pip install -r requirements.txt
   ```

## הרצה

מריצים תמיד **מתיקיית השורש** של הפרויקט.

```
python main.py                              כל קבצי ה-PDF שבתיקייה data/inputs
python main.py data/inputs/a_r_9.pdf        קובץ אחד
python main.py --format csv                 פלט CSV (גם: html, pdf)
python main.py --seed 3                     וריאציה אחרת (ברירת מחדל: 0)
python main.py --help
```

הפלט נכתב ל-`data/outputs/<שם הקובץ>_variation.html`. קובץ המקור לא נדרס.
אזהרות (שורה שלא נקראה, שורה שהושלמה מהשעות החודשיות, מחיר לשעה שלא נמצא) מודפסות עם התאריך.
ה-OCR לוקח בערך 20 שניות לקובץ.

ב-PyCharm: לשים את קבצי ה-PDF ב-`data/inputs` וללחוץ Run על `main.py`.
(Working directory בהגדרות ההרצה = תיקיית הפרויקט.)

**PDF:** `--format pdf` דורש `pip install weasyprint` (ב-Windows צריך גם GTK). בלי זה: `--format html`
ומהדפדפן "הדפסה ← שמירה כ-PDF".

## טסטים

```
python -m pytest
```

הטסטים לא צריכים Tesseract: הם רצים על עמודים שנבנו ביד (`tests/sample_pages.py`) ועל פלט OCR שמור
(`tests/fixtures/*.json`). כדי להוסיף את קבצי הדוגמה האמיתיים (פעם אחת, עם Tesseract):

```
python -m tools.save_ocr_fixture data/inputs/n_r_5_n.pdf data/inputs/n_r_10_n.pdf data/inputs/a_r_9.pdf data/inputs/a_r_25.pdf
```

מעכשיו `pytest` בודק גם שכל קובץ דוגמה מזוהה נכון (`n_*` = סוג A, `a_*` = סוג B), נקרא, ועובר טרנספורמציה בתוך הכללים.

כלי דיבאג: `python -m tools.diagnose tests/fixtures/a_r_9.json` מראה מה כל תחנה רואה.

## Docker

```
docker build -t attendance .
docker run --rm -v "%cd%/data:/app/data" attendance
```
(ב-Linux/Mac: `"$(pwd)/data:/app/data"`)

## איך הפרויקט בנוי

צינור של חמש תחנות. כל תחנה מקבלת דבר אחד ומחזירה דבר אחד, ואחרי הפרסר כולן עובדות רק עם `AttendanceReport`.

| # | תחנה | קובץ | מקבלת | מחזירה |
|---|---|---|---|---|
| 1 | OCR | `parsing/ocr.py` | נתיב ל-PDF | מילים + מיקום, לכל עמוד |
| 2 | Classifier | `parsing/classifier.py` | טקסט | `ReportType` |
| 3 | Parser | `parsing/parser_factory.py`, `base_parser.py`, `type_a_parser.py`, `type_b_parser.py` | מילים | `AttendanceReport` |
| 4 | Transformer | `transformation/service.py` + אסטרטגיה לכל סוג | `AttendanceReport` | `AttendanceReport` חדש |
| 5 | Generator | `generation/` (Renderer לכל פורמט, `layouts.py` לכל סוג) | `AttendanceReport` | קובץ |

```
main.py              מחבר את התחנות. אין בו לוגיקה של אף תחנה
domain/              המודל (models.py), השגיאות, חישובי זמן. לא מייבא כלום מהפרויקט
config/rules.py      כל המספרים: טווחי הזזה, שעות עבודה, ספי שעות נוספות
parsing/             תחנות 1-3: PDF -> AttendanceReport
transformation/      תחנה 4: Strategy לכל סוג + validation.py (האינווריאנטים)
generation/          תחנה 5: Renderer לכל פורמט + layouts.py (העמודות של כל סוג, כנתונים)
tests/               טסטים לכל תחנה + fixtures
tools/               שמירת fixtures ודיבאג
docs/DECISIONS.md    יומן החלטות
```

**הוספת סוג C:** `ReportType` ב-`domain/models.py`, קובץ פרסר חדש + שורה ב-`parser_factory.py`,
מילות מפתח ב-`classifier.py`, קובץ אסטרטגיה חדש + שורה ב-`main.py`, כללים ב-`config/rules.py`,
ופריסה ב-`generation/layouts.py`. שני קבצים חדשים ושורות במילונים, בלי לפתוח לוגיקה קיימת.
