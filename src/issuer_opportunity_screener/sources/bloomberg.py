"""Live Bloomberg Desktop API adapter.

Only this module touches blpapi, and only lazily inside _connect(), so the
rest of the package imports and tests cleanly on machines without a Terminal.

The blpapi boundary (_reference_fields, _bond_candidates, _spread_history)
converts responses to plain dicts; everything after that is pure and tested.
Field mnemonics are best-effort and MUST be verified on the Terminal machine
(see Task 10 verification checklist).
"""
from __future__ import annotations

import datetime as dt
import os

from issuer_opportunity_screener.sources.base import (
    BloombergUnavailable,
    BondSnapshot,
    BrazilBenchmark,
    EquityOverlay,
    FetchResult,
    HistoryPoint,
    IssuerCredit,
    UniverseIssuer,
)

BRAZIL_CDS_TICKER = "BRAZIL CDS USD SR 5Y D14 Corp"
BRAZIL_FALLBACK = BrazilBenchmark(cds_5y_bps=180.0, z_spread_bps=None, rating_sp="BB")
TENOR_MIN_YEARS = 3.0
TENOR_MAX_YEARS = 10.0
REFDATA_FIELDS = [
    "PX_LAST", "RTG_MOODY", "RTG_SP", "RTG_FITCH",
    "CHG_PCT_3M", "CHG_PCT_1YR", "TOT_BUY_REC", "TOT_SELL_REC", "TOT_HOLD_REC",
]
BOND_FIELDS = ["CRNCY", "PAYMENT_RANK", "MATURITY", "AMT_OUTSTANDING", "YAS_ZSPREAD", "PX_LAST", "CPN"]


YELLOW_KEYS = (" Corp", " Govt", " Mtge", " Muni", " Pfd", " Equity", " Index", " Curncy", " Comdty")


def as_date(value) -> dt.date | None:
    """blpapi returns datetime.datetime or datetime.date depending on element type."""
    if value is None:
        return None
    return value.date() if isinstance(value, dt.datetime) else value


def chain_security(item) -> str:
    """BOND_CHAIN identifiers come back without a yellow key; refdata needs one."""
    security = str(item).strip()
    return security if security.endswith(YELLOW_KEYS) else f"{security} Corp"


def cds_ticker(issuer_ticker: str) -> str:
    return f"{issuer_ticker} CDS USD SR 5Y D14 Corp"


def flatten_field_element(el):
    """Flatten a blpapi Element to a plain python value.

    Scalar fields return el.getValue(). BULK (array) fields such as
    BOND_CHAIN return a list, one entry per row, using the row's first
    sub-element value (BOND_CHAIN rows carry the security identifier as
    their first sub-element); rows with no sub-elements fall back to str(row).
    """
    if el.isArray():
        values = []
        for i in range(el.numValues()):
            row = el.getValueAsElement(i)
            if row.numElements() > 0:
                values.append(row.getElement(0).getValue())
            else:
                values.append(str(row))
        return values
    return el.getValue()


def select_bond(candidates: list[dict], as_of: dt.date) -> dict | None:
    eligible = []
    for c in candidates:
        if c.get("crncy") != "USD":
            continue
        if "Sr Unsecured" not in (c.get("payment_rank") or ""):
            continue
        maturity = c.get("maturity")
        if maturity is None:
            continue
        years = (maturity - as_of).days / 365.25
        if not TENOR_MIN_YEARS <= years <= TENOR_MAX_YEARS:
            continue
        eligible.append((abs(years - 5.0), -(c.get("amt_outstanding") or 0.0), c))
    if not eligible:
        return None
    eligible.sort(key=lambda t: (t[0], t[1]))
    return eligible[0][2]


def credit_from_fields(ticker: str, fields: dict, bond: dict | None) -> IssuerCredit:
    credit = IssuerCredit(
        ticker=ticker,
        cds_5y_bps=fields.get("cds_5y_bps"),
        cds_liquidity_score=fields.get("cds_liquidity_score"),
        rating_moody=fields.get("rating_moody"),
        rating_sp=fields.get("rating_sp"),
        rating_fitch=fields.get("rating_fitch"),
    )
    if credit.cds_5y_bps is None:
        credit.quality_notes.append("no liquid CDS quote; using bond z-spread when available")
    if bond is not None:
        credit.bond = BondSnapshot(
            security=bond.get("security"),
            z_spread_bps=bond.get("z_spread_bps"),
            last_price=bond.get("last_price"),
            maturity=bond.get("maturity"),
            coupon=bond.get("coupon"),
        )
    else:
        credit.quality_notes.append("no eligible senior unsecured USD 3-10y bond found")
    if fields.get("equity_ticker"):
        credit.equity = EquityOverlay(
            equity_ticker=fields["equity_ticker"],
            price_change_3m_pct=fields.get("px_chg_3m_pct"),
            price_change_12m_pct=fields.get("px_chg_12m_pct"),
            recommendation_balance=fields.get("rec_balance"),
        )
    else:
        credit.quality_notes.append("no listed equity; equity overlay skipped")
    return credit


class BloombergSource:
    name = "bloomberg"

    def __init__(self, host: str | None = None, port: int | None = None):
        self.host = host or os.environ.get("IOS_BB_HOST", "localhost")
        self.port = port if port is not None else int(os.environ.get("IOS_BB_PORT", "8194"))

    # --- blpapi boundary (untested; verified live on the Terminal machine) ---

    def _connect(self):
        try:
            import blpapi
        except ImportError as exc:
            raise BloombergUnavailable("blpapi is not installed in this environment") from exc
        options = blpapi.SessionOptions()
        options.setServerHost(self.host)
        options.setServerPort(self.port)
        session = blpapi.Session(options)
        if not session.start() or not session.openService("//blp/refdata"):
            raise BloombergUnavailable(f"could not open blpapi session on {self.host}:{self.port}")
        return session

    def _reference_fields(self, session, securities: list[str], fields: list[str]) -> dict[str, dict]:
        """ReferenceDataRequest -> {security: {FIELD: value}} with plain python values."""
        import blpapi

        service = session.getService("//blp/refdata")
        request = service.createRequest("ReferenceDataRequest")
        for security in securities:
            request.getElement("securities").appendValue(security)
        for field in fields:
            request.getElement("fields").appendValue(field)
        session.sendRequest(request)
        out: dict[str, dict] = {}
        while True:
            event = session.nextEvent(30_000)
            for msg in event:
                if not msg.hasElement("securityData"):
                    continue
                data = msg.getElement("securityData")
                for i in range(data.numValues()):
                    row = data.getValueAsElement(i)
                    security = row.getElementAsString("security")
                    values: dict = {}
                    field_data = row.getElement("fieldData")
                    for j in range(field_data.numElements()):
                        el = field_data.getElement(j)
                        try:
                            values[str(el.name())] = flatten_field_element(el)
                        except Exception:  # noqa: BLE001 — one bad field must not kill the request
                            continue
                    out[security] = values
            if event.eventType() == blpapi.Event.RESPONSE:
                break
        return out

    def _spread_history(self, session, security: str, as_of: dt.date) -> list[tuple[dt.date, float]]:
        """HistoricalDataRequest PX_LAST, weekly, 1y back -> [(date, value)]."""
        import blpapi

        service = session.getService("//blp/refdata")
        request = service.createRequest("HistoricalDataRequest")
        request.getElement("securities").appendValue(security)
        request.getElement("fields").appendValue("PX_LAST")
        request.set("startDate", (as_of - dt.timedelta(days=365)).strftime("%Y%m%d"))
        request.set("endDate", as_of.strftime("%Y%m%d"))
        request.set("periodicitySelection", "WEEKLY")
        session.sendRequest(request)
        points: list[tuple[dt.date, float]] = []
        while True:
            event = session.nextEvent(30_000)
            for msg in event:
                if not msg.hasElement("securityData"):
                    continue
                field_data = msg.getElement("securityData").getElement("fieldData")
                for i in range(field_data.numValues()):
                    row = field_data.getValueAsElement(i)
                    if row.hasElement("PX_LAST"):
                        points.append(
                            (as_date(row.getElementAsDatetime("date")), row.getElementAsFloat("PX_LAST"))
                        )
            if event.eventType() == blpapi.Event.RESPONSE:
                break
        return points

    # --- fetch -----------------------------------------------------------------

    def fetch(self, issuers: list[UniverseIssuer]) -> FetchResult:
        session = self._connect()
        as_of = dt.datetime.now()
        credits: list[IssuerCredit] = []
        history: list[HistoryPoint] = []
        failures: dict[str, str] = {}

        brazil = BRAZIL_FALLBACK
        try:
            brazil_row = self._reference_fields(session, [BRAZIL_CDS_TICKER], ["PX_LAST"]).get(BRAZIL_CDS_TICKER, {})
            if "PX_LAST" in brazil_row:
                brazil = BrazilBenchmark(
                    cds_5y_bps=float(brazil_row["PX_LAST"]),
                    z_spread_bps=None,
                    rating_sp=BRAZIL_FALLBACK.rating_sp,
                )
        except Exception as exc:  # noqa: BLE001 — benchmark failure must not kill the run
            failures["__BRAZIL__"] = f"benchmark fetch failed, using fallback: {exc}"

        for issuer in issuers:
            try:
                equity_security = f"{issuer.ticker} US Equity"
                cds_security = cds_ticker(issuer.ticker)
                rows = self._reference_fields(session, [equity_security, cds_security], REFDATA_FIELDS)
                equity_row = rows.get(equity_security, {})
                cds_row = rows.get(cds_security, {})

                total_recs = sum(equity_row.get(f, 0) or 0 for f in ("TOT_BUY_REC", "TOT_SELL_REC", "TOT_HOLD_REC"))
                fields = {
                    "cds_5y_bps": float(cds_row["PX_LAST"]) if "PX_LAST" in cds_row else None,
                    "cds_liquidity_score": 100.0 if "PX_LAST" in cds_row else None,
                    "rating_moody": equity_row.get("RTG_MOODY"),
                    "rating_sp": equity_row.get("RTG_SP"),
                    "rating_fitch": equity_row.get("RTG_FITCH"),
                    "equity_ticker": equity_security if "PX_LAST" in equity_row else None,
                    "px_chg_3m_pct": equity_row.get("CHG_PCT_3M"),
                    "px_chg_12m_pct": equity_row.get("CHG_PCT_1YR"),
                    "rec_balance": (
                        ((equity_row.get("TOT_BUY_REC") or 0) - (equity_row.get("TOT_SELL_REC") or 0)) / total_recs
                        if total_recs
                        else None
                    ),
                }
                bond_note = None
                try:
                    candidates, chain_len = self._bond_candidates(session, issuer.ticker)
                    bond = select_bond(candidates, as_of=as_of.date())
                    if bond is None:
                        bond_note = (
                            f"bond discovery: {chain_len} chain items, "
                            f"{len(candidates)} resolved via refdata, 0 eligible (USD Sr Unsecured 3-10y)"
                        )
                        if candidates:
                            sample = candidates[0]
                            bond_note += (
                                f"; sample candidate: crncy={sample.get('crncy')!r},"
                                f" rank={sample.get('payment_rank')!r}, maturity={sample.get('maturity')}"
                            )
                except Exception as exc:  # noqa: BLE001 — bond discovery must not drop good CDS/equity data
                    bond = None
                    bond_note = f"bond discovery failed: {exc}"
                credit = credit_from_fields(issuer.ticker, fields, bond)
                if bond_note is not None:
                    credit.quality_notes.append(bond_note)
                credits.append(credit)

                spread_security = cds_security if credit.cds_5y_bps is not None else credit.bond.security
                instrument = "cds" if credit.cds_5y_bps is not None else "bond"
                if spread_security is not None:
                    for date, value in self._spread_history(session, spread_security, as_of.date()):
                        history.append(HistoryPoint(issuer.ticker, date, float(value), instrument))
            except Exception as exc:  # noqa: BLE001 — one bad issuer must not kill the run
                failures[issuer.ticker] = str(exc)

        return FetchResult(
            as_of=as_of, source=self.name, issuers=credits,
            history=history, brazil=brazil, failures=failures,
        )

    def _bond_candidates(self, session, issuer_ticker: str) -> tuple[list[dict], int]:
        """Discover the issuer's bonds via BOND_CHAIN BDS, then pull BOND_FIELDS.

        Returns (candidates, chain_length) so callers can report where
        discovery thinned out.
        """
        chain_rows = self._reference_fields(session, [f"{issuer_ticker} US Equity"], ["BOND_CHAIN"])
        chain = chain_rows.get(f"{issuer_ticker} US Equity", {}).get("BOND_CHAIN") or []
        securities = [chain_security(item) for item in chain][:50]
        if not securities:
            return [], len(chain)
        rows = self._reference_fields(session, securities, BOND_FIELDS)
        candidates = []
        for security, values in rows.items():
            candidates.append(
                {
                    "security": security,
                    "crncy": values.get("CRNCY"),
                    "payment_rank": values.get("PAYMENT_RANK"),
                    "maturity": as_date(values.get("MATURITY")),
                    "amt_outstanding": values.get("AMT_OUTSTANDING"),
                    "z_spread_bps": values.get("YAS_ZSPREAD"),
                    "last_price": values.get("PX_LAST"),
                    "coupon": values.get("CPN"),
                }
            )
        return candidates, len(chain)
