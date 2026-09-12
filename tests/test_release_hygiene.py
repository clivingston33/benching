"""M4-task-13 tests: release hygiene for a public repository.

Repository fixture/public-example gate: committed public data must carry
no key material, home-directory paths, or private-artifact fields, and
packaging/ignore boundaries must keep runtime secrets out of artifacts.
This is a targeted gate, not a DLP engine: it scans the small committed
public corpus and the built distributions, never user runtime directories.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

PUBLIC_JSON_DIRS = (
    REPO / "examples" / "artifacts",
    REPO / "dashboard" / "data",
    REPO / "dashboard" / "tests" / "fixtures",
    REPO / "tests" / "fixtures",
)

#: JSON keys that must never appear in committed public data.
DENIED_KEY_PARTS = (
    "api_key", "apikey", "proxy_auth", "auth_token", "authorization",
    "private_secret", "secret", "password", "passwd",
)

#: Value patterns: bearer-style keys, private key blocks, home paths.
DENIED_VALUE_RES = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"fw_[A-Za-z0-9_-]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{8,}"),
    re.compile(r"xox[bpas]-[A-Za-z0-9-]+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"/home/[a-z_][a-z0-9_-]*"),
    re.compile(r"/Users/[A-Za-z][A-Za-z0-9_.-]*"),
    re.compile(r"[A-Za-z]:\\Users\\"),
)


def _public_json_files() -> list[Path]:
    files: list[Path] = []
    for directory in PUBLIC_JSON_DIRS:
        files.extend(sorted(directory.glob("*.json")))
    assert files, "public corpus must exist for the hygiene gate to mean anything"
    return files


def _walk_keys(value: object):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def test_license_present_and_advertised() -> None:
    """A: root LICENSE exists and both manifests agree on MIT."""
    text = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in text
    assert "Permission is hereby granted" in text
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["license"] == {"text": "MIT"}, project.get("license")
    manifest = json.loads((REPO / "dashboard" / "package.json").read_text(encoding="utf-8"))
    assert manifest["license"] == "MIT"
    assert manifest["private"] is True, "dashboard stays non-publishable"
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "LICENSE" in readme


def test_public_examples_have_no_private_fields() -> None:
    """D (fields): no credential-bearing keys in committed public data."""
    offenders: list[str] = []
    for path in _public_json_files():
        document = json.loads(path.read_text(encoding="utf-8"))
        for key in _walk_keys(document):
            lowered = str(key).lower()
            if any(part in lowered for part in DENIED_KEY_PARTS):
                offenders.append(f"{path.name}: {key}")
    assert offenders == []


def test_public_examples_have_no_secrets_or_local_paths() -> None:
    """D (values): no key material or machine-local paths in public data."""
    offenders: list[str] = []
    for path in _public_json_files():
        text = path.read_text(encoding="utf-8")
        for pattern in DENIED_VALUE_RES:
            if pattern.search(text):
                offenders.append(f"{path.name}: {pattern.pattern}")
    assert offenders == []


def test_gitignore_covers_secrets_keeps_templates() -> None:
    """F: secret-adjacent files ignored; example templates trackable."""
    def ignored(rel: str) -> bool:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", rel], cwd=str(REPO),
            capture_output=True, timeout=30,
        )
        return completed.returncode == 0

    for rel in (".env", ".env.local", ".env.production", "runs/x.json", "a.secret", "k.pem"):
        assert ignored(rel), rel
    template = "src/benching/benchmark/resources/provider.env.example"
    assert not ignored(template), template
    tracked = subprocess.run(
        ["git", "ls-files", template], cwd=str(REPO),
        capture_output=True, text=True, timeout=30,
    )
    assert template in tracked.stdout

    dashboard = REPO / "dashboard" / ".gitignore"
    ignore_text = dashboard.read_text(encoding="utf-8")
    for rel in (".env", ".env.local", ".env.production"):
        assert ignored(f"dashboard/{rel}"), rel
    assert ".env.production" in ignore_text


@pytest.fixture(scope="module")
def distributions(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("m4-dist")
    completed = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--sdist", "--outdir", str(target)],
        cwd=str(REPO), capture_output=True, text=True, timeout=600,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    return target


def test_wheel_contains_no_private_or_runtime_files(distributions: Path) -> None:
    """G: wheel ships code/resources only — no secrets, runs, or dashboard."""
    wheels = sorted(distributions.glob("benching-*.whl"))
    assert len(wheels) == 1
    names = set(zipfile.ZipFile(wheels[0]).namelist())
    assert any(n.endswith("resources/benchmark.yaml") for n in names)
    assert any(n.endswith("schemas/summary-v1.schema.json") for n in names)
    offenders = [
        name for name in names
        if re.search(r"runs/|\.env($|/)|credential|secret|proxy-auth|raw\.jsonl|metrics\.jsonl|\.git/|dashboard/", name)
    ]
    assert offenders == []


def test_sdist_contains_no_runtime_output(distributions: Path) -> None:
    """H: sdist has no credentials, runs, telemetry, or VCS metadata."""
    sdists = sorted(distributions.glob("benching-*.tar.gz"))
    assert len(sdists) == 1
    import tarfile

    with tarfile.open(sdists[0], "r:gz") as archive:
        names = archive.getnames()
    offenders = [
        name for name in names
        if re.search(r"/runs/|\.env($|/)|credential|secret|proxy-auth|raw\.jsonl|metrics\.jsonl|\.git/|egg-info.*\.pyc|__pycache__", name)
    ]
    assert offenders == []
    assert any(name.endswith("LICENSE") for name in names), "license must ship in sdist"
    assert any(name.endswith("pyproject.toml") for name in names)


def test_dashboard_source_never_imports_test_fixtures() -> None:
    """I (static): production dashboard code cannot bundle test secrets."""
    roots = [REPO / "dashboard" / "app", REPO / "dashboard" / "lib"]
    offenders: list[str] = []
    for root in roots:
        for path in sorted(root.rglob("*.ts*")):
            if "tests/fixtures" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(REPO)))
    assert offenders == []


def test_dashboard_prod_bundle_has_no_test_markers() -> None:
    """I (build): the production bundle carries no synthetic secret marker."""
    build_dir = REPO / "dashboard" / ".next"
    if not build_dir.is_dir():
        pytest.skip("dashboard production build not present")
    hits: list[str] = []
    for path in sorted(build_dir.rglob("*.js")):
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        if "DO_NOT_EXPOSE" in text:
            hits.append(str(path.relative_to(REPO)))
    assert hits == []
