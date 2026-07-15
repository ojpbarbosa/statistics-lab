import datetime as dt

from issuer_opportunity_screener.log import (
    BLUE,
    BOLD,
    CYAN,
    GRAY,
    GREEN,
    RED,
    RESET,
    YELLOW,
    format_line,
    get_logger,
)

TS = dt.datetime(2026, 7, 15, 14, 30, 5)


def test_plain_format():
    line = format_line("pipeline", "info", "hello", TS, color=False)
    assert line == "14:30:05 [pipeline] <info>    hello"


def test_colored_format_uses_ansi():
    line = format_line("bloomberg", "error", "boom", TS, color=True)
    assert RED in line and BOLD in line and RESET in line
    assert GRAY in line  # timestamp
    assert CYAN in line  # scope
    assert "[bloomberg]" in line and "<error>" in line and "boom" in line


def test_level_colors_distinct():
    success = format_line("x", "success", "ok", TS, color=True)
    warn = format_line("x", "warn", "eh", TS, color=True)
    info = format_line("x", "info", "fyi", TS, color=True)
    assert GREEN in success
    assert YELLOW in warn
    assert BLUE in info


def test_threshold_filters_below_level(monkeypatch, capsys):
    monkeypatch.setenv("IOS_LOG_LEVEL", "warn")
    log = get_logger("test")
    log.trace("t")
    log.step("s")
    log.info("i")
    log.success("ok")
    log.warn("w")
    log.error("e")
    err = capsys.readouterr().err
    assert "w" in err and "e" in err
    assert "<trace>" not in err and "<step>" not in err
    assert "<info>" not in err and "<success>" not in err


def test_default_threshold_is_step(monkeypatch, capsys):
    monkeypatch.delenv("IOS_LOG_LEVEL", raising=False)
    log = get_logger("test")
    log.trace("hidden")
    log.step("visible")
    err = capsys.readouterr().err
    assert "<step>" in err
    assert "<trace>" not in err
