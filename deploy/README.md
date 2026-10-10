# Deploying

Two things can be deployed, and they are different.

## 1. The recorded replay (one static file)

`deploy/replay/feeder-replay.html` is self-contained: one simulated day recorded
from the engine (clearing, flows, losses, commitments, signed readings,
verification, settlement), replayed on the mimic panel, plus the forecasting and
study results. It needs no server and can be hosted anywhere a file can.

    python -m sim.export_replay --day 2012-11-12

It replays; it does not trade. Nothing on it is typed by hand.

## 2. The interactive market (one container)

`deploy/Dockerfile` builds one image holding the Python engine and the Next.js
website. `deploy/start.py` runs both: the engine on 127.0.0.1:8000, visible only
to the website, and the website on `$PORT`, the one port a host exposes.

    docker build -f deploy/Dockerfile -t local-energy-market .
    docker run -p 3000:3000 -e LEM_ADMIN_TOKEN=<a long random secret> local-energy-market

The image does not rebuild the three-year, 300-household panel: that needs
gigabytes of memory and a slow weather download, too much for a small cloud
builder. It ships `deploy/bundle/` instead, the slice the engine reads (the 24
feeder households over the simulated six months, all customers' metadata, and
the out-of-sample forecasts), cut from the full pipeline by `python -m sim.bundle`
and recorded with SHA-256 hashes in `deploy/bundle/manifest.json`. Rebuilding
everything from the raw archive remains `python -m ml.data`, which CI does on
every push.

Measured on the development machine in production mode, under load from several
pages: engine about 165 MB, Next about 145 MB, so it fits even a 512 MB instance.

**Set `LEM_ADMIN_TOKEN` on any public deployment.** Every visitor shares one
clock. With the token set, pausing, stepping, changing speed or jumping to
another day needs it (the Operator button in the control room); visitors can
still trade. Visitor orders are capped: 300 open in total, 5 per household per
slot.

### Hosted demo: Hugging Face Spaces

The live demo runs as a free Docker Space (2 vCPU, 16 GB, sleeps only after 48
hours without visitors). `.github/workflows/deploy.yml` publishes it on every
push to `main` by running `deploy/hf_space.py`, which stages the tracked files,
puts `deploy/Dockerfile` at the root and adds the Space's settings to the top of
its README. One-time setup:

1. Create a Hugging Face account and a **write** access token
   (Settings → Access Tokens).
2. In this GitHub repository, add it as the Actions secret `HF_TOKEN`
   (Settings → Secrets and variables → Actions). Optionally add a second secret,
   `LEM_ADMIN_TOKEN`, with a long random value: it becomes the operator password.
3. Run the `deploy` workflow once (Actions → deploy → Run workflow), or push.

The Space is created on the first run, at
`https://<username>-local-energy-market.hf.space`.

### Any other Docker host

Railway, Fly, a VM: run the image as one long-running web service. The engine
keeps the order book and three days of history in memory, so it needs one
always-on instance, not a serverless function; a restart restarts the market.
The same image ran on Render's free plan, where it worked but slept after 15
idle minutes and woke slowly on a tenth of a CPU.

## On-chain anchoring

Off by default in the container (`LEM_CHAIN=0`). For a public testnet: deploy the
contracts with `contracts/script/Deploy.s.sol` using an operator key funded with
testnet gas, commit `contracts/deployments/<chainid>.json`, and run the container
with `LEM_CHAIN=1`, `LEM_RPC=<rpc url>` and `LEM_OPERATOR_KEY=<key>` (keep the key
in the host's secret store). See the main README, "Deploying to Polygon Amoy".
