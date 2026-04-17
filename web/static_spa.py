"""Mount the built React SPA. Falls through to index.html for HTML5 history routes."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

log = logging.getLogger(__name__)


def mount_spa(app: FastAPI, static_dir: Path) -> None:
    """Mount /assets and register a catch-all route returning index.html.

    If `static_dir` doesn't exist (e.g. during early dev before the SPA is built),
    the catch-all returns a short placeholder so API-only testing still works.
    """
    index = static_dir / "index.html"
    assets_dir = static_dir / "assets"

    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    else:
        log.warning("SPA assets dir missing at %s — serving placeholder on /", assets_dir)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_catch_all(full_path: str, request: Request):  # type: ignore[override]
        # Never intercept API or WebSocket routes — they were already matched above.
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "not found"})
        if index.is_file():
            return FileResponse(str(index))
        return JSONResponse(
            status_code=503,
            content={
                "detail": "SPA bundle not built; run `npm run build` in frontend/.",
                "path": full_path or "/",
            },
        )
