# 验证器规范化（Verifier Normalization）设计

> 日期：2026-08-01
> 状态：设计已批准
> 关联：评估体系第一步 `docs/superpowers/specs/2026-08-01-evaluation-harness-design.md`
> 分支：eval-harness（与第一步同分支，最后统一合入 master）

## 1. 背景与动机

第一步评估体系跑出首个基线（status 98.09% / value 88.32% / 幻觉 43 / 任务级 0/6），暴露三类问题：

1. **复核器是死代码**：`prompts.py` 的 `build_verification_prompt` / `build_adversarial_verification_prompt` 已无调用方，但审核链路（quality_flags → verification_status=suspicious → attention_required → 审核页）是活的——复核器的设计意图从未接入活动路径。
2. **指标有误报**：幻觉判定把"否定短语重建"（金标 value 在 OCR 不可定位）误报为幻觉；J 型字段"正常" vs "鼻腔通畅"语义等价被判 mismatch；长文本字段摘录范围差异判定过严。
3. **审核数据没有回流**：医生在审核页的修正值只留在 review_result.json，没有变成可复用的金标资产。

第二步目标：把复核器接入活动路径并校准（kappa≥0.7）、医生审核数据回流为金标活资产、修正三个指标误报。

## 2. 目标与边界

### 目标

1. 复核器接入活动路径：抽取 → 复核 → 可疑字段进审核页，可消融对比（--no-verifier）；
2. 验证器校准：kappa ≥ 0.7 后上岗；
3. 审核数据回流：医生修正 → 脱敏 → 金标活资产（source: review，与 manual 分开统计）；
4. 指标修正：幻觉豁免 / J 型语义归一 / 长文本核心句重合；
5. prompt 消息结构适配 Qwen ChatML：system（规则）+ user（数据）分层；
6. thinking 消融开关（--thinking），用评估体系实测 CoT 收益。

### 边界（明确不做）

- 分歧触发定向重抽取（二次抽取）——复核意见只做标记，不重抽；
- 复核意见原文展示给医生——LLM 复核文本不进前端（防误导），前端沿用规则化 attention_message；
- 抽取轨迹日志落盘（第三步）；
- 换模型 / 换温度制造复核独立性——本地单一 Qwen 模型、温度恒为 0.0（可复现是校准的前提）；
- 复核器对 not_found 字段复核（漏抽由审核页兜底）。

## 3. 复核器设计

### 3.1 位置与形态

- 新模块 `app/backend/services/copd_extraction/verifier.py`：`FieldVerifier` 类。
- 输入：`candidates`（抽取结果）+ `document_text` + `schema` + `llm_client`；输出：复核意见（按字段 verdict）。
- 复核范围：**status=found 且 value 非空**的字段。not_found / 空值字段不复核。
- 接入：`runner.run_pipeline` 增加 `apply_verify` 开关（复用 `apply_quality` 模式）；`port.extract` 增加可注入 verifier（生产路径接入）；`run_eval` 增加 `--no-verifier` 消融。
- 复核器输出映射：verdict=suspicious/fail → 新增 quality_flags（flag 名 `verifier_suspicious`，附加 reason_code）→ `verification_status=suspicious` → `attention_required=True`，attention_message 新增固定纯中文提示"复核器标记，请核对原文"（复用 attention_message 展示通道，不接入 admission_contract 的现有规则分支），LLM 复核文本只留在 quality_flags 内部审计。

### 3.2 Prompt 结构（ChatML 分层 + 防锚定布局）

**system（完全固定，前缀缓存友好）**：
- 身份：字段级复核器；
- 缺陷清单：否定翻转、OCR 标签混淆（P62/P02、嗜托溴铵/噻托溴铵、单位符号）、数值矛盾（单数字脉率/呼吸、体重下降零值）、OCR 纠偏合理性、生理范围；
- verdict 契约：pass/suspicious/fail + reason_code（ocr_quality_issue / extraction_mistake / evidence_insufficient / none）+ checks（value_semantically_supported / no_hallucination_or_inference / ocr_correction_justified）+ comment（≤40 汉字）+ **必须引用 evidence 编号作为依据**；
- 对抗精神：对每个字段先主动找茬，找不到茬才给 pass（吸收对抗性复核的锐度，保持 verdict 可校准形态）；
- few-shot：pass 和 suspicious 各一个结构示例（占位内容，防照抄）。

**user（变量区）**：evidence 在前（原文证据，带编号）→ 字段在后（field_key + 声称的 value + 引用的 evidence_ids）。
布局理由：
- 防"找补"：字段值在前会让复核器顺着值找证据支持（确认偏误）；evidence 在前，模型先形成自己的判断；
- 注意力引导：evidence 先出场，第一遍 pass 就是扫原文；
- 前缀缓存：system 固定 + user 变量，命中率最大化。

### 3.3 同源模型缓解

抽取与复核是同一 Qwen 模型、同一温度 0.0（可复现）。系统性偏差无法消除，缓解手段全部在上下文：

1. evidence 前置防锚定（3.2）；
2. 缺陷清单显式枚举已知易错点；
3. 每条可疑 verdict 必须引用 evidence 编号（拿原文说话）；
4. verdict 型主干 + 对抗精神（先找茬再放行）。

### 3.4 Thinking 消融（--thinking）

- `run_eval` 增加 `--thinking` 开关：开启时 chat_template_kwargs `enable_thinking=True`（关闭时保持 False）。
- 用途：实测 CoT 对抽取/复核质量的真实增益与代价（输出预算挤占、json_object 兼容性、时长）。
- 默认值：抽取器先保持 off（61 字段 JSON 输出预算风险），复核器倾向 on（verdict 输出小、推理任务收益大）——最终由实测决定，不拍脑袋。

## 4. 消息结构改造（Qwen ChatML 适配）

现状问题：`QwenVLLMClient.complete_json`（`algorithm_ports/qwen_vllm_client.py:148-151`）把整个 prompt 塞进一条 user 消息；system 内容（身份/规则/契约）与数据混在一起。OCR 路径（`complete_text_from_image`）已是 system+user 双消息，抽取路径反而没有。

改动：

- `complete_json` 签名扩展支持 system + user 分离（保持向后兼容：不传 system 时行为不变）；
- `build_admission_structured_fields_prompt` 拆为 system（身份+硬约束+固定字段表+输出契约+【再次强调】）与 user（evidence_units + OCR 原文）；
- 复核 prompt 同构拆分（3.2）；
- `enable_thinking=False` 保持为默认（thinking 由 --thinking 开关控制）；
- `response_format=json_object` 保持不变。

## 5. 验证器校准

### 5.1 人工金标集（复核器金标）

- 来源：现有 6 份金标样本跑真实抽取 + 复核，产出字段级 verdict（约 30-40 条/份，共约 180 条）；
- 单位：字段级——人工对每条 verdict 裁定"该字段是否应被标记可疑"（与字段金标不同维度：金标裁值对错，校准集裁可疑性）；
- 工具：`evaluation/calibrate.py`——跑复核 → 导出人工裁定模板（JSON/CSV，含 case_id/field_key/verdict/reason_code/comment/原文证据片段）→ 人工裁定 → 计算 Cohen's kappa（verdict 二值化：suspicious|fail vs pass，与人工裁定 2×2）。

### 5.2 上岗门槛

- kappa ≥ 0.7 才允许复核器接入活动路径（生产与评估共用同一 verifier 实现）；
- 校准不达标 → 迭代 prompt（缺陷清单 / few-shot / 布局）重测，不达标不接入；
- 校准集文件与裁定结果存 `data/evaluation/calibration/`（运行数据，不进 git）。

## 6. 审核数据回流

### 6.1 采集（review_service 改动）

- 触发：`complete_review`（审核确认）时聚合；
- 范围：`auto_value ≠ final_value` 的字段（医生实际修正过；确认字段与抽取一致不新增信息）；
- 记录：field_key / status / 抽取原值（auto_value）/ 医生修正值（final_value）/ task_id / 修正时间；status 规则：修正值非空记 `found`，修正值为空串（医生清空误值）记 `not_found`——"医生认为该字段不存在"本身是金标信号；
- 落盘：`data/evaluation/review_feedback/<task_id>.json`（运行数据，含患者信息，不进 git）。

### 6.2 脱敏

- 轻量正则脱敏：手机号、身份证、住院号、11 位数字串；日期保留（病历日期是抽取语义的一部分）；
- 位置：回流原始文件不脱敏（运行数据），**脱敏发生在生成金标活资产时**；
- 工具：`evaluation/` 模块内的脱敏函数（有单测），不单独成脚本。

### 6.3 金标活资产（source: review）

- 形态：增量修正字段文件（不要求 61 字段全量），每任务一份：`data/evaluation/golden_review/<task_id>.json`；
- 字段：case_id / field_key / status / value（医生修正值）/ source: "review"（与 manual 分开统计）；
- 评估消费：`evaluation` 工具按 source=review 子集单独统计"修正字段错误率"——修正字段=抽取器易错字段，盯住它们就是盯住实际伤害；评估报告单独一节。

## 7. 指标修正（metrics.py）

### 7.1 幻觉豁免（否定短语重建误报）

现状：`value_located_in_text` 要求 value 在 ocr_text 可定位；"否认糖尿病病史"（重建自"否认'糖尿病'、'冠心病'等病史"）不可定位 → 误报幻觉。

修正：评估时先测**金标 value** 在 ocr_text 的可定位性——金标不可定位 → 该字段跳过幻觉判定（期望输出本身就是重建短语，抽取器输出同款重建不该判幻觉）。真错误（金标不可定位但抽取值不同）由 value_mismatch 兜底捕获。

### 7.2 J 型字段语义归一

现状：金标"鼻腔通畅"、抽取"正常"，归一化后不同 → mismatch。

修正：从 schema 加载 J 型字段清单（`qwen_type=J` 或 `review_control=judgement`），仅这些字段的 value 判定前做"正常族"归一：正常 / 通畅 / 未见异常 / 无异常 / 阴性 / 无压痛 等表述 → 同一 token。非 J 型字段不受影响。

### 7.3 长文本字段核心句重合

现状：金标摘 A 段、抽取摘 B 段（语义等价）→ mismatch。

修正：按字段 key 配置长文本清单（初始：hpi_* 现病史类 + chief_complaint），这些字段的 value 判定改为**核心句重合率**：金标与预测按句切分，共有句占比 ≥ 0.6 判对。容忍摘录范围差异，不放过大面积错摘。清单模块级常量，可扩展。

### 7.4 口径影响

三处修正都会改变 value_accuracy 统计口径 → **修正后基线重跑**（评估报告 meta 记录指标版本号，对比时显式标注）。

## 8. 评估执行

### 命令形态

```
python -m app.backend.evaluation.run_eval \
  --golden data/evaluation/golden \
  --schema app/config/schemas/admission_record_structured_fields.v1.yaml \
  --model <模型名> \
  [--no-verifier] [--no-quality-flags] [--no-contract] [--thinking]
```

### 消融矩阵（第一步接口 + 本步新增）

| 开关 | 含义 |
|---|---|
| --no-quality-flags | 跳过薄规则 quality_checks |
| --no-contract | 跳过契约校验 |
| --no-verifier | 跳过复核器（新） |
| --thinking | 开启 Qwen thinking 模式（新） |

典型对比：`--no-verifier` vs 默认（复核器对质量指标的影响）；`--thinking` vs 默认（CoT 收益与代价）。

## 9. 与现有代码的关系

- 复用：`build_admission_structured_fields_prompt`（拆分 system/user）、`validate_qwen_payload`、`map_qwen_fields_to_review_candidates`、`apply_quality_checks`、`run_pipeline`（加 apply_verify 开关）、`evaluate_sample` / `build_report`（加 review 子集统计）；
- 新增：`copd_extraction/verifier.py`、`evaluation/calibrate.py`、回流采集（review_service）、脱敏函数（evaluation/）、金标活资产消费；
- 改动：`prompts.py`（拆层 + 复核 prompt 激活）、`qwen_vllm_client.py`（complete_json 支持 system+user）、`review_service.py`（complete_review 聚合回流）、`metrics.py`（三处修正）、`run_eval.py`（--no-verifier / --thinking）。

## 10. 测试约定

- verifier 单测：fake LLM 注入，覆盖 verdict 解析失败、无 found 字段（空复核）、suspicious 映射到 quality_flags / attention_required；
- 指标修正单测：合成数据覆盖幻觉豁免（金标不可定位）、J 型归一（"正常" vs "鼻腔通畅"）、长文本重合率（0.6 阈值边界）；
- 回流单测：complete_review 聚合（修正/未修正/空值修正）、脱敏正则（手机号/身份证/住院号）；
- ChatML 拆层单测：system/user 内容划分正确、向后兼容（不传 system 行为不变）；
- thinking 消融：单元层只测开关传递（chat_template_kwargs），真实收益由 run_eval 实测报告，不做 LLM 依赖断言；
- 全量 pytest 保持通过（既有 5 个失败与本工作无关，勿修）。

## 11. 实施顺序建议

1. 消息结构改造（complete_json system+user、抽取/复核 prompt 拆层）——一切 prompt 工作的地基；
2. 指标修正（metrics.py 三处 + 单测）——重跑基线，得到修正后基线；
3. 复核器（verifier.py + prompts 激活 + run_pipeline/port 接入 + --no-verifier 消融）；
4. 校准（calibrate.py + 人工裁定 + kappa）；
5. 回流（review_service 聚合 + 脱敏 + 金标活资产 + 评估子集统计）；
6. thinking 实测（--thinking 消融 + 报告对比）。
