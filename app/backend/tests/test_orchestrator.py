from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator
from app.backend.storage.json_store import JsonStore


def _admission_schema():
    from app.backend.services.schema_loader import load_schema

    return load_schema("app/config/schemas/admission_record_structured_fields.v1.yaml")


def _build_full_qwen_candidates_with_statuses(statuses: dict[str, str]):
    """Construct a full-schema 61-field review-candidate list with per-field status."""
    schema = _admission_schema()
    by_key_status = dict(statuses)
    candidates = []
    for group in schema["field_groups"]:
        for field in group["fields"]:
            fk = field["field_key"]
            status = by_key_status.get(fk, "not_found")
            if status == "found":
                extraction_status = "extracted"
                value = "found_value"
                evidence_ids = ["u001"]
                evidence = [{
                    "id": "u001",
                    "text": "found_value text",
                    "start_offset": 0,
                    "end_offset": 15,
                }]
                verification_status = "passed"
            else:
                extraction_status = "not_found"
                value = ""
                evidence_ids = []
                evidence = []
                verification_status = "not_checked"
            candidates.append({
                "field_key": fk,
                "field_label": field["label"],
                "section_key": group["group_key"],
                "section_label": group["group_label"],
                "status": status,
                "value": value,
                "evidence_ids": evidence_ids,
                "original_value": value,
                "extraction_status": extraction_status,
                "verification_status": verification_status,
                "evidence": evidence,
                "attention_required": False,
                "attention_message": "",
                "quality_flags": [],
                "source_section": None,
                "source_hint": None,
                "source_text": None,
                "source_group_id": None,
                "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
            })
    return candidates


def test_build_image_inputs_uses_task_images_and_omits_quad(tmp_path):
    orchestrator = ProcessingOrchestrator(store=JsonStore(str(tmp_path)))
    task = {
        "task_id": "task_001",
        "images": [
            {
                "page_id": "page_001",
                "page_no": 1,
                "original_image_path": "/data/task_001/page_001.png",
                "image_width": 120,
                "image_height": 80,
            }
        ],
    }

    inputs = orchestrator._build_image_inputs(task)

    assert inputs == [
        {
            "task_id": "task_001",
            "page_id": "page_001",
            "page_no": 1,
            "original_path": "/data/task_001/page_001.png",
            "image_width": 120,
            "image_height": 80,
        }
    ]


def test_build_image_inputs_returns_none_when_task_has_no_images(tmp_path):
    orchestrator = ProcessingOrchestrator(store=JsonStore(str(tmp_path)))

    assert orchestrator._build_image_inputs({"task_id": "task_001", "images": []}) is None


def test_build_image_inputs_sorts_by_page_no(tmp_path):
    orchestrator = ProcessingOrchestrator(store=JsonStore(str(tmp_path)))
    task = {
        "task_id": "task_001",
        "images": [
            {
                "page_id": "page_002",
                "page_no": 2,
                "original_image_path": "/data/task_001/page_002.png",
                "image_width": 120,
                "image_height": 80,
            },
            {
                "page_id": "page_001",
                "page_no": 1,
                "original_image_path": "/data/task_001/page_001.png",
                "image_width": 120,
                "image_height": 80,
            },
        ],
    }

    inputs = orchestrator._build_image_inputs(task)

    assert [item["page_id"] for item in inputs] == ["page_001", "page_002"]


def test_build_image_inputs_returns_none_when_image_path_missing(tmp_path):
    orchestrator = ProcessingOrchestrator(store=JsonStore(str(tmp_path)))
    task = {
        "task_id": "task_001",
        "images": [{"page_id": "page_001", "page_no": 1}],
    }

    assert orchestrator._build_image_inputs(task) is None


def test_orchestrator_detects_all_empty_field_results(tmp_path):
    from app.backend.services.algorithm_ports.field_extraction import all_fields_empty

    assert all_fields_empty([
        {"field_key": "bmi", "original_value": "", "extraction_status": "not_found"},
        {"field_key": "crp", "original_value": "", "extraction_status": "not_found"},
    ])
    assert not all_fields_empty([
        {"field_key": "bmi", "original_value": "24.2", "extraction_status": "extracted"},
        {"field_key": "crp", "original_value": "", "extraction_status": "not_found"},
    ])


def test_orchestrator_reuses_successful_document_result_on_retry(tmp_path):
    source = tmp_path / "page.jpg"
    source.write_text("image", encoding="utf-8")
    store = JsonStore(str(tmp_path))
    store.write(
        "results/task_001/document_result.json",
        {
            "task_id": "task_001",
            "stage": "document_parsing",
            "status": "success",
            "pages": [{"page_id": "page_001", "page_no": 1, "status": "success", "text": "主诉：咳嗽"}],
            "merged_text": "主诉：咳嗽",
        },
    )

    class ImagePort:
        def process(self, input):
            return {"processed_path": input["original_path"]}

    class DocPort:
        called = False

        def parse(self, input):
            self.called = True
            raise AssertionError("document parser should not run")

    class FieldPort:
        def __init__(self):
            self.seen_text = None

        def extract(self, input):
            self.seen_text = input["document_result"]["merged_text"]
            return [_valid_candidate()]

    class TaskService:
        def mark_processing_stage(self, task_id, stage, status, page_count=None):
            return {}

        def mark_ready(self, task_id):
            return {"task_id": task_id, "status": "review"}

        def mark_failed(self, *args, **kwargs):
            raise AssertionError("should not fail")

        def is_processing_cancelled(self, task_id):
            return False

    doc_port = DocPort()
    field_port = FieldPort()
    orchestrator = ProcessingOrchestrator(
        store=store,
        image_port=ImagePort(),
        doc_port=doc_port,
        field_port=field_port,
    )

    result = orchestrator.run(
        {
            "task_id": "task_001",
            "images": [{"page_id": "page_001", "page_no": 1, "original_image_path": str(source)}],
        },
        TaskService(),
        schema={"fields": [{"field_key": "chief_complaint"}]},
    )

    assert result["status"] == "review"
    assert doc_port.called is False
    assert field_port.seen_text == "主诉：咳嗽"


def test_orchestrator_reuses_partial_document_result_with_success_text_on_retry(tmp_path):
    source = tmp_path / "page.jpg"
    source.write_text("image", encoding="utf-8")
    store = JsonStore(str(tmp_path))
    store.write(
        "results/task_001/document_result.json",
        {
            "task_id": "task_001",
            "stage": "document_parsing",
            "status": "partial_failure",
            "pages": [
                {"page_id": "page_001", "page_no": 1, "status": "failed", "text": ""},
                {"page_id": "page_002", "page_no": 2, "status": "success", "text": "主诉：咳嗽"},
            ],
            "merged_text": "主诉：咳嗽",
        },
    )

    class ImagePort:
        def process(self, input):
            return {"processed_path": input["original_path"]}

    class DocPort:
        called = False

        def parse(self, input):
            self.called = True
            raise AssertionError("document parser should not rerun for reusable partial OCR")

    class FieldPort:
        def __init__(self):
            self.seen_text = None

        def extract(self, input):
            self.seen_text = input["document_result"]["merged_text"]
            return _build_full_qwen_candidates_with_statuses({"chief_complaint": "found"})

    class TaskService:
        def mark_processing_stage(self, task_id, stage, status, page_count=None):
            return {}

        def mark_ready(self, task_id):
            return {"task_id": task_id, "status": "review"}

        def mark_failed(self, *args, **kwargs):
            raise AssertionError("should not fail")

        def is_processing_cancelled(self, task_id):
            return False

    doc_port = DocPort()
    field_port = FieldPort()
    orchestrator = ProcessingOrchestrator(
        store=store,
        image_port=ImagePort(),
        doc_port=doc_port,
        field_port=field_port,
    )

    result = orchestrator.run(
        {
            "task_id": "task_001",
            "images": [{"page_id": "page_001", "page_no": 1, "original_image_path": str(source)}],
        },
        TaskService(),
        schema={"fields": [{"field_key": "chief_complaint"}]},
    )

    assert result["status"] == "review"
    assert doc_port.called is False
    assert field_port.seen_text == "主诉：咳嗽"


def test_orchestrator_uses_document_type_specific_field_port(tmp_path):
    class PassingImagePort:
        def process(self, input):
            return {"processed_path": input["original_path"]}

    class PassingDocPort:
        def parse(self, input):
            return {"pages": [{"page_id": "p1", "page_no": 1, "status": "success"}], "merged_text": "姓名：张三"}

    class CapturingFieldPort:
        def __init__(self):
            self.inputs = []

        def extract(self, input):
            self.inputs.append(input)
            return [{
                "field_key": "patient_name",
                "original_value": "张三",
                "extraction_status": "extracted",
                "verification_status": "not_checked",
                "quality_flags": [],
                "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
            }]

    class TaskService:
        def mark_processing_stage(self, task_id, stage, status, page_count=None):
            return {}

        def mark_ready(self, task_id):
            return {"task_id": task_id, "status": "review"}

        def mark_failed(self, *args, **kwargs):
            raise AssertionError("should not fail")

        def is_processing_cancelled(self, task_id):
            return False

        def get_task(self, task_id):
            return {"task_id": task_id, "status": "processing"}

    field_port = CapturingFieldPort()
    source = tmp_path / "page.jpg"
    source.write_text("image", encoding="utf-8")
    orchestrator = ProcessingOrchestrator(
        store=JsonStore(str(tmp_path)),
        image_port=PassingImagePort(),
        doc_port=PassingDocPort(),
        field_port_registry={"copd_admission_record": field_port},
    )

    orchestrator.run(
        {
            "task_id": "task_001",
            "document_type": "copd_admission_record",
            "images": [{"page_id": "p1", "page_no": 1, "original_image_path": str(source)}],
        },
        TaskService(),
        schema={"version": "copd.v1", "document_type": "copd_admission_record"},
    )

    assert field_port.inputs[0]["document_type"] == "copd_admission_record"


def _valid_candidate():
    return {
        "field_key": "chief_complaint",
        "original_value": "咳嗽",
        "evidence": "主诉：咳嗽",
        "confidence": 0.8,
        "extraction_status": "extracted",
        "verification_status": "not_checked",
        "quality_flags": [],
        "source_section": "主诉",
        "source_hint": "主诉",
        "source_text": "主诉：咳嗽",
        "source_group_id": "主诉",
        "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
    }


class RecordingGpuQueue:
    def __init__(self):
        self.stages = []

    def stage(self, task_id, stage):
        self.stages.append((task_id, stage))
        class _Context:
            def __enter__(_self):
                return None
            def __exit__(_self, exc_type, exc, tb):
                return False
        return _Context()


def test_orchestrator_passes_evidence_units_to_field_port_and_persists_them(tmp_path):
    from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator
    from app.backend.storage.json_store import JsonStore

    class ImagePort:
        def process(self, input):
            return {"processed_path": input["original_path"]}

    class DocPort:
        def parse(self, input):
            return {
                "pages": [
                    {
                        "page_id": "p1",
                        "page_no": 1,
                        "status": "success",
                        "text": "主诉：反复咳嗽、咳痰15年。",
                    }
                ],
                "merged_text": "主诉：反复咳嗽、咳痰15年。",
            }

    class CapturingFieldPort:
        def __init__(self):
            self.inputs = []

        def extract(self, input):
            self.inputs.append(input)
            return [{
                "field_key": "chief_complaint",
                "original_value": "反复咳嗽、咳痰15年",
                "evidence": "主诉：反复咳嗽、咳痰15年。",
                "confidence": 0.8,
                "extraction_status": "extracted",
                "verification_status": "not_checked",
                "quality_flags": [],
                "source_section": "主诉",
                "source_hint": "主诉",
                "source_text": "主诉：反复咳嗽、咳痰15年。",
                "source_group_id": "主诉",
                "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
            }]

    class TaskService:
        def mark_processing_stage(self, task_id, stage, status, page_count=None):
            return {}

        def mark_ready(self, task_id):
            return {"task_id": task_id, "status": "review"}

        def mark_failed(self, *args, **kwargs):
            raise AssertionError("should not fail")

        def is_processing_cancelled(self, task_id):
            return False

        def get_task(self, task_id):
            return {"task_id": task_id, "status": "processing"}

    store = JsonStore(str(tmp_path))
    field_port = CapturingFieldPort()
    (tmp_path / "p1.jpg").write_bytes(b"img")
    orchestrator = ProcessingOrchestrator(
        store=store,
        image_port=ImagePort(),
        doc_port=DocPort(),
        field_port=field_port,
    )

    orchestrator.run(
        {
            "task_id": "task_001",
            "images": [{"page_id": "p1", "page_no": 1, "original_image_path": str(tmp_path / "p1.jpg")}],
        },
        TaskService(),
        schema={"fields": [{"field_key": "chief_complaint"}]},
    )

    # evidence_units passed into the field port
    assert field_port.inputs, "field port must be called"
    evidence_units = field_port.inputs[0].get("evidence_units")
    assert isinstance(evidence_units, list) and evidence_units, (
        "field port input must carry a non-empty evidence_units list"
    )
    unit = evidence_units[0]
    assert "id" in unit and "text" in unit and "start_offset" in unit and "end_offset" in unit

    # evidence_units persisted to document_result.json
    persisted = store.read("results/task_001/document_result.json")
    assert isinstance(persisted, dict)
    assert "evidence_units" in persisted, "document_result.json must persist evidence_units"
    persisted_units = persisted["evidence_units"]
    assert isinstance(persisted_units, list) and persisted_units
    # same IDs must round-trip between the port input and the persisted store
    assert {u["id"] for u in persisted_units} == {u["id"] for u in evidence_units}


def test_orchestrator_continues_field_extraction_when_some_ocr_pages_failed(tmp_path):
    """部分 OCR 页为空时保留 failed 页记录，但只要有成功页就继续进入审核。"""
    class ImagePort:
        def process(self, input):
            return {"processed_path": input["original_path"]}

    class DocPort:
        def parse(self, input):
            return {
                "pages": [
                    {"page_id": "p1", "page_no": 1, "status": "failed", "text": ""},
                    {"page_id": "p2", "page_no": 2, "status": "success", "text": "主诉：咳嗽"},
                ],
                "merged_text": "主诉：咳嗽",
            }

    class FieldPort:
        def __init__(self):
            self.inputs = []

        def extract(self, input):
            self.inputs.append(input)
            return _build_full_qwen_candidates_with_statuses({"chief_complaint": "found"})

    class TaskService:
        def mark_processing_stage(self, task_id, stage, status, page_count=None):
            return {}

        def mark_ready(self, task_id):
            return {"task_id": task_id, "status": "review"}

        def mark_failed(self, *args, **kwargs):
            raise AssertionError("partial OCR page failures should not fail the task")

        def is_processing_cancelled(self, task_id):
            return False

        def get_task(self, task_id):
            return {"task_id": task_id, "status": "processing"}

    source1 = tmp_path / "p1.jpg"
    source2 = tmp_path / "p2.jpg"
    source1.write_text("image1", encoding="utf-8")
    source2.write_text("image2", encoding="utf-8")
    store = JsonStore(str(tmp_path))
    field_port = FieldPort()
    orchestrator = ProcessingOrchestrator(
        store=store,
        image_port=ImagePort(),
        doc_port=DocPort(),
        field_port=field_port,
    )

    result = orchestrator.run(
        {
            "task_id": "task_001",
            "images": [
                {"page_id": "p1", "page_no": 1, "original_image_path": str(source1)},
                {"page_id": "p2", "page_no": 2, "original_image_path": str(source2)},
            ],
        },
        TaskService(),
        schema={"fields": [{"field_key": "chief_complaint"}]},
    )

    assert result["status"] == "review"
    assert field_port.inputs, "field extraction should run with the successful OCR text"
    assert field_port.inputs[0]["document_result"]["merged_text"] == "主诉：咳嗽"
    persisted = store.read("results/task_001/document_result.json")
    assert [page["status"] for page in persisted["pages"]] == ["failed", "success"]


def test_orchestrator_holds_single_gpu_stage_across_ocr_and_field_extraction(tmp_path):
    """OCR 与固定字段抽取必须连续持有同一 `qwen_ocr_and_extraction` 阶段，
    避免 8GB 显存下两个任务之间被插队。"""
    from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator
    from app.backend.storage.json_store import JsonStore

    events = []

    class RecordingContext:
        def __init__(self, stage):
            self.stage = stage

        def __enter__(self):
            events.append(f"enter:{self.stage}")
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append(f"exit:{self.stage}")
            return False

    class RecordingQueue:
        def stage(self, task_id, stage):
            return RecordingContext(stage)

    class ImagePort:
        def process(self, input):
            return {"processed_path": input["original_path"]}

    class DocPort:
        def parse(self, input):
            events.append("doc_inside_stage")
            return {
                "pages": [{"page_id": "p1", "page_no": 1, "status": "success", "text": "主诉：咳嗽"}],
                "merged_text": "主诉：咳嗽",
            }

    class FieldPort:
        def extract(self, input):
            events.append("field_inside_stage")
            return _build_full_qwen_candidates_with_statuses({"chief_complaint": "found"})

    class TaskService:
        def mark_processing_stage(self, task_id, stage, status, page_count=None):
            return {}

        def mark_ready(self, task_id):
            return {"task_id": task_id, "status": "review"}

        def mark_failed(self, *args, **kwargs):
            raise AssertionError("should not fail")

        def is_processing_cancelled(self, task_id):
            return False

        def get_task(self, task_id):
            return {"task_id": task_id, "status": "processing"}

    source = tmp_path / "page.jpg"
    source.write_text("image", encoding="utf-8")
    orchestrator = ProcessingOrchestrator(
        store=JsonStore(str(tmp_path)),
        image_port=ImagePort(),
        doc_port=DocPort(),
        field_port=FieldPort(),
        gpu_stage_queue=RecordingQueue(),
    )

    result = orchestrator.run(
        {
            "task_id": "task_001",
            "document_type": "copd_admission_record",
            "images": [{"page_id": "page_001", "page_no": 1, "original_image_path": str(source)}],
        },
        TaskService(),
        schema=_admission_schema(),
    )

    assert result["status"] == "review"
    assert events == [
        "enter:qwen_ocr_and_extraction",
        "doc_inside_stage",
        "field_inside_stage",
        "exit:qwen_ocr_and_extraction",
    ]


def test_orchestrator_with_cached_document_result_only_holds_field_stage(tmp_path):
    """已有合法 `document_result.json` 时，重试只持有 field_extraction 阶段，不再重跑 OCR。"""
    from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator
    from app.backend.storage.json_store import JsonStore

    store = JsonStore(str(tmp_path))
    store.write(
        "results/task_001/document_result.json",
        {
            "task_id": "task_001",
            "stage": "document_parsing",
            "status": "success",
            "pages": [{"page_id": "page_001", "page_no": 1, "status": "success", "text": "主诉：咳嗽"}],
            "merged_text": "主诉：咳嗽",
        },
    )

    stages_entered = []

    class RecordingContext:
        def __init__(self, stage):
            self.stage = stage

        def __enter__(self):
            stages_entered.append(self.stage)
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class RecordingQueue:
        def stage(self, task_id, stage):
            return RecordingContext(stage)

    class ImagePort:
        def process(self, input):
            return {"processed_path": input["original_path"]}

    class DocPort:
        called = False

        def parse(self, input):
            self.called = True
            raise AssertionError("document parser should not run when document_result.json is valid")

    class FieldPort:
        def extract(self, input):
            return _build_full_qwen_candidates_with_statuses({"chief_complaint": "found"})

    class TaskService:
        def mark_processing_stage(self, task_id, stage, status, page_count=None):
            return {}

        def mark_ready(self, task_id):
            return {"task_id": task_id, "status": "review"}

        def mark_failed(self, *args, **kwargs):
            raise AssertionError("should not fail")

        def is_processing_cancelled(self, task_id):
            return False

        def get_task(self, task_id):
            return {"task_id": task_id, "status": "processing"}

    doc_port = DocPort()
    source = tmp_path / "page.jpg"
    source.write_text("image", encoding="utf-8")
    orchestrator = ProcessingOrchestrator(
        store=store,
        image_port=ImagePort(),
        doc_port=doc_port,
        field_port=FieldPort(),
        gpu_stage_queue=RecordingQueue(),
    )

    result = orchestrator.run(
        {
            "task_id": "task_001",
            "document_type": "copd_admission_record",
            "images": [{"page_id": "page_001", "page_no": 1, "original_image_path": str(source)}],
        },
        TaskService(),
        schema=_admission_schema(),
    )

    assert result["status"] == "review"
    assert doc_port.called is False
    # 仅进入 field_extraction 阶段，不进入 qwen_ocr_and_extraction
    assert "field_extraction" in stages_entered
    assert "qwen_ocr_and_extraction" not in stages_entered


def test_orchestrator_allows_many_not_found_fields_when_one_field_found(tmp_path):
    """当 61 个字段中只有 1 个 found、其余 60 个 not_found 时,任务应正常进入 review。"""
    from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator

    statuses = {"chief_complaint": "found"}
    # All others default to not_found via _build_full_qwen_candidates_with_statuses

    class ImagePort:
        def process(self, input):
            return {"processed_path": input["original_path"]}

    class DocPort:
        def parse(self, input):
            return {
                "pages": [
                    {
                        "page_id": "p1",
                        "page_no": 1,
                        "status": "success",
                        "text": "主诉：反复咳嗽、咳痰15年。",
                    }
                ],
                "merged_text": "主诉：反复咳嗽、咳痰15年。",
            }

    class QwenFieldPort:
        def extract(self, input):
            return _build_full_qwen_candidates_with_statuses(statuses)

    class TaskService:
        def __init__(self):
            self.fail_args = None

        def mark_processing_stage(self, task_id, stage, status, page_count=None):
            return {}

        def mark_ready(self, task_id):
            return {"task_id": task_id, "status": "review"}

        def mark_failed(self, task_id, code, message, **kwargs):
            self.fail_args = {"task_id": task_id, "code": code, "message": message, **kwargs}
            return {"task_id": task_id, "status": "failed", "error_code": code}

        def is_processing_cancelled(self, task_id):
            return False

        def get_task(self, task_id):
            return {"task_id": task_id, "status": "processing"}

    store = JsonStore(str(tmp_path))
    field_port = QwenFieldPort()
    (tmp_path / "p1.jpg").write_bytes(b"img")
    orchestrator = ProcessingOrchestrator(
        store=store,
        image_port=ImagePort(),
        doc_port=DocPort(),
        field_port=field_port,
    )

    result = orchestrator.run(
        {
            "task_id": "task_001",
            "document_type": "copd_admission_record",
            "images": [{"page_id": "p1", "page_no": 1, "original_image_path": str(tmp_path / "p1.jpg")}],
        },
        TaskService(),
        schema=_admission_schema(),
    )

    assert result["status"] == "review", "mixed (1 found + 60 not_found) must enter review"


def test_orchestrator_rejects_all_not_found_field_results(tmp_path):
    """当所有 61 个字段都是 not_found 时,任务应进入 failed,ALGORITHM_CONTRACT_INVALID。"""
    from app.backend.errors import ErrorCode
    from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator

    statuses = {fk: "not_found" for fk in (
        "chief_complaint", "pe_temperature", "aux_blood_gas_ph", "diagnosis_preliminary"
    )}
    # All fields not_found

    class ImagePort:
        def process(self, input):
            return {"processed_path": input["original_path"]}

    class DocPort:
        def parse(self, input):
            return {
                "pages": [{"page_id": "p1", "page_no": 1, "status": "success", "text": "正文"}],
                "merged_text": "正文",
            }

    class QwenFieldPort:
        def extract(self, input):
            return _build_full_qwen_candidates_with_statuses({})  # all not_found

    class TaskService:
        def __init__(self):
            self.fail_args = None

        def mark_processing_stage(self, task_id, stage, status, page_count=None):
            return {}

        def mark_ready(self, task_id):
            raise AssertionError("must not enter review when every field is not_found")

        def mark_failed(self, task_id, code, message, **kwargs):
            self.fail_args = {"task_id": task_id, "code": code, "message": message, **kwargs}
            return {"task_id": task_id, "status": "failed", "error_code": code}

        def is_processing_cancelled(self, task_id):
            return False

        def get_task(self, task_id):
            return {"task_id": task_id, "status": "processing"}

    store = JsonStore(str(tmp_path))
    field_port = QwenFieldPort()
    (tmp_path / "p1.jpg").write_bytes(b"img")
    orchestrator = ProcessingOrchestrator(
        store=store,
        image_port=ImagePort(),
        doc_port=DocPort(),
        field_port=field_port,
    )

    task_service = TaskService()
    result = orchestrator.run(
        {
            "task_id": "task_001",
            "document_type": "copd_admission_record",
            "images": [{"page_id": "p1", "page_no": 1, "original_image_path": str(tmp_path / "p1.jpg")}],
        },
        task_service,
        schema=_admission_schema(),
    )

    assert task_service.fail_args is not None, "task must be marked failed"
    assert task_service.fail_args["code"] == ErrorCode.ALGORITHM_CONTRACT_INVALID.code
    assert result["status"] == "failed"
