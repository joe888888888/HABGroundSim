"""
Fetch a live Tawhiri flight prediction and save it as a JSON fixture in data/.

By default, fetches using config.json's tawhiri.request block. Any of those
request params can be overridden for a one-off flight without editing
config.json (e.g. testing a different launch site or day).

Tawhiri is a shared community-run service with no published rate limit - be a
good citizen: don't run this in a loop or re-fetch the same prediction
repeatedly. The saved JSON file is a reusable fixture for plot_flight.py /
generate_map.py, so fetch once and reuse it.

Usage:
    python scripts/fetch_prediction.py
    python scripts/fetch_prediction.py --lat 35.1985 --lon -106.5931 --datetime 2026-09-05T18:00:00Z
    python scripts/fetch_prediction.py --output data/my_flight.json
"""

from __future__ import annotations

import argparse
import dataclasses
import sys  
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from habgroundsim import tawhiri
from habgroundsim.config import AppConfig, DEFAULT_CONFIG_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config.json (default: %(default)s)",
    )
    parser.add_argument("--lat", type=float, dest="launch_latitude", help="Override launch_latitude")
    parser.add_argument(
        "--lon",
        type=float,
        dest="launch_longitude",
        help="Override launch_longitude, accepted in -180..180 (converted to Tawhiri's 0..360)",
    )
    parser.add_argument("--altitude", type=float, dest="launch_altitude", help="Override launch_altitude (m)")
    parser.add_argument("--datetime", dest="launch_datetime", help="Override launch_datetime (RFC3339, e.g. 2026-09-05T18:00:00Z)")
    parser.add_argument("--ascent-rate", type=float, dest="ascent_rate", help="Override ascent_rate (m/s)")
    parser.add_argument("--burst-altitude", type=float, dest="burst_altitude", help="Override burst_altitude (m)")
    parser.add_argument("--descent-rate", type=float, dest="descent_rate", help="Override descent_rate (m/s)")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to save the fetched JSON (default: data/tawhiri_<lat>_<lon>_<datetime>.json)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = AppConfig.load(args.config)
    request_config = config.tawhiri_request

    overrides = {
        field: value
        for field in ("launch_latitude", "launch_longitude", "launch_altitude", "launch_datetime",
                       "ascent_rate", "burst_altitude", "descent_rate")
        if (value := getattr(args, field)) is not None
    }
    if "launch_longitude" in overrides and overrides["launch_longitude"] < 0:
        overrides["launch_longitude"] += 360
    if overrides:
        request_config = dataclasses.replace(request_config, **overrides)

    data_dir = args.output.parent if args.output else tawhiri.DEFAULT_DATA_DIR
    filename = args.output.name if args.output else None

    raw, saved_path = tawhiri.fetch_prediction(request_config, data_dir=data_dir, filename=filename)
    prediction = tawhiri.parse_prediction(raw)

    print(f"Saved prediction to {saved_path}")
    print(
        f"Launch {prediction.launch_point.latitude:.4f},{prediction.launch_point.longitude:.4f} -> "
        f"burst {prediction.burst_point.altitude:.0f}m -> "
        f"landing {prediction.landing_point.latitude:.4f},{prediction.landing_point.longitude:.4f}"
    )
    if raw.get("warnings"):
        print(f"Warnings: {raw['warnings']}")


if __name__ == "__main__":
    main()
