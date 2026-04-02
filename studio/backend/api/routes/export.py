# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/projects", tags=["export"])


@router.post("/{project_id}/runs/{run_id}/export/ply")
async def export_ply(project_id: str, run_id: str) -> dict:
    raise HTTPException(501, "PLY export: invoke threedgrut export scripts from checkpoint path (planned)")


@router.post("/{project_id}/runs/{run_id}/export/usd")
async def export_usd(project_id: str, run_id: str) -> dict:
    raise HTTPException(501, "USD export: invoke threedgrut export scripts (planned)")
