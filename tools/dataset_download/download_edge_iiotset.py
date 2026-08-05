"""Download the official Edge-IIoTset archive with resume and MD5 verification."""

from __future__ import annotations

import argparse
import hashlib
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


OFFICIAL_URL = (
    "https://www.kaggle.com/api/v1/datasets/download/"
    "mohamedamineferrag/edgeiiotset-cyber-security-dataset-of-iot-iiot"
)
ARCHIVE_NAME = "edgeiiotset-cyber-security-dataset-of-iot-iiot.zip"
EXPECTED_SIZE = 1_746_605_436
EXPECTED_MD5 = "d0f9be0185845a1ef4ed31cc6db4a9b2"


def file_md5(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - required to verify the publisher checksum
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(output_root: Path, *, retries: int = 30) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    output = output_root / ARCHIVE_NAME
    attempts = 0
    while (output.stat().st_size if output.exists() else 0) < EXPECTED_SIZE:
        offset = output.stat().st_size if output.exists() else 0
        if offset > EXPECTED_SIZE:
            raise RuntimeError(f"local file exceeds expected size: {offset}")
        headers = {"Accept-Encoding": "identity", "User-Agent": "flow-security-agent/0.1"}
        if offset:
            headers["Range"] = f"bytes={offset}-{EXPECTED_SIZE - 1}"
        request = urllib.request.Request(OFFICIAL_URL, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                status = response.status
                content_range = response.headers.get("Content-Range", "")
                if offset and (status != 206 or not content_range.startswith(f"bytes {offset}-")):
                    raise RuntimeError(
                        f"unsafe resume response: status={status} "
                        f"content-range={content_range!r} offset={offset}"
                    )
                mode = "r+b" if output.exists() else "wb"
                with output.open(mode) as handle:
                    handle.seek(offset)
                    while handle.tell() < EXPECTED_SIZE:
                        block = response.read(min(1024 * 1024, EXPECTED_SIZE - handle.tell()))
                        if not block:
                            break
                        handle.write(block)
                    handle.flush()
                    os.fsync(handle.fileno())
            attempts = 0
        except (OSError, urllib.error.URLError) as exc:
            attempts += 1
            if attempts >= retries:
                raise RuntimeError(f"download failed after {attempts} attempts") from exc
            time.sleep(min(30, 2 * attempts))

    actual_size = output.stat().st_size
    actual_md5 = file_md5(output)
    if actual_size != EXPECTED_SIZE:
        raise RuntimeError(f"size mismatch: {actual_size} != {EXPECTED_SIZE}")
    if actual_md5 != EXPECTED_MD5:
        raise RuntimeError(f"MD5 mismatch: {actual_md5} != {EXPECTED_MD5}")
    print(f"verified path={output} bytes={actual_size} md5={actual_md5}")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(os.environ.get("EDGE_DATA_ROOT", "data/external/edge_iiotset")),
        help="Directory for the official archive (default: EDGE_DATA_ROOT or data/external/edge_iiotset)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    download(arguments.output_root.expanduser().resolve())
