# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from studio.backend.api.hub import hub
from studio.backend.api.routes.projects import project_dir
from studio.backend.core.database import get_connection
from studio.backend.services import video_service

router = APIRouter(prefix="/api/projects", tags=["preprocess"])


class PreprocessStartBody(BaseModel):
    fps: float = Field(2.0, ge=0.1, le=60.0)
    jpeg_quality: int = Field(95, ge=50, le=100)
    time_start_s: float = 0.0
    time_end_s: float | None = None
    scale_divisor: int = Field(1, ge=1, le=8)
    blur_threshold: float = Field(0.0, ge=0.0)  # 0 = keep all after scoring


@router.post("/{project_id}/upload")
async def upload_video(project_id: str, file: UploadFile = File(...)) -> dict[str, str]:
    pdir = project_dir(project_id)
    if not pdir.is_dir():
        raise HTTPException(404, "project not found")
    dest_dir = pdir / "video"
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "video.mp4").suffix or ".mp4"
    out = dest_dir / f"original{suffix}"
    with out.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    rel = str(out.relative_to(pdir))
    async with await get_connection() as db:
        await db.execute("UPDATE projects SET video_path = ? WHERE id = ?", (rel, project_id))
        await db.commit()
    return {"video_path": rel}


@router.post("/{project_id}/preprocess/start")
async def preprocess_start(project_id: str, body: PreprocessStartBody) -> dict[str, str]:
    pdir = project_dir(project_id)
    if not pdir.is_dir():
        raise HTTPException(404, "project not found")
    video_dir = pdir / "video"
    vids = list(video_dir.glob("original.*"))
    if not vids:
        raise HTTPException(400, "no uploaded video in video/original.*")
    frames = pdir / "frames"
    frames.mkdir(parents=True, exist_ok=True)

    async def _run() -> None:
        loop = asyncio.get_running_loop()

        def log_sync(msg: str) -> None:
            asyncio.run_coroutine_threadsafe(
                hub.broadcast(
                    project_id,
                    {"type": "log", "stage": "preprocess", "backend": None, "line": msg},
                ),
                loop,
            )

        await hub.broadcast(
            project_id, {"type": "status", "stage": "preprocess", "status": "running", "backend": None}
        )
        async with await get_connection() as db:
            await db.execute(
                "UPDATE projects SET status = ? WHERE id = ?", ("preprocessing", project_id)
            )
            await db.commit()
        try:

            def extract() -> None:
                video_service.extract_frames(
                    vids[0],
                    frames,
                    fps=body.fps,
                    jpeg_quality=body.jpeg_quality,
                    time_start_s=body.time_start_s,
                    time_end_s=body.time_end_s,
                    scale_divisor=body.scale_divisor,
                    log=log_sync,
                )

            await asyncio.to_thread(extract)
            scores = await asyncio.to_thread(video_service.score_frames, frames)
            video_service.write_frame_quality_json(frames, scores)
            if body.blur_threshold > 0:
                await asyncio.to_thread(
                    video_service.filter_frames_by_blur, frames, scores, body.blur_threshold, log_sync
                )
            await hub.broadcast(
                project_id, {"type": "status", "stage": "preprocess", "status": "done", "backend": None}
            )
            async with await get_connection() as db:
                await db.execute("UPDATE projects SET status = ? WHERE id = ?", ("created", project_id))
                await db.commit()
        except Exception as e:
            await hub.broadcast(
                project_id,
                {"type": "status", "stage": "preprocess", "status": "error", "backend": None},
            )
            async with await get_connection() as db:
                await db.execute("UPDATE projects SET status = ? WHERE id = ?", ("error", project_id))
                await db.commit()
            raise e

    asyncio.create_task(_run())
    return {"status": "started"}


@router.get("/{project_id}/frames")
async def list_frames(project_id: str) -> dict:
    pdir = project_dir(project_id)
    frames = pdir / "frames"
    if not frames.is_dir():
        raise HTTPException(404, "frames not found")
    qpath = frames / "frame_quality.json"
    scores: dict = {}
    if qpath.is_file():
        scores = json.loads(qpath.read_text())
    files = sorted(f.name for f in frames.glob("frame_*.jpg"))
    return {"frames": files, "blur_scores": scores}
