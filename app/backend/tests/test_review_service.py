import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.review_service import ReviewService
from app.backend.services.task_service import TaskService
from app.backend.services._review_field_factory import (
    build_field_from_candidate,
    build_placeholder_field,
)
from app.backend.storage.json_store import JsonStore


_MVP_SCHEMA = {
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


def make_services(tmp_path):
    store = JsonStore(str(tmp_path))
    task_service = TaskService(store)
    review_service = ReviewService(store, task_service, schema_provider=lambda: _MVP_SCHEMA)
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


def test_get_or_init_updates_task_review_summary_from_review_fields(tmp_path):
    review_service, _task_service, store = make_services(tmp_path)
    write_review_task(store)
    write_candidates(store)

    review = review_service.get_or_init("task_001")

    task = store.read("tasks/task_001.json")
    assert task["review_summary"] == review["summary"]
    assert task["review_summary"]["total_count"] == 2
    assert task["review_summary"]["not_found_count"] == 0
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


def test_get_or_init_splits_legacy_composite_review_fields(tmp_path):
    store = JsonStore(str(tmp_path))

    class _TaskSvc:
        def get_task(self, task_id):
            return {"task_id": task_id, "status": "review", "schema_version": "qwen_batch_admission_record.v2"}

        def update_review_summary(self, task_id, summary):
            pass

    schema = {
        "version": "qwen_batch_admission_record.v2",
        "document_type": "qwen_batch_admission_record",
        "field_groups": [
            {
                "group_key": "physical_exam",
                "group_label": "体格检查",
                "fields": [
                    {"field_key": "pe_temperature", "label": "体温"},
                    {"field_key": "pe_pulse", "label": "脉搏"},
                    {"field_key": "pe_heart_rate", "label": "心率"},
                    {"field_key": "pe_respiration_rate", "label": "生命体征呼吸"},
                    {"field_key": "pe_blood_pressure", "label": "血压"},
                    {"field_key": "pe_height", "label": "身高"},
                    {"field_key": "pe_weight", "label": "体重"},
                    {"field_key": "pe_bmi", "label": "BMI"},
                    {"field_key": "pe_heart_rhythm", "label": "心律", "qwen_type": "J", "review_control": "judgement"},
                ],
            },
            {
                "group_key": "auxiliary_exam",
                "group_label": "辅助检查",
                "fields": [
                    {"field_key": "aux_blood_gas_ph", "label": "血气pH"},
                    {"field_key": "aux_blood_gas_pco2", "label": "血气pCO2"},
                    {"field_key": "aux_blood_gas_po2", "label": "血气pO2"},
                    {"field_key": "aux_blood_gas_na", "label": "血气Na+"},
                    {"field_key": "aux_blood_gas_fio2", "label": "血气FIO2"},
                    {"field_key": "aux_blood_gas_oxygenation_index", "label": "血气氧合指数"},
                    {"field_key": "aux_blood_routine_wbc", "label": "白细胞(WBC)"},
                    {"field_key": "aux_blood_routine_mxd_percent", "label": "单核细胞百分率(MXD%)"},
                    {"field_key": "aux_blood_routine_mod_absolute", "label": "单核细胞绝对值(MOD#)"},
                ],
            },
        ],
    }
    vital_signs = "体温:36.7℃脉搏:99次/分呼吸:21次/分血压:142/87mmHg"
    heart_rhythm = "心率99次/分，心律规则，心音正常，心脏各瓣膜未闻及病理性杂音，无心包摩擦音。"
    height_weight_bmi = "身高:175cm体重:74kgBMI:24.2kg/m²"
    blood_gas = "pH7.40↓、pCO235.00mmHg、PO276.00mmHg↓、Na+130.00mmol/L↓、FiO221.00、氧合指数:361%。"
    blood_routine = "白细胞(WBC)6.68*10^9/L、单核细胞百分率(MXD%)13.9%、单核细胞绝对值(MOD#)0.92*10^9/L。"
    store.write(
        "results/task_001/review_result.json",
        {
            "task_id": "task_001",
            "schema_version": "qwen_batch_admission_record.v2",
            "document_type": "qwen_batch_admission_record",
            "fields": [
                {"field_key": "pe_vital_signs", "field_name": "生命体征", "auto_value": vital_signs, "final_value": vital_signs, "status": "unreviewed"},
                {"field_key": "pe_heart_rhythm", "field_name": "心律", "auto_value": heart_rhythm, "final_value": heart_rhythm, "status": "unreviewed"},
                {"field_key": "pe_height_weight_bmi", "field_name": "身高体重BMI", "auto_value": height_weight_bmi, "final_value": height_weight_bmi, "status": "unreviewed"},
                {"field_key": "pe_weight", "field_name": "体重", "auto_value": "74kg", "final_value": "74kg", "status": "unreviewed"},
                {"field_key": "aux_blood_gas", "field_name": "血气", "auto_value": blood_gas, "final_value": blood_gas, "status": "unreviewed"},
                {"field_key": "aux_blood_gas_pco2", "field_name": "血气pCO2", "auto_value": "35.00mmHg", "final_value": "35.00mmHg", "status": "unreviewed"},
                {"field_key": "aux_blood_routine", "field_name": "血常规", "auto_value": blood_routine, "final_value": blood_routine, "status": "unreviewed"},
            ],
            "summary": {},
        },
    )
    service = ReviewService(store, _TaskSvc(), schema_provider=lambda: schema)

    review = service.get_or_init("task_001")

    field_keys = [field["field_key"] for field in review["fields"]]
    assert "pe_vital_signs" not in field_keys
    assert find_field(review, "pe_temperature")["final_value"] == "36.7"
    assert find_field(review, "pe_pulse")["final_value"] == "99"
    assert find_field(review, "pe_heart_rate")["final_value"] == "99"
    assert find_field(review, "pe_respiration_rate")["final_value"] == "21"
    assert find_field(review, "pe_blood_pressure")["final_value"] == "142/87"
    assert find_field(review, "pe_height")["final_value"] == "175"
    assert find_field(review, "pe_weight")["final_value"] == "74"
    assert find_field(review, "pe_bmi")["final_value"] == "24.2"
    assert find_field(review, "pe_heart_rhythm")["final_value"] == "正常"
    assert find_field(review, "aux_blood_gas_ph")["final_value"] == "7.40"
    assert find_field(review, "aux_blood_gas_pco2")["final_value"] == "35.00"
    assert find_field(review, "aux_blood_gas_po2")["final_value"] == "76.00"
    assert find_field(review, "aux_blood_gas_na")["final_value"] == "130.00"
    assert find_field(review, "aux_blood_gas_fio2")["final_value"] == "21.00"
    assert find_field(review, "aux_blood_gas_oxygenation_index")["final_value"] == "361"
    assert find_field(review, "aux_blood_routine_wbc")["final_value"] == "6.68"
    assert find_field(review, "aux_blood_routine_mxd_percent")["final_value"] == "13.9"
    assert find_field(review, "aux_blood_routine_mod_absolute")["final_value"] == "0.92"
    assert store.read("results/task_001/review_result.json")["summary"]["total_count"] == 18


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


def test_existing_review_with_old_schema_version_is_not_rehydrated_by_current_schema(tmp_path):
    review_service, _task_service, store = make_services(tmp_path)
    write_review_task(store)
    store.write(
        "results/task_001/review_result.json",
        {
            "task_id": "task_001",
            "schema_version": "old_schema.v1",
            "document_type": "medical_record",
            "initialized_at": "2026-05-19T10:00:00+00:00",
            "updated_at": "2026-05-19T10:00:00+00:00",
            "field_groups": [
                {
                    "group_key": "old",
                    "group_label": "旧字段",
                    "fields": [{"field_key": "legacy_only", "label": "旧字段"}],
                }
            ],
            "fields": [
                {
                    "field_key": "legacy_only",
                    "field_name": "旧字段",
                    "auto_value": "旧值",
                    "final_value": "旧值",
                    "status": "unreviewed",
                    "empty_accepted": False,
                    "extraction_status": "extracted",
                    "verification_status": "not_checked",
                    "quality_flags": [],
                    "ocr_correction": None,
                    "history": [],
                }
            ],
            "summary": {"total_count": 1},
        },
    )

    review = review_service.get_or_init("task_001")

    assert [field["field_key"] for field in review["fields"]] == ["legacy_only"]
    assert review["field_groups"][0]["group_key"] == "old"
    persisted = store.read("results/task_001/review_result.json")
    assert [field["field_key"] for field in persisted["fields"]] == ["legacy_only"]


def test_old_candidate_wrapper_with_schema_snapshot_initializes_without_current_schema(tmp_path):
    review_service, _task_service, store = make_services(tmp_path)
    write_review_task(store)
    store.write(
        "results/task_001/field_candidates.json",
        {
            "task_id": "task_001",
            "stage": "field_extraction",
            "status": "success",
            "schema_version": "old_schema.v1",
            "document_type": "medical_record",
            "field_groups": [
                {
                    "group_key": "old",
                    "group_label": "旧字段",
                    "fields": [{"field_key": "legacy_only", "label": "旧字段"}],
                }
            ],
            "candidates": [
                {
                    "field_key": "legacy_only",
                    "original_value": "旧值",
                    "evidence": "第1页",
                    "confidence": 0.9,
                }
            ],
        },
    )

    review = review_service.get_or_init("task_001")

    assert review["schema_version"] == "old_schema.v1"
    assert [field["field_key"] for field in review["fields"]] == ["legacy_only"]
    assert review["field_groups"][0]["group_key"] == "old"


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


# --- judgement 规则一致性 & 误判防护 ---


def test_judgement_rules_matches_normal_indicators():
    from app.backend.services.copd_extraction.judgement_rules import matches_normal_judgement

    # 两处应一致识别的正常/阴性表述
    for text in (
        "正常",
        "无异常",
        "未见异常",
        "无压痛",
        "无肿大",
        "无充血",
        "无水肿",
        "无黄染",
        "无分泌物",
        "未闻及病理性杂音",
        "未触及包块",
        "未扪及包块",
        "未触及明显",
        "未扪及肿大",
        "心律规则",
        "心音正常",
        "未闻及杂音",
        "阴性",
    ):
        assert matches_normal_judgement(text), f"应识别为正常: {text!r}"


def test_judgement_rules_matches_normal_in_compound_text():
    from app.backend.services.copd_extraction.judgement_rules import matches_normal_judgement

    # 复合文本中含有正常/阴性指示词时应命中
    assert matches_normal_judgement("腹部平坦，无压痛，无肿大")
    assert matches_normal_judgement("心律规则，心音正常，未闻及杂音")
    assert matches_normal_judgement("外耳道无异常分泌物，双侧乳突区无压痛")


def test_judgement_rules_rejects_false_positive_normal_substring():
    from app.backend.services.copd_extraction.judgement_rules import matches_normal_judgement

    # "正常" 作为其他词语的子串不应误判（如 "肺动脉压正常范围上限"）
    assert not matches_normal_judgement("肺动脉压正常范围上限"), (
        "\"正常\" 内嵌在复合词中不应被误判为正常结论"
    )
    assert not matches_normal_judgement("甲状腺功能异常进一步检查"), (
        "\"异常\" 不应触发误判（当前仅匹配正常模式，此断言确保\"异常\"不命中）"
    )
    # 不相关的临床描述不应命中
    assert not matches_normal_judgement("患者既往有血小板减少病史")


def test_judgement_rules_handles_edge_cases():
    from app.backend.services.copd_extraction.judgement_rules import matches_normal_judgement

    assert not matches_normal_judgement("")
    assert not matches_normal_judgement("   ")
    assert matches_normal_judgement(" 正常 ")  # 带空白
    assert matches_normal_judgement("正常。")  # 带标点
    assert matches_normal_judgement("，正常，")  # 中文标点包围


def test_review_service_infer_judgement_uses_shared_rules():
    """确保 ReviewService._infer_judgement_value 使用共享规则且不误判。"""
    from app.backend.services.review_service import ReviewService

    # 正常表述
    assert ReviewService._infer_judgement_value("无压痛") == "正常"
    assert ReviewService._infer_judgement_value("未闻及杂音") == "正常"
    assert ReviewService._infer_judgement_value("心律规则") == "正常"
    assert ReviewService._infer_judgement_value("阴性") == "正常"
    # 不应误判
    assert ReviewService._infer_judgement_value("肺动脉压正常范围上限") is None
    assert ReviewService._infer_judgement_value("血小板减少病史") is None
    # 空/空白
    assert ReviewService._infer_judgement_value("") is None
    assert ReviewService._infer_judgement_value("   ") is None


def test_existing_review_result_gets_quality_warning_on_read(tmp_path):
    store = JsonStore(str(tmp_path))

    class _TaskSvc:
        def get_task(self, task_id):
            return {
                "task_id": task_id,
                "status": "review",
                "schema_version": "admission_record_structured_fields.v1",
                "document_type": "copd_admission_record",
            }

        def update_review_summary(self, task_id, summary):
            store.write(f"tasks/{task_id}.json", {"task_id": task_id, "status": "review", "review_summary": summary})

    schema = {
        "version": "admission_record_structured_fields.v1",
        "document_type": "copd_admission_record",
        "field_groups": [
            {
                "group_key": "physical_examination",
                "group_label": "体格检查",
                "fields": [
                    {"field_key": "pe_pulse", "label": "脉搏"},
                ],
            }
        ],
    }
    store.write("results/t1/document_result.json", {
        "merged_text": "体温36.6℃，脉搏36次/分，呼吸20次/分。心率99次/分，心律规则。",
        "pages": [],
    })
    store.write("results/t1/review_result.json", {
        "task_id": "t1",
        "fields": [
            {
                "field_key": "pe_pulse",
                "field_name": "脉搏",
                "auto_value": "36次/分",
                "final_value": "36次/分",
                "evidence": [
                    {
                        "id": "u_vitals",
                        "text": "体温36.6℃，脉搏36次/分，呼吸20次/分",
                        "start_offset": 0,
                        "end_offset": 23,
                        "page_no": 1,
                    }
                ],
                "extraction_status": "extracted",
                "verification_status": "not_checked",
                "attention_required": False,
                "attention_message": "",
                "quality_flags": [],
                "status": "unreviewed",
            }
        ],
        "summary": {},
    })

    service = ReviewService(store, _TaskSvc(), schema_provider=lambda: schema)

    review = service.get_or_init("t1")

    field = find_field(review, "pe_pulse")
    assert field["verification_status"] == "suspicious"
    assert any(flag["flag"] == "ocr_numeric_conflict" for flag in field["quality_flags"])
    assert review["summary"]["suspicious_count"] == 1


# --- Task 6 (评估体系第二步): 审核数据回流聚合 ---


def test_confirm_collects_modified_fields_feedback(tmp_path):
    """Task 6: confirm 聚合 auto_value != final_value 的修正字段写入回流文件。

    - feedback["fields"] 只含 auto_value != final_value 的字段
    - 每项 {field_key, status, original_value, corrected_value}
    - 修正值非空 → status=found；修正值为空串 → status=not_found
    """
    review_service, task_service, store = make_services(tmp_path)
    write_review_task(store)
    write_candidates(store)
    review_service.save(
        "task_001",
        {
            "fields": [
                # auto_value=张三(候选 original_value) → final_value=张四
                {"field_key": "patient_name", "value": "张四", "status": "modified"},
                # auto_value=骨科 → final_value 清空(医生确认找不到)
                {"field_key": "department", "value": "", "status": "modified"},
            ]
        },
    )

    review_service.confirm("task_001")

    feedback = store.read("evaluation/review_feedback/task_001.json")
    assert feedback["task_id"] == "task_001"
    assert feedback["schema_version"] == "medical_record.v1"
    assert feedback["created_at"]
    assert [f["field_key"] for f in feedback["fields"]] == ["patient_name", "department"]
    assert feedback["fields"][0] == {
        "field_key": "patient_name",
        "status": "found",
        "original_value": "张三",
        "corrected_value": "张四",
    }
    assert feedback["fields"][1] == {
        "field_key": "department",
        "status": "not_found",
        "original_value": "骨科",
        "corrected_value": "",
    }


def test_confirm_feedback_write_failure_degrades_gracefully(tmp_path):
    """Task 6: 回流文件写失败(如磁盘异常)不阻断审核确认，confirm 正常完成。"""
    class _FeedbackFailingStore(JsonStore):
        def write(self, relative_path, data):
            if "review_feedback" in relative_path:
                raise OSError("模拟磁盘写入失败")
            return super().write(relative_path, data)

    store = _FeedbackFailingStore(str(tmp_path))
    task_service = TaskService(store)
    review_service = ReviewService(store, task_service, schema_provider=lambda: _MVP_SCHEMA)
    write_review_task(store)
    write_candidates(store)
    review_service.save(
        "task_001",
        {
            "fields": [
                {"field_key": "patient_name", "value": "张四", "status": "modified"},
                # department 确认不改值,避免未审核字段阻断 confirm
                {"field_key": "department", "value": "骨科", "status": "confirmed"},
            ]
        },
    )

    task = review_service.confirm("task_001")

    assert task["status"] == "done"
    assert store.exists("evaluation/review_feedback/task_001.json") is False
