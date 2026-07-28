#!/usr/bin/env python3
"""Generate tide-data.js from the XTide/OpenCPN harmonic constants file.

Source data: https://github.com/OpenCPN/OpenCPN/blob/master/data/tcdata/HARMONICS_NO_US
(XTide harmonic constants, which for Canadian ports derive from Canadian
Hydrographic Service analyses.)

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
    python3 tools/build_tide_data.py [path/to/HARMONICS_NO_US] [-o tide-data.js]

If the harmonics file is absent it is downloaded from the OpenCPN repository.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request

HARMONICS_URL = (
    "https://raw.githubusercontent.com/OpenCPN/OpenCPN/master/data/tcdata/HARMONICS_NO_US"
)

DEG2RAD = math.pi / 180.0
# degrees/hour -> radians/second
SPEED_SCALE = math.pi / 648000.0

# Stations to publish, in menu order. The first one is the default.
STATIONS = [
    {
        "id": "north-head",
        "record": "North Head, New Brunswick",
        "name": "North Head",
        "place": "Grand Manan Island",
        "note": "Ferry terminal and main village",
        "lat": 44.7667,
        "lon": -66.75,
    },
    {
        "id": "seal-cove",
        "record": "Seal Cove, Grand Manan Island, New Brunswick",
        "name": "Seal Cove",
        "place": "Grand Manan Island",
        "note": "South end of the island",
        "lat": 44.65,
        "lon": -66.85,
    },
    {
        "id": "blacks-harbour",
        "record": "Blacks Harbour, New Brunswick",
        "name": "Blacks Harbour",
        "place": "Mainland New Brunswick",
        "note": "Mainland end of the Grand Manan ferry",
        "lat": 45.05,
        "lon": -66.7833,
    },
]

FIRST_YEAR = 2026
LAST_YEAR = 2037


def read_harmonics(path: str) -> list[str]:
    if not os.path.exists(path):
        sys.stderr.write(f"downloading harmonic constants to {path} ...\n")
        with urllib.request.urlopen(HARMONICS_URL) as r, open(path, "wb") as f:
            f.write(r.read())
    with open(path, encoding="utf-8") as f:
        raw = f.read().split("\n")
    return [l for l in raw if not l.lstrip().startswith("#") and l.strip() != ""]


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


def build_station(spec: dict, tables: dict, records: dict) -> dict:
    rec = records.get(spec["record"])
    if rec is None:
        raise KeyError(f"station not found in harmonics file: {spec['record']}")

    datum_value, datum_units = rec["datum"].split()[:2]
    if datum_units != "meters":
        raise ValueError(f"{spec['record']}: expected meters, got {datum_units}")

    meridian_text = rec["meridian"].split()[0]
    tzfile = rec["meridian"].split()[1].lstrip(":") if len(rec["meridian"].split()) > 1 else "UTC"

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
        "note": spec["note"],
        "source": rec["name"],
        "lat": spec["lat"],
        "lon": spec["lon"],
        "timezone": tzfile,
        "meridian": hhmm_to_seconds(meridian_text),
        "datum": float(datum_value),
        "speeds": [round(s, 12) for s in speeds],
        "constituents": names,
        "years": years,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("harmonics", nargs="?", default="HARMONICS_NO_US")
    ap.add_argument("-o", "--output", default="tide-data.js")
    args = ap.parse_args()

    tables = parse(read_harmonics(args.harmonics))
    records = {st["name"]: st for st in iter_stations(tables["station_lines"], tables["order"])}
    stations = [build_station(spec, tables, records) for spec in STATIONS]

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

    for st in stations:
        print(
            f"{st['name']:16s} {len(st['constituents']):3d} constituents  "
            f"datum {st['datum']:.2f} m  tz {st['timezone']}"
        )
    print(f"wrote {args.output} ({os.path.getsize(args.output)} bytes), "
          f"years {FIRST_YEAR}-{LAST_YEAR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
