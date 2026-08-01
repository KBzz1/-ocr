"""审核数据回流：回流文件 → 脱敏 → 金标活资产（source: review），及评估加载。"""
import json
from pathlib import Path

from .desensitize import desensitize_text


def build_review_golden(feedback_dir: Path, golden_dir: Path, task_id: str) -> Path:
    """读回流文件，脱敏后写金标活资产（增量修正字段，不要求 61 字段全量）。"""
    feedback_path = feedback_dir / f"{task_id}.json"
    feedback = json.loads(feedback_path.read_text(encoding="utf-8"))
    fields = []
    for item in feedback.get("fields", []):
        value = desensitize_text(item.get("corrected_value") or "")
        fields.append({
            "field_key": item.get("field_key", ""),
            "status": item.get("status", "found"),
            "value": value,
        })
    golden = {
        "case_id": task_id,
        "source": "review",
        "schema_version": feedback.get("schema_version"),
        "golden": fields,
    }
    golden_dir.mkdir(parents=True, exist_ok=True)
    path = golden_dir / f"{task_id}.json"
    path.write_text(json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_review_golden(golden_dir: Path) -> list[dict]:
    """加载 review 活资产为评估样本（ocr_text 留空，只按修正字段子集统计）。"""
    samples = []
    for path in sorted(golden_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("source") != "review":
            continue
        samples.append({
            "case_id": data.get("case_id", path.stem),
            "ocr_text": data.get("ocr_text", ""),
            "pitfalls": ["review_feedback"],
            "golden": data.get("golden", []),
        })
    return samples
