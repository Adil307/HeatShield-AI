from __future__ import annotations

import sys
from pathlib import Path as _BackendPath

sys.path.insert(0, str(_BackendPath(__file__).resolve().parents[1]))

import asyncio
import json

from app.core.config import get_settings
from app.providers.fortyguard import FortyGuardClient, FortyGuardError
from app.schemas.fortyguard import EnvironmentalDateTimeConfig, EnvironmentalParametersRequest


async def main() -> int:
    request = EnvironmentalParametersRequest(
        latitude=40.7128,
        longitude=-74.0060,
        temperature=32.5,
        date_time=EnvironmentalDateTimeConfig(
            start_date="2024-07-15",
            start_time="14:00",
            filter_type=1,
        ),
    )

    try:
        client = FortyGuardClient(get_settings())
        submitted = await client.submit_environmental_parameters(request)
        print(json.dumps(submitted, indent=2))
        activity_id = (submitted.get("data") or {}).get("activity_id")
        if not activity_id:
            raise FortyGuardError("No activity_id returned.", response_body=submitted)
        completed = await client.wait_for_completion(activity_id)
        print(json.dumps(completed, indent=2)[:6000])
        return 0
    except FortyGuardError as exc:
        print(f"FORTYGUARD ERROR: {exc}")
        if exc.response_body is not None:
            print(exc.response_body)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
