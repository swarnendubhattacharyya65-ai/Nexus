# NEXUS demo data: I-BLEND (IIIT-Delhi)

> Public data from IIIT-Delhi, New Delhi. **This is not PES data.**

## Source
- Dataset: I-BLEND, a campus-scale commercial and residential buildings electrical energy dataset
- Institution: Indraprastha Institute of Information Technology Delhi (IIIT-Delhi)
- Paper: Rashid, H., Singh, P. & Singh, A. (2019). Scientific Data 6, 190015. https://doi.org/10.1038/sdata.2019.15
- Data: https://doi.org/10.6084/m9.figshare.c.3893581
- License: CC0 1.0 (public domain) for the energy, occupancy and calendar files. We still cite the paper.
- Downloaded 2026-10-02. Raw files live in `data/raw/` and are not committed (1.6 GB).

## Energy: `data/raw/energy_dataset/` (one CSV per meter, 1-minute)
Columns: `timestamp` (Unix seconds), `power` (W), `current`, `voltage`, `frequency`, `power_factor`.
Timestamps convert to Asia/Kolkata (UTC+5:30).

| Meter file | Building | Occupancy file | First | Last | Missing | Median W |
|---|---|---|---|---|---|---|
| acad_build_mains | Academic | ACB | 2013-08-10 | 2017-12-31 | 1.8% | 23,342 |
| lecture_build_mains | Lecture | LCB | 2013-08-10 | 2017-12-31 | 1.8% | 0 (check) |
| library_build_mains | Library | LB | 2013-08-10 | 2017-12-31 | 25.9% | 6,711 |
| mess_build_mains | Dining ("Mess") | DB | 2013-09-24 | 2017-12-31 | 10.4% | 20,648 |
| facilities_build_mains | Facilities | SRB | 2013-11-15 | 2017-12-31 | 5.6% | 9,861 |
| boys_hostel_mains | Boys dorm, mains | BH | 2013-08-10 | 2017-12-31 | 27.7% | 15,594 |
| boys_hostel_ups | Boys dorm, UPS backup | BH | 2013-08-10 | 2017-12-31 | 27.0% | 13,069 |
| girls_hostel_mains | Girls dorm, mains | GH | 2013-08-10 | 2017-12-31 | 28.5% | 7,080 |
| girls_hostel_ups | Girls dorm, UPS backup | GH | 2013-08-10 | 2017-12-31 | 0.5% | 6,783 |
| transformer_1 | Campus supply (not a building) | - | 2013-11-26 | 2017-12-31 | 34.2% | 27,841 |
| transformer_2 | Campus supply (not a building) | - | 2013-11-26 | 2017-12-31 | 6.2% | 93,363 |
| transformer_3 | Campus supply (not a building) | - | 2013-11-26 | 2017-12-31 | 5.8% | 70,192 |

- A dorm's total = mains + UPS (two separate supplies).
- Never add transformers to buildings: transformers feed the buildings, so that double counts.
- Not yet inspected: `all_buildings_power.csv`, `all_transformer_power.csv` (wide tables, one column per meter; the source spells it "transfomer"), `data_present_status_buildings.csv`, `data_present_status_transformers.csv`.

## Occupancy: `data/raw/IIITD_occupancy_dataset/` (one CSV per building, 10-minute)
Columns: `timestamp` (Unix seconds), `occupancy_count` (estimated people from Wi-Fi connections, max of each 10-minute window).
Codes: ACB Academic, BH Boys dorm, DB Dining, GH Girls dorm, LB Library, LCB Lecture, SRB Facilities.
Range 2014-02-16 to 2017-11-03 (SRB from 2014-07-10). Missing 8.0-22.5% (LCB highest).

## Calendar: `data/raw/iiitd_calender_schedule/` (one CSV per year, daily)
Columns: `Date`, `working_day` (1 working, 0 not), `activity` (H high-activity semester, L breaks and vacations).
Complete from 2013-08-01 to 2017-12-31.

## Checks done (`scripts/inspect_raw.py`, 2026-10-02)
- Power is in watts: medians match the paper's typical loads (Academic, Dining, Facilities, dorm backups).
- The least-missing meters (Academic, Lecture, Girls UPS) match the paper.
- No duplicate timestamps. Blank power values: 0-11 per file.

## Open questions (resolve before analysis)
1. Lecture median power is 0 W; the paper says about 2 kW is typical. Real zeros or meter dropouts?
2. Occupancy minimum is 1 everywhere, but the paper says Lecture reaches 0 at night. Missing rows may mean 0 people, not missing data.
3. Spikes: several maximums are 7-14x the median (Facilities 139 kW, Dining 142 kW, Library 99 kW). Flag, never silently delete.
4. Zero readings appear in most meters (power cuts?). Decide: real zero or missing.
5. Resolution and purpose of the `all_*` and `data_present_status_*` files.

## Limitations (shown in the app)
- Data is from 2013-2017, not current.
- Building level only: no rooms, schedules or capacity, so no room-utilization rates.
- Occupancy is a Wi-Fi estimate. It overcounts people with several devices (up to ~50 in Academic, ~20 elsewhere, per the paper) and misses people not on Wi-Fi.
- Large gaps in the dorm mains, Library and Transformer 1 meters (26-34%).
- No tariff: we report kWh, not money, unless an assumed rate is clearly stated.
