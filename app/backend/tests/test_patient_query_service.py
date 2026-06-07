"""Task 5: PatientQueryService 单元测试。

患者详情聚合按 document_type 分组,按 record_date 倒序、同日有时间排在仅日期记录之前。
列表返回未删除任务计数和最近记录时间。
"""
import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.patient_query_service import PatientQueryService
from app.backend.services.patient_service import PatientService
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


class StubPatientServiceBase:
    """直接复用真实 PatientService,只额外提供 fake now。"""

    def __init__(self, tmp_path):
        self._impl = PatientService(JsonStore(str(tmp_path)), now=lambda: "2026-06-07T10:00:00+08:00")

    def __getattr__(self, item):
        return getattr(self._impl, item)


def make_task_service(tmp_path, *, patient_service=None):
    if patient_service is None:
        patient_service = PatientService(
            JsonStore(str(tmp_path)),
            now=lambda: "2026-06-07T10:00:00+08:00",
        )
    return TaskService(
        store=JsonStore(str(tmp_path)),
        background_runner=lambda task_id, run: run(),
        schema_provider=lambda: {"version": "copd.v1", "document_type": "copd_admission_record"},
        patient_service=patient_service,
    )


def _seed_task(store, *, task_id, patient_id, document_type, record_date, record_time=None, status="review"):
    store.write(
        f"tasks/{task_id}.json",
        {
            "task_id": task_id,
            "status": status,
            "created_at": "2026-06-07T10:00:00+00:00",
            "updated_at": "2026-06-07T10:00:00+00:00",
            "images": [{"page_id": "p1", "page_no": 1}],
            "patient_id": patient_id,
            "patient_snapshot": {"patient_id": patient_id, "name": "测试用例"},
            "document_type": document_type,
            "document_type_label": "入院记录" if document_type == "copd_admission_record" else "病程记录",
            "schema_version": f"{document_type}.v1",
            "prompt_version": f"{document_type}.prompt.v1",
            "record_date": record_date,
            "record_time": record_time,
            "deleted_at": None,
        },
    )


def test_get_detail_groups_tasks_by_document_type_and_sorts_by_record_time(tmp_path):
    store = JsonStore(str(tmp_path))
    patient_service = PatientService(store, now=lambda: "2026-06-07T10:00:00+08:00")
    patient = patient_service.create("测试用例")
    task_service = make_task_service(tmp_path)

    _seed_task(store, task_id="1", patient_id=patient["patient_id"],
               document_type="copd_admission_record", record_date="2026-06-07", record_time="09:30")
    _seed_task(store, task_id="2", patient_id=patient["patient_id"],
               document_type="copd_admission_record", record_date="2026-06-07", record_time=None)
    _seed_task(store, task_id="3", patient_id=patient["patient_id"],
               document_type="progress_note", record_date="2026-05-01", record_time="12:00")

    query = PatientQueryService(patient_service, task_service)
    detail = query.get_detail(patient["patient_id"])

    assert detail["patient"]["patient_id"] == patient["patient_id"]
    groups_by_type = {group["document_type"]: group for group in detail["record_groups"]}
    assert "copd_admission_record" in groups_by_type
    assert "progress_note" in groups_by_type
    copd_tasks = groups_by_type["copd_admission_record"]["tasks"]
    # 同日 09:30 在仅日期记录之前
    assert [task["task_id"] for task in copd_tasks] == ["1", "2"]


def test_get_detail_orders_groups_by_most_recent_record_first(tmp_path):
    store = JsonStore(str(tmp_path))
    patient_service = PatientService(store, now=lambda: "2026-06-07T10:00:00+08:00")
    patient = patient_service.create("测试用例")
    task_service = make_task_service(tmp_path)

    _seed_task(store, task_id="1", patient_id=patient["patient_id"],
               document_type="progress_note", record_date="2026-06-07", record_time="09:30")
    _seed_task(store, task_id="2", patient_id=patient["patient_id"],
               document_type="copd_admission_record", record_date="2026-05-01", record_time="12:00")

    detail = PatientQueryService(patient_service, task_service).get_detail(patient["patient_id"])
    assert [g["document_type"] for g in detail["record_groups"]] == ["progress_note", "copd_admission_record"]


def test_get_detail_includes_all_non_deleted_statuses_and_omits_review_fields(tmp_path):
    store = JsonStore(str(tmp_path))
    patient_service = PatientService(store, now=lambda: "2026-06-07T10:00:00+08:00")
    patient = patient_service.create("测试用例")
    task_service = make_task_service(tmp_path)
    for status, tid in zip(("uploading", "processing", "review", "done", "failed"), ("1", "2", "3", "4", "5")):
        _seed_task(
            store,
            task_id=tid,
            patient_id=patient["patient_id"],
            document_type="copd_admission_record",
            record_date="2026-06-07",
            record_time=None,
            status=status,
        )
    # 写一份审核结果不应嵌入患者详情响应
    store.write(
        "results/3/review_result.json",
        {"task_id": "3", "fields": [{"field_key": "occupation", "final_value": "教师"}]},
    )

    detail = PatientQueryService(patient_service, task_service).get_detail(patient["patient_id"])

    [group] = detail["record_groups"]
    assert {task["task_id"] for task in group["tasks"]} == {"1", "2", "3", "4", "5"}
    serialized = str(detail)
    assert "教师" not in serialized
    assert "final_value" not in serialized


def test_get_detail_rejects_unknown_or_deleted_patient(tmp_path):
    store = JsonStore(str(tmp_path))
    patient_service = PatientService(store, now=lambda: "2026-06-07T10:00:00+08:00")
    task_service = make_task_service(tmp_path)
    query = PatientQueryService(patient_service, task_service)

    with pytest.raises(AppError) as exc:
        query.get_detail("P-MISSING01")
    assert exc.value.code == ErrorCode.PATIENT_NOT_FOUND.code

    patient = patient_service.create("测试用例")
    patient_service.mark_deleted(patient["patient_id"])
    with pytest.raises(AppError) as exc:
        query.get_detail(patient["patient_id"])
    assert exc.value.code == ErrorCode.PATIENT_NOT_FOUND.code


def test_list_patients_returns_task_count_and_latest_record_at(tmp_path):
    store = JsonStore(str(tmp_path))
    patient_service = PatientService(store, now=lambda: "2026-06-07T10:00:00+08:00")
    patient_a = patient_service.create("测试用例")
    patient_b = patient_service.create("测试病例")
    task_service = make_task_service(tmp_path)

    _seed_task(store, task_id="1", patient_id=patient_a["patient_id"],
               document_type="copd_admission_record", record_date="2026-06-07", record_time="09:30")
    _seed_task(store, task_id="2", patient_id=patient_a["patient_id"],
               document_type="copd_admission_record", record_date="2026-06-06", record_time=None)

    query = PatientQueryService(patient_service, task_service)
    items = {item["patient_id"]: item for item in query.list_patients()}

    assert items[patient_a["patient_id"]]["task_count"] == 2
    assert items[patient_a["patient_id"]]["latest_record_at"] == "2026-06-07T09:30"
    assert items[patient_b["patient_id"]]["task_count"] == 0
    assert items[patient_b["patient_id"]]["latest_record_at"] is None


def test_list_for_patient_in_task_service_returns_only_target_patient(tmp_path):
    store = JsonStore(str(tmp_path))
    patient_service = PatientService(store, now=lambda: "2026-06-07T10:00:00+08:00")
    patient_a = patient_service.create("测试用例")
    patient_b = patient_service.create("测试病例")
    task_service = make_task_service(tmp_path)

    _seed_task(store, task_id="1", patient_id=patient_a["patient_id"],
               document_type="copd_admission_record", record_date="2026-06-07", status="review")
    _seed_task(store, task_id="2", patient_id=patient_b["patient_id"],
               document_type="copd_admission_record", record_date="2026-06-07", status="review")
    # 已逻辑删除任务不应出现
    _seed_task(store, task_id="3", patient_id=patient_a["patient_id"],
               document_type="copd_admission_record", record_date="2026-06-07", status="review")
    task = store.read("tasks/3.json")
    task["deleted_at"] = "2026-06-07T11:00:00+00:00"
    store.write("tasks/3.json", task)

    tasks = task_service.list_for_patient(patient_a["patient_id"])
    assert [t["task_id"] for t in tasks] == ["1"]


def test_list_for_patient_returns_empty_uploading_task_unlike_list_tasks(tmp_path):
    """list_tasks 隐藏空 uploading 任务,但 list_for_patient 应返回所有未删除任务。"""
    store = JsonStore(str(tmp_path))
    patient_service = PatientService(store, now=lambda: "2026-06-07T10:00:00+08:00")
    patient = patient_service.create("测试用例")
    task_service = make_task_service(tmp_path)

    _seed_task(
        store,
        task_id="1",
        patient_id=patient["patient_id"],
        document_type="copd_admission_record",
        record_date="2026-06-07",
        status="uploading",
    )
    # 强制 images 为空
    raw = store.read("tasks/1.json")
    raw["images"] = []
    store.write("tasks/1.json", raw)

    assert task_service.list_tasks() == []
    assert [t["task_id"] for t in task_service.list_for_patient(patient["patient_id"])] == ["1"]
