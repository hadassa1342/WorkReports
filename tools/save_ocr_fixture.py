"""
שומר את פלט ה-OCR של קבצי הדוגמה ל-tests/fixtures, פעם אחת.
מעכשיו הטסטים וה-Classifier והפרסר רצים על הטקסט השמור, בשניות, בלי Tesseract.

    python -m tools.save_ocr_fixture data/inputs/n_r_5_n.pdf data/inputs/a_r_9.pdf ...
"""
import json
import sys
from pathlib import Path

from parsing.ocr import extract_pages

FIXTURES_DIR = Path("tests/fixtures")


def main(paths) -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for path in map(Path, paths):
        pages = extract_pages(path)
        target = FIXTURES_DIR / f"{path.stem}.json"
        target.write_text(json.dumps(pages, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"{path.name}: {sum(len(p) for p in pages)} words, {len(pages)} pages -> {target}")


if __name__ == "__main__":
    main(sys.argv[1:] or sorted(Path("data/inputs").glob("*.pdf")))
