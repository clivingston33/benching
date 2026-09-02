"""benching — benchmark LLM API providers against terminal-agent task suites.

Command groups (each a module under cli/):

  doctor      environment health checks
  config      inspect the active configuration
  provider    list / validate / probe providers
  run         execute a benchmark run for one provider
  compare     run and compare two or more providers
  runs        inspect past runs
  results     read run results
  tokenizer   manage the pinned tokenizer cache

CLI modules stay thin: they parse arguments, call the benchmark layer under
``benchmark/``, and render output. Benchmark logic lives in the layer so a
dashboard can import the exact same functions.
"""
from __future__ import annotations

import typer

app = typer.Typer(
    name="benching",
    help="Benchmark LLM providers against terminal-agent task suites.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _register() -> None:
    from cli import config as config_group
    from cli import providers as providers_group

    app.add_typer(config_group.app, name="config")
    app.add_typer(providers_group.app, name="provider")

    from cli import compare as compare_group
    from cli import run as run_group

    app.command()(run_group.run)
    app.command()(compare_group.compare)


_register()


def main() -> None:
    """Console entry point."""
    app()


if __name__ == "__main__":
    main()
