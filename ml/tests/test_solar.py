import numpy as np
import pandas as pd
import pytest

from ml.data import solar

SYD_LAT, SYD_LON = -33.87, 151.21


def noon_elevation(date: str) -> float:
    noon_utc = solar.solar_noon_utc_minutes(pd.DatetimeIndex([date]), SYD_LON)[0]
    ts = pd.DatetimeIndex([pd.Timestamp(date, tz="UTC") + pd.Timedelta(minutes=noon_utc)])
    return float(solar.elevation_deg(ts, SYD_LAT, SYD_LON)[0])


@pytest.mark.parametrize("date, expected", [
    ("2012-12-21", 90 - abs(SYD_LAT + 23.44)),  # summer solstice: 79.6 deg
    ("2012-06-21", 90 - abs(SYD_LAT - 23.44)),  # winter solstice: 32.7 deg
])
def test_noon_elevation_at_solstices(date, expected):
    assert noon_elevation(date) == pytest.approx(expected, abs=0.3)


@pytest.mark.parametrize("date, eot_min", [
    ("2012-11-03", +16.4),  # equation of time at its maximum
    ("2013-02-11", -14.2),  # and at its minimum
])
def test_solar_noon_tracks_equation_of_time(date, eot_min):
    # AEST meridian is 150E; Sydney is 1.21 deg east, so noon comes 4.84 min early.
    expected_aest = 12 * 60 - 4 * (SYD_LON - 150) - eot_min
    got_aest = solar.solar_noon_utc_minutes(pd.DatetimeIndex([date]), SYD_LON)[0] + 600
    assert got_aest == pytest.approx(expected_aest, abs=1.5)


def test_sun_is_down_at_local_midnight():
    ts = pd.date_range("2012-01-01 14:00", periods=365, freq="D", tz="UTC")  # 00:00 AEST
    assert np.all(solar.elevation_deg(ts, SYD_LAT, SYD_LON) < -20)


def test_naive_timestamps_rejected():
    with pytest.raises(ValueError):
        solar.elevation_deg(pd.DatetimeIndex(["2012-01-01"]), SYD_LAT, SYD_LON)
