# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_repo_root() -> Path:
    env = os.environ.get("STUDIO_REPO_ROOT")
    if env:
        return Path(env).resolve()
    # studio/backend/core/config.py -> studio -> repo root
    return Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STUDIO_", extra="ignore")

    repo_root: Path = _default_repo_root()
    data_dir: Path = Path("studio_data")
    mast3r_conda_env: str = "3dgrut-mast3r"
    mast3r_repo: Path | None = None  # e.g. /opt/mast3r if set
    mast3r_demo_script: str = "demo_glomap.py"

    @property
    def projects_root(self) -> Path:
        p = self.data_dir if self.data_dir.is_absolute() else self.repo_root / self.data_dir
        return p.resolve()


settings = Settings()
