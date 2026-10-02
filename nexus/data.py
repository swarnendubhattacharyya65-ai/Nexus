"""NEXUS data layer for the I-BLEND public dataset (IIIT-Delhi, 2013-2017).

Reads the raw minute-level files in data/raw/ (1.6 GB, never committed) and
writes small, clean hourly tables to data/processed/ (committed, read by the app).

Rebuild:                       python -m nexus.data
Rebuild and run all checks:    python -m nexus.data --check
"""
import sys
from pathlib import Path

import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/processed")
TZ = "Asia/Kolkata"

# An hour's energy is only calculated if at least 75% of its minutes were
# recorded (45 of 60). Otherwise it stays blank instead of being guessed.
MIN_COVERAGE = 0.75

# The occupancy files never contain a 0. A missing 10-minute slot can mean
# "nobody connected" or "no data". On days the Wi-Fi system was running (at
# least half the day's slots recorded), a building's gaps are read as 0 people
# only if they cluster at night (00:00-06:00), where chance would give 25%.
# Otherwise, and on outage days, gaps stay blank.
MIN_DAY_SLOTS = 0.5
NIGHT_GAP_SHARE = 0.40

# Buildings whose energy readings must not be used for findings, and why.
# Source: CHECK 2 of `python -m nexus.data --check`, run 2026-10-02.
ENERGY_WARNINGS = {
    "Lecture": "The meter reads exactly 0 W for 82% of recorded minutes, "
               "including 49% of working-day class hours (09:00-17:00).",
}

# Column in all_buildings_power.csv -> the building it belongs to.
# Dorms have two meters (mains + UPS backup); the building total is their sum.
BUILDING_OF = {
    "Academic": "Academic", "Lecture": "Lecture", "Library": "Library",
    "Mess": "Dining", "Facilities": "Facilities",
    "Boys_main": "Boys dorm", "Boys_backup": "Boys dorm",
    "Girls_main": "Girls dorm", "Girls_backup": "Girls dorm",
}
# The same meters as separate files. Only used to cross-check the combined file.
METER_FILE = {
    "Academic": "acad_build_mains", "Lecture": "lecture_build_mains",
    "Library": "library_build_mains", "Mess": "mess_build_mains",
    "Facilities": "facilities_build_mains", "Boys_main": "boys_hostel_mains",
    "Boys_backup": "boys_hostel_ups", "Girls_main": "girls_hostel_mains",
    "Girls_backup": "girls_hostel_ups",
}
OCCUPANCY_FILE = {
    "Academic": "ACB", "Lecture": "LCB", "Library": "LB", "Dining": "DB",
    "Facilities": "SRB", "Boys dorm": "BH", "Girls dorm": "GH",
}


def to_local(seconds):
    """Unix seconds -> IIIT-Delhi local time, as a DatetimeIndex."""
    utc = pd.DatetimeIndex(pd.to_datetime(seconds, unit="s", utc=True))
    return utc.tz_convert(TZ).tz_localize(None)


# ---------------------------------------------------------------- loading

def load_power_minutes():
    """Every building meter on one 1-minute grid, in watts. Blank = not recorded."""
    df = pd.read_csv(RAW / "energy_dataset" / "all_buildings_power.csv")
    df.index = to_local(df.pop("timestamp"))
    df = df[~df.index.duplicated()].sort_index()
    df = df.apply(pd.to_numeric, errors="coerce")  # stray text -> blank
    return df.mask(df < 0)  # negative power is impossible -> blank


def load_occupancy():
    """Wi-Fi occupancy estimates for every building, 10-minute, long format."""
    frames = []
    for building, code in OCCUPANCY_FILE.items():
        df = pd.read_csv(RAW / "IIITD_occupancy_dataset" / f"{code}.csv")
        frames.append(pd.DataFrame({
            "time": to_local(df["timestamp"]).floor("10min"),
            "building": building,
            "occupancy": pd.to_numeric(df["occupancy_count"], errors="coerce"),
        }))
    occ = pd.concat(frames, ignore_index=True)
    return occ.drop_duplicates(["building", "time"])


def load_calendar():
    """One row per day: working day or not, high or low academic activity."""
    files = sorted((RAW / "iiitd_calender_schedule").glob("*.csv"))
    cal = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    cal = pd.DataFrame({
        "date": pd.to_datetime(cal["Date"]),
        "working_day": cal["working_day"] == 1,
        "activity": cal["activity"].map({"H": "high", "L": "low"}),
    })
    cal = cal.drop_duplicates("date").sort_values("date", ignore_index=True)

    # "high" marks individual days (semester weekdays), so weekends are always
    # "low". A whole Monday-Sunday week counts as a semester week when at least
    # 3 of its 5 weekdays are high-activity days.
    week = cal["date"].dt.to_period("W-SUN")
    weekday_high = (cal["activity"] == "high") & (cal["date"].dt.dayofweek < 5)
    cal["semester_week"] = weekday_high.groupby(week).transform("sum") >= 3
    return cal


# ---------------------------------------------------------- hourly tables

def hourly_energy(minutes):
    """Minute power (W) -> hourly energy (kWh) per building, long format.

    kWh for one hour = average power over its recorded minutes (kW) x 1 hour.
    Hours with too few recorded minutes stay blank, and so does a dorm hour
    if either of its two meters is blank.
    """
    hours = minutes.resample("h")
    kwh = (hours.mean() / 1000).where(hours.count() >= 60 * MIN_COVERAGE)

    buildings = {}
    for col, building in BUILDING_OF.items():
        if building in buildings:
            buildings[building] = buildings[building] + kwh[col]
        else:
            buildings[building] = kwh[col]
    wide = pd.DataFrame(buildings)
    wide.index.name = "hour"
    return wide.reset_index().melt(id_vars="hour", var_name="building", value_name="kwh")


def fill_occupancy(occ):
    """Put each building on a full 10-minute grid and decide what its gaps mean.

    Returns the grid (gaps set to 0 are marked `filled`) and, per building:
    gaps on running days, the share of them at night, and whether they became 0.
    """
    frames, decisions = [], {}
    for building, g in occ.groupby("building"):
        s = g.set_index("time")["occupancy"].sort_index()
        grid = pd.date_range(s.index.min().normalize(),
                             s.index.max().normalize() + pd.Timedelta("1D"),
                             freq="10min", inclusive="left")
        s = s.reindex(grid)
        day_share = s.notna().groupby(grid.normalize()).transform("mean")
        gaps = s.isna() & (day_share >= MIN_DAY_SLOTS)
        night = (grid[gaps.to_numpy()].hour < 6).mean() if gaps.any() else 0.0
        empty_at_night = night >= NIGHT_GAP_SHARE
        filled = gaps & empty_at_night
        decisions[building] = (int(gaps.sum()), night, empty_at_night)
        frames.append(pd.DataFrame({
            "time": grid,
            "building": building,
            "occupancy": s.mask(filled, 0).to_numpy(),
            "filled": filled.to_numpy(),
        }))
    return pd.concat(frames, ignore_index=True), decisions


def hourly_occupancy(slots):
    """Hourly mean and max people per building, from the 10-minute grid."""
    slots = slots.assign(
        hour=slots["time"].dt.floor("h"),
        recorded=slots["occupancy"].notna() & ~slots["filled"],
    )
    return (slots.groupby(["hour", "building"], as_index=False)
                 .agg(occ_mean=("occupancy", "mean"),
                      occ_max=("occupancy", "max"),
                      slots_recorded=("recorded", "sum"),
                      slots_set_to_0=("filled", "sum")))


# ----------------------------------------------------------------- checks

def check_against_meter_files(minutes):
    print("\nCHECK 1  combined file vs the separate meter files")
    for col, name in METER_FILE.items():
        raw = pd.read_csv(RAW / "energy_dataset" / f"{name}.csv",
                          usecols=["timestamp", "power"], low_memory=False)
        own = pd.Series(pd.to_numeric(raw["power"], errors="coerce").to_numpy(),
                        index=to_local(raw["timestamp"]))
        own = own[~own.index.duplicated()].dropna()
        both = pd.concat([minutes[col].dropna(), own], axis=1, join="inner")
        diff = (both.iloc[:, 0] - both.iloc[:, 1]).abs().max()
        print(f"  {col:14}{len(both):>11,} shared minutes   max difference {diff:,.3f} W")


def check_meters(minutes, cal):
    print("\nCHECK 2  zeros and spikes per meter (recorded minutes only)")
    print(f"  {'meter':14}{'zeros':>7}{'p99 kW':>9}{'max kW':>9}{'>2x p99':>9}")
    for col in BUILDING_OF:
        s = minutes[col].dropna()
        p99 = s.quantile(0.99)
        print(f"  {col:14}{(s == 0).mean():>7.1%}{p99 / 1000:>9.1f}"
              f"{s.max() / 1000:>9.1f}{(s > 2 * p99).sum():>9,}")
    lec = minutes["Lecture"].dropna()
    working = list(cal.loc[cal["working_day"], "date"])
    daytime = (lec.index.normalize().isin(working)
               & (lec.index.hour >= 9) & (lec.index.hour < 17))
    print(f"  Lecture zeros on working days 09:00-17:00: {(lec[daytime] == 0).mean():.1%}")


# ------------------------------------------------------------------ build

def main(run_checks=False):
    OUT.mkdir(parents=True, exist_ok=True)
    print("Reading 1-minute power ...")
    minutes = load_power_minutes()
    occ = load_occupancy()
    slots, decisions = fill_occupancy(occ)
    cal = load_calendar()

    tables = {
        "energy_hourly.parquet": hourly_energy(minutes),
        "occupancy_hourly.parquet": hourly_occupancy(slots),
        "calendar.parquet": cal,
    }
    print(f"\nBUILT {OUT}/")
    for name, df in tables.items():
        df.to_parquet(OUT / name, index=False)
        first = df.iloc[:, 0].min()
        last = df.iloc[:, 0].max()
        size = (OUT / name).stat().st_size / 1e6
        print(f"  {name:26}{len(df):>9,} rows  {first:%Y-%m-%d} to {last:%Y-%m-%d}  {size:.1f} MB")

    energy = tables["energy_hourly.parquet"]
    kwh_ok = energy.groupby("building")["kwh"].apply(lambda s: s.notna().mean())
    print(f"\n  {'building':12}{'kWh hours':>10}   occupancy slots: "
          f"{'recorded':>9}{'set to 0':>10}{'blank':>8}")
    for building, g in slots.groupby("building"):
        recorded = (g["occupancy"].notna() & ~g["filled"]).mean()
        print(f"  {building:12}{kwh_ok[building]:>10.1%}{'':>20}"
              f"{recorded:>7.1%}{g['filled'].mean():>10.1%}{g['occupancy'].isna().mean():>8.1%}")
    print(f"\n  OCCUPANCY GAPS on running days (chance at night = 25%; "
          f"0 people if at least {NIGHT_GAP_SHARE:.0%})")
    for building, (gaps, night, empty) in decisions.items():
        print(f"  {building:12}{gaps:>9,} gaps {night:>7.1%} at night  -> "
              f"{'0 people' if empty else 'left blank'}")
    for building, why in ENERGY_WARNINGS.items():
        print(f"\n  WARNING {building} energy: {why}")

    if run_checks:
        check_against_meter_files(minutes)
        check_meters(minutes, cal)
    else:
        print("\n(add --check to also run the slow data checks)")


if __name__ == "__main__":
    main(run_checks="--check" in sys.argv)
