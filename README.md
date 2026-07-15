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
