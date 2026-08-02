# 复核器召回优化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按职责划分修复复核器召回（kappa 0.0834 不达标）：复核器 prompt 3 句措辞强化 + 2 个 few-shot 行为示例 + 抽取 pe_* 字段表描述精确化，step5 实验验证漏检 18 → 显著下降（先修召回，不设 0.7 硬线）。

**Architecture:** 两段 prompt 各加"有效载荷"：复核器在既有通用原则上追加阈值句/逻辑一致性/有证据不豁免，并新增 2 个行为示例（值忠实摘录但含错读 → 标记；值与他句矛盾 → 标记）；抽取侧 schema 加 description 元数据（13 条 pe_*），字段表渲染追加"；仅：<description>"。system 保持完全固定（前缀缓存前提不变），温度 0.0。

**Tech Stack:** Python 3.12 / Flask / pytest / vLLM OpenAI-compatible 客户端 / conda 环境 `manzufei_ocr`

## Global Constraints

- 测试命令一律：`conda run -n manzufei_ocr python -m pytest <path> -v`（在 worktree 根目录执行）
- 单测必须注入 fake LLM 客户端，不依赖真实 vLLM 服务
- Git commit message 使用中文
- 温度恒为 0.0；system 文本必须完全固定（不含任何 evidence/document_text 变量数据），变量数据只进 user
- prompt 改动视为契约变更：每次改动同步更新对应单测断言（test_copd_prompts.py / test_copd_verifier.py）
- 不改 evidence_units 切分逻辑；不改 reason_code 枚举（示例 2 复用现有 extraction_mistake）；不动 schema 字段体系（只加 description 元数据）
- 越界/边界表述各一句话，不列 case 级示例堆（宁少勿滥）
- 工作区已有未提交修改（`app/backend/tests/test_review_routes.py`、`app/backend/tests/test_qwen_batch_engine_layout.py`）与本工作无关，勿动勿提交
- 全量 pytest 既有失败（test_review_routes 4 + test_qwen_batch_engine_layout 1）与本工作无关，勿修
- 实验类任务（Task 3/4）由协调者（主 agent）执行，subagent 只做代码与单测
- 设计权威：`docs/superpowers/specs/2026-08-02-verifier-recall-optimization-design.md`（措辞逐字用 spec 3.1/3.2 节，本 plan 引用其定稿文本）

---

### Task 1: 复核器 prompt 召回强化（3 句 + 2 示例）+ 单测更新 + 文档同步

**Files:**
- Modify: `app/backend/services/copd_extraction/prompts.py`（`build_verification_messages` system 内【通用原则】与 few-shot 区）
- Modify: `app/backend/tests/test_copd_verifier.py`
- Modify: `docs/superpowers/specs/2026-08-01-verifier-normalization-design.md`（3.2 节通用原则措辞同步，最小化编辑）

**Interfaces:**
- `build_verification_messages(evidence_units, fields, append_reminder=False) -> tuple[str, str]` 签名不变；仅 system 文本内容变化
- 其他调用方（FieldVerifier / runner / calibrate）零改动

**措辞定稿（逐字用，来自 spec 3.1）：**

修改 1 — 原则 3（OCR 识别错误那条）句尾追加：
```
长文本字段按句拆分编号，必须逐句扫读全值，不得因整体语义通顺而放行。错读/病句/叠字等表达瑕疵：影响理解或产生歧义 → 必须标记；不影响语义理解的轻微重复可不标。值忠实摘录原文不豁免错读检查——值一致只证明抄得对，不证明文本本身没问题。
```

修改 2 — 原则 4（数值矛盾或异常那条）整条替换为：
```
- 数值矛盾或逻辑不一致：同段存在与字段值不一致的数值、数值超出合理范围疑似 OCR 截断（99→9）、反直觉数值（体重下降 0g）；值内部自相矛盾、值与他句/他证据矛盾（时间归属错误、否定翻转、体征互斥）、数值关系不合理（如氧合指数与 PO2/FiO2 明显不符）→ 均应标记。
```

修改 3 — 原则 7（字段越界那条）句尾追加：
```
字段越界：值的内容域与字段对应部位明显不符（如眼部字段出现一般情况内容）→ 标记为 extraction_mistake，引用原文片段即可。字段越界不因值有证据支持而豁免——证据同源只证明原文有这段话，不证明它属于该字段。
```

修改 4 — few-shot：在现有"输出示例"之后、`反例`之前，追加两个示例（标注沿用现有"示例仅示范结构，字段内容为占位，不得照抄"约定）：
```json
{"verifications": [{"field_key": "pe_eyes", "verdict": "suspicious", "reason_code": "ocr_quality_issue", "checks": {"value_semantically_supported": false, "no_hallucination_or_inference": true, "ocr_correction_justified": true}, "comment": "e005 值忠实摘录原文，但'双眼粗侧视力正常'中'粗侧'为 OCR 错读（应为'粗测'）"}]}
```
```json
{"verifications": [{"field_key": "pe_abdomen", "verdict": "suspicious", "reason_code": "extraction_mistake", "checks": {"value_semantically_supported": false, "no_hallucination_or_inference": true, "ocr_correction_justified": true}, "comment": "e012 同段既有'腹部正常，肝脾肋缘下未扪及'，值却写'腹部移动性浊音阳性'，两处矛盾，疑否定翻转"}]}
```

**注意：修改 2 替换了原则 4 原文**——先读 `app/backend/tests/test_copd_verifier.py` 现有断言，若有断言旧措辞（如"数值矛盾或异常"、"体重下降"等子串）必须同步适配；改完后 grep 确认无旧措辞残留断言。

- [ ] **Step 1: 写失败测试**（在 test_copd_verifier.py 追加或适配）

```python
def test_verifier_principle_threshold_for_expression_noise():
    system, _ = build_verification_messages([], [])
    assert "影响理解或产生歧义 → 必须标记" in system
    assert "值忠实摘录原文不豁免错读检查" in system

def test_verifier_principle_logic_consistency():
    system, _ = build_verification_messages([], [])
    assert "数值矛盾或逻辑不一致" in system
    assert "时间归属错误、否定翻转、体征互斥" in system

def test_verifier_principle_boundary_no_evidence_exemption():
    system, _ = build_verification_messages([], [])
    assert "字段越界不因值有证据支持而豁免" in system

def test_verifier_fewshot_recall_examples_present():
    system, _ = build_verification_messages([], [])
    assert "'粗侧'为 OCR 错读（应为'粗测'）" in system
    assert "值却写'腹部移动性浊音阳性'，两处矛盾" in system
    assert system.count("示例仅示范结构，字段内容为占位，不得照抄") >= 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py -v`
Expected: 新 4 个测试 FAIL（断言子串不存在）；如有既有断言因原则 4 改写而 FAIL，记录之（Step 4 一并适配）

- [ ] **Step 3: 实现 4 处措辞修改**（prompts.py `build_verification_messages`，逐字用上述定稿；保留【通用原则】其余条文与【输出契约】不动）

- [ ] **Step 4: 适配旧断言 + 跑通全文件**

先 grep `数值矛盾或异常` 与 `体重下降` 在 test_copd_verifier.py 的残留断言并适配为新措辞；然后：
Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py -v`
Expected: 全绿（含既有断言 + 新 4 个）

- [ ] **Step 5: 文档同步 2026-08-01 spec 3.2 节**

`docs/superpowers/specs/2026-08-01-verifier-normalization-design.md` 3.2 节"缺陷清单"描述同步为新措辞（数值矛盾→逻辑一致性、错读职责含阈值句、越界含不豁免句、few-shot 4 个示例），最小化编辑，不重写整节。

- [ ] **Step 6: Commit**

```bash
git add app/backend/services/copd_extraction/prompts.py app/backend/tests/test_copd_verifier.py docs/superpowers/specs/2026-08-01-verifier-normalization-design.md
git commit -m "refactor:复核器召回强化(表达瑕疵阈值句+逻辑一致性扩展+越界不豁免+2个行为示例)+单测与文档同步"
```

**验证:** 复核器 system 新旧字符数对比（改前 2027 → 改后记录实测）；test_copd_verifier.py 全绿。

---

### Task 2: 抽取 pe_* 字段表描述精确化（schema + 渲染）+ 单测更新

**Files:**
- Modify: `app/config/schemas/admission_record_structured_fields.v1.yaml`（13 个 pe_* 字段加 `description`）
- Modify: `app/backend/services/copd_extraction/prompts.py`（`build_admission_structured_fields_messages` 字段表渲染：约 184 行 `table_lines.append` 处）
- Modify: `app/backend/tests/test_copd_prompts.py`

**Interfaces:**
- schema 字段条目新增可选键 `description: str`；缺省时渲染不变（向后兼容）
- 渲染格式：有 description → `- [组] field_key（label）；仅：<description>`；无 → 原样 `- [组] field_key（label）`

**description 定稿（13 条，逐字用，来自 spec 3.2）：**

| field_key | description |
|---|---|
| pe_skin | 皮肤项目：颜色、皮疹、弹性、毛发、淋巴结；不含一般情况内容 |
| pe_eyes | 眼部项目：睑结膜、球结膜、巩膜、角膜、瞳孔、对光反射、视力；不含头颅、头发、颜面、耳鼻口颈内容 |
| pe_ears | 耳部项目：外耳道、鼓膜、听力、乳突；不含眼、鼻、口咽内容 |
| pe_nose | 鼻部项目：鼻腔、鼻窦、鼻翼、鼻通气；不含耳、口腔内容 |
| pe_oral_cavity | 口腔咽喉项目：唇、齿、龈、舌、口腔黏膜、咽、扁桃体；不含颈部、耳鼻内容 |
| pe_neck | 颈部项目：颈静脉、颈动脉、甲状腺、气管、颈软、淋巴结；不含口腔、胸部内容 |
| pe_chest | 胸廓项目：胸廓形态、肋间隙、胸骨、挤压试验；双肺内容归呼吸系统检查，乳房内容归乳房字段 |
| pe_breast | 乳房项目：对称、发育、乳头、皮肤、包块；不含胸廓、双肺内容 |
| pe_respiratory_exam | 呼吸系统项目：呼吸动度、语颤、叩诊音、呼吸音、啰音；不含胸廓形态、乳房内容 |
| pe_cardiac_exam | 心脏项目：心前区、心尖搏动、心界、心率、心律、心音、杂音 |
| pe_abdomen | 腹部项目：腹壁、压痛、肝脾、移动性浊音、Murphy 征 |
| pe_limbs | 四肢脊柱项目：脊柱、关节、肌力、水肿、静脉曲张、病理征 |
| pe_neurological_exam | 神经系统项目：神志、精神、对答、反射、病理征；一般情况（发育/营养/体型/体位/表情）不属本字段 |

数值型字段（pe_temperature/pe_pulse/pe_respiration_rate/pe_blood_pressure/pe_height/pe_weight/pe_bmi）**不加** description。

- [ ] **Step 1: 写失败测试**（test_copd_prompts.py 追加）

```python
def test_field_table_description_rendered():
    schema = load_schema("app/config/schemas/admission_record_structured_fields.v1.yaml")
    system, _ = build_admission_structured_fields_messages(schema, [])
    assert "pe_eyes（眼部）；仅：眼部项目：睑结膜、球结膜、巩膜、角膜、瞳孔、对光反射、视力；不含头颅、头发、颜面、耳鼻口颈内容" in system
    assert "pe_chest（胸部）；仅：胸廓项目：胸廓形态、肋间隙、胸骨、挤压试验" in system
    assert "pe_neurological_exam（神经系统检查）；仅：神经系统项目：神志、精神、对答、反射、病理征" in system

def test_numeric_fields_have_no_description():
    schema = load_schema("app/config/schemas/admission_record_structured_fields.v1.yaml")
    system, _ = build_admission_structured_fields_messages(schema, [])
    assert "pe_temperature（体温）；仅：" not in system
    assert "pe_pulse（脉搏）；仅：" not in system
```

（`load_schema` 从 `app/backend/services/...` 或 fixtures 导入——先看 test_copd_prompts.py 现有测试怎么加载 schema，沿用同一方式；若现有测试用固定 schema dict fixture，则在 fixture 的两个字段上加 description 后再断言，另加一条"真实 schema 渲染"测试用 `app/config/schemas/admission_record_structured_fields.v1.yaml`。）

- [ ] **Step 2: 跑测试确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py -v`
Expected: 新测试 FAIL（渲染无"；仅："）

- [ ] **Step 3: schema 加 description + 渲染逻辑**

schema：13 个字段条目各加一行 `description: <定稿文本>`（YAML 换行时用 `description: >-` 或单行字符串，保持该文件既有风格；注意 YAML 中冒号后内容含中文标点无碍，含 `：` 全角冒号无碍）。

prompts.py 渲染（`build_admission_structured_fields_messages` 第 1 节）：
```python
        for field in group.get("fields", []):
            field_key = field.get("field_key", "")
            field_label = field.get("label", "")
            description = field.get("description", "")
            if description:
                table_lines.append(
                    f"- [{group_key}/{group_label}] {field_key}（{field_label}）；仅：{description}"
                )
            else:
                table_lines.append(
                    f"- [{group_key}/{group_label}] {field_key}（{field_label}）"
                )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py app/backend/tests/test_copd_verifier.py -v`
Expected: 全绿

- [ ] **Step 5: Commit**

```bash
git add app/config/schemas/admission_record_structured_fields.v1.yaml app/backend/services/copd_extraction/prompts.py app/backend/tests/test_copd_prompts.py
git commit -m "feat:pe_*字段表加description精确化字段边界(13条)+渲染追加仅字句+单测"
```

**验证:** 抽取 system 新旧字符数对比（改前 4788 → 改后记录实测，预期约 5300，spec 5 节已记录此代价）；test_copd_prompts.py 全绿。

---

### Task 3: step5 实验 + AI judge 对比（协调者执行，不入 subagent）

- [ ] `run_eval` 全量（对比 step4 的 status/value/幻觉不回退）：
  `conda run -n manzufei_ocr python -m app.backend.evaluation.run_eval --schema app/config/schemas/admission_record_structured_fields.v1.yaml --model Qwen3.5-4B-AWQ-4bit --base-url http://127.0.0.1:8082/v1`
- [ ] `calibrate export` 生成新 verdicts（`data/evaluation/calibration/20260802_verdicts_step5_A.json`）
- [ ] 复用 6 个 judge 包（`data/evaluation/calibration/judge/step4/case_*.json`，OCR 原文未变）重新派 6 个 AI judge 裁定 → `20260802_adjudications_ai_step5.json`
- [ ] 对比 step4：漏检（18 → 目标 <5）、误报（1 → 不增）、kappa（0.0834 → 提升）；逐类（A/B/C/D）统计修复情况
- [ ] 生成新 focus 页（AI 应标 + 拿不准）给用户重点确认剩余条目
- [ ] 记录 token 缩减/回吐实测（复核器 2027→?、抽取 4788→?）

### Task 4: HTML 报告（协调者执行）

- [ ] 对比整理：step4 vs step5（指标 / 漏检 / kappa / 四类修复 / 用户确认结果）→ HTML + markdown 报告，数据留 `data/evaluation/`，不进 git
