# BDD 状态枚举

## 任务状态

| 状态值 | 含义 | 合法下一状态 |
|--------|------|--------------|
| `created` | 已创建 | `uploading`, `failed` |
| `uploading` | 上传中 | `uploaded`, `failed` |
| `uploaded` | 上传完成 | `processing`, `failed` |
| `processing` | 处理中 | `ready_for_review`, `failed` |
| `ready_for_review` | 待审核 | `confirmed`, `processing`, `failed` |
| `confirmed` | 已确认 | `exported` |
| `exported` | 已导出 | 无业务前进状态 |
| `failed` | 失败 | `processing` |

非法状态转换必须被拒绝并返回 `INVALID_TASK_TRANSITION`。

## 采集会话状态

| 状态值 | 含义 |
|--------|------|
| `active` | 可编辑（新增/删除/排序/补拍） |
| `expired` | 已过期，不可继续上传 |
| `locked` | 已完成采集，页序固化，不可编辑 |
| `cancelled` | 已取消 |

## 字段状态

| 状态值 | 含义 | 导出前处理 |
|--------|------|------------|
| `unreviewed` | 未审核 | 阻断确认 |
| `confirmed` | 已确认 | 允许确认/导出 |
| `modified` | 已修改 | 允许确认/导出 |
| `suspicious` | 存疑 | 阻断确认，需提示用户 |
| `empty` | 为空 | 阻断确认，可人工确认可接受 |
