from __future__ import annotations

import uvicorn
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_dashboard import router as dashboard_router
from app.core.paths import REPO_ROOT
from app.main import app

FRONTEND_DIR = REPO_ROOT / "frontend" / "dashboard"


def _register_once() -> None:
    route_paths = {getattr(route, "path", None) for route in app.routes}
    if "/api/v1/dashboard/overview" not in route_paths:
        app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["dashboard"])
    if not FRONTEND_DIR.exists():
        raise RuntimeError(f"Dashboard frontend directory not found: {FRONTEND_DIR}")
    if "/dashboard" not in route_paths:
        app.mount("/dashboard", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="heatshield-dashboard")
    if "/day10" not in route_paths:
        @app.get("/day10", include_in_schema=False)
        async def day10_redirect():
            return RedirectResponse(url="/dashboard/")

_register_once()

if __name__ == "__main__":
    print("HeatShield Day 10 dashboard")
    print("Dashboard: http://127.0.0.1:8000/dashboard/")
    print("API docs : http://127.0.0.1:8000/docs")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
