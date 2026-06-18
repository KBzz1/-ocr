import pytest

from app.backend.enums import FieldStatus
from app.backend.errors import AppError, ErrorCode
from app.backend.services.reextraction_service import ReextractionService
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


class FakeFieldPort:
    def __init__(self):
        self.inputs = []

    def extract(self, input):
        self.inputs.append(input)
        return [
            {
                "field_key": "patient_name",
                "original_value": "张三",
                "evidence": "姓名：张三",
                "confidence": 0.9,
                "source_hint": "基本信息",
                "source_text": "姓名：张三",
                "source_section": "基本信息",
                "extraction_status": "extracted",
                "verification_status": "not_checked",
                "quality_flags": [],
                "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
            }
        ]


def schema():
    return {
        "version": "copd.v1",
        "document_type": "copd_admission_record",
        "field_groups": [
            {"group_key": "basic", "group_label": "基本信息", "fields": [{"field_key": "patient_name", "label": "姓名"}]}
        ],
    }


def make_service(tmp_path, field_port=None):
    store = JsonStore(str(tmp_path / "data"))
    task_service = TaskService(store=store)
    port = field_port or FakeFieldPort()
    service = ReextractionService(
        store=store,
        task_service=task_service,
        field_port=port,
        schema_provider=schema,
        prompt_version_provider=lambda: "copd.prompt.v1",
    )
    return service, store, task_service, port


def write_task(store, status="review"):
    store.write(
        "tasks/task_001.json",
        {
            "task_id": "task_001",
            "status": status,
            "created_at": "2026-05-29T10:00:00+00:00",
            "updated_at": "2026-05-29T10:00:00+00:00",
            "upload_token": "token",
            "images": [],
            "error_code": None,
            "error_message": None,
            "export_summary": {"last_exported_at": None, "formats": [], "files": []},
        },
    )


def write_document_result(store):
    store.write(
        "results/task_001/document_result.json",
        {
            "task_id": "task_001",
            "stage": "document_parsing",
            "status": "success",
            "merged_text": "姓名：张三",
            "pages": [{"page_id": "page_001", "page_no": 1, "text": "姓名：张三"}],
        },
    )


def write_existing_review(store):
    store.write(
        "results/task_001/review_result.json",
        {
            "task_id": "task_001",
            "schema_version": "old",
            "fields": [
                {
                    "field_key": "patient_name",
                    "field_name": "姓名",
                    "auto_value": "李四",
                    "final_value": "人工改过",
                    "status": FieldStatus.MODIFIED.value,
                }
            ],
        },
    )


def test_reextract_uses_saved_document_text_and_records_versions(tmp_path):
    service, store, _task_service, port = make_service(tmp_path)
    write_task(store, status="review")
    write_document_result(store)
    write_existing_review(store)

    result = service.reextract("task_001")

    assert port.inputs[0]["document_result"]["merged_text"] == "姓名：张三"
    assert port.inputs[0]["source"] == "ocr_text_only"
    assert result["schema_version"] == "copd.v1"
    assert result["prompt_version"] == "copd.prompt.v1"
    wrapper = store.read("results/task_001/field_candidates.json")
    assert wrapper["metadata"]["source"] == "ocr_text_only"
    assert wrapper["metadata"]["schema_version"] == "copd.v1"
    assert wrapper["metadata"]["prompt_version"] == "copd.prompt.v1"
    assert wrapper["candidates"][0]["original_value"] == "张三"
    # 新契约:review_result.json 已被覆盖,final_value 来自新候选
    review = store.read("results/task_001/review_result.json")
    field = next(f for f in review["fields"] if f["field_key"] == "patient_name")
    assert field["final_value"] == "张三"
    assert field["auto_value"] == "张三"
    assert field["status"] == FieldStatus.UNREVIEWED.value
    # history 末项是 reextract 记录
    last_history = field["history"][-1]
    assert last_history["action"] == "reextract"
    assert last_history["from_value"] == "人工改过"
    assert last_history["to_value"] == "张三"
    assert last_history["run_id"] == result["run_id"]
    run = store.read(f"results/task_001/reextract_runs/{result['run_id']}.json")
    assert run["task_id"] == "task_001"
    assert run["run_id"] == result["run_id"]
    assert run["source"] == "ocr_text_only"
    assert run["schema_version"] == "copd.v1"
    assert run["prompt_version"] == "copd.prompt.v1"
    assert run["candidate_count"] == 1
    assert run["created_at"]


def test_reextract_done_task_reopens_review(tmp_path):
    """done 任务重抽取后,review 被覆盖,且 status 回退到 review。"""
    service, store, task_service, _port = make_service(tmp_path)
    write_task(store, status="done")
    write_document_result(store)

    result = service.reextract("task_001")

    assert result["status"] == "review"
    assert task_service.get_task("task_001")["status"] == "review"
    # review_result.json 已被覆盖,字段状态为 unreviewed
    review = store.read("results/task_001/review_result.json")
    field = next(f for f in review["fields"] if f["field_key"] == "patient_name")
    assert field["final_value"] == "张三"
    assert field["status"] == FieldStatus.UNREVIEWED.value


def test_reextract_keeps_field_candidates_and_run_artifacts(tmp_path):
    """重抽取后 field_candidates.json 和 reextract_runs/{run_id}.json 内容不变,作为审计线索。"""
    service, store, _task_service, _port = make_service(tmp_path)
    write_task(store, status="review")
    write_document_result(store)

    result = service.reextract("task_001")

    wrapper = store.read("results/task_001/field_candidates.json")
    assert wrapper["candidates"][0]["original_value"] == "张三"
    assert wrapper["metadata"]["run_id"] == result["run_id"]
    run = store.read(f"results/task_001/reextract_runs/{result['run_id']}.json")
    assert run["candidate_count"] == 1
    assert run["task_id"] == "task_001"


def test_reextract_hydrates_schema_fields_into_review(tmp_path):
    """review 缺 schema 字段、候选补齐这些字段时,重抽取后 review 也补齐并采用新候选值。"""
    service, store, _task_service, _port = make_service(tmp_path)
    write_task(store, status="review")
    write_document_result(store)
    # review 完全没有 patient_name
    store.write(
        "results/task_001/review_result.json",
        {
            "task_id": "task_001",
            "schema_version": "old",
            "fields": [
                {
                    "field_key": "occupation",
                    "field_name": "职业",
                    "auto_value": "退休",
                    "final_value": "退休",
                    "status": FieldStatus.CONFIRMED.value,
                    "extraction_status": "extracted",
                    "verification_status": "not_checked",
                    "quality_flags": [],
                    "ocr_correction": None,
                    "history": [],
                }
            ],
        },
    )

    service.reextract("task_001")

    review = store.read("results/task_001/review_result.json")
    field_by_key = {f["field_key"]: f for f in review["fields"]}
    # occupation 还在,值是候选的 original_value(因为候选里有 occupation 吗?不,候选只有 patient_name)
    # 这里要注意:候选是 FakeFieldPort 返回的 patient_name
    # occupation 不在新候选里,但 review 已有,应保留原 review 字段(不重置)
    # 而 patient_name 是新候选,应被加入
    assert "patient_name" in field_by_key
    assert field_by_key["patient_name"]["final_value"] == "张三"
    assert field_by_key["patient_name"]["status"] == FieldStatus.UNREVIEWED.value


def test_reextract_discards_candidates_not_in_schema(tmp_path):
    """新候选有 schema 不存在的 field_key 时,该候选被丢弃,不写入 review。"""

    class MultiFieldPort:
        def extract(self, input):
            return [
                {
                    "field_key": "patient_name",
                    "original_value": "张三",
                    "evidence": "第1页",
                    "confidence": 0.9,
                    "extraction_status": "extracted",
                    "verification_status": "not_checked",
                    "quality_flags": [],
                    "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
                },
                {
                    "field_key": "unknown_field",
                    "original_value": "应被丢弃",
                    "evidence": "x",
                    "confidence": 0.5,
                    "extraction_status": "extracted",
                    "verification_status": "not_checked",
                    "quality_flags": [],
                    "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
                },
            ]

    service, store, _task_service, _port = make_service(tmp_path, field_port=MultiFieldPort())
    write_task(store, status="review")
    write_document_result(store)

    service.reextract("task_001")

    review = store.read("results/task_001/review_result.json")
    field_keys = [f["field_key"] for f in review["fields"]]
    assert "unknown_field" not in field_keys
    assert "patient_name" in field_keys


def test_reextract_requires_saved_ocr_text(tmp_path):
    service, store, _task_service, _port = make_service(tmp_path)
    write_task(store, status="review")

    with pytest.raises(AppError) as exc:
        service.reextract("task_001")

    assert exc.value.code == ErrorCode.REEXTRACTION_VALIDATION_FAILED.code


def test_reextract_maps_invalid_candidate_contract_to_reextract_error(tmp_path):
    class InvalidFieldPort:
        def extract(self, input):
            return [
                {
                    "field_key": "patient_name",
                    "original_value": "张三",
                    "extraction_status": "extracted",
                    "verification_status": "not_checked",
                    "quality_flags": "invalid",
                    "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
                }
            ]

    service, store, _task_service, _port = make_service(tmp_path, field_port=InvalidFieldPort())
    write_task(store, status="review")
    write_document_result(store)

    with pytest.raises(AppError) as exc:
        service.reextract("task_001")

    assert exc.value.code == ErrorCode.REEXTRACTION_VALIDATION_FAILED.code
    assert exc.value.details["reason"] == "invalid_candidate_contract"


def test_reextract_passes_saved_evidence_units_to_field_port(tmp_path):
    """saved document_result.json 已带 evidence_units 时,重抽取必须把它原样透传给 field port。"""
    service, store, _task_service, port = make_service(tmp_path)
    write_task(store, status="review")
    store.write(
        "results/task_001/document_result.json",
        {
            "task_id": "task_001",
            "stage": "document_parsing",
            "status": "success",
            "merged_text": "主诉：反复咳嗽、咳痰15年。",
            "pages": [{"page_id": "page_001", "page_no": 1, "text": "主诉：反复咳嗽、咳痰15年。"}],
            "evidence_units": [
                {
                    "id": "u001",
                    "text": "主诉：反复咳嗽、咳痰15年。",
                    "start_offset": 0,
                    "end_offset": 16,
                    "page_no": 1,
                }
            ],
        },
    )

    service.reextract("task_001")

    forwarded = port.inputs[0]
    units = forwarded.get("evidence_units")
    assert isinstance(units, list) and units, "field port must receive saved evidence_units"
    assert units[0]["id"] == "u001"
    assert units[0]["text"] == "主诉：反复咳嗽、咳痰15年。"
    assert forwarded["document_result"]["evidence_units"] == units


def test_reextract_generates_evidence_units_when_legacy_document_result_lacks_them(tmp_path):
    """legacy document_result.json 没有 evidence_units 字段时,重抽取必须从 OCR 原文重建并传给 field port。"""
    service, store, _task_service, port = make_service(tmp_path)
    write_task(store, status="review")
    # Legacy-style document_result without evidence_units
    store.write(
        "results/task_001/document_result.json",
        {
            "task_id": "task_001",
            "stage": "document_parsing",
            "status": "success",
            "merged_text": "主诉：反复咳嗽、咳痰15年。",
            "pages": [{"page_id": "page_001", "page_no": 1, "text": "主诉：反复咳嗽、咳痰15年。"}],
        },
    )

    service.reextract("task_001")

    forwarded = port.inputs[0]
    units = forwarded.get("evidence_units")
    assert isinstance(units, list) and units, "field port must receive rebuilt evidence_units"
    assert units[0]["id"] == "u001"
    assert "主诉" in units[0]["text"]


def test_reextract_uses_task_document_type_profile(tmp_path):
    class ProfileFieldPort(FakeFieldPort):
        pass

    class FakeProfiles:
        def __init__(self, field_port):
            self.field_port = field_port

        def get_profile(self, document_type):
            assert document_type == "copd_admission_record"
            return type("Profile", (), {
                "document_type": "copd_admission_record",
                "schema": schema(),
                "prompt_version": "copd.prompt.v2",
                "field_port": self.field_port,
            })()

    field_port = ProfileFieldPort()
    service, store, _task_service, _port = make_service(tmp_path, field_port=None)
    service._document_profiles = FakeProfiles(field_port)
    write_task(store, status="review")
    task = store.read("tasks/task_001.json")
    task["document_type"] = "copd_admission_record"
    store.write("tasks/task_001.json", task)
    write_document_result(store)

    result = service.reextract("task_001")

    assert field_port.inputs[0]["document_type"] == "copd_admission_record"
    assert result["prompt_version"] == "copd.prompt.v2"
