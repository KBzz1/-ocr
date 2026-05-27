FROM python:3.12-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.docker.txt /app/requirements.docker.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install paddlepaddle-gpu==3.2.1 \
        -i https://www.paddlepaddle.org.cn/packages/stable/cu126/ \
        --extra-index-url https://pypi.org/simple \
    && python -m pip install -r /app/requirements.docker.txt

COPY app/backend /app/app/backend
COPY app/config/default.yaml /app/app/config/default.yaml
COPY app/config/schemas /app/app/config/schemas
COPY app/frontend/dist /app/app/frontend/dist

RUN mkdir -p /app/data /app/exports /app/logs /app/models

EXPOSE 8081

CMD ["python", "-m", "app.backend.main"]
