"""benching tokenizer — manage the pinned tokenizer cache.

Thin presentation over the shared tokenizer context
(:func:`benching.benchmark.tokenizer.resolve_tokenizer_context`), the same
resolution the runner uses — so status/prepare and execution agree on the
tokenizer identity for the same effective settings.
"""
from __future__ import annotations

import typer
from rich.console import Console

from benching.benchmark.settings import effective_settings
from benching.benchmark.tokenizer import ensure_tokenizer, resolve_tokenizer_context

app = typer.Typer(help="Manage the tokenizer cache.", no_args_is_help=True)
console = Console()


def _context(model: str | None = None) -> dict:
    """Effective settings + runner-identical tokenizer context."""
    settings = effective_settings(model=model)
    return {
        "settings": settings,
        **resolve_tokenizer_context(settings.root, settings.spec, settings.provider, settings.model),
    }


@app.command("prepare")
def prepare() -> None:
    """Download the pinned tokenizer into the local cache (idempotent)."""
    try:
        context = _context()
    except SystemExit as exc:
        console.print(f"[red]{exc.code or exc}[/red]")
        raise typer.Exit(1) from None
    spec = context["settings"].spec
    console.print(f"Preparing tokenizer [bold]{spec.tokenizer_repo}[/bold] @ {spec.tokenizer_revision[:12]}...")
    try:
        metadata = ensure_tokenizer(spec, context["values"])
    except SystemExit as exc:
        console.print("[red]Tokenizer prepare failed[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Tokenizer ready[/green] at [cyan]{metadata['local_cache']}[/cyan]")


@app.command("status")
def status() -> None:
    """Show whether the pinned tokenizer is cached."""
    try:
        context = _context()
    except SystemExit as exc:
        console.print(f"[red]{exc.code or exc}[/red]")
        raise typer.Exit(1) from None
    metadata = context["metadata"]
    cached = metadata["source"] == "huggingface"
    console.print(f"Repo: [bold]{metadata['repo']}[/bold]")
    console.print(f"Revision: {metadata['revision']}")
    if context["provider"]:
        console.print(f"Provider: [cyan]{context['provider']}[/cyan] · model: {context['api_model']}")
    console.print(f"Cache: [cyan]{metadata['local_cache']}[/cyan]")
    console.print(f"Status: {'[green]cached[/green]' if cached else '[yellow]not cached[/yellow]'} (run `benching tokenizer prepare`)")
