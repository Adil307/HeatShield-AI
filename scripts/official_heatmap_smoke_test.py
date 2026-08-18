import asyncio
import httpx

from app.core.config import get_settings


async def main():
    settings = get_settings()

    payload = {
        "polygon_aoi": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [-74.0170, 40.7050],
                            [-74.0030, 40.7050],
                            [-74.0030, 40.7180],
                            [-74.0170, 40.7180],
                            [-74.0170, 40.7050]
                        ]]
                    }
                }
            ]
        },
        "date_time": {
            "start_date": "2024-07-15",
            "start_time": "14:00",
            "filter_type": 1
        },
        "granularity": 100
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.fortyguard.com/v1/heatmap",
            headers={
                "api-key": settings.fortyguard_api_key
            },
            json=payload
        )

    print("HTTP:", response.status_code)
    print("BODY:", response.text)


asyncio.run(main())
