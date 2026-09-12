"""M3-task-12 tests: one core data path shared by Typer and the slash shell.

Typer commands and slash commands must resolve and represent the same
runs/results/settings/tokenizer state; only terminal formatting may
differ. Viewing results must never rewrite artifacts; only explicit
reanalysis may.
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

runner = CliRunner(env={"COLUMNS": "200"})
REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "benching"
BENCHMARK = SRC / "benchmark"
CLI = SRC / "cli"


def _write_run(root: Path, name: str, *, provider: str = "acme", status_name: str = "completed", stale: bool = False) -> Path:
    directory = root / name
    (directory / "harbor").mkdir(parents=True)
    now = "2026-09-01T00:00:00Z"
    directory.joinpath("run.json").write_text(json.dumps({
        "run_id": name, "created_at_utc": now, "benchmark": "terminal-bench",
        "benchmark_version": "2.1", "benchmark_model": "dummy-model", "api_model": "dummy-model",
        "provider": provider, "task_count": 0, "concurrency": 1, "trials": 1,
    }), encoding="utf-8")
    status_doc: dict = {"status": status_name, "updated_at_utc": now}
    if stale:
        status_doc["status"] = "running"
    directory.joinpath("status.json").write_text(json.dumps(status_doc), encoding="utf-8")
    if stale:
        directory.joinpath("pid").write_text("99999999\n", encoding="utf-8")
    directory.joinpath("raw.jsonl").write_text("", encoding="utf-8")
    directory.joinpath("metrics.jsonl").write_text("", encoding="utf-8")
    directory.joinpath("summary.json").write_text(json.dumps({
        "run_id": name, "timing": {}, "reliability": {"success_rate": 1.0}, "tokens": {},
    }), encoding="utf-8")
    return directory


@pytest.fixture()
def runs_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "runs"
    root.mkdir()
    monkeypatch.setenv("BENCHING_RUNS_DIR", str(root))
    return root


def test_runs_semantics_parity(runs_root: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """B: core discovery, Typer runs, and slash /runs agree on ids/status."""
    monkeypatch.setenv("COLUMNS", "200")
    from benching.benchmark.runs import all_run_dirs, describe_run
    from benching.cli import runs as runs_cli
    from benching.cli.shell import Session, cmd_runs

    _write_run(runs_root, "tb-v1-acme-full-20260901-000000-a1b2c3d4")
    _write_run(runs_root, "tb-v1-acme-full-20260901-000001-e5f6a7b8", stale=True)

    core = {d.name: describe_run(d) for d in all_run_dirs()}
    assert set(core) == {
        "tb-v1-acme-full-20260901-000000-a1b2c3d4",
        "tb-v1-acme-full-20260901-000001-e5f6a7b8",
    }
    assert core["tb-v1-acme-full-20260901-000000-a1b2c3d4"]["status"] == "completed"
    assert core["tb-v1-acme-full-20260901-000001-e5f6a7b8"]["stale"] is True

    completed = runner.invoke(runs_cli.app, ["list"])
    assert completed.exit_code == 0, completed.output
    for name in core:
        assert name[:30] in completed.output, name  # table ellipsizes long ids
    assert "completed" in completed.output
    assert "stale" in completed.output

    session = Session(provider="acme", benchmark=None, model=None, concurrency=3, reasoning="default", trials=1)
    cmd_runs(session, [])
    shell_out = capsys.readouterr().out
    for name in core:
        assert name[:30] in shell_out, name  # shell table also ellipsizes
    assert "stale" in shell_out


def test_results_semantics_parity_and_readonly(runs_root: Path, capsys: pytest.CaptureFixture) -> None:
    """C+K: core, Typer, and shell select the same summary; nobody rewrites."""
    from benching.benchmark.results import load_result, summary_for
    from benching.cli import results as results_cli
    from benching.cli.shell import Session, cmd_results

    name = "tb-v1-acme-full-20260901-000000-a1b2c3d4"
    _write_run(runs_root, name)

    def _hashes() -> dict[str, str]:
        return {
            str(p.relative_to(runs_root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((runs_root / name).rglob("*")) if p.is_file()
        }

    before = _hashes()
    directory, summary = load_result("latest")
    assert directory.name == name
    assert summary == summary_for(directory) == json.loads((directory / "summary.json").read_text(encoding="utf-8"))

    shown = runner.invoke(results_cli.app, ["show", "latest"])
    assert shown.exit_code == 0, shown.output
    assert name in shown.output

    session = Session(provider="acme", benchmark=None, model=None, concurrency=3, reasoning="default", trials=1)
    cmd_results(session, [])
    shell_out = capsys.readouterr().out
    assert name in shell_out

    assert _hashes() == before, "viewing results must not mutate run artifacts"


def test_reanalysis_remains_explicit(runs_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D: result viewing never calls the analyzer; reanalysis does."""
    import benching.benchmark.results as core_results
    from benching.cli import results as results_cli

    _write_run(runs_root, "tb-v1-acme-full-20260901-000000-a1b2c3d4")

    def _bomb(directories, **kwargs):
        raise AssertionError("analyzer must not run on result view")

    monkeypatch.setattr(core_results, "normalize_runs", _bomb)
    directory, summary = core_results.load_result("latest")
    assert summary is not None
    shown = runner.invoke(results_cli.app, ["show", "latest"])
    assert shown.exit_code == 0, shown.output
    with pytest.raises(AssertionError):
        core_results.reanalyze_run(directory)
    failed = runner.invoke(results_cli.app, ["reanalyze", "latest"])
    assert failed.exit_code != 0


def _register_dummy_provider(name: str = "acme-a", model: str = "dummy-model-x") -> None:
    from benching.benchmark.providers import add_provider

    add_provider(name, "https://api.example.test/v1", model, "dummy-key", make_active=False)


def _register_dummy_suite(tmp_path: Path, name: str = "suite-s") -> None:
    from benching.benchmark.benchmarks import add_benchmark, set_active_benchmark

    tasks = tmp_path / "tasks"
    (tasks / "task-one").mkdir(parents=True)
    spec_defaults = {"model": None, "reasoning": "default", "max_tokens": None,
                     "context_window": None, "tokenizer_repo": "repo", "tokenizer_revision": "rev"}
    add_benchmark(name, {
        "name": "suite-s", "version": "9", "tasks_dir": str(tasks), "agent": "agent",
        **spec_defaults, "run_id_prefix": name, "expected_task_count": 1,
        "smoke_tasks": ["task-one"], "tokenizer": {"repo": "repo", "revision": "rev"},
    }, make_active=False)
    set_active_benchmark(name)


def test_effective_settings_parity(tmp_path: Path) -> None:
    """E: Typer run and shell run resolve identical settings, plus override."""
    from benching.benchmark.settings import effective_settings, run_options
    from benching.benchmark.state import update_state
    from benching.cli.shell import Session, _build_run_options

    _register_dummy_provider()
    _register_dummy_suite(tmp_path)
    update_state(active_provider="acme-a", model="dummy-model-x", reasoning="enabled", concurrency=3, trials=2)

    typer_options, typer_settings = run_options("full")
    session = Session(provider="acme-a", benchmark="suite-s", model="dummy-model-x",
                      concurrency=3, reasoning="enabled", trials=2)
    shell_options, shell_settings = _build_run_options(session, "full")
    assert typer_options == shell_options
    assert typer_settings.provider == shell_settings.provider == "acme-a"
    assert (typer_settings.model, typer_settings.reasoning,
            typer_settings.concurrency, typer_settings.trials) == ("dummy-model-x", "enabled", 3, 2)
    assert typer_settings.spec.name == shell_settings.spec.name == "suite-s"

    overridden, _ = run_options("full", concurrency=9)
    assert overridden.concurrency == 9
    assert typer_options.concurrency == 3


def test_tokenizer_parity_with_runner(tmp_path: Path) -> None:
    """F: tokenizer status/prepare resolve the runner's tokenizer identity."""
    from benching.benchmark.settings import effective_settings
    from benching.benchmark.state import update_state
    from benching.benchmark.tokenizer import resolve_tokenizer_context, tokenizer_metadata

    _register_dummy_provider()
    _register_dummy_suite(tmp_path)
    update_state(active_provider="acme-a", model="dummy-model-x")
    settings = effective_settings()
    context = resolve_tokenizer_context(settings.root, settings.spec, settings.provider, settings.model)
    # Same inputs the runner feeds tokenizer_metadata inside run_one.
    assert context["metadata"] == tokenizer_metadata(settings.spec, context["values"], context["model_settings"])
    assert context["api_model"] == "dummy-model-x"
    assert context["metadata"]["repo"] == "repo"

    from benching.cli import tokenizer as tokenizer_cli

    status = runner.invoke(tokenizer_cli.app, ["status"])
    assert status.exit_code == 0, status.output
    assert "acme-a" in status.output and "dummy-model-x" in status.output


def test_doctor_default_runs_checks() -> None:
    """G: bare `benching doctor` performs checks instead of subgroup help."""
    from benching.cli.app import app

    completed = runner.invoke(app, ["doctor"])
    assert "benching environment" in completed.output
    assert "Usage:" not in completed.output


def test_runs_default_lists_runs(runs_root: Path) -> None:
    """H: bare `benching runs` lists runs instead of subgroup help."""
    from benching.cli.app import app

    _write_run(runs_root, "tb-v1-acme-full-20260901-000000-a1b2c3d4")
    completed = runner.invoke(app, ["runs"])
    assert completed.exit_code == 0, completed.output
    assert "tb-v1-acme-full-20260901-000000" in completed.output


def test_core_has_no_presentation_imports() -> None:
    """A (static): reusable benchmark code must not import CLI rendering."""
    offenders: list[str] = []
    for path in sorted(BENCHMARK.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in {"rich", "typer", "prompt_toolkit"}:
                        offenders.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root in {"rich", "typer", "prompt_toolkit"} or (node.module or "") == "benching.cli" or (node.module or "").startswith("benching.cli."):
                    offenders.append(f"{path.name}: from {node.module} import ...")
    assert offenders == []


def test_core_import_does_not_pull_presentation() -> None:
    """A (runtime): importing core must not require Rich/Typer/shell."""
    code = (
        "import sys;"
        "import benching.benchmark.runner, benching.benchmark.results, benching.benchmark.runs,"
        " benching.benchmark.settings, benching.benchmark.tokenizer, benching.benchmark.doctor;"
        "banned = [m for m in ('rich', 'typer', 'prompt_toolkit', 'benching.cli') if m in sys.modules];"
        "assert not banned, banned; print('core-clean')"
    )
    completed = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                               capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr
    assert "core-clean" in completed.stdout


    runs_text = (CLI / "runs.py").read_text(encoding="utf-8")
    assert "iterdir" not in runs_text, "cli/runs.py must use core discovery, not scan directories"
    assert "read_text" not in runs_text, "cli/runs.py must use core readers, not read run files"
    results_text = (CLI / "results.py").read_text(encoding="utf-8")
    assert "summarize(" not in results_text, "cli/results.py must show the canonical summary, not recompute it"
    results_tree = ast.parse((BENCHMARK / "results.py").read_text(encoding="utf-8"))
    loads = {node.name: ast.dump(node) for node in ast.walk(results_tree) if isinstance(node, ast.FunctionDef)}
    assert "normalize_runs" not in loads["load_result"], "viewing results must stay read-only"
    assert "normalize_runs" in loads["reanalyze_run"], "reanalysis is the explicit write path"


def test_no_benchmarkctl_references_remain() -> None:
    """J: the obsolete entry path is gone; only intentional history mentions it."""
    assert not (BENCHMARK / "benchmarkctl.py").exists()
    assert not (BENCHMARK / "live.py").exists(), "Rich live rendering lives in cli/live.py now"
    offenders: list[str] = []
    for path in sorted(REPO.rglob("*")):
        if "__pycache__" in path.parts or ".git" in path.parts or "build" in path.parts or ".pytest_cache" in path.parts:
            continue
        if path.suffix not in {".py", ".toml", ".md", ".ts", ".tsx", ".json", ".mjs"}:
            continue
        if path.name == "test_cli_core_parity.py" or path.name == "README.md":
            continue  # this test itself; README's intentional history note
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "benchmarkctl" in text:
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == []


def test_cli_does_not_bypass_results_boundary() -> None:
    """Architecture: no CLI module reaches around benchmark/results.py."""
    offenders: list[str] = []
    for path in sorted(CLI.glob("*.py")):
        if path.name in {"results.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if "summary_for" in text or "reanalyze_run" in text or "A.summarize" in text:
            offenders.append(path.name)
    assert offenders == []


def test_shell_smoke_without_provider_traffic(
    capsys: pytest.CaptureFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M: representative slash commands work with no provider traffic."""
    from benching.cli.shell import Session, dispatch

    empty = tmp_path / "runs"
    empty.mkdir()
    monkeypatch.setenv("BENCHING_RUNS_DIR", str(empty))
    monkeypatch.setenv("COLUMNS", "200")
    session = Session(provider=None, benchmark=None, model=None, concurrency=3, reasoning="default", trials=1)
    for line in ("/help", "/config", "/runs", "/results", "/tokenizer", "/tokenizer status"):
        assert dispatch(session, line) is True, line
    out = capsys.readouterr().out
    assert "Commands" in out and "tokenizer" in out, out
    assert "Benchmark" in out and "Repo" in out, out
    assert "No runs match." in out  # empty runs root, still a clean listing
