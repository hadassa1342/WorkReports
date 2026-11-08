"""
נקודת הכניסה: מחברת את חמש התחנות לפי הסדר, ולא עושה אף אחת מהן בעצמה.

    python main.py                         # כל קבצי ה-PDF בתיקייה data/inputs
    python main.py data/inputs/a_r_9.pdf   # קובץ אחד
    python main.py --help
"""
import argparse
import logging
import sys
from pathlib import Path

from config.rules import RULES
from domain.exceptions import AttendanceReportError
from domain.models import ReportType
from generation.csv_renderer import CsvRenderer
from generation.html_renderer import HtmlRenderer
from generation.pdf_renderer import PdfRenderer
from parsing.classifier import classify
from parsing.ocr import extract_pages, pages_to_text
from parsing.parser_factory import get_parser
from transformation.service import TransformationService
from transformation.type_a_strategy import TypeATransformationStrategy
from transformation.type_b_strategy import TypeBTransformationStrategy

DEFAULT_INPUT_DIR = Path("data/inputs")
DEFAULT_OUTPUT_DIR = Path("data/outputs")

# המקום היחיד שבונה את החלקים ומחבר ביניהם
TRANSFORMER = TransformationService(
    strategies={
        ReportType.TYPE_A: TypeATransformationStrategy(),
        ReportType.TYPE_B: TypeBTransformationStrategy(),
    },
    rules=RULES,
)
RENDERERS = {"html": HtmlRenderer(), "csv": CsvRenderer(), "pdf": PdfRenderer()}


def process_pdf(pdf_path: Path, output_dir: Path, output_format: str = "html", seed: int = 0) -> Path:
    pages = extract_pages(pdf_path)                          # 1. פיקסלים -> מילים
    report_type = classify(pages_to_text(pages))             # 2. איזה סוג?
    report = get_parser(report_type).parse(pages)            # 3. מילים -> AttendanceReport
    new_report = TRANSFORMER.transform(report, seed)         # 4. שעות חדשות, אותו מבנה
    renderer = RENDERERS[output_format]                      # 5. דו"ח -> קובץ
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{pdf_path.stem}_variation{renderer.file_extension}"
    return renderer.render(new_report, output_path)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a logical variation of a scanned attendance report")
    parser.add_argument("pdfs", nargs="*", type=Path,
                        help=f"scanned attendance reports (default: every PDF in {DEFAULT_INPUT_DIR})")
    parser.add_argument("-o", "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-f", "--format", choices=sorted(RENDERERS), default="html")
    parser.add_argument("--seed", type=int, default=0, help="another seed gives another variation")
    parser.add_argument("-v", "--verbose", action="store_true", help="show debug messages")
    return parser


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")

    pdfs = args.pdfs or sorted(DEFAULT_INPUT_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDF files given, and none found in {DEFAULT_INPUT_DIR}")
        return 1

    failed = 0
    for pdf in pdfs:
        try:
            result = process_pdf(pdf, args.output_dir, args.format, args.seed)
            print(f"Created {result}")
        except AttendanceReportError as error:
            print(f"Failed on {pdf.name}: {error}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
