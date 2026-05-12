from ...errors import AppError, ErrorCode


class FieldExtractionPort:
    def extract(self, input: dict) -> list[dict]:
        raise NotImplementedError


def validate_field_candidates(candidates: list) -> None:
    if not isinstance(candidates, list):
        raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="字段候选必须是列表")
    for item in candidates:
        if not isinstance(item, dict):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="字段候选项必须是字典")
        field_key = item.get("field_key")
        if not isinstance(field_key, str) or field_key == "":
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="field_key 必须是非空字符串")
        original_value = item.get("original_value")
        if not isinstance(original_value, str):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="original_value 必须是字符串")
        if "confidence" in item:
            confidence = item["confidence"]
            if not isinstance(confidence, (int, float)):
                raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="confidence 必须是数字")
        if "evidence" in item and item["evidence"] is not None:
            if not isinstance(item["evidence"], str):
                raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="evidence 必须是字符串或 None")
