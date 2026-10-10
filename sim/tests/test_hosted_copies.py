"""The hosted website ships copies of files that live outside web/. They must not drift."""

import json

import pytest

from ml import config as ml_config

ROOT = ml_config.ROOT
STATIC = ROOT / "web" / "data" / "static"
PAIRS = [
    ("config/market.json", "market.json"),
    ("reports/forecasting/results.json", "forecasting.json"),
    ("reports/study/results.json", "study.json"),
]


@pytest.mark.parametrize("original, copy", PAIRS)
def test_static_copy_matches_original(original, copy):
    a = json.loads((ROOT / original).read_text(encoding="utf-8"))
    b = json.loads((STATIC / copy).read_text(encoding="utf-8"))
    assert a == b, f"web/data/static/{copy} is stale: run python -m sim.export_hosted"


def test_recorded_week_is_complete_and_verified():
    index = json.loads((ROOT / "web" / "data" / "hosted" / "index.json").read_text(encoding="utf-8"))
    for day in index["days"]:
        d = json.loads((ROOT / "web" / "data" / "hosted" / "days" / f"{day}.json").read_text(encoding="utf-8"))
        assert [s["slot"] for s in d["slots"]] == list(range(1, 49))
        assert all(s["verification"]["verified"] and len(s["readings"]) == 24 for s in d["slots"])
        assert len(d["households"]) == 24
