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

后端通过子进程调用 `paddleocr_vl_batch_runner.py`，传入 `--max-new-tokens 1024` 限制 VLM 生成长度。PaddleX 默认 `max_new_tokens=8192`，在 8GB 显存 GPU 上会超出 KV cache 容量导致极慢。

2026-05-23 验证：RTX 4060 上 `max_new_tokens=1024`，单页病历约 46 秒完成，输出完整。

后续打包 Docker 时，OCR runner 作为后端进程内的子进程调用，不需要单独起 OCR 容器。

## 当前已验证的问题

在开发机 WSL2 环境中，CUDA 版 `llama-cpp-python==0.3.22` 可识别 RTX 4060 并将 Qwen2.5-7B 的 29/29 层 offload 到 GPU。该 wheel 自带的 `libggml-cpu.so` 在当前 CPU 上会触发 AVX-512 `Illegal instruction`，需要使用同版本 generic CPU wheel 中的 `libggml-cpu.so*` 替换，或在 Docker 镜像内源码构建兼容 CPU 指令集的 CUDA 版 llama.cpp。

Docker 化时必须把该兼容性处理固化到镜像构建步骤中，不能依赖人工进入容器替换库文件。

## 合并前后分界

本次主分支合并只包含：

- 慢阻肺专病字段抽取代码。
- 本地 LLM 客户端运行库预加载。
- 字段结果归一化和契约校验修正。
- Docker 部署策略文档。

不包含：

- 实际 Dockerfile 或 compose 文件。
- 医院现场离线镜像交付包。
- OCR、图像预处理或 HIS/EMR 接入。
