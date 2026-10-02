"""One college's data, in the shape every NEXUS analysis expects.

IIIT-Delhi's comes from data/processed/ (built by nexus.data). Other colleges come from
an uploaded CSV through nexus.importer. Analyses take a Dataset, so the same code runs
on any college.
"""
from dataclasses import dataclass, field

import pandas as pd

from nexus.data import ENERGY_WARNINGS, OUT

IIITD = "IIIT-Delhi, New Delhi"


@dataclass
class Dataset:
    name: str
    source: str                         # one line, shown on every page
    energy: pd.DataFrame                # hour, building, kwh (hourly grid, blank = not recorded)
    calendar: pd.DataFrame              # date, working_day, activity, semester_week
    occupancy: pd.DataFrame | None = None   # hour, building, occ_mean, occ_max
    warnings: dict = field(default_factory=dict)   # building -> why its energy is not analysed
    has_map: bool = False
    has_calendar: bool = True                      # False: weekdays only, no terms or holidays
    notes: list = field(default_factory=list)      # limitations specific to this college

    @property
    def first(self):
        return self.energy["hour"].min()

    @property
    def last(self):
        return self.energy["hour"].max()


def iiitd():
    """The I-BLEND demo data from IIIT-Delhi (public, CC0)."""
    return Dataset(
        name=IIITD,
        source="Public IIIT-Delhi data (I-BLEND, 2013-2017). Not PES data.",
        energy=pd.read_parquet(OUT / "energy_hourly.parquet"),
        calendar=pd.read_parquet(OUT / "calendar.parquet"),
        occupancy=pd.read_parquet(OUT / "occupancy_hourly.parquet"),
        warnings=dict(ENERGY_WARNINGS),
        has_map=True,
    )


def calendar_for(energy, uploaded=None):
    """A calendar covering the energy data: the uploaded one, or weekdays as working days.

    Without an academic calendar every day is 'low' activity and every week counts as a
    teaching week; the app says so wherever that matters.
    """
    days = pd.date_range(energy["hour"].min().normalize(), energy["hour"].max().normalize())
    cal = pd.DataFrame({"date": days})
    if uploaded is None:
        cal["working_day"] = cal["date"].dt.dayofweek < 5
        cal["activity"] = "low"
        cal["semester_week"] = True
        return cal
    up = uploaded.copy()
    up["date"] = pd.to_datetime(up["date"]).dt.normalize()
    up = up.drop_duplicates("date", keep="first")
    cal = cal.merge(up, on="date", how="left")
    cal["working_day"] = cal["working_day"].fillna(cal["date"].dt.dayofweek < 5).astype(bool)
    cal["activity"] = cal["activity"].fillna("low").astype(str).str.lower()
    cal.loc[cal["activity"].isin(["h", "high", "1"]), "activity"] = "high"
    cal.loc[cal["activity"] != "high", "activity"] = "low"
    week = cal["date"] - pd.to_timedelta(cal["date"].dt.dayofweek, unit="D")
    high_weekdays = (cal["activity"].eq("high") & (cal["date"].dt.dayofweek < 5)).groupby(week).transform("sum")
    cal["semester_week"] = high_weekdays >= 3
    return cal[["date", "working_day", "activity", "semester_week"]]
