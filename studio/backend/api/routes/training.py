# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from studio.backend.api.hub import hub
from studio.backend.api.routes.projects import project_dir
from studio.backend.core.database import get_connection
from studio.backend.models.project import TrainingStartBody
from studio.backend.models.training_config import TrainingLaunchConfig
from studio.backend.services.training_service import run_training_subprocess

router = APIRouter(prefix="/api/projects", tags=["training"])


@router.post("/{project_id}/runs")
async def start_training(project_id: str, body: TrainingStartBody) -> dict[str, str]:
    pdir = project_dir(project_id)
    if not pdir.is_dir():
        raise HTTPException(404, "project not found")
    sparse0 = pdir / "sfm" / "sparse" / "0"
    if not (sparse0 / "cameras.bin").is_file() and not (sparse0 / "cameras.txt").is_file():
        raise HTTPException(400, "SfM not complete; run sfm first")
    ds_path = body.path
    if not ds_path:
        ds_path = str((pdir / "sfm").resolve())
    else:
        ds_path = str(Path(ds_path).expanduser().resolve())

    rid = uuid.uuid4().hex
    run_dir = pdir / "runs" / rid
    run_dir.mkdir(parents=True, exist_ok=True)

    cfg = TrainingLaunchConfig(
        config_name=body.config_name,
        path=ds_path,
        out_dir=str((run_dir / "hydra_out").resolve()),
        experiment_name=body.experiment_name,
        n_iterations=body.n_iterations,
        val_frequency=body.val_frequency,
        num_workers=body.num_workers,
        use_wandb=body.use_wandb,
        extra_overrides=dict(body.extra_overrides),
    )

    async with await get_connection() as db:
        await db.execute(
            "INSERT INTO runs (id, project_id, config_json, status, metrics_path, started_at) VALUES (?, ?, ?, 'running', ?, datetime('now'))",
            (rid, project_id, json.dumps(body.model_dump()), str(run_dir / "metrics.jsonl")),
        )
        await db.execute("UPDATE projects SET status = ? WHERE id = ?", ("training", project_id))
        await db.commit()

    async def _run() -> None:

        async def on_line(line: str) -> None:
            await hub.broadcast(
                project_id,
                {"type": "log", "stage": "training", "backend": None, "line": line},
            )

        async def on_metric(m: dict) -> None:
            await hub.broadcast(project_id, {"type": "metric", **m})

        await hub.broadcast(
            project_id, {"type": "status", "stage": "training", "status": "running", "backend": None}
        )
        try:
            code = await run_training_subprocess(cfg, run_dir, on_line, on_metric)
            st = "done" if code == 0 else "failed"
            async with await get_connection() as db:
                await db.execute(
                    "UPDATE runs SET status = ?, finished_at = datetime('now') WHERE id = ?",
                    (st, rid),
                )
                await db.execute("UPDATE projects SET status = ? WHERE id = ?", ("created", project_id))
                await db.commit()
            await hub.broadcast(
                project_id, {"type": "status", "stage": "training", "status": st, "backend": None}
            )
        except Exception:
            async with await get_connection() as db:
                await db.execute(
                    "UPDATE runs SET status = 'failed', finished_at = datetime('now') WHERE id = ?",
                    (rid,),
                )
                await db.execute("UPDATE projects SET status = ? WHERE id = ?", ("error", project_id))
                await db.commit()
            await hub.broadcast(
                project_id, {"type": "status", "stage": "training", "status": "error", "backend": None}
            )
            raise

    asyncio.create_task(_run())
    return {"run_id": rid, "status": "started"}


@router.get("/{project_id}/runs")
async def list_runs(project_id: str) -> list[dict]:
    async with await get_connection() as db:
        cur = await db.execute(
            "SELECT id, status, metrics_path, started_at, finished_at FROM runs WHERE project_id = ? ORDER BY started_at DESC",
            (project_id,),
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "status": r[1],
            "metrics_path": r[2],
            "started_at": r[3],
            "finished_at": r[4],
        }
        for r in rows
    ]


@router.get("/{project_id}/runs/{run_id}/metrics")
async def get_metrics(project_id: str, run_id: str) -> list[dict]:
    pdir = project_dir(project_id)
    mp = pdir / "runs" / run_id / "metrics.jsonl"
    if not mp.is_file():
        raise HTTPException(404, "metrics not found")
    lines = mp.read_text().strip().splitlines()
    return [json.loads(x) for x in lines if x.strip()]
