"""Pre-fetches MapTiler tiles for a prediction's flight area (or an
arbitrary point) and caches them to disk, so that after the first fetch,
panning/zooming within that area - in this run or any future one - costs
zero further API calls.

Standard slippy-map tile math: https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import requests

from . import tawhiri
from .config import MapTilerConfig, MissingApiKeyError

REQUEST_DELAY_SECONDS = 0.05  # be polite - don't hammer the tile server in a tight loop
TILE_BUFFER = 2  # extra rows/cols fetched beyond the exact bbox on every side, matching Leaflet's default keepBuffer - without this, panning/zooming near the edge of the cached area requests tiles that were never fetched (confirmed via DevTools: Leaflet requesting x=1046,1047,1054,1055 when only 1048-1053 was cached), which show as blank/missing map background


def deg_to_tile(lat_deg: float, lon_deg: float, zoom: int) -> Tuple[int, int]:
    lat_rad = math.radians(lat_deg)
    n = 2.0**zoom
    x = int((lon_deg + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    # clamp - a point exactly at a pole or the antimeridian can round outside the valid tile range
    x = min(max(x, 0), int(n) - 1)
    y = min(max(y, 0), int(n) - 1)
    return x, y


def bounding_box(points: List[tawhiri.TrajectoryPoint], margin_deg: float) -> Tuple[float, float, float, float]:
    """Returns (min_lat, min_lon, max_lat, max_lon) padded by margin_deg."""
    lats = [p.latitude for p in points]
    lons = [p.longitude for p in points]
    return (
        min(lats) - margin_deg,
        min(lons) - margin_deg,
        max(lats) + margin_deg,
        max(lons) + margin_deg,
    )


def tiles_for_bbox(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float, zoom: int, buffer: int = TILE_BUFFER
) -> List[Tuple[int, int]]:
    x_min, y_min = deg_to_tile(max_lat, min_lon, zoom)  # top-left (north-west)
    x_max, y_max = deg_to_tile(min_lat, max_lon, zoom)  # bottom-right (south-east)
    n = int(2**zoom)
    x_min = max(x_min - buffer, 0)
    x_max = min(x_max + buffer, n - 1)
    y_min = max(y_min - buffer, 0)
    y_max = min(y_max + buffer, n - 1)
    return [(x, y) for x in range(x_min, x_max + 1) for y in range(y_min, y_max + 1)]


@dataclass
class CacheReport:
    fetched: int
    already_cached: int
    total: int
    zoom_levels: List[int]
    style_dir: Path


def _tile_path(style_dir: Path, zoom: int, x: int, y: int, tile_format: str) -> Path:
    return style_dir / str(zoom) / str(x) / f"{y}.{tile_format}"


def ensure_tiles_cached(prediction: tawhiri.Prediction, config: MapTilerConfig) -> CacheReport:
    """Downloads any tiles covering the prediction's flight area (launch to
    landing, all stages) that aren't already on disk. Safe to call
    repeatedly - already-cached tiles are skipped, so a second run against
    the same (or an overlapping) area makes no network calls at all.
    """
    min_lat, min_lon, max_lat, max_lon = bounding_box(prediction.all_points, config.bounds_margin_deg)
    return ensure_tiles_cached_for_bbox(min_lat, min_lon, max_lat, max_lon, config)


def ensure_tiles_cached_for_point(latitude: float, longitude: float, margin_deg: float, config: MapTilerConfig) -> CacheReport:
    """Same as ensure_tiles_cached, but for an arbitrary point instead of a
    parsed prediction - e.g. pre-caching a launch site before a prediction
    for it exists.
    """
    min_lat, min_lon, max_lat, max_lon = latitude - margin_deg, longitude - margin_deg, latitude + margin_deg, longitude + margin_deg
    return ensure_tiles_cached_for_bbox(min_lat, min_lon, max_lat, max_lon, config)


def ensure_tiles_cached_for_bbox(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float, config: MapTilerConfig
) -> CacheReport:
    """Downloads any tiles covering (min_lat, min_lon, max_lat, max_lon) that
    aren't already on disk. Safe to call repeatedly - already-cached tiles
    are skipped, so a second run against the same (or an overlapping) area
    makes no network calls at all.
    """
    if not config.api_key:
        raise MissingApiKeyError("MAPTILER_API_KEY is not set. Add it to env/.env.")

    style_dir = Path(config.cache_dir) / config.style
    style_dir.mkdir(parents=True, exist_ok=True)

    fetched = 0
    already_cached = 0
    session = requests.Session()

    for zoom in config.zoom_levels:
        for x, y in tiles_for_bbox(min_lat, min_lon, max_lat, max_lon, zoom):
            path = _tile_path(style_dir, zoom, x, y, config.tile_format)
            if path.exists():
                already_cached += 1
                continue

            url = f"https://api.maptiler.com/maps/{config.style}/{zoom}/{x}/{y}.{config.tile_format}?key={config.api_key}"
            response = session.get(url)
            if response.status_code == 404:
                # style has no imagery at this tile (e.g. open ocean at high zoom) - not an error
                continue
            response.raise_for_status()

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
            fetched += 1
            time.sleep(REQUEST_DELAY_SECONDS)

    return CacheReport(
        fetched=fetched,
        already_cached=already_cached,
        total=fetched + already_cached,
        zoom_levels=list(config.zoom_levels),
        style_dir=style_dir,
    )


def local_tile_url_template(style_dir: Path, tile_format: str) -> str:
    """file:// URL template pointing at the local cache, in the {z}/{x}/{y}
    form Leaflet expects. Using an absolute file:// URI (rather than a path
    relative to the saved HTML) means the map still works no matter where
    --output puts the HTML file.
    """
    base_uri = style_dir.resolve().as_uri()
    return f"{base_uri}/{{z}}/{{x}}/{{y}}.{tile_format}"
