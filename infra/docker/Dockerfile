FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

# -- system deps ---------------------------------------------------------------
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    python3.10 python3.10-dev python3-pip \
    git curl wget build-essential cmake \
    ninja-build pkg-config libssl-dev \
    libffi-dev libblas-dev liblapack-dev \
    screen tmux htop nvtop \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 \
    && update-alternatives --install /usr/bin/python  python  /usr/bin/python3.10 1 \
    && update-alternatives --install /usr/bin/pip     pip     /usr/bin/pip3       1

# -- python base deps ----------------------------------------------------------
RUN pip install --upgrade pip setuptools wheel

# PyTorch with CUDA 12.1 (Punica requires 2.1.x)
RUN pip install torch==2.1.2 torchvision==0.16.2 \
    --index-url https://download.pytorch.org/whl/cu121

# -- ezkl ---------------------------------------------------------------------
# Default keeps CPU-capable package; override at build-time for GPU-capable wheel path.
ARG EZKL_PYPI_PACKAGE=ezkl
LABEL aa.ezkl_pypi_package="${EZKL_PYPI_PACKAGE}"
RUN pip install "${EZKL_PYPI_PACKAGE}" onnx onnxruntime

# -- punica --------------------------------------------------------------------
# Install Punica from source -- required for custom SGMV CUDA kernels
# Cloned from fork; at runtime, volume-mounted for live editing.
# TORCH_CUDA_ARCH_LIST: T4 (7.5) lacks bf16 intrinsics that Punica needs.
# Compile for 8.0 (A100) only. Use --a100 flag for SGMV kernel runs.
ENV TORCH_CUDA_ARCH_LIST="8.0"
RUN pip install ninja "numpy<2"
WORKDIR /opt
RUN git clone https://github.com/9401adarsh/punica.git \
    && cd punica && git checkout 591b59899f0a20760821785d06b331c8a2e5cb86 \
    && git submodule sync && git submodule update --init
WORKDIR /opt/punica
RUN pip install -v --no-build-isolation -e ".[dev]"

# -- zkLoRA --------------------------------------------------------------------
# Cloned from fork; at runtime, volume-mounted for live editing.
WORKDIR /opt
RUN git clone https://github.com/9401adarsh/zkLoRA.git \
    && cd zkLoRA && git checkout cfdf3179f1ee3954b3fd4cc78f6d82060d57a347
WORKDIR /opt/zkLoRA
# No setup.py/pyproject.toml -- added to PYTHONPATH instead

# -- general ML + dev deps -----------------------------------------------------
RUN pip install \
    transformers==4.36.0 \
    accelerate \
    peft \
    datasets \
    "numpy<2" pandas scipy \
    matplotlib seaborn \
    jupyter jupyterlab \
    ipywidgets \
    tqdm rich \
    fastapi uvicorn \
    aiofiles \
    pytest pytest-asyncio

# -- workspace -----------------------------------------------------------------
WORKDIR /workspace
ENV PYTHONPATH=/workspace:/workspace/src:/workspace/zklora/src:/opt/punica:/opt/zkLoRA/src:/opt/zkLoRA

# expose jupyter
EXPOSE 8888

CMD ["/bin/bash"]