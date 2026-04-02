# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from studio.backend.services.sfm import BACKENDS
from studio.backend.services.sfm.base import SfMBackendInfo


ALLOWED_CAMERA_MODELS = {"SIMPLE_PINHOLE", "PINHOLE", "OPENCV_FISHEYE"}


def list_backends() -> list[SfMBackendInfo]:
    out: list[SfMBackendInfo] = []
    for bid, b in BACKENDS.items():
        avail = b.is_available()
        hint = None
        if bid == "mast3r" and not avail:
            hint = "Install conda env 3dgrut-mast3r and set STUDIO_MAST3R_REPO to naver/mast3r clone."
        if bid == "colmap_global" and not avail:
            hint = "Install COLMAP 4.0+ with global_mapper, or use COLMAP Incremental."
        out.append(
            SfMBackendInfo(
                id=bid,
                display=b.display_name,
                available=avail,
                requires_gpu=b.requires_gpu,
                install_hint=hint,
            )
        )
    return out


def _find_sparse_model_dir(workspace: Path) -> Path | None:
    sparse = workspace / "sparse"
    if not sparse.is_dir():
        return None
    for sub in sorted(sparse.iterdir()):
        if sub.is_dir() and (
            (sub / "cameras.bin").is_file()
            or (sub / "cameras.txt").is_file()
            or (sub / "images.bin").is_file()
        ):
            return sub
    return None


def _camera_models_from_txt(cameras_txt: Path) -> set[str]:
    models: set[str] = set()
    text = cameras_txt.read_text(errors="ignore")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            models.add(parts[1])
    return models


def _needs_undistort(sparse0: Path) -> bool:
    if (sparse0 / "cameras.txt").is_file():
        models = _camera_models_from_txt(sparse0 / "cameras.txt")
        if not models:
            return False
        return not models.issubset(ALLOWED_CAMERA_MODELS)
    try:
        import pycolmap

        rec = pycolmap.Reconstruction(str(sparse0))
        for cam in rec.cameras.values():
            name = cam.model.name
            if name not in ALLOWED_CAMERA_MODELS:
                return True
    except Exception:
        return False
    return False


def ensure_pinhole_output(workspace: Path, log: Callable[[str], None]) -> None:
    """Run COLMAP image_undistorter if camera models are not supported by 3DGRUT loader."""
    sparse0 = _find_sparse_model_dir(workspace)
    if sparse0 is None:
        raise RuntimeError("No sparse reconstruction found under sparse/")
    if not _needs_undistort(sparse0):
        return
    undist = workspace / "sparse" / "0_undist"
    if undist.exists():
        shutil.rmtree(undist)
    undist.mkdir(parents=True)
    cmd = [
        "colmap",
        "image_undistorter",
        "--image_path",
        str(workspace / "images"),
        "--input_path",
        str(sparse0),
        "--output_path",
        str(undist),
        "--output_type",
        "COLMAP",
    ]
    log(" ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.stdout:
        log(p.stdout)
    if p.stderr:
        log(p.stderr)
    if p.returncode != 0:
        raise RuntimeError("image_undistorter failed")
    # COLMAP writes undist/sparse/0 and undist/images — promote to workspace
    nested_sparse = undist / "sparse"
    if nested_sparse.is_dir():
        backup = workspace / "sparse" / "0_raw"
        if backup.exists():
            shutil.rmtree(backup)
        shutil.move(str(sparse0), str(backup))
        for sub in nested_sparse.iterdir():
            dest = workspace / "sparse" / sub.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.move(str(sub), str(dest))
    undist_images = undist / "images"
    if undist_images.is_dir():
        img_dir = workspace / "images"
        shutil.rmtree(img_dir)
        shutil.move(str(undist_images), str(img_dir))


def run_sfm_backend(
    backend_id: str,
    workspace: Path,
    params: dict,
    log: Callable[[str], None],
) -> None:
    backend = BACKENDS.get(backend_id)
    if backend is None:
        raise ValueError(f"Unknown SfM backend: {backend_id}")
    if not backend.is_available():
        raise RuntimeError(f"Backend {backend_id} is not available on this system")
    (workspace / "images").mkdir(parents=True, exist_ok=True)
    backend.run(workspace, params, log)
    ensure_pinhole_output(workspace, log)
    (workspace / "sfm_backend.txt").write_text(backend_id + "\n")


def parse_training_log_line(line: str) -> dict | None:
    """Best-effort metric extraction from train.py log lines."""
    # e.g. "iteration 1000 loss 0.05" patterns vary; keep flexible
    m = re.search(r"iter(?:ation)?[:\s]+(\d+)", line, re.I)
    if not m:
        return None
    it = int(m.group(1))
    out: dict = {"iteration": it}
    for key, pat in [
        ("loss_total", r"loss[:\s=]+([0-9.eE+-]+)"),
        ("psnr", r"psnr[:\s=]+([0-9.eE+-]+)"),
        ("n_gaussians", r"gaussians?[:\s=]+(\d+)"),
    ]:
        mm = re.search(pat, line, re.I)
        if mm:
            try:
                out[key] = float(mm.group(1)) if key != "n_gaussians" else int(mm.group(1))
            except ValueError:
                pass
    return out if len(out) > 1 else None
