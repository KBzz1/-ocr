# 后端 TDD — 图片上传、文件管理与元数据

> PRD: PR-BE-003, PR-BE-011

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
| BE-FILE-013 | API | `PUT /api/mobile/{sessionId}/pages/{pageId}/quad` 保存新的 `quad_points` 和更新时间，不要求重新上传原图 | 重新框选无法保存或错误要求文件 |
| BE-FILE-014 | API | 更新 `quad_points` 时复用上传坐标校验，非法坐标返回 `INVALID_QUAD_POINTS` | 非法坐标被接受 |
| BE-FILE-015 | API | `locked` 或 `expired` 会话拒绝更新 `quad_points`，返回对应会话错误码 | 锁定或过期后仍可编辑 |
| BE-FILE-016 | API | 更新不存在页面的 `quad_points` 返回 404，不影响其他页面 | 错误更新或污染页面 |
