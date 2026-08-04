"""评估指标模块单测（合成数据，不依赖真实 LLM）。"""
import pytest

from evaluation.code.metrics import (
    _KNOWN_J_FIELDS,
    METRIC_VERSION,
    compare_j_value,
    compare_value,
    grounding_result,
    is_canonical_normal,
    j_judgement_fields,
    j_judgement_normalize,
    normalize_text,
    project_stool_urine_value,
    sentence_overlap_ratio,
    status_matches,
    value_located_in_text,
)
from app.backend.services.copd_extraction.field_policies import NORMAL_JUDGEMENT_FIELD_KEYS


class TestNormalizeText:
    def test_fullwidth_to_halfwidth(self):
        assert normalize_text("血压：１３６/６８ｍｍＨｇ") == normalize_text("血压:136/68mmHg")

    def test_strip_whitespace_and_punctuation(self):
        assert normalize_text(" 反复咳嗽，咳痰20年。 ") == normalize_text("反复咳嗽咳痰20年")

    def test_keep_crucial_symbols(self):
        # 数值相关符号 / - % . 必须保留，否则数值比对失真
        assert normalize_text("136/68mmHg") == normalize_text("136/68mmHg")
        assert normalize_text("10-20口/日") == normalize_text("10-20口/日")
        assert normalize_text("+10^9/L") == normalize_text("+109/L")  # ^ 视为标点去掉

    def test_blank_inputs(self):
        assert normalize_text("") == ""
        assert normalize_text(None) == ""


class TestCompareValue:
    def test_exact_after_normalize(self):
        assert compare_value("反复咳嗽、咳痰20年", "反复咳嗽，咳痰20年") == "exact"

    def test_substring_both_directions(self):
        assert compare_value("反复咳嗽、咳痰20年，喘累2年", "反复咳嗽、咳痰20年") == "substring"
        assert compare_value("高血压", "有高血压病史1年余") == "substring"

    def test_mismatch(self):
        assert compare_value("否认糖尿病病史", "有糖尿病病史") == "mismatch"

    def test_empty_both_exact(self):
        assert compare_value("", "") == "exact"


class TestValueLocatedInText:
    OCR = "体温:36.6℃ 脉搏:99次/分 呼吸:20次/分 血压:136/68mmHg"

    def test_value_in_ocr(self):
        assert value_located_in_text("脉搏:99次/分", self.OCR)

    def test_value_not_in_ocr_is_hallucination(self):
        assert not value_located_in_text("胸痛3天", self.OCR)

    def test_empty_value_never_hallucination(self):
        assert value_located_in_text("", self.OCR)

    def test_ocr_correction_exempts(self):
        assert value_located_in_text("沙美特罗替卡松", "沙美特罗普卡松", ocr_correction_applied=True)


class TestStatusMatches:
    def test_equal_statuses(self):
        assert status_matches("found", "found")
        assert status_matches("not_found", "not_found")

    def test_different_statuses(self):
        assert not status_matches("found", "not_found")
        assert not status_matches("not_found", "found")
        assert not status_matches("uncertain", "found")

    def test_uncertain_golden_compares_status_only(self):
        # uncertain 金标的 value 不做严格比对，仅 status 计入（spec 第 4 节）
        assert status_matches("uncertain", "uncertain")


class TestJJudgementNormalize:
    def test_maps_normal_family(self):
        for text in ("正常", "鼻腔通畅", "未见异常", "无异常", "阴性", "无压痛"):
            assert j_judgement_normalize(text) == "正常"

    def test_keeps_abnormal_descriptions(self):
        # 异常描述不做"正常族"折叠：原样保留，且不等于"正常"
        assert "异常" in j_judgement_normalize("双肺呼吸音粗，闻及异常干啰音")
        assert j_judgement_normalize("双肺呼吸音粗") != "正常"

    def test_negated_normal_family_not_collapsed(self):
        # 否定形态（欠/不/稍欠 等前缀）不属于"正常族"：保持原文，不折叠为"正常"
        assert j_judgement_normalize("鼻腔欠通畅") == "鼻腔欠通畅"
        assert j_judgement_normalize("鼻腔不通畅") == "鼻腔不通畅"
        assert j_judgement_normalize("鼻黏膜稍欠通畅") == "鼻黏膜稍欠通畅"
        # 无否定的"通畅"仍归一为"正常"
        assert j_judgement_normalize("鼻腔通畅") == "正常"


class TestSentenceOverlapRatio:
    def test_shared_sentences_ratio(self):
        golden = "反复咳嗽、咳痰20年。活动后喘息。无发热。"
        predicted = "咳嗽、咳痰20年。活动后喘息。"
        # 金标 3 句，预测 2 句都覆盖（"咳嗽、咳痰20年"是金标句的摘录）→
        # 金标视角重合 2/3；取金标与预测覆盖的较小口径，至少过半
        assert sentence_overlap_ratio(golden, predicted) >= 0.5

    def test_disjoint_sentences_zero(self):
        assert sentence_overlap_ratio("无发热。", "胸痛3天") == 0.0

    def test_punctuation_only_segment_not_polluting(self):
        # 预测含纯标点段（归一化后为空串）不得让全部金标句被判覆盖：
        # 金标 2 句、预测 1 真句 + 1 纯标点段 → 0.5 而非 1.0
        golden = "无发热。无咳嗽。"
        predicted = "无发热。，，"
        assert sentence_overlap_ratio(golden, predicted) == 0.5


class TestJJudgementFields:
    def test_extracts_from_schema(self):
        schema = {
            "field_groups": [
                {"group_key": "pe", "fields": [
                    {"field_key": "pe_nose", "qwen_type": "J"},
                    {"field_key": "pe_ear", "review_control": "judgement"},
                    {"field_key": "pe_skin", "qwen_type": "T"},
                ]},
            ]
        }
        assert j_judgement_fields(schema) == {"pe_nose", "pe_ear"}


class TestIsCanonicalNormal:
    """evaluator.v2 严格"规范值正常"谓词：整个值归一后必须恰为"正常"。

    DESIGN_REVIEW MAJOR-1 显式检查项：含正常短语的混合长文本不得判为规范正常。
    """

    def test_canonical_forms(self):
        for value in ("正常", " 正常 ", "正常。", "正常，", "正常\n"):
            assert is_canonical_normal(value)

    def test_normal_family_phrases_are_canonical(self):
        # 纯正常/阴性表述（通畅/未见异常/阴性/无压痛…与带限定词的正常描述）
        # 都是规范正常判断：值是正常族表述且不含任何异常内容
        for value in ("鼻腔通畅", "未见异常", "无异常", "阴性", "无压痛",
                      "小便正常", "大便基本正常", "正常范围", "心音正常", "正常状态",
                      "皮肤粘膜正常，无黄疸、无出血点、无皮疹，皮肤弹性正常"):
            assert is_canonical_normal(value)

    def test_mixed_long_text_never_canonical(self):
        assert not is_canonical_normal("心率104次/分，律齐，心尖区可闻及杂音")
        assert not is_canonical_normal("双肺呼吸音粗，心音正常")

    def test_blank_never_canonical(self):
        assert not is_canonical_normal("")
        assert not is_canonical_normal(None)


class TestCompareJValue:
    """evaluator.v2 J 型非对称比较合同（DESIGN §4.4）。

    - 金标为异常摘录：原文归一 exact/substring（双向），预测含相同异常（即使
      附带正常描述）或预测是金标原文节选，都判正确；
    - 金标为规范正常判断（正常/阴性族）：预测必须是规范正常判断才判正确，
      混合正常与异常的长文本不得因含"正常"而通过；
    - 大小便投影先于族路由。
    """

    def test_abnormal_golden_exact(self):
        assert compare_j_value("双肺呼吸音粗", "双肺呼吸音粗") == "exact"

    def test_abnormal_golden_predicted_with_extra_normal_text_correct(self):
        # J 假阴性修正：金标异常摘录 + 预测包含相同异常但附带正常描述 → 正确
        assert compare_j_value("双肺呼吸音粗", "双肺呼吸音粗，心音正常") == "substring"
        assert compare_j_value("心界叩诊向左下扩大",
                               "心前区无隆起，心尖搏动无震荡，心界叩诊向左下扩大，心音正常") == "substring"

    def test_abnormal_golden_mismatch(self):
        assert compare_j_value("双肺呼吸音粗", "正常") == "mismatch"
        assert compare_j_value("双肺呼吸音粗", "双肺呼吸音清晰") == "mismatch"

    def test_normal_golden_requires_canonical_predicted(self):
        assert compare_j_value("正常", "正常") == "exact"
        assert compare_j_value("正常", "正常。") == "exact"
        # 纯正常/阴性表述等价于规范正常判断（§4.4：正常/阴性族预测必须是
        # 规范正常判断，纯阴性文本不是"混合正常与异常"）
        assert compare_j_value("正常", "鼻腔通畅") == "exact"
        assert compare_j_value("正常", "皮肤粘膜正常，无黄疸、无皮疹，皮肤弹性正常") == "exact"
        # 混合长文本不得因含"正常"而通过（MAJOR-1 反例）
        assert compare_j_value("正常", "心率104次/分，律齐，心尖区可闻及杂音") == "mismatch"
        assert compare_j_value("正常", "双肺呼吸音粗，心音正常") == "mismatch"
        assert compare_j_value("正常", "颜面眼睑浮肿，睑结膜正常") == "mismatch"

    def test_abnormal_golden_predicted_is_excerpt_of_golden(self):
        # 摘录族双向子串：预测是金标原文的节选（否定作用域截取）判正确
        assert compare_j_value("否认肝炎、结核、疟疾等传染病史", "否认肝炎") == "substring"
        assert compare_j_value("否认肾炎病史", "否认肾炎") == "substring"
        assert compare_j_value("患者自患病以来精神食欲欠佳夜间休息一般",
                               "精神食欲欠佳夜间休息一般") == "substring"

    def test_projection_precedes_family_routing(self):
        # 投影优先：金标"大小便…"先投影到"大便…"/"小便…"再比较
        assert compare_j_value("大小便正常", "大便正常", "hpi_stool_status") == "exact"
        assert compare_j_value("大小便正常", "小便正常", "hpi_urine_status") == "exact"
        assert compare_j_value("大小便基本正常", "大便基本正常", "hpi_stool_status") == "exact"
        # 预测保留"大小便"原文（未投影）也通过 substring
        assert compare_j_value("大小便基本正常", "大小便基本正常", "hpi_stool_status") == "exact"

    def test_projected_stool_golden_negative_family_accepts_canonical_normal(self):
        # 投影后"大便基本正常"是阴性族 → 预测规范"正常"判正确（§4.4 b）
        assert compare_j_value("大小便基本正常", "正常", "hpi_stool_status") == "exact"

    def test_projection_not_generalized_to_other_fields(self):
        # 反例：非目标字段（如 pe_abdomen）不做大小便投影——用摘录族用例
        # 区分投影是否生效（"大便成形"仅在与目标字段投影后才与金标等价）
        assert compare_j_value("大小便成形", "大便成形", "hpi_stool_status") == "exact"
        assert compare_j_value("大小便成形", "大便成形", "pe_abdomen") == "mismatch"
        assert compare_j_value("大小便成形", "大便成形", None) == "mismatch"


class TestProjectStoolUrineValue:
    def test_only_two_excretion_fields(self):
        assert project_stool_urine_value("大小便基本正常", "hpi_stool_status") == "大便基本正常"
        assert project_stool_urine_value("大小便基本正常", "hpi_urine_status") == "小便基本正常"

    def test_other_fields_and_none_unchanged(self):
        assert project_stool_urine_value("大小便基本正常", "pe_abdomen") == "大小便基本正常"
        assert project_stool_urine_value("大小便基本正常", None) == "大小便基本正常"
        assert project_stool_urine_value(None, "hpi_stool_status") is None

    def test_without_da_bian_unchanged(self):
        assert project_stool_urine_value("睡眠及二便尚可", "hpi_stool_status") == "睡眠及二便尚可"

    def test_first_occurrence_only(self):
        assert project_stool_urine_value("大小便正常，大小便失禁", "hpi_stool_status") == "大便正常，大小便失禁"


class TestGroundingNormalExemptionV2:
    """grounding normal-family 豁免（DESIGN §4.4）：只豁免规范"正常"预测，
    不能豁免任意含正常词的长文本。"""

    def test_canonical_normal_with_normal_family_citation_exempt(self):
        result = grounding_result(
            "正常", ["鼻腔通畅，各鼻窦区无压痛"], "鼻腔通畅，各鼻窦区无压痛",
            normal_allowed=True,
        )
        assert result["status"] == "located"
        assert result["allowed_normalization"] == "normal_family"
        assert result["unsupported_fragments"] == []

    def test_mixed_long_text_not_exempt(self):
        result = grounding_result(
            "心率104次/分，律齐，心音正常，心尖区可闻及杂音",
            ["心音正常"], "心音正常",
            normal_allowed=True,
        )
        assert result["status"] == "unsupported_claim_candidate"
        assert "allowed_normalization" not in result
        assert result["unsupported_fragments"] == ["心率104次/分，律齐，心音正常，心尖区可闻及杂音"]

    def test_normal_family_phrase_value_not_exempt(self):
        # "鼻腔通畅"是正常族短语但不是规范"正常"→ 不豁免
        result = grounding_result(
            "鼻腔通畅", ["双肺呼吸音减弱"], "双肺呼吸音减弱",
            normal_allowed=True,
        )
        assert result["status"] == "unsupported_claim_candidate"
        assert "allowed_normalization" not in result

    def test_canonical_normal_without_citation_not_exempt(self):
        # 豁免必须有对应 cited evidence，不是全文档豁免
        result = grounding_result("正常", [], "双肺呼吸音减弱", normal_allowed=True)
        assert "allowed_normalization" not in result
        assert result["status"] == "unsupported_claim_candidate"

    def test_no_comma_fragmentation_for_excretion_fields(self):
        # 不按普通逗号拆事实：逗号不是切分边界，含逗号的整段必须作为一个事实整体定位
        result = grounding_result(
            "大便基本正常，性状可", ["患者大便基本正常，性状可"], "患者大便基本正常，性状可",
            normal_allowed=True,
        )
        assert result["status"] == "located"
        assert result["located_fragments"] == ["大便基本正常，性状可"]
        assert result["unsupported_fragments"] == []
        # 逗号切分会把整段拆成两个碎片；强边界切分只按句号/分号/换行
        from evaluation.code.metrics import split_grounding_fragments
        assert split_grounding_fragments("大便基本正常，性状可") == ["大便基本正常，性状可"]


class TestJFieldsConsistencyWithFieldPolicies:
    """评估侧 J 集合必须与 prompt 策略真源 field_policies 一致（T1 R2 MINOR-2）。"""

    def test_symmetric_difference_empty(self):
        assert _KNOWN_J_FIELDS.symmetric_difference(NORMAL_JUDGEMENT_FIELD_KEYS) == set()

    def test_excretion_field_roles(self):
        # hpi_urine_status 是 J 字段；hpi_stool_status 是 T 字段（走 T 分支投影）——
        # 两条路径都必须支持大小便投影
        assert "hpi_urine_status" in NORMAL_JUDGEMENT_FIELD_KEYS
        assert "hpi_stool_status" not in NORMAL_JUDGEMENT_FIELD_KEYS


class TestMetricVersion:
    def test_metric_version_constant(self):
        assert METRIC_VERSION == "evaluator.v2"
