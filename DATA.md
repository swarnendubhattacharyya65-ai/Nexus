# NEXUS demo data: I-BLEND (IIIT-Delhi)

> Public data from IIIT-Delhi, New Delhi. **This is not PES data.**

## Source
- Dataset: I-BLEND, a campus-scale commercial and residential buildings electrical energy dataset
- Institution: Indraprastha Institute of Information Technology Delhi (IIIT-Delhi)
- Paper: Rashid, H., Singh, P. & Singh, A. (2019). Scientific Data 6, 190015. https://doi.org/10.1038/sdata.2019.15
- Data: https://doi.org/10.6084/m9.figshare.c.3893581
- License: CC0 1.0 (public domain) for the energy, occupancy and calendar files. We still cite the paper.
- Downloaded 2026-10-02. Raw files live in `data/raw/` and are not committed (1.6 GB).

## Raw files
**Energy** (`data/raw/energy_dataset/`, 1-minute, power in watts, Unix timestamps converted to Asia/Kolkata)
- Main input: `all_buildings_power.csv`, all nine building meters on one 1-minute grid, `NA` = not recorded.
- Also one file per meter (`acad_build_mains.csv` etc.) with `timestamp`, `power`, `current`, `voltage`, `frequency`, `power_factor`; used only to cross-check the combined file.
- `data_present_status_*.csv`: per-minute 1/0 flags for whether each meter recorded data.
- `all_transformer_power.csv`, `transformer_*.csv`: three campus supply transformers. Not used yet. Never add them to buildings (double counting).

| Meter column | Building | Occupancy code | First | Last | Missing minutes |
|---|---|---|---|---|---|
| Academic | Academic | ACB | 2013-08-10 | 2017-12-31 | 1.8% |
| Lecture | Lecture | LCB | 2013-08-10 | 2017-12-31 | 1.8% |
| Library | Library | LB | 2013-08-10 | 2017-12-31 | 25.9% |
| Mess | Dining | DB | 2013-09-24 | 2017-12-31 | 10.4% |
| Facilities | Facilities | SRB | 2013-11-15 | 2017-12-31 | 5.6% |
| Boys_main + Boys_backup | Boys dorm (mains + UPS) | BH | 2013-08-10 | 2017-12-31 | 27.7% / 27.0% |
| Girls_main + Girls_backup | Girls dorm (mains + UPS) | GH | 2013-08-10 | 2017-12-31 | 28.5% / 0.5% |

**Occupancy** (`data/raw/IIITD_occupancy_dataset/`, 10-minute): `timestamp`, `occupancy_count` = estimated people from Wi-Fi connections (max of each 10-minute window). 2014-02-16 to 2017-11-03 (Facilities from 2014-07-10). The files contain no zeros.

**Calendar** (`data/raw/iiitd_calender_schedule/`, daily): `Date`, `working_day` (1/0), `activity` (H/L). Complete 2013-08-01 to 2017-12-31. `activity` marks single days, not whole periods: across 2013-2017, Monday-Friday are high-activity on 135-143 days each, Saturdays on 3 days and Sundays never. So H means a high-activity day (a semester weekday), and weekends are L even during semesters.

## Processed tables (`data/processed/`, built by `python -m nexus.data`)
| File | One row per | Columns |
|---|---|---|
| energy_hourly.parquet | building and hour | `hour`, `building`, `kwh` (blank if fewer than 45 of 60 minutes recorded; a dorm is mains + UPS and blank if either is blank) |
| occupancy_hourly.parquet | building and hour | `hour`, `building`, `occ_mean`, `occ_max`, `slots_recorded`, `slots_set_to_0` |
| calendar.parquet | day | `date`, `working_day`, `activity` (high/low), `semester_week` (derived, see decision 6) |

## Decisions (from `python -m nexus.data --check`, 2026-10-02)
1. **Use the combined power file.** It matches the separate meter files to within 0.005 W (0.048 W for Dining), which is CSV rounding.
2. **Lecture energy is excluded from findings.** The meter reads exactly 0 W for 81.7% of recorded minutes, including 48.6% of working-day 09:00-17:00 minutes. We judge a building of nine classrooms in use is very unlikely to draw nothing, so the meter is treated as unreliable. Lecture occupancy is still used.
3. **Spikes are kept and flagged, never silently deleted.** Minutes above twice the 99th percentile: Facilities 1,232 (max 139.4 kW vs p99 21.1 kW), Dining 67, Library 2, Boys mains 1, all others 0. They are candidates for investigation, not confirmed problems.
4. **Zero readings outside Lecture are rare** (0.3% or less) and kept as real readings.
5. **Assumption: a missing occupancy slot = 0 people only in buildings that empty at night.** The files never contain 0, so a gap can mean "nobody connected" or "no data". On days the Wi-Fi system was running (at least half the day's slots recorded), gaps are set to 0 only for buildings whose gaps fall between 00:00 and 06:00 at least 40% of the time (chance would be 25%). On the real data: Lecture 49%, Library 49%, Facilities 50%, Dining 46% (set to 0); Academic 31%, Boys dorm 29%, Girls dorm 32% (left blank). The build prints this table every time. Outage days are always blank.
6. **Semester weeks are derived.** Because weekends are always low-activity days (see Calendar), a Monday-Sunday week counts as a semester week when at least 3 of its 5 weekdays are high-activity days. Used for occupancy patterns and the energy-when-quiet comparison.

## Still open
- Facilities spikes: real events (e.g. window ACs) or meter glitches? Look at when they happen.
- Transformers are not used yet.

## Limitations (shown in the app)
- Data is from 2013-2017, not current.
- Building level only: no rooms, schedules or capacity, so no room-utilization rates.
- Occupancy is a Wi-Fi estimate. It overcounts people with several devices (up to about 50 in Academic, about 20 elsewhere, per the paper), misses people not on Wi-Fi, and treats some gaps as 0 (decision 5).
- Lecture energy is unreliable (decision 2).
- Large gaps in the dorm mains, Library and Transformer 1 meters (26-34%).
- No tariff: we report kWh, not money, unless an assumed rate is clearly stated.
