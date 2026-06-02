# GPU Docker 部署说明

## 当前策略

OCR/文档解析和后端服务统一打包为 Docker 镜像交付。开发和医院现场均通过本地 `paddleocr-vlm-server` 常驻服务调用 OCR；医院现场部署不依赖开发机 conda 环境，统一走 Docker 容器。

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

后端默认通过 `paddleocr-vlm-server` 常驻服务调用 PaddleOCR-VL。该服务使用官方 `paddleocr-genai-vllm-server` 镜像、vLLM backend 和挂载的 `models/ppstructure/PaddleOCR-VL-1.6/` 模型目录。任务只通过 `DocumentParsingPort` 提交多页图片并保存 `document_result.json`。

5060 8GB 显存下启用 GPU 阶段队列：OCR 阶段和 LLM 字段抽取阶段串行执行，不允许同时抢占显存。OCR 成功而 LLM 失败时，重试复用已保存的 `document_result.json`，只重跑字段抽取。

服务化 OCR 当前验证组合：`paddlepaddle-gpu==3.2.1`、`paddleocr==3.5.0`、`paddlex==3.5.2`、`PaddleOCR-VL-1.6-0.9B`、官方 vLLM server 镜像离线 tar digest `sha256:1cee5e7e26e666bcd80d2a9741c450438bf507268cbfb14e0e0d33b8d5259621`。离线镜像 tar 固定放在 `deploy/offline-images/paddleocr-vlm-server.tar`。该组合已在 RTX 4070 Laptop 8GB 上流畅运行，目标 RTX 5060 8GB 按同显存级别保守参数部署。

## 当前已验证的问题

在开发机 WSL2 环境中，CUDA 版 `llama-cpp-python==0.3.22` 可识别 RTX 4060 并将 Qwen2.5-7B 的 29/29 层 offload 到 GPU。该 wheel 自带的 `libggml-cpu.so` 在当前 CPU 上会触发 AVX-512 `Illegal instruction`，需要使用同版本 generic CPU wheel 中的 `libggml-cpu.so*` 替换，或在 Docker 镜像内源码构建兼容 CPU 指令集的 CUDA 版 llama.cpp。

Docker 化时必须把该兼容性处理固化到镜像构建步骤中，不能依赖人工进入容器替换库文件。Windows Docker 镜像不得从 `requirements.docker.txt` 安装 PyPI 默认的 CPU wheel；需使用 CUDA devel 基础镜像，在镜像内以 `GGML_CUDA=on` 源码编译 `llama-cpp-python==0.3.22`。构建时需显式提供 `CMAKE_CUDA_ARCHITECTURES=89`，并通过 `/usr/local/cuda/compat` 的 `rpath-link` 解决 `libcuda.so.1` 链接。运行时必须由 compose 暴露 `gpus: all`，否则 CUDA 版 `llama_cpp` 会因没有宿主机 driver 注入而无法加载。

2026-05-29 Windows Docker LLM 根因定位：OCR 已成功进入 `field_extraction` 后，显存释放且后端 Python 进程 CPU/RSS 很高；容器内 `llama_cpp==0.3.22` 只带 `libggml-cpu.so`，`ldd libllama.so` 无 CUDA/cuBLAS 依赖，说明结构化抽取实际使用 CPU-only wheel。修复后验证镜像内 `llama_cpp/lib` 必须包含 `libggml-cuda.so`，且 `docker run --rm --gpus all manzufei-ocr:0.1.0 ldd .../llama_cpp/lib/libllama.so` 能看到 `libggml-cuda.so`、`libcudart.so.12`、`libcublas.so.12`、`libcuda.so.1`。

2026-05-29 完整流程收敛：Windows 部署包完整跑通需要同时满足两点。第一，`app/config/local.yaml` 中 `llm_max_tokens` 使用 4096，复核 prompt 限制短 `comment`，避免字段复核 JSON 被 1024 tokens 截断。第二，字段抽取失败后的重试复用已成功写入的 `document_result.json`，只重跑 LLM 字段抽取，避免再次进入 OCR 540 秒长尾超时。

## 离线包

离线包由 `scripts/deploy/package_offline_docker_bundle.sh` 生成，包含 Docker 镜像 tar、`docker-compose.yml`、Windows 启停脚本、配置占位和模型目录。目标 Windows 电脑上先运行 `00_import_image.bat` 导入镜像，再运行 `01_start.bat` 启动工作站。

正式现场验收使用 `docs/部署/离线验收记录.md`，记录目标 Windows 电脑环境、镜像导入、启动、GPU/OCR/LLM 依赖核验、业务闭环和日志留存。验收过程使用脱敏测试图片，不默认收集病历原图、完整 OCR 原文或模型完整输出。

打包脚本会重新构建前端和 Docker 镜像，并将 `app/config/local.docker.yaml` 复制为部署包内的 `app/config/local.yaml`。如果 OCR/GPU 行为和 WSL 开发环境不一致，优先比较 `backend-events.jsonl` 中的服务 URL、推理参数、容器内 Python 包版本、镜像创建时间和实际挂载的 Windows 部署目录，避免直接假设是参数问题。

不压缩 zip 的现场同步流程可直接覆盖部署目录中的 `images/manzufei-ocr.tar`、`docker-compose.yml`、`app/config/local.yaml` 和 Windows 启停脚本。同步后必须运行 `02_stop.bat`、`00_import_image.bat`、`01_start.bat`，确保 Docker Desktop 加载的是最新镜像而不是旧容器。
