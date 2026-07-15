# Issuer Opportunity Screener v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Issuer Opportunity Screener as a layered Python package — universe config → source adapters (blpapi/fixture) → versioned parquet snapshots → documented composite scoring → Streamlit dashboard.

**Architecture:** Strict one-directional flow: `data/universe.csv` → `pipeline` (via a `CreditDataSource` adapter) → timestamped snapshot directories (`snapshot.parquet` + `history.parquet` + `manifest.json`) → `scoring` (composite score from `docs/methodology/screening_criteria_v1.typ`) → `app.py` (Streamlit, 3 tabs). The dashboard never calls blpapi directly; a fixture adapter makes everything except `sources/bloomberg.py` testable on any machine.

**Tech Stack:** Python 3.12, Poetry (in-project venv), pandas ≥3.0.3, pyarrow, blpapi (Bloomberg supplemental source), Streamlit (+ `streamlit.testing.v1.AppTest`), pytest.

**Spec:** `docs/superpowers/specs/2026-07-15-issuer-opportunity-screener-design.md` — read it before starting.

## Global Constraints

- Python `>=3.12`; Poetry with `virtualenvs.in-project = true` (already in `poetry.toml`).
- Package lives at `src/issuer_opportunity_screener/`; tests at `tests/`.
- blpapi comes from the Bloomberg supplemental source `https://blpapi.bloomberg.com/repository/releases/python/simple` (already configured in `pyproject.toml`). `blpapi` is imported ONLY inside `sources/bloomberg.py`, and only lazily (inside methods), so every other module works without it installed.
- Missing data never crashes a run: absent fields become `None`/NaN plus a quality note. Scoring re-normalizes block weights over available blocks.
- Snapshot directories are append-only; never overwrite an existing snapshot.
- Desk viability rule (exact): viable when `spread_vs_brazil_bps >= 0`, OR `spread_vs_brazil_bps >= -20` AND issuer composite rating is strictly stronger than Brazil's rating.
- Composite score weights (exact, from screening_criteria_v1.typ): Credit and Spread Attractiveness 0.35, Credit Quality and Risk 0.20, Market Liquidity and Accessibility 0.20, Equity Overlay 0.10, Recognition and Client Fit 0.15. Tiers: A ≥ 70, B ≥ 50, else C.
- All timestamps in snapshot dir names use `%Y-%m-%dT%H%M%S` (local time).
- Run tests with `poetry run pytest -q` from the repo root.
- Commit after every task (and at each Commit step) with a conventional-commit message.

---

### Task 1: Project scaffolding, universe config, and universe loader

**Files:**
- Modify: `pyproject.toml`
- Create: `src/issuer_opportunity_screener/__init__.py`
- Create: `src/issuer_opportunity_screener/sources/__init__.py`
- Create: `data/universe.csv`
- Create: `src/issuer_opportunity_screener/universe.py`
- Test: `tests/test_universe.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `universe.load_universe(path: Path) -> list[UniverseIssuer]` raising `universe.UniverseError` on invalid input; `universe.BASKETS: set[str]`; the dataclass `UniverseIssuer` (defined here to avoid a forward dependency on Task 2; Task 2 re-exports it from `sources/base.py` — see note in Step 3).

- [ ] **Step 1: Update pyproject and install**

Replace the `[project]` dependencies block of `pyproject.toml` so the full file reads:

```toml
[project]
name = "issuer-opportunity-screener"
version = "0.2.0"
description = "A practical screening tool to help identify and prioritize potential corporate note issuance candidates using credit, spread, and market-based signals."
authors = [
    {name = "Joao Barbosa", email = "joao.fbarbosa@xpi.us"}
]
requires-python = ">=3.12"
dependencies = [
    "pandas (>=3.0.3,<4.0.0)",
    "numpy (>=2.5.1,<3.0.0)",
    "blpapi (>=3.26.5.1,<4.0.0.0)",
    "streamlit (>=1.45,<2.0)",
    "pyarrow (>=17.0,<30.0)",
]

[build-system]
requires = ["poetry-core>=2.0.0,<3.0.0"]
build-backend = "poetry.core.masonry.api"

[tool.poetry]
packages = [{include = "issuer_opportunity_screener", from = "src"}]

[[tool.poetry.source]]
name = "bloomberg"
url = "https://blpapi.bloomberg.com/repository/releases/python/simple"
priority = "supplemental"

[tool.poetry.dependencies]
blpapi = {source = "bloomberg"}

[tool.poetry.group.dev.dependencies]
pytest = ">=8.0"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Note: the old `[project.scripts]` entry (`issuer_opportunity_screener.main:main`) is intentionally dropped — there is no `main.py` in v2.

Create empty `src/issuer_opportunity_screener/__init__.py` and `src/issuer_opportunity_screener/sources/__init__.py`.

Run: `poetry lock && poetry install`
Expected: succeeds. If `blpapi` fails to build on this machine (no Bloomberg SDK), run `poetry install --no-root` won't help — instead temporarily verify with `poetry run python -c "import pandas, streamlit, pyarrow"`. If blpapi install is the blocker, move `blpapi` to an optional group:

```toml
[tool.poetry.group.bloomberg]
optional = true

[tool.poetry.group.bloomberg.dependencies]
blpapi = {version = ">=3.26.5.1,<4.0.0.0", source = "bloomberg"}
```

and remove it from `[project] dependencies`. Nothing else in the codebase imports blpapi at module level, so all tests pass without it.

- [ ] **Step 2: Seed `data/universe.csv`**

Create `data/universe.csv` with header `issuer,ticker,basket,country,sector,recognition_score,internal_rating` and one row per issuer from `docs/universe/candidate_names.typ` (88 rows). Tickers are best-effort Bloomberg issuer handles — mapping is validated on the Terminal machine later; `internal_rating` is blank everywhere (desk fills it). Use exactly these basket names (they become the validation set):

`Global Communications and Digital Platforms`, `Global Consumer and Leisure`, `Global Industrials, Autos, and Aerospace`, `Global Energy and Materials`, `Global Financials`, `Global Healthcare and Pharma`, `Latin America`, `Brazil`.

```csv
issuer,ticker,basket,country,sector,recognition_score,internal_rating
Tesla,TSLA,Global Communications and Digital Platforms,United States,Automotive and Technology,95,
Intel,INTC,Global Communications and Digital Platforms,United States,Technology,85,
AMD,AMD,Global Communications and Digital Platforms,United States,Technology,80,
Dell Technologies,DELL,Global Communications and Digital Platforms,United States,Technology,80,
Uber,UBER,Global Communications and Digital Platforms,United States,Technology and Mobility,95,
Netflix,NFLX,Global Communications and Digital Platforms,United States,Media and Entertainment,95,
Warner Bros. Discovery,WBD,Global Communications and Digital Platforms,United States,Media and Entertainment,75,
Paramount Global,PARA,Global Communications and Digital Platforms,United States,Media and Entertainment,70,
Comcast,CMCSA,Global Communications and Digital Platforms,United States,Media and Telecom,70,
Charter Communications,CHTR,Global Communications and Digital Platforms,United States,Media and Telecom,60,
T-Mobile US,TMUS,Global Communications and Digital Platforms,United States,Telecom,80,
AT&T,T,Global Communications and Digital Platforms,United States,Telecom,85,
AB InBev,ABIBB,Global Consumer and Leisure,Belgium,Beverages,85,
Kraft Heinz,KHC,Global Consumer and Leisure,United States,Consumer Staples,80,
Mondelez,MDLZ,Global Consumer and Leisure,United States,Consumer Staples,70,
Yum Brands,YUM,Global Consumer and Leisure,United States,Consumer Services,80,
Starbucks,SBUX,Global Consumer and Leisure,United States,Consumer Services,95,
Marriott International,MAR,Global Consumer and Leisure,United States,Hospitality,85,
Hilton Worldwide,HLT,Global Consumer and Leisure,United States,Hospitality,85,
Carnival,CCL,Global Consumer and Leisure,United States,Cruises and Leisure,80,
Royal Caribbean,RCL,Global Consumer and Leisure,United States,Cruises and Leisure,80,
Las Vegas Sands,LVS,Global Consumer and Leisure,United States,Gaming and Leisure,70,
Wynn Resorts,WYNN,Global Consumer and Leisure,United States,Gaming and Leisure,70,
Delta Air Lines,DAL,Global Consumer and Leisure,United States,Airlines,85,
Boeing,BA,Global Industrials, Autos, and Aerospace,United States,Aerospace,90,
Ford,F,Global Industrials, Autos, and Aerospace,United States,Automotive,90,
General Motors,GM,Global Industrials, Autos, and Aerospace,United States,Automotive,85,
Stellantis,STLA,Global Industrials, Autos, and Aerospace,Netherlands,Automotive,75,
Volkswagen,VW,Global Industrials, Autos, and Aerospace,Germany,Automotive,90,
Mercedes-Benz Group,MBG,Global Industrials, Autos, and Aerospace,Germany,Automotive,90,
Renault,RENAUL,Global Industrials, Autos, and Aerospace,France,Automotive,75,
Nissan Motor,NSANY,Global Industrials, Autos, and Aerospace,Japan,Automotive,80,
Hyundai Motor,HYNMTR,Global Industrials, Autos, and Aerospace,South Korea,Automotive,80,
Airbus,AIRFP,Global Industrials, Autos, and Aerospace,France,Aerospace,80,
Whirlpool,WHR,Global Industrials, Autos, and Aerospace,United States,Consumer Durables,75,
Goodyear Tire and Rubber,GT,Global Industrials, Autos, and Aerospace,United States,Automotive Components,75,
Occidental Petroleum,OXY,Global Energy and Materials,United States,Energy,70,
BP,BPLN,Global Energy and Materials,United Kingdom,Energy,85,
Shell,SHELL,Global Energy and Materials,United Kingdom,Energy,90,
TotalEnergies,TTEFP,Global Energy and Materials,France,Energy,75,
Repsol,REPSM,Global Energy and Materials,Spain,Energy,65,
Glencore,GLENLN,Global Energy and Materials,Switzerland,Materials and Mining,60,
ArcelorMittal,MTNA,Global Energy and Materials,Luxembourg,Steel and Mining,65,
Freeport-McMoRan,FCX,Global Energy and Materials,United States,Materials and Mining,60,
Newmont,NEM,Global Energy and Materials,United States,Materials and Mining,55,
Dow,DOW,Global Energy and Materials,United States,Chemicals,65,
LyondellBasell,LYB,Global Energy and Materials,United States,Chemicals,55,
Cleveland-Cliffs,CLF,Global Energy and Materials,United States,Steel,50,
Barclays,BACR,Global Financials,United Kingdom,Financials,80,
Deutsche Bank,DB,Global Financials,Germany,Financials,80,
Santander,SANTAN,Global Financials,Spain,Financials,90,
UniCredit,UCGIM,Global Financials,Italy,Financials,65,
Intesa Sanpaolo,ISPIM,Global Financials,Italy,Financials,60,
Societe Generale,SOCGEN,Global Financials,France,Financials,70,
Standard Chartered,STANLN,Global Financials,United Kingdom,Financials,60,
BBVA,BBVASM,Global Financials,Spain,Financials,75,
ING,INTNED,Global Financials,Netherlands,Financials,70,
NatWest Group,NWG,Global Financials,United Kingdom,Financials,60,
Lloyds Banking Group,LLOYDS,Global Financials,United Kingdom,Financials,65,
Ares Management,ARES,Global Financials,United States,Asset Management,50,
Bayer,BAYNGR,Global Healthcare and Pharma,Germany,Healthcare,85,
Teva Pharmaceutical,TEVA,Global Healthcare and Pharma,Israel,Healthcare,70,
CVS Health,CVS,Global Healthcare and Pharma,United States,Healthcare,80,
Walgreens Boots Alliance,WBA,Global Healthcare and Pharma,United States,Healthcare,75,
Viatris,VTRS,Global Healthcare and Pharma,United States,Healthcare,50,
Organon,OGN,Global Healthcare and Pharma,United States,Healthcare,45,
Biogen,BIIB,Global Healthcare and Pharma,United States,Healthcare,60,
GSK,GSK,Global Healthcare and Pharma,United Kingdom,Healthcare,75,
America Movil,AMXLMM,Latin America,Mexico,Telecom,80,
FEMSA,FEMSA,Latin America,Mexico,Consumer Staples,70,
Grupo Bimbo,BIMBOA,Latin America,Mexico,Consumer Staples,75,
Cemex,CEMEX,Latin America,Mexico,Materials,70,
Televisa,TELVIS,Latin America,Mexico,Media and Entertainment,70,
Ecopetrol,ECOPET,Latin America,Colombia,Energy,65,
Bancolombia,BCOLO,Latin America,Colombia,Financials,60,
Grupo Aval,AVALCB,Latin America,Colombia,Financials,50,
Cencosud,CENSUD,Latin America,Chile,Retail,60,
Falabella,FALAB,Latin America,Chile,Retail,60,
LATAM Airlines Group,LTM,Latin America,Chile,Airlines,75,
YPF,YPFDAR,Latin America,Argentina,Energy,65,
Petrobras,PETBRA,Brazil,Brazil,Energy,100,
Vale,VALEBZ,Brazil,Brazil,Materials and Mining,100,
Itau Unibanco,ITAU,Brazil,Brazil,Financials,100,
Bradesco,BRADES,Brazil,Brazil,Financials,100,
Banco do Brasil,BANBRA,Brazil,Brazil,Financials,100,
Suzano,SUZANO,Brazil,Brazil,Materials,90,
JBS,JBSSBZ,Brazil,Brazil,Protein and Food,95,
Marfrig,MARFRI,Brazil,Brazil,Protein and Food,85,
Gerdau,GGBRBZ,Brazil,Brazil,Steel,90,
CSN,CSNABZ,Brazil,Brazil,Steel and Mining,90,
Embraer,EMBRBZ,Brazil,Brazil,Aerospace,95,
Sabesp,SABESP,Brazil,Brazil,Utilities,90,
```

IMPORTANT (CSV correctness): the basket `Global Industrials, Autos, and Aerospace` contains commas — those fields MUST be double-quoted in the actual file, e.g. `Boeing,BA,"Global Industrials, Autos, and Aerospace",United States,Aerospace,90,`. Apply quoting to every row in that basket.

- [ ] **Step 3: Write the failing tests**

Create `tests/test_universe.py`:

```python
from pathlib import Path

import pytest

from issuer_opportunity_screener.universe import (
    BASKETS,
    UniverseError,
    load_universe,
)

REPO_UNIVERSE = Path(__file__).resolve().parents[1] / "data" / "universe.csv"

VALID_HEADER = "issuer,ticker,basket,country,sector,recognition_score,internal_rating\n"


def write(tmp_path, body):
    p = tmp_path / "universe.csv"
    p.write_text(VALID_HEADER + body, encoding="utf-8")
    return p


def test_loads_repo_universe():
    issuers = load_universe(REPO_UNIVERSE)
    assert len(issuers) >= 80
    tickers = [i.ticker for i in issuers]
    assert len(tickers) == len(set(tickers))
    assert all(i.basket in BASKETS for i in issuers)
    tesla = next(i for i in issuers if i.ticker == "TSLA")
    assert tesla.issuer == "Tesla"
    assert tesla.recognition_score == 95.0
    assert tesla.internal_rating is None


def test_duplicate_ticker_rejected(tmp_path):
    p = write(tmp_path, "A,TSLA,Brazil,Brazil,Energy,50,\nB,TSLA,Brazil,Brazil,Energy,50,\n")
    with pytest.raises(UniverseError, match="duplicate ticker 'TSLA'"):
        load_universe(p)


def test_unknown_basket_rejected(tmp_path):
    p = write(tmp_path, "A,TSLA,Weird Basket,US,Energy,50,\n")
    with pytest.raises(UniverseError, match="unknown basket 'Weird Basket'"):
        load_universe(p)


def test_recognition_out_of_range_rejected(tmp_path):
    p = write(tmp_path, "A,TSLA,Brazil,Brazil,Energy,150,\n")
    with pytest.raises(UniverseError, match="recognition_score"):
        load_universe(p)


def test_empty_file_rejected(tmp_path):
    p = tmp_path / "universe.csv"
    p.write_text(VALID_HEADER, encoding="utf-8")
    with pytest.raises(UniverseError, match="empty"):
        load_universe(p)


def test_internal_rating_kept_when_present(tmp_path):
    p = write(tmp_path, "A,TSLA,Brazil,Brazil,Energy,50,BB+\n")
    assert load_universe(p)[0].internal_rating == "BB+"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `poetry run pytest tests/test_universe.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` (universe module does not exist).

- [ ] **Step 5: Implement `universe.py`**

Create `src/issuer_opportunity_screener/universe.py`. Note: `UniverseIssuer` lives in `sources/base.py` per the spec's module map, but `base.py` is Task 2. To keep this task self-contained, define the dataclass here now; Task 2 moves it to `sources/base.py` and re-imports it here (exact instruction in Task 2 Step 3).

```python
"""Load and validate the issuer universe from data/universe.csv."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

BASKETS = {
    "Global Communications and Digital Platforms",
    "Global Consumer and Leisure",
    "Global Industrials, Autos, and Aerospace",
    "Global Energy and Materials",
    "Global Financials",
    "Global Healthcare and Pharma",
    "Latin America",
    "Brazil",
}


class UniverseError(ValueError):
    """The universe file is malformed; message names the offending rows."""


@dataclass(frozen=True)
class UniverseIssuer:
    issuer: str
    ticker: str
    basket: str
    country: str
    sector: str
    recognition_score: float
    internal_rating: str | None = None


def load_universe(path: Path) -> list[UniverseIssuer]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise UniverseError(f"{path}: universe file is empty")
    issuers: list[UniverseIssuer] = []
    errors: list[str] = []
    seen: set[str] = set()
    for lineno, row in enumerate(rows, start=2):
        ticker = (row.get("ticker") or "").strip()
        if not ticker:
            errors.append(f"line {lineno}: missing ticker")
            continue
        if ticker in seen:
            errors.append(f"line {lineno}: duplicate ticker {ticker!r}")
            continue
        seen.add(ticker)
        basket = (row.get("basket") or "").strip()
        if basket not in BASKETS:
            errors.append(f"line {lineno}: unknown basket {basket!r}")
            continue
        try:
            recognition = float(row.get("recognition_score") or "")
        except ValueError:
            errors.append(f"line {lineno}: recognition_score must be a number")
            continue
        if not 0.0 <= recognition <= 100.0:
            errors.append(f"line {lineno}: recognition_score must be within 0-100")
            continue
        issuers.append(
            UniverseIssuer(
                issuer=(row.get("issuer") or "").strip(),
                ticker=ticker,
                basket=basket,
                country=(row.get("country") or "").strip(),
                sector=(row.get("sector") or "").strip(),
                recognition_score=recognition,
                internal_rating=(row.get("internal_rating") or "").strip() or None,
            )
        )
    if errors:
        raise UniverseError(f"{path}: " + "; ".join(errors))
    return issuers
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `poetry run pytest tests/test_universe.py -q`
Expected: all PASS. If `test_loads_repo_universe` fails on the CSV, fix the CSV (quoting of comma-containing baskets is the usual culprit), not the loader.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml poetry.lock src/ data/universe.csv tests/test_universe.py
git commit -m "feat: scaffold v2 package with universe config and validated loader"
```

---

### Task 2: Source contract — `sources/base.py`

**Files:**
- Create: `src/issuer_opportunity_screener/sources/base.py`
- Modify: `src/issuer_opportunity_screener/universe.py` (move `UniverseIssuer` out)
- Test: `tests/test_sources_base.py`

**Interfaces:**
- Consumes: nothing.
- Produces (used by every later task):
  - `UniverseIssuer` (moved here; `universe.py` re-exports it).
  - `BondSnapshot(security, z_spread_bps, last_price, maturity, coupon)` — all optional.
  - `EquityOverlay(equity_ticker, price_change_3m_pct, price_change_12m_pct, recommendation_balance)` — all optional; `recommendation_balance` is in [-1, 1].
  - `IssuerCredit(ticker, cds_5y_bps, cds_liquidity_score, bond, rating_moody, rating_sp, rating_fitch, equity, quality_notes)`.
  - `HistoryPoint(ticker, date, spread_bps, instrument)` with `instrument` in `{"cds", "bond"}`.
  - `BrazilBenchmark(cds_5y_bps, z_spread_bps, rating_sp)`.
  - `FetchResult(as_of, source, issuers, history, brazil, failures)`.
  - `BloombergUnavailable(RuntimeError)`.
  - `CreditDataSource` Protocol: attribute `name: str`, method `fetch(self, issuers: list[UniverseIssuer]) -> FetchResult`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_sources_base.py`:

```python
import datetime as dt

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


def test_issuer_credit_defaults_are_empty_not_shared():
    a = IssuerCredit(ticker="AAA")
    b = IssuerCredit(ticker="BBB")
    a.quality_notes.append("note")
    assert b.quality_notes == []
    assert a.cds_5y_bps is None
    assert a.bond.z_spread_bps is None
    assert a.equity.equity_ticker is None


def test_fetch_result_shape():
    result = FetchResult(
        as_of=dt.datetime(2026, 7, 15, 12, 0),
        source="fixture",
        issuers=[IssuerCredit(ticker="AAA")],
        history=[HistoryPoint("AAA", dt.date(2026, 7, 1), 250.0, "cds")],
        brazil=BrazilBenchmark(cds_5y_bps=180.0, z_spread_bps=195.0, rating_sp="BB"),
    )
    assert result.failures == {}
    assert result.history[0].instrument == "cds"


def test_bloomberg_unavailable_is_runtime_error():
    assert issubclass(BloombergUnavailable, RuntimeError)


def test_universe_issuer_importable_from_both_modules():
    from issuer_opportunity_screener.universe import UniverseIssuer as FromUniverse

    assert FromUniverse is UniverseIssuer
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_sources_base.py -q`
Expected: FAIL — `ModuleNotFoundError: ... sources.base`.

- [ ] **Step 3: Implement `sources/base.py` and move `UniverseIssuer`**

Create `src/issuer_opportunity_screener/sources/base.py`:

```python
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
    bond: BondSnapshot = field(default_factory=BondSnapshot)
    rating_moody: str | None = None
    rating_sp: str | None = None
    rating_fitch: str | None = None
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
```

In `src/issuer_opportunity_screener/universe.py`: delete the local `UniverseIssuer` dataclass definition (and the now-unused `dataclass` import) and replace with:

```python
from issuer_opportunity_screener.sources.base import UniverseIssuer
```

Keep `UniverseIssuer` importable from `universe` (the plain import above achieves that).

- [ ] **Step 4: Run the full suite to verify pass and no regression**

Run: `poetry run pytest -q`
Expected: all PASS (Task 1 tests still green).

- [ ] **Step 5: Commit**

```bash
git add src/issuer_opportunity_screener/sources/base.py src/issuer_opportunity_screener/universe.py tests/test_sources_base.py
git commit -m "feat: add CreditDataSource protocol and shared credit datatypes"
```

---

### Task 3: Fixture source — `sources/fixture.py`

**Files:**
- Create: `src/issuer_opportunity_screener/sources/fixture.py`
- Test: `tests/test_fixture_source.py`

**Interfaces:**
- Consumes: everything from `sources/base.py`.
- Produces: `FixtureSource` (implements `CreditDataSource`, `name = "fixture"`), module constant `FIXTURE_BRAZIL = BrazilBenchmark(cds_5y_bps=180.0, z_spread_bps=195.0, rating_sp="BB")`. Deterministic: same universe in → identical `FetchResult` out. Edge-case roles by `idx % 6`: 0 normal, 1 missing CDS (bond-only), 2 unlisted equity, 3 partial history (8 points), 4 fetch failure (issuer in `failures`, not in `issuers`), 5 tight-vs-Brazil investment-grade name.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fixture_source.py`:

```python
from issuer_opportunity_screener.sources.fixture import FIXTURE_BRAZIL, FixtureSource
from issuer_opportunity_screener.universe import UniverseIssuer


def make_universe(n=12):
    return [
        UniverseIssuer(
            issuer=f"Issuer {i}",
            ticker=f"TICK{i}",
            basket="Brazil",
            country="Brazil",
            sector="Energy",
            recognition_score=80.0,
        )
        for i in range(n)
    ]


def test_deterministic():
    universe = make_universe()
    r1 = FixtureSource().fetch(universe)
    r2 = FixtureSource().fetch(universe)
    assert r1 == r2


def test_edge_case_roles():
    universe = make_universe(12)
    result = FixtureSource().fetch(universe)
    by_ticker = {c.ticker: c for c in result.issuers}

    assert result.source == "fixture"
    assert result.brazil == FIXTURE_BRAZIL

    # role 1: missing CDS but has a bond
    assert by_ticker["TICK1"].cds_5y_bps is None
    assert by_ticker["TICK1"].bond.z_spread_bps is not None
    assert any("cds" in n.lower() for n in by_ticker["TICK1"].quality_notes)

    # role 2: unlisted equity
    assert by_ticker["TICK2"].equity.equity_ticker is None

    # role 3: partial history (8 points vs 52 for normal names)
    hist3 = [h for h in result.history if h.ticker == "TICK3"]
    hist0 = [h for h in result.history if h.ticker == "TICK0"]
    assert len(hist3) == 8
    assert len(hist0) == 52

    # role 4: fetch failure — absent from issuers, present in failures
    assert "TICK4" not in by_ticker
    assert "TICK4" in result.failures

    # role 5: tighter than Brazil, strong rating
    assert by_ticker["TICK5"].cds_5y_bps < FIXTURE_BRAZIL.cds_5y_bps
    assert by_ticker["TICK5"].rating_sp == "BBB+"


def test_spreads_positive_and_history_matches_instrument():
    result = FixtureSource().fetch(make_universe(6))
    for credit in result.issuers:
        spread = credit.cds_5y_bps or credit.bond.z_spread_bps
        assert spread is not None and spread > 0
    instruments = {h.ticker: h.instrument for h in result.history}
    assert instruments["TICK1"] == "bond"
    assert instruments["TICK0"] == "cds"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_fixture_source.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `sources/fixture.py`**

```python
"""Deterministic synthetic credit data for development and tests.

Roles cycle by universe index (idx % 6):
  0 normal, 1 missing CDS, 2 unlisted equity, 3 partial history,
  4 fetch failure, 5 tight-vs-Brazil investment grade.
"""
from __future__ import annotations

import datetime as dt

from issuer_opportunity_screener.sources.base import (
    BondSnapshot,
    BrazilBenchmark,
    EquityOverlay,
    FetchResult,
    HistoryPoint,
    IssuerCredit,
    UniverseIssuer,
)

FIXTURE_BRAZIL = BrazilBenchmark(cds_5y_bps=180.0, z_spread_bps=195.0, rating_sp="BB")
FIXTURE_AS_OF = dt.datetime(2026, 7, 15, 12, 0, 0)

_RATINGS = ["BB+", "BB", "BB-", "B+"]
_MOODY = {"BBB+": "Baa1", "BB+": "Ba1", "BB": "Ba2", "BB-": "Ba3", "B+": "B1"}


class FixtureSource:
    name = "fixture"

    def fetch(self, issuers: list[UniverseIssuer]) -> FetchResult:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_fixture_source.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/issuer_opportunity_screener/sources/fixture.py tests/test_fixture_source.py
git commit -m "feat: add deterministic fixture credit source with edge-case roles"
```

---

### Task 4: Snapshot store — `snapshots.py`

**Files:**
- Create: `src/issuer_opportunity_screener/snapshots.py`
- Test: `tests/test_snapshots.py`

**Interfaces:**
- Consumes: `FetchResult`, `UniverseIssuer` from base; fixture source in tests.
- Produces:
  - `write_snapshot(root: Path, universe: list[UniverseIssuer], result: FetchResult) -> Path` — creates `root/<as_of:%Y-%m-%dT%H%M%S>/` with `snapshot.parquet`, `history.parquet`, `manifest.json`; raises `FileExistsError` if the directory already exists (append-only rule).
  - `list_snapshots(root: Path) -> list[Path]` (ascending by name), `latest(root: Path) -> Path | None`.
  - `load_snapshot(directory: Path) -> Snapshot` where `Snapshot` is a dataclass with `.directory: Path`, `.frame: pd.DataFrame`, `.history: pd.DataFrame`, `.manifest: dict`.
  - `snapshot.parquet` columns (exact, one row per universe issuer — including failed ones, with data columns null): `issuer, ticker, basket, country, sector, recognition_score, internal_rating, cds_5y_bps, cds_liquidity_score, bond_security, bond_z_spread_bps, bond_last_price, bond_maturity, bond_coupon, rating_moody, rating_sp, rating_fitch, equity_ticker, px_chg_3m_pct, px_chg_12m_pct, rec_balance, quality_notes` (`quality_notes` joined with `"; "`, empty string when none).
  - `history.parquet` columns: `ticker, date, spread_bps, instrument`.
  - `manifest.json` keys: `as_of` (ISO), `source`, `issuer_count` (universe size), `fetched_count`, `failures` (dict), `partial` (bool: any failures), `brazil` (`{"cds_5y_bps", "z_spread_bps", "rating_sp"}`), `coverage` (dict: fraction non-null per data column, for `cds_5y_bps, bond_z_spread_bps, bond_last_price, rating_sp, equity_ticker`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_snapshots.py`:

```python
import pytest

from issuer_opportunity_screener.snapshots import (
    latest,
    list_snapshots,
    load_snapshot,
    write_snapshot,
)
from issuer_opportunity_screener.sources.fixture import FixtureSource
from tests.test_fixture_source import make_universe


@pytest.fixture()
def universe():
    return make_universe(12)


@pytest.fixture()
def result(universe):
    return FixtureSource().fetch(universe)


def test_write_and_load_roundtrip(tmp_path, universe, result):
    snap_dir = write_snapshot(tmp_path, universe, result)
    assert snap_dir.name == "2026-07-15T120000"
    snap = load_snapshot(snap_dir)

    assert len(snap.frame) == 12  # failed issuer still has a row
    failed = snap.frame[snap.frame.ticker == "TICK4"].iloc[0]
    assert failed.isna()["cds_5y_bps"]

    assert set(snap.history.columns) == {"ticker", "date", "spread_bps", "instrument"}
    assert snap.manifest["source"] == "fixture"
    assert snap.manifest["partial"] is True
    assert snap.manifest["failures"] == {"TICK4": "fixture: simulated reference-data failure"}
    assert snap.manifest["issuer_count"] == 12
    assert snap.manifest["fetched_count"] == 10
    assert snap.manifest["brazil"]["cds_5y_bps"] == 180.0
    assert 0 < snap.manifest["coverage"]["cds_5y_bps"] < 1


def test_append_only(tmp_path, universe, result):
    write_snapshot(tmp_path, universe, result)
    with pytest.raises(FileExistsError):
        write_snapshot(tmp_path, universe, result)


def test_latest_and_list(tmp_path, universe, result):
    assert latest(tmp_path) is None
    d1 = write_snapshot(tmp_path, universe, result)
    assert list_snapshots(tmp_path) == [d1]
    assert latest(tmp_path) == d1


def test_quality_notes_joined(tmp_path, universe, result):
    snap = load_snapshot(write_snapshot(tmp_path, universe, result))
    row = snap.frame[snap.frame.ticker == "TICK1"].iloc[0]
    assert "no liquid CDS quote" in row.quality_notes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_snapshots.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `snapshots.py`**

```python
"""Versioned, append-only parquet snapshot store."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from issuer_opportunity_screener.sources.base import FetchResult, UniverseIssuer

SNAPSHOT_FILE = "snapshot.parquet"
HISTORY_FILE = "history.parquet"
MANIFEST_FILE = "manifest.json"
COVERAGE_COLUMNS = ["cds_5y_bps", "bond_z_spread_bps", "bond_last_price", "rating_sp", "equity_ticker"]


@dataclass
class Snapshot:
    directory: Path
    frame: pd.DataFrame
    history: pd.DataFrame
    manifest: dict


def _build_frame(universe: list[UniverseIssuer], result: FetchResult) -> pd.DataFrame:
    credit_by_ticker = {c.ticker: c for c in result.issuers}
    rows = []
    for u in universe:
        row: dict = {
            "issuer": u.issuer,
            "ticker": u.ticker,
            "basket": u.basket,
            "country": u.country,
            "sector": u.sector,
            "recognition_score": u.recognition_score,
            "internal_rating": u.internal_rating,
            "cds_5y_bps": None,
            "cds_liquidity_score": None,
            "bond_security": None,
            "bond_z_spread_bps": None,
            "bond_last_price": None,
            "bond_maturity": None,
            "bond_coupon": None,
            "rating_moody": None,
            "rating_sp": None,
            "rating_fitch": None,
            "equity_ticker": None,
            "px_chg_3m_pct": None,
            "px_chg_12m_pct": None,
            "rec_balance": None,
            "quality_notes": "",
        }
        credit = credit_by_ticker.get(u.ticker)
        if credit is not None:
            row.update(
                cds_5y_bps=credit.cds_5y_bps,
                cds_liquidity_score=credit.cds_liquidity_score,
                bond_security=credit.bond.security,
                bond_z_spread_bps=credit.bond.z_spread_bps,
                bond_last_price=credit.bond.last_price,
                bond_maturity=credit.bond.maturity,
                bond_coupon=credit.bond.coupon,
                rating_moody=credit.rating_moody,
                rating_sp=credit.rating_sp,
                rating_fitch=credit.rating_fitch,
                equity_ticker=credit.equity.equity_ticker,
                px_chg_3m_pct=credit.equity.price_change_3m_pct,
                px_chg_12m_pct=credit.equity.price_change_12m_pct,
                rec_balance=credit.equity.recommendation_balance,
                quality_notes="; ".join(credit.quality_notes),
            )
        rows.append(row)
    return pd.DataFrame(rows)


def write_snapshot(root: Path, universe: list[UniverseIssuer], result: FetchResult) -> Path:
    directory = Path(root) / result.as_of.strftime("%Y-%m-%dT%H%M%S")
    directory.mkdir(parents=True, exist_ok=False)

    frame = _build_frame(universe, result)
    frame.to_parquet(directory / SNAPSHOT_FILE, index=False)

    history = pd.DataFrame(
        [{"ticker": h.ticker, "date": h.date, "spread_bps": h.spread_bps, "instrument": h.instrument} for h in result.history],
        columns=["ticker", "date", "spread_bps", "instrument"],
    )
    history.to_parquet(directory / HISTORY_FILE, index=False)

    manifest = {
        "as_of": result.as_of.isoformat(),
        "source": result.source,
        "issuer_count": len(universe),
        "fetched_count": len(result.issuers),
        "failures": result.failures,
        "partial": bool(result.failures),
        "brazil": asdict(result.brazil),
        "coverage": {col: round(float(frame[col].notna().mean()), 4) for col in COVERAGE_COLUMNS},
    }
    (directory / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return directory


def list_snapshots(root: Path) -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    return sorted(d for d in root.iterdir() if d.is_dir() and (d / MANIFEST_FILE).exists())


def latest(root: Path) -> Path | None:
    snaps = list_snapshots(root)
    return snaps[-1] if snaps else None


def load_snapshot(directory: Path) -> Snapshot:
    directory = Path(directory)
    return Snapshot(
        directory=directory,
        frame=pd.read_parquet(directory / SNAPSHOT_FILE),
        history=pd.read_parquet(directory / HISTORY_FILE),
        manifest=json.loads((directory / MANIFEST_FILE).read_text(encoding="utf-8")),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_snapshots.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/issuer_opportunity_screener/snapshots.py tests/test_snapshots.py
git commit -m "feat: add append-only parquet snapshot store with quality manifest"
```

---

### Task 5: Pipeline — `pipeline.py`

**Files:**
- Create: `src/issuer_opportunity_screener/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `load_universe`, `CreditDataSource`, `write_snapshot`.
- Produces: `run_pipeline(universe_path: Path, source: CreditDataSource, snapshots_root: Path) -> Path` (returns the new snapshot directory). Propagates `UniverseError` and `BloombergUnavailable` unchanged — callers (the app) handle them.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline.py`:

```python
import pytest

from issuer_opportunity_screener.pipeline import run_pipeline
from issuer_opportunity_screener.snapshots import load_snapshot
from issuer_opportunity_screener.sources.base import BloombergUnavailable
from issuer_opportunity_screener.sources.fixture import FixtureSource
from issuer_opportunity_screener.universe import UniverseError

VALID_CSV = (
    "issuer,ticker,basket,country,sector,recognition_score,internal_rating\n"
    "Petrobras,PETBRA,Brazil,Brazil,Energy,100,\n"
    "Vale,VALEBZ,Brazil,Brazil,Materials and Mining,100,\n"
)


def test_pipeline_end_to_end(tmp_path):
    universe_path = tmp_path / "universe.csv"
    universe_path.write_text(VALID_CSV, encoding="utf-8")
    snap_dir = run_pipeline(universe_path, FixtureSource(), tmp_path / "snapshots")
    snap = load_snapshot(snap_dir)
    assert list(snap.frame.ticker) == ["PETBRA", "VALEBZ"]
    assert snap.manifest["source"] == "fixture"


def test_pipeline_propagates_universe_error(tmp_path):
    universe_path = tmp_path / "universe.csv"
    universe_path.write_text(
        "issuer,ticker,basket,country,sector,recognition_score,internal_rating\n"
        "X,ABC,Nope,Brazil,Energy,50,\n",
        encoding="utf-8",
    )
    with pytest.raises(UniverseError):
        run_pipeline(universe_path, FixtureSource(), tmp_path / "snapshots")


class ExplodingSource:
    name = "exploding"

    def fetch(self, issuers):
        raise BloombergUnavailable("no session")


def test_pipeline_propagates_bloomberg_unavailable(tmp_path):
    universe_path = tmp_path / "universe.csv"
    universe_path.write_text(VALID_CSV, encoding="utf-8")
    with pytest.raises(BloombergUnavailable):
        run_pipeline(universe_path, ExplodingSource(), tmp_path / "snapshots")
    assert not (tmp_path / "snapshots").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_pipeline.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `pipeline.py`**

```python
"""Orchestrates one data pull: universe -> source.fetch -> snapshot dir."""
from __future__ import annotations

from pathlib import Path

from issuer_opportunity_screener.snapshots import write_snapshot
from issuer_opportunity_screener.sources.base import CreditDataSource
from issuer_opportunity_screener.universe import load_universe


def run_pipeline(universe_path: Path, source: CreditDataSource, snapshots_root: Path) -> Path:
    issuers = load_universe(universe_path)
    result = source.fetch(issuers)
    return write_snapshot(snapshots_root, issuers, result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_pipeline.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/issuer_opportunity_screener/pipeline.py tests/test_pipeline.py
git commit -m "feat: add pipeline orchestrating universe fetch into snapshots"
```

---

### Task 6: Scoring foundations — ratings, viability, spread block

**Files:**
- Create: `src/issuer_opportunity_screener/scoring.py`
- Test: `tests/test_scoring_signals.py`

**Interfaces:**
- Consumes: nothing yet (pure functions over floats/strings; Task 7 wires it to snapshots).
- Produces (Task 7 and the app rely on these exact names):
  - `normalize_rating(raw: str | None) -> str | None` — uppercases S&P/Fitch style, maps Moody's (`Ba2` → `BB`), strips outlook decorations (`"BB+ *-"` → `"BB+"`, `"BBB (stable)"` → `"BBB"`); returns `None` for unknown/empty.
  - `rating_rank(rating: str | None) -> int | None` — position in the AAA…D scale (AAA=0, lower is stronger).
  - `composite_rating_rank(moody, sp, fitch) -> int | None` — median of available ranks (middle value; average of the two middles rounded to int for even counts).
  - `rating_score(rank: int | None) -> float | None` — `100 - rank * (100/21)`, clamped 0–100.
  - `viability(spread_bps, issuer_rank, brazil_cds_bps, brazil_rank) -> tuple[float | None, bool]` — implements the desk rule verbatim (see Global Constraints).
  - `clamp(x, lo=0.0, hi=100.0) -> float`.
  - Block-1 signal functions, each `-> float | None`: `spread_level_score(spread_bps)` (= `clamp(spread_bps / 6.0)`, i.e. 600 bps ⇒ 100), `history_percentile_score(spread_bps, history: list[float])` (percentile rank × 100; `None` if fewer than 12 points), `vs_ma_score(spread_bps, history)` (= `clamp(50 * spread / mean(history))`; at-average ⇒ 50), `vs_p75_score(spread_bps, history)` (= `clamp(100 * spread / p75)`; at-p75 ⇒ 100 cap), `peer_median_score(spread_bps, peer_median_bps)` (= `clamp(50 + 50 * (spread - peer_median) / peer_median)`).
  - `SignalScore(name: str, raw: float | None, score: float | None)` and `BlockScore(name: str, weight: float, score: float | None, signals: list[SignalScore])` dataclasses; `block_score(signals) -> float | None` (mean of non-None signal scores, `None` if none).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scoring_signals.py`:

```python
import pytest

from issuer_opportunity_screener.scoring import (
    SignalScore,
    block_score,
    clamp,
    composite_rating_rank,
    history_percentile_score,
    normalize_rating,
    peer_median_score,
    rating_rank,
    rating_score,
    spread_level_score,
    viability,
    vs_ma_score,
    vs_p75_score,
)


def test_normalize_rating():
    assert normalize_rating("BB+") == "BB+"
    assert normalize_rating("bb+") == "BB+"
    assert normalize_rating("Ba2") == "BB"
    assert normalize_rating("Baa3") == "BBB-"
    assert normalize_rating("BB+ *-") == "BB+"
    assert normalize_rating("BBB (stable)") == "BBB"
    assert normalize_rating("NR") is None
    assert normalize_rating(None) is None
    assert normalize_rating("") is None


def test_rating_rank_ordering():
    assert rating_rank("AAA") == 0
    assert rating_rank("BB") > rating_rank("BBB-")
    assert rating_rank("Ba2") == rating_rank("BB")  # normalizes first
    assert rating_rank("XYZ") is None


def test_composite_rating_rank_median():
    # BB+ (10), BB (11), BB- (12) -> median 11
    assert composite_rating_rank("Ba1", "BB", "BB-") == 11
    # two values -> rounded mean of 10 and 11 -> 10 or 11; int() of 10.5 rounds to 10 with round-half-even
    assert composite_rating_rank(None, "BB+", "BB") == round((10 + 11) / 2)
    assert composite_rating_rank(None, None, None) is None


def test_rating_score_endpoints():
    assert rating_score(0) == 100.0
    assert rating_score(21) == 0.0
    assert rating_score(None) is None


def test_viability_desk_rule():
    # spread >= Brazil: viable
    assert viability(200.0, 11, 180.0, 11) == (20.0, True)
    # within -20 and stronger rating (rank lower than Brazil): viable
    diff, viable = viability(165.0, 8, 180.0, 11)
    assert diff == -15.0 and viable is True
    # within -20 but same/weaker rating: not viable
    assert viability(165.0, 11, 180.0, 11)[1] is False
    # beyond -20 even with stronger rating: not viable
    assert viability(150.0, 0, 180.0, 11)[1] is False
    # no spread: no verdict data
    assert viability(None, 5, 180.0, 11) == (None, False)
    # within -20, stronger rating unknown: not viable
    assert viability(165.0, None, 180.0, 11)[1] is False


def test_spread_level_score():
    assert spread_level_score(300.0) == 50.0
    assert spread_level_score(600.0) == 100.0
    assert spread_level_score(900.0) == 100.0  # clamped
    assert spread_level_score(None) is None


def test_history_percentile_score():
    hist = [float(x) for x in range(100, 200)]  # 100 points, 100..199
    assert history_percentile_score(199.0, hist) == pytest.approx(100.0)
    assert history_percentile_score(100.0, hist) == pytest.approx(1.0)
    assert history_percentile_score(150.0, hist) == pytest.approx(51.0)
    assert history_percentile_score(150.0, [1.0] * 5) is None  # < 12 points
    assert history_percentile_score(None, hist) is None


def test_vs_ma_and_p75():
    hist = [100.0] * 20
    assert vs_ma_score(100.0, hist) == 50.0
    assert vs_ma_score(200.0, hist) == 100.0
    assert vs_p75_score(100.0, hist) == 100.0
    assert vs_p75_score(50.0, hist) == 50.0
    assert vs_ma_score(None, hist) is None
    assert vs_p75_score(100.0, []) is None


def test_peer_median_score():
    assert peer_median_score(200.0, 200.0) == 50.0
    assert peer_median_score(300.0, 200.0) == 75.0
    assert peer_median_score(50.0, 200.0) == clamp(50 + 50 * (50 - 200) / 200)
    assert peer_median_score(200.0, None) is None


def test_block_score_mean_of_available():
    signals = [
        SignalScore("a", 1.0, 40.0),
        SignalScore("b", None, None),
        SignalScore("c", 2.0, 60.0),
    ]
    assert block_score(signals) == 50.0
    assert block_score([SignalScore("a", None, None)]) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_scoring_signals.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the foundations in `scoring.py`**

```python
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
    brazil_cds_bps: float,
    brazil_rank: int | None,
) -> tuple[float | None, bool]:
    if spread_bps is None:
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
```

Note on `test_history_percentile_score` expectations: with 100 points `100..199`, spread `150.0` counts 51 values ≤ 150 → 51.0; spread `100.0` counts 1 → 1.0. The test matches this "fraction ≤" definition exactly.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_scoring_signals.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/issuer_opportunity_screener/scoring.py tests/test_scoring_signals.py
git commit -m "feat: add rating normalization, viability rule, and spread signals"
```

---

### Task 7: Composite scoring over snapshots

**Files:**
- Modify: `src/issuer_opportunity_screener/scoring.py` (append)
- Test: `tests/test_scoring_composite.py`

**Interfaces:**
- Consumes: `Snapshot` from `snapshots.py`; everything from Task 6.
- Produces:
  - `IssuerScore` dataclass: `ticker: str`, `composite: float`, `tier: str` ("A"/"B"/"C"), `viable: bool`, `spread_vs_brazil_bps: float | None`, `partial_data: bool`, `blocks: list[BlockScore]`.
  - `WEIGHTS: dict[str, float]` = `{"Credit and Spread Attractiveness": 0.35, "Credit Quality and Risk": 0.20, "Market Liquidity and Accessibility": 0.20, "Equity Overlay": 0.10, "Recognition and Client Fit": 0.15}`.
  - `score_snapshot(snap: Snapshot) -> list[IssuerScore]` — one entry per row that has ANY spread (rows with neither CDS nor bond z-spread are skipped; the dashboard lists them from the manifest failures/coverage instead).
  - `screen_frame(snap: Snapshot, scores: list[IssuerScore]) -> pd.DataFrame` — dashboard-ready, sorted by composite desc, columns exactly: `issuer, ticker, basket, tier, composite, viable, spread_vs_brazil_bps, cds_5y_bps, bond_z_spread_bps, bond_last_price, rating_composite, internal_rating, recognition_score, partial_data, quality_notes` (`rating_composite` is the normalized S&P-style string of the issuer's composite rank via `RATING_ORDER`).
  - Block construction rules (exact):
    - Primary spread = `cds_5y_bps` if present else `bond_z_spread_bps`.
    - Block 1 signals: `spread_level`, `history_percentile`, `vs_1y_ma`, `vs_1y_p75` (history = that ticker's `spread_bps` list from `snap.history`), `vs_peer_median` (peer median = median primary spread of other issuers in the same basket, `None` if no peers with spreads).
    - Block 2 signals: `external_rating` (= `rating_score(composite_rating_rank(...))`), `internal_rating` (= `rating_score(rating_rank(internal_rating))`).
    - Block 3 signals: `cds_available` (100.0 if `cds_5y_bps` present else 0.0), `cds_liquidity` (`cds_liquidity_score` as-is), `bond_available` (100.0 if `bond_security` present else 0.0).
    - Block 4: if `equity_ticker` is null the whole block score is `None` (skipped, weights renormalize). Otherwise signals: `momentum_3m` (= `clamp(50 + px_chg_3m_pct)`), `momentum_12m` (= `clamp(50 + px_chg_12m_pct / 2)`), `recommendations` (= `clamp(50 + 50 * rec_balance)`).
    - Block 5 signal: `recognition` (= `recognition_score` as-is).
    - Composite = `sum(w_b * s_b) / sum(w_b)` over blocks with score ≠ None, rounded to 1 decimal.
    - `partial_data` = any block score is None OR `quality_notes` non-empty.
    - Viability uses `manifest["brazil"]["cds_5y_bps"]` and `rating_rank(manifest["brazil"]["rating_sp"])`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scoring_composite.py`:

```python
import pytest

from issuer_opportunity_screener.scoring import (
    WEIGHTS,
    score_snapshot,
    screen_frame,
)
from issuer_opportunity_screener.snapshots import load_snapshot, write_snapshot
from issuer_opportunity_screener.sources.fixture import FixtureSource
from tests.test_fixture_source import make_universe


@pytest.fixture(scope="module")
def snap(tmp_path_factory):
    universe = make_universe(12)
    result = FixtureSource().fetch(universe)
    root = tmp_path_factory.mktemp("snaps")
    return load_snapshot(write_snapshot(root, universe, result))


def test_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_scores_one_per_fetched_issuer(snap):
    scores = score_snapshot(snap)
    # 12 universe rows, TICK4 failed (no spread) -> 10 scored (TICK10 is role 4 too)
    assert {s.ticker for s in scores} == {
        "TICK0", "TICK1", "TICK2", "TICK3", "TICK5",
        "TICK6", "TICK7", "TICK8", "TICK9", "TICK11",
    }
    for s in scores:
        assert 0.0 <= s.composite <= 100.0
        assert s.tier in {"A", "B", "C"}
        assert len(s.blocks) == 5


def test_composite_renormalizes_missing_blocks(snap):
    scores = {s.ticker: s for s in score_snapshot(snap)}
    unlisted = scores["TICK2"]  # role 2: no equity -> block 4 None
    equity_block = next(b for b in unlisted.blocks if b.name == "Equity Overlay")
    assert equity_block.score is None
    assert unlisted.partial_data is True
    available = [b for b in unlisted.blocks if b.score is not None]
    expected = sum(b.weight * b.score for b in available) / sum(b.weight for b in available)
    assert unlisted.composite == pytest.approx(round(expected, 1))


def test_viability_flags(snap):
    scores = {s.ticker: s for s in score_snapshot(snap)}
    # TICK5: 140 bps vs Brazil 180 = -40 -> below tolerance, not viable even at BBB+
    assert scores["TICK5"].viable is False
    assert scores["TICK5"].spread_vs_brazil_bps == pytest.approx(-40.0)
    # TICK0: base spread 90+0=90? No: idx0 -> 90.0 bps -> -90 not viable
    assert scores["TICK0"].viable is False
    # TICK6: 90 + (6*37)%320 = 90+222 = 312 -> viable
    assert scores["TICK6"].viable is True


def test_screen_frame_shape_and_order(snap):
    scores = score_snapshot(snap)
    frame = screen_frame(snap, scores)
    assert list(frame.columns) == [
        "issuer", "ticker", "basket", "tier", "composite", "viable",
        "spread_vs_brazil_bps", "cds_5y_bps", "bond_z_spread_bps",
        "bond_last_price", "rating_composite", "internal_rating",
        "recognition_score", "partial_data", "quality_notes",
    ]
    assert len(frame) == len(scores)
    assert list(frame.composite) == sorted(frame.composite, reverse=True)
    tick1 = frame[frame.ticker == "TICK1"].iloc[0]
    assert tick1.rating_composite in {"BB", "BB+", "BB-", "B+", "BBB+"}


def test_breakdown_signals_present(snap):
    score = next(s for s in score_snapshot(snap) if s.ticker == "TICK0")
    block1 = next(b for b in score.blocks if b.name == "Credit and Spread Attractiveness")
    assert {sig.name for sig in block1.signals} == {
        "spread_level", "history_percentile", "vs_1y_ma", "vs_1y_p75", "vs_peer_median",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_scoring_composite.py -q`
Expected: FAIL — `ImportError: cannot import name 'score_snapshot'`.

- [ ] **Step 3: Append composite scoring to `scoring.py`**

Append (imports go to the top of the file: `import pandas as pd`, `from issuer_opportunity_screener.snapshots import Snapshot`):

```python
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
        ext_rank = composite_rating_rank(row.rating_moody, row.rating_sp, row.rating_fitch)

        block1 = BlockScore(
            "Credit and Spread Attractiveness",
            WEIGHTS["Credit and Spread Attractiveness"],
            None,
            [
                SignalScore("spread_level", spread, spread_level_score(spread)),
                SignalScore("history_percentile", spread, history_percentile_score(spread, history)),
                SignalScore("vs_1y_ma", spread, vs_ma_score(spread, history)),
                SignalScore("vs_1y_p75", spread, vs_p75_score(spread, history)),
                SignalScore("vs_peer_median", peer_medians[row.ticker], peer_median_score(spread, peer_medians[row.ticker])),
            ],
        )
        block2 = BlockScore(
            "Credit Quality and Risk",
            WEIGHTS["Credit Quality and Risk"],
            None,
            [
                SignalScore("external_rating", float(ext_rank) if ext_rank is not None else None, rating_score(ext_rank)),
                SignalScore(
                    "internal_rating",
                    float(rating_rank(row.internal_rating)) if rating_rank(row.internal_rating) is not None else None,
                    rating_score(rating_rank(row.internal_rating)),
                ),
            ],
        )
        has_cds = pd.notna(row.cds_5y_bps)
        block3 = BlockScore(
            "Market Liquidity and Accessibility",
            WEIGHTS["Market Liquidity and Accessibility"],
            None,
            [
                SignalScore("cds_available", 1.0 if has_cds else 0.0, 100.0 if has_cds else 0.0),
                SignalScore("cds_liquidity", _opt(row.cds_liquidity_score), _opt(row.cds_liquidity_score)),
                SignalScore(
                    "bond_available",
                    1.0 if pd.notna(row.bond_security) else 0.0,
                    100.0 if pd.notna(row.bond_security) else 0.0,
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
                    SignalScore("momentum_3m", _opt(row.px_chg_3m_pct), clamp(50.0 + row.px_chg_3m_pct) if pd.notna(row.px_chg_3m_pct) else None),
                    SignalScore("momentum_12m", _opt(row.px_chg_12m_pct), clamp(50.0 + row.px_chg_12m_pct / 2.0) if pd.notna(row.px_chg_12m_pct) else None),
                    SignalScore("recommendations", _opt(row.rec_balance), clamp(50.0 + 50.0 * row.rec_balance) if pd.notna(row.rec_balance) else None),
                ],
            )
        block5 = BlockScore(
            "Recognition and Client Fit",
            WEIGHTS["Recognition and Client Fit"],
            None,
            [SignalScore("recognition", float(row.recognition_score), float(row.recognition_score))],
        )

        blocks = [
            BlockScore(b.name, b.weight, block_score(b.signals) if b.signals else None, b.signals)
            for b in (block1, block2, block3, block4, block5)
        ]
        available = [b for b in blocks if b.score is not None]
        composite = round(sum(b.weight * b.score for b in available) / sum(b.weight for b in available), 1)
        diff, viable = viability(spread, ext_rank, brazil_cds, brazil_rank)
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
        ext_rank = composite_rating_rank(row.rating_moody, row.rating_sp, row.rating_fitch)
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
                "internal_rating": row.internal_rating if pd.notna(row.internal_rating) else None,
                "recognition_score": float(row.recognition_score),
                "partial_data": score.partial_data,
                "quality_notes": row.quality_notes,
            }
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values("composite", ascending=False).reset_index(drop=True)
```

- [ ] **Step 4: Run the full suite**

Run: `poetry run pytest -q`
Expected: all PASS. If `test_viability_flags` disagrees on a fixture number, recompute by hand from the fixture formula (`base = 90 + (idx * 37) % 320`) — fix the TEST only if the hand computation says the implementation is right.

- [ ] **Step 5: Commit**

```bash
git add src/issuer_opportunity_screener/scoring.py tests/test_scoring_composite.py
git commit -m "feat: add snapshot-level composite scoring, tiers, and screen frame"
```

---

### Task 8: Bloomberg adapter — `sources/bloomberg.py`

**Files:**
- Create: `src/issuer_opportunity_screener/sources/bloomberg.py`
- Test: `tests/test_bloomberg_mapping.py`

**Interfaces:**
- Consumes: types from `sources/base.py`.
- Produces: `BloombergSource(host="localhost", port=8194)` implementing `CreditDataSource` with `name = "bloomberg"`. `fetch()` raises `BloombergUnavailable` when no session. Pure, unit-tested helpers (the blpapi boundary returns plain dicts so helpers stay testable without a Terminal):
  - `cds_ticker(issuer_ticker: str) -> str` = `f"{issuer_ticker} CDS USD SR 5Y D14 Corp"`.
  - `select_bond(candidates: list[dict], as_of: dt.date) -> dict | None` — filter to `crncy == "USD"`, `payment_rank` containing `"Sr Unsecured"`, maturity 3–10 years from `as_of`; pick min `abs(years_to_maturity - 5)`, tiebreak max `amt_outstanding`.
  - `credit_from_fields(ticker: str, fields: dict, bond: dict | None) -> IssuerCredit` — maps the plain-dict field values to the dataclass, appending quality notes for anything missing.
- IMPORTANT: `import blpapi` happens ONLY inside `BloombergSource._connect()`. Module import must succeed without blpapi installed.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bloomberg_mapping.py`:

```python
import datetime as dt

from issuer_opportunity_screener.sources.bloomberg import (
    cds_ticker,
    credit_from_fields,
    select_bond,
)

AS_OF = dt.date(2026, 7, 15)


def bond(security, years, rank="Sr Unsecured", crncy="USD", amt=500e6, z=250.0):
    return {
        "security": security,
        "crncy": crncy,
        "payment_rank": rank,
        "maturity": AS_OF + dt.timedelta(days=int(365.25 * years)),
        "amt_outstanding": amt,
        "z_spread_bps": z,
        "last_price": 98.0,
        "coupon": 5.0,
    }


def test_cds_ticker():
    assert cds_ticker("PETBRA") == "PETBRA CDS USD SR 5Y D14 Corp"


def test_select_bond_prefers_closest_to_5y():
    picked = select_bond([bond("A", 3.5), bond("B", 5.2), bond("C", 9.0)], as_of=AS_OF)
    assert picked["security"] == "B"


def test_select_bond_filters_currency_rank_and_tenor():
    candidates = [
        bond("EUR", 5.0, crncy="EUR"),
        bond("SUB", 5.0, rank="Subordinated"),
        bond("SHORT", 2.0),
        bond("LONG", 12.0),
        bond("OK", 6.0),
    ]
    assert select_bond(candidates, as_of=AS_OF)["security"] == "OK"


def test_select_bond_tiebreak_amount_outstanding():
    picked = select_bond([bond("SMALL", 5.0, amt=100e6), bond("BIG", 5.0, amt=900e6)], as_of=AS_OF)
    assert picked["security"] == "BIG"


def test_select_bond_none_when_no_candidates():
    assert select_bond([], as_of=AS_OF) is None
    assert select_bond([bond("EUR", 5.0, crncy="EUR")], as_of=AS_OF) is None


def test_credit_from_fields_full():
    credit = credit_from_fields(
        "PETBRA",
        {
            "cds_5y_bps": 210.5,
            "cds_liquidity_score": 70.0,
            "rating_moody": "Ba1",
            "rating_sp": "BB",
            "rating_fitch": "BB",
            "equity_ticker": "PBR US Equity",
            "px_chg_3m_pct": 4.2,
            "px_chg_12m_pct": -8.0,
            "rec_balance": 0.4,
        },
        bond("PETBRA 5.6 2031", 5.0),
    )
    assert credit.cds_5y_bps == 210.5
    assert credit.bond.security == "PETBRA 5.6 2031"
    assert credit.quality_notes == []


def test_credit_from_fields_missing_pieces_add_notes():
    credit = credit_from_fields("XXX", {}, None)
    assert credit.cds_5y_bps is None
    assert credit.bond.security is None
    assert credit.equity.equity_ticker is None
    notes = " ".join(credit.quality_notes).lower()
    assert "cds" in notes and "bond" in notes and "equity" in notes


def test_module_importable_without_blpapi():
    import issuer_opportunity_screener.sources.bloomberg  # noqa: F401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_bloomberg_mapping.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `sources/bloomberg.py`**

```python
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


def cds_ticker(issuer_ticker: str) -> str:
    return f"{issuer_ticker} CDS USD SR 5Y D14 Corp"


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

    def __init__(self, host: str = "localhost", port: int = 8194):
        self.host = host
        self.port = port

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
                        values[str(el.name())] = el.getValue()
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
                            (row.getElementAsDatetime("date").date(), row.getElementAsFloat("PX_LAST"))
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
                bond = select_bond(self._bond_candidates(session, issuer.ticker), as_of=as_of.date())
                credit = credit_from_fields(issuer.ticker, fields, bond)
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

    def _bond_candidates(self, session, issuer_ticker: str) -> list[dict]:
        """Discover the issuer's bonds via BOND_CHAIN BDS, then pull BOND_FIELDS."""
        chain_rows = self._reference_fields(session, [f"{issuer_ticker} US Equity"], ["BOND_CHAIN"])
        chain = chain_rows.get(f"{issuer_ticker} US Equity", {}).get("BOND_CHAIN") or []
        securities = [str(item) for item in chain][:50]
        if not securities:
            return []
        rows = self._reference_fields(session, securities, BOND_FIELDS)
        candidates = []
        for security, values in rows.items():
            maturity = values.get("MATURITY")
            candidates.append(
                {
                    "security": security,
                    "crncy": values.get("CRNCY"),
                    "payment_rank": values.get("PAYMENT_RANK"),
                    "maturity": maturity.date() if hasattr(maturity, "date") else maturity,
                    "amt_outstanding": values.get("AMT_OUTSTANDING"),
                    "z_spread_bps": values.get("YAS_ZSPREAD"),
                    "last_price": values.get("PX_LAST"),
                    "coupon": values.get("CPN"),
                }
            )
        return candidates
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_bloomberg_mapping.py -q`
Expected: all PASS (pure helpers + import test; live paths run only on the Terminal machine).

- [ ] **Step 5: Commit**

```bash
git add src/issuer_opportunity_screener/sources/bloomberg.py tests/test_bloomberg_mapping.py
git commit -m "feat: add blpapi adapter with tested bond selection and field mapping"
```

---

### Task 9: Streamlit dashboard — `app.py`

**Files:**
- Create: `src/issuer_opportunity_screener/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `snapshots.list_snapshots/latest/load_snapshot`, `scoring.score_snapshot/screen_frame/IssuerScore`, `pipeline.run_pipeline`, `BloombergSource`, `FixtureSource`, `BloombergUnavailable`.
- Produces: the Streamlit app. Data root resolution (exact): `Path(os.environ.get("IOS_DATA_DIR", "data"))`; universe at `<root>/universe.csv`, snapshots at `<root>/snapshots`. Env var `IOS_SOURCE=fixture` makes the Refresh button use `FixtureSource` (used by tests and local dev); default is `BloombergSource`.
- Run locally with: `poetry run streamlit run src/issuer_opportunity_screener/app.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_app.py`:

```python
import pytest
from streamlit.testing.v1 import AppTest

from issuer_opportunity_screener.pipeline import run_pipeline
from issuer_opportunity_screener.sources.fixture import FixtureSource

APP_PATH = "src/issuer_opportunity_screener/app.py"

UNIVERSE_CSV = (
    "issuer,ticker,basket,country,sector,recognition_score,internal_rating\n"
    + "".join(
        f"Issuer {i},TICK{i},Brazil,Brazil,Energy,80,\n" for i in range(12)
    )
)


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    (tmp_path / "universe.csv").write_text(UNIVERSE_CSV, encoding="utf-8")
    run_pipeline(tmp_path / "universe.csv", FixtureSource(), tmp_path / "snapshots")
    monkeypatch.setenv("IOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("IOS_SOURCE", "fixture")
    return tmp_path


def test_app_renders_screen_tab(data_dir):
    at = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert not at.exception
    # data-as-of banner in sidebar
    assert any("2026-07-15" in str(md.value) for md in at.sidebar.markdown)
    # screen table rendered with scored issuers
    assert len(at.dataframe) >= 1
    screen = at.dataframe[0].value
    assert "composite" in screen.columns
    assert len(screen) == 10  # 12 universe - 2 fixture failures (roles idx 4, 10)


def test_app_shows_message_when_no_snapshot(tmp_path, monkeypatch):
    (tmp_path / "universe.csv").write_text(UNIVERSE_CSV, encoding="utf-8")
    monkeypatch.setenv("IOS_DATA_DIR", str(tmp_path))
    at = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert not at.exception
    assert any("No snapshot" in str(w.value) for w in at.warning)


def test_refresh_button_runs_fixture_pipeline(data_dir):
    at = AppTest.from_file(APP_PATH, default_timeout=30).run()
    button = next(b for b in at.sidebar.button if "Refresh" in b.label)
    button.click()
    at.run()
    assert not at.exception
    snapshots = list((data_dir / "snapshots").iterdir())
    # fixture as_of is fixed -> the append-only store refuses the duplicate dir;
    # the app must catch FileExistsError and keep rendering (still exactly 1 snapshot)
    assert len(snapshots) == 1
```

Note: the third test asserts the app survives a refresh click without exception; the duplicate-directory case (fixture has a fixed `as_of`) must be caught by the app and shown as a warning, not raised. (Warning text is not asserted because sidebar-scoped warnings are not reliably visible through `at.warning`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_app.py -q`
Expected: FAIL — app file does not exist.

- [ ] **Step 3: Implement `app.py`**

```python
"""Issuer Opportunity Screener — Streamlit dashboard.

Reads the latest snapshot under $IOS_DATA_DIR (default ./data), scores it
in-memory, renders three tabs. Never talks to blpapi directly; the Refresh
button runs the pipeline and falls back gracefully when Bloomberg is away.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from issuer_opportunity_screener.pipeline import run_pipeline
from issuer_opportunity_screener.scoring import IssuerScore, score_snapshot, screen_frame
from issuer_opportunity_screener.snapshots import Snapshot, list_snapshots, load_snapshot
from issuer_opportunity_screener.sources.base import BloombergUnavailable
from issuer_opportunity_screener.universe import UniverseError

DATA_ROOT = Path(os.environ.get("IOS_DATA_DIR", "data"))
UNIVERSE_PATH = DATA_ROOT / "universe.csv"
SNAPSHOTS_ROOT = DATA_ROOT / "snapshots"

st.set_page_config(page_title="Issuer Opportunity Screener", layout="wide")
st.title("Issuer Opportunity Screener")


def make_source():
    if os.environ.get("IOS_SOURCE") == "fixture":
        from issuer_opportunity_screener.sources.fixture import FixtureSource

        return FixtureSource()
    from issuer_opportunity_screener.sources.bloomberg import BloombergSource

    return BloombergSource()


def sidebar(snapshot_dirs: list[Path]) -> Path | None:
    with st.sidebar:
        st.header("Data")
        if st.button("Refresh from Bloomberg"):
            try:
                new_dir = run_pipeline(UNIVERSE_PATH, make_source(), SNAPSHOTS_ROOT)
                st.success(f"New snapshot: {new_dir.name}")
                snapshot_dirs = list_snapshots(SNAPSHOTS_ROOT)
            except BloombergUnavailable as exc:
                st.warning(f"Bloomberg unavailable — staying on current snapshot. ({exc})")
            except FileExistsError:
                st.warning("Snapshot for this timestamp already exists; nothing to do.")
            except UniverseError as exc:
                st.error(str(exc))
        if not snapshot_dirs:
            return None
        labels = [d.name for d in reversed(snapshot_dirs)]
        chosen = st.selectbox("Snapshot", labels, index=0)
        return SNAPSHOTS_ROOT / chosen


def render_screen_tab(snap: Snapshot, scores: list[IssuerScore]):
    frame = screen_frame(snap, scores)
    col1, col2, col3, col4 = st.columns(4)
    baskets = col1.multiselect("Basket", sorted(frame.basket.unique()))
    tiers = col2.multiselect("Tier", ["A", "B", "C"])
    only_viable = col3.checkbox("Viable vs Brazil only")
    min_spread = col4.number_input("Min spread (bps)", value=0.0, step=25.0)

    view = frame
    if baskets:
        view = view[view.basket.isin(baskets)]
    if tiers:
        view = view[view.tier.isin(tiers)]
    if only_viable:
        view = view[view.viable]
    spread = view.cds_5y_bps.fillna(view.bond_z_spread_bps)
    view = view[spread.fillna(0) >= min_spread]

    st.dataframe(view, width="stretch", hide_index=True)
    st.download_button(
        "Export current view (CSV)",
        view.to_csv(index=False).encode("utf-8"),
        file_name=f"screen_{snap.directory.name}.csv",
        mime="text/csv",
    )


def render_issuer_tab(snap: Snapshot, scores: list[IssuerScore]):
    by_ticker = {s.ticker: s for s in scores}
    frame = snap.frame.set_index("ticker")
    ticker = st.selectbox("Issuer", sorted(by_ticker), format_func=lambda t: f"{frame.loc[t].issuer} ({t})")
    score = by_ticker[ticker]
    row = frame.loc[ticker]

    left, right = st.columns(2)
    left.metric("Composite", f"{score.composite:.1f}", f"Tier {score.tier}")
    right.metric(
        "Spread vs Brazil",
        f"{score.spread_vs_brazil_bps:+.0f} bps" if score.spread_vs_brazil_bps is not None else "n/a",
        "viable" if score.viable else "not viable",
        delta_color="normal" if score.viable else "inverse",
    )

    breakdown = pd.DataFrame(
        [
            {"block": b.name, "weight": b.weight, "signal": s.name, "raw": s.raw, "score": s.score}
            for b in score.blocks
            for s in (b.signals or [])
        ]
    )
    st.subheader("Score breakdown")
    st.dataframe(breakdown, width="stretch", hide_index=True)

    history = snap.history[snap.history.ticker == ticker]
    if not history.empty:
        st.subheader("1y spread history vs Brazil")
        chart = history.set_index("date")[["spread_bps"]].rename(columns={"spread_bps": row.issuer})
        chart["Brazil 5Y CDS"] = snap.manifest["brazil"]["cds_5y_bps"]
        st.line_chart(chart)

    if row.quality_notes:
        st.info(f"Data quality: {row.quality_notes}")


def render_quality_tab(snap: Snapshot):
    manifest = snap.manifest
    st.metric("Snapshot", manifest["as_of"], f'source: {manifest["source"]}' + (" — PARTIAL" if manifest["partial"] else ""))
    st.subheader("Field coverage")
    st.dataframe(
        pd.DataFrame(
            [{"field": k, "coverage": f"{v:.0%}"} for k, v in manifest["coverage"].items()]
        ),
        hide_index=True,
    )
    if manifest["failures"]:
        st.subheader("Fetch failures")
        st.dataframe(
            pd.DataFrame([{"ticker": k, "reason": v} for k, v in manifest["failures"].items()]),
            hide_index=True,
        )


def main():
    chosen = sidebar(list_snapshots(SNAPSHOTS_ROOT))
    if chosen is None:
        st.warning("No snapshot yet. Use 'Refresh from Bloomberg' on the Terminal machine, or set IOS_SOURCE=fixture for synthetic data.")
        return
    snap = load_snapshot(chosen)
    st.sidebar.markdown(f"**Data as of:** {snap.manifest['as_of']}  \n**Source:** {snap.manifest['source']}")
    if snap.manifest["partial"]:
        st.sidebar.warning(f"Partial snapshot — {len(snap.manifest['failures'])} issuer(s) failed.")

    scores = score_snapshot(snap)
    tab_screen, tab_issuer, tab_quality = st.tabs(["Screen", "Issuer detail", "Data quality"])
    with tab_screen:
        render_screen_tab(snap, scores)
    with tab_issuer:
        render_issuer_tab(snap, scores)
    with tab_quality:
        render_quality_tab(snap)


main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_app.py -q`
Expected: all PASS. Common failures: `st.dataframe` `width="stretch"` requires a recent Streamlit — if the installed version predates it, use `use_container_width=True` instead (both in app and keep tests unchanged).

- [ ] **Step 5: Manually smoke-run the app**

Run: `IOS_SOURCE=fixture poetry run streamlit run src/issuer_opportunity_screener/app.py --server.headless true` (then Ctrl-C)
Expected: starts without traceback; open the URL if a browser is handy — Screen tab shows a ranked table after clicking Refresh once (fixture data). Note: with no snapshot under `./data/snapshots` the first paint shows the "No snapshot yet" warning — that is correct behavior, click Refresh.

- [ ] **Step 6: Commit**

```bash
git add src/issuer_opportunity_screener/app.py tests/test_app.py
git commit -m "feat: add three-tab Streamlit dashboard over scored snapshots"
```

---

### Task 10: End-to-end test, README, cleanup

**Files:**
- Create: `tests/test_end_to_end.py`
- Create: `README.md`
- Modify: `docs/week-notes/week_01.typ` (append note)
- Delete: `map.txt`

**Interfaces:**
- Consumes: everything.
- Produces: green full suite; repo ready for the Terminal-machine run.

- [ ] **Step 1: Write the end-to-end test**

Create `tests/test_end_to_end.py`:

```python
"""Fixture -> pipeline -> snapshot -> scoring -> screen frame, on the real universe file."""
from pathlib import Path

from issuer_opportunity_screener.pipeline import run_pipeline
from issuer_opportunity_screener.scoring import score_snapshot, screen_frame
from issuer_opportunity_screener.snapshots import load_snapshot
from issuer_opportunity_screener.sources.fixture import FixtureSource

REPO_UNIVERSE = Path(__file__).resolve().parents[1] / "data" / "universe.csv"


def test_full_flow_on_repo_universe(tmp_path):
    snap_dir = run_pipeline(REPO_UNIVERSE, FixtureSource(), tmp_path / "snapshots")
    snap = load_snapshot(snap_dir)
    scores = score_snapshot(snap)
    frame = screen_frame(snap, scores)

    assert snap.manifest["issuer_count"] >= 80
    assert len(scores) == snap.manifest["fetched_count"]
    assert set(frame.tier) <= {"A", "B", "C"}
    assert frame.composite.between(0, 100).all()
    # every scored issuer has a full 5-block breakdown
    assert all(len(s.blocks) == 5 for s in scores)
    # viability is decided (True/False, never None) for every scored name
    assert frame.viable.isin([True, False]).all()
```

- [ ] **Step 2: Run it**

Run: `poetry run pytest tests/test_end_to_end.py -q`
Expected: PASS.

- [ ] **Step 3: Write README.md**

```markdown
# Issuer Opportunity Screener

Screens a curated issuer universe for names whose credit spread makes an
offshore COE attractive to Brazilian investors, ranks them with a documented
composite score, and serves the result as a Streamlit dashboard.

Spec: `docs/superpowers/specs/2026-07-15-issuer-opportunity-screener-design.md`
Methodology: `docs/methodology/screening_criteria_v1.typ`

## Quickstart

```bash
poetry install
poetry run pytest -q                       # everything runs without a Terminal

# dashboard with synthetic data (any machine):
IOS_SOURCE=fixture poetry run streamlit run src/issuer_opportunity_screener/app.py
# then click "Refresh from Bloomberg" once to create the first (fixture) snapshot

# dashboard with live data (Bloomberg Terminal machine, logged in):
poetry run streamlit run src/issuer_opportunity_screener/app.py
```

## Layout

- `data/universe.csv` — desk-editable universe (issuer, ticker, basket,
  recognition_score, internal_rating).
- `data/snapshots/<timestamp>/` — append-only parquet snapshots + manifest.
- `src/issuer_opportunity_screener/` — universe → sources → pipeline →
  snapshots → scoring → app (strictly one-directional).

## Desk rules encoded

- CDS-first: 5Y CDS preferred, bond z-spread fallback.
- Viability vs Brazil: spread ≥ Brazil, or ≥ Brazil − 20 bps with a rating
  strictly stronger than Brazil.
- Composite score: 35% spread attractiveness, 20% credit quality,
  20% liquidity, 10% equity overlay, 15% recognition. Tiers: A ≥ 70, B ≥ 50.
```

- [ ] **Step 4: Append to `docs/week-notes/week_01.typ`**

Append at the end of the file:

```typst
=== 2026-07-15 v2 Rebuild
- Rebuilt the application as a layered package: universe config, source adapters (Bloomberg plus deterministic fixture), append-only parquet snapshots, composite scoring, and a Streamlit dashboard.
- The v1 CLI structure was retired; see `docs/superpowers/specs/2026-07-15-issuer-opportunity-screener-design.md`.
- `docs/week-notes/bloomberg_data_discovery.typ` was lost during the repository wipe and could not be recovered.
```

- [ ] **Step 5: Delete `map.txt`, run everything, commit**

Run: `rm map.txt && poetry run pytest -q`
Expected: full suite PASS.

```bash
git add -A
git commit -m "feat: add end-to-end test, README, and retire v1 scaffolding notes"
```

- [ ] **Step 6: Terminal-machine verification checklist (manual, not CI)**

Document-only step — perform when on the Bloomberg Terminal machine, and record results in `docs/week-notes/`:

1. `poetry install` (with the bloomberg group if it was made optional in Task 1).
2. `poetry run streamlit run src/issuer_opportunity_screener/app.py`, click **Refresh from Bloomberg**.
3. Check the Data quality tab: coverage for `cds_5y_bps` and `bond_z_spread_bps`, and the failures list.
4. Verify field mnemonics actually resolve (`RTG_MOODY/RTG_SP/RTG_FITCH`, `CHG_PCT_3M`, `CHG_PCT_1YR`, `TOT_BUY_REC/TOT_SELL_REC/TOT_HOLD_REC`, `BOND_CHAIN`, `YAS_ZSPREAD`, `PAYMENT_RANK`, `AMT_OUTSTANDING`) — adjust `REFDATA_FIELDS`/`BOND_FIELDS` in `sources/bloomberg.py` if any come back as `NOT_APPLICABLE_TO_REF_DATA`.
5. Verify the CDS ticker convention (`<TICKER> CDS USD SR 5Y D14 Corp`) resolves for a handful of names; where it doesn't, the issuer will appear in failures — collect the correct handles with the desk.
6. Quarantine tickers whose identity looks wrong (issuer mismatch) by removing them from `data/universe.csv` pending desk confirmation.
```
