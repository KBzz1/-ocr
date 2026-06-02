# 后端 TDD — 图片上传、文件管理与元数据

> PRD: PR-BE-003

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-FILE-001 | 单元 | 文件类型校验允许 jpg/jpeg/png/bmp，拒绝 pdf、exe、txt | 非图片被接受 |
| BE-FILE-002 | 单元 | MIME、扩展名和 magic bytes 不一致时按安全策略拒绝 | 仅看扩展名导致误收 |
| BE-FILE-003 | 单元 | 文件大小超过配置阈值返回 `FILE_TOO_LARGE` | 超大文件被接受 |
| BE-FILE-004 | 单元 | 文件名净化移除路径穿越、控制字符和绝对路径 | 生成危险路径 |
| BE-FILE-005 | 集成 | 每个任务拥有独立目录，上传文件不覆盖其他任务文件 | 文件路径冲突 |
| BE-FILE-006 | 集成 | 同任务多页按上传成功顺序固化页序，路径包含 page_no 或稳定 page_id | 页序混乱 |
| BE-FILE-007 | API | `POST /api/mobile-upload/{task_id}/images` 校验任务 ID、上传令牌和 `uploading` 状态 | 未授权或非上传中任务仍可上传 |
| BE-FILE-008 | API | 图片上传只接收原图，不接收或保存 `quad_points` | 旧坐标字段仍影响上传契约 |
| BE-FILE-009 | 集成 | 上传阶段只保存原图、页序、上传时间和预览路径，不调用或伪造图像处理结果 | 测试发现本项目执行了图像处理 |
| BE-FILE-010 | API | 非 `uploading` 任务继续上传返回 `TASK_UPLOAD_CLOSED` | 已进入处理/审核任务仍可追加图片 |
| BE-FILE-011 | API | `POST /api/mobile-upload/{task_id}/finish` 在无图片时返回 `TASK_EMPTY` | 空任务进入处理 |
| BE-FILE-012 | API | 完成上传有图片时任务进入 `processing`，重复 finish 不重复触发多个处理任务 | 重复处理任务 |
| BE-FILE-013 | 集成 | 删除任务时只清理该任务目录，不能删除根目录或其他任务目录 | 清理范围过宽 |
