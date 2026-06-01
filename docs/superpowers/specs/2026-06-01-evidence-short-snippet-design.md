# Evidence 短片段约束设计

## 背景

5/29 修复（`7f94064 修复慢阻肺LLM抽取证据链与容错`）在 LLM 未返回 `evidence_phrase` 或返回过长时，把整段 section 文本回填到字段 `evidence`，并打上 `evidence_missing_fallback` 或 `evidence_too_long` 警告标记。

但前端 `ReviewSourcePanel` 用 `evidence` 在 OCR 文本中 `indexOf` 命中后整段 `<mark>` 包裹。task_058 重抽取数据中仍有 7 个字段的 `evidence` 长度 800-1400 字，触发整段高亮，掩盖了原始短片段应有的定位能力，也浪费了 5/29 修复的语义。

`docs/Front/Front_TDD/09-field-evidence.md` 约定 evidence 由后端返回，前端不补造、不推断。本次修复目标是把后端 evidence 收敛为短片段契约，从源头消除"整段高亮"。

## 范围

包含：

- 收紧后端 `evidence` 字段契约：必须为 `None` 或 `≤50` 字，且能在 `source_text` 中定位。
- 替换 `attach_source_text` 的整段回填为轻量 value 定位恢复（snippet windowing）。
- 在 `build_section_group_extraction_prompt` 中加入 evidence 短片段的最小 JSON 示例。
- 前端 `ReviewSourcePanel` 增加长度兜底（>100 字不高亮）。
- 同步更新 `app/backend/tests/test_copd_extractor.py` 和前端 `ReviewSourcePanel` 相关测试。

不包含：

- 字段值抽取逻辑改动。
- 医学规则、字段词典、OCR 纠偏规则、复杂正则。
- LangChain 或其他 LLM 编排框架。
- 调整全局 `llm_max_tokens` / `llm_extraction_batch_size`。
- LLM 定向重试或二次 prompt 编排。
- 字段 schema、prompt 中的 OCR 风险提示条目（5/29 已完成）。
- 重抽取、导出、批量导出等已闭合链路。
- 字段 status 状态机改动。

## 目标

1. 任意 `extracted` 字段的 `evidence` 满足：`len ≤ 50` 或 `None`。
2. 任意 `extracted` 字段的 `evidence`（非 None）能在 `source_text` 中 `in` 命中。
3. 任意 `extracted` 字段的 `evidence` 不等于 `source_text`。
4. LLM 未返回 `evidence_phrase`、返回为空或过长时，仍产出可定位短片段（用 `original_value` 在 `source_text` 中定位，截 50 字窗口），失败才置 `None`。
5. 现有 quality_flag 行为不变：`evidence_missing_fallback`、`evidence_too_long`、`evidence_not_in_source_text` 继续作为警告信号；`verification_status` 在 flag 触发时为 `suspicious`。
6. 前端 evidenceText 长度 > 100 字时放弃高亮；不补造、不推断。
7. 原始 `original_value` 抽取路径不因本次修复被规则改写。

## 非目标

- 不重写 prompt 主体（OCR 风险提示、字段列表、来源规则已在 5/29 spec 完成）。
- 不调整 schema 字段或 `medical_record.v1.yaml` / `copd_admission_record.v1.yaml`。
- 不修改 `n_ctx`、`llm_model_path`、模型加载方式。
- 不为不同字段定制 evidence 窗口大小（统一 50 字）。
- 不在 prompt 中输出 `quality_flags`（沿用 5/29 约定）。
- 不新增依赖（保持当前 requirements）。

## 现有 evidence 数据流（5/29 之后）

1. `_extract_section_groups` 调用 LLM，LLM 返回字段可能缺 `evidence_phrase`。
2. `_normalize_section_group_fields` 在 `evidence_phrase` 存在时复制为 `evidence`。
3. `attach_source_text` 在 `evidence` 缺失时回填 `source_text`（整段），在 `evidence` 存在时调用 `_validate_evidence_against_source_text`。
4. `validate_field_candidates` 校验 evidence 必须是字符串或 None。
5. review_service 把 evidence 透传给前端。

## 后端设计

### evidence 不变量

`attach_source_text` 输出后，对任意 `extraction_status == "extracted"` 的字段：

- `evidence is None` 或 `len(evidence) ≤ 50`。
- `evidence in source_text`（当 `evidence` 非 None 且 `source_text` 非 None）。

如果违反不变量，把 `evidence` 降级为 `None` 并打 flag。这条不变量是后端契约。

### 替换整段回填：value 定位恢复

`attach_source_text` 中：

- **当前行为**：`if not item.get("evidence"): item["evidence"] = source_text`。
- **新行为**：`if not item.get("evidence")` 或 `len(evidence) > 50` 或 `evidence not in source_text`：
  - 尝试 `_recover_evidence_from_value(item, source_text)`：
    - 用 `item["original_value"]` 在 `source_text` 中 `find` 第一个出现位置。
    - 找到：以该位置为中心，向前后扩展生成 50 字窗口（中点优先，可向一端倾斜），确保窗口包含 `original_value` 完整子串。
    - 找不到：`evidence = None`，加 `evidence_missing_fallback` 或 `evidence_not_in_source_text` flag。
  - 恢复成功：保留 evidence，加 `evidence_recovered_from_value` flag（用于审计），不视为新失败。
  - 恢复失败：`evidence = None`，按情况加 `evidence_missing_fallback` 或 `evidence_not_in_source_text`，`verification_status = "suspicious"`。
- **删除** 整段回填分支：`item["evidence"] = source_text`（无 evidence 时）和 `item["evidence"] = sections[FULL_TEXT_KEY]`（全文回退）。这两种路径不再产生 evidence。

### evidence 来源章节定位边界

`_recover_evidence_from_value` 严格要求在 `source_text`（即 `source_hint` 对应章节）内定位。如果 LLM 返回的 `source_hint` 本身指向 `全文`（`FULL_TEXT_KEY`），按现有契约进入 `source_section_not_found` 失败路径，evidence 保持 None，不做全文扫描恢复（避免 1500+ 字符窗口）。

### LLM 行为约定（保留现有 flag）

- LLM 返回有效 `evidence_phrase`（≤50 字且在 `source_text` 中）：原样使用，不加 recovery flag。
- LLM 返回 `evidence_phrase` 过长或不在 `source_text`：触发 recovery 路径，**丢弃** LLM 的 evidence。
- LLM 缺 `evidence_phrase`：直接走 recovery 路径。
- 任何 recovery 触发都打 `evidence_recovered_from_value` flag，便于审计。
- 不做 LLM 二次调用，不调整 prompt 让 LLM 重答。

### Prompt 小幅增强

`build_section_group_extraction_prompt` 末尾追加一段极简示例 + 一条硬约束：

```
示例输出（每个字段都必须包含 evidence_phrase）：
{"fields": [{"field_key": "temperature", "original_value": "36.7℃",
            "source_hint": "体格检查", "evidence_phrase": "体温：36.7℃",
            "confidence": 0.9, "ocr_correction": {"applied": false, "raw": "", "normalized": "", "reason": ""}}]}

硬约束：evidence_phrase 必填、≤50 字、必须是 OCR 原文短片段、严禁整段章节。
```

不要扩展 prompt 主体，不重复 OCR 风险提示，不引入 few-shot 多示例。约 +20 行 prompt 文案。

### Flag 调整

新增常量：

- `EVIDENCE_RECOVERED_FROM_VALUE = "evidence_recovered_from_value"`：value 定位恢复成功时附加。
- 现有 `EVIDENCE_MISSING_FALLBACK`、`EVIDENCE_TOO_LONG`、`EVIDENCE_NOT_IN_SOURCE_TEXT` 保留，触发条件由"整段回填失败"改为"recovery 失败"。

`_validate_evidence_against_source_text` 保留现有逻辑，但不再依赖 LLM 提供的 evidence 一定正确——它只做早期校验，主要恢复逻辑下沉到 `_recover_evidence_from_value`。

### 不动项

- `field_result.py` 的 `_normalize_extracted` 不变。
- `quality_checks.apply_quality_checks` 不变；只是它看到的 evidence 现在已是短片段或 None，薄规则仍然能正常跑。
- `review_service.py` 的 `evidence` 字段传递不变。
- `validate_field_candidates` 不变。
- 重抽取、导出、批量导出链路不变。

## 前端设计

### ReviewSourcePanel 兜底

`app/frontend/src/components/review/ReviewSourcePanel.tsx` 的 `renderTextWithHighlight`：

- 当前：`evidenceText` 非空且 `indexOf` 命中即整段 `<mark>`。
- 新增：定义 `MAX_EVIDENCE_HIGHLIGHT_CHARS = 100`（在文件顶部常量）。如果 `len(evidenceText) > 100`：
  - 不执行 `<mark>` 包裹，原样输出。
  - `sourceMessage` 文案改为"来源片段过长（>100 字），不进行高亮，请人工核验"。
- 其余路径行为不变。

### ReviewPage / FieldList

- `FieldList.tsx` 中已有的 `evidenceRiskFlags` 检查继续生效；新增 `evidence_recovered_from_value` 不视为风险，仅作审计展示（与其他 recovery 来源一致）。
- `ReviewPage` 不改 evidence 展示逻辑，只依赖 `ReviewSourcePanel` 的兜底。

### 边界

- 不补造 evidence，不从 OCR 推断字段值。
- 不修改 `app/frontend/src/api/review.ts` 的 evidence 字段结构。
- 不修改 `09-field-evidence.md` 现有 FE-EVD-001 到 FE-EVD-006 条目；新增 FE-EVD-007 到 FE-EVD-009 测试条目（见测试策略）。

## 测试策略

### 后端测试（先于实现落地）

更新 `app/backend/tests/test_copd_extractor.py`：

1. `test_attach_source_text_does_not_fill_whole_section_when_evidence_missing`：
   - LLM 返回字段缺 `evidence_phrase`，section 长度 > 50。
   - 断言 `result["evidence"]` 在 `result["source_text"]` 中、长度 ≤ 50，且 `result["evidence"] != result["source_text"]`。
2. `test_attach_source_text_recovers_evidence_from_original_value_in_section`：
   - section 含 `"体温：36.7℃ 脉搏：78次/分"`，`original_value="36.7℃"`。
   - 断言 evidence 包含 `"36.7℃"`，长度 ≤ 50，且在 section 内。
3. `test_attach_source_text_returns_none_evidence_when_value_not_locatable`：
   - section 无 `original_value` 子串。
   - 断言 `evidence is None`，quality_flag 包含 `evidence_missing_fallback` 或 `evidence_not_in_source_text`，`verification_status == "suspicious"`。
4. `test_attach_source_text_discards_llm_evidence_phrase_longer_than_50_chars`：
   - LLM 返回 `evidence_phrase` 长度 80。
   - 断言 evidence 长度 ≤ 50（或 None）；如果 LLM evidence 所在 section 内可由 value 定位，按 recovery 路径取短片段。
5. `test_attach_source_text_discards_llm_evidence_phrase_not_in_source_text`：
   - LLM 返回 `evidence_phrase` 不在 section 中。
   - 断言 evidence 由 recovery 路径产生或为 None。
6. `test_attach_source_text_does_not_use_full_text_key_for_recovery`：
   - LLM 返回 `source_hint="全文"`，section 为全文。
   - 断言 `evidence is None`，quality_flag 包含 `source_section_not_found`；不扫描全文生成窗口。
7. `test_attach_source_text_marks_recovered_evidence_with_flag`：
   - value 定位恢复成功时，`quality_flags` 包含 `evidence_recovered_from_value`。

更新 `app/backend/tests/test_copd_prompts.py`：

8. `test_section_group_prompt_contains_short_evidence_example`：断言 prompt 包含 `"evidence_phrase"` 示例 JSON 子串、≤50 字硬约束文案。

### 前端测试

更新 `app/frontend/src/components/review/ReviewSourcePanel.tsx` 的现有组件测试（`ReviewPage.test.tsx` 或 `ReviewSourcePanel` 独立测试）：

9. `FE-EVD-007` 组件：evidenceText 长度 > 100 时，OCR 文本不出现 `<mark>` 包裹的整段。
10. `FE-EVD-008` 组件：evidenceText 长度 ≤ 100 且存在时，行为不变（沿用 FE-EVD-002）。
11. `FE-EVD-009` 组件：evidenceText 缺失或为 `null` 时，沿用 FE-EVD-003 行为。

### 不改动的测试

- `test_copd_field_port.py`、`test_copd_quality_checks.py` 不变。
- `test_review_service.py` 不变。
- `test_backend_e2e.py` 不变。

### 运行命令

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_extractor.py app/backend/tests/test_copd_prompts.py -q
cd app/frontend && npm run test -- ReviewSourcePanel ReviewPage
```

## 验收标准

- 任意 `extraction_status == "extracted"` 字段：
  - `evidence is None` 或 `len(evidence) <= 50`。
  - `evidence` 非 None 时 `evidence in source_text`。
  - `evidence != source_text`（不会整段相等）。
- 任意后端单元测试新增 case 通过。
- 任意前端组件测试新增 case 通过。
- `app/backend/tests/test_copd_extractor.py` 全量通过。
- `app/backend/tests/test_copd_prompts.py` 全量通过。
- 前端 `ReviewSourcePanel` / `ReviewPage` 测试全量通过。
- 字段 `original_value` 不被本次修复改写：现有抽取值（如 `36.7℃`、`高血压、乙肝`）保持不变。
- 现有 flag（`evidence_missing_fallback`、`evidence_too_long`、`evidence_not_in_source_text`、`source_section_not_found`）继续触发对应 warning。
- `verification_status` 在新失败路径下保持 `suspicious`。
- 重抽取、导出、批量导出接口行为不变。

## 风险与回退

- 风险 1：value 定位恢复可能命中 value 出现多次的副作用（如 `"无"` 出现在多句否定中）。缓解：recovery 限制在 `source_text` 章节内，不跨章节；窗口以 value 第一次出现位置为中心。
- 风险 2：现有 task 数据历史 evidence 已写盘，重跑才会修复。缓解：本次只改抽取路径，不改历史数据；用户在审核页看到的是新任务的 evidence。
- 风险 3：少数字段 `original_value` 在 source_text 中被标点截断（如 `"36.7"` vs `"36.7℃"`）。缓解：现有 `apply_quality_checks` 已有 `value_not_in_evidence` 检查兜底；如果 `in` 不命中则 evidence=None。
- 回退：`attach_source_text` 行为变更可通过 `git revert` 回到 5/29 状态；前端兜底通过移除 `MAX_EVIDENCE_HIGHLIGHT_CHARS` 阈值恢复。

## 不在本 spec 内、留给后续

- LLM 二次重试 / few-shot 强化以提升 LLM 自发返回短 evidence 的概率。
- 任务级 evidence 历史清洗脚本。
- evidence 长度阈值做成任务配置项。
