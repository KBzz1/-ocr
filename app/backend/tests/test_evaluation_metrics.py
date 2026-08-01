"""评估指标模块单测（合成数据，不依赖真实 LLM）。"""
import pytest

from app.backend.evaluation.metrics import (
    compare_value,
    j_judgement_fields,
    j_judgement_normalize,
    normalize_text,
    sentence_overlap_ratio,
    status_matches,
    value_located_in_text,
)


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
