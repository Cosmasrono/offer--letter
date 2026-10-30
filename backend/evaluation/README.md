# Real-document evaluation

Create a private JSONL manifest, with one entry for each independently labelled document. The example manifest
points at **fictional** PDFs under `samples/generated`; it demonstrates the runner and does not count as real validation.

Each row needs an anonymous `id`, relative `path`, `label` (`GENUINE` or `SCAM`), `dataset` (`real` or `synthetic`),
and `label_source` explaining who confirmed the outcome. Optional fields are `country` (two-letter code) and
`kind` (`letter` or `message`). Use documents you are authorized to process and anonymize names/identifiers before sharing.
Issuer/employer confirmation is stronger evidence for a genuine label than a document merely looking plausible.

Keep real documents and their manifest in `evaluation/private/`, which is ignored by git. Files must be inside
the selected data root. Duplicate IDs and duplicate document bytes are rejected, so 100 copies cannot count as 100 cases.
Use a separate holdout set when tuning rules; do not measure final performance on the letters used to tune them.

From `backend/`, demonstrate the runner without AI or online lookups:

```powershell
.\.venv\Scripts\python.exe tools/evaluate_real.py evaluation/manifest.example.jsonl --data-root samples/generated --output evaluation/results/smoke.json
```

For the real test set:

```powershell
.\.venv\Scripts\python.exe tools/evaluate_real.py evaluation/private/manifest.jsonl --data-root evaluation/private --output evaluation/results/real-offline.json
```

Add `--online` only when you intend to send the documents to configured OCR/AI providers and use live domain and
company-registry lookups. This mode loads backend `.env` and may incur provider charges. Offline mode disables AI,
WHOIS, website discovery/content, live NEA and Companies House; local Tesseract OCR and the current NEA snapshot are still available.

Results contain anonymous case IDs, scores, source outcomes, timing, confusion matrices split by real/synthetic data,
missed scams scored LOW, genuine letters scored HIGH, borderline cases, warning recall, high-risk precision, and
false-alarm rates. Unreadable files and processing errors are counted separately. Document text, contacts, and letter
contents are excluded. Timing covers backend analysis, not payment, frontend community matching or browser delivery.

The minimum real-sample target is 100 checked, independently labelled real documents with both classes represented.
Synthetic cases never satisfy that target. A reached target is a sample-count check, not a claim that the app is accurate
enough to launch. Review every missed scam, false alarm, unreadable document and unavailable source before deciding.

An expired CoS is not automatically a confirmed scam label: it may be a genuine historical record. Keep unconfirmed
documents out of the labelled benchmark until their outcome has been independently established. Do not label user
uploads solely from the model's prediction or the presence of an expired date.
