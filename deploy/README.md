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

The image builds the Ausgrid panel during `docker build` (network needed; the
~57 MB archive is downloaded and hash-checked). The ERA5 weather responses ship
in `deploy/weather-cache.tar.gz`, because Open-Meteo can take many minutes to
answer a cloud builder; the out-of-sample forecasts come from `deploy/forecasts/`.

**Set `LEM_ADMIN_TOKEN` on any public deployment.** Every visitor shares one
clock. With the token set, pausing, stepping, changing speed or jumping to
another day needs it (the Operator button in the control room); visitors can
still trade. Visitor orders are capped: 300 open in total, 5 per household per
slot.

**Render**: the repository has a Blueprint (`render.yaml`). In the Render
dashboard choose New → Blueprint and pick this repository; it creates the web
service from `deploy/Dockerfile` with a generated `LEM_ADMIN_TOKEN` (shown in the
service's Environment tab). The first build takes several minutes because it
builds the data panel.

Any other host that runs a Docker image as a web service works too: Railway,
Fly, or a VM. The engine keeps the order book and three days of history in memory,
so give it one long-running instance, not a serverless function; a restart
restarts the market.

`deploy/start.py` was tested on the development machine in production mode
(port 3100, operator token set). The Dockerfile itself has not been built there,
because that machine has no Docker.

## On-chain anchoring

Off by default in the container (`LEM_CHAIN=0`). For a public testnet: deploy the
contracts with `contracts/script/Deploy.s.sol` using an operator key funded with
testnet gas, commit `contracts/deployments/<chainid>.json`, and run the container
with `LEM_CHAIN=1`, `LEM_RPC=<rpc url>` and `LEM_OPERATOR_KEY=<key>` (keep the key
in the host's secret store). See the main README, "Deploying to Polygon Amoy".
