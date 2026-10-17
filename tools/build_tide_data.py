#!/usr/bin/env python3
"""Generate tide-data.js from the XTide/OpenCPN harmonic constants file.

Source data:
  https://github.com/OpenCPN/OpenCPN/blob/master/data/tcdata/HARMONICS_NO_US
  https://github.com/OpenCPN/OpenCPN/blob/master/data/tcdata/HARMONICS_NO_US.IDX
(XTide harmonic constants, which for Canadian ports derive from Canadian
Hydrographic Service analyses. The .IDX file carries the station coordinates.)

The prediction model matches XTide and OpenCPN exactly:

    height(t) = DATUM + sum_i  A_i * f_i(year) * cos( w_i * (dt + meridian)
                                                      + V0_i(year) - kappa_i )

    w_i       constituent speed in radians/second
    dt        seconds from 00:00 UTC on Jan 1 of `year` to t
    meridian  the station's time meridian offset from UTC, in seconds
    f_i       node factor for `year`
    V0_i      equilibrium argument for `year`, radians
    kappa_i   the station's epoch for the constituent, radians

Because f and V0 are tabulated per year, this script folds them into two
per-year arrays so the browser only has to evaluate the cosine sum:

    amp[year][i]   = A_i * f_i(year)
    phase[year][i] = V0_i(year) - kappa_i

Usage:
    python3 tools/build_tide_data.py [dir-with-harmonics] [-o tide-data.js]

Missing source files are downloaded from the OpenCPN repository.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.request

BASE_URL = "https://raw.githubusercontent.com/OpenCPN/OpenCPN/master/data/tcdata/"
HARMONICS = "HARMONICS_NO_US"
INDEX = "HARMONICS_NO_US.IDX"

DEG2RAD = math.pi / 180.0
# degrees/hour -> radians/second
SPEED_SCALE = math.pi / 648000.0

# Published stations, in menu order. The first is the default.
#   record — the station name exactly as the harmonics file spells it
#   name   — what the picker shows
#   place  — a short locator shown under the chart
#   group  — the <optgroup> it sits in
STATIONS = [
    # The island itself.
    dict(id="north-head", record="North Head, New Brunswick",
         name="North Head", place="Grand Manan Island", group="Grand Manan"),
    dict(id="seal-cove", record="Seal Cove, Grand Manan Island, New Brunswick",
         name="Seal Cove", place="Grand Manan Island", group="Grand Manan"),

    # Getting there, and the rest of Charlotte County.
    dict(id="blacks-harbour", record="Blacks Harbour, New Brunswick",
         name="Blacks Harbour", place="Grand Manan ferry terminal",
         group="Passamaquoddy Bay"),
    dict(id="st-andrews", record="St. Andrews, Passamaquoddy Bay, New Brunswick",
         name="St. Andrews", place="Passamaquoddy Bay", group="Passamaquoddy Bay"),
    dict(id="beaver-harbour", record="Beaver Harbour, New Brunswick",
         name="Beaver Harbour", place="Charlotte County", group="Passamaquoddy Bay"),
    dict(id="campobello", record="Welshpool, Campobello Island, New Brunswick",
         name="Campobello", place="Welshpool", group="Passamaquoddy Bay"),

    # The big Fundy tides.
    dict(id="saint-john", record="Saint John, New Brunswick",
         name="Saint John", place="New Brunswick", group="Bay of Fundy"),
    dict(id="st-martins", record="St. Martins, New Brunswick",
         name="St. Martins", place="Sea caves, New Brunswick", group="Bay of Fundy"),
    dict(id="hopewell-rocks", record="Hopewell Cape, New Brunswick",
         name="Hopewell Rocks", place="Hopewell Cape, New Brunswick",
         group="Bay of Fundy"),
    dict(id="fundy-park", record="Herring Cove, New Brunswick",
         name="Fundy Park", place="Herring Cove, New Brunswick",
         group="Bay of Fundy"),
    dict(id="burntcoat-head", record="Burntcoat Head, Nova Scotia",
         name="Burntcoat Head", place="World's highest tides, Nova Scotia",
         group="Bay of Fundy"),
    dict(id="digby", record="Digby, Annapolis Basin, Nova Scotia",
         name="Digby", place="Annapolis Basin, Nova Scotia", group="Bay of Fundy"),

    # Atlantic-facing Nova Scotia.
    dict(id="halifax", record="Halifax, Nova Scotia",
         name="Halifax", place="Nova Scotia", group="Atlantic Coast"),
    dict(id="lunenburg", record="Lunenburg, Nova Scotia",
         name="Lunenburg", place="Nova Scotia", group="Atlantic Coast"),
    dict(id="yarmouth", record="Yarmouth, Nova Scotia",
         name="Yarmouth", place="Nova Scotia", group="Atlantic Coast"),
    dict(id="sydney", record="Sydney, Nova Scotia",
         name="Sydney", place="Cape Breton, Nova Scotia", group="Atlantic Coast"),

    # The warm side.
    dict(id="shediac", record="Shediac Bay, New Brunswick",
         name="Shediac", place="Parlee Beach, New Brunswick",
         group="Northumberland Strait"),
    dict(id="charlottetown", record="Charlottetown, Prince Edward Island",
         name="Charlottetown", place="Prince Edward Island",
         group="Northumberland Strait"),
    dict(id="summerside", record="Summerside, Prince Edward Island",
         name="Summerside", place="Prince Edward Island",
         group="Northumberland Strait"),
    dict(id="pictou", record="Pictou, Nova Scotia",
         name="Pictou", place="Nova Scotia", group="Northumberland Strait"),
]

FIRST_YEAR = 2026
LAST_YEAR = 2037


def fetch(directory: str, filename: str) -> str:
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        os.makedirs(directory, exist_ok=True)
        sys.stderr.write(f"downloading {filename} to {path} ...\n")
        with urllib.request.urlopen(BASE_URL + filename) as r, open(path, "wb") as f:
            f.write(r.read())
    return path


def read_harmonics(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        raw = f.read().split("\n")
    return [l for l in raw if not l.lstrip().startswith("#") and l.strip() != ""]


# "TNAA:Can:Newb: -66.75 44.7667 -4:0 North Head, New Brunswick"
IDX_LINE = re.compile(r"^T\S*\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\S+)\s+(.+?)\s*$")


def read_index(path: str) -> dict[str, tuple[float, float]]:
    """Map reference-station name -> (lat, lon). The IDX lists lon before lat."""
    coords: dict[str, tuple[float, float]] = {}
    with open(path, encoding="latin-1") as f:
        for line in f:
            m = IDX_LINE.match(line)
            if m:
                lon, lat, _tz, name = m.groups()
                coords.setdefault(name, (float(lat), float(lon)))
    return coords


def parse(lines: list[str]) -> dict:
    """Parse the XTide v1 ASCII harmonics file."""
    i = 0
    n_const = int(lines[i].strip())
    i += 1

    order: list[str] = []
    speeds: dict[str, float] = {}
    for _ in range(n_const):
        name, spd = lines[i].split()
        order.append(name)
        speeds[name] = float(spd)
        i += 1

    def read_table(i: int, n_years: int) -> tuple[dict[str, list[float]], int]:
        table: dict[str, list[float]] = {}
        while lines[i].strip() != "*END*":
            name = lines[i].strip()
            i += 1
            vals: list[float] = []
            while len(vals) < n_years:
                vals.extend(float(x) for x in lines[i].split())
                i += 1
            table[name] = vals
        return table, i + 1

    start_year = int(lines[i].split()[0])
    i += 1
    n_years = int(lines[i].split()[0])
    i += 1
    equilib, i = read_table(i, n_years)

    # The node-factor table repeats only the year count; it shares start_year.
    nf_years = int(lines[i].split()[0])
    i += 1
    nodes, i = read_table(i, nf_years)
    if nf_years != n_years:
        raise ValueError("equilibrium and node tables cover different year counts")

    return {
        "order": order,
        "speeds": speeds,
        "equilib": equilib,
        "nodes": nodes,
        "start_year": start_year,
        "n_years": n_years,
        "station_lines": lines[i:],
    }


def iter_stations(station_lines: list[str], order: list[str]):
    """Yield each station record.

    Layout: name line, "meridian tzfile" line, "DATUM units" line, then exactly
    len(order) constituent lines in the canonical constituent order. Slots the
    station does not use are written as the placeholder "x 0 0", so they must be
    matched by position rather than by name.
    """
    n = len(order)
    i = 0
    while i + 3 + n <= len(station_lines):
        consts = {}
        for k in range(n):
            parts = station_lines[i + 3 + k].split()
            if parts[0] == "x":
                continue
            if parts[0] != order[k]:
                raise ValueError(
                    f"record at index {i} desynced: slot {k} is {parts[0]!r}, "
                    f"expected {order[k]!r}"
                )
            consts[parts[0]] = (float(parts[1]), float(parts[2]))
        yield {
            "name": station_lines[i].strip(),
            "meridian": station_lines[i + 1].strip(),
            "datum": station_lines[i + 2].strip(),
            "constituents": consts,
        }
        i += 3 + n


def hhmm_to_seconds(text: str) -> int:
    """Parse a "-04:00" style time meridian into seconds, matching XTide."""
    hh, mm = text.split(":")
    sign = -1 if text.strip().startswith("-") else 1
    return int(hh) * 3600 + sign * int(mm) * 60


def build_station(spec: dict, tables: dict, records: dict, coords: dict) -> dict:
    rec = records.get(spec["record"])
    if rec is None:
        raise KeyError(f"station not found in harmonics file: {spec['record']}")
    if spec["record"] not in coords:
        raise KeyError(f"station not found in index: {spec['record']}")
    lat, lon = coords[spec["record"]]

    datum_value, datum_units = rec["datum"].split()[:2]
    if datum_units != "meters":
        raise ValueError(f"{spec['record']}: expected meters, got {datum_units}")

    meridian_text = rec["meridian"].split()[0]
    parts = rec["meridian"].split()
    tzfile = parts[1].lstrip(":") if len(parts) > 1 else "UTC"

    names, speeds, amps, kappas = [], [], [], []
    for cname in tables["order"]:
        entry = rec["constituents"].get(cname)
        if entry is None or entry[0] == 0.0:
            continue
        names.append(cname)
        speeds.append(tables["speeds"][cname] * SPEED_SCALE)
        amps.append(entry[0])
        kappas.append(entry[1] * DEG2RAD)

    years = {}
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        idx = year - tables["start_year"]
        if not 0 <= idx < tables["n_years"]:
            raise ValueError(f"year {year} outside tabulated range")
        amp_row, phase_row = [], []
        for k, cname in enumerate(names):
            f = tables["nodes"][cname][idx]
            v0 = tables["equilib"][cname][idx] * DEG2RAD
            amp_row.append(round(amps[k] * f, 6))
            # Normalise into [0, 2pi) so the serialised numbers stay short.
            phase_row.append(round((v0 - kappas[k]) % (2 * math.pi), 6))
        years[year] = {"amp": amp_row, "phase": phase_row}

    return {
        "id": spec["id"],
        "name": spec["name"],
        "place": spec["place"],
        "group": spec["group"],
        "source": rec["name"],
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "timezone": tzfile,
        "meridian": hhmm_to_seconds(meridian_text),
        "datum": float(datum_value),
        "speeds": [round(s, 12) for s in speeds],
        "constituents": names,
        "years": years,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source_dir", nargs="?", default=".",
                    help="directory holding (or to receive) the OpenCPN data files")
    ap.add_argument("-o", "--output", default="tide-data.js")
    args = ap.parse_args()

    tables = parse(read_harmonics(fetch(args.source_dir, HARMONICS)))
    coords = read_index(fetch(args.source_dir, INDEX))
    records = {st["name"]: st for st in iter_stations(tables["station_lines"], tables["order"])}
    stations = [build_station(spec, tables, records, coords) for spec in STATIONS]

    payload = {
        "firstYear": FIRST_YEAR,
        "lastYear": LAST_YEAR,
        "timezone": stations[0]["timezone"],
        "stations": stations,
    }

    body = json.dumps(payload, separators=(",", ":"))
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("// Generated by tools/build_tide_data.py - do not edit by hand.\n")
        f.write("// Harmonic constants from XTide / OpenCPN (HARMONICS_NO_US),\n")
        f.write("// which for Canadian ports derive from Canadian Hydrographic Service analyses.\n")
        f.write("window.TIDE_DATA = ")
        f.write(body)
        f.write(";\n")

    group = None
    for st in stations:
        if st["group"] != group:
            group = st["group"]
            print(f"  {group}")
        print(f"    {st['name']:18s} {len(st['constituents']):3d} consts  "
              f"datum {st['datum']:5.2f} m  {st['lat']:.3f},{st['lon']:.3f}  {st['timezone']}")
    print(f"wrote {args.output} ({os.path.getsize(args.output)} bytes), "
          f"{len(stations)} stations, years {FIRST_YEAR}-{LAST_YEAR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
