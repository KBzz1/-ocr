# deploy/offline-images

正式离线镜像缓存目录，用于保存本地启动和离线打包需要的 Docker image tar。

- `manzufei-ocr.tar`：工作站后端和前端静态资源镜像。
- `qwen-vllm-server.tar`：固定来源的 Qwen Vision vLLM OpenAI-compatible server 镜像，用于同一常驻服务完成 OCR 与固定字段抽取。

该目录只放正式离线部署镜像 tar，不放模型权重、vLLM cache、临时验证脚本、样本图片、OCR 输出、结构化结果或运行日志。
