# Issuer Opportunity Screener v2 — Design

Date: 2026-07-15
Status: Approved (rebuild of the v1 CLI prototype)

## Purpose

A local Streamlit dashboard, backed by the Bloomberg Desktop API (blpapi), that
screens a curated issuer universe for names whose credit spread makes an
offshore COE attractive to Brazilian investors, ranks them with the composite
score documented in `docs/methodology/screening_criteria_v1.typ`, and gives the
sales team an explainable "why this name" story per issuer.

Commercial premise (from desk feedback, 2026-07-13): Brazilian investors have
little appetite for super high-grade names that trade 70–100 bps through
Brazil. The screener favors peculiar, recognizable names with real yield:
`spread >= Brazil`, or `>= Brazil - 20 bps` when the issuer rating is stronger
than Brazil.

## Decisions made during brainstorming

- **Dashboard**: Streamlit (Python-native, same env as blpapi, fast to iterate).
- **Data layer**: Hybrid snapshot-first — pipeline writes versioned local
  snapshots; dashboard reads snapshots and offers a "Refresh from Bloomberg"
  button that works only where a Terminal is logged in.
- **Intelligence layer**: rule-based composite scoring only for v1 (no LLM).
  Explainability comes from per-issuer score breakdowns.
- **Users**: single user, run locally; exports shared with the desk.
- **Structure**: layered package (chosen over dashboard-first monolith and
  CLI-first designs). The v1 code structure is abandoned, not refactored.

## Architecture

Four layers, strictly one-directional data flow:

```
universe.csv ──▶ pipeline ──▶ snapshots (parquet) ──▶ scoring ──▶ app (Streamlit)
                    │
             sources/ (adapters)
             ├─ bloomberg.py  (live blpapi; only works on Terminal machine)
             └─ fixture.py    (deterministic synthetic data; dev/tests)
```

```
src/issuer_opportunity_screener/
├── universe.py      # load/validate data/universe.csv
├── sources/
│   ├── base.py      # CreditDataSource protocol + shared dataclasses
│   ├── bloomberg.py # live blpapi adapter
│   └── fixture.py   # synthetic source for dev/tests
├── pipeline.py      # universe → fetch → snapshot dir + manifest
├── snapshots.py     # versioned parquet store; latest(), list(), load()
├── scoring.py       # composite score, tiers, viability flag, breakdowns
└── app.py           # Streamlit dashboard

data/
├── universe.csv     # issuer, ticker, basket, country, sector, recognition_score, internal_rating
└── snapshots/<ISO-timestamp>/
    ├── snapshot.parquet   # one row per issuer, all fetched fields
    ├── history.parquet    # 1y spread history, long format
    └── manifest.json      # coverage stats, failures, source, timing
```

The dashboard never calls blpapi directly. It loads the latest snapshot,
scores in-memory, renders. Snapshots are append-only (new timestamped
directory per pull, never overwritten).

## Universe as data, not code

`data/universe.csv` is the single input the desk can edit without touching
code. Columns:

| column | source | notes |
|---|---|---|
| issuer | manual | display name |
| ticker | manual | Bloomberg issuer ticker |
| basket | manual | per universe_governance baskets |
| country, sector | manual | |
| recognition_score | manual | 0–100 household-name rubric (desk-owned) |
| internal_rating | manual, optional | XP internal rating; not available via blpapi |

Seeded from `docs/universe/candidate_names.typ`. Validation on load: unique
tickers, recognition_score in range, known basket names; hard error with a
clear message on violation.

## Fields pulled per issuer (CreditDataSource protocol)

- 5Y CDS spread (preferred instrument per desk feedback) + a liquidity proxy
  (quote availability/recency).
- Representative senior unsecured USD bond in the 3–10y window: Z-spread,
  last price, maturity, coupon. Selection rule: among the issuer's senior
  unsecured USD bonds maturing in 3–10y, pick the one closest to 5y maturity
  with a usable liquidity proxy (amount outstanding as tiebreaker).
- External ratings: Moody's / S&P / Fitch, composited to a bucket.
- 1y spread history (CDS preferred, bond z-spread fallback) for percentile,
  1y moving average, and 75th-percentile features.
- Brazil sovereign benchmark (5Y CDS + z-spread reference) fetched in the same
  run so every comparison is same-day.
- Equity overlay when a listed ticker exists: 3m and 12m price change,
  analyst recommendation balance. Skipped silently when unlisted.

The protocol returns typed dataclasses with `None` for anything unavailable,
plus a per-field provenance/quality note. Interpolated CDS tenors (e.g. 5Y3M)
are excluded, as learned in v1.

## Scoring

Direct implementation of `screening_criteria_v1.typ`:

- Five blocks weighted 35/20/20/10/15 → composite 0–100 → Tier A/B/C.
- Pre-score commercial viability flag: `spread_vs_brazil_bps` and boolean
  `viable` using the desk rule (>= Brazil, or >= Brazil − 20 bps with stronger
  rating). Non-viable names stay visible but flagged, never silently dropped.
- Missing blocks (e.g. no equity overlay): weights re-normalize over available
  blocks; issuer flagged `partial_data`.
- Every issuer gets a breakdown table: block → sub-signal → raw value →
  contribution. Nothing is a black box.

## Dashboard (app.py)

Three tabs plus a sidebar:

1. **Screen** — ranked table: issuer, basket, tier badge, composite score,
   CDS/z-spread, spread-vs-Brazil bps, viability flag, ratings, last price.
   Filters: basket, tier, viability, min spread. CSV export of current view.
2. **Issuer detail** — score breakdown, 1y spread history chart with Brazil
   overlay, bond details, equity overlay, data-quality notes for that name.
3. **Data quality** — coverage per field, failed fetches from the manifest,
   snapshot age and source (live vs fixture).

Sidebar: snapshot selector (default latest), "Refresh from Bloomberg" button,
banner showing "data as of <timestamp>".

## Error handling

- Missing fields → nulls + quality flags; never crash a run.
- blpapi unreachable → `BloombergUnavailable` raised by the adapter; the app
  catches it, shows a clear message, stays on the current snapshot.
- Partial pulls → manifest records per-issuer failures; the run is saved and
  labeled partial, never presented as complete (v1 lesson retained).
- Universe file invalid → fail fast with the offending rows named.

## Testing

- `sources/fixture.py` generates a deterministic synthetic universe covering
  edge cases: missing CDS, unlisted equity, distressed name, partial history.
- Unit tests for every scoring sub-signal against hand-computed values.
- One end-to-end test: fixture → pipeline → snapshot → scoring → screen frame.
- Only `sources/bloomberg.py` is untestable off the Terminal machine; it stays
  thin (field mapping + session handling only).

## Cleanup / migration notes

- v1 `src/` layout is not restored; this design supersedes it.
- `pyproject.toml` gains `streamlit`, `pyarrow`, `pytest`; keeps `blpapi`
  supplemental source.
- `map.txt` deleted once the rebuild lands.
- `docs/week-notes/bloomberg_data_discovery.typ` was lost in the wipe and is
  unrecoverable; noted in `week_01.typ`.

## Out of scope for v1

- LLM-generated sales narratives or chat.
- Hosted/multi-user deployment and scheduled refreshes.
- Bond-level multi-instrument screening per issuer (one representative bond
  per issuer in v1; the protocol leaves room to return several later).
- Media-heat signal (recognition_score column stands in for it).
