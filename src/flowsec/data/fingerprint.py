from __future__ import annotations

import hashlib
from pathlib import Path


def file_digest(path: Path, algorithm: str = "sha256", chunk_size: int = 8 * 1024 * 1024) -> str:
    """Return a streaming file digest without loading the file into memory."""

    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
