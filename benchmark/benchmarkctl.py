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

ROOT = Path(__file__).resolve().parents[1]
os.environ["PATH"] = str(Path.home() / ".local/bin") + os.pathsep + os.environ.get("PATH", "")
RUNS = ROOT / "runs"
CONFIG = ROOT / "config" / "providers.yaml"
TASKS = Path.home() / "terminal-bench-2-1" / "tasks"
DEFAULT_BENCHMARK = "terminal-bench"
DEFAULT_BENCHMARK_VERSION = "2.1"
DEFAULT_MODEL = "deepseek-v4-flash-0731"
DEFAULT_CONCURRENCY = 1
DEFAULT_TRIALS = 1
PROXY_PORT = 8765


@dataclass(frozen=True)
class RunOptions:
    provider: str
    mode: str
    benchmark: str = DEFAULT_BENCHMARK
    benchmark_version: str = DEFAULT_BENCHMARK_VERSION
    benchmark_model: str = DEFAULT_MODEL
    concurrency: int = DEFAULT_CONCURRENCY
    trials: int = DEFAULT_TRIALS


def utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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


def provider_config(name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    config = load_yaml()
    value = config["providers"].get(name)
    if not isinstance(value, dict) or not value.get("enabled", False):
        raise SystemExit(f"provider is not enabled: {name}")
    return config, value


def resolve(name: str, config: dict[str, Any]) -> tuple[str, str]:
    values = parse_env(ROOT / str(config["env_file"]))
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


def environment(config: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(parse_env(ROOT / str(config["env_file"])))
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PATH"] = str(Path.home() / ".local/bin") + os.pathsep + env.get("PATH", "")
    return env


def fingerprint(run: dict[str, Any]) -> str:
    encoded = json.dumps(run, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_directory(options: RunOptions, config: dict[str, Any], endpoint: str, api_model: str, tasks: list[str]) -> Path:
    RUNS.mkdir(parents=True, exist_ok=True)
    run_id = f"tb21-v1-{options.provider}-{options.mode}-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    directory = RUNS / run_id
    directory.mkdir(parents=False)
    (directory / "harbor").mkdir()
    benchmark_name, benchmark_version, benchmark_model = benchmark_settings(load_yaml())
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
        "proxy_port": PROXY_PORT,
        "tokenizer_path": parse_env(ROOT / str(config["env_file"])).get("DEEPSEEK_V4_TOKENIZER") or os.environ.get("DEEPSEEK_V4_TOKENIZER"),
    }
    run["environment_fingerprint"] = fingerprint(run)
    (directory / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    routes = {options.provider: {"upstream": endpoint, "plan": config.get("plan")}}
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
        "--agent-kwarg", f"provider={options.provider}",
        "--agent-kwarg", f"provider_plan={config.get('plan') or ''}",
        "--agent-kwarg", f"benchmark_model={benchmark_model}",
        "--agent-kwarg", f"model={api_model}",
        "--agent-kwarg", f"upstream={endpoint}",
        "--agent-kwarg", f"api_key_env={config['auth_env']}",
        "--agent-kwarg", f"run_id={directory.name}",
        "--agent-kwarg", f"proxy_url=http://host.docker.internal:{PROXY_PORT}",
        "--agent-kwarg", f"api={config.get('api', 'openai-completions')}",
        "--agent-kwarg", "reasoning=false", "--agent-kwarg", "max_tokens=49152", "--agent-kwarg", "context_window=262144",
    ]
    for task in tasks:
        command.extend(["--include-task-name", task])
    return command


def start_proxy(directory: Path) -> subprocess.Popen[bytes]:
    command = [sys.executable, "-m", "proxy.telemetry_proxy", "--events", str(directory / "raw.jsonl"), "--routes", str(directory / "proxy-routes.json"), "--port", str(PROXY_PORT)]
    stdout = (directory / "proxy.stdout.log").open("wb")
    stderr = (directory / "proxy.stderr.log").open("wb")
    process = subprocess.Popen(command, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)}, stdout=stdout, stderr=stderr, start_new_session=True)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PROXY_PORT), timeout=0.2):
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
    import re
    text = re.sub(r"(?i)(authorization\s*:\s*(?:bearer\s+)?|api[_-]?key\s*[:=]\s*|token\s*[:=]\s*)[^\s,;\"]+", r"\1[REDACTED]", text)
    return text[:limit]


def provider_request_id(headers: Any) -> str | None:
    return headers.get("x-request-id") or headers.get("request-id")


def has_stream_content(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"content", "text", "reasoning_content", "reasoning", "thinking"} and isinstance(item, str) and item:
                return True
            if isinstance(item, (dict, list)) and has_stream_content(item):
                return True
    elif isinstance(value, list):
        return any(has_stream_content(item) for item in value)
    return False


def parse_stream_body(body: bytes) -> tuple[bool, dict[str, Any] | None]:
    first_content = False
    usage: dict[str, Any] | None = None
    for raw in body.decode("utf-8", "replace").splitlines():
        if raw.startswith("data:"):
            payload = raw[5:].strip()
            if payload == "[DONE]":
                continue
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            first_content = first_content or has_stream_content(event)
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
            for choice in event.get("choices", []) if isinstance(event.get("choices"), list) else []:
                if isinstance(choice, dict):
                    delta = choice.get("delta") or {}
                    if isinstance(delta, dict) and delta.get("content"):
                        first_content = True
    return first_content, usage


def validation_request(url: str, key: str, api_model: str) -> dict[str, Any]:
    payload = json.dumps({"model": api_model, "messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 4, "stream": True}).encode()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    started = time.monotonic()
    result: dict[str, Any] = {"url": url, "api_model": api_model, "stream": True, "streaming": False, "first_content": False, "usage": None}
    try:
        with urlopen(Request(url, data=payload, headers=headers), timeout=90) as response:
            body = response.read()
            result.update(status=response.status, duration_ms=round((time.monotonic() - started) * 1000, 3), bytes=len(body), content_type=response.headers.get("content-type"), provider_request_id=provider_request_id(response.headers))
            result["streaming"] = "text/event-stream" in (response.headers.get("content-type", "").lower())
            result["first_content"], result["usage"] = parse_stream_body(body)
    except HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        result.update(status=error.code, duration_ms=round((time.monotonic() - started) * 1000, 3), provider_request_id=provider_request_id(error.headers), error_body=sanitized(body))
    except (URLError, TimeoutError, OSError) as error:
        result.update(status=None, duration_ms=round((time.monotonic() - started) * 1000, 3), error_type=type(getattr(error, "reason", error)).__name__, error_body=sanitized(str(error)))
    return result


def validate_provider(name: str) -> Path:
    root_config, config = provider_config(name)
    endpoint, api_model = resolve(name, config)
    key = parse_env(ROOT / str(config["env_file"])).get(str(config["auth_env"]))
    if not key:
        raise SystemExit(f"missing credential: {config['auth_env']}")
    result: dict[str, Any] = {"schema_version": 1, "provider": name, "provider_plan": config.get("plan"), "benchmark_model": benchmark_settings(root_config)[2], "api_model": api_model, "base_url": endpoint, "models": None}
    if name == "electronhub":
        try:
            with urlopen(Request(endpoint + "/models", headers={"Authorization": f"Bearer {key}"}), timeout=30) as response:
                catalog = json.loads(response.read())
                ids = [item.get("id") for item in catalog.get("data", []) if isinstance(item, dict) and item.get("id")] if isinstance(catalog, dict) else []
                result["models"] = {"status": response.status, "count": len(ids), "api_model_present": api_model in ids}
                if api_model not in ids:
                    raise SystemExit(f"ElectronHub api_model not present in /models: {api_model}")
        except HTTPError as error:
            result["models"] = {"status": error.code, "error_body": sanitized(error.read().decode("utf-8", "replace"))}
            raise SystemExit(json.dumps(result, indent=2))
    else:
        try:
            with urlopen(Request(endpoint + "/models", headers={"Authorization": f"Bearer {key}"}), timeout=30) as response:
                catalog = json.loads(response.read())
                result["models"] = {"status": response.status, "catalog_count": len(catalog.get("data", [])) if isinstance(catalog, dict) and isinstance(catalog.get("data"), list) else None}
        except Exception as error:
            result["models"] = {"status": None, "error_body": sanitized(str(error))}
    result["chat_completions"] = validation_request(endpoint + "/chat/completions", key, api_model)
    result["success"] = result["chat_completions"].get("status") == 200 and result["chat_completions"].get("streaming") and result["chat_completions"].get("first_content")
    output = RUNS / f"validation-{name}-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    os.chmod(output, 0o600)
    print(json.dumps(result, indent=2))
    if not result["success"]:
        raise SystemExit(f"provider validation failed; see {output}")
    return output


def run_one(options: RunOptions) -> Path:
    executable("docker")
    root_config, config = provider_config(options.provider)
    benchmark_name, benchmark_version, benchmark_model = benchmark_settings(root_config)
    if (options.benchmark, options.benchmark_version, options.benchmark_model) != (benchmark_name, benchmark_version, benchmark_model):
        raise SystemExit("benchmark configuration does not match providers.yaml")
    endpoint, api_model = resolve(options.provider, config)
    validate_provider(options.provider)
    tasks = task_names(options.mode)
    directory = run_directory(options, config, endpoint, api_model, tasks)
    (directory / "docker-host-gateway.yaml").write_text("services:\n  main:\n    extra_hosts:\n      - host.docker.internal:host-gateway\n", encoding="utf-8")
    command = harbor_command(options, config, endpoint, api_model, benchmark_model, directory, tasks)
    (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n", encoding="utf-8")
    env = environment(config)
    proxy: subprocess.Popen[bytes] | None = None
    try:
        proxy = start_proxy(directory)
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


def compare(providers: list[str], mode: str, model: str, concurrency: int, trials: int) -> None:
    directories = [run_one(RunOptions(provider=provider, mode=mode, benchmark_model=model, concurrency=concurrency, trials=trials)) for provider in providers]
    subprocess.run([sys.executable, str(ROOT / "analytics" / "analyze.py"), *(str(path) for path in directories)], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for mode in ("smoke", "full"):
        command = commands.add_parser(mode)
        command.add_argument("--provider", required=True, choices=("kourier", "electronhub"))
        command.add_argument("--model", default=DEFAULT_MODEL, dest="benchmark_model")
        command.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
        command.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("--providers", default="kourier,electronhub")
    compare_parser.add_argument("--mode", choices=("smoke", "full"), default="full")
    compare_parser.add_argument("--model", default=DEFAULT_MODEL, dest="benchmark_model")
    compare_parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    compare_parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    validate = commands.add_parser("validate")
    validate.add_argument("--provider", required=True, choices=("kourier", "electronhub"))
    args = parser.parse_args()
    if args.command in {"smoke", "full"}:
        run_one(RunOptions(provider=args.provider, mode=args.command, benchmark_model=args.benchmark_model, concurrency=args.concurrency, trials=args.trials))
    elif args.command == "compare":
        providers = [value.strip() for value in args.providers.split(",") if value.strip()]
        if sorted(providers) != ["electronhub", "kourier"]:
            raise SystemExit("V1 compare requires exactly kourier,electronhub")
        compare(providers, args.mode, args.benchmark_model, args.concurrency, args.trials)
    else:
        validate_provider(args.provider)


if __name__ == "__main__":
    main()
