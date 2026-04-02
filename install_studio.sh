#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Single entry: upstream 3DGRUT env + Studio Python deps + optional MASt3R + frontend build.
# Usage:
#   bash install_studio.sh [CONDA_ENV] [WITH_GCC11] [--with-mast3r] [--skip-frontend] [--docker-mode]
#
# COLMAP: install via your OS (apt/brew) or build from source; not built by this script by default.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONDA_ENV="3dgrut"
WITH_GCC11_ARG=""
WITH_MAST3R=false
SKIP_FRONTEND=false
DOCKER_MODE=false

positional=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-mast3r)   WITH_MAST3R=true; shift ;;
    --skip-frontend) SKIP_FRONTEND=true; shift ;;
    --docker-mode)   DOCKER_MODE=true; shift ;;
    --) shift; break ;;
    -*)
      echo "Unknown option: $1"
      exit 1
      ;;
    *)
      positional+=("$1")
      shift
      ;;
  esac
done

if [[ ${#positional[@]} -ge 1 ]]; then
  CONDA_ENV="${positional[0]}"
fi
if [[ ${#positional[@]} -ge 2 && "${positional[1]}" == "WITH_GCC11" ]]; then
  WITH_GCC11_ARG="WITH_GCC11"
fi

echo "=== 3DGRUT Studio install ==="
echo "  CONDA_ENV=$CONDA_ENV"
echo "  WITH_GCC11=$WITH_GCC11_ARG"
echo "  WITH_MAST3R=$WITH_MAST3R"
echo "  SKIP_FRONTEND=$SKIP_FRONTEND"
echo ""

if [[ ! -f "$SCRIPT_DIR/install_env.sh" ]]; then
  echo "ERROR: install_env.sh not found at repo root."
  exit 1
fi

if [[ "$DOCKER_MODE" != true ]]; then
  echo "NOTE: Install COLMAP 4.x and ffmpeg on PATH (apt/brew or build from source). See studio/README.md"
fi

if [[ -n "$WITH_GCC11_ARG" ]]; then
  bash "$SCRIPT_DIR/install_env.sh" "$CONDA_ENV" WITH_GCC11
else
  bash "$SCRIPT_DIR/install_env.sh" "$CONDA_ENV"
fi

eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV"

pip install --no-build-isolation -r "$SCRIPT_DIR/studio/requirements-studio.txt"

if [[ "$WITH_MAST3R" == true ]]; then
  MAST3R_ENV="3dgrut-mast3r"
  if ! conda env list | awk '{print $1}' | grep -qx "$MAST3R_ENV"; then
    conda create -n "$MAST3R_ENV" python=3.11 -y
  fi
  echo "MASt3R: clone https://github.com/naver/mast3r and install into env $MAST3R_ENV per upstream README."
fi

if [[ "$SKIP_FRONTEND" != true ]]; then
  if command -v npm &>/dev/null; then
    (cd "$SCRIPT_DIR/studio/frontend" && npm install && npm run build)
  else
    echo "WARN: npm not found; skipping frontend build."
  fi
fi

echo ""
echo "Done. conda activate $CONDA_ENV"
echo "Run: uvicorn studio.backend.main:app --reload --host 0.0.0.0 --port 8000"
