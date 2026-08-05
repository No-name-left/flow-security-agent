"""Download and verify the seven official IoT-23 Gate scenarios."""

from __future__ import annotations

import argparse
import hashlib
import lzma
import os
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path


BASE_URL = "https://mcfp.felk.cvut.cz/publicDatasets/IoT-23-Dataset/"


@dataclass(frozen=True)
class Asset:
    relative_path: str
    url_path: str
    sha256: str
    xz_compressed: bool = False


ASSETS = (
    Asset("metadata/README.md", "README.md", "8c645afd906d2a22c8cc9fae1251e7a35c27b09ccb6ecadf268b768643a44ab2"),
    Asset("CTU-IoT-Malware-Capture-8-1/2018-07-31-15-15-09-192.168.100.113.pcap", "IndividualScenarios/CTU-IoT-Malware-Capture-8-1/2018-07-31-15-15-09-192.168.100.113.pcap", "80dcc2602519479ddcde889fa902fee19a76696630811452f8df38888af894f2"),
    Asset("CTU-IoT-Malware-Capture-8-1/bro/conn.log.labeled", "IndividualScenarios/CTU-IoT-Malware-Capture-8-1/bro/conn.log.labeled", "4877ca8f0f01902fbd18d28b7d06cb3d0be082355b7f2c8862c9deef1782eb8a"),
    Asset("CTU-IoT-Malware-Capture-20-1/2018-10-02-13-12-30-192.168.100.103.pcap", "IndividualScenarios/CTU-IoT-Malware-Capture-20-1/2018-10-02-13-12-30-192.168.100.103.pcap", "4d0a00c33a4bf11228158baddd47c38f702731ea8d75ef1201061fc8bbd878b9"),
    Asset("CTU-IoT-Malware-Capture-20-1/bro/conn.log.labeled", "IndividualScenarios/CTU-IoT-Malware-Capture-20-1/bro/conn.log.labeled", "ef48ad72f65efd13d517223e61e4d877ba53a082ddb8159324b18d3f310d0711"),
    Asset("CTU-IoT-Malware-Capture-21-1/2018-10-03-15-22-32-192.168.100.113.pcap", "IndividualScenarios/CTU-IoT-Malware-Capture-21-1/2018-10-03-15-22-32-192.168.100.113.pcap", "40b6928cedcda03fe5ded8a9994ec007a6d784028f37cbc00bbe3a26a7893023"),
    Asset("CTU-IoT-Malware-Capture-21-1/bro/conn.log.labeled", "IndividualScenarios/CTU-IoT-Malware-Capture-21-1/bro/conn.log.labeled", "b63db259aead078f50fc150aa97ace4d1f69576e1245334962759d978ce437eb"),
    Asset("CTU-IoT-Malware-Capture-34-1/2018-12-21-15-50-14-192.168.1.195.pcap", "IndividualScenarios/CTU-IoT-Malware-Capture-34-1/2018-12-21-15-50-14-192.168.1.195.pcap", "92ec7e2f6658ee4b007d0b816986c46cc0338bc5e2bec6ceaaca566c695e4699"),
    Asset("CTU-IoT-Malware-Capture-34-1/bro/conn.log.labeled", "IndividualScenarios/CTU-IoT-Malware-Capture-34-1/bro/conn.log.labeled", "d69e49b2aae8c1bd33286936531658202dec47d989f0439bad3f8be180467a6e"),
    Asset("CTU-IoT-Malware-Capture-42-1/2019-01-10-14-34-38-192.168.1.197.pcap", "IndividualScenarios/CTU-IoT-Malware-Capture-42-1/2019-01-10-14-34-38-192.168.1.197.pcap", "7573797f17aae96e3804a3cfb22d531b74c17bbae740de1e14048f89130fba37"),
    Asset("CTU-IoT-Malware-Capture-42-1/bro/conn.log.labeled", "IndividualScenarios/CTU-IoT-Malware-Capture-42-1/bro/conn.log.labeled", "269fa1b22d9a37e159cf41b81a213a0032d21306f5d39b4c20cb0d211b04e8aa"),
    Asset("CTU-Honeypot-Capture-4-1/2018-10-25-14-06-32-192.168.1.132.pcap", "IndividualScenarios/CTU-Honeypot-Capture-4-1/2018-10-25-14-06-32-192.168.1.132.pcap.xz", "3fb775c0391b6ad313a3f7845e634a277b07c3f6377346c2486ba63e1c22e90c", True),
    Asset("CTU-Honeypot-Capture-4-1/bro/conn.log.labeled", "IndividualScenarios/CTU-Honeypot-Capture-4-1/bro/conn.log.labeled", "aebe40ea0e03b120265a5c7bc140dd9b0d3fe2fce65559e84776b7dd5360e71e"),
    Asset("CTU-Honeypot-Capture-7-1/Somfy-01/2019-07-03-15-15-47-first_start_somfy_gateway.pcap", "IndividualScenarios/CTU-Honeypot-Capture-7-1/Somfy-01/2019-07-03-15-15-47-first_start_somfy_gateway.pcap", "0ec756ff0e26fc6c7d985178a35206bd7bc5b8a33cc5c7a23d6bb0b103db2a2a"),
    Asset("CTU-Honeypot-Capture-7-1/Somfy-01/bro/conn.log.labeled", "IndividualScenarios/CTU-Honeypot-Capture-7-1/Somfy-01/bro/conn.log.labeled", "fb37fb38393c48b064d3afd373b075ffe31063d4924a2df1c5d13fc490b830cc"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_asset(root: Path, asset: Asset) -> None:
    destination = root / asset.relative_path
    if destination.exists() and sha256(destination) == asset.sha256:
        print(f"verified existing {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + (".xz.part" if asset.xz_compressed else ".part"))
    request = urllib.request.Request(BASE_URL + asset.url_path, headers={"User-Agent": "flow-security-agent/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:  # noqa: S310
        shutil.copyfileobj(response, output, length=1024 * 1024)
    if asset.xz_compressed:
        decoded = destination.with_suffix(destination.suffix + ".part")
        with lzma.open(temporary, "rb") as source, decoded.open("wb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
        temporary.unlink()
        temporary = decoded
    actual = sha256(temporary)
    if actual != asset.sha256:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"SHA256 mismatch for {asset.relative_path}: {actual} != {asset.sha256}")
    temporary.replace(destination)
    print(f"verified downloaded {destination} sha256={actual}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(os.environ.get("IOT23_DATA_ROOT", "data/external/iot23/official_subset")),
        help="Subset root (default: IOT23_DATA_ROOT or data/external/iot23/official_subset)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    output_root = arguments.output_root.expanduser().resolve()
    for selected_asset in ASSETS:
        download_asset(output_root, selected_asset)
