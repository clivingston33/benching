from __future__ import annotations

import benchmark.demo as demo_mod


def test_demo_run_emits_full_lifecycle_and_writes_results(tmp_path, monkeypatch) -> None:
    # Point the demo's run dir at a temp dir instead of the repo runs/ dir.
    monkeypatch.setattr(demo_mod, "RUNS", tmp_path)

    demo = demo_mod.DemoRun(provider="acme", total=3, failure_rate=0.0, task_seconds=0.0, seed=1)
    directory = demo.create_directory()
    assert (directory / "run.json").is_file()
    assert (directory / "harbor").is_dir()

    events = list(demo.events())
    phases = [event.phase for event in events]
    assert phases[0] == "docker"
    assert "running" in phases
    assert "task_completed" in phases
    assert phases[-1] == "done"

    completed = [event for event in events if event.phase == "task_completed"]
    assert len(completed) == 3
    final = events[-1]
    assert final.passed == 3
    assert final.failed == 0
    assert final.completed == 3
    # Harbor result files written per task.
    results = list((directory / "harbor").rglob("result.json"))
    assert len(results) == 3
    assert (directory / "raw.jsonl").stat().st_size > 0


def test_demo_run_respects_failure_rate(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(demo_mod, "RUNS", tmp_path)
    demo = demo_mod.DemoRun(provider="acme", total=20, failure_rate=1.0, task_seconds=0.0, seed=2)
    events = list(demo.events())
    final = events[-1]
    assert final.passed == 0
    assert final.failed == 20
