# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import aiosqlite

from studio.backend.core.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'created',
  video_path TEXT,
  sfm_path TEXT,
  sfm_backend TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  config_json TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  metrics_path TEXT,
  started_at TEXT,
  finished_at TEXT,
  FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);
"""


async def get_connection() -> aiosqlite.Connection:
    settings.projects_root.mkdir(parents=True, exist_ok=True)
    db_path = settings.projects_root / "studio.sqlite"
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    return conn


async def init_db() -> None:
    db = await get_connection()
    try:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.executescript(SCHEMA)
        await db.commit()
    finally:
        await db.close()
