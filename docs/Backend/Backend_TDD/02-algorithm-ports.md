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

当前默认 OCR 接入使用 `qwen-vision-vllm-server` 常驻服务适配 `DocumentParsingPort`；同一 vLLM 服务同时承担图片 OCR 与 text-only 固定字段 JSON 抽取。后端通过 OpenAI Python SDK 调本地 `/v1`，不接云 API。

- 配置项：`algorithms.enable_local_ocr`、`qwen_vllm_server_url`、`qwen_vllm_model_name`、`qwen_vllm_model_dir`、`qwen_vllm_max_model_len`、`qwen_vllm_gpu_memory_utilization`、`qwen_vllm_max_num_seqs`、`qwen_ocr_temperature`、`qwen_ocr_max_tokens`、`qwen_ocr_timeout_seconds`。
- 后端按页提交任务图片到 Qwen vLLM 服务（OpenAI Chat Completions，`image_url` data URL），把模型输出文本映射为 `DocumentResult`。
- OCR prompt 允许过滤页眉、页脚、页码、打印时间、医院页眉页脚、医生签名、手签等非病历正文干扰；禁止纠正文书正文、补全、重排、标题字符串替换（如 `品后诊断 → 最后诊断`）、医学推理补写。
- 任一页面缺失输出时，该页标记 `failed`；只要至少一页有 OCR 文本，编排器继续进入字段抽取，并在 `document_result.json` 保留 `partial_failure` 状态与失败页信息。
- `qwen_ocr_max_tokens` 默认 4096，`qwen_ocr_timeout_seconds` 默认 240，单页 OCR 超过该预算视为该页外部模块异常；所有页面均无文本时任务进入 `failed`，避免前端长期停留在“处理中”。
- `qwen_vllm_max_model_len` 默认 16384；`max_model_len >= 30000` 在 8GB 显卡下会撑爆 KV cache，必须被 `_validate_config` 拒绝。
- `qwen_ocr_temperature` 默认 0.0，保证同一原图多次 OCR 可复现。
- OCR 服务调用开始和结束时，事件日志记录 `ocr_vlm_started`、`ocr_vlm_finished`，payload 含 `backend="qwen_vision_vllm"`、`server_url`、`model`、`page_count`、`timeout_seconds`、`temperature`、`max_tokens`、`top_p`、`input_files`、耗时、输出大小、`failed_page_count`、失败 `reason`；**不**允许携带 OCR 文本、图片 base64、prompt 或模型完整输出。
- 整体 Docker 部署中，OCR 只通过常驻 `qwen-vision-vllm-server` 容器提供；旧 OCR 容器不再作为默认 OCR 路径。
- 任务级 `failed` 仍按 `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md` 判定：所有页面 OCR 文本为空、服务不可达、全局超时、非法响应或契约非法时，任务进入 `failed`。

## 本地 LLM/结构化抽取适配器

结构化抽取由 `qwen-vision-vllm-server` 同一服务提供，后端通过 `OpenAICompatibleJsonClient` 包装 `QwenVLLMClient.complete_json`，与 OCR 共享同一常驻模型。旧本地 GGUF 客户端与 builder 已从活动后端删除；旧 free-key prompt、旧 `section_groups` 抽取入口与旧 `copd_admission_record.v1.yaml` 不再作为活动 schema 路径。

- Windows Docker 部署不再为旧本地 GGUF 抽取路径编译 CUDA wheel；默认后端镜像只需 OpenAI SDK + Flask + PyYAML，OCR + 抽取的 GPU 计算全部由 `qwen-vision-vllm-server` 容器承担。
- `docker-compose.yml` 必须为 `qwen-vision-vllm-server` 暴露 `gpus: all`，并把宿主 `models/llm` 只读挂载到容器内 `/workspace/model/llm`。
- 同一任务从 OCR 到固定字段抽取连续持有 `qwen_ocr_and_extraction` GPU 阶段：OCR 完成后不释放锁，结构化抽取复用同一常驻 vLLM 服务；中途不允许其他任务插队。
- 失败任务重试时，如果上一轮已经写入成功的 `results/{task_id}/document_result.json`，编排器应复用该 OCR 结果，只重跑字段抽取（仅持有 `field_extraction` GPU 阶段），不重复触发耗时 OCR。
- `qwen_extraction_max_tokens` 默认 8192；`qwen_extraction_timeout_seconds` 默认 360；`qwen_extraction_temperature` 默认 0.0。
- 字段结果契约、证据回填与 `not_found` 处理继续按 `docs/superpowers/specs/2026-06-18-qwen-admission-record-structured-fields-evidence-design.md`；旧本地 GGUF 抽取路径与旧 OCR 容器路径不得再路由到 `copd_admission_record`。
- `weight_loss` 抽到 `0g`、`0kg`、`0克` 等反直觉值时，后端只追加 `counterintuitive_zero_weight_loss` 质量标记并置为 `suspicious`，不得自动改写为推测值。
