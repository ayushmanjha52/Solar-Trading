# Unix entry points. On Windows without make, run the same commands directly
# (see README): python demo.py, python -m pytest, forge test.

PY ?= .venv/bin/python

.PHONY: setup data test demo

setup:
	python3.11 -m venv .venv
	$(PY) -m pip install -r sim/requirements.txt pytest==8.3.4
	cd web && npm install --no-audit --no-fund

data:
	$(PY) -m ml.data

test:
	$(PY) -m pytest ml market sim -q
	cd contracts && forge test
	cd web && npx tsc --noEmit && npx next lint

demo:
	$(PY) demo.py
