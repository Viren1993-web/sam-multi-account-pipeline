"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove AWS and pipeline env vars before every test."""
    keys = [
        "AWS_ACCOUNT_ID",
        "AWS_ACCOUNT_IDS",
        "AWS_REGION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "STACK_NAME",
        "RUNTIME_LANGUAGE",
        "NODE_VERSION",
        "PYTHON_VERSION",
        "WORKING_DIRECTORY",
        "SAM_ADDOPTS",
        "DEBUG",
        "CI",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)
