"""Generates the test letters in samples/letters.py as PDFs (plus two photo versions) in samples/generated/.

Run from backend/:  .venv/Scripts/python samples/make_samples.py
"""

import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parent))
from letters import LETTERS, Letter  # noqa: E402

OUT = Path(__file__).parent / "generated"
FOOTER = "SAMPLE LETTER FOR TESTING ONLY - all names, companies and contact details are fictional."
# Letters also saved as photos, to test reading images (needs ANTHROPIC_API_KEY or Tesseract).
PHOTO_VERSIONS = {"fake_canada_farm.pdf": "png", "real_uae_facilities.pdf": "jpg"}


def write_pdf(path: Path, letter: Letter) -> None:
    doc = pymupdf.open()
    page = doc.new_page()  # A4
    overflow = page.insert_textbox(pymupdf.Rect(50, 45, 545, 790), letter.text, fontsize=9.5, fontname="helv")
    if overflow < 0:
        raise ValueError(f"{letter.file}: text does not fit on one page")
    page.insert_text((50, 815), FOOTER, fontsize=7, fontname="helv", color=(0.45, 0.45, 0.45))
    doc.set_metadata({
        "producer": letter.producer,
        "creator": letter.producer,
        "creationDate": "D:20260901093000",
        "modDate": "D:20260901093000",
    })
    doc.save(path)
    doc.close()

    if letter.edited_with:
        # Simulate someone opening the PDF in an online editor and re-saving it (an incremental update).
        doc = pymupdf.open(path)
        doc.set_metadata({**doc.metadata, "producer": letter.edited_with, "modDate": "D:20261005151200"})
        doc.saveIncr()
        doc.close()


def write_photo(pdf_path: Path, fmt: str) -> Path:
    doc = pymupdf.open(pdf_path)
    pix = doc[0].get_pixmap(dpi=150)
    out = pdf_path.with_name(pdf_path.stem + "_photo." + fmt)
    pix.save(out, jpg_quality=80) if fmt == "jpg" else pix.save(out)
    return out


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for letter in LETTERS:
        path = OUT / letter.file
        write_pdf(path, letter)
        print(f"  {letter.expected:4}  {path.name}")
        if fmt := PHOTO_VERSIONS.get(letter.file):
            print(f"  {letter.expected:4}  {write_photo(path, fmt).name}")
    print(f"Wrote {len(LETTERS)} letters to {OUT}")
