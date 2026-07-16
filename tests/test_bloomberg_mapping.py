import datetime as dt

from issuer_opportunity_screener.sources.bloomberg import (
    cds_ticker,
    credit_from_fields,
    flatten_field_element,
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


class FakeScalarElement:
    def isArray(self):
        return False

    def getValue(self):
        return 42


class FakeSubElement:
    def __init__(self, value):
        self._value = value

    def getValue(self):
        return self._value


class FakeRow:
    def __init__(self, sub_values):
        self._sub_values = sub_values

    def numElements(self):
        return len(self._sub_values)

    def getElement(self, index):
        return FakeSubElement(self._sub_values[index])

    def __str__(self):
        return "EMPTY_ROW"


class FakeArrayElement:
    def __init__(self, rows):
        self._rows = rows

    def isArray(self):
        return True

    def numValues(self):
        return len(self._rows)

    def getValueAsElement(self, index):
        return self._rows[index]


def test_flatten_field_element_scalar():
    assert flatten_field_element(FakeScalarElement()) == 42


def test_flatten_field_element_array_uses_first_sub_element():
    rows = [FakeRow(["AA123 Corp"]), FakeRow(["BB456 Corp"])]
    assert flatten_field_element(FakeArrayElement(rows)) == ["AA123 Corp", "BB456 Corp"]


def test_flatten_field_element_array_row_with_no_sub_elements_falls_back_to_str():
    rows = [FakeRow([])]
    assert flatten_field_element(FakeArrayElement(rows)) == ["EMPTY_ROW"]


def test_bloomberg_source_reads_host_from_env(monkeypatch):
    from issuer_opportunity_screener.sources.bloomberg import BloombergSource

    monkeypatch.setenv("IOS_BB_HOST", "10.1.2.3")
    monkeypatch.setenv("IOS_BB_PORT", "9999")
    source = BloombergSource()
    assert source.host == "10.1.2.3"
    assert source.port == 9999


def test_bloomberg_source_explicit_args_beat_env(monkeypatch):
    from issuer_opportunity_screener.sources.bloomberg import BloombergSource

    monkeypatch.setenv("IOS_BB_HOST", "10.1.2.3")
    monkeypatch.setenv("IOS_BB_PORT", "9999")
    source = BloombergSource(host="terminal-pc", port=8195)
    assert source.host == "terminal-pc"
    assert source.port == 8195


def test_bloomberg_source_defaults_without_env(monkeypatch):
    from issuer_opportunity_screener.sources.bloomberg import BloombergSource

    monkeypatch.delenv("IOS_BB_HOST", raising=False)
    monkeypatch.delenv("IOS_BB_PORT", raising=False)
    source = BloombergSource()
    assert source.host == "localhost"
    assert source.port == 8194


def test_as_date_normalizes_datetime_and_passes_date_through():
    import datetime as dtmod

    from issuer_opportunity_screener.sources.bloomberg import as_date

    assert as_date(dtmod.datetime(2026, 7, 15, 12, 30)) == dtmod.date(2026, 7, 15)
    assert as_date(dtmod.date(2026, 7, 15)) == dtmod.date(2026, 7, 15)
    assert as_date(None) is None


def test_chain_security_appends_yellow_key_only_when_missing():
    from issuer_opportunity_screener.sources.bloomberg import chain_security

    assert chain_security("BACR 4.375 01/12/26") == "BACR 4.375 01/12/26 Corp"
    assert chain_security("EJ1234567 Corp") == "EJ1234567 Corp"
    assert chain_security("  XS0055498413 ") == "XS0055498413 Corp"
    assert chain_security("BRAZIL 5 01/27/45 Govt") == "BRAZIL 5 01/27/45 Govt"


def test_issuer_securities_derived_defaults():
    from issuer_opportunity_screener.sources.bloomberg import issuer_securities
    from issuer_opportunity_screener.universe import UniverseIssuer

    issuer = UniverseIssuer("Tesla", "TSLA", "Brazil", "US", "Auto", 90.0)
    assert issuer_securities(issuer) == ("TSLA US Equity", "TSLA CDS USD SR 5Y D14 Corp")


def test_issuer_securities_overrides_win():
    from issuer_opportunity_screener.sources.bloomberg import issuer_securities
    from issuer_opportunity_screener.universe import UniverseIssuer

    issuer = UniverseIssuer(
        "AB InBev", "ABIBB", "Brazil", "BE", "Beverages", 85.0,
        equity_ticker="ABI BB Equity", cds_ticker="ABIBB CDS EUR SR 5Y D14 Corp",
    )
    assert issuer_securities(issuer) == ("ABI BB Equity", "ABIBB CDS EUR SR 5Y D14 Corp")


def test_parsekeyable_converts_instrument_result_suffix():
    from issuer_opportunity_screener.sources.bloomberg import parsekeyable

    assert parsekeyable("AMD 4.393 06/01/46<corp>") == "AMD 4.393 06/01/46 Corp"
    assert parsekeyable("GM 5.4 04/01/48<Corp>") == "GM 5.4 04/01/48 Corp"
    assert parsekeyable("PETBRA 6.85 06/05/2115 Corp") == "PETBRA 6.85 06/05/2115 Corp"
    assert parsekeyable(" T 3.5 09/15/53<corp> ") == "T 3.5 09/15/53 Corp"


def test_same_credit_family_uses_bloomberg_ticker_field():
    from issuer_opportunity_screener.sources.bloomberg import same_credit_family

    assert same_credit_family("AMD", "AMD") is True
    assert same_credit_family("amd ", "AMD") is True
    assert same_credit_family("AMDX", "AMD") is False
    assert same_credit_family(None, "AMD") is True  # missing TICKER never disqualifies
    assert same_credit_family("", "AMD") is True


def test_rank_is_senior_unsecured_variants():
    from issuer_opportunity_screener.sources.bloomberg import rank_is_senior_unsecured

    assert rank_is_senior_unsecured("Sr Unsecured") is True
    assert rank_is_senior_unsecured("SENIOR UNSECURED") is True
    assert rank_is_senior_unsecured("Unsecured") is True
    assert rank_is_senior_unsecured("Sr Preferred") is True
    assert rank_is_senior_unsecured("Senior Non-Preferred") is True
    assert rank_is_senior_unsecured("Sr Non Preferred") is True
    assert rank_is_senior_unsecured("Secured") is False
    assert rank_is_senior_unsecured("1st Lien Secured") is False
    assert rank_is_senior_unsecured("Subordinated") is False
    assert rank_is_senior_unsecured("Sr Subordinated") is False
    assert rank_is_senior_unsecured("Jr Subordinated") is False
    assert rank_is_senior_unsecured(None) is False
    assert rank_is_senior_unsecured("") is False


def test_select_bond_accepts_senior_preferred():
    picked = select_bond([bond("SP", 5.0, rank="Sr Preferred")], as_of=AS_OF)
    assert picked["security"] == "SP"


def test_rejection_summary_itemizes_reasons():
    import datetime as dtmod

    from issuer_opportunity_screener.sources.bloomberg import rejection_summary

    candidates = [
        bond("EUR1", 5.0, crncy="EUR"),
        bond("EUR2", 5.0, crncy="EUR"),
        bond("SUB", 5.0, rank="Subordinated"),
        bond("SUB2", 5.0, rank="Sr Subordinated"),
        bond("SHORT", 1.0),
        {"security": "EMPTY", "crncy": None, "payment_rank": None, "maturity": None,
         "amt_outstanding": None, "z_spread_bps": None, "last_price": None, "coupon": None},
        bond("OK", 5.0),
    ]
    summary = rejection_summary(candidates, as_of=AS_OF)
    assert "2 non-USD" in summary
    assert "2 rank mismatch" in summary
    assert "1 tenor outside 3-10y" in summary
    assert "1 empty refdata row" in summary
    assert "1 eligible" in summary
    assert "Subordinated" in summary  # top rejected ranks are named


def test_bond_currencies_from_env(monkeypatch):
    from issuer_opportunity_screener.sources.bloomberg import bond_currencies_from_env

    monkeypatch.delenv("IOS_BOND_CURRENCIES", raising=False)
    assert bond_currencies_from_env() == ("USD",)
    monkeypatch.setenv("IOS_BOND_CURRENCIES", "usd, eur")
    assert bond_currencies_from_env() == ("USD", "EUR")
    monkeypatch.setenv("IOS_BOND_CURRENCIES", " ")
    assert bond_currencies_from_env() == ("USD",)


def test_select_bond_eur_eligible_when_allowed():
    from issuer_opportunity_screener.sources.bloomberg import select_bond as select

    eur_only = [bond("EUR1", 5.0, crncy="EUR")]
    assert select(eur_only, as_of=AS_OF) is None
    picked = select(eur_only, as_of=AS_OF, currencies=("USD", "EUR"))
    assert picked["security"] == "EUR1"


def test_select_bond_prefers_earlier_currency_over_closer_tenor():
    from issuer_opportunity_screener.sources.bloomberg import select_bond as select

    candidates = [bond("USD-far", 8.5, crncy="USD"), bond("EUR-close", 5.0, crncy="EUR")]
    picked = select(candidates, as_of=AS_OF, currencies=("USD", "EUR"))
    assert picked["security"] == "USD-far"


def test_select_bond_custom_tenor_window():
    from issuer_opportunity_screener.sources.bloomberg import select_bond as select

    long_bond = [bond("LONG", 15.0)]
    assert select(long_bond, as_of=AS_OF) is None
    picked = select(long_bond, as_of=AS_OF, tenor_max=20.0)
    assert picked["security"] == "LONG"


def test_rejection_summary_names_allowed_currencies():
    from issuer_opportunity_screener.sources.bloomberg import rejection_summary

    summary = rejection_summary([bond("GBP1", 5.0, crncy="GBP")], as_of=AS_OF, currencies=("USD", "EUR"))
    assert "1 non-USD/EUR" in summary


def test_split_cds_curve_separates_contracts_from_bonds():
    from issuer_opportunity_screener.sources.bloomberg import split_cds_curve

    mixed = [
        "AMD CDS USD SR 5Y D14 Corp",
        "AMD 4.393 06/01/46 Corp",
        "AMD CDS USD SR 1Y6M D14 Corp",
        "AMD 0 09/15/26 Corp",
    ]
    bonds, curve = split_cds_curve(mixed)
    assert bonds == ["AMD 4.393 06/01/46 Corp", "AMD 0 09/15/26 Corp"]
    assert curve == ["AMD CDS USD SR 5Y D14 Corp", "AMD CDS USD SR 1Y6M D14 Corp"]


def test_pick_cds_5y_exact_tenor_only():
    from issuer_opportunity_screener.sources.bloomberg import pick_cds_5y

    curve = [
        "AMD CDS USD SR 1Y6M D14 Corp",
        "AMD CDS USD SR 5Y3M D14 Corp",
        "AMD CDS USD SR 20Y D14 Corp",
        "AMD CDS USD SR 5Y D14 Corp",
    ]
    assert pick_cds_5y(curve, "AMD") == "AMD CDS USD SR 5Y D14 Corp"
    assert pick_cds_5y(curve[:3], "AMD") is None  # interpolated tenors never match
    assert pick_cds_5y(curve, "INTC") is None  # wrong ticker never matches


def test_pick_cds_5y_currency_preference():
    from issuer_opportunity_screener.sources.bloomberg import pick_cds_5y

    curve = ["VW CDS EUR SR 5Y D14 Corp", "VW CDS USD SR 5Y D14 Corp"]
    assert pick_cds_5y(curve, "VW", ("USD", "EUR")) == "VW CDS USD SR 5Y D14 Corp"
    assert pick_cds_5y(["VW CDS EUR SR 5Y D14 Corp"], "VW", ("USD", "EUR")) == "VW CDS EUR SR 5Y D14 Corp"
    assert pick_cds_5y(["VW CDS EUR SR 5Y D14 Corp"], "VW") is None  # USD-only default


def test_merge_ratings_prefers_earlier_securities():
    from issuer_opportunity_screener.sources.bloomberg import merge_ratings

    rows = {
        "BOND Corp": {"RTG_MOODY": "Ba1", "BB_COMPOSITE": "BB+"},
        "CDS Corp": {"RTG_SP": "BB", "RTG_MOODY": "Ba3"},
        "EQ Equity": {"RTG_FITCH": "BB", "RTG_SP": "B+", "RTG_DBRS": "BB (high)"},
    }
    merged = merge_ratings(rows, ["BOND Corp", "CDS Corp", "EQ Equity"])
    assert merged == {
        "moody": "Ba1",  # bond wins over CDS
        "composite": "BB+",
        "sp": "BB",  # CDS wins over equity
        "fitch": "BB",
        "dbrs": "BB (high)",
    }
    assert merge_ratings({}, ["X"]) == {}


def test_select_benchmark_bond_ignores_payment_rank():
    from issuer_opportunity_screener.sources.bloomberg import select_benchmark_bond

    candidates = [
        bond("EUR", 5.0, crncy="EUR"),
        bond("NORANK", 5.2, rank=None),
        bond("FAR", 9.5, rank=None),
    ]
    picked = select_benchmark_bond(candidates, as_of=AS_OF)
    assert picked["security"] == "NORANK"
    assert select_benchmark_bond([bond("SHORT", 1.0)], as_of=AS_OF) is None


def test_select_bond_rejects_foreign_credit_family():
    from issuer_opportunity_screener.sources.bloomberg import select_bond as select

    foreign = dict(bond("EJ12345 Corp", 5.0), ticker_field="XRXFAKE")
    own = dict(bond("EJ99999 Corp", 6.0), ticker_field="AMD")
    unknown = dict(bond("EK55555 Corp", 7.0))  # no TICKER field, kept
    picked = select([foreign, own, unknown], as_of=AS_OF, family_ticker="AMD")
    assert picked["security"] == "EJ99999 Corp"
    assert select([foreign], as_of=AS_OF, family_ticker="AMD") is None
    # without family_ticker the check is off (back-compat)
    assert select([foreign], as_of=AS_OF)["security"] == "EJ12345 Corp"


def test_rejection_summary_counts_foreign_family_and_empty_rows():
    from issuer_opportunity_screener.sources.bloomberg import rejection_summary

    foreign = dict(bond("A Corp", 5.0), ticker_field="OTHER")
    summary = rejection_summary([foreign], as_of=AS_OF, family_ticker="AMD")
    assert "1 different credit family" in summary
    assert "0 refdata rows returned" in rejection_summary([], as_of=AS_OF)
