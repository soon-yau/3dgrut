# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

LogFn = Callable[[str], None]


@dataclass
class SfMBackendInfo:
    id: str
    display: str
    available: bool
    requires_gpu: bool
    install_hint: str | None = None


class SfMBackend(Protocol):
    id: str
    display_name: str
    requires_gpu: bool

    def is_available(self) -> bool: ...

    def run(self, workspace: Path, params: dict, log: LogFn) -> None:
        """workspace contains images/ and will receive database.db, sparse/0/."""
        ...


def _which(name: str) -> bool:
    from shutil import which

    return which(name) is not None
