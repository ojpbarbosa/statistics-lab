"""Hermes (XP treasury) internal API as a credit data source.

Hermes serves historical BBG bond EoD data over
GET {base}/v1/BBG/Bonds/{start}/{end} with a Bearer token. Today it carries
bonds only (no CDS, ratings, or equity), keyed by ISIN, so:

- issuers are matched through the optional `isin` column in universe.csv;
- the bond yield is solved from the clean EoD mid (semiannual convention);
- the spread is a G-spread proxy anchored on the Brazil benchmark bond:
  brazil_spread + (issuer_ytm - brazil_ytm), which preserves the
  spread-vs-Brazil comparison the viability rule needs;
- every payload date where both the issuer and Brazil bonds price becomes a
  history point, so a long lookback window doubles as spread history.

Config (read by `HermesSource.from_env`):
- IOS_HERMES_URL    base URL (default https://hermes-api.xptreasury.com.br)
- IOS_HERMES_TOKEN  Bearer token (required)
- IOS_HERMES_LOOKBACK_DAYS   request window, default 30
- IOS_HERMES_BRAZIL_ISIN     ISIN of the Brazil sovereign USD benchmark bond
- IOS_HERMES_BRAZIL_SPREAD_BPS  Brazil anchor spread, default 180
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.request
from collections.abc import Callable
from urllib.error import HTTPError, URLError

from issuer_opportunity_screener.log import get_logger
from issuer_opportunity_screener.sources.base import (
    BondSnapshot,
    BrazilBenchmark,
    FetchResult,
    HistoryPoint,
    IssuerCredit,
    UniverseIssuer,
)

log = get_logger("hermes")

DEFAULT_URL = "https://hermes-api.xptreasury.com.br"
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_BRAZIL_SPREAD_BPS = 180.0


class HermesUnavailable(RuntimeError):
    """Hermes cannot be reached or is not configured."""


def _opt_date(value) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _positive(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def clean_price(row: dict) -> float | None:
    """Best usable clean EoD price: clean mid, dirty mid less accrued, or
    the dirty bid/ask midpoint less accrued. Hermes uses 0 for missing."""
    clean = _positive(row.get("cleanMidPriceEoD"))
    if clean is not None:
        return clean
    accrued = float(row.get("intAcc") or 0.0)
    dirty = _positive(row.get("dirtyMidPriceEoD"))
    if dirty is not None:
        return dirty - accrued
    bid, ask = _positive(row.get("dirtyBid")), _positive(row.get("dirtyAsk"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2 - accrued
    return None


def ytm_pct(price: float, coupon_pct: float, maturity: dt.date, asof: dt.date) -> float | None:
    """Semiannual yield to maturity (percent) solved by bisection from a
    clean price per 100 face. Approximate on purpose: settlement accrual and
    day counts are ignored, which cancels out of spreads vs the same-dated
    Brazil benchmark."""
    years = (maturity - asof).days / 365.25
    if years <= 0 or price <= 0:
        return None
    periods = max(1, round(years * 2))
    per_coupon = coupon_pct / 2

    def pv(yield_pct: float) -> float:
        rate = yield_pct / 200
        discount = (1 + rate) ** -periods
        annuity = per_coupon * ((1 - discount) / rate) if rate != 0 else per_coupon * periods
        return annuity + 100 * discount

    low, high = -50.0, 500.0
    if not pv(low) >= price >= pv(high):
        return None
    for _ in range(100):
        mid = (low + high) / 2
        if pv(mid) > price:
            low = mid
        else:
            high = mid
    return (low + high) / 2


class HermesClient:
    """Thin transport wrapper so tests can inject a fake fetcher."""

    def __init__(self, base_url: str, token: str,
                 fetcher: Callable[[str, dict[str, str]], bytes] | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._fetcher = fetcher or self._http_fetch

    @staticmethod
    def _http_fetch(url: str, headers: dict[str, str]) -> bytes:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()

    def fetch_bonds(self, start: dt.date, end: dt.date) -> list[dict]:
        url = f"{self.base_url}/v1/BBG/Bonds/{start.isoformat()}/{end.isoformat()}"
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        log.step(f"GET {url}")
        try:
            payload = json.loads(self._fetcher(url, headers))
        except HTTPError as error:
            raise HermesUnavailable(f"Hermes returned HTTP {error.code} for {url}") from error
        except URLError as error:
            raise HermesUnavailable(f"Hermes unreachable at {url}: {error.reason}") from error
        except json.JSONDecodeError as error:
            raise HermesUnavailable(f"Hermes returned non-JSON for {url}") from error
        if not isinstance(payload, list):
            raise HermesUnavailable(f"Hermes returned unexpected shape for {url}: {type(payload).__name__}")
        return payload


class HermesSource:
    name = "hermes"

    def __init__(self, client: HermesClient, brazil_isin: str | None = None,
                 brazil_spread_bps: float = DEFAULT_BRAZIL_SPREAD_BPS,
                 lookback_days: int = DEFAULT_LOOKBACK_DAYS,
                 today: dt.date | None = None):
        self.client = client
        self.brazil_isin = brazil_isin
        self.brazil_spread_bps = brazil_spread_bps
        self.lookback_days = lookback_days
        self.today = today or dt.date.today()

    @classmethod
    def from_env(cls) -> "HermesSource":
        token = os.environ.get("IOS_HERMES_TOKEN")
        if not token:
            raise HermesUnavailable(
                "IOS_HERMES_TOKEN is not set; export the Hermes Bearer token to use IOS_SOURCE=hermes"
            )
        return cls(
            client=HermesClient(os.environ.get("IOS_HERMES_URL", DEFAULT_URL), token),
            brazil_isin=os.environ.get("IOS_HERMES_BRAZIL_ISIN") or None,
            brazil_spread_bps=float(os.environ.get("IOS_HERMES_BRAZIL_SPREAD_BPS", DEFAULT_BRAZIL_SPREAD_BPS)),
            lookback_days=int(os.environ.get("IOS_HERMES_LOOKBACK_DAYS", DEFAULT_LOOKBACK_DAYS)),
        )

    def fetch(self, issuers: list[UniverseIssuer]) -> FetchResult:
        start = self.today - dt.timedelta(days=self.lookback_days)
        rows = self.client.fetch_bonds(start, self.today)
        log.info(f"{len(rows)} bond rows from Hermes over {start} .. {self.today}")

        # isin -> date -> row (latest request wins within a date)
        by_isin: dict[str, dict[dt.date, dict]] = {}
        for row in rows:
            isin = (row.get("isin") or row.get("symbol") or "").strip()
            date = _opt_date(row.get("requestDate"))
            if isin and date is not None:
                by_isin.setdefault(isin, {})[date] = row

        brazil_yields = self._yields_by_date(by_isin.get(self.brazil_isin or "", {}))
        if self.brazil_isin and not brazil_yields:
            log.warn(f"Brazil benchmark ISIN {self.brazil_isin} not priceable in the Hermes window")

        credits: list[IssuerCredit] = []
        history: list[HistoryPoint] = []
        failures: dict[str, str] = {}
        as_of_date = start
        for issuer in issuers:
            if not issuer.isin:
                failures[issuer.ticker] = "no isin in universe.csv (Hermes matches by ISIN)"
                continue
            dated = by_isin.get(issuer.isin)
            if not dated:
                failures[issuer.ticker] = f"ISIN {issuer.isin} not in the Hermes window"
                continue
            issuer_yields = self._yields_by_date(dated)
            latest_date = max(dated)
            as_of_date = max(as_of_date, latest_date)
            latest = dated[latest_date]

            credit = IssuerCredit(ticker=issuer.ticker)
            credit.bond = BondSnapshot(
                security=issuer.isin,
                last_price=clean_price(latest),
                maturity=_opt_date(latest.get("maturityDate")),
                coupon=_positive(latest.get("coupon")),
            )
            spread_dates = sorted(set(issuer_yields) & set(brazil_yields))
            for date in spread_dates:
                spread = self.brazil_spread_bps + (issuer_yields[date] - brazil_yields[date]) * 100
                history.append(HistoryPoint(issuer.ticker, date, spread, "bond"))
            if spread_dates:
                latest_common = spread_dates[-1]
                credit.bond.z_spread_bps = (
                    self.brazil_spread_bps + (issuer_yields[latest_common] - brazil_yields[latest_common]) * 100
                )
                credit.quality_notes.append(
                    "spread is a G-spread proxy: yield from Hermes clean EoD mid vs the Brazil benchmark bond"
                )
            elif not issuer_yields:
                credit.quality_notes.append("no usable EoD price in the Hermes window")
            else:
                credit.quality_notes.append("no Brazil benchmark yield to anchor the spread")
            credit.quality_notes.append("Hermes carries bonds only: no CDS, ratings, or equity yet")
            credits.append(credit)

        brazil = BrazilBenchmark(
            cds_5y_bps=self.brazil_spread_bps,
            z_spread_bps=self.brazil_spread_bps if brazil_yields else None,
            rating_sp=os.environ.get("IOS_HERMES_BRAZIL_RATING", "BB"),
            bond_security=self.brazil_isin,
        )
        log.success(
            f"Hermes ingested: {len(credits)}/{len(issuers)} issuers, "
            f"{len(history)} history points, {len(failures)} unmatched"
        )
        return FetchResult(
            as_of=dt.datetime.combine(as_of_date, dt.time(0, 0)),
            source=self.name,
            issuers=credits,
            history=history,
            brazil=brazil,
            failures=failures,
        )

    @staticmethod
    def _yields_by_date(dated_rows: dict[dt.date, dict]) -> dict[dt.date, float]:
        yields: dict[dt.date, float] = {}
        for date, row in dated_rows.items():
            price = clean_price(row)
            maturity = _opt_date(row.get("maturityDate"))
            coupon = float(row.get("coupon") or 0.0)
            if price is None or maturity is None:
                continue
            solved = ytm_pct(price, coupon, maturity, date)
            if solved is not None:
                yields[date] = solved
        return yields
