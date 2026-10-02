import numpy as np
import pandas as pd
import pytest

from ml.features import build_features as bf

N = 48 * 30


@pytest.fixture(scope="module")
def setup():
    rng = np.random.default_rng(1)
    ts = pd.date_range("2012-10-01", periods=N, freq="30min", tz="UTC")
    load = rng.uniform(100, 900, N).round()
    gen = np.clip(np.sin(np.linspace(0, 30 * np.pi, N)), 0, None) * 800
    s = bf.Series(load, gen.round(), 1.5)
    return s, bf.calendar(ts), bf.sun_elevation(ts, -33.8, 151.2)


def test_features_use_only_data_up_to_t_minus_2(setup):
    s, cal, sun = setup
    bf.assert_causal(s, cal, sun, targets=np.array([400, 700, 1000, 1400]))


def test_the_check_catches_a_leaky_feature(setup, monkeypatch):
    """A feature built from the target slot itself must fail the build."""
    s, cal, sun = setup
    real = bf.features

    def leaky(series, *a, **k):
        f = real(series, *a, **k)
        f["net_l2"] = bf.shift(series.net_wh.astype(float), 1)  # t-1: one slot the forecaster cannot see
        return f

    monkeypatch.setattr(bf, "features", leaky)
    with pytest.raises(AssertionError, match="net_l2.*lookahead"):
        bf.assert_causal(s, cal, sun, targets=np.array([700]))


def test_lags_are_the_right_slots(setup):
    s, cal, sun = setup
    f = bf.features(s, cal, sun)
    t = 800
    assert f["net_l2"][t] == s.net_wh[t - 2]
    assert f["net_l48"][t] == s.net_wh[t - 48]
    assert f["net_mean6"][t] == pytest.approx(s.net_wh[t - 7:t - 1].mean())
    assert f["net_slot_mean7"][t] == pytest.approx(np.mean([s.net_wh[t - 48 * k] for k in range(1, 8)]))


def test_sequence_window_ends_at_t_minus_2(setup):
    s, _, _ = setup
    seq = bf.sequences(s, np.array([500]))
    assert seq.shape == (1, bf.SEQ_LEN, 3)
    assert seq[0, -1, 0] == pytest.approx(s.net_wh[498] / 1000)
