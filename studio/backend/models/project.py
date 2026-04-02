# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Literal

from pydantic import BaseModel, Field

ProjectStatus = Literal["created", "preprocessing", "sfm", "training", "done", "error"]
RunStatus = Literal["queued", "running", "done", "failed", "cancelled"]
SfmBackendId = Literal["colmap_incremental", "colmap_global", "mast3r"]


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)


class ProjectOut(BaseModel):
    id: str
    name: str
    status: str
    video_path: str | None = None
    sfm_path: str | None = None
    sfm_backend: str | None = None
    created_at: str


class RunOut(BaseModel):
    id: str
    project_id: str
    status: str
    metrics_path: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class SfmStartBody(BaseModel):
    backend: SfmBackendId = "colmap_incremental"
    params: dict[str, Any] = Field(default_factory=dict)


class TrainingStartBody(BaseModel):
    """Hydra-oriented launch: app preset + dataset path + overrides."""

    config_name: str = "apps/colmap_3dgrt.yaml"
    experiment_name: str = "studio_run"
    path: str | None = Field(
        None,
        description="COLMAP dataset root (images/ + sparse/0/). Default: project sfm/ directory.",
    )
    n_iterations: int | None = None
    val_frequency: int | None = None
    num_workers: int | None = None
    use_wandb: bool = False
    extra_overrides: dict[str, Any] = Field(default_factory=dict)
