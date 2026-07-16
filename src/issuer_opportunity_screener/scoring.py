"""Composite scoring per docs/methodology/screening_criteria_v1.typ.

This module is pure: it never touches Bloomberg or disk. Task 7 adds the
snapshot-level scoring entry points.
"""
from __future__ import annotations

import json
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


def composite_rating_rank_any(ratings: dict[str, str] | None) -> int | None:
    """Median rank across every rating the sources produced, whoever the
    provider is. Unrecognized values are simply skipped."""
    if not ratings:
        return None
    ranks = [r for r in (rating_rank(value) for value in ratings.values()) if r is not None]
    if not ranks:
        return None
    return round(statistics.median(ranks))


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


def _tier(composite: float) -> str:
    if composite >= 70.0:
        return "A"
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


def score_snapshot(snap: Snapshot) -> list[IssuerScore]:
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

    brazil_cds = float(snap.manifest["brazil"]["cds_5y_bps"])
    brazil_rank = rating_rank(snap.manifest["brazil"]["rating_sp"])

    scores: list[IssuerScore] = []
    for row in frame.itertuples():
        spread = primary[row.ticker]
        if spread is None:
            continue
        history = history_by_ticker.get(row.ticker, [])
        ratings = _row_ratings(row)
        ext_rank = composite_rating_rank_any(ratings)
        peer = peer_medians[row.ticker]

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
        peer_s = peer_median_score(spread, peer)
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
                    else f"needs at least {MIN_HISTORY_POINTS} weekly history points, have {n_points}",
                ),
                SignalScore(
                    "vs_1y_ma", spread, ma_s,
                    f"clamp(50 * {spread:.0f} / {ma:.0f}) = {ma_s:.1f} (1y average {ma:.0f} bps)"
                    if ma_s is not None
                    else "no usable 1y history",
                ),
                SignalScore(
                    "vs_1y_p75", spread, p75_s,
                    f"clamp(100 * {spread:.0f} / {p75:.0f}) = {p75_s:.1f} (1y 75th percentile {p75:.0f} bps)"
                    if p75_s is not None
                    else "no usable 1y history",
                ),
                SignalScore(
                    "vs_peer_median", peer, peer_s,
                    f"clamp(50 + 50 * ({spread:.0f} - {peer:.0f}) / {peer:.0f}) = {peer_s:.1f} (basket median {peer:.0f} bps)"
                    if peer_s is not None
                    else "no basket peers with a spread",
                ),
            ],
        )

        internal_rank = rating_rank(row.internal_rating)
        ratings_text = ", ".join(f"{agency}: {value}" for agency, value in ratings.items())
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
        # The desk's edge case needs a rating to compare against Brazil;
        # fall back to the desk-set internal rating when no agency resolves.
        viability_rank = ext_rank if ext_rank is not None else internal_rank
        diff, viable = viability(spread, viability_rank, brazil_cds, brazil_rank)
        partial = any(b.score is None for b in blocks) or bool(row.quality_notes)
        scores.append(
            IssuerScore(
                ticker=row.ticker,
                composite=composite,
                tier=_tier(composite),
                viable=viable,
                spread_vs_brazil_bps=diff,
                partial_data=partial,
                blocks=blocks,
                composite_detail=composite_detail,
                viability_note=viability_explanation(diff, viable, viability_rank, brazil_rank),
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
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "issuer", "ticker", "basket", "tier", "composite", "viable",
                "spread_vs_brazil_bps", "cds_5y_bps", "bond_z_spread_bps",
                "bond_last_price", "rating_composite", "rating_source",
                "internal_rating", "recognition_score", "partial_data",
                "quality_notes", "viability_note",
            ]
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values("composite", ascending=False).reset_index(drop=True)
