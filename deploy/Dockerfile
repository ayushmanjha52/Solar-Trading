# The whole interactive market in one image: Python engine + Next.js website.
#   docker build -f deploy/Dockerfile -t local-energy-market .
#   docker run -p 3000:3000 -e LEM_ADMIN_TOKEN=<secret> local-energy-market
# Any single-container host (Render, Railway, Fly, a VM) can run it; it exposes $PORT.
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
# ERA5 is a fixed historical reanalysis, so its 17 responses ship with the repo:
# Open-Meteo can take minutes to answer a cloud builder, and the build should not
# depend on it. The Ausgrid archive (~57 MB, hash-pinned) is still downloaded.
RUN mkdir -p data/raw/weather && tar -xzf deploy/weather-cache.tar.gz -C data/raw/weather
RUN python -m ml.data
# Out-of-sample forecasts for the agents, produced offline by `python -m ml.evaluate`.
RUN cp deploy/forecasts/forecasts_feeder.* data/processed/
RUN cd web && npm run build

ENV PORT=3000 NODE_ENV=production
EXPOSE 3000
CMD ["python", "deploy/start.py"]
