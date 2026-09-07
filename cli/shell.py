"""benching interactive shell — slash commands over prompt_toolkit.

Thin: parses input, mutates the :class:`Session`, delegates all real work to
the ``benchmark/`` layer. ``/run`` and ``/smoke`` build the same
``RunOptions`` the CLI uses, so execution is identical.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass

from rich.console import Console

from benchmark.state import UserState, load_state, update_state

console = Console()


@dataclass
class Session:
    provider: str | None
    benchmark: str | None
    model: str | None
    concurrency: int
    reasoning: str
    trials: int

    @classmethod
    def from_state(cls, state: UserState) -> Session:
        return cls(
            provider=state.active_provider,
            benchmark=state.active_benchmark,
            model=state.model,
            concurrency=state.concurrency,
            reasoning=state.reasoning,
            trials=state.trials,
        )


def _ok(message: str) -> None:
    console.print(f"[green]✓[/green] {message}")


def _err(message: str) -> None:
    console.print(f"[red]✗[/red] {message}")


def _resolve_root_config(session: Session) -> dict:
    from benchmark.benchmarks import active_root_config

    return active_root_config()


def _session_benchmark_name(session: Session) -> str | None:
    return session.benchmark


def cmd_provider(session: Session, args: list[str]) -> None:
    """/provider [use|add|remove|edit|validate|probe] — manage providers."""
    from benchmark.providers import set_active_provider

    if not args:
        if session.provider:
            console.print(f"Active provider: [cyan]{session.provider}[/cyan]")
        else:
            console.print("No active provider; use [bold]/provider use NAME[/bold].")
        return
    command, rest = args[0], args[1:]
    if command in {"list", "ls"}:
        cmd_providers(session, [])
        return
    if command == "use" and rest:
        name = rest[0]
        try:
            set_active_provider(name)
        except SystemExit as exc:
            _err(str(exc.code or exc))
            return
        session.provider = name
        _ok(f"Provider: {name}")
        return
    if command == "add":
        import getpass
        import typer

        from benchmark.providers import add_provider

        name = typer.prompt("Name")
        base_url = typer.prompt("Base URL")
        api_key = getpass.getpass("API key: ")
        model = typer.prompt("Model")
        try:
            add_provider(name, base_url, model, api_key)
        except SystemExit as exc:
            _err(str(exc.code or exc))
            return
        session.provider = name
        _ok(f"Provider added: {name}")
        console.print("Testing connection...")
        from cli.providers import validate

        validate(name)
        _ok("Authentication")
        _ok("Streaming response")
        return
    if command in {"remove", "edit", "validate", "probe"} and rest:
        name = rest[0]
        if command == "remove":
            import typer

            if not typer.confirm(f"Remove provider {name}?", default=False):
                return
            from benchmark.providers import remove_provider

            remove_provider(name)
            if session.provider == name:
                session.provider = None
            _ok(f"Provider removed: {name}")
        elif command == "edit":
            import getpass
            import typer

            from benchmark.config import load_yaml
            from benchmark.providers import rename_key_field, update_provider

            cfg = (load_yaml().get("providers") or {}).get(name)
            if not isinstance(cfg, dict):
                _err(f"unknown provider: {name}")
                return
            base_url = typer.prompt("Base URL", default=str(cfg.get("base_url") or ""))
            model = typer.prompt("Model", default=str(cfg.get("api_model") or ""))
            api_key = getpass.getpass("API key (blank keeps current): ")
            update_provider(name, base_url=base_url, api_model=model)
            if api_key:
                rename_key_field(name, api_key)
            _ok(f"Provider updated: {name}")
        elif command == "validate":
            from cli.providers import validate

            validate(name)
        else:
            from cli.providers import probe

            probe(name)
        return
    _err("usage: /provider use NAME | add | remove NAME | edit NAME | validate NAME | probe NAME")


def cmd_providers(session: Session, args: list[str]) -> None:
    """/providers — list all configured providers."""
    from rich.table import Table

    from benchmark.providers import list_providers

    table = Table(title="Providers", show_header=True, header_style="bold")
    table.add_column("NAME", style="bold")
    table.add_column("MODEL")
    table.add_column("STATUS")
    for item in list_providers():
        name = item["name"]
        cfg = item["cfg"]
        auth_env = str(cfg.get("auth_env", ""))
        from benchmark.config import provider_env_values

        env = provider_env_values(name, cfg)
        status = "configured" if env.get(auth_env) else "missing credentials"
        table.add_row(("* " if name == session.provider else "") + name, str(cfg.get("api_model") or ""), status)
    console.print(table)


def cmd_model(session: Session, args: list[str]) -> None:
    """/model [name] — show or set the model override."""
    if not args:
        console.print(f"Model: [cyan]{session.model or '(benchmark default)'}[/cyan]")
        return
    model = args[0]
    update_state(model=model)
    session.model = model
    _ok(f"Model: {model}")


def cmd_benchmark(session: Session, args: list[str]) -> None:
    """/benchmark [use|add|remove|list|info] — manage benchmarks."""
    from benchmark.benchmarks import add_benchmark, load_manifest, set_active_benchmark
    from benchmark.config import benchmark_spec, load_yaml

    if not args:
        if session.benchmark:
            manifest = load_manifest(session.benchmark)
            settings = manifest.get("benchmark") or {}
            console.print(f"Active benchmark: [cyan]{session.benchmark}[/cyan] ({settings.get('name', '')} {settings.get('version', '')})".strip())
        else:
            console.print("No active benchmark; using repo config/benchmark.yaml.")
        return
    command, rest = args[0], args[1:]
    if command in {"list", "ls"}:
        cmd_benchmarks(session, [])
        return
    if command == "add":
        import typer

        defaults = benchmark_spec(load_yaml())
        name = typer.prompt("Name")
        suite = typer.prompt("Suite name")
        version = typer.prompt("Version")
        tasks_dir = typer.prompt("Tasks directory")
        agent = typer.prompt("Agent", default=defaults.agent)
        expected = typer.prompt("Expected task count (blank for unset)", default="")
        smoke = typer.prompt("Smoke tasks (comma-separated)", default="")
        try:
            settings = {
                "name": suite,
                "version": version,
                "tasks_dir": tasks_dir,
                "agent": agent,
                "model": defaults.model,
                "reasoning": defaults.reasoning,
                "max_tokens": defaults.max_tokens,
                "context_window": defaults.context_window,
                "run_id_prefix": name,
                "expected_task_count": int(expected) if expected else None,
                "smoke_tasks": [item.strip() for item in smoke.split(",") if item.strip()],
                "tokenizer": {"repo": defaults.tokenizer_repo, "revision": defaults.tokenizer_revision},
            }
            add_benchmark(name, settings)
        except (SystemExit, ValueError) as exc:
            _err(str(getattr(exc, "code", None) or exc))
            return
        session.benchmark = name
        _ok(f"Benchmark added: {name}")
        return
    if command == "remove" and rest:
        import typer

        name = rest[0]
        if typer.confirm(f"Remove benchmark {name}?", default=False):
            from benchmark.benchmarks import remove_benchmark

            remove_benchmark(name)
            if session.benchmark == name:
                session.benchmark = None
            _ok(f"Benchmark removed: {name}")
        return
    if command == "info" and rest:
        console.print(load_manifest(rest[0]))
        return
    name = rest[0] if command == "use" and rest else command
    try:
        set_active_benchmark(name)
    except SystemExit as exc:
        _err(str(exc.code or exc))
        return
    session.benchmark = name
    settings = load_manifest(name).get("benchmark") or {}
    display = f"{settings.get('name', name)} {settings.get('version', '')}".strip()
    _ok(f"Benchmark: {display} · {settings.get('expected_task_count') or '?'} tasks")


def cmd_benchmarks(session: Session, args: list[str]) -> None:
    """/benchmarks — list registered benchmarks."""
    from rich.table import Table

    from benchmark.benchmarks import list_benchmarks

    entries = list_benchmarks()
    table = Table(title="Benchmarks", show_header=True, header_style="bold")
    table.add_column("", width=2)
    table.add_column("NAME", style="bold")
    table.add_column("SUITE")
    table.add_column("TASKS")
    if not entries:
        console.print("[yellow]No benchmarks registered; use `benching benchmark add`.[/yellow]")
        return
    for entry in entries:
        table.add_row("*" if entry["active"] else "", entry["name"], str(entry["display"]), str(entry["expected_task_count"] or "?"))
    console.print(table)


def _build_run_options(session: Session, mode: str):
    from benchmark.runner import RunOptions

    return RunOptions(
        provider=session.provider or "",
        mode=mode,
        benchmark_model=session.model,
        reasoning=session.reasoning,
        concurrency=session.concurrency,
        trials=session.trials,
    )


def _run(session: Session, mode: str) -> None:
    from benchmark.benchmarks import active_root_config
    from benchmark.runner import run_one
    from cli.live import drive_live_view

    if not session.provider:
        _err("no active provider; /provider use NAME")
        return
    options = _build_run_options(session, mode)
    root = active_root_config()
    from benchmark.config import benchmark_spec

    spec = benchmark_spec(root)
    title = f"[bold]{spec.display_name}[/bold] — [cyan]{session.provider}[/cyan] ({mode}, concurrency {session.concurrency})"

    def start(on_event):
        return run_one(options, root, progress=on_event)

    result = drive_live_view(start, title=title)
    if "error" in result:
        _err("run failed")
        console.print(f"[red]{result['error']}[/red]")
        return
    directory = result.get("value")
    if directory is not None:
        console.print(f"\n[green]Run complete:[/green] [cyan]{directory}[/cyan]")


def cmd_run(session: Session, args: list[str]) -> None:
    """/run — full run against the active provider."""
    _run(session, "full")


def cmd_smoke(session: Session, args: list[str]) -> None:
    """/smoke — smoke run against the active provider."""
    _run(session, "smoke")


def cmd_concurrency(session: Session, args: list[str]) -> None:
    """/concurrency [N] — show or set default concurrency."""
    if not args:
        console.print(f"Concurrency: [cyan]{session.concurrency}[/cyan]")
        return
    try:
        value = int(args[0])
        assert value >= 1
    except (ValueError, AssertionError):
        _err("concurrency must be a positive integer")
        return
    update_state(concurrency=value)
    session.concurrency = value
    _ok(f"Concurrency: {value}")


def cmd_reasoning(session: Session, args: list[str]) -> None:
    """/reasoning [mode] — show or set reasoning mode (default/enabled/disabled)."""
    if not args:
        console.print(f"Reasoning: [cyan]{session.reasoning}[/cyan]")
        return
    mode = args[0]
    if mode not in {"default", "enabled", "disabled"}:
        _err("reasoning must be default, enabled, or disabled")
        return
    update_state(reasoning=mode)
    session.reasoning = mode
    _ok(f"Reasoning: {mode}")


def cmd_trials(session: Session, args: list[str]) -> None:
    """/trials [N] — show or set trials per task."""
    if not args:
        console.print(f"Trials: [cyan]{session.trials}[/cyan]")
        return
    try:
        value = int(args[0])
        assert value >= 1
    except (ValueError, AssertionError):
        _err("trials must be a positive integer")
        return
    update_state(trials=value)
    session.trials = value
    _ok(f"Trials: {value}")


def cmd_compare(session: Session, args: list[str]) -> None:
    """/compare A B — run and compare two providers."""
    from benchmark.benchmarks import active_root_config
    from benchmark.config import benchmark_spec, enabled_providers
    from benchmark.runner import analyze_runs, compare as compare_runs

    if len(args) < 2:
        _err("usage: /compare PROVIDER_A PROVIDER_B [...]")
        return
    root = active_root_config()
    configured = set(enabled_providers(root))
    unknown = [name for name in args if name not in configured]
    if unknown:
        _err(f"provider(s) not enabled: {', '.join(unknown)}")
        return
    spec = benchmark_spec(root)
    console.print(f"[bold]{spec.display_name}[/bold] — comparing {', '.join(args)} (sequential)")
    try:
        directories = compare_runs(args, "full", session.model, session.concurrency, session.trials, root, reasoning=session.reasoning)
        analyze_runs(directories)
    except SystemExit as exc:
        _err(f"comparison failed: {exc.code or exc}")
        return
    console.print("[green]Comparison complete[/green]")


def cmd_runs(session: Session, args: list[str]) -> None:
    """/runs — list past runs."""
    from cli.runs import list as runs_list

    runs_list()


def cmd_results(session: Session, args: list[str]) -> None:
    """/results [run_id|latest] — show results for a run."""
    from cli.results import show as results_show

    results_show(args[0] if args else "latest")


def cmd_doctor(session: Session, args: list[str]) -> None:
    """/doctor — environment health checks."""
    from cli.doctor import check as doctor_check

    doctor_check()


def cmd_config(session: Session, args: list[str]) -> None:
    """/config — show active configuration."""
    from cli.config import show as config_show

    config_show()


def cmd_help(session: Session, args: list[str]) -> None:
    """/help — list commands."""
    console.print("[bold]Commands[/bold]")
    for name, handler in sorted(COMMANDS.items()):
        doc = (handler.__doc__ or "").strip()
        console.print(f"  [cyan]/{name:<12}[/cyan] {doc}")


def cmd_exit(session: Session, args: list[str]) -> bool:
    """/exit — leave the shell."""
    return False


COMMANDS: dict[str, object] = {
    "provider": cmd_provider,
    "providers": cmd_providers,
    "model": cmd_model,
    "benchmark": cmd_benchmark,
    "benchmarks": cmd_benchmarks,
    "run": cmd_run,
    "smoke": cmd_smoke,
    "compare": cmd_compare,
    "concurrency": cmd_concurrency,
    "reasoning": cmd_reasoning,
    "trials": cmd_trials,
    "runs": cmd_runs,
    "results": cmd_results,
    "doctor": cmd_doctor,
    "config": cmd_config,
    "help": cmd_help,
    "exit": cmd_exit,
}


def dispatch(session: Session, line: str) -> bool:
    """Dispatch one slash command; return False when the shell should exit."""
    parts = shlex.split(line[1:] if line.startswith("/") else line)
    if not parts:
        return True
    handler = COMMANDS.get(parts[0].lower())
    if handler is None:
        _err(f"unknown command: /{parts[0]}")
        return True
    try:
        result = handler(session, parts[1:])
    except SystemExit as exc:
        _err(str(exc.code or exc))
        return True
    except KeyboardInterrupt:
        return False
    return result is not False


def _banner(session: Session) -> None:
    from benchmark.config import benchmark_spec, load_yaml

    bench_name = session.benchmark or "config/benchmark.yaml"
    try:
        if session.benchmark:
            from benchmark.benchmarks import load_manifest
            spec = benchmark_spec(load_manifest(session.benchmark))
        else:
            spec = benchmark_spec(load_yaml())
        bench_display = spec.display_name
        task_count = spec.expected_task_count or "?"
        model = session.model or spec.model
    except SystemExit:
        bench_display, task_count, model = bench_name, "?", "?"
    provider = session.provider or "no provider"
    console.print("[bold]benching 0.2.0[/bold]")
    console.print()
    console.print(f"{bench_display} · {task_count} tasks")
    console.print(f"{model} · {provider}")
    console.print(f"concurrency {session.concurrency} · reasoning {session.reasoning} · trials {session.trials}")
    console.print()
    console.print("Type [cyan]/help[/cyan] for commands")


def run_shell() -> None:
    """Entry point: the interactive loop."""
    state = load_state()
    session = Session.from_state(state)
    _banner(session)
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import Completer, Completion
        from prompt_toolkit.history import FileHistory
    except ImportError:
        console.print("[yellow]prompt_toolkit missing; falling back to plain input.[/yellow]")
        _plain_loop(session)
        return
    from benchmark.state import app_dir

    history_path = app_dir() / "history"
    history_path.parent.mkdir(parents=True, exist_ok=True)

    class SlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text
            if text.startswith("/") and " " not in text:
                for name in sorted(COMMANDS):
                    if name.startswith(text[1:]):
                        yield Completion(name, start_position=-len(text[1:]))

    try:
        prompt = PromptSession(history=FileHistory(str(history_path)), completer=SlashCompleter())
    except Exception:
        # No interactive console (piped/CI); plain input still works.
        console.print("[yellow]No interactive console; plain input mode.[/yellow]")
        _plain_loop(session)
        return
    while True:
        try:
            line = prompt.prompt("benching> ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        line = line.strip()
        if not dispatch(session, line):
            break


def _plain_loop(session: Session) -> None:
    while True:
        try:
            line = input("benching> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if not dispatch(session, line):
            break
