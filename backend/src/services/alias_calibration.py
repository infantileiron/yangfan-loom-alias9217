"""Calibrate per-manufacturer merge thresholds by leaving out one source batch at a time."""

from collections import defaultdict
from math import isclose

from .alias_features import ReferenceAlias, hash_plate, rank_parts
from .alias_validation import validate_history

MAX_FALSE_ATTACH = 0.05
SCORE_GRID = [round(0.30 + 0.05 * step, 2) for step in range(14)]
MARGIN_GRID = [round(0.02 * step, 2) for step in range(16)]


def _decision(ranked, min_score, min_margin):
    """Replicate the merge gate: return the proposed part number or None."""
    first = ranked[0] if ranked else None
    if first is None or first.score < min_score:
        return None
    if len(ranked) > 1:
        margin = first.score - ranked[1].score
        if isclose(margin, 0, abs_tol=1e-12) or margin < min_margin:
            return None
    return first.alias.part_number


def _samples(records, settings):
    """Score each signed-off plate against the pool that remains after exclusions."""
    aliases = {}
    vectors = {}
    for record in records:
        vectors[record.record_id] = hash_plate(record.normalized_plate, settings.dimension, settings.max_ngram)
        aliases[record.record_id] = ReferenceAlias(
            record.record_id, record.plate_text, record.part_number, vectors[record.record_id]
        )
    known, simulated = [], []
    skipped_known = skipped_new = 0
    for record in records:
        pool = [
            aliases[other.record_id] for other in records
            if other.batch_id != record.batch_id and other.normalized_plate != record.normalized_plate
        ]
        if any(alias.part_number == record.part_number for alias in pool):
            known.append((record.part_number, rank_parts(vectors[record.record_id], pool)))
        else:
            skipped_known += 1
        novel = [alias for alias in pool if alias.part_number != record.part_number]
        if novel:
            simulated.append(rank_parts(vectors[record.record_id], novel))
        else:
            skipped_new += 1
    return known, simulated, skipped_known, skipped_new


def _fit(known, simulated):
    """Pick the threshold pair that recognizes the most known plates within the false-attach cap."""
    best = None
    for min_score in SCORE_GRID:
        for min_margin in MARGIN_GRID:
            correct = sum(1 for truth, ranked in known if _decision(ranked, min_score, min_margin) == truth)
            attached = sum(1 for ranked in simulated if _decision(ranked, min_score, min_margin) is not None)
            rate = attached / len(simulated)
            if rate > MAX_FALSE_ATTACH:
                continue
            candidate = (correct, -rate, min_score, min_margin)
            if best is None or candidate > best[0]:
                best = candidate, correct, attached, rate
    return best


def calibrate(rows, settings):
    """Evaluate every manufacturer, then hand back one release decision per manufacturer."""
    history = validate_history(rows)
    by_manufacturer: dict[str, list] = defaultdict(list)
    for record in history:
        by_manufacturer[record.manufacturer_key].append(record)
    manufacturers = {}
    for key in sorted(by_manufacturer, key=lambda item: by_manufacturer[item][0].manufacturer):
        records = by_manufacturer[key]
        known, simulated, skipped_known, skipped_new = _samples(records, settings)
        entry = {
            "manufacturer": records[0].manufacturer,
            "aliases": len(records),
            "batches": len({record.batch_id for record in records}),
            "known_usable": len(known),
            "known_skipped": skipped_known,
            "new_usable": len(simulated),
            "new_skipped": skipped_new,
        }
        if not known or not simulated:
            missing = "、".join(label for label, empty in (("已知", not known), ("新件号模拟", not simulated)) if empty)
            entry.update(released=False, reason=f"缺少可用{missing}样本")
        else:
            fit = _fit(known, simulated)
            if fit is None:
                entry.update(released=False, reason=f"模拟新件号误挂率无法压到 {MAX_FALSE_ATTACH:.0%} 以内")
            else:
                (_, _, min_score, min_margin), correct, attached, rate = fit
                entry.update(
                    released=True, min_score=min_score, min_margin=min_margin,
                    known_correct=correct, new_attached=attached,
                    false_attach_rate=round(rate, 6), reason="",
                )
        manufacturers[key] = entry
    return {
        "max_false_attach": MAX_FALSE_ATTACH,
        "score_grid": SCORE_GRID,
        "margin_grid": MARGIN_GRID,
        "manufacturers": manufacturers,
    }
