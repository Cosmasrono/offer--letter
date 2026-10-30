import logging
import os
import secrets
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from . import ai  # noqa: E402
from .analyzer import analyze_letter  # noqa: E402
from .models import AnalysisReport, Kind  # noqa: E402
from .models import VisaPreview, VisaReview  # noqa: E402
from .visas import analyze_visa, preview_visa  # noqa: E402
from .agencies import DEFAULT_CSV, load_agencies  # noqa: E402
from .nea_dataset import SOURCE_URL, dataset_metadata, import_export  # noqa: E402
from .pdf_report import render_pdf  # noqa: E402
from .memory_assessment import assess_memory  # noqa: E402
from .rules import COUNTRIES  # noqa: E402

logging.basicConfig(level=logging.INFO)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

app = FastAPI(title="Offer Letter Checker API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_api_key(x_api_key: str = Header("")):
    """If BACKEND_API_KEY is set, only callers that send it (the Next.js server) may use the API. Without this, anyone
    who can reach the backend could render an official-looking PDF from made-up report data."""
    expected = os.getenv("BACKEND_API_KEY")
    if expected and not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(401, "Missing or wrong API key.")


def require_maintenance_key(x_api_key: str = Header("")):
    expected = os.getenv("BACKEND_API_KEY")
    if not expected:
        raise HTTPException(503, "Registry maintenance requires a configured backend key.")
    if not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(401, "Missing or wrong API key.")


@app.get("/verification/nea", dependencies=[Depends(require_maintenance_key)])
def nea_status():
    path = Path(os.getenv("NEA_AGENCIES_CSV") or DEFAULT_CSV)
    metadata = dataset_metadata(path)
    try:
        count = len(load_agencies())
    except (OSError, ValueError, UnicodeError):
        count = 0
    return {"records": count, "fresh": bool(count and metadata.get("fresh")),
            "retrieved_at": metadata.get("retrieved_at"), "source_url": SOURCE_URL}


@app.post("/verification/nea", dependencies=[Depends(require_maintenance_key)])
async def update_nea(file: UploadFile = File(...), retrieved_at: str = Form(...)):
    data = await file.read(8_000_001)
    if not data or len(data) > 8_000_000:
        raise HTTPException(400, "Choose an NEA HTML or CSV export smaller than 8 MB.")
    destination = Path(os.getenv("NEA_AGENCIES_CSV") or DEFAULT_CSV)
    try:
        def save():
            with tempfile.TemporaryDirectory(prefix="nea-import-") as directory:
                source = Path(directory) / "export.html"
                source.write_bytes(data)
                return import_export(source, destination, retrieved_at=retrieved_at)
        metadata = await run_in_threadpool(save)
    except (ValueError, UnicodeError) as error:
        raise HTTPException(400, str(error)) from error
    except OSError as error:
        raise HTTPException(503, "The NEA dataset could not be saved. The import must be retried.") from error
    return {"records": metadata["records"], "retrieved_at": metadata["retrieved_at"],
            "source_url": SOURCE_URL, "fresh": dataset_metadata(destination).get("fresh", False)}


@app.get("/health")
def health():
    return {"status": "ok", "ai_enabled": ai.is_enabled()}


@app.get("/countries")
def countries():
    return [{"code": c.code, "name": c.name} for c in COUNTRIES.values()]


@app.post("/analyze", response_model=AnalysisReport, dependencies=[Depends(require_api_key)])
async def analyze(
    file: UploadFile = File(...),
    country: str | None = Form(None),
    # "letter" for an offer letter, "message" for a job ad / SMS / chat message (pasted text or a screenshot).
    kind: Kind = Form("letter"),
    offer_file: UploadFile | None = File(None),
    visa_review: str | None = Form(None),
):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is too large. The limit is 10 MB.")
    try:
        if kind == "visa":
            from pydantic import ValidationError
            try:
                if not visa_review or len(visa_review) > 20_000:
                    raise ValueError("Review the extracted visa details before checking.")
                review = VisaReview.model_validate_json(visa_review)
            except (ValidationError, ValueError) as error:
                raise HTTPException(422, "Review the extracted visa details before checking.") from error
            offer_data = await offer_file.read(MAX_UPLOAD_BYTES + 1) if offer_file else None
            if offer_data is not None and (not offer_data or len(offer_data) > MAX_UPLOAD_BYTES):
                raise HTTPException(413, "Choose a non-empty offer smaller than 10 MB.")
            return await run_in_threadpool(analyze_visa, data, file.filename or "visa", country or "", review,
                                           offer_data, offer_file.filename if offer_file else None)
        if offer_file is not None or visa_review is not None:
            raise HTTPException(422, "Offer comparison is available for visa checks only.")
        # Analysis does blocking work (PDF parsing, WHOIS, Claude), so keep it off the event loop.
        report = await run_in_threadpool(analyze_letter, data, file.filename or "letter", country, kind)
        if not report.text_excerpt.strip():
            raise HTTPException(422, {"code": "DOCUMENT_NOT_CHECKED", "message": "Not checked — no readable text was found. Upload a clearer photo, the original PDF or original EML email."})
        return report
    except ValueError as e:
        raise HTTPException(422, {"code": "DOCUMENT_NOT_CHECKED", "message": "Not checked — the document could not be recognized or read. Use a supported, readable file."}) from e


@app.post("/visa/preview", response_model=VisaPreview, dependencies=[Depends(require_api_key)])
async def visa_preview(file: UploadFile = File(...), country: str = Form(...), offer_file: UploadFile | None = File(None)):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    offer_data = await offer_file.read(MAX_UPLOAD_BYTES + 1) if offer_file else None
    if not data or len(data) > MAX_UPLOAD_BYTES or offer_data is not None and (not offer_data or len(offer_data) > MAX_UPLOAD_BYTES):
        raise HTTPException(413, "Choose non-empty documents smaller than 10 MB each.")
    try:
        return await run_in_threadpool(preview_visa, data, file.filename or "visa", country, offer_data, offer_file.filename if offer_file else None)
    except ValueError as error:
        raise HTTPException(422, "Not checked — supported visa or offer fields could not be read.") from error


class PdfRequest(BaseModel):
    report: AnalysisReport
    report_id: str
    checked_at: str  # already formatted for display, e.g. "17 Oct 2026, 08:05"
    report_url: str | None = None


@app.post("/assess-memory", dependencies=[Depends(require_maintenance_key)])
async def assess_saved_case_context(report: AnalysisReport):
    """Server-to-server context assessment. Historical letter text is never sent or returned."""
    return await run_in_threadpool(assess_memory, report)


@app.post("/report-pdf", dependencies=[Depends(require_api_key)])
async def report_pdf(body: PdfRequest):
    """Render a saved report as a PDF. Called by the frontend after the download has been paid for."""
    pdf = await run_in_threadpool(render_pdf, body.report, body.report_id, body.checked_at, body.report_url)
    return Response(content=pdf, media_type="application/pdf")
