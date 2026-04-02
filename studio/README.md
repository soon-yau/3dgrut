# 3DGRUT Studio

Web UI and API wrapper around [3DGRUT](../README.md): video preprocessing, SfM (COLMAP / global mapper / MASt3R), and training via `train.py`.

## Prerequisites

- Completed upstream install: [install_env.sh](../install_env.sh) (PyTorch, `requirements.txt`, editable `threedgrut`).
- **COLMAP** 4.x recommended (`global_mapper` for the GLOMAP-style backend). **ffmpeg** on `PATH`.
- **Node.js 18+** for the frontend.

## Install

From the repository root:

```bash
chmod +x install_studio.sh
./install_studio.sh 3dgrut WITH_GCC11          # matches upstream conda env name
# Optional deep-learning SfM (separate env; finish MASt3R setup per naver/mast3r README):
./install_studio.sh 3dgrut WITH_GCC11 --with-mast3r
```

## Run

```bash
conda activate 3dgrut
cd /path/to/3dgrut   # repository root
export STUDIO_REPO_ROOT="$PWD"
export STUDIO_DATA_DIR="$PWD/studio_data"   # optional; default ./studio_data
uvicorn studio.backend.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` for the built SPA (served by FastAPI from `studio/frontend/dist`).

Dev frontend (hot reload):

```bash
cd studio/frontend
npm install
npm run dev
# Vite proxies /api and /ws to http://localhost:8000 — run uvicorn separately
```

## Docker

```bash
docker build -f studio/Dockerfile.studio -t 3dgrut-studio .
# Mount data + GPU as needed for your stack
```

## Plan

See [PLAN.md](PLAN.md) for architecture, API, and UI specification.
