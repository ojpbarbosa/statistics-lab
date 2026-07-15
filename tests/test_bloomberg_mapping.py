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
