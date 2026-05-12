from .schema_loader import load_schema
from .schema_validator import SchemaValidator


class SchemaService:
    """持有当前 schema 路径和内存缓存。BE-06 对其他后端模块的入口。"""

    def __init__(self, schema_path: str):
        self._schema_path = schema_path
        self._cached = None

    def _ensure_loaded(self):
        if self._cached is None:
            self._cached = load_schema(self._schema_path)

    def get_current(self) -> dict:
        self._ensure_loaded()
        return self._cached

    def get_current_version(self) -> str:
        return self.get_current()["version"]

    def _iter_field_keys(self):
        for group in self.get_current()["field_groups"]:
            for field in group["fields"]:
                yield field["field_key"]

    def get_allowed_field_keys(self) -> set[str]:
        return set(self._iter_field_keys())

    def get_field_order(self) -> list[str]:
        return list(self._iter_field_keys())

    def build_validator(self) -> SchemaValidator:
        return SchemaValidator(self.get_allowed_field_keys())
