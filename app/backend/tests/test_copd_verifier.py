"""复核器单测：prompt 布局、verdict 解析与映射、失败降级（fake client，不依赖真实 LLM）。"""
import json

import pytest

from app.backend.services.copd_extraction.prompts import build_verification_messages
from app.backend.services.copd_extraction.verifier import FieldVerifier, apply_verdicts


def test_verification_messages_long_field_split_into_sentences():
    """超长字段按句拆分编号（逐句核验，防整段一致性放行）；短字段保持原样。"""
    long_value = "唇色发绀。" + "口腔粘膜无溃疡，张口正常。" * 12
    system, user = build_verification_messages(
        evidence_units=[{"id": "e001", "text": long_value}],
        fields=[
            {"field_key": "pe_oral", "value": long_value, "evidence_ids": ["e001"]},
            {"field_key": "pe_short", "value": "正常", "evidence_ids": ["e001"]},
        ],
    )
    # 长字段拆句编号 + 提示；短字段保持"声称值"原样
    assert "已按句拆分，逐句检查" in user
    assert "1「唇色发绀。」" in user
    assert "pe_short：声称值 正常" in user
    # system 包含错读模式特征信号与"逐句扫读"要求（仅文本契约，不含数据）
    assert "逐句扫读" in system
    assert "叠字" in system and "近形替换" in system


def test_verification_messages_evidence_first_fields_after():
    system, user = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "双耳粗测听力正常"}],
        fields=[{"field_key": "pe_ear", "value": "正常", "evidence_ids": ["e001"]}],
    )
    # system：身份/任务 2 句 + 通用原则 + 输出契约 + few-shot，不含数据
    assert "复核器" in system
    assert "e001" not in system and "听力正常" not in system
    assert "verdict" in system and "pass" in system and "suspicious" in system
    assert "suspicious" in system  # few-shot 覆盖 suspicious 示例
    # 校准迭代契约：只标记可逐字定位 + 双向标准直白句（值证一致即 pass，可逐字定位的实质矛盾才标记）+ OCR 识别职责 + 误报反例（仅文本契约，不含数据）
    assert "只标记可逐字定位" in system
    assert "逐字" in system
    assert "证据可逐字定位的实质矛盾" in system and "语义等价即可" in system
    assert "反例" in system
    # OCR 识别错误是复核器显式职责（通用原则），且不要求给出修正值（纠偏归抽取环节）
    assert "OCR 识别错误" in system
    assert "纠偏由抽取环节负责" in system
    # user：evidence 编号块在字段块之前
    assert user.index("e001") < user.index("pe_ear")
    assert "pe_ear" in user and "正常" in user


def test_verification_messages_general_principle_field_boundary():
    """通用原则新增字段越界一句：内容域与字段对应部位明显不符 → extraction_mistake。"""
    system, _ = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "双耳粗测听力正常"}],
        fields=[{"field_key": "pe_ear", "value": "正常", "evidence_ids": ["e001"]}],
    )
    assert "字段越界" in system
    assert "内容域与字段对应部位明显不符" in system
    assert "extraction_mistake" in system
    assert "引用原文片段即可" in system


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
    reminder = "请严格遵守 system prompt 中的【输出契约】【通用原则】【领域规则】。"
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
    reminder = "请严格遵守 system prompt 中的【输出契约】【通用原则】【领域规则】。"
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
    assert "影响理解或产生歧义 → 必须标记" in system
    assert "值忠实摘录原文不豁免错读检查" in system


def test_verifier_principle_logic_consistency():
    system, _ = build_verification_messages([], [])
    assert "数值矛盾或逻辑不一致" in system
    assert "时间归属错误、否定翻转、体征互斥" in system


def test_verifier_principle_boundary_no_evidence_exemption():
    system, _ = build_verification_messages([], [])
    assert "字段越界不因值有证据支持而豁免" in system


def test_verifier_fewshot_recall_examples_present():
    system, _ = build_verification_messages([], [])
    assert "'粗侧'为 OCR 错读（应为'粗测'）" in system
    assert "值却写'腹部移动性浊音阳性'，两处矛盾" in system
    assert system.count("示例仅示范结构，字段内容为占位，不得照抄") >= 2


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
        {"verifications": [{"field_key": "pe_temperature", "verdict": "pass", "reason_code": "none", "checks": {}, "comment": "一致"}]},
        {"verifications": [{"field_key": "pe_pulse", "verdict": "pass", "reason_code": "none", "checks": {}, "comment": "一致"}]},
    ])
    verifier = FieldVerifier(client)
    result = verifier.verify(candidates, document_text="全文", group_by="field")
    assert len(client.calls) == 2
    # 每条请求的字段声称值只含自己字段的值，不含其他字段
    # （两字段共享同一证据单元 u001，其原文文本可合法出现于任一组证据块）
    assert "声称值 36.5℃" in client.calls[0][0] and "声称值 88次/分" not in client.calls[0][0]
    assert "声称值 88次/分" in client.calls[1][0] and "声称值 36.5℃" not in client.calls[1][0]
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
            {"field_key": "pe_neck", "verdict": "pass", "reason_code": "none", "checks": {}, "comment": "一致"},
            {"field_key": "pe_chest", "verdict": "pass", "reason_code": "none", "checks": {}, "comment": "一致"},
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
        [{"verifications": [{"field_key": "pe_lung", "verdict": "suspicious", "reason_code": "ocr_quality_issue", "checks": {}, "comment": "疑"}]}],
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

def test_verify_group_filters_out_of_scope_fields():
    units = [_mk_unit("u001", "体温36.5℃。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [units[0]])]
    client = _RecordingClient([
        {"verifications": [
            {"field_key": "pe_temperature", "verdict": "pass", "reason_code": "none", "checks": {}, "comment": "一致"},
            {"field_key": "pe_eyes", "verdict": "suspicious", "reason_code": "ocr_quality_issue", "checks": {}, "comment": "越界"},
        ]},
    ])
    verifier = FieldVerifier(client)
    result = verifier.verify(candidates, group_by="field")
    assert [v["field_key"] for v in result] == ["pe_temperature"]  # 范围外字段按现状契约过滤
