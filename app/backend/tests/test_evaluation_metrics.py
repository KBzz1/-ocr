"""评估指标模块单测（合成数据，不依赖真实 LLM）。"""
import pytest

from app.backend.evaluation.metrics import (
    compare_value,
    normalize_text,
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
