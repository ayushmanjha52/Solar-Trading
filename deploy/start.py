"""Run the engine and the website in one container (or one process group anywhere).

    PORT=3000 LEM_ADMIN_TOKEN=... python deploy/start.py

The engine listens on 127.0.0.1:8000, reachable only by the website; the
website listens on $PORT (default 3000), the one port a host exposes. If
either process exits, the other is stopped and the container exits, so the
host's restart policy brings both back together.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    port = os.environ.get("PORT", "3000")
    if not os.environ.get("LEM_ADMIN_TOKEN"):
        print("start  warning: LEM_ADMIN_TOKEN is not set, so any visitor can pause or reset the shared clock",
              flush=True)
    engine = subprocess.Popen(
        [sys.executable, "-c", "import uvicorn; uvicorn.run('sim.api:app', host='127.0.0.1', port=8000, "
                               "log_level='warning')"],
        cwd=ROOT, env={**os.environ, "LEM_CHAIN": os.environ.get("LEM_CHAIN", "0")},
    )
    for _ in range(240):
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/api/clock", timeout=2)
            break
        except Exception:
            if engine.poll() is not None:
                print("start  the engine exited during startup", flush=True)
                return 1
            time.sleep(0.5)
    print("start  engine ready on 127.0.0.1:8000", flush=True)

    # Start Next directly, not through npm: the npm wrapper process alone costs ~70 MB,
    # which matters on a 512 MB instance (measured: engine ~165 MB, Next ~145 MB).
    node = shutil.which("node") or "node"
    web = subprocess.Popen([node, "node_modules/next/dist/bin/next", "start", "-p", port, "-H", "0.0.0.0"],
                           cwd=ROOT / "web", env={**os.environ, "SIM_URL": "http://127.0.0.1:8000"})
    print(f"start  website on :{port}", flush=True)

    def stop(*_):
        for p in (web, engine):
            if p.poll() is None:
                p.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while engine.poll() is None and web.poll() is None:
            time.sleep(1)
    finally:
        stop()
    return 1


if __name__ == "__main__":
    sys.exit(main())
