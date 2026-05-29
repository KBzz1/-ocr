# GPU Docker 部署说明

## 当前策略

OCR/文档解析和后端服务统一打包为 Docker 镜像交付。开发阶段使用本地 conda 环境的 Python runner；医院现场部署不依赖开发机 conda 环境，统一走 Docker 容器。

## 医院现场目标

- 使用 Docker 固化 Python、CUDA runtime、PaddleOCR-VL 依赖、llama.cpp Python 绑定和前端构建产物。
- 通过容器挂载本地 `models/`、`data/`、`exports/`、`logs/`，不把模型权重和真实运行数据打进镜像。
- 容器只暴露本地工作站端口，不依赖云 API、CDN、遥测或运行时下载模型。
- 手机仍只通过医生电脑所在本地网络访问采集页。

## 宿主机前置条件

- Windows 电脑已安装支持 WSL2 GPU 的 NVIDIA 驱动。
- Docker Desktop 已启用 WSL2 backend。
- `docker run --gpus all nvidia/cuda:*-runtime-* nvidia-smi` 能看到显卡。
- 本地已预置 Qwen2.5-7B GGUF 分片到 `models/llm/qwen2.5-7b-instruct-gguf/`。

## OCR 接入

后端通过子进程调用 `paddleocr_vl_batch_runner.py`，传入 `--max-new-tokens 1024` 限制 VLM 生成长度，并传入 `--max-pixels 501760` 控制视觉输入尺寸。PaddleX 默认 `max_new_tokens=8192`，在 8GB 显存 GPU 上会超出 KV cache 容量导致极慢。

2026-05-23 验证：RTX 4060 上 `max_new_tokens=1024`，单页病历约 46 秒完成，输出完整。

2026-05-28 Windows Docker 验证：同一参数在 WSL conda 环境正常，Windows Docker 离线包中若 `paddlex` 漂移到 `3.5.2`，会出现加载 PaddleOCR-VL 权重后长时间低 GPU 利用率并最终超时。部署镜像必须锁定 `paddlepaddle-gpu==3.2.1`、`paddleocr==3.5.0`、`paddlex[ocr]==3.5.0`，并在打包后用 `docker run --rm manzufei-ocr:0.1.0 python -m pip show paddlepaddle-gpu paddleocr paddlex` 核对版本。

Docker 部署中，OCR runner 作为后端进程内的子进程调用，不需要单独起 OCR 容器。

## 当前已验证的问题

在开发机 WSL2 环境中，CUDA 版 `llama-cpp-python==0.3.22` 可识别 RTX 4060 并将 Qwen2.5-7B 的 29/29 层 offload 到 GPU。该 wheel 自带的 `libggml-cpu.so` 在当前 CPU 上会触发 AVX-512 `Illegal instruction`，需要使用同版本 generic CPU wheel 中的 `libggml-cpu.so*` 替换，或在 Docker 镜像内源码构建兼容 CPU 指令集的 CUDA 版 llama.cpp。

Docker 化时必须把该兼容性处理固化到镜像构建步骤中，不能依赖人工进入容器替换库文件。Windows Docker 镜像不得从 `requirements.docker.txt` 安装 PyPI 默认的 CPU wheel；需使用 CUDA devel 基础镜像，在镜像内以 `GGML_CUDA=on` 源码编译 `llama-cpp-python==0.3.22`。构建时需显式提供 `CMAKE_CUDA_ARCHITECTURES=89`，并通过 `/usr/local/cuda/compat` 的 `rpath-link` 解决 `libcuda.so.1` 链接。运行时必须由 compose 暴露 `gpus: all`，否则 CUDA 版 `llama_cpp` 会因没有宿主机 driver 注入而无法加载。

2026-05-29 Windows Docker LLM 根因定位：OCR 已成功进入 `field_extraction` 后，显存释放且后端 Python 进程 CPU/RSS 很高；容器内 `llama_cpp==0.3.22` 只带 `libggml-cpu.so`，`ldd libllama.so` 无 CUDA/cuBLAS 依赖，说明结构化抽取实际使用 CPU-only wheel。修复后验证镜像内 `llama_cpp/lib` 必须包含 `libggml-cuda.so`，且 `docker run --rm --gpus all manzufei-ocr:0.1.0 ldd .../llama_cpp/lib/libllama.so` 能看到 `libggml-cuda.so`、`libcudart.so.12`、`libcublas.so.12`、`libcuda.so.1`。

2026-05-29 完整流程收敛：Windows 部署包完整跑通需要同时满足两点。第一，`app/config/local.yaml` 中 `llm_max_tokens` 使用 4096，复核 prompt 限制短 `comment`，避免字段复核 JSON 被 1024 tokens 截断。第二，字段抽取失败后的重试复用已成功写入的 `document_result.json`，只重跑 LLM 字段抽取，避免再次进入 OCR 540 秒长尾超时。

## 离线包

离线包由 `scripts/package_offline_docker_bundle.sh` 生成，包含 Docker 镜像 tar、`docker-compose.yml`、Windows 启停脚本、配置占位和模型目录。目标 Windows 电脑上先运行 `00_import_image.bat` 导入镜像，再运行 `01_start.bat` 启动工作站。

打包脚本会重新构建前端和 Docker 镜像，并将 `app/config/local.docker.yaml` 复制为部署包内的 `app/config/local.yaml`。如果 OCR/GPU 行为和 WSL 开发环境不一致，优先比较 `backend-events.jsonl` 中的 runner 参数、容器内 Python 包版本、镜像创建时间和实际挂载的 Windows 部署目录，避免直接假设是参数问题。

不压缩 zip 的现场同步流程可直接覆盖部署目录中的 `images/manzufei-ocr.tar`、`docker-compose.yml`、`app/config/local.yaml` 和 Windows 启停脚本。同步后必须运行 `02_stop.bat`、`00_import_image.bat`、`01_start.bat`，确保 Docker Desktop 加载的是最新镜像而不是旧容器。
