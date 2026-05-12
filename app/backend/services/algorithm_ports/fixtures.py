from .image_processing import ImageProcessingPort
from .document_parsing import DocumentParsingPort
from .field_extraction import FieldExtractionPort


class FixtureImagePort(ImageProcessingPort):
    def __init__(self, processed_dir="/tmp/processed", should_fail=False,
                 return_bad_path=False):
        self._processed_dir = processed_dir
        self._should_fail = should_fail
        self._return_bad_path = return_bad_path
        self.calls = []

    def process(self, input: dict) -> dict:
        self.calls.append(input)
        if self._should_fail:
            raise RuntimeError("fixture image processing failure")
        if self._return_bad_path:
            return {"processed_path": ""}
        return {"processed_path": f"{self._processed_dir}/{input['page_id']}_processed.jpg"}


class FixtureDocPort(DocumentParsingPort):
    def __init__(self, pages=None, merged_text="merged text",
                 partial_fail_page_id=None, should_fail=False,
                 return_empty=False, return_non_dict=False,
                 return_missing_pages=False):
        self._preset_pages = pages
        self._merged_text = merged_text
        self._partial_fail_page_id = partial_fail_page_id
        self._should_fail = should_fail
        self._return_empty = return_empty
        self._return_non_dict = return_non_dict
        self._return_missing_pages = return_missing_pages
        self.calls = []

    def parse(self, input: dict) -> dict:
        self.calls.append(input)
        if self._should_fail:
            raise RuntimeError("fixture document parsing failure")
        if self._return_non_dict:
            return "not a dict"
        if self._return_missing_pages:
            return {"merged_text": self._merged_text}
        if self._return_empty:
            return {"pages": [], "merged_text": ""}
        if self._preset_pages is not None:
            return {"pages": self._preset_pages, "merged_text": self._merged_text}
        pages = []
        for p in input.get("pages", []):
            status = "failed" if p["page_id"] == self._partial_fail_page_id else "success"
            pages.append({
                "page_id": p["page_id"], "page_no": p["page_no"],
                "status": status, "text": f"text of {p['page_id']}", "blocks": [], "tables": [],
            })
        return {"pages": pages, "merged_text": self._merged_text}


class FixtureFieldPort(FieldExtractionPort):
    def __init__(self, candidates=None, should_fail=False, return_empty=False,
                 return_non_list=False, return_bad_structure=False):
        self._candidates = candidates if candidates is not None else [
            {"field_key": "chief_complaint", "original_value": "头痛3天",
             "evidence": "page 1 line 2", "confidence": 0.95},
        ]
        self._should_fail = should_fail
        self._return_empty = return_empty
        self._return_non_list = return_non_list
        self._return_bad_structure = return_bad_structure
        self.calls = []

    def extract(self, input: dict) -> list[dict]:
        self.calls.append(input)
        if self._should_fail:
            raise RuntimeError("fixture field extraction failure")
        if self._return_non_list:
            return {"not": "list"}
        if self._return_empty:
            return []
        if self._return_bad_structure:
            return [{"field_key": "k"}]
        return list(self._candidates)
