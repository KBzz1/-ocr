"""复核器单测：prompt 布局、verdict 解析与映射、失败降级（fake client，不依赖真实 LLM）。"""
import json

import pytest

from app.backend.services.copd_extraction.prompts import build_verification_messages
from app.backend.services.copd_extraction.verifier import FieldVerifier, apply_verdicts


def test_verification_messages_evidence_first_fields_after():
    system, user = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "双耳粗测听力正常"}],
        fields=[{"field_key": "pe_ear", "value": "正常", "evidence_ids": ["e001"]}],
    )
    # system：身份 + 缺陷清单 + verdict 契约 + few-shot，不含数据
    assert "复核器" in system
    assert "e001" not in system and "听力正常" not in system
    assert "verdict" in system and "pass" in system and "suspicious" in system
    assert "suspicious" in system  # few-shot 覆盖 suspicious 示例
    # 校准迭代契约：证据一致性硬约束 + 找茬失败转 pass + 误报反例（仅文本契约，不含数据）
    assert "证据一致性硬约束" in system
    assert "逐字" in system
    assert "找茬失败时必须输出 pass" in system
    assert "反例" in system
    # user：evidence 编号块在字段块之前
    assert user.index("e001") < user.index("pe_ear")
    assert "pe_ear" in user and "正常" in user


class FakeLlmClient:
    def __init__(self, payload):
        self._payload = payload

    def complete_json(self, prompt: str, **kwargs):
        return json.loads(json.dumps(self._payload))


def make_candidates():
    return [
        {
            "field_key": "pe_ear", "original_value": "正常",
            "value": "正常", "status": "found",
            "evidence": [{"id": "e001", "text": "双耳粗测听力正常"}],
            "evidence_ids": ["e001"],
            "quality_flags": [], "verification_status": "not_checked",
            "attention_required": False, "attention_message": "",
        },
        {
            "field_key": "pe_nose", "original_value": "鼻腔通畅",
            "value": "鼻腔通畅", "status": "found",
            "evidence": [{"id": "e002", "text": "鼻腔通畅，各鼻窦区无压痛"}],
            "evidence_ids": ["e002"],
            "quality_flags": [], "verification_status": "not_checked",
            "attention_required": False, "attention_message": "",
        },
        {
            "field_key": "pe_mouth", "original_value": "口腔黏膜正常",
            "value": "口腔黏膜正常", "status": "not_found",
            "evidence": [], "evidence_ids": [],
            "quality_flags": [], "verification_status": "not_checked",
            "attention_required": False, "attention_message": "",
        },
        {
            "field_key": "pe_face", "original_value": "无面瘫",
            "value": "", "status": "found",
            "evidence": [{"id": "e003", "text": "无面瘫"}],
            "evidence_ids": ["e003"],
            "quality_flags": [], "verification_status": "not_checked",
            "attention_required": False, "attention_message": "",
        },
    ]


def test_verify_returns_verdicts_for_found_fields_only():
    verifier = FieldVerifier(FakeLlmClient({
        "verifications": [
            {"field_key": "pe_ear", "verdict": "pass", "reason_code": "none",
             "checks": {}, "comment": "一致"},
            {"field_key": "pe_nose", "verdict": "suspicious", "reason_code": "extraction_mistake",
             "checks": {}, "comment": "e002无异常表述，值与原文不符"},
            {"field_key": "pe_mouth", "verdict": "suspicious", "reason_code": "extraction_mistake",
             "checks": {}, "comment": "not_found 字段不应送审"},
            {"field_key": "pe_face", "verdict": "suspicious", "reason_code": "extraction_mistake",
             "checks": {}, "comment": "空值字段不应送审"},
        ]
    }))
    verdicts = verifier.verify(make_candidates(), document_text="")
    # 复核范围过滤：只返回 status=found 且 value 非空 字段的 verdict
    assert [v["field_key"] for v in verdicts] == ["pe_ear", "pe_nose"]
    assert verdicts[1]["verdict"] == "suspicious"


def test_verify_llm_failure_degrades_to_empty_verdicts():
    class BoomClient:
        def complete_json(self, prompt: str, **kwargs):
            raise RuntimeError("vLLM 不可用")

    verifier = FieldVerifier(BoomClient())
    assert verifier.verify(make_candidates(), document_text="") == []


def test_verify_non_json_output_degrades_to_empty_verdicts():
    class StringClient:
        def complete_json(self, prompt: str, **kwargs):
            return "不是 JSON"

    verifier = FieldVerifier(StringClient())
    assert verifier.verify(make_candidates(), document_text="") == []


def test_apply_verdicts_marks_suspicious_fields():
    candidates = make_candidates()
    verdicts = [
        {"field_key": "pe_ear", "verdict": "pass", "reason_code": "none", "checks": {}, "comment": "一致"},
        {"field_key": "pe_nose", "verdict": "suspicious", "reason_code": "extraction_mistake", "checks": {}, "comment": "e002无异常表述"},
    ]
    out = apply_verdicts(candidates, verdicts)
    by_key = {c["field_key"]: c for c in out}
    # pass 字段不动
    assert by_key["pe_ear"]["verification_status"] == "not_checked"
    assert by_key["pe_ear"]["attention_required"] is False
    # suspicious 字段标记
    assert by_key["pe_nose"]["verification_status"] == "suspicious"
    assert by_key["pe_nose"]["attention_required"] is True
    assert by_key["pe_nose"]["attention_message"] == "复核器标记，请核对原文"
    flags = by_key["pe_nose"]["quality_flags"]
    assert any(f["flag"] == "verifier_suspicious" for f in flags)


def test_apply_verdicts_does_not_downgrade_failed_fields():
    candidates = make_candidates()
    candidates[1]["verification_status"] = "failed"
    apply_verdicts(candidates, [
        {"field_key": "pe_nose", "verdict": "suspicious", "reason_code": "extraction_mistake", "checks": {}, "comment": "x"},
    ])
    assert candidates[1]["verification_status"] == "failed"
