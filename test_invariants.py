import os
from parser import ReportParserFactory


def test_invariants_and_determinism():
    pdf_path = r"E:\מסלול יד\פרקטיקוד\data\inputs\a.pdf"  # התאמי לנתיב קובץ A שלך

    if not os.path.exists(pdf_path):
        print(f"קובץ הקלט לא נמצא בנתיב: {pdf_path}")
        return

    output_path_1 = "data/outputs/test_output_1.csv"
    output_path_2 = "data/outputs/test_output_2.csv"

    # הרצה ראשונה
    result_1 = ReportParserFactory.process_and_generate(pdf_path, output_path_1)

    # הרצה שנייה על אותו קובץ בדיוק
    result_2 = ReportParserFactory.process_and_generate(pdf_path, output_path_2)

    # בדיקת אינווריאנטים: השוואת מספר השורות וסוג הדוח
    assert len(result_1.rows) == len(result_2.rows), "שגיאה: מספר השורות אינו זהה בין שתי ההרצות!"
    assert result_1.report_type == result_2.report_type, "שגיאה: סוג הדוח שונה בין ההרצות!"

    # השוואת תוכן קובצי הפלט ברמת הביטים/הטקסט
    with open(output_path_1, "r", encoding="utf-8-sig") as f1, open(output_path_2, "r", encoding="utf-8-sig") as f2:
        content_1 = f1.read()
        content_2 = f2.read()
        assert content_1 == content_2, "שגיאה: קובצי הפלט אינם זהים לחלוטין!"

    print("הבדיקה עברה בהצלחה: שתי הרצות על אותו קובץ נותנות פלט זהה לחלוטין!")


if __name__ == "__main__":
    test_invariants_and_determinism()