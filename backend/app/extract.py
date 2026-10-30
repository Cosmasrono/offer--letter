"""Get readable text out of an uploaded PDF or image."""

import io
import os
import shutil
import re
from dataclasses import dataclass, field

import anthropic
import pymupdf
from PIL import Image, UnidentifiedImageError

from . import ai
from .models import Finding, SourceCheck

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
MIN_TEXT_CHARS = 80  # below this a PDF is treated as a scan


@dataclass
class Extraction:
    text: str
    method: str
    pdf: pymupdf.Document | None = None
    warnings: list[str] = field(default_factory=list)
    source_checks: list[SourceCheck] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    sender_emails: list[str] = field(default_factory=list)
    checks_not_run: list[str] = field(default_factory=list)
    pdf_data: bytes | None = None


def _tesseract_available() -> bool:
    cmd = os.getenv("TESSERACT_CMD")
    if cmd:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = cmd
        return os.path.exists(cmd)
    return shutil.which("tesseract") is not None


def _ocr_images(images: list[bytes], media_type: str) -> tuple[str, str, list[str]]:
    """OCR page images with the configured AI provider, otherwise Tesseract."""
    warnings = []
    if ai.is_enabled():
        try:
            text = ai.read_images(images, media_type)
            if text.strip():
                return text, f"{ai.provider_name().lower()}-vision", []
            warnings.append(f"{ai.provider_name()} returned no text from the image.")
        except ai.AIError as e:
            warnings.append(str(e))
        except anthropic.APIError as e:
            warnings.append(f"Could not read the image with {ai.provider_name()} ({type(e).__name__}).")
    if _tesseract_available():
        import pytesseract

        pages = []
        for content in images:
            image = Image.open(io.BytesIO(content))
            page = pytesseract.image_to_string(image)
            if re.search(r"sponsor licen[cs]e number", page, re.I) and re.search(r"certificate number", page, re.I):
                # CoS forms put labels and values in separate columns; block mode keeps each row together.
                structured = pytesseract.image_to_string(image, config="--psm 6")
                if re.search(r"expiry date\s*\(\s*use\s*by\s*\)\s*:", structured, re.I):
                    page = structured
            pages.append(page)
        text = "\n".join(pages)
        if text.strip() and warnings:
            warnings = ["The image was read using local Tesseract OCR because AI image reading was unavailable."]
        return text, "tesseract-ocr", warnings
    return "", "none", warnings or [
        "This file is a photo or scan. Configure Groq or OpenRouter, or install Tesseract OCR so its text can be read."
    ]


def extract(data: bytes, filename: str) -> Extraction:
    ext = os.path.splitext(filename.lower())[1]

    if ext == ".pdf":
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except (pymupdf.FileDataError, RuntimeError) as e:
            raise ValueError("This PDF could not be opened. It may be damaged or password-protected.") from e
        text = "\n".join(page.get_text() for page in doc)
        if len(text.strip()) >= MIN_TEXT_CHARS:
            return Extraction(text=text, method="pdf-text", pdf=doc)
        # Scanned PDF: render the first pages to images and OCR them.
        images = [page.get_pixmap(dpi=200).tobytes("png") for page in list(doc)[:5]]
        ocr_text, method, warnings = _ocr_images(images, "image/png")
        return Extraction(text=ocr_text or text, method=f"pdf-scan/{method}", pdf=doc, warnings=warnings)

    if ext in IMAGE_TYPES:
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > 40_000_000:
                    raise ValueError("The image is too large to read safely. Resize it and try again.")
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise ValueError("Not checked — the image file could not be recognized or read. Export it again as JPG, PNG or WEBP.") from error
        text, method, warnings = _ocr_images([data], IMAGE_TYPES[ext])
        return Extraction(text=text, method=method, warnings=warnings)

    if ext == ".txt":
        return Extraction(text=data.decode("utf-8", errors="ignore"), method="plain-text")

    if ext == ".eml":
        from .email_document import read_email

        email = read_email(data)
        texts, warnings, not_run = [], list(email.warnings), []
        pdf, pdf_data = None, None
        for name, content in email.pdf_attachments:
            try:
                attachment = extract(content, name)
                texts.append(attachment.text)
                warnings.extend(attachment.warnings)
                if attachment.pdf is not None:
                    if pdf is None:
                        pdf, pdf_data = attachment.pdf, content
                    else:
                        attachment.pdf.close()
                if not attachment.text.strip():
                    not_run.append("An attached PDF had no readable text; its offer terms were not checked.")
            except ValueError:
                warnings.append("An attached PDF could not be opened. Upload the original attachment separately.")
                not_run.append("An email PDF attachment could not be read.")
        if len(email.pdf_attachments) > 1:
            not_run.append("PDF editing checks cover the first readable PDF attachment only; text was read from up to three attachments.")
        texts.append(email.text)
        not_run.append("Email authenticity: supplied authentication headers and DKIM signatures were not independently validated.")
        return Extraction(text="\n\n".join(texts), method="original-email", pdf=pdf, pdf_data=pdf_data,
                          warnings=warnings, source_checks=[email.evidence], findings=email.findings,
                          sender_emails=email.sender_addresses, checks_not_run=not_run)

    raise ValueError(f"Unsupported file type '{ext}'. Upload a PDF, PNG, JPG, WEBP, TXT or original EML email.")
