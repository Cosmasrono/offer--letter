"""Check public source connectivity without sending a letter, paying, or printing credentials."""

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

import os  # noqa: E402
import ssl  # noqa: E402

from app.nea_live import live_dataset  # noqa: E402
from app.public_web import WebUnavailable, fetch_public  # noqa: E402


def failure_kind(error):
    while error.__cause__ is not None:
        error = error.__cause__
    return f"{type(error).__name__}: {error.verify_message}" if isinstance(error, ssl.SSLCertVerificationError) else type(error).__name__


def main():
    for name in ("COMPANIES_HOUSE_API_KEY", "BRAVE_SEARCH_API_KEY"):
        print(f"{name}: {'configured' if os.getenv(name, '').strip() else 'not configured'}")
    try:
        page = fetch_public("https://example.com/")
        print(f"Public HTTPS reader: reachable ({len(page.text)} characters)")
    except WebUnavailable as error:
        print(f"Public HTTPS reader: unavailable ({error}; {failure_kind(error)})")
    try:
        content, retrieved = live_dataset()
        print(f"NEA live register: parsed {max(0, len(content.splitlines()) - 1)} records; retrieved {retrieved}")
    except WebUnavailable as error:
        print(f"NEA live register: unavailable ({error}; {failure_kind(error)})")


if __name__ == "__main__":
    main()
