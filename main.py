from parser import ReportParserFactory
from generator import ReportHtmlPdfGenerator

def main():
    input_pdf_path = r"E:\מסלול יד\פרקטיקוד\data\inputs\n_r_5_n.pdf"
    output_csv_path = r"data/outputs/output_report.csv"
    output_pdf_path = r"data/outputs/output_report.pdf"

    print("מתחיל תהליך עיבוד וניתוח הדוח...")
    result = ReportParserFactory.process_and_generate(input_pdf_path, output_csv_path)

    # קריאה לגנרטור ליצירת קובץ הפלט המעוצב
    ReportHtmlPdfGenerator.generate_like_original(result, output_pdf_path)
    print("התהליך הסתיים בהצלחה!")

if __name__ == "__main__":
    main()