# NEXUS

Campus energy intelligence from the data an institution already generates: meter readings,
Wi-Fi occupancy and the academic calendar. NEXUS finds unusual use, shows when buildings run
empty, forecasts the next two weeks, and turns what it finds into solution plans, with the
numbers behind every result.

> **Demo data:** public electricity and Wi-Fi occupancy data from IIIT-Delhi, New Delhi
> (I-BLEND, 2013-2017). **This is not PES data.** PES integration would be a separate,
> approved pilot.

**Live app:** https://nexusv2demo.streamlit.app (free hosting sleeps when idle, so the first
visit can take a minute to wake up).

This is **NEXUS v2**, on the `main` branch. The first version is kept on the
[`v1`](https://github.com/swarnendubhattacharyya65-ai/Nexus/tree/v1) branch.

## What's new in v2
- **Recommendations rebuilt as solution plans.** Nine rules (up from five) find unusual use,
  data faults, high use in near-empty buildings, large always-on loads, buildings running on
  days off, the campus peak hour and big seasonal swings. Each recommendation shows what the
  data shows, the energy at stake, common causes to rule out, a three-stage action plan (this
  week at no cost, this month at low cost, next budget) with who does each step, and how to
  confirm it worked. "Start here" picks the three biggest opportunities, and the whole plan
  downloads as a checklist.
- **Everything follows the date you pick.** Recommendations look at the 12 months ending on
  the Week ending date, so you can step back through the years.
- **No guessed savings.** NEXUS shows the energy each problem involves, as measured, and what
  every 10% of it is worth (in rupees too, once you enter a tariff). It never claims how much
  a fix will save.
- **Find any college by name.** Type a college in the College box: NEXUS searches open research
  repositories (Zenodo, Figshare, Harvard Dataverse) for its energy data and analyses what it
  can read, or says "College data unavailable". The map moves to that campus either way.
- **3D campus map.** Real building outlines from OpenStreetMap, coloured by the week's findings,
  with a day-by-day replay of the 12 weeks to the chosen date.
- **Ask NEXUS, a chatbot.** A continuing conversation with Google Gemini (free key) or Claude,
  which looks up NEXUS's own tables before answering. A no-AI "Quick answers" tab works without
  any key.
- **Forecasts start where the data ends.** The chart shows the next 14 days only; the test on
  past data is in an expander.
- **Weekly Overview, Reports and Settings.** A week-on-week comparison with an insights feed, a
  printable week report and CSV downloads, and your own tariff and carbon factor for rupees
  and CO₂.
- **Your own data.** Upload a college's meter readings as a CSV, or load the public US sample.
- **Updates appear after a push.** The app reloads its code when it changes, so a new version
  shows on refresh without rebooting the server.
- **Offline tests** for the college search, the chatbot and the recommendations.

## What each page does
| Page | Question it answers | How |
|---|---|---|
| Overview | How did the chosen week compare with the week before? What's happening, what's next, what to do first | Hour-for-hour week comparison, insights feed, 30-day trend, 2-week outlook |
| Resource Intelligence | Which hours used unusually more or less energy than normal? | Each hour vs a baseline of comparable hours |
| Institutional Intelligence | When are buildings busy or near-empty, and do they still use energy when near-empty? | Wi-Fi occupancy estimates by hour and weekday |
| Predictive Intelligence | How much energy will each building use over the 14 days after the data ends? | Two simple forecasts, tested on history |
| Recommendations | What should we do, and what is at stake? | Nine explicit rules on the 12 months to the chosen date, each with a solution plan |
| Campus Map | Where on campus is something happening this week? | 3D building outlines coloured by the week's findings, with a replay |
| Reports | Can I share this week's findings? | Printable week report (HTML) and CSV downloads |
| Ask NEXUS | Any question, in a continuing conversation | Gemini or Claude with lookup tools over NEXUS's tables; Quick answers without AI |
| College box (top of every page) | Does this college publish energy data? | Searches public repositories; otherwise "College data unavailable" |
| Add college data | I have the college's own file | Upload a CSV (or load the public sample); every page then runs on it |
| Settings, Help | Tariff and carbon factor; plain answers | Your figures, shown next to every result they produce |
| Data & method | Where the data comes from and every cleaning decision | Shows `DATA.md`, or the import checks for an uploaded college |

Every number is calculated by the code in `nexus/`, not typed in. Where there is not enough
data, the app says so instead of guessing. Recommendations come with causes to rule out, not
diagnoses. The data has no electricity tariff, so rupees appear only after you enter your own
tariff in Settings, labelled as yours.

## Recommendations in detail
| Rule | Type | Triggered when (thresholds in `nexus/recommend.py`) |
|---|---|---|
| R1 Unusual high use | Investigate | An event 50%+ above expected for 3+ hours; the 5 largest |
| R2 Long low reading | Fix data | 24+ hours at 50%+ below expected |
| R3 High use when near-empty | Save energy | Near-empty hours use 60%+ of busy-hour energy |
| R4 Forecast differs from last year | Plan | The 14 days after the chosen week are forecast 15%+ above or below a year earlier |
| R5 Less reliable forecast | Plan | The forecast missed by 15%+ of a typical day in the test year |
| R6 Large always-on load | Save energy | The overnight minimum, running all day, is 50%+ of the building's energy |
| R7 Running on days off | Save energy | A day off uses 60%+ of a working day (not residences or dining halls) |
| R8 Campus peak demand | Cut peak | The highest campus hour is 15%+ above its 95th-percentile hour |
| R9 Big seasonal swing | Save energy | The 3 highest months add 15%+ to the year |

- Every rule looks at the **12 months ending on the Week ending date**. With less than a year of
  data the page says how many days there are, and rules that need more are skipped.
- **Energy at stake** is measured from the data (per year, scaled up where readings are
  missing). The campus peak is energy to *shift*, not save. Amounts of different rules overlap,
  so they are not added up.
- **Causes and actions** come from general building-energy practice in `nexus/playbook.py`,
  adapted to the building's type, which is guessed from its name (dorm/hostel → residence,
  dining/mess → dining hall, facilities/plant → plant). The 24 °C AC setting cites India's
  Bureau of Energy Efficiency.
- Meters flagged unreliable are left out.

## Setup
Needs Python 3.11 or newer (developed in GitHub Codespaces with Python 3.14).

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app only reads the small processed tables in `data/processed/`, which are committed, so it
runs without downloading the raw data.

### Dependencies (`requirements.txt`)
| Package | Version | Used for |
|---|---|---|
| streamlit | 1.64.0 | Web app |
| pandas | 3.0.6 | All data processing |
| altair | 6.3.0 | Charts |
| pyarrow | 25.0.1 | Reading and writing the parquet tables |
| anthropic | 0.40 or newer | Chatbot with Claude (optional) |
| requests | 2.31 or newer | College search, map lookups, Gemini chatbot |

### Chatbot setup
The conversation needs an API key in the app's secrets (Streamlit Cloud: Manage app →
Settings → Secrets). Never put a key in GitHub.

- **Free, Google Gemini:** create a key at https://aistudio.google.com/apikey and add
  `GEMINI_API_KEY = "..."`. Optionally `GEMINI_MODEL` (default `gemini-2.5-flash`; change it if
  Google retires that name). Free-tier limits and data terms are Google's and can change; on the
  free tier prompts may be used to improve Google's products, which is acceptable for public
  data only.
- **Anthropic:** `ANTHROPIC_API_KEY = "sk-ant-..."` (optionally `ANTHROPIC_MODEL`). Paid.
- If both are set, Gemini is used.

A public link lets anyone use your quota, so the app stops after 30 questions per session.
Without a key the Quick answers tab still works.

### Tests and command-line checks
```bash
python tests/test_recommend.py   # recommendation rules, playbooks, date windows
python tests/test_finder.py      # college search and map lookup (offline, fake responses)
python tests/test_chat.py        # chatbot tool loop (offline)
python -m nexus.data --check     # rebuild data/processed/ and print every data check

python -m nexus.resource         # baselines and unusual events
python -m nexus.institutional    # occupancy summary per building
python -m nexus.predictive       # forecast backtest and accuracy on 2017
python -m nexus.recommend        # every recommendation with its plan and evidence
python -m nexus.kpis 2016-09-14  # one week vs the week before
```

### Rebuilding the data from the raw files (optional)
1. Download the I-BLEND files from https://doi.org/10.6084/m9.figshare.c.3893581
   (energy dataset, occupancy dataset and calendar schedule).
2. Unzip them into `data/raw/` so these folders exist (delete any `__MACOSX` folders):
   - `data/raw/energy_dataset/`
   - `data/raw/IIITD_occupancy_dataset/`
   - `data/raw/iiitd_calender_schedule/`
3. Run `python scripts/inspect_raw.py` (read-only summary) and `python -m nexus.data --check`.

`data/raw/` is 1.6 GB and is listed in `.gitignore`. Never commit it. When committing, add
files by name instead of using `git add .`.

## Project structure
```
app.py                   Entry point: navigation, top bar, pages; reloads changed code after a push
views/                   One file per page, plus shell.py (top bar, search) and common.py (shared data)
nexus/data.py            Raw files -> hourly tables in data/processed/, plus data checks
nexus/resource.py        Baselines and unusual events
nexus/institutional.py   Occupancy patterns and energy when near-empty
nexus/predictive.py      Forecasts and backtest
nexus/recommend.py       Recommendation rules R1-R9, the 12-month window and the energy at stake
nexus/playbook.py        Solution plans: causes to rule out, staged actions with owners, how to check
nexus/kpis.py            Week-on-week cards and the Overview headline
nexus/insights.py        Overview panels: insights feed, 30-day trend, building hours, 2-week outlook
nexus/ask.py             Quick answers: question routing and rule-based answers
nexus/chat.py            Chatbot: Gemini or Claude plus lookup tools over NEXUS's tables
nexus/finder.py          College search: vetted list, Zenodo, Figshare, Harvard Dataverse
nexus/place.py           College on the map: OpenStreetMap lookup and building outlines
nexus/dataset.py         One college's data; nexus/importer.py turns an uploaded CSV into one
tests/                   Offline tests: recommendations, search and map lookup, chatbot
scripts/                 Raw data summary, logo generator
static/                  Logo and self-hosted fonts (SIL Open Font License)
.streamlit/config.toml   Theme: colours, fonts
DATA.md                  Source, license, files, cleaning decisions, limitations
data/processed/          Committed hourly tables the app reads
data/samples/            Public sample college (BDG2 site Fox, USA)
```

## Methods in brief
All thresholds are named constants at the top of each file in `nexus/`.

- **Hourly energy:** kWh from 1-minute power readings, only when at least 45 of 60 minutes were
  recorded; otherwise left blank. A dorm is mains + UPS.
- **Baseline (Resource):** for each hour, the median of comparable hours in the same building
  (same hour of day, working day or not, high or low activity day) within 3 weeks either side.
  An hour is unusual when it is more than 3.5 robust standard deviations and at least 10% away
  from that median, with at least 8 comparable hours. Consecutive unusual hours form one event.
- **Occupancy (Institutional):** Wi-Fi estimate of people per hour. Busy and near-empty hours are
  set relative to each building's own 95th-percentile hour. Energy in near-empty hours is
  compared with busy hours during semester weeks only.
- **Forecast (Predictive):** daily kWh, 14 days ahead. Method 1, "same weekday last week".
  Method 2, the median of recent days of the same calendar day type. Each building's method was
  chosen on 2013-2016 and scored on 2017, which was not used to choose it. The 80% range comes
  from past forecast errors.
- **Week cards (Overview):** the 7 days ending on the chosen date vs the 7 days before, hour for
  hour, counting only building-hours recorded in both weeks. Fewer than 50% comparable hours
  gives "Insufficient data".
- **Recommendations:** see [Recommendations in detail](#recommendations-in-detail).

## Other colleges
**Add college data** takes one CSV of meter readings (`timestamp`, `building`, and one of `kwh`,
`kw` or `w`; optional `people`) and an optional calendar. `nexus/importer.py` checks every row,
turns readings into hourly kWh with the same 75% rule, and reports what it set aside and why.
Uploaded files are kept in the server's memory for that visitor's session only; they are not
written to disk or shown to other visitors.

A public sample is included: 8 buildings from site Fox of the Building Data Genome Project 2 (a
US university campus, 2016-2017, CC BY-SA 4.0); see `data/samples/README.md`.

**Searching by name** is best effort. Few colleges publish meter data, so "College data
unavailable" is a normal, honest answer: nothing usable was found in Zenodo, Figshare or Harvard
Dataverse under an open licence, not that none exists. A search that could not reach the
repositories says so separately ("Could not search right now"). Data found online is labelled
with its record and licence and is never presented as PES data.

## Data
I-BLEND, IIIT-Delhi. Rashid, H., Singh, P. & Singh, A. (2019). *Scientific Data* 6, 190015.
https://doi.org/10.1038/sdata.2019.15. The energy, occupancy and calendar files are CC0 1.0
(public domain). See `DATA.md` for the raw files, units, coverage, every cleaning decision and
its evidence.

## Known issues
- **Lecture energy is not analysed.** Its meter reads exactly 0 W for 82% of recorded minutes,
  including 49% of class hours. Lecture occupancy is still used.
- **Facilities has very large spikes.** The largest events (more than 300% above expected) may be
  meter faults rather than real use, so the app flags them and suggests checking the meter first.
- **Large meter gaps:** the dorm mains and Library meters miss about 26-29% of minutes. Hours with
  too little data are left blank, not filled in; yearly amounts are scaled up and say so.
- **Occupancy is an estimate.** Wi-Fi counts devices, not people. In buildings that empty at
  night, missing 10-minute slots are read as 0 people (`DATA.md`, decision 5).
- **Building level only.** There are no rooms, timetables or capacities, so no room utilisation.
- **No weather data.** Forecasts have no weather input, and the seasonal-swing rule cannot
  separate cooling from term-time activity. In at least one building the calendar forecast did
  not beat the simple rule on 2017; the app says which.
- **The data ends in 2017.** The forecast starts the day after the data ends (1 Jan 2018 for
  IIIT-Delhi), so it is not a prediction for today.
- **Building types are guessed from names** for the recommendation playbooks; a building with an
  unusual name gets the general academic/office plan.
- **College search formats and the default Gemini model name** were written without live testing
  from the build environment; the offline tests use fake responses.
- **First load is slow on free hosting.** The app calculates baselines and the forecast backtest
  when it starts, then caches them.
- The three campus supply transformers in the dataset are not used yet.
