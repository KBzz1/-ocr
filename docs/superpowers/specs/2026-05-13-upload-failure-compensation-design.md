# BE-03-08 上传失败补偿设计

## 范围

对应 `docs/PRD任务清单.md` 中 BE-03-08：

- 文件或元数据保存失败时清理已创建的空页面项和临时文件。
- 不得留下 finish 可固化的空上传页。

本阶段聚焦手机上传 API 的失败补偿。当前上传路径会先调用 `SessionService.add_page()` 创建页面项，再调用 `PageService.save()` 保存图片、元数据并回写 `upload_ref`。如果保存阶段失败，必须撤销刚创建的 page，并清理当前上传产生的半成品文件。

本阶段覆盖：

- 文件类型非法、文件过大、非法 quad 等校验失败时，撤销本次新增 page。
- 图片文件写入成功但元数据写入失败时，删除本次图片文件并撤销 page。
- 元数据写入成功但 `attach_page_upload()` 失败时，删除本次图片文件、元数据文件并撤销 page。
- 补偿只影响本次失败上传产生的 page 和文件，不影响同一 session 已成功上传的页面。
- 已过期、已锁定会话仍沿用现有 guard，不额外创建补偿路径。

本阶段不覆盖：

- 真实图像处理、裁剪、透视矫正、OCR、LLM 或规则抽取。
- 上传重试队列或断点续传。
- 删除任务的完整清理策略（BE-09 已有任务级清理服务）。
- 前端上传重试 UI。
- 修改正常上传 API 响应结构。

## 权威依据

- `docs/产品PRD.md`：PR-BE-003、PR-BE-011、上传失败可恢复性。
- `docs/PRD任务清单.md`：BE-03-08。
- `docs/Shared/error-codes.md`：`INVALID_REQUEST_PARAMS`、`UNSUPPORTED_FILE_TYPE`、`FILE_TOO_LARGE`、`INVALID_QUAD_POINTS`。
- `docs/Backend/Backend_BDD/file-upload.md`。
- `docs/Backend/Backend_TDD/05-file-upload.md`。
- `docs/Backend/Backend_TDD/12-api-contracts.md`。
- `app/backend/services/session_service.py`。
- `app/backend/services/page_service.py`。
- `app/backend/routes/mobile.py`。

## 设计原则

- 会话 `pages` 是页序唯一来源；失败上传不能留下空 page。
- 补偿必须精确，只删除本次失败上传产生的 page_id 和文件路径。
- 正常上传路径不改变 API 契约。
- 不吞掉原始业务错误码；补偿失败不应掩盖上传失败的主错误。
- 文件删除只允许发生在配置的 storage_dir 下。

## 当前流程和问题

当前 `POST /api/mobile/{session_id}/pages` 主要流程：

```text
读取 multipart 图片和尺寸
  ↓
SessionService.add_page(session_id, upload_ref=None)
  ↓
PageService.save(session_id, page_id, page_no, image_data, ...)
  ↓
FileValidator.validate / quad 校验 / 图片写入 / 元数据写入 / attach_page_upload
  ↓
返回页面元数据
```

风险：

- `add_page()` 成功后，如果 `PageService.save()` 任一步失败，session 中已新增的 page 可能保留。
- 用户之后 finish 会把空 page 固化进任务，导致后续算法输入缺失。
- 如果图片文件已写入但元数据或 attach 失败，可能留下孤儿文件。

## 文件边界

```text
app/backend/
├── routes/
│   └── mobile.py                       # MODIFIED 在上传失败时调用补偿
├── services/
│   ├── session_service.py              # MODIFIED 增加 remove_unuploaded_page
│   └── page_service.py                 # MODIFIED 对半成品文件做局部清理
└── tests/
    ├── test_mobile_pages.py            # MODIFIED API 补偿集成测试
    ├── test_page_service.py            # MODIFIED 文件/元数据失败清理测试
    └── test_session_service.py         # MODIFIED 页面撤销测试
```

不修改：

- `app/backend/services/algorithm_ports/`。
- `app/backend/services/review_service.py`。
- `app/backend/services/export_service.py`。
- `app/backend/services/local_event_log.py`。
- `run.bat` / `stop.bat`。

## 服务契约

### SessionService

新增或复用一个精确撤销方法：

```python
def remove_unuploaded_page(self, session_id: str, page_id: str) -> dict:
    """仅当 page.upload_ref 为空时移除 page，防止误删已成功上传页面。"""
```

规则：

- 只允许 active session。
- 只移除指定 `page_id`。
- 如果 page 不存在，幂等返回当前 session。
- 如果 page 已有 `upload_ref`，必须抛出 `INVALID_REQUEST_PARAMS`，message 为“页面已有上传引用，不能按失败上传撤销”。
- 移除后保持剩余页面顺序稳定；是否重排 page_no 按现有 `delete_page()` 行为保持一致。

不得直接在路由补偿中调用现有 `delete_page()`，因为它不区分 `upload_ref`，容易误删已成功上传页面。实现必须新增 `remove_unuploaded_page()`，并在该方法内复用现有页序重排逻辑。

### PageService

`save()` 内部应在本次操作失败时清理它自己已经写出的文件：

```text
validate 失败：无文件写入，无需清理
quad 校验失败：无文件写入，无需清理
图片写入失败：不应留下完整文件；如有半文件则尝试删除
元数据写入失败：删除图片文件
attach_page_upload 失败：删除图片文件和元数据文件
```

`PageService.save()` 继续抛出原始 `AppError` 或异常，不把失败包装成成功。

实现约束：

- `PageService.save()` 内部只删除它自己本次已写出的 `image_path` 和 `metadata_path`，不得扫描或清理整个 session 目录。
- 删除路径必须经由 `JsonStore`/配置 storage 根目录解析，确认位于 storage 根目录内后再删除。
- `PageService.save()` 不调用 `SessionService.remove_unuploaded_page()`，避免服务层互相回滚；page 撤销只在路由层统一处理。
- 路由层只在 `add_page()` 已成功并获得 `page_id` 后，对 `PageService.save()` 的失败调用 `remove_unuploaded_page()`。

## API 行为

### POST /api/mobile/{session_id}/pages

成功路径不变：

- 返回 201。
- session page 有 `upload_ref`。
- 文件和元数据存在。

失败路径：

| 失败点 | API 错误 | 补偿 |
|--------|----------|------|
| 缺少 image | `INVALID_REQUEST_PARAMS` | 未创建 page，无补偿 |
| 缺少/非法尺寸 | `INVALID_REQUEST_PARAMS` | 未创建 page，无补偿 |
| 文件类型非法 | `UNSUPPORTED_FILE_TYPE` | 撤销本次 page |
| 文件过大 | `FILE_TOO_LARGE` | 撤销本次 page |
| quad 非法 | `INVALID_QUAD_POINTS` | 撤销本次 page |
| 图片/元数据写入失败 | 原错误或 `INTERNAL_SERVER_ERROR` | 撤销 page，删除半成品 |
| attach upload_ref 失败 | 原错误 | 撤销 page，删除图片和元数据 |

补偿失败处理：

- API 仍返回主错误。
- 可记录本地 warning，但不得改变错误码为补偿错误。
- 不在 error details 中包含完整路径、图片内容或敏感数据。

## 测试设计

### SessionService

- `remove_unuploaded_page` 能移除 active session 中 upload_ref 为空的 page。
- 已有 upload_ref 的 page 不会被补偿删除。
- 移除一个 page 不影响其他 page。
- expired/locked session 仍拒绝写操作。

### PageService

- 文件类型非法时不会写文件。
- quad 非法时不会写文件。
- monkeypatch `JsonStore.write` 模拟元数据写失败，已写图片被删除。
- monkeypatch `SessionService.attach_page_upload` 模拟回写失败，图片和元数据都被删除。
- 清理只删除本次 page 对应路径，不删除同 session 其他 page 文件。

### Mobile API

- 非图片上传返回 `UNSUPPORTED_FILE_TYPE`，session pages 没有新增空 page。
- 非法 quad 返回 `INVALID_QUAD_POINTS`，session pages 没有新增空 page。
- 模拟 `PageService.save` 抛错时，session pages 没有新增空 page。
- 一个成功页面后再上传失败，成功页面仍保留且 finish 可固化成功页面。

## 与其他任务的边界

- 与 BE-08 并行：无共享文件。BE-08 只读 review_result 并写 exports；本任务不读写 exports/review_result/task export_summary。
- 与 BE-10 并行：BE-10 可增加当前主流程 E2E 覆盖，但不在 BE-10 中实现补偿逻辑；BE-03 合并后再补上传失败补偿 E2E。
- 与 BE-09：不改日志结构。若当前 `_safe_event` 存在，上传失败日志不是本任务目标。
- 潜在共享文件：`app/backend/tests/test_mobile_pages.py`。若 BE-10 也新增 API 契约测试，应优先让 BE-10 新建 `test_api_contracts.py`，本任务只在现有上传测试文件中补失败补偿断言。

## 验收标准

- 失败上传后，`SessionService.get(session_id)["pages"]` 中不存在本次失败创建的 page。
- 失败上传后，storage_dir 下不存在本次失败 page 的图片或元数据文件。
- 已成功上传的页面不受失败补偿影响。
- 正常上传测试、会话测试、页面服务测试和后端全量测试通过。
