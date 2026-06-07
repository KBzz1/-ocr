# 患者中心记录归档 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加轻量患者档案，使任务在创建前绑定患者、记录类型和记录时间，并支持按患者阅览历次结构化结果、任务改绑、逻辑删除和带患者元数据导出。

**Architecture:** 继续使用本地 `JsonStore`，患者保存在 `patients/{patient_id}.json`，任务继续保存在 `tasks/{task_id}.json`。现有 `document_type` 是记录类型的唯一后端字段；新增 `patient_id`、`patient_snapshot`、`record_date`、`record_time`、`deleted_at` 和轻量元数据变更历史。患者详情只返回任务摘要，展开字段时按需复用现有审核接口，避免复制审核契约。

**Tech Stack:** Flask、Python、JsonStore、pytest、React 18、TypeScript、Vite、Vitest、React Testing Library、MSW、Playwright。

**Spec:** `docs/superpowers/specs/2026-06-07-patient-centered-records-design.md`

---

## 实施约束

- 开始实现前先读取根 `AGENTS.md`、`docs/AGENTS.md`、`app/backend/CLAUDE.md`、`app/frontend/README.md`。
- 工作区可能有用户未提交改动；每次提交只暂存当前任务文件，不得回滚或覆盖无关修改。
- 所有代码任务遵循 TDD：先写失败测试并运行确认，再写最小实现。
- Python 命令使用 `conda run -n manzufei_ocr`。
- Git commit message 使用中文。
- 不提交真实患者数据、日志、导出文件、模型、密钥或本机私有路径。
- 所有前端 fixture 使用“测试用例”等虚构信息；不得 `console.*` 输出患者姓名、OCR 原文、结构化字段值或包含这些内容的对象。
- 正常用户删除不得调用 `CleanupService.cleanup_task`；物理清理不属于本功能。
- 不新增 `record_type` 字段；界面叫“记录类型”，后端继续使用 `document_type` / `document_type_label`。

## 里程碑

1. **里程碑 A：后端患者与任务归属**，对应 Task 1-6。
2. **里程碑 B：前端患者中心闭环**，对应 Task 7-11。
3. **里程碑 C：数据整理与全量验收**，对应 Task 12。

---

### Task 1: 先更新产品、术语、错误码与 BDD/TDD 契约

**Files:**
- Modify: `docs/PRD文档/产品PRD.md`
- Modify: `docs/PRD文档/PRD任务清单.md`
- Modify: `docs/Shared/terminology.md`
- Modify: `docs/Shared/error-codes.md`
- Create: `docs/Backend/Backend_BDD/patient-records.md`
- Create: `docs/Backend/Backend_TDD/17-patient-records.md`
- Create: `docs/Front/Front_BDD/patient-records.md`
- Create: `docs/Front/Front_TDD/17-patient-records.md`
- Modify: `docs/Backend/Backend_BDD/AGENTS.md`
- Modify: `docs/Backend/Backend_TDD/AGENTS.md`
- Modify: `docs/Front/Front_BDD/AGENTS.md`
- Modify: `docs/Front/Front_TDD/AGENTS.md`
- Modify: `app/backend/CLAUDE.md`
- Modify: `app/frontend/README.md`

- [ ] **Step 1: 写入共享术语和错误码契约**

在 `docs/Shared/terminology.md` 增加：

```markdown
| 患者 | 用系统患者编号归集多个任务的轻量档案；首版仅要求患者姓名 |
| 患者编号 | 系统生成且不可变的患者唯一标识，不承载医院业务语义 |
| 记录类型 | 用户界面对 `document_type` 的称谓，例如“入院记录” |
| 记录时间 | 用户填写的记录日期和可选具体时间，不等同于任务创建时间 |
| 患者中心 | 按患者、记录类型和记录时间组织任务的阅览方式 |
```

在 `docs/Shared/error-codes.md` 增加：

```markdown
| `PATIENT_NOT_FOUND` | 404 | 患者不存在 |
| `PATIENT_DELETED` | 409 | 患者已删除，不能用于创建或改绑任务 |
```

BDD/TDD 同步写明：查询不存在或已删除患者、重复删除患者返回 `PATIENT_NOT_FOUND`；创建任务或改绑到已删除患者返回 `PATIENT_DELETED`；已逻辑删除任务继续返回 `TASK_NOT_FOUND`。

- [ ] **Step 2: 更新 PRD 和任务清单**

在 PRD 中明确：

```text
新建任务弹窗填写患者、记录类型、记录日期和可选时间
→ 提交创建 uploading 任务
→ 展示二维码
→ 手机只上传图片，不修改记录类型
```

任务清单新增：

```markdown
| BE-PAT-01 患者档案与任务归属 | 待开始 | `app/backend/services/patient_service.py`、`app/backend/services/task_service.py` | 患者、记录时间、改绑、逻辑删除 |
| FE-PAT-01 患者中心页面 | 待开始 | `app/frontend/src/pages/patients/`、工作台新建任务弹窗 | 患者搜索、详情时间轴、字段摘要 |
```

同时把 `FE-MVP-02-05 手机端文书模板选择` 标记为“需收敛”，注明本功能将移除手机端模板切换。

在 `app/backend/CLAUDE.md` 增加 `routes/patient.py`、`patient_service.py`、`patient_query_service.py` 指针；在 `app/frontend/README.md` 增加患者管理和患者详情页面职责。

- [ ] **Step 3: 写 BDD 场景**

四份 BDD/TDD 文档至少覆盖：

```gherkin
场景: 创建带患者归属的任务
  假如存在一个未删除患者
  当用户提交患者、记录类型和记录日期
  那么系统创建 uploading 任务并返回二维码

场景: 删除患者但保留任务
  当用户仅删除患者
  那么患者默认不可见
  并且关联任务显示患者已删除且允许改绑

场景: 处理后修改记录类型
  当 review 或 done 任务修改记录类型
  那么任务重新进入 processing
  并且旧 Schema 的审核字段不再可展示或导出
```

TDD 文档写明 fixture、接口、失败条件和测试文件路径，不写实现代码。

- [ ] **Step 4: 检查文档无冲突**

Run:

```bash
rg -n "手机端.*(文书|记录).*选择|点击.*新建任务.*立即|PATIENT_NOT_FOUND|PATIENT_DELETED" docs
git diff --check
```

Expected:

- PRD 不再要求手机端选择记录类型。
- 新错误码在共享文档中只有一个权威定义。
- `git diff --check` 无输出。

- [ ] **Step 5: Commit**

```bash
git add docs/PRD文档 docs/Shared docs/Backend/Backend_BDD docs/Backend/Backend_TDD docs/Front/Front_BDD docs/Front/Front_TDD app/backend/CLAUDE.md app/frontend/README.md
git commit -m "文档：补充患者中心业务与测试契约"
```

---

### Task 2: 患者服务、错误码和患者 API

**Files:**
- Create: `app/backend/services/patient_service.py`
- Create: `app/backend/routes/patient.py`
- Create: `app/backend/tests/test_patient_service.py`
- Create: `app/backend/tests/test_patient_routes.py`
- Create: `app/backend/tests/conftest.py`
- Modify: `app/backend/errors.py`
- Modify: `app/backend/routes/__init__.py`
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/services/local_event_log.py`
- Test: `app/backend/tests/test_errors.py`
- Test: `app/backend/tests/test_logging_integration.py`

- [ ] **Step 1: 写 PatientService 失败测试**

在 `test_patient_service.py` 覆盖：

```python
def test_create_patient_generates_stable_id_and_allows_duplicate_names(tmp_path):
    service = PatientService(JsonStore(str(tmp_path)), now=lambda: "2026-06-07T10:00:00+08:00")
    first = service.create("张三")
    second = service.create("张三")
    assert first["patient_id"].startswith("P-")
    assert first["patient_id"] != second["patient_id"]
    assert first["name"] == second["name"] == "张三"

def test_search_matches_exact_id_or_name_and_hides_deleted(tmp_path):
    store = JsonStore(str(tmp_path))
    service = PatientService(store, now=lambda: "2026-06-07T10:00:00+08:00")
    visible = service.create("张三")
    deleted = service.create("张三")
    service.mark_deleted(deleted["patient_id"])
    assert [item["patient_id"] for item in service.list("张三")] == [visible["patient_id"]]

def test_rename_appends_name_history(tmp_path):
    service = PatientService(JsonStore(str(tmp_path)), now=lambda: "2026-06-07T10:00:00+08:00")
    patient = service.create("张三")
    renamed = service.rename(patient["patient_id"], "李四")
    assert renamed["name_history"][-1] == {
        "from_name": "张三",
        "to_name": "李四",
        "changed_at": "2026-06-07T10:00:00+08:00",
    }

def test_get_bindable_rejects_deleted_patient(tmp_path):
    service = PatientService(JsonStore(str(tmp_path)), now=lambda: "2026-06-07T10:00:00+08:00")
    patient = service.create("张三")
    service.mark_deleted(patient["patient_id"])
    with pytest.raises(AppError) as exc:
        service.get_bindable(patient["patient_id"])
    assert exc.value.code == ErrorCode.PATIENT_DELETED.code
```

另加两个边界测试：

```python
def test_patient_id_retries_on_collision(tmp_path, monkeypatch):
    values = iter([
        type("U", (), {"hex": "a1b2c3d4ffffffffffffffffffffffff"})(),
        type("U", (), {"hex": "a1b2c3d4eeeeeeeeeeeeeeeeeeeeeeee"})(),
        type("U", (), {"hex": "e5f6a7b8dddddddddddddddddddddddd"})(),
    ])
    monkeypatch.setattr("app.backend.services.patient_service.uuid4", lambda: next(values))
    service = PatientService(JsonStore(str(tmp_path)))
    assert service.create("甲")["patient_id"] == "P-A1B2C3D4"
    assert service.create("乙")["patient_id"] == "P-E5F6A7B8"

def test_patient_public_shape_omits_name_history(tmp_path):
    service = PatientService(JsonStore(str(tmp_path)))
    patient = service.create("甲")
    renamed = service.rename(patient["patient_id"], "乙")
    assert "name_history" in renamed
    assert "name_history" not in service.to_public(renamed)
```

`conftest.py` 提供本功能共用的 `store`、`patient_service`、`task_service`、`write_task`、`seeded_patient_task` 和 `seeded_processing_patient_task` fixture。`write_task` 固定签名为 `write_task(task_id="1", status="uploading", **overrides)`，只服务本轮新增测试，不强制重构所有旧测试文件。

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_patient_service.py -q
```

Expected: FAIL，原因是 `patient_service` 尚不存在。

- [ ] **Step 3: 实现最小 PatientService**

核心接口：

```python
class PatientService:
    def create(self, name: str) -> dict:
        """创建未删除患者并返回规范化记录。"""

    def list(self, query: str | None = None) -> list[dict]:
        """返回未删除患者，可按编号或姓名过滤。"""

    def get(self, patient_id: str, *, include_deleted: bool = False) -> dict:
        """读取患者；默认把已删除患者视为不存在。"""

    def get_bindable(self, patient_id: str) -> dict:
        """读取可绑定患者；已删除时抛 PATIENT_DELETED。"""

    def rename(self, patient_id: str, name: str) -> dict:
        """修改姓名并追加 name_history。"""

    def mark_deleted(self, patient_id: str) -> dict:
        """设置 deleted_at，不删除 JSON 文件。"""
```

编号生成：

```python
def _new_patient_id(self) -> str:
    while True:
        patient_id = f"P-{uuid4().hex[:8].upper()}"
        if not self._store.exists(f"patients/{patient_id}.json"):
            return patient_id
```

姓名使用 `.strip()`，空姓名抛出 `INVALID_REQUEST_PARAMS`。查询参数也先 `.strip()`；空查询返回全部未删除患者，患者编号做精确匹配，姓名做包含匹配。`PatientService` 内部记录保留 `name_history`，患者路由和 `PatientQueryService` 返回前统一调用 `to_public()` 过滤该字段。

- [ ] **Step 4: 运行 PatientService 测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_patient_service.py -q
```

Expected: PASS。

- [ ] **Step 5: 写患者路由失败测试**

在 `test_patient_routes.py` 覆盖：

```python
def test_patient_crud_contract(client):
    created = client.post("/api/patients", json={"name": "测试患者"})
    assert created.status_code == 201
    patient_id = created.get_json()["data"]["patient_id"]
    assert client.get("/api/patients?query=测试患者").status_code == 200
    assert client.patch(f"/api/patients/{patient_id}", json={"name": "测试用例"}).status_code == 200
```

患者删除路由和删除后绑定测试留到 Task 6；本任务只实现创建、搜索、详情和改名。

- [ ] **Step 6: 运行路由测试确认失败**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_patient_routes.py app/backend/tests/test_errors.py -q
```

Expected: FAIL，患者蓝图和错误码尚未注册。

- [ ] **Step 7: 注册错误码、服务和蓝图**

在 `errors.py` 增加：

```python
PATIENT_NOT_FOUND = ("PATIENT_NOT_FOUND", 404, "患者不存在")
PATIENT_DELETED = ("PATIENT_DELETED", 409, "患者已删除，不能继续使用")
```

在 `routes/__init__.py` 增加 `_get_patient_service()`；在 app factory 中先创建 `PatientService` 并写入 `app.config["PATIENT_SERVICE"]`，再创建 `TaskService`。Task 3 将该实例注入 `TaskService`。Task 5 在 `TaskService` 创建完成后再创建 `PatientQueryService`，避免循环依赖。注册 `patient_bp` 后运行 app factory 测试确认 getter 可用。

患者 API：

```text
POST   /api/patients
GET    /api/patients?query=
GET    /api/patients/{patient_id}
PATCH  /api/patients/{patient_id}
```

事件日志只写 `patient_id`，事件名使用：

```text
patient_created
patient_renamed
```

同步更新固定白名单：

```python
ALLOWED_EVENTS |= {"patient_created", "patient_renamed"}
EVENT_FIELDS["patient_created"] = {"patient_id"}
EVENT_FIELDS["patient_renamed"] = {"patient_id"}
```

在 `test_logging_integration.py` 增加 `test_patient_event_log_has_no_pii`：执行创建和改名后读取 `backend-events.jsonl`，断言两个事件存在、包含 `patient_id`，且不包含修改前后姓名。

- [ ] **Step 8: 运行患者和日志测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest \
  app/backend/tests/test_patient_service.py \
  app/backend/tests/test_patient_routes.py \
  app/backend/tests/test_errors.py \
  app/backend/tests/test_logging_integration.py -q
```

Expected: PASS，日志断言中不存在患者姓名。

- [ ] **Step 9: Commit**

```bash
git add app/backend/errors.py app/backend/__init__.py app/backend/routes/__init__.py app/backend/routes/patient.py app/backend/services/patient_service.py app/backend/services/local_event_log.py app/backend/tests/conftest.py app/backend/tests/test_patient_service.py app/backend/tests/test_patient_routes.py app/backend/tests/test_errors.py app/backend/tests/test_logging_integration.py
git commit -m "功能：新增患者档案服务和接口"
```

---

### Task 3: 创建任务时绑定患者和记录时间

**Files:**
- Modify: `app/backend/services/task_service.py`
- Modify: `app/backend/routes/task.py`
- Modify: `app/backend/routes/mobile.py`
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/tests/test_task_service.py`
- Modify: `app/backend/tests/test_task_routes.py`
- Modify: `app/backend/tests/test_api_contracts.py`
- Modify: `app/backend/tests/test_backend_e2e.py`
- Modify: `app/backend/tests/test_logging_integration.py`
- Modify: `app/backend/tests/test_mobile_upload_routes.py`
- Modify: `app/backend/tests/test_export_service.py`
- Modify: `app/backend/tests/test_orchestrator.py`
- Modify: `app/backend/tests/test_reextraction_service.py`
- Modify: `app/backend/tests/test_review_service.py`
- Modify: `app/backend/tests/fixtures/processing.py`
- Modify: `app/backend/tests/fixtures/client.py`

- [ ] **Step 1: 写创建契约失败测试**

更新测试，要求：

```python
payload = {
    "patient_id": patient["patient_id"],
    "document_type": "copd_admission_record",
    "record_date": "2026-06-07",
    "record_time": "09:30",
}
response = client.post("/api/tasks", json=payload)
data = response.get_json()["data"]
assert data["patient"]["patient_id"] == patient["patient_id"]
assert data["record_date"] == "2026-06-07"
assert data["record_time"] == "09:30"
```

同时覆盖：

- 缺少患者、记录类型或记录日期返回 `INVALID_REQUEST_PARAMS`。
- 日期不是 `YYYY-MM-DD`、时间不是 `HH:mm` 时拒绝。
- 已删除患者返回 `PATIENT_DELETED`。
- 任务 ID 继续保持数字字符串兼容现有 UI；生成规则固定为所有任务 JSON（包括已逻辑删除任务）的最大数字 ID 加一，并在写入前检查目标文件不存在。禁止继续使用 `len(tasks)+1`。
- 增加 `test_create_task_id_uses_max_plus_one_even_with_gaps`：已有 `1.json`、`5.json` 和 `task_legacy.json` 时，新任务 ID 为 `"6"`；非数字旧 ID 不参与最大值计算，但文件继续保留。
- 日期/时间使用 `pytest.mark.parametrize` 覆盖 `2026-13-45`、`2026-02-30`、`24:00`、`23:60`，均返回 `INVALID_REQUEST_PARAMS`。
- 迁移 `test_backend_e2e.py`、`test_logging_integration.py`、`test_mobile_upload_routes.py` 和 `tests/fixtures/client.py` 中所有无请求体的 `POST /api/tasks`，统一先创建测试患者，再提交完整任务 payload。
- 删除 `PATCH /api/mobile-upload/{task_id}/document-type` 路由测试，改为断言该路径返回 404；手机上传状态响应移除 `available_document_types`。

- [ ] **Step 2: 运行失败测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest \
  app/backend/tests/test_task_service.py \
  app/backend/tests/test_task_routes.py \
  app/backend/tests/test_api_contracts.py -q
```

Expected: FAIL，旧接口不接收 payload。

- [ ] **Step 3: 修改 TaskService 创建接口**

签名改为：

```python
def create_uploading_task(
    self,
    base_url: str,
    *,
    patient_id: str,
    document_type: str,
    record_date: str,
    record_time: str | None = None,
) -> dict:
```

创建时：

```python
patient = self._patient_service.get_bindable(patient_id)
document_summary = self._document_summary_for(document_type)
task.update({
    "patient_id": patient["patient_id"],
    "patient_snapshot": {"patient_id": patient["patient_id"], "name": patient["name"]},
    "record_date": record_date,
    "record_time": record_time,
    "deleted_at": None,
    "metadata_history": [],
})
```

`TaskService.__init__` 增加必需的 `patient_service` 参数；app factory 传入 Task 2 已注册的 `app.config["PATIENT_SERVICE"]`。同步更新 `test_task_service.py`、`test_backend_e2e.py`、`test_export_service.py`、`test_orchestrator.py`、`test_reextraction_service.py`、`test_review_service.py`、`tests/fixtures/processing.py` 中所有直接构造点，注入 `PatientService` 或最小 fake。

使用 `datetime.strptime` 严格校验日期和时间。`_to_task_summary` 返回：

```python
"patient": {
    "patient_id": task["patient_id"],
    "name": resolved_patient_name,
    "deleted": patient_deleted,
},
"record_date": task["record_date"],
"record_time": task.get("record_time"),
```

- [ ] **Step 4: 修改 POST `/api/tasks`**

读取 JSON 并显式传参：

```python
body = request.get_json(silent=True) or {}
return success(
    data=_get_task_service().create_uploading_task(
        base_url=_mobile_base_url(),
        patient_id=body.get("patient_id"),
        document_type=body.get("document_type"),
        record_date=body.get("record_date"),
        record_time=body.get("record_time"),
    ),
    status=201,
)
```

同时从 `routes/mobile.py` 删除 `change_task_document_type` 路由；手机上传状态只返回当前任务的 `document_type`、`document_type_label` 和 `schema_version`，不返回可选类型列表。

删除不再使用的 `TaskService.change_document_type` 和对应服务测试；`DocumentProfileRegistry.remember_last_document_type` 不再由手机上传流程调用。记录类型修改统一走 Task 4 的 `update_metadata`。

- [ ] **Step 5: 运行聚焦测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest \
  app/backend/tests/test_task_service.py \
  app/backend/tests/test_task_routes.py \
  app/backend/tests/test_api_contracts.py \
  app/backend/tests/test_backend_e2e.py \
  app/backend/tests/test_logging_integration.py \
  app/backend/tests/test_mobile_upload_routes.py -q
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add app/backend/services/task_service.py app/backend/routes/task.py app/backend/routes/mobile.py app/backend/__init__.py app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py app/backend/tests/test_api_contracts.py app/backend/tests/test_backend_e2e.py app/backend/tests/test_logging_integration.py app/backend/tests/test_mobile_upload_routes.py app/backend/tests/test_export_service.py app/backend/tests/test_orchestrator.py app/backend/tests/test_reextraction_service.py app/backend/tests/test_review_service.py app/backend/tests/fixtures/processing.py app/backend/tests/fixtures/client.py
git commit -m "功能：创建任务时绑定患者和记录时间"
```

---

### Task 4: 任务归属修改、改绑和记录类型重新处理

**Files:**
- Modify: `app/backend/services/task_service.py`
- Modify: `app/backend/routes/task.py`
- Modify: `app/backend/tests/test_task_service.py`
- Modify: `app/backend/tests/test_task_routes.py`
- Modify: `app/backend/tests/test_backend_e2e.py`
- Modify: `app/backend/tests/test_orchestrator.py`

- [ ] **Step 1: 写元数据修改失败测试**

覆盖：

```python
def test_update_metadata_rejects_processing_task(task_service, write_task):
    write_task(status="processing")
    with pytest.raises(AppError) as exc:
        task_service.update_metadata("1", patient_id="P-A1B2C3D4")
    assert exc.value.code == ErrorCode.INVALID_TASK_TRANSITION.code

def test_rebind_patient_preserves_images_and_review_results(task_service, store, write_task):
    write_task(status="review", images=[{"page_id": "p1"}])
    store.write("results/1/review_result.json", {"task_id": "1", "fields": []})
    updated = task_service.update_metadata("1", patient_id="P-E5F6A7B8")
    assert updated["images"] == [{"page_id": "p1"}]
    assert store.read("results/1/review_result.json") == {"task_id": "1", "fields": []}

def test_change_document_type_after_review_reuses_ocr_and_reextracts_fields(task_service, write_task):
    write_task(status="review", document_type="copd_admission_record")
    updated = task_service.update_metadata("1", document_type="progress_note")
    assert updated["status"] == "processing"
    assert updated["document_type"] == "progress_note"
```

断言：

- `uploading` 可直接修改患者、`document_type`、日期和时间。
- `processing` 返回 `INVALID_TASK_TRANSITION`。
- `review` / `done` 只修改患者或时间时不改变任务状态、图片和审核结果。
- `review` / `done` 修改 `document_type` 时更新 schema/prompt 元数据并进入 `processing`。
- 成功 `document_result.json` 存在时，`doc_port.parse` 调用次数为 0，新记录类型的 `field_port.extract` 调用次数为 1。
- 缺少成功 OCR 文本时返回 `REEXTRACTION_VALIDATION_FAILED`，任务和旧审核结果保持不变。
- `ReextractJobRegistry.get(task_id)` 非空时，记录类型更正返回 `INVALID_TASK_TRANSITION`，不修改任务或审核结果。
- `metadata_history` 每项严格等于 `{field, from_value, to_value, changed_at}`，不通过普通任务 API 返回。
- `GET /api/tasks` 和 `GET /api/tasks/{task_id}` 的响应均不包含 `metadata_history`；服务内部持久化记录仍保留。
- 记录类型更正前，把旧 `review_result.json` 写入 `results/{task_id}/record_type_change_archive/{change_id}.json`；新审核结果不得读取旧 Schema 字段。

- [ ] **Step 2: 运行失败测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest \
  app/backend/tests/test_task_service.py \
  app/backend/tests/test_task_routes.py \
  app/backend/tests/test_backend_e2e.py -q
```

Expected: FAIL，更新接口尚不存在。

- [ ] **Step 3: 实现统一更新方法**

新增：

```python
def update_metadata(
    self,
    task_id: str,
    *,
    patient_id: str | None = None,
    document_type: str | None = None,
    record_date: str | None = None,
    record_time: str | None = None,
) -> dict:
```

行为：

```python
if task["status"] == TaskStatus.PROCESSING.value:
    raise AppError(
        ErrorCode.INVALID_TASK_TRANSITION,
        details={"current": task["status"], "target": "metadata_change"},
    )

document_type_changed = document_type is not None and document_type != task["document_type"]
if document_type_changed and task["status"] != TaskStatus.UPLOADING.value:
    self._assert_saved_ocr_available(task_id)
    self._archive_review_result(task_id)
    task.update(self._document_summary_for(document_type))
    self._append_metadata_history(task, "document_type", previous_type, document_type)
    self._write_task(task)
    processing_task = self._start_processing(task_id, "更正记录类型后重新处理")
    return self._dispatch_orchestrator(processing_task)
```

`_archive_review_result` 先写归档副本，再删除当前 `review_result.json`，确保后续审核初始化只读取新候选。归档不通过普通 API 暴露。

重新处理复用现有 orchestrator 和 GPU 队列。`ProcessingOrchestrator` 已会读取成功的 `document_result.json` 并跳过 `doc_port.parse`；本任务补回归测试锁定该行为。图片输入仍经过现有轻量 image port，OCR/文档解析不重跑，字段抽取使用新 `document_type` 的端口。字段抽取失败仍进入现有 `failed`。

- [ ] **Step 4: 增加 PATCH API**

```text
PATCH /api/tasks/{task_id}/metadata
```

请求体允许：

```json
{
  "patient_id": "P-A1B2C3D4",
  "document_type": "copd_admission_record",
  "record_date": "2026-06-07",
  "record_time": "09:30"
}
```

至少一个字段出现，否则返回 `INVALID_REQUEST_PARAMS`。

`TaskService` 增加内部/公开边界：持久化和服务内部可读取 `metadata_history`，`_to_task_summary` 与任务详情公开序列化均显式移除该字段。
路由在提交 `document_type` 变更前查询 `REEXTRACT_JOB_REGISTRY.get(task_id)`；存在活动重抽取时返回 `INVALID_TASK_TRANSITION`。患者改绑和记录时间修改不触碰字段结果，可继续按任务状态规则处理。

- [ ] **Step 5: 运行聚焦与 E2E 测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest \
  app/backend/tests/test_task_service.py \
  app/backend/tests/test_task_routes.py \
  app/backend/tests/test_backend_e2e.py \
  app/backend/tests/test_orchestrator.py -q
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add app/backend/services/task_service.py app/backend/routes/task.py app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py app/backend/tests/test_backend_e2e.py app/backend/tests/test_orchestrator.py
git commit -m "功能：支持任务归属修改和记录类型重处理"
```

---

### Task 5: 患者详情聚合和只读任务时间轴 API

**Files:**
- Create: `app/backend/services/patient_query_service.py`
- Modify: `app/backend/services/patient_service.py`
- Modify: `app/backend/services/task_service.py`
- Modify: `app/backend/routes/patient.py`
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/tests/test_patient_service.py`
- Modify: `app/backend/tests/test_patient_routes.py`

- [ ] **Step 1: 写患者详情失败测试**

测试数据包含：

```python
[
    {"document_type": "copd_admission_record", "record_date": "2026-06-07", "record_time": "09:30"},
    {"document_type": "copd_admission_record", "record_date": "2026-06-07", "record_time": None},
    {"document_type": "progress_note", "record_date": "2026-05-01", "record_time": "12:00"},
]
```

断言：

- 按 `document_type` 分组。
- 日期倒序，同日有时间记录在仅日期记录之前。
- 包含所有未删除任务状态。
- 不把审核字段嵌入患者详情响应。
- 患者列表返回未删除任务数和最近记录时间。

- [ ] **Step 2: 运行失败测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_patient_service.py app/backend/tests/test_patient_routes.py -q
```

Expected: FAIL，详情聚合尚未实现。

- [ ] **Step 3: 实现聚合**

新增：

```python
def get_detail(self, patient_id: str) -> dict:
    patient = self.get(patient_id)
    tasks = self._task_service.list_for_patient(patient_id)
    return {
        "patient": patient,
        "record_groups": self._group_tasks(tasks),
    }
```

使用独立 `PatientQueryService`，避免 `PatientService` 和 `TaskService` 循环依赖：

```python
class PatientQueryService:
    def __init__(self, patient_service, task_service):
        self._patient_service = patient_service
        self._task_service = task_service

    def get_detail(self, patient_id: str) -> dict:
        patient = self._patient_service.get(patient_id)
        tasks = self._task_service.list_for_patient(patient_id)
        return {"patient": patient, "record_groups": self._group_tasks(tasks)}

    def list_patients(self, query: str | None = None) -> list[dict]:
        patients = self._patient_service.list(query)
        return [self._with_task_summary(patient) for patient in patients]
```

在 `TaskService` 增加 `list_for_patient(patient_id)`，只返回 `deleted_at` 为空的任务摘要，不受“空 uploading 任务在总任务列表隐藏”的 `_should_list_task` 规则影响。app factory 创建并注入 `PatientQueryService`，患者列表和详情路由通过该服务读取任务统计。

路由：

```text
GET /api/patients/{patient_id}/records
```

- [ ] **Step 4: 运行测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_patient_service.py app/backend/tests/test_patient_routes.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/patient_query_service.py app/backend/services/patient_service.py app/backend/services/task_service.py app/backend/routes/patient.py app/backend/__init__.py app/backend/tests/test_patient_service.py app/backend/tests/test_patient_routes.py
git commit -m "功能：提供患者记录时间轴查询"
```

---

### Task 6: 逻辑删除与导出患者元数据

**Files:**
- Modify: `app/backend/services/patient_service.py`
- Modify: `app/backend/services/task_service.py`
- Modify: `app/backend/services/export_service.py`
- Modify: `app/backend/routes/patient.py`
- Modify: `app/backend/routes/task.py`
- Modify: `app/backend/tests/test_patient_service.py`
- Modify: `app/backend/tests/test_patient_routes.py`
- Modify: `app/backend/tests/test_task_service.py`
- Modify: `app/backend/tests/test_task_routes.py`
- Modify: `app/backend/tests/test_export_service.py`
- Modify: `app/backend/tests/test_export_routes.py`

- [ ] **Step 1: 写逻辑删除失败测试**

覆盖：

```python
def test_delete_patient_only_keeps_tasks_visible_with_deleted_marker(client, seeded_patient_task):
    patient_id, task_id = seeded_patient_task
    response = client.delete(f"/api/patients/{patient_id}?delete_tasks=false")
    assert response.status_code == 200
    task = client.get(f"/api/tasks/{task_id}").get_json()["data"]
    assert task["patient"]["deleted"] is True

def test_delete_patient_and_tasks_hides_tasks_without_deleting_files(client, app, seeded_patient_task):
    patient_id, task_id = seeded_patient_task
    response = client.delete(f"/api/patients/{patient_id}?delete_tasks=true")
    assert response.status_code == 200
    assert client.get(f"/api/tasks/{task_id}").status_code == 404
    assert JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"]).exists(f"tasks/{task_id}.json")

def test_delete_patient_with_processing_tasks_is_rejected(client, seeded_processing_patient_task):
    patient_id, _task_id = seeded_processing_patient_task
    response = client.delete(f"/api/patients/{patient_id}?delete_tasks=true")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"

def test_deleted_task_behaves_as_task_not_found(client, seeded_patient_task):
    _patient_id, task_id = seeded_patient_task
    client.delete(f"/api/tasks/{task_id}")
    response = client.get(f"/api/tasks/{task_id}")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TASK_NOT_FOUND"

def test_deleted_patient_error_matrix(client, seeded_patient_task):
    patient_id, task_id = seeded_patient_task
    client.delete(f"/api/patients/{patient_id}?delete_tasks=false")
    assert client.get(f"/api/patients/{patient_id}").status_code == 404
    assert client.delete(f"/api/patients/{patient_id}?delete_tasks=false").status_code == 404
    response = client.patch(f"/api/tasks/{task_id}/metadata", json={"patient_id": patient_id})
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "PATIENT_DELETED"
```

测试必须记录任务 JSON、图片路径和结果文件在删除前后都存在。
增加查询参数解析测试：`?delete_tasks=false` 必须保留任务，`?delete_tasks=true` 才逻辑删除关联任务，其他字符串返回 `INVALID_REQUEST_PARAMS`。不要使用 Flask `type=bool`，显式比较 `"true"` / `"false"`。

- [ ] **Step 2: 写导出失败测试**

断言 JSON、Excel 和 batch zip model 都有：

```json
{
  "patient": {
    "patient_id": "P-A1B2C3D4",
    "name": "测试用例",
    "deleted": false
  },
  "record": {
    "document_type": "copd_admission_record",
    "document_type_label": "入院记录",
    "record_date": "2026-06-07",
    "record_time": "09:30"
  }
}
```

患者已删除但任务保留时使用 `patient_snapshot.name` 且 `deleted=true`。已删除任务不可导出。

- [ ] **Step 3: 运行失败测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest \
  app/backend/tests/test_patient_service.py \
  app/backend/tests/test_patient_routes.py \
  app/backend/tests/test_task_service.py \
  app/backend/tests/test_task_routes.py \
  app/backend/tests/test_export_service.py \
  app/backend/tests/test_export_routes.py -q
```

Expected: FAIL，现有删除仍是物理删除且导出无患者元数据。

- [ ] **Step 4: 实现逻辑删除**

患者删除接口：

```text
DELETE /api/patients/{patient_id}?delete_tasks=false
DELETE /api/patients/{patient_id}?delete_tasks=true
```

任务删除保持现有路径但改语义：

```python
def delete_task(self, task_id: str) -> dict:
    task = self._read_task(task_id)
    if task["status"] == TaskStatus.PROCESSING.value:
        raise AppError(
            ErrorCode.INVALID_TASK_TRANSITION,
            details={"current": task["status"], "target": "deleted"},
        )
    task["deleted_at"] = self._now()
    task["updated_at"] = task["deleted_at"]
    self._write_task(task)
    return task
```

删除路由不得调用：

```python
current_app.config["CLEANUP_SERVICE"].cleanup_task(task_id, confirm=True)
```

将读取方法签名改为 `_read_task(self, task_id: str, *, include_deleted: bool = False)`。普通调用保持默认值并拒绝已删除任务；内部逻辑删除批处理显式调用 `_read_task(task_id, include_deleted=True)`。
删除患者时，只对 `task.patient_id` 仍等于目标患者且 `deleted_at` 为空的任务刷新 `patient_snapshot`；已改绑任务不修改。

- [ ] **Step 5: 增加导出元数据**

在 `_build_export_model` 返回：

```python
"patient": self._task_service.patient_export_metadata(task),
"record": {
    "document_type": task.get("document_type"),
    "document_type_label": task.get("document_type_label"),
    "record_date": task.get("record_date"),
    "record_time": task.get("record_time"),
},
```

Excel 固定新增独立“任务信息”sheet，写入患者和记录元数据；现有“全部字段”和字段分组 sheet 的列结构保持不变。

- [ ] **Step 6: 运行聚焦测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest \
  app/backend/tests/test_patient_service.py \
  app/backend/tests/test_patient_routes.py \
  app/backend/tests/test_task_service.py \
  app/backend/tests/test_task_routes.py \
  app/backend/tests/test_export_service.py \
  app/backend/tests/test_export_routes.py -q
```

Expected: PASS，且测试确认任务文件和结果文件仍存在。

- [ ] **Step 7: 运行后端全量测试**

先明确翻面现有删除测试，不删除测试用例：

- `test_task_service.py::test_delete_task_removes_from_store` 改为断言任务 JSON 仍存在、`deleted_at` 非空、普通 `get_task` 返回 `TASK_NOT_FOUND`。
- `test_task_service.py::test_delete_task_works_for_non_processing_statuses` 对每个状态断言逻辑删除成功且 JSON 保留。
- `test_task_routes.py::test_delete_task_removes_from_listing` 保留列表过滤和 404 断言，并增加底层 JSON 仍存在。
- `test_task_routes.py::test_delete_task_with_cleanup` 改名为 `test_delete_task_does_not_cleanup_files`，断言任务、pages、results 目录均保留。
- 其余 processing 和 missing-task 删除测试保持原语义。

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: 全部 PASS。旧物理删除测试应改为逻辑删除断言，不得删除测试来规避失败。

- [ ] **Step 8: Commit**

```bash
git add app/backend/services/patient_service.py app/backend/services/task_service.py app/backend/services/export_service.py app/backend/routes/patient.py app/backend/routes/task.py app/backend/tests/test_patient_service.py app/backend/tests/test_patient_routes.py app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py app/backend/tests/test_export_service.py app/backend/tests/test_export_routes.py
git commit -m "功能：实现患者任务逻辑删除和导出元数据"
```

---

### Task 7: 前端患者和任务 API 契约

**Files:**
- Create: `app/frontend/src/api/patients.ts`
- Modify: `app/frontend/src/api/tasks.ts`
- Modify: `app/frontend/src/api/mobileUpload.ts`
- Modify: `app/frontend/src/api/shared-contracts.test.ts`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx`

- [ ] **Step 1: 写前端 API 失败测试**

测试以下请求：

```typescript
await createPatient({ name: '测试用例' });
await getPatients('测试');
await getPatientRecords('P-A1B2C3D4');
await updatePatient('P-A1B2C3D4', { name: '测试患者' });
await deletePatient('P-A1B2C3D4', false);
await createTask({
  patient_id: 'P-A1B2C3D4',
  document_type: 'copd_admission_record',
  record_date: '2026-06-07',
  record_time: '09:30'
});
await updateTaskMetadata('1', { patient_id: 'P-E5F6A7B8' });
```

并断言 `mobileUpload.ts` 不再发起 `/document-type` PATCH。

- [ ] **Step 2: 运行失败测试**

Run:

```bash
npm --prefix app/frontend run test -- src/api/shared-contracts.test.ts src/pages/mobile-capture/MobileCapturePage.test.tsx
```

Expected: FAIL，患者 API 和新创建参数尚不存在。

- [ ] **Step 3: 实现类型与 API**

`patients.ts` 定义：

```typescript
export interface PatientSummary {
  patient_id: string;
  name: string;
  task_count: number;
  latest_record_at?: string | null;
}

export interface PatientRecordGroup {
  document_type: string;
  document_type_label: string;
  tasks: TaskSummary[];
}
```

`tasks.ts` 扩展：

```typescript
export interface CreateTaskInput {
  patient_id: string;
  document_type: string;
  record_date: string;
  record_time?: string | null;
}

export interface TaskPatientSummary {
  patient_id: string;
  name: string;
  deleted: boolean;
}

// CreateTaskResult 和 TaskSummary 均增加：
// patient: TaskPatientSummary
// document_type: string
// document_type_label?: string
// record_date: string
// record_time?: string | null

export function createTask(input: CreateTaskInput) {
  return apiRequest<CreateTaskResult>('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
}
```

`latest_record_at` 是该患者未删除任务中最大的记录时间，格式为本地 `YYYY-MM-DDTHH:mm`；仅日期记录使用 `YYYY-MM-DD`。无任务时为 `null`。

- [ ] **Step 4: 移除手机端记录类型选择**

从 `MobileCapturePage.tsx` 删除模板选择器、状态和 `changeTaskDocumentType` 调用。手机状态仍可只读显示 `document_type_label`，但不可编辑。

- [ ] **Step 5: 运行测试和类型检查**

Run:

```bash
npm --prefix app/frontend run test -- src/api/shared-contracts.test.ts src/pages/mobile-capture/MobileCapturePage.test.tsx
npm --prefix app/frontend run typecheck
```

Expected: 两条命令 PASS。

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/api/patients.ts app/frontend/src/api/tasks.ts app/frontend/src/api/mobileUpload.ts app/frontend/src/api/shared-contracts.test.ts app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx
git commit -m "功能：接入患者和任务归属前端契约"
```

---

### Task 8: 统一新建任务弹窗，提交后展示二维码

**Files:**
- Create: `app/frontend/src/components/workstation/CreateTaskDialog.tsx`
- Create: `app/frontend/src/components/workstation/CreateTaskDialog.test.tsx`
- Modify: `app/frontend/src/app/App.tsx`
- Modify: `app/frontend/src/app/App.test.tsx`
- Modify: `app/frontend/src/pages/workstation/WorkstationPage.tsx`
- Modify: `app/frontend/src/components/workstation/WorkstationHero.tsx`
- Modify: `app/frontend/src/components/workstation/workstation.css`

- [ ] **Step 1: 写弹窗失败测试**

写三个完整 RTL 测试：

1. mock `GET /api/patients?query=` 返回患者 `P-A1B2C3D4`，依次选择患者、`copd_admission_record`、`2026-06-07`、`09:30`，点击创建后捕获 `POST /api/tasks` 请求体并断言：

```typescript
expect(createRequestBody).toEqual({
  patient_id: 'P-A1B2C3D4',
  document_type: 'copd_admission_record',
  record_date: '2026-06-07',
  record_time: '09:30'
});
```

2. mock 精确同名搜索返回两个患者，断言页面先显示两个患者编号和“仍然新建”，用户点击“仍然新建”后才调用 `POST /api/patients`。
3. 延迟 `POST /api/tasks` 响应，断言响应返回前页面不存在“任务上传二维码”；响应成功后二维码出现且值等于服务端 `mobile_upload_url`。

- [ ] **Step 2: 运行失败测试**

Run:

```bash
npm --prefix app/frontend run test -- src/components/workstation/CreateTaskDialog.test.tsx src/app/App.test.tsx
```

Expected: FAIL，新弹窗尚不存在。

- [ ] **Step 3: 实现 CreateTaskDialog**

组件 props：

```typescript
type CreateTaskDialogProps = {
  isOpen: boolean;
  isSubmitting: boolean;
  onClose: () => void;
  onSubmit: (input: CreateTaskInput) => Promise<void>;
};
```

表单同屏显示患者搜索/新建、记录类型、日期和时间。患者新建流程：

1. 输入姓名；
2. 调用 `getPatients(name)`；
3. 若有精确同名，显示患者编号、任务数和最近记录时间；
4. 用户选择已有患者或点击“仍然新建”；
5. 创建患者后填入新 `patient_id`。

- [ ] **Step 4: 修改 App 创建流程**

`handleCreateSession` 不再直接调用 `createTask()`。点击“新建任务”只打开表单；表单提交成功后设置 `currentTask` 并切换到现有 `CaptureQrDialog`。

`currentTask` 继续使用扩展后的 `CreateTaskResult | null`；同步更新 `tests/fixtures/tasks.ts` 的 `mockCreateTask` 默认结果和 `App.test.tsx` 中所有创建任务 mock，使其包含患者、记录类型和记录时间。

- [ ] **Step 5: 运行测试**

Run:

```bash
npm --prefix app/frontend run test -- src/components/workstation/CreateTaskDialog.test.tsx src/app/App.test.tsx
npm --prefix app/frontend run typecheck
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/components/workstation/CreateTaskDialog.tsx app/frontend/src/components/workstation/CreateTaskDialog.test.tsx app/frontend/src/app/App.tsx app/frontend/src/app/App.test.tsx app/frontend/src/pages/workstation/WorkstationPage.tsx app/frontend/src/components/workstation/WorkstationHero.tsx app/frontend/src/components/workstation/workstation.css
git commit -m "功能：新增患者归属任务创建弹窗"
```

---

### Task 9: 患者管理页面、导航和搜索

**Files:**
- Create: `app/frontend/src/pages/patients/PatientsPage.tsx`
- Create: `app/frontend/src/pages/patients/PatientsPage.test.tsx`
- Create: `app/frontend/src/pages/patients/patients.css`
- Modify: `app/frontend/src/app/routes.tsx`
- Modify: `app/frontend/src/app/routes.test.ts`
- Modify: `app/frontend/src/app/App.tsx`
- Modify: `app/frontend/src/components/layout/WorkstationLayout.tsx`

- [ ] **Step 1: 写路由和页面失败测试**

断言：

```typescript
expect(appRoutes.patients.path).toBe('/patients');
expect(buildPatientPath('P/A')).toBe('/patients/P%2FA');
```

页面测试覆盖：

- 姓名或编号搜索。
- 列表显示姓名、患者编号、任务数、最近记录时间。
- 新建患者。
- 点击进入患者详情。
- 主导航显示“患者管理”并正确高亮。

- [ ] **Step 2: 运行失败测试**

Run:

```bash
npm --prefix app/frontend run test -- src/app/routes.test.ts src/pages/patients/PatientsPage.test.tsx
```

Expected: FAIL，路由和页面尚不存在。

- [ ] **Step 3: 实现患者列表页面**

路由：

```typescript
patients: { id: 'patients', label: '患者管理', path: '/patients' }
```

页面使用 `WorkstationLayout activeRouteId="patients"`，采用显式“搜索”按钮。请求期间禁用搜索按钮，避免快速连击产生响应错序；组件测试使用延迟 MSW 响应断言第二次点击不会发出并发请求。

- [ ] **Step 4: 注册 App 路由和导航**

匹配：

```typescript
if (pathname === '/patients' || pathname === '/patients/') {
  return <PatientsPage />;
}
```

`WorkstationLayoutProps.activeRouteId` 增加 `patients`。

- [ ] **Step 5: 运行测试和类型检查**

Run:

```bash
npm --prefix app/frontend run test -- src/app/routes.test.ts src/pages/patients/PatientsPage.test.tsx
npm --prefix app/frontend run typecheck
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/pages/patients app/frontend/src/app/routes.tsx app/frontend/src/app/routes.test.ts app/frontend/src/app/App.tsx app/frontend/src/components/layout/WorkstationLayout.tsx
git commit -m "功能：新增患者管理页面"
```

---

### Task 10: 患者详情、类型导航、时间轴和字段摘要

**Files:**
- Create: `app/frontend/src/pages/patients/PatientDetailPage.tsx`
- Create: `app/frontend/src/pages/patients/PatientDetailPage.test.tsx`
- Modify: `app/frontend/src/pages/patients/patients.css`
- Modify: `app/frontend/src/app/App.tsx`
- Modify: `app/frontend/src/app/routes.tsx`
- Modify: `app/frontend/src/api/patients.ts`
- Reuse: `app/frontend/src/api/review.ts`
- Reuse: `app/frontend/src/components/review/FieldList.tsx`

- [ ] **Step 1: 写详情页失败测试**

覆盖：

- 左侧显示记录类型和数量。
- 默认选择第一组，右侧按服务端顺序展示时间轴。
- `review` / `done` 点击展开才调用审核接口。
- `uploading` / `processing` / `failed` 不请求审核结果。
- 字段按 Schema 分组展示全部字段，包括空值。
- “进入审核/查看结果”跳转现有审核页。
- 改名后刷新页头和列表数据。

- [ ] **Step 2: 运行失败测试**

Run:

```bash
npm --prefix app/frontend run test -- src/pages/patients/PatientDetailPage.test.tsx
```

Expected: FAIL，详情页尚不存在。

- [ ] **Step 3: 实现详情页**

App 匹配：

```typescript
if (/^\/patients\/[^/]+\/?$/.test(pathname)) {
  return <PatientDetailPage />;
}
```

按需加载审核结果：

```typescript
async function toggleRecord(task: TaskSummary) {
  if (!['review', 'done'].includes(task.status)) return;
  if (!reviewsByTaskId[task.task_id]) {
    const review = await getReviewResult(task.task_id);
    setReviewsByTaskId((current) => ({ ...current, [task.task_id]: review }));
  }
  setExpandedTaskId((current) => current === task.task_id ? null : task.task_id);
}
```

复用 `FieldList` 前先确认其 props 支持只读；若不支持，增加 `readOnly` prop，并补原组件测试。

- [ ] **Step 4: 运行测试**

Run:

```bash
npm --prefix app/frontend run test -- src/pages/patients/PatientDetailPage.test.tsx src/pages/review/ReviewPage.test.tsx
npm --prefix app/frontend run typecheck
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/pages/patients/PatientDetailPage.tsx app/frontend/src/pages/patients/PatientDetailPage.test.tsx app/frontend/src/pages/patients/patients.css app/frontend/src/app/App.tsx app/frontend/src/app/routes.tsx app/frontend/src/api/patients.ts app/frontend/src/components/review/FieldList.tsx app/frontend/src/pages/review/ReviewPage.test.tsx
git commit -m "功能：新增患者记录时间轴和字段阅览"
```

---

### Task 11: 任务管理、审核页、改绑和删除交互

**Files:**
- Modify: `app/frontend/src/components/tasks/TaskList.tsx`
- Modify: `app/frontend/src/components/tasks/tasks.css`
- Modify: `app/frontend/src/pages/tasks/TasksPlaceholder.tsx`
- Modify: `app/frontend/src/pages/tasks/TasksPage.test.tsx`
- Modify: `app/frontend/src/pages/review/ReviewPage.tsx`
- Modify: `app/frontend/src/pages/review/ReviewPage.test.tsx`
- Modify: `app/frontend/src/pages/patients/PatientDetailPage.tsx`
- Modify: `app/frontend/src/pages/patients/PatientDetailPage.test.tsx`
- Modify: `app/frontend/src/api/tasks.ts`
- Modify: `app/frontend/src/api/patients.ts`

- [ ] **Step 1: 写任务管理失败测试**

断言每行显示：

```text
患者姓名 / 患者编号
记录类型
记录日期和可选时间
患者已删除标记
改绑患者
```

在 `TaskList.tsx` 增加一个合并列“患者与记录”，同一单元格显示患者姓名/编号、记录类型和记录时间；患者已删除时在该列显示状态标记。不要拆成多个窄列，避免现有桌面表格横向膨胀。

覆盖：

- 改绑到现有患者。
- 在改绑弹窗中新建患者。
- `processing` 任务禁用改绑并说明原因。
- 删除任务后行消失，但 API 语义为逻辑删除。

- [ ] **Step 2: 写患者删除失败测试**

详情页删除弹窗提供：

```text
仅删除患者
同时删除患者及关联任务
```

存在 `processing` 任务时，“同时删除”返回后端错误并保持页面数据。

- [ ] **Step 3: 写审核页元数据失败测试**

页头显示患者姓名、患者编号、记录类型、记录时间。患者已删除但任务保留时显示“患者已删除”。

- [ ] **Step 4: 运行失败测试**

Run:

```bash
npm --prefix app/frontend run test -- \
  src/pages/tasks/TasksPage.test.tsx \
  src/pages/review/ReviewPage.test.tsx \
  src/pages/patients/PatientDetailPage.test.tsx
```

Expected: FAIL，新字段和交互尚未实现。

- [ ] **Step 5: 实现任务改绑和删除 UI**

复用 `updateTaskMetadata(taskId, { patient_id })`。处理中的任务按钮禁用；后端仍是最终校验方。

患者删除调用：

```typescript
deletePatient(patientId, false)
deletePatient(patientId, true)
```

成功后导航回 `/patients`。失败显示统一错误消息，不在前端推测任务状态。

- [ ] **Step 6: 实现审核页元数据展示**

使用 `getTaskDetail` 返回的患者和记录字段，不从 OCR 或字段内容推断。

- [ ] **Step 7: 运行前端聚焦测试**

Run:

```bash
npm --prefix app/frontend run test -- \
  src/pages/tasks/TasksPage.test.tsx \
  src/pages/review/ReviewPage.test.tsx \
  src/pages/patients/PatientDetailPage.test.tsx
npm --prefix app/frontend run typecheck
```

Expected: PASS。

- [ ] **Step 8: 运行前端全量测试和构建**

Run:

```bash
npm --prefix app/frontend run test
npm --prefix app/frontend run build
```

Expected: 全部 PASS，构建成功。

- [ ] **Step 9: Commit**

```bash
git add app/frontend/src/components/tasks app/frontend/src/pages/tasks app/frontend/src/pages/review app/frontend/src/pages/patients app/frontend/src/api/tasks.ts app/frontend/src/api/patients.ts
git commit -m "功能：补充任务患者改绑和删除交互"
```

---

### Task 12: 一次性测试数据整理、E2E 和最终验收

**Files:**
- Create: `scripts/maintenance/prepare_patient_demo_data.py`
- Create: `app/backend/tests/test_prepare_patient_demo_data.py`
- Modify: `scripts/CLAUDE.md`
- Create: `app/frontend/tests/e2e/patient-records.spec.ts`
- Modify: `app/frontend/tests/e2e/helpers/mvpApi.ts`
- Modify: `docs/PRD文档/PRD任务清单.md`

- [ ] **Step 1: 写数据整理脚本失败测试**

测试使用临时目录，不操作真实 `data/`：

```python
def test_prepare_demo_data_keeps_one_visible_task_and_binds_test_patient(tmp_path):
    store = JsonStore(str(tmp_path))
    store.write("tasks/1.json", {"task_id": "1", "status": "done", "deleted_at": None})
    store.write("tasks/2.json", {"task_id": "2", "status": "failed", "deleted_at": None})
    result = prepare_demo_data(
        storage_dir=str(tmp_path),
        keep_task_id="1",
        record_date="2026-06-07",
        apply=True,
    )
    visible_tasks = [task for task in store.list_json("tasks") if not task.get("deleted_at")]
    kept_task = store.read("tasks/1.json")
    patient = store.read(f"patients/{kept_task['patient_id']}.json")
    assert visible_tasks == [kept_task]
    assert patient["name"] == "测试用例"
    assert kept_task["patient_id"] == patient["patient_id"]
    assert store.exists("tasks/2.json")
    assert result["hidden_task_count"] == 1
```

还要断言：

- 其他任务仅设置 `deleted_at`，文件和结果目录保留。
- 保留任务补充有效 `record_date`、`document_type`。
- 重复运行脚本幂等，不创建多个“测试用例”患者。
- `--keep-task-id` 不存在时进程返回非零，目录内文件内容和 mtime 均不变化。
- 任务 JSON 中即使包含病历原文、手机号或身份证号，stdout/stderr 也不包含这些内容。

- [ ] **Step 2: 运行失败测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_prepare_patient_demo_data.py -q
```

Expected: FAIL，脚本尚不存在。

- [ ] **Step 3: 实现维护脚本**

CLI：

```text
python scripts/maintenance/prepare_patient_demo_data.py \
  --storage-dir <path> \
  --keep-task-id <task_id> \
  --record-date 2026-06-07
```

安全规则：

- 必须显式传 `--storage-dir` 和 `--keep-task-id`。
- 找不到保留任务时退出非零，不修改数据。
- 默认 dry-run；只有 `--apply` 才写入。
- 启动时输出 `DEV TOOL ONLY`，`--apply` 还必须同时提供 `--confirm-dev-data`。
- 输出只显示任务 ID、患者 ID 和计数，不输出患者病历内容。

- [ ] **Step 4: 运行脚本测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_prepare_patient_demo_data.py -q
```

Expected: PASS。

- [ ] **Step 5: 写并运行患者中心 E2E**

E2E 覆盖：

```text
新建“测试用例”患者
→ 同一弹窗创建任务
→ 创建成功后出现二维码
→ 患者管理能搜索到患者
→ 患者详情显示该任务及记录时间
→ review fixture 任务可展开字段摘要
→ 进入审核页
→ 仅删除患者
→ 任务管理仍显示该任务并标记“患者已删除”
```

E2E 只覆盖上述主闭环和最关键删除可见性。记录类型更正失败、逻辑删除文件保留、导出元数据、日期边界、错误码矩阵由后端 API/服务测试和前端组件测试覆盖，不重复扩大浏览器测试。

Run:

```bash
npm --prefix app/frontend run test:e2e -- patient-records.spec.ts
```

Expected: PASS。

- [ ] **Step 6: 执行最终全量验证**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
npm --prefix app/frontend run test
npm --prefix app/frontend run build
npm --prefix app/frontend run test:e2e
git diff --check
! rg -n "console\\.(log|debug|info|warn|error)" app/frontend/src
```

Expected:

- 后端测试全部 PASS。
- 前端 Vitest 全部 PASS。
- TypeScript/Vite 构建成功。
- Playwright E2E 全部 PASS。
- `git diff --check` 无输出。
- 前端业务源码没有 `console.*` 调用，避免输出患者姓名、OCR 原文或字段值。

- [ ] **Step 7: 仅在用户确认目标开发数据目录后执行整理**

先 dry-run：

```bash
STORAGE_DIR="/path/confirmed-by-user"
KEEP_TASK_ID="confirmed-task-id"
conda run -n manzufei_ocr python scripts/maintenance/prepare_patient_demo_data.py \
  --storage-dir "$STORAGE_DIR" \
  --keep-task-id "$KEEP_TASK_ID" \
  --record-date 2026-06-07
```

Expected: 输出将保留/逻辑删除的计数，不修改文件。

用户确认 dry-run 后：

```bash
conda run -n manzufei_ocr python scripts/maintenance/prepare_patient_demo_data.py \
  --storage-dir "$STORAGE_DIR" \
  --keep-task-id "$KEEP_TASK_ID" \
  --record-date 2026-06-07 \
  --confirm-dev-data \
  --apply
```

Expected: 仅一个任务默认可见并绑定“测试用例”患者；原始任务和结果文件仍存在。

- [ ] **Step 8: 更新任务清单状态**

将 `BE-PAT-01`、`FE-PAT-01` 及手机模板选择收敛项更新为实际完成状态，并写入实现文件与测试入口。

- [ ] **Step 9: Commit**

```bash
git add scripts/maintenance/prepare_patient_demo_data.py scripts/CLAUDE.md app/backend/tests/test_prepare_patient_demo_data.py app/frontend/tests/e2e docs/PRD文档/PRD任务清单.md
git commit -m "测试：补充患者中心验收和演示数据整理"
```

---

## 最终交付检查

- [ ] `POST /api/tasks` 必须带患者、`document_type` 和记录日期。
- [ ] 手机上传页不能修改记录类型。
- [ ] 患者详情不复制审核字段契约，只按需调用审核 API。
- [ ] `processing` 期间不能改绑或修改记录元数据。
- [ ] 处理后修改记录类型复用成功 OCR 文本，只重新执行新记录类型的字段抽取。
- [ ] 删除任务和患者不会物理删除文件。
- [ ] 已删除患者的保留任务可以改绑和导出，导出使用姓名快照并标记删除。
- [ ] 已删除任务普通 API 返回 `TASK_NOT_FOUND`。
- [ ] JSON、Excel、批量 JSON zip 都包含患者和记录元数据。
- [ ] 日志不记录患者姓名、OCR 原文或字段值。
- [ ] 开发数据整理只在用户确认目录和任务 ID 后执行。
