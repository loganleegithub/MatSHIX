from __future__ import annotations

import platform
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

RUNTIME_PACKAGES = (
    "duckdb",
    "exchange-calendars",
    "numpy",
    "pandas",
    "pyarrow",
    "scikit-learn",
    "scipy",
)


def _git(project: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def repository_provenance(project: Path) -> dict[str, Any]:
    """Return deterministic repository identity for an evidence manifest."""

    return {
        "project_dir": str(project),
        "git_sha": _git(project, "rev-parse", "HEAD"),
        "git_branch": _git(project, "branch", "--show-current"),
        "worktree_clean": not bool(_git(project, "status", "--porcelain")),
    }


def runtime_provenance() -> dict[str, Any]:
    """Return frozen interpreter and dependency versions without timestamps."""

    dependencies: dict[str, str | None] = {}
    for package in RUNTIME_PACKAGES:
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = None
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "executable": str(Path(sys.executable).resolve()),
        "dependencies": dependencies,
    }
