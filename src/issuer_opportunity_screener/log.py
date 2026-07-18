"""Tiny leveled, colored terminal logger: `{timestamp} [scope] <level> {message}`.

Levels (ascending): trace, step, info/success, warn, error. The threshold
comes from IOS_LOG_LEVEL (default "step"). Colors auto-disable when stderr
is not a TTY or NO_COLOR is set; IOS_FORCE_COLOR overrides.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
GRAY = "\033[90m"

LEVELS = {"trace": 0, "step": 1, "info": 2, "success": 2, "warn": 3, "error": 4}
LEVEL_COLORS = {
    "trace": GRAY,
    "step": MAGENTA,
    "info": BLUE,
    "success": GREEN,
    "warn": YELLOW,
    "error": RED,
}
_TAG_WIDTH = max(len(level) for level in LEVELS) + 2  # "<success>"


def _threshold() -> int:
    return LEVELS.get(os.environ.get("IOS_LOG_LEVEL", "step").lower(), LEVELS["step"])


def _colors_enabled() -> bool:
    if os.environ.get("IOS_FORCE_COLOR"):
        return True
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stderr.isatty()


def format_line(scope: str, level: str, message: str, timestamp: dt.datetime, color: bool) -> str:
    ts = timestamp.strftime("%H:%M:%S")
    tag = f"<{level}>".ljust(_TAG_WIDTH)
    if not color:
        return f"{ts} [{scope}] {tag} {message}"
    return (
        f"{GRAY}{ts}{RESET} "
        f"{CYAN}[{scope}]{RESET} "
        f"{BOLD}{LEVEL_COLORS[level]}{tag}{RESET} "
        f"{message}"
    )


class Logger:
    def __init__(self, scope: str):
        self.scope = scope

    def _log(self, level: str, message: str) -> None:
        if LEVELS[level] < _threshold():
            return
        line = format_line(self.scope, level, message, dt.datetime.now(), _colors_enabled())
        print(line, file=sys.stderr)

    def trace(self, message: str) -> None:
        self._log("trace", message)

    def step(self, message: str) -> None:
        self._log("step", message)

    def info(self, message: str) -> None:
        self._log("info", message)

    def success(self, message: str) -> None:
        self._log("success", message)

    def warn(self, message: str) -> None:
        self._log("warn", message)

    def error(self, message: str) -> None:
        self._log("error", message)


def get_logger(scope: str) -> Logger:
    return Logger(scope)
