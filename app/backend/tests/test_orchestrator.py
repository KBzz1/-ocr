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
