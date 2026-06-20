# AGENTS.md

## 作用

本文件管辖 `deploy/` 目录，是 Windows 离线 Docker 部署入口的长期规则。仓库边界在根级 `CLAUDE.md`，文档总入口在 `docs/AGENTS.md`。本文件只描述进入 `deploy/` 工作时才需要的独有约束；通用规则不重复。

## 子目录职责

- `windows/`：Windows 离线部署包的用户可见层。最终用户在目标电脑运行 `00_import_image.bat`（导入镜像）、`01_start.bat`（启动）、`02_stop.bat`（停止）、`03_logs.bat`（看日志）。`README_DEPLOY.txt` 是给最终用户看的，**不要**把它跟本目录 agent 文件合并或改造为面向用户的入口。
- `offline-images/`：正式离线 Docker 镜像 tar 缓存。固定 digest 的 `qwen-vllm-server.tar` 与 `manzufei-ocr.tar` 同时被本地启动和离线打包复用。**只放**正式离线部署资源；不放临时验证脚本、样本图片、OCR 输出、运行日志。

## 打包与镜像约束

- 离线包必须**不包含** AGENTS.md、CLAUDE.md、`.git`、开发文档、tests、frontend 源码、`node_modules`、运行时缓存数据；详见 `deploy/windows/README_DEPLOY.txt:33-34`。
- 正式镜像必须**固定 digest**：`qwen-vllm-server`（基于 `vllm/vllm-openai` 加载 `Qwen3.5-4B-AWQ-4bit`）与 `manzufei-ocr` 镜像的离线 tar 必须由 QA 在交付前锚定到具体 digest 并通过 `OFFLINE_IMAGE_DIR` 路径使用；不要在没改 PRD/共享契约前随便换 Qwen vLLM 镜像版本。
- 默认后端镜像不再为 `llama.cpp/GGUF` 编译 CUDA wheel，也不依赖 `paddleocr` / `paddlex` 容器；OCR 与固定字段抽取都由本地 `qwen-vision-vllm-server` 统一提供。
- 现场不压缩 zip 的覆盖同步只能改 `images/manzufei-ocr.tar`、`docker-compose.yml`、`app/config/local.yaml` 和 Windows 启停脚本；同步后必须按 `02_stop.bat` → `00_import_image.bat` → `01_start.bat` 顺序走一遍，避免 Docker Desktop 加载旧容器（见 `docs/部署/GPU-Docker部署.md:47`）。
- `data/`、`exports/`、`logs/` 是运行产物位置，`models/` 是模型权重目录，**不要**在打包脚本里硬编码本机路径或把它们打进镜像。
- 验收环境与 GPU 行为不一致时，优先比较 `logs/backend-events.jsonl`、服务 URL、容器内 Python 包版本、镜像创建时间、实际挂载的部署目录，不要直接假设是参数问题（见 `docs/部署/GPU-Docker部署.md:45`）。

## 打包脚本入口

真正的打包入口在 `scripts/deploy/package_offline_docker_bundle.sh`。`deploy/windows/` 只放最终用户要复制的 bat/说明文件，不要把打包脚本逻辑搬进 bat 脚本里。

## 现场排障

- `deploy/windows/00_import_image.bat` 和 `deploy/windows/01_start.bat` 会把诊断写入 `deploy_debug_logs/import_*.log` 和 `deploy_debug_logs/start_*.log`。
- 启动、Docker 或 GPU 检测失败时，把整目录 `deploy_debug_logs/` 发回调试（详见 `deploy/windows/README_DEPLOY.txt:20-25`）。
- 现场验收必跑项、GPU/OCR/LLM 依赖核验、故障定位方向以 `docs/部署/离线验收记录.md` 为准（特别是「GPU 和依赖核验」「OCR 常驻服务专项验收」「故障记录」三节）。

## 环境前提

目标 Windows 电脑必须满足：Docker Desktop 已装且运行、WSL2 已启用、GPU OCR/LLM 还需要 NVIDIA 驱动和 Docker GPU 支持；`docker run --gpus all ... nvidia-smi` 能看到显卡。完整列表见 `deploy/windows/README_DEPLOY.txt:1-7` 和 `docs/部署/GPU-Docker部署.md:15-19`。

## 子目录 agent 文件

`windows/` 和 `offline-images/` 已各自有面向用户/读者的说明文件（`windows/README_DEPLOY.txt`、`offline-images/README.md`），**不要**再为它们新增更深的 `CLAUDE.md` / `AGENTS.md`。

## 验收与隐私

- 现场验收使用脱敏测试图片；不默认收集病历原图、完整 OCR 原文、模型完整输出、患者身份信息（见 `docs/部署/离线验收记录.md:5-7`）。
- 验收结论只允许填 `通过` / `未通过` / `未执行`（见 `docs/部署/离线验收记录.md:22-26`）。
