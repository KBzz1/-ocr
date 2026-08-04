import pytest

from app.backend import create_backend_app
from app.backend.storage.json_store import JsonStore


@pytest.fixture
def app(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{tmp_path / 'data'}"
  log_dir: "{tmp_path / 'logs'}"
  storage_dir: "{tmp_path / 'data'}"
  export_dir: "{tmp_path / 'exports'}"
sessions:
  capture_session_ttl_minutes: 30
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
algorithms:
  algorithm_engine: qwen_batch
  qwen_batch_schema_path: "./app/config/schemas/qwen_batch_admission_record.v2.yaml"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    flask_app = create_backend_app(config_dir=str(config_dir))
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def review_task(app):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        "tasks/1.json",
        {
            "task_id": "1",
            "status": "review",
            "created_at": "2026-05-19T10:00:00+00:00",
            "updated_at": "2026-05-19T10:00:00+00:00",
            "upload_token": "token_001",
            "images": [],
            "error_code": None,
            "error_message": None,
            "export_summary": {"last_exported_at": None, "formats": [], "files": []},
        },
    )
    # 使用当前默认 Qwen 批处理 schema 实际存在的字段。
    store.write(
        "results/1/field_candidates.json",
        {
            "task_id": "1",
            "stage": "field_extraction",
            "status": "success",
            "candidates": [
                {"field_key": "chief_complaint", "original_value": "退休", "evidence": "第1页", "confidence": 0.9},
                {"field_key": "pe_temperature", "original_value": "体温36.5℃", "evidence": "第2页", "confidence": 0.85},
            ],
        },
    )
    return {"task_id": "1"}


def test_get_review_initializes_result(client, review_task):
    response = client.get(f"/api/tasks/{review_task['task_id']}/review")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["task_id"] == "1"
    assert data["status"] == "review"
    fields = data["review_result"]["fields"]
    # BE-MVP-05-06: 字段集合与当前 schema 一致。
    assert len(fields) >= 2
    # 候选里有的字段被正确填入
    field_by_key = {f["field_key"]: f for f in fields}
    assert field_by_key["chief_complaint"]["final_value"] == "退休"
    # pe_temperature 为数值型参数(unit ℃),review 初始化按既有契约规范化为纯数值
    assert field_by_key["pe_temperature"]["final_value"] == "36.5"


def test_put_review_saves_final_fields(client, review_task):
    response = client.put(
        f"/api/tasks/{review_task['task_id']}/review",
        json={
            "fields": [
                {"field_key": "chief_complaint", "value": "工人", "status": "modified"},
                {"field_key": "pe_temperature", "value": "体温36.5℃", "status": "confirmed"},
            ]
        },
    )

    assert response.status_code == 200
    fields = response.get_json()["data"]["review_result"]["fields"]
    field_by_key = {f["field_key"]: f for f in fields}
    assert field_by_key["chief_complaint"]["status"] == "modified"
    assert field_by_key["chief_complaint"]["final_value"] == "工人"
    assert field_by_key["pe_temperature"]["status"] == "confirmed"


def test_complete_review_route_marks_done(client, review_task):
    client.put(
        f"/api/tasks/{review_task['task_id']}/review",
        json={
            "fields": [
                {"field_key": "chief_complaint", "value": "退休", "status": "confirmed"},
                {"field_key": "pe_temperature", "value": "体温36.5℃", "status": "confirmed"},
            ]
        },
    )

    response = client.post(f"/api/tasks/{review_task['task_id']}/complete")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "done"


def test_reopen_review_transitions_done_to_review(client, app, review_task):
    client.put(
        f"/api/tasks/{review_task['task_id']}/review",
        json={
            "fields": [
                {"field_key": "chief_complaint", "value": "退休", "status": "confirmed"},
                {"field_key": "pe_temperature", "value": "体温36.5℃", "status": "confirmed"},
            ]
        },
    )
    client.post(f"/api/tasks/{review_task['task_id']}/complete")

    response = client.post(f"/api/tasks/{review_task['task_id']}/review/reopen")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "review"


def test_failed_task_cannot_enter_review_flow(client, app):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        "tasks/1.json",
        {
            "task_id": "1",
            "status": "failed",
            "created_at": "2026-05-19T10:00:00+00:00",
            "updated_at": "2026-05-19T10:00:00+00:00",
            "images": [],
        },
    )

    response = client.get("/api/tasks/1/review")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"


# --- Task 6: 审核返回证据数组与核验提示 ---


def test_review_route_returns_schema_ordered_admission_fields(client, app, review_task):
    """Task 6: /api/tasks/{id}/review 返回的 review_result 必须包含 field_groups
    (按 schema 顺序),且 fields 数量与 schema 一致。
    """
    schema_service = app.config["SCHEMA_SERVICE"]
    schema = schema_service.get_current()

    response = client.get(f"/api/tasks/{review_task['task_id']}/review")

    assert response.status_code == 200
    data = response.get_json()["data"]
    review_result = data["review_result"]

    # field_groups 必须存在且按 schema 顺序产出
    assert "field_groups" in review_result
    field_groups = review_result["field_groups"]
    assert isinstance(field_groups, list)
    schema_field_keys = [
        schema_field["field_key"]
        for group in schema["field_groups"]
        for schema_field in group["fields"]
    ]
    schema_groups_keys = [group["group_key"] for group in schema["field_groups"]]
    assert [group["group_key"] for group in field_groups] == schema_groups_keys
    # fields 数量与 schema 一致,按 schema 顺序
    returned_field_keys = [f["field_key"] for f in review_result["fields"]]
    assert len(returned_field_keys) == len(schema_field_keys)
    assert returned_field_keys == schema_field_keys


def test_review_route_does_not_expose_internal_attention_flag_names_as_messages(client, app, review_task):
    """Task 6: review 路由返回的 attention_message 不能包含内部 flag 名
    (source_section_not_found / evidence_missing_fallback / source_hint= 等),
    只能给前端可读的中文提示。
    """
    # 在 field_candidates 里塞一个带 attention 的字段,触发 attention_message 写入
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    candidates = store.read(f"results/{review_task['task_id']}/field_candidates.json")
    candidates["candidates"].append({
        "field_key": "chief_complaint",
        "original_value": "咳嗽",
        "evidence": [
            {"id": "u777", "text": "主诉：咳嗽 5 天。", "start_offset": 0, "end_offset": 9, "page_no": 1}
        ],
        "extraction_status": "extracted",
        "verification_status": "suspicious",
        "attention_required": True,
        "attention_message": "缺少来源证据，请核对原文",
        "quality_flags": ["evidence_missing_fallback"],
    })
    store.write(f"results/{review_task['task_id']}/field_candidates.json", candidates)

    response = client.get(f"/api/tasks/{review_task['task_id']}/review")

    assert response.status_code == 200
    fields = response.get_json()["data"]["review_result"]["fields"]
    # 收集所有前端可见的 attention_message 文本
    messages = [f.get("attention_message", "") or "" for f in fields]
    joined = "\n".join(messages)
    # 内部 flag 名不应作为 attention_message 暴露
    for forbidden in ("source_section_not_found", "evidence_missing_fallback", "source_hint="):
        assert forbidden not in joined, f"attention_message 暴露内部 flag 名: {forbidden}"
    # 内部 quality_flags 可以保留(审计需要),但前端只看到 attention_message
    chief = next(f for f in fields if f["field_key"] == "chief_complaint")
    assert chief["attention_required"] is True
    assert chief["attention_message"] == "缺少来源证据，请核对原文"
