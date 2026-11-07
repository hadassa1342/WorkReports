import sys
import pdfplumber
from parser import ReportParserFactory, read_word_lines
from ocr_words import page_words

path = sys.argv[1]

with pdfplumber.open(path) as pdf:
    page = pdf.pages[0]
    print("יש שכבת טקסט בקובץ:", bool(page.extract_words()))
    print("--- 25 השורות הראשונות כפי שהפרסר רואה אותן ---")
    for i, line in enumerate(read_word_lines(page)[:25]):
        print(i, [w["text"] for w in line])

print("--- סוג שזוהה:", ReportParserFactory.detect_report_type(path))

result = ReportParserFactory.get_parser(path).parse(path)
print("מספר שורות:", len(result.rows))
print("סיכום:", result.summary_data)
for row in result.rows[:6]:
    print(row)