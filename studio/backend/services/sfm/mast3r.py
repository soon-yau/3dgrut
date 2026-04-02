# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from studio.backend.core.config import settings


class Mast3rBackend:
    id = "mast3r"
    display_name = "MASt3R-SfM"
    requires_gpu = True

    def is_available(self) -> bool:
        if shutil.which("conda") is None:
            return False
        r = subprocess.run(
            ["conda", "info", "--envs"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (r.stdout or "") + (r.stderr or "")
        if settings.mast3r_conda_env not in out:
            return False
        root = settings.mast3r_repo
        if root is None:
            return False
        return (Path(root) / settings.mast3r_demo_script).is_file()

    def run(self, workspace: Path, params: dict, log: Callable[[str], None]) -> None:
        images = workspace / "images"
        out_sparse = workspace / "sparse"
        out_sparse.mkdir(parents=True, exist_ok=True)

        root = settings.mast3r_repo
        script = settings.mast3r_demo_script
        if not root or not (Path(root) / script).is_file():
            raise RuntimeError(
                "MASt3R not configured. Set STUDIO_MAST3R_REPO to a clone of naver/mast3r "
                f"containing {script}, and install deps in conda env {settings.mast3r_conda_env}."
            )

        cmd = [
            "conda",
            "run",
            "-n",
            settings.mast3r_conda_env,
            "--no-capture-output",
            "python",
            str(Path(root) / script),
            "--image_dir",
            str(images),
            "--colmap_output_path",
            str(out_sparse / "0"),
        ]
        # Pass through only string/bool/number extras as --key value (upstream script-dependent)
        for k, v in params.items():
            if k in ("image_dir", "colmap_output_path"):
                continue
            cmd.append(f"--{k}")
            cmd.append(str(v))
        log(" ".join(cmd))
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.stdout:
            log(p.stdout)
        if p.stderr:
            log(p.stderr)
        if p.returncode != 0:
            raise RuntimeError("MASt3R pipeline failed")
