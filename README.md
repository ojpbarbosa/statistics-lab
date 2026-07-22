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

## Configuration (env vars)

| Variable | Default | Purpose |
|---|---|---|
| `IOS_DATA_DIR` | `data` | Root for `universe.csv` and `snapshots/` |
| `IOS_SOURCE` | (unset → live Bloomberg) | `fixture` for synthetic data; `bquant` ingests a BQuant export directory; `hermes` pulls bonds from the XP treasury Hermes API |
| `IOS_BQUANT_EXPORT` | `data/bquant_export` | Directory holding the files written by `bquant/bquant_export.py` |
| `IOS_HERMES_URL` | `https://hermes-api.xptreasury.com.br` | Hermes base URL |
| `IOS_HERMES_TOKEN` | (required for `hermes`) | Hermes Bearer token |
| `IOS_HERMES_LOOKBACK_DAYS` | `30` | Hermes request window; each payload date becomes a spread history point |
| `IOS_HERMES_BRAZIL_ISIN` | unset | ISIN of the Brazil sovereign USD benchmark bond inside Hermes (required for spreads) |
| `IOS_HERMES_BRAZIL_SPREAD_BPS` | `180` | Anchor spread assigned to Brazil when deriving the G-spread proxy |
| `IOS_BB_HOST` | `localhost` | Bloomberg API host (e.g. a remote Terminal PC or B-PIPE endpoint) |
| `IOS_BB_PORT` | `8194` | Bloomberg API port |
| `IOS_LOG_LEVEL` | `step` | Terminal log verbosity: `trace`, `step`, `info`, `warn`, `error` (`success` logs at `info` rank) |
| `IOS_AUTO_QUARANTINE` | unset | `1` moves unscored names to `data/universe_quarantine.csv` after each live refresh (keep off until data access is unblocked) |
| `IOS_BOND_CURRENCIES` | `USD` | Allowed bond currencies in preference order, e.g. `USD,EUR` (earlier wins when both are eligible; non-USD selections carry an "indicative only" quality note) |
| `IOS_TENOR_MIN_YEARS` / `IOS_TENOR_MAX_YEARS` | `3` / `10` | Bond maturity window for eligibility |

Logs go to stderr as `{timestamp} [scope] <level> {message}` with ANSI colors
(auto-disabled when not a TTY or when `NO_COLOR` is set; `IOS_FORCE_COLOR=1`
overrides). Use `IOS_LOG_LEVEL=trace` to watch every issuer's CDS, bond
selection, and history fetch during a refresh.

## Layout

- `data/universe.csv`: desk-editable universe (issuer, ticker, basket,
  recognition_score, internal_rating), plus optional Bloomberg handle
  overrides per issuer: `equity_ticker` (e.g. `ABI BB Equity` for non-US
  listings) and `cds_ticker` (when the derived
  `{ticker} CDS USD SR 5Y D14 Corp` convention doesn't resolve). Filling
  these is how coverage improves for non-US names.
- `data/snapshots/<timestamp>/`: append-only parquet snapshots + manifest.
- `src/issuer_opportunity_screener/`: universe → sources → pipeline →
  snapshots → scoring → app (strictly one-directional).

The dashboard defines both a terminal-dark and a paper-light theme
(`[theme.dark]` / `[theme.light]`); it follows your OS/browser color scheme
and the ⋮ → Settings toggle. Chart colors are validated for both modes.

## Reports and universe lifecycle

- Snapshot report (screening summary, edge cases, flagged names, movers, data
  quality): download from the Data quality tab or run
  `poetry run python -m issuer_opportunity_screener.reports` (writes to `reports/`).
- Movers tab compares any two snapshots: spread deltas, viability flips,
  tier changes, new and dropped names, plus rule-based callouts. Viability
  flips are attributed between the issuer and the sovereign, since Brazil's own
  CDS moves more than the 20 bps tolerance in a normal week.
- Flags annotate a rank without changing it: `unrated`, `split_rating`,
  `stale_history`, `thin_peers`, `subordinated`, `long_tenor`,
  `sovereign_correlated`, `cheap_for_a_reason`, `benchmark_mismatch`, and
  `benchmark_sensitive`. Filter them out on the Screen tab, read the per-name
  explanation on the Issuer tab. Defined in
  `docs/methodology/screening_criteria_v1.typ`.
- Add names via the sidebar form; quarantine unscored names (with reasons)
  and restore them from the Data quality tab. The final report skeleton
  lives at `docs/report/final_report.typ`.

## Validation

The Validation tab and the snapshot report answer the questions the methodology's
Validation Plan asks: rank stability between snapshots (Spearman, tier changes,
viability flips), weight sensitivity across twelve named scenarios, shortlist
concentration by basket/country/sector (HHI), and co-movement of weekly spread
changes. Code in `validation.py`, all pure functions over snapshots.

Snapshot manifests record the SHA-256 of the universe file that produced them,
so a snapshot stays reconstructible as the universe drifts.

## Live Bloomberg runs

- `IOS_MAX_ISSUERS=3` runs a preflight over the first few names before
  committing to the full universe. Recommended before every long run.
- Requests give up after four silent 30s waits rather than hanging forever, and
  a dropped session is reconnected up to three times before the run stops and
  keeps what it already fetched.
- `IOS_LOG_LEVEL=trace` prints every candidate and field decision.
- `IOS_HEDGE_COST_BPS` sets the cross-currency hedging cost used for the
  BRL-hedged pickup. It is a desk input, not a market observation.

## BQuant route (bypasses the Desktop API gate)

`bql` runs server-side inside Bloomberg's BQuant environment (`BQNT <GO>`)
under different entitlements, so bond screening there is not subject to the
Desktop API workflow-review gate. Flow: upload `bquant/bquant_export.py` and
`data/universe.csv` to a BQNT notebook, run it, download the
`bquant_export/` directory it writes into `data/bquant_export/`, then
Refresh with `IOS_SOURCE=bquant`. The export feeds the exact same snapshot,
scoring, and dashboard pipeline. BQL item names in the exporter are marked
where they may need adjustment to your BQL version.

## Hermes route (XP treasury internal API)

Hermes serves historical BBG bond EoD data at
`GET /v1/BBG/Bonds/{start}/{end}` with a Bearer token, outside the Desktop
API gate. It carries bonds only (no CDS, ratings, or equity yet; a CDS
endpoint is being pursued server-side), keyed by ISIN: fill the optional
`isin` column in `data/universe.csv` with each issuer's representative
senior unsecured USD bond. Spreads are a G-spread proxy: yields solved from
clean EoD mids, anchored on the Brazil benchmark bond
(`IOS_HERMES_BRAZIL_ISIN`) at `IOS_HERMES_BRAZIL_SPREAD_BPS`, which
preserves the spread-vs-Brazil comparison the viability rule needs. Every
payload date prices, so a long `IOS_HERMES_LOOKBACK_DAYS` backfills spread
history. Run with `IOS_SOURCE=hermes`.

## Bloomberg workflow review

Bulk bond requests over the Desktop API can be gated by Bloomberg with
`responseError` category `LIMIT`, subcategory `WORKFLOW_REVIEW_NEEDED`.
That is an entitlement decision on Bloomberg's side, not an app failure:
contact your Bloomberg representative (or `HELP HELP`), cite the `nid`
from the log message, and describe the workflow (internal desk screening,
display only, no redistribution). The app minimizes the gated surface by
requesting static reference fields for candidates and pricing fields for
the single selected bond per issuer only.

## Desk rules encoded

- CDS-first: 5Y CDS preferred, bond z-spread fallback.
- Senior unsecured includes bank senior paper labeled `Sr Preferred` /
  `Sr Non Preferred` on Bloomberg (desk to confirm SNP inclusion).
- Viability vs Brazil: spread ≥ Brazil, or ≥ Brazil − 20 bps with a rating
  strictly stronger than Brazil.
- Composite score: 35% spread attractiveness, 20% credit quality,
  20% liquidity, 10% equity overlay, 15% recognition. Tiers: A ≥ 70, B ≥ 50.
