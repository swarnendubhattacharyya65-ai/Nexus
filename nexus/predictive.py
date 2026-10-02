"""NEXUS Predictive Intelligence: daily energy forecasts, tested on history.

Two simple, transparent methods forecast each building's daily kWh 14 days ahead:
  - Naive: the same weekday from the most recent week before the forecast date.
  - Calendar: the median of recent days of the same day type (semester weekday,
    break weekday, Saturday, Sunday or holiday), using the institute calendar,
    which is published in advance.
Each building uses whichever method was more accurate before the last full year of
data (late 2013 to 2016 for IIIT-Delhi). That choice is then tested on the last year (2017),
which it never saw.

Print the evaluation:   python -m nexus.predictive
"""
import numpy as np
import pandas as pd

from nexus.data import ENERGY_WARNINGS, OUT

HORIZON = 14                       # days ahead
STEP = 7                           # backtest: a new forecast every 7 days
RECENT = (28, 56)                  # look back this far for the same day type
MIN_SAME_TYPE = 2                  # recent days of the same type needed
WARM_UP = 56                       # days of history before the first forecast
TEST_FROM = pd.Timestamp("2017-01-01")   # IIIT-Delhi; other colleges: see test_start()
BAND = (0.10, 0.90)                # the 80% range around a forecast
MIN_TEST_DAYS = 100                # fewer test days -> "insufficient data"
METHODS = {"naive": "Same weekday last week", "calendar": "Calendar day type"}


def daily_energy(ds=None):
    """Daily kWh per building, complete days only (all 24 hours measured)."""
    e = pd.read_parquet(OUT / "energy_hourly.parquet") if ds is None else ds.energy
    unreliable = ENERGY_WARNINGS if ds is None else ds.warnings
    e = e[~e["building"].isin(unreliable)].dropna(subset=["kwh"])
    e["date"] = e["hour"].dt.normalize()
    d = e.groupby(["building", "date"])["kwh"].agg(["sum", "count"]).reset_index()
    return d[d["count"] == 24].drop(columns="count").rename(columns={"sum": "kwh"})


def day_types(ds=None):
    """Each calendar date's day type."""
    cal = pd.read_parquet(OUT / "calendar.parquet") if ds is None else ds.calendar
    working = cal["working_day"].astype(bool)
    kind = np.select(
        [working & (cal["activity"] == "high"), working, cal["date"].dt.dayofweek == 5],
        ["Semester weekday", "Break weekday", "Saturday"], "Sunday or holiday")
    return pd.Series(kind, index=cal["date"])


class _History:
    """One building's past days as sorted arrays, so forecasts are fast."""

    def __init__(self, series, types):
        s = series.sort_index()
        self.dates = s.index.to_numpy()
        self.weekdays = s.index.dayofweek.to_numpy()
        self.values = s.to_numpy()
        self.kinds = types.reindex(s.index).to_numpy()
        self.lookup = dict(zip(s.index, s.to_numpy()))
        self.types = dict(zip(types.index, types.to_numpy()))

    def forecast(self, origin):
        """Both methods for `origin` and the 13 days after it, from earlier days only."""
        end = np.searchsorted(self.dates, np.datetime64(origin))

        def start(days):
            return np.searchsorted(self.dates, np.datetime64(origin - pd.Timedelta(days=days)))

        # Naive: the latest value of each weekday in the last 4 weeks.
        naive_by_weekday = dict(zip(self.weekdays[start(28):end], self.values[start(28):end]))

        # Calendar: median of the same day type, looking back further only if needed.
        calendar_by_type = {}
        for back in RECENT:
            k, v = self.kinds[start(back):end], self.values[start(back):end]
            for kind in set(k) - set(calendar_by_type):
                same = v[k == kind]
                if len(same) >= MIN_SAME_TYPE:
                    calendar_by_type[kind] = float(np.median(same))

        days = [origin + pd.Timedelta(days=i) for i in range(HORIZON)]
        kinds = [self.types.get(d) for d in days]
        naive = [naive_by_weekday.get(d.dayofweek, np.nan) for d in days]
        calendar = [calendar_by_type.get(k, n) for k, n in zip(kinds, naive)]  # else naive
        actual = [self.lookup.get(d, np.nan) for d in days]
        return days, kinds, naive, calendar, actual


def forecast(series, types, origin):
    """One forecast as a table: both methods, day type and (if known) the actual."""
    days, kinds, naive, calendar, actual = _History(series, types).forecast(origin)
    return pd.DataFrame({"date": days, "day_type": kinds, "naive": naive,
                         "calendar": calendar, "actual": actual})


def backtest(daily, types):
    """Forecast every 7 days through history and keep what actually happened."""
    cols = {k: [] for k in ["building", "origin", "horizon", "date", "day_type",
                            "naive", "calendar", "actual"]}
    for building, g in daily.groupby("building"):
        history = _History(g.set_index("date")["kwh"], types)
        first, last = history.dates[0], history.dates[-1]
        for origin in pd.date_range(pd.Timestamp(first) + pd.Timedelta(days=WARM_UP),
                                    pd.Timestamp(last), freq=f"{STEP}D"):
            days, kinds, naive, calendar, actual = history.forecast(origin)
            cols["building"] += [building] * HORIZON
            cols["origin"] += [origin] * HORIZON
            cols["horizon"] += list(range(1, HORIZON + 1))
            cols["date"] += days
            cols["day_type"] += kinds
            cols["naive"] += naive
            cols["calendar"] += calendar
            cols["actual"] += actual
    return pd.DataFrame(cols).dropna(subset=["actual", "naive", "calendar"])


def test_start(bt):
    """Start of the test year: the last calendar year with forecasts, if earlier years exist.

    For IIIT-Delhi this is 1 Jan 2017 (method chosen on 2013-2016, scored on 2017).
    """
    if bt.empty:
        return TEST_FROM
    start = pd.Timestamp(year=bt["origin"].max().year, month=1, day=1)
    return start if bt["origin"].min() < start else TEST_FROM


def periods(bt):
    """Plain labels for the training and test periods, e.g. ("2013-2016", "2017")."""
    start = test_start(bt)
    first = bt["origin"].min().year if not bt.empty else start.year - 1
    train = f"{first}" if first == start.year - 1 else f"{first}-{start.year - 1}"
    return train, f"{start.year}"


def evaluate(bt):
    """Per building: choose a method on the earlier years, then score it on the last year."""
    rows = []
    split = test_start(bt)
    train_label, test_label = periods(bt)
    for building, g in bt.groupby("building"):
        train, test = g[g["origin"] < split], g[g["origin"] >= split]
        if len(test) < MIN_TEST_DAYS or len(train) < MIN_TEST_DAYS:
            rows.append({"building": building, "test_days": len(test),
                         "train_period": train_label, "test_period": test_label,
                         "note": f"Insufficient data: fewer than {MIN_TEST_DAYS} forecast days to test"})
            continue

        def mae(df, method):
            return (df[method] - df["actual"]).abs().mean()

        method = "calendar" if mae(train, "calendar") < mae(train, "naive") else "naive"
        ratio = (train["actual"] - train[method]) / train[method]
        low, high = ratio.quantile(BAND[0]), ratio.quantile(BAND[1])
        in_band = test["actual"].between(test[method] * (1 + low), test[method] * (1 + high))
        rows.append({
            "building": building,
            "method": method,
            "test_days": len(test),
            "mae_naive": mae(test, "naive"),
            "mae_calendar": mae(test, "calendar"),
            "error_pct": mae(test, method) / test["actual"].mean(),
            "skill": 1 - mae(test, method) / mae(test, "naive"),
            "band_low": low,
            "band_high": high,
            "band_coverage": in_band.mean(),
            "train_period": train_label,
            "test_period": test_label,
            "note": "",
        })
    return pd.DataFrame(rows)


def main():
    daily, types = daily_energy(), day_types()
    ev = evaluate(backtest(daily, types))
    train, test = (ev["train_period"].iloc[0], ev["test_period"].iloc[0]) if len(ev) else ("-", "-")
    print(f"BACKTEST  {HORIZON}-day forecasts every {STEP} days; method chosen on {train}, "
          f"scored on {test}")
    print(f"  {'building':12}{'method':>10}{'forecasts':>10}{'naive MAE':>11}{'calendar MAE':>14}"
          f"{'error':>8}{'vs naive':>10}{'80% band hit':>14}")
    for r in ev.itertuples():
        if r.note:
            print(f"  {r.building:12}  {r.note}")
            continue
        print(f"  {r.building:12}{r.method:>10}{r.test_days:>10,}{r.mae_naive:>11.0f}"
              f"{r.mae_calendar:>14.0f}{r.error_pct:>8.0%}{r.skill:>+10.0%}{r.band_coverage:>14.0%}")
    print(f"\n  forecasts = forecast days scored in {test} (each day is forecast twice: 1-7 and 8-14 days ahead).")
    print("  MAE = average miss in kWh per day. error = MAE as % of the average day.")
    print("  vs naive = how much smaller the error is than 'same weekday last week'.")


if __name__ == "__main__":
    main()
