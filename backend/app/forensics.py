"""Look inside the PDF file itself for signs it was edited or made with consumer tools."""

import re

import pymupdf

from .models import Finding

ONLINE_EDITORS = re.compile(
    r"ilovepdf|smallpdf|sejda|pdfescape|pdffiller|dochub|pdf ?candy|soda ?pdf|pdf2go|sodapdf|"
    r"online2pdf|pdf ?editor|inkscape|photoshop|gimp|camscanner",
    re.I,
)
DESIGN_TOOLS = re.compile(r"canva|picsart|wps", re.I)


def pdf_findings(doc: pymupdf.Document, raw: bytes) -> list[Finding]:
    findings: list[Finding] = []
    meta = {k: (v or "") for k, v in (doc.metadata or {}).items()}
    tools = f"{meta.get('producer', '')} {meta.get('creator', '')}".strip()

    if m := ONLINE_EDITORS.search(tools):
        findings.append(Finding(
            id="edited_with_editor", title="PDF made or changed with an editing tool",
            detail=f"The file metadata shows \"{m.group(0)}\". Official HR systems rarely produce letters this way, "
            "and these tools are often used to alter real documents.",
            severity="medium", category="document", points=12,
        ))
    elif m := DESIGN_TOOLS.search(tools):
        findings.append(Finding(
            id="design_tool", title="Created with a design app",
            detail=f"The letter was made in \"{m.group(0)}\". That's unusual for a large employer's HR department.",
            severity="low", category="document", points=5,
        ))

    if not tools and not meta.get("creationDate"):
        findings.append(Finding(
            id="metadata_stripped", title="File information removed",
            detail="The PDF has no creator or date information. This is sometimes done to hide editing.",
            severity="low", category="document", points=4,
        ))

    created, modified = meta.get("creationDate", ""), meta.get("modDate", "")
    if created and modified and modified[:16] != created[:16]:
        findings.append(Finding(
            id="modified_after_creation", title="Modified after it was created",
            detail=f"Created {_fmt(created)}, last modified {_fmt(modified)}.",
            severity="low", category="document", points=5,
        ))

    # Each incremental save appends a new %%EOF marker - several means the file was edited and re-saved.
    if raw.count(b"%%EOF") > 1:
        findings.append(Finding(
            id="incremental_updates", title="Edited and re-saved",
            detail=f"The PDF contains {raw.count(b'%%EOF')} save layers, which means content was changed after the original was made.",
            severity="medium", category="document", points=8,
        ))

    fonts = {f[3].split("+")[-1].split("-")[0] for page in doc for f in page.get_fonts()}
    if len(fonts) > 6:
        findings.append(Finding(
            id="many_fonts", title="Many different fonts",
            detail=f"{len(fonts)} font families are used. Mixed fonts can mean text was pasted in from elsewhere.",
            severity="low", category="document", points=4,
        ))

    if doc.page_count and all(not page.get_text().strip() for page in doc):
        findings.append(Finding(
            id="image_only_pdf", title="Letter is only an image",
            detail="The PDF is a picture with no real text. It may be a scan, or a screenshot of an edited letter.",
            severity="low", category="document", points=3,
        ))
    return findings


def _fmt(pdf_date: str) -> str:
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?", pdf_date)
    if not m:
        return pdf_date
    y, mo, d, h, mi = m.groups()
    return f"{y}-{mo}-{d}" + (f" {h}:{mi or '00'}" if h else "")
