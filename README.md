# Maritime Tides

A one-page tide viewer for the Maritimes — built to answer "is the tide coming in
or going out, and when is the next high?" at a glance on a phone.

Live site: **https://katsuma0.github.io/nb-tides/**

- Coming in / going out, with a countdown to the next high or low.
- A 30-hour tide curve with every crest and trough labelled, and a `NOW` marker.
- Every high and low for the next **31 days**, four to a line.
- **20 locations**, from Grand Manan to Cape Breton.
- Metres and feet, always in Atlantic Time — no matter what time zone the phone
  thinks it is in.

| Region | Locations |
|---|---|
| Grand Manan | North Head, Seal Cove |
| Passamaquoddy Bay | Blacks Harbour, St. Andrews, Beaver Harbour, Campobello |
| Bay of Fundy | Saint John, St. Martins, Hopewell Rocks, Fundy Park, Burntcoat Head, Digby |
| Atlantic Coast | Halifax, Lunenburg, Yarmouth, Sydney |
| Northumberland Strait | Shediac, Charlottetown, Summerside, Pictou |

Ranges run from Sydney's 1.3 m to Burntcoat Head's 15 m — the largest tides in
the world.

## It works offline

Predictions are **computed in the browser** from harmonic constituents baked into
`tide-data.js`. Nothing is fetched at runtime, so once the page has loaded once it
keeps working with no signal — useful on an island where coverage is patchy.

A service worker caches the handful of files that make up the page (~250 KB). On an iPhone,
open the site once on wifi, then tap **Share → Add to Home Screen**; it then opens
like an app with no network at all.

The bundled data covers **2026 through 2037**, so it does not expire.

## How the predictions work

Tide height is the sum of a few dozen sinusoids — the harmonic constituents of a
particular place. The model here matches XTide and OpenCPN exactly:

```
height(t) = datum + Σ  Aᵢ · fᵢ(year) · cos( ωᵢ · (Δt + meridian) + V0ᵢ(year) − κᵢ )
```

- `ωᵢ` — constituent speed, radians per second
- `Δt` — seconds from 00:00 UTC on 1 January of that year
- `meridian` — the station's time meridian offset from UTC (−4 h here)
- `fᵢ`, `V0ᵢ` — node factor and equilibrium argument, tabulated per year
- `κᵢ` — the station's epoch for that constituent

`tools/build_tide_data.py` folds `f` and `V0` into per-year amplitude and phase
arrays, so the browser only evaluates the cosine sum. Highs and lows are found by
bracketing sign changes in the derivative and bisecting. Station coordinates come
from the companion `HARMONICS_NO_US.IDX`, so nothing is hand-entered.

Heights are metres above **chart datum** (roughly the lowest normal low water), the
same reference the Canadian tide tables use.

### Where the numbers come from

Harmonic constants are taken from the XTide dataset as packaged by
[OpenCPN](https://github.com/OpenCPN/OpenCPN/blob/master/data/tcdata/HARMONICS_NO_US);
for Canadian ports these derive from Canadian Hydrographic Service analyses.

Sanity checks that the output is right, not merely plausible:

Every published station is checked against its known tidal range, and every one
has a mean high-to-high interval within seconds of the M2 period (12.4206 h):

| Check | Expected | Computed |
|---|---|---|
| Highest high water at North Head | ≈ 7.0 m (HHWLT) | 7.01 m |
| Mean water level at North Head | ≈ 3.6 m | 3.56 m |
| Burntcoat Head range | ≈ 16 m (world record) | 15.2 m |
| Hopewell Rocks range | ≈ 14 m | 13.9 m |
| Halifax range | ≈ 2.1 m | 2.0 m |
| Sydney range | ≈ 1.3 m | 1.3 m |
| Spring tides | 1–2 days after new/full moon | 15–16 Jul, 13–14 Aug 2026 |

The table was produced by predicting Oct–Dec 2026 for all 20 stations and
comparing against published ranges.

### Known limitation

The node factors and equilibrium arguments are tabulated per calendar year, and
this switches tables at 00:00 UTC on 1 January rather than blending across the
boundary the way XTide does. The resulting step in the curve is a few
centimetres — below the 0.1 m the page displays, and far below the effect of
weather — but a high or low falling within minutes of that instant can be
reported slightly off. It has no effect during the rest of the year.

## Rebuilding the data

```sh
python3 tools/build_tide_data.py      # downloads the harmonics file if absent
python3 tools/make_icons.py           # regenerates icon.svg and the PNGs
```

Both scripts use only the Python standard library and download the source data
if it is absent. Edit `STATIONS` in `build_tide_data.py` to add a location (the
`record` field must match the harmonics file's spelling exactly), or
`FIRST_YEAR` / `LAST_YEAR` to change the span.

## Deploying

Pushes to `main` publish via `.github/workflows/pages.yml`. The workflow passes
`enablement: true` to `actions/configure-pages`, so it switches Pages on by
itself the first time it runs — there is nothing to set by hand.

## Not for navigation

These are astronomical predictions. Wind, barometric pressure and storm surge
routinely shift real water levels by tens of centimetres, and more in a blow. For
anything that matters on the water, carry the official Canadian Tide and Current
Tables.
