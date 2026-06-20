FROM nvidia/cuda:12.6.3-devel-ubuntu24.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

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
    && python -m pip install -r /app/requirements.docker.txt --retries 10 --timeout 120

COPY app/backend /app/app/backend
COPY app/config/default.yaml /app/app/config/default.yaml
COPY app/config/schemas /app/app/config/schemas
COPY app/frontend/dist /app/app/frontend/dist

RUN mkdir -p /app/data /app/exports /app/logs /app/models

EXPOSE 8081

CMD ["python", "-m", "app.backend.main"]
