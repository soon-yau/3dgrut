# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import shutil
import uuid
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, HTTPException

from studio.backend.core.config import settings
from studio.backend.core.database import get_connection
from studio.backend.models.project import ProjectCreate, ProjectOut

router = APIRouter(prefix="/api/projects", tags=["projects"])


def project_dir(project_id: str) -> Path:
    return settings.projects_root / project_id


@router.post("", response_model=ProjectOut)
async def create_project(body: ProjectCreate) -> ProjectOut:
    pid = uuid.uuid4().hex
    pdir = project_dir(pid)
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "video").mkdir(exist_ok=True)
    (pdir / "frames").mkdir(exist_ok=True)
    (pdir / "sfm").mkdir(exist_ok=True)
    (pdir / "runs").mkdir(exist_ok=True)
    async with await get_connection() as db:
        await db.execute(
            "INSERT INTO projects (id, name, status) VALUES (?, ?, 'created')",
            (pid, body.name),
        )
        await db.commit()
    return await get_project(pid)


@router.get("", response_model=list[ProjectOut])
async def list_projects() -> list[ProjectOut]:
    async with await get_connection() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, name, status, video_path, sfm_path, sfm_backend, created_at FROM projects ORDER BY created_at DESC"
        )
        rows = await cur.fetchall()
    return [_row_to_out(dict(r)) for r in rows]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str) -> ProjectOut:
    async with await get_connection() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, name, status, video_path, sfm_path, sfm_backend, created_at FROM projects WHERE id = ?",
            (project_id,),
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "project not found")
    return _row_to_out(dict(row))


@router.delete("/{project_id}")
async def delete_project(project_id: str) -> dict[str, str]:
    async with await get_connection() as db:
        cur = await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "project not found")
    pdir = project_dir(project_id)
    if pdir.is_dir():
        shutil.rmtree(pdir)
    return {"status": "deleted"}


def _row_to_out(row: dict) -> ProjectOut:
    return ProjectOut(
        id=row["id"],
        name=row["name"],
        status=row["status"],
        video_path=row["video_path"],
        sfm_path=row["sfm_path"],
        sfm_backend=row["sfm_backend"],
        created_at=row["created_at"],
    )
