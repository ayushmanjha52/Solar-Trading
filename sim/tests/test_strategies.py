import numpy as np
import pytest

from market.orders import Side, Tariff
from sim import strategies

T = Tariff(feed_in=300, retail=850)


def expected_payoff(contract: float, samples: np.ndarray, price: float, t: Tariff) -> float:
    """Pass 1 + pass 2 for a net contract C against realised net X (Wh x paise/kWh)."""
    dev = samples - contract
    imbalance = np.where(dev > 0, dev * t.feed_in, dev * t.retail)
    market = price * contract if contract > 0 else (price + t.wheeling) * contract
    return float(np.mean(market + imbalance))


@pytest.mark.parametrize("price", [320, 450, 575, 700, 830])
def test_newsvendor_matches_brute_force_optimum(price):
    rng = np.random.default_rng(0)
    samples = rng.normal(400, 250, 200_000)  # uncertain surplus, sometimes negative
    q3 = np.quantile(samples, [0.1, 0.5, 0.9])
    chosen = strategies.newsvendor_position(q3, price, T)
    grid = np.linspace(-200, 900, 1101)
    payoffs = [expected_payoff(c, samples, price, T) for c in grid]
    best = grid[int(np.argmax(payoffs))]
    level = (price - T.feed_in) / (T.retail - T.feed_in)
    if 0.1 <= level <= 0.9:
        # Inside the forecast's quantile range the rule is the optimum, up to interpolation between P10/P50/P90.
        assert abs(chosen - best) < 60
    # Outside it the rule is clamped to the outermost quantile: never further out than the optimum.
    assert expected_payoff(chosen, samples, price, T) >= max(payoffs) - abs(max(payoffs)) * 0.02


def test_mid_band_price_bids_the_median():
    mid = (T.feed_in + T.retail) / 2
    assert strategies.newsvendor_position(np.array([100, 400, 700]), mid, T) == pytest.approx(400)


def test_price_near_feed_in_sells_cautiously():
    assert strategies.newsvendor_position(np.array([100, 400, 700]), 310, T) == pytest.approx(100)


def test_negative_quantile_means_buy():
    assert strategies.newsvendor_position(np.array([-700, -400, -100]), 575, T) == pytest.approx(-400)


def test_truthful_and_shaded_limit_prices():
    assert strategies.limit_price("truthful", Side.SELL, T, 0.3, "k") == T.floor
    assert strategies.limit_price("truthful", Side.BUY, T, 0.3, "k") == T.ceiling
    span = T.ceiling - T.floor
    assert strategies.limit_price("shaded", Side.SELL, T, 0.3, "k") == T.floor + round(0.3 * span)
    assert strategies.limit_price("shaded", Side.BUY, T, 0.3, "k") == T.ceiling - round(0.3 * span)


def test_wheeling_shrinks_what_a_buyer_contracts():
    t = Tariff(300, 850, 200)
    q3 = np.array([-700, -400, -100])
    assert abs(strategies.newsvendor_position(q3, 500, t)) < abs(strategies.newsvendor_position(q3, 500, T))
