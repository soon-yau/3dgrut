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

### What the image is meant to include

The [Dockerfile.studio](Dockerfile.studio) is **not** a thin Studio-only layer. It is intended to produce an **all-in-one** runtime that can run **SfM (COLMAP in the base image) and full 3DGRUT / 3DGS training** (`train.py`, native tracers, Hydra configs), plus the Studio API and static UI:

| Layer | Source in the image |
|--------|---------------------|
| COLMAP CLI | `FROM colmap/colmap:latest` |
| ffmpeg, git, Node (UI build) | `apt-get` in Dockerfile |
| PyTorch (CUDA), `requirements.txt`, editable `threedgrut` + compiled extensions | [install_env.sh](../install_env.sh) via [install_studio.sh](../install_studio.sh) |
| Studio FastAPI + deps | `studio/requirements-studio.txt` |
| Frontend | `npm run build` in `studio/frontend` |

**Important caveats**

- The Dockerfile currently runs `install_studio.sh ... || true`, so a **failed** conda/native build may still yield an image that **looks** built but cannot train. After `docker build`, verify with an interactive GPU run (see below).
- **GPU training** requires running the container with NVIDIA Container Toolkit (`--gpus all` or equivalent) and a **host driver** compatible with the CUDA/PyTorch version installed by `install_env.sh` (see the main repo README).
- **MASt3R-SfM** is not fully baked in; it needs a separate conda env and clone (see [PLAN.md](PLAN.md) / install script flags).
- For reproducible CI builds, consider a **CUDA-devel base** that matches the repo’s documented CUDA line, or build on a machine that mirrors your training hosts.

### Build and smoke-test locally

```bash
# From repository root (large build; needs network)
docker build -f studio/Dockerfile.studio -t 3dgrut-studio .

# Optional: confirm training stack inside the image (needs NVIDIA runtime on host)
docker run --rm -it --gpus all \
  -e STUDIO_REPO_ROOT=/workspace \
  -v "$PWD/studio_data:/data/studio_projects" \
  3dgrut-studio \
  conda run -n 3dgrut python -c "import torch; print('cuda', torch.cuda.is_available()); import threedgrut"

docker run --rm -it --gpus all -p 8000:8000 \
  -e STUDIO_REPO_ROOT=/workspace \
  -e STUDIO_DATA_DIR=/data/studio_projects \
  -v "$PWD/studio_data:/data/studio_projects" \
  3dgrut-studio
```

Open `http://localhost:8000` after the server starts.

### Push the image to a cloud registry

Replace `YOUR_REGISTRY` / `YOUR_IMAGE` / `TAG` with your names (example: `docker.io/janedoe/3dgrut-studio`, `v1`).

**1. Docker Hub**

```bash
docker login
docker tag 3dgrut-studio:latest YOUR_DOCKERHUB_USER/3dgrut-studio:TAG
docker push YOUR_DOCKERHUB_USER/3dgrut-studio:TAG
```

**2. Amazon ECR**

```bash
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012
REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY"
aws ecr create-repository --repository-name 3dgrut-studio --region "$AWS_REGION" 2>/dev/null || true

docker tag 3dgrut-studio:latest "${REGISTRY}/3dgrut-studio:TAG"
docker push "${REGISTRY}/3dgrut-studio:TAG"
```

**3. Google Artifact Registry**

```bash
GCP_REGION=us-central1
GCP_PROJECT=my-project
REGISTRY="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/docker"

gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev"
gcloud artifacts repositories create docker --repository-format=docker --location="$GCP_REGION" 2>/dev/null || true

docker tag 3dgrut-studio:latest "${REGISTRY}/3dgrut-studio:TAG"
docker push "${REGISTRY}/3dgrut-studio:TAG"
```

**4. Azure Container Registry**

```bash
ACR_NAME=myregistry
REGISTRY="${ACR_NAME}.azurecr.io"

az acr login --name "$ACR_NAME"
docker tag 3dgrut-studio:latest "${REGISTRY}/3dgrut-studio:TAG"
docker push "${REGISTRY}/3dgrut-studio:TAG"
```

**5. Run from cloud (typical pattern)**

On any GPU VM or Kubernetes pod, use the same image URI you pushed, mount persistent volumes for `STUDIO_DATA_DIR` and datasets, and pass `--gpus all` (Docker) or the platform’s GPU resource limits (GKE/EKS/AKS).

## Plan

See [PLAN.md](PLAN.md) for architecture, API, and UI specification.
