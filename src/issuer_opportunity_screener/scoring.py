"""Composite scoring per docs/methodology/screening_criteria_v1.typ.

This module is pure: it never touches Bloomberg or disk. Task 7 adds the
snapshot-level scoring entry points.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

RATING_ORDER = [
    "AAA", "AA+", "AA", "AA-", "A+", "A", "A-",
    "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
    "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C", "D",
]
RATING_RANKS = {r: i for i, r in enumerate(RATING_ORDER)}
MOODY_TO_SP = {
    "AAA": "AAA", "AA1": "AA+", "AA2": "AA", "AA3": "AA-",
    "A1": "A+", "A2": "A", "A3": "A-",
    "BAA1": "BBB+", "BAA2": "BBB", "BAA3": "BBB-",
    "BA1": "BB+", "BA2": "BB", "BA3": "BB-",
    "B1": "B+", "B2": "B", "B3": "B-",
    "CAA1": "CCC+", "CAA2": "CCC", "CAA3": "CCC-",
    "CA": "CC", "C": "C",
}
MIN_HISTORY_POINTS = 12
VIABILITY_TOLERANCE_BPS = 20.0


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def normalize_rating(raw: str | None) -> str | None:
    if not raw:
        return None
    token = re.split(r"[\s(]", raw.strip())[0].upper().rstrip("U")
    token = MOODY_TO_SP.get(token, token)
    return token if token in RATING_RANKS else None


def rating_rank(rating: str | None) -> int | None:
    normalized = normalize_rating(rating)
    return RATING_RANKS.get(normalized) if normalized else None


def composite_rating_rank(moody: str | None, sp: str | None, fitch: str | None) -> int | None:
    ranks = [r for r in (rating_rank(moody), rating_rank(sp), rating_rank(fitch)) if r is not None]
    if not ranks:
        return None
    return round(statistics.median(ranks))


def rating_score(rank: int | None) -> float | None:
    if rank is None:
        return None
    return clamp(100.0 - rank * (100.0 / 21.0))


def viability(
    spread_bps: float | None,
    issuer_rank: int | None,
    brazil_cds_bps: float | None,
    brazil_rank: int | None,
) -> tuple[float | None, bool]:
    if spread_bps is None or brazil_cds_bps is None:
        return None, False
    diff = spread_bps - brazil_cds_bps
    if diff >= 0:
        return diff, True
    if diff >= -VIABILITY_TOLERANCE_BPS and issuer_rank is not None and brazil_rank is not None:
        return diff, issuer_rank < brazil_rank
    return diff, False


# --- Block 1: Credit and Spread Attractiveness -------------------------------

def spread_level_score(spread_bps: float | None) -> float | None:
    if spread_bps is None:
        return None
    return clamp(spread_bps / 6.0)


def history_percentile_score(spread_bps: float | None, history: list[float]) -> float | None:
    if spread_bps is None or len(history) < MIN_HISTORY_POINTS:
        return None
    below_or_equal = sum(1 for h in history if h <= spread_bps)
    return clamp(100.0 * below_or_equal / len(history))


def vs_ma_score(spread_bps: float | None, history: list[float]) -> float | None:
    if spread_bps is None or not history:
        return None
    mean = statistics.fmean(history)
    if mean <= 0:
        return None
    return clamp(50.0 * spread_bps / mean)


def vs_p75_score(spread_bps: float | None, history: list[float]) -> float | None:
    if spread_bps is None or not history:
        return None
    p75 = statistics.quantiles(history, n=4)[-1] if len(history) > 1 else history[0]
    if p75 <= 0:
        return None
    return clamp(100.0 * spread_bps / p75)


def peer_median_score(spread_bps: float | None, peer_median_bps: float | None) -> float | None:
    if spread_bps is None or peer_median_bps is None or peer_median_bps <= 0:
        return None
    return clamp(50.0 + 50.0 * (spread_bps - peer_median_bps) / peer_median_bps)


# --- Breakdown containers -----------------------------------------------------

@dataclass(frozen=True)
class SignalScore:
    name: str
    raw: float | None
    score: float | None


@dataclass(frozen=True)
class BlockScore:
    name: str
    weight: float
    score: float | None
    signals: list[SignalScore]


def block_score(signals: list[SignalScore]) -> float | None:
    scores = [s.score for s in signals if s.score is not None]
    return statistics.fmean(scores) if scores else None
