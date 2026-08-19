from fastapi import FastAPI

from app.api.routes_copilot import router as copilot_router
from app.api.routes_decision import router as decision_router
from app.api.routes_fortyguard import router as fortyguard_router

app = FastAPI(
    title="HeatShield AI API",
    version="0.1.0",
    description="Backend for the FortyGuard Global AI Hackathon'26 project.",
)

app.include_router(
    fortyguard_router,
    prefix="/api/v1/fortyguard",
    tags=["FortyGuard"],
)

app.include_router(
    decision_router,
    prefix="/api/v1/decision",
    tags=["Decision Intelligence"],
)

app.include_router(
    copilot_router,
    prefix="/api/v1/copilot",
    tags=["Grounded Copilot"],
)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "heatshield-api",
        "version": "0.1.0",
    }
