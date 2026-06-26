"""后端 E2E 契约测试：MVP 任务上传、处理、审核、完成、导出。"""
import inspect
import json
import os
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


def test_backend_configures_qwen_vision_vllm_ocr_port(tmp_path, monkeypatch):
    from app.backend import create_backend_app
    from app.backend.services.algorithm_ports.qwen_vision_vllm import QwenVisionVLLMDocumentPort

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
  qwen_vllm_server_url: http://qwen-vision-vllm-server:8000/v1
  qwen_vllm_model_name: Qwen3.5-4B-AWQ-4bit
  gpu_stage_queue_enabled: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])

    app = create_backend_app(str(config_dir))
    orchestrator = app.config["TASK_SERVICE"]._orchestrator

    assert orchestrator._image_port is not None
    assert isinstance(orchestrator._doc_port, QwenVisionVLLMDocumentPort)
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

    # 等待两个 orchestrator 线程真正完成（qwen_ocr_and_extraction 共 2 次 stage）
    for tid, ev in done_events.items():
        assert ev.wait(timeout=15), f"{tid} orchestrator 线程未在 15s 内完成"

    # 2 次 stage 调用：2 task × qwen_ocr_and_extraction（OCR + 抽取连续持有同一阶段）
    assert len(entries) == 2, f"应 2 次 stage 调用，实际 {len(entries)}: {entries}"

    # 两个 task 都经历过 qwen_ocr_and_extraction
    task_ids_in_order = [e["task_id"] for e in entries]
    stages_in_order = [e["stage"] for e in entries]
    assert "task-A" in task_ids_in_order and "task-B" in task_ids_in_order
    assert stages_in_order.count("qwen_ocr_and_extraction") == 2

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


def test_fixture_client_starts_with_system_status(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.get("/api/system/status")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "running"


def test_mvp_success_flow_create_upload_process_review_done_export(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="success")
    patient = client.post("/api/patients", json={"name": "测试用例"}).get_json()["data"]
    created = client.post(
        "/api/tasks",
        json={
            "patient_id": patient["patient_id"],
            "document_type": "copd_admission_record",
            "record_date": "2026-06-07",
        },
    ).get_json()["data"]

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
    field_by_key = {f["field_key"]: f for f in fields}
    assert field_by_key["chief_complaint"]["auto_value"] == "模拟外部算法返回的主诉"
    assert field_by_key["chief_complaint"]["status"] == "unreviewed"

    saved = client.put(
        f"/api/tasks/{created['task_id']}/review",
        json={"fields": [{"field_key": "chief_complaint", "value": "人工审核后的主诉", "status": "modified"}]},
    )
    assert saved.status_code == 200
    saved_fields = saved.get_json()["data"]["review_result"]["fields"]
    saved_field = next(f for f in saved_fields if f["field_key"] == "chief_complaint")
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


def test_admission_record_raw_ocr_typo_and_page_order_still_reviewable(tmp_path, monkeypatch):
    """Task 10 端到端回归: 入院记录 OCR 标题错字 + 页面乱序,审核页必须仍然能展示。

    模拟场景:
    - OCR 页面按系统保存顺序写入(不重排): page 1 = ## 品后诊断 + 最终诊断; page 2 = 主诉...
    - Fake Qwen 字段端口返回 schema 全量 61 字段:
      * chief_complaint found,evidence 指向 page 2
      * diagnosis_final found,evidence 指向 page 1
      * 血气 6 字段共享同一 evidence unit
      * 大部分 pmh 字段 not_found
    """
    from app.backend.services.schema_loader import load_schema
    from app.backend.services.task_service import TaskService
    from app.backend.storage.json_store import JsonStore

    schema = load_schema("app/config/schemas/admission_record_structured_fields.v1.yaml")
    schema_field_groups = schema["field_groups"]

    class AdmissionRecordFullProcessing:
        """模拟 Qwen 固定字段全量 61 字段抽取 + OCR 标题错字 + 乱序保存。"""

        # OCR 页面按系统保存顺序写入(刻意乱序: 诊断在前,主诉在后)
        PAGE1_TEXT = "## 品后诊断\n慢性阻塞性肺疾病急性加重\nⅡ型呼吸衰竭"
        PAGE2_TEXT = (
            "## 初步诊断：\n"
            "主诉：反复咳嗽、咳痰20年，喘累2年，加重10余天。\n"
            "血气分析:pH7.40、pCO236.00mmHg、PO276.00mmHg↓、Na+130.00mmol/L↓、FiO221.00、氧合指数:961"
        )
        # 与当前 OCR 端口使用的页面分隔符保持一致
        MERGED_TEXT = f"{PAGE1_TEXT}\n\n{PAGE2_TEXT}"

        # 诊断原文 = OCR 页面 1 中的"最终诊断"片段(不静默改写)
        SOURCE_DIAGNOSIS_FINAL = "慢性阻塞性肺疾病急性加重\nⅡ型呼吸衰竭"
        # 主诉原文 = OCR 页面 2 中的"主诉:..."片段
        SOURCE_CHIEF_COMPLAINT = "主诉：反复咳嗽、咳痰20年，喘累2年，加重10余天。"
        # 血气原文(整组保持在一个 evidence unit)
        SOURCE_BLOOD_GAS = (
            "血气分析:pH7.40、pCO236.00mmHg、PO276.00mmHg↓、Na+130.00mmol/L↓、FiO221.00、氧合指数:961"
        )

        def __init__(self, store: JsonStore):
            self._store = store

        def _build_candidates(self, task: dict) -> list[dict]:
            """按 schema 全量 61 字段产出候选;found/not_found 严格匹配 task 描述。"""
            images = task.get("images") or []
            page_ids = [img["page_id"] for img in sorted(images, key=lambda i: i["page_no"])]

            # evidence unit IDs 由 backend 自有 evidence_units 提供,
            # 这里只引用已生成的 ID 字符串。Task 2 之前未持久化 evidence_units 的场景下,
            # review 阶段通过 evidence 文本和 offset 定位;为了保持端到端测试自洽,
            # 我们用与 evidence_units 一致的 ID 字符串,但 evidence 列表在 review 阶段
            # 只看 page_no / text / start_offset / end_offset,不直接读 evidence_units。
            chief_evidence = {
                "id": "u_chief",
                "text": self.SOURCE_CHIEF_COMPLAINT,
                "start_offset": self.MERGED_TEXT.index(self.SOURCE_CHIEF_COMPLAINT),
                "end_offset": self.MERGED_TEXT.index(self.SOURCE_CHIEF_COMPLAINT) + len(self.SOURCE_CHIEF_COMPLAINT),
                "page_no": 2,
                "page_id": page_ids[1] if len(page_ids) > 1 else page_ids[0],
            }
            diagnosis_evidence = {
                "id": "u_diag",
                "text": self.SOURCE_DIAGNOSIS_FINAL,
                "start_offset": self.MERGED_TEXT.index(self.SOURCE_DIAGNOSIS_FINAL),
                "end_offset": self.MERGED_TEXT.index(self.SOURCE_DIAGNOSIS_FINAL) + len(self.SOURCE_DIAGNOSIS_FINAL),
                "page_no": 1,
                "page_id": page_ids[0],
            }
            blood_gas_evidence = {
                "id": "u_blood_gas",
                "text": self.SOURCE_BLOOD_GAS,
                "start_offset": self.MERGED_TEXT.index(self.SOURCE_BLOOD_GAS),
                "end_offset": self.MERGED_TEXT.index(self.SOURCE_BLOOD_GAS) + len(self.SOURCE_BLOOD_GAS),
                "page_no": 2,
                "page_id": page_ids[1] if len(page_ids) > 1 else page_ids[0],
            }

            blood_gas_fields = {
                "aux_blood_gas_ph",
                "aux_blood_gas_pco2",
                "aux_blood_gas_po2",
                "aux_blood_gas_na",
                "aux_blood_gas_fio2",
                "aux_blood_gas_oxygenation_index",
            }

            # past_medical_history 里我们挑一个字段显式测 attention_required=False
            # 其余保持 not_found
            candidates: list[dict] = []
            for group in schema_field_groups:
                for schema_field in group["fields"]:
                    fk = schema_field["field_key"]
                    label = schema_field["label"]
                    if fk == "chief_complaint":
                        candidates.append({
                            "field_key": fk,
                            "field_name": label,
                            "section_key": group["group_key"],
                            "section_label": group["group_label"],
                            "extraction_status": "extracted",
                            "verification_status": "not_checked",
                            "original_value": self.SOURCE_CHIEF_COMPLAINT,
                            "evidence": [dict(chief_evidence)],
                            "page_no": 2,
                            "attention_required": False,
                            "attention_message": "",
                            "quality_flags": [],
                            "source_section": group["group_label"],
                            "source_hint": "主诉",
                            "source_text": self.SOURCE_CHIEF_COMPLAINT,
                            "source_group_id": group["group_key"],
                            "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
                        })
                    elif fk == "diagnosis_final":
                        candidates.append({
                            "field_key": fk,
                            "field_name": label,
                            "section_key": group["group_key"],
                            "section_label": group["group_label"],
                            "extraction_status": "extracted",
                            "verification_status": "not_checked",
                            "original_value": self.SOURCE_DIAGNOSIS_FINAL,
                            "evidence": [dict(diagnosis_evidence)],
                            "page_no": 1,
                            "attention_required": False,
                            "attention_message": "",
                            "quality_flags": [],
                            "source_section": group["group_label"],
                            "source_hint": "最终诊断",
                            "source_text": self.SOURCE_DIAGNOSIS_FINAL,
                            "source_group_id": group["group_key"],
                            "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
                        })
                    elif fk in blood_gas_fields:
                        # 6 个血气字段共享同一个 evidence unit(同 id / 同 text / 同 offset)
                        candidates.append({
                            "field_key": fk,
                            "field_name": label,
                            "section_key": group["group_key"],
                            "section_label": group["group_label"],
                            "extraction_status": "extracted",
                            "verification_status": "not_checked",
                            "original_value": "见血气分析",
                            "evidence": [dict(blood_gas_evidence)],
                            "page_no": 2,
                            "attention_required": False,
                            "attention_message": "",
                            "quality_flags": [],
                            "source_section": group["group_label"],
                            "source_hint": "血气",
                            "source_text": self.SOURCE_BLOOD_GAS,
                            "source_group_id": group["group_key"],
                            "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
                        })
                    else:
                        # not_found 字段: attention_required 必须为 False(既往史等不默认黄色感叹号)
                        candidates.append({
                            "field_key": fk,
                            "field_name": label,
                            "section_key": group["group_key"],
                            "section_label": group["group_label"],
                            "extraction_status": "not_found",
                            "verification_status": "not_checked",
                            "original_value": "",
                            "evidence": [],
                            "page_no": None,
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

        def run(self, task: dict, task_service, schema: dict | None = None) -> dict:
            task_id = task["task_id"]
            images = sorted(task.get("images") or [], key=lambda i: i["page_no"])
            # 故意按系统保存顺序写入 OCR(模拟医生上传顺序: 诊断页在前,主诉页在后)
            pages = []
            for image in images:
                if image["page_no"] == 1:
                    text = self.PAGE1_TEXT
                elif image["page_no"] == 2:
                    text = self.PAGE2_TEXT
                else:
                    text = ""
                pages.append({
                    "page_id": image["page_id"],
                    "page_no": image["page_no"],
                    "text": text,
                    "status": "success",
                })
            evidence_units = [
                {
                    "id": "u_chief",
                    "text": self.SOURCE_CHIEF_COMPLAINT,
                    "start_offset": self.MERGED_TEXT.index(self.SOURCE_CHIEF_COMPLAINT),
                    "end_offset": self.MERGED_TEXT.index(self.SOURCE_CHIEF_COMPLAINT) + len(self.SOURCE_CHIEF_COMPLAINT),
                    "page_no": 2,
                },
                {
                    "id": "u_diag",
                    "text": self.SOURCE_DIAGNOSIS_FINAL,
                    "start_offset": self.MERGED_TEXT.index(self.SOURCE_DIAGNOSIS_FINAL),
                    "end_offset": self.MERGED_TEXT.index(self.SOURCE_DIAGNOSIS_FINAL) + len(self.SOURCE_DIAGNOSIS_FINAL),
                    "page_no": 1,
                },
                {
                    "id": "u_blood_gas",
                    "text": self.SOURCE_BLOOD_GAS,
                    "start_offset": self.MERGED_TEXT.index(self.SOURCE_BLOOD_GAS),
                    "end_offset": self.MERGED_TEXT.index(self.SOURCE_BLOOD_GAS) + len(self.SOURCE_BLOOD_GAS),
                    "page_no": 2,
                },
            ]
            self._store.write(
                f"results/{task_id}/document_result.json",
                {
                    "task_id": task_id,
                    "stage": "document_parsing",
                    "status": "success",
                    "pages": pages,
                    "merged_text": self.MERGED_TEXT,
                    "evidence_units": evidence_units,
                },
            )
            self._store.write(
                f"results/{task_id}/field_candidates.json",
                {
                    "task_id": task_id,
                    "stage": "field_extraction",
                    "status": "success",
                    "schema_version": (schema or {}).get("version"),
                    "candidates": self._build_candidates(task),
                },
            )
            return task_service.mark_ready(task_id)

    client, app = make_client(tmp_path, monkeypatch)
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    task_service = TaskService(
        store=store,
        orchestrator=AdmissionRecordFullProcessing(store),
        schema_provider=app.config["SCHEMA_SERVICE"].get_current,
        background_runner=lambda task_id, run: run(),
        patient_service=app.config.get("PATIENT_SERVICE"),
    )
    app.config["TASK_SERVICE"] = task_service
    from app.backend.services.review_service import ReviewService
    app.config["REVIEW_SERVICE"] = ReviewService(
        store=store,
        task_service=task_service,
        schema_provider=app.config["SCHEMA_SERVICE"].get_current,
    )

    patient = client.post("/api/patients", json={"name": "OCR乱序"}).get_json()["data"]
    created = client.post(
        "/api/tasks",
        json={
            "patient_id": patient["patient_id"],
            "document_type": "copd_admission_record",
            "record_date": "2026-06-18",
        },
    ).get_json()["data"]

    for index in range(2):
        upload = upload_task_image(client, created, filename=f"page-{index + 1}.jpg")
        assert upload.status_code == 201

    finished = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")
    assert finished.status_code == 200
    final = wait_for_task_status(client, created["task_id"], "review")
    assert final["status"] == "review"

    review = client.get(f"/api/tasks/{created['task_id']}/review")
    assert review.status_code == 200
    review_payload = review.get_json()["data"]["review_result"]

    # 1. ocr_text 保留 OCR 原文(包括 ## 品后诊断 错字)
    assert "## 品后诊断" in review_payload["ocr_text"]
    assert "反复咳嗽、咳痰20年" in review_payload["ocr_text"]
    assert review_payload["ocr_text"] == AdmissionRecordFullProcessing.MERGED_TEXT

    # 2. 字段组按 schema 顺序:chief_complaint(主诉) 在 diagnosis(诊断) 之前
    field_groups = review_payload.get("field_groups") or []
    assert field_groups, "审核响应必须包含 schema field_groups"
    group_order = [g["group_key"] for g in field_groups]
    assert "chief_complaint" in group_order
    assert "diagnosis" in group_order
    assert group_order.index("chief_complaint") < group_order.index("diagnosis"), (
        "主诉章节必须早于诊断章节,与 OCR 页面保存顺序无关"
    )

    fields_by_key = {f["field_key"]: f for f in review_payload["fields"]}
    assert "chief_complaint" in fields_by_key
    assert "diagnosis_final" in fields_by_key
    assert "pmh_nephritis" in fields_by_key

    # 3. diagnosis_final 值 = OCR 页面 1 中的最终诊断原文(逐字匹配,不静默改写)
    assert fields_by_key["diagnosis_final"]["auto_value"] == AdmissionRecordFullProcessing.SOURCE_DIAGNOSIS_FINAL
    assert fields_by_key["diagnosis_final"]["final_value"] == AdmissionRecordFullProcessing.SOURCE_DIAGNOSIS_FINAL
    assert fields_by_key["diagnosis_final"]["status"] == "unreviewed"

    # 4. pmh_nephritis not_found + attention_required=False
    assert fields_by_key["pmh_nephritis"]["extraction_status"] == "not_found"
    assert fields_by_key["pmh_nephritis"]["attention_required"] is False
    assert fields_by_key["pmh_nephritis"]["auto_value"] == ""
    assert fields_by_key["pmh_nephritis"]["final_value"] == ""

    # 5. 血气 6 字段共享同一 evidence unit ID
    blood_gas_keys = [
        "aux_blood_gas_ph", "aux_blood_gas_pco2", "aux_blood_gas_po2",
        "aux_blood_gas_na", "aux_blood_gas_fio2", "aux_blood_gas_oxygenation_index",
    ]
    blood_gas_ids = set()
    for fk in blood_gas_keys:
        f = fields_by_key[fk]
        assert f["extraction_status"] == "extracted"
        assert f["evidence"], f"{fk} 必须有 evidence"
        assert len(f["evidence"]) == 1
        blood_gas_ids.add(f["evidence"][0]["id"])
    assert blood_gas_ids == {"u_blood_gas"}, (
        f"6 个血气字段必须共享同一 evidence unit id,实际 {blood_gas_ids}"
    )

    # 6. chief_complaint evidence 指向 page 2, diagnosis_final evidence 指向 page 1
    assert fields_by_key["chief_complaint"]["evidence"][0]["page_no"] == 2
    assert fields_by_key["diagnosis_final"]["evidence"][0]["page_no"] == 1

    # 7. 全量 61 字段已被补齐(由 _hydrate_missing_fields)
    assert len(review_payload["fields"]) == 61


# 测试内本地缓存 schema 字段表,避免每个候选构造都重读 yaml
def test_backend_default_profile_uses_admission_record_structured_schema(tmp_path, monkeypatch):
    """默认 copd_admission_record profile 的 schema 版本必须是固定字段 schema。"""
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
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    monkeypatch.setattr(
        "app.backend.services.copd_extraction.port.build_default_copd_field_port",
        lambda config, field_keys_provider: object(),
    )

    app = create_backend_app(str(config_dir))
    registry = app.config["DOCUMENT_PROFILE_REGISTRY"]
    profile = registry.get_profile("copd_admission_record")

    assert profile.document_type == "copd_admission_record"
    assert profile.label == "入院记录"
    assert profile.schema_version == "admission_record_structured_fields.v1"


def test_create_backend_app_with_qwen_batch_engine_config(tmp_path, monkeypatch):
    from app.backend import create_backend_app
    from app.backend.services.algorithm_ports.qwen_batch_orchestrator import (
        QwenBatchProcessingOrchestrator,
    )

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
    job_dir = tmp_path / "jobs"
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
  algorithm_engine: qwen_batch
  qwen_batch_job_dir: "{job_dir}"
  qwen_batch_schema_path: "./app/config/schemas/qwen_batch_admission_record.v1.yaml"
  qwen_batch_runner_timeout_seconds: 1800
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])

    app = create_backend_app(str(config_dir))
    config = app.config["BACKEND_CONFIG"]
    registry = app.config["DOCUMENT_PROFILE_REGISTRY"]
    profile = registry.get_profile("qwen_batch_admission_record")

    assert config["algorithm_engine"] == "qwen_batch"
    assert registry.get_default_document_type() == "qwen_batch_admission_record"
    assert profile.schema_version == "qwen_batch_admission_record.v1"
    assert profile.field_port is not None
    assert isinstance(app.config["TASK_SERVICE"]._orchestrator, QwenBatchProcessingOrchestrator)
