# 前端 TDD — 字段来源核验

> PRD: PR-FE-005
> 注意：来源文本由后端或外部算法返回，前端不判断 evidence 是否真实匹配 OCR 文本。

| ID | 类型 | 用例 |
|----|------|------|
| FE-EVD-001 | 组件 | 字段有 `evidence` 和 `page_no` 时，字段旁展示来源页码和文本片段 |
| FE-EVD-002 | 组件 | 点击有来源字段时，文本区滚动并高亮对应片段 |
| FE-EVD-003 | 组件 | 字段无来源时展示"未定位来源"与"需人工确认"提示 |
| FE-EVD-004 | 组件 | 点击无来源字段时，文本区显示"此字段无对应来源文本" |
| FE-EVD-005 | 组件 | 来源页码不存在于页面列表时，显示"来源页不可用"，不抛异常 |
| FE-EVD-006 | 组件 | 导出前统计未定位来源字段数量并提示用户 |
| FE-EVD-007 | 组件 | `evidenceText` 长度 > 100 字时，OCR 文本不高亮该整段，并提示人工核验 |
| FE-EVD-008 | 组件 | `evidenceText` 长度 ≤ 100 且存在于 OCR 文本时，继续高亮对应片段 |
| FE-EVD-009 | 组件 | `evidenceText` 缺失或为 `null` 时，沿用无来源提示，不补造来源 |

## 高亮优先级（PR-FE-007 / T7）

> 后端返回的 evidence 可以携带 `start_offset` / `end_offset`，前端必须按 offset 优先、文本匹配兜底、不补造高亮的顺序处理高亮，禁止改写或修正 raw OCR。

| ID | 类型 | 用例 |
|----|------|------|
| FE-EVD-010 | 契约 | evidence 携带 `id` / `start_offset` / `end_offset` / `page_no` / `text` 时，标准化后字段仍保留这些字段 |
| FE-EVD-011 | 契约 | evidence 数组通过 `getReview` 标准化后保留 `attention_required` 标记 |
| FE-EVD-012 | 高亮 | OCR 原文包含 `## 品后诊断` 等错字标题时，前端不修正为 `最后诊断`，并按 evidence offset/原文片段定位 |
| FE-EVD-013 | 高亮 | evidence 只携带 `text` 不携带 `start_offset` / `end_offset` 时，按原文片段兜底匹配高亮 |
| FE-EVD-014 | 高亮 | evidence 携带 offset 但 offset 与原文片段不一致、原文片段也不在 OCR 中时，显示"来源片段未在 OCR 文本中定位，请核对"，不渲染 `<mark>` |
| FE-EVD-015 | 兜底 | 多个 evidence 单元 id 同时存在时，前端按 evidence 数组顺序取首个作为高亮目标 |
| FE-EVD-016 | 兜底 | 字段 evidence 同时含 `text` 和 `start_offset` / `end_offset` 且 offset 区间对应的原文片段与 `text` 一致时，offset 优先 |
| FE-EVD-017 | 兜底 | OCR 面板按后端保存的页顺序展示，跳转 evidence 时跳到 evidence 实际指向的页与位置，不重新排序 |
| FE-EVD-018 | 兜底 | evidence 文本超过 100 字时，前端不渲染大范围高亮，显示"来源片段较长，请人工核对" |
