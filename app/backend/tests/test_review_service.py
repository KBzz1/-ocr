import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.review_service import ReviewService
from app.backend.services.task_service import TaskService
from app.backend.services._review_field_factory import (
    build_field_from_candidate,
    build_placeholder_field,
)
from app.backend.storage.json_store import JsonStore


def make_services(tmp_path):
    store = JsonStore(str(tmp_path))
    task_service = TaskService(store)
    schema = {
        "version": "medical_record.v1",
        "document_type": "medical_record",
        "field_groups": [
            {
                "group_key": "basic",
                "group_label": "基本信息",
                "fields": [
                    {"field_key": "patient_name", "label": "姓名"},
                    {"field_key": "department", "label": "科室"},
                ],
            }
        ],
    }
    review_service = ReviewService(store, task_service, schema_provider=lambda: schema)
    return review_service, task_service, store


def write_review_task(store, task_id="task_001", status="review"):
    store.write(
        f"tasks/{task_id}.json",
        {
            "task_id": task_id,
            "status": status,
            "created_at": "2026-05-19T10:00:00+00:00",
            "updated_at": "2026-05-19T10:00:00+00:00",
            "upload_token": "token_001",
            "images": [],
            "error_code": None,
            "error_message": None,
            "export_summary": {"last_exported_at": None, "formats": [], "files": []},
        },
    )


def write_candidates(store, task_id="task_001"):
    store.write(
        f"results/{task_id}/field_candidates.json",
        {
            "task_id": task_id,
            "stage": "field_extraction",
            "status": "success",
            "candidates": [
                {"field_key": "patient_name", "original_value": "张三", "evidence": "第1页", "confidence": 0.9},
                {"field_key": "department", "original_value": "骨科", "evidence": "第1页", "confidence": 0.8},
            ],
        },
    )


def find_field(review, field_key):
    return next(field for field in review["fields"] if field["field_key"] == field_key)


def test_review_fields_preserve_extraction_metadata(tmp_path):
    """Task 10: each field must carry source_section, extraction_status,
    verification_status, quality_flags, and ocr_correction from the candidate."""
    store = JsonStore(str(tmp_path))

    # Minimal task service stub — only get_task is called
    class _TaskSvc:
        def get_task(self, task_id):
            return {
                "task_id": task_id,
                "status": "review",
                "schema_version": "1.0.0",
                "document_type": "copd_admission_record",
            }

    store.write("results/t1/field_candidates.json", {
        "candidates": [
            {
                "field_key": "bmi",
                "original_value": "24.2kg/m2",
                "evidence": "BHI:24.2kg/m2",
                "confidence": 0.78,
                "source_hint": "体格检查",
                "source_text": "体格检查：身高体重后记录 BHI:24.2kg/m2。",
                "source_group_id": "source_group_体格检查",
                "source_section": "体格检查",
                "extraction_status": "extracted",
                "verification_status": "suspicious",
                "quality_flags": [{"flag": "value_not_in_evidence", "severity": "warning", "message": "risk"}],
                "ocr_correction": {"applied": True, "raw": "BHI", "normalized": "BMI", "reason": "unit kg/m2"},
            }
        ]
    })
    schema = {
        "version": "1.0.0",
        "document_type": "copd_admission_record",
        "field_groups": [
            {"fields": [{"field_key": "bmi", "label": "BMI"}]}
        ],
    }
    service = ReviewService(store, _TaskSvc(), schema_provider=lambda: schema)

    review = service.get_or_init("t1")
    field = review["fields"][0]

    assert field["extraction_status"] == "extracted"
    assert field["verification_status"] == "suspicious"
    assert field["quality_flags"][0]["flag"] == "value_not_in_evidence"
    assert field["ocr_correction"]["normalized"] == "BMI"
    assert field["source_hint"] == "体格检查"
    assert field["source_text"] == "体格检查：身高体重后记录 BHI:24.2kg/m2。"
    assert field["source_group_id"] == "source_group_体格检查"
    assert field["source_section"] == "体格检查"
    assert review["source_groups"] == [
        {
            "source_group_id": "source_group_体格检查",
            "source_hint": "体格检查",
            "source_text": "体格检查：身高体重后记录 BHI:24.2kg/m2。",
            "field_keys": ["bmi"],
        }
    ]


def test_first_read_initializes_review_result_from_candidates(tmp_path):
    review_service, _task_service, store = make_services(tmp_path)
    write_review_task(store)
    write_candidates(store)

    review = review_service.get_or_init("task_001")

    assert [field["field_key"] for field in review["fields"]] == ["patient_name", "department"]
    assert find_field(review, "patient_name")["status"] == "unreviewed"
    assert review["summary"]["unreviewed_count"] == 2
    assert review["summary"]["suspicious_count"] == 0
    assert review["summary"]["failed_verification_count"] == 0
    assert review["summary"]["not_found_count"] == 0


def test_review_save_rejects_legacy_field_status(tmp_path):
    review_service, _task_service, store = make_services(tmp_path)
    write_review_task(store)
    write_candidates(store)

    with pytest.raises(AppError) as exc:
        review_service.update_field(
            "task_001",
            "patient_name",
            {"value": "张三", "status": "suspicious"},
        )

    assert exc.value.code == ErrorCode.REVIEW_VALIDATION_FAILED.code


def test_update_field_accepts_mvp_status_payload(tmp_path):
    review_service, _task_service, store = make_services(tmp_path)
    write_review_task(store)
    write_candidates(store)

    review = review_service.update_field(
        "task_001",
        "patient_name",
        {"value": "李四", "status": "modified"},
    )

    field = find_field(review, "patient_name")
    assert field["final_value"] == "李四"
    assert field["status"] == "modified"
    assert review["summary"]["modified_count"] == 1


def test_save_bulk_fields_updates_review_result(tmp_path):
    review_service, _task_service, store = make_services(tmp_path)
    write_review_task(store)
    write_candidates(store)

    review = review_service.save(
        "task_001",
        {
            "fields": [
                {"field_key": "patient_name", "value": "张三", "status": "confirmed"},
                {"field_key": "department", "value": "骨外科", "status": "modified"},
            ]
        },
    )

    assert find_field(review, "patient_name")["status"] == "confirmed"
    assert find_field(review, "department")["final_value"] == "骨外科"
    assert review["summary"]["confirmed_count"] == 1
    assert review["summary"]["modified_count"] == 1


def test_confirm_review_marks_task_done(tmp_path):
    review_service, task_service, store = make_services(tmp_path)
    write_review_task(store)
    write_candidates(store)
    review_service.save(
        "task_001",
        {
            "fields": [
                {"field_key": "patient_name", "value": "张三", "status": "confirmed"},
                {"field_key": "department", "value": "骨科", "status": "confirmed"},
            ]
        },
    )

    task = review_service.confirm("task_001")

    assert task["status"] == "done"
    assert task["done_at"]
    assert task_service.get_task("task_001")["review_summary"]["confirmed_count"] == 2


def test_get_or_init_hydrates_missing_schema_fields(tmp_path):
    """BE-MVP-05-06: review_result.json 缺 schema 字段时,get_or_init 补齐占位并写回。"""
    review_service, _task_service, store = make_services(tmp_path)
    write_review_task(store)
    # candidates 只有 patient_name,schema 多了 department
    store.write(
        "results/task_001/field_candidates.json",
        {
            "task_id": "task_001",
            "stage": "field_extraction",
            "status": "success",
            "candidates": [
                {"field_key": "patient_name", "original_value": "张三", "evidence": "第1页", "confidence": 0.9},
            ],
        },
    )

    review = review_service.get_or_init("task_001")
    field_keys = [f["field_key"] for f in review["fields"]]

    # schema 有 patient_name + department,两者都要在 review 里
    assert field_keys == ["patient_name", "department"]
    assert review["summary"]["total_count"] == 2
    # department 是占位字段
    department = find_field(review, "department")
    assert department["final_value"] == ""
    assert department["status"] == "unreviewed"
    assert department["extraction_status"] == "not_found"
    assert department["empty_accepted"] is False
    assert department["reviewed_at"] is None
    # 写回 store,后续 get_or_init 不会重复补齐
    persisted = store.read("results/task_001/review_result.json")
    assert {f["field_key"] for f in persisted["fields"]} == {"patient_name", "department"}


def test_get_or_init_reorders_fields_to_schema_order(tmp_path):
    """BE-MVP-05-06: review 已有字段按 schema 顺序重排,确保导出顺序与 schema 一致。"""
    review_service, _task_service, store = make_services(tmp_path)
    write_review_task(store)
    # review_result.json 已有 patient_name 和 department,但顺序与 schema 不同
    store.write(
        "results/task_001/review_result.json",
        {
            "task_id": "task_001",
            "schema_version": "medical_record.v1",
            "document_type": "medical_record",
            "initialized_at": "2026-05-19T10:00:00+00:00",
            "updated_at": "2026-05-19T10:00:00+00:00",
            "fields": [
                {"field_key": "department", "field_name": "科室", "auto_value": "骨科",
                 "final_value": "骨科", "status": "unreviewed", "empty_accepted": False,
                 "extraction_status": "extracted", "verification_status": "not_checked",
                 "quality_flags": [], "ocr_correction": None, "history": []},
                {"field_key": "patient_name", "field_name": "姓名", "auto_value": "张三",
                 "final_value": "张三", "status": "unreviewed", "empty_accepted": False,
                 "extraction_status": "extracted", "verification_status": "not_checked",
                 "quality_flags": [], "ocr_correction": None, "history": []},
            ],
        },
    )

    review = review_service.get_or_init("task_001")
    field_keys = [f["field_key"] for f in review["fields"]]

    # schema 顺序是 patient_name → department
    assert field_keys == ["patient_name", "department"]
    # 值保留
    assert find_field(review, "department")["final_value"] == "骨科"
    assert find_field(review, "patient_name")["final_value"] == "张三"


# --- Task 6: 审核返回证据数组与核验提示 ---


def test_review_field_preserves_evidence_array_and_attention_message():
    """Task 6: candidate 携带 evidence 数组 + attention_required/attention_message 时,
    review 字段保留 evidence 数组(不扁平化为字符串),并把 attention 元数据透传给前端。
    """
    candidate = {
        "field_key": "chief_complaint",
        "original_value": "咳嗽 5 天",
        "evidence": [
            {
                "id": "u001",
                "text": "主诉：反复咳嗽 5 天。",
                "start_offset": 0,
                "end_offset": 11,
                "page_no": 1,
            }
        ],
        "extraction_status": "extracted",
        "verification_status": "suspicious",
        "attention_required": True,
        "attention_message": "缺少来源证据，请核对原文",
        "quality_flags": ["evidence_missing"],
    }

    field = build_field_from_candidate(
        "chief_complaint",
        "主诉",
        candidate,
    )

    # evidence 必须是 list[dict],不能扁平化为字符串
    assert isinstance(field["evidence"], list)
    assert field["evidence"] == [
        {
            "id": "u001",
            "text": "主诉：反复咳嗽 5 天。",
            "start_offset": 0,
            "end_offset": 11,
            "page_no": 1,
        }
    ]
    # 核验提示必须透传,前端可见 attention_message 必须是中文可读文案
    assert field["attention_required"] is True
    assert field["attention_message"] == "缺少来源证据，请核对原文"
    # 内部 quality_flags 仅留作审计
    assert field["quality_flags"] == ["evidence_missing"]


def test_not_found_review_field_is_not_attention():
    """Task 6: not_found 候选 review 字段 attention_required=False,final_value/auto_value 空,
    extraction_status=not_found。前端看到 not_found 字段不应该亮黄色感叹号。
    """
    placeholder = build_placeholder_field("pe_temperature", "体温")

    # 占位字段本身就是 not_found 默认形态
    assert placeholder["attention_required"] is False
    assert placeholder["final_value"] == ""
    assert placeholder["auto_value"] == ""
    assert placeholder["extraction_status"] == "not_found"

    # 显式 not_found 的候选也必须满足同样约束
    not_found_candidate = {
        "field_key": "pe_temperature",
        "original_value": "",
        "evidence": [],
        "extraction_status": "not_found",
        "verification_status": "not_checked",
        "attention_required": False,
        "attention_message": "",
        "quality_flags": [],
    }

    field = build_field_from_candidate(
        "pe_temperature",
        "体温",
        not_found_candidate,
    )

    assert field["attention_required"] is False
    assert field["final_value"] == ""
    assert field["auto_value"] == ""
    assert field["extraction_status"] == "not_found"
    assert field["attention_message"] == ""
