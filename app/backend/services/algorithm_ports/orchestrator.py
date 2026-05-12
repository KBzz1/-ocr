from ...storage.json_store import JsonStore
from .field_extraction import validate_field_candidates


class ProcessingOrchestrator:
    def __init__(self, store: JsonStore, image_port=None, doc_port=None,
                 field_port=None, schema_validator=None):
        self._store = store
        self._image_port = image_port
        self._doc_port = doc_port
        self._field_port = field_port
        self._schema_validator = schema_validator

    def run(self, task: dict, task_service, schema: dict | None = None) -> dict:
        task_id = task["task_id"]

        # -- image processing --
        if self._image_port is None:
            return task_service.mark_failed(
                task_id, "ALGORITHM_MODULE_NOT_CONFIGURED", "图像处理模块未配置",
                stage="image_processing",
                details={"stage": "image_processing", "reason": "module_not_configured"},
            )

        image_inputs = self._build_image_inputs(task)
        if image_inputs is None:
            return task_service.mark_failed(
                task_id, "ALGORITHM_CONTRACT_INVALID", "页面元数据缺失",
                stage="image_processing",
                details={"stage": "image_processing", "reason": "page_metadata_missing"},
            )

        processed_pages = []
        for img_input in image_inputs:
            try:
                result = self._image_port.process(img_input)
            except Exception:
                return task_service.mark_failed(
                    task_id, "ALGORITHM_MODULE_FAILED", "图像处理模块异常",
                    stage="image_processing",
                    details={"stage": "image_processing", "reason": "module_exception"},
                )
            proc_path = result.get("processed_path") if isinstance(result, dict) else None
            if not proc_path or not isinstance(proc_path, str):
                return task_service.mark_failed(
                    task_id, "ALGORITHM_CONTRACT_INVALID", "图像处理模块返回缺少非空 processed_path",
                    stage="image_processing",
                    details={"stage": "image_processing", "reason": "invalid_processed_path"},
                )
            processed_pages.append({
                "page_id": img_input["page_id"],
                "page_no": img_input["page_no"],
                "processed_path": proc_path,
            })

        self._store.write(f"results/{task_id}/image_result.json", {
            "task_id": task_id, "stage": "image_processing", "status": "success",
            "pages": [{"page_id": p["page_id"], "original_path": img["original_path"],
                        "processed_path": p["processed_path"]}
                      for p, img in zip(processed_pages, image_inputs)],
        })

        # -- document parsing --
        if self._doc_port is None:
            return task_service.mark_failed(
                task_id, "ALGORITHM_MODULE_NOT_CONFIGURED", "文档解析模块未配置",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "module_not_configured"},
            )

        doc_input = {
            "task_id": task_id,
            "image_paths": [p["processed_path"] for p in processed_pages],
            "pages": [{"page_id": p["page_id"], "page_no": p["page_no"],
                        "processed_path": p["processed_path"]} for p in processed_pages],
        }
        try:
            doc_result = self._doc_port.parse(doc_input)
        except Exception:
            return task_service.mark_failed(
                task_id, "ALGORITHM_MODULE_FAILED", "文档解析模块异常",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "module_exception"},
            )

        if not isinstance(doc_result, dict) or "pages" not in doc_result or not isinstance(doc_result["pages"], list):
            return task_service.mark_failed(
                task_id, "ALGORITHM_CONTRACT_INVALID", "文档解析模块返回结构非法",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "invalid_document_result"},
            )

        pages = doc_result["pages"]
        if not pages:
            return task_service.mark_failed(
                task_id, "ALGORITHM_CONTRACT_INVALID", "文档解析结果为空",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "empty_pages"},
            )

        has_failure = any(p.get("status") == "failed" for p in pages)
        self._store.write(f"results/{task_id}/document_result.json", {
            "task_id": task_id, "stage": "document_parsing",
            "status": "success" if not has_failure else "partial_failure",
            "pages": pages, "merged_text": doc_result.get("merged_text", ""),
        })

        if has_failure:
            return task_service.mark_failed(
                task_id, "ALGORITHM_MODULE_FAILED", "部分页面解析失败",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "partial_page_failed"},
            )

        # -- field extraction --
        if self._field_port is None:
            return task_service.mark_failed(
                task_id, "ALGORITHM_MODULE_NOT_CONFIGURED", "字段抽取模块未配置",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "module_not_configured"},
            )

        if not isinstance(schema, dict):
            return task_service.mark_failed(
                task_id, "ALGORITHM_CONTRACT_INVALID", "schema 缺失或非法",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "schema_missing_or_invalid"},
            )

        field_input = {"task_id": task_id, "document_result": doc_result, "schema": schema}
        try:
            candidates = self._field_port.extract(field_input)
        except Exception:
            return task_service.mark_failed(
                task_id, "ALGORITHM_MODULE_FAILED", "字段抽取模块异常",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "module_exception"},
            )

        if not isinstance(candidates, list):
            return task_service.mark_failed(
                task_id, "ALGORITHM_CONTRACT_INVALID", "字段候选必须是列表",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "invalid_candidate_contract"},
            )
        if not candidates:
            return task_service.mark_failed(
                task_id, "ALGORITHM_CONTRACT_INVALID", "字段候选结果为空",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "empty_candidates"},
            )
        try:
            validate_field_candidates(candidates)
        except Exception:
            return task_service.mark_failed(
                task_id, "ALGORITHM_CONTRACT_INVALID", "字段候选结构非法",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "invalid_candidate_contract"},
            )

        if self._schema_validator:
            try:
                self._schema_validator(candidates, schema)
            except Exception:
                return task_service.mark_failed(
                    task_id, "ALGORITHM_CONTRACT_INVALID", "schema 校验失败",
                    stage="field_extraction",
                    details={"stage": "field_extraction", "reason": "schema_validation_failed"},
                )

        self._store.write(f"results/{task_id}/field_candidates.json", {
            "task_id": task_id, "stage": "field_extraction", "status": "success",
            "candidates": candidates,
        })

        return task_service.mark_ready(task_id)

    def _build_image_inputs(self, task: dict) -> list | None:
        session_id = task.get("session_id")
        page_order = task.get("page_order", [])
        if not session_id or not page_order:
            return None

        session = self._store.read(f"sessions/{session_id}.json")
        if session is None:
            return None

        page_by_id = {p["page_id"]: p for p in session.get("pages", [])}

        inputs = []
        for page_no, page_id in enumerate(page_order, start=1):
            session_page = page_by_id.get(page_id)
            if not session_page or not session_page.get("upload_ref"):
                return None

            meta = self._store.read(session_page["upload_ref"])
            if meta is None:
                return None

            original_path = meta.get("original_image_path")
            if not original_path:
                return None
            if not isinstance(meta.get("image_width"), int) or not isinstance(meta.get("image_height"), int):
                return None

            inputs.append({
                "task_id": task["task_id"],
                "page_id": page_id,
                "page_no": page_no,
                "original_path": original_path,
                "quad_points": meta.get("quad_points"),
                "image_width": meta["image_width"],
                "image_height": meta["image_height"],
            })
        return inputs
