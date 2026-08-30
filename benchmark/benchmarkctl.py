#!/usr/bin/env python3
"""Single supported Terminal-Bench 2.1 runner for provider comparisons."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from benchmark._util import redact, stream_summary, utc

ROOT = Path(__file__).resolve().parents[1]
os.environ["PATH"] = str(Path.home() / ".local/bin") + os.pathsep + os.environ.get("PATH", "")
RUNS = ROOT / "runs"
CONFIG = ROOT / "config" / "providers.yaml"
TASKS = Path.home() / "terminal-bench-2-1" / "tasks"
DEFAULT_BENCHMARK = "terminal-bench"
DEFAULT_BENCHMARK_VERSION = "2.1"
DEFAULT_MODEL = "deepseek-v4-flash-0731"
DEFAULT_CONCURRENCY = 3
DEFAULT_TRIALS = 1
PROXY_PORT = 8765
TOKENIZER_REPO = "deepseek-ai/DeepSeek-V4-Flash-0731"
TOKENIZER_REVISION = "7872f01b1d1fe23eabc4c98b48bffcef5a386062"
TOKENIZER_CACHE = Path.home() / ".cache" / "provider-benchmark" / "deepseek-v4-flash-0731"


@dataclass(frozen=True)
class RunOptions:
    provider: str
    mode: str
    benchmark: str = DEFAULT_BENCHMARK
    benchmark_version: str = DEFAULT_BENCHMARK_VERSION
    benchmark_model: str = DEFAULT_MODEL
    concurrency: int = DEFAULT_CONCURRENCY
    trials: int = DEFAULT_TRIALS
    proxy_port: int = PROXY_PORT



def load_yaml() -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML is required; install the project dependencies first") from exc
    value = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("providers"), dict):
        raise SystemExit("invalid providers.yaml")
    return value


def benchmark_settings(config: dict[str, Any]) -> tuple[str, str, str]:
    settings = config.get("benchmark") if isinstance(config.get("benchmark"), dict) else {}
    return (
        str(settings.get("name", DEFAULT_BENCHMARK)),
        str(settings.get("version", DEFAULT_BENCHMARK_VERSION)),
        str(settings.get("model", DEFAULT_MODEL)),
    )


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def provider_config(name: str, root_config: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    config = root_config or load_yaml()
    value = config["providers"].get(name)
    if not isinstance(value, dict) or not value.get("enabled", False):
        raise SystemExit(f"provider is not enabled: {name}")
    return config, value


def resolve(name: str, config: dict[str, Any], values: dict[str, str] | None = None) -> tuple[str, str]:
    values = values if values is not None else parse_env(ROOT / str(config["env_file"]))
    prefix = name.upper().replace("-", "_")
    endpoint = values.get(f"{prefix}_BASE_URL") or config.get("base_url") or config.get("endpoint")
    api_model = values.get(f"{prefix}_API_MODEL") or config.get("api_model")
    if not isinstance(endpoint, str) or not endpoint:
        raise SystemExit(f"endpoint unresolved for {name}")
    if not isinstance(api_model, str) or not api_model:
        raise SystemExit(f"api_model unresolved for {name}")
    return endpoint.rstrip("/"), api_model


def task_names(mode: str) -> list[str]:
    if mode == "smoke":
        return ["break-filter-js-from-html", "cancel-async-tasks", "adaptive-rejection-sampler"]
    if mode != "full":
        raise SystemExit(f"unsupported mode: {mode}")
    tasks = sorted(path.name for path in TASKS.iterdir() if path.is_dir())
    if len(tasks) != 89:
        raise SystemExit(f"expected 89 Terminal-Bench 2.1 tasks, found {len(tasks)}")
    return tasks


def executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"required executable not found: {name}")
    return path


def environment(config: dict[str, Any], values: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(values if values is not None else parse_env(ROOT / str(config["env_file"])))
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PATH"] = str(Path.home() / ".local/bin") + os.pathsep + env.get("PATH", "")
    return env


def tokenizer_metadata(config: dict[str, Any], values: dict[str, str] | None = None) -> dict[str, Any]:
    values = values if values is not None else parse_env(ROOT / str(config["env_file"]))
    env_path = values.get("DEEPSEEK_V4_TOKENIZER")
    local_cache = Path(env_path).expanduser() if env_path else TOKENIZER_CACHE
    available = (local_cache / "tokenizer.json").is_file() and (local_cache / "config.json").is_file() if local_cache.is_dir() else local_cache.is_file()
    return {
        "repo": TOKENIZER_REPO,
        "revision": TOKENIZER_REVISION,
        "source": "huggingface" if available else "unavailable",
        "local_cache": str(local_cache),
    }


def ensure_tokenizer(config: dict[str, Any], values: dict[str, str] | None = None) -> dict[str, Any]:
    metadata = tokenizer_metadata(config, values)
    if metadata["source"] == "huggingface":
        return metadata
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id=TOKENIZER_REPO,
            revision=TOKENIZER_REVISION,
            local_dir=metadata["local_cache"],
            allow_patterns=["tokenizer.json", "tokenizer_config.json", "config.json"],
        )
    except Exception as exc:
        raise SystemExit(f"official tokenizer unavailable: {exc}") from exc
    metadata = tokenizer_metadata(config, values)
    if metadata["source"] != "huggingface":
        raise SystemExit("official tokenizer download completed without tokenizer.json")
    return metadata


def tokenizer_cache_path(metadata: dict[str, Any]) -> str | None:
    path = metadata.get("local_cache")
    return str(path) if isinstance(path, str) and path else None


def fingerprint(run: dict[str, Any]) -> str:
    encoded = json.dumps(run, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_directory(
    options: RunOptions,
    config: dict[str, Any],
    endpoint: str,
    api_model: str,
    tasks: list[str],
    root_config: dict[str, Any] | None = None,
    env_values: dict[str, str] | None = None,
) -> Path:
    RUNS.mkdir(parents=True, exist_ok=True)
    run_id = f"tb21-v1-{options.provider}-{options.mode}-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    directory = RUNS / run_id
    directory.mkdir(parents=False)
    (directory / "harbor").mkdir()
    benchmark_name, benchmark_version, benchmark_model = benchmark_settings(root_config or load_yaml())
    run = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at_utc": utc(),
        "benchmark": benchmark_name,
        "benchmark_version": benchmark_version,
        "benchmark_model": benchmark_model,
        "task_count": len(tasks),
        "tasks": tasks,
        "agent": "agents.instrumented_omp_agent:InstrumentedOmpAgent",
        "provider": options.provider,
        "provider_plan": config.get("plan"),
        "provider_plan_tier": config.get("plan_tier", "unknown"),
        "endpoint": endpoint,
        "api_model": api_model,
        "reasoning": False,
        "streaming": True,
        "concurrency": options.concurrency,
        "trials": options.trials,
        "automatic_provider_retries": 0,
        "task_attempts": options.trials,
        "harbor_version": version("harbor"),
        "omp_version": version("omp"),
        "python_version": platform.python_version(),
        "os": platform.platform(),
        "kernel": platform.release(),
        "cpu": platform.processor(),
        "proxy_schema_version": 1,
        "proxy_port": options.proxy_port,
        "tokenizer": tokenizer_metadata(config, env_values),
    }
    run["environment_fingerprint"] = fingerprint(run)
    (directory / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    routes = {options.provider: {"upstream": endpoint, "plan": config.get("plan"), "plan_tier": config.get("plan_tier", "unknown")}}
    (directory / "proxy-routes.json").write_text(json.dumps(routes, indent=2) + "\n", encoding="utf-8")
    (directory / "status.json").write_text(json.dumps({"status": "created", "updated_at_utc": utc()}, indent=2) + "\n", encoding="utf-8")
    return directory


def version(name: str) -> str | None:
    path = shutil.which(name)
    if path is None:
        return None
    try:
        completed = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (completed.stdout or completed.stderr).strip()
    return text[:256] or None


def harbor_command(options: RunOptions, config: dict[str, Any], endpoint: str, api_model: str, benchmark_model: str, directory: Path, tasks: list[str]) -> list[str]:
    command = [
        executable("harbor"), "run", "--path", str(TASKS),
        "--agent", "agents.instrumented_omp_agent:InstrumentedOmpAgent",
        "--model", f"{options.provider}/{api_model}",
        "--jobs-dir", str(directory / "harbor"), "--job-name", directory.name,
        "--n-attempts", str(options.trials), "--n-concurrent", str(options.concurrency),
        "--n-concurrent-agents", str(options.concurrency), "--max-retries", "0",
        "--agent-include-logs", "**/*",
        "--mounts", json.dumps([{"type": "bind", "source": str(ROOT / "cache"), "target": "/opt/provider-benchmark", "read_only": True}]),
        "--extra-docker-compose", str(directory / "docker-host-gateway.yaml"),
    ]
    agent_kwargs = {
        "provider": options.provider,
        "provider_plan": config.get("plan") or "",
        "benchmark_model": benchmark_model,
        "model": api_model,
        "upstream": endpoint,
        "api_key_env": config["auth_env"],
        "run_id": directory.name,
        "proxy_url": f"http://host.docker.internal:{options.proxy_port}",
        "api": config.get("api", "openai-completions"),
        "reasoning": "false",
        "max_tokens": "49152",
        "context_window": "262144",
    }
    for key, value in agent_kwargs.items():
        command.extend(["--agent-kwarg", f"{key}={value}"])
    for task in tasks:
        command.extend(["--include-task-name", task])
    return command


def start_proxy(directory: Path, port: int = PROXY_PORT) -> subprocess.Popen[bytes]:
    command = [sys.executable, "-m", "proxy.telemetry_proxy", "--events", str(directory / "raw.jsonl"), "--routes", str(directory / "proxy-routes.json"), "--port", str(port)]
    stdout = (directory / "proxy.stdout.log").open("wb")
    stderr = (directory / "proxy.stderr.log").open("wb")
    process = subprocess.Popen(command, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)}, stdout=stdout, stderr=stderr, start_new_session=True)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                stdout.close(); stderr.close()
                return process
        except OSError:
            if process.poll() is not None:
                raise SystemExit(f"proxy failed to start; see {directory / 'proxy.stderr.log'}")
            time.sleep(0.1)
    stop_process(process)
    raise SystemExit("proxy did not become ready within 10 seconds")


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def set_status(directory: Path, status: str, **extra: Any) -> None:
    (directory / "status.json").write_text(json.dumps({"status": status, "updated_at_utc": utc(), **extra}, indent=2) + "\n", encoding="utf-8")


def sanitized(text: str, limit: int = 4096) -> str:
    return redact(text, limit) or ""


def provider_request_id(headers: Any) -> str | None:
    return headers.get("x-request-id") or headers.get("request-id")


def parse_stream_body(body: bytes) -> tuple[bool, dict[str, Any] | None]:
    first_content, _, usage = stream_summary(body)
    return first_content, usage


def validation_request(url: str, key: str, api_model: str) -> dict[str, Any]:
    payload = json.dumps({"model": api_model, "messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 4, "stream": True}).encode()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "text/event-stream", "User-Agent": "provider-benchmark/1.0"}
    started = time.monotonic()
    result: dict[str, Any] = {"url": url, "api_model": api_model, "stream": True, "user_agent": "provider-benchmark/1.0", "streaming": False, "first_content": False, "usage": None}
    try:
        with urlopen(Request(url, data=payload, headers=headers), timeout=90) as response:
            body = response.read()
            result.update(status=response.status, duration_ms=round((time.monotonic() - started) * 1000, 3), bytes=len(body), content_type=response.headers.get("content-type"), provider_request_id=provider_request_id(response.headers), server=response.headers.get("server"), cf_ray=response.headers.get("cf-ray"), via=response.headers.get("via"), http_version="unknown")
            result["streaming"] = "text/event-stream" in (response.headers.get("content-type", "").lower())
            result["first_content"], result["usage"] = parse_stream_body(body)
    except HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        result.update(status=error.code, duration_ms=round((time.monotonic() - started) * 1000, 3), provider_request_id=provider_request_id(error.headers), server=error.headers.get("server"), cf_ray=error.headers.get("cf-ray"), via=error.headers.get("via"), http_version="unknown", error_body=sanitized(body))
    except (URLError, TimeoutError, OSError) as error:
        result.update(status=None, duration_ms=round((time.monotonic() - started) * 1000, 3), error_type=type(getattr(error, "reason", error)).__name__, error_body=sanitized(str(error)))
    return result


def classify_validation(result: dict[str, Any]) -> str:
    status = result.get("status")
    if status in {401, 403}:
        if result.get("cf_ray") or str(result.get("server", "")).lower() == "cloudflare":
            return "edge_access_denied"
        return "authentication_failure"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    if status is None:
        return "network_failure"
    if isinstance(status, int) and status >= 500:
        return "provider_internal_error"
    return "provider_response"


def validate_provider(
    name: str,
    root_config: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    env_values: dict[str, str] | None = None,
) -> Path:
    if config is None:
        root_config, config = provider_config(name, root_config)
    assert root_config is not None
    env_values = env_values if env_values is not None else parse_env(ROOT / str(config["env_file"]))
    endpoint, api_model = resolve(name, config, env_values)
    key = env_values.get(str(config["auth_env"]))
    if not key:
        raise SystemExit(f"missing credential: {config['auth_env']}")
    result: dict[str, Any] = {"schema_version": 1, "provider": name, "provider_plan": config.get("plan"), "benchmark_model": benchmark_settings(root_config)[2], "api_model": api_model, "base_url": endpoint, "models": None}
    if config.get("strict_model_check"):
        try:
            with urlopen(Request(endpoint + "/models", headers={"Authorization": f"Bearer {key}"}), timeout=30) as response:
                catalog = json.loads(response.read())
                ids = [item.get("id") for item in catalog.get("data", []) if isinstance(item, dict) and item.get("id")] if isinstance(catalog, dict) else []
                result["models"] = {"status": response.status, "count": len(ids), "api_model_present": api_model in ids}
                if api_model not in ids:
                    raise SystemExit(f"{name} api_model not present in /models: {api_model}")
        except HTTPError as error:
            result["models"] = {"status": error.code, "error_body": sanitized(error.read().decode("utf-8", "replace"))}
            raise SystemExit(json.dumps(result, indent=2))
    else:
        try:
            with urlopen(Request(endpoint + "/models", headers={"Authorization": f"Bearer {key}"}), timeout=30) as response:
                catalog = json.loads(response.read())
                result["models"] = {"status": response.status, "catalog_count": len(catalog.get("data", [])) if isinstance(catalog, dict) and isinstance(catalog.get("data"), list) else None}
        except HTTPError as error:
            result["models"] = {"status": error.code, "error_body": sanitized(error.read().decode("utf-8", "replace")), "server": error.headers.get("server"), "cf_ray": error.headers.get("cf-ray")}
        except Exception as error:
            result["models"] = {"status": None, "error_body": sanitized(str(error))}
    result["chat_completions"] = validation_request(endpoint + "/chat/completions", key, api_model)
    result["error_class"] = classify_validation(result["chat_completions"])
    result["models_error_class"] = classify_validation(result["models"]) if isinstance(result.get("models"), dict) and result["models"].get("status") is not None else None
    result["success"] = result["chat_completions"].get("status") == 200 and result["chat_completions"].get("streaming") and result["chat_completions"].get("first_content")
    output = RUNS / f"validation-{name}-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    os.chmod(output, 0o600)
    print(json.dumps(result, indent=2))
    if not result["success"]:
        raise SystemExit(f"provider validation failed; see {output}")
    return output


def run_one(options: RunOptions, root_config: dict[str, Any] | None = None) -> Path:
    executable("docker")
    root_config, config = provider_config(options.provider, root_config)
    values = parse_env(ROOT / str(config["env_file"]))
    benchmark_name, benchmark_version, benchmark_model = benchmark_settings(root_config)
    if (options.benchmark, options.benchmark_version, options.benchmark_model) != (benchmark_name, benchmark_version, benchmark_model):
        raise SystemExit("benchmark configuration does not match providers.yaml")
    endpoint, api_model = resolve(options.provider, config, values)
    tokenizer = tokenizer_metadata(config, values)
    if tokenizer["source"] != "huggingface":
        raise SystemExit("official tokenizer is not cached; run benchmarkctl prepare-tokenizer")
    validate_provider(options.provider, root_config, config, values)
    tasks = task_names(options.mode)
    directory = run_directory(options, config, endpoint, api_model, tasks, root_config, values)
    (directory / "docker-host-gateway.yaml").write_text("services:\n  main:\n    extra_hosts:\n      - host.docker.internal:host-gateway\n", encoding="utf-8")
    command = harbor_command(options, config, endpoint, api_model, benchmark_model, directory, tasks)
    (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n", encoding="utf-8")
    env = environment(config, values)
    proxy: subprocess.Popen[bytes] | None = None
    try:
        proxy = start_proxy(directory, options.proxy_port)
        set_status(directory, "running", pid=None)
        with (directory / "harbor.stdout.log").open("wb") as stdout, (directory / "harbor.stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
        (directory / "pid").write_text(str(process.pid) + "\n", encoding="utf-8")
        set_status(directory, "running", pid=process.pid)
        return_code = process.wait()
        set_status(directory, "completed" if return_code == 0 else "failed", pid=process.pid, return_code=return_code)
        if return_code != 0:
            raise SystemExit(return_code)
        subprocess.run([sys.executable, str(ROOT / "analytics" / "analyze.py"), str(directory)], cwd=ROOT, check=True)
        return directory
    except KeyboardInterrupt:
        set_status(directory, "interrupted")
        raise
    finally:
        stop_process(proxy)

def probe_concurrency(name: str, root_config: dict[str, Any] | None = None, stages: tuple[int, ...] = (2, 3, 5, 6)) -> None:
    root_config, config = provider_config(name, root_config)
    values = parse_env(ROOT / str(config["env_file"]))
    endpoint, api_model = resolve(name, config, values)
    validate_provider(name, root_config, config, values)
    key = values.get(str(config["auth_env"]))
    if not key:
        raise SystemExit(f"missing credential: {config['auth_env']}")
    summary_path, jsonl_path = run_probe(name, config, endpoint, api_model, key, RUNS, stages)
    print(json.dumps({"summary": str(summary_path), "requests": str(jsonl_path)}, indent=2))


def compare(providers: list[str], mode: str, model: str, concurrency: int, trials: int, root_config: dict[str, Any] | None = None) -> None:
    import concurrent.futures
    root_config = root_config or load_yaml()
    base_port = PROXY_PORT
    directories: list[Path] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers), thread_name_prefix="compare") as pool:
        futures = {
            pool.submit(run_one, RunOptions(provider=provider, mode=mode, benchmark_model=model, concurrency=concurrency, trials=trials, proxy_port=base_port + index), root_config): index
            for index, provider in enumerate(providers)
        }
        for future in concurrent.futures.as_completed(futures):
            directories.append(future.result())
    directories.sort(key=lambda d: d.name)
    subprocess.run([sys.executable, str(ROOT / "analytics" / "analyze.py"), *(str(path) for path in directories)], cwd=ROOT, check=True)


def main() -> None:
    root_config = load_yaml()
    providers = [name for name, cfg in root_config.get("providers", {}).items() if isinstance(cfg, dict) and cfg.get("enabled")]
    if not providers:
        raise SystemExit("no enabled providers in config/providers.yaml")
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for mode in ("smoke", "full"):
        command = commands.add_parser(mode)
        command.add_argument("--provider", required=True, choices=providers)
        command.add_argument("--model", default=DEFAULT_MODEL, dest="benchmark_model")
        command.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
        command.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("--providers", default=",".join(providers))
    compare_parser.add_argument("--mode", choices=("smoke", "full"), default="full")
    compare_parser.add_argument("--model", default=DEFAULT_MODEL, dest="benchmark_model")
    compare_parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    compare_parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    validate = commands.add_parser("validate")
    validate.add_argument("--provider", required=True, choices=providers)
    probe_parser = commands.add_parser("probe-concurrency")
    probe_parser.add_argument("--provider", required=True, choices=providers)
    probe_parser.add_argument("--stages", default="2,3,5,6", help="comma-separated concurrency levels to probe")
    commands.add_parser("prepare-tokenizer")
    args = parser.parse_args()
    if args.command in {"smoke", "full"}:
        run_one(RunOptions(provider=args.provider, mode=args.command, benchmark_model=args.benchmark_model, concurrency=args.concurrency, trials=args.trials), root_config)
    elif args.command == "compare":
        requested = [value.strip() for value in args.providers.split(",") if value.strip()]
        if not requested:
            raise SystemExit("compare requires at least one provider")
        unknown = [name for name in requested if name not in providers]
        if unknown:
            raise SystemExit(f"unknown provider(s): {', '.join(unknown)}")
        compare(requested, args.mode, args.benchmark_model, args.concurrency, args.trials, root_config)
    elif args.command == "probe-concurrency":
        probe_concurrency(args.provider, root_config, stages=tuple(int(value.strip()) for value in args.stages.split(",") if value.strip()))
    elif args.command == "prepare-tokenizer":
        _, config = provider_config(providers[0], root_config)
        values = parse_env(ROOT / str(config["env_file"]))
        print(json.dumps(ensure_tokenizer(config, values), indent=2))
    else:
        validate_provider(args.provider, root_config)

if __name__ == "__main__":
    main()
