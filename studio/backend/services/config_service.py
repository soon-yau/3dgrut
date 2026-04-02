# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from typing import Any

from omegaconf import OmegaConf

from studio.backend.core.config import settings
from studio.backend.models.training_config import TrainingLaunchConfig


def build_hydra_overrides(cfg: TrainingLaunchConfig) -> list[str]:
    """Build CLI-style overrides for `python train.py`."""
    o: list[str] = []
    if cfg.path:
        o.append(f"path={cfg.path}")
    if cfg.out_dir:
        o.append(f"out_dir={cfg.out_dir}")
    if cfg.experiment_name:
        o.append(f"experiment_name={cfg.experiment_name}")
    if cfg.n_iterations is not None:
        o.append(f"n_iterations={cfg.n_iterations}")
    if cfg.val_frequency is not None:
        o.append(f"val_frequency={cfg.val_frequency}")
    if cfg.num_workers is not None:
        o.append(f"num_workers={cfg.num_workers}")
    if cfg.use_wandb:
        o.append("use_wandb=true")
    for k, v in cfg.extra_overrides.items():
        if isinstance(v, str) and not v.startswith("${"):
            o.append(f"{k}={v}")
        elif isinstance(v, (int, float, bool)):
            o.append(f"{k}={v}")
        else:
            o.append(f"{k}={v!s}")
    return o


def write_run_config_yaml(run_dir: Path, cfg: TrainingLaunchConfig) -> Path:
    """Write a flat YAML snapshot for reproducibility (not necessarily full Hydra compose)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "studio_launch.yaml"
    data: dict[str, Any] = {
        "config_name": cfg.config_name,
        "path": cfg.path,
        "out_dir": cfg.out_dir,
        "experiment_name": cfg.experiment_name,
        "n_iterations": cfg.n_iterations,
        "val_frequency": cfg.val_frequency,
        "num_workers": cfg.num_workers,
        "use_wandb": cfg.use_wandb,
        "extra_overrides": cfg.extra_overrides,
    }
    out.write_text(OmegaConf.to_yaml(OmegaConf.create(data)))
    return out


def train_command_hydra(cfg: TrainingLaunchConfig) -> list[str]:
    """`python train.py --config-name <name> key=value ...` from repo root."""
    repo = settings.repo_root
    train_py = repo / "train.py"
    name = cfg.config_name.replace(".yaml", "").strip()
    if "/" in name:
        name = name.split("/")[-1]
    cmd: list[str] = ["python", str(train_py), "--config-name", name]
    cmd.extend(build_hydra_overrides(cfg))
    return cmd
