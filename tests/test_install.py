"""M3-task-10 tests: namespaced package install, resources, path ownership.

Fast in-process checks first; a module-scoped isolated build + fresh venv
install (offline: --no-deps, --no-build-isolation, --no-index) proves the
wheel works outside the checkout. The venv inherits site packages only for
third-party dependencies, never for benching itself.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _run_venv(python: Path, code: str, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    merged = dict(os.environ)
    merged.pop("PYTHONPATH", None)
    merged.pop("PYTHONHOME", None)
    merged.pop("BENCHING_CONFIG_DIR", None)
    merged.pop("BENCHING_RUNS_DIR", None)
    if env:
        merged.update(env)
    return subprocess.run(
        [str(python), "-c", code],
        cwd=str(cwd),
        env=merged,
        capture_output=True,
        text=True,
        timeout=120,
    )


# Unit scope: namespace, runs-root policy, packaged resources. ----------------

def test_namespaced_imports() -> None:
    import benching
    import benching.agents
    import benching.analytics
    import benching.benchmark
    import benching.cli
    import benching.proxy

    assert Path(benching.__file__).resolve().parent.name == "benching"


def test_runs_root_defaults_to_invocation_directory(tmp_path: Path, monkeypatch) -> None:
    from benching.benchmark._paths import runs_root

    monkeypatch.delenv("BENCHING_RUNS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert runs_root() == tmp_path / "runs"


def test_runs_root_override_wins(tmp_path: Path, monkeypatch) -> None:
    from benching.benchmark._paths import runs_root

    target = tmp_path / "elsewhere" / "runs"
    monkeypatch.setenv("BENCHING_RUNS_DIR", str(target))
    assert runs_root() == target


def test_runs_root_never_inside_package() -> None:
    import benching
    from benching.benchmark._paths import runs_root

    install_root = Path(benching.__file__).resolve().parent
    assert runs_root() != install_root
    assert install_root not in runs_root().parents


def test_default_config_loads_from_package_resource() -> None:
    from benching.benchmark.config import benchmark_spec, default_config_text, load_yaml

    import yaml

    assert yaml.safe_load(default_config_text())["benchmark"]["name"] == "terminal-bench"
    spec = benchmark_spec(load_yaml())
    assert spec.name == "terminal-bench"
    assert spec.smoke_tasks


def test_schemas_load_from_package_resource() -> None:
    from benching.benchmark.contract import COMPARISON_SCHEMA, SUMMARY_SCHEMA, load_schema

    assert load_schema(SUMMARY_SCHEMA)["$id"].endswith("summary-v1.schema.json")
    assert load_schema(COMPARISON_SCHEMA)["$id"].endswith("comparison-v1.schema.json")


def test_resolve_executable_without_global_mutation(tmp_path: Path, monkeypatch) -> None:
    from benching.benchmark._paths import resolve_executable

    fake = tmp_path / "bin" / "harbor-fake"
    if os.name == "nt":
        fake = fake.with_suffix(".exe")
    fake.parent.mkdir(parents=True)
    fake.write_bytes(b"")
    if os.name != "nt":
        fake.chmod(0o755)  # shutil.which requires executability on POSIX
    monkeypatch.setenv("PATH", str(fake.parent))
    assert resolve_executable(fake.stem) == fake
    assert resolve_executable("definitely-not-a-real-binary-xyz") is None


def test_subprocess_environment_is_child_local(monkeypatch) -> None:
    from benching.benchmark.config import environment

    before = os.environ.get("PATH", "")
    monkeypatch.delenv("PYTHONPATH", raising=False)
    child = environment({"auth_env": "X", "api": "openai-completions"}, {"A": "1"})
    assert os.environ.get("PATH", "") == before
    assert "PYTHONPATH" not in os.environ
    assert str(Path.home() / ".local" / "bin") in child["PATH"]
    assert child["A"] == "1"


def test_import_has_no_path_side_effect() -> None:
    code = (
        "import os, sys; before = (os.environ.get('PATH', ''), os.environ.get('PYTHONPATH'))\n"
        "import benching.benchmark.runner, benching.benchmark.config, benching.benchmark.providers, "
        "benching.benchmark.concurrency, benching.analytics.analyze, benching.cli.app\n"
        "assert (os.environ.get('PATH', ''), os.environ.get('PYTHONPATH')) == before, 'env mutated by import'\n"
        "print('path-clean')\n"
    )
    completed = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr
    assert "path-clean" in completed.stdout


def test_harbor_command_uses_namespaced_agent(monkeypatch, tmp_path: Path) -> None:
    import benching.benchmark.runner as runner
    from benching.benchmark.config import benchmark_spec

    assert benchmark_spec({}).agent == "benching.agents.instrumented_omp_agent:InstrumentedOmpAgent"
    monkeypatch.setattr(runner, "executable", lambda name: name)
    spec = benchmark_spec({})
    command = runner.harbor_command(
        runner.RunOptions("acme", "smoke"),
        spec,
        {"auth_env": "ACME_API_KEY", "api": "openai-completions", "plan": None},
        "https://api.example.test/v1",
        "m",
        tmp_path / "run",
        ["task-a"],
    )
    agent = command[command.index("--agent") + 1]
    assert agent == "benching.agents.instrumented_omp_agent:InstrumentedOmpAgent"
    assert not any(part.startswith("agents.") and ":InstrumentedOmpAgent" in part for part in command)


def test_proxy_startup_uses_namespaced_module(tmp_path: Path, monkeypatch) -> None:
    import benching.benchmark.runner as runner

    captured: dict = {}

    class _FakePopen:
        pid = 4321

        def __init__(self, command, **kwargs):
            captured["command"] = command

        def poll(self):
            return None

    monkeypatch.setenv("BENCHING_ALLOW_UNSUPPORTED_PLATFORM", "1")
    monkeypatch.setattr(runner, "spawn_owned", _FakePopen)
    monkeypatch.setattr(runner, "_proxy_health_ok", lambda port, token: True)
    directory = tmp_path / "run"
    directory.mkdir()
    (directory / "proxy-auth.json").write_text(json.dumps({"auth_token": "tok"}), encoding="utf-8")
    process = runner.start_proxy(directory, 8765, "tok", timeout=5.0)
    assert process.pid == 4321
    assert captured["command"][:3] == [sys.executable, "-m", "benching.proxy.telemetry_proxy"]


def test_analyze_runs_uses_namespaced_module(tmp_path: Path, monkeypatch) -> None:
    import benching.benchmark.runner as runner

    captured: dict = {}

    class _Completed:
        returncode = 0

    def _fake_run(command, **kwargs):
        captured["command"] = command
        return _Completed()

    monkeypatch.setattr(runner.subprocess, "run", _fake_run)
    runner.analyze_runs([tmp_path / "a"], execution="sequential")
    assert captured["command"][:3] == [sys.executable, "-m", "benching.analytics.analyze"]


def test_examples_validate_and_hide_install_paths() -> None:
    from benching.benchmark.contract import check_summary_invariants, validate_comparison, validate_summary

    base = REPO / "examples" / "artifacts"
    for name in ("summary-fireworks-a.json", "summary-fireworks-b.json"):
        text = (base / name).read_text(encoding="utf-8")
        assert "site-packages" not in text
        assert "proxy_auth_token" not in text
        assert validate_summary(json.loads(text)) == []
    comparison_text = (base / "comparison-fireworks-ab.json").read_text(encoding="utf-8")
    assert "site-packages" not in comparison_text
    comparison = json.loads(comparison_text)
    assert validate_comparison(comparison) == []
    assert check_summary_invariants(json.loads((base / "summary-fireworks-a.json").read_text())) == []


# Isolated build + fresh install scope. ---------------------------------------

@pytest.fixture(scope="module")
def dist_dir(tmp_path_factory):
    target = tmp_path_factory.mktemp("dist")
    completed = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--sdist", "--outdir", str(target)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    return target


@pytest.fixture(scope="module")
def installed(dist_dir, tmp_path_factory):
    wheels = sorted(dist_dir.glob("benching-*.whl"))
    assert len(wheels) == 1
    home = tmp_path_factory.mktemp("install")
    venv_dir = home / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)], check=True, timeout=300)
    python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", "--force-reinstall", "--no-index", str(wheels[0])],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    site_packages = next(p for p in
                         (venv_dir / ("Lib/site-packages" if os.name == "nt" else f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"),)
                         if p.is_dir())
    return {"python": python, "site_packages": site_packages, "home": home}


def test_wheel_contains_namespaced_package(dist_dir) -> None:
    wheels = sorted(dist_dir.glob("benching-*.whl"))
    assert len(wheels) == 1
    names = set(zipfile.ZipFile(wheels[0]).namelist())
    for required in (
        "benching/__init__.py",
        "benching/benchmark/__init__.py",
        "benching/analytics/__init__.py",
        "benching/proxy/__init__.py",
        "benching/agents/__init__.py",
        "benching/cli/__init__.py",
        "benching/benchmark/resources/benchmark.yaml",
        "benching/benchmark/resources/provider.env.example",
        "benching/benchmark/schemas/summary-v1.schema.json",
        "benching/benchmark/schemas/comparison-v1.schema.json",
    ):
        assert required in names, required
    for legacy in ("benchmark/", "analytics/", "proxy/", "agents/", "cli/", "config/", "schemas/"):
        assert not any(name == legacy or name.startswith(legacy) for name in names), legacy
    assert not any(name == "dashboard/" or name.startswith("dashboard/") for name in names)


def test_sdist_contains_resources(dist_dir) -> None:
    archives = sorted(dist_dir.glob("benching-*.tar.gz"))
    assert len(archives) == 1
    names = set(tarfile.open(archives[0]).getnames())
    assert any(name.endswith("benching/benchmark/resources/benchmark.yaml") for name in names)
    assert any(name.endswith("benching/benchmark/schemas/summary-v1.schema.json") for name in names)
    assert any(name.endswith("benching/benchmark/schemas/comparison-v1.schema.json") for name in names)
    assert any(name.endswith("src/benching/benchmark/runner.py") for name in names)
    assert not any("/dashboard/" in name or name.endswith("/dashboard") for name in names)


def test_fresh_install_namespace_imports(installed, tmp_path) -> None:
    work = tmp_path / "outside"
    work.mkdir()
    code = (
        "import benching, benching.benchmark, benching.analytics, benching.proxy, benching.agents, benching.cli;"
        "import importlib.util;"
        "assert benching.__file__.startswith(r'''%s'''), benching.__file__;"
        "assert importlib.util.find_spec('benchmark') is None;"
        "assert importlib.util.find_spec('analytics') is None;"
        "assert importlib.util.find_spec('proxy') is None;"
        "assert importlib.util.find_spec('agents') is None;"
        "assert importlib.util.find_spec('cli') is None;"
        "print('namespace-ok')\n" % str(installed["site_packages"]).replace("'", "")
    )
    completed = _run_venv(installed["python"], code, work)
    assert completed.returncode == 0, completed.stderr
    assert "namespace-ok" in completed.stdout


def test_fresh_install_loads_default_config_and_schemas(installed, tmp_path) -> None:
    work = tmp_path / "outside"
    work.mkdir()
    code = (
        "from benching.benchmark.config import load_yaml;"
        "spec = load_yaml()['benchmark'];"
        "assert spec['name'] == 'terminal-bench', spec;"
        "from benching.benchmark.contract import validate_summary, validate_comparison, load_schema;"
        "load_schema('summary-v1.schema.json'); load_schema('comparison-v1.schema.json');"
        "assert validate_summary({'schema_version': 1}) != [];"
        "print('installed-ok')\n"
    )
    completed = _run_venv(installed["python"], code, work)
    assert completed.returncode == 0, completed.stderr
    assert "installed-ok" in completed.stdout


def test_fresh_install_module_invocation(installed, tmp_path) -> None:
    work = tmp_path / "outside"
    work.mkdir()
    merged = dict(os.environ)
    merged.pop("PYTHONPATH", None)
    for target in (
        [installed["python"], "-m", "benching.cli.app", "--help"],
        [installed["python"], "-m", "benching.proxy.telemetry_proxy", "--help"],
        [installed["python"], "-m", "benching.analytics.analyze", "--help"],
    ):
        completed = subprocess.run([str(part) for part in target], cwd=str(work), env=merged,
                                   capture_output=True, text=True, timeout=120)
        assert completed.returncode == 0, (target, completed.stderr)


def test_fresh_install_runs_root_outside_site_packages(installed, tmp_path) -> None:
    work = tmp_path / "outside"
    work.mkdir()
    code = (
        "from benching.benchmark._paths import runs_root;"
        "root = runs_root();"
        f"assert str(root).startswith(r'''{work}'''), root;"
        "import benching.benchmark._paths as p;"
        f"assert r'''{installed['site_packages']}''' not in str(root), root;"
        "print('runs-root-ok', root)\n"
    )
    completed = _run_venv(installed["python"], code, work)
    assert completed.returncode == 0, completed.stderr
    assert "runs-root-ok" in completed.stdout


def test_fresh_install_runs_root_override_and_discovery(installed, tmp_path) -> None:
    runs = tmp_path / "custom-runs"
    code = (
        "from benching.benchmark._paths import runs_root;"
        "from benching.analytics.analyze import comparison_path;"
        "from benching.benchmark.validation import write_validation_report;"
        "from benching.benchmark.runs import all_run_dirs;"
        "assert runs_root().name == 'custom-runs';"
        "assert comparison_path().parent.name == 'custom-runs';"
        "report = write_validation_report('probe', {'ok': True});"
        "assert report.parent.name == 'custom-runs' and report.is_file();"
        "assert all_run_dirs() == [];"
        "print('override-ok')\n"
    )
    completed = _run_venv(installed["python"], code, tmp_path, env={"BENCHING_RUNS_DIR": str(runs)})
    assert completed.returncode == 0, completed.stderr
    assert "override-ok" in completed.stdout
    assert runs.is_dir()


def test_fresh_install_user_config_override(installed, tmp_path) -> None:
    cfg = tmp_path / "user-cfg"
    code = (
        "import os;"
        "from benching.benchmark.providers import add_provider, list_providers;"
        "from benching.benchmark.state import load_state;"
        "entry = add_provider('acme', 'https://api.example.test/v1', 'm', 'dummy-secret', make_active=False);"
        "assert entry['env_file'].startswith(os.environ['BENCHING_CONFIG_DIR']), entry;"
        "assert any(item['name'] == 'acme' for item in list_providers());"
        "assert load_state().concurrency > 0;"
        "from benching.benchmark.config import load_yaml;"
        "assert load_yaml()['benchmark']['name'] == 'terminal-bench';"
        "print('config-ok')\n"
    )
    completed = _run_venv(installed["python"], code, tmp_path, env={"BENCHING_CONFIG_DIR": str(cfg)})
    assert completed.returncode == 0, completed.stderr
    assert "config-ok" in completed.stdout
    assert (cfg / "providers" / "acme.env").is_file()
    assert (cfg / "providers.yaml").is_file()


def test_read_only_package_files_keep_working(installed, tmp_path) -> None:
    package = installed["site_packages"] / "benching" / "benchmark"
    targets = [package / "resources" / "benchmark.yaml", package / "schemas" / "summary-v1.schema.json"]
    previous = {}
    for target in targets:
        st = target.stat()
        previous[target] = st.st_mode
        try:
            target.chmod(0o444)
        except OSError:
            pass
    try:
        work = tmp_path / "outside"
        work.mkdir()
        code = (
            "from benching.benchmark.config import load_yaml;"
            "from benching.benchmark.contract import load_schema;"
            "assert load_yaml()['benchmark']['name'] == 'terminal-bench';"
            "assert load_schema('summary-v1.schema.json')['$id'];"
            "from benching.benchmark._paths import runs_root;"
            "runs_root().mkdir(parents=True, exist_ok=True);"
            "(runs_root() / 'status.json').write_text('{}');"
            "print('readonly-ok')\n"
        )
        completed = _run_venv(installed["python"], code, work)
        assert completed.returncode == 0, completed.stderr
        assert "readonly-ok" in completed.stdout
        assert (work / "runs" / "status.json").is_file()
    finally:
        for target, mode in previous.items():
            try:
                target.chmod(mode)
            except OSError:
                pass


def test_fresh_install_cli(installed, tmp_path) -> None:
    work = tmp_path / "outside"
    work.mkdir()
    console = installed["python"].parent / ("benching.exe" if os.name == "nt" else "benching")
    assert console.is_file()
    merged = dict(os.environ)
    merged.pop("PYTHONPATH", None)
    completed = subprocess.run([str(console), "--help"], cwd=str(work), env=merged, capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr
    assert "benchmark" in completed.stdout.lower()
    doctor = subprocess.run([str(console), "doctor", "check"], cwd=str(work), env=merged, capture_output=True, text=True, timeout=180)
    assert "benching environment" in doctor.stdout, doctor.stderr
    # M3-12: bare doctor/runs perform their default actions; help surfaces stay green.
    bare_doctor = subprocess.run([str(console), "doctor"], cwd=str(work), env=merged, capture_output=True, text=True, timeout=180)
    assert "benching environment" in bare_doctor.stdout, bare_doctor.stderr
    runs = subprocess.run([str(console), "runs"], cwd=str(work), env=merged, capture_output=True, text=True, timeout=180)
    assert runs.returncode == 0, runs.stderr
    assert "No runs match." in runs.stdout, runs.stdout
    for args in (["results", "--help"], ["tokenizer", "--help"]):
        completed = subprocess.run([str(console), *args], cwd=str(work), env=merged, capture_output=True, text=True, timeout=120)
        assert completed.returncode == 0, (args, completed.stderr)
