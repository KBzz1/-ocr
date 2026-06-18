# 后端 TDD — 算法端口失败契约

> PRD: PR-BE-005, PR-BE-006
> 端口定义见 `02-algorithm-ports.md`

## 图像处理边界 (PR-BE-005)

当前 MVP 默认不启用独立图像处理端口，不保存 `quad_points`，不要求 processed 图片路径。算法输入为任务原图列表；若新算法子系统需要预处理或批处理目录，必须先更新端口契约和测试。

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-IMG-001 | 契约 | 处理编排直接读取任务原图列表，按上传成功顺序传给文档解析端口 | 仍依赖 processed 路径或 quad 元数据 |
| BE-IMG-002 | 契约 | 原图缺失或任务图片列表为空时任务进入 `failed` 或返回 `TASK_EMPTY` | 空输入被当成成功处理 |
| BE-IMG-003 | 契约 | 未声明图像处理契约时，后端不得在处理前裁剪、矫正或伪造处理后图片 | 未经契约变更就执行了图像处理 |

## 文档解析端口 (PR-BE-006)

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-DOC-001 | 契约 | 解析适配器未配置时，任务进入 `failed` 且错误码为 `ALGORITHM_MODULE_NOT_CONFIGURED` | 默认实现尝试 OCR 或返回空成功 |
| BE-DOC-002 | 集成 | 空解析结果被视为失败，保存错误记录，不暴露为可审核结果 | 空结果被当成成功 |
| BE-DOC-003 | 契约 | fixture 解析适配器返回的 `pages`、`blocks`、`tables` 被原样保存 | 系统改写算法结果 |
| BE-DOC-004 | 契约 | 单页解析失败、其他页成功时，保留每页 success/failed 标记，整体任务进入 `failed` | 部分失败被放行 |
| BE-DOC-005 | API | 失败任务请求文档结果时返回错误状态和排查信息，不返回空成功结果 | 空结果接口伪装成功 |
| BE-DOC-006 | 契约 | 本机 OCR 常驻服务不可达、超时、返回结构非法或输出缺少页面时，任务进入 `failed` | OCR 服务失败被当成空成功 |

## 入院记录结构化字段抽取 (PR-BE-006)

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-FLD-001 | 契约 | 字段抽取端口未配置或调用异常时，任务进入 `failed` | 异常导致任务崩溃或被降级 |
| BE-FLD-002 | 集成 | 字段结果必须按 `admission_record_structured_fields.v1` schema 全量返回（61 字段）；全字段为空或全部 `not_found` 且无有效文本支撑时任务进入 `failed`；存在 `found` 但其余 `not_found` 时正常进入 `review` | 全空结果仍进入审核页 |
| BE-FLD-003 | 契约 | 字段值、evidence 数组（id/text/offset/page_no）、抽取状态、复核状态、医生可读的 `attention_required`/`attention_message` 被保存供审核页展示 | 字段级风险或证据丢失 |
| BE-FLD-004 | 契约 | 单字段可疑（`uncertain` / 证据缺失 / 证据 ID 无法定位 / OCR 疑似错读影响字段值）进入审核页标 `attention_required=true`，不直接让任务失败 | 单字段问题阻断整单 |
| BE-FLD-005 | API | 失败任务请求字段结果时返回错误，不返回空数组成功响应 | 空数组接口伪装成功 |
| BE-FLD-006 | 契约 | 字段结果包含 schema 外字段、缺失字段或重复字段时任务进入 `failed` | 非法字段被保存 |
| BE-FLD-007 | 契约 | 字段结果缺少必要元数据或状态非法时任务进入 `failed` | 非法结构被保存 |
| BE-FLD-008 | 契约 | 诊断字段（`diagnosis_preliminary` / `diagnosis_final`）只摘录原文记录，禁止模型主观补造、改写、推理诊断 | 模型自由生成诊断 |
| BE-FLD-009 | 契约 | `not_found` 是正常抽取状态，不默认触发 `attention_required`；既往史等全量字段中的未提及项不阻断进入审核 | 未提及字段被全量标黄 |
| BE-FLD-010 | 契约 | 医生可读的 `attention_message` 必须为中文自然语言；不得暴露内部 flag 原始名（如 `source_section_not_found`、`evidence_missing_fallback`） | 内部 flag 名称泄露给医生 |

业务契约测试禁止以裁剪、透视矫正、摩尔纹处理效果或真实模型准确率作为通过条件。慢阻肺字段契约、质量核验和审核流转使用手写样本、fixture 和可注入 LLM 客户端覆盖；算法子系统自身效果评估应另行设计，不混入后端业务契约测试。
