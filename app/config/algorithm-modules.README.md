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

当前支持通过 `app/config/local.yaml` 开启本机 Python OCR runner：

```yaml
algorithms:
  enable_local_ocr: true
  local_ocr_python_executable: "/home/kbzz1/miniconda3/envs/manzufei_ocr/bin/python"
  local_ocr_script_path: "./app/backend/services/algorithm_ports/paddleocr_vl_batch_runner.py"
  local_ocr_timeout_seconds: 1800
  local_ocr_device: "gpu:0"
  local_ocr_max_new_tokens: 1024
  local_ocr_max_pixels: 200000
```

该 runner 只调用已安装的 `paddleocr.PaddleOCRVL`，把任务图片目录识别为 Markdown，再由后端适配为 `DocumentResult`。Docker 镜像交付暂不作为默认运行链路。
