#!/usr/bin/env python
"""SiteScore task runner. Stdlib only, works on Windows/macOS/Linux.

    python run.py install   # virtualenv + backend deps (+ frontend deps and build, once it exists)
    python run.py start     # run the app at http://127.0.0.1:8000
    python run.py dev       # backend + frontend with hot reload
    python run.py data      # fetch/refresh datasets; any unavailable source falls back to mock
    python run.py test      # run the test suite
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sitescore.paths import FRONTEND_DIR, FRONTEND_DIST, inside_synced_folder, venv_dir

HOST, PORT = "127.0.0.1", 8000


def venv_python() -> Path:
    sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return venv_dir() / sub


def sh(cmd: list, **kwargs) -> None:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kwargs)


def require_venv() -> Path:
    py = venv_python()
    if not py.exists():
        sys.exit("No virtualenv found. Run `python run.py install` first.")
    return py


def npm() -> str:
    exe = shutil.which("npm")
    if not exe:
        sys.exit("npm not found. Install Node.js 20+ from https://nodejs.org")
    return exe


def has_frontend() -> bool:
    return (FRONTEND_DIR / "package.json").exists()


def cmd_install(_: argparse.Namespace) -> None:
    if sys.version_info < (3, 11):
        sys.exit("Python 3.11+ required.")
    target = venv_dir()
    if not venv_python().exists():
        if inside_synced_folder():
            print(f"Repo is in a cloud-synced folder; putting the virtualenv outside it: {target}")
        venv.create(target, with_pip=True)
    py = venv_python()
    sh([py, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
    sh([py, "-m", "pip", "install", "-e", f"{ROOT}[dev]"])
    if has_frontend():
        sh([npm(), "install"], cwd=FRONTEND_DIR)
        sh([npm(), "run", "build"], cwd=FRONTEND_DIR)
    env, example = ROOT / ".env", ROOT / ".env.example"
    if not env.exists() and example.exists():
        shutil.copy(example, env)
        print("Created .env from .env.example (all keys optional).")
    print("\nInstalled. Next: python run.py start")


def cmd_start(args: argparse.Namespace) -> None:
    py = require_venv()
    if has_frontend() and not FRONTEND_DIST.exists():
        sh([npm(), "run", "build"], cwd=FRONTEND_DIR)
    url = f"http://{HOST}:{PORT}"
    if not args.no_browser:
        threading.Timer(2.0, webbrowser.open, [url]).start()
    print(f"SiteScore running at {url}  (Ctrl+C to stop)")
    sh([py, "-m", "uvicorn", "sitescore.api.main:app", "--host", HOST, "--port", PORT], cwd=ROOT)


def cmd_dev(_: argparse.Namespace) -> None:
    py = require_venv()
    procs = [
        subprocess.Popen(
            [str(py), "-m", "uvicorn", "sitescore.api.main:app", "--reload",
             "--host", HOST, "--port", str(PORT)],
            cwd=ROOT,
        )
    ]
    if has_frontend():
        procs.append(subprocess.Popen([npm(), "run", "dev"], cwd=FRONTEND_DIR))
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


def cmd_data(args: argparse.Namespace) -> None:
    sh([require_venv(), "-m", "sitescore.pipeline", *args.rest], cwd=ROOT)


def cmd_test(args: argparse.Namespace) -> None:
    sh([require_venv(), "-m", "pytest", *args.rest], cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install", help="create virtualenv and install everything").set_defaults(fn=cmd_install)
    start = sub.add_parser("start", help="run the app")
    start.add_argument("--no-browser", action="store_true")
    start.set_defaults(fn=cmd_start)
    sub.add_parser("dev", help="run with hot reload").set_defaults(fn=cmd_dev)
    # data/test forward any extra arguments (e.g. `data --mock`, `test -k leakage`).
    passthrough = {"data": cmd_data, "test": cmd_test}
    sub.add_parser("data", help="fetch/refresh datasets (extra args go to the pipeline)")
    sub.add_parser("test", help="run tests (extra args go to pytest)")
    args, rest = parser.parse_known_args()
    if args.command in passthrough:
        args.fn, args.rest = passthrough[args.command], rest
    elif rest:
        parser.error(f"unrecognized arguments: {' '.join(rest)}")
    try:
        args.fn(args)
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)


if __name__ == "__main__":
    main()
