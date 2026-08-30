"""Plot a top-down (lat/lon) view of a Tawhiri flight prediction.

Usage:
    python scripts/plot_flight.py --prediction data/sample_prediction.json
    python scripts/plot_flight.py --prediction data/sample_prediction.json --output flight.png
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from habgroundsim import tawhiri
from habgroundsim.config import AppConfig, DEFAULT_CONFIG_PATH

STAGE_COLORS = {"ascent": "tab:blue", "descent": "tab:orange"}


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
        help="Save the plot to this path instead of showing it interactively",
    )
    return parser.parse_args()


def plot_prediction(prediction: tawhiri.Prediction, title: str, output: Path | None) -> None:
    fig, ax = plt.subplots(figsize=(8, 8))

    for stage in prediction.stages:
        lons = [p.longitude for p in stage.points]
        lats = [p.latitude for p in stage.points]
        ax.plot(
            lons,
            lats,
            color=STAGE_COLORS.get(stage.name, "gray"),
            label=stage.name.capitalize(),
            linewidth=1.5,
        )

    launch = prediction.launch_point
    burst = prediction.burst_point
    landing = prediction.landing_point

    ax.scatter([launch.longitude], [launch.latitude], color="green", marker="^", s=80, zorder=5, label="Launch")
    ax.scatter([burst.longitude], [burst.latitude], color="red", marker="*", s=120, zorder=5, label="Burst")
    ax.scatter([landing.longitude], [landing.latitude], color="black", marker="x", s=80, zorder=5, label="Landing")

    all_points = prediction.all_points
    mean_lat = sum(p.latitude for p in all_points) / len(all_points)
    ax.set_aspect(1.0 / math.cos(math.radians(mean_lat)))

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend()

    fig.tight_layout()

    if output:
        fig.savefig(output, dpi=150)
        print(f"Saved plot to {output}")
    else:
        plt.show()


def main() -> None:
    args = parse_args()

    config = AppConfig.load(args.config)
    raw = tawhiri.load_prediction_file(args.prediction)
    prediction = tawhiri.parse_prediction(raw)

    mismatches = tawhiri.diff_against_config(prediction.request, config.tawhiri_request.as_query_params())
    if mismatches:
        print("Warning: prediction file's request params differ from config.json:")
        for key, values in mismatches.items():
            print(f"  {key}: config={values['config']!r} prediction={values['prediction']!r}")

    launch_dt = prediction.request.get("launch_datetime", "unknown launch time")
    burst_alt = prediction.request.get("burst_altitude", "unknown burst altitude")
    title = f"Predicted flight - launch {launch_dt}, burst {burst_alt} m"

    plot_prediction(prediction, title, args.output)


if __name__ == "__main__":
    main()
