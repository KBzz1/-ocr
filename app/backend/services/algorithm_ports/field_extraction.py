import logging

from ...errors import AppError, ErrorCode

EXTRACTION_STATUSES = {"extracted", "not_found", "uncertain"}
VERIFICATION_STATUSES = {"passed", "suspicious", "failed", "not_checked"}

logger = logging.getLogger(__name__)


def all_fields_empty(candidates: list[dict]) -> bool:
    return all(
        item.get("extraction_status") != "uncertain"
        and not (item.get("original_value") or "").strip()
        for item in candidates
    )


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
        fk = field_key
        original_value = item.get("original_value")
        if not isinstance(original_value, str):
            logger.error("field=%s original_value type=%s value=%s", fk, type(original_value).__name__, repr(original_value))
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message=f"field_key={fk}: original_value 必须是字符串，实际为 {type(original_value).__name__}")
        if "confidence" in item:
            confidence = item["confidence"]
            if not isinstance(confidence, (int, float)):
                logger.error("field=%s confidence type=%s value=%s", fk, type(confidence).__name__, repr(confidence))
                raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message=f"field_key={fk}: confidence 必须是数字，实际为 {type(confidence).__name__}")
        if "evidence" in item and item["evidence"] is not None:
            if not isinstance(item["evidence"], str):
                logger.error("field=%s evidence type=%s value=%s", fk, type(item["evidence"]).__name__, repr(item["evidence"]))
                raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message=f"field_key={fk}: evidence 必须是字符串或 None，实际为 {type(item['evidence']).__name__}")
        extraction_status = item.get("extraction_status")
        if extraction_status not in EXTRACTION_STATUSES:
            logger.error("field=%s extraction_status=%s", fk, repr(extraction_status))
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message=f"field_key={fk}: extraction_status 非法，实际为 {repr(extraction_status)}")
        verification_status = item.get("verification_status")
        if verification_status not in VERIFICATION_STATUSES:
            logger.error("field=%s verification_status=%s", fk, repr(verification_status))
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message=f"field_key={fk}: verification_status 非法，实际为 {repr(verification_status)}")
        quality_flags = item.get("quality_flags")
        if not isinstance(quality_flags, list):
            logger.error("field=%s quality_flags type=%s value=%s", fk, type(quality_flags).__name__, repr(quality_flags))
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message=f"field_key={fk}: quality_flags 必须是列表，实际为 {type(quality_flags).__name__}")
        source_section = item.get("source_section")
        if source_section is not None and not isinstance(source_section, str):
            logger.error("field=%s source_section type=%s value=%s", fk, type(source_section).__name__, repr(source_section))
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message=f"field_key={fk}: source_section 必须是字符串或 None，实际为 {type(source_section).__name__}")
        ocr_correction = item.get("ocr_correction")
        if not isinstance(ocr_correction, dict):
            logger.error("field=%s ocr_correction type=%s value=%s", fk, type(ocr_correction).__name__, repr(ocr_correction))
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message=f"field_key={fk}: ocr_correction 必须是对象，实际为 {type(ocr_correction).__name__}")
        if not isinstance(ocr_correction.get("applied"), bool):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message=f"field_key={fk}: ocr_correction.applied 必须是布尔值")
        for key in ("raw", "normalized", "reason"):
            if not isinstance(ocr_correction.get(key), str):
                raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message=f"field_key={fk}: ocr_correction.{key} 必须是字符串")
        if extraction_status == "extracted" and (not original_value or not item.get("evidence")):
            logger.error("field=%s extracted but missing value/evidence: value=%s evidence=%s", fk, repr(original_value), repr(item.get("evidence")))
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message=f"field_key={fk}: extracted 字段必须包含值和 evidence")
