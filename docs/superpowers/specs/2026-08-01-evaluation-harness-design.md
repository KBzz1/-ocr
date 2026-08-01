# 评估体系（Evaluation Harness）设计

> 日期：2026-08-01
> 状态：设计已批准
> 关联：`docs/superpowers/plans/` 实施计划待写

## 1. 背景与动机

本项目是离线病历文书结构化采集与人工核验工作站，COPD 入院记录抽取核心位于 `app/backend/services/copd_extraction/`。当前管线形态为**单次 LLM 调用**：prompt 组装 → `complete_json` → 契约校验 → evidence 回填 → quality_flags → 人工审核页兜底。

借鉴《AI Agent 实战营》教材（bojieli/ai-agent-book）第 6 章评估方法论，对照现状得出：

- 当前 harness 的"能做事"层（抽取流程）已简单干净；缺失的是**评估与回归机制**——没有任何正确率度量，每次改 prompt 都是凭感觉，无法回答"这次改动真的变好了吗"。
- 本项目的最大需求是**准确性**（离线、无工具调用、无多 agent、无记忆），评估体系正是"准确性"的工程化度量。
- 项目已有黄金资源：医生审核修正后的字段结果、人工标注数据 `data/text_data/`（6 份干净病历 ground_truth + 对应 OCR 结果）——可直接提炼为字段级金标。

## 2. 目标与边界

### 目标

建立"评估 = 金标比对 + 字段级指标 + 回归基线"的最小闭环，让每次 prompt / 模型变更都有度量支撑：

1. 一套字段级金标评估集（6 份起步，可扩展）；
2. 五个确定性指标（不依赖 LLM 打分）；
3. 可重复执行的评估脚本，支持模型替换实验与消融变体参数；
4. 基线快照 + prompt 回归对比机制。

### 边界（明确不做）

- 审核数据自动回流（第二步"验证器规范化"再做）；
- 复核器接入活动路径（第二步）；
- 抽取轨迹日志落盘（第三步）；
- LLM-as-a-Judge 评分器（有金标，确定性比对优先）；
- 多 agent / 记忆 / 上下文压缩 / 工具安全（本项目场景不需要）。

## 3. 评估集（golden set）

### 位置

- 金标目录：`data/evaluation/golden/case_001.json` ~ `case_006.json`
- `data/` 已在 `.gitignore` / `.git/info/exclude` 排除，金标为运行数据不进 git 仓库。
- 评估报告目录：`data/evaluation/reports/`（同样不进 git）。

### 样本格式

```json
{
  "case_id": "case_001",
  "ocr_text": "<ocr_results/1.txt 原文>",
  "pitfalls": ["negation", "ocr_typo"],
  "golden": [
    {"field_key": "chief_complaint", "status": "found", "value": "反复咳嗽、咳痰20年，喘累2年，加重10余天"},
    {"field_key": "pmh_diabetes", "status": "found", "value": "否认糖尿病病史"}
  ]
}
```

- `status` 只允许 `found` / `not_found` / `uncertain`，与抽取契约一致。
- `golden` 必须覆盖 schema 全部 61 字段（`app/config/schemas/admission_record_structured_fields.v1.yaml`），未提及的字段为 `not_found` + 空 value。

### 金标生成流程

1. 从 `data/text_data/ground_truth/*.txt` 干净病历文本提炼 61 字段初稿（提炼脚本放 `scripts/` 下，一次性使用）；
2. 同时生成每份病历的 **OCR 差异清单**（ground_truth 与 `ocr_results` 的文本差异，供人工快速定位错读处）；
3. 用户（医生视角）复核初稿，重点裁定 OCR 错读处的预期输出（保留原文 / uncertain / ocr_correction）；
4. 裁定结果回写金标，以裁定为准修正金标 value。

### 质量控制（宁少勿滥）

- 6 份起步；每份标注 `pitfalls` 陷阱类别：`negation`（否定表达）、`ocr_typo`（OCR 错读）、`numeric_conflict`（数值矛盾）、`diagnosis_numbering`（诊断编号）、`blood_gas_shared_evidence`（血气共享证据）、`aux_missing`（辅助检查缺失）。
- 指标报告按陷阱类别分组，诊断具体能力短板。

## 4. 指标设计

核心原则：**能用确定性比对就不用 LLM 打分**。61 个字段按判定策略分三类。

### 指标 1：status 判定准确率

`found / not_found / uncertain` 与金标一一比对（完全确定性），按字段、按陷阱类别分组统计。金标 found 而抽取 not_found = 漏抽（召回损失）；金标 not_found 而抽取 found = 多抽（幻觉风险）。

### 指标 2：value 正确率（归一化两级判定）

- **归一化一致**：去空白、全半角、标点后完全一致 → 正确；
- **互为子串**：归一化后预测值是金标的子串（或反之）→ 正确（截断摘录视为合理）；
- 两者都不满足 → 疑似错误，进错误明细，由人工逐条裁定；裁定结果回写金标；
- 金标 status 为 `not_found` 时不做 value 比对（预测 value 必须为空字符串，非空即错）；`uncertain` 的 value 不做严格比对，仅计入 status 指标。

### 指标 3：幻觉率（veto 维度，不需要金标）

**value 必须在 `ocr_text` 中可定位**（归一化子串查找）。value 中出现 OCR 原文没有的内容 = 幻觉/补造，违反项目硬约束"不得补造字段"。完全确定性判定，与金标无关。例外：该字段 `ocr_correction` 非空时，以修正链判定——修正后的 value 若与 OCR 原文 + 修正理由一致则不记幻觉（OCR 错读纠偏是受控行为，非补造）。

### 指标 4：任务级成功率（严格，仅参考）

61 字段 status 全对 + value 全对 = 成功。样本 6 份时方差极大，报告标注噪声带宽，不作为主线指标。

### 指标 5：契约非法率

`validate_qwen_payload` 失败比例（任务进 `failed` 的源头之一）。

### 统计显著性

报告标注样本量与噪声带宽（√(p(1-p)/n)）；指标 diff 小于带宽不视为改进。主线盯字段级指标而非任务级。

## 5. 评估执行

### 命令形态

```
python -m app.backend.evaluation.run_eval \
  --golden data/evaluation/golden \
  --model <模型名> \
  [--no-quality-flags] [--no-contract]
```

- 复用 `COPDAdmissionQwenFieldPort`（`app/backend/services/copd_extraction/port.py`），注入真实 vLLM 客户端（`OpenAICompatibleJsonClient`）；
- 每条样本跑完整管线（prompt 构建 → LLM → 契约校验 → evidence 回填 → quality_flags），收集 payload / candidates，与金标比对；
- 评估脚本不引入业务代码侵入，与 pytest 单测（注入 fake client）互不干扰。

### 模型替换实验

`--model` 切参同命令跑两遍，报告直接可比（报告头部记录模型名）。

### 消融开关（第一步只立接口）

- `--no-quality-flags`：跳过 quality_flags 处理；
- `--no-contract`：跳过契约校验。
- 诚实声明：当前活动管线这些层不改 value（质控只加标记、契约只拦失败），现有消融对比收益有限；接口先立是书里"消融开关必须从第一天设计进架构"的要求，真正用武之地是第二步复核器接入后的"有复核 vs 无复核"对比。

## 6. 报告与回归机制

### 报告输出

- 控制台汇总：总表（5 指标）+ 按字段分组表 + 按陷阱类别分组表；
- JSON 落盘 `data/evaluation/reports/<日期>_<prompt版本>_<模型>.json`，含逐字段错误明细；
- 报告头部记录：prompt 版本（`ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION`）、模型名、schema 版本、参数、样本数。

### 回归流程（写进工作方式）

1. 首次跑通后的报告存为基线（`baseline_<prompt版本>.json`）；
2. 修改 `prompts.py`（prompt 改动视为契约变更）→ 跑评估 → 与基线对比（指标 diff + 字段错误明细 diff）→ 有收益才合入；
3. diff 小于噪声带宽不视为改进。

## 7. 与现有代码的关系

- 复用：`COPDAdmissionQwenFieldPort`、`build_admission_structured_fields_prompt`、`validate_qwen_payload`、`map_qwen_fields_to_review_candidates`、`apply_quality_checks`、schema loader；
- 新增：`app/backend/evaluation/`（run_eval 脚本 + 指标比对模块）；
- 不改动：`copd_extraction/` 业务代码、pytest 测试、schema、prompt 契约；
- 金标提炼脚本放 `scripts/` 下（一次性），评估脚本放 `app/backend/evaluation/`（可重复）。

## 8. 测试约定

- 指标比对逻辑（归一化、子串判定、幻觉定位、分组统计）需要有 pytest 单测，注入合成数据，不依赖真实 LLM；
- 评估脚本本身用手写 fixture 冒烟（不需要真实推理即可验证脚本链路），真实推理跑数据 `data/evaluation/golden/`。
