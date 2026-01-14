from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import hashlib
import subprocess


def _find_repo_root(start: Path) -> Optional[Path]:
    cur = start
    for _ in range(10):
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _read_git_sha_from_dotgit(repo_root: Path) -> Optional[str]:
    git_dir = repo_root / ".git"
    head_path = git_dir / "HEAD"
    if not head_path.exists():
        return None

    head = head_path.read_text(encoding="utf-8", errors="ignore").strip()
    if head.startswith("ref:"):
        ref = head.split(" ", 1)[1].strip()
        ref_path = git_dir / ref
        if ref_path.exists():
            sha = ref_path.read_text(encoding="utf-8", errors="ignore").strip()
            return sha or None
        packed_refs = git_dir / "packed-refs"
        if packed_refs.exists():
            for line in packed_refs.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line or line.startswith("#") or line.startswith("^"):
                    continue
                parts = line.split(" ")
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
        return None

    # Detached HEAD
    return head or None


def _try_run_git(repo_root: Path, args: list[str]) -> Optional[str]:
    """Best-effort helper for git queries.

    We prefer not to depend on the `git` binary, but when it's available locally it lets us detect
    uncommitted changes. Failures are swallowed and reported as None.
    """
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.5,
        )
        if r.returncode != 0:
            return None
        return r.stdout
    except Exception:
        return None


def _compute_dirty_hash_short(repo_root: Path) -> Optional[str]:
    """Return a short hash representing the working tree diff, or None if clean/unknown."""
    status = _try_run_git(repo_root, ["status", "--porcelain"])
    if status is None:
        return None
    if not status.strip():
        return None

    diff = _try_run_git(repo_root, ["diff", "--no-ext-diff"])
    if diff is None:
        # Dirty but can't read diff; still return a stable marker.
        return "dirty"

    h = hashlib.sha256(diff.encode("utf-8", errors="ignore")).hexdigest()
    return h[:12]


@lru_cache(maxsize=1)
def get_code_version() -> Dict[str, Any]:
    """Return a small, stable version payload to embed in exports/reports.

    Priority:
    1) Environment variables (works in Docker/CI): GIT_SHA, APP_VERSION, BUILD_TIME_UTC
    2) Read from .git without shelling out (works locally without `git` binary)
    """

    app_version_env = os.getenv("APP_VERSION") or os.getenv("VERSION")
    app_version = app_version_env or "dev"
    build_time_utc = os.getenv("BUILD_TIME_UTC")

    git_sha = os.getenv("GIT_SHA") or os.getenv("SOURCE_VERSION")
    source = "env" if git_sha else "unknown"

    if not git_sha:
        repo_root = _find_repo_root(Path(__file__).resolve())
        if repo_root is not None:
            sha = _read_git_sha_from_dotgit(repo_root)
            if sha:
                git_sha = sha
                source = ".git"

    # Detect uncommitted changes (best-effort). This is especially useful in local dev where
    # `git_sha` remains the same until a commit is created.
    dirty_hash_short: Optional[str] = None
    git_is_dirty: Optional[bool] = None
    repo_root_for_dirty = _find_repo_root(Path(__file__).resolve())
    if repo_root_for_dirty is not None:
        dirty_hash_short = _compute_dirty_hash_short(repo_root_for_dirty)
        if dirty_hash_short is not None:
            git_is_dirty = True
            # If the user didn't set a real version, make the dev version visibly change when code changes.
            if not app_version_env and app_version == "dev":
                app_version = f"dev+{dirty_hash_short}"
        else:
            git_is_dirty = False

    short_sha = git_sha[:12] if isinstance(git_sha, str) and git_sha else None

    payload: Dict[str, Any] = {
        "app_version": app_version,
        "git_sha": git_sha,
        "git_sha_short": short_sha,
        "git_is_dirty": git_is_dirty,
        "git_dirty_hash_short": dirty_hash_short,
        "build_time_utc": build_time_utc,
        "source": source,
    }

    # Keep it clean for JSON/PDF: omit nulls.
    return {k: v for k, v in payload.items() if v is not None}
