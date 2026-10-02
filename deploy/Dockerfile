# The whole interactive market in one image: Python engine + Next.js website.
#   docker build -f deploy/Dockerfile -t local-energy-market .
#   docker run -p 3000:3000 -e LEM_ADMIN_TOKEN=<secret> local-energy-market
# Sized for a small instance (512 MB): the image ships the engine's data slice
# (deploy/bundle, cut from the full pipeline by `python -m sim.bundle`) instead of
# rebuilding the three-year, 300-household panel during the build.
FROM node:20-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH" PYTHONUNBUFFERED=1

WORKDIR /app
COPY deploy/requirements-engine.txt deploy/requirements-engine.txt
RUN pip install --no-cache-dir -r deploy/requirements-engine.txt

COPY web/package.json web/package-lock.json web/
RUN cd web && npm ci

COPY . .
RUN mkdir -p data/processed && cp deploy/bundle/*.parquet deploy/bundle/forecasts_feeder.json data/processed/
RUN cd web && npm run build && npm prune --omit=dev

# Keep Node's heap well inside a 512 MB instance alongside the Python engine.
ENV PORT=3000 NODE_ENV=production NODE_OPTIONS=--max-old-space-size=192
EXPOSE 3000
CMD ["python", "deploy/start.py"]
