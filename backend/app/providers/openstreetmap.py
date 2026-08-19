from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings


class OverpassError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


@dataclass(frozen=True, slots=True)
class OverpassResult:
    endpoint: str
    response: dict[str, Any]
    request_count: int
    semantic_rejections: int
    attempted_endpoints: tuple[str, ...]


def validate_overpass_payload(payload: Any) -> dict[str, Any]:
    """Reject transport-success responses that contain Overpass runtime failures."""
    if not isinstance(payload, dict):
        raise OverpassError("Overpass returned a non-object JSON payload.", status_code=200)

    elements = payload.get("elements")
    if not isinstance(elements, list):
        raise OverpassError(
            "Overpass returned an unexpected schema without an elements list.",
            status_code=200,
            response_body=json.dumps(payload, ensure_ascii=False)[:1000],
        )

    remark = payload.get("remark")
    if isinstance(remark, str) and remark.strip():
        raise OverpassError(
            f"Overpass semantic failure: {remark.strip()}",
            status_code=200,
            response_body=json.dumps(payload, ensure_ascii=False)[:1000],
        )

    return payload


class OverpassClient:
    """Small-query client with sequential endpoint failover.

    We deliberately do not issue concurrent requests to public Overpass instances.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        endpoints = [
            settings.overpass_base_url.strip(),
            settings.overpass_fallback_url.strip(),
            settings.overpass_third_url.strip(),
        ]
        self.endpoints = tuple(dict.fromkeys(endpoint for endpoint in endpoints if endpoint))
        if not self.endpoints:
            raise OverpassError("No Overpass endpoint configured.")

    async def query(self, query: str) -> OverpassResult:
        last_error: OverpassError | None = None
        request_count = 0
        semantic_rejections = 0
        attempted_endpoints: list[str] = []
        headers = {
            "User-Agent": self.settings.overpass_user_agent,
            "Referer": "https://github.com/Adil307/Heckathon26",
            "Accept": "application/json",
        }
        timeout = httpx.Timeout(
            self.settings.overpass_request_timeout_seconds,
            connect=self.settings.overpass_connect_timeout_seconds,
        )

        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            for endpoint in self.endpoints:
                attempted_endpoints.append(endpoint)
                request_count += 1
                try:
                    response = await client.post(endpoint, data={"data": query})
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_error = OverpassError(
                        f"Overpass network failure at {endpoint}: {exc.__class__.__name__}: {exc}"
                    )
                    continue

                if response.status_code == 200:
                    try:
                        payload = response.json()
                    except ValueError:
                        last_error = OverpassError(
                            f"Overpass returned invalid JSON from {endpoint}.",
                            status_code=200,
                            response_body=response.text[:1000],
                        )
                        continue

                    try:
                        valid_payload = validate_overpass_payload(payload)
                    except OverpassError as exc:
                        semantic_rejections += 1
                        last_error = OverpassError(
                            f"{exc} Endpoint: {endpoint}",
                            status_code=exc.status_code,
                            response_body=exc.response_body,
                        )
                        continue

                    return OverpassResult(
                        endpoint=endpoint,
                        response=valid_payload,
                        request_count=request_count,
                        semantic_rejections=semantic_rejections,
                        attempted_endpoints=tuple(attempted_endpoints),
                    )

                retryable = response.status_code == 429 or 500 <= response.status_code < 600
                last_error = OverpassError(
                    f"Overpass request failed with HTTP {response.status_code} at {endpoint}.",
                    status_code=response.status_code,
                    response_body=response.text[:1000],
                )
                if not retryable:
                    break
                await asyncio.sleep(0.5)

        raise last_error or OverpassError("All Overpass endpoints failed.")
