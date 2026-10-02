"""Clock-time to UTC mapping. These encode what Ausgrid's 48-column days mean."""

import numpy as np
import pandas as pd

from ml.data.preprocess import GRID_START, INTERVAL_LABELS, clock_to_grid

HALF_HOUR = pd.Timedelta(minutes=30)


def utc_of(pos: int) -> pd.Timestamp:
    return GRID_START + pos * HALF_HOUR


def test_interval_labels_are_period_ends():
    assert INTERVAL_LABELS[0] == "0:30"
    assert INTERVAL_LABELS[-1] == "0:00"
    assert len(INTERVAL_LABELS) == 48


def test_winter_day_is_aest():
    first, second = clock_to_grid(pd.DatetimeIndex(["2011-07-15"]))
    # Column "0:30" covers 00:00-00:30 AEST = 14:00 UTC the previous day.
    assert utc_of(first[0, 0]) == pd.Timestamp("2011-07-14 14:00", tz="UTC")
    assert np.array_equal(np.diff(first[0]), np.ones(47))
    assert (second == -1).all()


def test_summer_day_is_aedt():
    first, _ = clock_to_grid(pd.DatetimeIndex(["2012-01-15"]))
    # 00:00 AEDT is 13:00 UTC, one hour earlier than in winter.
    assert utc_of(first[0, 0]) == pd.Timestamp("2012-01-14 13:00", tz="UTC")


def test_spring_forward_drops_two_phantom_columns():
    first, second = clock_to_grid(pd.DatetimeIndex(["2011-10-02"]))
    phantom = [INTERVAL_LABELS[k] for k in np.nonzero(first[0] < 0)[0]]
    assert phantom == ["2:30", "3:00"]
    # Real time is continuous across the gap: 01:30-02:00 AEST then 03:00-03:30 AEDT.
    k_before, k_after = INTERVAL_LABELS.index("2:00"), INTERVAL_LABELS.index("3:30")
    assert first[0, k_after] - first[0, k_before] == 1
    assert (second == -1).all()


def test_fall_back_maps_two_columns_to_two_periods_each():
    first, second = clock_to_grid(pd.DatetimeIndex(["2012-04-01"]))
    doubled = [INTERVAL_LABELS[k] for k in np.nonzero(second[0] >= 0)[0]]
    assert doubled == ["2:30", "3:00"]
    k = INTERVAL_LABELS.index("2:30")
    # 02:00 AEDT (15:00 UTC) and 02:00 AEST (16:00 UTC) are one hour apart.
    assert utc_of(first[0, k]) == pd.Timestamp("2012-03-31 15:00", tz="UTC")
    assert utc_of(second[0, k]) == pd.Timestamp("2012-03-31 16:00", tz="UTC")
    # The day has 50 real periods, all distinct.
    real = np.concatenate([first[0], second[0][second[0] >= 0]])
    assert len(np.unique(real)) == 50
    assert np.array_equal(np.sort(real), np.arange(real.min(), real.min() + 50))


def test_midnight_column_joins_the_next_day():
    first, _ = clock_to_grid(pd.DatetimeIndex(["2011-07-15", "2011-07-16"]))
    assert first[1, 0] - first[0, -1] == 1
