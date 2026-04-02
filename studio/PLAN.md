# 3DGRUT Studio — Detailed Implementation Plan

A web-based pipeline wrapper for 3DGRUT that takes a user from raw video to a trained 3DGS scene, exposing every tunable parameter in a structured, visual, beginner-friendly yet expert-ready interface.

---

## 1. Goals & Principles

| Goal | Design consequence |
|------|-------------------|
| End-to-end pipeline in one UI | Five-stage wizard: Upload → Preprocess → SfM → Configure → Train |
| Expose ALL parameters | Tiered progressive disclosure (Simple / Advanced / Expert panels) |
| Prevent bad configurations | Live validation, range enforcement, mutual-exclusion guards, tooltips |
| Make experimentation fast | Preset system, experiment history, side-by-side metric comparison |
| Show what is happening | Live charts, point-cloud preview, training metrics, log streaming |
| Stay non-invasive | No changes to existing `threedgrut/` code; subprocess + YAML generation only |
| Choice of SfM quality | Three interchangeable backends: COLMAP incremental, COLMAP global (GLOMAP), MASt3R-SfM |

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Browser (React SPA)                         │
│  Pipeline Wizard ─► Config Panels ─► Training Dashboard ─► Viewer  │
└────────────────────────────┬────────────────────────────────────────┘
              REST / WebSocket│
┌────────────────────────────▼────────────────────────────────────────┐
│                       FastAPI Backend                               │
│  /api/projects  /api/preprocess  /api/sfm  /api/training  /api/ws   │
└───┬──────────────┬──────────────┬──────────────────────────────────┘
    │              │              │
 ffmpeg        sfm_service    train.py (subprocess)
 frames        (3 backends)   Hydra YAML written per run
 extraction    → sparse/0/
               + images/
```

All pipeline stages run as **managed subprocesses**. The backend streams
`stdout`/`stderr` over WebSocket to the frontend in real time. Training
metrics are parsed from the log stream and forwarded as structured JSON events.
No GPU code is modified; the backend only generates config YAMLs and invokes
the existing entry points.

### SfM flow detail

```
                ┌──────────────────────────────────────────────────────┐
                │               sfm_service.py                         │
                │                                                      │
  images/ ─────►  ColmapIncrementalBackend  ─────────────────────────► normalize()
                │  (colmap feature_extractor                           │
                │   colmap exhaustive/sequential_matcher               │
                │   colmap mapper)                                     │
                │                                                      │
         ──────►  ColmapGlobalBackend  ──────────────────────────────► normalize()
                │  (colmap feature_extractor                           │
                │   colmap exhaustive_matcher                          │
                │   colmap global_mapper)                              │
                │                                                      │
         ──────►  Mast3rBackend  ─────────────────────────────────────► normalize()
                │  (conda run -n 3dgrut-mast3r                        │
                │   python demo_glomap.py --colmap_output_path)        │
                │                                                      │
                │  normalize(): ensure PINHOLE model, run              │
                │  image_undistorter if needed, verify sparse/0/       │
                └──────────────────────────────────────────────────────┘
                              │
                              ▼
                   sparse/0/{cameras,images,points3D}.{bin|txt}
                   images/
                              │
                              ▼
                       train.py  dataset.type=colmap
```

All three backends converge on the same **output contract** required by
[`threedgrut/datasets/dataset_colmap.py`](../threedgrut/datasets/dataset_colmap.py):
- `sparse/0/cameras.{bin,txt}` with camera model in `{PINHOLE, SIMPLE_PINHOLE, OPENCV_FISHEYE}`
- `sparse/0/images.{bin,txt}` and `sparse/0/points3D.{bin,txt}`
- Image files under `images/`

---

## 3. Project Data Model

Each project is a directory on disk and a row in SQLite.

```
projects/
  <project_id>/
    video/
      original.<ext>           # uploaded video
    frames/
      frame_0001.jpg           # extracted frames
      frame_quality.json       # per-frame blur scores
    sfm/
      images/                  # symlinks or copies of selected frames
      sparse/0/                # SfM output (cameras.bin, images.bin, points3D.bin)
      cameras.json             # human-readable export for UI
      sfm_backend.txt          # which backend was used (for reproducibility)
    runs/
      <run_id>/
        config.yaml            # generated Hydra config
        train.log              # full stdout
        metrics.jsonl          # one JSON object per logged iteration
        checkpoints/
        ply/
```

SQLite schema (simplified):

```sql
CREATE TABLE projects (
  id TEXT PRIMARY KEY,
  name TEXT,
  status TEXT,          -- created | preprocessing | sfm | training | done | error
  video_path TEXT,
  sfm_path TEXT,        -- path to sfm/ directory once SfM is complete
  sfm_backend TEXT,     -- colmap_incremental | colmap_global | mast3r
  created_at DATETIME
);

CREATE TABLE runs (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id),
  config_json TEXT,     -- full config snapshot (for reproduction)
  status TEXT,          -- queued | running | done | failed | cancelled
  metrics_path TEXT,
  started_at DATETIME,
  finished_at DATETIME
);
```

---

## 4. Backend Structure

```
studio/backend/
├── main.py                     # FastAPI app, CORS, lifespan handler
├── core/
│   ├── config.py               # App-level settings (paths, ports, GPU, conda envs)
│   └── database.py             # SQLite with aiosqlite
├── models/
│   ├── project.py              # Pydantic project/run schemas (API I/O)
│   └── training_config.py      # Full training config as Pydantic model tree
├── services/
│   ├── video_service.py        # ffmpeg: extract frames, detect blur, resize
│   ├── sfm_service.py          # SfM strategy dispatcher + normalizer
│   ├── sfm/
│   │   ├── __init__.py
│   │   ├── base.py             # SfMBackend Protocol + SfMResult dataclass
│   │   ├── colmap_incremental.py   # colmap feature_extractor / matcher / mapper
│   │   ├── colmap_global.py        # colmap feature_extractor / matcher / global_mapper
│   │   └── mast3r.py               # conda run -n 3dgrut-mast3r + weight download check
│   ├── training_service.py     # train.py subprocess, log/metric parsing
│   └── config_service.py       # Build + validate Hydra YAML from Pydantic
└── api/
    ├── routes/
    │   ├── projects.py         # CRUD + project listing
    │   ├── preprocess.py       # POST /start, GET /status, GET /frames
    │   ├── sfm.py              # POST /start, GET /status, GET /point_cloud, GET /backends
    │   ├── training.py         # POST /start, POST /stop, GET /runs
    │   └── export.py           # POST /ply, POST /usd
    └── websocket.py            # WS /ws/{project_id} — unified event stream
```

### 4.1 WebSocket Event Types

```jsonc
// Log line from any subprocess
{ "type": "log",    "stage": "sfm|training|preprocess",
  "backend": "colmap_incremental|colmap_global|mast3r|null", "line": "..." }

// Parsed training metric
{ "type": "metric", "iteration": 1500, "loss_total": 0.042,
  "loss_l1": 0.034, "loss_ssim": 0.008, "psnr": 24.1,
  "n_gaussians": 347821, "iter_per_sec": 12.4 }

// Stage status change
{ "type": "status", "stage": "sfm|training|preprocess",
  "status": "running|done|error", "backend": "colmap_incremental|colmap_global|mast3r|null" }

// Validation image (base64 PNG thumbnail)
{ "type": "image",  "iteration": 7000, "view_idx": 0, "data": "iVBORw..." }

// Gaussian cloud snapshot (sparse JSON for live point cloud)
{ "type": "pointcloud", "iteration": 7000, "positions": [[x,y,z],...] }
```

### 4.2 `sfm_service.py` — SfM Strategy Pattern

```python
# studio/backend/services/sfm/base.py
class SfMBackend(Protocol):
    name: str
    display_name: str
    available: bool           # False if binary/env not installed
    requires_gpu: bool

    def run(self, images_dir: Path, output_dir: Path,
            params: dict, log_callback: Callable) -> None: ...

# Three concrete implementations:
class ColmapIncrementalBackend:   # colmap mapper
class ColmapGlobalBackend:        # colmap global_mapper  (COLMAP 4.0 built-in GLOMAP)
class Mast3rBackend:              # conda run -n 3dgrut-mast3r

BACKENDS: dict[str, SfMBackend] = {
    "colmap_incremental": ColmapIncrementalBackend(),
    "colmap_global":      ColmapGlobalBackend(),
    "mast3r":             Mast3rBackend(),
}

def ensure_pinhole_output(sfm_dir: Path) -> None:
    """
    Read sparse/0/cameras.{bin,txt}. If any camera model is not in
    {PINHOLE, SIMPLE_PINHOLE, OPENCV_FISHEYE}, run:
      colmap image_undistorter --input_path sfm_dir/sparse/0
                               --output_path sfm_dir/sparse/0_undist
                               --image_path sfm_dir/images
    then rename output to sparse/0/.
    This is called after every backend run before the result is marked done.
    """
```

### 4.3 `training_config.py` — Full Pydantic Schema

The Pydantic model mirrors every Hydra YAML field and generates the final YAML.
Organized into nested models matching the config hierarchy:

```python
class ProgressiveTrainingConfig(BaseModel):
    feature_type: Literal["sh"] = "sh"
    init_n_features: int = 0          # initial SH degree
    max_n_features: int = 3           # maximum SH degree
    increase_frequency: int = 1000
    increase_step: int = 1

class BackgroundConfig(BaseModel):
    name: Literal["skip-background", "background-color"] = "background-color"
    color: Literal["black", "white", "random"] = "black"

class ModelConfig(BaseModel):
    density_activation: Literal["sigmoid", "exp"] = "sigmoid"
    scale_activation: Literal["exp"] = "exp"
    default_density: float = 0.1
    default_scale_factor: float = 1.0
    optimize_density: bool = True
    optimize_features_albedo: bool = True
    optimize_features_specular: bool = True
    optimize_position: bool = True
    optimize_rotation: bool = True
    optimize_scale: bool = True
    bvh_update_frequency: int = 1
    progressive_training: ProgressiveTrainingConfig = ProgressiveTrainingConfig()
    background: BackgroundConfig = BackgroundConfig()

class PerParamLR(BaseModel):
    positions: float = 0.00016
    density: float = 0.05
    features_albedo: float = 0.0025
    features_specular: float = 0.000125  # albedo / 20
    rotation: float = 0.001
    scale: float = 0.005

class OptimizerConfig(BaseModel):
    type: Literal["adam", "selective_adam"] = "adam"
    eps: float = 1e-15
    params: PerParamLR = PerParamLR()

class SchedulerConfig(BaseModel):
    lr_init: float = 0.00016
    lr_final: float = 0.0000016
    max_steps: int = 30000

class LossConfig(BaseModel):
    use_l1: bool = True;     lambda_l1: float = 0.8
    use_l2: bool = False;    lambda_l2: float = 1.0
    use_ssim: bool = True;   lambda_ssim: float = 0.2
    use_opacity: bool = False; lambda_opacity: float = 0.0
    use_scale: bool = False;   lambda_scale: float = 0.0

class DensifyConfig(BaseModel):
    params: Literal["positions","positions_gradient_norm","features_albedo"] = "positions"
    frequency: int = 300
    start_iteration: int = 500
    end_iteration: int = 15000
    clone_grad_threshold: float = 0.0002
    split_grad_threshold: float = 0.0002
    relative_size_threshold: float = 0.01

class PruneConfig(BaseModel):
    frequency: int = 100
    start_iteration: int = 500
    end_iteration: int = 15000
    density_threshold: float = 0.005

class ResetDensityConfig(BaseModel):
    frequency: int = 3000
    new_max_density: float = 0.01

class GSStrategyConfig(BaseModel):
    method: Literal["GSStrategy"] = "GSStrategy"
    densify: DensifyConfig = DensifyConfig()
    prune: PruneConfig = PruneConfig()
    reset_density: ResetDensityConfig = ResetDensityConfig()

class MCMCRelocateConfig(BaseModel):
    start_iteration: int = 500
    end_iteration: int = 25000
    frequency: int = 100

class MCMCPerturbConfig(BaseModel):
    start_iteration: int = 0
    end_iteration: int = 27500
    frequency: int = 1
    noise_lr: float = 500000.0

class MCMCAddConfig(BaseModel):
    start_iteration: int = 500
    end_iteration: int = 25000
    frequency: int = 100
    max_n_gaussians: int = 1_000_000

class MCMCStrategyConfig(BaseModel):
    method: Literal["MCMCStrategy"] = "MCMCStrategy"
    binom_n_max: int = 51
    opacity_threshold: float = 0.005
    relocate: MCMCRelocateConfig = MCMCRelocateConfig()
    perturb: MCMCPerturbConfig = MCMCPerturbConfig()
    add: MCMCAddConfig = MCMCAddConfig()

class SplatConfig(BaseModel):  # 3DGUT only
    rect_bounding: bool = True
    tight_opacity_bounding: bool = True
    tile_based_culling: bool = True
    n_rolling_shutter_iterations: int = 5
    ut_alpha: float = 1.0
    ut_beta: float = 2.0
    ut_kappa: float = 0.0
    ut_in_image_margin_factor: float = 0.1
    ut_require_all_sigma_points_valid: bool = False
    k_buffer_size: int = 0
    global_z_order: bool = True
    fine_grained_load_balancing: bool = False

class RenderConfig(BaseModel):
    method: Literal["3dgrt", "3dgut"] = "3dgrt"
    pipeline_type: str = "reference"
    particle_kernel_degree: int = 4        # 3DGUT uses 2
    particle_kernel_density_clamping: bool = True
    particle_kernel_min_response: float = 0.0113
    particle_kernel_min_alpha: float = 1/255
    particle_kernel_max_alpha: float = 0.99
    particle_radiance_sph_degree: int = 3
    min_transmittance: float = 0.001       # 3DGUT: 0.0001
    max_consecutive_bvh_update: int = 15
    enable_normals: bool = False
    enable_hitcounts: bool = True
    splat: Optional[SplatConfig] = None    # only when method == "3dgut"

class PostProcessingConfig(BaseModel):
    method: Optional[Literal["ppisp"]] = None
    use_controller: bool = True
    n_distillation_steps: int = 5000

class InitColmapConfig(BaseModel):
    method: Literal["colmap"] = "colmap"
    observation_scale_factor: float = 0.01
    use_observation_points: bool = True

class InitRandomConfig(BaseModel):
    method: Literal["random"] = "random"
    num_gaussians: int = 100_000
    xyz_max: float = 1.5
    xyz_min: float = -1.5

class DatasetConfig(BaseModel):
    type: Literal["colmap","nerf","scannetpp","ncore"] = "colmap"
    downsample_factor: int = 1
    test_split_interval: int = 8
    load_exif: bool = True

class CheckpointConfig(BaseModel):
    iterations: list[int] = [7000, 30000]

class ExportPLYConfig(BaseModel):
    enabled: bool = False
    path: str = ""

class ExportUSDConfig(BaseModel):
    enabled: bool = False
    path: str = ""
    format: Literal["standard", "nurec"] = "standard"
    half_precision: bool = False
    export_cameras: bool = True
    export_background: bool = True
    sorting_mode_hint: str = "cameraDistance"

class TrainingConfig(BaseModel):
    # ── top-level ──────────────────────────────────────────
    path: str                              # dataset path
    out_dir: str = "./runs"
    experiment_name: str = ""
    n_iterations: int = 30000
    seed_initialization: int = 42
    val_frequency: int = 5000
    num_workers: int = 24
    log_frequency: int = 1
    use_wandb: bool = False
    wandb_project: str = "3dgrt"
    test_last: bool = True
    validate_first: bool = False
    compute_extra_metrics: bool = True
    # ── sub-configs ────────────────────────────────────────
    render_method: Literal["3dgrt","3dgut"] = "3dgrt"
    strategy_method: Literal["GSStrategy","MCMCStrategy"] = "GSStrategy"
    model: ModelConfig = ModelConfig()
    optimizer: OptimizerConfig = OptimizerConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    loss: LossConfig = LossConfig()
    strategy: Union[GSStrategyConfig, MCMCStrategyConfig] = GSStrategyConfig()
    render: RenderConfig = RenderConfig()
    post_processing: PostProcessingConfig = PostProcessingConfig()
    initialization: Union[InitColmapConfig, InitRandomConfig] = InitColmapConfig()
    dataset: DatasetConfig = DatasetConfig()
    checkpoint: CheckpointConfig = CheckpointConfig()
    export_ply: ExportPLYConfig = ExportPLYConfig()
    export_usd: ExportUSDConfig = ExportUSDConfig()
```

### 4.4 `config_service.py` — YAML Generation

Converts a `TrainingConfig` Pydantic instance into a valid Hydra YAML.
Selects the correct `apps/` preset as base and writes only the diff, or writes
a self-contained flat override file with `# @package _global_`.

```python
def build_yaml(config: TrainingConfig, project_dir: Path) -> Path:
    """Write config.yaml into project_dir/runs/<run_id>/ and return path."""
```

---

## 5. Installation

### 5.1 Dependency philosophy (no duplication)

**Rule:** `studio/requirements-studio.txt` lists **only** packages not already present in the root [`requirements.txt`](../requirements.txt) or installed by [`install_env.sh`](../install_env.sh). Packages such as `opencv-python`, `omegaconf`, `hydra-core`, `pillow`, `rich`, and `tqdm` are provided by the upstream install and must **not** be listed again.

| Layer | Managed by | Packages |
|-------|-----------|---------|
| PyTorch / CUDA / numpy / kaolin / submodules / `threedgrut` | upstream `install_env.sh` + `requirements.txt` | pytorch, numpy<2, opencv-python, omegaconf, hydra-core, viser, polyscope, … |
| Studio Python extras | `studio/requirements-studio.txt` | fastapi, uvicorn[standard], pydantic>=2, aiosqlite, aiofiles, python-multipart, ffmpeg-python, pycolmap |
| COLMAP 4.x binary | system (apt / Docker) | colmap (build from source for GPU+ONNX) |
| ffmpeg binary | system (apt / Docker) | ffmpeg |
| MASt3R-SfM | separate conda env `3dgrut-mast3r` | pytorch, mast3r, dust3r, asmk, model weights |
| Node / npm | system (apt / Docker) | nodejs, npm (for frontend build) |

### 5.2 `install_studio.sh` — the single entry point (repo root)

```
Usage:
  bash install_studio.sh [CONDA_ENV] [WITH_GCC11] [OPTIONS]

Options:
  --skip-colmap         Skip COLMAP system build (user provides their own)
  --with-mast3r         Install MASt3R-SfM in a separate conda env
  --skip-frontend       Skip npm ci / frontend build
  --docker-mode         Assumes root; skips sudo checks

Default CONDA_ENV = 3dgrut  (same as install_env.sh)
```

Execution order:

```
1. Pre-flight checks (repo root, gcc version)
2. [Unless --skip-colmap]  Build COLMAP 4.x from source with CUDA + ONNX
3.  Install system packages: ffmpeg, nodejs, npm
4.  bash install_env.sh "$CONDA_ENV" "$GCC_ARG"       ← upstream unchanged
5.  conda activate "$CONDA_ENV"
6.  pip install --no-build-isolation -r studio/requirements-studio.txt
7. [If --with-mast3r]  Create 3dgrut-mast3r env + install MASt3R + download weights
8. [Unless --skip-frontend]  cd studio/frontend && npm ci && npm run build
9.  Print "Setup complete. Run: uvicorn studio.backend.main:app"
```

### 5.3 COLMAP 4.x build block

COLMAP 4.0+ ships GLOMAP's global mapper built-in as `colmap global_mapper` and
`colmap automatic_reconstructor --mapper GLOBAL`. The separate `colmap/glomap`
repo is deprecated; **one build covers both COLMAP incremental and GLOMAP global**.

GPU feature extraction (ALIKED, LightGlue) requires ONNX runtime.

```bash
# install_studio.sh — COLMAP build block
if [ "$SKIP_COLMAP" = false ]; then
  apt-get install -y cmake ninja-build libboost-all-dev libeigen3-dev      \
    libsuitesparse-dev libceres-dev libflann-dev libmetis-dev              \
    libsqlite3-dev qt6-base-dev libgl1-mesa-dev libglib2.0-dev libgomp1

  # ONNX runtime (for ALIKED / LightGlue GPU matchers)
  ONNXRT_VER=1.17.3
  wget https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRT_VER}/\
onnxruntime-linux-x64-gpu-${ONNXRT_VER}.tgz
  tar xf onnxruntime-linux-x64-gpu-${ONNXRT_VER}.tgz -C /opt/

  git clone --depth 1 --branch 4.0.0 https://github.com/colmap/colmap /opt/colmap_src
  pushd /opt/colmap_src
  mkdir build && cd build
  cmake .. -GNinja \
    -DCMAKE_CUDA_ARCHITECTURES=all-major \
    -DONNX_ENABLED=ON \
    -DONNXRUNTIME_INCLUDE_DIRS=/opt/onnxruntime-linux-x64-gpu-${ONNXRT_VER}/include \
    -DONNXRUNTIME_LIBRARIES=/opt/onnxruntime-linux-x64-gpu-${ONNXRT_VER}/lib/libonnxruntime.so
  ninja install
  popd
fi
```

### 5.4 MASt3R-SfM block (optional)

MASt3R-SfM runs in a **separate conda environment** (`3dgrut-mast3r`) to avoid
Torch/NumPy version conflicts with the main `3dgrut` env.
The Studio backend invokes it via `conda run -n 3dgrut-mast3r python ...`.

```bash
# install_studio.sh — MASt3R block
if [ "$WITH_MAST3R" = true ]; then
  conda create -n 3dgrut-mast3r python=3.11 -y
  conda run -n 3dgrut-mast3r conda install pytorch torchvision \
    pytorch-cuda=12.1 -c pytorch -c nvidia -y

  git clone --recursive https://github.com/naver/mast3r /opt/mast3r
  conda run -n 3dgrut-mast3r pip install -r /opt/mast3r/requirements.txt
  conda run -n 3dgrut-mast3r pip install -r /opt/mast3r/dust3r/requirements.txt

  # asmk retrieval library
  conda run -n 3dgrut-mast3r pip install cython
  git clone https://github.com/jenicek/asmk /opt/asmk
  (cd /opt/asmk/cython && conda run -n 3dgrut-mast3r cythonize *.pyx)
  conda run -n 3dgrut-mast3r bash -c "cd /opt/asmk && pip install ."

  # Download pretrained weights (~1.5 GB, one-time)
  conda run -n 3dgrut-mast3r python /opt/mast3r/download_weights.py
fi
```

### 5.5 Docker integration

The existing [`Dockerfile`](../Dockerfile) uses `ubuntu:24.04` + Miniconda and
calls `install_env.sh`. Extend it to call `install_studio.sh` instead.
For the full GPU + MASt3R image use the official `colmap/colmap` base
(already ships COLMAP 4.x with CUDA):

```dockerfile
# Dockerfile.studio (new file in studio/)
FROM colmap/colmap:latest        # COLMAP 4.x + CUDA pre-installed

ARG CUDA_VERSION=12.8.1
ARG WITH_MAST3R=false

# System extras (ffmpeg, nodejs, npm)
RUN apt-get update && apt-get install -y ffmpeg nodejs npm \
    gcc-11 g++-11 libgl1-mesa-dev libglib2.0-0 wget git && \
    rm -rf /var/lib/apt/lists/*

# Conda
RUN curl -o ~/miniconda.sh \
    https://repo.anaconda.com/miniconda/Miniconda3-py311_25.1.1-2-Linux-x86_64.sh && \
    bash ~/miniconda.sh -b -p /opt/conda && rm ~/miniconda.sh
ENV PATH=/opt/conda/bin:$PATH

WORKDIR /workspace
COPY . .

RUN CUDA_VERSION=$CUDA_VERSION \
    WITH_MAST3R=$WITH_MAST3R \
    bash ./install_studio.sh 3dgrut WITH_GCC11 --skip-colmap --docker-mode

RUN echo "conda activate 3dgrut" >> ~/.bashrc
EXPOSE 8000
CMD ["conda", "run", "-n", "3dgrut", \
     "uvicorn", "studio.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build variants:
```bash
# Minimal (COLMAP + GPU features, no MASt3R)
docker build -f studio/Dockerfile.studio -t 3dgrut-studio .

# Full (+ MASt3R, ~8 GB extra)
docker build -f studio/Dockerfile.studio --build-arg WITH_MAST3R=true \
  -t 3dgrut-studio-full .
```

### 5.6 `studio/requirements-studio.txt`

```
# Studio-only Python packages.
# DO NOT add packages already in ../requirements.txt or installed by install_env.sh.
# opencv-python, omegaconf, hydra-core, pillow, rich, tqdm etc. come from upstream.

fastapi>=0.111.0
uvicorn[standard]>=0.29.0
pydantic>=2.7.0
aiosqlite>=0.20.0
aiofiles>=23.2.1
python-multipart>=0.0.9
ffmpeg-python>=0.2.0
pycolmap>=0.6.0          # for reading COLMAP sparse models (points3D.bin etc.)
```

---

## 6. Frontend Structure

```
studio/frontend/
├── package.json         # React 18, Vite, TypeScript, Tailwind, shadcn/ui
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.ts
├── index.html
└── src/
    ├── main.tsx
    ├── App.tsx                   # Router (React Router v6)
    ├── types/
    │   ├── project.ts
    │   ├── config.ts             # Mirrors backend Pydantic models
    │   ├── sfm.ts                # SfM backend descriptors + params
    │   └── events.ts             # WebSocket event union types
    ├── api/
    │   ├── client.ts             # axios instance + error handling
    │   ├── projects.ts
    │   ├── preprocess.ts
    │   ├── sfm.ts                # GET /backends, POST /start, GET /status, GET /pointcloud
    │   └── training.ts
    ├── stores/
    │   ├── pipelineStore.ts      # Zustand: active step, step statuses
    │   ├── sfmStore.ts           # Zustand: selected backend, params, availability
    │   ├── configStore.ts        # Zustand: full TrainingConfig form state
    │   └── trainingStore.ts      # Zustand: metrics stream, run state
    ├── hooks/
    │   ├── useWebSocket.ts       # WS connection, event dispatch
    │   ├── useProject.ts         # TanStack Query project CRUD
    │   ├── useSfmBackends.ts     # Query /api/sfm/backends for availability
    │   └── usePresets.ts         # Load / apply / diff presets
    └── components/
        ├── layout/
        │   ├── AppShell.tsx
        │   ├── Sidebar.tsx
        │   └── TopBar.tsx
        ├── pipeline/
        │   ├── PipelineWizard.tsx
        │   ├── StepIndicator.tsx
        │   └── steps/
        │       ├── Step1_Upload.tsx
        │       ├── Step2_Preprocess.tsx
        │       ├── Step3_SfM.tsx         # backend selector + params + 3D viewer
        │       ├── Step4_Configure.tsx
        │       └── Step5_Monitor.tsx
        ├── sfm/
        │   ├── SfMBackendCard.tsx        # reusable backend selection card
        │   ├── ColmapIncrementalParams.tsx
        │   ├── ColmapGlobalParams.tsx
        │   └── Mast3rParams.tsx
        ├── config/
        │   ├── PresetSelector.tsx
        │   ├── AlgorithmCard.tsx
        │   ├── StrategyCard.tsx
        │   ├── CoreSettings.tsx
        │   ├── ModelParams.tsx
        │   ├── OptimizerParams.tsx
        │   ├── LossParams.tsx
        │   ├── StrategyParams/
        │   │   ├── index.tsx
        │   │   ├── GSStrategyForm.tsx
        │   │   └── MCMCStrategyForm.tsx
        │   ├── RenderParams/
        │   │   ├── index.tsx
        │   │   ├── GRTForm.tsx
        │   │   └── GUTForm.tsx
        │   ├── PostProcessingParams.tsx
        │   └── InitializationParams.tsx
        ├── monitoring/
        │   ├── TrainingDashboard.tsx
        │   ├── LossChart.tsx
        │   ├── PSNRChart.tsx
        │   ├── GaussianCountChart.tsx
        │   ├── SpeedPanel.tsx
        │   ├── MetricsTable.tsx
        │   └── LogViewer.tsx
        ├── viewer/
        │   ├── PointCloudViewer.tsx
        │   ├── CameraFrustums.tsx
        │   └── ImageSlider.tsx
        └── ui/
            ├── ParamRow.tsx
            ├── SectionCard.tsx
            ├── NumberField.tsx
            ├── SliderField.tsx
            ├── SelectField.tsx
            ├── ToggleField.tsx
            ├── DiffBadge.tsx
            └── Tooltip.tsx
```

---

## 7. Page & Component Design

### 7.1 Application Shell

```
┌─ Sidebar (240px) ──────────────┐ ┌─ Main Panel ────────────────────────────────────────┐
│  3DGRUT Studio                 │ │  <active view>                                      │
│                                │ │                                                     │
│  ▼ Projects                    │ │                                                     │
│    ● garden (running)          │ │                                                     │
│    ○ bicycle (done)            │ │                                                     │
│    ○ room (done)               │ │                                                     │
│  + New Project                 │ │                                                     │
│                                │ │                                                     │
│  ▼ Recent Runs                 │ │                                                     │
│    run_abc  PSNR 27.4          │ │                                                     │
│    run_def  PSNR 25.1          │ │                                                     │
└────────────────────────────────┘ └─────────────────────────────────────────────────────┘
```

### 7.2 Step Indicator

Horizontal bar at the top of the wizard with five numbered nodes:

```
  ①Upload ──── ②Preprocess ──── ③SfM ──── ④Configure ──── ⑤Train
  (done)         (done)       (active)     (pending)       (pending)
```
Color states: gray (pending) / blue (active) / green (done) / red (error).
Each node is clickable to revisit a completed step.

---

### 7.3 Step 1 — Upload

```
┌─────────────────────────────────────────────────────────────────────┐
│  PROJECT NAME  [ garden                                    ]        │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                                                             │   │
│  │              Drop video here, or click to browse            │   │
│  │              (.mp4 .mov .avi .mkv)                          │   │
│  │                                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  OR  Use existing image folder  [ Browse ]                          │
│      (skip preprocessing — provide COLMAP-ready images)            │
│                                                                     │
│                                        [ Next → ]                   │
└─────────────────────────────────────────────────────────────────────┘
```

If an existing `sfm/` directory (with `sparse/0/` + `images/`) is provided,
steps 2 and 3 can be skipped entirely.

---

### 7.4 Step 2 — Video Preprocessing

Left panel: controls. Right panel: live frame strip preview.

```
┌─ Controls ─────────────────────────────┐  ┌─ Frame Preview ──────────────────────────┐
│                                        │  │                                          │
│  Extraction FPS   ────●──── 2 fps      │  │  ▸ 142 frames estimated                 │
│  (1 – 30)                              │  │                                          │
│                                        │  │  [ f001 ] [ f002 ] [ f003 ] [ f004 ] …  │
│  Time range  [00:00] – [01:11]         │  │  ████     ████     ████     ████         │
│                                        │  │   good     good    blurry   good         │
│  Target resolution                     │  │                                          │
│    ○ Original                          │  │  Blur score threshold ──●────  0.80     │
│    ● Downscale 2x  (will halve W/H)    │  │  (frames below threshold excluded)      │
│    ○ Downscale 4x                      │  │                                          │
│    ○ Custom  W[   ] H[   ]             │  │  ✓ 138 frames selected / 142 total      │
│                                        │  │                                          │
│  JPEG quality   ──────────●── 95       │  └──────────────────────────────────────────┘
│                                        │
│  [ Run Extraction ]                    │
└────────────────────────────────────────┘
```

Blur detection uses the Laplacian variance heuristic via OpenCV.
Threshold slider re-filters instantly (client-side, scores already returned).

---

### 7.5 Step 3 — Structure from Motion

#### Backend selection row (top of step)

Three cards side by side. Availability is queried from `GET /api/sfm/backends`
at page load; unavailable backends are shown greyed with an install hint.

```
┌─ COLMAP Incremental ────────────────┐  ┌─ COLMAP Global (GLOMAP) ────────────┐  ┌─ MASt3R-SfM ────────────────────────┐
│  Classic Sequential SfM             │  │  Global SfM  (COLMAP 4.0+)          │  │  Deep-learning SfM                  │
│                                     │  │                                     │  │                                     │
│  ✓ Battle-tested, predictable       │  │  ✓ Faster for large scenes          │  │  ✓ Works without feature overlap    │
│  ✓ Best docs + community support    │  │  ✓ No sequential order needed       │  │  ✓ Robust for casual/handheld video │
│  ✓ Handles fisheye cameras          │  │  ✓ Single COLMAP 4.x binary         │  │  ✓ GPU-accelerated full pipeline    │
│  ✗ Slow for large frame counts      │  │  ✗ Less robust for noisy captures   │  │  ✗ Separate env + ~1.5 GB weights   │
│                                     │  │                                     │  │  ✗ Slower on first run              │
│  GPU: feature extraction/matching   │  │  GPU: feature extraction/matching   │  │  GPU: full pipeline                 │
│  CPU: mapper + bundle adjustment    │  │  CPU: bundle adjustment             │  │  CPU: not recommended               │
│                                     │  │                                     │  │                                     │
│  requires: COLMAP 4.x               │  │  requires: COLMAP 4.x               │  │  requires: --with-mast3r install    │
│  [ ● SELECT ]                       │  │  [   SELECT ]                       │  │  [   SELECT ]  (greyed if absent)   │
└─────────────────────────────────────┘  └─────────────────────────────────────┘  └─────────────────────────────────────┘
```

When MASt3R is absent, the card shows:
```
  ⚠ MASt3R-SfM not installed.
  Re-run: bash install_studio.sh --with-mast3r
```

#### Shared layout for all backends

Left panel: backend-specific parameter form (see below).
Right panel: 3D viewer + progress panel.

```
┌─ [Backend params] ─────────────────────────┐  ┌─ 3D Preview ──────────────────────┐
│  <see backend-specific panels below>       │  │  (Three.js PointCloud viewer)    │
│                                            │  │                                  │
│                                            │  │  ·  ·· ·   ·                     │
│                                            │  │ ·  scene  ·· ·                  │
│                                            │  │  · ·   ·   ·                    │
│                                            │  │                                  │
│                                            │  │  📷 📷 📷 📷  ← camera frusta   │
│                                            │  │     📷 📷                        │
│                                            │  │                                  │
│                                            │  │  Points:   124,351               │
│                                            │  │  Cameras:  138                   │
│                                            │  │  Mean reproj error: 0.82 px      │
│  [ Run SfM ]                              │  └──────────────────────────────────┘
└────────────────────────────────────────────┘
                                                ┌─ Progress ───────────────────────┐
                                                │  ▶ Feature extraction  ████ done │
                                                │  ▶ Feature matching    ████ done │
                                                │  ▶ Sparse mapping      ████ 73%  │
                                                │  [ Stop ]   [ Re-run ]           │
                                                └──────────────────────────────────┘
```

#### COLMAP Incremental params panel

```
  Feature extractor    [ SIFT ▼ ]   (SIFT | ALIKED-N16Rot | ALIKED-N32)
  Max features/img     [ 8192  ]
  Matcher              [ Sequential ▼ ]   (Sequential | Exhaustive | VocabTree)
  Sequential overlap   [ 10  ]            (only when Sequential)
  Camera model output  [ PINHOLE ▼ ]      (PINHOLE | SIMPLE_PINHOLE | OPENCV_FISHEYE)

  ── Advanced ──────────────────────────────────────────────────────────
  Min inliers per image  [ 15  ]
  Min track length       [ 3   ]
  [✓] Refine focal length   [✓] Refine principal point   [✓] Refine extra params
```

#### COLMAP Global (GLOMAP) params panel

```
  Feature extractor    [ SIFT ▼ ]   (SIFT | ALIKED-N16Rot | ALIKED-N32)
  Max features/img     [ 8192  ]
  Matcher              [ Exhaustive ▼ ]   (Exhaustive | VocabTree)
                       ⓘ Global mapper requires exhaustive matching for best results
  Camera model output  [ PINHOLE ▼ ]

  ── Advanced ──────────────────────────────────────────────────────────
  Min inliers per image  [ 15  ]
  [✓] View graph calibration   ⓘ Estimates intrinsics from two-view geometries
```

#### MASt3R-SfM params panel

```
  Model variant        [ MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric ▼ ]
  Min confidence       [ 1.5  ]   ⓘ Per-point confidence threshold
  Max image pairs      [ 512  ]   ⓘ Limit via retrieval (0 = all pairs)
  Camera model output  [ PINHOLE ] (fixed; MASt3R always exports PINHOLE)

  ── Advanced ──────────────────────────────────────────────────────────
  ASMK retrieval top-k [ 20   ]
  Global alignment iters [ 300 ]
  [✓] Use retrieval-based pair selection
```

After SfM completes, the 3D viewer shows the sparse point cloud and camera
frustums in a navigable Three.js scene. Users can verify coverage before training.
The `sfm_backend.txt` records which backend was used for reproducibility.

---

### 7.6 Step 4 — Training Configuration

Unchanged from original design; organized as a 9-tab panel with a sticky
"Launch Training" footer.

```
┌─ [Algorithm] [Core] [Model] [Optimizer] [Loss] [Strategy] [Render] [PostProc] [Export] ──┐
│  ┌─ Preset bar ──────────────────────────────────────────────────────────────────────┐  │
│  │  [● Quick Preview]  [  Balanced  ]  [  High Quality  ]  [  Custom  ]  [Save…]   │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│  <tab content>                                                                          │
│  [ ◀ Back ]                                            [ ▶ Launch Training ]           │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Tab A — Algorithm

**Card pair 1 — Render Method:** 3DGRT vs 3DGUT (unchanged).

**Card pair 2 — Densification Strategy:** GSStrategy vs MCMCStrategy (unchanged).

#### Tab B — Core Settings

Iterations, validation freq, workers, seed, experiment name, output dir,
checkpoint saves, W&B logging, extra metrics flags (unchanged).

#### Tab C — Model Parameters

Gaussian properties, optimize flags, progressive SH training, background (unchanged).

#### Tab D — Optimizer & Scheduler

Optimizer type, epsilon, per-parameter LR table, position LR decay curve preview (unchanged).

#### Tab E — Loss Function

Toggle + weight sliders for L1/L2/SSIM/opacity/scale with live pie chart (unchanged).

#### Tab F — Densification Strategy

Conditional: GSStrategy (densify/prune/reset with event timeline) or
MCMCStrategy (Gaussian cap, relocate/perturb/add windows) (unchanged).

#### Tab G — Render Parameters

Conditional: 3DGRT (kernel degree, transmittance, BVH) or
3DGUT (culling flags, unscented transform params, k-buffer) (unchanged).

#### Tab H — Post-Processing

PPISP toggle, controller, distillation steps (unchanged).

#### Tab I — Export & Initialization

Initialization method (colmap/random/fused PC/checkpoint), PLY export,
USD export (unchanged).

---

### 7.7 Step 5 — Training Monitor

Four-panel layout: progress bar + speed + stop/pause, loss chart, PSNR chart,
Gaussian count chart, GT vs prediction comparison slider, log viewer (unchanged).

---

## 8. Preset System

Five built-in presets stored as JSON overlays on `TrainingConfig` defaults:

| Preset | Render | Strategy | Iters | Key changes |
|--------|--------|----------|-------|-------------|
| **Quick Preview** | 3DGUT | GSStrategy | 7,000 | `val_frequency=999999`, `densify.end=5000` |
| **Balanced** | 3DGUT | GSStrategy | 30,000 | defaults |
| **High Quality** | 3DGRT | GSStrategy | 30,000 | `particle_kernel_degree=4`, `max_n_features=3` |
| **MCMC Quality** | 3DGRT | MCMCStrategy | 30,000 | MCMC defaults + ppisp=null |
| **Custom** | any | any | any | user-controlled |

---

## 9. Experiment Comparison

A dedicated "Compare Runs" panel in the sidebar allows selecting 2–4 completed runs and shows:

- Side-by-side metric table (PSNR, SSIM, LPIPS, training time, final Gaussian count)
- Overlaid loss curves (different colors per run)
- Configuration diff tree (only fields that differ between runs are shown)
- Side-by-side rendered view comparison (same camera, multiple runs)

---

## 10. Backend API Summary

```
POST   /api/projects                     Create project
GET    /api/projects                     List projects
GET    /api/projects/{id}                Get project
DELETE /api/projects/{id}                Delete project

POST   /api/projects/{id}/upload         Upload video
POST   /api/projects/{id}/preprocess     Start frame extraction
GET    /api/projects/{id}/frames         Get frame list + quality scores

GET    /api/sfm/backends                 List available backends + availability flags
POST   /api/projects/{id}/sfm/start      Start SfM  (body: { backend, params })
GET    /api/projects/{id}/sfm/status     SfM status + stats + backend used
GET    /api/projects/{id}/sfm/pointcloud Sparse PC (JSON {positions, colors})

POST   /api/projects/{id}/runs           Launch training run (body: TrainingConfig)
GET    /api/projects/{id}/runs           List runs
GET    /api/projects/{id}/runs/{rid}     Run status + config + metrics
DELETE /api/projects/{id}/runs/{rid}     Cancel / delete run
GET    /api/projects/{id}/runs/{rid}/metrics  Full JSONL metrics

POST   /api/projects/{id}/runs/{rid}/export/ply
POST   /api/projects/{id}/runs/{rid}/export/usd

WS     /ws/{project_id}                  Live event stream
```

`GET /api/sfm/backends` response example:

```jsonc
[
  { "id": "colmap_incremental", "display": "COLMAP Incremental",
    "available": true,  "requires_gpu": false },
  { "id": "colmap_global",      "display": "COLMAP Global (GLOMAP)",
    "available": true,  "requires_gpu": false },
  { "id": "mast3r",             "display": "MASt3R-SfM",
    "available": false, "requires_gpu": true,
    "install_hint": "Re-run: bash install_studio.sh --with-mast3r" }
]
```

`POST /api/projects/{id}/sfm/start` body:

```jsonc
{
  "backend": "colmap_incremental",
  "params": {
    "feature_extractor": "SIFT",
    "max_num_features": 8192,
    "matcher": "sequential",
    "sequential_overlap": 10,
    "camera_model": "PINHOLE"
  }
}
```

---

## 11. Technology Stack

### Backend

| Package | Source | Purpose |
|---------|--------|---------|
| `fastapi` | `requirements-studio.txt` | REST + WebSocket |
| `uvicorn[standard]` | `requirements-studio.txt` | ASGI server |
| `pydantic>=2` | `requirements-studio.txt` | Config validation / serialization |
| `aiosqlite` | `requirements-studio.txt` | Async SQLite |
| `aiofiles` | `requirements-studio.txt` | Async file I/O |
| `ffmpeg-python` | `requirements-studio.txt` | Video frame extraction |
| `pycolmap` | `requirements-studio.txt` | Read COLMAP sparse models (points3D.bin) |
| `python-multipart` | `requirements-studio.txt` | File upload |
| `opencv-python` | upstream `requirements.txt` | Blur scoring (already installed) |
| `omegaconf` | upstream `requirements.txt` | YAML generation (already installed) |

### Frontend

| Package | Purpose |
|---------|---------|
| `react@18` + `typescript` | Core framework |
| `vite` | Build tool |
| `tailwindcss` | Utility CSS |
| `shadcn/ui` | Accessible component primitives |
| `zustand` | Lightweight global state |
| `@tanstack/react-query` | Server state, caching |
| `recharts` | Loss / metrics charts |
| `@react-three/fiber` + `@react-three/drei` | 3D point cloud viewer |
| `react-dropzone` | Drag-and-drop upload |
| `react-compare-slider` | GT vs prediction image slider |
| `react-router-dom v6` | Routing |
| `zod` | Runtime TypeScript validation |

### System (managed by `install_studio.sh` / Docker)

| Tool | How installed | Purpose |
|------|--------------|---------|
| `colmap` 4.x | Build from source (CUDA + ONNX) or `colmap/colmap` Docker image | All SfM (incremental + global/GLOMAP) |
| `ffmpeg` | `apt-get install ffmpeg` | Video frame extraction binary |
| `nodejs` / `npm` | `apt-get install nodejs npm` | Frontend build |
| MASt3R-SfM | Separate conda env `3dgrut-mast3r` | Deep-learning SfM (optional) |

---

## 12. Implementation Phases

### Phase 1 — Backend Foundation
1. `studio/backend/main.py` — FastAPI app shell, CORS, static serving
2. `studio/backend/core/database.py` — SQLite schema + migrations
3. `studio/backend/models/project.py` — Pydantic project / run models
4. `studio/backend/models/training_config.py` — Full config Pydantic tree
5. `studio/backend/services/config_service.py` — YAML builder
6. `studio/backend/api/routes/projects.py` — CRUD

### Phase 2 — Video Pipeline
7. `studio/backend/services/video_service.py` — ffmpeg + blur scoring
8. `studio/backend/api/routes/preprocess.py`

### Phase 3 — SfM Pipeline
9. `studio/backend/services/sfm/base.py` — Protocol + SfMResult
10. `studio/backend/services/sfm/colmap_incremental.py`
11. `studio/backend/services/sfm/colmap_global.py`
12. `studio/backend/services/sfm/mast3r.py`
13. `studio/backend/services/sfm_service.py` — dispatcher + `ensure_pinhole_output()`
14. `studio/backend/api/routes/sfm.py`

### Phase 4 — Training Pipeline & WebSocket
15. `studio/backend/services/training_service.py` — subprocess, metric parsing
16. `studio/backend/api/websocket.py` — event stream
17. `studio/backend/api/routes/training.py`

### Phase 5 — Installation Scripts
18. `install_studio.sh` — single entry point (COLMAP build + upstream + Studio pip + MASt3R optional + npm)
19. `studio/requirements-studio.txt`
20. `studio/Dockerfile.studio`

### Phase 6 — Frontend Scaffold
21. `studio/frontend/package.json`, `tsconfig.json`, `vite.config.ts`
22. `studio/frontend/src/main.tsx`, `App.tsx`
23. `studio/frontend/src/components/layout/AppShell.tsx`
24. `studio/frontend/src/components/pipeline/StepIndicator.tsx`
25. `studio/frontend/src/stores/` — all Zustand stores (including `sfmStore.ts`)
26. `studio/frontend/src/api/` — all API client modules
27. `studio/frontend/src/types/` — TypeScript types (including `sfm.ts`)

### Phase 7 — Pipeline Steps UI
28. `Step1_Upload.tsx`
29. `Step2_Preprocess.tsx`
30. `Step3_SfM.tsx` — three backend cards + conditional param panels + 3D viewer
31. `Step4_Configure.tsx` — full 9-tab config panel
32. `Step5_Monitor.tsx`

### Phase 8 — SfM Components
33. `SfMBackendCard.tsx`
34. `ColmapIncrementalParams.tsx`
35. `ColmapGlobalParams.tsx`
36. `Mast3rParams.tsx`
37. `useSfmBackends.ts`

### Phase 9 — Config Tabs
38–46. One component per tab: Algorithm, Core, Model, Optimizer, Loss, Strategy (×2),
Render (×2), PostProc, Export

### Phase 10 — Monitoring & Viewer
47. `LossChart.tsx`, `PSNRChart.tsx`, `GaussianCountChart.tsx`
48. `LogViewer.tsx` (virtualized)
49. `PointCloudViewer.tsx` (Three.js)
50. `ImageSlider.tsx` (react-compare-slider)

### Phase 11 — Experiment Management
51. Sidebar run history
52. Compare runs panel
53. Preset save / load

---

## 13. Key Design Decisions

### Why a wizard?
The pipeline is strictly sequential (video → frames → SfM → train), so a
linear wizard with clear step completion states is the most intuitive UX. Steps
can be revisited but not skipped (unless the user provides pre-processed data).

### SfM backend design: output contract not tool coupling
All three backends converge to the same `sparse/0/` + `images/` layout that
[`ColmapDataset`](../threedgrut/datasets/dataset_colmap.py) already expects.
The `ensure_pinhole_output()` normalizer handles any edge cases where a backend
emits a non-supported camera model (e.g. `SIMPLE_RADIAL`) by running
`colmap image_undistorter` transparently. The trainer never knows or cares which
backend was used.

### Why COLMAP 4.x from source?
`apt install colmap` on most distros ships a CPU-only older version without
ALIKED/LightGlue/ONNX and without the integrated global mapper. Building from
source pins the version and enables GPU feature extraction + GLOMAP in one
binary. The `colmap/colmap` Docker image is the zero-effort alternative.

### Why MASt3R in a separate conda env?
MASt3R-SfM has its own Torch/NumPy pins that may conflict with 3DGRUT's
`numpy<2` requirement. Isolating it in `3dgrut-mast3r` lets both coexist
without version negotiation. The Studio backend invokes it via
`conda run -n 3dgrut-mast3r python ...` and treats the output directory as
a black box that feeds into the shared normalizer.

### Why not duplicate opencv/omegaconf in `requirements-studio.txt`?
Both are already installed by the upstream `install_env.sh` + `requirements.txt`
path into the `3dgrut` conda env. Listing them again risks inadvertent upgrades
that break the `numpy<2` pin or the `opencv-python<4.12.0` constraint.

### How are training metrics extracted?
`training_service.py` parses each stdout line of `train.py` with a regex for
the Hydra log format. Structured metric objects are emitted as WebSocket events
and also appended to `metrics.jsonl` for persistence.

### Config YAML generation
`config_service.py` takes a `TrainingConfig` Pydantic instance and:
1. Determines the closest `apps/` preset as a base.
2. Serializes the full config using `omegaconf.OmegaConf.to_yaml`.
3. Writes a `# @package _global_` flat override file.
This ensures the generated YAML is valid Hydra input without needing to compose
individual sub-config files.

---

## 14. File Creation List (new files only)

```
install_studio.sh                               ← single install entry point (repo root)
studio/
├── PLAN.md                                     ← this file
├── README.md
├── requirements-studio.txt                     ← Studio-only Python deps (no upstream dups)
├── Dockerfile.studio                           ← Docker image for Studio + COLMAP 4.x
├── backend/
│   ├── main.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── database.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── project.py
│   │   └── training_config.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── video_service.py
│   │   ├── sfm_service.py          ← dispatcher + ensure_pinhole_output()
│   │   ├── sfm/
│   │   │   ├── __init__.py
│   │   │   ├── base.py             ← SfMBackend Protocol + SfMResult
│   │   │   ├── colmap_incremental.py
│   │   │   ├── colmap_global.py
│   │   │   └── mast3r.py
│   │   ├── training_service.py
│   │   └── config_service.py
│   └── api/
│       ├── __init__.py
│       ├── websocket.py
│       └── routes/
│           ├── __init__.py
│           ├── projects.py
│           ├── preprocess.py
│           ├── sfm.py
│           ├── training.py
│           └── export.py
└── frontend/
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── tailwind.config.ts
    ├── postcss.config.js
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── types/
        │   ├── project.ts
        │   ├── config.ts
        │   ├── sfm.ts              ← SfMBackend descriptors + param types
        │   └── events.ts
        ├── api/
        │   ├── client.ts
        │   ├── projects.ts
        │   ├── preprocess.ts
        │   ├── sfm.ts
        │   └── training.ts
        ├── stores/
        │   ├── pipelineStore.ts
        │   ├── sfmStore.ts         ← selected backend, params, availability
        │   ├── configStore.ts
        │   └── trainingStore.ts
        ├── hooks/
        │   ├── useWebSocket.ts
        │   ├── useProject.ts
        │   ├── useSfmBackends.ts   ← query /api/sfm/backends
        │   └── usePresets.ts
        └── components/
            ├── layout/
            │   ├── AppShell.tsx
            │   ├── Sidebar.tsx
            │   └── TopBar.tsx
            ├── pipeline/
            │   ├── PipelineWizard.tsx
            │   ├── StepIndicator.tsx
            │   └── steps/
            │       ├── Step1_Upload.tsx
            │       ├── Step2_Preprocess.tsx
            │       ├── Step3_SfM.tsx
            │       ├── Step4_Configure.tsx
            │       └── Step5_Monitor.tsx
            ├── sfm/
            │   ├── SfMBackendCard.tsx
            │   ├── ColmapIncrementalParams.tsx
            │   ├── ColmapGlobalParams.tsx
            │   └── Mast3rParams.tsx
            ├── config/
            │   ├── PresetSelector.tsx
            │   ├── AlgorithmCard.tsx
            │   ├── StrategyCard.tsx
            │   ├── CoreSettings.tsx
            │   ├── ModelParams.tsx
            │   ├── OptimizerParams.tsx
            │   ├── LossParams.tsx
            │   ├── StrategyParams/
            │   │   ├── index.tsx
            │   │   ├── GSStrategyForm.tsx
            │   │   └── MCMCStrategyForm.tsx
            │   ├── RenderParams/
            │   │   ├── index.tsx
            │   │   ├── GRTForm.tsx
            │   │   └── GUTForm.tsx
            │   ├── PostProcessingParams.tsx
            │   └── InitializationParams.tsx
            ├── monitoring/
            │   ├── TrainingDashboard.tsx
            │   ├── LossChart.tsx
            │   ├── PSNRChart.tsx
            │   ├── GaussianCountChart.tsx
            │   ├── SpeedPanel.tsx
            │   ├── MetricsTable.tsx
            │   └── LogViewer.tsx
            ├── viewer/
            │   ├── PointCloudViewer.tsx
            │   ├── CameraFrustums.tsx
            │   └── ImageSlider.tsx
            └── ui/
                ├── ParamRow.tsx
                ├── SectionCard.tsx
                ├── NumberField.tsx
                ├── SliderField.tsx
                ├── SelectField.tsx
                ├── ToggleField.tsx
                ├── DiffBadge.tsx
                └── Tooltip.tsx
```

Total: **~70 new files**, zero modifications to existing `threedgrut/` code.
