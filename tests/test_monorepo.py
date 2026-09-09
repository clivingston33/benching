"""M3-task-11 tests: one repository, single contract source, independent manifests.

The dashboard lives at dashboard/ with its own package.json; the only
cross-component connection is artifacts (schemas + examples) consumed from
their authoritative producer locations. No synchronized duplicates, no
sibling-checkout skips, no shared release version.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DASHBOARD = REPO / "dashboard"
SCHEMAS = REPO / "src" / "benching" / "benchmark" / "schemas"
CORPUS = REPO / "examples" / "artifacts"


def test_single_physical_schema_source() -> None:
    assert (SCHEMAS / "summary-v1.schema.json").is_file()
    assert (SCHEMAS / "comparison-v1.schema.json").is_file()
    assert not (DASHBOARD / "schemas").exists(), "dashboard must not keep synchronized schema copies"
    assert not (DASHBOARD / "scripts" / "sync-contract.mjs").exists()


def test_dashboard_contract_imports_resolve_to_producer_schemas() -> None:
    text = (DASHBOARD / "lib" / "contract.ts").read_text(encoding="utf-8")
    imported = re.findall(r'''from\s+["']([^"']+\.schema\.json)["']''', text)
    assert len(imported) == 2, imported
    for reference in imported:
        target = (DASHBOARD / "lib" / reference).resolve()
        assert target.is_file(), reference
        assert SCHEMAS in target.parents, reference


def test_no_sibling_checkout_assumptions_remain() -> None:
    haystacks = []
    package = DASHBOARD / "package.json"
    haystacks.append(package.read_text(encoding="utf-8"))
    for path in sorted((DASHBOARD / "tests").glob("*.test.ts")):
        haystacks.append(path.read_text(encoding="utf-8"))
    combined = "\n".join(haystacks)
    for marker in ("no benching checkout", "checkout not present", "sync-contract",
                   "contract:sync", "contract:check", "../benching", "../benching-dashboard"):
        assert marker not in combined, marker


def test_independent_manifests_and_versions() -> None:
    manifest = json.loads((DASHBOARD / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "benching-dashboard"
    assert manifest["version"]
    assert not (REPO / "package.json").exists(), "no root Node tree: dashboard keeps its own manifest"
    assert not (REPO / "pnpm-workspace.yaml").exists()
    assert not (REPO / "turbo.json").exists()
    assert not (REPO / "nx.json").exists()
    assert (DASHBOARD / "package-lock.json").is_file()


def test_no_nested_repository() -> None:
    assert not (DASHBOARD / ".git").exists()


def test_shared_corpus_present_dashboard_negatives_local() -> None:
    for name in ("summary-fireworks-a.json", "summary-fireworks-b.json", "comparison-fireworks-ab.json"):
        assert (CORPUS / name).is_file(), name
    for name in ("summary-malformed.json", "comparison-v2.json"):
        assert (DASHBOARD / "tests" / "fixtures" / name).is_file(), name
