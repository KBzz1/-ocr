# app/config/algorithm-modules

外部算法模块配置预留目录。

## 范围

- 图像处理模块位置。
- OCR 和文档解析模块位置。
- LLM 字段抽取模块位置。
- 模块契约版本。

当前不提交具体配置值。模块未配置时，任务处理必须失败并明确报错。

## 本地 OCR 接入

`manzufei_ocr` conda 环境需要安装 PaddleOCR-VL 依赖。当前验证过的组合：

```bash
conda run -n manzufei_ocr python -m pip install paddlepaddle-gpu==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
conda run -n manzufei_ocr python -m pip install "paddleocr[doc-parser]==3.5.0" "paddlex[serving]==3.5.0"
```

Python runner 配置：

```yaml
algorithms:
  enable_local_ocr: true
  local_ocr_python_executable: "/home/kbzz1/miniconda3/envs/manzufei_ocr/bin/python"
  local_ocr_script_path: "./app/backend/services/algorithm_ports/paddleocr_vl_batch_runner.py"
  local_ocr_work_root: "/tmp/manzufei_ocr_ocr_runs"
  local_ocr_max_new_tokens: 1024
  local_ocr_timeout_seconds: 180
  local_ocr_device:
  local_ocr_max_pixels: 501760
```

### PaddleOCR-VL 集成结论

2026-05-23 根因定位：PaddleX 的 VLM 推理默认 `max_new_tokens=8192`，在 RTX 4060 (8GB) 上 KV cache 超出显存容量，导致生成极慢甚至卡死。传入 `max_new_tokens=1024` 后，同一张屏摄病历约 46 秒完成，输出完整。

`local_ocr_max_new_tokens` 默认值 1024，对单页病历足够。如后续重新调参，需用同一组脱敏样本记录耗时、显存峰值、输出字节数和是否存在缺页/幻觉，再更新本说明。

2026-05-25 复发根因定位：手机上传原图 1800x4000，比此前验证样本 1919x1080 大很多。即使限制了 `max_new_tokens`，视觉输入过大仍会让显存接近满载并长时间低利用率。`local_ocr_max_pixels=1003520` 仍存在长尾卡死，当前默认传入 `local_ocr_max_pixels=501760`（28*28*640）作为 8GB 显卡保守上限。

`local_ocr_timeout_seconds` 默认 180。单页 OCR 超过 180 秒视为外部模块异常并进入失败，避免界面长期停在“处理中”。

本机 Python runner 默认不要配置 `local_ocr_device`。不传 `device` 让 `PaddleOCRVL()` 自动选择设备时表现最稳定；显式传入 `gpu:0` 会让同一张图超过 90 秒未返回。

同一图片放在 `/tmp` 工作目录下可正常返回，而放在 `data/ocr_runs` 下出现过 120 秒超时；当前配置将 `local_ocr_work_root` 指向 `/tmp/manzufei_ocr_ocr_runs`。

OCR runner 执行超时或异常时，事件日志记录 `ocr_runner_started`、`ocr_runner_finished`、`ocr_runner_timeout`，包含退出码和 stdout/stderr 尾部。后续整体打包 Docker 时，OCR runner 作为后端进程内的子进程调用，不再单独起 Docker 容器。
