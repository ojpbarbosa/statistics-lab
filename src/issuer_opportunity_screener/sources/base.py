"""Shared datatypes and the CreditDataSource protocol.

Every adapter (bloomberg, fixture) returns these types. Anything a source
cannot provide is None plus, when meaningful, an entry in quality_notes.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class UniverseIssuer:
    issuer: str
    ticker: str
    basket: str
    country: str
    sector: str
    recognition_score: float
    internal_rating: str | None = None
    equity_ticker: str | None = None  # explicit Bloomberg handle, e.g. "ABI BB Equity"
    cds_ticker: str | None = None  # explicit CDS handle when the derived convention fails


@dataclass
class BondSnapshot:
    security: str | None = None
    z_spread_bps: float | None = None
    last_price: float | None = None
    maturity: dt.date | None = None
    coupon: float | None = None


@dataclass
class EquityOverlay:
    equity_ticker: str | None = None
    price_change_3m_pct: float | None = None
    price_change_12m_pct: float | None = None
    recommendation_balance: float | None = None  # -1 (all sells) .. 1 (all buys)


@dataclass
class IssuerCredit:
    ticker: str
    cds_5y_bps: float | None = None
    cds_liquidity_score: float | None = None  # 0-100 proxy
    cds_security: str | None = None  # the resolved Bloomberg CDS handle
    bond: BondSnapshot = field(default_factory=BondSnapshot)
    rating_moody: str | None = None
    rating_sp: str | None = None
    rating_fitch: str | None = None
    ratings: dict[str, str] = field(default_factory=dict)  # agency key -> raw value, any provider
    equity: EquityOverlay = field(default_factory=EquityOverlay)
    quality_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HistoryPoint:
    ticker: str
    date: dt.date
    spread_bps: float
    instrument: str  # "cds" | "bond"


@dataclass(frozen=True)
class BrazilBenchmark:
    cds_5y_bps: float
    z_spread_bps: float | None
    rating_sp: str


@dataclass
class FetchResult:
    as_of: dt.datetime
    source: str  # "bloomberg" | "fixture"
    issuers: list[IssuerCredit]
    history: list[HistoryPoint]
    brazil: BrazilBenchmark
    failures: dict[str, str] = field(default_factory=dict)  # ticker -> reason


class BloombergUnavailable(RuntimeError):
    """Raised when no Bloomberg Terminal session can be established."""


class CreditDataSource(Protocol):
    name: str

    def fetch(self, issuers: list[UniverseIssuer]) -> FetchResult: ...
