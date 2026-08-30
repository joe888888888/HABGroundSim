"""
Generate a scrollable/zoomable HTML map of a flight prediction,
with a MapTiler basemap.

The map view frames the whole flight (launch to landing). By default, tiles
covering that area are pre-fetched to a local disk cache (config.json:
maptiler.cache_dir); panning beyond it is hard-restricted, and zooming out
is capped at whatever level fills your actual browser window with the
flight (computed client-side at load time, since that depends on your
window size) - so after the first run for a given flight, no further
MapTiler calls happen no matter how much you pan or zoom out, in this run or
any future one. Zooming in has no hard cap: past the deepest cached zoom
level, Leaflet just upscales the closest real tile (blurrier, but free -
no extra calls). Pass --live to skip caching and hit MapTiler directly
instead (fully unrestricted pan/zoom, but every new tile is a live call and
the key ends up visible in the saved HTML). Cached maps save to
flight_maps/html/ by default; --live maps save to flight_maps/html/live/
instead, since they embed the API key and shouldn't be mixed up with the
safe-to-share cached ones.

Usage:
    python scripts/generate_map.py --prediction data/sample_prediction.json
    python scripts/generate_map.py --prediction data/sample_prediction.json --output route.html
    python scripts/generate_map.py --prediction data/sample_prediction.json --live
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from habgroundsim import maptiler, tawhiri, tile_cache
from habgroundsim.config import AppConfig, DEFAULT_CONFIG_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prediction",
        type=Path,
        required=True,
        help="Path to a saved Tawhiri prediction JSON file",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config.json (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Where to save the map HTML (default: flight_maps/html/flight_map.html, "
            "or flight_maps/html/live/flight_map.html with --live)"
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Skip the local tile cache and hit MapTiler directly (overrides config.json's use_local_cache)",
    )
    args = parser.parse_args()
    if args.output is None:
        args.output = (
            Path("flight_maps/html/live/flight_map.html")
            if args.live
            else Path("flight_maps/html/flight_map.html")
        )
    return args


def main() -> None:
    args = parse_args()

    config = AppConfig.load(args.config)
    raw = tawhiri.load_prediction_file(args.prediction)
    prediction = tawhiri.parse_prediction(raw)

    use_cache = config.maptiler.use_local_cache and not args.live

    cache_report = None
    if use_cache:
        cache_report = tile_cache.ensure_tiles_cached(prediction, config.maptiler)
        print(
            f"Tiles: {cache_report.fetched} fetched, "
            f"{cache_report.already_cached} already cached "
            f"({cache_report.total} total, zoom levels {cache_report.zoom_levels})"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    m = maptiler.build_map(prediction, config.maptiler, cache_report=cache_report)
    m.save(args.output)
    print(f"Saved map to {args.output}")


if __name__ == "__main__":
    main()
