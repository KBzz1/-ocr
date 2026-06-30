import logging

from ...errors import ErrorCode
from ...routes import _safe_event
from ...storage.json_store import JsonStore
from .field_extraction import all_fields_empty, validate_field_candidates
from .evidence_units import build_evidence_units
from .results import AlgorithmResultStore

logger = logging.getLogger(__name__)


class ProcessingOrchestrator:
    def __init__(
        self,
        store: JsonStore,
        result_store=None,
        image_port=None,
        doc_port=None,
        field_port=None,
        schema_validator=None,
        field_port_registry=None,
        gpu_stage_queue=None,
    ):
        self._store = store
        self._result_store = result_store or AlgorithmResultStore(store)
        self._image_port = image_port
        self._doc_port = doc_port
        self._field_port = field_port
        self._schema_validator = schema_validator
        self._field_port_registry = field_port_registry or {}
        self._gpu_stage_queue = gpu_stage_queue

    def _resolve_field_port(self, document_type):
        if self._field_port_registry:
            if document_type and document_type in self._field_port_registry:
                return self._field_port_registry[document_type]
            return None
        return self._field_port

    def run(self, task: dict, task_service, schema: dict | None = None) -> dict:
        task_id = task["task_id"]

        # -- image processing --
        if self._is_cancelled(task_service, task_id):
            return task_service.get_task(task_id)
        if self._image_port is None:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_MODULE_NOT_CONFIGURED.code,
                "图像处理模块未配置",
                stage="image_processing",
                details={"stage": "image_processing", "reason": "module_not_configured"},
            )

        image_inputs = self._build_image_inputs(task)
        if image_inputs is None:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "页面元数据缺失",
                stage="image_processing",
                details={"stage": "image_processing", "reason": "page_metadata_missing"},
            )

        processed_pages = []
        self._stage_started(task_service, task_id, "image_processing", len(image_inputs))
        for img_input in image_inputs:
            if self._is_cancelled(task_service, task_id):
                return task_service.get_task(task_id)
            try:
                result = self._image_port.process(img_input)
            except Exception as exc:
                return task_service.mark_failed(
                    task_id, ErrorCode.ALGORITHM_MODULE_FAILED.code,
                    "图像处理模块异常",
                    stage="image_processing",
                    details={**self._exception_details(exc), "stage": "image_processing", "reason": "module_exception"},
                )
            proc_path = result.get("processed_path") if isinstance(result, dict) else None
            if not proc_path or not isinstance(proc_path, str):
                return task_service.mark_failed(
                    task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                    "图像处理模块返回缺少非空 processed_path",
                    stage="image_processing",
                    details={"stage": "image_processing", "reason": "invalid_processed_path"},
                )
            processed_pages.append({
                "page_id": img_input["page_id"],
                "page_no": img_input["page_no"],
                "original_path": img_input["original_path"],
                "processed_path": proc_path,
            })
        self._stage_finished(task_id, "image_processing", len(processed_pages), "success")

        self._result_store.write_image_result(
            task_id,
            [{"page_id": p["page_id"], "original_path": img["original_path"],
              "processed_path": p["processed_path"]}
             for p, img in zip(processed_pages, image_inputs)],
        )

        # -- document parsing + field extraction (single GPU stage when no cached OCR) --
        if self._is_cancelled(task_service, task_id):
            return task_service.get_task(task_id)
        if self._doc_port is None:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_MODULE_NOT_CONFIGURED.code,
                "文档解析模块未配置",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "module_not_configured"},
            )

        cached_doc_result = self._result_store.read_success_document_result(task_id)
        if cached_doc_result is not None:
            # 重试已有合法 OCR 结果：只持有 field_extraction 阶段。
            doc_result = cached_doc_result
            if not isinstance(doc_result, dict) or "pages" not in doc_result or not isinstance(doc_result["pages"], list):
                return task_service.mark_failed(
                    task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                    "缓存的文档解析模块返回结构非法",
                    stage="document_parsing",
                    details={"stage": "document_parsing", "reason": "invalid_document_result"},
                )
            pages = doc_result["pages"]
            if not pages:
                return task_service.mark_failed(
                    task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                    "缓存的文档解析结果为空",
                    stage="document_parsing",
                    details={"stage": "document_parsing", "reason": "empty_pages"},
                )
            evidence_units = doc_result.get("evidence_units")
            if not isinstance(evidence_units, list):
                evidence_units = build_evidence_units(doc_result)
            return self._run_field_extraction(
                task, task_service, schema, doc_result, evidence_units, pages,
            )

        # OCR + 字段抽取连续持有 `qwen_ocr_and_extraction` GPU 阶段。
        # 在同一上下文里完成 OCR、document_result 持久化、evidence_units 生成
        # 与字段抽取，确保 8GB 显存下其他任务不能在这两个模型调用之间插队。
        doc_input = {
            "task_id": task_id,
            "image_paths": [p["processed_path"] for p in processed_pages],
            "pages": [{"page_id": p["page_id"], "page_no": p["page_no"],
                        "source_image_path": p["original_path"],
                        "processed_path": p["processed_path"]} for p in processed_pages],
            "is_cancelled": lambda: self._is_cancelled(task_service, task_id),
        }
        # 在 GPU 阶段进入前先做轻量校验（schema/field_port 缺失/取消）
        early_exit = self._pre_check_field_stage(task, task_service, schema)
        if early_exit is not None:
            return early_exit

        try:
            self._stage_started(task_service, task_id, "document_parsing", len(processed_pages))
            with self._gpu_stage(task_id, "qwen_ocr_and_extraction"):
                doc_result = self._doc_port.parse(doc_input)
                doc_validation_failed = self._validate_doc_result_or_fail(
                    task_id, doc_result, task_service,
                )
                if doc_validation_failed is not None:
                    return doc_validation_failed
                pages = doc_result["pages"]
                has_failure = any(p.get("status") == "failed" for p in pages)
                if not _has_successful_ocr_text(doc_result):
                    return task_service.mark_failed(
                        task_id, ErrorCode.ALGORITHM_MODULE_FAILED.code,
                        "所有页面 OCR 文本为空",
                        stage="document_parsing",
                        details={"stage": "document_parsing", "reason": "all_pages_empty"},
                    )
                evidence_units = build_evidence_units(doc_result)
                self._result_store.write_document_result(
                    task_id,
                    pages,
                    doc_result.get("merged_text", ""),
                    has_failure=has_failure,
                    evidence_units=evidence_units,
                )
                doc_result["evidence_units"] = evidence_units
                # 字段抽取在同一 GPU 阶段内继续执行：保持连续持有
                self._stage_started(task_service, task_id, "field_extraction", len(pages))
                field_result = self._run_field_extraction_in_stage(
                    task, task_service, schema, doc_result, evidence_units, pages,
                )
                if isinstance(field_result, dict) and field_result.get("status") == "failed":
                    return field_result
            self._stage_finished(task_id, "document_parsing", len(processed_pages), "success")
            self._stage_finished(task_id, "field_extraction", len(pages), "success")
        except Exception as exc:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_MODULE_FAILED.code,
                "文档解析模块异常",
                stage="document_parsing",
                details={**self._exception_details(exc), "stage": "document_parsing", "reason": "module_exception"},
            )

        return field_result

    def _pre_check_field_stage(self, task, task_service, schema):
        task_id = task["task_id"]
        if self._is_cancelled(task_service, task_id):
            return task_service.get_task(task_id)
        field_port = self._resolve_field_port(task.get("document_type"))
        if field_port is None:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_MODULE_NOT_CONFIGURED.code,
                "字段抽取模块未配置",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "module_not_configured"},
            )
        if not isinstance(schema, dict):
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "schema 缺失或非法",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "schema_missing_or_invalid"},
            )
        return None

    def _run_field_extraction_in_stage(
        self,
        task: dict,
        task_service,
        schema: dict | None,
        doc_result: dict,
        evidence_units: list,
        pages: list,
    ) -> dict:
        task_id = task["task_id"]
        field_port = self._resolve_field_port(task.get("document_type"))
        if field_port is None:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_MODULE_NOT_CONFIGURED.code,
                "字段抽取模块未配置",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "module_not_configured"},
            )
        field_input = {
            "task_id": task_id,
            "document_type": task.get("document_type"),
            "document_result": doc_result,
            "evidence_units": evidence_units,
            "schema": schema,
            "prompt_version": task.get("prompt_version"),
        }
        try:
            candidates = field_port.extract(field_input)
        except Exception as exc:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_MODULE_FAILED.code,
                "字段抽取模块异常",
                stage="field_extraction",
                details={**self._exception_details(exc), "stage": "field_extraction", "reason": "module_exception"},
            )
        return self._finalize_field_extraction(
            task, task_service, schema, candidates,
        )

    def _validate_doc_result_or_fail(self, task_id, doc_result, task_service):
        if not isinstance(doc_result, dict) or "pages" not in doc_result or not isinstance(doc_result["pages"], list):
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "文档解析模块返回结构非法",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "invalid_document_result"},
            )
        if not doc_result["pages"]:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "文档解析结果为空",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "empty_pages"},
            )
        return None

    def _run_field_extraction(
        self,
        task: dict,
        task_service,
        schema: dict | None,
        doc_result: dict,
        evidence_units: list,
        pages: list,
    ) -> dict:
        task_id = task["task_id"]
        if self._is_cancelled(task_service, task_id):
            return task_service.get_task(task_id)
        field_port = self._resolve_field_port(task.get("document_type"))
        if field_port is None:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_MODULE_NOT_CONFIGURED.code,
                "字段抽取模块未配置",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "module_not_configured"},
            )

        if not isinstance(schema, dict):
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "schema 缺失或非法",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "schema_missing_or_invalid"},
            )

        field_input = {
            "task_id": task_id,
            "document_type": task.get("document_type"),
            "document_result": doc_result,
            "evidence_units": evidence_units,
            "schema": schema,
            "prompt_version": task.get("prompt_version"),
        }
        try:
            self._stage_started(task_service, task_id, "field_extraction", len(pages))
            with self._gpu_stage(task_id, "field_extraction"):
                candidates = field_port.extract(field_input)
        except Exception as exc:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_MODULE_FAILED.code,
                "字段抽取模块异常",
                stage="field_extraction",
                details={**self._exception_details(exc), "stage": "field_extraction", "reason": "module_exception"},
            )
        self._stage_finished(task_id, "field_extraction", len(pages), "success")

        return self._finalize_field_extraction(task, task_service, schema, candidates)

    def _finalize_field_extraction(
        self,
        task: dict,
        task_service,
        schema: dict | None,
        candidates,
    ) -> dict:
        task_id = task["task_id"]
        if not isinstance(candidates, list):
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "字段候选必须是列表",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "invalid_candidate_contract"},
            )
        if not candidates or all_fields_empty(candidates):
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "字段结果为空",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "empty_field_results"},
            )
        try:
            validate_field_candidates(candidates)
        except Exception as exc:
            logger.error("task=%s validate_field_candidates failed: %s", task_id, exc)
            _log_candidates_summary(task_id, candidates)
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "字段候选结构非法",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "invalid_candidate_contract",
                         "validation_error": str(exc)},
            )

        if self._schema_validator:
            try:
                if hasattr(self._schema_validator, "validate"):
                    self._schema_validator.validate(candidates, schema)
                else:
                    self._schema_validator(candidates, schema)
            except Exception:
                return task_service.mark_failed(
                    task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                    "schema 校验失败",
                    stage="field_extraction",
                    details={"stage": "field_extraction", "reason": "schema_validation_failed"},
                )

        self._result_store.write_field_candidates(task_id, candidates, schema)

        return task_service.mark_ready(task_id)

    def _is_cancelled(self, task_service, task_id: str) -> bool:
        if not hasattr(task_service, "is_processing_cancelled"):
            return False
        return task_service.is_processing_cancelled(task_id)

    def _gpu_stage(self, task_id: str, stage: str):
        if self._gpu_stage_queue is None:
            return _NoopContext()
        return self._gpu_stage_queue.stage(task_id=task_id, stage=stage)

    def _build_image_inputs(self, task: dict) -> list | None:
        images = task.get("images") or []
        if not images:
            return None

        inputs = []
        for image in sorted(images, key=lambda item: item["page_no"]):
            original_path = image.get("original_image_path")
            if not original_path:
                return None
            inputs.append(
                {
                    "task_id": task["task_id"],
                    "page_id": image["page_id"],
                    "page_no": image["page_no"],
                    "original_path": original_path,
                    "image_width": image.get("image_width"),
                    "image_height": image.get("image_height"),
                }
            )
        return inputs

    def _stage_started(self, task_service, task_id: str, stage: str, page_count: int) -> None:
        task_service.mark_processing_stage(task_id, stage, "running", page_count=page_count)
        _safe_event("processing_stage_started", task_id=task_id, stage=stage, page_count=page_count)

    def _stage_finished(self, task_id: str, stage: str, page_count: int, status: str) -> None:
        _safe_event("processing_stage_finished", task_id=task_id, stage=stage, page_count=page_count, status=status)

    def _exception_details(self, exc: Exception) -> dict:
        message = str(exc)
        if len(message) > 500:
            message = message[:500] + "...[truncated]"
        return {"exception_type": type(exc).__name__, "exception_message": message}


def _log_candidates_summary(task_id: str, candidates: list) -> None:
    """记录 candidates 结构摘要，用于排查字段候选校验失败。"""
    try:
        for item in candidates:
            if not isinstance(item, dict):
                logger.error("task=%s candidate not dict: %s", task_id, type(item).__name__)
                continue
            fk = item.get("field_key", "?")
            issues = []
            for key in ("quality_flags", "verification_status", "ocr_correction",
                        "extraction_status", "original_value", "evidence", "confidence", "source_section"):
                val = item.get(key, "<missing>")
                issues.append(f"{key}={type(val).__name__}:{repr(val)[:80]}")
            logger.error("task=%s field=%s %s", task_id, fk, " | ".join(issues))
    except Exception:
        logger.exception("task=%s failed to log candidates summary", task_id)


class _NoopContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


def _has_successful_ocr_text(doc_result: dict) -> bool:
    merged_text = doc_result.get("merged_text")
    if isinstance(merged_text, str) and merged_text.strip():
        return True
    pages = doc_result.get("pages") or []
    for page in pages:
        if page.get("status") == "success" and isinstance(page.get("text"), str) and page["text"].strip():
            return True
    return False
