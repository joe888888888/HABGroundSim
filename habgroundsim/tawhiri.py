"""Fetches and parses Tawhiri prediction responses into flight data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import requests

from .config import TawhiriRequestConfig

# SondeHub-hosted Tawhiri instance (https://tawhiri.readthedocs.io/en/latest/api.html
# documents the request params; the old predict.cusf.co.uk host behind that doc is
# defunct - this is the live community-run replacement).
TAWHIRI_API_URL = "https://api.v2.sondehub.org/tawhiri"

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TawhiriApiError(RuntimeError):
    pass


def normalize_longitude(longitude: float) -> float:
    """Tawhiri reports longitude in 0-360; convert to the usual -180..180 range."""
    return longitude - 360 if longitude > 180 else longitude


@dataclass
class TrajectoryPoint:
    time: datetime
    latitude: float
    longitude: float  # normalized to -180..180
    altitude: float


@dataclass
class Stage:
    name: str  # "ascent" or "descent"
    points: List[TrajectoryPoint]


@dataclass
class Prediction:
    request: dict
    metadata: dict
    warnings: dict
    stages: List[Stage]

    @property
    def all_points(self) -> List[TrajectoryPoint]:
        points: List[TrajectoryPoint] = []
        for stage in self.stages:
            points.extend(stage.points)
        return points

    @property
    def launch_point(self) -> TrajectoryPoint:
        return self.stages[0].points[0]

    @property
    def burst_point(self) -> TrajectoryPoint:
        ascent = next((s for s in self.stages if s.name == "ascent"), self.stages[0])
        return ascent.points[-1]

    @property
    def landing_point(self) -> TrajectoryPoint:
        return self.stages[-1].points[-1]


def load_prediction_file(path: Path | str) -> dict:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _default_prediction_filename(request_config: TawhiriRequestConfig) -> str:
    launch_dt = request_config.launch_datetime.replace(":", "")
    return f"tawhiri_{request_config.launch_latitude}_{request_config.launch_longitude}_{launch_dt}.json"


def fetch_prediction(
    request_config: TawhiriRequestConfig,
    data_dir: Path | str = DEFAULT_DATA_DIR,
    filename: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> Tuple[dict, Path]:
    """Fetch a live prediction from the Tawhiri API and save the raw response to disk.

    Returns (raw_response, saved_path) - pass raw_response straight to
    parse_prediction(), same as you would data from load_prediction_file(). Every
    live fetch is saved as a JSON file rather than used in memory only, so it
    becomes a reusable fixture instead of a one-off call.

    Tawhiri is a shared community-run service with no published rate limit - be a
    good citizen: don't call this in a loop or re-request the same prediction
    repeatedly during development. Reuse the saved file instead.
    """
    session = session or requests.Session()
    try:
        response = session.get(
            TAWHIRI_API_URL, params=request_config.as_query_params(), timeout=30
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        description = None
        try:
            description = response.json().get("error", {}).get("description")
        except ValueError:
            pass
        raise TawhiriApiError(description or str(exc)) from exc
    except requests.RequestException as exc:
        raise TawhiriApiError(str(exc)) from exc

    data = response.json()
    if "error" in data:
        raise TawhiriApiError(data["error"].get("description", str(data["error"])))

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    output_path = data_dir / (filename or _default_prediction_filename(request_config))
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return data, output_path


def parse_prediction(data: dict) -> Prediction:
    stages = []
    for stage_raw in data["prediction"]:
        points = [
            TrajectoryPoint(
                time=datetime.fromisoformat(p["datetime"].replace("Z", "+00:00")),
                latitude=p["latitude"],
                longitude=normalize_longitude(p["longitude"]),
                altitude=p["altitude"],
            )
            for p in stage_raw["trajectory"]
        ]
        stages.append(Stage(name=stage_raw["stage"], points=points))

    return Prediction(
        request=data.get("request", {}),
        metadata=data.get("metadata", {}),
        warnings=data.get("warnings", {}),
        stages=stages,
    )


def diff_against_config(prediction_request: dict, config_request: dict) -> dict:
    """Fields where the prediction's own request block differs from config.json.

    Useful as a sanity check when reading a prediction file that was fetched
    separately, to confirm it actually matches the parameters you think you
    asked for.
    """
    mismatches = {}
    for key, config_value in config_request.items():
        if key not in prediction_request:
            continue
        prediction_value = prediction_request[key]
        if prediction_value != config_value:
            mismatches[key] = {"config": config_value, "prediction": prediction_value}
    return mismatches
