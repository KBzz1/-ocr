# 院内离线病历文书结构化采集与人工核验工作站 — 后端 TDD 测试用例（优化版）

> 基于 `docs/产品prd.md` 第 8 节后端需求编写。本文档用于指导后端按 TDD 实施，重点覆盖本地服务、会话、文件、任务、人工审核、导出、日志和算法模块边界。

## 0. 审查结论与边界修正

原后端测试用例整体方向可用，但存在三类关键问题：

- 越界实现了算法能力：原文中的“基于规则/模板抽取字段”“生成合并文本为非空”“OCR/解析结果包含主诉值”等用例，会把 OCR、LLM、图像处理责任留在本项目内。新版边界要求这些能力由外部团队交付，本项目必须只做接口、适配、持久化和错误上报。
- 状态和流程不完整：缺少 `uploading`、会话锁定、完成采集后页序固化、算法失败后的明确失败路径。
- 可测试性不够强：部分用例只描述“应处理错误”，缺少明确输入、输出、失败原因和边界断言。

优化后的原则是：后端只测试“业务壳”和“算法端口”，不测试算法本身。

## 1. 测试总原则

### 1.1 本项目后端负责

- 本地服务启动、离线运行、静态前端和 API 提供
- 采集会话创建、过期、锁定、页面新增/删除/排序/补拍
- 图片文件接收、任务目录隔离、元数据保存、文件清理
- 任务状态机、失败原因、重试、状态查询
- 算法模块的端口定义、调用编排、结果持久化、错误映射
- schema 读取和版本记录
- 人工审核结果保存、修改痕迹、确认校验
- Excel/JSON 导出、完整性检查
- 本地日志和隐私保护

### 1.2 本项目后端不负责

- 图像预处理、裁剪、透视矫正、去摩尔纹、去反光
- OCR 文字识别
- 文档版面解析算法
- LLM 字段抽取
- 医学诊断、医学建议、医学合理性判断
- 云端 API 或外部网络调用

涉及算法能力时，只允许测试：

- 端口是否被正确调用
- 外部模块返回的数据是否被原样持久化和暴露
- 外部模块未配置、异常、结构化字段为空或契约非法时是否进入 `failed` 并记录明确错误码
- 系统是否不崩溃、不吞错、不请求外网、不自行补规则兜底

## 2. 测试层次

| 层次 | 目的 | 示例 |
|------|------|------|
| 单元测试 | 验证纯逻辑 | 状态机、schema 校验、字段状态统计、路径生成 |
| 集成测试 | 验证本地存储和服务编排 | 文件保存、任务目录、结果 JSON、日志、导出文件 |
| API 测试 | 验证 HTTP 契约 | 状态码、响应结构、错误码、权限/锁定约束 |
| 契约测试 | 验证外部算法模块边界 | 成功 fixture 适配器、未配置适配器、异常适配器、契约非法适配器 |

所有测试必须可在断网环境下运行。

## 3. 统一状态与错误码

### 3.1 任务状态

| 状态值 | 含义 | 合法下一状态 |
|--------|------|--------------|
| `created` | 任务已创建 | `uploading`, `failed` |
| `uploading` | 上传中 | `uploaded`, `failed` |
| `uploaded` | 上传完成 | `processing`, `failed` |
| `processing` | 处理中 | `ready_for_review`, `failed` |
| `ready_for_review` | 待审核 | `confirmed`, `processing`, `failed` |
| `confirmed` | 已确认 | `exported` |
| `exported` | 已导出 | 无业务前进状态 |
| `failed` | 失败 | `processing` |

非法状态转换必须被拒绝并返回明确错误。

### 3.2 采集会话状态

| 状态值 | 含义 |
|--------|------|
| `active` | 可新增、删除、排序、补拍 |
| `expired` | 不可继续上传 |
| `locked` | 已完成采集，页序固化 |
| `cancelled` | 已取消 |

### 3.3 标准错误码

| 错误码 | 场景 |
|--------|------|
| `SESSION_NOT_FOUND` | 会话不存在 |
| `SESSION_EXPIRED` | 会话已过期 |
| `SESSION_LOCKED` | 会话已完成采集，禁止编辑 |
| `UNSUPPORTED_FILE_TYPE` | 非图片文件 |
| `FILE_TOO_LARGE` | 图片超过限制 |
| `INVALID_QUAD_POINTS` | 框选坐标格式非法 |
| `TASK_NOT_FOUND` | 任务不存在 |
| `INVALID_TASK_TRANSITION` | 非法状态流转 |
| `ALGORITHM_MODULE_NOT_CONFIGURED` | 算法模块未配置 |
| `ALGORITHM_MODULE_FAILED` | 外部算法模块异常 |
| `ALGORITHM_CONTRACT_INVALID` | 外部算法模块返回结构不符合契约 |
| `REVIEW_VALIDATION_FAILED` | 审核确认校验失败 |
| `EXPORT_VALIDATION_FAILED` | 导出前完整性校验失败 |
| `EXPORT_FAILED` | 导出失败 |

## 4. 算法模块端口与失败契约

后端应定义端口，但本项目内不得实现真实 OCR/LLM/图像处理，也不得实现基于规则的字段抽取兜底。端口未配置、调用异常、返回空结构化结果或返回结构不符合契约时，处理任务必须进入 `failed`。

```ts
type ImageProcessingPort = {
  process(input: { original_path: string; quad_points?: QuadPoints | null }): Promise<ImageProcessingResult>;
};

type DocumentParsingPort = {
  parse(input: { image_paths: string[]; task_id: string }): Promise<DocumentResult>;
};

type FieldExtractionPort = {
  extract(input: { document_result: DocumentResult; schema: FieldSchema }): Promise<StructuredField[]>;
};
```

失败契约：

- `ImageProcessingPort` 未配置或异常时，任务处理失败，错误码为 `ALGORITHM_MODULE_NOT_CONFIGURED` 或 `ALGORITHM_MODULE_FAILED`。
- `DocumentParsingPort` 未配置、异常或返回空页结果时，任务处理失败。
- `FieldExtractionPort` 未配置、异常、返回空字段候选、返回 schema 之外字段或返回契约非法字段时，任务处理失败。
- 处理流程不得崩溃；但也不得生成“空成功结果”、不得进入人工降级流程、不得允许后端基于 schema 或规则生成替代字段。

契约测试可以使用 fixture 适配器模拟外部团队未来交付结果，但不得在本项目实现识别或抽取算法。

## 5. 系统启动与离线运行（PR-BE-001）

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-SYS-001 | 单元 | 系统状态对象包含 `status`、`version`、`started_at`、`lan_addresses` | 状态函数不存在或字段缺失 |
| BE-SYS-002 | API | `GET /api/system/status` 返回 200 和 `status: "running"` | 路由未注册 |
| BE-SYS-003 | 集成 | 启动流程不访问外部网络、CDN、模型下载地址 | 测试拦截到外部请求 |
| BE-SYS-004 | 集成 | 断网环境下系统仍可启动并返回状态 | 启动依赖网络导致失败 |
| BE-SYS-005 | 单元 | 多网卡场景返回候选局域网地址，不把 `127.0.0.1` 作为手机默认地址 | 地址选择逻辑错误 |
| BE-SYS-006 | API | 手动指定局域网地址后，二维码 URL 使用用户选择地址 | 响应仍使用错误地址 |

## 6. 采集会话管理（PR-BE-002）

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-SES-001 | 单元 | 创建会话生成唯一 `session_id` | ID 为空或重复 |
| BE-SES-002 | 单元 | 创建会话记录 `created_at`、`expires_at`、`status: active` | 字段缺失 |
| BE-SES-003 | API | `POST /api/capture-sessions` 返回 201、会话信息和二维码 URL | 路由或响应结构缺失 |
| BE-SES-004 | API | `GET /api/capture-sessions/{id}` 返回会话页数、状态和过期时间 | 查询接口缺失 |
| BE-SES-005 | 单元 | 过期会话被判定为 `expired` | 过期判断缺失 |
| BE-SES-006 | API | 过期会话上传返回 409 和 `SESSION_EXPIRED` | 仍允许上传 |
| BE-SES-007 | API | 完成采集前允许新增、删除、排序、补拍页面 | 编辑接口未实现 |
| BE-SES-008 | API | `POST /api/mobile/{sessionId}/finish` 后会话变为 `locked` | 状态未锁定 |
| BE-SES-009 | API | `locked` 会话禁止新增、删除、排序页面，返回 `SESSION_LOCKED` | 完成后仍可编辑 |
| BE-SES-010 | 集成 | 完成采集后页面顺序固化，后续任务处理使用固化顺序 | 处理顺序仍受临时列表影响 |

## 7. 图片上传、文件管理与元数据（PR-BE-003、PR-BE-011）

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-FILE-001 | 单元 | 文件类型校验允许 jpg/jpeg/png/bmp，拒绝 pdf、exe、txt | 非图片被接受 |
| BE-FILE-002 | 单元 | MIME 与扩展名不一致时按安全策略拒绝 | 仅看扩展名导致误收 |
| BE-FILE-003 | 单元 | 文件大小超过配置阈值返回 `FILE_TOO_LARGE` | 超大文件被接受 |
| BE-FILE-004 | 单元 | 文件名净化移除路径穿越、控制字符和绝对路径 | 生成危险路径 |
| BE-FILE-005 | 集成 | 每个任务拥有独立目录，上传文件不覆盖其他任务文件 | 文件路径冲突 |
| BE-FILE-006 | 集成 | 同任务多页按固化页序保存，路径包含 page_no 或稳定 page_id | 页序混乱 |
| BE-FILE-007 | API | 上传带 `quad_points` 的页面时，页面记录保存四个角点、图片尺寸、上传时间 | 元数据缺失 |
| BE-FILE-008 | API | 缺少 `quad_points` 不阻断上传，字段保存为 null | 上传被错误拒绝 |
| BE-FILE-009 | 单元 | `quad_points` 缺点、非数字、越界、自相交时返回 `INVALID_QUAD_POINTS` | 非法坐标被接受 |
| BE-FILE-010 | 集成 | 上传阶段只保存原图和元数据，不调用或伪造图像处理结果 | 测试发现本项目执行了图像处理 |
| BE-FILE-011 | 集成 | 若外部 fixture 图像处理适配器返回 processed 路径，系统只记录该路径，不验证像素效果 | 后端试图判断图像质量 |
| BE-FILE-012 | 集成 | 删除任务时只清理该任务目录，不能删除根目录或其他任务目录 | 清理范围过宽 |

## 8. 任务生命周期（PR-BE-004）

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-TASK-001 | 单元 | 新任务默认状态为 `created` | 默认状态错误 |
| BE-TASK-002 | 单元 | 合法状态转换全部通过 | 状态机缺失 |
| BE-TASK-003 | 单元 | 非法状态转换返回 `INVALID_TASK_TRANSITION` | 非法转换被接受 |
| BE-TASK-004 | API | `GET /api/tasks` 支持按状态筛选 | 筛选无效 |
| BE-TASK-005 | API | `GET /api/tasks/{taskId}` 返回任务、页面、审核和导出摘要 | 详情缺字段 |
| BE-TASK-006 | 集成 | 任务失败时保存 `error_code`、`error_message`、`failed_at` | 失败原因丢失 |
| BE-TASK-007 | API | 失败任务可 `POST /api/tasks/{taskId}/retry` 回到 `processing` | 重试接口缺失 |
| BE-TASK-008 | 集成 | 处理过程中算法未配置时任务进入 `failed`，保存 `ALGORITHM_MODULE_NOT_CONFIGURED` | 未配置被当作可审核任务 |
| BE-TASK-009 | 集成 | 部分页处理失败时任务进入 `failed`，同时保留已成功页面的外部结果用于排查 | 成功结果被丢弃或任务被错误放行 |
| BE-TASK-010 | 集成 | 状态变更写入状态历史，包含时间和原因 | 无状态历史 |

合法状态转换表必须作为单元测试数据覆盖所有状态。

## 9. 算法端口与失败契约（PR-BE-005、PR-BE-006）

### 9.1 图像处理端口

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-IMG-001 | 契约 | 图像处理适配器未配置时，任务进入 `failed` 且错误码为 `ALGORITHM_MODULE_NOT_CONFIGURED` | 未配置被当成成功处理 |
| BE-IMG-002 | 契约 | 图像处理失败时仍保留原图和 `quad_points` 供排查，但不进入审核流程 | 元数据丢失或任务被放行 |
| BE-IMG-003 | 契约 | fixture 适配器返回 processed 路径时，系统记录路径并传给后续端口 | 路径未传递 |
| BE-IMG-004 | 契约 | 适配器抛异常时错误被映射为 `ALGORITHM_MODULE_FAILED`，任务进入 `failed` | 异常冒泡导致 500 崩溃或被降级 |

禁止测试裁剪、透视矫正、摩尔纹处理效果。

### 9.2 文档解析端口

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-DOC-001 | 契约 | 解析适配器未配置时，任务进入 `failed` 且错误码为 `ALGORITHM_MODULE_NOT_CONFIGURED` | 默认实现尝试 OCR 或返回空成功 |
| BE-DOC-002 | 集成 | 空解析结果被视为失败，保存错误记录，不暴露为可审核结果 | 空结果被当成成功 |
| BE-DOC-003 | 契约 | fixture 解析适配器返回的 `pages`、`blocks`、`tables` 被原样保存 | 系统改写算法结果 |
| BE-DOC-004 | 契约 | 单页解析失败、其他页成功时，保留每页 success/failed 标记，整体任务进入 `failed` | 部分失败被放行 |
| BE-DOC-005 | API | 失败任务请求文档结果时返回错误状态和排查信息，不返回空成功结果 | 空结果接口伪装成功 |

禁止测试 OCR 是否识别出“主诉”“现病史”等文本。

### 9.3 字段抽取端口

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-FLD-001 | 契约 | 字段抽取适配器未配置时，任务进入 `failed` 且错误码为 `ALGORITHM_MODULE_NOT_CONFIGURED` | 默认实现尝试规则抽取或返回空成功 |
| BE-FLD-002 | 集成 | 字段候选为空必须阻断任务并进入 `failed`，不得基于 schema 生成空字段 | 无字段仍进入审核页 |
| BE-FLD-003 | 契约 | fixture 抽取适配器返回的字段值、来源、置信度被原样保存 | 系统修改候选值 |
| BE-FLD-004 | 契约 | 抽取适配器异常时任务进入 `failed`，并保存错误原因 | 异常导致任务崩溃或被降级 |
| BE-FLD-005 | API | `GET /api/tasks/{taskId}/structured-fields` 对失败任务返回错误，不返回空数组成功响应 | 空数组接口伪装成功 |
| BE-FLD-006 | 契约 | 抽取适配器返回 schema 外字段时任务进入 `failed`，错误码为 `ALGORITHM_CONTRACT_INVALID` | 非法字段被保存 |
| BE-FLD-007 | 契约 | 抽取适配器返回缺少 `field_key`、`original_value` 或状态非法的字段时任务进入 `failed` | 非法结构被保存 |

禁止实现或测试“从文本中抽取主诉”等规则/LLM 行为。

## 10. 字段 Schema 管理（PR-BE-007）

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-SCH-001 | 单元 | schema 文件必须包含 `version`、`document_type`、字段组和字段 key | 缺字段仍通过 |
| BE-SCH-002 | 单元 | 重复 `field_key` 被拒绝 | 重复 key 被接受 |
| BE-SCH-003 | 单元 | 字段组顺序稳定，导出和前端展示使用同一顺序 | 顺序不稳定 |
| BE-SCH-004 | 集成 | 修改 schema 后，新任务读取新 schema，历史任务保留旧 `schema_version` | 历史任务被新 schema 影响 |
| BE-SCH-005 | API | `GET /api/schema/current` 返回当前 schema，前端可动态展示字段 | schema 接口缺失 |
| BE-SCH-006 | 集成 | schema 只用于校验外部字段候选、前端展示和导出顺序；不得在算法失败时生成替代字段 | schema 被用于兜底抽取 |
| BE-SCH-007 | 单元 | 不同 `document_type` 可选择不同 schema；第一版默认通用 schema | 文书类型选择失败 |

## 11. 人工审核结果保存（PR-BE-008）

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-REV-001 | API | 获取审核结果时，若无人工结果则基于外部候选字段生成初始审核记录 | 首次审核无数据 |
| BE-REV-002 | API | 修改字段保存 `final_value`，保留 `original_value` | 原值被覆盖 |
| BE-REV-003 | 集成 | 人工审核结果与自动候选结果分开存储 | 自动结果被覆盖 |
| BE-REV-004 | API | 确认字段、修改字段、清空字段、标记存疑分别更新字段状态 | 状态不变 |
| BE-REV-005 | 集成 | 多次修改字段保留修改历史，包含修改前后值和时间 | 历史缺失 |
| BE-REV-006 | API | 重新打开任务优先返回人工 `final_value` | 返回自动候选值 |
| BE-REV-007 | 单元 | 确认任务前统计未审核、存疑、为空、无来源字段数量 | 统计错误 |
| BE-REV-008 | API | 存在阻断项时确认返回 `REVIEW_VALIDATION_FAILED` 和字段列表 | 错误不明确 |
| BE-REV-009 | API | 有未审核、存疑或未确认可接受的空值字段时，确认任务必须返回 `REVIEW_VALIDATION_FAILED` | 阻断项被放行 |
| BE-REV-010 | 集成 | 算法失败任务不能保存审核、确认或导出，必须返回任务失败错误 | 失败任务仍可被审核 |

## 12. 导出服务（PR-BE-009）

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-EXP-001 | 单元 | 导出前完整性检查返回未审核、存疑、为空、无来源数量 | 统计缺失 |
| BE-EXP-002 | 单元 | JSON 导出结构包含任务编号、导出时间、schema 版本、字段结果和审核状态 | 结构缺字段 |
| BE-EXP-003 | 集成 | JSON 导出字段顺序稳定，与 schema 顺序一致 | 输出顺序不稳定 |
| BE-EXP-004 | 单元 | Excel 数据按字段组组织，字段值来自人工 `final_value` | 使用了自动候选值 |
| BE-EXP-005 | 集成 | 导出文件保存到任务独立 `exports/` 目录 | 文件路径错误 |
| BE-EXP-006 | API | `GET /api/tasks/{taskId}/export/json` 返回下载响应和正确文件名 | 响应头错误 |
| BE-EXP-007 | API | `GET /api/tasks/{taskId}/export/excel` 返回下载响应和正确文件名 | 响应头错误 |
| BE-EXP-008 | API | 未确认任务导出必须返回 `EXPORT_VALIDATION_FAILED`，不允许 warning 后继续导出 | 未确认任务被导出 |
| BE-EXP-009 | 集成 | 导出失败不修改审核结果和任务确认状态 | 失败产生脏状态 |
| BE-EXP-010 | 集成 | 导出成功后记录导出时间、格式和文件路径，任务可变为 `exported` | 导出记录缺失 |

## 13. 本地日志与隐私（PR-BE-010）

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-LOG-001 | 集成 | 系统启动、会话创建、上传、finish、处理、审核、导出写入日志 | 事件缺失 |
| BE-LOG-002 | 集成 | 错误日志包含 `task_id`、`session_id`、`error_code`、简短原因 | 上下文缺失 |
| BE-LOG-003 | 集成 | 日志不记录完整 OCR 文本、完整病历原文、身份证号、图片 base64 | 敏感信息泄露 |
| BE-LOG-004 | 单元 | 日志脱敏函数可屏蔽身份证、手机号、长文本字段 | 脱敏失败 |
| BE-LOG-005 | 集成 | 日志只保存在本地目录，不上传、不请求外部日志服务 | 存在外部请求 |
| BE-LOG-006 | 集成 | 日志轮转或大小限制生效，避免无限增长 | 日志无上限 |

## 14. API 契约与错误响应

统一错误响应：

```json
{
  "error": {
    "code": "SESSION_EXPIRED",
    "message": "采集会话已过期",
    "details": {}
  }
}
```

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-API-001 | API | 所有成功响应包含稳定 JSON 结构或明确下载响应头 | 响应结构漂移 |
| BE-API-002 | API | 所有失败响应使用统一 `error.code/message/details` | 错误格式不统一 |
| BE-API-003 | API | 404 任务、会话、页面均返回对应错误码，不返回堆栈 | 泄露堆栈 |
| BE-API-004 | API | 上传接口缺少文件返回 400 和明确错误 | 500 崩溃 |
| BE-API-005 | API | 重复 finish 同一会话幂等返回 locked 状态，不重复创建任务 | 重复任务 |
| BE-API-006 | API | 重复上传同一 page_id 按幂等策略处理，不产生重复页序 | 页序重复 |
| BE-API-007 | API | 删除不存在页面返回 404，不影响其他页面 | 错误删除 |
| BE-API-008 | API | 排序请求含未知 page_id 时整体拒绝，不局部应用 | 顺序被破坏 |

## 15. 部署与本地运行

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-DEP-001 | 集成 | 测试环境不需要 Docker、WSL、GPU、云服务客户端即可运行核心测试 | 环境依赖过重 |
| BE-DEP-002 | 集成 | 缺少外部算法模块时启动成功，但触发处理任务会失败并返回 `ALGORITHM_MODULE_NOT_CONFIGURED` | 启动失败或处理被降级 |
| BE-DEP-003 | 集成 | 配置外部 fixture 算法模块后，处理流程使用 fixture 返回，且所有字段候选来自 fixture | 适配器注入失败或后端自行抽取 |
| BE-DEP-004 | 集成 | 本地数据目录、上传目录、结果目录、导出目录不存在时自动创建 | 目录缺失导致失败 |
| BE-DEP-005 | 集成 | 配置文件缺失时使用安全默认值并记录 warning | 配置缺失崩溃 |

## 16. 推荐 fixtures

### 16.1 上传图片 fixture

| 文件 | 用途 | 注意 |
|------|------|------|
| `sample_page_1.jpg` | 普通图片上传 | 不用于 OCR 正确性断言 |
| `sample_page_2.png` | 多页上传 | 不用于 OCR 正确性断言 |
| `sample_large.jpg` | 文件大小校验 | 可用生成文件替代真实大图 |
| `sample_not_image.pdf` | 非图片拒绝 | 验证文件类型 |
| `sample_poly_invalid.json` | 非法四边形 | 验证坐标校验 |

### 16.2 算法未配置错误 fixture

```json
{
  "task_id": "task_20260511_0001",
  "status": "failed",
  "error_code": "ALGORITHM_MODULE_NOT_CONFIGURED",
  "error_message": "算法模块未配置，无法生成结构化字段"
}
```

### 16.3 fixture 解析结果

```json
{
  "pages": [
    {
      "page_no": 1,
      "status": "success",
      "plain_text": "fixture text from external parser",
      "blocks": [],
      "tables": []
    }
  ],
  "merged_text": "fixture text from external parser"
}
```

说明：该文本只用于验证“外部结果被原样保存”，不用于验证 OCR 或语义准确性。

### 16.4 fixture 字段候选

```json
[
  {
    "field_key": "chief_complaint",
    "field_name": "主诉",
    "original_value": "fixture value from external extractor",
    "evidence": "fixture evidence",
    "page_no": 1,
    "confidence": "medium"
  }
]
```

说明：字段值只代表外部模块返回，不代表本项目抽取能力。

### 16.5 通用 schema fixture

```json
{
  "version": "1.0.0",
  "document_type": "general_medical_record",
  "groups": [
    {
      "group_key": "basic_info",
      "group_name": "患者基本信息",
      "fields": [
        { "field_key": "name", "field_name": "姓名", "value_type": "text" },
        { "field_key": "gender", "field_name": "性别", "value_type": "text" }
      ]
    },
    {
      "group_key": "admission_course",
      "group_name": "入院/病程信息",
      "fields": [
        { "field_key": "chief_complaint", "field_name": "主诉", "value_type": "long_text" }
      ]
    }
  ]
}
```

## 17. TDD 实施顺序

1. 状态机、错误码、统一响应结构。
2. 系统状态、离线启动、局域网地址选择。
3. 采集会话创建、过期、锁定。
4. 上传文件校验、任务目录、页面元数据。
5. 页面删除、排序、finish 幂等和页序固化。
6. 算法端口失败契约：未配置、异常、空结构化字段、契约非法。
7. 任务处理编排：算法失败进入 `failed`，成功 fixture 进入 `ready_for_review`。
8. schema 管理和候选字段契约校验。
9. 人工审核保存、确认校验、修改历史。
10. JSON/Excel 导出和导出前完整性检查。
11. 日志、隐私、部署与断网测试。
12. API 全量契约测试和关键 E2E。

每个条目执行时必须：

- 先写失败测试。
- 运行单个测试确认 RED，失败原因正确。
- 写最小实现。
- 运行单个测试确认 GREEN。
- 运行相关测试集确认无回归。
- 重构后再次运行相关测试。

## 18. 禁止项

- 禁止在本项目实现 OCR、LLM、自动边界识别、透视矫正或图像增强算法。
- 禁止用规则抽取“主诉”“姓名”等字段来冒充 LLM 抽取。
- 禁止测试真实病历图片的识别准确率。
- 禁止联网下载模型、依赖或调用云 API。
- 禁止在日志和错误响应中输出完整病历原文、身份证号、图片 base64。
- 禁止把算法模块未配置当成系统启动失败；但触发任务处理时必须失败并明确报错，不能进入人工降级路径。
