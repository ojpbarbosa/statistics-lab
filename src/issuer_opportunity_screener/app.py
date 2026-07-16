"""Issuer Opportunity Screener: Streamlit dashboard.

Reads the latest snapshot under $IOS_DATA_DIR (default ./data), scores it
in-memory, renders three tabs. Never talks to blpapi directly; the Refresh
button runs the pipeline and falls back gracefully when Bloomberg is away.

Visual language: terminal-dark surface, amber accent, and every spread
anchored against the Brazil benchmark line, the product's one thesis.
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

ISSUER_COLOR = "#2287c7"  # validated for BOTH light and dark surfaces (dataviz six checks)
BRAZIL_COLOR = "#bc8400"
MUTED_COLOR = "#8a919c"  # neutral status for "not viable"; shape/legend carry identity
BRAZIL_TICKER_HINT = "BRAZIL CDS USD SR 5Y D14 Corp"

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
                st.warning(f"Bloomberg unavailable, staying on current snapshot. ({exc})")
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
    brazil = snap.manifest["brazil"]
    scored, universe_size = len(frame), snap.manifest["issuer_count"]
    columns = st.columns(4)
    columns[0].metric("Issuers scored", f"{scored}/{universe_size}")
    columns[1].metric("Tier A", int((frame.tier == "A").sum()))
    columns[2].metric("Viable vs Brazil", int(frame.viable.sum()))
    columns[3].metric(
        "Brazil 5Y CDS",
        f"{brazil['cds_5y_bps']:.0f} bps",
        f"rating {brazil.get('rating_sp', 'n/a')}",
        delta_color="off",
    )
    bond = brazil.get("bond_security")
    z_spread = brazil.get("z_spread_bps")
    if bond:
        z_text = f", z-spread {z_spread:.0f} bps" if z_spread is not None else ""
        columns[3].caption(f"benchmark bond: {bond}{z_text}")


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
    "rating_source": st.column_config.TextColumn("Rating providers"),
    "internal_rating": st.column_config.TextColumn("Internal", width="small"),
    "recognition_score": st.column_config.NumberColumn("Recognition", format="%.0f"),
    "partial_data": st.column_config.CheckboxColumn("Partial"),
    "quality_notes": st.column_config.TextColumn("Notes"),
    "viability_note": st.column_config.TextColumn("Viability", width="large"),
}

EDGE_CASE_COLUMNS = [
    "issuer", "ticker", "basket", "rating_composite", "rating_source",
    "cds_5y_bps", "bond_z_spread_bps", "spread_vs_brazil_bps", "viability_note",
]


def render_market_map(view: pd.DataFrame):
    import altair as alt

    data = view.assign(status=view.viable.map({True: "viable", False: "not viable"}))
    points = (
        alt.Chart(data)
        .mark_point(size=90, filled=True, opacity=0.9)
        .encode(
            x=alt.X("composite:Q", title="composite score", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("spread_vs_brazil_bps:Q", title="spread vs Brazil (bps)"),
            color=alt.Color(
                "status:N",
                scale=alt.Scale(domain=["viable", "not viable"], range=[ISSUER_COLOR, MUTED_COLOR]),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=[
                alt.Tooltip("issuer:N"),
                alt.Tooltip("ticker:N"),
                alt.Tooltip("tier:N"),
                alt.Tooltip("composite:Q", format=".1f"),
                alt.Tooltip("spread_vs_brazil_bps:Q", format="+.0f", title="vs Brazil (bps)"),
            ],
        )
    )
    brazil_line = (
        alt.Chart(pd.DataFrame({"y": [0]}))
        .mark_rule(color=BRAZIL_COLOR, strokeDash=[6, 4], strokeWidth=2)
        .encode(y="y:Q", tooltip=alt.value("Brazil benchmark (0 bps = trades flat to Brazil)"))
    )
    st.altair_chart((points + brazil_line).properties(height=300), width="stretch")


def render_basket_bar(view: pd.DataFrame):
    import altair as alt

    agg = view.groupby("basket", as_index=False).agg(
        median_vs_brazil=("spread_vs_brazil_bps", "median"),
        names=("ticker", "count"),
    )
    bars = (
        alt.Chart(agg)
        .mark_bar(color=ISSUER_COLOR, cornerRadiusEnd=4, size=18)
        .encode(
            y=alt.Y("basket:N", sort="-x", title=None),
            x=alt.X("median_vs_brazil:Q", title="median spread vs Brazil (bps)"),
            tooltip=[
                alt.Tooltip("basket:N"),
                alt.Tooltip("median_vs_brazil:Q", format="+.0f", title="median vs Brazil (bps)"),
                alt.Tooltip("names:Q", title="names"),
            ],
        )
    )
    zero = (
        alt.Chart(pd.DataFrame({"x": [0]}))
        .mark_rule(color=BRAZIL_COLOR, strokeDash=[6, 4], strokeWidth=2)
        .encode(x="x:Q")
    )
    st.altair_chart((bars + zero).properties(height=300), width="stretch")


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

    if not view.empty:
        map_col, basket_col = st.columns((3, 2))
        with map_col:
            st.markdown("##### Market map: score vs spread")
            render_market_map(view)
        with basket_col:
            st.markdown("##### Baskets vs Brazil")
            render_basket_bar(view)

    numeric_columns = [
        "composite", "spread_vs_brazil_bps", "cds_5y_bps",
        "bond_z_spread_bps", "bond_last_price", "recognition_score",
    ]
    display = view.assign(
        rating_composite=view.rating_composite.fillna(""),
        internal_rating=view.internal_rating.fillna(""),
        **{column: pd.to_numeric(view[column], errors="coerce") for column in numeric_columns},
    )
    st.dataframe(display, width="stretch", hide_index=True, column_config=SCREEN_COLUMNS, height=520)
    st.download_button(
        "Export current view (CSV)",
        view.to_csv(index=False).encode("utf-8"),
        file_name=f"screen_{snap.directory.name}.csv",
        mime="text/csv",
    )

    st.subheader("Edge cases vs Brazil")
    st.caption(
        "Names trading through Brazil by at most 20 bps that stay viable because "
        "their rating is strictly stronger than Brazil's."
    )
    edge = frame[frame.viable & (frame.spread_vs_brazil_bps < 0)]
    if edge.empty:
        st.caption("No edge-case names in this snapshot.")
    else:
        st.dataframe(
            edge[EDGE_CASE_COLUMNS],
            width="stretch",
            hide_index=True,
            column_config={key: SCREEN_COLUMNS[key] for key in EDGE_CASE_COLUMNS},
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
            x=alt.X("date:T", axis=alt.Axis(title=None, grid=False)),
            y=alt.Y(
                "spread_bps:Q",
                scale=alt.Scale(zero=False),
                axis=alt.Axis(title="bps", gridOpacity=0.12),
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
    st.caption(f"Viability: {score.viability_note}")

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
    st.markdown(f"**Composite** = `{score.composite_detail}` (weights renormalize over blocks with data; tiers: A at 70, B at 50)")

    st.subheader("Signal detail")
    signals = pd.DataFrame(
        [
            {"block": b.name, "signal": s.name, "raw": s.raw, "score": s.score, "how it is computed": s.detail}
            for b in score.blocks
            for s in (b.signals or [])
        ]
    )
    st.dataframe(
        signals,
        width="stretch",
        hide_index=True,
        height=int(38 * (len(signals) + 1.2)),
        column_config={
            "block": st.column_config.TextColumn("Block"),
            "signal": st.column_config.TextColumn("Signal"),
            "raw": st.column_config.NumberColumn("Raw", format="%.2f"),
            "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
            "how it is computed": st.column_config.TextColumn("How it is computed", width="large"),
        },
    )

    st.subheader("Replicate on the terminal")
    brazil_manifest = snap.manifest["brazil"]
    replication = [f"- Brazil benchmark: `{BRAZIL_TICKER_HINT}`, field `PX_LAST` = {brazil_manifest['cds_5y_bps']:.1f} bps"]
    if brazil_manifest.get("bond_security"):
        brazil_z = brazil_manifest.get("z_spread_bps")
        replication.append(
            f"- Brazil benchmark bond: `{brazil_manifest['bond_security']}`, field `YAS_ZSPREAD`"
            + (f" = {brazil_z:.0f} bps" if brazil_z is not None else "")
        )
    if brazil_manifest.get("ratings"):
        replication.append(f"- Brazil ratings as fetched: `{brazil_manifest['ratings']}`")
    if pd.notna(getattr(row, "cds_security", None)):
        replication.append(f"- 5Y CDS: `{row.cds_security}`, field `PX_LAST` (spread history: weekly `PX_LAST`, 1y back)")
    if pd.notna(row.bond_security):
        replication.append(
            f"- Bond: `{row.bond_security}`, fields `YAS_ZSPREAD` (current z-spread), `PX_LAST` (price), "
            f"`PAYMENT_RANK`, `MATURITY` via DES (spread history: weekly `Z_SPRD_MID`, 1y back)"
        )
    ratings_raw = getattr(row, "ratings_all", None)
    if isinstance(ratings_raw, str) and ratings_raw.strip():
        replication.append(f"- Ratings as fetched (bond, then CDS, then equity): `{ratings_raw}`")
    replication.append("- Viability rule: spread vs Brazil >= 0 bps, or >= -20 bps with a rating strictly stronger than Brazil")
    st.markdown("\n".join(replication))

    if row.quality_notes:
        st.info(f"Data quality: {row.quality_notes}")


def render_quality_tab(snap: Snapshot):
    manifest = snap.manifest
    st.metric(
        "Snapshot",
        manifest["as_of"],
        f'source: {manifest["source"]}' + (" (PARTIAL)" if manifest["partial"] else ""),
        delta_color="inverse" if manifest["partial"] else "off",
    )
    brazil = manifest["brazil"]
    st.caption(
        f"Brazil benchmark: 5Y CDS {brazil['cds_5y_bps']:.0f} bps"
        + (f"; bond {brazil['bond_security']}" if brazil.get("bond_security") else "; no benchmark bond resolved")
        + (f" (z-spread {brazil['z_spread_bps']:.0f} bps)" if brazil.get("z_spread_bps") is not None else "")
        + f"; rating {brazil.get('rating_sp', 'n/a')}"
        + (f" from {', '.join(brazil['ratings'])}" if brazil.get("ratings") else " (fallback, no provider resolved)")
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
        st.sidebar.warning(f"Partial snapshot: {len(snap.manifest['failures'])} issuer(s) failed.")
    st.caption(
        f"data as of {snap.manifest['as_of']} · source: {snap.manifest['source']}"
        + (" · partial snapshot" if snap.manifest["partial"] else "")
    )

    scores = score_snapshot(snap)
    if not scores:
        st.warning("No scorable issuers in this snapshot. Check the Data quality tab.")
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
