# 后端 TDD — OCR/文档解析端口与慢阻肺字段结果契约

> 本项目内不得实现真实 OCR、图像处理、裁剪或透视矫正。慢阻肺/呼吸系统入院记录专病字段抽取属于当前主代码范围，具体设计见 `docs/superpowers/specs/2026-05-21-copd-field-extraction-design.md`。

## 端口定义

```ts
type ImageProcessingPort = {
  process(input: { original_path: string; quad_points?: QuadPoints | null }): Promise<ImageProcessingResult>;
};

type DocumentParsingPort = {
  parse(input: { image_paths: string[]; task_id: string }): Promise<DocumentResult>;
};

type FieldExtractionPort = {
  extract(input: { document_result: DocumentResult; schema: FieldSchema }): Promise<FieldResult[]>;
};
```

`FieldResult` 是按 schema 全量返回的字段结果。每个字段保留自动值、证据、抽取状态、字段级复核状态、质量风险标记和 OCR 纠偏审计信息；未抽到字段也应作为空值结果进入审核页。

## 失败契约

- `ImageProcessingPort` 未配置或异常时，任务处理失败，错误码为 `ALGORITHM_MODULE_NOT_CONFIGURED` 或 `ALGORITHM_MODULE_FAILED`。
- `DocumentParsingPort` 未配置、异常或返回空页结果时，任务处理失败。
- 慢阻肺字段抽取未配置、异常、全字段为空、返回 schema 之外字段或返回契约非法字段时，任务处理失败。
- 单字段 evidence 可疑、OCR 疑似错误或复核失败时，字段进入审核页提示人工核验，不直接让整个任务失败。
- 处理流程不得崩溃；不得在无原文证据时生成医学值。
- 慢阻肺字段抽取返回局部字段为空或不确定时，任务不失败而是进入 `review`，单字段风险由前端展示供人工核验。

契约测试可以使用 fixture 或可注入 LLM 客户端模拟字段抽取结果。

## 本地 OCR 适配器

真实 OCR 接入使用本地 Python runner 适配 `DocumentParsingPort`：

- 配置项：`algorithms.enable_local_ocr`、`local_ocr_python_executable`、`local_ocr_script_path`、`local_ocr_work_root`、`local_ocr_max_new_tokens`、`local_ocr_timeout_seconds`、`local_ocr_device`、`local_ocr_max_pixels`。
- 后端只负责复制任务图片到 runner 输入目录、执行 runner、读取 `all_results.md` 并转换为 `DocumentResult`。
- runner 调用外部 `paddleocr.PaddleOCRVL`；本仓库不实现 OCR 模型、图像预处理、裁剪或透视矫正。
- 输出 Markdown 中缺失某页结果时，该页标记 `failed`，整体任务按文档解析部分失败进入 `failed`。
- `local_ocr_max_new_tokens` 默认 1024。PaddleX VLM 推理默认 `max_new_tokens=8192`，在 8GB 显存 GPU 上 KV cache 超出显存容量导致极慢甚至卡死；1024 对单页病历足够完整。2026-05-23 验证：RTX 4060 上约 46 秒完成。
- `local_ocr_max_pixels` 默认 501760（28*28*640），限制 PaddleOCR-VL 视觉输入尺寸。2026-05-25 复发根因：手机上传原图 1800x4000，显著大于此前 1919x1080 验证样本；1003520 仍可能触发 PaddleOCR-VL 显存接近满载且长时间低利用率，501760 作为 8GB 显卡保守默认值。
- `local_ocr_timeout_seconds` 默认 180。OCR 单页超过 180 秒视为外部模块异常并进入 `failed`，避免前端长期停留在“处理中”。
- 默认不配置 `local_ocr_device`，让 `PaddleOCRVL()` 自动选择设备。显式传入 `gpu:0` 会导致同一图片超过 90 秒未返回。
- `local_ocr_work_root` 指向 `/tmp/manzufei_ocr_ocr_runs`，避免 `data/ocr_runs` 下出现过 120 秒超时。
- OCR runner 执行超时或异常时，事件日志记录 `ocr_runner_started`、`ocr_runner_finished`、`ocr_runner_timeout`，包含退出码和 stdout/stderr 尾部。
- 后续整体打包 Docker 时，OCR runner 作为后端进程内的子进程调用，不再单独起 OCR 容器。
