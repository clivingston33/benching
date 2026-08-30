"""Harbor agent that runs OMP through the canonical benchmark proxy."""
from __future__ import annotations

import base64
import json
import os
import shlex
import uuid
from pathlib import Path
from typing import Any, override

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class InstrumentedOmpAgent(BaseInstalledAgent):
    _OUTPUT_FILENAME = "omp.jsonl"
    SUPPORTS_RESUME = False

    def __init__(self, logs_dir: Path, provider: str, model: str, benchmark_model: str, upstream: str, api_key_env: str, run_id: str, proxy_url: str, provider_plan: str = "", api: str = "openai-completions", reasoning: str | bool = False, max_tokens: int | str = 49152, context_window: int | str = 262144, omp_version: str = "17.1.3", **kwargs: object) -> None:
        key = os.environ.get(api_key_env)
        if not key:
            raise ValueError(f"required credential {api_key_env} is absent")
        extra_env = dict(kwargs.pop("extra_env", {}) or {})
        extra_env[api_key_env] = key
        super().__init__(logs_dir, extra_env=extra_env, **kwargs)
        self.provider = provider
        self.provider_plan = provider_plan
        self.benchmark_model = benchmark_model
        self.model = model
        self.upstream = upstream.rstrip("/")
        self.api_key_env = api_key_env
        self.run_id = run_id
        self.proxy_url = proxy_url.rstrip("/")
        self.api = api
        self.reasoning = str(reasoning).lower() in {"1", "true", "yes", "on"}
        self.reasoning_mode = str(reasoning).lower()
        self.max_tokens = int(max_tokens)
        self.context_window = int(context_window)
        self.omp_version = omp_version

    @staticmethod
    @override
    def name() -> str:
        return "instrumented-omp"

    @override
    def get_version_command(self) -> str | None:
        return "omp --version"

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        cached = f"/opt/provider-benchmark/omp-{self.omp_version}"
        await self.exec_as_root(environment, "set -euo pipefail; if [ -x " + shlex.quote(cached) + " ]; then install -m 755 " + shlex.quote(cached) + " /usr/local/bin/omp; else apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y curl ca-certificates; curl -fsSL https://raw.githubusercontent.com/can1357/oh-my-pi/main/scripts/install.sh | sh -s -- --binary --ref v" + shlex.quote(self.omp_version) + "; install -m 755 /root/.local/bin/omp /usr/local/bin/omp; fi; omp --version")
        await self.exec_as_agent(environment, "set -euo pipefail; mkdir -p $HOME/.omp/agent; omp --version")

    @staticmethod
    def _metadata_value(metadata: dict[str, Any], names: set[str]) -> str | None:
        stack: list[Any] = [metadata]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                for key, item in value.items():
                    if str(key).lower() in names and item is not None:
                        return str(item)
                    if isinstance(item, (dict, list)):
                        stack.append(item)
            elif isinstance(value, list):
                stack.extend(value)
        return None

    @override
    @with_prompt_template
    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        metadata = context.metadata or {}
        session_id = str(getattr(self, "session_id", "") or "")
        session_task = session_id.split("__", 1)[0] if session_id else "unknown"
        task_id = self._metadata_value(metadata, {"task_id", "task_name", "task"}) or session_task
        trial_id = self._metadata_value(metadata, {"trial_id", "trial_name", "trial"}) or session_id or str(getattr(self, "context_id", "unknown"))
        invocation_id = uuid.uuid4().hex
        model: dict[str, Any] = {"id": self.model, "name": self.model, "api": self.api, "input": ["text"], "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, "contextWindow": self.context_window, "maxTokens": self.max_tokens}
        if self.reasoning_mode == "enabled":
            model["reasoning"] = True
        elif self.reasoning_mode == "disabled":
            model["reasoning"] = False
        config = {"providers": {self.provider: {"baseUrl": f"{self.proxy_url}/{self.provider}", "apiKey": f"!printenv {self.api_key_env}", "api": self.api, "headers": headers, "models": [model]}}}
        config_json = shlex.quote(json.dumps(config, separators=(",", ":")))
        prompt_b64 = shlex.quote(base64.b64encode(instruction.encode("utf-8")).decode("ascii"))
        command = "set -euo pipefail; mkdir -p $HOME/.omp/agent /logs/agent/omp/sessions; " + f"printf '%s' {config_json} > $HOME/.omp/agent/models.json; " + f"printf '%s' {prompt_b64} | base64 -d > /tmp/omp-prompt.txt; " + f"omp --print --mode json --model {shlex.quote(self.provider + '/' + self.model)} --auto-approve --no-prewalk --no-extensions --session-dir /logs/agent/omp/sessions @/tmp/omp-prompt.txt > /logs/agent/{self._OUTPUT_FILENAME} 2> /logs/agent/omp.stderr"
        await self.exec_as_agent(environment, command=command)

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        output = self.logs_dir / self._OUTPUT_FILENAME
        if not output.exists():
            return
        entries: list[tuple[str | None, dict[str, object]]] = []
        for line in output.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    continue
                message = event.get("message")
                usage = message.get("usage") if isinstance(message, dict) else event.get("usage")
                if isinstance(usage, dict):
                    entries.append((event.get("type"), usage))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        if any(kind == "message_end" for kind, _ in entries):
            entries = [(kind, usage) for kind, usage in entries if kind == "message_end"]
        elif any(kind == "turn_end" for kind, _ in entries):
            entries = [(kind, usage) for kind, usage in entries if kind == "turn_end"]
        values = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
        for _, usage in entries:
            details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
            values["input"] += _integer(usage.get("input", usage.get("input_tokens", usage.get("prompt_tokens", 0))))
            values["output"] += _integer(usage.get("output", usage.get("output_tokens", usage.get("completion_tokens", 0))))
            values["cacheRead"] += _integer(usage.get("cacheRead", usage.get("cache_read_input_tokens", details.get("cached_tokens", 0))))
            values["cacheWrite"] += _integer(usage.get("cacheWrite", usage.get("cache_creation_input_tokens", details.get("cache_creation_tokens", 0))))
        context.n_input_tokens = values["input"] + values["cacheRead"]
        context.n_output_tokens = values["output"]
        context.n_cache_tokens = values["cacheRead"] + values["cacheWrite"]


def _integer(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
