from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional


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


@lru_cache(maxsize=1)
def get_code_version() -> Dict[str, Any]:
    """Return a small, stable version payload to embed in exports/reports.

    Priority:
    1) Environment variables (works in Docker/CI): GIT_SHA, APP_VERSION, BUILD_TIME_UTC
    2) Read from .git without shelling out (works locally without `git` binary)
    """

    app_version = os.getenv("APP_VERSION") or os.getenv("VERSION") or "dev"
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

    short_sha = git_sha[:12] if isinstance(git_sha, str) and git_sha else None

    payload: Dict[str, Any] = {
        "app_version": app_version,
        "git_sha": git_sha,
        "git_sha_short": short_sha,
        "build_time_utc": build_time_utc,
        "source": source,
    }

    # Keep it clean for JSON/PDF: omit nulls.
    return {k: v for k, v in payload.items() if v is not None}
