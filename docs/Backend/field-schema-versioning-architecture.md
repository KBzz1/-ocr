# 字段 Schema 版本架构

## 目标

字段 schema 决定审核页字段、算法抽取模板、导出列顺序和历史任务可追溯性。任何字段新增、删除、拆分、合并、`T/J` 类型调整或 `field_key` 调整，都必须通过显式版本变迁处理，不能直接覆盖活动文件导致历史任务被新字段污染。

## 核心规则

1. **schema 文件不可变**
   - 已被任务使用过的 schema 文件不得原地改字段语义。
   - 字段结构变化必须新增文件，例如 `qwen_batch_admission_record.v2.yaml`。
   - 旧文件保留为历史兼容入口，不作为新任务默认 schema。

2. **任务绑定 schema 版本**
   - 创建/处理任务时，`task.schema_version`、`task.document_type`、`prompt_version` 来自当时的 `DocumentProfile`。
   - 新任务只读取当前 profile 指向的 schema。
   - 历史任务不因默认 schema 切换而改变字段集合。

3. **运行结果保存 schema 快照**
   - `results/{task_id}/field_candidates.json` 保存 `schema_version`、`document_type`、`field_groups`。
   - `results/{task_id}/review_result.json` 保存同一份 `field_groups` 快照。
   - 前端优先渲染 `review_result.field_groups`；没有快照时才退化为字段原始顺序。

4. **读取历史结果不得自动迁移**
   - `ReviewService.get_or_init()` 只在 `review_result.schema_version == 当前 schema.version` 时按当前 schema 补齐/重排字段。
   - 版本不同时，按已保存的 `review_result.fields` 和 `field_groups` 原样展示，不写盘改字段。

5. **迁移必须显式**
   - 需要把旧任务迁到新字段时，必须提供迁移脚本/命令，输出迁移审计记录。
   - 迁移脚本必须声明：源版本、目标版本、字段映射表、丢弃字段、合并字段、拆分字段、无法自动迁移字段。
   - 不能在普通 GET 审核页、导出、重抽取读取路径里偷偷迁移。

## 当前活动版本

- `qwen_batch_admission_record.v2`
  - 文件：`app/config/schemas/qwen_batch_admission_record.v2.yaml`
  - 来源：按师弟 `aufgh/qwen` 的中文嵌套 schema 模板恢复，并保留本项目稳定 `field_key`。
  - 字段数：51。
  - 关键语义：`精神睡眠食欲`、`小便情况`、既往史若干项、体格检查若干项和辅助检查若干项使用 `J` 判断型；`生命体征`、`身高体重BMI`、`血气`、`CRP` 保持合并字段。

## 历史版本

- `qwen_batch_admission_record.v1`
  - 文件：`app/config/schemas/qwen_batch_admission_record.v1.yaml`
  - 保留用于识别历史任务，不再作为默认 Qwen 批处理字段版本。
- `admission_record_structured_fields.v1`
  - 文件：`app/config/schemas/admission_record_structured_fields.v1.yaml`
  - legacy COPD 固定 61 字段路径，仅 legacy profile 使用。

## 字段变更流程

1. 新增 schema 文件并更新 `version`。
2. 更新 `app/config/default.yaml` / 部署配置指向新文件。
3. 更新算法端口测试，验证字段数、关键 `qwen_path`、`qwen_type` 和证据定位。
4. 更新 review/export 测试，验证 `field_groups` 快照与历史版本隔离。
5. 如需迁移历史任务，新增独立迁移脚本和审计测试。
6. 在本文件记录新版本、来源、字段数和关键语义变化。
