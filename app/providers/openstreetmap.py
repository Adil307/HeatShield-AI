from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings


class OverpassError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, response_body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


@dataclass(frozen=True, slots=True)
class OverpassResult:
    endpoint: str
    response: dict[str, Any]


class OverpassClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        endpoints = [settings.overpass_base_url.strip(), settings.overpass_fallback_url.strip()]
        self.endpoints = tuple(dict.fromkeys(endpoint for endpoint in endpoints if endpoint))
        if not self.endpoints:
            raise OverpassError("No Overpass endpoint configured.")

    async def query(self, query: str) -> OverpassResult:
        last_error: OverpassError | None = None
        headers = {
            "User-Agent": self.settings.overpass_user_agent,
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(
            timeout=self.settings.overpass_request_timeout_seconds,
            headers=headers,
        ) as client:
            for endpoint in self.endpoints:
                for attempt in range(2):
                    try:
                        response = await client.post(endpoint, data={"data": query})
                    except (httpx.TimeoutException, httpx.NetworkError) as exc:
                        last_error = OverpassError(f"Overpass network failure at {endpoint}: {exc}")
                        if attempt == 0:
                            await asyncio.sleep(1.5)
                            continue
                        break

                    if response.status_code == 200:
                        try:
                            payload = response.json()
                        except ValueError as exc:
                            last_error = OverpassError(
                                f"Overpass returned invalid JSON from {endpoint}.",
                                status_code=200,
                                response_body=response.text[:1000],
                            )
                            break
                        if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
                            last_error = OverpassError(
                                f"Overpass returned an unexpected schema from {endpoint}.",
                                status_code=200,
                                response_body=response.text[:1000],
                            )
                            break
                        return OverpassResult(endpoint=endpoint, response=payload)

                    retryable = response.status_code == 429 or 500 <= response.status_code < 600
                    last_error = OverpassError(
                        f"Overpass request failed with HTTP {response.status_code} at {endpoint}.",
                        status_code=response.status_code,
                        response_body=response.text[:1000],
                    )
                    if retryable and attempt == 0:
                        await asyncio.sleep(1.5)
                        continue
                    break

        raise last_error or OverpassError("All Overpass endpoints failed.")
