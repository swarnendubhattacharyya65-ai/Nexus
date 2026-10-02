"""Find out whether a college's energy data is public, and analyse it if it is.

search(name) looks, in this order:
  1. NEXUS's own short list of vetted public datasets (IIIT-Delhi's I-BLEND, the BDG2 sample)
  2. open research repositories: Zenodo, Figshare and Harvard Dataverse

A repository record is used only if its title or description names the college, it mentions
electricity or energy, its licence is open, and one of its CSV files has a time column and
energy columns with a clear unit (kWh, kW or W). Anything less is reported, never guessed.

The result's `status` is one of
  "found"        a dataset was loaded (`dataset`, `report`, `source`)
  "unavailable"  at least one repository answered and nothing usable was found
  "unreachable"  no repository could be asked (offline or blocked): this is NOT "unavailable"
"""
import io
import re

import pandas as pd
import requests

from nexus import importer, place as places
from nexus.dataset import IIITD

UA = places.UA
TIMEOUT = 12
MAX_FILE_MB = 60
MAX_RECORDS = 6          # records opened per repository
MAX_FILES = 3            # CSV files tried per record
GENERIC = {"university", "college", "institute", "institution", "of", "the", "technology",
           "engineering", "school", "campus", "and", "for", "in", "science", "sciences", "national"}
OPEN_LICENCE = re.compile(r"cc0|cc[- ]?by|cc[- ]?zero|public domain|pddl|odc|open data|mit\b|"
                          r"creative commons", re.I)
CLOSED_LICENCE = re.compile(r"nc|non[- ]?commercial|no[- ]?deriv|\bnd\b|restricted|closed", re.I)
ENERGY_WORDS = re.compile(r"electric|energy|kwh|meter|power|consumption", re.I)

# Vetted datasets that ship with NEXUS (nothing is downloaded for these).
REGISTRY = [
    {"aliases": ["iiit delhi", "iiit-delhi", "iiitd", "indraprastha institute of information technology"],
     "college": IIITD, "kind": "iiitd"},
    {"aliases": ["bdg2 fox", "bdg2 site fox", "sample bdg2 site fox usa"], "college": "Sample: BDG2 site Fox, USA", "kind": "sample"},
]


# ------------------------------------------------------------------ helpers

def norm(text):
    return re.sub(r"[^a-z0-9 ]+", " ", str(text).lower().replace("-", " ")).split()


def name_tokens(name):
    t = [w for w in norm(name) if w not in GENERIC]
    return t or norm(name)


def mentions(text, name):
    """Every significant word of the college's name appears as a whole word in `text`."""
    words = set(norm(text))
    return all(t in words for t in name_tokens(name))


def registry_hit(name):
    """Exact (spelling-insensitive) match on the first part of the name, e.g. 'IIIT-Delhi, New Delhi'."""
    q = " ".join(norm(name.split(",")[0]))
    for r in REGISTRY:
        if q in {" ".join(norm(a)) for a in r["aliases"]}:
            return r
    return None


def _get(url, **kw):
    try:
        r = requests.get(url, headers=UA, timeout=kw.pop("timeout", TIMEOUT), **kw)
        r.raise_for_status()
        return r
    except requests.RequestException as e:
        raise places.Unreachable(f"{url.split('/')[2]}: {type(e).__name__}") from e


def _json(url, **kw):
    try:
        return _get(url, **kw).json()
    except ValueError as e:
        raise places.Unreachable(f"{url.split('/')[2]}: bad answer") from e


def _post(url, body):
    try:
        r = requests.post(url, json=body, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as e:
        raise places.Unreachable(f"{url.split('/')[2]}: {type(e).__name__}") from e


def _download(url):
    """File bytes, refusing anything over MAX_FILE_MB."""
    r = _get(url, stream=True, timeout=60)
    buf, limit = io.BytesIO(), MAX_FILE_MB * 1024 * 1024
    for chunk in r.iter_content(1 << 20):
        buf.write(chunk)
        if buf.tell() > limit:
            raise places.Unreachable("file too large")
    return buf.getvalue()


# --------------------------------------------------- turning a found table into NEXUS's shape

UNIT = [("kwh", re.compile(r"kwh|kw[ _-]?h")), ("kw", re.compile(r"(^|[\W_])kw($|[\W_])")),
        ("w", re.compile(r"watt|(^|[\W_])w($|[\W_])"))]
SKIP = re.compile(r"temp|humid|price|cost|rate|co2|emission|tariff|pressure|wind|solar_rad", re.I)


def _unit_of(header):
    h = str(header).lower()
    if SKIP.search(h):
        return None
    for unit, pat in UNIT:
        if pat.search(h):
            return unit
    return None


def _time_column(df):
    for c in df.columns:
        if not re.search(r"time|date|stamp|hour", str(c), re.I) or pd.api.types.is_numeric_dtype(df[c]):
            continue
        sample = pd.to_datetime(df[c].head(200), errors="coerce", format="mixed")
        if sample.notna().mean() >= 0.9:
            return c
    return None


def _clean_name(header):
    """'Main Block (kWh)' / 'Main_Block_kwh' -> 'Main Block'; the unit is already known."""
    h = re.sub(r"[\(\[]\s*(kwh|kw|w|watts?)\s*[\)\]]", "", str(header), flags=re.I)
    h = re.sub(r"[ _-]+(kwh|kw|w|watts?)$", "", h.strip(), flags=re.I)
    return h.replace("_", " ").strip() or str(header)


def to_raw(df):
    """A table with a time column and unit-labelled energy columns -> importer's raw format.

    Raises importer.ImportProblem with the reason when the table cannot be read with certainty.
    """
    t = _time_column(df)
    if t is None:
        raise importer.ImportProblem("no time column")
    units = {c: _unit_of(c) for c in df.columns if c != t and pd.api.types.is_numeric_dtype(df[c])}
    units = {c: u for c, u in units.items() if u}
    if not units:
        raise importer.ImportProblem("no energy column with a clear unit (kWh, kW or W)")
    if len(set(units.values())) != 1:
        raise importer.ImportProblem("energy columns use mixed units")
    unit = next(iter(units.values()))
    cols = list(units)
    building_col = next((c for c in df.columns if re.search(r"building|meter|site|facility", str(c), re.I)
                         and not pd.api.types.is_numeric_dtype(df[c])), None)
    if building_col is not None and len(cols) == 1:                 # long format
        out = pd.DataFrame({"timestamp": df[t], "building": df[building_col], unit: df[cols[0]]})
    else:                                                           # one column per building
        out = df[[t, *cols]].melt(id_vars=t, var_name="building", value_name=unit)
        out = out.rename(columns={t: "timestamp"})
        out["building"] = out["building"].map(_clean_name)
    return out


def analyse(name, df, source):
    """Run a found table through NEXUS's importer. Returns (Dataset, report)."""
    return importer.build(name, to_raw(df), None, source)


# ------------------------------------------------------------------ repositories
# Each returns candidate records: {title, url, licence, files: [(name, size, download_url)], text}.

def zenodo(query, http=_json):
    data = http("https://zenodo.org/api/records", params={"q": query, "size": 20, "type": "dataset"})
    out = []
    for h in data.get("hits", {}).get("hits", []):
        m = h.get("metadata", {})
        lic = (m.get("license") or {}).get("id", "")
        files = [(f.get("key", ""), f.get("size", 0), (f.get("links") or {}).get("self", ""))
                 for f in h.get("files", [])]
        out.append({"source": "Zenodo", "title": m.get("title", ""), "text": m.get("description", ""),
                    "url": (h.get("links") or {}).get("self_html") or f"https://zenodo.org/records/{h.get('id')}",
                    "licence": lic, "files": files})
    return out


def figshare(query, http=_json, post=_post):
    rows = post("https://api.figshare.com/v2/articles/search",
                {"search_for": query, "page_size": 20, "item_type": 3})
    out = []
    for r in rows[:MAX_RECORDS * 2]:
        out.append({"source": "Figshare", "title": r.get("title", ""), "text": "",
                    "url": r.get("url_public_html") or r.get("doi", ""), "licence": "",
                    "files": [], "_id": r.get("id")})
    return out


def figshare_detail(rec, http=_json):
    a = http(f"https://api.figshare.com/v2/articles/{rec['_id']}")
    rec["text"] = re.sub(r"<[^>]+>", " ", a.get("description", "") or "")
    rec["licence"] = (a.get("license") or {}).get("name", "")
    rec["files"] = [(f.get("name", ""), f.get("size", 0), f.get("download_url", "")) for f in a.get("files", [])]
    return rec


def dataverse(query, http=_json):
    base = "https://dataverse.harvard.edu"
    data = http(f"{base}/api/search", params={"q": query, "type": "dataset", "per_page": 20})
    out = []
    for i in data.get("data", {}).get("items", []):
        out.append({"source": "Harvard Dataverse", "title": i.get("name", ""),
                    "text": i.get("description", ""), "url": i.get("url", ""), "licence": "",
                    "files": [], "_pid": i.get("global_id")})
    return out


def dataverse_detail(rec, http=_json):
    base = "https://dataverse.harvard.edu"
    d = http(f"{base}/api/datasets/:persistentId/", params={"persistentId": rec["_pid"]})
    v = d.get("data", {}).get("latestVersion", {})
    rec["licence"] = (v.get("license") or {}).get("name", "") if isinstance(v.get("license"), dict) else str(v.get("license") or "")
    rec["files"] = [(f.get("label", ""), (f.get("dataFile") or {}).get("filesize", 0),
                     f"{base}/api/access/datafile/{(f.get('dataFile') or {}).get('id')}")
                    for f in v.get("files", [])]
    return rec


def relevant(rec, name):
    return mentions(f"{rec['title']} {rec['text']}", name) and bool(ENERGY_WORDS.search(f"{rec['title']} {rec['text']}"))


def usable_files(rec):
    out = []
    for fname, size, url in rec["files"]:
        low = fname.lower()
        if (low.endswith(".csv") or low.endswith(".csv.gz")) and url and (size or 0) <= MAX_FILE_MB * 1024 * 1024:
            out.append((0 if re.search(r"energy|electric|meter|kwh|consum|load", low) else 1, fname, url))
    return [(n, u) for _, n, u in sorted(out)][:MAX_FILES]


# ------------------------------------------------------------------ the search

SOURCES = ["Zenodo", "Figshare", "Harvard Dataverse"]


def search(name, fetchers=None, download=_download):
    """Look for `name`'s public energy data. See the module docstring for the result."""
    name = " ".join(name.split())
    out = {"query": name, "status": "unavailable", "dataset": None, "report": None, "source": "",
           "candidates": [], "checked": [], "failed": [], "tried": []}
    hit = registry_hit(name)
    if hit:
        out.update(status="found", registry=hit["kind"], college=hit["college"],
                   source="NEXUS's list of vetted public datasets", checked=["NEXUS's list"])
        return out

    fetchers = fetchers or {
        "Zenodo": (zenodo, None), "Figshare": (figshare, figshare_detail),
        "Harvard Dataverse": (dataverse, dataverse_detail)}
    query = f"{name} electricity"
    for source, (find, detail) in fetchers.items():
        try:
            records = find(query)
        except places.Unreachable as e:
            out["failed"].append(f"{source} ({e})")
            continue
        out["checked"].append(source)
        # The college must be named in the title or description before anything is opened.
        named = [r for r in records if mentions(f"{r['title']} {r['text']}", name)]
        for rec in named[:MAX_RECORDS]:
            try:
                rec = detail(rec) if detail else rec
            except places.Unreachable:
                continue
            if not relevant(rec, name):
                continue
            lic = rec["licence"]
            note = {"title": rec["title"], "url": rec["url"], "source": source,
                    "licence": lic or "not stated"}
            if not lic or CLOSED_LICENCE.search(lic) or not OPEN_LICENCE.search(lic):
                note["why"] = "its licence is not clearly open, so NEXUS did not download it"
                out["candidates"].append(note)
                continue
            for fname, url in usable_files(rec):
                try:
                    df = importer.read_csv(download(url), fname)
                    src = f"Public data found online: {rec['title']} ({source}, {lic}). Not PES data."
                    ds, report = analyse(name, df, src)
                except Exception as e:   # unreadable file, wrong shape, too short: try the next one
                    out["tried"].append(f"{fname}: {e}")
                    continue
                out.update(status="found", dataset=ds, report=report, source=src,
                           candidates=[{**note, "why": "used"}])
                return out
            note["why"] = "no CSV file NEXUS could read with certainty"
            out["candidates"].append(note)
    if not out["checked"]:
        out["status"] = "unreachable"
    return out
