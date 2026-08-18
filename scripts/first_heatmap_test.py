import asyncio
import json
from pathlib import Path

from app.core.config import get_settings
from app.providers.fortyguard import FortyGuardClient, FortyGuardError
from app.schemas.fortyguard import HeatmapRequest


# Small central-Peshawar AOI.
# GeoJSON coordinate order: [longitude, latitude].
PESHAWAR_PAYLOAD = {
    "polygon_aoi": {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Peshawar Day-1 Test AOI"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [71.5150, 34.0100],
                        [71.5250, 34.0100],
                        [71.5250, 34.0180],
                        [71.5150, 34.0180],
                        [71.5150, 34.0100]
                    ]]
                }
            }
        ]
    },
    "date_time": {
        "start_date": "2026-08-18",
        "start_time": "14:00",
        "filter_type": 1
    },
    "granularity": 100,
    "analytic_type": "tcm"
}


async def main() -> None:
    settings = get_settings()

    if not settings.api_key_configured:
        print("ERROR: FortyGuard API key is not configured.")
        print("Copy .env.example to .env and add your real key locally.")
        return

    request = HeatmapRequest.model_validate(PESHAWAR_PAYLOAD)
    client = FortyGuardClient(settings)

    try:
        print("Submitting real FortyGuard heatmap request...")
        submitted = await client.submit_heatmap(request)
        print(json.dumps(submitted, indent=2))

        activity_id = (submitted.get("data") or {}).get("activity_id")
        if not activity_id:
            print("ERROR: Provider returned no activity_id.")
            return

        print(f"\nActivity ID: {activity_id}")
        print("Polling until completion...")

        completed = await client.wait_for_completion(activity_id)

        data = completed.get("data") or {}
        status = data.get("status")
        result = data.get("result") or {}
        map_data = result.get("map_data")
        stats_data = result.get("stats_data")

        output_dir = Path("data/raw")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "first_heatmap_result.json"
        output_path.write_text(
            json.dumps(completed, indent=2),
            encoding="utf-8",
        )

        feature_count = None
        if isinstance(map_data, dict) and isinstance(map_data.get("features"), list):
            feature_count = len(map_data["features"])

        print("\nDAY 1 PROVIDER PROOF")
        print("--------------------")
        print(f"Final status: {status}")
        print(f"GeoJSON feature count: {feature_count}")
        print(f"stats_data present: {stats_data is not None}")
        print(f"Saved result: {output_path.resolve()}")

    except FortyGuardError as exc:
        print("\nFORTYGUARD ERROR")
        print("----------------")
        print(str(exc))
        print(f"HTTP status: {exc.status_code}")
        if exc.response_body is not None:
            print("Provider response:")
            print(json.dumps(exc.response_body, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
