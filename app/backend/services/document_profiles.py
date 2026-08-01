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
    batch_excel_enabled: bool = False

    @property
    def schema_version(self) -> str:
        return str(self.schema.get("version") or "")

    @property
    def is_available(self) -> bool:
        return bool(self.document_type and self.label and self.schema_version and self.prompt_version and self.field_port is not None)


class DocumentProfileRegistry:
    def __init__(self, store: JsonStore, profiles: list[DocumentProfile], default_document_type: str):
        self._store = store
        self._profiles = {profile.document_type: profile for profile in profiles}
        self._default_document_type = default_document_type
        self._cached_default: str | None = None

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
            if profile.is_available
        ]

    def get_batch_excel_available_document_types(self) -> list[dict]:
        """仅返回显式启用批量 Excel 且已完整接入的模板。"""
        return [
            {"document_type": profile.document_type, "label": profile.label}
            for profile in self._profiles.values()
            if profile.is_available and profile.batch_excel_enabled
        ]

    def get_default_document_type(self) -> str:
        if self._cached_default is not None:
            return self._cached_default
        settings = self._store.read("settings/document_type.json") or {}
        candidate = settings.get("last_document_type")
        if candidate in self._profiles:
            self._cached_default = candidate
            return candidate
        self._cached_default = self._default_document_type
        return self._default_document_type

    def remember_last_document_type(self, document_type: str) -> None:
        self.get_profile(document_type)
        self._store.write("settings/document_type.json", {"last_document_type": document_type})
        self._cached_default = document_type

    def to_task_document_summary(self, document_type: str | None) -> dict:
        profile = self.get_profile(document_type)
        return {
            "document_type": profile.document_type,
            "document_type_label": profile.label,
            "schema_version": profile.schema_version,
            "prompt_version": profile.prompt_version,
            "extraction_profile": profile.document_type,
        }
