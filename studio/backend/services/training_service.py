# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
from pathlib import Path
from typing import Callable

from studio.backend.core.config import settings
from studio.backend.models.training_config import TrainingLaunchConfig
from studio.backend.services.config_service import train_command_hydra, write_run_config_yaml
from studio.backend.services.sfm_service import parse_training_log_line


async def run_training_subprocess(
    cfg: TrainingLaunchConfig,
    run_dir: Path,
    on_line: Callable[[str], None],
    on_metric: Callable[[dict], None],
) -> int:
    """Run train.py; stream stdout lines. Returns process return code."""
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "train.log"
    metrics_path = run_dir / "metrics.jsonl"
    write_run_config_yaml(run_dir, cfg)
    cmd = train_command_hydra(cfg)
    on_line(" ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(settings.repo_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=None,
    )
    assert proc.stdout is not None
    with log_path.open("w", encoding="utf-8") as logf:
        async for raw in proc.stdout:
            line = raw.decode(errors="replace")
            logf.write(line)
            logf.flush()
            on_line(line.rstrip())
            metric = parse_training_log_line(line)
            if metric:
                on_metric(metric)
                with metrics_path.open("a", encoding="utf-8") as mf:
                    mf.write(json.dumps(metric) + "\n")
    return await proc.wait()
