"""
Pre-cache MapTiler tiles around a specific point, and render a small
marker-only map to visually confirm the cache/basemap for that area.

Useful for pre-caching a launch site's basemap ahead of time, independent of
any specific flight prediction (e.g. before you have a Tawhiri run for it
yet), or for testing the tile cache against a new location.

Usage:
    python scripts/cache_area.py --lat 37.953233 --lon -87.672916
    python scripts/cache_area.py --lat 37.953233 --lon -87.672916 --zoom-levels 10 11 12 13 --margin 0.15
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import folium

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from habgroundsim import tile_cache
from habgroundsim.config import AppConfig, DEFAULT_CONFIG_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, required=True, help="Latitude, decimal degrees")
    parser.add_argument("--lon", type=float, required=True, help="Longitude, decimal degrees (-180..180)")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config.json (default: %(default)s)",
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=None,
        help="Degrees of padding around the point (default: config.json's maptiler.bounds_margin_deg)",
    )
    parser.add_argument(
        "--zoom-levels",
        type=int,
        nargs="+",
        default=None,
        help="Zoom levels to cache (default: config.json's maptiler.zoom_levels)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("area_maps/area_map.html"),
        help="Where to save the preview map HTML (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = AppConfig.load(args.config)
    maptiler_config = config.maptiler
    margin = args.margin if args.margin is not None else maptiler_config.bounds_margin_deg
    if args.zoom_levels is not None:
        maptiler_config.zoom_levels = args.zoom_levels

    report = tile_cache.ensure_tiles_cached_for_point(args.lat, args.lon, margin, maptiler_config)
    print(
        f"Tiles: {report.fetched} fetched, {report.already_cached} already cached "
        f"({report.total} total, zoom levels {report.zoom_levels})"
    )

    tile_url = tile_cache.local_tile_url_template(report.style_dir, maptiler_config.tile_format)
    m = folium.Map(
        location=[args.lat, args.lon],
        zoom_start=max(report.zoom_levels),
        tiles=tile_url,
        attr=maptiler_config.attribution,
        min_zoom=min(report.zoom_levels),
        max_zoom=max(report.zoom_levels),
        min_lat=args.lat - margin,
        max_lat=args.lat + margin,
        min_lon=args.lon - margin,
        max_lon=args.lon + margin,
        max_bounds=True,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    folium.Marker([args.lat, args.lon], tooltip="Point").add_to(m)
    m.save(args.output)
    print(f"Saved preview map to {args.output}")


if __name__ == "__main__":
    main()
