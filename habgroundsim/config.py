# Loads config.json (non-secret, tunable parameters) and .env (API keys).

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


@dataclass
class TawhiriRequestConfig:
    launch_latitude: float
    launch_longitude: float
    launch_altitude: float
    launch_datetime: str
    ascent_rate: float
    burst_altitude: float
    descent_rate: float
    profile: str
    dataset: str
    format: str = "json"
    version: int = 1

    def as_query_params(self) -> dict:
        # Params in the shape the Tawhiri API expects for a live request.
        return {
            "launch_latitude": self.launch_latitude,
            "launch_longitude": self.launch_longitude,
            "launch_altitude": self.launch_altitude,
            "launch_datetime": self.launch_datetime,
            "ascent_rate": self.ascent_rate,
            "burst_altitude": self.burst_altitude,
            "descent_rate": self.descent_rate,
            "profile": self.profile,
            "dataset": self.dataset,
            "format": self.format,
            "version": self.version,
        }


@dataclass
class MapTilerConfig:
    style: str
    tile_format: str
    default_zoom: int
    attribution: str
    use_local_cache: bool
    cache_dir: str
    zoom_levels: List[int]
    bounds_margin_deg: float
    api_key: Optional[str]  # loaded from environment, not config.json

    def tile_url_template(self) -> str:
        """Live MapTiler URL template (literal {z}/{x}/{y}, key already filled
        in). Hits the real API on every tile a browser requests - prefer the
        local tile cache (tile_cache.py) unless you specifically want that.
        """
        if not self.api_key:
            raise MissingApiKeyError(
                "MAPTILER_API_KEY is not set. Add it to .env."
            )
        return f"https://api.maptiler.com/maps/{self.style}/{{z}}/{{x}}/{{y}}.{self.tile_format}?key={self.api_key}"


class MissingApiKeyError(RuntimeError):
    pass


@dataclass
class AppConfig:
    tawhiri_request: TawhiriRequestConfig
    maptiler: MapTilerConfig

    @classmethod
    def load(cls, config_path: Path | str = DEFAULT_CONFIG_PATH, env_path: Optional[Path | str] = None) -> "AppConfig":
        load_dotenv(dotenv_path=env_path)  # no-op if .env doesn't exist

        config_path = Path(config_path)
        with config_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        tawhiri_raw = raw["tawhiri"]["request"]
        tawhiri_request = TawhiriRequestConfig(**tawhiri_raw)

        maptiler_raw = raw.get("maptiler", {})
        maptiler = MapTilerConfig(
            style=maptiler_raw.get("style", "hybrid"),
            tile_format=maptiler_raw.get("tile_format", "jpg"),
            default_zoom=maptiler_raw.get("default_zoom", 11),
            attribution=maptiler_raw.get(
                "attribution", '© MapTiler © OpenStreetMap contributors'
            ),
            use_local_cache=maptiler_raw.get("use_local_cache", True),
            cache_dir=maptiler_raw.get("cache_dir", "tile_cache"),
            zoom_levels=maptiler_raw.get("zoom_levels", [7, 8, 9, 10, 11, 12]),
            bounds_margin_deg=maptiler_raw.get("bounds_margin_deg", 0.15),
            api_key=os.environ.get("MAPTILER_API_KEY") or None,
        )

        return cls(tawhiri_request=tawhiri_request, maptiler=maptiler)
