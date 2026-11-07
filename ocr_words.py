"""
קריאת מילים מ-PDF: אם יש שכבת טקסט משתמשים בה, ואם הקובץ סרוק (תמונה) - OCR.
מחזיר מילים באותו מבנה של pdfplumber (text, x0, x1, top, bottom), כך שהפרסרים לא משתנים.

ה-OCR רץ בשני מעברים:
  1. אנגלית בלבד - לתאריכים, שעות ומספרים. קורא אותם מדויק יותר מהמעבר העברי.
  2. עברית+אנגלית - למילים בעברית (כותרות, מקום, הערות).
ומאחד: מספרים מהמעבר הראשון, מילים עבריות מהשני.

דרישות:
    pip install pytesseract pdfplumber
    Tesseract מותקן + חבילת השפה heb (tesseract --list-langs צריך להציג heb)
"""
OCR_DPI = 300          # 300 מומלץ לטקסט קטן. מתחת ל-200 הדיוק יורד מהר.
MIN_CONF = 30          # מילים עם ביטחון נמוך מזה נזרקות (רעש)
TESS_CONFIG = "--psm 6"   # בלוק אחיד של שורות - מתאים לטבלאות
REQUIRE_HEBREW = True  # False = אם heb חסר, ממשיכים עם מספרים בלבד (לבדיקות)


def _setup_tesseract(pytesseract):
    """
    ב-Windows ההתקנה של Tesseract לא תמיד מוסיפה אותו ל-PATH.
    סדר חיפוש: משתנה סביבה TESSERACT_CMD, אחר כך PATH, אחר כך נתיבי ההתקנה הרגילים.
    """
    import os
    import shutil

    env_path = os.environ.get("TESSERACT_CMD")
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
    raise RuntimeError(
        "Tesseract לא נמצא. התקן אותו, או הגדר משתנה סביבה "
        "TESSERACT_CMD לנתיב של tesseract.exe"
    )


def _has_hebrew(text):
    return any("\u0590" <= c <= "\u05FF" for c in text)


def _ocr_pass(pytesseract, img, lang, scale):
    data = pytesseract.image_to_data(
        img, lang=lang, config=TESS_CONFIG, output_type=pytesseract.Output.DICT
    )
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


def ocr_words(page, dpi=OCR_DPI):
    import pytesseract   # נטען רק כשצריך, כדי ש-PDF רגיל יעבוד גם בלי OCR

    _setup_tesseract(pytesseract)
    has_heb = "heb" in pytesseract.get_languages(config="")
    if not has_heb and REQUIRE_HEBREW:
        raise RuntimeError(
            "חבילת השפה העברית (heb) לא מותקנת ב-Tesseract. "
            "הורד heb.traineddata לתיקיית tessdata."
        )

    img = page.to_image(resolution=dpi).original.convert("L")
    scale = 72 / dpi   # מ-פיקסלים לנקודות, כמו הקואורדינטות של pdfplumber

    numeric = [w for w in _ocr_pass(pytesseract, img, "eng", scale)
               if any(c.isdigit() for c in w["text"])]
    hebrew = []
    if has_heb:
        hebrew = [w for w in _ocr_pass(pytesseract, img, "heb+eng", scale)
                  if _has_hebrew(w["text"])]
    return numeric + hebrew


def page_words(page):
    """שכבת טקסט אם קיימת, אחרת OCR."""
    words = page.extract_words()
    return words if words else ocr_words(page)
