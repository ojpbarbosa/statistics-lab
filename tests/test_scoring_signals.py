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
    # missing Brazil benchmark: no verdict, never a crash
    assert viability(200.0, 11, None, 11) == (None, False)


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
