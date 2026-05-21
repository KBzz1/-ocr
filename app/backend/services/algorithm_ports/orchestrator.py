from ...errors import ErrorCode
from ...storage.json_store import JsonStore
from .field_extraction import validate_field_candidates
from .results import AlgorithmResultStore


def _all_field_results_empty(candidates: list[dict]) -> bool:
    return all(not (item.get("original_value") or "").strip() for item in candidates)


class ProcessingOrchestrator:
    def __init__(
        self,
        store: JsonStore,
        result_store=None,
        image_port=None,
        doc_port=None,
        field_port=None,
        schema_validator=None,
    ):
        self._store = store
        self._result_store = result_store or AlgorithmResultStore(store)
        self._image_port = image_port
        self._doc_port = doc_port
        self._field_port = field_port
        self._schema_validator = schema_validator

    def run(self, task: dict, task_service, schema: dict | None = None) -> dict:
        task_id = task["task_id"]

        # -- image processing --
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
        for img_input in image_inputs:
            try:
                result = self._image_port.process(img_input)
            except Exception:
                return task_service.mark_failed(
                    task_id, ErrorCode.ALGORITHM_MODULE_FAILED.code,
                    "图像处理模块异常",
                    stage="image_processing",
                    details={"stage": "image_processing", "reason": "module_exception"},
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

        self._result_store.write_image_result(
            task_id,
            [{"page_id": p["page_id"], "original_path": img["original_path"],
              "processed_path": p["processed_path"]}
             for p, img in zip(processed_pages, image_inputs)],
        )

        # -- document parsing --
        if self._doc_port is None:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_MODULE_NOT_CONFIGURED.code,
                "文档解析模块未配置",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "module_not_configured"},
            )

        doc_input = {
            "task_id": task_id,
            "image_paths": [p["processed_path"] for p in processed_pages],
            "pages": [{"page_id": p["page_id"], "page_no": p["page_no"],
                        "source_image_path": p["original_path"],
                        "processed_path": p["processed_path"]} for p in processed_pages],
        }
        try:
            doc_result = self._doc_port.parse(doc_input)
        except Exception:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_MODULE_FAILED.code,
                "文档解析模块异常",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "module_exception"},
            )

        if not isinstance(doc_result, dict) or "pages" not in doc_result or not isinstance(doc_result["pages"], list):
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "文档解析模块返回结构非法",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "invalid_document_result"},
            )

        pages = doc_result["pages"]
        if not pages:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "文档解析结果为空",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "empty_pages"},
            )

        has_failure = any(p.get("status") == "failed" for p in pages)
        self._result_store.write_document_result(
            task_id,
            pages,
            doc_result.get("merged_text", ""),
            has_failure=has_failure,
        )

        if has_failure:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_MODULE_FAILED.code,
                "部分页面解析失败",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "partial_page_failed"},
            )

        # -- field extraction --
        if self._field_port is None:
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

        field_input = {"task_id": task_id, "document_result": doc_result, "schema": schema}
        try:
            candidates = self._field_port.extract(field_input)
        except Exception:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_MODULE_FAILED.code,
                "字段抽取模块异常",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "module_exception"},
            )

        if not isinstance(candidates, list):
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "字段候选必须是列表",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "invalid_candidate_contract"},
            )
        if not candidates or _all_field_results_empty(candidates):
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "字段结果为空",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "empty_field_results"},
            )
        try:
            validate_field_candidates(candidates)
        except Exception:
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "字段候选结构非法",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "invalid_candidate_contract"},
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

        self._result_store.write_field_candidates(task_id, candidates)

        return task_service.mark_ready(task_id)

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
