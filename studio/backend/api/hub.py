# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class WsHub:
    """Project-scoped WebSocket fan-out."""

    def __init__(self) -> None:
        self._clients: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, project_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients[project_id].add(ws)

    async def disconnect(self, project_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._clients[project_id].discard(ws)

    async def broadcast(self, project_id: str, message: dict[str, Any]) -> None:
        data = json.dumps(message)
        async with self._lock:
            clients = list(self._clients.get(project_id, ()))
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        async with self._lock:
            for ws in dead:
                self._clients[project_id].discard(ws)


hub = WsHub()
