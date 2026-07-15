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


def test_security_matches_ticker():
    from issuer_opportunity_screener.sources.bloomberg import security_matches_ticker

    assert security_matches_ticker("AMD 4.393 06/01/46 Corp", "AMD") is True
    assert security_matches_ticker("AMDX 5 01/01/30 Corp", "AMD") is False
    assert security_matches_ticker("GM Financial 5.4 04/01/48 Corp", "GM") is True
