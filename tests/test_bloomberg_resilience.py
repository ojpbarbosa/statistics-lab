"""Failure modes of a long live run: silence, dropped sessions, bad field types.

The blpapi boundary is faked here (a real Terminal is not available in CI or on
a dev machine), but the loop and recovery logic under test is the same code the
live run executes.
"""
import sys
import types

import pytest

from issuer_opportunity_screener.sources.base import BloombergUnavailable

TIMEOUT = 1
RESPONSE = 2
PARTIAL_RESPONSE = 3


class FakeEvent:
    def __init__(self, event_type, messages=()):
        self._type = event_type
        self._messages = list(messages)

    def eventType(self):
        return self._type

    def __iter__(self):
        return iter(self._messages)


class FakeSession:
    """Replays a scripted list of events, then goes silent forever."""

    def __init__(self, events):
        self._events = list(events)
        self.waits = 0

    def nextEvent(self, timeout_ms):
        self.waits += 1
        if self._events:
            return self._events.pop(0)
        return FakeEvent(TIMEOUT)


@pytest.fixture(autouse=True)
def fake_blpapi(monkeypatch):
    module = types.ModuleType("blpapi")
    module.Event = types.SimpleNamespace(
        TIMEOUT=TIMEOUT, RESPONSE=RESPONSE, PARTIAL_RESPONSE=PARTIAL_RESPONSE
    )
    monkeypatch.setitem(sys.modules, "blpapi", module)
    return module


def make_source():
    from issuer_opportunity_screener.sources.bloomberg import BloombergSource

    return BloombergSource()


def test_a_silent_terminal_raises_instead_of_looping_forever():
    """A request that never gets a RESPONSE used to spin nextEvent() forever,
    which would hang a 125-name run with no output and no way to tell why."""
    from issuer_opportunity_screener.sources.bloomberg import MAX_SILENT_WAITS

    session = FakeSession([])  # never answers
    with pytest.raises(BloombergUnavailable, match="no response"):
        list(make_source()._drain(session))
    assert session.waits == MAX_SILENT_WAITS


def test_drain_yields_messages_until_the_response_event():
    session = FakeSession([
        FakeEvent(PARTIAL_RESPONSE, ["first"]),
        FakeEvent(RESPONSE, ["second"]),
        FakeEvent(RESPONSE, ["never reached"]),
    ])
    assert list(make_source()._drain(session)) == ["first", "second"]


def test_an_intermittent_timeout_does_not_abort_the_request():
    session = FakeSession([
        FakeEvent(TIMEOUT),
        FakeEvent(PARTIAL_RESPONSE, ["a"]),
        FakeEvent(TIMEOUT),
        FakeEvent(RESPONSE, ["b"]),
    ])
    assert list(make_source()._drain(session)) == ["a", "b"]


# --- Preflight limit -----------------------------------------------------------

def test_issuer_limit_env_var_trims_the_run(monkeypatch):
    """Lets the desk smoke-test 3 names before committing to the full universe."""
    from issuer_opportunity_screener.sources.bloomberg import issuers_to_fetch

    issuers = [f"name{i}" for i in range(10)]
    monkeypatch.delenv("IOS_MAX_ISSUERS", raising=False)
    assert issuers_to_fetch(issuers) == issuers
    monkeypatch.setenv("IOS_MAX_ISSUERS", "3")
    assert issuers_to_fetch(issuers) == issuers[:3]
    monkeypatch.setenv("IOS_MAX_ISSUERS", "not a number")
    assert issuers_to_fetch(issuers) == issuers


# --- A session that dies mid-run ------------------------------------------------

def test_a_dropped_session_is_reconnected_instead_of_failing_every_remaining_name(monkeypatch):
    """Without this, a network blip at issuer 50 of 125 fails the other 75 with
    the same error and the whole run has to be repeated."""
    from issuer_opportunity_screener.sources.base import UniverseIssuer
    from issuer_opportunity_screener.sources.bloomberg import BloombergSource

    source = BloombergSource()
    sessions = [FakeSession([]), FakeSession([])]
    connects = []

    def fake_connect():
        connects.append(len(connects))
        return sessions[min(len(connects) - 1, len(sessions) - 1)]

    monkeypatch.setattr(source, "_connect", fake_connect)
    # Brazil and every issuer request dies as if the session dropped.
    monkeypatch.setattr(
        source, "_reference_fields",
        lambda *a, **k: (_ for _ in ()).throw(BloombergUnavailable("session terminated")),
    )
    monkeypatch.setattr(source, "_spread_history", lambda *a, **k: [])

    issuers = [
        UniverseIssuer(issuer=f"Co {i}", ticker=f"TICK{i}", basket="Brazil",
                       country="Brazil", sector="Energy", recognition_score=50.0)
        for i in range(3)
    ]
    result = source.fetch(issuers)

    # Every name failed, but the source tried to reconnect rather than giving up.
    assert len(result.failures) >= 3
    assert len(connects) > 1


# --- Field values that are not the type the mapping assumes --------------------

def test_payment_rank_that_is_not_text_does_not_poison_the_snapshot():
    """PAYMENT_RANK comes back as whatever blpapi decoded; a non-string value
    written straight into the frame breaks the parquet write for every issuer."""
    from issuer_opportunity_screener.sources.bloomberg import credit_from_fields

    credit = credit_from_fields("ACME", {}, {"security": "ACME 5 2031 Corp", "payment_rank": 7})
    assert credit.bond.payment_rank == "7"


def test_selected_bond_carries_size_and_currency_for_the_execution_screen():
    from issuer_opportunity_screener.sources.bloomberg import credit_from_fields

    credit = credit_from_fields("ACME", {}, {
        "security": "ACME 5 2031 Corp", "crncy": "EUR", "amt_outstanding": 750_000_000.0,
    })
    assert credit.bond.currency == "EUR"
    assert credit.bond.amount_outstanding == 750_000_000.0
