"""PatientService 单元测试。"""
import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.patient_service import PatientService
from app.backend.storage.json_store import JsonStore


def make_service(tmp_path, *, now=None):
    return PatientService(JsonStore(str(tmp_path)), now=now or (lambda: "2026-06-07T10:00:00+08:00"))


def test_create_patient_generates_stable_id_and_allows_duplicate_names(tmp_path):
    service = make_service(tmp_path)

    first = service.create("张三")
    second = service.create("张三")

    assert first["patient_id"].startswith("P-")
    assert len(first["patient_id"]) == len("P-") + 8
    assert first["patient_id"] != second["patient_id"]
    assert first["name"] == second["name"] == "张三"
    assert first["deleted_at"] is None
    assert first["name_history"] == []


def test_search_matches_exact_id_or_name_and_hides_deleted(tmp_path):
    service = make_service(tmp_path)
    visible = service.create("张三")
    deleted = service.create("张三")
    service.mark_deleted(deleted["patient_id"])

    assert [item["patient_id"] for item in service.list("张三")] == [visible["patient_id"]]


def test_search_empty_query_returns_all_visible_patients(tmp_path):
    service = make_service(tmp_path)
    a = service.create("张三")
    b = service.create("李四")

    assert {item["patient_id"] for item in service.list("")} == {a["patient_id"], b["patient_id"]}


def test_rename_appends_name_history(tmp_path):
    service = make_service(tmp_path)
    patient = service.create("张三")

    renamed = service.rename(patient["patient_id"], "李四")

    assert renamed["name"] == "李四"
    assert renamed["name_history"][-1] == {
        "from_name": "张三",
        "to_name": "李四",
        "changed_at": "2026-06-07T10:00:00+08:00",
    }


def test_get_bindable_rejects_deleted_patient(tmp_path):
    service = make_service(tmp_path)
    patient = service.create("张三")
    service.mark_deleted(patient["patient_id"])

    with pytest.raises(AppError) as exc:
        service.get_bindable(patient["patient_id"])

    assert exc.value.code == ErrorCode.PATIENT_DELETED.code


def test_get_returns_not_found_for_unknown_patient(tmp_path):
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc:
        service.get("P-MISSING01")

    assert exc.value.code == ErrorCode.PATIENT_NOT_FOUND.code


def test_get_returns_not_found_for_deleted_patient(tmp_path):
    service = make_service(tmp_path)
    patient = service.create("张三")
    service.mark_deleted(patient["patient_id"])

    with pytest.raises(AppError) as exc:
        service.get(patient["patient_id"])

    assert exc.value.code == ErrorCode.PATIENT_NOT_FOUND.code


def test_patient_id_retries_on_collision(tmp_path, monkeypatch):
    from app.backend.services import patient_uuid as uuid_module

    values = iter(
        [
            type("U", (), {"hex": "a1b2c3d4ffffffffffffffffffffffff"})(),
            type("U", (), {"hex": "a1b2c3d4eeeeeeeeeeeeeeeeeeeeeeee"})(),
            type("U", (), {"hex": "e5f6a7b8dddddddddddddddddddddddd"})(),
        ]
    )

    monkeypatch.setattr(uuid_module, "uuid4", lambda: next(values))
    service = PatientService(JsonStore(str(tmp_path)))

    first = service.create("甲")
    second = service.create("乙")

    assert first["patient_id"] == "P-A1B2C3D4"
    assert second["patient_id"] == "P-E5F6A7B8"


def test_patient_public_shape_omits_name_history(tmp_path):
    service = make_service(tmp_path)
    patient = service.create("甲")
    renamed = service.rename(patient["patient_id"], "乙")

    assert "name_history" in renamed
    assert "name_history" not in service.to_public(renamed)


def test_create_rejects_blank_name(tmp_path):
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc:
        service.create("   ")

    assert exc.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_rename_rejects_blank_name(tmp_path):
    service = make_service(tmp_path)
    patient = service.create("张三")

    with pytest.raises(AppError) as exc:
        service.rename(patient["patient_id"], "")

    assert exc.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_mark_deleted_is_idempotent_for_404(tmp_path):
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc:
        service.mark_deleted("P-MISSING01")

    assert exc.value.code == ErrorCode.PATIENT_NOT_FOUND.code


def test_search_by_exact_patient_id(tmp_path):
    service = make_service(tmp_path)
    a = service.create("张三")
    service.create("李四")

    [match] = service.list(a["patient_id"])

    assert match["patient_id"] == a["patient_id"]


def test_create_strips_name_whitespace(tmp_path):
    service = make_service(tmp_path)

    patient = service.create("  张三  ")

    assert patient["name"] == "张三"
