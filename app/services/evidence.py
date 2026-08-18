from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def thermal_evidence_id(source_sha256: str, tile_id: int | str) -> str:
    payload = f"fortyguard|{source_sha256}|tile|{tile_id}".encode("utf-8")
    return "hs_thermal_" + hashlib.sha256(payload).hexdigest()[:20]
