from ...storage.json_store import JsonStore


class AlgorithmResultStore:
    """Persistence boundary for external algorithm intermediate results."""

    def __init__(self, store: JsonStore):
        self._store = store

    def write_image_result(self, task_id: str, pages: list[dict]) -> None:
        self._store.write(f"results/{task_id}/image_result.json", {
            "task_id": task_id,
            "stage": "image_processing",
            "status": "success",
            "pages": pages,
        })

    def write_document_result(
        self,
        task_id: str,
        pages: list[dict],
        merged_text: str,
        has_failure: bool = False,
    ) -> None:
        self._store.write(f"results/{task_id}/document_result.json", {
            "task_id": task_id,
            "stage": "document_parsing",
            "status": "partial_failure" if has_failure else "success",
            "pages": pages,
            "merged_text": merged_text,
        })

    def read_success_document_result(self, task_id: str) -> dict | None:
        result = self._store.read(f"results/{task_id}/document_result.json")
        if not isinstance(result, dict) or result.get("status") != "success":
            return None
        pages = result.get("pages")
        if not isinstance(pages, list) or not pages:
            return None
        return {"pages": pages, "merged_text": result.get("merged_text", "")}

    def write_field_candidates(self, task_id: str, candidates: list[dict]) -> None:
        self._store.write(f"results/{task_id}/field_candidates.json", {
            "task_id": task_id,
            "stage": "field_extraction",
            "status": "success",
            "candidates": candidates,
        })
