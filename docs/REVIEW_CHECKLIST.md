# מפה לטופס הקוד ריוויו: איפה כל דבר נמצא בקוד

לכל תחנת בדיקה בטופס: איפה זה בקוד, כדי לכתוב בשדה ההערה.
סעיפים שמסומנים **(את)** הם דברים שרק את יכולה לעשות. הקוד מוכן להם, אבל הם לא "יש אצלי" עד שעשית אותם.

## 1. התמונה הגדולה
| בדיקה | איפה |
|---|---|
| הפלט הוא וריאציה הגיונית | `transformation/service.py` + `transformation/validation.py` |
| מצביעה על כל 5 התחנות | `main.py` → `process_pdf`: `extract_pages` → `classify` → `get_parser().parse` → `TRANSFORMER.transform` → `renderer.render` |
| כל תחנה מקבלת פרמטר ומחזירה תוצאה | אין משתנים גלובליים שתחנה כותבת ואחרת קוראת. אין קבצים זמניים |
| אחרי הפרסר אף קוד לא חוזר לטקסט | `transformation/` ו-`generation/` מקבלים רק `AttendanceReport` |

**המפה (1.5):** OCR = `parsing/ocr.py: extract_pages` · Classifier = `parsing/classifier.py: classify` · Parser = `parsing/parser_factory.py: get_parser` + `BaseParser.parse` · Transformer = `transformation/service.py: TransformationService.transform` · Generator = `generation/html_renderer.py: HtmlRenderer.render`. בין התחנות: `AttendanceReport`.

## 2. מפת הפרויקט
| בדיקה | איפה |
|---|---|
| תיקייה לכל שלב | `domain/ config/ parsing/ transformation/ generation/ tests/` |
| main קצר, תוכן עניינים | `main.py: process_pdf` (5 שורות, 5 תחנות). השאר הוא argparse |
| `if __name__ == "__main__"` | `main.py`, `tools/*.py` |
| domain לא מייבא מהפרויקט, generation לא מייבא מ-parsing | נבדק בחיפוש `import` |
| אין נתיבים של המחשב שלי | `TESSERACT_CMD` ממשתנה סביבה; קלט ב-`data/inputs` (יחסי); README |
| בלי `sys.path.append` | `pytest.ini` (`pythonpath = .`), כלים רצים עם `python -m` |

## 3. המודל
| בדיקה | איפה |
|---|---|
| שעות כ-`time` | `domain/models.py: AttendanceRow`. המרה: בפרסר (`read_times`) ובגנרוט (`generation/formatting.py`) |
| frozen + tuple | כל המודלים `frozen=True`, `rows: tuple` |
| מודל אחד אחרי הפרסר | `AttendanceReport` |
| שדות B אופציונליים + הסבר | `AttendanceRow` (location, break_minutes, hours_*), `docs/DECISIONS.md` סעיף 4 |
| סוג במקום אחד | `ReportType` (Enum) |
| שבת וחג במודל, בלי שעות | `entry_time=None`, `is_work_day` |

## 4. יסודות OOP
| בדיקה | איפה |
|---|---|
| `@abstractmethod` | `parsing/base_parser.py`, `transformation/base_strategy.py`, `generation/base_renderer.py`. טסט: יורש בלי מימוש לא נוצר |
| אותה קריאה, כמה מחלקות | `get_parser(t).parse(pages)`, `strategy.transform_row(...)`, `renderer.render(...)` |
| מילון במקום if | `_PARSERS`, `_EVIDENCE`, `RULES`, `LAYOUTS`, `RENDERERS`, האסטרטגיות ב-`main.py` |

## 5. התחנות
**OCR:** רק `parsing/ocr.py` מייבא pytesseract · כל העמודים (`for page in pdf.pages`) · ניקוי: `parsing/text_tools.py: clean_token, fix_date_token`, כל כלל עם דוגמה אמיתית בהערה · fixtures: `tools/save_ocr_fixture.py` → `tests/fixtures/`.

**Classifier:** ניקוד על כמה ראיות + סף + שגיאה בתיקו (`parsing/classifier.py`) · טסט לכל קובץ דוגמה: `tests/test_classifier.py::test_every_sample_file_is_classified_correctly` **(את: להריץ `save_ocr_fixture` על 4 הקבצים)**.

**Parser:** `BaseParser.parse` (Template Method) + `_parse_row`/`_parse_summary` ביורשים · אין קוד מועתק: הכול ב-`text_tools.py` · שעות לפי עמודה: `read_times` + טסט `test_type_b_reads_times_by_column_not_by_size` · Factory: `parsing/parser_factory.py` · שורה שלא נקראה: `log.warning` עם התאריך, נשארת בלי שעות · מחזיר `AttendanceReport`.

**Transformer:** אסטרטגיה לכל סוג + מילון ב-`TransformationService` · דו"ח חדש עם `replace` · seed לפי תאריך · מחשבים מחדש סה"כ, 100/125/150, סיכום (`build_summary`) · בדיקה אחרי כל שורה: `validate_row` · מספרים ב-`config/rules.py` · שבת/חג: `if not row.is_work_day: return row`.

**Generator:** מקבל רק `AttendanceReport` · מחלקה לכל פורמט: `HtmlRenderer`, `CsvRenderer`, `PdfRenderer` · עמודות וסיכום כנתונים: `generation/layouts.py` · לא מחשב (טסט `test_generator_shows_the_summary_and_does_not_recompute_it`) · `dir="rtl"`, גופן David/Arial · פלט ל-`data/outputs/<שם>_variation.html` · **(את: להניח מקור ופלט זה לצד זה ולבדוק)**.

**main.py:** קורא לתחנות לפי הסדר · אסטרטגיות ורנדררים נוצרים ב-main ומועברים פנימה · `except AttendanceReportError` → הודעה אחת · argparse עם `--help`, `-o`, `-f`, `--seed` (בונוס).

## 6. חוצה הכול
| בדיקה | איפה |
|---|---|
| מספרים בקובץ config אחד | `config/rules.py` |
| היררכיית שגיאות, אין except ריק | `domain/exceptions.py` |
| טסט לכל תחנה | `tests/test_classifier.py`, `test_parsers.py`, `test_transformation.py`, `test_generation.py` |
| כל אינווריאנט בטסט | `tests/test_transformation.py::test_invariants` (20 seeds × 2 סוגים) |
| חברה הריצה לפי README | **(את)** |
| יומן החלטות | `docs/DECISIONS.md` **(את: לעבור ולנסח במילים שלך)** |
| Dockerfile (בונוס) | `Dockerfile`. **(את: `docker build` לפני שמסמנים)** |

## 7. מבחן הגמישות
סוג C: `ReportType` + `parsing/type_c_parser.py` (חדש) + שורה ב-`_PARSERS` + שורה ב-`_EVIDENCE` + `transformation/type_c_strategy.py` (חדש) + שורה ב-`RULES` + שורה ב-`main.py` + שורה ב-`LAYOUTS`. אף if/elif קיים לא נפתח.
פורמט חדש: מחלקה ב-`generation/` + שורה ב-`RENDERERS`. כלל: שורה ב-`config/rules.py`.

## 8-9. קוד ריוויו לחברה, הכנה לראיון
**(את)**. התשובות לשאלות הראיון נמצאות ב-`docs/DECISIONS.md`.
