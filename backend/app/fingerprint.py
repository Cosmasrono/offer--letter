"""Fingerprint a letter's wording so a reused scam template is recognised even when names and numbers change.

The text is normalised (names of people stay, but emails, links, phone numbers and amounts become placeholders),
cut into overlapping 5-word shingles and summarised with MinHash: 64 numbers where the share of equal positions
between two letters estimates how much of their wording they share. The 64 numbers are also grouped into 32
"bands"; letters sharing any band are candidates, so the database can look them up with an index instead of
comparing every stored template.

Similarity is computed by the frontend (frontend/lib/reports.ts) when it compares a letter with stored templates.
"""

import hashlib
import random
import re

from .entities import EMAIL_RE, MONEY_RE, PHONE_RE, URL_RE
from .models import Fingerprint

NUM_HASHES = 64
BAND_SIZE = 2
SHINGLE_WORDS = 5
MIN_WORDS = 40  # shorter texts are too generic to fingerprint
_PRIME = (1 << 61) - 1
# Fixed seed: fingerprints must stay comparable across servers and restarts. Changing it invalidates stored templates.
_rng = random.Random(20261017)
_PERMUTATIONS = [(_rng.randrange(1, _PRIME), _rng.randrange(0, _PRIME)) for _ in range(NUM_HASHES)]


def _normalise(text: str) -> list[str]:
    text = EMAIL_RE.sub(" email ", text)
    text = URL_RE.sub(" link ", text)
    text = PHONE_RE.sub(" phone ", text)
    text = MONEY_RE.sub(" amount ", text)
    text = re.sub(r"\d+", " num ", text)
    return re.findall(r"[a-z]+", text.lower())


def _hash64(value: str) -> int:
    return int.from_bytes(hashlib.blake2b(value.encode(), digest_size=8).digest(), "big")


def fingerprint(text: str) -> Fingerprint | None:
    words = _normalise(text)
    if len(words) < MIN_WORDS:
        return None
    shingles = {_hash64(" ".join(words[i: i + SHINGLE_WORDS])) for i in range(len(words) - SHINGLE_WORDS + 1)}
    # Kept below 2^31 so the values fit a 32-bit Int in the database and are exact in JavaScript.
    signature = [min((a * s + b) % _PRIME for s in shingles) & 0x7FFFFFFF for a, b in _PERMUTATIONS]
    bands = [
        f"{i}:{hashlib.blake2b(repr(signature[i * BAND_SIZE:(i + 1) * BAND_SIZE]).encode(), digest_size=6).hexdigest()}"
        for i in range(NUM_HASHES // BAND_SIZE)
    ]
    return Fingerprint(signature=signature, bands=bands)


def similarity(a: list[int], b: list[int]) -> float:
    return sum(x == y for x, y in zip(a, b)) / NUM_HASHES
