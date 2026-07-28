# Grand Manan Tides

A one-page tide viewer for **Grand Manan Island, New Brunswick** — built to answer
"is the tide coming in or going out, and when is the next high?" at a glance.

Live site: **https://katsuma0.github.io/nb-tides/**

- Big "the tide is coming in / going out" state with a countdown to the next high or low.
- A 36-hour tide curve with every crest and trough labelled, and a `NOW` marker.
- Every high and low for the next two weeks, day by day.
- Three locations: North Head and Seal Cove on the island, plus Blacks Harbour
  (the mainland end of the ferry).
- Metres and feet, always in Atlantic Time — no matter what time zone the phone
  thinks it is in.

## It works offline

Predictions are **computed in the browser** from harmonic constituents baked into
`tide-data.js`. Nothing is fetched at runtime, so once the page has loaded once it
keeps working with no signal — useful on an island where coverage is patchy.

A service worker caches the handful of files that make up the page. On an iPhone,
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
bracketing sign changes in the derivative and bisecting.

Heights are metres above **chart datum** (roughly the lowest normal low water), the
same reference the Canadian tide tables use.

### Where the numbers come from

Harmonic constants are taken from the XTide dataset as packaged by
[OpenCPN](https://github.com/OpenCPN/OpenCPN/blob/master/data/tcdata/HARMONICS_NO_US);
for Canadian ports these derive from Canadian Hydrographic Service analyses.

Sanity checks that the output is right, not merely plausible:

| Check | Expected | Computed |
|---|---|---|
| Mean high-to-high interval over 62 days | 12.4206 h (M2) | 12.4159 h |
| Highest high water at North Head | ≈ 7.0 m (HHWLT) | 7.02 m |
| Mean water level at North Head | ≈ 3.6 m | 3.56 m |
| Spring tides | 1–2 days after new/full moon | 15–16 Jul, 13–14 Aug 2026 |

## Rebuilding the data

```sh
python3 tools/build_tide_data.py      # downloads the harmonics file if absent
python3 tools/make_icons.py           # regenerates icon.svg and the PNGs
```

Both scripts use only the Python standard library. Edit `STATIONS` in
`build_tide_data.py` to add a location, or `FIRST_YEAR` / `LAST_YEAR` to change
the span.

## Deploying

Pushes to `main` publish via `.github/workflows/pages.yml`. The workflow passes
`enablement: true` to `actions/configure-pages`, so it switches Pages on by
itself the first time it runs — there is nothing to set by hand.

## Not for navigation

These are astronomical predictions. Wind, barometric pressure and storm surge
routinely shift real water levels by tens of centimetres, and more in a blow. For
anything that matters on the water, carry the official Canadian Tide and Current
Tables.
