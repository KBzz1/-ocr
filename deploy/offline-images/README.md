# deploy/offline-images

正式离线镜像缓存目录，用于保存本地启动和离线打包需要的 Docker image tar。

- `paddleocr-vlm-server.tar`：固定 digest 的 PaddleOCR-VL vLLM server 镜像。

该目录只放离线部署资源，不放临时验证脚本、样本图片、OCR 输出或运行日志。
