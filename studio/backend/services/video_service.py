# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import subprocess
from pathlib import Path
from typing import Callable

import cv2
import numpy as np


def _laplacian_blur_score(bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def extract_frames(
    video_path: Path,
    out_dir: Path,
    fps: float,
    jpeg_quality: int = 95,
    time_start_s: float = 0.0,
    time_end_s: float | None = None,
    scale_divisor: int = 1,
    log: Callable[[str], None] | None = None,
) -> None:
    """Extract frames with ffmpeg; filenames frame_%06d.jpg."""
    out_dir.mkdir(parents=True, exist_ok=True)
    vf = f"fps={fps}"
    if scale_divisor and scale_divisor > 1:
        vf += f",scale=iw/{scale_divisor}:ih/{scale_divisor}"
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(time_start_s),
    ]
    if time_end_s is not None:
        cmd.extend(["-to", str(time_end_s)])
    q = max(2, min(31, int(round(31 - (jpeg_quality / 100.0) * 29))))
    cmd.extend(
        [
            "-i",
            str(video_path),
            "-vf",
            vf,
            "-q:v",
            str(q),
            str(out_dir / "frame_%06d.jpg"),
        ]
    )
    if log:
        log(" ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def score_frames(frames_dir: Path) -> dict[str, float]:
    """Return map stem -> blur score (variance of Laplacian)."""
    scores: dict[str, float] = {}
    for p in sorted(frames_dir.glob("frame_*.jpg")):
        img = cv2.imread(str(p))
        if img is None:
            continue
        scores[p.stem] = _laplacian_blur_score(img)
    return scores


def write_frame_quality_json(frames_dir: Path, scores: dict[str, float]) -> Path:
    path = frames_dir / "frame_quality.json"
    path.write_text(json.dumps(scores, indent=2))
    return path


def filter_frames_by_blur(
    frames_dir: Path,
    scores: dict[str, float],
    min_score: float,
    log: Callable[[str], None] | None = None,
) -> list[str]:
    """Delete frames below threshold; return list of kept stems."""
    kept: list[str] = []
    for stem, sc in scores.items():
        fp = frames_dir / f"{stem}.jpg"
        if not fp.is_file():
            continue
        if sc >= min_score:
            kept.append(stem)
        else:
            fp.unlink()
            if log:
                log(f"removed low-blur {fp.name} score={sc:.2f}")
    return kept
