"""Shared configuration/credential trust boundary (M1 task 2).

One reusable validation/resolution boundary for provider endpoints,
model/key inputs, and registry names. All provider add/edit/resolve/
preflight/probe/run paths must use these helpers so equivalent invalid
input is rejected consistently before any credential is transmitted.

Secrets never appear in exception messages raised here.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

_REGISTRY_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def validate_registry_name(name: object, kind: str = "provider") -> str:
    """Validate a provider/benchmark registry name.

    Rejects ``../``, ``..\\``, absolute paths, and separators by only
    allowing letters, numbers, ``-`` and ``_`` (leading alnum).
    Raises ``SystemExit`` with a generic message (no secret content).
    """
    if not isinstance(name, str) or not re.fullmatch(_REGISTRY_NAME_RE, name):
        if kind == "benchmark":
            raise SystemExit("benchmark name must contain only letters, numbers, '-' or '_'")
        raise SystemExit("provider name must contain only letters, numbers, '-' or '_'")
    return name


def _reject_control(value: str, message: str) -> None:
    for char in value:
        code = ord(char)
        if char in ("\n", "\r") or code < 32 or code == 127:
            raise SystemExit(message)


def validate_api_key(api_key: object) -> str:
    """Validate an API key without echoing it.

    Rejects empty/whitespace-only values and newline/control-character
    injection that would corrupt ``KEY=VALUE`` credential files or HTTP
    headers. Returns the original key unchanged.
    """
    if not isinstance(api_key, str) or not api_key.strip():
        raise SystemExit("API key is required")
    _reject_control(api_key, "API key must not contain newline or control characters")
    return api_key


def validate_model_name(model: object) -> str:
    """Validate a model id without echoing secrets."""
    if not isinstance(model, str) or not model.strip():
        raise SystemExit("model is required")
    _reject_control(model, "model must not contain newline or control characters")
    return model


def validate_endpoint(raw_url: object) -> str:
    """Validate a provider base URL and return its normalized form.

    Enforces:
    - well-formed URL with ``https`` scheme (no cleartext HTTP, no
      localhost HTTP exception: the proxy enforces HTTPS end-to-end)
    - hostname present
    - no URL userinfo / credential-bearing URLs
    - no query or fragment (current endpoint contract appends fixed
      ``/models`` and ``/chat/completions`` paths)
    - no embedded whitespace/control characters

    Never includes the raw URL in errors so query/userinfo secrets
    cannot leak into logs. Raises ``SystemExit`` on invalid input.
    """
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise SystemExit("provider endpoint is required")
    stripped = raw_url.strip()
    # Reject control characters and whitespace that have no place in a base URL.
    for char in stripped:
        code = ord(char)
        if code < 33 or code == 127:
            # Covers spaces, tabs, newlines, and other controls.
            raise SystemExit("provider endpoint is not a valid URL")
    if "\\" in stripped:
        raise SystemExit("provider endpoint is not a valid URL")
    try:
        parsed = urlsplit(stripped)
    except ValueError:
        raise SystemExit("provider endpoint is not a valid URL") from None
    if parsed.scheme.lower() != "https":
        raise SystemExit("provider endpoint must use https://")
    if not parsed.hostname:
        raise SystemExit("provider endpoint must include a hostname")
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise SystemExit("provider endpoint must not contain credentials")
    if parsed.query or parsed.fragment:
        raise SystemExit("provider endpoint must not contain query or fragment")
    return stripped.rstrip("/")


def ensure_within_directory(base: Path, target: Path) -> Path:
    """Resolve ``target`` and require containment within ``base``.

    Raises ``SystemExit`` when the resolved target escapes. Used for
    registry file operations so ``../`` cannot load/overwrite/delete
    files outside the application registry.
    """
    try:
        resolved_base = base.expanduser().resolve()
        resolved_target = target.expanduser().resolve()
    except OSError:
        raise SystemExit("invalid registry name") from None
    try:
        if not resolved_target.is_relative_to(resolved_base):
            raise SystemExit("invalid registry name")
    except AttributeError:  # Python <3.9 fallback (repo requires 3.12, defensive only)
        try:
            resolved_target.relative_to(resolved_base)
        except ValueError:
            raise SystemExit("invalid registry name") from None
    return resolved_target


def is_owned_credential_file(env_file: Path, owned_dir: Path) -> bool:
    """True when ``env_file`` resolves inside ``owned_dir``.

    Application-owned files (under the providers directory) may be
    removed as part of provider removal. Externally supplied files
    outside that directory must never be silently deleted.
    """
    try:
        resolved_base = owned_dir.expanduser().resolve()
        resolved_target = env_file.expanduser().resolve()
    except OSError:
        return False
    try:
        return resolved_target.is_relative_to(resolved_base)
    except AttributeError:
        try:
            resolved_target.relative_to(resolved_base)
            return True
        except ValueError:
            return False


def write_credential_file(path: Path, content: str) -> None:
    """Write a credential file atomically with restrictive permissions.

    Same-directory temp file (restricted before it is visible) plus
    ``os.replace``: readers never observe truncated or partial secrets,
    and a failed write leaves the previous credential intact. Mode 0600
    where supported. Existing restrictive ACL semantics on Windows are
    documented limits, not established here.
    """
    from benching.benchmark.io import write_text_atomic

    write_text_atomic(path, content, mode=0o600)

