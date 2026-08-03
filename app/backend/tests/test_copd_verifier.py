"""复核器单测：prompt 布局、verdict 解析与映射、失败降级（fake client，不依赖真实 LLM）。"""
import json

import pytest

from app.backend.services.copd_extraction.prompts import build_verification_messages
from app.backend.services.copd_extraction.verifier import FieldVerifier, apply_verdicts


def test_verification_messages_claim_manifest_keeps_evidence_once():
    """复核 claim 使用 JSON，长证据正文只在证据区出现一次。"""
    long_value = "唇色发绀。" + "口腔粘膜无溃疡，张口正常。" * 12
    system, user = build_verification_messages(
        evidence_units=[{"id": "e001", "text": long_value}],
        fields=[
            {"field_key": "pe_oral", "value": long_value, "evidence_ids": ["e001"]},
            {"field_key": "pe_short", "value": "正常", "evidence_ids": ["e001"]},
        ],
    )
    assert '"claims"' in user
    assert '"field_key":"pe_oral"' in user
    assert '"value":"正常"' in user
    # 长文本作为 claim value 本身出现一次，证据正文出现一次；没有第三份
    # cited_text 或按值重新定位的证据副本。
    assert user.count(long_value) == 2
    assert "cited_text" not in user
    assert "value 超过 40 字时，按逗号、顿号补充拆分" in system


def test_verification_messages_evidence_first_fields_after():
    system, user = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "双耳粗测听力正常"}],
        fields=[{"field_key": "pe_ear", "value": "正常", "evidence_ids": ["e001"]}],
    )
    # system：身份/任务 + 审核顺序 + 裁定边界，不含输入数据（证据 ID 与请求文本）
    assert "复核器" in system
    assert "e001" not in system and "双耳粗测听力正常" not in system
    assert "verdict" in system and "pass" in system and "suspicious" in system
    assert "suspicious" in system  # few-shot 覆盖 suspicious 示例
    # user：evidence 块在 claims JSON 之前，证据 ID 保留原样
    assert user.index("<evidence>") < user.index("<claims>")
    assert '"field_key":"pe_ear"' in user and '"value":"正常"' in user


def test_verification_messages_general_principle_field_boundary():
    """通用原则新增字段越界一句：内容域与字段对应部位明显不符 → extraction_mistake。"""
    system, _ = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "双耳粗测听力正常"}],
        fields=[{"field_key": "pe_ear", "value": "正常", "evidence_ids": ["e001"]}],
    )
    assert "字段越界" in system
    assert "extraction_mistake" in system


def test_verification_messages_append_reminder_default_absent():
    """变体 A：默认（append_reminder=False）时 system 与 user 均无提醒句。"""
    system, user = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "双耳粗测听力正常"}],
        fields=[{"field_key": "pe_ear", "value": "正常", "evidence_ids": ["e001"]}],
    )
    assert "请严格遵守" not in user
    assert "请严格遵守" not in system


def test_verification_messages_append_reminder_true_appends_at_user_end():
    """变体 B：append_reminder=True 时提醒句恰好出现一次且位于 user 末尾，system 不含提醒句。"""
    reminder = "再次检查：每个 verdict 的 field_key 必须来自 claims，引用必须来自上面的 [uXXX]。"
    system, user = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "双耳粗测听力正常"}],
        fields=[{"field_key": "pe_ear", "value": "正常", "evidence_ids": ["e001"]}],
        append_reminder=True,
    )
    assert user.endswith(reminder)
    assert user.count(reminder) == 1
    assert "请严格遵守" not in system


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
            "evidence": [{"id": "u001", "text": "双耳粗测听力正常"}],
            "evidence_ids": ["u001"],
            "quality_flags": [], "verification_status": "not_checked",
            "attention_required": False, "attention_message": "",
        },
        {
            "field_key": "pe_nose", "original_value": "鼻腔通畅",
            "value": "鼻腔通畅", "status": "found",
            "evidence": [{"id": "u002", "text": "鼻腔通畅，各鼻窦区无压痛"}],
            "evidence_ids": ["u002"],
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
            "evidence": [{"id": "u003", "text": "无面瘫"}],
            "evidence_ids": ["u003"],
            "quality_flags": [], "verification_status": "not_checked",
            "attention_required": False, "attention_message": "",
        },
    ]


def test_verify_returns_verdicts_for_found_fields_only():
    verifier = FieldVerifier(FakeLlmClient({
        "verifications": [
            {"field_key": "pe_ear", "verdict": "pass", "reason_code": "none",
             "checks": {"grounding_supported": True, "field_scope_valid": True,
                        "text_standard": True, "logic_consistent": True},
             "comment": "一致"},
            {"field_key": "pe_nose", "verdict": "suspicious", "reason_code": "extraction_mistake",
             "checks": {"grounding_supported": False, "field_scope_valid": True,
                        "text_standard": True, "logic_consistent": True},
             "comment": "u002无异常表述，值与原文不符"},
        ]
    }))
    verdicts = verifier.verify(make_candidates(), document_text="")
    # 复核范围过滤：只返回 status=found 且 value 非空 字段的 verdict
    assert [v["field_key"] for v in verdicts] == ["pe_ear", "pe_nose"]
    assert verdicts[1]["verdict"] == "suspicious"


def test_verifier_threads_append_reminder_into_user_message():
    """FieldVerifier(append_reminder=...) 透传两态：True 时 user 尾部含提醒句，False 时无；system 两态一致。"""
    calls = []

    class RecordingClient:
        def complete_json(self, prompt: str, system_prompt=None):
            calls.append((prompt, system_prompt))
            return {"verifications": []}

    on = FieldVerifier(RecordingClient(), append_reminder=True)
    assert on.verify(make_candidates(), document_text="") == []
    off = FieldVerifier(RecordingClient(), append_reminder=False)
    assert off.verify(make_candidates(), document_text="") == []
    reminder = "再次检查：每个 verdict 的 field_key 必须来自 claims，引用必须来自上面的 [uXXX]。"
    assert calls[0][0].endswith(reminder)
    assert "请严格遵守" not in calls[1][0]
    assert calls[0][1] == calls[1][1]  # system 不受提醒开关影响


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


def test_verifier_principle_threshold_for_expression_noise():
    system, _ = build_verification_messages([], [])
    assert "可定位的非标准表述" in system


def test_verifier_principle_logic_consistency():
    system, _ = build_verification_messages([], [])
    assert "数值关系" in system
    assert "否定翻转" in system


def test_verifier_principle_boundary_no_evidence_exemption():
    system, _ = build_verification_messages([], [])
    assert "原文支持但字段越界仍应标记" in system


def test_verifier_fewshot_recall_examples_present():
    system, _ = build_verification_messages([], [])
    assert "pe_eyes" in system and "pe_respiratory_exam" in system
    assert "示例仅展示结构与裁定边界" in system


class _RecordingClient:
    """记录每次调用 (user, system_prompt)，按序返回预设响应；raise 抛错模拟单组失败。"""
    def __init__(self, responses, fail_at=None):
        self.responses = list(responses)
        self.fail_at = fail_at
        self.calls = []
    def complete_json(self, user, system_prompt=None, **kwargs):
        self.calls.append((user, system_prompt))
        idx = len(self.calls) - 1
        if self.fail_at is not None and idx in self.fail_at:
            raise RuntimeError("模拟失败")
        return self.responses.pop(0)

def _mk_field(fk, value, units, section=None):
    return {
        "field_key": fk, "status": "found", "value": value,
        "evidence_ids": [u["id"] for u in units],
        "evidence": [dict(u, section_key=section) for u in units] if section else [dict(u) for u in units],
    }

def _mk_unit(uid, text):
    return {"id": uid, "text": text}

def test_verify_group_by_field_one_request_per_field():
    units = [_mk_unit("u001", "体温36.5℃，脉搏88次/分。")]
    candidates = [
        _mk_field("pe_temperature", "36.5℃", [units[0]]),
        _mk_field("pe_pulse", "88次/分", [units[0]]),
    ]
    client = _RecordingClient([
        {"verifications": [{"field_key": "pe_temperature", "verdict": "pass", "reason_code": "none",
          "checks": {"grounding_supported": True, "field_scope_valid": True, "text_standard": True, "logic_consistent": True}, "comment": "一致"}]},
        {"verifications": [{"field_key": "pe_pulse", "verdict": "pass", "reason_code": "none",
          "checks": {"grounding_supported": True, "field_scope_valid": True, "text_standard": True, "logic_consistent": True}, "comment": "一致"}]},
    ])
    verifier = FieldVerifier(client)
    result = verifier.verify(candidates, document_text="全文", group_by="field")
    assert len(client.calls) == 2
    # 每条请求的字段声称值只含自己字段的值，不含其他字段
    # （两字段共享同一证据单元 u001，其原文文本可合法出现于任一组证据块）
    assert '"value":"36.5℃"' in client.calls[0][0] and '"value":"88次/分"' not in client.calls[0][0]
    assert '"value":"88次/分"' in client.calls[1][0] and '"value":"36.5℃"' not in client.calls[1][0]
    # system 逐字节相同
    assert client.calls[0][1] == client.calls[1][1]
    assert len(result) == 2

def test_verify_group_by_section_groups_same_section():
    units = [_mk_unit("u001", "颈部：颈软，气管居中。"), _mk_unit("u002", "胸部：胸廓对称。")]
    candidates = [
        _mk_field("pe_neck", "颈软", [units[0]], section="physical_examination"),
        _mk_field("pe_chest", "胸廓对称", [units[1]], section="physical_examination"),
    ]
    client = _RecordingClient([
        {"verifications": [
            {"field_key": "pe_neck", "verdict": "pass", "reason_code": "none",
             "checks": {"grounding_supported": True, "field_scope_valid": True, "text_standard": True, "logic_consistent": True}, "comment": "一致"},
            {"field_key": "pe_chest", "verdict": "pass", "reason_code": "none",
             "checks": {"grounding_supported": True, "field_scope_valid": True, "text_standard": True, "logic_consistent": True}, "comment": "一致"},
        ]},
    ])
    verifier = FieldVerifier(client)
    result = verifier.verify(candidates, group_by="section")
    assert len(client.calls) == 1  # 同 section 合并为一条请求
    assert "颈软" in client.calls[0][0] and "胸廓对称" in client.calls[0][0]
    assert len(result) == 2

def test_verify_group_failure_isolation():
    units = [_mk_unit("u001", "腹部：腹部正常。"), _mk_unit("u002", "肺部：呼吸音清。")]
    candidates = [
        _mk_field("pe_abdomen", "腹部正常", [units[0]]),
        _mk_field("pe_lung", "呼吸音清", [units[1]]),
    ]
    client = _RecordingClient(
        [{"verifications": [{"field_key": "pe_lung", "verdict": "suspicious", "reason_code": "nonstandard_expression",
          "checks": {"grounding_supported": True, "field_scope_valid": True, "text_standard": False, "logic_consistent": True},
          "comment": "u002 疑为错读"}]}],
        fail_at={0},
    )
    verifier = FieldVerifier(client)
    result = verifier.verify(candidates, group_by="field")
    assert len(client.calls) == 2  # 失败组不中断后续组
    assert len(result) == 1 and result[0]["field_key"] == "pe_lung"

def test_verify_group_all_failed_returns_empty():
    units = [_mk_unit("u001", "体温36.5℃。"), _mk_unit("u002", "脉搏88次/分。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [units[0]]), _mk_field("pe_pulse", "88次/分", [units[1]])]
    client = _RecordingClient([], fail_at={0, 1})
    verifier = FieldVerifier(client)
    result = verifier.verify(candidates, group_by="field")
    assert result == []

def test_verify_group_out_of_scope_field_rejects_group():
    """verifier.v3 语义契约：组外字段 = 该组响应整体非法，整组拒绝。"""
    units = [_mk_unit("u001", "体温36.5℃。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [units[0]])]
    client = _RecordingClient([
        {"verifications": [
            {"field_key": "pe_temperature", "verdict": "pass", "reason_code": "none",
             "checks": {"grounding_supported": True, "field_scope_valid": True, "text_standard": True, "logic_consistent": True}, "comment": "一致"},
            {"field_key": "pe_eyes", "verdict": "suspicious", "reason_code": "nonstandard_expression",
             "checks": {"grounding_supported": True, "field_scope_valid": True, "text_standard": False, "logic_consistent": True}, "comment": "u001 越界"},
        ]},
    ])
    verifier = FieldVerifier(client)
    result = verifier.verify(candidates, group_by="field")
    assert result == []  # 组外字段 → 整组拒绝


# —— verifier.v3：5 个 JSON 微例与后端语义契约 ——

def _four_checks(grounding=True, scope=True, text=True, logic=True):
    return {
        "grounding_supported": grounding,
        "field_scope_valid": scope,
        "text_standard": text,
        "logic_consistent": logic,
    }


def test_verifier_v3_five_json_micro_examples_present_and_parseable():
    """三类核心微例 + 术语陌生 pass + 错读形似规范词对照：存在、可解析、顶层仅 verifications。"""
    import re

    system, _ = build_verification_messages([], [])
    blocks = re.findall(r"```json\n(.*?)```", system, re.S)
    assert len(blocks) == 5
    for block in blocks:
        data = json.loads(block)
        assert sorted(data.keys()) == ["verifications"]
        assert len(data["verifications"]) == 1
        v = data["verifications"][0]
        assert set(v.keys()) == {"field_key", "verdict", "reason_code", "checks", "comment"}
        assert set(v["checks"].keys()) == {
            "grounding_supported", "field_scope_valid", "text_standard", "logic_consistent"}
    # 对照形态：越界示例、错读形似规范词示例、术语陌生 pass 示例
    assert "粗测" in system and "古手" in system
    assert "胸状胸" in system
    assert "u911" in system and "u912" in system and "u913" in system
    assert "禁止复制到输出" in system


def test_verify_skips_group_with_missing_cited_ids_without_llm_call():
    """cited ID 缺失/为空：调用前拦截，不调用复核 LLM。"""
    units = [_mk_unit("u001", "体温36.5℃。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [])]  # evidence_ids 空

    class NeverClient:
        def complete_json(self, prompt, **kwargs):
            raise AssertionError("不应调用复核 LLM")

    result = FieldVerifier(NeverClient()).verify(
        candidates, evidence_units=[units[0]]
    )
    assert result == []


def test_semantic_contract_duplicate_field_key_rejected():
    units = [_mk_unit("u001", "体温36.5℃。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [units[0]])]
    client = FakeLlmClient({"verifications": [
        {"field_key": "pe_temperature", "verdict": "pass", "reason_code": "none",
         "checks": _four_checks(), "comment": "一致"},
        {"field_key": "pe_temperature", "verdict": "pass", "reason_code": "none",
         "checks": _four_checks(), "comment": "一致"},
    ]})
    assert FieldVerifier(client).verify(candidates, document_text="") == []


def test_semantic_contract_missing_field_rejected():
    units = [_mk_unit("u001", "体温36.5℃。"), _mk_unit("u002", "脉搏88次/分。")]
    candidates = [
        _mk_field("pe_temperature", "36.5℃", [units[0]]),
        _mk_field("pe_pulse", "88次/分", [units[1]]),
    ]
    client = FakeLlmClient({"verifications": [
        {"field_key": "pe_temperature", "verdict": "pass", "reason_code": "none",
         "checks": _four_checks(), "comment": "一致"},
        # 缺 pe_pulse → 整组拒绝
    ]})
    assert FieldVerifier(client).verify(candidates, document_text="") == []


def test_semantic_contract_pass_with_false_check_rejected():
    units = [_mk_unit("u001", "体温36.5℃。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [units[0]])]
    client = FakeLlmClient({"verifications": [
        {"field_key": "pe_temperature", "verdict": "pass", "reason_code": "none",
         "checks": _four_checks(grounding=False), "comment": "一致"},
    ]})
    assert FieldVerifier(client).verify(candidates, document_text="") == []


def test_semantic_contract_suspicious_all_true_or_reason_none_rejected():
    units = [_mk_unit("u001", "体温36.5℃。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [units[0]])]
    for payload in (
        # suspicious 但四项全 true
        {"verifications": [{"field_key": "pe_temperature", "verdict": "suspicious",
          "reason_code": "extraction_mistake", "checks": _four_checks(), "comment": "u001 疑"}]},
        # suspicious 但 reason=none
        {"verifications": [{"field_key": "pe_temperature", "verdict": "suspicious",
          "reason_code": "none", "checks": _four_checks(grounding=False), "comment": "u001 疑"}]},
    ):
        assert FieldVerifier(FakeLlmClient(payload)).verify(candidates, document_text="") == []


def test_semantic_contract_reason_check_mismatch_rejected():
    units = [_mk_unit("u001", "体温36.5℃。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [units[0]])]
    # nonstandard_expression 但 text_standard=true
    payload1 = {"verifications": [{"field_key": "pe_temperature", "verdict": "suspicious",
        "reason_code": "nonstandard_expression", "checks": _four_checks(), "comment": "u001 疑"}]}
    assert FieldVerifier(FakeLlmClient(payload1)).verify(candidates, document_text="") == []
    # extraction_mistake 但 grounding/scope/logic 全 true
    payload2 = {"verifications": [{"field_key": "pe_temperature", "verdict": "suspicious",
        "reason_code": "extraction_mistake", "checks": _four_checks(text=False), "comment": "u001 疑"}]}
    assert FieldVerifier(FakeLlmClient(payload2)).verify(candidates, document_text="") == []


def test_semantic_contract_suspicious_comment_unknown_id_rejected():
    units = [_mk_unit("u001", "体温36.5℃。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [units[0]])]
    payload = {"verifications": [{"field_key": "pe_temperature", "verdict": "suspicious",
        "reason_code": "extraction_mistake", "checks": _four_checks(grounding=False),
        "comment": "u999 不存在的证据"}]}
    assert FieldVerifier(FakeLlmClient(payload)).verify(candidates, document_text="") == []


def test_semantic_contract_legit_pass_scope_ocr_parsed():
    """合法 pass、字段越界、OCR 病句三类均能解析。"""
    units = [_mk_unit("u001", "双耳粗测听力正常。"), _mk_unit("u002", "双眼粗测视力正常。")]
    candidates = [
        _mk_field("pe_ears", "正常", [units[0]]),
        _mk_field("pe_eyes", "正常", [units[1]]),
    ]
    client = FakeLlmClient({"verifications": [
        {"field_key": "pe_ears", "verdict": "pass", "reason_code": "none",
         "checks": _four_checks(), "comment": "一致"},
        {"field_key": "pe_eyes", "verdict": "suspicious", "reason_code": "nonstandard_expression",
         "checks": _four_checks(text=False), "comment": "u002 '粗侧'疑为'粗测'错读"},
    ]})
    result = FieldVerifier(client).verify(candidates, document_text="")
    assert len(result) == 2
    assert result[0]["verdict"] == "pass"
    assert result[1]["reason_code"] == "nonstandard_expression"


def test_semantic_contract_legacy_fail_still_parsed():
    """历史 fail 响应（旧 checks 键名）仍可解析，不套用新语义。"""
    units = [_mk_unit("u001", "体温36.5℃。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [units[0]])]
    payload = {"verifications": [{"field_key": "pe_temperature", "verdict": "fail",
        "reason_code": "extraction_mistake", "checks": {"value_semantically_supported": False},
        "comment": "u001 证据不支持"}]}
    result = FieldVerifier(FakeLlmClient(payload)).verify(candidates, document_text="")
    assert len(result) == 1 and result[0]["verdict"] == "fail"


def test_semantic_contract_bad_group_does_not_affect_other_section():
    """一组语义违规整组拒绝，不影响其他 section 组。"""
    units1 = [_mk_unit("u001", "主诉：反复咳嗽。")]
    units2 = [_mk_unit("u002", "肺部：呼吸音清。")]
    candidates = [
        _mk_field("chief_complaint", "反复咳嗽", [units1[0]], section="chief_complaint"),
        _mk_field("pe_lung", "呼吸音清", [units2[0]], section="physical_examination"),
    ]
    responses = [
        {"verifications": [{"field_key": "chief_complaint", "verdict": "pass", "reason_code": "none",
          "checks": _four_checks(), "comment": "一致"}]},
        {"verifications": [{"field_key": "pe_lung", "verdict": "suspicious", "reason_code": "extraction_mistake",
          "checks": _four_checks(grounding=False), "comment": "u999 不存在的证据"}]},  # 违规
    ]
    client = _RecordingClient(responses)
    result = FieldVerifier(client).verify(candidates, group_by="section")
    assert len(result) == 1 and result[0]["field_key"] == "chief_complaint"


def test_v3_contract_new_keys_accepted():
    """verifier.v3：新 checks 键 text_standard + 新 reason nonstandard_expression 可解析。"""
    units = [_mk_unit("u001", "胸状胸。")]
    candidates = [_mk_field("pe_chest", "胸状胸", [units[0]])]
    payload = {"verifications": [{"field_key": "pe_chest", "verdict": "suspicious",
        "reason_code": "nonstandard_expression",
        "checks": _four_checks(text=False), "comment": "u001 胸状胸非标准表述"}]}
    result = FieldVerifier(FakeLlmClient(payload)).verify(candidates, document_text="")
    assert len(result) == 1
    assert result[0]["reason_code"] == "nonstandard_expression"
    assert result[0]["checks"]["text_standard"] is False


def test_v3_contract_old_check_key_renormalized():
    """历史数据：旧 checks 键 ocr_text_clear 解析时归一化为 text_standard。"""
    units = [_mk_unit("u001", "体温36.5℃。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [units[0]])]
    payload = {"verifications": [{"field_key": "pe_temperature", "verdict": "pass",
        "reason_code": "none",
        "checks": {"grounding_supported": True, "field_scope_valid": True,
                   "ocr_text_clear": True, "logic_consistent": True},
        "comment": "一致"}]}
    result = FieldVerifier(FakeLlmClient(payload)).verify(candidates, document_text="")
    assert len(result) == 1
    assert "text_standard" in result[0]["checks"] and "ocr_text_clear" not in result[0]["checks"]


def test_v3_contract_legacy_reason_still_parsed_with_old_check():
    """历史数据：reason=ocr_quality_issue + 旧键 ocr_text_clear=false 组合可解析（不误拒）。"""
    units = [_mk_unit("u001", "古手中指断指再植术后5年。")]
    candidates = [_mk_field("pmh_surgery_history", "古手中指断指再植术后5年", [units[0]])]
    payload = {"verifications": [{"field_key": "pmh_surgery_history", "verdict": "suspicious",
        "reason_code": "ocr_quality_issue",
        "checks": {"grounding_supported": True, "field_scope_valid": True,
                   "ocr_text_clear": False, "logic_consistent": True},
        "comment": "u001 古手疑为左手错读"}]}
    result = FieldVerifier(FakeLlmClient(payload)).verify(candidates, document_text="")
    assert len(result) == 1
    assert result[0]["reason_code"] == "ocr_quality_issue"
    assert result[0]["checks"]["text_standard"] is False


def test_v3_contract_legacy_e_prefixed_cited_id_parsed():
    """历史数据：comment 引用 e 前缀 ID（v2 前格式）且该 ID 在请求 evidence_ids 内可解析。"""
    units = [_mk_unit("e001", "双耳粗测听力正常。")]
    candidates = [_mk_field("pe_ears", "正常", [units[0]])]
    payload = {"verifications": [{"field_key": "pe_ears", "verdict": "suspicious",
        "reason_code": "nonstandard_expression",
        "checks": _four_checks(text=False), "comment": "e001 '粗侧'疑为'粗测'错读"}]}
    result = FieldVerifier(FakeLlmClient(payload)).verify(candidates, document_text="")
    assert len(result) == 1
    assert result[0]["reason_code"] == "nonstandard_expression"
