# 后端 TDD — 算法子系统端口与结构化字段结果契约

> OCR、图像处理、文档解析和 LLM 结构化提取按可替换算法子系统管理。后端主流程只依赖端口输入输出、字段结果契约、失败语义和部署配置，不与某一套算法内部实现强耦合。

## 端口定义

```ts
type DocumentParsingPort = {
  parse(input: { image_paths: string[]; task_id: string }): Promise<DocumentResult>;
};

type FieldExtractionPort = {
  extract(input: {
    document_result: DocumentResult;
    schema: FieldSchema;
    evidence_units: EvidenceUnit[];
  }): Promise<FieldResult[]>;
};
```

当前 MVP 的算法输入来自任务图片列表，按上传成功顺序排列。默认不向算法端口传入采集会话、`quad_points`、裁剪图或透视矫正结果；如果新的算法子系统需要预处理输入或批处理目录，必须先更新本契约和对应测试。

`FieldResult` 是按 schema 全量返回的字段结果。每个字段保留自动值、证据数组、抽取状态、字段级复核状态、医生可读的关注标记和 OCR 纠偏审计信息；未抽到字段也应作为空值结果进入审核页。

## 入量记录结构化字段契约 (admission_record_structured_fields.v1)

- 入院记录 schema 来自 `app/config/schemas/admission_record_structured_fields.v1.yaml`，按章节（主诉、现病史、既往史、个人史、家族史、体格检查、辅助检查、诊断）组织 61 个固定字段。
- `DocumentProfile.document_type` 仍为 `copd_admission_record`（与既有任务/导出/审核入口兼容），profile.label 为 `入院记录`。
- `schema_version` 字段为新固定字段 schema 版本号；算法侧 payload 仍可写 `document_type: "admission_record"`，仅作为信息字段，不用于任务路由。
- 旧的 `copd_admission_record.v1.yaml` 小字段 schema 与自由二级 key 抽取路径不在新固定字段流程内使用；其物理清理在算法-清理任务内统一处理。

## evidence_units → evidence_ids → evidence 回填链路

- OCR 完成后，后端在文档解析结果基础上生成轻量 `evidence_units`：`{id, text, start_offset, end_offset, page_no?, section_key?}`，编号稳定于本次 OCR 文本（`u001` 起）。
- 切分策略以换行/句号/分号/受控逗号回退为主：生命体征行、血气整组、诊断行或诊断块、治疗药物整段保持为一个 unit；不做 OCR 纠错、不做章节标题硬匹配、不做页序推断。
- `evidence_units` 持久化在 `results/{task_id}/document_result.json`，与 `merged_text` 字符偏移一致。
- 字段抽取 prompt 收到 `evidence_units` 后仅返回 `field_key / status / value / evidence_ids`；模型不自由生成 evidence 文本。
- 后端在 `admission_contract` 中按 `evidence_ids` 把 unit 文本和 offset 回填到 `FieldResult.evidence[]`；未知 ID 或 `found` 字段缺证据不伪造高亮，置为 `verification_status=suspicious` 并由前端展示“缺少来源证据，请核对原文”。
- 单字段可疑（`uncertain` / 证据缺失 / 证据无法定位 / OCR 疑似错读影响字段值）走审核页，标 `attention_required=true`；`not_found` 不默认标黄。

## 失败契约

- `DocumentParsingPort` 未配置、异常或返回空页结果时，任务处理失败。
- 结构化字段抽取未配置、异常、JSON 无法解析、`fields` 不是列表、字段缺失、字段重复、出现 schema 外字段、或全字段为 `not_found` 且无有效文本支撑时，任务处理失败。
- 单字段 evidence 可疑、OCR 疑似错误或复核失败时，字段进入审核页提示人工核验，不直接让整个任务失败。
- 处理流程不得崩溃；不得在无原文证据时生成医学值。诊断字段（`diagnosis_preliminary` / `diagnosis_final`）只摘录原文，不得由模型补造、改写或推理。
- 结构化字段抽取返回局部 `not_found` 或 `uncertain` 时，任务不失败而是进入 `review`，单字段风险由前端展示供人工核验。

契约测试可以使用 fixture 或可注入 LLM 客户端模拟字段抽取结果。

## 本地 OCR 适配器

当前已验证 OCR 接入使用 `paddleocr-vlm-server` 常驻服务适配 `DocumentParsingPort`；后续可以替换为新的本地 OCR/LLM 视觉算法子系统，但必须保持 `DocumentResult` 契约或提供适配层：

- 配置项：`algorithms.enable_local_ocr`、`local_ocr_vlm_server_url`、`local_ocr_vlm_timeout_seconds`、`local_ocr_max_new_tokens`、`local_ocr_max_pixels`。
- 后端按页提交任务图片到本地 OCR 服务、读取算法输出并转换为 `DocumentResult`。
- 现有 OCR 服务调用 `paddleocr.PaddleOCRVL(vl_rec_backend="vllm-server")`；该组合是当前验证版本，不是长期唯一实现。
- 服务化 OCR 当前验证组合：`paddlepaddle-gpu==3.2.1`、`paddleocr==3.5.0`、`paddlex==3.5.2`、`PaddleOCR-VL-1.6-0.9B`、官方 vLLM server 镜像 digest `sha256:1cee5e7e26e666bcd80d2a9741c450438bf507268cbfb14e0e0d33b8d5259621`。
- 任一页面缺失输出时，该页标记 `failed`，整体任务按文档解析部分失败进入 `failed`。
- `local_ocr_max_new_tokens` 默认 1024，`local_ocr_max_pixels` 默认 501760（28*28*640），作为 8GB 显存保守默认值。
- `local_ocr_vlm_timeout_seconds` 默认 240，单页 OCR 超过该预算视为外部模块异常并进入 `failed`，避免前端长期停留在“处理中”。
- OCR 服务调用开始和结束时，事件日志记录 `ocr_vlm_started`、`ocr_vlm_finished`，包含服务 URL、页数、推理参数、耗时、输出大小和失败原因。
- 整体 Docker 部署中，OCR 只通过常驻 `paddleocr-vlm-server` 容器提供。

## 本地 LLM/结构化抽取适配器

结构化抽取可以由当前 `llama.cpp` 客户端、OpenAI-compatible vLLM 服务或新的算法包提供；后端审核页依赖的是字段结果契约，而不是具体推理框架。

- Windows Docker 部署必须使用 CUDA 版 `llama-cpp-python==0.3.22`，并通过 `docker-compose.yml` 的 `gpus: all` 暴露宿主机 GPU。
- `requirements.docker.txt` 不得安装默认 `llama-cpp-python` wheel；Dockerfile 必须在 CUDA devel 镜像内以 `GGML_CUDA=on` 源码编译，并固定 `CMAKE_CUDA_ARCHITECTURES=89`。
- 构建 CUDA 版 llama.cpp 时需提供 `/usr/local/cuda/compat` 的 `rpath-link`，否则最后链接工具程序时可能因找不到 `libcuda.so.1` 失败。
- 2026-05-29 Windows Docker 根因：OCR 成功后进入字段抽取，但显存为空、后端 CPU/RSS 很高；容器内 `llama_cpp/lib` 只有 CPU 后端库，`libllama.so` 无 CUDA/cuBLAS 依赖。修复后验证镜像必须包含 `libggml-cuda.so`，并在 `--gpus all` 下可加载 `llama_cpp`。
- `llm_max_tokens` 默认 4096。2026-05-29 Windows 完整流程验证发现 1024 会截断字段复核 JSON，导致 `Unterminated string`；LLM 客户端必须在 `finish_reason=length` 时明确报错，复核 prompt 的 `comment` 必须保持短文本。
- 失败任务重试时，如果上一轮已经写入成功的 `results/{task_id}/document_result.json`，编排器应复用该 OCR 结果，只重跑字段抽取；不要因为字段抽取失败而重复触发耗时 OCR，除非用户明确选择重新跑完整算法流程。
- `weight_loss` 抽到 `0g`、`0kg`、`0克` 等反直觉值时，后端只追加 `counterintuitive_zero_weight_loss` 质量标记并置为 `suspicious`，不得自动改写为推测值。
