"""Import an official NEA HTML/CSV export without fabricating data or overwriting on parse errors."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.nea_dataset import import_export  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="HTML or CSV saved from the official NEA register")
    parser.add_argument("--retrieved-at", required=True, help="When it was fetched, e.g. 2026-10-26T10:00:00+00:00")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "nea_agencies.csv")
    args = parser.parse_args()
    try:
        metadata = import_export(args.source, args.output, retrieved_at=args.retrieved_at)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    print(f"Imported {metadata['records']} agencies; source retrieved {metadata['retrieved_at']}.")
    print(f"Saved {args.output} and its provenance metadata. Refresh within 30 days.")


if __name__ == "__main__":
    main()
