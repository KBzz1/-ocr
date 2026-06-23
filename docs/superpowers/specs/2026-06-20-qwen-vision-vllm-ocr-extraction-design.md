# Qwen Vision vLLM OCR 与固定字段抽取服务化接入设计

## 背景

当前工作站 OCR 默认路径是 `paddleocr-vlm-server` 常驻服务。后端通过 `PaddleOCRVL(vl_rec_backend="vllm-server")` 客户端提交任务页图片，得到每页 Markdown 文本和 `merged_text`，再交给结构化字段抽取流程。结构化抽取当前仍存在旧 `llama.cpp`/GGUF、旧 COPD 小字段和早期 section-group/free-key prompt 的历史路径，容易在新固定字段契约实施时污染上下文。

`/mnt/c/Users/97949/Desktop/qwen` 验证了另一种本地模型服务形态：用 `vllm/vllm-openai` 容器加载 `Qwen3.5-4B-AWQ-4bit` 视觉模型，并通过 OpenAI-compatible Chat Completions API 对图片做 OCR 和对文本做结构化抽取。该方案真正有价值的地方不是批处理流程，而是同一个 Qwen 视觉模型常驻 GPU 后，同时承担 OCR 与 LLM 抽取，避免 OCR 和结构化阶段分别冷启动不同模型。

本设计定义首版 Qwen Vision vLLM 服务化接入：同一个 vLLM 服务同时提供 OCR 和固定字段结构化抽取。结构化字段体系、字段全量返回、诊断约束、`not_found` 语义和证据回填仍以 `docs/superpowers/specs/2026-06-18-qwen-admission-record-structured-fields-evidence-design.md` 为准。

实施基线应采用 2026-06-18 固定字段证据实现分支，而不是从 `master` 重新实现固定字段契约。当前已存在的基线分支为 `worktree-qwen-admission-structured-fields`；本 spec 的后续 plan 应以该分支作为起点创建执行 worktree，完成并验收后再合并回主线。

## 已确认决策

- 使用 Qwen Vision vLLM 服务替换当前 PaddleOCR VLM 服务和默认 llama.cpp 结构化抽取路径，作为工作站默认 OCR + LLM 固定字段抽取算法子系统。
- 同一个 `qwen-vision-vllm-server` 常驻加载 `Qwen3.5-4B-AWQ-4bit`，OCR 阶段发送图片消息，结构化阶段发送文本 prompt。
- Qwen3.5-4B-AWQ-4bit 模型目录放在 `models/llm/Qwen3.5-4B-AWQ-4bit/`，部署时以只读挂载方式提供给 vLLM 容器。
- 后端调用 vLLM 使用桌面 qwen 同款 OpenAI Python SDK，连接本地 OpenAI-compatible API；只迁移 SDK 调用方式，不迁移桌面批处理业务流程。
- 同一任务处理时，GPU 阶段队列从 OCR 开始连续持有到固定字段抽取完成，再释放，避免 OCR 与抽取之间被其他任务插队造成额外等待。
- 首版迁移模型服务、OCR 端口和固定字段抽取端口，不迁移桌面 qwen 的批处理业务流程。
- 工作站业务流保持不变：医生上传图片，后端创建任务，OCR 生成文本，结构化抽取固定字段，医生审核，导出。
- OCR 输出允许过滤页眉、页脚、页码、打印时间、医院页眉页脚、医生签名、手签等非病历正文干扰。
- OCR 输出不得纠正文书正文、补全文字、总结病历、重排页面或做样本特化替换。
- 前端 OCR 区展示 OCR 模型输出文本；字段证据高亮也定位到该 OCR 输出文本。
- 固定字段抽取必须沿用 2026-06-18 spec：章节到固定字段、全量字段返回、未找到返回 `not_found`、不允许自由生成二级 key。
- 字段证据策略继续使用轻量 `evidence_units -> evidence_ids -> 回填 evidence`，不退回桌面 qwen 的逗号级单 `evidence_id`。
- 默认路径不得继续并行保留旧 free-key prompt、旧 section-group 抽取入口或旧 COPD 小字段 schema 作为可路由默认实现。
- `not_found` 仍是正常字段状态，不因未找到证据默认黄色感叹号。
- 医生上传图片顺序乱时，OCR 区按系统保存顺序展示模型输出文本；字段区按 schema 顺序展示；证据跳到 OCR 输出文本实际位置。
- 不提交真实患者数据、OCR 输出、运行日志、模型权重、vLLM cache、镜像 tar 或本机私有路径。

## 范围

包含：

- 定义 Qwen Vision vLLM 服务的部署形态和默认参数。
- 定义同一 vLLM 服务如何承担 OCR 和固定字段结构化抽取。
- 定义实施基线必须基于 2026-06-18 固定字段证据分支。
- 定义模型目录、OpenAI SDK 客户端和连续 GPU 队列策略。
- 定义后端 OCR 端口如何调用 OpenAI-compatible Vision Chat API。
- 定义后端固定字段抽取端口如何调用 OpenAI-compatible text Chat API。
- 定义 OCR prompt 的允许过滤范围和禁止行为。
- 定义 `DocumentParsingPort` 和字段抽取端口的输出契约保持方式。
- 定义任务失败、事件日志、重试复用和隐私边界。
- 定义需要同步更新的配置、脚本、部署文档和测试范围。

不包含：

- 结构化字段表设计，见 2026-06-18 固定字段证据 spec。
- 2026-06-18 固定字段 prompt 的完整字段内容重写；本 spec 只约束它必须跑在同一个 vLLM 服务上。
- 桌面 qwen 批处理客户端迁移。
- 图片 bounding box、版面坐标、自动页序修复、复杂章节恢复、OCR 标题纠错。
- HIS/EMR 接入、病历写回、诊断建议或医学推理。
- 真实模型权重、运行缓存、镜像 tar 的提交。

## 分支与集成策略

当前设计文档所在分支只承载本次 Qwen vLLM 迁移 spec。实施时应以 `worktree-qwen-admission-structured-fields` 为代码基线，因为该分支已经实现 2026-06-18 固定字段证据契约的主要代码路径。

推荐流程：

- 从 `worktree-qwen-admission-structured-fields` 新建实施分支或实施 worktree。
- 在该分支上接入 Qwen Vision vLLM OCR 与固定字段抽取。
- 实施完成后先在分支内完成测试和人工验收。
- 用户认可后，再将固定字段证据实现和 Qwen vLLM 迁移一起合并回主代码。

不要从 `master` 重新实现固定字段契约，也不要把本 spec 分支直接当作最终实施基线，除非先把 2026-06-18 固定字段实现合入该分支。

## 桌面 qwen 迁移边界

### 迁移

- `vllm/vllm-openai` 提供 OpenAI-compatible API 的服务形态。
- 同一个 vLLM 服务先处理图片 OCR，再处理固定字段 text-only JSON 抽取。
- 模型目录只读挂载，vLLM cache 单独挂载。
- 桌面 qwen 的 OpenAI SDK 客户端调用方式。
- GPU 资源声明、`ipc: host`、`/v1/models` 健康检查。
- `Qwen3.5-4B-AWQ-4bit` 作为 8GB 显存优先验证模型。
- `--enable-chunked-prefill`、`--enable-prefix-caching`、`--dtype auto`、`--trust-remote-code`。
- 图片 base64 data URL 和 MIME 类型识别。
- OCR prompt 中忠实识别、不纠错、不补全、不输出解释、关闭 thinking 的原则。
- 结构化抽取中关闭 thinking、`temperature=0.0`、严格 JSON 输出、固定字段表输出的原则。
- Windows 启动脚本等待 vLLM 服务健康后再启动工作站的做法。

### 不迁移

- `MAX_MODEL_LEN=30000` 作为 8GB 默认值。
- `temperature: 0.6`。OCR 和固定字段抽取默认必须使用 `temperature=0.0`。
- 未固定来源的 `vllm/vllm-openai:latest` 作为正式离线部署镜像。
- 扫描 `input/` 目录、移动原图到 `input/processed/`、生成 `output/` zip 的批处理归档流程。
- 动态 schema、模型自由生成二级 key、总结式结构化 value。
- 逗号级切分文本并要求模型只返回一个 integer `evidence_id`。
- 使用独立 `llama.cpp`/GGUF 模型作为默认结构化抽取路径。
- 桌面 qwen 的真实输入、输出、日志、cache、模型权重或镜像 tar。

## 证据策略对比结论

当前仓库 2026-06-18 固定字段证据设计优于桌面 qwen 的 evidence 方案，应继续保留：

- 当前仓库按固定字段表约束 `field_key`，证据服务于审核字段；桌面 qwen 允许模型自由生成二级 key，字段边界不稳定。
- 当前仓库由后端生成 `evidence_units`，模型只选择 `evidence_ids`；桌面 qwen 让模型绑定逗号级短句编号，证据容易过碎。
- 当前仓库允许一个字段引用多个 `evidence_ids`，也允许多个字段共用同一条证据；桌面 qwen 的单 integer `evidence_id` 不能表达跨片段字段。
- 当前仓库后端回填 evidence 文本和 offset，前端可在 OCR 文本中稳定高亮；桌面 qwen 主要把编号映射回短句，缺少工作站审核所需的定位契约。
- 当前仓库把 `not_found` 作为正常状态，不默认黄色风险；桌面 qwen 更偏一次性批处理抽取，不区分医生审核卡片的风险语义。

桌面 qwen 的证据编号思路可以借鉴，但只能作为 `evidence_units` 编号输入的灵感，不能照搬逗号级单证据方案。

## 推荐架构

```text
doctor uploads images
  -> TaskService 保存任务页和系统页序
  -> QwenVisionVLLMDocumentPort
       -> qwen-vision-vllm-server /v1/chat/completions
       -> 每页 OCR 模型输出文本
  -> DocumentResult pages + merged_text
  -> evidence_units from OCR output text
  -> QwenVisionVLLMFixedFieldPort
       -> same qwen-vision-vllm-server /v1/chat/completions
       -> fixed fields + evidence_ids
  -> review result + evidence offsets
  -> 前端审核页
```

服务组成：

- `manzufei-ocr`：Flask API、任务状态、持久化、字段抽取编排、审核页静态资源。
- `qwen-vision-vllm-server`：Qwen 视觉模型服务，暴露 OpenAI-compatible API，同时处理图片 OCR 和 text-only 固定字段抽取。

后端主流程只依赖 `DocumentParsingPort` 和字段抽取端口，不得让路由、任务服务或前端直接耦合 vLLM 内部协议。

## Qwen Vision vLLM 服务契约

服务名建议为 `qwen-vision-vllm-server`。

API：

- `GET /v1/models`：健康检查和模型名发现。
- `POST /v1/chat/completions`：每页图片 OCR。
- `POST /v1/chat/completions`：text-only 固定字段结构化抽取。

8GB 显存默认参数：

```text
--model /workspace/model/llm/Qwen3.5-4B-AWQ-4bit
--max-model-len 16384
--gpu-memory-utilization 0.85
--max-num-seqs 1
--enable-chunked-prefill
--enable-prefix-caching
--dtype auto
--host 0.0.0.0
--port 8000
--trust-remote-code
```

约束：

- `max_num_seqs` 首版默认 1，确保同一个常驻模型服务串行处理 OCR 和结构化请求。
- 不使用 `MAX_MODEL_LEN=30000` 作为 8GB 默认。
- 正式离线部署不得依赖浮动 `latest` 镜像；需使用固定镜像来源或经过验证的离线 tar。
- 模型目录为宿主机 `models/llm/Qwen3.5-4B-AWQ-4bit/`，容器内只读挂载到 `/workspace/model/llm/Qwen3.5-4B-AWQ-4bit/`。
- vLLM cache 单独挂载；cache 不进入仓库和离线包源码目录。
- OCR 与固定字段抽取共享同一模型实例，后端不得在默认路径中另起 llama.cpp 模型。

## OCR 调用契约

后端端口按页调用 vLLM。调用方式采用 OpenAI Python SDK，`base_url` 指向本地 vLLM `/v1` 地址，`api_key` 使用离线占位值。请求使用 OpenAI-compatible Chat Completions：

```json
{
  "model": "Qwen3.5-4B-AWQ-4bit",
  "messages": [
    {
      "role": "system",
      "content": "你是一个医疗文档 OCR 识别助手。"
    },
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/jpeg;base64,..."
          }
        },
        {
          "type": "text",
          "text": "请识别这张图片中的病历正文。"
        }
      ]
    }
  ],
  "temperature": 0.0,
  "top_p": 1.0,
  "max_tokens": 4096
}
```

如果模型支持 thinking 开关，请通过 vLLM 支持的 `extra_body` 关闭 thinking，例如 `chat_template_kwargs.enable_thinking=false`。如果当前模型或 vLLM 版本不支持该参数，端口不得失败；应保持 prompt 中禁止输出 thinking，并通过测试确保 `<think>` 内容会被拒绝或清理。

图片输入：

- 支持 `.jpg`、`.jpeg`、`.png`、`.bmp`、`.tif`、`.tiff`、`.webp`。
- 端口按扩展名生成 MIME 类型。
- 输入图片必须来自任务页 `processed_path`。
- 不移动、归档、重命名任务原图。

输出映射：

- 每页生成一个 `DocumentResult.pages[]`。
- `source` 使用 `qwen_vision_vllm`。
- `text` 为 OCR 模型输出文本。
- `blocks` 和 `tables` 首版为空数组。
- `merged_text` 按系统页序拼接所有成功页文本。
- 单页空输出记为该页 failed；所有页均空、服务不可达、超时、非法响应时任务进入 `failed`。

## OCR prompt 契约

OCR prompt 必须表达以下规则：

- 输出病历正文文本。
- 不输出解释、寒暄、JSON、Markdown 代码块或 thinking。
- 保持当前页可见正文的自然阅读顺序。
- 不纠错、不改写、不总结、不补全。
- 当前页末尾未完句保持原样，不补标点、不补后文。
- 可忽略页眉、页脚、页码、打印时间、医院页眉页脚、医生签名、手签等非病历正文干扰。

禁止行为：

- 不得专门把 `品后诊断` 替换为 `最后诊断`。
- 不得因为 `主诉` 出现在诊断后就自动重排页面。
- 不得通过医学常识补写诊断、症状、检查或治疗。
- 不得把结构化字段名反向写进 OCR 文本。

如果过滤误删了病历正文，属于 OCR 算法质量问题。首版通过人工审核、日志诊断和后续 prompt/模型迭代处理，不写样本特化规则。

## 固定字段抽取调用契约

后端在 OCR 完成后，从 OCR 模型输出文本生成 `evidence_units`，再通过同一个 OpenAI SDK client 向同一个 vLLM 服务发送 text-only Chat Completions 请求。请求必须按 2026-06-18 固定字段证据 spec 组织 prompt：

```json
{
  "model": "Qwen3.5-4B-AWQ-4bit",
  "messages": [
    {
      "role": "system",
      "content": "你是一个病历结构化字段抽取助手，只能按固定字段表输出 JSON。"
    },
    {
      "role": "user",
      "content": "字段表、证据单元和 OCR 文本..."
    }
  ],
  "temperature": 0.0,
  "top_p": 1.0,
  "max_tokens": 8192,
  "response_format": {
    "type": "json_object"
  }
}
```

如果 vLLM 或模型版本不支持 `response_format`，端口不得降级为自由文本业务输出；必须继续要求只输出 JSON，并由后端解析、校验和失败映射。

固定字段抽取硬约束：

- 输入字段表来源为 `data/temp/结构化字段(2).md` 落地后的 schema，不使用旧 `copd_admission_record.v1.yaml` 小字段作为默认抽取字段。
- 输出必须覆盖固定字段表中的每个字段。
- `field_key` 只能来自固定字段表。
- 不允许模型自由生成二级 key。
- 未找到字段返回 `not_found`，不得省略。
- 诊断字段只能摘录病历原文中的诊断结果，禁止主观补诊断、改写诊断、推理诊断。
- 每个字段返回 `status`、`value`、`evidence_ids`，由后端回填 evidence 文本和 offset。
- 允许多个字段共用同一条证据，允许一个字段引用多个 `evidence_ids`。
- 字段级可疑只进入审核页黄色感叹号，不导致任务失败。

默认路径迁移后，旧 `llama.cpp` 客户端、旧 free-key prompt、旧 section-group 抽取入口和旧 COPD 小字段 schema 不得继续作为运行时默认候选路径。若实现阶段需要保留代码作历史兼容，必须明确不可被当前 admission record profile 路由到。

## 固定字段与证据链路

同一个 Qwen Vision vLLM 服务承接结构化抽取，但不改变 2026-06-18 固定字段设计：

- 字段体系来源仍为 `data/temp/结构化字段(2).md`。
- 输出仍是“章节 -> 固定字段”。
- 每个字段全量返回；未找到返回 `not_found`。
- qwen 结构化 prompt 仍必须按固定字段表输出，不允许自由生成二级 key。
- 诊断字段只提取病历原文里的诊断结果，禁止主观补诊断、改写诊断、推理诊断。
- 字段卡片黄色感叹号只表示“需要医生重点核验”。
- `not_found` 是正常状态，不默认黄色感叹号。
- evidence 仍采用轻量 `evidence_units -> evidence_ids -> 回填 evidence`。

OCR 过滤后，证据高亮基准是 OCR 模型输出文本，不是图片像素中的完整原始文本。首版不做图片 bounding box，因此证据定位只承诺跳转到 OCR 输出文本中的对应片段。

## GPU 阶段队列

8GB 显存下继续保留 GPU 阶段队列，但默认路径只有一个常驻 Qwen Vision vLLM 模型。队列目标从“避免两个模型同时抢显存”调整为“避免同一小显存 vLLM 服务并发处理多任务长请求，并保证同一任务 OCR 到固定字段抽取不中途插队”：

```text
task processing
  -> acquire gpu stage: qwen_ocr_and_extraction
  -> qwen vision OCR
  -> persist document_result.json
  -> same qwen vision vLLM fixed-field extraction
  -> persist review result
  -> release gpu stage
```

规则：

- OCR 阶段和结构化抽取阶段仍按任务串行进入 vLLM，避免 8GB 显存下长请求并发。
- 同一任务从 OCR 到固定字段抽取连续持有 GPU 阶段队列；中间不允许其他任务插队。
- 同一任务 OCR 完成后不卸载模型；结构化抽取复用已经常驻的 vLLM 服务，减少冷启动和队列等待延迟。
- 队列释放必须放在异常路径，避免永久锁死。
- OCR 成功后必须先写入 `document_result.json`。
- 后续结构化抽取失败时，重试应复用合法 `document_result.json`，只重跑结构化抽取。

## 失败语义

任务进入 `failed`：

- Qwen Vision vLLM 服务不可达。
- `/v1/models` 长时间不健康。
- 单页 OCR 请求超时。
- 固定字段抽取请求超时。
- vLLM 返回非法结构。
- 所有页面 OCR 文本为空。
- `DocumentResult` 契约非法。
- 固定字段抽取整体不可用、字段结果全空或契约非法。
- 固定字段抽取输出 schema 外字段、缺少固定字段、自由生成二级 key 或诊断字段违反原文摘录约束。

任务不因以下情况直接失败：

- 单字段 `not_found`。
- 单字段证据不足或需要黄色感叹号重点核验。
- 部分页 OCR 空输出但至少有成功页，且后续字段抽取可进入审核页。空页需在 `DocumentResult.pages[]` 标记 failed 并记录错误信息。

## 日志与可观测性

继续使用事件日志记录 OCR 和固定字段抽取阶段，不记录完整 OCR 正文、图片 base64、患者身份信息或模型完整输出。

`ocr_vlm_started` payload 至少包含：

- `backend=qwen_vision_vllm`
- `server_url`
- `model`
- `page_count`
- `timeout_seconds`
- `temperature`
- `max_tokens`
- `top_p`
- `input_files` 的文件名、字节数、页序和存在性

`ocr_vlm_finished` payload 至少包含：

- `backend=qwen_vision_vllm`
- `elapsed_ms`
- `exit_code`
- `output_exists`
- `output_bytes`
- `failed_page_count`
- 失败时的 `reason`

日志不得包含完整 OCR 文本、真实患者数据、密钥、本机私有路径或图片 base64。

固定字段抽取阶段需要记录结构化诊断事件，事件名可沿用现有字段抽取事件，也可新增 `llm_extraction_started` / `llm_extraction_finished`。payload 至少包含：

- `backend=qwen_vision_vllm`
- `server_url`
- `model`
- `schema_version`
- `field_count`
- `evidence_unit_count`
- `timeout_seconds`
- `temperature`
- `max_tokens`
- `elapsed_ms`
- `exit_code`
- 失败时的 `reason`

字段抽取日志不得包含完整 OCR 文本、完整 prompt、完整模型输出、真实患者数据或 evidence 全文。

## 配置与部署影响

需要同步调整：

- 实施分支：从 `worktree-qwen-admission-structured-fields` 创建新的执行 worktree 或在其后续分支上实施，避免从 `master` 重做固定字段契约。
- `docker-compose.yml`：默认 OCR + 固定字段抽取模型服务替换为 `qwen-vision-vllm-server`。
- `scripts/dev/run.sh`：启动并等待 Qwen Vision vLLM 服务健康。
- `scripts/dev/stop.sh`：停止 Qwen Vision vLLM 服务以释放 GPU。
- `deploy/windows/00_import_image.bat`：导入新 vLLM 服务镜像 tar。
- `deploy/windows/01_start.bat`：启动新服务，检查 `/v1/models`，记录诊断信息。
- `deploy/windows/02_stop.bat` / `03_logs.bat`：服务名和日志路径同步更新。
- `scripts/deploy/package_offline_docker_bundle.sh`：打包新 vLLM 服务镜像 tar，不再默认打包 PaddleOCR VLM tar。
- `app/config/local.docker.yaml`：配置新 shared Qwen vLLM backend、vLLM URL、模型名、宿主模型目录、OCR temperature、抽取 temperature、timeout、max tokens。
- `app/backend/config.py`：加载和校验新配置项。
- `app/backend/services/algorithm_ports/`：新增或替换 OCR 端口适配器，保持 `DocumentParsingPort` 输出契约。
- `app/backend/services/copd_extraction/` 或新的固定字段抽取模块：把默认抽取客户端切到同一个 vLLM OpenAI-compatible 服务。
- `requirements.txt` / `requirements.docker.txt`：加入或保留 `openai` SDK 作为后端 vLLM 客户端依赖；不得引入联网云 API 依赖或真实 API key 配置。
- `requirements.docker.txt` / `Dockerfile`：如果默认结构化抽取不再使用 llama.cpp，部署镜像不得继续为了默认路径编译 CUDA 版 `llama-cpp-python`；如保留兼容依赖，必须证明它不会成为默认冷启动路径。
- `docs/部署/GPU-Docker部署.md`、`docs/Backend/Backend_TDD/02-algorithm-ports.md`、`deploy/CLAUDE.md`、`deploy/AGENTS.md`：删除 PaddleOCR VLM digest 是唯一正式 OCR 服务的旧说法，改为 Qwen Vision vLLM 契约。

## 批处理归档边界

桌面 qwen 的批处理归档指：

- 扫描 `input/` 目录中的图片或 PDF。
- OCR 和结构化完成后，把已处理文件移动到 `input/processed/`。
- 在 `output/` 下生成每个病人的 OCR、结构化 JSON、汇总文件和 zip。

该机制不进入首版工作站：

- 工作站原图属于任务上传文件，不能被算法流程移动。
- 系统保存顺序是 OCR 展示和证据跳转依据，不能由批处理目录状态改变。
- `output/` 可能包含真实患者 OCR 和结构化结果，不能进入仓库。
- 工作站已有 `data/`、`exports/`、`logs/` 分层，不引入桌面 qwen 的输出目录语义。

未来如需算法评测工具，应作为独立离线评测脚本，并只使用脱敏样本。

## 测试要求

实施计划必须按任务拆分并使用失败测试先行。

配置测试：

- 默认 OCR backend 指向 `qwen_vision_vllm`。
- 默认固定字段抽取 backend 指向同一个 `qwen_vision_vllm` 服务。
- 模型目录默认落在 `models/llm/Qwen3.5-4B-AWQ-4bit/`，配置不得写入本机私有绝对路径。
- OCR temperature 默认 `0.0`。
- 固定字段抽取 temperature 默认 `0.0`。
- 8GB 默认 `max_model_len` 不允许为 `30000`。
- OCR max tokens、抽取 max tokens、timeout、server URL、model name 校验失败时给出明确错误。

端口测试：

- 后端 vLLM client 使用 OpenAI SDK，并将 `base_url` 指向本地 vLLM 服务。
- 将图片编码为正确 MIME 的 base64 data URL。
- 调用 Chat Completions 时传入 `temperature=0.0`、`top_p=1.0`、`max_tokens`。
- 支持关闭 thinking 的 `extra_body`；不支持时不破坏调用。
- 多页按 `page_no` 排序输出。
- 空页、服务超时、非法响应和所有页为空映射为文档解析失败。
- 事件日志包含诊断字段但不包含 OCR 全文或图片 base64。

固定字段抽取测试：

- 使用同一个 vLLM server URL 和 model name 调用 text-only Chat Completions。
- prompt 输入为固定字段表和 `evidence_units`，不允许自由二级 key。
- 模型输出缺字段、schema 外字段、非法 JSON、所有字段空或诊断主观改写时映射为抽取失败。
- `not_found` 字段不生成黄色感叹号。
- 多字段可引用同一 evidence id，一个字段可引用多个 evidence ids。
- 后端回填 evidence 文本和 offset，前端高亮基准为 OCR 输出文本。

编排测试：

- 后端启用本地 OCR 后使用 Qwen Vision vLLM `DocumentParsingPort`。
- 后端启用固定字段抽取后使用同一个 Qwen Vision vLLM 服务，不加载默认 llama.cpp/GGUF 模型。
- OCR 成功、结构化失败后的重试复用 `document_result.json`。
- 同一任务连续持有 GPU 阶段队列完成 OCR 和结构化抽取，中间不允许其他任务插队。
- 重试已有合法 `document_result.json` 时，只持有队列执行结构化抽取，不重跑 OCR。

脚本与部署测试：

- 开发启动脚本使用新服务名和 `/v1/models` healthcheck。
- 停止脚本停止新服务并释放 GPU。
- 离线导入脚本加载新 vLLM 服务 tar。
- 打包脚本不把模型权重、vLLM cache、真实数据、日志打入仓库或源码包。
- 旧 `paddleocr-vlm-server` 不再作为默认 OCR 服务路径出现。
- 旧 `llama.cpp`/GGUF 抽取不再作为默认固定字段抽取路径出现。

## 验收标准

- 工作站默认 OCR 路径不再依赖 PaddleOCR VLM 容器。
- 工作站默认固定字段抽取路径不再冷启动独立 llama.cpp/GGUF 模型。
- Qwen 模型目录使用 `models/llm/Qwen3.5-4B-AWQ-4bit/` 挂载，不提交模型权重。
- 后端通过 OpenAI SDK 调用本地 vLLM OpenAI-compatible API，不接入云 API。
- Qwen Vision vLLM 服务健康后，任务能完成 OCR、生成合法 `DocumentResult`、完成固定字段抽取并进入审核页。
- OCR 文本允许过滤非正文干扰，但不纠错、不补全、不重排、不写样本特化替换。
- 固定字段证据链路继续按 2026-06-18 spec 执行。
- `not_found` 不默认触发黄色感叹号。
- 任务失败语义、日志隐私和 GPU 阶段队列与现有工作站契约一致；同一任务 OCR 和固定字段抽取连续持有队列。
- 同一任务 OCR 与固定字段抽取复用同一个常驻 Qwen Vision vLLM 服务，避免两个模型分别冷启动。
- 不提交真实患者数据、模型权重、运行缓存、日志、本机私有路径或密钥。

## 风险

- Qwen3.5-4B 视觉模型对医疗 OCR 的准确率可能低于 PaddleOCR-VL，需要使用脱敏样本做人工对比。
- OCR 过滤页眉页脚可能误删正文，首版通过 prompt 和人工审核兜底，不通过样本特化规则修复。
- vLLM 视觉模型显存占用与图片尺寸、上下文长度有关，8GB 参数必须保守。
- Qwen3.5-4B 视觉模型承担固定字段抽取的准确率可能与 Qwen2.5-7B GGUF 不同，需要用脱敏样本对比字段覆盖、诊断忠实性和证据定位。
- 同一 vLLM 服务承担 OCR 与结构化抽取可减少冷启动，但长上下文 fixed-field prompt 仍可能触发 8GB 显存压力，需要保持串行和保守 `max_model_len`。
- 桌面 qwen 的模型和镜像位于本机路径，不能直接成为仓库默认路径或提交内容。
