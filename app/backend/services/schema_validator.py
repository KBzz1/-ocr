class SchemaValidationError(ValueError):
    """SchemaValidator 白名单校验失败。由 BE-05 捕获并映射为任务 failed。"""
    pass


class SchemaValidator:
    """只做 schema 白名单契约校验。不生成、补齐、排序或改写字段值。"""

    def __init__(self, allowed_field_keys: set[str]):
        self._allowed = allowed_field_keys

    def validate(self, candidates: list[dict], schema: dict | None = None) -> list[dict]:
        """BE-05 orchestrator 注入调用入口；schema 参数只为签名兼容，不读取或改写。"""
        return self.validate_candidates(candidates)

    def validate_candidates(self, candidates: list[dict]) -> list[dict]:
        if not candidates:
            raise SchemaValidationError("候选字段列表为空")

        seen_keys = set()
        for candidate in candidates:
            field_key = candidate.get("field_key")
            if not field_key:
                raise SchemaValidationError("候选字段缺少 field_key")
            if field_key not in self._allowed:
                raise SchemaValidationError(
                    f"候选字段 {field_key} 不在 schema 中")
            if field_key in seen_keys:
                raise SchemaValidationError(
                    f"候选字段 {field_key} 重复")
            seen_keys.add(field_key)

        return candidates
