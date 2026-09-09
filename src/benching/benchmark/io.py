"""Atomic publication primitive for application-owned files (M1 task 4).

Same-directory temp file + ``os.replace``: readers always observe the
previous complete document or the new complete document, never truncated
intermediate content. Replacement stays on one filesystem. Temporary
files are removed on failure where practical.

Permissions: pass ``mode=0o600`` for secret-bearing files (temp is
restricted before it ever becomes visible at the target). Otherwise an
existing target keeps its mode and brand-new files get ``0o644``.

No journal, no transaction framework, no cross-filesystem staging, no
generic storage layer. Append-only evidence (``raw.jsonl``) intentionally
does not use this helper.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import time
from pathlib import Path
from typing import Any


def _target_mode(path: Path, mode: int | None) -> int | None:
    if mode is not None:
        return mode
    try:
        return stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        return 0o644


def write_bytes_atomic(path: Path, data: bytes, *, mode: int | None = None) -> None:
    """Write bytes atomically via same-directory temp file + os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".benching-tmp-", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        if os.name != "nt":
            try:
                os.fchmod(fd, 0o600)
            except OSError:
                pass
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except OSError:
                pass
        resolved_mode = _target_mode(path, mode)
        if resolved_mode is not None:
            try:
                os.chmod(tmp_path, resolved_mode)
            except OSError:
                pass
        # On Windows a concurrent reader may briefly hold the target open,
        # making replacement fail with a transient PermissionError. Retry
        # briefly (a reader handle closes in milliseconds), then fail
        # closed (temp is cleaned below).
        for attempt in range(25):
            try:
                os.replace(tmp_path, path)
                break
            except PermissionError:
                if attempt == 24:
                    raise
                time.sleep(0.01)
        if os.name != "nt":
            try:
                dir_fd = os.open(str(path.parent), os.O_RDONLY)
            except OSError:
                dir_fd = None
            if dir_fd is not None:
                try:
                    os.fsync(dir_fd)
                except OSError:
                    pass
                finally:
                    os.close(dir_fd)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_text_atomic(path: Path, text: str, *, encoding: str = "utf-8", mode: int | None = None) -> None:
    """Write text atomically via same-directory temp file + os.replace."""
    write_bytes_atomic(path, text.encode(encoding), mode=mode)


def dump_json_atomic(path: Path, obj: Any, *, indent: int = 2, mode: int | None = None) -> None:
    """Write a complete JSON document atomically."""
    write_text_atomic(path, json.dumps(obj, indent=indent, ensure_ascii=False) + "\n", mode=mode)


def dump_yaml_atomic(path: Path, obj: Any, *, sort_keys: bool = False, mode: int | None = None) -> None:
    """Write a complete YAML document atomically."""
    import yaml

    write_text_atomic(path, yaml.safe_dump(obj, sort_keys=sort_keys), mode=mode)


def yaml_error_summary(exc: BaseException) -> str:
    """One-line summary of a YAML parse failure, without file contents."""
    try:
        line = str(exc).strip().splitlines()
        return line[0][:160] if line else type(exc).__name__
    except Exception:
        return type(exc).__name__
