"""Solar geometry (NOAA general solar position equations).

Accurate to roughly a minute in solar noon and a few tenths of a degree in
elevation, which is ample for half-hour data. Used to
  * define "night" when checking that generation is zero,
  * give the solar-noon reference the time-base check compares against,
  * later, build clear-sky features for the PV forecaster.
"""

import numpy as np
import pandas as pd


def _fractional_year(ts_utc: pd.DatetimeIndex) -> np.ndarray:
    days_in_year = np.where(ts_utc.is_leap_year, 366.0, 365.0)
    hours = ts_utc.hour + ts_utc.minute / 60 + ts_utc.second / 3600
    return 2 * np.pi / days_in_year * (ts_utc.dayofyear - 1 + (hours - 12) / 24)


def _eqtime_decl(g: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    eqtime = 229.18 * (
        0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
        - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g)
    )
    decl = (
        0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g)
        - 0.006758 * np.cos(2 * g) + 0.000907 * np.sin(2 * g)
        - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g)
    )
    return eqtime, decl


def elevation_deg(ts_utc: pd.DatetimeIndex, lat: float | np.ndarray, lon: float | np.ndarray) -> np.ndarray:
    """Solar elevation angle in degrees at each UTC instant."""
    ts_utc = pd.DatetimeIndex(ts_utc)
    if ts_utc.tz is None:
        raise ValueError("timestamps must be tz-aware UTC")
    ts_utc = ts_utc.tz_convert("UTC")
    eqtime, decl = _eqtime_decl(_fractional_year(ts_utc))
    minutes = ts_utc.hour * 60 + ts_utc.minute + ts_utc.second / 60
    true_solar_min = minutes + eqtime + 4 * np.asarray(lon)
    hour_angle = np.radians(true_solar_min / 4 - 180)
    phi = np.radians(np.asarray(lat))
    cos_zen = np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(hour_angle)
    return np.asarray(90 - np.degrees(np.arccos(np.clip(cos_zen, -1, 1))), dtype=np.float64)


def solar_noon_utc_minutes(dates: pd.DatetimeIndex, lon: float) -> np.ndarray:
    """Minutes after 00:00 UTC at which the sun transits, for each calendar date."""
    dates = pd.DatetimeIndex(dates)
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    noon = dates.normalize().tz_localize("UTC") + pd.Timedelta(hours=12)
    eqtime, _ = _eqtime_decl(_fractional_year(noon))
    return np.asarray(720 - 4 * lon - eqtime, dtype=np.float64)
