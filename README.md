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
| `IOS_SOURCE` | (unset → live Bloomberg) | `fixture` switches Refresh to synthetic data |
| `IOS_BB_HOST` | `localhost` | Bloomberg API host (e.g. a remote Terminal PC or B-PIPE endpoint) |
| `IOS_BB_PORT` | `8194` | Bloomberg API port |
| `IOS_LOG_LEVEL` | `step` | Terminal log verbosity: `trace`, `step`, `info`, `warn`, `error` (`success` logs at `info` rank) |
| `IOS_BOND_CURRENCIES` | `USD` | Allowed bond currencies in preference order, e.g. `USD,EUR` (earlier wins when both are eligible; non-USD selections carry an "indicative only" quality note) |
| `IOS_TENOR_MIN_YEARS` / `IOS_TENOR_MAX_YEARS` | `3` / `10` | Bond maturity window for eligibility |

Logs go to stderr as `{timestamp} [scope] <level> {message}` with ANSI colors
(auto-disabled when not a TTY or when `NO_COLOR` is set; `IOS_FORCE_COLOR=1`
overrides). Use `IOS_LOG_LEVEL=trace` to watch every issuer's CDS, bond
selection, and history fetch during a refresh.

## Layout

- `data/universe.csv` — desk-editable universe (issuer, ticker, basket,
  recognition_score, internal_rating), plus optional Bloomberg handle
  overrides per issuer: `equity_ticker` (e.g. `ABI BB Equity` for non-US
  listings) and `cds_ticker` (when the derived
  `{ticker} CDS USD SR 5Y D14 Corp` convention doesn't resolve). Filling
  these is how coverage improves for non-US names.
- `data/snapshots/<timestamp>/` — append-only parquet snapshots + manifest.
- `src/issuer_opportunity_screener/` — universe → sources → pipeline →
  snapshots → scoring → app (strictly one-directional).

The dashboard defines both a terminal-dark and a paper-light theme
(`[theme.dark]` / `[theme.light]`); it follows your OS/browser color scheme
and the ⋮ → Settings toggle. Chart colors are validated for both modes.

## Desk rules encoded

- CDS-first: 5Y CDS preferred, bond z-spread fallback.
- Senior unsecured includes bank senior paper labeled `Sr Preferred` /
  `Sr Non Preferred` on Bloomberg (desk to confirm SNP inclusion).
- Viability vs Brazil: spread ≥ Brazil, or ≥ Brazil − 20 bps with a rating
  strictly stronger than Brazil.
- Composite score: 35% spread attractiveness, 20% credit quality,
  20% liquidity, 10% equity overlay, 15% recognition. Tiers: A ≥ 70, B ≥ 50.
