# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import random
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException

from studio.backend.api.hub import hub
from studio.backend.api.routes.projects import project_dir
from studio.backend.core.database import get_connection
from studio.backend.models.project import SfmStartBody
from studio.backend.services.sfm_service import list_backends, run_sfm_backend

router = APIRouter(tags=["sfm"])

_global = APIRouter()


@_global.get("/api/sfm/backends")
async def get_sfm_backends():
    return [
        {
            "id": b.id,
            "display": b.display,
            "available": b.available,
            "requires_gpu": b.requires_gpu,
            "install_hint": b.install_hint,
        }
        for b in list_backends()
    ]


@router.post("/{project_id}/sfm/start")
async def sfm_start(project_id: str, body: SfmStartBody) -> dict[str, str]:
    pdir = project_dir(project_id)
    if not pdir.is_dir():
        raise HTTPException(404, "project not found")
    frames = pdir / "frames"
    sfm_root = pdir / "sfm"
    images = sfm_root / "images"
    if not any(frames.glob("frame_*.jpg")):
        raise HTTPException(400, "no frames; run preprocess first")
    sfm_root.mkdir(parents=True, exist_ok=True)
    # Clean prior COLMAP artifacts (keep directory)
    db_file = sfm_root / "database.db"
    if db_file.is_file():
        db_file.unlink()
    sparse_root = sfm_root / "sparse"
    if sparse_root.is_dir():
        shutil.rmtree(sparse_root)
    if images.is_dir():
        shutil.rmtree(images)
    images.mkdir(parents=True, exist_ok=True)

    async def _run() -> None:
        loop = asyncio.get_running_loop()

        def log(msg: str) -> None:
            asyncio.run_coroutine_threadsafe(
                hub.broadcast(
                    project_id,
                    {
                        "type": "log",
                        "stage": "sfm",
                        "backend": body.backend,
                        "line": msg,
                    },
                ),
                loop,
            )

        await hub.broadcast(
            project_id,
            {"type": "status", "stage": "sfm", "status": "running", "backend": body.backend},
        )
        async with await get_connection() as db:
            await db.execute("UPDATE projects SET status = ? WHERE id = ?", ("sfm", project_id))
            await db.commit()
        try:

            def copy_frames() -> None:
                for f in sorted(frames.glob("frame_*.jpg")):
                    shutil.copy2(f, images / f.name)

            await asyncio.to_thread(copy_frames)
            await asyncio.to_thread(run_sfm_backend, body.backend, sfm_root, body.params, log)
            rel = "sfm"
            async with await get_connection() as db:
                await db.execute(
                    "UPDATE projects SET status = ?, sfm_path = ?, sfm_backend = ? WHERE id = ?",
                    ("created", rel, body.backend, project_id),
                )
                await db.commit()
            await hub.broadcast(
                project_id, {"type": "status", "stage": "sfm", "status": "done", "backend": body.backend}
            )
        except Exception as e:
            await hub.broadcast(
                project_id,
                {"type": "status", "stage": "sfm", "status": "error", "backend": body.backend},
            )
            async with await get_connection() as db:
                await db.execute("UPDATE projects SET status = ? WHERE id = ?", ("error", project_id))
                await db.commit()
            raise e

    asyncio.create_task(_run())
    return {"status": "started"}


@router.get("/{project_id}/sfm/status")
async def sfm_status(project_id: str) -> dict:
    pdir = project_dir(project_id)
    sparse0 = pdir / "sfm" / "sparse" / "0"
    ok = (sparse0 / "cameras.bin").is_file() or (sparse0 / "cameras.txt").is_file()
    n_cams = 0
    n_pts = 0
    if ok:
        try:
            import pycolmap

            rec = pycolmap.Reconstruction(str(sparse0))
            n_cams = rec.num_reg_images()
            n_pts = rec.num_points3D()
        except Exception:
            pass
    async with await get_connection() as db:
        db.row_factory = None
        cur = await db.execute("SELECT sfm_backend FROM projects WHERE id = ?", (project_id,))
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "project not found")
    return {"ready": ok, "n_cameras": n_cams, "n_points": n_pts, "backend": row[0]}


@router.get("/{project_id}/sfm/pointcloud")
async def sfm_pointcloud(project_id: str, max_points: int = 100_000) -> dict:
    pdir = project_dir(project_id)
    sparse0 = pdir / "sfm" / "sparse" / "0"
    if not (sparse0 / "points3D.bin").is_file() and not (sparse0 / "points3D.txt").is_file():
        raise HTTPException(404, "no sparse point cloud")
    try:
        import pycolmap

        rec = pycolmap.Reconstruction(str(sparse0))
        pts = []
        colors = []
        for p in rec.points3D.values():
            pts.append(p.xyz.tolist())
            c = p.color
            colors.append([int(c[0]), int(c[1]), int(c[2])])
        if len(pts) > max_points:
            idx = random.sample(range(len(pts)), max_points)
            pts = [pts[i] for i in idx]
            colors = [colors[i] for i in idx]
        return {"positions": pts, "colors": colors}
    except Exception as e:
        raise HTTPException(500, f"pycolmap read failed: {e}") from e


# merge routers in main: include _global and router with prefix /api/projects
