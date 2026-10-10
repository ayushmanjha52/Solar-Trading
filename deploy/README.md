# Deploying

The market has two parts: the Python engine, a long-running process that owns
the order book and the clock, and the Next.js website. How it is hosted depends
on whether the host can run the engine.

## 1. Vercel: free, always on, a recorded week

Vercel runs short-lived functions, not long-running processes, so it cannot run
the engine. The website therefore has a hosted mode: `python -m sim.export_hosted`
records seven real days from the engine (every book, clearing, flow, loss,
commitment, 24 signed meter readings and settlement per slot) into
`web/data/hosted/`, and `web/src/lib/hosted.ts` replays them on a loop timed by
the wall clock, answering the same API the engine does. Every visitor sees the
same slot at the same moment, and "Verify in this browser" still checks the
recorded signatures. Placing orders and moving the clock need the engine, and
the hosted copy says so.

Hosted mode switches on by itself on Vercel (it sets `VERCEL=1`), or with
`LEM_HOSTED=1` anywhere else.

One-time setup:

1. Sign in at vercel.com with GitHub.
2. Add New → Project → import **Solar-Trading**.
3. Set **Root Directory** to `web`, and name the project `local-energy-market`.
   Leave everything else as detected (Next.js).
4. Deploy. Every push to `main` redeploys.

The site is then at `https://local-energy-market.vercel.app` (or the name Vercel
gives the project if that one is taken).

Re-record the week after changing the engine or the results:
`python -m sim.export_hosted`. A test (`sim/tests/test_hosted_copies.py`) fails
if the website's copies of `config/` and `reports/` drift from the originals.

## 2. Railway, or any Docker host: the full interactive market

`deploy/Dockerfile` builds one image holding the engine and the website;
`deploy/start.py` runs both (the engine on 127.0.0.1:8000, the website on
`$PORT`). On Railway: New Project → Deploy from GitHub repo → **Solar-Trading**;
`railway.json` points it at the Dockerfile and the health check. Add the variable
`LEM_ADMIN_TOKEN` (a long random value) so only you can move the shared clock.
Railway's free allowance is a trial credit, not a permanent free tier.

Locally: `docker build -f deploy/Dockerfile -t local-energy-market .` then
`docker run -p 3000:3000 -e LEM_ADMIN_TOKEN=<secret> local-energy-market`.

The image ships `deploy/bundle/` (the 24 feeder households over the simulated six
months, all customers' metadata and the out-of-sample forecasts, cut from the
full pipeline by `python -m sim.bundle`, hashed in `manifest.json`) instead of
rebuilding the full panel, which needs gigabytes of memory. Measured in
production mode under load: engine about 165 MB, website about 145 MB. With
`LEM_ADMIN_TOKEN` set, pausing, stepping, changing speed or jumping to another
day needs the token (the Operator button); visitors can still trade, with at
most 300 open orders and 5 per household per slot.

## 3. The recorded replay as one static file

`deploy/replay/feeder-replay.html` is a single self-contained page replaying one
day (`python -m sim.export_replay --day 2012-11-12`). It can be hosted anywhere a
file can.

## On-chain anchoring

Off by default (`LEM_CHAIN=0`). For a public testnet: deploy the contracts with
`contracts/script/Deploy.s.sol` using an operator key funded with testnet gas,
commit `contracts/deployments/<chainid>.json`, and run the engine with
`LEM_CHAIN=1`, `LEM_RPC=<rpc url>` and `LEM_OPERATOR_KEY=<key>`, keeping the key
in the host's secret store. See the main README, "Deploying to Polygon Amoy".
