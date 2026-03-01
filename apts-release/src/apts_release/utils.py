"""Shared utilities — file ops, hashing, size formatting."""

import hashlib
import shutil
from pathlib import Path


def compute_sha256(filepath: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def format_size(size_bytes: int) -> str:
    """Format byte count as human-readable string (e.g. '1.42 MB', '89 KB')."""
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.2f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def safe_copy(src: Path, dst: Path) -> None:
    """Copy a file and verify the destination size matches."""
    shutil.copy2(src, dst)
    src_size = src.stat().st_size
    dst_size = dst.stat().st_size
    if src_size != dst_size:
        raise IOError(
            f"Copy verification failed: {src.name} "
            f"(src={src_size}, dst={dst_size})"
        )


def ensure_dir(path: Path) -> Path:
    """Create directory (and parents) if it doesn't exist. Returns the path."""
    path.mkdir(parents=True, exist_ok=True)
    return path
