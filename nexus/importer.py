"""Turn a college's uploaded CSV into a NEXUS Dataset, with a report of every check.

Expected file (one row per meter reading; any order; .csv or .csv.gz):
    timestamp   local date and time, e.g. 2016-01-01 13:00 (not Unix seconds)
    building    building name
    kwh | kw | w   ONE energy column: kWh used in that interval, OR average kW, OR watts
    people      optional: people or Wi-Fi devices counted in that interval

Optional calendar file: date, working_day (1/0), activity (high/low).

Readings become hourly kWh with the same rule as IIIT-Delhi: an hour counts only if at
least 75% of its readings are present. Nothing is filled in or smoothed.
"""
import io

import pandas as pd

from nexus.data import MIN_COVERAGE
from nexus.dataset import Dataset, calendar_for

ENERGY_COLUMNS = {"kwh": "kWh per interval", "kw": "average kW", "w": "watts"}
MAX_ROWS = 3_000_000
MAX_BUILDINGS = 40
ZERO_LIMIT = 0.5      # a meter reading exactly 0 in more than half its hours is not analysed
GAP_WARNING = 0.3     # warn when a building misses more than 30% of hours


class ImportProblem(Exception):
    """The file cannot be used; the message says how to fix it."""


def read_csv(data, name=""):
    """Read uploaded bytes or a path as a CSV (gzip if the name ends in .gz)."""
    if isinstance(data, (bytes, bytearray)):
        data = io.BytesIO(data)
    try:
        return pd.read_csv(data, compression="gzip" if str(name).endswith(".gz") else "infer",
                           low_memory=False)
    except Exception as e:
        raise ImportProblem(f"Could not read the file as CSV: {e}")


def build(name, raw, calendar_raw=None, source=""):
    """Check and convert. Returns (Dataset, report). Raises ImportProblem if unusable."""
    report = {"rows_read": len(raw), "rejected": {}, "warnings": [], "buildings": []}
    if len(raw) > MAX_ROWS:
        raise ImportProblem(f"The file has {len(raw):,} rows; the limit is {MAX_ROWS:,}. "
                            "Upload hourly readings or fewer buildings.")
    df = raw.rename(columns=lambda c: str(c).strip().lower())
    missing = [c for c in ("timestamp", "building") if c not in df.columns]
    if missing:
        raise ImportProblem(f"Missing column(s): {', '.join(missing)}. The file needs "
                            "timestamp, building and one energy column (kwh, kw or w).")
    energy_cols = [c for c in ENERGY_COLUMNS if c in df.columns]
    if len(energy_cols) != 1:
        raise ImportProblem("Include exactly one energy column, named kwh (kWh in each "
                            "interval), kw (average kW) or w (watts).")
    unit = energy_cols[0]
    report["unit"] = ENERGY_COLUMNS[unit]

    # --- row checks: each rejected row is counted with its reason
    if pd.api.types.is_numeric_dtype(df["timestamp"]):
        raise ImportProblem("Timestamps look like numbers (Unix seconds). Use local date and "
                            "time text instead, e.g. 2016-01-01 13:00, so the time zone is clear.")
    ts = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed")
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)   # keep the local clock time as written
        report["warnings"].append("Timestamps had a time-zone offset; their local clock time was kept.")
    value = pd.to_numeric(df[unit], errors="coerce")
    building = df["building"].astype("string").str.strip()
    bad = {
        "timestamp not readable": ts.isna(),
        "building name empty": (building.isna() | building.eq("")
                                | building.str.lower().isin(["nan", "none"])).fillna(True),
        f"{unit} not a number": value.isna() & df[unit].notna(),
        f"{unit} blank": df[unit].isna(),
        f"{unit} negative": value < 0,
    }
    keep = pd.Series(True, index=df.index)
    for reason, mask in bad.items():
        mask = mask & keep
        if mask.any():
            report["rejected"][reason] = int(mask.sum())
        keep &= ~mask
    people = pd.to_numeric(df["people"], errors="coerce") if "people" in df.columns else None
    clean = pd.DataFrame({"ts": ts, "building": building.astype(object), "value": value})
    if people is not None:
        clean["people"] = people
    clean = clean[keep]
    dupes = clean.duplicated(["building", "ts"])
    if dupes.any():
        report["rejected"]["duplicate timestamp for a building (first kept)"] = int(dupes.sum())
        clean = clean[~dupes]
    report["rows_used"] = len(clean)
    if clean.empty:
        raise ImportProblem("No usable rows after the checks below.")
    n_buildings = clean["building"].nunique()
    if n_buildings > MAX_BUILDINGS:
        raise ImportProblem(f"{n_buildings} buildings found; the limit is {MAX_BUILDINGS}.")

    # --- hourly kWh per building, with the 75% coverage rule
    start, end = clean["ts"].min().floor("h"), clean["ts"].max().floor("h")
    hours = pd.date_range(start, end, freq="h")
    energy_parts, occ_parts = [], []
    for b, g in clean.groupby("building"):
        g = g.sort_values("ts")
        step = g["ts"].diff().dropna().median()
        minutes = step / pd.Timedelta(minutes=1) if pd.notna(step) else 60.0
        if minutes > 60:
            raise ImportProblem(f"{b}: readings are every {minutes:.0f} minutes. NEXUS needs "
                                "hourly or more frequent readings.")
        per_hour = max(1, round(60 / minutes))
        hour = g["ts"].dt.floor("h")
        grouped = g.groupby(hour)["value"]
        count = grouped.size()
        if unit == "kwh":
            kwh = grouped.sum()
        elif unit == "kw":
            kwh = grouped.mean()
        else:
            kwh = grouped.mean() / 1000
        kwh = kwh.where(count / per_hour >= MIN_COVERAGE).reindex(hours)
        energy_parts.append(pd.DataFrame({"hour": hours, "building": b, "kwh": kwh.to_numpy()}))
        if people is not None and g["people"].notna().any():
            pg = g.dropna(subset=["people"]).groupby(hour)["people"]
            occ_parts.append(pd.DataFrame({"hour": pg.mean().index, "building": b,
                                           "occ_mean": pg.mean().to_numpy(),
                                           "occ_max": pg.max().to_numpy()}))
        recorded = kwh.notna().mean()
        zeros = (kwh == 0).sum() / max(kwh.notna().sum(), 1)
        report["buildings"].append({
            "building": b, "first": g["ts"].min(), "last": g["ts"].max(),
            "reading_every_min": round(minutes, 1), "hours_with_energy": int(kwh.notna().sum()),
            "hours_recorded_pct": round(recorded * 100, 1), "zero_hours_pct": round(zeros * 100, 1),
        })
    if not energy_parts:
        raise ImportProblem("No usable rows after the checks below.")
    energy = pd.concat(energy_parts, ignore_index=True)

    warnings = {}
    for r in report["buildings"]:
        if r["zero_hours_pct"] / 100 > ZERO_LIMIT:
            warnings[r["building"]] = (f"The meter reads exactly 0 in {r['zero_hours_pct']:.0f}% of "
                                       "recorded hours, so it is treated as unreliable.")
        if r["hours_recorded_pct"] / 100 < 1 - GAP_WARNING:
            report["warnings"].append(f"{r['building']}: only {r['hours_recorded_pct']:.0f}% of hours "
                                      "have energy data; gaps are left blank, not filled in.")
    for b, why in warnings.items():
        report["warnings"].append(f"{b}: {why}")

    cal = None
    if calendar_raw is not None:
        c = calendar_raw.rename(columns=lambda x: str(x).strip().lower())
        if "date" not in c.columns or "working_day" not in c.columns:
            raise ImportProblem("The calendar needs columns date and working_day (1/0); "
                                "activity (high/low) is optional.")
        c["working_day"] = pd.to_numeric(c["working_day"], errors="coerce").fillna(0).astype(bool)
        if "activity" not in c.columns:
            c["activity"] = "low"
        cal = c[["date", "working_day", "activity"]]
    calendar = calendar_for(energy, cal)
    notes = []
    if cal is None:
        notes.append("No academic calendar was uploaded: Monday-Friday count as working days and "
                     "every week as a teaching week.")
        report["warnings"].append(notes[-1])
    occupancy = pd.concat(occ_parts, ignore_index=True) if occ_parts else None
    if occupancy is None:
        notes.append("No people or Wi-Fi counts were uploaded, so occupancy analysis is not available.")

    report["period"] = (energy["hour"].min(), energy["hour"].max())
    ds = Dataset(name=name, source=source or f"Uploaded data: {name}. Stays in this browser session.",
                 energy=energy, calendar=calendar, occupancy=occupancy, warnings=warnings,
                 notes=notes)
    return ds, report


TEMPLATE = """timestamp,building,kwh,people
2024-01-08 09:00,Main Academic Block,41.2,310
2024-01-08 09:00,Hostel A,18.7,95
2024-01-08 10:00,Main Academic Block,44.9,355
2024-01-08 10:00,Hostel A,16.1,60
"""

CALENDAR_TEMPLATE = """date,working_day,activity
2024-01-08,1,high
2024-01-13,0,low
2024-01-26,0,low
"""
