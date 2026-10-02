"""Run the whole thing: data, chain, market engine, website.

    python demo.py              # Windows: .venv\\Scripts\\python demo.py
    python demo.py --no-chain   # skip Anvil; settlement is verified off-chain only
    python demo.py --prod       # production build of the website instead of dev mode

Then open http://localhost:3000. Ctrl+C stops everything this script started.
Standard library only, so it runs before anything else is installed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ANVIL_KEY_0 = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"  # public Anvil test key
CHILDREN: list[subprocess.Popen] = []


def say(msg: str) -> None:
    print(f"demo  {msg}", flush=True)


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for(url: str, seconds: float, what: str) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit(f"{what} did not come up at {url} within {seconds:.0f}s")


def spawn(cmd: list[str], cwd: Path, env: dict | None = None, log: str | None = None) -> subprocess.Popen:
    out = open(ROOT / ".demo-logs" / log, "w") if log else subprocess.DEVNULL
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    p = subprocess.Popen(cmd, cwd=cwd, env={**os.environ, **(env or {})}, stdout=out, stderr=subprocess.STDOUT,
                         creationflags=flags, start_new_session=os.name != "nt")
    CHILDREN.append(p)
    return p


def stop_all() -> None:
    for p in reversed(CHILDREN):
        if p.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
            else:
                os.killpg(p.pid, signal.SIGTERM)


def foundry(tool: str) -> str | None:
    found = shutil.which(tool)
    if found:
        return found
    local = Path.home() / ".foundry" / "bin" / (tool + (".exe" if os.name == "nt" else ""))
    return str(local) if local.exists() else None


def ensure_data() -> None:
    if (ROOT / "data" / "processed" / "panel.parquet").exists():
        say("data      panel present")
        return
    say("data      building the Ausgrid panel (downloads ~57 MB the first time)")
    subprocess.run([sys.executable, "-m", "ml.data"], cwd=ROOT, check=True)


def ensure_chain() -> bool:
    anvil, forge = foundry("anvil"), foundry("forge")
    if not anvil or not forge:
        say("chain     Foundry not found; running without a chain (https://book.getfoundry.sh)")
        return False
    fresh = False
    if not port_open(8545):
        say("chain     starting Anvil on :8545")
        spawn([anvil, "--port", "8545", "--silent"], ROOT, log="anvil.log")
        for _ in range(40):
            if port_open(8545):
                break
            time.sleep(0.25)
        fresh = True
    dep = ROOT / "contracts" / "deployments" / "31337.json"
    if fresh or not dep.exists() or not has_code(json.loads(dep.read_text())["market"]):
        say("chain     deploying MeterRegistry and EnergyMarket")
        (ROOT / "contracts" / "deployments").mkdir(exist_ok=True)
        subprocess.run([forge, "script", "script/Deploy.s.sol", "--rpc-url", "http://127.0.0.1:8545",
                        "--broadcast", "--private-key", ANVIL_KEY_0], cwd=ROOT / "contracts", check=True,
                       capture_output=True)
    say(f"chain     contracts at {json.loads(dep.read_text())['market']} (chain 31337)")
    return True


def has_code(address: str) -> bool:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getCode", "params": [address, "latest"]}).encode()
    req = urllib.request.Request("http://127.0.0.1:8545", data=body, headers={"content-type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=3).read())["result"] not in ("0x", "0x0")
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-chain", action="store_true")
    ap.add_argument("--prod", action="store_true")
    args = ap.parse_args()
    (ROOT / ".demo-logs").mkdir(exist_ok=True)

    try:
        ensure_data()
        chain = False if args.no_chain else ensure_chain()

        if port_open(8000):
            raise SystemExit("port 8000 is busy; stop the other market engine first")
        say("engine    starting the market engine on :8000")
        spawn([sys.executable, "-m", "sim.api"], ROOT, env={"LEM_CHAIN": "1" if chain else "0"}, log="engine.log")
        wait_for("http://127.0.0.1:8000/api/clock", 120, "the market engine")

        npm = shutil.which("npm")
        if not npm:
            raise SystemExit("npm not found; install Node.js 18 or newer")
        web = ROOT / "web"
        if not (web / "node_modules").exists():
            say("web       installing packages (first run only)")
            subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=web, check=True)
        if args.prod:
            say("web       building for production")
            subprocess.run([npm, "run", "build"], cwd=web, check=True)
        say("web       starting the website on :3000")
        spawn([npm, "run", "start" if args.prod else "dev"], web, log="web.log")
        wait_for("http://localhost:3000/api/clock", 180, "the website")

        say("ready     open http://localhost:3000   (logs in .demo-logs/, Ctrl+C to stop)")
        while all(p.poll() is None for p in CHILDREN):
            time.sleep(1)
        say("a process exited; see .demo-logs/")
    except KeyboardInterrupt:
        pass
    finally:
        stop_all()
        say("stopped")


if __name__ == "__main__":
    main()
