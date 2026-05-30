from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator
from app.backend.storage.json_store import JsonStore


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
