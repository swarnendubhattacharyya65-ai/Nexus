"""NEXUS Resource Intelligence: energy baselines and unusual consumption.

Works on the small hourly tables in data/processed/, so it also runs in the
deployed app. Nothing here invents a number: every flag comes with the
actual value, the expected value and how many comparable hours it used.

Print a summary:   python -m nexus.resource
"""
import pandas as pd

from nexus.data import ENERGY_WARNINGS, OUT

WINDOW = "42D"      # compare with 3 weeks either side of each hour
MIN_SAMPLES = 8     # needs at least 8 comparable hours, otherwise no baseline
Z_LIMIT = 3.5       # how far outside normal variation counts as unusual
MIN_CHANGE = 0.10   # ...and it must also be at least 10% away from expected
MIN_SPREAD = 0.1    # kWh; stops perfectly steady hours from dividing by zero


def load_energy():
    """Hourly kWh per building joined with that day's calendar."""
    energy = pd.read_parquet(OUT / "energy_hourly.parquet")
    cal = pd.read_parquet(OUT / "calendar.parquet")
    energy["date"] = energy["hour"].dt.normalize()
    return energy.merge(cal, on="date", how="left")


def add_baseline(energy):
    """Add the expected kWh for every hour, and flag hours far from it.

    Expected = the median of comparable hours within 3 weeks either side.
    Comparable = same building, same hour of day, same day type (working or
    not) and same academic activity (high or low). The interquartile range
    of those hours measures how much they normally vary.

    Looking both ways cancels out slow seasonal change (summer cooling ramps
    up for weeks), which suits analysing history. A live system could only
    look back, so it would need a weather adjustment instead.
    """
    df = energy.dropna(subset=["kwh"]).copy()
    df["hour_of_day"] = df["hour"].dt.hour
    df = df.sort_values("hour")

    keys = ["building", "hour_of_day", "working_day", "activity"]
    parts = []
    for _, g in df.groupby(keys, dropna=False):
        near = g.set_index("hour")["kwh"].rolling(WINDOW, center=True)
        parts.append(g.assign(
            expected=near.median().to_numpy(),
            low=near.quantile(0.25).to_numpy(),
            high=near.quantile(0.75).to_numpy(),
            samples=near.count().to_numpy(),
        ))
    df = pd.concat(parts).sort_values(["building", "hour"], ignore_index=True)

    spread = ((df["high"] - df["low"]) / 1.349).clip(lower=MIN_SPREAD)
    df["z"] = (df["kwh"] - df["expected"]) / spread
    change = (df["kwh"] - df["expected"]) / df["expected"]
    has_baseline = df["samples"] >= MIN_SAMPLES

    df["flag"] = "normal"
    df.loc[has_baseline & (df["z"] >= Z_LIMIT) & (change >= MIN_CHANGE), "flag"] = "high"
    df.loc[has_baseline & (df["z"] <= -Z_LIMIT) & (change <= -MIN_CHANGE), "flag"] = "low"
    df.loc[~has_baseline, "flag"] = "no baseline"
    df.loc[df["building"].isin(ENERGY_WARNINGS), "flag"] = "unreliable meter"
    return df


def find_events(df):
    """Join back-to-back unusual hours into events, biggest difference first."""
    flagged = df[df["flag"].isin(["high", "low"])].copy()
    new_event = ((flagged["building"] != flagged["building"].shift())
                 | (flagged["flag"] != flagged["flag"].shift())
                 | (flagged["hour"].diff() != pd.Timedelta("1h")))
    flagged["event"] = new_event.cumsum()
    events = flagged.groupby("event").agg(
        building=("building", "first"),
        direction=("flag", "first"),
        start=("hour", "min"),
        end=("hour", "max"),
        hours=("hour", "size"),
        actual_kwh=("kwh", "sum"),
        expected_kwh=("expected", "sum"),
        samples=("samples", "min"),
        activity=("activity", "first"),
    )
    events["end"] = events["end"] + pd.Timedelta("1h")
    events["extra_kwh"] = events["actual_kwh"] - events["expected_kwh"]
    events["extra_pct"] = events["extra_kwh"] / events["expected_kwh"]
    return events.sort_values("extra_kwh", key=abs, ascending=False, ignore_index=True)


def main():
    df = add_baseline(load_energy())
    events = find_events(df)

    print("BASELINE  same hour of day, day type and activity, 3 weeks either side")
    print(f"  {'building':12}{'has baseline':>13}{'high hrs':>10}{'low hrs':>9}"
          f"{'high events':>13}{'low events':>12}")
    for building, g in df.groupby("building"):
        ev = events[events["building"] == building]
        print(f"  {building:12}{g['flag'].isin(['normal', 'high', 'low']).mean():>13.1%}"
              f"{(g['flag'] == 'high').sum():>10,}{(g['flag'] == 'low').sum():>9,}"
              f"{(ev['direction'] == 'high').sum():>13,}{(ev['direction'] == 'low').sum():>12,}")

    print("\nTOP 10 HIGHER-THAN-USUAL EVENTS (by extra kWh)")
    print(f"  {'building':12}{'start':17}{'hours':>5}{'actual':>9}{'expected':>10}"
          f"{'extra':>8}{'extra %':>9}")
    for _, e in events[events["direction"] == "high"].head(10).iterrows():
        print(f"  {e['building']:12}{e['start']:%Y-%m-%d %H:%M} {e['hours']:>5}"
              f"{e['actual_kwh']:>9.0f}{e['expected_kwh']:>10.0f}{e['extra_kwh']:>8.0f}"
              f"{e['extra_pct']:>9.0%}")
    for building, why in ENERGY_WARNINGS.items():
        print(f"\n  {building} not analysed: {why}")


if __name__ == "__main__":
    main()
