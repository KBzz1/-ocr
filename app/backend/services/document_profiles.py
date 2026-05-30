from dataclasses import dataclass
from typing import Any

from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


@dataclass(frozen=True)
class DocumentProfile:
    document_type: str
    label: str
    schema: dict
    prompt_version: str
    field_port: Any
    quality_rule_profile: str | None = None

    @property
    def schema_version(self) -> str:
        return str(self.schema.get("version") or "")


class DocumentProfileRegistry:
    def __init__(self, store: JsonStore, profiles: list[DocumentProfile], default_document_type: str):
        self._store = store
        self._profiles = {profile.document_type: profile for profile in profiles}
        self._default_document_type = default_document_type

    def get_profile(self, document_type: str | None) -> DocumentProfile:
        resolved = document_type or self.get_default_document_type()
        profile = self._profiles.get(resolved)
        if profile is None:
            raise AppError(
                ErrorCode.INVALID_REQUEST_PARAMS,
                message="文书模板不存在或未完成接入",
                details={"document_type": resolved},
            )
        return profile

    def get_schema(self, document_type: str | None) -> dict:
        return self.get_profile(document_type).schema

    def get_available_document_types(self) -> list[dict]:
        return [
            {
                "document_type": profile.document_type,
                "label": profile.label,
                "schema_version": profile.schema_version,
            }
            for profile in self._profiles.values()
        ]

    def get_default_document_type(self) -> str:
        settings = self._store.read("settings/document_type.json") or {}
        candidate = settings.get("last_document_type")
        if candidate in self._profiles:
            return candidate
        return self._default_document_type

    def remember_last_document_type(self, document_type: str) -> None:
        self.get_profile(document_type)
        self._store.write("settings/document_type.json", {"last_document_type": document_type})

    def to_task_document_summary(self, document_type: str | None) -> dict:
        profile = self.get_profile(document_type)
        return {
            "document_type": profile.document_type,
            "document_type_label": profile.label,
            "schema_version": profile.schema_version,
            "prompt_version": profile.prompt_version,
            "extraction_profile": profile.document_type,
        }
