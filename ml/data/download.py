"""Fetch and cache the Ausgrid dataset and the postcode centroid table.

    python -m ml.data.download
"""

import hashlib
import zipfile
from pathlib import Path

import requests

from ml import config


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path) -> Path:
    if dest.exists():
        print(f"cached  {dest.relative_to(config.ROOT)}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"fetch   {url}")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    tmp.replace(dest)
    return dest


def verify(path: Path, expected: str) -> None:
    actual = sha256_of(path)
    if expected == "PIN_ON_FIRST_DOWNLOAD":
        raise SystemExit(
            f"No hash pinned for {path.name}. Inspect the file, then set\n"
            f"    AUSGRID_SHA256 = \"{actual}\"\nin ml/config.py."
        )
    if actual != expected:
        raise SystemExit(
            f"{path.name} hash mismatch.\n  expected {expected}\n  actual   {actual}\n"
            "The mirror's contents have changed. Do not proceed until you know why."
        )
    print(f"sha256  ok  {actual[:16]}…")


def extract(zip_path: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest)
    return sorted(dest.rglob("*"))


def main() -> None:
    fetch(config.AUSGRID_URL, config.AUSGRID_ZIP)
    verify(config.AUSGRID_ZIP, config.AUSGRID_SHA256)
    for p in extract(config.AUSGRID_ZIP, config.AUSGRID_DIR):
        if p.is_file():
            print(f"        {p.relative_to(config.ROOT)}  {p.stat().st_size / 1e6:.1f} MB")
    fetch(config.POSTCODES_URL, config.POSTCODES_CSV)


if __name__ == "__main__":
    main()
