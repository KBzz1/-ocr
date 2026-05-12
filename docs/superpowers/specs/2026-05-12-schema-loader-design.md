# BE-06 Schema 管理 - Schema Loader 与校验设计

## 范围

本设计对应 PRD `PR-BE-007` 和任务清单 `BE-06`，定义第一版通用病历 schema 的文件位置、加载校验、当前 schema API、字段 key 白名单能力，以及与 BE-05 字段抽取和 BE-07 人工审核的边界。

覆盖：

- `BE-SCH-001`：schema 文件必须包含 `version`、`document_type`、字段组和字段 key。
- `BE-SCH-002`：重复 `field_key` 被拒绝。
- `BE-SCH-003`：字段组和字段顺序稳定，API、审核展示和导出使用同一顺序。
- `BE-SCH-004`：新任务记录当前 `schema_version`，历史任务不因后续 schema 文件变化而改变已记录版本。
- `BE-SCH-005`：`GET /api/schema/current` 返回当前 schema，前端可动态展示字段组。
- `BE-SCH-006`：schema 只用于字段范围、候选字段契约校验、展示和导出顺序，不生成字段值。
- `BE-SCH-007`：schema 支持 `document_type` 标识；第一版默认 `general_medical_record`。

不覆盖：

- 多文书类型动态选择、前端 schema 管理页面、热重载 API。
- OCR、LLM 字段抽取、图像处理、规则抽取或任何兜底字段生成。
- BE-05 算法端口实现细节；BE-05 只接收 schema dict 并可调用 BE-06 提供的白名单校验能力。

## 权威输入

- PRD 字段组以 `docs/产品PRD.md` 的 `PR-BE-007` 为准。
- 字段状态以 `docs/Shared/state-enums.md` 为准，BE-06 不新增字段状态。
- 错误响应结构以 `docs/Shared/error-codes.md` 为准。
- 当前 API 路径以后端 BDD/TDD 中的 `GET /api/schema/current` 为准。

## Schema 文件

第一版固定 schema 文件位置：

```text
app/config/schemas/medical_record.v1.yaml
```

文件随应用本地部署，不在运行时联网下载。路径由后端应用工厂或配置注入，测试可使用临时 schema 文件。`app/config/README.md` 只记录配置目录说明；实际字段定义只放在 `app/config/schemas/*.yaml`。

### YAML 结构

```yaml
version: "1.0.0"
document_type: general_medical_record
field_groups:
  - group_key: patient_info
    group_label: 患者基本信息
    fields:
      - field_key: name
        label: 姓名
        type: string
        required: false
        hint: ""
```

字段对象使用 `field_key` 作为持久化、候选字段校验、审核保存和导出的唯一字段标识。API 可以兼容输出 `key` 别名给前端展示，但后端内部契约和算法候选统一使用 `field_key`。

### 第一版字段组

| group_key | group_label | 字段 |
|-----------|-------------|------|
| `patient_info` | 患者基本信息 | 姓名、性别、年龄、ID号、住院号、病区、床号、科室 |
| `admission_info` | 入院/病程信息 | 入院时间、记录时间、主诉、现病史、既往史、个人史、婚育史、家族史 |
| `physical_exam` | 体格检查 | 体温、脉搏、呼吸、血压、身高、体重、BMI、一般情况、专科体征 |
| `auxiliary_exam` | 辅助检查 | 检查日期、检查类型、检查所见、检查结论、关键检验指标 |
| `diagnosis` | 诊断相关 | 初步诊断、最后诊断、修正诊断、诊断列表 |
| `treatment` | 治疗相关 | 主要治疗、用药信息、处理意见、诊疗计划 |
| `signature` | 签名与时间 | 记录医生、上级医生、签名时间、出院/入院日期 |

字段 key 采用稳定英文 snake_case。第一版建议字段如下：

| 字段 | field_key |
|------|-----------|
| 姓名 | `name` |
| 性别 | `gender` |
| 年龄 | `age` |
| ID号 | `patient_id` |
| 住院号 | `inpatient_no` |
| 病区 | `ward` |
| 床号 | `bed_no` |
| 科室 | `department` |
| 入院时间 | `admission_time` |
| 记录时间 | `record_time` |
| 主诉 | `chief_complaint` |
| 现病史 | `present_illness` |
| 既往史 | `past_history` |
| 个人史 | `personal_history` |
| 婚育史 | `marital_history` |
| 家族史 | `family_history` |
| 体温 | `temperature` |
| 脉搏 | `pulse` |
| 呼吸 | `respiration` |
| 血压 | `blood_pressure` |
| 身高 | `height` |
| 体重 | `weight` |
| BMI | `bmi` |
| 一般情况 | `general_condition` |
| 专科体征 | `specialty_signs` |
| 检查日期 | `exam_date` |
| 检查类型 | `exam_type` |
| 检查所见 | `exam_findings` |
| 检查结论 | `exam_conclusion` |
| 关键检验指标 | `key_lab_indicators` |
| 初步诊断 | `primary_diagnosis` |
| 最后诊断 | `final_diagnosis` |
| 修正诊断 | `revised_diagnosis` |
| 诊断列表 | `diagnosis_list` |
| 主要治疗 | `main_treatment` |
| 用药信息 | `medication_info` |
| 处理意见 | `treatment_opinion` |
| 诊疗计划 | `treatment_plan` |
| 记录医生 | `recording_doctor` |
| 上级医生 | `superior_doctor` |
| 签名时间 | `signature_time` |
| 出院/入院日期 | `discharge_or_admission_date` |

## 加载与校验

### SchemaLoader

`SchemaLoader` 负责从 YAML 文件加载并规范化 schema。它不依赖 Flask，不调用算法模块，不读取任务数据。

加载成功返回规范化 dict：

- 保留 YAML 中 `field_groups` 和 `fields` 顺序。
- 为缺省的 `required` 填充 `false`。
- 为缺省的 `hint` 填充空字符串。
- 字段对象必须包含 `field_key`；如实现需要前端兼容，可在 API 层派生 `key`，不得替代内部 `field_key`。

拒绝条件：

| 级别 | 规则 |
|------|------|
| 文件 | 文件必须存在，且内容是合法 YAML mapping |
| 顶层 | `version`、`document_type` 必须是非空字符串 |
| 顶层 | `field_groups` 必须是非空列表 |
| 字段组 | `group_key`、`group_label` 必须是非空字符串 |
| 字段组 | `group_key` 在当前 schema 内唯一 |
| 字段 | `fields` 必须是非空列表 |
| 字段 | `field_key`、`label` 必须是非空字符串 |
| 字段 | `field_key` 在当前 schema 内全局唯一 |
| 字段 | `type` 必须在 `{string, number, date, boolean}` 内，缺省为 `string` |
| 字段 | `required` 缺省为 `false`，存在时必须为 boolean |
| 字段 | `hint` 缺省为空字符串，存在时必须为 string |

schema 校验失败是配置错误，不是算法错误。

### SchemaService

`SchemaService` 是 BE-06 对其他后端模块的入口，持有当前 schema 路径和内存缓存。

职责：

- `get_current()`：返回当前规范化 schema dict，供 API、BE-05 字段抽取输入、BE-07 展示、BE-08 导出顺序使用。
- `get_current_version()`：返回当前 `version`，供 Task 创建或处理开始时写入 `task.schema_version`。
- `get_allowed_field_keys()`：返回当前 schema 的字段 key 白名单集合。
- `get_field_order()`：返回按 schema 顺序展开的字段 key 列表，供审核展示和导出排序。
- `build_validator()` 或 `validator` 属性：提供绑定当前 schema 的 `SchemaValidator`。

缓存策略：

- 首次调用时加载 schema 并缓存。
- 进程生命周期内默认不自动检测文件变更。
- 维护者修改 schema 后需要重启应用，新任务才读取新 schema。
- 测试可显式构造新的 `SchemaService` 实例验证不同 schema 文件。
- 不提供 `POST /api/schemas/reload` 或后台热重载，避免历史任务在同一进程内出现不可追踪的 schema 漂移。

### SchemaValidator

`SchemaValidator` 只做 schema 相关契约校验，不生成、补齐、排序或改写字段值。

职责：

- 校验候选字段列表非空。
- 校验每个候选字段结构满足 BE-05 字段候选契约。
- 校验每个候选字段的 `field_key` 属于当前 schema 白名单。
- 校验重复候选 `field_key` 是否按契约拒绝；第一版拒绝重复，避免覆盖和合并歧义。
- 校验通过时返回原候选列表或不可变视图；不得根据 schema 补出缺失字段。

供 BE-05 使用：

- BE-05 字段抽取端口调用外部模块时只透传 `SchemaService.get_current()` 返回的 schema dict。
- BE-05 自身可做候选字段基础结构校验，但 schema 外字段白名单校验必须委托 `SchemaValidator`。
- 外部字段抽取返回空候选、schema 外字段、重复字段或候选结构非法时，处理流程进入 `failed`，错误码映射为 `ALGORITHM_CONTRACT_INVALID`。

供 BE-07 使用：

- BE-07 保存人工审核结果时使用同一字段 key 白名单，拒绝 schema 外字段。
- 人工审核字段状态必须来自共享字段状态：`unreviewed`、`confirmed`、`modified`、`suspicious`、`empty`。
- BE-07 可以保存医生录入或修正的最终值，但 BE-06 不提供默认值、空值字段生成或医学含义推断。

## API JSON 输出

### GET /api/schema/current

成功响应：

```json
{
  "success": true,
  "data": {
    "version": "1.0.0",
    "document_type": "general_medical_record",
    "field_groups": [
      {
        "group_key": "patient_info",
        "group_label": "患者基本信息",
        "fields": [
          {
            "field_key": "name",
            "key": "name",
            "label": "姓名",
            "type": "string",
            "required": false,
            "hint": ""
          }
        ]
      }
    ]
  }
}
```

说明：

- API 输出顺序必须与 YAML 文件一致。
- `field_key` 是后端权威字段标识。
- `key` 仅作为前端兼容别名，值必须等于 `field_key`；若前端统一改用 `field_key`，可不输出 `key`。
- API 不输出字段值、候选结果、字段状态或审核结果。
- API 不暴露本机 schema 文件路径。

## 版本记录边界

BE-06 提供当前 schema version 和 document_type，但不负责创建任务或迁移历史任务。

任务创建或处理开始时，TaskService 必须把当时使用的 `schema_version` 和 `document_type` 写入任务记录。实现上可以由应用装配把 `SchemaService.get_current()` 的返回值传给 BE-05 编排入口，TaskService 只记录传入 schema 中的 `version` 和 `document_type`，不自行解析 schema 文件。后续 schema 文件修改只影响重启后新任务，不改变已有任务记录中的版本字段。

第一版不要求保存完整历史 schema 快照。历史任务的字段结果和审核结果按任务记录中的 `schema_version` 标识追溯；如后续需要按旧 schema 重新渲染历史字段组，应另立设计补充 schema 归档策略。

## 错误映射

| 场景 | 错误码 | HTTP / 任务状态 |
|------|--------|-----------------|
| `GET /api/schema/current` 时 schema 文件缺失、YAML 非法或 schema 结构非法 | `INTERNAL_SERVER_ERROR` | HTTP 500 |
| 创建任务或处理任务时无法加载当前 schema | `INTERNAL_SERVER_ERROR` | 若任务尚未进入处理流程则返回 HTTP 500；若任务已进入 `processing`，任务进入 `failed` 并记录短配置错误原因 |
| 外部字段抽取返回空候选 | `ALGORITHM_CONTRACT_INVALID` | 任务进入 `failed` |
| 外部字段抽取返回 schema 外字段 | `ALGORITHM_CONTRACT_INVALID` | 任务进入 `failed` |
| 外部字段抽取返回重复字段或候选字段结构非法 | `ALGORITHM_CONTRACT_INVALID` | 任务进入 `failed` |
| BE-07 审核保存包含 schema 外字段或非法字段状态 | `REVIEW_VALIDATION_FAILED` | HTTP 400 |
| BE-08 导出前发现字段状态不允许导出或字段结构非法 | `EXPORT_VALIDATION_FAILED` | HTTP 400 |

当前共享错误码未定义 `SCHEMA_LOAD_FAILED`，本 spec 不新增错误码。schema 配置错误通过 `INTERNAL_SERVER_ERROR` 返回；如果任务已进入处理状态，任务记录中的 `error_code` 也使用 `INTERNAL_SERVER_ERROR`。`details.reason` 可包含短错误原因，但不得包含完整病历原文、模型输出全文、图片 base64、堆栈或本机私有路径。

## 禁止行为

- 不得根据 schema 的 `field_key` 生成空候选字段。
- 不得在算法失败、返回空结果或契约非法时进入人工降级补录流程。
- 不得基于 OCR 文本、schema label、hint 或字段组规则抽取字段值。
- 不得由前端基于 schema、OCR 文本或页面内容推断、补造可审核字段。
- 不得把 schema hint 当作抽取规则在后端执行。
- 不得在日志中记录完整病历原文、身份证号、图片 base64 或模型输出全文。

## 验收要点

- 修改 `medical_record.v1.yaml` 并重启后，`GET /api/schema/current` 的字段范围和顺序随之变化。
- schema 缺少必要字段、重复 `field_key`、非法字段类型或字段组为空时拒绝加载。
- BE-05 调用字段抽取时传入当前 schema dict，但 schema 外字段校验由 BE-06 的 `SchemaValidator` 提供。
- 外部字段抽取返回空候选或 schema 外字段时任务进入 `failed`，不得生成替代字段。
- BE-07 保存审核结果时拒绝 schema 外字段，字段状态只接受共享枚举。
- TaskService 记录任务使用的 `schema_version` 和 `document_type`，历史任务记录不因 schema 文件后续修改而变化。
