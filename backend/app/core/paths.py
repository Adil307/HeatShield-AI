from pathlib import Path

# backend/app/core/paths.py -> parents[2] is backend/
BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


def backend_path(*parts: str | Path) -> Path:
    return BACKEND_ROOT.joinpath(*parts)
