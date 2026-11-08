class AttendanceReportError(Exception):
    """מחלקת הבסיס: מי שתופס אותה תופס כל שגיאה של הפרויקט."""


class OcrError(AttendanceReportError):
    """לא הצלחנו לקרוא את הקובץ (PDF פגום, Tesseract חסר, חבילת עברית חסרה)."""


class UnknownReportTypeError(AttendanceReportError):
    """אין מספיק ראיות כדי לקבוע אם זה סוג A או סוג B."""


class ParseError(AttendanceReportError):
    """הקובץ זוהה, אבל לא נמצאו בו שורות נוכחות."""


class TransformationError(AttendanceReportError):
    """הווריאציה שנוצרה לא עומדת באחד הכללים."""


class RenderError(AttendanceReportError):
    """לא הצלחנו לכתוב את קובץ הפלט."""
