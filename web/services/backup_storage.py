"""Filesystem helpers for reading backup XML files written by the worker."""

from __future__ import annotations

import gzip
import io
import zipfile
from collections.abc import Iterator
from pathlib import Path


def read_content(path: Path) -> str:
    """Return the decoded XML content, transparently decompressing .gz files."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.read()
    return path.read_text(encoding="utf-8")


def stream_raw(path: Path, chunk_size: int = 65536) -> Iterator[bytes]:
    """Yield raw bytes of the file (no decompression)."""
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                return
            yield chunk


def zip_files(paths: list[Path]) -> bytes:
    """Build an in-memory zip archive containing ``paths``.

    Each file is stored under its basename; duplicates get a suffix.
    """
    buf = io.BytesIO()
    seen: dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            name = p.name
            if name in seen:
                seen[name] += 1
                stem, dot, suffix = name.partition(".")
                name = f"{stem}__{seen[name]}{dot}{suffix}" if dot else f"{stem}__{seen[name]}"
            else:
                seen[name] = 1
            zf.write(p, arcname=name)
    return buf.getvalue()
