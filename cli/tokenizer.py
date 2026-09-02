"""benching tokenizer — manage the pinned tokenizer cache."""
from __future__ import annotations

import typer
from rich.console import Console

from benchmark.config import all_provider_env_values, benchmark_spec, load_yaml
from benchmark.tokenizer import ensure_tokenizer, tokenizer_metadata

app = typer.Typer(help="Manage the tokenizer cache.", no_args_is_help=True)
console = Console()


@app.command("prepare")
def prepare() -> None:
    """Download the pinned tokenizer into the local cache (idempotent)."""
    root = load_yaml()
    spec = benchmark_spec(root)
    console.print(f"Preparing tokenizer [bold]{spec.tokenizer_repo}[/bold] @ {spec.tokenizer_revision[:12]}...")
    try:
        metadata = ensure_tokenizer(spec, all_provider_env_values(root))
    except SystemExit as exc:
        console.print("[red]Tokenizer prepare failed[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Tokenizer ready[/green] at [cyan]{metadata['local_cache']}[/cyan]")


@app.command("status")
def status() -> None:
    """Show whether the pinned tokenizer is cached."""
    root = load_yaml()
    spec = benchmark_spec(root)
    metadata = tokenizer_metadata(spec, all_provider_env_values(root))
    cached = metadata["source"] == "huggingface"
    console.print(f"Repo: [bold]{metadata['repo']}[/bold]")
    console.print(f"Revision: {metadata['revision']}")
    console.print(f"Cache: [cyan]{metadata['local_cache']}[/cyan]")
    console.print(f"Status: {'[green]cached[/green]' if cached else '[yellow]not cached[/yellow]'} (run `benching tokenizer prepare`)")
