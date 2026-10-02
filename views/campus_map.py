"""Campus Map: IIIT-Delhi's real building outlines in 3D, coloured by NEXUS findings.

Building outlines come from OpenStreetMap (scripts/fetch_campus.py). The I-BLEND buildings
are matched to outlines in data/campus/building_map.csv; everything else is drawn dim.
"""
import json
import math
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from nexus.data import ENERGY_WARNINGS, OUT
from nexus.kpis import HOURS_PER_WEEK, compare, window

CAMPUS = Path(os.environ.get("NEXUS_CAMPUS_DIR", "data/campus"))
LEVEL_M = 3.5          # metres per floor when OpenStreetMap records floors
DEFAULT_M = 12.0       # height when it records neither floors nor height
MAPLIBRE = "https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1/dist/maplibre-gl"

# Colours: status (fixed meanings), diverging blue-grey-red, sequential blue.
NORMAL, HIGH, LOW, NO_DATA, OTHER = "#3987e5", "#ec835a", "#9085e9", "#5b6478", "#1f2c4a"
RAMP = ["#0d366b", "#1c5cab", "#3987e5", "#86b6ef", "#cde2fb"]


# --------------------------------------------------------------- geometry

def matches():
    """Which outline each I-BLEND building was matched to, and how."""
    return pd.read_csv(CAMPUS / "building_map.csv")


def outlines_ready():
    return (CAMPUS / "buildings.geojson").exists() and (CAMPUS / "building_map.csv").exists()


@st.cache_data(show_spinner=False)
def load_outlines():
    """Campus features with heights and, where matched, the I-BLEND building name."""
    gj = json.loads((CAMPUS / "buildings.geojson").read_text())
    match = pd.read_csv(CAMPUS / "building_map.csv")
    nexus_of = dict(zip(match["osm_id"], match["nexus_building"]))
    buildings, campus = [], []
    for f in gj["features"]:
        p = f["properties"]
        if p.get("kind") == "campus":
            campus.append(f)
            continue
        height = _height(p)
        ring = f["geometry"]["coordinates"][0]
        buildings.append({
            "type": "Feature", "id": p["osm_id"], "geometry": f["geometry"],
            "properties": {"osm_id": p["osm_id"], "osm_name": p.get("name", ""),
                           "nexus": nexus_of.get(p["osm_id"]), "height": height,
                           "center": _centroid(ring)},
        })
    return buildings, campus


def _height(p):
    for key, scale in (("height", 1.0), ("levels", LEVEL_M)):
        try:
            return round(float(str(p.get(key, "")).split()[0]) * scale, 1)
        except (ValueError, IndexError):
            pass
    return DEFAULT_M


def _centroid(ring):
    xs, ys = [c[0] for c in ring[:-1]], [c[1] for c in ring[:-1]]
    return [sum(xs) / len(xs), sum(ys) / len(ys)]


# ----------------------------------------------------------------- status

@st.cache_data(show_spinner="Reading the week for each building ...")
def week_status(week_end, _df, _occ):
    """One row per I-BLEND building: what the map shows for the chosen week."""
    start, end = window(week_end)
    w = _df[(_df["hour"] >= start) & (_df["hour"] < end)]
    energy = _df[["hour", "building", "kwh"]]
    change = compare(energy, "kwh", week_end)["per_building"].set_index("building")

    occ = _occ.dropna(subset=["occ_mean"])
    busy_level = occ.groupby("building")["occ_mean"].quantile(0.95)
    ow = occ[(occ["hour"] >= start) & (occ["hour"] < end)]
    day = ow[(ow["hour"].dt.dayofweek < 5) & ow["hour"].dt.hour.between(9, 16)]
    daytime = day.groupby("building")["occ_mean"].median()

    rows = []
    for b in sorted(_df["building"].unique()):
        g = w[w["building"] == b]
        recorded = int(g["kwh"].notna().sum())
        rows.append({
            "building": b,
            "unreliable": b in ENERGY_WARNINGS,
            "hours_recorded": recorded,
            "kwh": g["kwh"].sum() if recorded and b not in ENERGY_WARNINGS else None,
            "high_hours": int((g["flag"] == "high").sum()),
            "low_hours": int((g["flag"] == "low").sum()),
            "change": change["change"].get(b) if b not in ENERGY_WARNINGS else None,
            "wifi_daytime": daytime.get(b),
            "wifi_share": daytime.get(b) / busy_level.get(b) if b in daytime and busy_level.get(b) else None,
        })
    return pd.DataFrame(rows)


def _layers_for(r):
    """Colour and label for each map layer, for one building's row."""
    enough = r["hours_recorded"] >= HOURS_PER_WEEK / 2
    if r["unreliable"]:
        unusual = (NO_DATA, "Energy meter unreliable")
    elif not enough:
        unusual = (NO_DATA, "Not enough meter data")
    elif r["high_hours"]:
        unusual = (HIGH, f"{r['high_hours']} hour{'s' if r['high_hours'] != 1 else ''} higher than usual")
    elif r["low_hours"]:
        unusual = (LOW, f"{r['low_hours']} hour{'s' if r['low_hours'] != 1 else ''} lower than usual")
    else:
        unusual = (NORMAL, "Normal all week")

    c = r["change"]
    if c is None or pd.isna(c):
        change = (NO_DATA, "No comparison" if not r["unreliable"] else "Energy meter unreliable")
    else:
        change = (_diverging(c), f"{c:+.0%} vs last week")

    s = r["wifi_share"]
    if s is None or pd.isna(s):
        wifi = (NO_DATA, "No Wi-Fi data this week")
    else:
        wifi = (_ramp(min(s, 1.0)), f"Weekday daytime: {s:.0%} of usual peak")
    return {"unusual": unusual, "change": change, "wifi": wifi}


def _mix(a, b, t):
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(pa, pb))


def _diverging(change, limit=0.25):
    t = max(-1.0, min(1.0, change / limit))
    return _mix("#5b6478", "#e66767", t) if t >= 0 else _mix("#5b6478", "#3987e5", -t)


def _ramp(share):
    pos = share * (len(RAMP) - 1)
    i = min(int(math.floor(pos)), len(RAMP) - 2)
    return _mix(RAMP[i], RAMP[i + 1], pos - i)


LEGENDS = {
    "unusual": [(HIGH, "Higher than usual"), (LOW, "Lower than usual"), (NORMAL, "Normal"),
                (NO_DATA, "No reliable data"), (OTHER, "Not metered in this dataset")],
    "change": [("#e66767", "25% or more above last week"), ("#5b6478", "About the same"),
               ("#3987e5", "25% or more below"), (OTHER, "Not metered in this dataset")],
    "wifi": [(RAMP[-1], "At usual peak"), (RAMP[2], "About half"), (RAMP[0], "Near-empty"),
             (NO_DATA, "No Wi-Fi data"), (OTHER, "Not metered in this dataset")],
}
LAYER_NAMES = {"unusual": "Unusual hours", "change": "vs last week", "wifi": "Wi-Fi activity"}


# ----------------------------------------------------------------- replay

REPLAY_DAYS = 84   # 12 weeks ending on the chosen date


@st.cache_data(show_spinner="Preparing the replay ...")
def timeline(week_end, _df, _occ, days=REPLAY_DAYS):
    """Each matched building's colour and label for every day of the replay, per layer.

    unusual: hours flagged higher or lower than usual that day.
    change:  that day's kWh vs the median of the same weekday over the 4 weeks before.
    wifi:    weekday daytime (09:00-17:00) people as a share of the building's usual peak.
    """
    end = pd.Timestamp(week_end).normalize() + pd.Timedelta(days=1)
    start = end - pd.Timedelta(days=days)
    dates = pd.date_range(start, end - pd.Timedelta(days=1))
    d = _df[(_df["hour"] >= start - pd.Timedelta(days=28)) & (_df["hour"] < end)].copy()
    d["day"] = d["hour"].dt.normalize()
    per_day = d.groupby(["building", "day"]).agg(
        kwh=("kwh", "sum"), hours=("kwh", "count"),
        high=("flag", lambda f: int((f == "high").sum())), low=("flag", lambda f: int((f == "low").sum())))
    occ = _occ.dropna(subset=["occ_mean"]) if _occ is not None else None
    level = occ.groupby("building")["occ_mean"].quantile(0.95) if occ is not None else pd.Series(dtype=float)
    if occ is not None:
        o = occ[(occ["hour"] >= start) & (occ["hour"] < end)
                & (occ["hour"].dt.dayofweek < 5) & occ["hour"].dt.hour.between(9, 16)]
        daytime = o.groupby(["building", o["hour"].dt.normalize()])["occ_mean"].median()
    out = {}
    for b in sorted(d["building"].unique()):
        if b in ENERGY_WARNINGS:
            continue
        unusual, change, wifi = [], [], []
        for day in dates:
            r = per_day.loc[(b, day)] if (b, day) in per_day.index else None
            full = r is not None and r["hours"] >= 18
            if not full:
                unusual.append([NO_DATA, "Not enough meter data"])
                change.append([NO_DATA, "Not enough meter data"])
            else:
                if r["high"]:
                    unusual.append([HIGH, f"{r['high']} hour{'s' if r['high'] != 1 else ''} higher than usual"])
                elif r["low"]:
                    unusual.append([LOW, f"{r['low']} hour{'s' if r['low'] != 1 else ''} lower than usual"])
                else:
                    unusual.append([NORMAL, "Normal"])
                same = [day - pd.Timedelta(days=7 * k) for k in range(1, 5)]
                ref = [per_day.loc[(b, x)]["kwh"] for x in same
                       if (b, x) in per_day.index and per_day.loc[(b, x)]["hours"] == 24]
                if len(ref) >= 2 and r["hours"] == 24:
                    c = r["kwh"] / pd.Series(ref).median() - 1
                    change.append([_diverging(c), f"{c:+.0%} vs a typical {day:%A}"])
                else:
                    change.append([NO_DATA, "No typical day to compare"])
            share = None
            if occ is not None and day.dayofweek < 5 and (b, day) in daytime.index and level.get(b):
                share = daytime.loc[(b, day)] / level[b]
            wifi.append([_ramp(min(share, 1.0)), f"Daytime: {share:.0%} of usual peak"] if share is not None
                        else [NO_DATA, "Weekend" if day.dayofweek >= 5 else "No Wi-Fi data"])
        out[b] = {"unusual": unusual, "change": change, "wifi": wifi}
    return {"labels": [f"{x:%a %-d %b %Y}" for x in dates], "buildings": out}


# -------------------------------------------------------------------- map

def payload(buildings, campus, status, week_label, replay=None):
    rows = status.set_index("building").to_dict("index")
    features = []
    for f in buildings:
        p = dict(f["properties"])
        if p["nexus"] in rows:
            for layer, (color, label) in _layers_for(rows[p["nexus"]]).items():
                p[f"color_{layer}"], p[f"label_{layer}"] = color, label
        else:
            p["nexus"] = None
            for layer in LEGENDS:
                p[f"color_{layer}"], p[f"label_{layer}"] = OTHER, ""
        features.append({**f, "properties": p})
    matched = [f["properties"]["center"] for f in features if f["properties"]["nexus"]]
    center = ([sum(c[0] for c in matched) / len(matched), sum(c[1] for c in matched) / len(matched)]
              if matched else [77.2725, 28.54444])
    pts = [c for f in features if f["properties"]["nexus"] for c in f["geometry"]["coordinates"][0]]
    bounds = ([[min(c[0] for c in pts), min(c[1] for c in pts)],
               [max(c[0] for c in pts), max(c[1] for c in pts)]] if pts else None)
    return {
        "center": center,
        "bounds": bounds,
        "features": {"type": "FeatureCollection", "features": features},
        "campus": {"type": "FeatureCollection", "features": campus},
        "layers": [{"id": k, "name": v, "legend": LEGENDS[k]} for k, v in LAYER_NAMES.items()],
        "week": week_label,
        "timeline": replay,
    }


def render(data, height=600, layer="unusual", key="campus_map"):
    """Draw the map. Returns the component result; `.picked` is the last building tapped."""
    return _MAP(data={**data, "height": height, "layer": layer}, key=key,
                on_picked_change=lambda: None)


CSS = """
.nx-map-root { position: relative; width: 100%; border-radius: 18px; overflow: hidden;
  border: 1px solid rgba(127,178,255,0.22); background: #0a1020;
  font-family: "IBM Plex Sans", system-ui, sans-serif; color: #e6ecfa; }
.nx-map-root .nx-canvas { position: absolute; inset: 0; }
.nx-map-root .nx-panel { position: absolute; z-index: 2; background: rgba(10,16,32,0.8);
  border: 1px solid rgba(127,178,255,0.2); border-radius: 12px; backdrop-filter: blur(6px); }
.nx-map-root .nx-modes { left: 12px; top: 12px; padding: 6px; display: flex; flex-direction: column; gap: 4px; }
.nx-map-root .nx-modes button { font: 500 13px "IBM Plex Sans", system-ui, sans-serif; color: #b9c6e4;
  background: transparent; border: 1px solid transparent; border-radius: 8px;
  padding: 7px 10px; text-align: left; cursor: pointer; }
.nx-map-root .nx-modes button[aria-pressed="true"] { color: #fff; background: rgba(79,140,255,0.22);
  border-color: rgba(127,178,255,0.45); }
.nx-map-root .nx-modes button:focus-visible { outline: 2px solid #8ab4ff; outline-offset: 1px; }
.nx-map-root .nx-modes hr { border: 0; border-top: 1px solid rgba(127,178,255,0.18); margin: 4px 2px; }
.nx-map-root .nx-legend { left: 12px; bottom: 12px; padding: 10px 12px; font-size: 12px;
  color: #b9c6e4; max-width: 260px; }
.nx-map-root .nx-legend h4 { font: 600 13px "Chakra Petch", system-ui, sans-serif; color: #f2f6ff;
  margin: 0 0 6px; padding: 0; letter-spacing: .02em; }
.nx-map-root .nx-legend div { display: flex; align-items: center; gap: 8px; margin: 3px 0; }
.nx-map-root .nx-legend i { width: 12px; height: 12px; border-radius: 3px; flex: none; }
.nx-map-root .nx-week { right: 12px; bottom: 34px; padding: 7px 11px; font-size: 12px; color: #b9c6e4; }
.nx-map-root .nx-replay { right: 12px; bottom: 34px; padding: 8px 10px; display: none;
  align-items: center; gap: 10px; width: min(420px, calc(100% - 300px)); }
.nx-map-root.nx-has-replay .nx-replay { display: flex; }
.nx-map-root.nx-has-replay .nx-week { display: none; }
.nx-map-root .nx-replay button { width: 34px; height: 34px; flex: none; border-radius: 50%; cursor: pointer;
  border: 1px solid rgba(127,178,255,0.5); background: rgba(79,140,255,0.25); color: #fff;
  font: 600 14px system-ui, sans-serif; }
.nx-map-root .nx-replay button:focus-visible { outline: 2px solid #8ab4ff; outline-offset: 2px; }
.nx-map-root .nx-replay input { flex: 1; min-width: 80px; accent-color: #4f8cff; }
.nx-map-root .nx-replay span { font-size: 12px; color: #e6ecfa; white-space: nowrap; min-width: 112px; }
.nx-map-root.nx-compact .nx-modes { flex-direction: row; flex-wrap: wrap; max-width: calc(100% - 70px); }
.nx-map-root.nx-compact .nx-modes button { padding: 5px 8px; font-size: 12px; }
.nx-map-root.nx-compact .nx-modes hr { display: none; }
.nx-map-root.nx-compact .nx-legend { padding: 7px 9px; font-size: 11px; max-width: 200px; }
.nx-map-root.nx-compact .nx-legend div:last-child { display: none; }
.nx-map-root.nx-compact .nx-week { display: none; }
.nx-pin { pointer-events: none; }
.nx-tag { --c: #3987e5; --lift: 30px; position: relative; pointer-events: auto;
  margin-bottom: var(--lift); font: 600 12px "IBM Plex Sans", system-ui, sans-serif; color: #f2f6ff;
  background: rgba(10,16,32,0.86); border: 1px solid var(--c); border-radius: 9px;
  padding: 5px 9px; white-space: nowrap; cursor: pointer; line-height: 1.3;
  box-shadow: 0 0 16px -4px var(--c); transition: margin-bottom .2s ease; }
.nx-tag small { display: block; font-weight: 500; font-size: 11px; color: #b9c6e4; }
.nx-tag::after { content: ""; position: absolute; left: 50%; top: 100%; height: var(--lift);
  border-left: 1px solid var(--c); opacity: .7; }
.nx-tag:focus-visible { outline: 2px solid #8ab4ff; outline-offset: 2px; }
.nx-map-root .maplibregl-ctrl-group { background: rgba(10,16,32,0.8); }
.nx-map-root .maplibregl-ctrl-group button .maplibregl-ctrl-icon { filter: invert(1); }
.nx-map-root .maplibregl-ctrl-attrib { background: rgba(10,16,32,0.7); color: #8b94a8; font-size: 10px; }
.nx-map-root .maplibregl-ctrl-attrib a { color: #a3b0cc; }
.nx-map-root .nx-error { position: absolute; inset: 0; display: grid; place-items: center;
  color: #a3b0cc; font-size: 14px; padding: 24px; text-align: center; }
"""

HTML = """
<div class="nx-map-root" role="region" aria-label="3D map of the IIIT-Delhi campus">
  <div class="nx-canvas"></div>
  <div class="nx-panel nx-modes" role="toolbar" aria-label="Map layers"></div>
  <div class="nx-panel nx-legend" aria-live="polite"></div>
  <div class="nx-panel nx-week"></div>
  <div class="nx-panel nx-replay" role="group" aria-label="Replay the last 12 weeks"></div>
</div>
"""

JS = """
const ML = "__MAPLIBRE__";

function loadMapLibre() {
  if (window.maplibregl) return Promise.resolve(window.maplibregl);
  if (!window.__nxMapLibre) {
    window.__nxMapLibre = new Promise((resolve, reject) => {
      const css = document.createElement("link");
      css.rel = "stylesheet"; css.href = ML + ".css"; document.head.appendChild(css);
      const js = document.createElement("script");
      js.src = ML + ".js"; js.onload = () => resolve(window.maplibregl); js.onerror = reject;
      document.head.appendChild(js);
    });
  }
  return window.__nxMapLibre;
}

const BASE = {
  version: 8,
  sources: {
    dark: { type: "raster", tileSize: 256,
      tiles: ["a", "b", "c", "d"].map(s => `https://${s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png`),
      attribution: "© OpenStreetMap contributors © CARTO" },
    sat: { type: "raster", tileSize: 256,
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      attribution: "Imagery © Esri, Maxar, Earthstar Geographics" }
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#0a1020" } },
    { id: "dark", type: "raster", source: "dark", paint: { "raster-opacity": 0.9 } },
    { id: "sat", type: "raster", source: "sat", layout: { visibility: "none" },
      paint: { "raster-brightness-max": 0.75, "raster-saturation": -0.2 } }
  ]
};

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector(".nx-map-root");
  root.style.height = data.height + "px";
  root.classList.toggle("nx-compact", data.height < 560);
  const state = root.__nx || (root.__nx = { layer: data.layer, satellite: false, markers: [] });
  state.data = data;
  root.querySelector(".nx-week").textContent = data.week;

  loadMapLibre().then(maplibregl => {
    if (!state.map) build(maplibregl, root, state, setTriggerValue);
    else refresh(state);
  }).catch(() => {
    root.querySelector(".nx-canvas").innerHTML =
      '<div class="nx-error">The map library could not load. Check the internet connection and reload.</div>';
  });

  return () => {
    if (state.map) { state.map.remove(); state.map = null; }
    root.__nx = null;
  };
}

function build(maplibregl, root, state, setTriggerValue) {
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const map = new maplibregl.Map({
    container: root.querySelector(".nx-canvas"), style: BASE, center: state.data.center,
    zoom: 16.6, pitch: 58, bearing: -28, maxPitch: 75, attributionControl: false
  });
  state.map = map; state.maplibregl = maplibregl;
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
  map.addControl(new maplibregl.AttributionControl({ compact: true,
    customAttribution: "Buildings © OpenStreetMap contributors (ODbL)" }), "bottom-right");

  const init = () => {
    if (state.ready || !map.isStyleLoaded()) return;
    state.ready = true;
    map.addSource("campus", { type: "geojson", data: state.data.campus });
    map.addSource("b", { type: "geojson", data: state.data.features, promoteId: "osm_id" });
    map.addLayer({ id: "campus-line", type: "line", source: "campus",
      paint: { "line-color": "#8ab4ff", "line-width": 1.5, "line-dasharray": [2, 2], "line-opacity": 0.6 } });
    map.addLayer({ id: "glow", type: "line", source: "b", filter: ["!=", ["get", "nexus"], null],
      paint: { "line-color": colorOf(state.layer), "line-width": 6, "line-blur": 6, "line-opacity": 0.85 } });
    map.addLayer({ id: "extrude", type: "fill-extrusion", source: "b",
      paint: { "fill-extrusion-color": colorOf(state.layer),
               "fill-extrusion-height": ["get", "height"], "fill-extrusion-opacity": 0.92,
               "fill-extrusion-vertical-gradient": true } });
    map.on("click", "extrude", e => {
      const name = e.features[0] && e.features[0].properties.nexus;
      if (name && name !== "null") setTriggerValue("picked", name);
    });
    map.on("mouseenter", "extrude", () => map.getCanvas().style.cursor = "pointer");
    map.on("mouseleave", "extrude", () => map.getCanvas().style.cursor = "");
    state.pick = setTriggerValue;
    if (state.data.bounds) {
      // Frame the metered buildings; looking west puts the campus's long north-south axis across the screen.
      const box = root.getBoundingClientRect(), compact = state.data.height < 560;
      map.fitBounds(state.data.bounds, {
        padding: { top: Math.round(box.height * (compact ? 0.3 : 0.2)), bottom: Math.round(box.height * 0.14),
                   left: Math.round(compact ? box.width * 0.16 : 190),
                   right: Math.round(box.width * (compact ? 0.16 : 0.08)) },
        bearing: -78, pitch: 55, duration: 0, maxZoom: 17.2 });
    }
    paint(state);
    if (!still) {
      map.easeTo({ bearing: map.getBearing() + 40, duration: 16000, easing: t => t });
      ["mousedown", "touchstart", "wheel"].forEach(ev => map.on(ev, () => map.stop()));
    }
  };
  map.on("style.load", init);
  map.on("load", init);
  const poll = setInterval(() => { init(); if (state.ready || !state.map) clearInterval(poll); }, 150);
  drawModes(root, state);
}

function refresh(state) {
  if (!state.ready) return;
  state.map.getSource("b").setData(state.data.features);
  state.map.getSource("campus").setData(state.data.campus);
  paint(state);
}

function paint(state) {
  const { map, layer } = state;
  map.setPaintProperty("extrude", "fill-extrusion-color", colorOf(layer));
  map.setPaintProperty("glow", "line-color", colorOf(layer));
  state.markers.forEach(m => m.remove());
  state.markers = state.data.features.features.filter(f => f.properties.nexus).map(f => {
    const p = f.properties, pin = document.createElement("div"), el = document.createElement("div");
    pin.className = "nx-pin"; pin.appendChild(el);
    el.className = "nx-tag"; el.style.setProperty("--c", p["color_" + layer]);
    el.innerHTML = `${p.nexus}<small>${p["label_" + layer]}</small>`;
    el.dataset.b = p.nexus; el.dataset.osm = p.osm_id;
    el.setAttribute("role", "button"); el.tabIndex = 0;
    el.setAttribute("aria-label", `${p.nexus}: ${p["label_" + layer]}`);
    el.onclick = () => state.pick && state.pick("picked", p.nexus);
    el.onkeydown = e => { if (e.key === "Enter") el.onclick(); };
    return new state.maplibregl.Marker({ element: pin, anchor: "bottom" }).setLngLat(p.center).addTo(map);
  });
  if (!state.declutterOn) {
    state.declutterOn = true;
    let queued = false;
    map.on("move", () => { if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; declutter(state); }); } });
  }
  declutter(state);
  const root = map.getContainer().closest(".nx-map-root");
  const L = state.data.layers.find(l => l.id === layer);
  root.querySelector(".nx-legend").innerHTML = `<h4>${L.name}</h4>` +
    L.legend.map(([c, t]) => `<div><i style="background:${c}"></i>${t}</div>`).join("");
  drawModes(root, state);
  drawReplay(root, state);
  if (state.day != null) showDay(state, state.day);
}

// During the replay a building's colour comes from its feature-state; otherwise from the week.
function colorOf(layer) {
  return ["coalesce", ["feature-state", "c"], ["get", "color_" + layer]];
}

function drawReplay(root, state) {
  const T = state.data.timeline;
  root.classList.toggle("nx-has-replay", !!T);
  if (!T || root.querySelector(".nx-replay input")) return;
  const last = T.labels.length - 1, box = root.querySelector(".nx-replay");
  box.innerHTML = `<button type="button" aria-label="Play the last 12 weeks, one day at a time">▶</button>
    <input type="range" min="0" max="${last}" value="${last}" aria-label="Day">
    <span aria-live="polite">Week view</span>`;
  const btn = box.querySelector("button"), range = box.querySelector("input");
  const stop = () => { clearInterval(state.timer); state.timer = null; btn.textContent = "▶";
                       btn.setAttribute("aria-label", "Play the last 12 weeks, one day at a time"); };
  btn.onclick = () => {
    if (state.timer) return stop();
    let i = state.day == null || state.day >= last ? 0 : state.day + 1;
    btn.textContent = "❚❚"; btn.setAttribute("aria-label", "Pause");
    showDay(state, i);
    state.timer = setInterval(() => { i += 1; if (i > last) return stop(); showDay(state, i); }, 650);
  };
  range.oninput = () => { stop(); showDay(state, +range.value); };
}

function showDay(state, i) {
  const T = state.data.timeline, map = state.map, root = map.getContainer().closest(".nx-map-root");
  state.day = i;
  root.querySelector(".nx-replay input").value = i;
  root.querySelector(".nx-replay span").textContent = T.labels[i];
  state.markers.forEach(m => {
    const el = m.getElement().firstChild, series = T.buildings[el.dataset.b];
    if (!series) return;
    const [color, label] = series[state.layer][i];
    map.setFeatureState({ source: "b", id: el.dataset.osm }, { c: color });
    el.style.setProperty("--c", color);
    el.innerHTML = `${el.dataset.b}<small>${label}</small>`;
  });
  declutter(state);
}

// Stack labels that would overlap on screen: each one rises until it clears the others.
function declutter(state) {
  const placed = [];
  state.markers
    .map(m => { const el = m.getElement().firstChild, pt = state.map.project(m.getLngLat());
                return { el, x: pt.x, y: pt.y, w: el.offsetWidth + 8, h: el.offsetHeight + 6 }; })
    .sort((a, b) => b.y - a.y)
    .forEach(it => {
      let lift = 30;
      for (let tries = 0; tries < 6; tries++) {
        const top = it.y - lift - it.h;
        const hit = placed.some(o => Math.abs(o.x - it.x) < (o.w + it.w) / 2 &&
                                     top < o.top + o.h && top + it.h > o.top);
        if (!hit) break;
        lift += it.h;
      }
      it.top = it.y - lift - it.h;
      it.el.style.setProperty("--lift", lift + "px");
      placed.push(it);
    });
}

function drawModes(root, state) {
  const box = root.querySelector(".nx-modes");
  box.innerHTML = state.data.layers.map(l =>
    `<button type="button" aria-pressed="${l.id === state.layer}" data-l="${l.id}">${l.name}</button>`).join("") +
    `<hr><button type="button" aria-pressed="${state.satellite}" data-s="1">Satellite view</button>`;
  box.querySelectorAll("button[data-l]").forEach(b => b.onclick = () => {
    state.layer = b.dataset.l;
    if (state.ready) paint(state); else drawModes(root, state);
  });
  box.querySelector("button[data-s]").onclick = () => {
    state.satellite = !state.satellite;
    if (state.map && state.map.getLayer("sat"))
      state.map.setLayoutProperty("sat", "visibility", state.satellite ? "visible" : "none");
    drawModes(root, state);
  };
}
""".replace("__MAPLIBRE__", MAPLIBRE)

_MAP = st.components.v2.component("nexus_campus_map", html=HTML, css=CSS, js=JS,
                                  isolate_styles=False)


def status_table(status):
    """The numbers behind the map, one row per I-BLEND building."""
    t = status.assign(
        kwh=status["kwh"].round(),
        change=(status["change"] * 100).round(1),
        wifi_share=(status["wifi_share"] * 100).round(),
        wifi_daytime=status["wifi_daytime"].round())
    st.dataframe(t.rename(columns={
        "building": "Building", "hours_recorded": "Hours recorded (of 168)", "kwh": "kWh",
        "change": "vs last week %", "high_hours": "Hours higher than usual",
        "low_hours": "Hours lower than usual", "wifi_daytime": "Weekday daytime people",
        "wifi_share": "% of usual peak"}).drop(columns=["unreliable"]),
        hide_index=True)
    st.caption("vs last week compares the same hours in both weeks. Weekday daytime is "
               "Monday-Friday 09:00-17:00; usual peak is the building's 95th-percentile hour "
               "over 2014-2017. Heights come from OpenStreetMap floors where recorded, "
               f"otherwise {DEFAULT_M:.0f} m.")


def details(status, picked):
    """The tapped building's week, with a way into its detail page."""
    from views.shell import _go

    if not picked or picked not in set(status["building"]):
        st.caption("Tap a building or its label on the map to see its numbers here.")
        return
    r = status.set_index("building").loc[picked]
    with st.container(border=True):
        st.subheader(picked)
        if r["unreliable"]:
            st.caption(f"{picked}'s energy meter is unreliable, so its energy is not analysed. "
                       "Its Wi-Fi counts are still used.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("kWh this week", "—" if pd.isna(r["kwh"]) or r["unreliable"] else f"{r['kwh']:,.0f}")
        c2.metric("vs last week", "—" if pd.isna(r["change"]) else f"{r['change']:+.1%}")
        c3.metric("Hours higher than usual", int(r["high_hours"]))
        c4.metric("Weekday daytime Wi-Fi", "—" if pd.isna(r["wifi_share"]) else f"{r['wifi_share']:.0%} of peak")
        if not r["unreliable"]:
            st.button(f"Open {picked} in Resource Intelligence", icon=":material/bolt:",
                      on_click=_go, args=("resource", {"res_building": picked}))


def matching_notes(status):
    """How each I-BLEND building was placed on the map, and which ones could not be."""
    m = matches()
    missing = sorted(set(status["building"]) - set(m["nexus_building"]))
    if missing:
        st.caption(f"Not on the map: {', '.join(missing)}. OpenStreetMap does not identify "
                   "these buildings, so NEXUS does not guess where they are. Their numbers are "
                   "in the table above.")
    with st.expander("How buildings were placed on the map"):
        st.markdown("Outlines and floor counts come from OpenStreetMap, today's campus. Some "
                    "buildings there (R&D Block, New Boys Hostel, Sports Block) were built after "
                    "the 2013-2017 data period, so they are drawn as not metered.")
        st.dataframe(m.rename(columns={"nexus_building": "I-BLEND building", "osm_id": "OpenStreetMap id",
                                       "osm_name": "OpenStreetMap name", "how_matched": "How matched"}),
                     hide_index=True)
