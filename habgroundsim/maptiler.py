"""
Builds a scrollable/zoomable folium (Leaflet) map with a MapTiler basemap
and a parsed Tawhiri prediction overlaid on top.

The map view frames the whole flight (launch to landing), padded by
config.json's maptiler.bounds_margin_deg.

Two tile sources, chosen by whether a CacheReport is passed in:

- Cached (default): tiles were pre-fetched to disk by tile_cache.py for the
  flight's bounding box, at a fixed set of zoom levels
  (config.json: maptiler.zoom_levels).
    - Zoom IN has a small soft buffer past the real cache: the tile layer's
      max_native_zoom is set to the deepest zoom actually cached, and
      max_zoom is that plus CACHE_ZOOM_IN_BUFFER (currently 1) - a little
      upscaled/blurry zoom past the real tiles, then a hard stop. No extra
      tiles or calls are needed for that one buffer level.
    - Zoom OUT is capped, but not at a fixed number: after the map's
      initial fitBounds() call places the flight in view, a small injected
      script locks minZoom to whatever zoom that landed on for the
      viewer's actual window size (never lower than the shallowest cached
      zoom, so it can't ask for tiles that were never fetched). That's the
      only way to get "fills the screen at the most zoomed-out point" to
      hold across different window sizes - it has to be computed in the
      browser, not baked in statically.
  Pan is hard-restricted to the flight's bounding box (max_bounds). The
  MapTiler key never ends up in the saved HTML in this mode.
- Live: tiles come straight from MapTiler on every pan/zoom, no
  restrictions at all. The view starts framed on the flight, but nothing
  stops going further from there. Whatever key is used ends up visible in
  the saved HTML's page source. 
"""

from __future__ import annotations

from typing import Optional

import folium

from . import tawhiri, tile_cache
from .config import MapTilerConfig

STAGE_COLORS = {"ascent": "blue", "descent": "orange"}
LIVE_MAX_ZOOM = 19  # generous ceiling for --live mode; MapTiler serves real tiles up to its own native max
CACHE_ZOOM_IN_BUFFER = 1  # cached mode: allow this much soft/blurry zoom past max_native_zoom, no more


def build_map(prediction: tawhiri.Prediction, config: MapTilerConfig, cache_report: Optional[tile_cache.CacheReport] = None,) -> folium.Map:
    launch = prediction.launch_point
    burst = prediction.burst_point
    landing = prediction.landing_point

    min_lat, min_lon, max_lat, max_lon = tile_cache.bounding_box(prediction.all_points, config.bounds_margin_deg)
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    if cache_report is not None:
        tile_url = tile_cache.local_tile_url_template(cache_report.style_dir, config.tile_format)
        cache_min_zoom, cache_max_zoom = min(cache_report.zoom_levels), max(cache_report.zoom_levels)
        tiles = folium.TileLayer(
            tiles=tile_url,
            attr=config.attribution,
            min_zoom=cache_min_zoom,
            max_zoom=cache_max_zoom + CACHE_ZOOM_IN_BUFFER,  # a little soft zoom past the cache, then a hard stop
            max_native_zoom=cache_max_zoom,  # only this deep is a real tile; the buffer zoom above is upscaled
        )
        map_kwargs = dict(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            max_bounds=True,
            max_bounds_viscosity=1.0,  # rigid bounds - no elastic overscroll past the cached area (which would show as blank whitespace, since no tiles exist beyond it)
        )
        zoom_start = cache_max_zoom
    else:
        tiles = config.tile_url_template()
        map_kwargs = {"attr": config.attribution}
        zoom_start = config.default_zoom

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_start,
        tiles=tiles,
        zoom_snap=0.25,  # fractional zoom: smooth scroll/pinch instead of jumping whole levels
        zoom_delta=0.5,
        **map_kwargs,
    )

    for stage in prediction.stages:
        points = [[p.latitude, p.longitude] for p in stage.points]
        folium.PolyLine(
            points,
            color=STAGE_COLORS.get(stage.name, "gray"),
            weight=3,
            tooltip=stage.name.capitalize(),
        ).add_to(m)

    folium.Marker(
        [launch.latitude, launch.longitude],
        tooltip="Launch",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(m)
    folium.Marker(
        [burst.latitude, burst.longitude],
        tooltip=f"Burst ({burst.altitude:.0f} m)",
        icon=folium.Icon(color="red", icon="star"),
    ).add_to(m)
    folium.Marker(
        [landing.latitude, landing.longitude],
        tooltip="Landing",
        icon=folium.Icon(color="black", icon="stop"),
    ).add_to(m)

    # fitBounds() is re-run (not just done once) because containers that
    # report the wrong size at initial script execution - a VS Code preview
    # pane, a split view, any layout that finishes sizing after the page
    # fires its scripts - leave Leaflet's internal size stale forever unless
    # told otherwise (invalidateSize()); that stale size is what shows up as
    # large blank margins around the map. Re-fitting on 'load' and on every
    # resize keeps the flight framed correctly regardless of what size the
    # container happened to be when the script first ran.
    min_zoom_lock = (
        f"leafletMap.setMinZoom(Math.max(containZoom, {cache_min_zoom}));"
        if cache_report is not None
        else ""
    )
    reset_min_zoom = (
        f"leafletMap.setMinZoom({cache_min_zoom});"
        if cache_report is not None
        else ""
    )
    script = f"""
    (function() {{
        var bounds = [[{min_lat}, {min_lon}], [{max_lat}, {max_lon}]];
        function refit() {{
            var leafletMap = {m.get_name()};
            {reset_min_zoom}
            leafletMap.invalidateSize();
            var llBounds = L.latLngBounds(bounds);
            // containZoom ("contain" fitting, same as fitBounds()) is the
            // smaller of the two axis-constrained zoom levels, so the whole
            // flight fits in view - this is the most-zoomed-out level that
            // still shows everything. Default/resize framing starts here
            // (whichever axis isn't the tight constraint shows blank margin,
            // which is expected: the flight's bounding box aspect ratio
            // doesn't match every window's). minZoom is capped at the same
            // level, so this is as far out as the map goes - zooming in from
            // here is unrestricted up to the deepest cached zoom.
            var containZoom = leafletMap.getBoundsZoom(llBounds, false);
            leafletMap.setView(llBounds.getCenter(), containZoom);
            {min_zoom_lock}
        }}
        // Looking up the map by its variable name has to happen inside
        // refit(), not once up here: this whole block runs (in page source
        // order) before folium's own script declares that variable further
        // down, so a lookup at this point would permanently capture
        // "undefined" instead of the real Leaflet map object.
        document.addEventListener('DOMContentLoaded', refit);
        window.addEventListener('load', refit);
        var resizeTimer;
        window.addEventListener('resize', function() {{
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(refit, 150);
        }});
    }})();
    """
    m.get_root().script.add_child(folium.Element(script))

    return m
