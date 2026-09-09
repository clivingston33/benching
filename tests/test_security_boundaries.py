"""Focused M1 regression tests: endpoint/credential/registry boundaries.

Uses dummy credentials only; no real provider requests.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest


INVALID_ENDPOINTS = [
    "http://api.example.test/v1",
    "https://user:secret@example.test/v1",
    "https://user@example.test/v1",
    "https://api.example.test/v1?api_key=dummy",
    "https://api.example.test/v1#fragment",
    "not-a-url",
    "https://",
    "ftp://api.example.test/v1",
    "http://localhost:8000/v1",
]


def test_unsafe_http_endpoint_never_receives_authorization(monkeypatch) -> None:
    """A dummy HTTP endpoint must not receive Authorization: Bearer."""
    from benching.benchmark import validation as validation_mod

    calls: list = []

    class _NoNetwork:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("network must not be used for unsafe endpoint")

    monkeypatch.setattr(validation_mod, "urlopen", _NoNetwork)
    with pytest.raises(SystemExit):
        validation_mod.validation_request(
            "http://api.example.test/v1/chat/completions", "dummy-secret", "dummy-model"
        )
    assert calls == []


def test_concurrency_probe_rejects_unsafe_endpoint_without_network(monkeypatch) -> None:
    from benching.benchmark import concurrency as probe

    monkeypatch.setattr(probe, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    barrier = threading.Barrier(1)
    result = probe.one_request(
        "acme", None, "unknown", "http://api.example.test/v1", "dummy-model", "dummy-secret", 1, 0, barrier
    )
    assert result["provider_failure"] is True
    assert result["stream_success"] is False
    assert result["http_status"] is None


def test_add_and_edit_reject_equivalent_invalid_urls() -> None:
    from benching.benchmark.config import load_yaml
    from benching.benchmark.providers import add_provider, remove_provider, update_provider

    for index, bad_url in enumerate(INVALID_ENDPOINTS):
        name = f"bad{index}"
        with pytest.raises(SystemExit):
            add_provider(name, bad_url, "dummy-model", "dummy-secret", make_active=False)
    # Valid provider stays valid; edit path rejects the same bad URLs.
    add_provider("goodone", "https://api.example.test/v1", "dummy-model", "dummy-secret", make_active=False)
    try:
        for bad_url in INVALID_ENDPOINTS:
            with pytest.raises(SystemExit):
                update_provider("goodone", base_url=bad_url)
        cfg = load_yaml()["providers"]["goodone"]
        assert cfg["base_url"] == "https://api.example.test/v1"
    finally:
        remove_provider("goodone")


def test_invalid_edit_does_not_create_partially_valid_config() -> None:
    from benching.benchmark.config import load_yaml
    from benching.benchmark.providers import add_provider, remove_provider, update_provider

    add_provider("partial", "https://valid.example.test/v1", "model-one", "dummy-secret", make_active=False)
    try:
        with pytest.raises(SystemExit):
            update_provider("partial", base_url="http://insecure.example.test/v1", default_model="model-two")
        cfg = load_yaml()["providers"]["partial"]
        assert cfg["base_url"] == "https://valid.example.test/v1"
        assert cfg["default_model"] == "model-one"
    finally:
        remove_provider("partial")


def test_registry_traversal_cannot_escape(tmp_path: Path) -> None:
    from benching.benchmark.benchmarks import load_manifest, manifest_path, remove_benchmark
    from benching.benchmark.state import benchmarks_dir

    benchmarks_dir().mkdir(parents=True, exist_ok=True)
    victim = benchmarks_dir().parent / "victim.yaml"
    victim.write_text("benchmark: {name: victim}\n", encoding="utf-8")
    for evil in ("../victim", "../../x", "..\\victim", "/absolute", "a/b"):
        with pytest.raises(SystemExit):
            manifest_path(evil)
        with pytest.raises(SystemExit):
            load_manifest(evil)
        with pytest.raises(SystemExit):
            remove_benchmark(evil)
    assert victim.is_file()
    assert victim.read_text(encoding="utf-8") == "benchmark: {name: victim}\n"


def test_key_rotation_rejects_newline_control_injection() -> None:
    from benching.benchmark.providers import add_provider, remove_provider, rename_key_field
    from benching.benchmark.state import providers_dir

    add_provider("rot", "https://api.example.test/v1", "dummy-model", "dummy-secret", make_active=False)
    try:
        env_path = providers_dir() / "rot.env"
        before = env_path.read_text(encoding="utf-8")
        for evil in ("new\nINJECTED=1", "new\rINJECTED=1", "new\x00secret", "new\x1fsecret", "   "):
            with pytest.raises(SystemExit) as excinfo:
                rename_key_field("rot", evil)
            # Secrets must not be echoed in normal exception messages.
            message = str(excinfo.value.code or excinfo.value)
            assert evil not in message
            assert "INJECTED" not in message
        assert env_path.read_text(encoding="utf-8") == before
        assert "INJECTED" not in before
    finally:
        remove_provider("rot")


def test_external_credential_file_not_deleted(tmp_path: Path) -> None:
    from benching.benchmark.providers import _load_registry, _save_registry, add_provider, remove_provider

    add_provider("ext", "https://api.example.test/v1", "dummy-model", "dummy-secret", make_active=False)
    external = tmp_path / "external.env"
    external.write_text("EXT_API_KEY=dummy-secret\n", encoding="utf-8")
    providers = _load_registry()
    providers["ext"]["env_file"] = str(external)
    _save_registry(providers)
    remove_provider("ext")
    assert external.is_file()
    assert external.read_text(encoding="utf-8") == "EXT_API_KEY=dummy-secret\n"
    assert "ext" not in _load_registry()


def test_failed_registration_leaves_no_enabled_provider(monkeypatch) -> None:
    import benching.benchmark.providers as providers_mod
    from benching.benchmark.config import enabled_providers, load_yaml
    from benching.benchmark.providers import _load_registry, add_provider

    def _fail_write(path, content):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(providers_mod, "write_credential_file", _fail_write)
    with pytest.raises(OSError):
        add_provider("doomed", "https://api.example.test/v1", "dummy-model", "dummy-secret", make_active=False)
    assert "doomed" not in _load_registry()
    root = load_yaml()
    assert "doomed" not in (root.get("providers") or {})
    assert "doomed" not in enabled_providers(root)


def test_secrets_not_in_exception_messages() -> None:
    from benching.benchmark.security import validate_api_key, validate_endpoint

    with pytest.raises(SystemExit) as excinfo:
        validate_api_key("super-secret-123\ninjected")
    assert "super-secret-123" not in str(excinfo.value.code or excinfo.value)
    with pytest.raises(SystemExit) as excinfo2:
        validate_endpoint("https://user:supersecret123@example.test/v1")
    assert "supersecret123" not in str(excinfo2.value.code or excinfo2.value)


