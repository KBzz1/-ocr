# BE-06 Schema 管理 — Schema Loader 与校验设计

## 范围

实现通用病历 schema 文件的加载与结构校验，提供 `GET /api/schemas/current` API。对应 PRD PR-BE-007，覆盖 TDD BE-SCH-001/002/003/005/007。

本阶段覆盖：
- BE-SCH-001：schema 文件必须包含 `version`、`document_type`、field_groups 和字段 key
- BE-SCH-002：重复 `field_key` 被拒绝
- BE-SCH-003：字段组顺序稳定，API 输出顺序与配置文件一致
- BE-SCH-005：`GET /api/schemas/current` 返回当前 schema，前端可动态展示字段
- BE-SCH-007：支持 `document_type` 标识；第一版默认通用病历 schema

本阶段不覆盖：
- BE-SCH-004：版本隔离（Task 创建时记录 schema_version 由 TaskService 负责）
- BE-SCH-006：禁止兜底抽取（属 BE-05 算法端口契约）

## 技术选型

| 项 | 选择 |
|----|------|
| Schema 文件格式 | YAML |
| API 输出格式 | JSON |
| 加载器 | 纯函数 `load_schema(path) -> dict` |
| 校验 | 加载时内联完整校验 |
| 缓存 | 首次加载后内存缓存 |

## 数据模型

### Schema YAML（`app/config/schemas/medical_record.v1.yaml`）

```yaml
version: "1.0.0"
document_type: general_medical_record
field_groups:
  - group_key: patient_info
    group_label: 患者基本信息
    fields:
      - key: name
        label: 姓名
        type: string
        required: false
        hint: ""
      - key: gender
        label: 性别
        type: string
        required: false
        hint: ""
      - key: age
        label: 年龄
        type: string
        required: false
        hint: ""
      - key: patient_id
        label: ID号
        type: string
        required: false
        hint: ""
      - key: inpatient_no
        label: 住院号
        type: string
        required: false
        hint: ""
      - key: ward
        label: 病区
        type: string
        required: false
        hint: ""
      - key: bed_no
        label: 床号
        type: string
        required: false
        hint: ""
      - key: department
        label: 科室
        type: string
        required: false
        hint: ""

  - group_key: admission_info
    group_label: 入院/病程信息
    fields:
      - key: admission_time
        label: 入院时间
        type: date
        required: false
        hint: ""
      - key: record_time
        label: 记录时间
        type: date
        required: false
        hint: ""
      - key: chief_complaint
        label: 主诉
        type: string
        required: false
        hint: ""
      - key: present_illness
        label: 现病史
        type: string
        required: false
        hint: ""
      - key: past_history
        label: 既往史
        type: string
        required: false
        hint: ""
      - key: personal_history
        label: 个人史
        type: string
        required: false
        hint: ""
      - key: marital_history
        label: 婚育史
        type: string
        required: false
        hint: ""
      - key: family_history
        label: 家族史
        type: string
        required: false
        hint: ""

  - group_key: physical_exam
    group_label: 体格检查
    fields:
      - key: temperature
        label: 体温
        type: string
        required: false
        hint: ""
      - key: pulse
        label: 脉搏
        type: string
        required: false
        hint: ""
      - key: respiration
        label: 呼吸
        type: string
        required: false
        hint: ""
      - key: blood_pressure
        label: 血压
        type: string
        required: false
        hint: ""
      - key: height
        label: 身高
        type: string
        required: false
        hint: ""
      - key: weight
        label: 体重
        type: string
        required: false
        hint: ""
      - key: bmi
        label: BMI
        type: string
        required: false
        hint: ""
      - key: general_condition
        label: 一般情况
        type: string
        required: false
        hint: ""
      - key: specialty_signs
        label: 专科体征
        type: string
        required: false
        hint: ""

  - group_key: auxiliary_exam
    group_label: 辅助检查
    fields:
      - key: exam_date
        label: 检查日期
        type: date
        required: false
        hint: ""
      - key: exam_type
        label: 检查类型
        type: string
        required: false
        hint: ""
      - key: exam_findings
        label: 检查所见
        type: string
        required: false
        hint: ""
      - key: exam_conclusion
        label: 检查结论
        type: string
        required: false
        hint: ""
      - key: key_lab_indicators
        label: 关键检验指标
        type: string
        required: false
        hint: ""

  - group_key: diagnosis
    group_label: 诊断相关
    fields:
      - key: primary_diagnosis
        label: 初步诊断
        type: string
        required: false
        hint: ""
      - key: final_diagnosis
        label: 最后诊断
        type: string
        required: false
        hint: ""
      - key: revised_diagnosis
        label: 修正诊断
        type: string
        required: false
        hint: ""
      - key: diagnosis_list
        label: 诊断列表
        type: string
        required: false
        hint: ""

  - group_key: treatment
    group_label: 治疗相关
    fields:
      - key: main_treatment
        label: 主要治疗
        type: string
        required: false
        hint: ""
      - key: medication_info
        label: 用药信息
        type: string
        required: false
        hint: ""
      - key: treatment_opinion
        label: 处理意见
        type: string
        required: false
        hint: ""
      - key: treatment_plan
        label: 诊疗计划
        type: string
        required: false
        hint: ""

  - group_key: signature
    group_label: 签名与时间
    fields:
      - key: recording_doctor
        label: 记录医生
        type: string
        required: false
        hint: ""
      - key: superior_doctor
        label: 上级医生
        type: string
        required: false
        hint: ""
      - key: signature_time
        label: 签名时间
        type: date
        required: false
        hint: ""
      - key: discharge_date
        label: 出院/入院日期
        type: date
        required: false
        hint: ""
```

### 校验规则

| 级别 | 规则 | 拒绝条件 |
|------|------|----------|
| 文件 | 文件存在且为合法 YAML | 文件缺失或 YAML 解析异常 |
| 顶层 | `version` 为非空字符串 | 缺失或空 |
| 顶层 | `document_type` 为非空字符串 | 缺失或空 |
| 顶层 | `field_groups` 为非空列表 | 缺失或空列表 |
| 字段组 | `group_key` 和 `group_label` 非空 | 任一缺失或空 |
| 字段组 | `group_key` 不重复 | 发现重复 |
| 字段 | `key` 和 `label` 非空 | 任一缺失或空 |
| 字段 | 全局 `key` 唯一 | 发现重复 key |
| 字段 | `type` 在允许集合内 | 不在 `{string, number, date, boolean}` 中 |
| 字段 | `required` 可选，默认 false | — |
| 字段 | `hint` 可选，默认空字符串 | — |

### API 响应

**GET /api/schemas/current**

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

## 模块接口契约

### services/schema_loader.py

```python
ALLOWED_FIELD_TYPES = {"string", "number", "date", "boolean"}

def load_schema(path: str) -> dict:
    """加载并校验 YAML schema 文件。成功返回完整 dict；失败抛 AppError。

    校验顺序：
    1. 文件存在 + YAML 解析
    2. version / document_type 非空
    3. field_groups 非空列表
    4. group_key / group_label 非空，group_key 不重复
    5. 所有 field key 全局唯一
    6. 每个 field key / label 非空，type 合法
    """
```

无类，无 Flask 依赖。只依赖 `yaml`、`AppError`、`ErrorCode`。

### services/schema_service.py

```python
class SchemaService:
    """持有当前 schema 路径，提供 get_current()。

    首次调用时加载并缓存，后续请求直接返回缓存。
    """

    def __init__(self, schema_path: str):
        ...

    def get_current(self) -> dict:
        ...
```

### routes/schema.py

```python
schema_bp = Blueprint("schema", __name__)

@schema_bp.route("/api/schemas/current")
def get_current_schema():
    service = current_app.config["SCHEMA_SERVICE"]
    return success(data=service.get_current())
```

### errors.py 新增

```python
SCHEMA_LOAD_FAILED = ("SCHEMA_LOAD_FAILED", 500, "Schema 加载失败")
```

details 中携带具体原因：
```python
AppError(ErrorCode.SCHEMA_LOAD_FAILED, 
         message="Schema 加载失败：缺少 version 字段",
         details={"reason": "缺少 version 字段"})
```

### __init__.py 变更

在 `create_backend_app` 中：

```python
# 初始化 SchemaService（路径由工厂决定，测试可传入临时文件）
import os
from .services.schema_service import SchemaService

schema_path = os.path.join(PROJECT_ROOT, "app", "config", "schemas",
                           "medical_record.v1.yaml")
app.config["SCHEMA_SERVICE"] = SchemaService(schema_path)

# 注册 schema_bp
from .routes.schema import schema_bp
app.register_blueprint(schema_bp)
```

## 目录结构

```
app/config/schemas/
└── medical_record.v1.yaml       # NEW

app/backend/
├── services/
│   ├── schema_loader.py         # NEW
│   └── schema_service.py        # NEW
├── routes/
│   └── schema.py                # NEW
├── errors.py                    # MODIFY +SCHEMA_LOAD_FAILED
├── __init__.py                  # MODIFY +SchemaService +schema_bp
└── tests/
    ├── test_schema_loader.py    # NEW 单元测试
    └── test_schema_api.py       # NEW API 集成测试
```

## 测试策略

遵循 TDD：先写失败测试 → RED → 实现 → GREEN → 重构。

### test_schema_loader.py（单元测试）

不依赖 Flask，直接调用 `load_schema()`。

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_load_valid_schema_returns_dict` | SCH-001 | 函数不存在 |
| `test_load_missing_file_raises` | SCH-001 | 文件不存在未抛异常 |
| `test_reject_missing_version` | SCH-001 | 缺 version 仍通过 |
| `test_reject_missing_document_type` | SCH-001 | 缺 document_type 仍通过 |
| `test_reject_empty_field_groups` | SCH-001 | 空列表仍通过 |
| `test_reject_duplicate_field_key` | SCH-002 | 重复 key 被接受 |
| `test_reject_missing_field_label` | SCH-001 | 缺 label 仍通过 |
| `test_reject_invalid_field_type` | SCH-001 | 非法 type 仍通过 |
| `test_field_groups_order_preserved` | SCH-003 | 顺序改变 |
| `test_reject_duplicate_group_key` | SCH-001 | 重复 group_key 被接受 |
| `test_default_required_and_hint` | SCH-001 | 默认值未设置 |

### test_schema_api.py（API 集成测试）

使用 Flask test client。

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_get_current_schema_returns_200` | SCH-005 | 路由缺失 |
| `test_get_current_schema_has_version` | SCH-005 | 响应结构缺 version |
| `test_get_current_schema_has_field_groups` | SCH-005 | 响应结构缺 field_groups |
| `test_schema_load_failure_returns_500` | SCH-001 | 坏 schema 仍返回 200 |

## 不在此阶段实现

- BE-SCH-004：版本隔离（TaskService 写入 task.schema_version）
- BE-SCH-006：禁止兜底抽取（BE-05 算法端口契约）
- 多文书类型 schema 选择和加载
- `POST /api/schemas/reload` 热重载
- 前端 schema 展示页面
