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
- PaddleOCR-VL 运行栈需锁定已验证组合：`paddlepaddle-gpu==3.2.1`、`paddleocr==3.5.0`、`paddlex==3.5.0`。Docker 离线镜像使用 `paddlex[ocr]==3.5.0`，WSL conda 开发环境使用 `paddlex[serving]==3.5.0`。不得让 Docker 依赖漂移到未验证的 PaddleX 小版本。
- 输出 Markdown 中缺失某页结果时，该页标记 `failed`，整体任务按文档解析部分失败进入 `failed`。
- `local_ocr_max_new_tokens` 默认 1024。PaddleX VLM 推理默认 `max_new_tokens=8192`，在 8GB 显存 GPU 上 KV cache 超出显存容量导致极慢甚至卡死；1024 对单页病历足够完整。2026-05-23 验证：RTX 4060 上约 46 秒完成。
- `local_ocr_max_pixels` 默认 501760（28*28*640），限制 PaddleOCR-VL 视觉输入尺寸。2026-05-25 复发根因：手机上传原图 1800x4000，显著大于此前 1919x1080 验证样本；1003520 仍可能触发 PaddleOCR-VL 显存接近满载且长时间低利用率，501760 作为 8GB 显卡保守默认值。
- 2026-05-28 Windows Docker 复发根因：镜像中 `paddlex==3.5.2` 与 WSL 已验证的 `paddlex==3.5.0` 不一致，导致同一 runner 参数在 Windows Docker 下加载权重后长时间低 GPU 利用率并超时。日志排除旧镜像、旧代码和 CPU-only 配置后，将 Docker 依赖锁回 `paddlex[ocr]==3.5.0`，Windows OCR 验证通过。
- `local_ocr_timeout_seconds` 默认 180，表示单页 OCR 超时预算；多页任务 runner 超时按页数线性放大。OCR 单页超过 180 秒视为外部模块异常并进入 `failed`，避免前端长期停留在“处理中”。
- `local_ocr_work_root` 指向 `/tmp/manzufei_ocr_ocr_runs`，避免 `data/ocr_runs` 下出现过 120 秒超时。
- OCR runner 执行超时或异常时，事件日志记录 `ocr_runner_started`、`ocr_runner_finished`、`ocr_runner_timeout`，包含退出码和 stdout/stderr 尾部。
- 整体 Docker 部署中，OCR runner 作为后端进程内的子进程调用，不再单独起 OCR 容器。

## 本地 LLM 抽取适配器

- Windows Docker 部署必须使用 CUDA 版 `llama-cpp-python==0.3.22`，并通过 `docker-compose.yml` 的 `gpus: all` 暴露宿主机 GPU。
- `requirements.docker.txt` 不得安装默认 `llama-cpp-python` wheel；Dockerfile 必须在 CUDA devel 镜像内以 `GGML_CUDA=on` 源码编译，并固定 `CMAKE_CUDA_ARCHITECTURES=89`。
- 构建 CUDA 版 llama.cpp 时需提供 `/usr/local/cuda/compat` 的 `rpath-link`，否则最后链接工具程序时可能因找不到 `libcuda.so.1` 失败。
- 2026-05-29 Windows Docker 根因：OCR 成功后进入字段抽取，但显存为空、后端 CPU/RSS 很高；容器内 `llama_cpp/lib` 只有 CPU 后端库，`libllama.so` 无 CUDA/cuBLAS 依赖。修复后验证镜像必须包含 `libggml-cuda.so`，并在 `--gpus all` 下可加载 `llama_cpp`。
- `llm_max_tokens` 默认 4096。2026-05-29 Windows 完整流程验证发现 1024 会截断字段复核 JSON，导致 `Unterminated string`；LLM 客户端必须在 `finish_reason=length` 时明确报错，复核 prompt 的 `comment` 必须保持短文本。
- 失败任务重试时，如果上一轮已经写入成功的 `results/{task_id}/document_result.json`，编排器应复用该 OCR 结果，只重跑字段抽取；不要因为字段抽取失败而重复触发耗时 OCR。
- `weight_loss` 抽到 `0g`、`0kg`、`0克` 等反直觉值时，后端只追加 `counterintuitive_zero_weight_loss` 质量标记并置为 `suspicious`，不得自动改写为推测值。
