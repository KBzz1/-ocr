# 后端 TDD — 算法端口失败契约

> PRD: PR-BE-005, PR-BE-006
> 端口定义见 `02-algorithm-ports.md`

## 图像处理端口 (PR-BE-005)

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-IMG-001 | 契约 | 图像处理适配器未配置时，任务进入 `failed` 且错误码为 `ALGORITHM_MODULE_NOT_CONFIGURED` | 未配置被当成成功处理 |
| BE-IMG-002 | 契约 | 图像处理失败时仍保留原图和 `quad_points` 供排查，但不进入审核流程 | 元数据丢失或任务被放行 |
| BE-IMG-003 | 契约 | fixture 适配器返回 processed 路径时，系统记录路径并传给后续端口 | 路径未传递 |
| BE-IMG-004 | 契约 | 适配器抛异常时错误被映射为 `ALGORITHM_MODULE_FAILED`，任务进入 `failed` | 异常冒泡导致 500 崩溃或被降级 |

## 文档解析端口 (PR-BE-006)

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-DOC-001 | 契约 | 解析适配器未配置时，任务进入 `failed` 且错误码为 `ALGORITHM_MODULE_NOT_CONFIGURED` | 默认实现尝试 OCR 或返回空成功 |
| BE-DOC-002 | 集成 | 空解析结果被视为失败，保存错误记录，不暴露为可审核结果 | 空结果被当成成功 |
| BE-DOC-003 | 契约 | fixture 解析适配器返回的 `pages`、`blocks`、`tables` 被原样保存 | 系统改写算法结果 |
| BE-DOC-004 | 契约 | 单页解析失败、其他页成功时，保留每页 success/failed 标记，整体任务进入 `failed` | 部分失败被放行 |
| BE-DOC-005 | API | 失败任务请求文档结果时返回错误状态和排查信息，不返回空成功结果 | 空结果接口伪装成功 |

## 字段抽取端口 (PR-BE-006)

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-FLD-001 | 契约 | 字段抽取适配器未配置时，任务进入 `failed` 且错误码为 `ALGORITHM_MODULE_NOT_CONFIGURED` | 默认实现尝试规则抽取或返回空成功 |
| BE-FLD-002 | 集成 | 整任务字段结果为全空或无效输出时阻断任务并进入 `failed`；单字段为空或不确定时任务进入 `review`，字段保留 extraction_status 供人工核验 | 全空仍进入审核页 |
| BE-FLD-003 | 契约 | fixture 抽取适配器返回的字段值、来源、置信度被原样保存 | 系统修改候选值 |
| BE-FLD-004 | 契约 | 抽取适配器异常时任务进入 `failed`，并保存错误原因 | 异常导致任务崩溃或被降级 |
| BE-FLD-005 | API | `GET /api/tasks/{taskId}/structured-fields` 对失败任务返回错误，不返回空数组成功响应 | 空数组接口伪装成功 |
| BE-FLD-006 | 契约 | 抽取适配器返回 schema 外字段时任务进入 `failed`，错误码为 `ALGORITHM_CONTRACT_INVALID` | 非法字段被保存 |
| BE-FLD-007 | 契约 | 抽取适配器返回缺少 `field_key`、`original_value` 或状态非法的字段时任务进入 `failed` | 非法结构被保存 |

禁止测试裁剪、透视矫正、摩尔纹处理效果。慢阻肺专病字段抽取的规则分段、prompt harness、薄规则质量核验和 LLM 调用编排属于本仓库实现范围，其测试不在此限制内。
