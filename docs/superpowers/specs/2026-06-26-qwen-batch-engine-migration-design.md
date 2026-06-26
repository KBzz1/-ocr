# Qwen 批处理算法引擎迁移设计

## 背景

当前工作站已经接入本地 Qwen OCR + LLM 一体模型，但运行方式仍以现有后端端口为中心：任务页逐页 OCR、后端生成 `evidence_units`、再按固定字段 schema 抽取并进入审核页。实际审核中仍能看到字段识别和归属问题。

师弟维护的 `https://github.com/aufgh/qwen` 仓库当前提交为 `a746ba9d061d2af8878485f1f837e4d10e2bd755`，它不是一个后端端口实现，而是一个目录批处理管线：

- 扫描 `input/` 下按病人或分组组织的图片/PDF。
- 使用 OpenCV 做图片预处理。
- 通过 OpenAI-compatible vLLM 服务调用 Qwen 多模态模型做 OCR。
- 按分组合并 OCR 文本。
- 在合并长文本上做一次全局 JSON 结构化抽取。
- 通过锚点范围还原证据文本。
- 输出 `merged_ocr.md`、`merged_ocr.txt`、`merged_structured.json` 等结果。

该管线已经由算法侧做过准确率量化，声称稳定版本准确率约 97%。本次迁移目标是最大化复用该稳定算法链路，把它接入工作站任务流，同时保持后续算法仓库继续迭代时可同步。

## 结论

迁移是必要的，但不应把算法仓库代码拆碎后散落进后端。

推荐采用“独立批处理算法引擎 + 工作站适配层”的架构：

```text
工作站后端任务
  -> 创建 qwen batch job
  -> 调用 algorithms/qwen_batch_engine
       -> 图片预处理
       -> 并发 OCR
       -> 合并 OCR
       -> 全局结构化抽取
       -> 锚点证据
       -> 输出 job result
  -> 后端适配器读取结果
  -> 写入任务状态、OCR 文本、结构化字段和审核证据
  -> 前端审核、修订、导出
```

算法内部尽量保持上游结构，后端只依赖一层稳定的 job 输入输出契约。后续算法侧更新时，优先同步 `algorithms/qwen_batch_engine/`，再只修兼容层。

## 已确认决策

- 模型仍使用当前本地 Qwen OCR + LLM 一体模型，通过 vLLM OpenAI-compatible API 提供服务。
- 算法运行模式切换为师弟批处理 job，不再把现有逐页 OCR 端口作为默认算法主路径。
- OCR 整体识别、图片预处理、拼接/合并、并发调度、字段抽取、LLM harness 和核心 prompt 流程以师弟算法仓库为权威来源。
- 字段体系按师弟仓库的中文嵌套 schema 对齐；本项目内部稳定 key 只作为工程 ID，不形成第二套业务字段契约。
- 保留并优先复用师弟 prompt 中 `T`/`J` 两类字段思想：
  - `T`：原文截取型，输出值和锚点范围。
  - `J`：状态判断型，输出正常、异常、未提及和锚点范围。
- 证据 prompt 层采用师弟的锚点范围方案。
- 后端持久化层必须补齐审核需要的证据结构：证据文本、起止 offset、页号或来源文件、锚点范围。
- 本项目负责把算法能力产品化：任务状态、job 输入输出、结果校验、证据 offset 回填、审核页、导出、离线部署、日志和错误映射。
- 允许为了工作站后端契约对 prompt 做受控适配，但不得重写师弟已经验证过的核心 prompt 流程、字段含义、并发策略或算法判断逻辑。
- 算法仓库作为模块接入，后续可继续从上游同步；上游同步优先于在本项目内重造算法逻辑。
- 不提交模型权重、真实患者图片、OCR 输出、运行日志、vLLM cache 或镜像 tar。

## 范围

包含：

- 新增 `algorithms/qwen_batch_engine/`，承载师弟批处理管线。
- 定义工作站任务到 batch job 的输入目录和 manifest。
- 定义 batch job 的标准输出文件和结果摘要。
- 定义中文嵌套字段 schema 在工作站内的版本化方式。
- 定义锚点证据到审核高亮证据的回填策略。
- 定义后端适配器如何触发、等待、读取和失败映射。
- 定义前端审核页对中文嵌套字段、`T`/`J` 字段和证据跳转的支持方向。
- 定义离线部署改造和后续算法同步策略。

不包含：

- 医学诊断建议、HIS/EMR 写回或云端服务。
- 真实算法准确率复现实验设计。
- 上游算法核心 prompt 流程、字段含义和医学抽取逻辑重写。
- 复杂版面坐标、像素级 bounding box 高亮。
- 在第一阶段完全重写导出模板和所有历史字段兼容逻辑。

## 推荐目录结构

```text
algorithms/
  qwen_batch_engine/
    upstream/
      scripts/
      config.yaml
      Dockerfile.qwen-client
      docker-compose.yaml
      start.bat
      stop.bat
    overlay/
      config/
      prompts/
      patches/
      CHANGELOG.md
    adapter/
      run_job.py
      normalize_result.py
      README.md
    VERSION

app/backend/services/algorithm_ports/
  qwen_batch_adapter.py

app/config/schemas/
  qwen_batch_admission_record.v1.yaml

data/algorithm_jobs/
  {task_id}/
    input/
    output/
    manifest.json
    result.json
    error.json
```

`upstream/` 默认保持师弟仓库结构，便于后续同步和 diff。`overlay/` 放本项目对算法侧的可审计补丁和配置覆盖。`adapter/` 放本项目私有包装代码，负责把工作站任务转换成上游可处理的目录形态，并把输出标准化。

## 模块边界

本迁移的核心目标是避免算法逻辑和产品后端混在一起。目录边界必须按以下规则执行：

```text
algorithms/qwen_batch_engine/upstream/
  师弟算法仓库的原样同步区。默认不改或只做同步所需的极小兼容变更。

algorithms/qwen_batch_engine/overlay/
  本项目对算法侧的可审计补丁区，例如配置覆盖、prompt 包装、证据锚点 offset 记录、
  离线运行所需的最小补丁。overlay 必须能说明是补产品化契约，不是重写算法。

algorithms/qwen_batch_engine/adapter/
  工作站 job 输入输出适配区。只负责 manifest、目录准备、结果归一化、错误映射、
  证据 offset 回填和 contract validation。

app/backend/
  产品后端。只负责任务状态、审核、导出、API、持久化和本地日志。
  不承载 OCR、字段抽取、医学判断、prompt 分支或并发调度算法。
```

硬约束：

- `adapter/` 不得按 OCR 文本推断或补造字段值。
- `adapter/` 不得把师弟中文字段重新映射回本项目旧 61 字段作为默认路径。
- `app/backend/` 不得 import `upstream/scripts/process.py` 内部函数；后端只调用稳定 job 入口或读取标准 job result。
- 上游算法输出结构变化时，优先在 `adapter/normalize_result.py` 兼容；如果变化涉及字段含义或 prompt 流程，先同步 spec，再实施。
- 旧算法路径切换为非默认后，必须先通过测试确认无活动引用，再分阶段删除交集代码，不做无验证的大规模物理删除。

## Prompt 适配原则

允许修改 prompt，但修改目标必须是“让师弟算法更稳定地服务工作站契约”，不是把算法责任迁回本项目后端。

允许：

- 增加固定输出外壳，例如 job id、schema version、字段类型、锚点元数据。
- 增强 JSON 严格性、禁止 Markdown、禁止思考过程、禁止证据原文生成等格式约束。
- 在不改变字段含义的前提下补充后端需要的错误语义、空值语义和证据锚点要求。
- 把锚点生成从只保存文本升级为保存 `start_offset`、`end_offset`、`page_no`、`source_file`。
- 通过配置覆盖调整温度、token、并发、超时和模型服务地址。

不允许：

- 在本项目里重写一套独立字段抽取 prompt，并让它与师弟 prompt 并行演化。
- 为适配旧前端/旧导出而改变师弟字段含义。
- 在 prompt 或后端 adapter 中加入样本特化医学规则来“修正”模型结果。
- 让前端从 schema、OCR 文本或页面内容推断、补造结构化字段。
- 未经量化或至少样例回归验证就改动核心 prompt 流程。

每次 prompt 适配必须记录：

- 变更原因。
- 影响字段或输出结构。
- 是否改变核心抽取语义。
- 至少一条离线样例回归结果或无法回归的原因。

## 工作站 Batch Job 契约

后端创建每个任务的 job 目录：

```text
data/algorithm_jobs/{task_id}/
  input/
    page_001.jpg
    page_002.jpg
  manifest.json
```

`manifest.json`：

```json
{
  "job_id": "task-123",
  "task_id": "task-123",
  "schema_version": "qwen_batch_admission_record.v1",
  "created_at": "2026-06-26T00:00:00+08:00",
  "input_files": [
    {
      "page_id": "p1",
      "page_no": 1,
      "filename": "page_001.jpg",
      "original_path": "data/tasks/task-123/pages/p1.jpg"
    }
  ],
  "engine": {
    "name": "qwen_batch_engine",
    "upstream_commit": "a746ba9d061d2af8878485f1f837e4d10e2bd755"
  }
}
```

算法引擎完成后输出：

```text
output/
  merged_ocr.md
  merged_ocr.txt
  merged_structured.json
  anchors.json
  summary.json
```

本项目适配器再生成统一 `result.json`：

```json
{
  "job_id": "task-123",
  "status": "success",
  "engine": {
    "name": "qwen_batch_engine",
    "upstream_commit": "a746ba9d061d2af8878485f1f837e4d10e2bd755"
  },
  "document_result": {
    "merged_text": "...",
    "pages": []
  },
  "structured_result": {},
  "review_fields": [],
  "warnings": []
}
```

## 字段体系

第一阶段按师弟中文嵌套 schema 建立新 schema 版本 `qwen_batch_admission_record.v1`。展示层可使用中文路径，但内部仍应生成稳定 key，避免导出和历史记录完全依赖中文标题。

示例：

```yaml
version: "qwen_batch_admission_record.v1"
document_type: qwen_batch_admission_record
field_groups:
  - group_key: history_of_present_illness
    group_label: 现病史
    fields:
      - field_key: hpi_mental_sleep_appetite
        label: 精神睡眠食欲
        qwen_path: ["现病史", "精神睡眠食欲"]
        qwen_type: J
```

差异处理：

- 师弟有而当前没有的字段，例如 `CRP`，纳入新 schema。
- 当前拆得更细但师弟合并的字段，例如血气、生命体征、身高体重 BMI，第一阶段按师弟合并字段展示。
- 后续若需要医生精细审核，可在第二阶段从合并字段再派生细字段，但不得在前端从 OCR 文本自行推断。

## T/J 字段语义

`T` 字段映射为原文截取型：

```json
{
  "value": "反复咳嗽、咳痰15年",
  "status": "found",
  "evidence": []
}
```

`J` 字段映射为状态判断型：

```json
{
  "value": "异常",
  "status": "abnormal",
  "evidence": []
}
```

状态建议：

- `T`：`found`、`not_found`、`uncertain`。
- `J`：`normal`、`abnormal`、`not_mentioned`、`uncertain`。

前端审核页需要明确区分：

- 原文截取字段：医生审核文本值。
- 状态判断字段：医生审核正常/异常/未提及状态，必要时编辑备注或值。

## 证据方案

推荐采用混合方案：

- prompt 层沿用师弟的锚点范围：`p: ["<s3>", "<s5>"]`。
- 适配层维护 `anchors.json`，记录每个锚点对应的文本、offset、页号或来源文件。
- 持久化层输出审核证据结构，前端不直接依赖 `<sN>`。

`anchors.json`：

```json
{
  "<s3>": {
    "id": "s3",
    "text": "主诉：反复咳嗽、咳痰15年。",
    "start_offset": 18,
    "end_offset": 35,
    "page_no": 1,
    "source_file": "page_001.jpg"
  }
}
```

审核证据：

```json
{
  "id": "s3-s5",
  "text": "主诉：反复咳嗽、咳痰15年。现病史：...",
  "start_offset": 18,
  "end_offset": 96,
  "page_no": 1,
  "anchor_start": "<s3>",
  "anchor_end": "<s5>"
}
```

如果锚点不存在、范围非法或无法映射 offset：

- 字段不直接导致任务失败。
- 字段标记为需要人工重点核验。
- 医生提示使用中文自然语言，例如“来源证据定位失败，请核对原文”。

## 后端适配器

新增 `QwenBatchAlgorithmPort` 或等价适配器，职责：

- 根据任务图片创建 job 输入目录。
- 写入 `manifest.json`。
- 启动算法引擎，或调用常驻批处理服务。
- 等待结果并设置超时。
- 读取 `merged_ocr.txt`、`merged_structured.json`、`anchors.json`、`summary.json`。
- 转换为工作站 `document_result` 和审核字段。
- 将失败映射为任务失败。

失败映射：

- job 创建失败：`ALGORITHM_MODULE_FAILED`。
- vLLM 服务不可达：`ALGORITHM_MODULE_FAILED`。
- OCR 全空：任务失败。
- `merged_structured.json` 缺失或 JSON 非法：任务失败。
- 字段全空：任务失败。
- 单字段证据定位失败：字段重点核验，不阻断任务。

## 算法运行形态

第一阶段允许后端以子进程或 Docker run 方式调用 batch engine，降低改造成本。

第二阶段再评估是否改成长驻算法服务：

```text
POST /jobs
GET /jobs/{job_id}
GET /jobs/{job_id}/result
```

不建议第一阶段就把师弟脚本改成 Flask/FastAPI 服务，因为这会增加同步上游代码的成本。

## 前端影响

审核页需要从扁平固定字段扩展为支持 schema 驱动的嵌套章节展示：

- 章节按中文 schema 展示。
- `T` 字段展示文本编辑框。
- `J` 字段展示正常、异常、未提及状态控件。
- 字段证据点击后跳转 OCR 文本高亮。
- 证据异常字段显示黄色重点核验提示。

第一阶段可以不追求复杂视觉重构，但必须保证：

- 医生能看到所有字段。
- 医生能修改字段值或状态。
- 医生能看到 OCR 原文和证据定位。
- 导出至少能按新字段 schema 输出。

## 离线部署

师弟仓库当前 Dockerfile 存在构建期联网行为：

- apt 使用外部镜像源。
- pip 从公网镜像安装依赖。
- compose 使用 `vllm/vllm-openai:latest`。

并入工作站后必须调整：

- 正式离线部署不得依赖运行时联网。
- vLLM 镜像需要固定版本或 digest，并纳入离线镜像包。
- Python client 镜像依赖需要使用离线 wheelhouse 或预构建镜像。
- 模型权重仍通过 `models/llm/` 本地只读挂载。
- `input/`、`output/`、`logs/`、`vllm_cache/` 均为运行目录，不提交真实内容。

## 后续同步策略

上游同步原则：

- `algorithms/qwen_batch_engine/upstream/` 只做必要最小改动。
- `algorithms/qwen_batch_engine/overlay/` 保存本项目补丁、配置覆盖和 prompt 适配记录。
- 本项目私有包装放在 `algorithms/qwen_batch_engine/adapter/`。
- 每次同步记录上游 commit 到 `VERSION` 和 job manifest。
- 每次 overlay 变更记录到 `overlay/CHANGELOG.md`，说明原因、影响字段、是否改变核心抽取语义和回归结果。
- 同步后先跑算法适配器契约测试，再做工作站端到端测试。

建议同步流程：

```text
1. 拉取 aufgh/qwen 新提交到 /tmp
2. 对比 upstream/ 差异
3. 更新 algorithms/qwen_batch_engine/upstream/
4. 重新套用 overlay/ 中的配置、prompt 和补丁
5. 若输出结构变化，只改 adapter/normalize_result.py
6. 跑后端适配器测试和一条离线样例验收
```

## 分阶段实施

### 第一阶段：引擎落仓与 job 适配

- 新增 `algorithms/qwen_batch_engine/`。
- 保留上游批处理脚本和配置。
- 新增 `overlay/`，把 prompt 适配、证据 offset 记录和离线配置覆盖放在可审计补丁区。
- 新增 job manifest、result normalize、anchors offset 回填。
- 后端能对单个工作站任务创建 job 并读取成功结果。
- 测试覆盖成功、OCR 全空、JSON 非法、字段全空、证据锚点缺失。

### 第二阶段：审核页和导出切换

- 新增 `qwen_batch_admission_record.v1` schema。
- 前端审核页支持中文嵌套章节和 `T`/`J` 字段。
- 导出支持新字段 schema。
- 保留原始 `merged_structured.json` 供排查。

### 第三阶段：部署离线化和同步治理

- 固定 vLLM 镜像版本。
- 构建离线 client 镜像或 wheelhouse。
- 更新 Windows 启停脚本。
- 增加算法版本展示和健康检查。

## 风险与缓解

- 风险：算法输出中文 key 改名会破坏前端和导出。
  - 缓解：内部 schema 使用稳定 `field_key`，中文路径只作为映射来源。
- 风险：上游批处理脚本和工作站任务状态机运行模型不同。
  - 缓解：通过 job adapter 隔离，不让后端路由直接依赖脚本内部函数。
- 风险：证据锚点只有文本，没有审核 offset。
  - 缓解：适配层生成 `anchors.json` 并补齐 offset/page。
- 风险：并发策略可能与工作站 GPU 队列冲突。
  - 缓解：第一阶段一个工作站任务对应一个 batch job，任务级串行；后续再开放多 job 并发。
- 风险：离线部署被公网依赖破坏。
  - 缓解：正式部署前替换 `latest` 镜像和联网 pip/apt。

## 验收标准

- 后端可以把一个工作站任务转成 qwen batch job，并读取算法输出。
- OCR 原文来自 batch engine 的合并结果。
- 字段展示按 `qwen_batch_admission_record.v1` 中文嵌套 schema。
- 字段证据可在 OCR 文本中高亮，锚点异常时显示人工核验提示。
- 算法模块目录与后端适配层分离，便于后续同步上游。
- 测试不依赖真实模型、真实患者数据或联网。
- 离线部署文档明确正式镜像和依赖不得使用公网 `latest` 或构建期下载。
