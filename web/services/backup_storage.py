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


class _RollingBuffer(io.RawIOBase):
    """Write-only buffer that lets the producer drain bytes as they arrive.

    Used to feed ``zipfile.ZipFile`` without ever materializing the whole
    archive in memory. After each write, the consumer calls ``drain()`` to
    pull bytes off and send them to the client.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def writable(self) -> bool:
        return True

    def write(self, b) -> int:  # type: ignore[override]
        data = bytes(b)
        self._buf.extend(data)
        return len(data)

    def drain(self) -> bytes:
        out = bytes(self._buf)
        self._buf.clear()
        return out


def zip_stream(paths: list[Path], chunk_size: int = 65536) -> Iterator[bytes]:
    """Yield a zip archive containing ``paths`` one chunk at a time.

    Each file is written into a rolling buffer via ``zipfile.ZipFile``, and
    we yield drained chunks after every write. Duplicate basenames get
    a ``__N`` suffix.
    """
    buf = _RollingBuffer()
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

            with zf.open(name, "w") as entry:
                with open(p, "rb") as src:
                    while True:
                        chunk = src.read(chunk_size)
                        if not chunk:
                            break
                        entry.write(chunk)
                        drained = buf.drain()
                        if drained:
                            yield drained
            # Flush any bytes emitted during central-directory/local-header writes.
            drained = buf.drain()
            if drained:
                yield drained
    # Final central directory bytes.
    tail = buf.drain()
    if tail:
        yield tail
