# NEXUS

Campus intelligence from the data an institution already generates.

> **Demo data:** public electricity and Wi-Fi occupancy data from IIIT-Delhi, New Delhi
> (I-BLEND, 2013-2017). **This is not PES data.** PES integration would be a separate,
> approved pilot.

Live app: https://nexusdemo.streamlit.app (free hosting sleeps when idle, so the first
visit can take a minute to wake up).

## What it does
| Page | Question it answers | How |
|---|---|---|
| Overview | How did the chosen week compare with the week before? What is happening, what might happen next, what to check | Hour-for-hour week comparison, plus a summary of the pages below |
| Resource Intelligence | Which hours used unusually more or less energy than normal? | Each hour vs a baseline of comparable hours |
| Institutional Intelligence | When are buildings busy or near-empty, and do they still use energy when near-empty? | Wi-Fi occupancy estimates by hour and weekday |
| Predictive Intelligence | How much energy will each building use over the next 14 days? | Two simple forecasts, tested on history |
| Recommendations | What should someone check next? | Explicit rules applied to the findings above |
| Campus Map | Where on campus is something happening this week? | Real building outlines in 3D, coloured by the week's findings, with a day-by-day replay of the 12 weeks to the chosen date |
| Reports | Can I share this week's findings? | A printable week report (HTML) and CSV downloads |
| Ask NEXUS | Plain questions: which building needs attention, trends, next 2 weeks, savings, underused buildings | Fixed rules over NEXUS's own tables; no language model, no guessed causes |
| Add college data | Does this work on another college? | Upload a CSV (or load the public sample); every page then runs on it |
| Settings, Help | Tariff and carbon factor for ₹ and CO₂; plain answers | Your figures, shown next to every result they produce |
| Data & method | Where the data comes from and every cleaning decision | Shows `DATA.md`, or the import checks for an uploaded college |

Every number is calculated by the code in `nexus/`, not typed in. Where there is not
enough data, the app says "Insufficient data" instead of guessing. Recommendations are
things to check, not diagnosed causes. The data has no electricity tariff, so money
appears only after you enter your own tariff in Settings, and is labelled as yours.

## Setup
Needs Python 3.11 or newer (developed in GitHub Codespaces with Python 3.14).

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app only reads the small processed tables in `data/processed/`, which are
committed, so it runs without downloading the raw data.

### Dependencies (`requirements.txt`)
| Package | Version | Used for |
|---|---|---|
| streamlit | 1.64.0 | Web app |
| pandas | 3.0.6 | All data processing |
| altair | 6.3.0 | Charts |
| pyarrow | 25.0.1 | Reading and writing the parquet tables |

### Rebuilding the data from the raw files (optional)
1. Download the I-BLEND files from https://doi.org/10.6084/m9.figshare.c.3893581
   (energy dataset, occupancy dataset and calendar schedule).
2. Unzip them into `data/raw/` so these folders exist (delete any `__MACOSX` folders):
   - `data/raw/energy_dataset/`
   - `data/raw/IIITD_occupancy_dataset/`
   - `data/raw/iiitd_calender_schedule/`
3. Run, from the repo root:

```bash
python scripts/inspect_raw.py      # read-only summary of the raw files
python -m nexus.data --check       # build data/processed/ and print every check
```

`data/raw/` is 1.6 GB and is listed in `.gitignore`. Never commit it. When committing,
add files by name instead of using `git add .`.

### Printing the analyses without the app
```bash
python -m nexus.resource        # baselines and unusual events
python -m nexus.institutional   # occupancy summary per building
python -m nexus.predictive      # forecast backtest and accuracy on 2017
python -m nexus.recommend       # every recommendation with its evidence
python -m nexus.kpis 2016-09-14  # one week vs the week before
```

## Project structure
```
app.py                   Entry point: sidebar navigation, top bar, pages
views/                   One file per page, plus shell.py (top bar, search) and common.py
nexus/data.py            Raw files -> hourly tables in data/processed/, plus data checks
nexus/resource.py        Baselines and unusual events
nexus/institutional.py   Occupancy patterns and energy when near-empty
nexus/predictive.py      Forecasts and backtest
nexus/recommend.py       Recommendation rules R1-R5
nexus/kpis.py            Week-on-week cards and the Overview headline
nexus/insights.py        Overview panels: insights feed, 30-day trend, building hours, 2-week outlook
nexus/ask.py             Ask NEXUS: question routing and rule-based answers
nexus/dataset.py         One college's data; nexus/importer.py turns an uploaded CSV into one
scripts/                 Raw data summary, logo generator
static/                  Logo and self-hosted fonts (SIL Open Font License)
.streamlit/config.toml   Theme: colours, fonts
DATA.md                  Source, license, files, cleaning decisions, limitations
data/processed/          Committed hourly tables the app reads
```

## Methods in brief
All thresholds are named constants at the top of each file in `nexus/`.

- **Hourly energy:** kWh from 1-minute power readings, only when at least 45 of 60
  minutes were recorded; otherwise left blank. A dorm is mains + UPS.
- **Baseline (Resource):** for each hour, the median of comparable hours in the same
  building: same hour of day, working day or not, and high or low activity day, within
  3 weeks either side. An hour is unusual when it is more than 3.5 robust standard
  deviations and at least 10% away from that median. At least 8 comparable hours are
  needed, otherwise there is no baseline. Consecutive unusual hours form one event.
- **Occupancy (Institutional):** Wi-Fi estimate of people per hour. Busy and near-empty
  hours are set relative to each building's own 95th-percentile hour. Energy in
  near-empty hours is compared with busy hours during semester weeks only.
- **Forecast (Predictive):** daily kWh, 14 days ahead. Method 1, "same weekday last
  week". Method 2, the median of recent days of the same calendar day type. Forecasts
  were made every 7 days through the history using only data available at the time.
  Each building's method was chosen on the earlier years (late 2013 to 2016 for
  IIIT-Delhi) and then scored on the last year (2017), which was not used to choose it.
  The 80% range comes from past forecast errors.
- **Week cards (Overview):** the 7 days ending on the chosen date vs the 7 days before,
  hour for hour, counting only building-hours recorded in both weeks. Fewer than 50%
  comparable hours gives "Insufficient data".
- **Recommendations:** five explicit rules (R1-R5), each shown in the app with its
  threshold, the finding that triggered it and the evidence.

## Other colleges
`Add college data` takes one CSV of meter readings (`timestamp`, `building`, and one of
`kwh`, `kw` or `w`; optional `people`) and an optional calendar. `nexus/importer.py`
checks every row, turns readings into hourly kWh with the same 75% rule, and reports what
it set aside and why. Uploaded files go to the NEXUS server and are kept in its memory for
that visitor's session only; they are not written to disk or shown to other visitors.

A public sample is included: 8 buildings from site Fox of the Building Data Genome
Project 2 (a US university campus, 2016-2017, CC BY-SA 4.0); see `data/samples/README.md`.

## Data
I-BLEND, IIIT-Delhi. Rashid, H., Singh, P. & Singh, A. (2019). *Scientific Data* 6,
190015. https://doi.org/10.1038/sdata.2019.15. The energy, occupancy and calendar files
are CC0 1.0 (public domain). See `DATA.md` for the raw files, units, coverage, every
cleaning decision and its evidence.

## Known issues
- **Lecture energy is not analysed.** Its meter reads exactly 0 W for 82% of recorded
  minutes, including 49% of class hours. Lecture occupancy is still used.
- **Facilities has very large spikes.** The largest events (more than 300% above
  expected) may be meter faults rather than real use. This is not resolved, so the
  app flags these and suggests checking the meter.
- **Large meter gaps:** the dorm mains and Library meters miss about 26-29% of minutes.
  Hours with too little data are left blank, not filled in.
- **Occupancy is an estimate.** Wi-Fi counts devices, not people. It overcounts people
  with several devices and misses people not on Wi-Fi. In buildings that empty at night,
  missing 10-minute slots are read as 0 people (`DATA.md`, decision 5).
- **Building level only.** There are no rooms, timetables or capacities, so there are
  no room utilization rates.
- **Forecasts have no weather input**, and in at least one building the calendar
  method did not beat the simple rule on 2017. The app says which, rather than switching methods
  after seeing the test year.
- **The data ends in 2017.** Forecasts can only be checked against history, not used
  for the coming weeks.
- **No tariff in the data.** Rupees appear only from a tariff you enter in Settings; the
  savings answer in Ask NEXUS is a what-if with a reduction you choose, not a forecast.
- **First load is slow on free hosting.** The app calculates baselines and the forecast
  backtest when it starts, then caches them.
- **No automated test suite yet.** Data checks run with `python -m nexus.data --check`.
- The three campus supply transformers in the dataset are not used yet.
