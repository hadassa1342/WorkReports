"""
תחנה 1: OCR. הקובץ היחיד בפרויקט שמכיר את Tesseract ואת pdfplumber.

מקבל נתיב ל-PDF ומחזיר את המילים של כל העמודים, כל מילה עם המיקום שלה בעמוד:
    [[{"text": "8:30", "x0": .., "x1": .., "top": .., "bottom": ..}, ...], ...]   # רשימה לכל עמוד
שומרים מיקום ולא רק טקסט, כי הטבלאות סרוקות ועקומות: הפרסרים משייכים מילה לשורה לפי
הגובה שלה, ומזהים עמודה לפי המיקום האופקי.

אם ל-PDF יש שכבת טקסט משתמשים בה. אם הוא סרוק (תמונה), מריצים OCR בכמה מעברים:
  1. אנגלית בלבד, בכמה רזולוציות - לתאריכים, שעות ומספרים. קורא אותם מדויק יותר מהמעבר העברי,
     ואיחוד של כמה מעברים משחזר תאריכים שמעבר בודד מפספס.
  2. עברית+אנגלית - למילים בעברית (כותרות, מקום, הערות).

הגדרות מחשב (נתיב ל-Tesseract) מגיעות ממשתנה הסביבה TESSERACT_CMD. ראו README.
"""
import os
import shutil
from pathlib import Path

from domain.exceptions import OcrError

HEBREW_DPI = 300
MIN_CONF = 30               # מילים עם ביטחון נמוך מזה נזרקות (רעש)
HEBREW_PSM = 6              # בלוק אחיד של שורות - מתאים לטבלאות
NUMERIC_PASSES = [(300, 6), (200, 12), (300, 3), (400, 6), (400, 4), (200, 6), (250, 6), (500, 6)]
TOP_CROP_RATIO = 0.30       # קופסת הסיכום בראש הדף קטנה, ומעבר על כל העמוד מפספס אותה
TOP_CROP_PSMS = (6, 4, 11)
_WORD_KEYS = ("x0", "x1", "top", "bottom")


def extract_pages(pdf_path: Path) -> list[list[dict]]:
    """כל העמודים, לא רק הראשון."""
    import pdfplumber
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            return [_page_words(page) for page in pdf.pages]
    except OcrError:
        raise
    except Exception as error:
        raise OcrError(f"Could not read {Path(pdf_path).name}: {error}") from error


def pages_to_text(pages: list[list[dict]]) -> str:
    """כל המילים כמחרוזת אחת - בשביל ה-Classifier, שלא צריך מיקומים."""
    return " ".join(w["text"] for page in pages for w in page)


def _normalize(word: dict) -> dict:
    return {"text": str(word["text"]), **{k: float(word[k]) for k in _WORD_KEYS}}


def _page_words(page) -> list[dict]:
    words = page.extract_words()
    if words:                                   # יש שכבת טקסט: לא צריך OCR
        return [_normalize(w) for w in words]
    return _ocr_page(page)


def _setup_tesseract(pytesseract):
    """סדר חיפוש: משתנה הסביבה TESSERACT_CMD, אחר כך PATH, אחר כך נתיבי ההתקנה הרגילים של Windows."""
    env_path = os.getenv("TESSERACT_CMD")
    if env_path and os.path.exists(env_path):
        pytesseract.pytesseract.tesseract_cmd = env_path
        return
    if shutil.which("tesseract"):
        return
    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ):
        if os.path.exists(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            return
    raise OcrError("Tesseract not found. Install it, or set TESSERACT_CMD to the path of tesseract.exe")


def _ocr_pass(pytesseract, img, lang, scale, psm) -> list[dict]:
    data = pytesseract.image_to_data(img, lang=lang, config=f"--psm {psm}",
                                     output_type=pytesseract.Output.DICT)
    words = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text or float(data["conf"][i]) < MIN_CONF:
            continue
        left, top = data["left"][i], data["top"][i]
        words.append({
            "text": text,
            "x0": left * scale,
            "x1": (left + data["width"][i]) * scale,
            "top": top * scale,
            "bottom": (top + data["height"][i]) * scale,
        })
    return words


def _has_hebrew(text):
    return any("\u0590" <= c <= "\u05FF" for c in text)


def _ocr_page(page) -> list[dict]:
    import pytesseract
    from PIL import ImageOps

    _setup_tesseract(pytesseract)
    if "heb" not in pytesseract.get_languages(config=""):
        raise OcrError("The Hebrew language pack (heb) is not installed in Tesseract. "
                       "Download heb.traineddata into the tessdata folder.")

    images = {}

    def image_at(dpi):
        if dpi not in images:
            img = page.to_image(resolution=dpi).original.convert("L")
            images[dpi] = ImageOps.autocontrast(img, cutoff=1)
        return images[dpi]

    numeric = []
    for dpi, psm in NUMERIC_PASSES:
        numeric += [w for w in _ocr_pass(pytesseract, image_at(dpi), "eng", 72 / dpi, psm)
                    if any(c.isdigit() for c in w["text"])]

    top_img = image_at(300)
    top_crop = top_img.crop((0, 0, top_img.width, int(top_img.height * TOP_CROP_RATIO)))
    for psm in TOP_CROP_PSMS:
        numeric += [w for w in _ocr_pass(pytesseract, top_crop, "eng", 72 / 300, psm)
                    if any(c.isdigit() for c in w["text"])]

    hebrew = [w for w in _ocr_pass(pytesseract, image_at(HEBREW_DPI), "heb+eng", 72 / HEBREW_DPI, HEBREW_PSM)
              if _has_hebrew(w["text"])]
    return numeric + hebrew
