# BDD 状态枚举

## 任务状态

| 状态值 | 含义 | 合法下一状态 |
|--------|------|--------------|
| `capturing` | 采集中（会话活跃，页面可编辑） | `uploaded`, `failed` |
| `uploaded` | 上传完成（会话已锁定，页序固化） | `processing`, `capturing`, `failed` |
| `processing` | 处理中（OCR/LLM 进行中） | `ready_for_review`, `failed` |
| `ready_for_review` | 待审核 | `confirmed`, `processing`, `capturing`, `failed` |
| `confirmed` | 已确认 | `exported`, `capturing` |
| `exported` | 已导出 | `capturing` |
| `failed` | 失败 | `processing`, `capturing` |

非法状态转换必须被拒绝并返回 `INVALID_TASK_TRANSITION`。

### 状态说明

- `capturing`：点击"新建采集"时创建任务并进入此状态，表示正在手机端采集页面。若用户取消采集会话，任务进入 `failed`；若会话过期且无已上传页面，任务进入 `failed`。
- `uploaded`：用户点击"完成采集"后进入此状态，页序和框选元数据已固化。可触发算法处理进入 `processing`，或通过电脑端"修订采集"流程回到 `capturing` 继续编辑。
- `processing`：后端正在调用外部算法模块（图像处理 → 文档解析 → 字段抽取）。处理成功进入 `ready_for_review`，任何环节失败进入 `failed`。
- `ready_for_review`：算法处理完成，等待人工审核。可点击"重新处理"回到 `processing`（适用于处理配置更新或怀疑处理异常时重新生成结果），也可通过"修订采集"回到 `capturing`（适用于发现图片质量问题、漏拍或页序错误需重拍）。
- `confirmed`：人工审核已确认，可导出；若发现图片或页序问题，也可通过"修订采集"回到 `capturing`。
- `exported`：已导出最终结果；若个人使用时发现采集错误，可通过"修订采集"回到 `capturing` 后重新处理和导出。
- `failed`：处理失败或会话异常终止。可点击"重新处理"回到 `processing`，或通过"修订采集"回到 `capturing`。

### 修订采集与任务状态

当用户在电脑端点击"修订采集"并确认后，已锁定会话可回到 `active`，关联任务从 `uploaded`、`ready_for_review`、`confirmed`、`exported` 或 `failed` 回到 `capturing`，允许重新编辑页面（新增、删除、补拍、重新框选、拖拽调整顺序）。重新完成采集后，任务再次进入 `uploaded → processing → ready_for_review`。修订采集不改变会话 ID 和任务 ID；`processing` 状态不允许修订，避免处理过程中同时修改输入。

## 采集会话状态

| 状态值 | 含义 |
|--------|------|
| `active` | 可编辑（新增/删除/排序/补拍/重新框选） |
| `expired` | 已过期，不可继续上传 |
| `locked` | 已完成采集，页序固化，不可编辑 |
| `cancelled` | 已取消（用户主动取消未完成的采集） |

### 会话状态转换

- `active` → `locked`：用户点击"完成采集"。
- `active` → `cancelled`：用户主动取消采集会话，已上传页面和任务进入清理流程。
- `active` → `expired`：超过过期时间（默认 30 分钟）仍未完成采集。
- `locked` → `active`：用户通过电脑端"修订采集"解锁会话以重新编辑页面，关联任务回到 `capturing`。
- `cancelled` 为终态，不可再转换。
- `expired` 为终态，不可再转换。

### 会话过期时间

- 默认过期时间为创建后 **30 分钟**。
- 电脑端工作台可在"新建采集"或会话设置中修改过期时间。
- 过期后，若会话已有已上传页面且未取消，关联任务保留为 `capturing` 状态；若会话无任何已上传页面，关联任务进入 `failed`。

## 字段状态

| 状态值 | 含义 | 导出前处理 |
|--------|------|------------|
| `unreviewed` | 未审核 | 预警提示，允许用户在了解风险后继续导出 |
| `confirmed` | 已确认 | 允许导出 |
| `modified` | 已修改 | 允许导出 |
| `suspicious` | 存疑 | 预警提示，允许用户在了解风险后继续导出 |
| `empty` | 为空 | 预警提示；用户可显式确认"空值可接受"后转为已确认等效状态 |
| `confirmed_empty` | 空值已确认 | 允许导出 |

### 字段空值处理

- 字段值为空时，状态为 `empty`。
- 用户可点击字段旁的"确认空值"操作，将状态转为 `confirmed_empty`（空值已确认可接受）。
- `confirmed_empty` 等同于 `confirmed`，不再阻断确认和导出。
- 导出前完整性检查面板中，`confirmed_empty` 字段单独列出，不记入未处理项。
- 常见合理空值场景：未婚患者的"婚育史"、无过敏史患者的"过敏史"等。
