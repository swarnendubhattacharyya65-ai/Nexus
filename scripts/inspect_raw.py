"""Inspect the raw I-BLEND files and print a one-screen summary.

Read-only: it never changes anything in data/raw.
Run it from the repo root:   python scripts/inspect_raw.py
"""
from pathlib import Path

import pandas as pd

RAW = Path("data/raw")
TZ = "Asia/Kolkata"  # the dataset's Readme says timestamps are Unix seconds, IST


def to_local(seconds):
    """Unix seconds -> IIIT-Delhi local time (no timezone label attached)."""
    utc = pd.to_datetime(seconds, unit="s", utc=True)
    return utc.dt.tz_convert(TZ).dt.tz_localize(None)


def summarize(path, value_col, step):
    """One line per file: size, date range, gaps, duplicates and value range."""
    cols = pd.read_csv(path, nrows=0).columns.tolist()
    if "timestamp" not in cols or value_col not in cols:
        return f"{path.name:28} SKIPPED, columns are: {cols}"

    df = pd.read_csv(path, usecols=["timestamp", value_col], low_memory=False)
    if df.empty:
        return f"{path.name:28} EMPTY FILE"

    t = to_local(df["timestamp"])
    v = pd.to_numeric(df[value_col], errors="coerce")  # text -> blank, never crashes
    expected = int((t.max() - t.min()) / pd.Timedelta(step)) + 1
    missing = 1 - t.nunique() / expected

    return (
        f"{path.name:28}{len(df):>10,}  {t.min():%Y-%m-%d} {t.max():%Y-%m-%d}"
        f"{missing:>7.1%}{t.duplicated().sum():>6}{v.isna().sum():>7}"
        f"{v.min():>9.0f}{v.median():>9.0f}{v.max():>9.0f}"
    )


def table(title, folder, value_col, step):
    print(f"\n{title}")
    print(f"{'file':28}{'rows':>10}  {'first':10} {'last':10}"
          f"{'gaps':>7}{'dupes':>6}{'blank':>7}{'min':>9}{'median':>9}{'max':>9}")
    files = sorted((RAW / folder).glob("*.csv"))
    for path in files:
        print(summarize(path, value_col, step))
    return files


def main():
    energy = table("ENERGY  (1-minute readings, power in watts)",
                   "energy_dataset", "power", "1min")
    occupancy = table("OCCUPANCY  (10-minute Wi-Fi device counts)",
                      "IIITD_occupancy_dataset", "occupancy_count", "10min")

    print("\nCOLUMNS")
    if energy:
        print("energy:   ", pd.read_csv(energy[0], nrows=0).columns.tolist())
    if occupancy:
        print("occupancy:", pd.read_csv(occupancy[0], nrows=0).columns.tolist())

    print("\nCALENDAR")
    calendar = sorted((RAW / "iiitd_calender_schedule").glob("*.csv"))
    for path in calendar:
        print(f"{path.name:28}{len(pd.read_csv(path)):>5} rows")
    if calendar:
        print(pd.read_csv(calendar[0]).head(3).to_string(index=False))


if __name__ == "__main__":
    main()
