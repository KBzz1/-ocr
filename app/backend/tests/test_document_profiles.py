import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.document_profiles import DocumentProfile, DocumentProfileRegistry
from app.backend.storage.json_store import JsonStore


class FakeFieldPort:
    def extract(self, input):
        return []


def make_profile(document_type="copd_admission_record", label="入院记录"):
    return DocumentProfile(
        document_type=document_type,
        label=label,
        schema={"version": f"{document_type}.v1", "document_type": document_type, "field_groups": []},
        prompt_version=f"{document_type}.prompt.v1",
        field_port=FakeFieldPort(),
        quality_rule_profile=document_type,
    )


def test_registry_lists_only_registered_profiles(tmp_path):
    registry = DocumentProfileRegistry(
        store=JsonStore(str(tmp_path)),
        profiles=[make_profile()],
        default_document_type="copd_admission_record",
    )

    assert registry.get_available_document_types() == [
        {
            "document_type": "copd_admission_record",
            "label": "入院记录",
            "schema_version": "copd_admission_record.v1",
        }
    ]


def test_registry_remembers_last_document_type(tmp_path):
    registry = DocumentProfileRegistry(
        store=JsonStore(str(tmp_path)),
        profiles=[
            make_profile("copd_admission_record", "入院记录"),
            make_profile("progress_note", "病程记录"),
        ],
        default_document_type="copd_admission_record",
    )

    registry.remember_last_document_type("progress_note")

    assert registry.get_default_document_type() == "progress_note"
    assert JsonStore(str(tmp_path)).read("settings/document_type.json")["last_document_type"] == "progress_note"


def test_registry_rejects_unknown_document_type(tmp_path):
    registry = DocumentProfileRegistry(
        store=JsonStore(str(tmp_path)),
        profiles=[make_profile()],
        default_document_type="copd_admission_record",
    )

    with pytest.raises(AppError) as exc:
        registry.get_profile("progress_note")

    assert exc.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code
    assert exc.value.details["document_type"] == "progress_note"


def test_registry_hides_incomplete_profiles_from_mobile_choices(tmp_path):
    registry = DocumentProfileRegistry(
        store=JsonStore(str(tmp_path)),
        profiles=[
            make_profile(),
            DocumentProfile(
                document_type="progress_note",
                label="病程记录",
                schema={"version": "progress_note.v1", "document_type": "progress_note", "field_groups": []},
                prompt_version="progress_note.prompt.v1",
                field_port=None,
            ),
        ],
        default_document_type="copd_admission_record",
    )

    assert registry.get_available_document_types() == [
        {
            "document_type": "copd_admission_record",
            "label": "入院记录",
            "schema_version": "copd_admission_record.v1",
        }
    ]
