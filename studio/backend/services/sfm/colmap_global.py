# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import subprocess
from pathlib import Path
from typing import Callable

from studio.backend.services.sfm.base import _which


class ColmapGlobalBackend:
    id = "colmap_global"
    display_name = "COLMAP Global (GLOMAP)"
    requires_gpu = False

    def is_available(self) -> bool:
        if not _which("colmap"):
            return False
        p = subprocess.run(["colmap", "help"], capture_output=True, text=True)
        return "global_mapper" in (p.stdout or "") + (p.stderr or "")

    def run(self, workspace: Path, params: dict, log: Callable[[str], None]) -> None:
        images = workspace / "images"
        db = workspace / "database.db"
        sparse = workspace / "sparse"
        sparse.mkdir(parents=True, exist_ok=True)
        max_feat = int(params.get("max_num_features", 8192))

        def run_cmd(args: list[str]) -> None:
            log(" ".join(args))
            p = subprocess.run(args, cwd=str(workspace), capture_output=True, text=True)
            if p.stdout:
                log(p.stdout)
            if p.stderr:
                log(p.stderr)
            if p.returncode != 0:
                raise RuntimeError(f"colmap failed: {' '.join(args)}")

        run_cmd(
            [
                "colmap",
                "feature_extractor",
                "--database_path",
                str(db),
                "--image_path",
                str(images),
                "--ImageReader.single_camera",
                "0",
                "--SiftExtraction.max_num_features",
                str(max_feat),
            ]
        )
        run_cmd(["colmap", "exhaustive_matcher", "--database_path", str(db)])

        # COLMAP 4.x global mapper (GLOMAP integration)
        try:
            run_cmd(
                [
                    "colmap",
                    "global_mapper",
                    "--database_path",
                    str(db),
                    "--image_path",
                    str(images),
                    "--output_path",
                    str(sparse),
                ]
            )
        except RuntimeError as e:
            raise RuntimeError(
                "global_mapper failed. Install COLMAP 4.0+ with global mapper support."
            ) from e
