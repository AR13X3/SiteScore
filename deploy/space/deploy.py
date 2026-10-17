"""Mirror this repository into the Hugging Face Space that runs the live demo.

Run by .github/workflows/deploy-demo.yml on every push to main. Needs:
  HF_TOKEN   a Hugging Face token with write access (repository secret)
  HF_SPACE   the Space, "username/name" (repository variable); created if missing

Uploads the files the container needs (see .dockerignore for what it leaves out) with the
Space's own README card on top, and removes anything on the Space that is no longer in
the repository. Binary files (the demo pack) go through Hugging Face's large-file store.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from fnmatch import fnmatch
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]
# Tracked files the Space doesn't need: tests, docs and screenshots, CI, this folder.
SKIP = ["tests/*", "docs/*", ".github/*", "deploy/*", "backtests/results/*", ".gitattributes"]


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True).stdout
    return [f for f in out.decode().split("\0") if f and not any(fnmatch(f, p) for p in SKIP)]


def main() -> None:
    token, space = os.environ.get("HF_TOKEN"), os.environ.get("HF_SPACE")
    if not token or not space:
        sys.exit("Set HF_TOKEN (secret) and HF_SPACE (variable, e.g. yourname/sitescore).")
    sha = os.environ.get("GITHUB_SHA", "local")[:7]
    api = HfApi(token=token)
    api.create_repo(space, repo_type="space", space_sdk="docker", exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        files = tracked_files()
        for f in files:
            (stage / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, stage / f)
        shutil.copy2(ROOT / "deploy" / "space" / "README.md", stage / "README.md")

        keep = set(files) | {"README.md", ".gitattributes"}  # HF's own .gitattributes stays
        stale = [f for f in api.list_repo_files(space, repo_type="space") if f not in keep]
        api.upload_folder(
            repo_id=space, repo_type="space", folder_path=stage,
            commit_message=f"Deploy {sha} from GitHub",
            delete_patterns=stale or None,
        )
    host = space.replace("/", "-").replace("_", "-").lower()
    print(f"Deployed {sha} to https://huggingface.co/spaces/{space} (app: https://{host}.hf.space)")


if __name__ == "__main__":
    main()
