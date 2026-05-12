# BE-06 Schema Loader 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 BE-06 Schema Loader — YAML schema 文件、加载校验器、缓存 service、白名单 validator、GET /api/schema/current API

**Architecture:** `load_schema()` 纯函数解析校验 YAML，`SchemaService` 缓存 wrapper 供其他模块使用，`SchemaValidator` 只做白名单校验不生成字段值。API 输出 `field_key` + `key` 别名兼容前端。

**Tech Stack:** Python 3.12 via conda env `manzufei_ocr`, Flask, pytest, PyYAML

---

## 并行执行与合并边界

BE-06 可以与 BE-05 外部算法端口并行执行，但必须按以下边界保持无缝合并：

- BE-06 拥有 schema 文件、schema loader、`SchemaService`、`SchemaValidator` 和 `GET /api/schema/current`。
- BE-06 不修改 BE-05 的 `app/backend/services/algorithm_ports/` 包，不实现图像处理、OCR、文档解析、LLM 字段抽取、规则抽取或字段值生成。
- BE-05 只接收调用方显式传入的 schema dict；不得读取 `app/config/schemas/medical_record.v1.yaml`，不得构造默认 schema，schema 外字段校验必须委托 BE-06 的 `SchemaValidator`。
- 两个分支都会修改 `app/backend/__init__.py`。合并时保留两块装配：`SCHEMA_SERVICE` 初始化和 schema route 注册来自 BE-06；`ProcessingOrchestrator`/`TASK_SERVICE` 装配来自 BE-05。不要用一方整文件覆盖另一方。
- 推荐合并顺序：先合并 BE-06，再合并 BE-05。BE-05 合并时把 `SchemaService.get_current()` 的返回值传给处理入口，把 `SchemaService.build_validator()` 注入 orchestrator。
- 如果必须先合并 BE-05，BE-05 必须继续使用测试显式传入的 schema dict；合并 BE-06 后再做装配层小补丁接入 `SchemaService`，不能在 BE-05 内临时复制 schema loader。
- 并行执行期间只允许使用 conda 环境 `manzufei_ocr` 运行验证命令。

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `app/config/schemas/medical_record.v1.yaml` | CREATE | 第一版通用病历 schema 定义 |
| `app/backend/services/schema_loader.py` | CREATE | 纯函数 YAML 加载 + 结构校验 |
| `app/backend/services/schema_service.py` | CREATE | 缓存 wrapper，对外入口 |
| `app/backend/services/schema_validator.py` | CREATE | 白名单契约校验 |
| `app/backend/routes/schema.py` | CREATE | GET /api/schema/current |
| `app/backend/__init__.py` | MODIFY | 注入 SchemaService + 注册 schema_bp |
| `app/backend/tests/test_schema_loader.py` | CREATE | 单元测试 |
| `app/backend/tests/test_schema_service.py` | CREATE | 单元测试 |
| `app/backend/tests/test_schema_validator.py` | CREATE | 单元测试 |
| `app/backend/tests/test_schema_api.py` | CREATE | API 集成测试 |

---

### Task 1: Schema YAML 文件

**Files:**
- Create: `app/config/schemas/medical_record.v1.yaml`

- [ ] **Step 1: 创建 schema 目录和文件**

```bash
mkdir -p app/config/schemas
```

创建 `app/config/schemas/medical_record.v1.yaml`：

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
      - field_key: gender
        label: 性别
        type: string
      - field_key: age
        label: 年龄
        type: string
      - field_key: patient_id
        label: ID号
        type: string
      - field_key: inpatient_no
        label: 住院号
        type: string
      - field_key: ward
        label: 病区
        type: string
      - field_key: bed_no
        label: 床号
        type: string
      - field_key: department
        label: 科室
        type: string

  - group_key: admission_info
    group_label: 入院/病程信息
    fields:
      - field_key: admission_time
        label: 入院时间
        type: date
      - field_key: record_time
        label: 记录时间
        type: date
      - field_key: chief_complaint
        label: 主诉
        type: string
      - field_key: present_illness
        label: 现病史
        type: string
      - field_key: past_history
        label: 既往史
        type: string
      - field_key: personal_history
        label: 个人史
        type: string
      - field_key: marital_history
        label: 婚育史
        type: string
      - field_key: family_history
        label: 家族史
        type: string

  - group_key: physical_exam
    group_label: 体格检查
    fields:
      - field_key: temperature
        label: 体温
        type: string
      - field_key: pulse
        label: 脉搏
        type: string
      - field_key: respiration
        label: 呼吸
        type: string
      - field_key: blood_pressure
        label: 血压
        type: string
      - field_key: height
        label: 身高
        type: string
      - field_key: weight
        label: 体重
        type: string
      - field_key: bmi
        label: BMI
        type: string
      - field_key: general_condition
        label: 一般情况
        type: string
      - field_key: specialty_signs
        label: 专科体征
        type: string

  - group_key: auxiliary_exam
    group_label: 辅助检查
    fields:
      - field_key: exam_date
        label: 检查日期
        type: date
      - field_key: exam_type
        label: 检查类型
        type: string
      - field_key: exam_findings
        label: 检查所见
        type: string
      - field_key: exam_conclusion
        label: 检查结论
        type: string
      - field_key: key_lab_indicators
        label: 关键检验指标
        type: string

  - group_key: diagnosis
    group_label: 诊断相关
    fields:
      - field_key: primary_diagnosis
        label: 初步诊断
        type: string
      - field_key: final_diagnosis
        label: 最后诊断
        type: string
      - field_key: revised_diagnosis
        label: 修正诊断
        type: string
      - field_key: diagnosis_list
        label: 诊断列表
        type: string

  - group_key: treatment
    group_label: 治疗相关
    fields:
      - field_key: main_treatment
        label: 主要治疗
        type: string
      - field_key: medication_info
        label: 用药信息
        type: string
      - field_key: treatment_opinion
        label: 处理意见
        type: string
      - field_key: treatment_plan
        label: 诊疗计划
        type: string

  - group_key: signature
    group_label: 签名与时间
    fields:
      - field_key: recording_doctor
        label: 记录医生
        type: string
      - field_key: superior_doctor
        label: 上级医生
        type: string
      - field_key: signature_time
        label: 签名时间
        type: date
      - field_key: discharge_or_admission_date
        label: 出院/入院日期
        type: date
```

- [ ] **Step 2: 运行已有全量测试确认无回归**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/ -q
```

- [ ] **Step 3: Commit**

```bash
git add app/config/schemas/medical_record.v1.yaml
git commit -m "feat: 新增通用病历 schema 定义文件"
```

---

### Task 2: SchemaLoader TDD

**Files:**
- Create: `app/backend/tests/test_schema_loader.py`
- Create: `app/backend/services/schema_loader.py`

- [ ] **Step 1: 写失败单元测试**

创建 `app/backend/tests/test_schema_loader.py`：

```python
import os
import tempfile
import pytest
import yaml
from app.backend.errors import AppError, ErrorCode


def _write_yaml(tmpdir, filename, data):
    path = os.path.join(tmpdir, filename)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)
    return path


def _valid_schema():
    return {
        "version": "1.0.0",
        "document_type": "general_medical_record",
        "field_groups": [
            {
                "group_key": "basic",
                "group_label": "基本信息",
                "fields": [
                    {"field_key": "name", "label": "姓名", "type": "string"},
                    {"field_key": "age", "label": "年龄", "type": "number"},
                ],
            }
        ],
    }


class TestSchemaLoaderValid:
    def test_load_valid_schema_returns_dict(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        path = _write_yaml(tmpdir, "schema.yaml", _valid_schema())
        result = load_schema(path)
        assert isinstance(result, dict)
        assert result["version"] == "1.0.0"
        assert result["document_type"] == "general_medical_record"
        assert len(result["field_groups"]) == 1

    def test_load_normalized_defaults_for_required_and_hint(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        # 不提供 required 和 hint，验证默认值
        path = _write_yaml(tmpdir, "schema.yaml", schema)
        result = load_schema(path)
        field = result["field_groups"][0]["fields"][0]
        assert field["required"] is False
        assert field["hint"] == ""

    def test_type_defaults_to_string_when_missing(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        del schema["field_groups"][0]["fields"][0]["type"]
        path = _write_yaml(tmpdir, "schema.yaml", schema)
        result = load_schema(path)
        assert result["field_groups"][0]["fields"][0]["type"] == "string"

    def test_field_groups_order_preserved(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = {
            "version": "1.0.0",
            "document_type": "test",
            "field_groups": [
                {"group_key": "c", "group_label": "第三", "fields": [
                    {"field_key": "f3", "label": "f3"}]},
                {"group_key": "a", "group_label": "第一", "fields": [
                    {"field_key": "f1", "label": "f1"}]},
                {"group_key": "b", "group_label": "第二", "fields": [
                    {"field_key": "f2", "label": "f2"}]},
            ],
        }
        path = _write_yaml(tmpdir, "schema.yaml", schema)
        result = load_schema(path)
        group_keys = [g["group_key"] for g in result["field_groups"]]
        assert group_keys == ["c", "a", "b"]


class TestSchemaLoaderReject:
    def test_load_missing_file_raises(self):
        from app.backend.services.schema_loader import load_schema

        with pytest.raises(AppError) as exc_info:
            load_schema("/nonexistent/schema.yaml")
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_missing_version(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        del schema["version"]
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_missing_document_type(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        del schema["document_type"]
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_empty_field_groups(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        schema["field_groups"] = []
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_duplicate_field_key(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        schema["field_groups"][0]["fields"].append(
            {"field_key": "name", "label": "重复字段"}
        )
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_missing_field_label(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        del schema["field_groups"][0]["fields"][0]["label"]
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_invalid_field_type(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        schema["field_groups"][0]["fields"][0]["type"] = "datetime"
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_duplicate_group_key(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        schema["field_groups"].append({
            "group_key": "basic",
            "group_label": "重复组",
            "fields": [{"field_key": "x", "label": "x"}],
        })
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code
```

- [ ] **Step 2: 运行测试确认 RED**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_loader.py -v
```

预期: FAIL — `ModuleNotFoundError: No module named 'app.backend.services.schema_loader'`

- [ ] **Step 3: 实现 schema_loader.py**

创建 `app/backend/services/schema_loader.py`：

```python
import os
import yaml
from ..errors import AppError, ErrorCode

ALLOWED_FIELD_TYPES = {"string", "number", "date", "boolean"}


def load_schema(path: str) -> dict:
    """加载并校验 YAML schema 文件。成功返回规范化 dict；失败抛 AppError。"""

    if not os.path.isfile(path):
        raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                       message="Schema 文件不存在",
                       details={"reason": "文件不存在"})

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError:
        raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                       message="Schema YAML 语法错误",
                       details={"reason": "YAML 语法错误"})

    if not isinstance(raw, dict):
        raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                       message="Schema 必须为 YAML mapping",
                       details={"reason": "不是 YAML mapping"})

    # version
    version = raw.get("version")
    if not isinstance(version, str) or not version.strip():
        raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                       message="Schema 缺少 version 字段",
                       details={"reason": "缺少 version 字段"})

    # document_type
    document_type = raw.get("document_type")
    if not isinstance(document_type, str) or not document_type.strip():
        raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                       message="Schema 缺少 document_type 字段",
                       details={"reason": "缺少 document_type 字段"})

    # field_groups
    field_groups = raw.get("field_groups")
    if not isinstance(field_groups, list) or len(field_groups) == 0:
        raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                       message="Schema field_groups 必须为非空列表",
                       details={"reason": "field_groups 不能为空"})

    seen_group_keys = set()
    seen_field_keys = set()
    normalized_groups = []

    for group in field_groups:
        if not isinstance(group, dict):
            raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                           message="field_group 必须为 dict",
                           details={"reason": "field_group 格式非法"})

        group_key = group.get("group_key")
        if not isinstance(group_key, str) or not group_key.strip():
            raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                           message="field_group 缺少 group_key",
                           details={"reason": "缺少 group_key"})

        group_label = group.get("group_label")
        if not isinstance(group_label, str) or not group_label.strip():
            raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                           message="field_group 缺少 group_label",
                           details={"reason": "缺少 group_label",
                                    "group_key": group_key})

        if group_key in seen_group_keys:
            raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                           message="field_group group_key 重复",
                           details={"reason": "group_key 重复",
                                    "group_key": group_key})
        seen_group_keys.add(group_key)

        fields = group.get("fields")
        if not isinstance(fields, list) or len(fields) == 0:
            raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                           message="field_group 的 fields 必须为非空列表",
                           details={"reason": "fields 不能为空",
                                    "group_key": group_key})

        normalized_fields = []
        for field in fields:
            if not isinstance(field, dict):
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field 必须为 dict",
                               details={"reason": "field 格式非法",
                                        "group_key": group_key})

            field_key = field.get("field_key")
            if not isinstance(field_key, str) or not field_key.strip():
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field 缺少 field_key",
                               details={"reason": "缺少 field_key",
                                        "group_key": group_key})

            label = field.get("label")
            if not isinstance(label, str) or not label.strip():
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field 缺少 label",
                               details={"reason": "缺少 label",
                                        "field_key": field_key})

            if field_key in seen_field_keys:
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field_key 重复",
                               details={"reason": "field_key 重复",
                                        "field_key": field_key})
            seen_field_keys.add(field_key)

            field_type = field.get("type", "string")
            if field_type not in ALLOWED_FIELD_TYPES:
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field type 非法",
                               details={"reason": "type 非法",
                                        "field_key": field_key,
                                        "type": field_type})

            required = field.get("required", False)
            if not isinstance(required, bool):
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field required 必须为 boolean",
                               details={"reason": "required 非法",
                                        "field_key": field_key})

            hint = field.get("hint", "")
            if not isinstance(hint, str):
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field hint 必须为 string",
                               details={"reason": "hint 非法",
                                        "field_key": field_key})

            normalized_fields.append({
                "field_key": field_key,
                "label": label,
                "type": field_type,
                "required": required,
                "hint": hint,
            })

        normalized_groups.append({
            "group_key": group_key,
            "group_label": group_label,
            "fields": normalized_fields,
        })

    return {
        "version": version,
        "document_type": document_type,
        "field_groups": normalized_groups,
    }
```

- [ ] **Step 4: 运行测试确认 GREEN**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_loader.py -v
```

预期: ALL 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/schema_loader.py app/backend/tests/test_schema_loader.py
git commit -m "feat: 实现 SchemaLoader 加载与校验"
```

---

### Task 3: SchemaService TDD

**Files:**
- Create: `app/backend/tests/test_schema_service.py`
- Create: `app/backend/services/schema_service.py`

- [ ] **Step 1: 写失败测试**

创建 `app/backend/tests/test_schema_service.py`：

```python
import os
import tempfile
import pytest
import yaml


def _write_schema(tmpdir, data):
    path = os.path.join(tmpdir, "schema.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)
    return path


def _valid_schema():
    return {
        "version": "1.0.0",
        "document_type": "general_medical_record",
        "field_groups": [
            {
                "group_key": "basic",
                "group_label": "基本信息",
                "fields": [
                    {"field_key": "name", "label": "姓名", "type": "string"},
                    {"field_key": "age", "label": "年龄", "type": "number"},
                ],
            },
            {
                "group_key": "exam",
                "group_label": "检查",
                "fields": [
                    {"field_key": "temp", "label": "体温", "type": "string"},
                ],
            },
        ],
    }


class TestSchemaService:
    @staticmethod
    def _make_service(tmpdir, schema_data=None):
        from app.backend.services.schema_service import SchemaService

        data = schema_data if schema_data is not None else _valid_schema()
        path = _write_schema(tmpdir, data)
        return SchemaService(path)

    def test_get_current_returns_schema_dict(self, tmp_path):
        service = self._make_service(tmp_path)
        schema = service.get_current()
        assert schema["version"] == "1.0.0"
        assert len(schema["field_groups"]) == 2

    def test_get_current_version(self, tmp_path):
        service = self._make_service(tmp_path)
        assert service.get_current_version() == "1.0.0"

    def test_get_allowed_field_keys(self, tmp_path):
        service = self._make_service(tmp_path)
        keys = service.get_allowed_field_keys()
        assert keys == {"name", "age", "temp"}

    def test_get_field_order_returns_ordered_list(self, tmp_path):
        service = self._make_service(tmp_path)
        order = service.get_field_order()
        assert order == ["name", "age", "temp"]

    def test_build_validator_returns_schema_validator(self, tmp_path):
        from app.backend.services.schema_validator import SchemaValidator

        service = self._make_service(tmp_path)
        validator = service.build_validator()
        assert isinstance(validator, SchemaValidator)

    def test_cache_reuses_loaded_schema(self, tmp_path):
        service = self._make_service(tmp_path)
        first = service.get_current()
        second = service.get_current()
        assert first is second
```

- [ ] **Step 2: 运行测试确认 RED**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_service.py -v
```

预期: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 schema_service.py**

创建 `app/backend/services/schema_service.py`：

```python
from .schema_loader import load_schema
from .schema_validator import SchemaValidator


class SchemaService:
    """持有当前 schema 路径和内存缓存。BE-06 对其他后端模块的入口。"""

    def __init__(self, schema_path: str):
        self._schema_path = schema_path
        self._cached = None

    def _ensure_loaded(self):
        if self._cached is None:
            self._cached = load_schema(self._schema_path)

    def get_current(self) -> dict:
        self._ensure_loaded()
        return self._cached

    def get_current_version(self) -> str:
        return self.get_current()["version"]

    def get_allowed_field_keys(self) -> set[str]:
        keys = set()
        for group in self.get_current()["field_groups"]:
            for field in group["fields"]:
                keys.add(field["field_key"])
        return keys

    def get_field_order(self) -> list[str]:
        order = []
        for group in self.get_current()["field_groups"]:
            for field in group["fields"]:
                order.append(field["field_key"])
        return order

    def build_validator(self) -> SchemaValidator:
        return SchemaValidator(self.get_allowed_field_keys())
```

需要先提供 `SchemaValidator` 占位，使 `build_validator` 测试可运行。创建 `app/backend/services/schema_validator.py`（Task 4 会替换为完整实现）：

```python
class SchemaValidationError(ValueError):
    pass


class SchemaValidator:
    def __init__(self, allowed_field_keys: set[str]):
        self._allowed = allowed_field_keys
```

- [ ] **Step 4: 运行测试确认 GREEN**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_service.py -v
```

预期: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/schema_service.py app/backend/services/schema_validator.py app/backend/tests/test_schema_service.py
git commit -m "feat: 实现 SchemaService 缓存包装器"
```

---

### Task 4: SchemaValidator TDD

**Files:**
- Create: `app/backend/tests/test_schema_validator.py`
- Modify: `app/backend/services/schema_validator.py`（替换占位实现）

- [ ] **Step 1: 写失败测试**

创建 `app/backend/tests/test_schema_validator.py`：

```python
import pytest
from app.backend.services.schema_validator import SchemaValidator, SchemaValidationError


class TestSchemaValidator:
    @staticmethod
    def _make_validator(allowed=None):
        return SchemaValidator(allowed or {"name", "age", "gender"})

    def test_validate_empty_candidates_raises(self):
        validator = self._make_validator()
        with pytest.raises(SchemaValidationError, match="候选字段列表为空"):
            validator.validate_candidates([])

    def test_validate_unknown_field_key_raises(self):
        validator = self._make_validator()
        candidates = [{"field_key": "unknown_field", "value": "x"}]
        with pytest.raises(SchemaValidationError, match="unknown_field"):
            validator.validate_candidates(candidates)

    def test_validate_duplicate_field_key_raises(self):
        validator = self._make_validator()
        candidates = [
            {"field_key": "name", "value": "a"},
            {"field_key": "name", "value": "b"},
        ]
        with pytest.raises(SchemaValidationError, match="重复"):
            validator.validate_candidates(candidates)

    def test_validate_missing_field_key_raises(self):
        validator = self._make_validator()
        candidates = [{"value": "x"}]
        with pytest.raises(SchemaValidationError, match="缺少 field_key"):
            validator.validate_candidates(candidates)

    def test_validate_valid_candidates_passes(self):
        validator = self._make_validator()
        candidates = [
            {"field_key": "name", "value": "张三"},
            {"field_key": "age", "value": "30"},
        ]
        result = validator.validate_candidates(candidates)
        assert result == candidates

    def test_validate_alias_accepts_be05_signature(self):
        validator = self._make_validator()
        candidates = [{"field_key": "name", "value": "张三"}]
        result = validator.validate(candidates, {"version": "1.0.0"})
        assert result == candidates
```

- [ ] **Step 2: 运行测试确认 RED**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_validator.py -v
```

预期: FAIL — `AttributeError: 'SchemaValidator' object has no attribute 'validate_candidates'`

- [ ] **Step 3: 替换 SchemaValidator 为完整实现**

替换 `app/backend/services/schema_validator.py`：

```python
class SchemaValidationError(ValueError):
    """SchemaValidator 白名单校验失败。由 BE-05 捕获并映射为任务 failed。"""
    pass


class SchemaValidator:
    """只做 schema 白名单契约校验。不生成、补齐、排序或改写字段值。"""

    def __init__(self, allowed_field_keys: set[str]):
        self._allowed = allowed_field_keys

    def validate(self, candidates: list[dict], schema: dict | None = None) -> list[dict]:
        """BE-05 orchestrator 注入调用入口；schema 参数只为签名兼容，不读取或改写。"""
        return self.validate_candidates(candidates)

    def validate_candidates(self, candidates: list[dict]) -> list[dict]:
        if not candidates:
            raise SchemaValidationError("候选字段列表为空")

        seen_keys = set()
        for candidate in candidates:
            field_key = candidate.get("field_key")
            if not field_key:
                raise SchemaValidationError("候选字段缺少 field_key")
            if field_key not in self._allowed:
                raise SchemaValidationError(
                    f"候选字段 {field_key} 不在 schema 中")
            if field_key in seen_keys:
                raise SchemaValidationError(
                    f"候选字段 {field_key} 重复")
            seen_keys.add(field_key)

        return candidates
```

- [ ] **Step 4: 运行测试确认 GREEN**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_validator.py -v
```

预期: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/schema_validator.py app/backend/tests/test_schema_validator.py
git commit -m "feat: 实现 SchemaValidator 白名单校验"
```

---

### Task 5: API Route + App Factory 布线

**Files:**
- Create: `app/backend/routes/schema.py`
- Modify: `app/backend/__init__.py`

- [ ] **Step 1: 创建 schema_bp**

创建 `app/backend/routes/schema.py`：

```python
from flask import Blueprint, current_app
from ..responses import success

schema_bp = Blueprint("schema", __name__)


@schema_bp.route("/api/schema/current")
def get_current_schema():
    service = current_app.config["SCHEMA_SERVICE"]
    schema = service.get_current()
    data = {
        "version": schema["version"],
        "document_type": schema["document_type"],
        "field_groups": [
            {
                "group_key": g["group_key"],
                "group_label": g["group_label"],
                "fields": [
                    {
                        "field_key": f["field_key"],
                        "key": f["field_key"],
                        "label": f["label"],
                        "type": f["type"],
                        "required": f["required"],
                        "hint": f["hint"],
                    }
                    for f in g["fields"]
                ],
            }
            for g in schema["field_groups"]
        ],
    }
    return success(data=data)
```

- [ ] **Step 2: 修改 create_backend_app**

在 `app/backend/__init__.py` 中，找到现有的服务初始化区域。在 `SESSION_SERVICE` 初始化之后追加。若 BE-05 已经合并并在同一区域创建了 `TASK_SERVICE` 或 `ProcessingOrchestrator`，只追加 `SCHEMA_SERVICE`，不得覆盖 BE-05 的 orchestrator 装配：

```python
    # 初始化 SchemaService
    import os
    from .services.schema_service import SchemaService

    schema_path = os.path.join(PROJECT_ROOT, "app", "config", "schemas",
                               "medical_record.v1.yaml")
    app.config["SCHEMA_SERVICE"] = SchemaService(schema_path)
```

然后在 Blueprint 注册区域追加：

```python
    from .routes.schema import schema_bp
    app.register_blueprint(schema_bp)
```

如果 BE-05 已经合并，额外在 orchestrator 装配处使用当前 schema 和 validator：

```python
    schema_service = app.config["SCHEMA_SERVICE"]
    processing_orchestrator = ProcessingOrchestrator(
        store=store,
        image_port=DefaultImageProcessingPort(),
        doc_port=DefaultDocumentParsingPort(),
        field_port=DefaultFieldExtractionPort(),
        schema_validator=schema_service.build_validator(),
    )
```

`TaskService.process()`/`retry()` 调用时由路由或服务装配传入 `schema_service.get_current()`；BE-06 不在本任务中修改 BE-05 端口实现。

- [ ] **Step 3: 冒烟测试确认可启动**

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/worktree-be06-schema && conda run -n manzufei_ocr python -c "from app.backend import create_backend_app; app = create_backend_app(); print('OK')"
```

预期: OK

- [ ] **Step 4: Commit**

```bash
git add app/backend/routes/schema.py app/backend/__init__.py
git commit -m "feat: 注册 GET /api/schema/current 路由"
```

---

### Task 6: API 集成测试

**Files:**
- Create: `app/backend/tests/test_schema_api.py`

- [ ] **Step 1: 写 API 集成测试**

创建 `app/backend/tests/test_schema_api.py`：

```python
import os
import tempfile
import pytest
import yaml
from app.backend import create_backend_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()

    # 写入合法 schema 文件
    schema_data = {
        "version": "1.0.0",
        "document_type": "general_medical_record",
        "field_groups": [
            {
                "group_key": "basic",
                "group_label": "基本信息",
                "fields": [
                    {"field_key": "name", "label": "姓名", "type": "string"},
                ],
            }
        ],
    }
    schema_path = schemas_dir / "medical_record.v1.yaml"
    with open(schema_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(schema_data, f)

    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{tmp_path}"
  log_dir: "{tmp_path}/logs"
  storage_dir: "{tmp_path}"
  export_dir: "{tmp_path}/exports"
sessions:
  capture_session_ttl_minutes: 30
""",
        encoding="utf-8",
    )

    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    # 替换 schema 路径为临时目录
    monkeypatch.setattr("app.backend.services.schema_service.SchemaService.__init__",
                        lambda self, path: setattr(self, "_schema_path", str(schema_path))
                        or setattr(self, "_cached", None))
    app = create_backend_app(config_dir=str(config_dir))
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestSchemaAPI:
    def test_get_current_schema_returns_200(self, client):
        resp = client.get("/api/schema/current")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["version"] == "1.0.0"
        assert data["data"]["document_type"] == "general_medical_record"

    def test_response_has_field_groups_with_field_key_and_key(self, client):
        resp = client.get("/api/schema/current")
        data = resp.get_json()
        groups = data["data"]["field_groups"]
        assert len(groups) == 1
        field = groups[0]["fields"][0]
        assert field["field_key"] == "name"
        assert field["key"] == "name"
        assert field["label"] == "姓名"

    def test_response_field_groups_preserve_order(self, client):
        resp = client.get("/api/schema/current")
        groups = resp.get_json()["data"]["field_groups"]
        assert groups[0]["group_key"] == "basic"
```

- [ ] **Step 2: 运行 API 测试确认 GREEN**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_api.py -v
```

预期: 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add app/backend/tests/test_schema_api.py
git commit -m "test: 增加 GET /api/schema/current API 集成测试"
```

---

### Task 7: 全量回归与 BDD 对照

- [ ] **Step 1: 运行全量测试**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/ -v
```

预期: 所有已有 + 新增测试全部 PASS

- [ ] **Step 2: BDD 场景对照**

| BDD 场景 | 覆盖测试 |
|----------|----------|
| 读取当前生效的 schema | `test_get_current_schema_returns_200` |
| Schema 缺少必要字段时加载失败 | `test_reject_missing_version` 等 |
| Schema 包含重复 field_key 时拒绝加载 | `test_reject_duplicate_field_key` |
| 修改 schema 后新任务使用新版本 | `test_get_current_version`（SchemaService 提供版本号） |
| 后端不得用 schema 兜底抽取字段 | `test_validate_unknown_field_key_raises`（SchemaValidator 只做白名单校验） |
| 不同文书类型可选择不同 schema | `test_load_valid_schema_returns_dict`（schema 含 document_type） |

- [ ] **Step 3: 越界检查**

```bash
rg -n "ocr|llm|crop|perspective|quad_points|image_width|image_height" app/backend --glob '!tests' --glob '!enums.py' --glob '!errors.py'
```

预期: 无本计划新增越界实现

- [ ] **Step 4: Commit 收尾（如有修改）**

```bash
git status --short
```
