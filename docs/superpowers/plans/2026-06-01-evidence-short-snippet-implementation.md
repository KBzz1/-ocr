# Evidence 短片段约束 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把慢阻肺字段抽取的 `evidence` 收敛为 `None` 或可定位的短片段（≤50 字），并让前端来源面板对历史超长 evidence 做兜底，避免整段 OCR 高亮。

**Architecture:** 后端删除 `attach_source_text` 的整段章节/全文回填，改为优先保留合法 LLM evidence，否则用 `original_value` 在对应 `source_text` 中恢复 50 字窗口；恢复成功追加 `evidence_recovered_from_value` 审计 flag，恢复失败保留既有 warning flag 语义并置 `suspicious`。Prompt 只追加极简 JSON 示例和短 evidence 硬约束。前端兜底放在 `ReviewSourcePanel` 内部，`ReviewPage` 不承担 evidence 推断或长度判断。

**Tech Stack:** Python 3.12 + pytest；TypeScript + React + Vitest + React Testing Library；不新增依赖。

---

## 文件结构

| 路径 | 角色 | 修改类型 |
|---|---|---|
| `app/backend/services/copd_extraction/extractor.py` | 新增 `EVIDENCE_RECOVERED_FROM_VALUE`、`_recover_evidence_from_value`、`_resolve_field_evidence`；重写 `attach_source_text` | Modify |
| `app/backend/services/copd_extraction/prompts.py` | `build_section_group_extraction_prompt` 追加短 evidence JSON 示例和硬约束 | Modify |
| `app/backend/tests/test_copd_extractor.py` | 覆盖短 evidence 不变量、recovery 成功/失败、旧 flag 保留、全文不恢复 | Modify |
| `app/backend/tests/test_copd_prompts.py` | 验证 prompt 包含短 evidence 示例与硬约束 | Modify |
| `app/frontend/src/components/review/ReviewSourcePanel.tsx` | 内部新增 `MAX_EVIDENCE_HIGHLIGHT_CHARS=100` 兜底，不高亮超长 evidence | Modify |
| `app/frontend/src/pages/review/ReviewPage.test.tsx` | 验证超长 evidence 不高亮、短 evidence 仍高亮、recovery flag 不当作 evidence 风险 | Modify |
| `docs/Front/Front_TDD/09-field-evidence.md` | 新增 FE-EVD-007/008/009 测试条目 | Modify |

不创建新代码文件；只修改上述文件。

---

## Task 1: 新增 evidence value 定位恢复函数

**Files:**
- Modify: `app/backend/services/copd_extraction/extractor.py`
- Test: `app/backend/tests/test_copd_extractor.py`

- [ ] **Step 1: 写失败测试**

在 `app/backend/tests/test_copd_extractor.py` 末尾追加：

```python
def test_recover_evidence_from_value_locates_and_creates_window():
    from app.backend.services.copd_extraction.extractor import _recover_evidence_from_value

    source_text = "体温：36.7℃ 脉搏：99次/分 呼吸：21次/分 血压：142/87mmHg"
    result = _recover_evidence_from_value("36.7℃", source_text, max_chars=50)

    assert result is not None
    assert "36.7℃" in result
    assert len(result) <= 50
    assert result in source_text


def test_recover_evidence_from_value_returns_none_when_value_not_in_source():
    from app.backend.services.copd_extraction.extractor import _recover_evidence_from_value

    assert _recover_evidence_from_value("40℃", "体温：36.7℃", max_chars=50) is None


def test_recover_evidence_from_value_returns_none_for_empty_value():
    from app.backend.services.copd_extraction.extractor import _recover_evidence_from_value

    assert _recover_evidence_from_value("", "anything", max_chars=50) is None
    assert _recover_evidence_from_value("   ", "anything", max_chars=50) is None


def test_recover_evidence_from_value_returns_none_when_value_exceeds_max_chars():
    from app.backend.services.copd_extraction.extractor import _recover_evidence_from_value

    long_value = "x" * 60
    assert _recover_evidence_from_value(long_value, long_value + " tail", max_chars=50) is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_extractor.py -k "recover_evidence_from_value" -v
```

Expected: FAIL，提示无法 import `_recover_evidence_from_value`。

- [ ] **Step 3: 新增常量和函数**

在 `app/backend/services/copd_extraction/extractor.py` 中，现有 `EVIDENCE_TOO_LONG` 常量之后新增：

```python
EVIDENCE_RECOVERED_FROM_VALUE = "evidence_recovered_from_value"
```

在 `_validate_evidence_against_source_text` 之后新增：

```python
def _recover_evidence_from_value(
    original_value: str,
    source_text: str,
    max_chars: int = MAX_EVIDENCE_PHRASE_CHARS,
) -> str | None:
    if not isinstance(original_value, str) or not original_value.strip():
        return None
    if not isinstance(source_text, str):
        return None
    value = original_value.strip()
    if len(value) > max_chars:
        return None
    index = source_text.find(value)
    if index < 0:
        return None
    window_radius = max(0, (max_chars - len(value)) // 2)
    start = max(0, index - window_radius)
    end = min(len(source_text), start + max_chars)
    start = max(0, end - max_chars)
    return source_text[start:end]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_extractor.py -k "recover_evidence_from_value" -v
```

Expected: `4 passed`。

- [ ] **Step 5: 提交**

```bash
git add app/backend/services/copd_extraction/extractor.py app/backend/tests/test_copd_extractor.py
git commit -m "feat(copd): 新增 evidence value 定位恢复函数"
```

---

## Task 2: 重写 attach_source_text 并补齐后端契约测试

**Files:**
- Modify: `app/backend/services/copd_extraction/extractor.py`
- Test: `app/backend/tests/test_copd_extractor.py`

- [ ] **Step 1: 先写/改后端契约测试**

在 `app/backend/tests/test_copd_extractor.py` 中替换旧的 missing/too-long/not-in-source 测试，并新增全文边界测试。测试代码如下：

```python
def _flag_names(item: dict) -> set[str]:
    return {flag["flag"] for flag in item.get("quality_flags", [])}


def test_copd_extractor_recovers_evidence_from_value_when_phrase_missing():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {"fields": [{"field_key": "pulse", "original_value": "78次/分", "source_hint": "体格检查"}]}

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("体格检查：体温36.7℃，脉搏78次/分，呼吸20次/分。")[0]

    assert result["evidence"] != result["source_text"]
    assert "78次/分" in result["evidence"]
    assert len(result["evidence"]) <= 50
    assert result["evidence"] in result["source_text"]
    assert result["verification_status"] == "suspicious"
    assert "evidence_recovered_from_value" in _flag_names(result)


def test_copd_extractor_returns_none_evidence_when_value_not_locatable():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {"fields": [{"field_key": "pulse", "original_value": "88次/分", "source_hint": "体格检查"}]}

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("体格检查：体温36.7℃，呼吸20次/分。")[0]

    assert result["evidence"] is None
    assert result["verification_status"] == "suspicious"
    assert "evidence_missing_fallback" in _flag_names(result)


def test_copd_extractor_discards_evidence_phrase_longer_than_50_chars_and_keeps_warning_flag():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    long_evidence = "体温36.7℃，脉搏78次/分，呼吸20次/分，血压128/76mmHg，神志清楚，双肺呼吸音粗，双下肢无水肿。"

    class LlmClient:
        def complete_json(self, prompt: str):
            return {
                "fields": [
                    {
                        "field_key": "pulse",
                        "original_value": "78次/分",
                        "evidence_phrase": long_evidence,
                        "source_hint": "体格检查",
                    }
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract(f"体格检查：{long_evidence}")[0]

    assert len(result["evidence"]) <= 50
    assert result["evidence"] != long_evidence
    assert "78次/分" in result["evidence"]
    assert result["evidence"] in result["source_text"]
    assert result["verification_status"] == "suspicious"
    flags = _flag_names(result)
    assert "evidence_too_long" in flags
    assert "evidence_recovered_from_value" in flags


def test_copd_extractor_discards_evidence_phrase_not_in_source_text_and_keeps_warning_flag():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {
                "fields": [
                    {
                        "field_key": "pulse",
                        "original_value": "78次/分",
                        "evidence_phrase": "脉搏88次/分",
                        "source_hint": "体格检查",
                    }
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("体格检查：体温36.7℃，脉搏78次/分。")[0]

    assert len(result["evidence"]) <= 50
    assert "78次/分" in result["evidence"]
    assert result["evidence"] in result["source_text"]
    assert result["verification_status"] == "suspicious"
    flags = _flag_names(result)
    assert "evidence_not_in_source_text" in flags
    assert "evidence_recovered_from_value" in flags


def test_copd_extractor_does_not_use_full_text_key_for_recovery():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {"fields": [{"field_key": "pulse", "original_value": "78次/分", "source_hint": "全文"}]}

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("主诉：咳嗽。\n体格检查：脉搏78次/分。")[0]

    assert result["evidence"] is None
    assert result["source_section"] is None
    assert result["source_text"] is None
    assert result["verification_status"] == "suspicious"
    assert "source_section_not_found" in _flag_names(result)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_extractor.py -k "evidence or full_text_key" -v
```

Expected: 多个 FAIL，仍有整段回填或旧 flag 不符合新契约。

- [ ] **Step 3: 重写 `attach_source_text` 并新增 `_resolve_field_evidence`**

将 `app/backend/services/copd_extraction/extractor.py` 中 `attach_source_text` 整段替换为：

```python
def attach_source_text(results: list[dict], sections: dict[str, str]) -> list[dict]:
    for item in results:
        if item.get("extraction_status") != "extracted":
            continue
        source_hint = item.get("source_hint") or item.get("source_section")
        if not source_hint:
            continue
        if source_hint == SOURCE_HINT_NOT_FOUND or source_hint == FULL_TEXT_KEY:
            item["source_section"] = None
            item["evidence"] = None
            item["source_text"] = None
            item["source_group_id"] = None
            item["verification_status"] = "suspicious"
            _append_quality_flag(
                item,
                SOURCE_SECTION_NOT_FOUND,
                {"comment": f"source_hint={source_hint} 不作为章节定位依据"},
            )
            continue
        source_text = sections.get(source_hint)
        if not source_text:
            item["evidence"] = None
            item["source_text"] = None
            item["source_group_id"] = None
            item["verification_status"] = "suspicious"
            _append_quality_flag(
                item,
                SOURCE_SECTION_NOT_FOUND,
                {"comment": f"source_hint={source_hint} 未在 OCR 章节中定位"},
            )
            continue
        item["source_hint"] = source_hint
        item["source_section"] = source_hint
        item["source_text"] = source_text
        item["source_group_id"] = _source_group_id(source_hint)
        _resolve_field_evidence(item, source_text)
    return results
```

在 `attach_source_text` 后新增：

```python
def _resolve_field_evidence(item: dict, source_text: str) -> None:
    raw_evidence = item.get("evidence")
    has_raw_evidence = isinstance(raw_evidence, str) and raw_evidence.strip()
    raw_evidence_too_long = has_raw_evidence and len(raw_evidence) > MAX_EVIDENCE_PHRASE_CHARS
    raw_evidence_not_in_source = has_raw_evidence and raw_evidence not in source_text

    if has_raw_evidence and not raw_evidence_too_long and not raw_evidence_not_in_source:
        item["evidence"] = raw_evidence
        return

    if raw_evidence_too_long:
        _append_quality_flag(item, EVIDENCE_TOO_LONG, {"comment": "evidence 超过50字，已丢弃"})
    elif raw_evidence_not_in_source:
        _append_quality_flag(
            item,
            EVIDENCE_NOT_IN_SOURCE_TEXT,
            {"comment": "evidence 未在来源章节中定位，已丢弃"},
        )

    recovered = _recover_evidence_from_value(
        item.get("original_value", ""),
        source_text,
        max_chars=MAX_EVIDENCE_PHRASE_CHARS,
    )
    if recovered is not None:
        item["evidence"] = recovered
        _append_quality_flag(
            item,
            EVIDENCE_RECOVERED_FROM_VALUE,
            {"comment": "evidence 缺失或非法，已用 original_value 在章节中定位恢复"},
        )
        if item.get("verification_status") != "failed":
            item["verification_status"] = "suspicious"
        return

    item["evidence"] = None
    if not raw_evidence_too_long and not raw_evidence_not_in_source:
        _append_quality_flag(
            item,
            EVIDENCE_MISSING_FALLBACK,
            {"comment": "缺少短 evidence 且无法用 original_value 恢复"},
        )
    if item.get("verification_status") != "failed":
        item["verification_status"] = "suspicious"
```

- [ ] **Step 4: 运行后端 extractor 测试**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_extractor.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add app/backend/services/copd_extraction/extractor.py app/backend/tests/test_copd_extractor.py
git commit -m "feat(copd): 收紧 evidence 契约并保留告警标记"
```

---

## Task 3: Prompt 增强

**Files:**
- Modify: `app/backend/services/copd_extraction/prompts.py`
- Test: `app/backend/tests/test_copd_prompts.py`

- [ ] **Step 1: 写失败测试**

在 `app/backend/tests/test_copd_prompts.py` 末尾追加：

```python
def test_section_group_prompt_contains_short_evidence_json_example():
    from app.backend.services.copd_extraction.prompts import build_section_group_extraction_prompt

    prompt = build_section_group_extraction_prompt("physical_exam", "体格检查：体温36.7℃。", ["temperature"])

    assert "evidence_phrase" in prompt
    assert '"field_key": "temperature"' in prompt
    assert "体温：36.7℃" in prompt
    assert "≤50" in prompt or "不超过50字" in prompt
    assert "严禁整段章节" in prompt or "不要输出整段章节" in prompt
    assert "示例输出" in prompt
```

- [ ] **Step 2: 运行测试确认失败**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py::test_section_group_prompt_contains_short_evidence_json_example -v
```

Expected: FAIL。

- [ ] **Step 3: 在 prompt 中追加示例和硬约束**

在 `build_section_group_extraction_prompt` 中，`OCR 原文：` 之前追加：

```python
示例输出（每个字段都必须包含 evidence_phrase）：
{{"fields": [{{"field_key": "temperature", "original_value": "36.7℃", "source_hint": "体格检查", "evidence_phrase": "体温：36.7℃", "confidence": 0.9, "ocr_correction": {{"applied": false, "raw": "", "normalized": "", "reason": ""}}}}]}}

硬约束：evidence_phrase 必填、≤50 字、必须是 OCR 原文短片段、严禁整段章节。
```

同时把原规则中的 evidence 约束改为：

```text
- evidence_phrase 必填、≤50 字、必须是 OCR 原文短片段、严禁整段章节或省略该字段。
```

- [ ] **Step 4: 运行 prompt 和后端相关测试**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py app/backend/tests/test_copd_extractor.py app/backend/tests/test_copd_field_port.py app/backend/tests/test_copd_quality_checks.py app/backend/tests/test_copd_field_result.py -q
```

Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
git add app/backend/services/copd_extraction/prompts.py app/backend/tests/test_copd_prompts.py
git commit -m "feat(copd): section_group prompt 追加短 evidence 示例"
```

---

## Task 4: ReviewSourcePanel 内部实现超长 evidence 兜底

**Files:**
- Modify: `app/frontend/src/components/review/ReviewSourcePanel.tsx`
- Test: `app/frontend/src/pages/review/ReviewPage.test.tsx`

- [ ] **Step 1: 写失败测试**

在 `app/frontend/src/pages/review/ReviewPage.test.tsx` 末尾追加：

```tsx
it('does not highlight evidenceText when it exceeds the short-snippet threshold', async () => {
  const scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView;

  const longEvidence = '体温：36.7℃ 脉搏：99次/分 呼吸：21次/分 血压：142/87mmHg 身高：175cm 体重：74kg BMI：24.2kg/m² 及多句冗长描述。';

  server.use(
    http.get('*/api/tasks/task_001/review', () =>
      HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          status: 'review',
          review_result: {
            ocr_text: `${longEvidence} 后续文本`,
            pages: [],
            fields: [
              {
                field_key: 'temperature',
                label: '体温',
                value: '36.7℃',
                status: 'unreviewed',
                evidence: [{ text: longEvidence }],
              },
            ],
          },
        },
      })
    )
  );

  render(<ReviewPage taskId="task_001" />);

  expect(await screen.findByText('来源片段过长（>100 字），不进行高亮，请人工核验')).toBeTruthy();
  expect(document.querySelector('mark')).toBeNull();
  expect(scrollIntoView).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd app/frontend && npm run test -- ReviewPage.test.tsx -t "does not highlight evidenceText when it exceeds"
```

Expected: FAIL。

- [ ] **Step 3: 修改 `ReviewSourcePanel.tsx`**

将 `app/frontend/src/components/review/ReviewSourcePanel.tsx` 改为由组件内部兜底。核心代码应包含：

```tsx
export const MAX_EVIDENCE_HIGHLIGHT_CHARS = 100;

export type SourceMessage = {
  kind: 'located' | 'missing' | 'unavailable' | 'too_long';
  text: string;
  evidenceText?: string;
};

function resolveSourceMessage(sourceMessage: SourceMessage | null): SourceMessage | null {
  if (!sourceMessage?.evidenceText) return sourceMessage;
  if (sourceMessage.evidenceText.length <= MAX_EVIDENCE_HIGHLIGHT_CHARS) return sourceMessage;
  return {
    kind: 'too_long',
    text: '来源片段过长（>100 字），不进行高亮，请人工核验',
  };
}

function renderTextWithHighlight(text: string, evidenceText: string | undefined, markRef: RefObject<HTMLElement>) {
  if (!evidenceText) return text;
  if (evidenceText.length > MAX_EVIDENCE_HIGHLIGHT_CHARS) return text;
  const index = text.indexOf(evidenceText);
  if (index < 0) return text;

  return (
    <>
      {text.slice(0, index)}
      <mark ref={markRef}>{evidenceText}</mark>
      {text.slice(index + evidenceText.length)}
    </>
  );
}
```

在组件中先计算：

```tsx
const effectiveSourceMessage = resolveSourceMessage(sourceMessage);
```

并将原先所有 `sourceMessage` 渲染和 `useEffect` 判断改为 `effectiveSourceMessage`。`useEffect` 只在 `effectiveSourceMessage.kind === 'located'` 时滚动。

不要修改 `ReviewPage.tsx` 的 `sourceMessage` 构造逻辑；前端兜底属于 `ReviewSourcePanel`。

- [ ] **Step 4: 运行前端测试**

```bash
cd app/frontend && npm run test -- ReviewPage.test.tsx -t "does not highlight evidenceText when it exceeds"
cd app/frontend && npm run test -- ReviewPage.test.tsx -t "highlights"
```

Expected: 两条命令均 PASS。

- [ ] **Step 5: 提交**

```bash
git add app/frontend/src/components/review/ReviewSourcePanel.tsx app/frontend/src/pages/review/ReviewPage.test.tsx
git commit -m "feat(front): ReviewSourcePanel 兜底超长 evidence 高亮"
```

---

## Task 5: 前端 TDD 文档和审计 flag 展示保护

**Files:**
- Modify: `docs/Front/Front_TDD/09-field-evidence.md`
- Test: `app/frontend/src/pages/review/ReviewPage.test.tsx`

- [ ] **Step 1: 更新 FE-EVD 测试条目**

在 `docs/Front/Front_TDD/09-field-evidence.md` 表格末尾追加：

```markdown
| FE-EVD-007 | 组件 | `evidenceText` 长度 > 100 字时，OCR 文本不高亮该整段，并提示人工核验 |
| FE-EVD-008 | 组件 | `evidenceText` 长度 ≤ 100 且存在于 OCR 文本时，继续高亮对应片段 |
| FE-EVD-009 | 组件 | `evidenceText` 缺失或为 `null` 时，沿用无来源提示，不补造来源 |
```

- [ ] **Step 2: 补审计 flag 不视为风险的测试**

在 `app/frontend/src/pages/review/ReviewPage.test.tsx` 中新增测试，构造字段 `quality_flags: [{ flag: 'evidence_recovered_from_value', severity: 'warning', message: '已用 original_value 恢复' }]`，断言字段卡片不出现 evidence 风险提示文案，例如不出现 `证据风险` / `来源风险`（按现有测试里的实际文案选择断言），同时字段仍可正常点击和高亮。

如果现有测试没有稳定的风险提示文案，只断言 `screen.queryByText(/证据风险|来源风险/)` 为 null，并保留正常字段渲染断言。

- [ ] **Step 3: 运行前端相关测试**

```bash
cd app/frontend && npm run test -- ReviewPage.test.tsx
```

Expected: 全 PASS。

- [ ] **Step 4: 提交**

```bash
git add docs/Front/Front_TDD/09-field-evidence.md app/frontend/src/pages/review/ReviewPage.test.tsx
git commit -m "test(front): 补充 evidence 短片段兜底用例"
```

---

## Task 6: 集成验证

**Files:** 无。

- [ ] **Step 1: 后端全量测试**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: 全 PASS。

- [ ] **Step 2: 前端全量测试**

```bash
cd app/frontend && npm run test
```

Expected: 全 PASS。

- [ ] **Step 3: 前端类型检查**

```bash
cd app/frontend && npx tsc --noEmit
```

Expected: 无 TypeScript error。如项目没有配置该命令或存在无关历史错误，记录具体输出，不要吞掉失败。

- [ ] **Step 4: 最终状态检查**

```bash
git status --short
```

Expected: working tree clean，或只剩用户明确保留的无关改动。

---

## 回退预案

| 改动点 | 回退方式 |
|---|---|
| Task 1 + 2 后端抽取行为 | `git revert <task-commit-sha>` 逐个回退对应提交 |
| Task 3 prompt | `git revert <task-commit-sha>` 回退 prompt 提交 |
| Task 4 + 5 前端和文档 | `git revert <task-commit-sha>` 逐个回退对应提交 |

回退后重新运行：

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
cd app/frontend && npm run test
```

---

## 风险与注意

1. `evidence_recovered_from_value` 是审计 flag，不应被前端当成 evidence 风险；`evidence_too_long`、`evidence_not_in_source_text`、`evidence_missing_fallback` 仍是 warning 信号。
2. recovery 只在 `source_hint` 对应章节内查找 `original_value`，不扫描 `全文`。
3. 历史 `data/results/*.json` 不清洗；只有重抽取或新任务会走新后端路径。前端兜底保护历史超长 evidence 的展示。
4. 不改字段值抽取逻辑，不改 `original_value`，不引入 OCR/图像处理逻辑。

---

## 验收标准

- [ ] 任意新抽取的 `extraction_status == "extracted"` 字段满足 `evidence is None` 或 `len(evidence) <= 50`。
- [ ] 任意非空 `evidence` 都能在 `source_text` 中命中，且不等于整段 `source_text`。
- [ ] 缺失、过长、不在来源章节内的 LLM evidence 都不会整段回填；可恢复时追加 `evidence_recovered_from_value`，同时保留对应旧 warning flag。
- [ ] `source_hint == "全文"` 不做 recovery，字段进入 `source_section_not_found` 可疑路径。
- [ ] Prompt 包含短 evidence JSON 示例和 `evidence_phrase` ≤50 字硬约束。
- [ ] `ReviewSourcePanel` 对 `evidenceText > 100` 不高亮并显示人工核验提示，短 evidence 行为不变。
- [ ] FE-EVD-007/008/009 已写入前端 TDD 文档。
- [ ] 后端全量测试、前端全量测试和 TypeScript 检查完成并记录结果。
