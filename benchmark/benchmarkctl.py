#!/usr/bin/env python3
"""Legacy benchmarkctl CLI. Superseded by the benching console script."""
from __future__ import annotations

import json
import sys

from benchmark._paths import DEFAULT_CONCURRENCY, DEFAULT_TRIALS, PROXY_PORT
from benchmark.config import (
    all_provider_env_values,
    benchmark_spec,
    enabled_providers,
    load_yaml,
    resolve,
)
from benchmark.concurrency import probe_provider
from benchmark.runner import RunOptions, analyze_runs, compare, run_one
from benchmark.tokenizer import ensure_tokenizer
from benchmark.validation import validate_provider, write_validation_report


def main() -> None:
    import argparse

    root_config = load_yaml()
    spec = benchmark_spec(root_config)
    providers = enabled_providers(root_config)
    default_model = spec.model
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    default_reasoning = spec.reasoning
    for mode in ("smoke", "full"):
        command = commands.add_parser(mode)
        command.add_argument("--provider", required=True, choices=providers or None)
        command.add_argument("--model", default=default_model, dest="benchmark_model")
        command.add_argument("--reasoning", choices=("default", "enabled", "disabled"), default=default_reasoning)
        command.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
        command.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("--providers", default=",".join(providers))
    compare_parser.add_argument("--mode", choices=("smoke", "full"), default="full")
    compare_parser.add_argument("--model", default=default_model, dest="benchmark_model")
    compare_parser.add_argument("--reasoning", choices=("default", "enabled", "disabled"), default=default_reasoning)
    compare_parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    compare_parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    execution_group = compare_parser.add_mutually_exclusive_group()
    execution_group.add_argument("--execution", choices=("sequential", "parallel"), default="sequential", help="how provider benchmark runs are scheduled (default: sequential)")
    execution_group.add_argument("--parallel-providers", action="store_true", dest="parallel_alias", help="alias for --execution parallel (informal testing only)")
    validate = commands.add_parser("validate")
    validate.add_argument("--provider", required=True, choices=providers or None)
    probe_parser = commands.add_parser("probe-concurrency")
    probe_parser.add_argument("--provider", required=True, choices=providers or None)
    probe_parser.add_argument("--stages", default="2,3,5,6", help="comma-separated concurrency levels to probe")
    commands.add_parser("prepare-tokenizer")
    args = parser.parse_args()
    if args.command == "prepare-tokenizer":
        print(json.dumps(ensure_tokenizer(spec, all_provider_env_values(root_config)), indent=2))
        return
    if not providers:
        raise SystemExit("no enabled providers; add a provider entry (with env_file and auth_env) to config/benchmark.yaml")
    if args.command in {"smoke", "full"}:
        run_one(RunOptions(provider=args.provider, mode=args.command, benchmark_model=args.benchmark_model, reasoning=args.reasoning, concurrency=args.concurrency, trials=args.trials), root_config)
    elif args.command == "compare":
        requested = [value.strip() for value in args.providers.split(",") if value.strip()]
        if not requested:
            raise SystemExit("compare requires at least one provider")
        unknown = [name for name in requested if name not in providers]
        if unknown:
            raise SystemExit(f"unknown provider(s): {', '.join(unknown)}")
        execution = "parallel" if getattr(args, "parallel_alias", False) else args.execution
        directories = compare(requested, args.mode, args.benchmark_model, args.concurrency, args.trials, root_config, execution=execution, reasoning=args.reasoning)
        analyze_runs(directories, execution=execution)
    elif args.command == "probe-concurrency":
        summary_path, jsonl_path = probe_provider(args.provider, spec, root_config, stages=tuple(int(value.strip()) for value in args.stages.split(",") if value.strip()))
        print(json.dumps({"summary": str(summary_path), "requests": str(jsonl_path)}, indent=2))
    else:
        result = validate_provider(args.provider, spec, root_config)
        output = write_validation_report(args.provider, result)
        print(json.dumps(result, indent=2))
        if not result["success"]:
            raise SystemExit(f"provider validation failed; see {output}")


if __name__ == "__main__":
    main()
