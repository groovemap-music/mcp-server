"""Shared fixtures for the MCP server test suite."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _scrub_otel_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every OTEL_* environment variable so tests never inherit shell/CI config.

    Keeps the "endpoint unset" regression path deterministic regardless of what the
    invoking shell or CI runner happens to export, and keeps tests independent of
    each other's environment mutations.
    """
    for name in list(os.environ):
        if name.startswith("OTEL_"):
            monkeypatch.delenv(name, raising=False)
