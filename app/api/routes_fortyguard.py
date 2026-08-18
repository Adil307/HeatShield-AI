from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.providers.fortyguard import FortyGuardClient, FortyGuardError
from app.schemas.fortyguard import HeatmapRequest

router = APIRouter()


def make_client() -> FortyGuardClient:
    return FortyGuardClient(get_settings())


def provider_http_error(exc: FortyGuardError) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "message": str(exc),
            "provider_status_code": exc.status_code,
            "provider_response": exc.response_body,
        },
    )


@router.get("/config-status")
async def config_status() -> dict:
    settings = get_settings()
    return {
        "api_key_configured": settings.api_key_configured,
        "base_url": settings.fortyguard_base_url,
        "api_key_value_exposed": False,
    }


@router.post("/heatmap/submit")
async def submit_heatmap(request: HeatmapRequest) -> dict:
    try:
        return await make_client().submit_heatmap(request)
    except FortyGuardError as exc:
        raise provider_http_error(exc)


@router.get("/status/{activity_id}")
async def get_status(activity_id: str) -> dict:
    try:
        return await make_client().get_status(activity_id)
    except FortyGuardError as exc:
        raise provider_http_error(exc)


@router.post("/heatmap/run")
async def run_heatmap(request: HeatmapRequest) -> dict:
    # Development convenience endpoint:
    # submit -> activity_id -> poll -> return completed result.
    try:
        client = make_client()
        submitted = await client.submit_heatmap(request)

        activity_id = (submitted.get("data") or {}).get("activity_id")
        if not activity_id:
            raise FortyGuardError(
                "Submission returned no activity_id.",
                response_body=submitted,
            )

        completed = await client.wait_for_completion(activity_id)

        return {
            "submission": submitted,
            "completion": completed,
        }
    except FortyGuardError as exc:
        raise provider_http_error(exc)
