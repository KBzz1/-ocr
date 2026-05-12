class SchemaValidationError(ValueError):
    pass


class SchemaValidator:
    def __init__(self, allowed_field_keys: set[str]):
        self._allowed = allowed_field_keys
