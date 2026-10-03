"""NEXUS Institutional Intelligence: how campus buildings are used over time.

Building level only. I-BLEND has no rooms, timetables or capacities, so this
never reports a utilization rate. Each building is compared with its own
busiest hours instead, and its occupancy is set against its energy use.

Print a summary:   python -m nexus.institutional
"""
import pandas as pd

from nexus.data import ENERGY_WARNINGS, OUT

BUSY_LEVEL = 0.95  # a building's busy level = people in its 95th-percentile hour
QUIET = 0.10       # quiet hour: fewer than 10% of the busy level
BUSY = 0.50        # busy hour: at least 50% of the busy level
MIN_HOURS = 200    # fewer hours than this -> "insufficient data", not a number
MIN_QUIET_SHARE = 0.10  # near-empty in fewer hours than this -> not compared
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load_occupancy(ds=None):
    """Hourly people estimates joined with the calendar. Blank hours are dropped."""
    if ds is None:
        occ = pd.read_parquet(OUT / "occupancy_hourly.parquet")
        cal = pd.read_parquet(OUT / "calendar.parquet")
    else:
        occ, cal = ds.occupancy.copy(), ds.calendar
    occ["date"] = occ["hour"].dt.normalize()
    occ = occ.merge(cal, on="date", how="left")
    return occ.dropna(subset=["occ_mean", "semester_week"])


def weekly_profile(occ, building, semester):
    """Median people for each day of the week and hour, in semester or break weeks."""
    g = occ[(occ["building"] == building) & (occ["semester_week"] == semester)]
    g = g.assign(day=g["hour"].dt.dayofweek.map(dict(enumerate(DAYS))),
                 hour_of_day=g["hour"].dt.hour)
    return g.groupby(["day", "hour_of_day"], as_index=False).agg(
        people=("occ_mean", "median"), hours=("occ_mean", "size"))


def building_summary(occ, ds=None):
    """One row per building: how busy it gets, when it is quiet, and its energy then.

    Energy is compared within semester weeks only, so that long holidays do
    not make quiet hours look cheaper than they are.
    """
    energy = pd.read_parquet(OUT / "energy_hourly.parquet") if ds is None else ds.energy
    unreliable = ENERGY_WARNINGS if ds is None else ds.warnings
    both = occ.merge(energy, on=["hour", "building"], how="left")
    rows = []
    for building, g in both.groupby("building"):
        busy_level = g["occ_mean"].quantile(BUSY_LEVEL)
        quiet = g["occ_mean"] < QUIET * busy_level
        busy = g["occ_mean"] >= BUSY * busy_level
        semester = g["semester_week"].astype(bool)
        hour = g["hour"].dt.hour
        class_hours = semester & g["working_day"].astype(bool) & (hour >= 9) & (hour < 17)

        quiet_kwh = g.loc[semester & quiet, "kwh"].dropna()
        busy_kwh = g.loc[semester & busy, "kwh"].dropna()
        if building in unreliable:
            note = "Energy meter unreliable"
        elif quiet.mean() < MIN_QUIET_SHARE:
            note = (f"Rarely near-empty ({quiet.mean():.0%} of hours), so a quiet reading "
                    "is more likely a Wi-Fi drop-out than an empty building")
        elif min(len(quiet_kwh), len(busy_kwh)) < MIN_HOURS:
            note = f"Insufficient data: fewer than {MIN_HOURS} quiet or busy semester hours with energy"
        else:
            note = ""

        rows.append({
            "building": building,
            "busy_level": busy_level,
            "class_hours_people": g.loc[class_hours, "occ_mean"].median(),
            "night_people": g.loc[semester & (hour < 6), "occ_mean"].median(),
            "quiet_share": quiet.mean(),
            "quiet_in_class_hours": quiet[class_hours].mean(),
            "class_hours": int(class_hours.sum()),
            "quiet_kwh": quiet_kwh.median() if not note else float("nan"),
            "busy_kwh": busy_kwh.median() if not note else float("nan"),
            "quiet_energy_hours": len(quiet_kwh),
            "busy_energy_hours": len(busy_kwh),
            "energy_note": note,
        })
    summary = pd.DataFrame(rows)
    summary["quiet_vs_busy"] = summary["quiet_kwh"] / summary["busy_kwh"]
    return summary


def main():
    s = building_summary(load_occupancy())
    print("OCCUPANCY  Wi-Fi estimate of people; busy level = 95th-percentile hour")
    print(f"  {'building':12}{'busy lvl':>9}{'class hrs':>10}{'night':>7}"
          f"{'quiet hrs':>10}{'quiet in class':>15}")
    for r in s.itertuples():
        print(f"  {r.building:12}{r.busy_level:>9.0f}{r.class_hours_people:>10.0f}"
              f"{r.night_people:>7.0f}{r.quiet_share:>10.0%}{r.quiet_in_class_hours:>15.0%}")

    print("\nENERGY WHEN QUIET vs BUSY  (semester hours, median kWh per hour)")
    print(f"  {'building':12}{'quiet':>8}{'busy':>8}{'quiet/busy':>12}{'hours q/b':>14}")
    for r in s.itertuples():
        if r.energy_note:
            print(f"  {r.building:12}  {r.energy_note}")
        else:
            print(f"  {r.building:12}{r.quiet_kwh:>8.1f}{r.busy_kwh:>8.1f}{r.quiet_vs_busy:>12.0%}"
                  f"{r.quiet_energy_hours:>8,}/{r.busy_energy_hours:,}")


if __name__ == "__main__":
    main()
