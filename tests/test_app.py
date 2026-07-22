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


def test_screen_tab_offers_a_flag_filter(data_dir):
    at = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert not at.exception
    flag_filter = next(m for m in at.multiselect if "flags" in m.label.lower())
    # Fixture roles 1 and 3 carry subordinated/long-dated bonds and a split rating.
    # The filter shows the plain-language label, not the code. Importing app.py
    # here would re-execute the Streamlit script, so match on the label text.
    options = " | ".join(flag_filter.options)
    for label in ("Subordinated", "Long tenor", "Split rating"):
        assert label in options


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
