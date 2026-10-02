# Deploying

Two things can be deployed, and they are different.

## 1. The recorded replay (one static file)

`deploy/replay/feeder-replay.html` is self-contained: one simulated day recorded
from the engine (clearing, flows, losses, commitments, signed readings,
verification, settlement), replayed on the mimic panel, plus the forecasting and
study results. It needs no server and can be hosted anywhere a file can.

    python -m sim.export_replay --day 2012-11-12

It replays; it does not trade. Nothing on it is typed by hand.

## 2. The interactive market (engine + website)

The live market needs two processes: the Python engine (`sim.api`) and the
Next.js website, which talks to it at `SIM_URL`.

**Any Docker host** (a VM, Render, Railway, Fly):

    docker compose -f deploy/docker-compose.yml up --build

The engine image builds the Ausgrid panel during `docker build` (it downloads the
archive and calls Open-Meteo). Copy `data/processed/forecasts_feeder.parquet` and
`forecasts_feeder.json` into `deploy/forecasts/` first if you want agents to bid
from the learned forecasts; without them they use the seasonal-naive rule.
These files were written for a Docker host and have not been run on the
development machine, which has no Docker.

**Split hosting**: the website on Vercel (set the project root to `web/` and
`SIM_URL` to the engine's public URL) and the engine anywhere that runs a
long-lived Python process with a background thread (not a serverless function:
the engine holds the order book in memory and runs the clock).

**On-chain anchoring** on a public testnet needs an operator key funded with
testnet gas: deploy the contracts with `contracts/script/Deploy.s.sol`, then run
the engine with `LEM_RPC` and `LEM_OPERATOR_KEY` set. See the main README.
