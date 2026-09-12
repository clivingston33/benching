from __future__ import annotations

import pytest


def selective_analysis_fake(monkeypatch, runner, on_analyze):
    """Double ``subprocess.run`` for run_one tests without poisoning the process.

    ``runner.subprocess`` is the stdlib module, so replacing its ``run``
    outright breaks unrelated stdlib subprocess use during the test — e.g.
    ``platform.platform()`` shells out to ``uname`` on Linux (Windows never
    does, which hid this). Route only the analytics child argv to the fake
    and execute everything else for real.
    """
    import subprocess as stdlib_subprocess

    real_run = stdlib_subprocess.run

    def _fake(*args, **kwargs):
        argv = args[0] if args else kwargs.get("args", [])
        parts = list(argv) if isinstance(argv, (list, tuple)) else [argv]
        if any("benching.analytics.analyze" in str(part) for part in parts):
            return on_analyze(*args, **kwargs)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(runner.subprocess, "run", _fake)


@pytest.fixture(autouse=True)
def isolated_user_config(tmp_path, monkeypatch):
    """Prevent developer-local providers from changing repo-config tests."""
    monkeypatch.setenv("BENCHING_CONFIG_DIR", str(tmp_path / "benching"))
