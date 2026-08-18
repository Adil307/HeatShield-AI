import asyncio
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.schemas.fortyguard import HeatmapRequest


class FortyGuardError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: Any | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class FortyGuardClient:
    def __init__(self, settings: Settings):
        self.settings = settings

        if not settings.api_key_configured:
            raise FortyGuardError(
                "FORTYGUARD_API_KEY is not configured. Add it to your local .env file."
            )

        self.base_url = settings.fortyguard_base_url.rstrip("/")
        self.headers = {
            "api-key": settings.fortyguard_api_key,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        timeout = httpx.Timeout(self.settings.fortyguard_request_timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=self.headers,
                json=json_body,
            )

        try:
            body: Any = response.json()
        except ValueError:
            body = response.text

        if response.is_error:
            raise FortyGuardError(
                f"FortyGuard request failed with HTTP {response.status_code}",
                status_code=response.status_code,
                response_body=body,
            )

        if not isinstance(body, dict):
            raise FortyGuardError(
                "FortyGuard returned an unexpected non-object response.",
                status_code=response.status_code,
                response_body=body,
            )

        return body

    async def submit_heatmap(self, request: HeatmapRequest) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/heatmap",
            json_body=request.to_provider_payload(),
        )

    async def get_status(self, activity_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/status/{activity_id}")

    async def wait_for_completion(self, activity_id: str) -> dict[str, Any]:
        started = time.monotonic()

        while True:
            response = await self.get_status(activity_id)
            data = response.get("data") or {}
            status = str(data.get("status", "")).lower()

            if status in {"completed", "succeeded"}:
                return response

            if status in {"failed", "error"}:
                raise FortyGuardError(
                    f"FortyGuard activity {activity_id} failed.",
                    response_body=response,
                )

            if time.monotonic() - started >= self.settings.fortyguard_max_poll_seconds:
                raise FortyGuardError(
                    f"Timed out waiting for activity {activity_id}.",
                    response_body=response,
                )

            await asyncio.sleep(self.settings.fortyguard_poll_interval_seconds)
