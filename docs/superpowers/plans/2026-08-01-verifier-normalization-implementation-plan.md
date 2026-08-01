# 验证器规范化（评估体系第二步）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 复核器接入活动路径并校准（kappa≥0.7）、审核数据回流为金标活资产、修正三个指标误报、prompt 适配 Qwen ChatML、thinking 消融实测。

**Architecture:** 复核器为独立可消融阶段（`FieldVerifier` 注入 port / run_pipeline，`--no-verifier` 消融）；prompt 全部拆 system（固定规则）/ user（变量数据）两层，适配 Qwen ChatML 并最大化前缀缓存命中；校准集人工裁定由 Claude 子 agent 模拟；医生审核修正经 review_service 聚合 → 脱敏 → 增量金标活资产（source: review）。

**Tech Stack:** Python 3.12 / Flask / pytest / vLLM OpenAI-compatible 客户端 / conda 环境 `manzufei_ocr`

## Global Constraints

- 测试命令一律：`conda run -n manzufei_ocr python -m pytest <path> -v`（在 worktree 根目录执行）
- 单测必须注入 fake LLM 客户端（参考 `test_evaluation_runner.py` 的 `FakeLlmClient` 模式），不依赖真实 vLLM 服务
- Git commit message 使用中文
- 温度恒为 0.0；同源模型缓解只靠上下文差异（evidence 前置防锚定、缺陷清单、引用 evidence 编号），不得引入温度差异
- 复核器失败必须静默降级（返回空意见、记日志），不得导致任务失败或抽取结果丢失
- `quality_flags` 是内部审计信号；`attention_message` 必须是纯中文；LLM 复核文本不得进前端展示
- 回流原始文件（`data/evaluation/review_feedback/`）含患者信息，不进 git；脱敏只发生在生成金标活资产时
- 全量 pytest 既有 5 个失败（test_review_routes 4 + test_qwen_batch_engine_layout 1）与本工作无关，勿修
- `data/`、`exports/`、`logs/` 中的运行数据不得提交
- J 型字段判定依据 schema 的 `qwen_type == "J"` 或 `review_control == "judgement"`（参考 `review_service.py` 既有用法）

---

### Task 1: ChatML 消息结构改造（complete_json 支持 system+user）

**Files:**
- Modify: `app/backend/services/algorithm_ports/qwen_vllm_client.py:148`（complete_json 签名）
- Modify: `app/backend/services/copd_extraction/llm_client.py:26-31`（适配层透传）
- Modify: `app/backend/services/copd_extraction/prompts.py`（拆层 + 兼容包装）
- Modify: `app/backend/services/copd_extraction/port.py:42-47`（调用新接口）
- Modify: `app/backend/evaluation/runner.py:32-38`（调用新接口）
- Test: `app/backend/tests/test_qwen_vllm_client.py`、`app/backend/tests/test_copd_prompts.py`、`app/backend/tests/test_evaluation_runner.py`

**Interfaces:**
- 生产：`QwenVLLMClient.complete_json(prompt: str, max_tokens: int, temperature: float, system_prompt: str | None = None) -> dict`——不传 system_prompt 时 messages 只含 user（行为不变，向后兼容）；传时 `[{"role": "system", ...}, {"role": "user", ...}]`
- 生产：`OpenAICompatibleJsonClient.complete_json(prompt: str, system_prompt: str | None = None) -> dict`
- 生产：`prompts.build_admission_structured_fields_messages(schema: dict, evidence_units: list[dict], document_text: str = "") -> tuple[str, str]`——返回 (system, user)；旧函数 `build_admission_structured_fields_prompt` 保留为兼容包装（返回两段拼接后的整体字符串）

- [ ] **Step 1: 写失败测试——system_prompt 进入 messages 形状**

在 `test_qwen_vllm_client.py` 追加（复用现有 `FakeOpenAIClient` / `FakeCompletions`）：

```python
def test_complete_json_accepts_system_prompt():
    client = QwenVLLMClient(
        base_url="http://localhost:8000/v1", model="test-model",
        api_key="not-needed", timeout_seconds=30,
    )
    fake = FakeOpenAIClient('{"ok": true}')
    client._client = fake
    client.complete_json(
        prompt="user 内容", max_tokens=100, temperature=0.0,
        system_prompt="system 规则",
    )
    kwargs = fake.chat.completions.calls[0]
    assert kwargs["messages"] == [
        {"role": "system", "content": "system 规则"},
        {"role": "user", "content": "user 内容"},
    ]


def test_complete_json_without_system_prompt_keeps_single_user_message():
    client = QwenVLLMClient(
        base_url="http://localhost:8000/v1", model="test-model",
        api_key="not-needed", timeout_seconds=30,
    )
    fake = FakeOpenAIClient('{"ok": true}')
    client._client = fake
    client.complete_json(prompt="仅 user", max_tokens=100, temperature=0.0)
    kwargs = fake.chat.completions.calls[0]
    assert kwargs["messages"] == [{"role": "user", "content": "仅 user"}]
```

注意：构造 `QwenVLLMClient` 需要真实 openai 客户端——参考测试文件里现有用例如何构造（`test_qwen_vllm_client.py` 已有类似模式，若构造路径不同以现有用例为准，重点是断言 `messages` 形状）。

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_vllm_client.py -v`
Expected: FAIL（complete_json 不接受 system_prompt 参数 / TypeError）

- [ ] **Step 3: 实现——complete_json 加 system_prompt**

`qwen_vllm_client.py` 修改 `complete_json`：

```python
def complete_json(
    self, prompt: str, max_tokens: int, temperature: float,
    system_prompt: str | None = None,
) -> dict:
    kwargs = self._common_kwargs(max_tokens=max_tokens, temperature=temperature)
    if system_prompt:
        kwargs["messages"] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
    else:
        kwargs["messages"] = [{"role": "user", "content": prompt}]
    kwargs["response_format"] = {"type": "json_object"}
    # 其余逻辑不变
```

`llm_client.py` 适配层透传：

```python
def complete_json(self, prompt: str, system_prompt: str | None = None) -> dict:
    return self._qwen_client.complete_json(
        prompt=prompt,
        max_tokens=self._max_tokens,
        temperature=self._temperature,
        system_prompt=system_prompt,
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_vllm_client.py -v`
Expected: PASS

- [ ] **Step 5: 写失败测试——抽取 prompt 拆层**

在 `test_copd_prompts.py` 追加：

```python
def test_admission_messages_split_system_and_user():
    schema = _sample_admission_schema()
    system, user = build_admission_structured_fields_messages(
        schema=schema, evidence_units=[{"id": "u001", "text": "主诉：咳嗽20年"}], document_text="全文"
    )
    # system 承载身份与固定规则，不含证据/原文数据
    assert "结构化抽取助手" in system
    assert "u001" not in system and "咳嗽20年" not in system
    assert "硬约束" in system
    # user 承载证据与原文
    assert "u001：主诉：咳嗽20年" in user
    assert "全文" in user
```

（`build_admission_structured_fields_messages` 尚未定义，导入即失败——先写导入。）

- [ ] **Step 6: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 7: 实现——prompts.py 拆层**

```python
def build_admission_structured_fields_messages(
    schema: dict, evidence_units: list[dict], document_text: str = "",
) -> tuple[str, str]:
    """返回 (system, user)。system 固定承载身份/硬约束/字段表/契约；
    user 承载 evidence_units 与 OCR 原文（变量数据）。"""
    schema_version = schema.get("version", "")
    document_type = schema.get("document_type", "")
    table_lines = []
    for group in schema.get("field_groups", []):
        group_key = group.get("group_key", "")
        group_label = group.get("group_label", "")
        for field in group.get("fields", []):
            table_lines.append(
                f"- [{group_key}/{group_label}] {field.get('field_key', '')}（{field.get('label', '')}）"
            )
    fixed_field_table = "\n".join(table_lines)

    unit_blocks = []
    for unit in evidence_units or []:
        unit_blocks.append(f"- {unit.get('id', '')}：{unit.get('text', '')}")
    evidence_units_section = "\n".join(unit_blocks) if unit_blocks else "（未提供 evidence_units）"

    if document_text:
        document_text_section = document_text
    elif evidence_units:
        document_text_section = "已由上方 evidence_units 按 OCR 原始顺序覆盖，本次不重复粘贴完整 OCR。"
    else:
        document_text_section = "（未提供 document_text）"

    system = f"""你是慢阻肺/呼吸系统入院记录结构化抽取助手，使用固定字段表对 OCR 原文做结构化抽取。

schema_version：{schema_version}
document_type：{document_type}

【硬约束 — 输出 JSON 形状】
输出必须是单个 JSON 对象，顶层键固定为 `schema_version`、`document_type`、`fields`，不得新增顶层键。`fields` 是数组，每个 schema 字段对应一项，不得增删。

字段状态枚举仅允许：`found` / `not_found` / `uncertain`。
- found：原文中明确出现该字段语义，`value` 非空，`evidence_ids` 应非空。
- not_found：原文未提及该字段，必须输出 `status="not_found"`、`value=""`、`evidence_ids=[]`，不得省略字段。
- uncertain：疑似找到但 OCR 或上下文不确定，需要医生重点核验；`value` 可空，`evidence_ids` 可空。

每项字段输出固定包含：field_key、status、value、evidence_ids。后端按 schema 回填章节、字段标签、审核状态和 evidence 详情，模型不要重复输出 section_key、section_label、field_label 或其他字段。`evidence_ids` 必须是字符串列表（list[str]），只允许从"证据单元编号"中选择现有 ID，不允许编造或自填 evidence 文本。

输出示例：
```json
{{
  "schema_version": "{schema_version}",
  "document_type": "{document_type}",
  "fields": [
    {{
      "field_key": "chief_complaint",
      "status": "found",
      "value": "反复咳嗽、咳痰15年，喘息6年，加重1月。",
      "evidence_ids": ["u001"]
    }},
    {{
      "field_key": "hpi_initial_onset",
      "status": "not_found",
      "value": "",
      "evidence_ids": []
    }}
  ]
}}
```

【硬约束 — 字段与 key】
- field_key 只允许使用"固定字段表"中的 key；禁止输出 schema 外字段；禁止自由生成二级 key、二级字典或额外字段。
- 字段顺序按固定字段表顺序输出，便于后端对齐。

【硬约束 — evidence 与原文】
- evidence_ids 只允许从编号证据单元中选择，禁止编造 ID；找不到支撑证据时使用 `evidence_ids=[]`。
- value 必须是 OCR 原文中可定位的语义片段，不得根据医学常识补全、合并或重写。

【硬约束 — 否定表达与既往史】
- 对既往史、个人史、家族史中的疾病字段，必须先判断否定范围；`否认A、B等病史`、`无A、B史`、`未见A、B` 均表示 A、B 是明确否定事实。
- 字段被明确否定时，不得输出阳性值；应输出 `status="found"`，并在 `value` 中保留否定词，例如 `否认糖尿病病史`、`否认冠心病病史`，同时引用对应 evidence_ids。
- 保留否定词是硬要求：不得把 `否认/无/未见` 从 value 中删掉；删掉否定词会把否定事实变成模型幻觉。
- 若同一句存在混合事实，例如 `否认糖尿病，既往有冠心病`，只允许把冠心病输出为阳性，糖尿病仍必须保留否定。

【硬约束 — J 型状态字段判定】
- qwen_type 为 J 或 review_control 为 judgement 的字段：正常时输出 `value="正常"`；异常时必须在 `value` 中摘录 OCR 原文里的具体异常描述；未提及时输出 `status="not_found"`、`value=""`；不确定时输出 `status="uncertain"`。
- 原文明确描述该部位/项目正常或阴性时，必须输出 `status="found"`、`value="正常"`；不得因为是阴性描述而输出 not_found。
- 正常/阴性证据包括但不限于：`正常`、`未见异常`、`无异常`、`无压痛`、`无肿大`、`无充血水肿`、`无黄染`、`未闻及病理性杂音`、`阴性`。
- 只有原文完全没有该部位/项目信息时才输出 `status="not_found"`、`value=""`、`evidence_ids=[]`。

【硬约束 — OCR 原文保持原样】
- 不得静默修正 OCR 文本；不得把 1/I/l、0/O/o、P62/P02/PC02/PCO2/PO2/PaO2/PaCO2 等疑似错读标签自动改成标准标签。
- 不得纠正章节标题错字；例如 `品后诊断` 必须保留原文写法。
- 不得重排页序或重新组织 OCR 原文；raw OCR 顺序即真相。

【硬约束 — 诊断字段禁止主观】
- diagnosis_preliminary 和 diagnosis_final 只能摘录 OCR 原文中已经写出的诊断文本。
- 禁止对诊断字段做主观医学判断、推断、改写、合并、添加诊断或医学推理。
- 如果诊断在原文中是编号列表，`value` 必须按编号分行保留，例如 `1慢性阻塞性肺疾病急性加重\n2高血压2级中危\n3慢性胃炎`；不得合并成一句，不得丢失编号。

【硬约束 — 共享证据单元】
- 允许多个字段共用同一条 evidence unit；evidence_ids 可以包含 1 个或多个 ID。
- 血气 6 个字段（血气pH、血气pCO2、血气pO2、血气Na+、血气FIO2、血气氧合指数）通常共享同一条血气分析证据单元，应当显式共享 evidence_ids。

OCR 风险提示：1/I/l、0/O/o、BHI/BMI、cT/CT/Ct、血气项目名 P62/P02/PC02/PCO2/PO2/PaO2/PaCO2 混淆、药名和医学词近形/同音/缺字错读（例如嗜托溴铵/噻托溴铵）、单位断裂、单位符号错读（例如 +10^9/L 可能是 ×10^9/L）、表格错位、项目和值跨行、冒号和空格丢失、小数点和逗号异常、常见错别字。硬约束：不得静默修正 OCR；不得改写数值；不得医学换算；不得把"无、否认、未见、可能、考虑、建议复查"等表达改成确定阳性。

【固定字段表】
{fixed_field_table}

【再次强调】
- 字段必须全量输出，未找到返回 status="not_found"、value=""、evidence_ids=[]，不得省略任何字段。
- 禁止 schema 外字段；禁止自由生成二级 key。
- 禁止 OCR 文本修正、标题纠正、页序重排；禁止诊断字段主观推断或医学推理。
- 允许多个字段共用同一条 evidence unit，特别是血气 6 项。"""

    user = f"""【证据单元编号（每条对应 OCR 原文片段，仅按 ID 引用）】
{evidence_units_section}

【合并 OCR 原文（仅供上下文理解，不作为 evidence_ids 选择依据）】
{document_text_section}"""
    return system, user
```

保留旧函数为兼容包装（现有调用方与测试继续可用）：

```python
def build_admission_structured_fields_prompt(
    schema: dict, evidence_units: list[dict], document_text: str = "",
) -> str:
    system, user = build_admission_structured_fields_messages(
        schema, evidence_units, document_text
    )
    return f"{system}\n\n{user}"
```

注意：原 prompt 里的"你是…抽取助手"身份段、`_OCR_RISK_WARNINGS` 常量等按上面对应位置归入 system/user；**system 部分必须完全不含 evidence_units / document_text 变量**（前缀缓存命中前提）。原函数实现以 `prompts.py` 现有内容为准，拆层时把固定规则段（【硬约束】、固定字段表、风险提示中的非数据部分）全部并入 system。

- [ ] **Step 8: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py -v`
Expected: PASS（新旧测试都过）

- [ ] **Step 9: 更新调用方（port.py / runner.py）传 system_prompt**

`port.py`：

```python
from .prompts import build_admission_structured_fields_messages
...
    system, user = build_admission_structured_fields_messages(
        schema=schema, evidence_units=evidence_units, document_text=document_text,
    )
    payload = self._llm_client.complete_json(user, system_prompt=system)
```

`runner.py` 同样改为 `system, user = build_admission_structured_fields_messages(...)` + `llm_client.complete_json(user, system_prompt=system)`。

- [ ] **Step 10: 跑相关测试确认全绿**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_field_port.py app/backend/tests/test_evaluation_runner.py app/backend/tests/test_qwen_vllm_client.py app/backend/tests/test_copd_prompts.py -q`
Expected: PASS（fake client 的 `complete_json(prompt, **kwargs)` 接收 system_prompt 不报错——`test_evaluation_runner.py` 的 FakeLlmClient 已用 `**kwargs`）

- [ ] **Step 11: Commit**

```bash
git add app/backend/services/algorithm_ports/qwen_vllm_client.py app/backend/services/copd_extraction/llm_client.py app/backend/services/copd_extraction/prompts.py app/backend/services/copd_extraction/port.py app/backend/evaluation/runner.py app/backend/tests/test_qwen_vllm_client.py app/backend/tests/test_copd_prompts.py
git commit -m "feat:抽取prompt拆system/user适配Qwen ChatML(complete_json支持system_prompt)"
```

---

### Task 2: 复核器 prompt 激活 + FieldVerifier

**Files:**
- Create: `app/backend/services/copd_extraction/verifier.py`
- Modify: `app/backend/services/copd_extraction/prompts.py`（重构 `build_verification_prompt` → `build_verification_messages`，死代码无调用方，直接改签名）
- Create: `app/backend/tests/test_copd_verifier.py`

**Interfaces:**
- 生产：`prompts.build_verification_messages(evidence_units: list[dict], fields: list[dict]) -> tuple[str, str]`——返回 (system, user)；evidence 在前、字段在后
- 生产：`verifier.FieldVerifier(llm_client).verify(candidates: list[dict], document_text: str) -> list[dict]`——输入 `map_qwen_fields_to_review_candidates` 输出的候选列表，输出复核意见列表 `[{field_key, verdict, reason_code, checks, comment}]`；LLM 失败 / 非 JSON / 字段不在 candidates → 静默降级跳过，**绝不抛出**
- 生产：`verifier.apply_verdicts(candidates: list[dict], verdicts: list[dict]) -> list[dict]`——verdict=suspicious/fail 的字段：追加 quality_flags（`verifier_suspicious`）、verification_status 升为 suspicious（failed 保持）、attention_required=True、attention_message="复核器标记，请核对原文"

- [ ] **Step 1: 写失败测试——复核 prompt 布局**

在 `test_copd_verifier.py` 新建：

```python
"""复核器单测：prompt 布局、verdict 解析与映射、失败降级（fake client，不依赖真实 LLM）。"""
import json

import pytest

from app.backend.services.copd_extraction.prompts import build_verification_messages
from app.backend.services.copd_extraction.verifier import FieldVerifier, apply_verdicts


def test_verification_messages_evidence_first_fields_after():
    system, user = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "双耳粗测听力正常"}],
        fields=[{"field_key": "pe_ear", "value": "正常", "evidence_ids": ["e001"]}],
    )
    # system：身份 + 缺陷清单 + verdict 契约 + few-shot，不含数据
    assert "复核器" in system
    assert "e001" not in system and "听力正常" not in system
    assert "verdict" in system and "pass" in system and "suspicious" in system
    assert "suspicious" in system  # few-shot 覆盖 suspicious 示例
    # user：evidence 编号块在字段块之前
    assert user.index("e001") < user.index("pe_ear")
    assert "pe_ear" in user and "正常" in user
```

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 实现——build_verification_messages**

`prompts.py` 中把死代码 `build_verification_prompt` 重构替换：

```python
def build_verification_messages(
    evidence_units: list[dict], fields: list[dict],
) -> tuple[str, str]:
    """复核器 prompt：(system, user)。evidence 在前、字段在后（防锚定）。

    system 完全固定（前缀缓存友好）：身份、缺陷清单、verdict 契约、few-shot。
    user 为变量：编号证据块 + 字段块。
    """
    system = """你是字段级复核器。
任务：审查已抽取的字段值是否被 OCR 原文事实支持，主动找出可能存在的问题。

审查方法：先通读下方 OCR 原文证据，形成你自己的判断；再对照字段声称的值。
禁止顺着字段值在证据中找支撑（找补）；禁止使用医学常识补全字段值；禁止把否定或不确定表述改成确定阳性。

【缺陷清单 —— 逐项核对】
1. 否定翻转：evidence 中存在"无、否认、未见、可能、考虑、建议复查"等表述，但字段值被当作确定阳性抽取；字段值删掉了否定词。
2. OCR 标签混淆：P62/P02/PC02/PCO2/PO2/PaO2/PaCO2 等血气项目名前缀疑似错读但被归入标准项目；药名和医学词近形错读（嗜托溴铵/噻托溴铵、二程丙苯碱/二羟丙茶碱）；单位符号错读（+10^9/L/×10^9/L）。
3. OCR 纠偏合理性：字段值依赖纠偏（ocr_correction）但理由不充分、原始 OCR 文本与修正后值关系不合理。
4. 数值矛盾：同一字段附近存在与字段值不一致的数值（如脉搏 9 次/分但同段另有心率 99 次/分）。
5. 体重下降零值矛盾：体重下降/减轻字段输出 0g、0kg、0克等反直觉数值。
6. 生理范围异常：体温/脉搏/呼吸/血压/BMI/血气超出合理范围，疑似 OCR 截断（99→9、36.7→3.7）。
7. 证据缺失/幻觉：字段值在下方证据中找不到对应文本；引入了 OCR 原文没有的信息或做了医学推断。

【verdict 契约】
输出 JSON 对象，顶层键为 `verifications`，`verifications` 是数组。每项包含：
- field_key：被审查字段的 key
- verdict：只能是 pass / suspicious / fail
- reason_code：只能是 ocr_quality_issue / extraction_mistake / evidence_insufficient / none
- checks：对象，包含 value_semantically_supported（值是否被证据语义支持）、no_hallucination_or_inference（是否引入原文外信息或医学推断）、ocr_correction_justified（纠偏理由是否充分）
- comment：不超过 40 个汉字，只写必要原因；通过项写"一致"

对抗要求：对每个字段先主动找茬；确实找到疑点才输出 suspicious/fail，**每条 suspicious/fail 必须引用具体证据编号（eXXX）和疑点描述**；没有疑点才输出 pass。

输出示例：
```json
{"verifications": [
  {"field_key": "pe_ear", "verdict": "pass", "reason_code": "none",
   "checks": {"value_semantically_supported": true, "no_hallucination_or_inference": true, "ocr_correction_justified": true},
   "comment": "一致"},
  {"field_key": "pe_pulse", "verdict": "suspicious", "reason_code": "ocr_quality_issue",
   "checks": {"value_semantically_supported": false, "no_hallucination_or_inference": true, "ocr_correction_justified": true},
   "comment": "e002附近另有心率99次/分，疑与脉搏9次/分冲突"}
]}
```
示例仅示范结构，字段内容为占位，不得照抄。"""

    evidence_blocks = [
        f"- {unit.get('id', '')}：{unit.get('text', '')}"
        for unit in evidence_units or []
    ]
    evidence_section = "\n".join(evidence_blocks) if evidence_blocks else "（未提供证据）"

    field_blocks = []
    for field in fields or []:
        fk = field.get("field_key", "")
        value = field.get("value", "")
        ids = ", ".join(field.get("evidence_ids") or [])
        field_blocks.append(f"- {fk}：声称值 {value or '（空）'}；引用证据 {ids or '（无）'}")
    fields_section = "\n".join(field_blocks) if field_blocks else "（无字段）"

    user = f"""【OCR 原文证据（先读，编号引用）】
{evidence_section}

【字段声称值（后看，逐字段审查）】
{fields_section}"""
    return system, user
```

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py::test_verification_messages_evidence_first_fields_after -v`
Expected: PASS

- [ ] **Step 5: 写失败测试——verify 主流程与失败降级**

```python
class FakeLlmClient:
    def __init__(self, payload):
        self._payload = payload

    def complete_json(self, prompt: str, **kwargs):
        return json.loads(json.dumps(self._payload))


def make_candidates():
    return [
        {
            "field_key": "pe_ear", "original_value": "正常",
            "value": "正常", "status": "found",
            "evidence": [{"id": "e001", "text": "双耳粗测听力正常"}],
            "evidence_ids": ["e001"],
            "quality_flags": [], "verification_status": "not_checked",
            "attention_required": False, "attention_message": "",
        },
        {
            "field_key": "pe_nose", "original_value": "鼻腔通畅",
            "value": "鼻腔通畅", "status": "found",
            "evidence": [{"id": "e002", "text": "鼻腔通畅，各鼻窦区无压痛"}],
            "evidence_ids": ["e002"],
            "quality_flags": [], "verification_status": "not_checked",
            "attention_required": False, "attention_message": "",
        },
    ]


def test_verify_returns_verdicts_for_found_fields_only():
    verifier = FieldVerifier(FakeLlmClient({
        "verifications": [
            {"field_key": "pe_ear", "verdict": "pass", "reason_code": "none",
             "checks": {}, "comment": "一致"},
            {"field_key": "pe_nose", "verdict": "suspicious", "reason_code": "extraction_mistake",
             "checks": {}, "comment": "e002无异常表述，值与原文不符"},
        ]
    }))
    verdicts = verifier.verify(make_candidates(), document_text="")
    assert [v["field_key"] for v in verdicts] == ["pe_ear", "pe_nose"]
    assert verdicts[1]["verdict"] == "suspicious"


def test_verify_llm_failure_degrades_to_empty_verdicts():
    class BoomClient:
        def complete_json(self, prompt: str, **kwargs):
            raise RuntimeError("vLLM 不可用")

    verifier = FieldVerifier(BoomClient())
    assert verifier.verify(make_candidates(), document_text="") == []


def test_verify_non_json_output_degrades_to_empty_verdicts():
    class StringClient:
        def complete_json(self, prompt: str, **kwargs):
            return "不是 JSON"

    verifier = FieldVerifier(StringClient())
    assert verifier.verify(make_candidates(), document_text="") == []
```

- [ ] **Step 6: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py -v`
Expected: FAIL（FieldVerifier 未定义）

- [ ] **Step 7: 实现——verifier.py**

```python
"""字段级复核器：对抽取结果做 LLM 二次审查，输出 verdict 意见。

- 复核范围：status=found 且 value 非空 的字段（not_found / 空值由审核页兜底）。
- 失败语义：LLM 失败 / 输出非 JSON / verdict 契约非法 → 静默降级为空意见，
  绝不抛出、绝不导致任务失败、绝不修改抽取结果的值。
- 输出映射（apply_verdicts）：suspicious/fail → quality_flags(verifier_suspicious)
  + verification_status=suspicious + attention_required + 规则化 message。
"""
import json
import logging

logger = logging.getLogger(__name__)

_ALLOWED_VERDICTS = {"pass", "suspicious", "fail"}


class FieldVerifier:
    def __init__(self, llm_client):
        self._llm_client = llm_client

    def verify(self, candidates: list[dict], document_text: str = "") -> list[dict]:
        """对 found + value 非空的字段执行复核，返回意见列表；失败降级为空列表。"""
        targets = [
            c for c in candidates
            if isinstance(c, dict)
            and c.get("status") == "found"
            and (c.get("value") or "").strip()
        ]
        if not targets:
            return []
        try:
            from .prompts import build_verification_messages

            evidence_units = _collect_evidence(targets, document_text)
            fields = [
                {
                    "field_key": c.get("field_key", ""),
                    "value": c.get("value", ""),
                    "evidence_ids": c.get("evidence_ids") or [],
                }
                for c in targets
            ]
            system, user = build_verification_messages(evidence_units, fields)
            payload = self._llm_client.complete_json(user, system_prompt=system)
        except Exception:  # noqa: BLE001 — 复核器失败必须静默降级
            logger.warning("复核器调用失败，已降级为空意见", exc_info=True)
            return []
        return _parse_verdicts(payload)


def _collect_evidence(candidates: list[dict], document_text: str) -> list[dict]:
    """聚合候选字段的 evidence（去重保序），超长时以 document_text 兜底。"""
    seen: set[str] = set()
    units: list[dict] = []
    for c in candidates:
        for ev in c.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            key = ev.get("id") or ev.get("text") or ""
            if key and key not in seen:
                seen.add(key)
                units.append({"id": ev.get("id") or f"e{len(units) + 1:03d}", "text": ev.get("text", "")})
    if not units and document_text:
        # evidence 缺失时用原文全文兜底，保证复核器仍有事实可依
        units.append({"id": "doc", "text": document_text[:8000]})
    return units


def _parse_verdicts(payload) -> list[dict]:
    """容错解析 LLM 输出；任何异常/非法项跳过，不抛出。"""
    if not isinstance(payload, dict):
        try:
            payload = json.loads(payload) if isinstance(payload, str) else None
        except (json.JSONDecodeError, TypeError):
            logger.warning("复核器输出非 JSON，已降级为空意见")
            return []
    verifications = payload.get("verifications") if isinstance(payload, dict) else None
    if not isinstance(verifications, list):
        return []
    verdicts = []
    for item in verifications:
        if not isinstance(item, dict):
            continue
        verdict = item.get("verdict")
        if verdict not in _ALLOWED_VERDICTS:
            continue
        verdicts.append({
            "field_key": item.get("field_key", ""),
            "verdict": verdict,
            "reason_code": item.get("reason_code") or "none",
            "checks": item.get("checks") or {},
            "comment": str(item.get("comment") or "")[:40],
        })
    return verdicts


def apply_verdicts(candidates: list[dict], verdicts: list[dict]) -> list[dict]:
    """把复核意见合并进候选字段：suspicious/fail → 标记 + verification_status 升为 suspicious。

    不修改字段值；verification_status 已是 failed 的字段不降级。
    """
    by_key = {c.get("field_key"): c for c in candidates if isinstance(c, dict)}
    for v in verdicts:
        field = by_key.get(v.get("field_key"))
        if field is None:
            continue
        if v.get("verdict") not in ("suspicious", "fail"):
            continue
        flags = field.setdefault("quality_flags", [])
        if not any(f.get("flag") == "verifier_suspicious" for f in flags if isinstance(f, dict)):
            flags.append({
                "flag": "verifier_suspicious",
                "severity": "warning",
                "message": v.get("comment") or "复核器标记，请核对原文",
            })
        if field.get("verification_status") != "failed":
            field["verification_status"] = "suspicious"
        field["attention_required"] = True
        field["attention_message"] = "复核器标记，请核对原文"
    return candidates
```

- [ ] **Step 8: 写失败测试——apply_verdicts 映射**

```python
def test_apply_verdicts_marks_suspicious_fields():
    candidates = make_candidates()
    verdicts = [
        {"field_key": "pe_ear", "verdict": "pass", "reason_code": "none", "checks": {}, "comment": "一致"},
        {"field_key": "pe_nose", "verdict": "suspicious", "reason_code": "extraction_mistake", "checks": {}, "comment": "e002无异常表述"},
    ]
    out = apply_verdicts(candidates, verdicts)
    by_key = {c["field_key"]: c for c in out}
    # pass 字段不动
    assert by_key["pe_ear"]["verification_status"] == "not_checked"
    assert by_key["pe_ear"]["attention_required"] is False
    # suspicious 字段标记
    assert by_key["pe_nose"]["verification_status"] == "suspicious"
    assert by_key["pe_nose"]["attention_required"] is True
    assert by_key["pe_nose"]["attention_message"] == "复核器标记，请核对原文"
    flags = by_key["pe_nose"]["quality_flags"]
    assert any(f["flag"] == "verifier_suspicious" for f in flags)


def test_apply_verdicts_does_not_downgrade_failed_fields():
    candidates = make_candidates()
    candidates[1]["verification_status"] = "failed"
    apply_verdicts(candidates, [
        {"field_key": "pe_nose", "verdict": "suspicious", "reason_code": "extraction_mistake", "checks": {}, "comment": "x"},
    ])
    assert candidates[1]["verification_status"] == "failed"
```

- [ ] **Step 9: 运行确认全绿**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py -q`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add app/backend/services/copd_extraction/prompts.py app/backend/services/copd_extraction/verifier.py app/backend/tests/test_copd_verifier.py
git commit -m "feat:复核器FieldVerifier(verdict解析/失败降级/quality_flags映射)+复核prompt激活"
```

---

### Task 3: 复核器接入管线与消融

**Files:**
- Modify: `app/backend/evaluation/runner.py`（run_pipeline 加 apply_verify / verifier 参数）
- Modify: `app/backend/services/copd_extraction/port.py`（可注入 verifier）
- Modify: `app/backend/evaluation/run_eval.py`（--no-verifier）
- Modify: `app/backend/evaluation/runner.py`（evaluate_sample 记 verifier 错误？不需要——复核失败不改变指标；只需 apply_verify 开关）
- Test: `app/backend/tests/test_evaluation_runner.py`、`app/backend/tests/test_copd_field_port.py`

**Interfaces:**
- 生产：`runner.run_pipeline(input, llm_client, *, check_contract=True, apply_quality=True, apply_verify=True, verifier=None) -> dict`——默认构造 `FieldVerifier(llm_client)`；`apply_verify=False` 时跳过
- 生产：`port.COPDAdmissionQwenFieldPort(llm_client, verifier=None)`——`extract()` 在 `apply_quality_checks` 之后执行 `verifier.verify` + `apply_verdicts`
- 生产：`run_eval --no-verifier` → `run_pipeline(apply_verify=False)`

- [ ] **Step 1: 写失败测试——runner 消融开关**

在 `test_evaluation_runner.py` 追加：

```python
class FakeVerifier:
    def __init__(self, verdicts):
        self._verdicts = verdicts
        self.called = 0

    def verify(self, candidates, document_text=""):
        self.called += 1
        return [dict(v) for v in self._verdicts]

    def close(self):
        pass


class TestRunPipelineVerifier:
    def test_apply_verify_default_runs_verifier(self):
        schema = make_schema()
        verifier = FakeVerifier([
            {"field_key": "chief_complaint", "verdict": "suspicious", "reason_code": "extraction_mistake",
             "checks": {}, "comment": "原文无此值"},
        ])
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(make_golden_payload()),
            verifier=verifier,
        )
        assert verifier.called == 1
        candidates = result["candidates"]
        assert candidates[0]["verification_status"] == "suspicious"

    def test_no_verifier_skips_verifier(self):
        schema = make_schema()
        verifier = FakeVerifier([
            {"field_key": "chief_complaint", "verdict": "suspicious", "reason_code": "extraction_mistake",
             "checks": {}, "comment": "x"},
        ])
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(make_golden_payload()),
            apply_verify=False,
            verifier=verifier,
        )
        assert verifier.called == 0
        assert result["candidates"][0]["verification_status"] != "suspicious"
```

注意：`make_schema` / `make_golden_payload` / `FakeLlmClient` / `SAMPLE` 复用文件内已有定义；候选字段的实际 verification_status 以 `map_qwen_fields_to_review_candidates` 输出为准（断言"不等于 suspicious"即可）。

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_runner.py::TestRunPipelineVerifier -v`
Expected: FAIL（run_pipeline 不接受 verifier 参数 / 未调用）

- [ ] **Step 3: 实现——runner.run_pipeline 接入**

```python
from .metrics import compare_value, status_matches, value_located_in_text
from ..services.copd_extraction.verifier import FieldVerifier, apply_verdicts
...
def run_pipeline(
    input: dict,
    llm_client,
    *,
    check_contract: bool = True,
    apply_quality: bool = True,
    apply_verify: bool = True,
    verifier=None,
) -> dict:
    ...
    if apply_quality:
        candidates = apply_quality_checks(candidates, document_text, include_document_flags=False)
    if apply_verify:
        verifier = verifier or FieldVerifier(llm_client)
        verdicts = verifier.verify(candidates, document_text)
        candidates = apply_verdicts(candidates, verdicts)
    return {"payload": payload, "candidates": candidates, "error": None}
```

（`llm_client.complete_json(user, system_prompt=system)` 的拆层调用保持 Task 1 的实现。）

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_runner.py::TestRunPipelineVerifier -q`
Expected: PASS

- [ ] **Step 5: 写失败测试——port 可注入 verifier**

在 `test_copd_field_port.py` 追加（参考该文件现有 fake client fixture 模式）：

```python
def test_port_extract_runs_injected_verifier():
    # 复用现有 fake llm client fixture 构造 port，注入记录调用次数的 verifier
    port = COPDAdmissionQwenFieldPort(llm_client=fake_llm_client, verifier=recording_verifier)
    candidates = port.extract({"schema": ..., "document_result": ..., "evidence_units": ...})
    assert recording_verifier.called == 1
```

（`fake_llm_client` / `recording_verifier` 以该文件现有 fixture 方式实现，核心断言：extract 调用一次 verifier.verify。）

- [ ] **Step 6: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_field_port.py -v`
Expected: FAIL（COPDAdmissionQwenFieldPort 不接受 verifier 参数）

- [ ] **Step 7: 实现——port 注入**

```python
from .verifier import FieldVerifier, apply_verdicts


class COPDAdmissionQwenFieldPort:
    def __init__(self, llm_client, verifier=None):
        self._llm_client = llm_client
        self._verifier = verifier

    def extract(self, input: dict) -> list[dict]:
        ...
        candidates = map_qwen_fields_to_review_candidates(payload, schema, evidence_units=evidence_units)
        candidates = apply_quality_checks(candidates, document_text, include_document_flags=False)
        if self._verifier is not None:
            verdicts = self._verifier.verify(candidates, document_text)
            candidates = apply_verdicts(candidates, verdicts)
        return candidates
```

注意：`_LazyCOPDAdmissionQwenFieldPort` 构建 `COPDAdmissionQwenFieldPort` 时默认不传 verifier（活动路径接入点留到 Task 3 的下一步/生产装配，先保持 None 不改变既有行为；生产接入由实现者在 `_build_port` 里追加 `verifier=FieldVerifier(self._llm_client)`——若需要活动路径默认开启，此处加一行并同步 port 测试）。

- [ ] **Step 8: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_field_port.py app/backend/tests/test_evaluation_runner.py -q`
Expected: PASS

- [ ] **Step 9: 实现——run_eval --no-verifier**

`run_eval.py` 加参数与传递：

```python
parser.add_argument("--no-verifier", action="store_true")
...
    return run_pipeline(
        _input_for(sample, schema),
        llm_client,
        check_contract=not args.no_contract,
        apply_quality=not args.no_quality_flags,
        apply_verify=not args.no_verifier,
    )
```

meta 记录消融：

```python
"ablation": {
    "quality_flags": not args.no_quality_flags,
    "contract": not args.no_contract,
    "verifier": not args.no_verifier,
},
```

- [ ] **Step 10: 跑全量评估相关测试**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_runner.py app/backend/tests/test_evaluation_run_eval.py app/backend/tests/test_copd_field_port.py -q`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add app/backend/evaluation/runner.py app/backend/services/copd_extraction/port.py app/backend/evaluation/run_eval.py app/backend/tests/test_evaluation_runner.py app/backend/tests/test_copd_field_port.py
git commit -m "feat:复核器接入管线(port注入/run_pipeline apply_verify/run_eval --no-verifier消融)"
```

---

### Task 4: 指标修正（metrics.py 三处）

**Files:**
- Modify: `app/backend/evaluation/metrics.py`
- Modify: `app/backend/evaluation/runner.py`（evaluate_sample 加 schema 参数 + 幻觉豁免）
- Modify: `app/backend/evaluation/run_eval.py`（evaluate_sample 传 schema）
- Test: `app/backend/tests/test_evaluation_metrics.py`、`app/backend/tests/test_evaluation_runner.py`

**Interfaces:**
- 生产：`metrics.j_judgement_normalize(value: str) -> str`——J 型"正常族"归一（正常/通畅/未见异常/无异常/阴性/无压痛 等 → 统一 token）
- 生产：`metrics.sentence_overlap_ratio(golden: str, predicted: str) -> float`——按句切分共有句占比
- 生产：`metrics.LONG_TEXT_FIELDS: set[str]`——长文本宽松判定字段（初始：hpi_ 前缀 + chief_complaint）
- 生产：`metrics.j_judgement_fields(schema: dict) -> set[str]`——从 schema 提取 qwen_type=J / review_control=judgement 字段
- 生产：`evaluate_sample(sample: dict, result: dict, schema: dict | None = None) -> dict`——schema 提供时 J 型归一生效；幻觉判定前先测金标 value 可定位性（金标不可定位 → 跳过该字段幻觉判定）

- [ ] **Step 1: 写失败测试——J 型归一 + 长文本重合率 + 幻觉豁免**

在 `test_evaluation_metrics.py` 追加：

```python
from app.backend.evaluation.metrics import (
    j_judgement_normalize,
    sentence_overlap_ratio,
    j_judgement_fields,
)


def test_j_judgement_normalize_maps_normal_family():
    for text in ("正常", "鼻腔通畅", "未见异常", "无异常", "阴性", "无压痛"):
        assert j_judgement_normalize(text) == "正常"


def test_j_judgement_normalize_keeps_abnormal_descriptions():
    assert "异常" in j_judgement_normalize("双肺呼吸音粗")
    assert j_judgement_normalize("双肺呼吸音粗") != "正常"


def test_sentence_overlap_ratio():
    golden = "反复咳嗽、咳痰20年。活动后喘息。无发热。"
    predicted = "咳嗽、咳痰20年。活动后喘息。"
    # 金标 3 句，预测 2 句都共有 → 金标视角重合 2/3；取金标与预测覆盖的较小口径
    assert sentence_overlap_ratio(golden, predicted) >= 0.5


def test_j_judgement_fields_extracts_from_schema():
    schema = {
        "field_groups": [
            {"group_key": "pe", "fields": [
                {"field_key": "pe_nose", "qwen_type": "J"},
                {"field_key": "pe_ear", "review_control": "judgement"},
                {"field_key": "pe_skin", "qwen_type": "T"},
            ]},
        ]
    }
    assert j_judgement_fields(schema) == {"pe_nose", "pe_ear"}
```

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_metrics.py -v`
Expected: FAIL（函数未定义）

- [ ] **Step 3: 实现——metrics.py 三处修正**

```python
# —— J 型"正常族"归一 ——
_J_NORMAL_PHRASES = ("正常", "通畅", "未见异常", "无异常", "阴性", "无压痛", "无肿大", "无充血水肿", "无黄染", "无发绀", "无皮疹")
_J_NORMAL_TOKEN = "正常"


def j_judgement_normalize(value: str | None) -> str:
    """J 型字段"正常族"语义归一：正常/通畅/未见异常/阴性 等 → 统一 token。"""
    if not value:
        return ""
    t = normalize_text(value)
    if any(phrase in t for phrase in _J_NORMAL_PHRASES):
        return _J_NORMAL_TOKEN
    return t


def j_judgement_fields(schema: dict) -> set[str]:
    """从 schema 提取 J 型字段（qwen_type=J 或 review_control=judgement）。"""
    keys: set[str] = set()
    for group in schema.get("field_groups", []) or []:
        for field in group.get("fields", []) or []:
            fk = field.get("field_key")
            if not fk:
                continue
            if field.get("qwen_type") == "J" or field.get("review_control") == "judgement":
                keys.add(fk)
    return keys


# —— 长文本字段宽松判定 ——
LONG_TEXT_FIELDS = {
    "chief_complaint",
    "hpi_initial_onset", "hpi_subsequent_course", "hpi_hospital_diagnosis",
    "hpi_treatment_medications", "hpi_recent_symptoms",
}


def sentence_overlap_ratio(golden: str, predicted: str) -> float:
    """按句切分后共有句占比（取金标视角）。容忍摘录范围差异，不放过大面积错摘。"""
    import re as _re

    def split(text: str) -> list[str]:
        return [s for s in _re.split(r"[。；;\n]", text or "") if s.strip()]

    g_sentences = split(golden)
    if not g_sentences:
        return 0.0
    g_norm = [normalize_text(s) for s in g_sentences]
    p_norm = [normalize_text(s) for s in split(predicted)]
    overlap = sum(1 for s in g_norm if s in p_norm)
    return round(overlap / len(g_norm), 4)
```

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_metrics.py -v`
Expected: PASS

- [ ] **Step 5: 写失败测试——evaluate_sample 修正生效**

在 `test_evaluation_runner.py` 追加：

```python
def test_evaluate_sample_skips_hallucination_when_golden_not_located():
    # 金标 value 在 ocr_text 不可定位（否定短语重建）→ 该字段不判幻觉
    sample = {
        "case_id": "case_001",
        "ocr_text": "否认\"糖尿病\"、\"冠心病\"等病史",
        "golden": [{"field_key": "pmh_diabetes", "status": "found", "value": "否认糖尿病病史"}],
    }
    result = {
        "payload": {},
        "candidates": [{
            "field_key": "pmh_diabetes", "status": "found",
            "value": "否认糖尿病病史", "ocr_correction": {"applied": False},
        }],
        "error": None,
    }
    out = evaluate_sample(sample, result)
    assert out["metrics"]["hallucination"] == 0
    assert out["metrics"]["value_correct"] == 1  # 值一致


def test_evaluate_sample_j_judgement_fields_use_normal_family_equivalence():
    sample = {
        "case_id": "case_001",
        "ocr_text": "鼻腔通畅，各鼻窦区无压痛",
        "golden": [{"field_key": "pe_nose", "status": "found", "value": "鼻腔通畅"}],
    }
    result = {
        "payload": {},
        "candidates": [{
            "field_key": "pe_nose", "status": "found",
            "value": "正常", "ocr_correction": {"applied": False},
        }],
        "error": None,
    }
    schema = make_schema_with_j_fields()
    out = evaluate_sample(sample, result, schema=schema)
    assert out["metrics"]["value_correct"] == 1


def make_schema_with_j_fields():
    schema = make_schema()
    schema["field_groups"][0]["fields"][0]["qwen_type"] = "J"
    return schema
```

注意 `make_schema()` 中 chief_complaint 字段的 `review_control` 是 "text"——新增的 j 字段 schema 需在现有 make_schema 基础上设置（上面的 `make_schema_with_j_fields` 已处理；若 chief_complaint 的 golden 是长文本，恰好也验证 LONG_TEXT_FIELDS 分支，但本测试聚焦 J 型归一，schema 的 review_control 覆盖即可）。

- [ ] **Step 6: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_runner.py -v`
Expected: FAIL（幻觉判定仍把"否认糖尿病病史"计为 hallucination=1；J 型仍 mismatch）

- [ ] **Step 7: 实现——evaluate_sample 修正**

`runner.py`：

```python
from .metrics import (
    compare_value, j_judgement_fields, j_judgement_normalize,
    sentence_overlap_ratio, status_matches, value_located_in_text,
    LONG_TEXT_FIELDS,
)
...
def evaluate_sample(sample: dict, result: dict, schema: dict | None = None) -> dict:
    ...
    j_fields = j_judgement_fields(schema) if isinstance(schema, dict) else set()
    ...
        # 幻觉（veto）：金标本身在 OCR 不可定位时跳过该字段的幻觉判定
        # （否定短语重建的期望输出不可定位；真错误由 value_mismatch 兜底）
        golden_located = value_located_in_text(golden_value, ocr_text)
        if not value_located_in_text(predicted_value, ocr_text, correction_applied) and golden_located:
            metrics["hallucination"] += 1
            if verdict in ("exact", "substring"):
                metrics["errors"].append(
                    {"case_id": sample.get("case_id"), "field_key": field_key, "kind": "hallucination"}
                )
        ...
        # value 判定：J 型字段先做"正常族"归一；长文本字段用核心句重合率
        if field_key in j_fields:
            g_n, p_n = j_judgement_normalize(golden_value), j_judgement_normalize(predicted_value)
            verdict = compare_value(g_n, p_n)
        elif field_key in LONG_TEXT_FIELDS:
            verdict = "exact" if sentence_overlap_ratio(golden_value, predicted_value) >= 0.6 else "mismatch"
        else:
            verdict = compare_value(golden_value, predicted_value)
```

注意实现顺序：value 判定在幻觉判定之前（`verdict` 变量先算再用于幻觉分支），与现有代码结构对齐——现有代码先算 `verdict = compare_value(...)`，再进幻觉判定；按此调整使两处复用同一个（可能被 J 型/长文本修正过的）verdict。

- [ ] **Step 8: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_runner.py app/backend/tests/test_evaluation_metrics.py -q`
Expected: PASS

- [ ] **Step 9: run_eval 传 schema**

`run_eval.py` 组装处：`evaluate_sample(sample, result)` → `evaluate_sample(sample, result, schema)`。

- [ ] **Step 10: 跑全量评估测试**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_runner.py app/backend/tests/test_evaluation_run_eval.py app/backend/tests/test_evaluation_metrics.py -q`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add app/backend/evaluation/metrics.py app/backend/evaluation/runner.py app/backend/evaluation/run_eval.py app/backend/tests/test_evaluation_metrics.py app/backend/tests/test_evaluation_runner.py
git commit -m "fix:指标修正(金标不可定位豁免幻觉/J型正常族归一/长文本核心句重合)"
```

---

### Task 5: 校准工具 calibrate.py

**Files:**
- Create: `app/backend/evaluation/calibrate.py`
- Create: `app/backend/tests/test_evaluation_calibrate.py`

**Interfaces:**
- 生产：`calibrate.cohen_kappa(table: list[list[int]]) -> float`——2×2 一致表（行=复核器 verdict：pass / suspicious|fail；列=裁定：不应标 / 应标）
- 生产：`calibrate.export_verdicts_file(verdicts_by_sample: list[dict], out_path: Path)`——每条 `{case_id, field_key, verdict, reason_code, comment, value, evidence_text}`；证据取字段 evidence 拼接（≤200 字）
- 生产：`calibrate.load_adjudications(path: Path) -> dict[tuple[str, str], bool]`——裁定文件 `{adjudications: [{case_id, field_key, should_flag}]}`
- 生产：`calibrate.compute_kappa(verdicts: list[dict], adjudications: dict) -> dict`——返回 `{kappa, n, table}`；verdict 二值化：suspicious/fail=应标侧，pass=不应标侧

**Claude 裁定执行方式（用户决策）：** 校准的人工裁定由 Claude 子 agent 模拟——导出裁定模板后，实施时开一个子 agent 逐条阅读（OCR 原文 + 字段声称值 + 复核器 verdict/comment），裁定 `should_flag` 写入裁定文件，再跑 compute_kappa。

- [ ] **Step 1: 写失败测试——kappa 计算**

```python
"""校准工具单测：Cohen's kappa、裁定模板导出与加载（纯确定性，无 LLM）。"""
import json

from pathlib import Path

from app.backend.evaluation.calibrate import (
    cohen_kappa,
    compute_kappa,
    export_verdicts_file,
    load_adjudications,
)


def test_cohen_kappa_known_value():
    # 2×2: [[pass/不应标, pass/应标], [suspicious/不应标, suspicious/应标]]
    # P0=(20+15)/50=0.70, Pe=(25*30+25*20)/2500=0.50 → kappa=0.40
    table = [[20, 5], [10, 15]]
    assert round(cohen_kappa(table), 4) == 0.4


def test_cohen_kappa_perfect_and_random():
    assert cohen_kappa([[30, 0], [0, 30]]) == 1.0
    assert cohen_kappa([[15, 15], [15, 15]]) == 0.0


def test_compute_kappa_builds_table_from_verdicts_and_adjudications():
    verdicts = [
        {"case_id": "c1", "field_key": "f1", "verdict": "pass"},
        {"case_id": "c1", "field_key": "f2", "verdict": "suspicious"},
        {"case_id": "c1", "field_key": "f3", "verdict": "fail"},
        {"case_id": "c1", "field_key": "f4", "verdict": "pass"},
    ]
    adjudications = {("c1", "f1"): False, ("c1", "f2"): True, ("c1", "f3"): True, ("c1", "f4"): True}
    out = compute_kappa(verdicts, adjudications)
    assert out["n"] == 4
    assert out["table"] == [[1, 1], [0, 2]]  # [[pass&不应标, pass&应标], [suspicious&不应标, suspicious&应标]]


def test_export_and_load_adjudication_template_roundtrip(tmp_path: Path):
    verdicts = [{"case_id": "c1", "field_key": "f1", "verdict": "suspicious",
                 "reason_code": "extraction_mistake", "comment": "值无证据", "value": "6次/分",
                 "evidence_text": "脉搏：66次/分"}]
    out = tmp_path / "verdicts.json"
    export_verdicts_file(verdicts, out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["items"][0]["field_key"] == "f1"
    # 裁定文件格式
    adj_path = tmp_path / "adjudications.json"
    adj_path.write_text(json.dumps({"adjudications": [{"case_id": "c1", "field_key": "f1", "should_flag": True}]}, ensure_ascii=False), encoding="utf-8")
    assert load_adjudications(adj_path) == {("c1", "f1"): True}
```

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_calibrate.py -v`
Expected: FAIL（calibrate 模块未定义）

- [ ] **Step 3: 实现——calibrate.py**

```python
"""验证器校准工具：导出复核 verdict → 裁定模板 → Cohen's kappa。

裁定执行方式：裁定由 Claude 子 agent 模拟人工（逐条判定"该字段是否应被
标记可疑"），写入裁定文件后 compute_kappa。kappa ≥ 0.7 才允许复核器上岗。
"""
import json
from pathlib import Path


def cohen_kappa(table: list[list[int]]) -> float:
    """2×2 一致表 Cohen's kappa。行=复核器判定，列=人工裁定。"""
    if len(table) != 2 or any(len(row) != 2 for row in table):
        raise ValueError("kappa 需要 2×2 一致表")
    n = sum(sum(row) for row in table)
    if n == 0:
        return 0.0
    p0 = (table[0][0] + table[1][1]) / n
    row_totals = [sum(r) for r in table]
    col_totals = [table[0][c] + table[1][c] for c in range(2)]
    pe = sum(row_totals[i] * col_totals[i] for i in range(2)) / (n * n)
    if pe == 1.0:
        return 0.0
    return round((p0 - pe) / (1 - pe), 4)


def export_verdicts_file(verdicts: list[dict], out_path: Path) -> None:
    """导出裁定模板：每条含 case_id/field_key/verdict/原因/声称值/证据片段。"""
    items = []
    for v in verdicts:
        items.append({
            "case_id": v.get("case_id"),
            "field_key": v.get("field_key"),
            "verdict": v.get("verdict"),
            "reason_code": v.get("reason_code"),
            "comment": v.get("comment"),
            "value": v.get("value"),
            "evidence_text": (v.get("evidence_text") or "")[:200],
        })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_adjudications(path: Path) -> dict[tuple[str, str], bool]:
    """加载裁定文件 → {(case_id, field_key): should_flag}。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    result = {}
    for item in data.get("adjudications", []):
        result[(item["case_id"], item["field_key"])] = bool(item["should_flag"])
    return result


def compute_kappa(
    verdicts: list[dict], adjudications: dict[tuple[str, str], bool]
) -> dict:
    """verdict 二值化（suspicious/fail=应标侧）后与裁定比对，返回 kappa/n/table。"""
    table = [[0, 0], [0, 0]]  # [复核pass][复核suspicious/fail] × [裁定不应标][裁定应标]
    n = 0
    for v in verdicts:
        key = (v.get("case_id"), v.get("field_key"))
        if key not in adjudications:
            continue
        n += 1
        verifier_flagged = v.get("verdict") in ("suspicious", "fail")
        should_flag = adjudications[key]
        table[1 if verifier_flagged else 0][1 if should_flag else 0] += 1
    return {"kappa": cohen_kappa(table) if n else 0.0, "n": n, "table": table}
```

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_calibrate.py -q`
Expected: PASS

- [ ] **Step 5: 加 CLI 入口（校准执行数据任务用）**

`calibrate.py` 末尾加 argparse 子命令（export / kappa），export 复用 `run_eval` 的样本循环（真实 LLM）：

```python
def main(argv: list[str] | None = None) -> None:
    import argparse
    import sys
    from datetime import datetime, timezone

    from ..services.algorithm_ports.qwen_vllm_client import QwenVLLMClient
    from ..services.copd_extraction.llm_client import OpenAICompatibleJsonClient
    from ..services.schema_loader import load_schema
    from .run_eval import _input_for, load_golden_samples
    from .runner import run_pipeline

    parser = argparse.ArgumentParser(description="验证器校准")
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="跑抽取+复核，导出裁定模板")
    p_export.add_argument("--golden-dir", default="data/evaluation/golden")
    p_export.add_argument("--schema", required=True)
    p_export.add_argument("--base-url", default="http://localhost:8000/v1")
    p_export.add_argument("--model", required=True)
    p_export.add_argument("--max-tokens", type=int, default=8192)
    p_export.add_argument("--out", required=True, help="裁定模板 JSON 路径")

    p_kappa = sub.add_parser("kappa", help="裁定文件 → kappa")
    p_kappa.add_argument("--verdicts", required=True)
    p_kappa.add_argument("--adjudications", required=True)

    args = parser.parse_args(argv)
    if args.command == "kappa":
        verdicts = json.loads(Path(args.verdicts).read_text(encoding="utf-8"))["items"]
        result = compute_kappa(verdicts, load_adjudications(Path(args.adjudications)))
        print(f"kappa={result['kappa']} n={result['n']} table={result['table']}")
        return
    if args.command == "export":
        schema = load_schema(args.schema)
        samples = load_golden_samples(Path(args.golden_dir))
        qwen = QwenVLLMClient(base_url=args.base_url, model=args.model, api_key="not-needed", timeout_seconds=360)
        llm_client = OpenAICompatibleJsonClient(qwen, max_tokens=args.max_tokens, temperature=0.0)
        from ..services.copd_extraction.verifier import FieldVerifier
        verifier = FieldVerifier(llm_client)
        items = []
        for sample in samples:
            result = run_pipeline(_input_for(sample, schema), llm_client, verifier=verifier)
            if result.get("error"):
                continue
            by_key = {c["field_key"]: c for c in result["candidates"]}
            for v in verifier.verify(result["candidates"], sample.get("ocr_text") or ""):
                field = by_key.get(v["field_key"]) or {}
                items.append({
                    "case_id": sample.get("case_id"),
                    "field_key": v["field_key"],
                    "verdict": v["verdict"],
                    "reason_code": v["reason_code"],
                    "comment": v["comment"],
                    "value": field.get("value", ""),
                    "evidence_text": "；".join(
                        (e.get("text") or "") for e in (field.get("evidence") or [])[:3]
                    ),
                })
        export_verdicts_file(items, Path(args.out))
        print(f"已导出 {len(items)} 条 verdict 到 {args.out}")


if __name__ == "__main__":
    main()
```

注意：export 里 `verifier.verify(...)` 会跑第二次复核（run_pipeline 内已跑一次）——为免重复，改为直接用 `result["candidates"]` 上 apply_verdicts 已合并的 quality_flags 反推，或接受一次重复调用（校准数据量小，可接受；实现者以简洁为准，保留对 run_pipeline 结果的 verify 再调用仅当验证行为一致）。简化方案：export 里不复跑，改从 `apply_verdicts` 后的 candidates 提取 `verifier_suspicious` flag 的 message 作为 comment，verdict 按 flag 存在与否二值化——但校准需要原始 verdict 分布（含 pass），因此**保持二次 verify 调用**（真实 LLM 温度 0.0 输出确定性，两次调用结果一致），此为可接受代价。

- [ ] **Step 6: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_calibrate.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/backend/evaluation/calibrate.py app/backend/tests/test_evaluation_calibrate.py
git commit -m "feat:校准工具(Cohen's kappa/裁定模板导出/CLI子命令)"
```

---

### Task 6: 审核数据回流

**Files:**
- Modify: `app/backend/services/review_service.py`（confirm 聚合回流）
- Create: `app/backend/evaluation/desensitize.py`
- Create: `app/backend/evaluation/feedback.py`
- Modify: `app/backend/evaluation/run_eval.py`（--golden-review 子集统计）
- Create: `app/backend/tests/test_review_feedback.py`
- Modify: `app/backend/tests/test_review_service.py`（回流聚合用例）

**Interfaces:**
- 生产：`review_service.ReviewService.confirm(task_id)` 内聚合并写 `evaluation/review_feedback/<task_id>.json`（store 相对路径），失败降级（try/except 记日志，不阻断审核确认）
- 生产：`desensitize.desensitize_text(text: str) -> str`——手机号 `1[3-9]\d{9}` → `***`；身份证/住院号/长数字串 `(?<!\d)\d{11,18}(?!\d)` → `***`
- 生产：`feedback.build_review_golden(feedback_dir: Path, golden_dir: Path, task_id: str) -> Path`——读回流文件 → 脱敏 → 写 `golden_dir/<task_id>.json`（`{case_id, source: "review", fields: [{field_key, status, value}]}`）
- 生产：`feedback.load_review_golden(golden_dir: Path) -> list[dict]`——加载所有 review 活资产为样本列表（供评估）
- 生产：`run_eval --golden-review <dir>`——对 review 样本跑 evaluate_sample，报告单独输出"review 修正字段错误率"

- [ ] **Step 1: 写失败测试——回流聚合（review_service）**

在 `test_review_service.py` 追加（复用现有 fixture 模式）：

```python
def test_confirm_collects_modified_fields_feedback():
    # 构造含修正字段的 review：auto_value != final_value
    # confirm() 后断言 store 里 evaluation/review_feedback/<task_id>.json 存在且字段正确
    # 修正字段：final_value 非空 → status found；final_value 空 → status not_found
```

实现约定（写测试时按此断言）：
- `feedback["fields"]` 只含 `auto_value != final_value` 的字段
- 每项 `{field_key, status, original_value, corrected_value}`；修正值非空 status=found，空串 status=not_found
- 写失败（如 store 异常）不抛，confirm 正常完成

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_service.py -v`
Expected: FAIL（无回流文件产生）

- [ ] **Step 3: 实现——review_service 聚合**

`confirm()` 内（`complete_review` 成功前后均可，选成功后）：

```python
def confirm(self, task_id: str) -> dict:
    ...
    result = self._task_service.complete_review(task_id, review_summary=summary)
    self._collect_review_feedback(task_id, review)
    return result

def _collect_review_feedback(self, task_id: str, review: dict) -> None:
    """聚合医生修正字段（auto_value≠final_value）写入回流文件；失败降级不阻断。"""
    fields = review.get("fields")
    if not isinstance(fields, list):
        return
    items = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        original = str(field.get("auto_value") or "")
        corrected = str(field.get("final_value") or "")
        if original == corrected:
            continue
        items.append({
            "field_key": field.get("field_key", ""),
            "status": "found" if corrected.strip() else "not_found",
            "original_value": original,
            "corrected_value": corrected,
        })
    if not items:
        return
    feedback = {
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": review.get("schema_version"),
        "fields": items,
    }
    try:
        self._store.write(f"evaluation/review_feedback/{task_id}.json", feedback)
    except Exception:  # noqa: BLE001 — 回流失败不阻断审核确认
        logger.warning("审核回流写入失败 task_id=%s", task_id, exc_info=True)
```

（`review_service.py` 需补 `import logging; logger = logging.getLogger(__name__)`。）

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_service.py -q`
Expected: PASS

- [ ] **Step 5: 写失败测试——脱敏 + 金标活资产**

创建 `app/backend/tests/test_review_feedback.py`：

```python
"""审核回流工具单测：脱敏、金标活资产生成与加载。"""
import json

from pathlib import Path

from app.backend.evaluation.desensitize import desensitize_text
from app.backend.evaluation.feedback import build_review_golden, load_review_golden


def test_desensitize_masks_phone_id_and_long_numbers():
    text = "联系电话13812345678，住院号12345678901，身份证110101199003078858。"
    out = desensitize_text(text)
    assert "13812345678" not in out
    assert "12345678901" not in out
    assert "110101199003078858" not in out
    assert "联系电话" in out and "住院号" in out


def test_desensitize_keeps_dates():
    text = "2023-12-22 入院，体温36.5℃"
    assert desensitize_text(text) == text


def test_build_review_golden_writes_desensitized_file(tmp_path: Path):
    feedback_dir = tmp_path / "feedback"
    golden_dir = tmp_path / "golden_review"
    feedback_dir.mkdir()
    (feedback_dir / "t001.json").write_text(json.dumps({
        "task_id": "t001", "created_at": "2026-08-01T00:00:00+00:00",
        "schema_version": "1.0.0",
        "fields": [
            {"field_key": "pe_pulse", "status": "found",
             "original_value": "6次/分", "corrected_value": "66次/分"},
            {"field_key": "pmh_diabetes", "status": "found",
             "original_value": "否认糖尿病", "corrected_value": "否认糖尿病 电话13812345678"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    path = build_review_golden(feedback_dir, golden_dir, "t001")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["source"] == "review"
    assert data["case_id"] == "t001"
    assert data["fields"][0] == {"field_key": "pe_pulse", "status": "found", "value": "66次/分"}
    assert "13812345678" not in json.dumps(data, ensure_ascii=False)


def test_load_review_golden_collects_samples(tmp_path: Path):
    golden_dir = tmp_path / "golden_review"
    golden_dir.mkdir()
    (golden_dir / "t001.json").write_text(json.dumps({
        "case_id": "t001", "source": "review",
        "fields": [{"field_key": "pe_pulse", "status": "found", "value": "66次/分"}],
    }, ensure_ascii=False), encoding="utf-8")
    samples = load_review_golden(golden_dir)
    assert len(samples) == 1
    assert samples[0]["golden"][0]["field_key"] == "pe_pulse"
```

- [ ] **Step 6: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_feedback.py -v`
Expected: FAIL（模块未定义）

- [ ] **Step 7: 实现——desensitize.py + feedback.py**

`desensitize.py`：

```python
"""轻量脱敏：手机号、身份证/住院号/长数字串。日期保留（病历日期是抽取语义）。"""
import re

_PHONE = re.compile(r"1[3-9]\d{9}")
_LONG_DIGITS = re.compile(r"(?<!\d)\d{11,18}(?!\d)")


def desensitize_text(text: str) -> str:
    if not text:
        return text
    out = _PHONE.sub("***", text)
    out = _LONG_DIGITS.sub("***", out)
    return out
```

`feedback.py`：

```python
"""审核数据回流：回流文件 → 脱敏 → 金标活资产（source: review），及评估加载。"""
import json
from pathlib import Path

from .desensitize import desensitize_text


def build_review_golden(feedback_dir: Path, golden_dir: Path, task_id: str) -> Path:
    """读回流文件，脱敏后写金标活资产（增量修正字段，不要求 61 字段全量）。"""
    feedback_path = feedback_dir / f"{task_id}.json"
    feedback = json.loads(feedback_path.read_text(encoding="utf-8"))
    fields = []
    for item in feedback.get("fields", []):
        value = desensitize_text(item.get("corrected_value") or "")
        fields.append({
            "field_key": item.get("field_key", ""),
            "status": item.get("status", "found"),
            "value": value,
        })
    golden = {
        "case_id": task_id,
        "source": "review",
        "schema_version": feedback.get("schema_version"),
        "golden": fields,
    }
    golden_dir.mkdir(parents=True, exist_ok=True)
    path = golden_dir / f"{task_id}.json"
    path.write_text(json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_review_golden(golden_dir: Path) -> list[dict]:
    """加载 review 活资产为评估样本（ocr_text 留空，只按修正字段子集统计）。"""
    samples = []
    for path in sorted(golden_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("source") != "review":
            continue
        samples.append({
            "case_id": data.get("case_id", path.stem),
            "ocr_text": data.get("ocr_text", ""),
            "pitfalls": ["review_feedback"],
            "golden": data.get("golden", []),
        })
    return samples
```

- [ ] **Step 8: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_feedback.py -q`
Expected: PASS

- [ ] **Step 9: run_eval --golden-review 子集统计**

`run_eval.py` 加 `--golden-review` 参数（目录）：加载 review 活资产 → 对每个样本跑抽取 → evaluate_sample → 报告追加一节：

```python
# 主流程后追加（--golden-review 提供时）：
from .feedback import load_review_golden
review_samples = load_review_golden(Path(args.golden_review)) if args.golden_review else []
review_results = []
for sample in review_samples:
    result = _run_pipeline_with_fallback(sample, schema, llm_client, args)
    review_results.append(evaluate_sample(sample, result, schema))
# build_report(review_results, {...meta + source: review}) → 控制台打印"review 修正字段错误率"
```

（报告单独生成一份 `..._review.json` 或以独立 section 输出，实现者选其一；要点：review 子集与 manual 分开统计。）

- [ ] **Step 10: 跑相关测试确认全绿**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_feedback.py app/backend/tests/test_review_service.py app/backend/tests/test_evaluation_run_eval.py -q`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add app/backend/services/review_service.py app/backend/evaluation/desensitize.py app/backend/evaluation/feedback.py app/backend/evaluation/run_eval.py app/backend/tests/test_review_feedback.py app/backend/tests/test_review_service.py
git commit -m "feat:审核数据回流(确认时聚合修正字段/脱敏/金标活资产source=review/评估子集统计)"
```

---

### Task 7: thinking 消融开关

**Files:**
- Modify: `app/backend/services/algorithm_ports/qwen_vllm_client.py`（complete_json / _common_kwargs 加 enable_thinking）
- Modify: `app/backend/services/copd_extraction/llm_client.py`（透传）
- Modify: `app/backend/evaluation/run_eval.py`（--thinking）
- Test: `app/backend/tests/test_qwen_vllm_client.py`、`app/backend/tests/test_evaluation_run_eval.py`

**Interfaces:**
- 生产：`QwenVLLMClient.complete_json(..., system_prompt=None, enable_thinking: bool | None = None)`——None/False → `chat_template_kwargs={"enable_thinking": False}`（现状）；True → `{"enable_thinking": True}`
- 生产：`OpenAICompatibleJsonClient.complete_json(prompt, system_prompt=None, enable_thinking: bool | None = None)`
- 生产：`run_eval --thinking` → `build_llm_client` 传 enable_thinking

- [ ] **Step 1: 写失败测试——enable_thinking 传入 chat_template_kwargs**

在 `test_qwen_vllm_client.py` 追加：

```python
def test_complete_json_thinking_switch():
    client = QwenVLLMClient(base_url="http://localhost:8000/v1", model="test-model",
                            api_key="not-needed", timeout_seconds=30)
    fake = FakeOpenAIClient('{"ok": true}')
    client._client = fake
    client.complete_json(prompt="p", max_tokens=10, temperature=0.0, enable_thinking=True)
    kwargs = fake.chat.completions.calls[0]
    assert kwargs["extra_body"]["chat_template_kwargs"] == {"enable_thinking": True}
    client.complete_json(prompt="p", max_tokens=10, temperature=0.0)
    kwargs2 = fake.chat.completions.calls[1]
    assert kwargs2["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}
```

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_vllm_client.py -v`
Expected: FAIL（enable_thinking 参数不存在）

- [ ] **Step 3: 实现**

`qwen_vllm_client.py`：

```python
def _common_kwargs(self, max_tokens: int, temperature: float, enable_thinking: bool = False) -> dict:
    return {
        "model": self._model,
        "temperature": temperature,
        "top_p": 1.0,
        "max_tokens": max_tokens,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": enable_thinking}},
    }

def complete_json(self, prompt, max_tokens, temperature, system_prompt=None, enable_thinking=None) -> dict:
    kwargs = self._common_kwargs(
        max_tokens=max_tokens, temperature=temperature,
        enable_thinking=bool(enable_thinking),
    )
    ...
```

`llm_client.py` 透传 enable_thinking。

`run_eval.py`：

```python
parser.add_argument("--thinking", action="store_true")

def build_llm_client(args) -> OpenAICompatibleJsonClient:
    qwen_client = QwenVLLMClient(
        base_url=args.base_url, model=args.model, api_key="not-needed", timeout_seconds=360,
    )
    return OpenAICompatibleJsonClient(
        qwen_client, max_tokens=args.max_tokens, temperature=args.temperature,
        enable_thinking=args.thinking,
    )
```

meta 记录：`"thinking": args.thinking`。

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_vllm_client.py app/backend/tests/test_evaluation_run_eval.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/algorithm_ports/qwen_vllm_client.py app/backend/services/copd_extraction/llm_client.py app/backend/evaluation/run_eval.py app/backend/tests/test_qwen_vllm_client.py
git commit -m "feat:thinking消融开关(--thinking传入chat_template_kwargs,CoT收益实测用)"
```

---

### Task 8: 数据任务（真实 LLM 执行）

**前提：** qwen-vision-vllm-server 已启动（`docker compose up -d` 或既有环境）；本任务产生 `data/evaluation/` 运行数据，不进 git。

**Files:**
- 运行产物：`data/evaluation/reports/*.json`（不进 git）
- 运行产物：`data/evaluation/calibration/*.json`（不进 git）

- [ ] **Step 1: 重跑修正后基线**

```bash
conda run -n manzufei_ocr python -m app.backend.evaluation.run_eval \
  --schema app/config/schemas/admission_record_structured_fields.v1.yaml \
  --model Qwen3.5-4B-AWQ-4bit
```
与旧基线 `data/evaluation/reports/baseline_admission_record_structured_fields_prompt.v1.json` 对比：幻觉数应显著下降（否定短语重建豁免），value 准确率应上升（J 型/长文本修正）。记录对比结论（供复盘）。

- [ ] **Step 2: 复核器消融对比（有复核 vs 无复核）**

```bash
conda run -n manzufei_ocr python -m app.backend.evaluation.run_eval \
  --schema app/config/schemas/admission_record_structured_fields.v1.yaml \
  --model Qwen3.5-4B-AWQ-4bit --no-verifier
```
对比：复核器引入的 suspicious 数量（quality_flags 中 verifier_suspicious 计数）、对指标的影响。

- [ ] **Step 3: 校准执行（Claude 子 agent 模拟人工裁定）**

```bash
conda run -n manzufei_ocr python -m app.backend.evaluation.calibrate export \
  --schema app/config/schemas/admission_record_structured_fields.v1.yaml \
  --model Qwen3.5-4B-AWQ-4bit \
  --out data/evaluation/calibration/<stamp>_verdicts.json
```
然后开一个 **Claude 子 agent**（general-purpose）：读取裁定模板，逐条对照（模板内附 value + evidence_text；必要时读 `data/evaluation/golden/<case>.json` 的 ocr_text），裁定每条 `should_flag: true/false`，写入 `<stamp>_adjudications.json`。再：

```bash
conda run -n manzufei_ocr python -m app.backend.evaluation.calibrate kappa \
  --verdicts data/evaluation/calibration/<stamp>_verdicts.json \
  --adjudications data/evaluation/calibration/<stamp>_adjudications.json
```
kappa ≥ 0.7 → 复核器达标；< 0.7 → 迭代复核 prompt（缺陷清单/few-shot/布局）重测（回 Task 2，改后重跑 Task 8 Step 2-3）。

- [ ] **Step 4: thinking 实测对比**

```bash
conda run -n manzufei_ocr python -m app.backend.evaluation.run_eval \
  --schema app/config/schemas/admission_record_structured_fields.v1.yaml \
  --model Qwen3.5-4B-AWQ-4bit --thinking
```
对比默认（thinking off）：status/value 准确率、幻觉数、契约非法数（截断风险）、任务级成功率、单样本耗时。结论记录供复盘与后续默认值决策。

- [ ] **Step 5: 汇总结果**

把四次运行的报告对比结论写入复盘文档（参照第一步复盘 HTML 惯例，放 master 的 `docs/可视化html/`），并更新 CLAUDE.md 的 evaluation 目录索引（如需要）。
