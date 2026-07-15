"""Issuer Opportunity Screener — Streamlit dashboard.

Reads the latest snapshot under $IOS_DATA_DIR (default ./data), scores it
in-memory, renders three tabs. Never talks to blpapi directly; the Refresh
button runs the pipeline and falls back gracefully when Bloomberg is away.

Visual language: terminal-dark surface, amber accent, and every spread
anchored against the Brazil benchmark line — the product's one thesis.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    import issuer_opportunity_screener  # noqa: F401
except ModuleNotFoundError:
    # `streamlit run src/issuer_opportunity_screener/app.py` without the package
    # installed (fresh clone, non-poetry env): make the app self-locating.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from issuer_opportunity_screener.pipeline import run_pipeline
from issuer_opportunity_screener.scoring import IssuerScore, score_snapshot, screen_frame
from issuer_opportunity_screener.snapshots import Snapshot, list_snapshots, load_snapshot
from issuer_opportunity_screener.sources.base import BloombergUnavailable
from issuer_opportunity_screener.universe import UniverseError

DATA_ROOT = Path(os.environ.get("IOS_DATA_DIR", "data"))
UNIVERSE_PATH = DATA_ROOT / "universe.csv"
SNAPSHOTS_ROOT = DATA_ROOT / "snapshots"

ISSUER_COLOR = "#2287c7"  # validated vs dark surface (dataviz six checks)
BRAZIL_COLOR = "#bc8400"

st.set_page_config(page_title="Issuer Opportunity Screener", layout="wide")
st.markdown(
    """
    <style>
    [data-testid="stMetricValue"], [data-testid="stDataFrame"] {
        font-variant-numeric: tabular-nums;
    }
    [data-testid="stMetricLabel"] p {
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-size: 0.72rem;
        opacity: 0.75;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def make_source():
    if os.environ.get("IOS_SOURCE") == "fixture":
        from issuer_opportunity_screener.sources.fixture import FixtureSource

        return FixtureSource()
    from issuer_opportunity_screener.sources.bloomberg import BloombergSource

    return BloombergSource()


def sidebar(snapshot_dirs: list[Path]) -> Path | None:
    with st.sidebar:
        st.header("Data")
        if st.button("Refresh from Bloomberg", type="primary", width="stretch"):
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


def render_kpis(snap: Snapshot, frame: pd.DataFrame):
    brazil = snap.manifest["brazil"]["cds_5y_bps"]
    scored, universe_size = len(frame), snap.manifest["issuer_count"]
    columns = st.columns(4)
    columns[0].metric("Issuers scored", f"{scored}/{universe_size}")
    columns[1].metric("Tier A", int((frame.tier == "A").sum()))
    columns[2].metric("Viable vs Brazil", int(frame.viable.sum()))
    columns[3].metric("Brazil 5Y CDS", f"{brazil:.0f} bps")


SCREEN_COLUMNS = {
    "issuer": st.column_config.TextColumn("Issuer"),
    "ticker": st.column_config.TextColumn("Ticker"),
    "basket": st.column_config.TextColumn("Basket"),
    "tier": st.column_config.TextColumn("Tier", width="small"),
    "composite": st.column_config.ProgressColumn("Composite", min_value=0, max_value=100, format="%.1f"),
    "viable": st.column_config.CheckboxColumn("Viable"),
    "spread_vs_brazil_bps": st.column_config.NumberColumn("vs Brazil", format="%+.0f bps"),
    "cds_5y_bps": st.column_config.NumberColumn("5Y CDS", format="%.0f bps"),
    "bond_z_spread_bps": st.column_config.NumberColumn("Z-spread", format="%.0f bps"),
    "bond_last_price": st.column_config.NumberColumn("Last px", format="%.2f"),
    "rating_composite": st.column_config.TextColumn("Rating", width="small"),
    "internal_rating": st.column_config.TextColumn("Internal", width="small"),
    "recognition_score": st.column_config.NumberColumn("Recognition", format="%.0f"),
    "partial_data": st.column_config.CheckboxColumn("Partial"),
    "quality_notes": st.column_config.TextColumn("Notes"),
}


def render_screen_tab(snap: Snapshot, frame: pd.DataFrame):
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

    display = view.assign(
        rating_composite=view.rating_composite.fillna(""),
        internal_rating=view.internal_rating.fillna(""),
    )
    st.dataframe(display, width="stretch", hide_index=True, column_config=SCREEN_COLUMNS, height=520)
    st.download_button(
        "Export current view (CSV)",
        view.to_csv(index=False).encode("utf-8"),
        file_name=f"screen_{snap.directory.name}.csv",
        mime="text/csv",
    )


def render_history_chart(snap: Snapshot, ticker: str, issuer_name: str):
    history = snap.history[snap.history.ticker == ticker]
    if history.empty:
        st.caption("No spread history for this name.")
        return
    import altair as alt

    brazil = snap.manifest["brazil"]["cds_5y_bps"]
    frame = history.assign(date=pd.to_datetime(history.date))
    line = (
        alt.Chart(frame)
        .mark_line(color=ISSUER_COLOR, strokeWidth=2, point=alt.OverlayMarkDef(size=22, color=ISSUER_COLOR, opacity=0))
        .encode(
            x=alt.X("date:T", axis=alt.Axis(title=None, grid=False, labelColor="#9aa4ae")),
            y=alt.Y(
                "spread_bps:Q",
                scale=alt.Scale(zero=False),
                axis=alt.Axis(title="bps", gridOpacity=0.12, labelColor="#9aa4ae"),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="date"),
                alt.Tooltip("spread_bps:Q", format=".1f", title="spread (bps)"),
            ],
        )
    )
    rule = (
        alt.Chart(pd.DataFrame({"brazil": [brazil]}))
        .mark_rule(color=BRAZIL_COLOR, strokeDash=[6, 4], strokeWidth=2)
        .encode(y="brazil:Q", tooltip=alt.value(f"Brazil 5Y CDS: {brazil:.1f} bps"))
    )
    st.altair_chart((line + rule).properties(height=280), width="stretch")
    st.markdown(
        f'<small><span style="color:{ISSUER_COLOR}">▬</span> {issuer_name} '
        f'&nbsp;&nbsp;<span style="color:{BRAZIL_COLOR}">╌╌</span> Brazil 5Y CDS ({brazil:.0f} bps)</small>',
        unsafe_allow_html=True,
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

    st.subheader("1y spread history vs Brazil")
    render_history_chart(snap, ticker, row.issuer)

    st.subheader("Score breakdown")
    blocks = pd.DataFrame(
        [
            {"block": b.name, "weight": b.weight, "score": b.score if b.score is not None else None}
            for b in score.blocks
        ]
    )
    st.dataframe(
        blocks,
        width="stretch",
        hide_index=True,
        column_config={
            "block": st.column_config.TextColumn("Block"),
            "weight": st.column_config.NumberColumn("Weight", format="percent"),
            "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
        },
    )
    with st.expander("Signal detail"):
        signals = pd.DataFrame(
            [
                {"block": b.name, "signal": s.name, "raw": s.raw, "score": s.score}
                for b in score.blocks
                for s in (b.signals or [])
            ]
        )
        st.dataframe(signals, width="stretch", hide_index=True)

    if row.quality_notes:
        st.info(f"Data quality: {row.quality_notes}")


def render_quality_tab(snap: Snapshot):
    manifest = snap.manifest
    st.metric(
        "Snapshot",
        manifest["as_of"],
        f'source: {manifest["source"]}' + (" — PARTIAL" if manifest["partial"] else ""),
        delta_color="inverse" if manifest["partial"] else "off",
    )
    st.subheader("Field coverage")
    coverage = pd.DataFrame(
        [{"field": key, "coverage": value} for key, value in manifest["coverage"].items()]
    )
    st.dataframe(
        coverage,
        hide_index=True,
        column_config={
            "field": st.column_config.TextColumn("Field"),
            "coverage": st.column_config.ProgressColumn("Coverage", min_value=0, max_value=1, format="percent"),
        },
    )
    if manifest["failures"]:
        st.subheader("Fetch failures")
        st.dataframe(
            pd.DataFrame([{"ticker": k, "reason": v} for k, v in manifest["failures"].items()]),
            hide_index=True,
            width="stretch",
        )


def main():
    chosen = sidebar(list_snapshots(SNAPSHOTS_ROOT))
    st.title("Issuer Opportunity Screener")
    if chosen is None:
        st.warning("No snapshot yet. Use 'Refresh from Bloomberg' on the Terminal machine, or set IOS_SOURCE=fixture for synthetic data.")
        return
    snap = load_snapshot(chosen)
    st.sidebar.markdown(f"**Data as of:** {snap.manifest['as_of']}  \n**Source:** {snap.manifest['source']}")
    if snap.manifest["partial"]:
        st.sidebar.warning(f"Partial snapshot — {len(snap.manifest['failures'])} issuer(s) failed.")
    st.caption(
        f"data as of {snap.manifest['as_of']} · source: {snap.manifest['source']}"
        + (" · partial snapshot" if snap.manifest["partial"] else "")
    )

    scores = score_snapshot(snap)
    if not scores:
        st.warning("No scorable issuers in this snapshot — check the Data quality tab.")
        render_quality_tab(snap)
        return
    frame = screen_frame(snap, scores)
    render_kpis(snap, frame)

    tab_screen, tab_issuer, tab_quality = st.tabs(["Screen", "Issuer detail", "Data quality"])
    with tab_screen:
        render_screen_tab(snap, frame)
    with tab_issuer:
        render_issuer_tab(snap, scores)
    with tab_quality:
        render_quality_tab(snap)


main()
