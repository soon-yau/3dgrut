# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from studio.backend.api.hub import hub
from studio.backend.api.routes import export, preprocess, projects, sfm, training
from studio.backend.core.config import settings
from studio.backend.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    settings.projects_root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="3DGRUT Studio", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(preprocess.router)
app.include_router(sfm.router, prefix="/api/projects")
app.include_router(sfm._global)
app.include_router(training.router)
app.include_router(export.router)


@app.websocket("/ws/{project_id}")
async def websocket_project(project_id: str, websocket: WebSocket):
    await hub.connect(project_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(project_id, websocket)


@app.get("/health")
async def health():
    return {"status": "ok", "repo_root": str(settings.repo_root)}


_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if not _dist.is_dir():

    @app.get("/")
    async def root_no_spa():
        return {
            "service": "3DGRUT Studio API",
            "hint": "Build UI: cd studio/frontend && npm install && npm run build",
            "health": "/health",
        }


if _dist.is_dir():
    _assets = _dist / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/")
    async def spa_index():
        return FileResponse(_dist / "index.html")

    @app.get("/{full_path:path}")
    async def spa_catchall(full_path: str):
        if full_path.startswith("api/") or full_path in ("openapi.json", "redoc", "docs"):
            raise HTTPException(404)
        cand = _dist / full_path
        if cand.is_file():
            return FileResponse(cand)
        return FileResponse(_dist / "index.html")
