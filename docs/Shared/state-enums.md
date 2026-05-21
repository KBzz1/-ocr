# MVP 状态枚举

本文定义当前 MVP 设计使用的共享状态。MVP 保留手机扫码拍照上传，但不再设计独立采集会话，不做会话过期、锁定/解锁、修订采集、四边形框选或拖拽排序。

## 任务状态

| 状态值 | 含义 | 合法下一状态 |
|--------|------|--------------|
| `uploading` | 上传中。任务已创建，手机端可继续拍照或选择图片上传，多图页序按上传成功顺序确定 | `processing`, `failed` |
| `processing` | 处理中。后端正在调用本地 OCR/结构化抽取模块 | `review`, `failed` |
| `review` | 待审核。OCR 文本和结构化字段已生成，等待电脑端人工核对 | `processing`, `done`, `failed` |
| `done` | 已完成。人工审核结果已保存，可导出或查看结果 | `processing` |
| `failed` | 失败。上传、处理或导出前置步骤失败，保留错误原因 | `processing` |

非法状态转换必须被拒绝并返回 `INVALID_TASK_TRANSITION`。

### 状态说明

- `uploading`：电脑端点击"新建任务"后创建任务并生成手机上传二维码。手机端只负责拍照/选择图片、多图上传和完成上传；不做审核、字段展示或复杂页面管理。
- `processing`：用户点击"完成上传"后进入此状态，后端调用本地 OCR 和结构化抽取模块。任何算法模块未配置、调用失败、返回空结构化字段或契约非法，任务进入 `failed`。
- `review`：处理成功后进入此状态。电脑端展示原图、OCR 文本和结构化字段，用户可编辑、保存、确认并导出。
- `done`：用户完成审核后进入此状态。导出不引入新的任务状态；导出成功只记录导出文件信息。
- `failed`：失败任务保留错误码和错误说明。用户可基于现有图片重新处理；如果图片本身有问题，MVP 建议新建任务重新上传，或在后续版本再增加轻量补传能力。

### MVP 不保留的状态

旧设计中的 `capturing`、`uploaded`、`ready_for_review`、`confirmed`、`exported` 不再作为当前 MVP 目标状态使用。

## 字段抽取元数据

`extraction_status`: `extracted`、`not_found`、`uncertain`
`verification_status`: `passed`、`suspicious`、`failed`、`not_checked`
`quality_flags`: 规则化质量核验风险标记列表
`ocr_correction`: OCR 纠偏审计信息

这些不是人工审核状态；人工审核状态仍使用 `unreviewed`、`confirmed`、`modified`。

## 字段状态

MVP 字段状态先保持简单，避免审核流程过重。

| 状态值 | 含义 | 导出前处理 |
|--------|------|------------|
| `unreviewed` | 未审核，来自自动抽取结果或尚未人工确认 | 允许导出，但界面提示仍有未确认字段 |
| `confirmed` | 已确认，人工已核对或保存为最终值 | 允许导出 |
| `modified` | 已修改，人工改过字段值 | 允许导出 |

### 后续可选扩展

`suspicious`、`empty`、`confirmed_empty` 等细分状态不属于当前 MVP 必做范围。若后续需要更严格的质控或导出预警，再重新扩展字段状态与审核界面。
