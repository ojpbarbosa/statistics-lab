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
    "PX_LAST",
    "CHG_PCT_3M", "CHG_PCT_1YR", "TOT_BUY_REC", "TOT_SELL_REC", "TOT_HOLD_REC",
]
# Bond fields are requested in two stages to stay under Bloomberg's workflow
# review radar: cheap static/reference fields for ALL candidates, pricing
# (calculated) fields ONLY for the single selected bond per issuer.
BOND_STATIC_FIELDS = ["TICKER", "CRNCY", "PAYMENT_RANK", "MATURITY", "AMT_OUTSTANDING", "CPN"]
BOND_PRICING_FIELDS = ["YAS_ZSPREAD", "PX_LAST"]
BOND_HISTORY_FIELD = "Z_SPRD_MID"  # bond PX_LAST is a price, not a spread
RATING_FIELD_TO_AGENCY = {
    "RTG_MOODY": "moody",
    "RTG_SP": "sp",
    "RTG_FITCH": "fitch",
    "RTG_DBRS": "dbrs",
    "RTG_KBRA": "kbra",
    "BB_COMPOSITE": "composite",
}
RATING_FIELDS = list(RATING_FIELD_TO_AGENCY)
DEFAULT_BOND_CURRENCIES = ("USD",)


def merge_ratings(rows_by_security: dict[str, dict], order: list[str]) -> dict[str, str]:
    """First non-empty value per agency across the securities in `order`
    (typically bond, then CDS, then equity), provider-agnostic."""
    merged: dict[str, str] = {}
    for security in order:
        values = rows_by_security.get(security, {})
        for field, agency in RATING_FIELD_TO_AGENCY.items():
            value = values.get(field)
            if agency not in merged and isinstance(value, str) and value.strip():
                merged[agency] = value.strip()
    return merged


def split_cds_curve(securities: list[str]) -> tuple[list[str], list[str]]:
    """The //blp/instruments corp lookup mixes cash bonds with the CDS curve;
    split them so CDS contracts never enter bond eligibility."""
    bonds = [s for s in securities if " CDS " not in s.upper()]
    curve = [s for s in securities if " CDS " in s.upper()]
    return bonds, curve


def pick_cds_5y(curve: list[str], ticker: str, currencies: tuple[str, ...] = DEFAULT_BOND_CURRENCIES) -> str | None:
    """Exact 5Y D14 point from a discovered CDS curve, preferred currency
    first. Interpolated tenors such as 1Y6M or 5Y3M never match."""
    for currency in currencies:
        pattern = re.compile(rf"^{re.escape(ticker)} CDS {currency} SR 5Y D14 Corp$", re.IGNORECASE)
        for security in curve:
            if pattern.match(security.strip()):
                return security.strip()
    return None


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


def same_credit_family(ticker_field, issuer_ticker: str) -> bool:
    """Bond belongs to the issuer when Bloomberg's TICKER field matches.
    A missing TICKER never disqualifies (benefit of the doubt; other
    eligibility checks still apply)."""
    if ticker_field is None or not str(ticker_field).strip():
        return True
    return str(ticker_field).strip().upper() == issuer_ticker.strip().upper()


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


def rank_is_senior_unsecured(rank: str | None) -> bool:
    """Senior-unsecured-equivalent PAYMENT_RANK values.

    Bloomberg labels senior bank paper 'Sr Preferred' / 'Sr Non Preferred';
    both are senior unsecured for the desk's purposes. Anything secured,
    subordinated, or junior is out.
    """
    if not rank:
        return False
    value = rank.lower()
    if "subordinat" in value or "junior" in value or value.startswith("jr"):
        return False
    if "unsecured" in value:
        return True
    if "secured" in value or "lien" in value:
        return False
    return (
        "sr preferred" in value
        or "senior preferred" in value
        or "sr non preferred" in value
        or "sr non-preferred" in value
        or "senior non preferred" in value
        or "senior non-preferred" in value
    )


_CANDIDATE_DATA_KEYS = ("crncy", "payment_rank", "maturity", "z_spread_bps", "last_price", "coupon")


def bond_currencies_from_env() -> tuple[str, ...]:
    """Allowed bond currencies in preference order, e.g. IOS_BOND_CURRENCIES=USD,EUR."""
    raw = os.environ.get("IOS_BOND_CURRENCIES", "")
    parsed = tuple(c.strip().upper() for c in raw.split(",") if c.strip())
    return parsed or DEFAULT_BOND_CURRENCIES


def tenor_window_from_env() -> tuple[float, float]:
    return (
        float(os.environ.get("IOS_TENOR_MIN_YEARS", TENOR_MIN_YEARS)),
        float(os.environ.get("IOS_TENOR_MAX_YEARS", TENOR_MAX_YEARS)),
    )


def _rejection_reason(
    candidate: dict,
    as_of: dt.date,
    currencies: tuple[str, ...] = DEFAULT_BOND_CURRENCIES,
    tenor_min: float = TENOR_MIN_YEARS,
    tenor_max: float = TENOR_MAX_YEARS,
    family_ticker: str | None = None,
) -> str:
    """Why this candidate fails eligibility; 'eligible' when it doesn't."""
    if all(candidate.get(key) is None for key in _CANDIDATE_DATA_KEYS):
        return "empty refdata row"
    if family_ticker and not same_credit_family(candidate.get("ticker_field"), family_ticker):
        return "different credit family"
    if candidate.get("crncy") not in currencies:
        return f"non-{'/'.join(currencies)}"
    if not rank_is_senior_unsecured(candidate.get("payment_rank")):
        return "rank mismatch"
    maturity = candidate.get("maturity")
    if maturity is None:
        return "no maturity"
    years = (maturity - as_of).days / 365.25
    if not tenor_min <= years <= tenor_max:
        return f"tenor outside {tenor_min:g}-{tenor_max:g}y"
    return "eligible"


def rejection_summary(
    candidates: list[dict],
    as_of: dt.date,
    currencies: tuple[str, ...] = DEFAULT_BOND_CURRENCIES,
    tenor_min: float = TENOR_MIN_YEARS,
    tenor_max: float = TENOR_MAX_YEARS,
    family_ticker: str | None = None,
) -> str:
    """Per-reason counts plus the most common rejected ranks, so a
    zero-eligible run self-diagnosing from the quality notes alone."""
    from collections import Counter

    reasons: Counter[str] = Counter()
    rejected_ranks: Counter[str] = Counter()
    for candidate in candidates:
        reason = _rejection_reason(candidate, as_of, currencies, tenor_min, tenor_max, family_ticker)
        reasons[reason] += 1
        if reason == "rank mismatch":
            rejected_ranks[str(candidate.get("payment_rank"))] += 1
    parts = [f"{count} {reason}" for reason, count in reasons.most_common()]
    if rejected_ranks:
        top = ", ".join(f"{rank!r}×{count}" for rank, count in rejected_ranks.most_common(3))
        parts.append(f"top rejected ranks: {top}")
    return "; ".join(parts) if parts else "0 refdata rows returned; run IOS_LOG_LEVEL=trace and check securityError/responseError lines"


def select_benchmark_bond(candidates: list[dict], as_of: dt.date) -> dict | None:
    """Sovereign benchmark pick: USD, 3-10y, closest to 5y, largest issue.
    No payment-rank requirement (govt paper often reports none)."""
    eligible = []
    for c in candidates:
        if c.get("crncy") != "USD" or c.get("maturity") is None:
            continue
        years = (c["maturity"] - as_of).days / 365.25
        if not TENOR_MIN_YEARS <= years <= TENOR_MAX_YEARS:
            continue
        eligible.append((abs(years - 5.0), -(c.get("amt_outstanding") or 0.0), c))
    if not eligible:
        return None
    eligible.sort(key=lambda t: (t[0], t[1]))
    return eligible[0][2]


def select_bond(
    candidates: list[dict],
    as_of: dt.date,
    currencies: tuple[str, ...] = DEFAULT_BOND_CURRENCIES,
    tenor_min: float = TENOR_MIN_YEARS,
    tenor_max: float = TENOR_MAX_YEARS,
    family_ticker: str | None = None,
) -> dict | None:
    """Pick the best eligible bond: preferred currency first, then closest to
    the 5y point (clamped into the tenor window), then largest outstanding."""
    target = min(max(5.0, tenor_min), tenor_max)
    eligible = []
    for c in candidates:
        if _rejection_reason(c, as_of, currencies, tenor_min, tenor_max, family_ticker) != "eligible":
            continue
        years = (c["maturity"] - as_of).days / 365.25
        eligible.append(
            (currencies.index(c["crncy"]), abs(years - target), -(c.get("amt_outstanding") or 0.0), c)
        )
    if not eligible:
        return None
    eligible.sort(key=lambda t: (t[0], t[1], t[2]))
    return eligible[0][3]


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
        self.currencies = bond_currencies_from_env()
        self.tenor_min, self.tenor_max = tenor_window_from_env()
        self._workflow_review_hit = False

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
                if msg.hasElement("responseError"):
                    error_text = str(msg.getElement("responseError"))
                    log.warn(f"refdata responseError: {error_text}")
                    if "WORKFLOW_REVIEW_NEEDED" in error_text and not self._workflow_review_hit:
                        self._workflow_review_hit = True
                        log.error(
                            "Bloomberg has gated this request pattern behind a workflow review "
                            "(category LIMIT, subcategory WORKFLOW_REVIEW_NEEDED). This is an "
                            "entitlement decision, not a code failure: contact your Bloomberg "
                            "representative or HELP HELP, cite the nid from the message above, "
                            "and describe the workflow (internal desk screening, display only, "
                            "no redistribution) to get it approved."
                        )
                    continue
                if not msg.hasElement("securityData"):
                    continue
                data = msg.getElement("securityData")
                for i in range(data.numValues()):
                    row = data.getValueAsElement(i)
                    security = row.getElementAsString("security")
                    values: dict = {}
                    if row.hasElement("securityError"):
                        log.trace(f"refdata securityError for {security!r}")
                        out[security] = values
                        continue
                    if row.hasElement("fieldData"):
                        field_data = row.getElement("fieldData")
                        for j in range(field_data.numElements()):
                            el = field_data.getElement(j)
                            try:
                                values[str(el.name())] = flatten_field_element(el)
                            except Exception:  # noqa: BLE001: one bad field must not kill the request
                                continue
                    out[security] = values
            if event.eventType() == blpapi.Event.RESPONSE:
                break
        return out

    def _spread_history(self, session, security: str, as_of: dt.date, field: str = "PX_LAST") -> list[tuple[dt.date, float]]:
        """HistoricalDataRequest for one field, weekly, 1y back -> [(date, value)].
        CDS curves quote spread as PX_LAST; bonds need Z_SPRD_MID (their
        PX_LAST is a price, which must never enter spread history)."""
        import blpapi

        service = session.getService("//blp/refdata")
        request = service.createRequest("HistoricalDataRequest")
        request.getElement("securities").appendValue(security)
        request.getElement("fields").appendValue(field)
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
                    if row.hasElement(field):
                        points.append(
                            (as_date(row.getElementAsDatetime("date")), row.getElementAsFloat(field))
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
            brazil_cds = float(brazil_row["PX_LAST"]) if "PX_LAST" in brazil_row else None
            if brazil_cds is None:
                _, brazil_curve = split_cds_curve(self._instrument_lookup(session, "BRAZIL"))
                brazil_cds_security = pick_cds_5y(brazil_curve, "BRAZIL", self.currencies)
                if brazil_cds_security:
                    lookup_row = self._reference_fields(session, [brazil_cds_security], ["PX_LAST"]).get(brazil_cds_security, {})
                    if "PX_LAST" in lookup_row:
                        brazil_cds = float(lookup_row["PX_LAST"])
                        log.info(f"Brazil CDS resolved via instruments lookup: {brazil_cds_security}")
            if brazil_cds is None:
                brazil_cds = BRAZIL_FALLBACK.cds_5y_bps
                log.warn(f"Brazil CDS quote missing; using fallback {BRAZIL_FALLBACK.cds_5y_bps:.0f} bps")
            else:
                log.info(f"Brazil 5Y CDS: {brazil_cds:.1f} bps")

            brazil_bond = None
            try:
                govt_securities = [
                    s
                    for s in self._instrument_lookup(session, "BRAZIL", yellow_key="YK_FILTER_GOVT")
                    if " CDS " not in s.upper()
                ]
                brazil_bond = select_benchmark_bond(
                    self._bond_refdata(session, govt_securities, "BRAZIL"), as_of=as_of.date()
                )
                if brazil_bond is not None:
                    brazil_bond = self._price_bond(session, brazil_bond, "BRAZIL")
            except Exception as exc:  # noqa: BLE001: bond discovery is optional for the benchmark
                log.warn(f"Brazil benchmark bond discovery failed: {exc}")
            if brazil_bond is not None:
                log.info(
                    f"Brazil benchmark bond: {brazil_bond.get('security')} "
                    f"(z-spread {brazil_bond.get('z_spread_bps')} bps)"
                )
            else:
                log.warn("no Brazil USD benchmark bond in the 3-10y window was found")

            rating_securities = [
                s for s in ((brazil_bond or {}).get("security"), BRAZIL_CDS_TICKER) if s
            ]
            brazil_ratings = merge_ratings(
                self._reference_fields(session, rating_securities, RATING_FIELDS), rating_securities
            )
            headline = (
                brazil_ratings.get("sp")
                or brazil_ratings.get("composite")
                or next(iter(brazil_ratings.values()), BRAZIL_FALLBACK.rating_sp)
            )
            log.info(f"Brazil ratings: {brazil_ratings or 'none resolved, using fallback ' + headline}")

            brazil = BrazilBenchmark(
                cds_5y_bps=brazil_cds,
                z_spread_bps=(brazil_bond or {}).get("z_spread_bps"),
                rating_sp=headline,
                bond_security=(brazil_bond or {}).get("security"),
                ratings=brazil_ratings,
            )
        except Exception as exc:  # noqa: BLE001: benchmark failure must not kill the run
            failures["__BRAZIL__"] = f"benchmark fetch failed, using fallback: {exc}"
            log.error(f"Brazil benchmark fetch failed ({exc}); using fallback {BRAZIL_FALLBACK.cds_5y_bps:.0f} bps")

        total = len(issuers)
        for index, issuer in enumerate(issuers, start=1):
            log.step(f"({index}/{total}) {issuer.ticker}: {issuer.issuer}")
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
                    "equity_ticker": equity_security if "PX_LAST" in equity_row else None,
                    "px_chg_3m_pct": equity_row.get("CHG_PCT_3M"),
                    "px_chg_12m_pct": equity_row.get("CHG_PCT_1YR"),
                    "rec_balance": (
                        ((equity_row.get("TOT_BUY_REC") or 0) - (equity_row.get("TOT_SELL_REC") or 0)) / total_recs
                        if total_recs
                        else None
                    ),
                }

                bond_securities, cds_curve = self._discover_corp_securities(session, equity_security, issuer.ticker)

                if fields["cds_5y_bps"] is None and cds_curve:
                    fallback = pick_cds_5y(cds_curve, issuer.ticker, self.currencies)
                    if fallback and fallback != cds_security:
                        fallback_row = self._reference_fields(session, [fallback], ["PX_LAST"]).get(fallback, {})
                        if "PX_LAST" in fallback_row:
                            cds_security = fallback
                            fields["cds_5y_bps"] = float(fallback_row["PX_LAST"])
                            fields["cds_liquidity_score"] = 100.0
                            log.info(f"{issuer.ticker}: CDS resolved via instruments lookup: {fallback}")
                cds_resolved = fields["cds_5y_bps"] is not None
                if cds_resolved:
                    log.trace(f"{issuer.ticker}: 5Y CDS {fields['cds_5y_bps']:.1f} bps via {cds_security}")
                else:
                    log.trace(f"{issuer.ticker}: no CDS quote ({len(cds_curve)} curve items discovered)")

                bond_note = None
                try:
                    candidates = self._bond_refdata(session, bond_securities, issuer.ticker)
                    bond = select_bond(
                        candidates,
                        as_of=as_of.date(),
                        currencies=self.currencies,
                        tenor_min=self.tenor_min,
                        tenor_max=self.tenor_max,
                        family_ticker=issuer.ticker,
                    )
                    if bond is None:
                        bond_note = (
                            f"bond discovery: {len(bond_securities)} bond securities "
                            f"({len(cds_curve)} CDS curve items excluded), 0 selected: "
                            f"{rejection_summary(candidates, as_of.date(), self.currencies, self.tenor_min, self.tenor_max, issuer.ticker)}"
                        )
                        if self._workflow_review_hit and not candidates:
                            bond_note += (
                                "; Bloomberg workflow review is blocking bond requests "
                                "(ask your Bloomberg rep to approve, nid in the logs)"
                            )
                        log.warn(f"{issuer.ticker}: {bond_note}")
                    else:
                        bond = self._price_bond(session, bond, issuer.ticker)
                        if bond.get("crncy") and bond["crncy"] != "USD":
                            bond_note = (
                                f"selected bond is {bond['crncy']}-denominated; "
                                f"z-spread vs the Brazil USD benchmark is indicative only"
                            )
                        log.trace(
                            f"{issuer.ticker}: bond {bond.get('security')} "
                            f"(z-spread {bond.get('z_spread_bps')}, {len(bond_securities)} discovered, {len(candidates)} resolved)"
                        )
                except Exception as exc:  # noqa: BLE001: bond discovery must not drop good CDS/equity data
                    bond = None
                    bond_note = f"bond discovery failed: {exc}"
                    log.warn(f"{issuer.ticker}: {bond_note}")

                rating_securities = [
                    security
                    for security in (
                        (bond or {}).get("security"),
                        cds_security if cds_resolved else None,
                        equity_security if equity_row else None,
                    )
                    if security
                ]
                ratings: dict[str, str] = {}
                if rating_securities:
                    ratings = merge_ratings(
                        self._reference_fields(session, rating_securities, RATING_FIELDS), rating_securities
                    )
                log.trace(f"{issuer.ticker}: ratings {ratings or 'none resolved'}")
                fields["rating_moody"] = ratings.get("moody")
                fields["rating_sp"] = ratings.get("sp")
                fields["rating_fitch"] = ratings.get("fitch")

                credit = credit_from_fields(issuer.ticker, fields, bond)
                credit.ratings = ratings
                credit.cds_security = cds_security if cds_resolved else None
                if not ratings:
                    credit.quality_notes.append("no agency ratings resolved from bond, CDS, or equity")
                if bond_note is not None:
                    credit.quality_notes.append(bond_note)
                if bond is not None:
                    z_bps = bond.get("z_spread_bps")
                    px = bond.get("last_price")
                    if (z_bps is not None and z_bps > 1000) or (px is not None and px < 50):
                        distress_note = (
                            f"selected bond {bond.get('security')} looks distressed or stale "
                            f"(px {px}, z-spread {z_bps} bps); verify on DES before pitching"
                        )
                        credit.quality_notes.append(distress_note)
                        log.warn(f"{issuer.ticker}: {distress_note}")
                credits.append(credit)

                spread_security = cds_security if credit.cds_5y_bps is not None else credit.bond.security
                instrument = "cds" if credit.cds_5y_bps is not None else "bond"
                history_field = "PX_LAST" if instrument == "cds" else BOND_HISTORY_FIELD
                if spread_security is not None:
                    points = self._spread_history(session, spread_security, as_of.date(), field=history_field)
                    log.trace(f"{issuer.ticker}: {len(points)} history points via {instrument} ({history_field})")
                    for date, value in points:
                        history.append(HistoryPoint(issuer.ticker, date, float(value), instrument))
                else:
                    log.trace(f"{issuer.ticker}: no spread instrument for history")
            except Exception as exc:  # noqa: BLE001: one bad issuer must not kill the run
                failures[issuer.ticker] = str(exc)
                log.error(f"{issuer.ticker}: {exc}")

        ok = len(credits)
        summary = f"fetched {ok}/{total} issuers, {len(history)} history points, {len(failures)} failure(s)"
        (log.success if not failures else log.warn)(summary)
        return FetchResult(
            as_of=as_of, source=self.name, issuers=credits,
            history=history, brazil=brazil, failures=failures,
        )

    def _instrument_lookup(self, session, ticker: str, yellow_key: str = "YK_FILTER_CORP") -> list[str]:
        """Search //blp/instruments for the issuer's securities."""
        import blpapi

        if not session.openService("//blp/instruments"):
            return []
        service = session.getService("//blp/instruments")
        request = service.createRequest("instrumentListRequest")
        request.set("query", ticker)
        request.set("yellowKeyFilter", yellow_key)
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
                    # No ticker-prefix filter here: bond results often come back
                    # as ID-style keys (e.g. 'EJ682107 Corp'); the credit-family
                    # check happens after refdata via the TICKER field.
                    results.append(parsekeyable(row.getElementAsString("security")))
            if event.eventType() == blpapi.Event.RESPONSE:
                break
        return results

    def _discover_corp_securities(self, session, equity_security: str, ticker: str) -> tuple[list[str], list[str]]:
        """Discover the issuer's corp securities and split (bonds, cds_curve).
        BOND_CHAIN on the equity, then on the '{ticker} Corp' company shell,
        then the //blp/instruments lookup (which mixes in the CDS curve,
        hence the split)."""
        securities: list[str] = []
        for chain_source in (equity_security, f"{ticker} Corp"):
            chain_rows = self._reference_fields(session, [chain_source], ["BOND_CHAIN"])
            chain = chain_rows.get(chain_source, {}).get("BOND_CHAIN") or []
            if chain:
                log.trace(f"{ticker}: BOND_CHAIN on {chain_source!r} returned {len(chain)} items")
                securities = [chain_security(item) for item in chain]
                break
        if not securities:
            log.trace(f"{ticker}: BOND_CHAIN empty; falling back to //blp/instruments lookup")
            securities = self._instrument_lookup(session, ticker)
        return split_cds_curve(securities)

    def _bond_refdata(self, session, securities: list[str], ticker: str) -> list[dict]:
        """Static reference data for discovered bond securities, in polite
        batches. Pricing fields are fetched later, for the selected bond only."""
        if not securities:
            return []
        rows: dict[str, dict] = {}
        for start in range(0, len(securities), 100):
            rows.update(self._reference_fields(session, securities[start : start + 100], BOND_STATIC_FIELDS))
        candidates = []
        for security, values in rows.items():
            candidate = {
                "security": security,
                "ticker_field": values.get("TICKER"),
                "crncy": values.get("CRNCY"),
                "payment_rank": values.get("PAYMENT_RANK"),
                "maturity": as_date(values.get("MATURITY")),
                "amt_outstanding": values.get("AMT_OUTSTANDING"),
                "z_spread_bps": None,  # filled by _price_bond for the winner only
                "last_price": None,
                "coupon": values.get("CPN"),
            }
            log.trace(f"{ticker}: bond candidate {candidate}")
            candidates.append(candidate)
        return candidates

    def _price_bond(self, session, bond: dict, ticker: str) -> dict:
        """Fetch pricing for the single selected bond."""
        security = bond["security"]
        pricing = self._reference_fields(session, [security], BOND_PRICING_FIELDS).get(security, {})
        bond["z_spread_bps"] = pricing.get("YAS_ZSPREAD")
        bond["last_price"] = pricing.get("PX_LAST")
        if bond["z_spread_bps"] is None:
            log.warn(f"{ticker}: selected bond {security} returned no z-spread")
        return bond
