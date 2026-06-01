"""后端 E2E 契约测试：MVP 任务上传、处理、审核、完成、导出。"""
import inspect
import json
import os
import sys
import threading
import time

from app.backend.errors import ErrorCode
from app.backend.tests.fixtures.client import make_client, setup_task_with_images, upload_task_image
from app.backend.tests.fixtures.processing import install_simulated_processing


def wait_for_task_status(client, task_id: str, status: str, timeout: float = 1.0) -> dict:
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        latest = client.get(f"/api/tasks/{task_id}").get_json()["data"]
        if latest["status"] == status:
            return latest
        time.sleep(0.01)
    return latest or client.get(f"/api/tasks/{task_id}").get_json()["data"]


def test_backend_configures_copd_field_port(tmp_path, monkeypatch):
    from app.backend import create_backend_app

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{data_dir}"
  log_dir: "{log_dir}"
  model_dir: "{tmp_path}/models"
  export_dir: "{export_dir}"
  static_dir: "{static_dir}"
  storage_dir: "{data_dir}"
algorithms:
  enable_copd_extractor: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.backend._get_lan_addresses",
        lambda port: ["192.168.1.5:8081"],
    )
    monkeypatch.setattr(
        "app.backend.services.copd_extraction.port.build_default_copd_field_port",
        lambda config, field_keys_provider: object(),
    )

    app = create_backend_app(str(config_dir))
    orchestrator = app.config["TASK_SERVICE"]._orchestrator

    assert orchestrator._field_port is not None


def test_backend_configures_local_ocr_ports(tmp_path, monkeypatch):
    from app.backend import create_backend_app

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    runner = tmp_path / "ocr_runner.py"
    runner.write_text("print('fake')\n", encoding="utf-8")
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{data_dir}"
  log_dir: "{log_dir}"
  model_dir: "{tmp_path}/models"
  export_dir: "{export_dir}"
  static_dir: "{static_dir}"
  storage_dir: "{data_dir}"
algorithms:
  enable_local_ocr: true
  local_ocr_python_executable: "{sys.executable}"
  local_ocr_script_path: "{runner}"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.backend._get_lan_addresses",
        lambda port: ["192.168.1.5:8081"],
    )

    app = create_backend_app(str(config_dir))
    orchestrator = app.config["TASK_SERVICE"]._orchestrator

    assert orchestrator._image_port is not None
    assert orchestrator._doc_port is not None
    assert orchestrator._doc_port._cache_dir == f"{tmp_path}/models/ppstructure/paddlex_cache"


def test_backend_configures_vlm_server_ocr_port(tmp_path, monkeypatch):
    from app.backend import create_backend_app
    from app.backend.services.algorithm_ports.paddleocr_vlm_server import PaddleOCRVLMServerDocumentPort

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{data_dir}"
  log_dir: "{log_dir}"
  model_dir: "{tmp_path}/models"
  export_dir: "{export_dir}"
  static_dir: "{static_dir}"
  storage_dir: "{data_dir}"
algorithms:
  enable_local_ocr: true
  local_ocr_mode: vlm_server
  local_ocr_vlm_server_url: http://paddleocr-vlm-server:8080/v1
  gpu_stage_queue_enabled: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])

    app = create_backend_app(str(config_dir))
    orchestrator = app.config["TASK_SERVICE"]._orchestrator

    assert orchestrator._image_port is not None
    assert isinstance(orchestrator._doc_port, PaddleOCRVLMServerDocumentPort)
    assert orchestrator._gpu_stage_queue is not None


def test_run_processing_background_does_not_serialize_across_tasks(tmp_path, monkeypatch):
    """run_processing_background 不应持有全局 processing_lock，否则 GPU 阶段队列无法发挥跨任务并发序列化作用。"""
    from app.backend import create_backend_app

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{data_dir}"
  log_dir: "{log_dir}"
  model_dir: "{tmp_path}/models"
  export_dir: "{export_dir}"
  static_dir: "{static_dir}"
  storage_dir: "{data_dir}"
algorithms:
  enable_local_ocr: true
  local_ocr_mode: runner
  gpu_stage_queue_enabled: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])

    app = create_backend_app(str(config_dir))
    task_service = app.config["TASK_SERVICE"]

    # 抓取 run_processing_background 源码；全局 processing_lock 会让其 body 出现
    # `with processing_lock:`，与跨任务 GPU 并发序列化目标冲突。
    runner = task_service._background_runner
    src = inspect.getsource(runner)
    assert "with processing_lock" not in src, (
        "run_processing_background 仍持有全局 processing_lock，"
        "导致 GPU 阶段队列无法发挥跨任务并发序列化作用。"
    )


def test_two_tasks_serialize_gpu_stages_via_run_processing_background(tmp_path, monkeypatch):
    """两个不同 task 通过 run_processing_background 启动后，必须并发进入 orchestrator；
    GPU 阶段（document_parsing / field_extraction）由 gpu_stage_queue 串行化，互不重叠。"""
    from app.backend import create_backend_app

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{data_dir}"
  log_dir: "{log_dir}"
  model_dir: "{tmp_path}/models"
  export_dir: "{export_dir}"
  static_dir: "{static_dir}"
  storage_dir: "{data_dir}"
algorithms:
  enable_local_ocr: true
  local_ocr_mode: runner
  gpu_stage_queue_enabled: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])

    app = create_backend_app(str(config_dir))
    task_service = app.config["TASK_SERVICE"]
    orchestrator = task_service._orchestrator

    # 准备两个真实图片文件
    (tmp_path / "p1.jpg").write_bytes(b"img1")
    (tmp_path / "p2.jpg").write_bytes(b"img2")

    # 探针队列：包装真实 GpuStageQueue，记录每次 stage 调用的 task_id / stage / 进入时间 / 离开时间
    real_queue = orchestrator._gpu_stage_queue
    assert real_queue is not None, "测试前置：必须启用 gpu_stage_queue"

    entries = []
    entries_lock = threading.Lock()

    class ProbingQueue:
        def __init__(self, inner):
            self._inner = inner

        def stage(self, task_id, stage):
            inner_ctx = self._inner.stage(task_id=task_id, stage=stage)
            idx_holder = {}

            class _Ctx:
                def __enter__(_self):
                    result = inner_ctx.__enter__()
                    with entries_lock:
                        idx_holder["idx"] = len(entries)
                        entries.append({
                            "task_id": task_id,
                            "stage": stage,
                            "enter": time.monotonic(),
                            "exit": None,
                        })
                    return result

                def __exit__(_self, exc_type, exc, tb):
                    try:
                        return inner_ctx.__exit__(exc_type, exc, tb)
                    finally:
                        with entries_lock:
                            entries[idx_holder["idx"]]["exit"] = time.monotonic()

            return _Ctx()

    orchestrator._gpu_stage_queue = ProbingQueue(real_queue)

    # 替换 orchestrator 端口为可控桩：image 透传 / doc 慢 100ms / field 返回合法候选
    class ImagePort:
        def process(self, input):
            return {"processed_path": input["original_path"]}

    class SlowDocPort:
        def parse(self, input):
            time.sleep(0.1)
            return {
                "pages": [
                    {"page_id": p["page_id"], "page_no": p["page_no"], "status": "success", "text": "x"}
                    for p in input["pages"]
                ],
                "merged_text": "x",
            }

    class FieldPort:
        def extract(self, input):
            time.sleep(0.1)
            return [
                {
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
            ]

    orchestrator._image_port = ImagePort()
    orchestrator._doc_port = SlowDocPort()
    orchestrator._field_port = FieldPort()
    orchestrator._field_port_registry = {"copd_admission_record": FieldPort()}

    # 准备两个 task JSON（PROCESSING 状态，避免 is_processing_cancelled 立即返回 True）
    store = app.config["BACKEND_CONFIG"]["storage_dir"]
    for tid, page_id in [("task-A", "page_a"), ("task-B", "page_b")]:
        task = {
            "task_id": tid,
            "display_name": tid,
            "status": "processing",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "processing_at": "2026-01-01T00:00:00+00:00",
            "images": [
                {
                    "page_id": page_id,
                    "page_no": 1,
                    "original_image_path": str(tmp_path / ("p1.jpg" if tid == "task-A" else "p2.jpg")),
                }
            ],
            "document_type": "copd_admission_record",
            "document_type_label": "入院记录",
            "export_summary": {"last_exported_at": None, "formats": [], "files": []},
            "status_history": [],
        }
        from app.backend.storage.json_store import JsonStore
        JsonStore(store).write(f"tasks/{tid}.json", task)

    # 抓取 task_service 实例的 background_runner（来自 __init__.py 的 run_processing_background）
    runner = task_service._background_runner

    # orchestrator.run 触发的最简 stub：仅响应状态变更回调，不读 JSON。
    class StubTaskService:
        def mark_processing_stage(self, task_id, stage, status, page_count=None):
            return {"task_id": task_id, "status": "processing"}

        def mark_ready(self, task_id):
            return {"task_id": task_id, "status": "review"}

        def mark_failed(self, task_id, error_code, error_message, stage="processing", details=None):
            return {"task_id": task_id, "status": "failed", "error_code": error_code}

        def is_processing_cancelled(self, task_id):
            return False

        def get_task(self, task_id):
            return {"task_id": task_id, "status": "processing"}

    # 由于 runner 是异步的（启动 daemon 线程后立即返回），需要事件机制等待 orchestrator
    # 真正跑完，避免在 t.join 之后立刻断言 entries（orchestrator 还没跑到 gpu_stage）。
    done_events = {}

    def run_task(tid, image_path):
        task_input = {
            "task_id": tid,
            "document_type": "copd_admission_record",
            "images": [
                {"page_id": "p1", "page_no": 1, "original_image_path": image_path}
            ],
        }
        done = threading.Event()
        done_events[tid] = done

        def _wrapped():
            try:
                return orchestrator.run(task_input, StubTaskService(), schema={"fields": [{"field_key": "chief_complaint"}]})
            finally:
                done.set()

        # 走真实 background_runner（run_processing_background），不再持有全局 lock
        runner(tid, _wrapped)

    threads = [
        threading.Thread(target=run_task, args=("task-A", str(tmp_path / "p1.jpg"))),
        threading.Thread(target=run_task, args=("task-B", str(tmp_path / "p2.jpg"))),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
        assert not t.is_alive(), f"线程 {t.name} 卡死，说明 run_processing_background 仍有全局互斥"

    # 等待两个 orchestrator 线程真正完成（document_parsing + field_extraction 共 4 次 stage）
    for tid, ev in done_events.items():
        assert ev.wait(timeout=15), f"{tid} orchestrator 线程未在 15s 内完成"

    # 4 次 stage 调用：2 task × (document_parsing + field_extraction)
    assert len(entries) == 4, f"应 4 次 stage 调用，实际 {len(entries)}: {entries}"

    # 两个 task 都经历过 document_parsing 和 field_extraction
    task_ids_in_order = [e["task_id"] for e in entries]
    stages_in_order = [e["stage"] for e in entries]
    assert "task-A" in task_ids_in_order and "task-B" in task_ids_in_order
    assert stages_in_order.count("document_parsing") == 2
    assert stages_in_order.count("field_extraction") == 2

    # 关键验证：GPU 阶段不重叠（每个 stage 的 [enter, exit] 区间不能与其他 stage 的区间相交）。
    # 真实 GpuStageQueue 的锁保证实际执行不重叠；这里加 5ms 宽容是为了过滤：
    # - inner_ctx.__exit__() 已释放锁后才记录 A 的 exit；
    # - inner_ctx.__enter__() 取得锁后才记录 B 的 enter；
    #   调度切换可能让 B 的 enter 略早于 A 的 exit 写入。
    OVERLAP_TOLERANCE = 0.005
    intervals = [(e["enter"], e["exit"], e["task_id"], e["stage"]) for e in entries]
    for i, (ei, xi, ti, si) in enumerate(intervals):
        for j, (ej, xj, tj, sj) in enumerate(intervals):
            if i == j:
                continue
            overlap = ei < xj - OVERLAP_TOLERANCE and ej < xi - OVERLAP_TOLERANCE
            assert not overlap, f"GPU 阶段重叠: {ti}/{si}[{ei:.4f},{xi:.4f}] 与 {tj}/{sj}[{ej:.4f},{xj:.4f}]"


def test_backend_configures_local_ocr_port(tmp_path, monkeypatch):
    from app.backend import create_backend_app
    from app.backend.services.algorithm_ports.local_paddleocr import LocalPaddleOCRDocumentPort

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{data_dir}"
  log_dir: "{log_dir}"
  model_dir: "{tmp_path}/models"
  export_dir: "{export_dir}"
  static_dir: "{static_dir}"
  storage_dir: "{data_dir}"
algorithms:
  enable_local_ocr: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.backend._get_lan_addresses",
        lambda port: ["192.168.1.5:8081"],
    )

    app = create_backend_app(str(config_dir))
    orchestrator = app.config["TASK_SERVICE"]._orchestrator

    assert isinstance(orchestrator._doc_port, LocalPaddleOCRDocumentPort)


def test_local_ocr_runner_flow_create_upload_process_review(tmp_path, monkeypatch):
    from app.backend import create_backend_app

    class FieldPortFromOcrText:
        def extract(self, input: dict) -> list[dict]:
            text = input["document_result"]["merged_text"]
            return [
                {
                    "field_key": "cough_sputum_change",
                    "original_value": "咳嗽咳痰3天",
                    "evidence": text,
                    "confidence": 0.9,
                    "extraction_status": "extracted",
                    "verification_status": "passed",
                    "quality_flags": [],
                    "source_section": "主诉",
                    "ocr_correction": {
                        "applied": False,
                        "raw": "",
                        "normalized": "",
                        "reason": "",
                    },
                }
            ]

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    runner = tmp_path / "ocr_runner.py"
    runner.write_text(
        """
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input-dir")
parser.add_argument("--output-file")
parser.add_argument("--max-new-tokens")
parser.add_argument("--max-pixels")
args = parser.parse_args()

images = sorted(Path(args.input_dir).iterdir())
output = Path(args.output_file)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("\\n\\n---\\n\\n".join(
    f"# {image.name}\\n\\n主诉：咳嗽咳痰3天" for image in images
), encoding="utf-8")
""",
        encoding="utf-8",
    )
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{data_dir}"
  log_dir: "{log_dir}"
  model_dir: "{tmp_path}/models"
  export_dir: "{export_dir}"
  static_dir: "{static_dir}"
  storage_dir: "{data_dir}"
algorithms:
  enable_local_ocr: true
  local_ocr_python_executable: "{sys.executable}"
  local_ocr_script_path: "{runner}"
  enable_copd_extractor: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.backend._get_lan_addresses",
        lambda port: ["192.168.1.5:8081"],
    )
    monkeypatch.setattr(
        "app.backend.services.copd_extraction.port.build_default_copd_field_port",
        lambda config, field_keys_provider: FieldPortFromOcrText(),
    )

    app = create_backend_app(str(config_dir))
    app.config["TESTING"] = True
    client = app.test_client()

    created = setup_task_with_images(client)
    finished = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert finished.status_code == 200
    assert finished.get_json()["data"]["status"] == "processing"
    assert wait_for_task_status(client, created["task_id"], "review")["status"] == "review"
    review = client.get(f"/api/tasks/{created['task_id']}/review")
    assert review.status_code == 200
    data = review.get_json()["data"]
    fields = {field["field_key"]: field for field in data["review_result"]["fields"]}
    assert fields["cough_sputum_change"]["auto_value"] == "咳嗽咳痰3天"
    assert fields["cough_sputum_change"]["evidence"] == "主诉：咳嗽咳痰3天"


def test_fixture_client_starts_with_system_status(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.get("/api/system/status")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "running"


def test_mvp_success_flow_create_upload_process_review_done_export(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="success")
    created = client.post("/api/tasks").get_json()["data"]

    for index in range(3):
        upload = upload_task_image(client, created, filename=f"page-{index + 1}.jpg")
        assert upload.status_code == 201
        assert upload.get_json()["data"]["page_no"] == index + 1

    finished = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")
    assert finished.status_code == 200
    assert finished.get_json()["data"]["status"] == "processing"
    assert wait_for_task_status(client, created["task_id"], "review")["status"] == "review"

    task_after_finish = client.get(f"/api/tasks/{created['task_id']}").get_json()["data"]
    assert task_after_finish["page_count"] == 3

    review = client.get(f"/api/tasks/{created['task_id']}/review")
    assert review.status_code == 200
    fields = review.get_json()["data"]["review_result"]["fields"]
    assert fields[0]["field_key"] == "chief_complaint"
    assert fields[0]["auto_value"] == "模拟外部算法返回的主诉"
    assert fields[0]["status"] == "unreviewed"

    saved = client.put(
        f"/api/tasks/{created['task_id']}/review",
        json={"fields": [{"field_key": "chief_complaint", "value": "人工审核后的主诉", "status": "modified"}]},
    )
    assert saved.status_code == 200
    saved_field = saved.get_json()["data"]["review_result"]["fields"][0]
    assert saved_field["auto_value"] == "模拟外部算法返回的主诉"
    assert saved_field["final_value"] == "人工审核后的主诉"

    completed = client.post(f"/api/tasks/{created['task_id']}/complete")
    assert completed.status_code == 200
    assert completed.get_json()["data"]["status"] == "done"

    exported_json = client.get(f"/api/tasks/{created['task_id']}/export/json")
    assert exported_json.status_code == 200
    assert "人工审核后的主诉" in exported_json.get_data(as_text=True)

    exported_excel = client.get(f"/api/tasks/{created['task_id']}/export/excel")
    assert exported_excel.status_code == 200

    assert client.get(f"/api/tasks/{created['task_id']}").get_json()["data"]["status"] == "done"


def test_mvp_algorithm_not_configured_goes_failed(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)
    created = setup_task_with_images(client)

    response = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert response.status_code == 200
    data = wait_for_task_status(client, created["task_id"], "failed")
    assert data["status"] == "failed"
    assert data["error_code"] == ErrorCode.ALGORITHM_MODULE_NOT_CONFIGURED.code


def test_mvp_empty_field_candidates_goes_failed(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="empty_fields")
    created = setup_task_with_images(client)

    response = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert response.status_code == 200
    data = wait_for_task_status(client, created["task_id"], "failed")
    assert data["status"] == "failed"
    assert data["error_code"] == ErrorCode.ALGORITHM_CONTRACT_INVALID.code
    review = client.get(f"/api/tasks/{created['task_id']}/review")
    assert review.status_code == 400
    assert review.get_json()["error"]["code"] == ErrorCode.INVALID_TASK_TRANSITION.code


def test_mvp_simulated_algorithm_exception_goes_failed(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="module_failed")
    created = setup_task_with_images(client)

    response = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert response.status_code == 200
    data = wait_for_task_status(client, created["task_id"], "failed")
    assert data["status"] == "failed"
    assert data["error_code"] == ErrorCode.ALGORITHM_MODULE_FAILED.code
    assert data["failed_at"]


def test_mvp_invalid_field_contract_goes_failed(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="invalid_contract")
    created = setup_task_with_images(client)

    response = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert response.status_code == 200
    data = wait_for_task_status(client, created["task_id"], "failed")
    assert data["status"] == "failed"
    assert data["error_code"] == ErrorCode.ALGORITHM_CONTRACT_INVALID.code
    assert data["failed_at"]


def test_e2e_logs_do_not_include_sensitive_payloads(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="success")
    created = setup_task_with_images(client, page_count=2)
    client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")
    assert wait_for_task_status(client, created["task_id"], "review")["status"] == "review"

    log_path = os.path.join(app.config["BACKEND_CONFIG"]["log_dir"], "backend-events.jsonl")
    assert os.path.isfile(log_path)

    with open(log_path, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    events = [record["event"] for record in lines]
    assert "system_started" in events
    assert "task_processing_started" in events
    assert "task_review_ready" in events

    log_text = json.dumps(lines, ensure_ascii=False)
    assert "ffd8" not in log_text.lower()
    assert "\\xff\\xd8" not in log_text
    assert "110101" not in log_text
    assert "merged text" not in log_text
