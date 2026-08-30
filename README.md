# HABGroundSim

High-altitude balloon flight prediction for use on ground: parses
Tawhiri flight predictions and renders the predicted flight path on a
scrollable/zoomable MapTiler basemap.

## Quick start

```bash
pip install -r env/requirements.txt
cp env/.env.example env/.env        # then fill in your API keys
```

Edit `config.json` with your launch parameters (see below).

Plot a static top-down view of a prediction:

```bash
python scripts/plot_flight.py --prediction data/sample_prediction.json
```

Generate a scrollable/zoomable HTML map. The first run for a given area
fetches and caches MapTiler tiles to `tile_cache/` (a bounded, one-time
cost - see "Tile caching" below); every run after that for an overlapping
area costs nothing:

```bash
python scripts/generate_map.py --prediction data/sample_prediction.json
```

Saves to `flight_maps/html/flight_map.html` by default (open it in a browser).
`--live` maps save to `flight_maps/html/live/` instead, since they embed
your MapTiler key and shouldn't be mixed up with the safe-to-share cached
ones.

You'll see a warning printed if the prediction file's own `request` block
doesn't match `config.json` (e.g. you changed the launch site in
`config.json` but the prediction file is from before that). This is a sanity
check, not an error, telling you the two have drifted apart.

To pre-cache a launch site's basemap before you even have a prediction for
it, or to sanity-check the tile cache against a new point:

```bash
python scripts/cache_area.py --lat 37.953233 --lon -87.672916
```

## Config

Two separate places hold configuration, deliberately split by sensitivity:

- **`config.json`** - tunable, non-secret parameters. Safe to commit.
- **`env/.env`** - API keys. Gitignored, never committed. Copy
  `env/.env.example` to `env/.env` and fill in real values.

### `config.json`


```jsonc
{
  "tawhiri": {
    "request": {
      // Mirrors the Tawhiri API's request params exactly (see
      // https://tawhiri.readthedocs.io/en/latest/api.html#api-request).
      "launch_latitude": 37.953233,
      "launch_longitude": 272.327084,   // Tawhiri uses 0-360 convention
      "launch_altitude": 136,
      "launch_datetime": "2026-08-30T18:00:00Z",
      "ascent_rate": 5,
      "burst_altitude": 30000,
      "descent_rate": 10,
      "profile": "standard_profile",
      "dataset": "2026-08-29T12:00:00Z",
      "format": "json",
      "version": 1
    }
  },
  "maptiler": {
    "style": "hybrid",              // any MapTiler map style id
    "tile_format": "jpg",
    "default_zoom": 11,
    "attribution": "© MapTiler © OpenStreetMap contributors",
    "use_local_cache": true,           // see "Tile caching" below
    "cache_dir": "tile_cache",
    "zoom_levels": [10, 11, 12, 13],   // only these zooms get pre-fetched/allowed
    "bounds_margin_deg": 0.15          // padding around the flight's bbox, in degrees
  }
}
```

`AppConfig.load()` (in `habgroundsim/config.py`) reads this file plus `env/.env`
and hands back typed dataclasses (`TawhiriRequestConfig`, `MapTilerConfig`) —
nothing downstream touches raw dicts.

### `env/.env`

```
MAPTILER_API_KEY=
```

Tawhiri's API is public and doesn't need a key.

## Codebase

```
habgroundsim/
    config.py         AppConfig.load() - reads config.json + env/.env
    tawhiri.py         fetch_prediction() hits the live Tawhiri API and saves
                        the response to data/; parse_prediction() turns
                        either that or a saved file into
                        Prediction / Stage / TrajectoryPoint dataclasses
    maptiler.py        builds a folium map: MapTiler basemap + the parsed
                        flight path overlaid as polylines/markers
    tile_cache.py      pre-fetches/caches MapTiler tiles to disk for a
                        prediction's bounding box (see "Tile caching" below)

scripts/
    fetch_prediction.py  fetches a live Tawhiri prediction (config.json's
                          request params, or CLI overrides) and saves it to
                          data/
    plot_flight.py     static top-down matplotlib plot of a prediction
    generate_map.py    scrollable/zoomable HTML map of a prediction
    cache_area.py      pre-caches tiles for an arbitrary lat/lon (no
                        prediction needed) and saves a marker-only preview

data/
    sample_prediction.json   an already-fetched Tawhiri response, used as
                              test/example input

area_maps/              marker-only preview maps from cache_area.py.
                         Gitignored - regenerable, not source.

flight_maps/
    html/                scrollable/zoomable flight maps from generate_map.py
        live/             maps generated with --live - these embed your
                           MapTiler key, keep them separate from the
                           cached (key-free) ones above
    png/                 static top-down plots from plot_flight.py
    Gitignored - regenerable, not source.

env/
    .env                 API keys. Gitignored, never committed.
    .env.example          template for .env. Safe to commit.
    requirements.txt      Python dependencies.

tile_cache/            downloaded MapTiler tiles, generated on first run.
                        Gitignored - regenerable, not source.
```

The shared shape across all of this: **fetching/parsing is separate from
rendering.** `tawhiri.parse_prediction()` takes a plain dict (from a file, or
eventually from a live response) and returns the same typed structure either
way. Both `plot_flight.py` and `generate_map.py` consume that structure and
don't care where it came from. That's what makes it easy to develop against
`data/sample_prediction.json` without touching the network at all.

## API call architecture - what calls what, and why

| API | Does this repo call it? | Where | Notes |
|---|---|---|---|
| Tawhiri | **Yes, when invoked** | `tawhiri.fetch_prediction()`, driven by `scripts/fetch_prediction.py` | Every fetch is saved to `data/` as a JSON file rather than used in memory only, so it becomes a reusable fixture instead of a one-off call. No key required. |
| MapTiler | **Yes, but only to build a local cache** | `tile_cache.py`, driven by `generate_map.py` | By default, tiles for the flight's bounding box are pre-fetched to disk once; the saved HTML then points at those local files, not MapTiler, so panning/zooming afterward makes zero further calls. `--live` mode skips this and hits MapTiler directly from the browser instead. |

### Fetching a live Tawhiri prediction

```bash
python scripts/fetch_prediction.py
python scripts/fetch_prediction.py --lat 35.1985 --lon -106.5931 --datetime 2026-09-05T18:00:00Z
```

With no flags, it fetches using `config.json`'s `tawhiri.request` block. Any
individual param (`--lat`, `--lon`, `--altitude`, `--datetime`, `--ascent-rate`,
`--burst-altitude`, `--descent-rate`) can be overridden for a one-off flight
without editing `config.json`. The raw response is saved to `data/` (default
filename `tawhiri_<lat>_<lon>_<datetime>.json`, or pass `--output`) and printed
as a quick launch/burst/landing summary.

Under the hood this hits the SondeHub-hosted Tawhiri instance
(`api.v2.sondehub.org/tawhiri`) via `tawhiri.fetch_prediction()`. Tawhiri is a
shared community-run service with no published hard rate limit, but the
informal expectation is to be a good citizen, aka don't poll it in a loop and don't
re-fetch the same prediction repeatedly during development. Reuse the saved
JSON file instead. `TawhiriApiError` is raised with the API's own error description 
rather than a raw HTTP traceback.

You can still develop entirely offline against `data/sample_prediction.json`
without touching the network at all. `fetch_prediction.py` is opt-in, not a
replacement for that workflow.

### Why MapTiler needed a different approach entirely: tile caching

Left uncached, MapTiler is structurally different from Tawhiri:
**your Python code never calls it**. It just writes a tile URL template
(with your key embedded) into the saved HTML, and the actual API traffic
happens in whichever browser opens that file, once per tile, every time the
map is panned or zoomed. Casual scrolling burns through quota fast (each
zoom level is an entirely different tile set), the cost isn't visible or 
bounded from this script's side, and the key ends up sitting in the page 
source of whatever HTML gets produced.

`tile_cache.py` fixes this by pre-fetching once instead of leaving it to the
browser:

1. `generate_map.py` computes the flight's bounding box (from the parsed
   prediction) plus a margin (`maptiler.bounds_margin_deg`), for each zoom
   level in `maptiler.zoom_levels`.
2. For each tile in that set, it checks `tile_cache/<style>/<z>/<x>/<y>.<format>`
   on disk first. Only tiles not already there get downloaded.
3. The saved map points at those local files via an absolute `file://` URL,
   with pan/zoom locked (`max_bounds` + `min_zoom`/`max_zoom`) to exactly
   what was fetched so there's no way to accidentally scroll into
   uncached territory and hit MapTiler again unexpectedly.

The same underlying fetch logic also works from a bare lat/lon instead of a
prediction (`tile_cache.ensure_tiles_cached_for_point`, exposed via
`scripts/cache_area.py`). Useful for pre-caching a launch site before a
real Tawhiri prediction exists for it.

Net effect: the *first* time you generate a map for a given area, that's a
real, bounded number of API calls (printed to the console each run, e.g.
`Tiles: 53 fetched, 0 already cached`). Every run after that, for that
flight, or any other flight whose bounding box overlaps it, costs nothing,
since the cache is keyed by tile coordinates not by prediction. As a nice
side effect, the key never even ends up in the generated HTML in this mode,
since tiles are referenced by local path instead of a live URL.

Trade-offs to know about:
- **Only the pre-fetched area/zoom range is viewable.** This is deliberate,
  it's the thing that makes cost bounded, but it does mean this isn't a
  general-purpose "explore anywhere" map. If you need to look far outside
  the flight's predicted path, that's what `--live` mode is for.
- **`zoom_levels` is the main cost lever.** Tile count roughly quadruples
  per zoom level, so adding one more zoom to the default `[10, 11, 12, 13]`
  (~230 tiles for a typical flight) can easily 3-4x the cost. Check 
  MapTiler plan's quota before widening this. 
- `--live` mode (`python scripts/generate_map.py ... --live`) skips all of
  this and behaves like a normal MapTiler-backed Leaflet map: unrestricted
  pan/zoom, but every new tile is a live call and the key is visible in the
  saved HTML's page source. Useful for one-off exploration; restrict the key
  to your expected domains/referrers in the MapTiler dashboard if you use it
  and might ever share the resulting HTML.
- Never commit `tile_cache/` or a generated map file to version control —
  `.gitignore` already excludes `tile_cache/`, `env/.env`, `area_maps/`,
  and `flight_maps/` (`--live` maps included, via `flight_maps/html/live/`).

