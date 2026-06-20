# GPU Docker 部署说明

## 当前策略

OCR/文档解析、固定字段抽取和后端服务统一打包为 Docker 镜像交付。开发和医院现场均通过本地 `qwen-vision-vllm-server` 常驻服务调用 Qwen 视觉模型（vLLM OpenAI 兼容 API），同一服务同时承担图片 OCR 与 text-only 固定字段 JSON 抽取。医院现场部署不依赖开发机 conda 环境，统一走 Docker 容器。

## 医院现场目标

- 使用 Docker 固化 Python、CUDA runtime、Qwen vLLM 服务依赖、OpenAI Python SDK 和前端构建产物。
- 通过容器挂载本地 `models/llm/Qwen3.5-4B-AWQ-4bit/`、`data/`、`exports/`、`logs/`，不把模型权重和真实运行数据打进镜像。
- 容器只暴露本地工作站端口，不依赖云 API、CDN、遥测或运行时下载模型。
- 手机仍只通过医生电脑所在本地网络访问采集页。

## 宿主机前置条件

- Windows 电脑已安装支持 WSL2 GPU 的 NVIDIA 驱动。
- Docker Desktop 已启用 WSL2 backend。
- `docker run --gpus all nvidia/cuda:*-runtime-* nvidia-smi` 能看到显卡。
- 本地已预置 `Qwen3.5-4B-AWQ-4bit` 到 `models/llm/Qwen3.5-4B-AWQ-4bit/`（容器内只读挂载到 `/workspace/model/llm/Qwen3.5-4B-AWQ-4bit`）。

## OCR 与固定字段抽取接入

后端默认通过 `qwen-vision-vllm-server` 常驻服务调用 Qwen 视觉模型。该服务使用 `vllm/vllm-openai` 镜像加载 `Qwen3.5-4B-AWQ-4bit`，暴露 OpenAI 兼容的 `/v1/chat/completions` 接口；后端通过 OpenAI Python SDK 调本服务的 `/v1`。任务只通过 `DocumentParsingPort` 提交多页图片、保存 `document_result.json` 与 `evidence_units`，再由 `COPDAdmissionQwenFieldPort` 发起 text-only JSON 抽取。

5060 8GB 显存下启用 GPU 阶段队列：同一任务从 OCR 到固定字段抽取连续持有 `qwen_ocr_and_extraction` 阶段，OCR 与结构化抽取之间不允许其他任务插队，避免一个任务独占 8GB 显存。OCR 成功而抽取失败时，重试复用已保存的 `document_result.json`，只重跑字段抽取（仅持有 `field_extraction` 阶段）。

服务化 Qwen vLLM 当前验证组合：`vllm/vllm-openai` 镜像 + `Qwen3.5-4B-AWQ-4bit` 模型权重 + `--max-model-len 16384 --gpu-memory-utilization 0.85 --max-num-seqs 1 --enable-chunked-prefill --enable-prefix-caching --dtype auto --trust-remote-code`。`max_model_len=30000` 在 8GB 显卡下会撑爆 KV cache，绝不允许作为默认；`max_num_seqs=1` 保证同一常驻模型串行处理请求。模型目录只读挂载到容器内 `/workspace/model/llm/Qwen3.5-4B-AWQ-4bit`，vLLM cache 单独挂载到 `/root/.cache/vllm`（不进仓库）。离线镜像 tar 固定放在 `deploy/offline-images/qwen-vllm-server.tar`，命名由 `QWEN_VLLM_SERVER_LOCAL_TAG` 控制。

## OCR 行为约束

- 允许过滤页眉、页脚、页码、打印时间、医院页眉页脚、医生签名、手签等非病历正文干扰。
- 禁止纠正文书正文、补全、重排、标题字符串替换（如 `品后诊断 → 最后诊断`）、医学推理补写。
- 证据高亮基准是 OCR 模型输出文本，不在图片像素层做版面恢复或 bounding box。

## 离线包

离线包由 `scripts/deploy/package_offline_docker_bundle.sh` 生成，包含 Docker 镜像 tar（`manzufei-ocr.tar` + `qwen-vllm-server.tar`）、`docker-compose.yml`、Windows 启停脚本、配置占位和模型目录。目标 Windows 电脑上先运行 `00_import_image.bat` 导入两个镜像，再运行 `01_start.bat` 启动工作站；`01_start.bat` 会先等 `http://127.0.0.1:8082/v1/models` 健康，再等后端 `/api/system/status` 健康。

正式现场验收使用 `docs/部署/离线验收记录.md`，记录目标 Windows 电脑环境、镜像导入、启动、GPU/OCR/LLM 依赖核验、业务闭环和日志留存。验收过程使用脱敏测试图片，不默认收集病历原图、完整 OCR 原文或模型完整输出。

打包脚本会重新构建前端和 Docker 镜像，并将 `app/config/local.docker.yaml` 复制为部署包内的 `app/config/local.yaml`。如果 OCR/GPU 行为和 WSL 开发环境不一致，优先比较 `backend-events.jsonl` 中的服务 URL、推理参数、容器内 Python 包版本、镜像创建时间和实际挂载的 Windows 部署目录，避免直接假设是参数问题。

不压缩 zip 的现场同步流程可直接覆盖部署目录中的 `images/manzufei-ocr.tar`、`images/qwen-vllm-server.tar`、`docker-compose.yml`、`app/config/local.yaml` 和 Windows 启停脚本。同步后必须运行 `02_stop.bat`、`00_import_image.bat`、`01_start.bat`，确保 Docker Desktop 加载的是最新镜像而不是旧容器。
