"""患者 API 路由测试。"""
import pytest

from app.backend.errors import ErrorCode
from app.backend.tests.fixtures.client import make_client


def test_patient_crud_contract(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    created = client.post("/api/patients", json={"name": "测试患者"})
    assert created.status_code == 201
    patient_id = created.get_json()["data"]["patient_id"]
    assert patient_id.startswith("P-")

    search = client.get("/api/patients?query=测试患者")
    assert search.status_code == 200
    payload = search.get_json()["data"]["patients"]
    assert any(item["patient_id"] == patient_id for item in payload)

    detail = client.get(f"/api/patients/{patient_id}")
    assert detail.status_code == 200
    assert detail.get_json()["data"]["name"] == "测试患者"
    assert "name_history" not in detail.get_json()["data"]

    patched = client.patch(f"/api/patients/{patient_id}", json={"name": "测试用例"})
    assert patched.status_code == 200
    assert patched.get_json()["data"]["name"] == "测试用例"


def test_create_patient_rejects_blank_name(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.post("/api/patients", json={"name": "   "})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_get_missing_patient_returns_404(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.get("/api/patients/P-MISSING01")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == ErrorCode.PATIENT_NOT_FOUND.code


def test_rename_patient_appends_history_but_does_not_leak(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)
    created = client.post("/api/patients", json={"name": "甲"}).get_json()["data"]
    patient_id = created["patient_id"]

    renamed = client.patch(f"/api/patients/{patient_id}", json={"name": "乙"})
    assert renamed.status_code == 200
    assert "name_history" not in renamed.get_json()["data"]


def test_rename_patient_rejects_blank(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)
    created = client.post("/api/patients", json={"name": "甲"}).get_json()["data"]

    response = client.patch(f"/api/patients/{created['patient_id']}", json={"name": ""})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == ErrorCode.INVALID_REQUEST_PARAMS.code
