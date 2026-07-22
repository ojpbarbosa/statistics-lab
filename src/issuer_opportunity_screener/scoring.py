"""Composite scoring per docs/methodology/screening_criteria_v1.typ.

This module is pure: it never touches Bloomberg or disk. Task 7 adds the
snapshot-level scoring entry points.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import statistics
from dataclasses import dataclass

import pandas as pd

from issuer_opportunity_screener.snapshots import Snapshot

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
SPLIT_RATING_NOTCHES = 3  # providers this far apart are a credit disagreement, not noise
MIN_HISTORY_UNIQUE = 6  # fewer distinct closes than this reads as a stale quote, not a stable one
MIN_PEERS = 3  # a "peer median" off one or two names is not a median
LONG_TENOR_YEARS = 7.0  # bonds beyond this are far from the 5Y CDS standard
WIDE_SPREAD_BPS = 450.0  # wide enough that a negative outlook is a warning, not a bargain
SUBORDINATION_MARKERS = ("subordinat", "junior", "non-preferred", "non preferred", "nonpreferred")
OUTLOOK_SCORES = {"positive": 75.0, "stable": 50.0, "negative": 25.0}
MIN_ISSUE_SIZE_USD = 500_000_000.0  # below this an issue cannot support a note program


def hedged_pickup_bps(
    spread_bps: float | None,
    brazil_bps: float | None,
    hedge_cost_bps: float = 0.0,
) -> float | None:
    """Pickup over Brazil after the cost of hedging the note back to BRL.

    The hedging cost is a desk input (IOS_HEDGE_COST_BPS), not a market
    observation: the screener has no cross-currency basis feed. It exists so the
    ranking can be read in the client's economics rather than in raw USD spread."""
    if spread_bps is None or brazil_bps is None:
        return None
    return spread_bps - brazil_bps - hedge_cost_bps


def hedge_cost_from_env() -> float:
    try:
        return float(os.environ.get("IOS_HEDGE_COST_BPS", "0"))
    except ValueError:
        return 0.0


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def normalize_rating(raw: str | None) -> str | None:
    """Provider-agnostic: S&P/Fitch/KBRA scales pass through, Moody's maps
    across, DBRS '(high)/(low)' become +/-, and decorations are stripped:
    '(P)' provisional prefixes, rating-watch markers like '*-', unsolicited
    'u' suffixes, and outlook text in parentheses."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().upper()
    text = text.removeprefix("(P)").strip()
    text = re.sub(r"\*[+-]?", "", text).strip()
    high_low = re.search(r"\((HIGH|LOW)\)", text)
    if high_low:
        text = text[: high_low.start()].strip()
    token = re.split(r"[\s(]", text)[0].rstrip("U")
    token = MOODY_TO_SP.get(token, token)
    if high_low and token in RATING_RANKS and not token.endswith(("+", "-")):
        token += "+" if high_low.group(1) == "HIGH" else "-"
    return token if token in RATING_RANKS else None


def rating_rank(rating: str | None) -> int | None:
    normalized = normalize_rating(rating)
    return RATING_RANKS.get(normalized) if normalized else None


def _ranks(ratings: dict[str, str] | None) -> list[int]:
    if not ratings:
        return []
    return [r for r in (rating_rank(value) for value in ratings.values()) if r is not None]


def composite_rating_rank_any(ratings: dict[str, str] | None) -> int | None:
    """Median rank across every rating the sources produced, whoever the
    provider is. Unrecognized values are simply skipped.

    An even number of providers puts the median between two notches. We take
    the weaker side (ceil): rounding to even would otherwise flip the tie-break
    direction depending on where the split sits on the scale."""
    ranks = _ranks(ratings)
    if not ranks:
        return None
    return math.ceil(statistics.median(ranks))


def conservative_rating_rank_any(ratings: dict[str, str] | None) -> int | None:
    """The weakest rating any provider assigned. Viability is a risk gate, so it
    reads the conservative side rather than the median."""
    ranks = _ranks(ratings)
    return max(ranks) if ranks else None


def rating_dispersion_notches(ratings: dict[str, str] | None) -> int | None:
    """How far apart the providers are. A wide split is a credit disagreement
    worth surfacing, not something to average away."""
    ranks = _ranks(ratings)
    return max(ranks) - min(ranks) if ranks else None


def rating_outlook(raw: str | None) -> str | None:
    """The outlook or watch direction that normalize_rating strips off, kept as
    its own signal: 'positive', 'negative', 'stable', or None when not stated."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().lower()
    if "*-" in text or "negative" in text or "neg watch" in text or "(neg)" in text:
        return "negative"
    if "*+" in text or "positive" in text or "(pos)" in text:
        return "positive"
    if "stable" in text:
        return "stable"
    return None


def ratings_outlook(ratings: dict[str, str] | None) -> str | None:
    """Worst outlook across providers: one negative watch is the story."""
    outlooks = {rating_outlook(value) for value in (ratings or {}).values()}
    for direction in ("negative", "positive", "stable"):
        if direction in outlooks:
            return direction
    return None


def history_is_stale(history: list[float]) -> bool:
    """A history with almost no distinct closes is an unrefreshed quote, not a
    stable credit. Percentile and moving-average signals are meaningless on it."""
    return len({round(float(h), 4) for h in history}) < MIN_HISTORY_UNIQUE


def years_to_maturity(maturity, as_of) -> float | None:
    """Tenor of the selected bond in years, for comparison against the 5Y CDS
    standard the rest of the screen is built on."""
    if maturity is None or (isinstance(maturity, float) and pd.isna(maturity)):
        return None
    maturity = pd.to_datetime(maturity, errors="coerce")
    as_of = pd.to_datetime(as_of, errors="coerce")
    if pd.isna(maturity) or pd.isna(as_of):
        return None
    return (maturity - as_of).days / 365.25


def is_subordinated(payment_rank: str | None) -> bool:
    """True for anything ranking below senior preferred: subordinated, junior
    subordinated, and bank Sr Non-Preferred. Their spread pickup is structural,
    not a credit view."""
    if not isinstance(payment_rank, str):
        return False
    text = payment_rank.lower()
    return any(marker in text for marker in SUBORDINATION_MARKERS)


def brazil_reference(
    instrument: str,
    brazil_cds_bps: float | None,
    brazil_z_spread_bps: float | None,
) -> tuple[float | None, str, bool]:
    """The Brazil leg to measure this issuer against, matched to the instrument
    its own spread came from. Returns (level, basis label, like-for-like)."""
    if instrument == "bond":
        if brazil_z_spread_bps is not None:
            return brazil_z_spread_bps, "bond z-spread vs Brazil bond z-spread", True
        return (
            brazil_cds_bps,
            "bond z-spread vs Brazil 5Y CDS, indicative only",
            False,
        )
    return brazil_cds_bps, "5Y CDS vs Brazil 5Y CDS", True


def composite_rating_rank(moody: str | None, sp: str | None, fitch: str | None) -> int | None:
    return composite_rating_rank_any(
        {key: value for key, value in (("moody", moody), ("sp", sp), ("fitch", fitch)) if value}
    )


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


def viability_explanation(
    diff: float | None,
    viable: bool,
    issuer_rank: int | None,
    brazil_rank: int | None,
) -> str:
    """Human-readable verdict for the desk: exactly why a name is or is not
    viable under the spread-vs-Brazil rule."""
    brazil_label = RATING_ORDER[brazil_rank] if brazil_rank is not None else "unknown"
    if diff is None:
        return "no spread available, so no viability verdict"
    if diff >= 0:
        return f"spread is {diff:+.0f} bps vs Brazil, at or above the benchmark, so viable"
    if diff < -VIABILITY_TOLERANCE_BPS:
        return (
            f"{diff:+.0f} bps is more than {VIABILITY_TOLERANCE_BPS:.0f} bps through Brazil, so not viable"
        )
    if issuer_rank is None:
        return (
            f"{diff:+.0f} bps is within the {VIABILITY_TOLERANCE_BPS:.0f} bps tolerance, "
            f"but no issuer rating is available to compare against Brazil ({brazil_label}), so not viable"
        )
    issuer_label = RATING_ORDER[issuer_rank]
    if viable:
        return (
            f"{diff:+.0f} bps is within the {VIABILITY_TOLERANCE_BPS:.0f} bps tolerance and rating "
            f"{issuer_label} is stronger than Brazil ({brazil_label}), so viable (edge case)"
        )
    return (
        f"{diff:+.0f} bps is within the {VIABILITY_TOLERANCE_BPS:.0f} bps tolerance, "
        f"but rating {issuer_label} is not stronger than Brazil ({brazil_label}), so not viable"
    )


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


def peer_median_score(
    spread_bps: float | None,
    peer_median_bps: float | None,
    peer_count: int | None = None,
) -> float | None:
    if spread_bps is None or peer_median_bps is None or peer_median_bps <= 0:
        return None
    if peer_count is not None and peer_count < MIN_PEERS:
        return None
    return clamp(50.0 + 50.0 * (spread_bps - peer_median_bps) / peer_median_bps)


# --- Breakdown containers -----------------------------------------------------

@dataclass(frozen=True)
class SignalScore:
    name: str
    raw: float | None
    score: float | None
    detail: str | None = None  # plugged-numbers formula, replicable on the terminal


@dataclass(frozen=True)
class BlockScore:
    name: str
    weight: float
    score: float | None
    signals: list[SignalScore]


def block_score(signals: list[SignalScore]) -> float | None:
    scores = [s.score for s in signals if s.score is not None]
    return statistics.fmean(scores) if scores else None


WEIGHTS = {
    "Credit and Spread Attractiveness": 0.35,
    "Credit Quality and Risk": 0.20,
    "Market Liquidity and Accessibility": 0.20,
    "Equity Overlay": 0.10,
    "Recognition and Client Fit": 0.15,
}


@dataclass(frozen=True)
class Flag:
    """A desk-readable warning attached to a scored name."""
    code: str
    message: str


@dataclass(frozen=True)
class IssuerScore:
    ticker: str
    composite: float
    tier: str
    viable: bool
    spread_vs_brazil_bps: float | None
    partial_data: bool
    blocks: list[BlockScore]
    composite_detail: str = ""  # the exact weighted-average arithmetic
    viability_note: str = ""  # why the name is or is not viable vs Brazil
    flags: tuple[Flag, ...] = ()
    coverage: float = 1.0  # share of the block weight that actually scored
    benchmark_basis: str = ""  # which Brazil leg the viability verdict used
    rating_dispersion: int | None = None  # notches between the widest-apart providers


def _tier(composite: float, rated: bool = True) -> str:
    """An unrated name cannot be Tier A. Renormalizing over the blocks that
    scored means a missing rating removes the credit-quality penalty instead of
    applying it, which otherwise promotes exactly the widest, least-known names."""
    if composite >= 70.0:
        return "A" if rated else "B"
    if composite >= 50.0:
        return "B"
    return "C"


def _primary_spread(row) -> float | None:
    if pd.notna(row.cds_5y_bps):
        return float(row.cds_5y_bps)
    if pd.notna(row.bond_z_spread_bps):
        return float(row.bond_z_spread_bps)
    return None


def _opt(value) -> float | None:
    return float(value) if pd.notna(value) else None


def _row_ratings(row) -> dict[str, str]:
    """All ratings the sources produced for this row, provider-agnostic.
    Prefers the ratings_all JSON column; falls back to the three legacy ones."""
    raw = getattr(row, "ratings_all", None)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items() if v}
        except ValueError:
            pass
    return {
        agency: value
        for agency, value in (("moody", row.rating_moody), ("sp", row.rating_sp), ("fitch", row.rating_fitch))
        if isinstance(value, str) and value
    }


def _issuer_flags(
    *,
    row,
    spread: float,
    ratings: dict[str, str],
    ext_rank: int | None,
    internal_rank: int | None,
    outlook: str | None,
    stale: bool,
    raw_history: list[float],
    peer_count: int,
    instrument: str,
    like_for_like: bool,
    viable: bool,
    viability_rank: int | None,
    brazil_cds: float | None,
    brazil_z: float | None,
    brazil_rank: int | None,
    as_of,
) -> tuple[Flag, ...]:
    """Every warning the desk should read before acting on a rank. Each one
    answers "why might this number mean something other than what it looks like"."""
    flags: list[Flag] = []

    if ext_rank is None and internal_rank is None:
        flags.append(Flag(
            "unrated",
            "no agency or internal rating: the credit-quality block is absent, not passed, "
            "so the composite reflects spread and recognition only",
        ))

    dispersion = rating_dispersion_notches(ratings)
    if dispersion is not None and dispersion >= SPLIT_RATING_NOTCHES:
        ranks = {agency: rating_rank(value) for agency, value in ratings.items()}
        spread_text = ", ".join(
            f"{agency} {RATING_ORDER[rank]}" for agency, rank in ranks.items() if rank is not None
        )
        flags.append(Flag(
            "split_rating",
            f"providers disagree by {dispersion} notches ({spread_text}): "
            "viability reads the weakest of them",
        ))

    if stale:
        flags.append(Flag(
            "stale_history",
            f"1y history has fewer than {MIN_HISTORY_UNIQUE} distinct closes over "
            f"{len(raw_history)} points: the quote looks unrefreshed, not stable",
        ))

    if peer_count < MIN_PEERS:
        flags.append(Flag(
            "thin_peers",
            f"only {peer_count} basket peer(s) with a spread: no peer-median comparison",
        ))

    payment_rank = getattr(row, "bond_payment_rank", None)
    if is_subordinated(payment_rank if isinstance(payment_rank, str) else None):
        flags.append(Flag(
            "subordinated",
            f"selected bond ranks {payment_rank}: part of the spread pickup is "
            "structural subordination, not a credit view",
        ))

    if instrument == "bond":
        tenor = years_to_maturity(getattr(row, "bond_maturity", None), as_of)
        if tenor is not None and tenor > LONG_TENOR_YEARS:
            flags.append(Flag(
                "long_tenor",
                f"spread comes from a {tenor:.1f}y bond against a 5Y CDS standard: "
                "some of the pickup is curve, not credit",
            ))

    country = getattr(row, "country", None)
    state_linked = bool(getattr(row, "state_linked", False))
    if (isinstance(country, str) and country.strip().lower() == "brazil") or state_linked:
        reason = "domiciled in Brazil" if not state_linked else "state-linked or quasi-sovereign"
        flags.append(Flag(
            "sovereign_correlated",
            f"{reason}: viable versus Brazil is not diversification away from Brazil",
        ))

    amount = getattr(row, "bond_amt_outstanding", None)
    amount = float(amount) if amount is not None and pd.notna(amount) else None
    if amount is not None and amount < MIN_ISSUE_SIZE_USD:
        flags.append(Flag(
            "small_issue",
            f"selected bond has {amount / 1e6:.0f}mm outstanding, below the "
            f"{MIN_ISSUE_SIZE_USD / 1e6:.0f}mm the desk needs for a note program",
        ))

    if outlook == "negative" and spread >= WIDE_SPREAD_BPS:
        flags.append(Flag(
            "cheap_for_a_reason",
            f"{spread:.0f} bps with a negative outlook or watch: wide because the "
            "credit is deteriorating, not because it is overlooked",
        ))

    if not like_for_like:
        flags.append(Flag(
            "benchmark_mismatch",
            "issuer bond z-spread measured against Brazil's 5Y CDS: no sovereign "
            "bond spread available, so the verdict is indicative",
        ))

    other_level = brazil_cds if instrument == "bond" else brazil_z
    if other_level is not None:
        _, other_viable = viability(spread, viability_rank, other_level, brazil_rank)
        if other_viable != viable:
            flags.append(Flag(
                "benchmark_sensitive",
                f"the verdict flips to {'viable' if other_viable else 'not viable'} against "
                "Brazil's other leg: the call rests on which benchmark is used",
            ))

    return tuple(flags)


def score_snapshot(snap: Snapshot, weights: dict[str, float] | None = None) -> list[IssuerScore]:
    """Score every name in a snapshot.

    `weights` overrides the documented block weights, which is what the
    sensitivity analysis in validation.py uses to ask whether the ranking is
    driven by the evidence or by the weighting choice."""
    WEIGHTS = weights or globals()["WEIGHTS"]
    frame = snap.frame
    history_by_ticker = {
        ticker: group.spread_bps.astype(float).tolist()
        for ticker, group in snap.history.groupby("ticker")
    }
    primary = {row.ticker: _primary_spread(row) for row in frame.itertuples()}
    peer_medians: dict[str, float | None] = {}
    for row in frame.itertuples():
        peers = [
            primary[r.ticker]
            for r in frame.itertuples()
            if r.basket == row.basket and r.ticker != row.ticker and primary[r.ticker] is not None
        ]
        peer_medians[row.ticker] = statistics.median(peers) if peers else None

    peer_counts = {
        row.ticker: sum(
            1
            for r in frame.itertuples()
            if r.basket == row.basket and r.ticker != row.ticker and primary[r.ticker] is not None
        )
        for row in frame.itertuples()
    }

    brazil_cds = float(snap.manifest["brazil"]["cds_5y_bps"])
    brazil_z = snap.manifest["brazil"].get("z_spread_bps")
    brazil_rank = rating_rank(snap.manifest["brazil"]["rating_sp"])
    as_of = snap.manifest.get("as_of")

    scores: list[IssuerScore] = []
    for row in frame.itertuples():
        spread = primary[row.ticker]
        if spread is None:
            continue
        raw_history = history_by_ticker.get(row.ticker, [])
        stale = bool(raw_history) and history_is_stale(raw_history)
        # A quote that never moves is unrefreshed, not stable. Percentile and
        # moving-average signals off it would read as confident and be wrong.
        history = [] if stale else raw_history
        ratings = _row_ratings(row)
        ext_rank = composite_rating_rank_any(ratings)
        peer = peer_medians[row.ticker]
        peer_count = peer_counts[row.ticker]

        n_points = len(history)
        points_le = sum(1 for h in history if h <= spread)
        ma = statistics.fmean(history) if history else None
        if len(history) > 1:
            p75 = statistics.quantiles(history, n=4)[-1]
        elif history:
            p75 = history[0]
        else:
            p75 = None

        pct_score = history_percentile_score(spread, history)
        ma_s = vs_ma_score(spread, history)
        p75_s = vs_p75_score(spread, history)
        peer_s = peer_median_score(spread, peer, peer_count=peer_count)
        stale_detail = (
            f"1y history has fewer than {MIN_HISTORY_UNIQUE} distinct closes "
            f"({len(raw_history)} points): stale quote, signal suppressed"
        )
        block1 = BlockScore(
            "Credit and Spread Attractiveness",
            WEIGHTS["Credit and Spread Attractiveness"],
            None,
            [
                SignalScore(
                    "spread_level", spread, spread_level_score(spread),
                    f"min({spread:.0f} bps / 6, 100) = {spread_level_score(spread):.1f}",
                ),
                SignalScore(
                    "history_percentile", spread, pct_score,
                    f"{points_le} of {n_points} weekly closes <= {spread:.0f} bps, so {pct_score:.1f}"
                    if pct_score is not None
                    else stale_detail
                    if stale
                    else f"needs at least {MIN_HISTORY_POINTS} weekly history points, have {n_points}",
                ),
                SignalScore(
                    "vs_1y_ma", spread, ma_s,
                    f"clamp(50 * {spread:.0f} / {ma:.0f}) = {ma_s:.1f} (1y average {ma:.0f} bps)"
                    if ma_s is not None
                    else stale_detail
                    if stale
                    else "no usable 1y history",
                ),
                SignalScore(
                    "vs_1y_p75", spread, p75_s,
                    f"clamp(100 * {spread:.0f} / {p75:.0f}) = {p75_s:.1f} (1y 75th percentile {p75:.0f} bps)"
                    if p75_s is not None
                    else stale_detail
                    if stale
                    else "no usable 1y history",
                ),
                SignalScore(
                    "vs_peer_median", peer, peer_s,
                    f"clamp(50 + 50 * ({spread:.0f} - {peer:.0f}) / {peer:.0f}) = {peer_s:.1f} "
                    f"({peer_count} basket peers, median {peer:.0f} bps)"
                    if peer_s is not None
                    else f"only {peer_count} basket peer(s) with a spread, need {MIN_PEERS} for a median",
                ),
            ],
        )

        internal_rank = rating_rank(row.internal_rating)
        ratings_text = ", ".join(f"{agency}: {value}" for agency, value in ratings.items())
        outlook = ratings_outlook(ratings)
        trend_score = OUTLOOK_SCORES.get(outlook)
        block2 = BlockScore(
            "Credit Quality and Risk",
            WEIGHTS["Credit Quality and Risk"],
            None,
            [
                SignalScore(
                    "external_rating",
                    float(ext_rank) if ext_rank is not None else None,
                    rating_score(ext_rank),
                    f"median of [{ratings_text}] is {RATING_ORDER[ext_rank]} (rank {ext_rank}); 100 - {ext_rank} * 100/21 = {rating_score(ext_rank):.1f}"
                    if ext_rank is not None
                    else "no agency rating resolved from any provider",
                ),
                SignalScore(
                    "internal_rating",
                    float(internal_rank) if internal_rank is not None else None,
                    rating_score(internal_rank),
                    f"{row.internal_rating} (rank {internal_rank}); 100 - {internal_rank} * 100/21 = {rating_score(internal_rank):.1f}"
                    if internal_rank is not None
                    else "not set in universe.csv",
                ),
                SignalScore(
                    "rating_trend", None, trend_score,
                    f"{outlook} outlook or watch across providers, so {trend_score:.0f}"
                    if trend_score is not None
                    else "no outlook or watch stated by any provider",
                ),
            ],
        )

        has_cds = pd.notna(row.cds_5y_bps)
        has_bond = pd.notna(row.bond_security)
        block3 = BlockScore(
            "Market Liquidity and Accessibility",
            WEIGHTS["Market Liquidity and Accessibility"],
            None,
            [
                SignalScore(
                    "cds_available", 1.0 if has_cds else 0.0, 100.0 if has_cds else 0.0,
                    "5Y CDS quote present, so 100" if has_cds else "no 5Y CDS quote, so 0",
                ),
                SignalScore(
                    "cds_liquidity", _opt(row.cds_liquidity_score), _opt(row.cds_liquidity_score),
                    "quote-availability proxy, used as-is",
                ),
                SignalScore(
                    "bond_available", 1.0 if has_bond else 0.0, 100.0 if has_bond else 0.0,
                    "eligible bond selected, so 100" if has_bond else "no eligible bond, so 0",
                ),
            ],
        )

        if pd.isna(row.equity_ticker):
            block4 = BlockScore("Equity Overlay", WEIGHTS["Equity Overlay"], None, [])
        else:
            block4 = BlockScore(
                "Equity Overlay",
                WEIGHTS["Equity Overlay"],
                None,
                [
                    SignalScore(
                        "momentum_3m", _opt(row.px_chg_3m_pct),
                        clamp(50.0 + row.px_chg_3m_pct) if pd.notna(row.px_chg_3m_pct) else None,
                        f"clamp(50 + {row.px_chg_3m_pct:.1f}) = {clamp(50.0 + row.px_chg_3m_pct):.1f}"
                        if pd.notna(row.px_chg_3m_pct)
                        else "3m price change unavailable",
                    ),
                    SignalScore(
                        "momentum_12m", _opt(row.px_chg_12m_pct),
                        clamp(50.0 + row.px_chg_12m_pct / 2.0) if pd.notna(row.px_chg_12m_pct) else None,
                        f"clamp(50 + {row.px_chg_12m_pct:.1f} / 2) = {clamp(50.0 + row.px_chg_12m_pct / 2.0):.1f}"
                        if pd.notna(row.px_chg_12m_pct)
                        else "12m price change unavailable",
                    ),
                    SignalScore(
                        "recommendations", _opt(row.rec_balance),
                        clamp(50.0 + 50.0 * row.rec_balance) if pd.notna(row.rec_balance) else None,
                        f"clamp(50 + 50 * {row.rec_balance:.2f}) = {clamp(50.0 + 50.0 * row.rec_balance):.1f} (buy-sell balance)"
                        if pd.notna(row.rec_balance)
                        else "analyst recommendations unavailable",
                    ),
                ],
            )

        block5 = BlockScore(
            "Recognition and Client Fit",
            WEIGHTS["Recognition and Client Fit"],
            None,
            [
                SignalScore(
                    "recognition", float(row.recognition_score), float(row.recognition_score),
                    "desk-set household-name score from universe.csv, used as-is",
                )
            ],
        )

        blocks = [
            BlockScore(b.name, b.weight, block_score(b.signals) if b.signals else None, b.signals)
            for b in (block1, block2, block3, block4, block5)
        ]
        available = [b for b in blocks if b.score is not None]
        weight_sum = sum(b.weight for b in available)
        composite = round(sum(b.weight * b.score for b in available) / weight_sum, 1)
        composite_detail = (
            "("
            + " + ".join(f"{b.weight:.2f} * {b.score:.1f}" for b in available)
            + f") / {weight_sum:.2f} = {composite:.1f}"
        )
        # The desk's edge case needs a rating to compare against Brazil. The gate
        # reads the conservative side of a split, then falls back to the desk-set
        # internal rating when no agency resolves at all.
        conservative_rank = conservative_rating_rank_any(ratings)
        viability_rank = conservative_rank if conservative_rank is not None else internal_rank
        instrument = "cds" if pd.notna(row.cds_5y_bps) else "bond"
        brazil_level, benchmark_basis, like_for_like = brazil_reference(instrument, brazil_cds, brazil_z)
        diff, viable = viability(spread, viability_rank, brazil_level, brazil_rank)

        flags = _issuer_flags(
            row=row,
            spread=spread,
            ratings=ratings,
            ext_rank=ext_rank,
            internal_rank=internal_rank,
            outlook=outlook,
            stale=stale,
            raw_history=raw_history,
            peer_count=peer_count,
            instrument=instrument,
            like_for_like=like_for_like,
            viable=viable,
            viability_rank=viability_rank,
            brazil_cds=brazil_cds,
            brazil_z=brazil_z,
            brazil_rank=brazil_rank,
            as_of=as_of,
        )
        partial = any(b.score is None for b in blocks) or bool(row.quality_notes)
        scores.append(
            IssuerScore(
                ticker=row.ticker,
                composite=composite,
                tier=_tier(composite, rated=viability_rank is not None),
                viable=viable,
                spread_vs_brazil_bps=diff,
                partial_data=partial,
                blocks=blocks,
                composite_detail=composite_detail,
                viability_note=viability_explanation(diff, viable, viability_rank, brazil_rank),
                flags=flags,
                coverage=round(weight_sum, 4),
                benchmark_basis=benchmark_basis,
                rating_dispersion=rating_dispersion_notches(ratings),
            )
        )
    return scores


def screen_frame(snap: Snapshot, scores: list[IssuerScore]) -> pd.DataFrame:
    by_ticker = {s.ticker: s for s in scores}
    rows = []
    for row in snap.frame.itertuples():
        score = by_ticker.get(row.ticker)
        if score is None:
            continue
        ratings = _row_ratings(row)
        ext_rank = composite_rating_rank_any(ratings)
        rows.append(
            {
                "issuer": row.issuer,
                "ticker": row.ticker,
                "basket": row.basket,
                "country": getattr(row, "country", None),
                "sector": getattr(row, "sector", None),
                "tier": score.tier,
                "composite": score.composite,
                "viable": score.viable,
                "spread_vs_brazil_bps": score.spread_vs_brazil_bps,
                "cds_5y_bps": _opt(row.cds_5y_bps),
                "bond_z_spread_bps": _opt(row.bond_z_spread_bps),
                "bond_last_price": _opt(row.bond_last_price),
                "rating_composite": RATING_ORDER[ext_rank] if ext_rank is not None else None,
                "rating_source": ", ".join(ratings) if ratings else None,
                "internal_rating": row.internal_rating if pd.notna(row.internal_rating) else None,
                "recognition_score": float(row.recognition_score),
                "partial_data": score.partial_data,
                "quality_notes": row.quality_notes,
                "viability_note": score.viability_note,
                "flag_codes": ", ".join(f.code for f in score.flags),
                "flag_notes": "; ".join(f.message for f in score.flags),
                "coverage": score.coverage,
                "benchmark_basis": score.benchmark_basis,
                "rating_dispersion": score.rating_dispersion,
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "issuer", "ticker", "basket", "country", "sector", "tier", "composite", "viable",
                "spread_vs_brazil_bps", "cds_5y_bps", "bond_z_spread_bps",
                "bond_last_price", "rating_composite", "rating_source",
                "internal_rating", "recognition_score", "partial_data",
                "quality_notes", "viability_note", "flag_codes", "flag_notes",
                "coverage", "benchmark_basis", "rating_dispersion",
            ]
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values("composite", ascending=False).reset_index(drop=True)
