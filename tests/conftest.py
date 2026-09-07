from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_user_config(tmp_path, monkeypatch):
    """Prevent developer-local providers from changing repo-config tests."""
    monkeypatch.setenv("BENCHING_CONFIG_DIR", str(tmp_path / "benching"))
