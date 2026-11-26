"""Stable sparse character features and retrieval across distinct part numbers."""

from collections import Counter
from dataclasses import dataclass
from hashlib import blake2b
from math import sqrt
from unicodedata import normalize


@dataclass(frozen=True)
class PlateVector:
    counts: dict[int, int]
    norm: float


@dataclass(frozen=True)
class ReferenceAlias:
    record_id: str
    plate_text: str
    part_number: str
    vector: PlateVector


@dataclass(frozen=True)
class Match:
    alias: ReferenceAlias
    score: float


def normalize_text(text: str) -> str:
    """Fold widths and case, retain letters and numbers, including leading zeros."""
    return "".join(char for char in normalize("NFKC", text).casefold() if char.isalnum())


def hash_plate(normalized: str, dimension: int, max_ngram: int) -> PlateVector:
    # These markers are outside the normalized alphabet and distinguish plate edges.
    padded = f"^{normalized}$"
    counts: Counter[int] = Counter()
    for size in range(2, max_ngram + 1):
        for offset in range(len(padded) - size + 1):
            gram = padded[offset:offset + size].encode("utf-8")
            digest = blake2b(gram, digest_size=8).digest()
            bucket = int.from_bytes(digest, byteorder="big") % dimension
            counts[bucket] += 1
    return PlateVector(dict(counts), sqrt(sum(count * count for count in counts.values())))


def cosine(left: PlateVector, right: PlateVector) -> float:
    if not left.norm or not right.norm:
        return 0.0
    if left.counts == right.counts:
        return 1.0
    if len(left.counts) > len(right.counts):
        left, right = right, left
    dot = sum(count * right.counts.get(bucket, 0) for bucket, count in left.counts.items())
    return min(1.0, dot / (left.norm * right.norm))


def rank_parts(query: PlateVector, aliases: list[ReferenceAlias]) -> list[Match]:
    best_by_part: dict[str, Match] = {}
    for alias in aliases:
        match = Match(alias, cosine(query, alias.vector))
        previous = best_by_part.get(alias.part_number)
        if previous is None or (-match.score, alias.record_id) < (
            -previous.score, previous.alias.record_id
        ):
            best_by_part[alias.part_number] = match
    return sorted(best_by_part.values(), key=lambda match: (-match.score, match.alias.part_number))
