"""
מראה מה כל תחנה רואה, בשביל דיבאג. עובד על PDF או על fixture שמור (json).

    python -m tools.diagnose tests/fixtures/a_r_9.json
"""
import json
import logging
import sys
from pathlib import Path

from parsing.classifier import classify, score
from parsing.ocr import extract_pages, pages_to_text
from parsing.parser_factory import get_parser
from parsing.text_tools import read_word_lines


def load_pages(path: Path):
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return extract_pages(path)


def main(path: Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    pages = load_pages(path)
    print("--- first 25 lines of page 1 ---")
    for i, line in enumerate(read_word_lines(pages[0])[:25]):
        print(i, [w["text"] for w in line])
    text = pages_to_text(pages)
    print("--- classifier scores:", {t.value: s for t, s in score(text).items()})
    report = get_parser(classify(text)).parse(pages)
    print("--- type:", report.report_type.value, "| rows:", len(report.rows))
    print("--- summary:", report.summary)
    for row in report.rows[:6]:
        print(row)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
