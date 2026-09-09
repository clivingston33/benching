"""Shared paths: immutable package resources vs. explicit runtime roots.

Ownership rules (M3 task 9):

- Package resources (default benchmark YAML, JSON Schemas) ship inside the
  installed package and are read-only. Load them through
  :func:`resource_text`, never through checkout-relative paths.
- Writable runtime data (runs) resolves through :func:`runs_root`, which
  is never the package installation directory.
- User configuration/credentials/caches stay user-local (see
  :mod:`benchmark.state`).
- Importing this module (or any Benching library) must not mutate the
  process environment. Subprocess additions (user-local binary lookup)
  happen explicitly per child process; see :func:`local_bin_dir` and
  :func:`resolve_executable`.
"""

from __future__ import annotations

import os
import shutil
from importlib import resources
from pathlib import Path

#: Source-checkout repository root (``src/benching/benchmark/_paths.py``
#: parents[2]). Development-only: meaningful only inside a source checkout
#: (for example the OMP bind-mount source below). Never a writable data
#: root, and never meaningful for an installed package.
ROOT = Path(__file__).resolve().parents[2]

CACHE_ROOT = Path.home() / ".cache" / "benching"
PROXY_PORT = 8765
DEFAULT_CONCURRENCY = 3
DEFAULT_TRIALS = 1

#: Environment variable overriding the writable runs root.
RUNS_DIR_ENVVAR = "BENCHING_RUNS_DIR"

#: Conventional user-local binary directory (harbor, omp). Consulted
#: explicitly when resolving executables and building child environments;
#: never prepended to the parent process PATH.
LOCAL_BIN_DIRNAME = ".local/bin"


def resource_text(*parts: str) -> str:
    """Read an immutable packaged resource as text.

    Looks under the installed ``benching.benchmark`` package (for example
    ``resource_text("resources", "benchmark.yaml")``), so it works
    identically from a source checkout, an editable install, and a wheel
    installed outside the repository.
    """
    return (resources.files("benching.benchmark").joinpath(*parts)).read_text(encoding="utf-8")


def runs_root() -> Path:
    """Writable benchmark runs root, never the install location.

    Explicit ``BENCHING_RUNS_DIR`` override wins; otherwise the runs
    directory of the invoking working directory (``./runs``). Evaluate at
    call time so directory changes and overrides always take effect.
    """
    override = os.environ.get(RUNS_DIR_ENVVAR)
    if override:
        return Path(override).expanduser()
    return Path.cwd() / "runs"


def package_parent() -> Path:
    """Directory containing the imported ``benching`` package.

    Layout-correct in every mode: ``src/`` for source-checkout runs,
    ``site-packages`` (or equivalent) for installed runs. Used to build
    child-process PYTHONPATH entries without hardcoding either layout.
    """
    import benching

    return Path(benching.__file__).resolve().parent.parent


def local_bin_dir() -> Path:
    """Conventional user-local binary directory (may not exist)."""
    return Path.home() / ".local/bin"


def resolve_executable(name: str) -> Path | None:
    """Locate an executable without touching the parent environment.

    Checks the inherited ``PATH`` first, then the conventional user-local
    binary directory. Returns None when not found.
    """
    found = shutil.which(name)
    if found is not None:
        return Path(found)
    candidate = local_bin_dir() / name
    if candidate.is_file():
        return candidate
    return None
