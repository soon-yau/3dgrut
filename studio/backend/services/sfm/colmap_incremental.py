# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import subprocess
from pathlib import Path
from typing import Callable

from studio.backend.services.sfm.base import _which


class ColmapIncrementalBackend:
    id = "colmap_incremental"
    display_name = "COLMAP Incremental"
    requires_gpu = False

    def is_available(self) -> bool:
        return _which("colmap")

    def run(self, workspace: Path, params: dict, log: Callable[[str], None]) -> None:
        images = workspace / "images"
        db = workspace / "database.db"
        sparse = workspace / "sparse"
        sparse.mkdir(parents=True, exist_ok=True)

        max_feat = int(params.get("max_num_features", 8192))
        matcher = params.get("matcher", "sequential")
        overlap = int(params.get("sequential_overlap", 10))

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

        if matcher == "exhaustive":
            run_cmd(["colmap", "exhaustive_matcher", "--database_path", str(db)])
        else:
            run_cmd(
                [
                    "colmap",
                    "sequential_matcher",
                    "--database_path",
                    str(db),
                    "--SequentialMatching.overlap",
                    str(overlap),
                ]
            )

        run_cmd(
            [
                "colmap",
                "mapper",
                "--database_path",
                str(db),
                "--image_path",
                str(images),
                "--output_path",
                str(sparse),
            ]
        )
