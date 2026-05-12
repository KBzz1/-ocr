# 本地日志、隐私和离线检查设计（BE-09）

## 范围

对应 PRD `PR-BE-010`、部分 `PR-BE-001` 和 `docs/PRD任务清单.md` 中：

- BE-09-01 本地日志事件
- BE-09-02 离线依赖和模型目录检查
- BE-09-03 数据清理策略

本阶段目标是在不上传任何数据、不接入外部日志服务的前提下，记录本地关键事件、控制敏感信息泄漏，并提供离线部署所需的目录/依赖检查能力。

本阶段覆盖：

- 本地结构化日志事件：启动、会话创建、上传、finish、任务处理、审核、导出和失败。
- 错误日志只保存必要上下文：`task_id`、`session_id`、`error_code`、阶段和简短原因。
- 日志脱敏：身份证号、手机号、图片 base64、长文本字段、模型输出全文。
- 日志只写入 `logs/` 或配置指定的本地日志目录。
- 离线检查：运行目录、data/results/exports/logs 目录、schema 文件、模型目录占位和嵌入式 Python 目录。
- 数据清理策略的后端服务边界：只列出可清理项和任务级清理计划，不在本阶段做前端清理 UI。

本阶段不覆盖：

- Windows 启停脚本联调（BE-01 分支）。
- JSON/Excel 导出实现（BE-08）。
- 真实外部算法模块加载和模型调用。
- 删除所有历史数据的一键危险操作。
- 上传真实日志或遥测。

## 权威依据

- `docs/产品PRD.md`：PR-BE-001、PR-BE-010、隐私和部署边界。
- `docs/Backend/Backend_BDD/logging-privacy.md`。
- `docs/Backend/Backend_TDD/11-logging-privacy.md`。
- `docs/Backend/Backend_TDD/13-deployment.md`。
- `docs/Backend/Backend_TDD/16-prohibited-items.md`。
- `docs/Shared/error-codes.md`。

## 设计原则

- 日志是本地排查材料，不是病历数据副本。
- 默认日志字段白名单优先，避免把整段 request、response、OCR 文本或模型输出写入日志。
- 任何清理能力必须限定在仓库配置的数据目录内，拒绝路径穿越和根目录删除。
- 离线检查只检查本地路径和配置，不联网下载、探测或安装依赖。
- 日志系统失败不得破坏核心业务流程；可记录到 stderr，但不得让任务状态误变为成功。

## 文件边界

```text
app/backend/
├── services/
│   ├── local_event_log.py          # NEW 本地结构化事件写入、脱敏、轮转
│   ├── offline_check_service.py    # NEW 离线目录/依赖/配置检查
│   └── cleanup_service.py          # NEW 任务级数据清理计划和安全删除边界
├── routes/
│   └── maintenance.py              # NEW 本地维护 API：离线检查、清理预览/执行
├── tests/
│   ├── test_local_event_log.py
│   ├── test_offline_check_service.py
│   ├── test_cleanup_service.py
│   └── test_maintenance_routes.py
└── __init__.py                     # MODIFIED 注入日志服务、注册维护路由
```

允许小范围接入事件点：

- `SessionService`：会话创建、finish。
- `PageService`：上传成功/失败摘要。
- `TaskService` / `ProcessingOrchestrator`：处理开始、成功、失败。
- BE-07 合并后：ReviewService 记录审核保存/确认摘要。
- BE-08 合并后：ExportService 记录导出成功/失败摘要。

BE-09 不应修改 BE-07 的 review 数据结构，也不应修改 BE-01 的 `run.bat`/`stop.bat`。

## 日志格式

推荐 JSON Lines：

```json
{
  "ts": "2026-05-12T10:00:00+00:00",
  "level": "INFO",
  "event": "task_processing_failed",
  "task_id": "task_001",
  "session_id": "session_001",
  "error_code": "ALGORITHM_MODULE_FAILED",
  "stage": "field_extraction",
  "reason": "module_exception"
}
```

允许事件：

| event | level | 必要字段 |
|-------|-------|----------|
| `system_started` | INFO | `port`、`lan_addresses_count` |
| `config_default_used` | WARNING | `config_key` |
| `algorithm_module_not_configured` | WARNING | `stage` |
| `session_created` | INFO | `session_id` |
| `session_finished` | INFO | `session_id`、`task_id`、`page_count` |
| `page_uploaded` | INFO | `session_id`、`page_id`、`image_width`、`image_height` |
| `task_processing_started` | INFO | `task_id` |
| `task_processing_failed` | ERROR | `task_id`、`error_code`、`stage`、`reason` |
| `task_ready_for_review` | INFO | `task_id`、`schema_version` |
| `review_field_saved` | INFO | `task_id`、`field_key`、`status` |
| `review_confirmed` | INFO | `task_id`、`field_count` |
| `export_succeeded` | INFO | `task_id`、`format`、`relative_path` |
| `export_failed` | ERROR | `task_id`、`format`、`error_code` |

禁止日志字段：

- 完整病历原文、完整 OCR 文本、完整 LLM 输出。
- 身份证号、手机号。
- 图片 base64。
- 文件绝对路径中的用户名可保留为相对路径或脱敏路径。
- Python 调用栈默认不写入业务日志；测试环境可单独捕获异常。

## 脱敏规则

`sanitize_log_payload(payload: dict) -> dict`：

- 只允许标量、短 list 和短 dict；复杂对象转为类型名。
- key 命中 `text`、`merged_text`、`plain_text`、`ocr_text`、`model_output`、`base64` 时，替换为 `"[redacted]"`。
- 字符串长度超过 120 字符时截断为前 80 字符 + `"...[truncated]"`。
- 18 位身份证模式替换为 `"[id_card]"`。
- 11 位手机号模式替换为 `"[phone]"`。
- `data:image/...;base64,` 或长度异常的 base64 样式替换为 `"[base64]"`。

## 离线检查

API：

```text
GET /api/maintenance/offline-check
```

返回：

```json
{
  "success": true,
  "data": {
    "status": "warning",
    "checks": [
      {"key": "storage_dir", "status": "ok", "path": "data"},
      {"key": "exports_dir", "status": "ok", "path": "exports"},
      {"key": "logs_dir", "status": "ok", "path": "logs"},
      {"key": "schema_file", "status": "ok", "path": "app/config/schemas/medical_record.v1.yaml"},
      {"key": "embedded_python", "status": "warning", "path": "runtime/python/python.exe"},
      {"key": "ppstructure_models", "status": "warning", "path": "models/ppstructure"},
      {"key": "llm_models", "status": "warning", "path": "models/llm"}
    ]
  }
}
```

状态语义：

- `ok`：路径存在且类型符合预期。
- `warning`：可启动但能力可能不可用，例如模型目录为空。
- `failed`：核心目录无法创建或 schema 文件缺失，启动/处理不可正常完成。

离线检查不得发起网络请求，不得自动下载依赖或模型。

## 数据清理策略

本阶段只做任务级清理服务：

```text
GET /api/maintenance/tasks/{task_id}/cleanup-plan
POST /api/maintenance/tasks/{task_id}/cleanup
```

清理范围：

- `data/pages/` 中该任务 session 关联的上传文件和页面元数据。
- `data/results/{task_id}/` 或配置存储中的结果目录。
- `exports/{task_id}/` 中该任务导出文件。
- 该任务相关日志不物理删除，只在清理结果中提示日志按轮转策略处理。

安全规则：

- 只允许删除配置根目录下的相对路径。
- 拒绝空路径、根目录、`..`、绝对路径和符号链接逃逸。
- 默认先返回 cleanup plan；执行必须显式传入 `{"confirm": true}`。
- 删除失败时返回失败清单，不继续扩大删除范围。

## 并行与合并边界

- BE-09 可与 BE-07 并行。BE-07 先定义审核数据；BE-09 后续通过事件调用补日志，不反向修改审核契约。
- BE-09 可与 BE-01 并行。BE-01 负责脚本和启动体验；BE-09 负责后端离线检查 API 和日志。
- BE-08 合并后再补导出事件点；BE-09 当前 spec 可以先实现日志服务和维护 API。

## 测试重点

- 日志事件写入本地 JSONL，字段稳定。
- 脱敏函数屏蔽身份证、手机号、base64、长文本和模型输出全文。
- 日志服务不会写出完整病历原文或 OCR 文本。
- 离线检查不触发网络访问。
- 缺失非关键模型目录返回 warning，不导致系统启动失败。
- 缺失 schema 或无法创建数据目录返回 failed。
- 清理计划只包含允许根目录下路径。
- 路径穿越、绝对路径、根目录删除被拒绝。
- 后端全量测试保持通过。
