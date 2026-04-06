FROM ghcr.io/nerfstudio-project/nerfstudio:latest

USER root
ENV DEBIAN_FRONTEND=noninteractive

# ----------------------------------------------------
# 1. System dependencies
# (Added CGAL, FLANN, METIS, and LZ4 to permanently shut up COLMAP's CMake)
# ----------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    ninja-build build-essential git git-lfs curl wget \
    libpcre2-dev \
    libsuitesparse-dev libatlas-base-dev libboost-all-dev \
    libgoogle-glog-dev libgflags-dev libfreeimage-dev libglew-dev \
    libceres-dev \
    libsqlite3-dev \
    libcgal-dev \
    libflann-dev \
    libmetis-dev \
    liblz4-dev \
    && rm -rf /var/lib/apt/lists/*

# ----------------------------------------------------
# 2. Modern CMake (Bypass pip entirely)
# ----------------------------------------------------
RUN wget -qO- "https://cmake.org/files/v3.29/cmake-3.29.3-linux-x86_64.tar.gz" | \
    tar --strip-components=1 -xz -C /usr/local

# ----------------------------------------------------
# 3. Build and install GLOMAP
# ----------------------------------------------------
WORKDIR /opt
RUN git clone https://github.com/colmap/glomap.git && \
    cd glomap && \
    mkdir build && cd build && \
    cmake .. -GNinja -DCMAKE_BUILD_TYPE=Release && \
    ninja install && \
    cd / && rm -rf /opt/glomap

# ----------------------------------------------------
# 4. Clone hloc
# ----------------------------------------------------
RUN git clone --recursive https://github.com/cvg/Hierarchical-Localization/ /opt/hloc

# ----------------------------------------------------
# 5. Python stack (as root to write into system site-packages)
# ----------------------------------------------------
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir pycolmap opencv-python-headless kornia && \
    python -m pip install -e /opt/hloc

# ----------------------------------------------------
# 5b. Pre-cache model weights at build time
# ----------------------------------------------------
ENV TORCH_HOME=/opt/model_cache
# NetVLAD .mat checkpoints (hloc stores them at $TORCH_HOME/hub/netvlad/<name>.mat)
RUN mkdir -p /opt/model_cache/hub/netvlad && \
    wget -q -O /opt/model_cache/hub/netvlad/VGG16-NetVLAD-Pitts30K.mat \
        https://cvg-data.inf.ethz.ch/hloc/netvlad/Pitts30K_struct.mat && \
    wget -q -O /opt/model_cache/hub/netvlad/VGG16-NetVLAD-TokyoTM.mat \
        https://cvg-data.inf.ethz.ch/hloc/netvlad/TokyoTM_struct.mat && \
    chmod -R a+rX /opt/model_cache

# ----------------------------------------------------
# 6. Fix permissions and switch to unprivileged user
# ----------------------------------------------------
RUN chown -R 1000:1000 /opt/hloc && \
    mkdir -p /workspace && chown 1000:1000 /workspace
ENV HOME=/workspace
USER 1000
WORKDIR /workspace

CMD ["/bin/bash"]
