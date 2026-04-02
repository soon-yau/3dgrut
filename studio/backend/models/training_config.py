# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Extensible training launch model; full Hydra tree can be passed via extra_overrides.

from typing import Any

from pydantic import BaseModel, Field


class TrainingLaunchConfig(BaseModel):
    config_name: str = "apps/colmap_3dgrt.yaml"
    path: str = ""
    out_dir: str = "./runs"
    experiment_name: str = "studio"
    n_iterations: int | None = None
    val_frequency: int | None = None
    num_workers: int | None = None
    use_wandb: bool = False
    extra_overrides: dict[str, Any] = Field(default_factory=dict)
