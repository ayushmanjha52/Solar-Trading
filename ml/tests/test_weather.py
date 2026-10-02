import numpy as np
import pandas as pd
import pytest

from ml import config
from ml.data.weather import cell_of, to_half_hours


def fake_response(hours: pd.DatetimeIndex) -> dict:
    n = len(hours)
    hourly = {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in hours]}
    for var in config.WEATHER_HOURLY_MEAN_VARS + config.WEATHER_HOURLY_INSTANT_VARS:
        hourly[var] = list(np.arange(n, dtype=float) * 10)  # value stamped T is 10 * index
    return {"hourly": hourly, "latitude": -33.75, "longitude": 151.25}


def test_hourly_means_cover_the_preceding_hour():
    hours = pd.date_range("2012-01-01 00:00", periods=6, freq="h", tz="UTC")
    grid = pd.date_range("2012-01-01 01:00", periods=4, freq="30min", tz="UTC")
    out = to_half_hours(fake_response(hours), grid)
    # Periods 01:00-01:30 and 01:30-02:00 both lie inside the hour stamped 02:00 (index 2).
    assert out["shortwave_radiation"].tolist() == [20, 20, 30, 30]


def test_instant_variables_interpolate_to_period_midpoint():
    hours = pd.date_range("2012-01-01 00:00", periods=6, freq="h", tz="UTC")
    grid = pd.date_range("2012-01-01 01:00", periods=2, freq="30min", tz="UTC")
    out = to_half_hours(fake_response(hours), grid)
    # Midpoints 01:15 and 01:45 sit a quarter and three quarters between 10 and 20.
    assert out["temperature_2m"].tolist() == pytest.approx([12.5, 17.5])


def test_grid_outside_weather_coverage_fails():
    hours = pd.date_range("2012-01-01 00:00", periods=3, freq="h", tz="UTC")
    grid = pd.date_range("2012-01-01 02:00", periods=2, freq="30min", tz="UTC")
    with pytest.raises(RuntimeError):
        to_half_hours(fake_response(hours), grid)


def test_cell_snaps_to_quarter_degree():
    assert cell_of(-33.8878, 151.1964) == "-34.00_151.25"  # 0.112 deg from -34.00, 0.138 from -33.75
    assert cell_of(-33.80, 151.20) == "-33.75_151.25"
    assert cell_of(-32.93, 151.70) == "-33.00_151.75"
