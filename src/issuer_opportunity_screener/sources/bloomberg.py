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
import re

from issuer_opportunity_screener.log import get_logger
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


log = get_logger("bloomberg")

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


def parsekeyable(instrument_result) -> str:
    """//blp/instruments results end in '<corp>'-style keys; refdata wants ' Corp'."""
    security = str(instrument_result).strip()
    match = re.search(r"<(\w+)>$", security)
    if match:
        security = f"{security[: match.start()].rstrip()} {match.group(1).capitalize()}"
    return security


def security_matches_ticker(security: str, ticker: str) -> bool:
    """Keep only lookup results that belong to the issuer's credit family."""
    return security.upper().startswith(f"{ticker.upper()} ")


def cds_ticker(issuer_ticker: str) -> str:
    return f"{issuer_ticker} CDS USD SR 5Y D14 Corp"


def issuer_securities(issuer: UniverseIssuer) -> tuple[str, str]:
    """Resolve (equity_security, cds_security), preferring explicit universe
    overrides over the derived `{ticker} US Equity` / D14 CDS conventions."""
    equity = issuer.equity_ticker or f"{issuer.ticker} US Equity"
    cds = issuer.cds_ticker or cds_ticker(issuer.ticker)
    return equity, cds


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
        log.step(f"connecting to Bloomberg at {self.host}:{self.port}")
        session = self._connect()
        log.info("session established")
        as_of = dt.datetime.now()
        credits: list[IssuerCredit] = []
        history: list[HistoryPoint] = []
        failures: dict[str, str] = {}

        brazil = BRAZIL_FALLBACK
        log.step(f"fetching Brazil benchmark ({BRAZIL_CDS_TICKER})")
        try:
            brazil_row = self._reference_fields(session, [BRAZIL_CDS_TICKER], ["PX_LAST"]).get(BRAZIL_CDS_TICKER, {})
            if "PX_LAST" in brazil_row:
                brazil = BrazilBenchmark(
                    cds_5y_bps=float(brazil_row["PX_LAST"]),
                    z_spread_bps=None,
                    rating_sp=BRAZIL_FALLBACK.rating_sp,
                )
                log.info(f"Brazil 5Y CDS: {brazil.cds_5y_bps:.1f} bps")
            else:
                log.warn(f"Brazil benchmark quote missing; using fallback {BRAZIL_FALLBACK.cds_5y_bps:.0f} bps")
        except Exception as exc:  # noqa: BLE001 — benchmark failure must not kill the run
            failures["__BRAZIL__"] = f"benchmark fetch failed, using fallback: {exc}"
            log.error(f"Brazil benchmark fetch failed ({exc}); using fallback {BRAZIL_FALLBACK.cds_5y_bps:.0f} bps")

        total = len(issuers)
        for index, issuer in enumerate(issuers, start=1):
            log.step(f"({index}/{total}) {issuer.ticker} — {issuer.issuer}")
            try:
                equity_security, cds_security = issuer_securities(issuer)
                rows = self._reference_fields(session, [equity_security, cds_security], REFDATA_FIELDS)
                equity_row = rows.get(equity_security, {})
                cds_row = rows.get(cds_security, {})
                if "PX_LAST" not in equity_row:
                    log.trace(f"{issuer.ticker}: equity handle {equity_security!r} did not resolve")

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
                if fields["cds_5y_bps"] is not None:
                    log.trace(f"{issuer.ticker}: 5Y CDS {fields['cds_5y_bps']:.1f} bps")
                else:
                    log.trace(f"{issuer.ticker}: no CDS quote")
                log.trace(
                    f"{issuer.ticker}: raw ratings moody={fields['rating_moody']!r} "
                    f"sp={fields['rating_sp']!r} fitch={fields['rating_fitch']!r}"
                )

                bond_note = None
                try:
                    candidates, discovered = self._bond_candidates(session, equity_security, issuer.ticker)
                    bond = select_bond(candidates, as_of=as_of.date())
                    if bond is None:
                        bond_note = (
                            f"bond discovery: {discovered} securities discovered, "
                            f"{len(candidates)} resolved via refdata, 0 eligible (USD Sr Unsecured 3-10y)"
                        )
                        if candidates:
                            sample = candidates[0]
                            bond_note += (
                                f"; sample candidate: crncy={sample.get('crncy')!r},"
                                f" rank={sample.get('payment_rank')!r}, maturity={sample.get('maturity')}"
                            )
                        log.warn(f"{issuer.ticker}: {bond_note}")
                    else:
                        log.trace(
                            f"{issuer.ticker}: bond {bond.get('security')} "
                            f"(z-spread {bond.get('z_spread_bps')}, {discovered} discovered, {len(candidates)} resolved)"
                        )
                except Exception as exc:  # noqa: BLE001 — bond discovery must not drop good CDS/equity data
                    bond = None
                    bond_note = f"bond discovery failed: {exc}"
                    log.warn(f"{issuer.ticker}: {bond_note}")
                credit = credit_from_fields(issuer.ticker, fields, bond)
                if bond_note is not None:
                    credit.quality_notes.append(bond_note)
                credits.append(credit)

                spread_security = cds_security if credit.cds_5y_bps is not None else credit.bond.security
                instrument = "cds" if credit.cds_5y_bps is not None else "bond"
                if spread_security is not None:
                    points = self._spread_history(session, spread_security, as_of.date())
                    log.trace(f"{issuer.ticker}: {len(points)} history points via {instrument}")
                    for date, value in points:
                        history.append(HistoryPoint(issuer.ticker, date, float(value), instrument))
                else:
                    log.trace(f"{issuer.ticker}: no spread instrument for history")
            except Exception as exc:  # noqa: BLE001 — one bad issuer must not kill the run
                failures[issuer.ticker] = str(exc)
                log.error(f"{issuer.ticker}: {exc}")

        ok = len(credits)
        summary = f"fetched {ok}/{total} issuers, {len(history)} history points, {len(failures)} failure(s)"
        (log.success if not failures else log.warn)(summary)
        return FetchResult(
            as_of=as_of, source=self.name, issuers=credits,
            history=history, brazil=brazil, failures=failures,
        )

    def _instrument_lookup(self, session, ticker: str) -> list[str]:
        """Search //blp/instruments for the issuer's corp securities."""
        import blpapi

        if not session.openService("//blp/instruments"):
            return []
        service = session.getService("//blp/instruments")
        request = service.createRequest("instrumentListRequest")
        request.set("query", ticker)
        request.set("yellowKeyFilter", "YK_FILTER_CORP")
        request.set("maxResults", 200)
        session.sendRequest(request)
        results: list[str] = []
        while True:
            event = session.nextEvent(30_000)
            for msg in event:
                if not msg.hasElement("results"):
                    continue
                rows = msg.getElement("results")
                for i in range(rows.numValues()):
                    row = rows.getValueAsElement(i)
                    security = parsekeyable(row.getElementAsString("security"))
                    if security_matches_ticker(security, ticker):
                        results.append(security)
            if event.eventType() == blpapi.Event.RESPONSE:
                break
        return results

    def _bond_candidates(self, session, equity_security: str, ticker: str) -> tuple[list[dict], int]:
        """Discover the issuer's bonds: BOND_CHAIN first, //blp/instruments fallback.

        Returns (candidates, discovered_count) so callers can report where
        discovery thinned out.
        """
        chain_rows = self._reference_fields(session, [equity_security], ["BOND_CHAIN"])
        chain = chain_rows.get(equity_security, {}).get("BOND_CHAIN") or []
        securities = [chain_security(item) for item in chain][:50]
        if not securities:
            log.trace(f"{ticker}: BOND_CHAIN empty; falling back to //blp/instruments lookup")
            securities = self._instrument_lookup(session, ticker)[:50]
        if not securities:
            return [], 0
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
        return candidates, len(securities)
