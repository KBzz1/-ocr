FROM nvidia/cuda:12.6.3-devel-ubuntu24.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        python3 \
        python3-dev \
        python3-pip \
        libgomp1 \
        libgl1 \
        libglib2.0-0 \
        ninja-build \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.docker.txt /app/requirements.docker.txt
RUN python -m pip install --upgrade --ignore-installed pip --retries 10 --timeout 120 \
    && python -m pip install paddlepaddle-gpu==3.2.1 --retries 10 --timeout 120 \
        -i https://www.paddlepaddle.org.cn/packages/stable/cu126/ \
        --extra-index-url https://pypi.org/simple
RUN python -m pip install -r /app/requirements.docker.txt --retries 10 --timeout 120
RUN CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=89 -DCMAKE_EXE_LINKER_FLAGS=-Wl,-rpath-link,/usr/local/cuda/compat" \
    CUDAToolkit_ROOT=/usr/local/cuda \
    CUDA_HOME=/usr/local/cuda \
    CUDACXX=/usr/local/cuda/bin/nvcc \
    FORCE_CMAKE=1 \
    python -m pip install --no-binary llama-cpp-python llama-cpp-python==0.3.22 --retries 10 --timeout 120

COPY app/backend /app/app/backend
COPY app/config/default.yaml /app/app/config/default.yaml
COPY app/config/schemas /app/app/config/schemas
COPY app/frontend/dist /app/app/frontend/dist

RUN mkdir -p /app/data /app/exports /app/logs /app/models

EXPOSE 8081

CMD ["python", "-m", "app.backend.main"]
