"""Publish the interactive market to a Hugging Face Docker Space.

    HF_TOKEN=<write token> python deploy/hf_space.py            publish
    python deploy/hf_space.py --dry-run                          stage only, print what would go up

Run by .github/workflows/deploy.yml on every push to main. A Space builds the
Dockerfile at its root and reads its settings from front matter at the top of
its README, so the script stages a copy of the tracked files with
deploy/Dockerfile moved to the root and the front matter added, then mirrors
that into the Space (files removed here are removed there too).

If LEM_ADMIN_TOKEN is set, it is stored as a Space secret, which locks the
shared clock to the operator.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPACE_NAME = "local-energy-market"
FRONT_MATTER = """---
title: Local Energy Market
emoji: ⚡
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 3000
pinned: true
short_description: Peer-to-peer solar market, settled on signed meters
---

"""
# Not needed by the image (see .dockerignore); keeping them out keeps the Space small.
SKIP = ("contracts/lib/", ".github/")


def stage(dst: Path) -> int:
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    n = 0
    for rel in tracked.splitlines():
        if rel.startswith(SKIP) or not (ROOT / rel).is_file():
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
        n += 1
    shutil.copy2(ROOT / "deploy" / "Dockerfile", dst / "Dockerfile")
    readme = (ROOT / "Readme.md").read_text(encoding="utf-8")
    (dst / "Readme.md").unlink(missing_ok=True)
    (dst / "README.md").write_text(FRONT_MATTER + readme, encoding="utf-8")
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--space", default=SPACE_NAME)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        n = stage(staging)
        size = sum(p.stat().st_size for p in staging.rglob("*") if p.is_file())
        print(f"staged {n} files, {size / 1e6:.1f} MB")
        if args.dry_run:
            print("README front matter:\n" + (staging / "README.md").read_text(encoding="utf-8")[:400])
            return

        from huggingface_hub import HfApi

        api = HfApi(token=os.environ["HF_TOKEN"])
        user = api.whoami()["name"]
        repo_id = f"{user}/{args.space}"
        api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
        if os.environ.get("LEM_ADMIN_TOKEN"):
            api.add_space_secret(repo_id, "LEM_ADMIN_TOKEN", os.environ["LEM_ADMIN_TOKEN"])
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        api.upload_folder(folder_path=str(staging), repo_id=repo_id, repo_type="space",
                          commit_message=f"Deploy {sha}", delete_patterns=["*"])
        print(f"published https://huggingface.co/spaces/{repo_id}")
        print(f"app       https://{user}-{args.space}.hf.space")


if __name__ == "__main__":
    main()
