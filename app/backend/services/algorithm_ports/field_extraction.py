from ...errors import AppError, ErrorCode

EXTRACTION_STATUSES = {"extracted", "not_found", "uncertain"}
VERIFICATION_STATUSES = {"passed", "suspicious", "failed", "not_checked"}


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
        extraction_status = item.get("extraction_status")
        if extraction_status not in EXTRACTION_STATUSES:
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="extraction_status 非法")
        verification_status = item.get("verification_status")
        if verification_status not in VERIFICATION_STATUSES:
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="verification_status 非法")
        quality_flags = item.get("quality_flags")
        if not isinstance(quality_flags, list):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="quality_flags 必须是列表")
        source_section = item.get("source_section")
        if source_section is not None and not isinstance(source_section, str):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="source_section 必须是字符串或 None")
        ocr_correction = item.get("ocr_correction")
        if not isinstance(ocr_correction, dict):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="ocr_correction 必须是对象")
        if not isinstance(ocr_correction.get("applied"), bool):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="ocr_correction.applied 必须是布尔值")
        for key in ("raw", "normalized", "reason"):
            if not isinstance(ocr_correction.get(key), str):
                raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message=f"ocr_correction.{key} 必须是字符串")
        if extraction_status == "extracted" and (not original_value or not item.get("evidence")):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="extracted 字段必须包含值和 evidence")
