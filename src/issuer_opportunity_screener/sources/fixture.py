"""Deterministic synthetic credit data for development and tests.

Roles cycle by universe index (idx % 6):
  0 normal, 1 missing CDS, 2 unlisted equity, 3 partial history,
  4 fetch failure, 5 tight-vs-Brazil investment grade.
"""
from __future__ import annotations

import datetime as dt

from issuer_opportunity_screener.log import get_logger
from issuer_opportunity_screener.sources.base import (
    BondSnapshot,
    BrazilBenchmark,
    EquityOverlay,
    FetchResult,
    HistoryPoint,
    IssuerCredit,
    UniverseIssuer,
)

log = get_logger("fixture")

FIXTURE_BRAZIL = BrazilBenchmark(cds_5y_bps=180.0, z_spread_bps=195.0, rating_sp="BB")
FIXTURE_AS_OF = dt.datetime(2026, 7, 15, 12, 0, 0)

_RATINGS = ["BB+", "BB", "BB-", "B+"]
_MOODY = {"BBB+": "Baa1", "BB+": "Ba1", "BB": "Ba2", "BB-": "Ba3", "B+": "B1"}


class FixtureSource:
    name = "fixture"

    def fetch(self, issuers: list[UniverseIssuer]) -> FetchResult:
        log.step(f"generating deterministic synthetic data for {len(issuers)} issuers")
        credits: list[IssuerCredit] = []
        history: list[HistoryPoint] = []
        failures: dict[str, str] = {}

        for idx, u in enumerate(issuers):
            role = idx % 6
            if role == 4:
                failures[u.ticker] = "fixture: simulated reference-data failure"
                continue

            base = 90.0 + (idx * 37) % 320  # 90..409 bps, deterministic
            if role == 5:
                base = 140.0  # tighter than Brazil's 180
            rating = "BBB+" if role == 5 else _RATINGS[idx % len(_RATINGS)]

            credit = IssuerCredit(
                ticker=u.ticker,
                cds_5y_bps=None if role == 1 else base,
                cds_liquidity_score=None if role == 1 else 40.0 + (idx * 13) % 60,
                bond=BondSnapshot(
                    security=f"{u.ticker} 5.5 2031 Corp",
                    z_spread_bps=base + 15.0,
                    last_price=97.5 - (idx % 7),
                    maturity=dt.date(2031, 6, 15),
                    coupon=5.5,
                ),
                rating_moody=_MOODY[rating],
                rating_sp=rating,
                rating_fitch=rating,
                equity=(
                    EquityOverlay()
                    if role == 2
                    else EquityOverlay(
                        equity_ticker=f"{u.ticker} US Equity",
                        price_change_3m_pct=-10.0 + (idx * 7) % 25,
                        price_change_12m_pct=-20.0 + (idx * 11) % 55,
                        recommendation_balance=round(-1.0 + 2.0 * ((idx * 3) % 11) / 10, 2),
                    )
                ),
            )
            if role == 1:
                credit.quality_notes.append("no liquid CDS quote; using bond z-spread")
            if role == 2:
                credit.quality_notes.append("no listed equity; equity overlay skipped")
            credits.append(credit)

            instrument = "bond" if role == 1 else "cds"
            points = 8 if role == 3 else 52
            if role == 3:
                credit.quality_notes.append("partial spread history (8 weekly points)")
            for week in range(points):
                wobble = 0.80 + 0.40 * ((week * (idx + 3)) % 10) / 10.0
                history.append(
                    HistoryPoint(
                        ticker=u.ticker,
                        date=FIXTURE_AS_OF.date() - dt.timedelta(weeks=points - week),
                        spread_bps=round(base * wobble, 2),
                        instrument=instrument,
                    )
                )

        return FetchResult(
            as_of=FIXTURE_AS_OF,
            source=self.name,
            issuers=credits,
            history=history,
            brazil=FIXTURE_BRAZIL,
            failures=failures,
        )
