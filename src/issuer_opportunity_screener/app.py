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
    if not scores:
        st.warning("No scorable issuers in this snapshot — check the Data quality tab.")
        (tab_quality,) = st.tabs(["Data quality"])
        with tab_quality:
            render_quality_tab(snap)
        return

    tab_screen, tab_issuer, tab_quality = st.tabs(["Screen", "Issuer detail", "Data quality"])
    with tab_screen:
        render_screen_tab(snap, scores)
    with tab_issuer:
        render_issuer_tab(snap, scores)
    with tab_quality:
        render_quality_tab(snap)


main()
