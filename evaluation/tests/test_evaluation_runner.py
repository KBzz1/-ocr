"""评估 runner 单测：管线组装、消融变体、报告生成（fake client，不依赖真实 LLM）。"""
import json
from pathlib import Path

import pytest

from evaluation.code.runner import build_report, evaluate_sample, run_pipeline


def make_schema():
    return {
        "version": "1.0.0",
        "document_type": "copd_admission_record",
        "field_groups": [
            {
                "group_key": "chief_complaint",
                "group_label": "主诉",
                "fields": [{"field_key": "chief_complaint", "label": "主诉", "review_control": "text"}],
            }
        ],
    }


def make_schema_with_j_fields(*extra_keys):
    schema = make_schema()
    for key in (extra_keys or ["pe_nose"]):
        schema["field_groups"][0]["fields"].append(
            {"field_key": key, "label": key, "qwen_type": "J"}
        )
    return schema


def make_golden_payload():
    return {
        "schema_version": "1.0.0",
        "document_type": "copd_admission_record",
        "fields": [{"field_key": "chief_complaint", "status": "found", "value": "反复咳嗽、咳痰20年", "evidence_ids": []}],
    }


class FakeLlmClient:
    def __init__(self, payload):
        self._payload = payload

    def complete_json(self, prompt: str, **kwargs):
        return json.loads(json.dumps(self._payload))


SAMPLE = {
    "case_id": "case_001",
    "ocr_text": "主诉：反复咳嗽、咳痰20年，加重10余天。",
    "pitfalls": ["negation"],
    "golden": [{"field_key": "chief_complaint", "status": "found", "value": "反复咳嗽、咳痰20年，加重10余天"}],
}


class TestRunPipeline:
    def test_happy_path_returns_payload_and_candidates(self):
        schema = make_schema()
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(make_golden_payload()),
        )
        assert result["error"] is None
        assert result["candidates"][0]["field_key"] == "chief_complaint"
        assert result["candidates"][0]["status"] == "found"

    def test_contract_failure_captured_not_raised(self):
        schema = make_schema()
        bad_payload = {"fields": []}  # 契约非法
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(bad_payload),
        )
        assert result["error"] is not None
        assert result["error"]["code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["candidates"] == []

    def test_no_contract_skips_validation(self):
        schema = make_schema()
        bad_payload = {"fields": []}
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(bad_payload),
            check_contract=False,
        )
        assert result["error"] is None


class TestEvaluateSample:
    def test_perfect_match(self):
        result = evaluate_sample(SAMPLE, {
            "payload": make_golden_payload(),
            "candidates": [{
                "field_key": "chief_complaint", "status": "found",
                "value": "反复咳嗽、咳痰20年，加重10余天", "ocr_correction": {"applied": False},
            }],
            "error": None,
        })
        assert result["metrics"]["value_correct"] == 1
        assert result["metrics"]["value_total"] == 1
        assert result["metrics"]["status_correct"] == 1
        assert result["metrics"]["hallucination"] == 0

    def test_status_mismatch_counts(self):
        result = evaluate_sample(SAMPLE, {
            "payload": make_golden_payload(),
            "candidates": [{
                "field_key": "chief_complaint", "status": "not_found",
                "value": "", "ocr_correction": {"applied": False},
            }],
            "error": None,
        })
        assert result["metrics"]["status_correct"] == 0
        assert result["metrics"]["value_correct"] == 0
        assert result["metrics"]["value_total"] == 1
        assert result["metrics"]["extraction_fn"] == 1

    def test_gold_not_found_predicted_found_is_checked_for_grounding(self):
        sample = {
            "case_id": "case_001",
            "ocr_text": "无胸痛。",
            "golden": [{"field_key": "chief_complaint", "status": "not_found", "value": ""}],
        }
        result = {
            "payload": {},
            "candidates": [{
                "field_key": "chief_complaint",
                "status": "found",
                "value": "胸痛3天",
                "evidence": [{"id": "u001", "text": "无胸痛。"}],
                "evidence_ids": ["u001"],
            }],
            "error": None,
        }

        metrics = evaluate_sample(sample, result)["metrics"]
        assert metrics["over_extraction_fp"] == 1
        assert metrics["unsupported_claim_candidate"] == 1
        assert metrics["confirmed_hallucination"] == 1

    def test_contract_error_counts_as_contract_invalid(self):
        result = evaluate_sample(SAMPLE, {
            "payload": {}, "candidates": [],
            "error": {"code": "ALGORITHM_CONTRACT_INVALID", "message": "bad"},
        })
        assert result["metrics"]["contract_invalid"] == 1

    def test_skips_hallucination_when_golden_not_located(self):
        # 金标 value 在 ocr_text 不可定位（否定短语重建）→ 该字段不判幻觉
        sample = {
            "case_id": "case_001",
            "ocr_text": "否认\"糖尿病\"、\"冠心病\"等病史",
            "golden": [{"field_key": "pmh_diabetes", "status": "found", "value": "否认糖尿病病史"}],
        }
        result = {
            "payload": {},
            "candidates": [{
                "field_key": "pmh_diabetes", "status": "found",
                "value": "否认糖尿病病史", "ocr_correction": {"applied": False},
            }],
            "error": None,
        }
        out = evaluate_sample(sample, result)
        assert out["metrics"]["hallucination"] == 0
        assert out["metrics"]["value_correct"] == 1  # 值一致

    def test_j_canonical_normal_golden_matches_canonical_normal_predicted(self):
        # evaluator.v2：金标为规范"正常"，预测也为规范"正常"且 cited evidence
        # 支持正常族 → 值正确，normal-family 豁免成立，不判幻觉
        sample = {
            "case_id": "case_001",
            "ocr_text": "鼻腔通畅，各鼻窦区无压痛",
            "golden": [{"field_key": "pe_nose", "status": "found", "value": "正常"}],
        }
        result = {
            "payload": {},
            "candidates": [{
                "field_key": "pe_nose", "status": "found",
                "value": "正常", "ocr_correction": {"applied": False},
                "evidence": [{"id": "u001", "text": "鼻腔通畅，各鼻窦区无压痛"}],
            }],
            "error": None,
        }
        out = evaluate_sample(sample, result, schema=make_schema_with_j_fields())
        assert out["metrics"]["value_correct"] == 1
        assert out["metrics"]["unsupported_claim_candidate"] == 0
        assert out["metrics"]["hallucination"] == 0

    def test_j_normal_family_phrase_golden_accepts_canonical_normal(self):
        # v2 语义：金标阴性族短语（"鼻腔通畅"）是规范正常判断 → 预测规范
        # "正常"判正确（§4.4 b"金标属于正常/阴性族时，预测必须是规范值
        # '正常'才判正确"）；真正被拒绝的是混合正常与异常的文本
        sample = {
            "case_id": "case_001",
            "ocr_text": "鼻腔通畅，各鼻窦区无压痛",
            "golden": [{"field_key": "pe_nose", "status": "found", "value": "鼻腔通畅"}],
        }
        result = {
            "payload": {},
            "candidates": [{
                "field_key": "pe_nose", "status": "found",
                "value": "正常", "ocr_correction": {"applied": False},
            }],
            "error": None,
        }
        out = evaluate_sample(sample, result, schema=make_schema_with_j_fields())
        assert out["metrics"]["value_correct"] == 1
        assert out["metrics"]["hallucination"] == 0

    def test_j_normal_golden_mixed_abnormal_text_is_mismatch(self):
        # v2 语义：金标规范"正常"，预测含异常内容的混合文本不得通过
        sample = {
            "case_id": "case_001",
            "ocr_text": "颜面眼睑浮肿，睑结膜正常",
            "golden": [{"field_key": "pe_eyes", "status": "found", "value": "正常"}],
        }
        result = {
            "payload": {},
            "candidates": [{
                "field_key": "pe_eyes", "status": "found",
                "value": "颜面眼睑浮肿，睑结膜正常", "ocr_correction": {"applied": False},
            }],
            "error": None,
        }
        out = evaluate_sample(sample, result, schema=make_schema_with_j_fields("pe_eyes"))
        assert out["metrics"]["value_correct"] == 0
        assert out["metrics"]["hallucination"] == 0

    def test_j_abnormal_golden_predicted_with_extra_normal_text_is_correct(self):
        # J 假阴性修正：金标异常摘录，预测附带正常描述也判正确
        sample = {
            "case_id": "case_001",
            "ocr_text": "心界叩诊向左下扩大，心音正常",
            "golden": [{"field_key": "pe_cardiac_exam", "status": "found", "value": "心界叩诊向左下扩大"}],
        }
        result = {
            "payload": {},
            "candidates": [{
                "field_key": "pe_cardiac_exam", "status": "found",
                "value": "心前区无隆起，心尖搏动无震荡，心界叩诊向左下扩大，心音正常",
                "ocr_correction": {"applied": False},
                "evidence": [{"id": "u001", "text": "心界叩诊向左下扩大，心音正常"}],
            }],
            "error": None,
        }
        out = evaluate_sample(sample, result, schema=make_schema_with_j_fields("pe_cardiac_exam"))
        assert out["metrics"]["value_correct"] == 1

    def test_j_normal_golden_mixed_long_predicted_is_value_error_and_not_exempt(self):
        # 金标规范"正常"vs 预测混合长文本（含"正常"词但非规范值）→ 值错误；
        # grounding 不得豁免该长文本（unsupported 候选保留）
        sample = {
            "case_id": "case_001",
            "ocr_text": "心率92次/分，心律规则，心音正常",
            "golden": [{"field_key": "pe_nose", "status": "found", "value": "正常"}],
        }
        result = {
            "payload": {},
            "candidates": [{
                "field_key": "pe_nose", "status": "found",
                "value": "心率104次/分，律齐，心音正常，心尖区可闻及杂音",
                "ocr_correction": {"applied": False},
                "evidence": [{"id": "u001", "text": "心音正常，心脏各瓣膜未闻及病理性杂音"}],
            }],
            "error": None,
        }
        out = evaluate_sample(sample, result, schema=make_schema_with_j_fields())
        assert out["metrics"]["value_correct"] == 0
        assert out["metrics"]["unsupported_claim_candidate"] == 1
        assert out["metrics"]["hallucination"] == 0

    def test_stool_golden_projection_matches_predicted(self):
        # hpi_stool_status（T 分支）：金标"大小便…"投影"大便…"后比较通过
        sample = {
            "case_id": "case_005",
            "ocr_text": "大小便基本正常",
            "golden": [{"field_key": "hpi_stool_status", "status": "found", "value": "大小便基本正常"}],
        }
        result = {
            "payload": {},
            "candidates": [{
                "field_key": "hpi_stool_status", "status": "found",
                "value": "大便基本正常", "ocr_correction": {"applied": False},
                "evidence": [{"id": "u001", "text": "患者大便基本正常"}],
            }],
            "error": None,
        }
        out = evaluate_sample(sample, result)
        assert out["metrics"]["value_correct"] == 1
        assert out["metrics"]["unsupported_claim_candidate"] == 0

    def test_urine_golden_projection_uses_j_comparator(self):
        # hpi_urine_status（J 分支）：金标"大小便…"投影"小便…"后按 J 非对称合同比较
        sample = {
            "case_id": "case_005",
            "ocr_text": "大小便基本正常",
            "golden": [{"field_key": "hpi_urine_status", "status": "found", "value": "大小便基本正常"}],
        }
        result = {
            "payload": {},
            "candidates": [{
                "field_key": "hpi_urine_status", "status": "found",
                "value": "小便基本正常", "ocr_correction": {"applied": False},
                "evidence": [{"id": "u001", "text": "大小便基本正常"}],
            }],
            "error": None,
        }
        out = evaluate_sample(sample, result, schema=make_schema_with_j_fields("hpi_urine_status"))
        assert out["metrics"]["value_correct"] == 1

    def test_stool_golden_without_projection_target_field_is_mismatch(self):
        # 反例：投影不推广到非目标字段——用摘录族值区分投影是否生效：
        # "大便成形"仅在与目标字段投影后才与金标"大小便成形"等价
        sample = {
            "case_id": "case_005",
            "ocr_text": "腹部大小便成形",
            "golden": [{"field_key": "pe_abdomen", "status": "found", "value": "大小便成形"}],
        }
        result = {
            "payload": {},
            "candidates": [{
                "field_key": "pe_abdomen", "status": "found",
                "value": "大便成形", "ocr_correction": {"applied": False},
                "evidence": [{"id": "u001", "text": "腹部大小便成形"}],
            }],
            "error": None,
        }
        out = evaluate_sample(sample, result, schema=make_schema_with_j_fields("pe_abdomen"))
        assert out["metrics"]["value_correct"] == 0

    def test_j_abnormal_golden_predicted_normal_is_value_error_not_hallucination(self):
        # 金标是异常描述（双肺呼吸音粗，OCR 可定位），预测折叠为"正常"→
        # 语义不等价，但这是已知字段的值错误，不是新增临床事实。
        sample = {
            "case_id": "case_001",
            "ocr_text": "双肺呼吸音粗",
            "golden": [{"field_key": "pe_nose", "status": "found", "value": "双肺呼吸音粗"}],
        }
        result = {
            "payload": {},
            "candidates": [{
                "field_key": "pe_nose", "status": "found",
                "value": "正常", "ocr_correction": {"applied": False},
            }],
            "error": None,
        }
        out = evaluate_sample(sample, result, schema=make_schema_with_j_fields())
        assert out["metrics"]["value_correct"] == 0
        assert out["metrics"]["hallucination"] == 0


class TestBuildReport:
    def test_summary_and_grouping(self):
        report = build_report([evaluate_sample(SAMPLE, {
            "payload": make_golden_payload(),
            "candidates": [{
                "field_key": "chief_complaint", "status": "found",
                "value": "完全错误的值", "ocr_correction": {"applied": False},
            }],
            "error": None,
        })], {"model": "qwen", "prompt_version": "v1", "sample_count": 1})
        assert report["metrics"]["value_accuracy"] == 0.0
        assert report["metrics"]["status_accuracy"] == 1.0
        assert report["metrics"]["hallucination_count"] == 0
        assert report["by_field"]["chief_complaint"]["value_total"] == 1
        assert report["by_pitfall"]["negation"]["value_total"] == 1
        assert report["errors"] == [{"case_id": "case_001", "field_key": "chief_complaint", "kind": "value_mismatch"}]


class FakeVerifier:
    def __init__(self, verdicts):
        self._verdicts = verdicts
        self.called = 0
        self.group_by = None

    def verify(self, candidates, document_text="", group_by=None, evidence_units=None):
        self.called += 1
        self.group_by = group_by
        return [dict(v) for v in self._verdicts]

    def close(self):
        pass


class TestRunPipelineVerifier:
    def test_apply_verify_default_runs_verifier(self):
        schema = make_schema()
        verifier = FakeVerifier([
            {"field_key": "chief_complaint", "verdict": "suspicious", "reason_code": "extraction_mistake",
             "checks": {}, "comment": "原文无此值"},
        ])
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(make_golden_payload()),
            verifier=verifier,
        )
        assert verifier.called == 1
        assert verifier.group_by == "field"
        candidates = result["candidates"]
        # found+无 evidence_ids 的候选在 map 阶段即被标 suspicious
        # （evidence_missing，与复核器无关），故不能断言 verification_status；
        # 改为断言复核器专属痕迹（verifier_suspicious flag）存在——该 dict flag
        # 只由 apply_verdicts 添加，能捕获"复核器已跑但 verdict 未应用"的回归。
        # 注意 quality_flags 中还有字符串 flag（map 阶段的 evidence_missing），
        # 需 isinstance(dict) 过滤（与 test_no_verifier_skips_verifier 对称）。
        assert any(
            f.get("flag") == "verifier_suspicious"
            for f in candidates[0].get("quality_flags", [])
            if isinstance(f, dict)
        )

    def test_no_verifier_skips_verifier(self):
        schema = make_schema()
        verifier = FakeVerifier([
            {"field_key": "chief_complaint", "verdict": "suspicious", "reason_code": "extraction_mistake",
             "checks": {}, "comment": "x"},
        ])
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(make_golden_payload()),
            apply_verify=False,
            verifier=verifier,
        )
        assert verifier.called == 0
        # 注意：found+无 evidence_ids 的候选在 map 阶段即被标 suspicious
        # （evidence_missing，与复核器无关），故不能断言 verification_status
        # 不等于 suspicious；改为断言复核器专属痕迹（verifier_suspicious flag）不存在。
        assert not any(
            f.get("flag") == "verifier_suspicious"
            for f in result["candidates"][0].get("quality_flags", [])
            if isinstance(f, dict)
        )


class TestBuildReportMetricVersion:
    def test_report_meta_always_stamped_v2(self):
        # 报告 meta 必须有 metric_version="evaluator.v2"（DESIGN §4.4），
        # 即使调用方 meta 未提供也由 build_report 兜底注入
        report = build_report([evaluate_sample(SAMPLE, {
            "payload": make_golden_payload(),
            "candidates": [{
                "field_key": "chief_complaint", "status": "found",
                "value": "反复咳嗽、咳痰20年，加重10余天", "ocr_correction": {"applied": False},
            }],
            "error": None,
        })], {"model": "qwen", "prompt_version": "v4"})
        assert report["meta"]["metric_version"] == "evaluator.v2"


CASE_005_GOLDEN_BEFORE = {
    'chief_complaint': ('found', '反复咳嗽、咳痰10+年, 喘累、气促2+年, 颜面部浮肿1周。'),
    'hpi_initial_onset': ('found', '10+年前, 患者无明显诱因出现咳嗽、咳痰, 咳白色泡沫痰, 好发于冬春季, 每年咳嗽、咳痰总时长超过3月, 于当地医院诊断为慢性阻塞性肺疾病, 并办理医保卡'),
    'hpi_subsequent_course': ('found', '近2+年, 患者出现活动后喘累、气促不适宜, 日常活动耐量减少, 长期家庭导氧, 每日鼻导管吸氧1.5小时左右, 未吸氧情况下, 自测指氧饱和度和在82%左右, 吸氧情况下, 指氧饱和度和在92%左右'),
    'hpi_hospital_diagnosis': ('found', '考虑Ⅱ型呼吸衰竭'),
    'hpi_treatment_medications': ('found', '给予无创呼吸机辅助通气'),
    'hpi_recent_symptoms': ('found', '1+月前(2月24日), 患者接电话时出现腰腹痛, 未影响日常生活, 未予以重视, 但腰痛症状持续加重, 患者于22天前(3月4日)前往沙坪坝区中医院住院行康复理疗, 觉腰痛症状逐渐缓解, 于7天前办理出院(3月19日), 家属发现患者颜面部浮肿, 面部浮肿持续2-3天后, 同时出现双下肢水肿明显'),
    'hpi_mental_status': ('found', '患者自患病以来, 精神食欲欠佳, 夜间休息一般'),
    'hpi_stool_status': ('found', '大小便基本正常'),
    'hpi_urine_status': ('found', '大小便基本正常'),
    'hpi_weight_change': ('found', '近期体重未见明显减轻'),
    'pmh_cardiac_disease': ('not_found', ''),
    'pmh_hypertension': ('found', '否认高血压病史'),
    'pmh_diabetes': ('found', '否认糖尿病病史'),
    'pmh_hepatitis_b': ('found', '否认肝炎、结核、疟疾等传染病史'),
    'pmh_hematochezia': ('not_found', ''),
    'pmh_nephritis': ('found', '否认肾炎病史'),
    'pmh_hematologic_disease': ('not_found', ''),
    'pmh_coronary_heart_disease': ('found', '否认冠心病病史'),
    'pmh_cerebral_infarction': ('not_found', ''),
    'pmh_surgery_history': ('found', '否认手术史'),
    'pmh_transfusion_history': ('found', '否认输血史'),
    'pmh_blood_product_history': ('found', '否认制品史'),
    'pmh_allergy_history': ('found', '否认药物、食物过敏史'),
    'personal_occupation': ('not_found', ''),
    'personal_smoking_history': ('found', '无烟史'),
    'personal_drinking_history': ('found', '无饮酒史'),
    'family_history': ('found', '子女健康良好, 家族中无传染病及遗传病史, 无特殊疾病'),
    'pe_temperature': ('found', '36.5℃'),
    'pe_pulse': ('found', '92次/分'),
    'pe_respiration_rate': ('found', '26次/分'),
    'pe_blood_pressure': ('found', '102/57mmHg'),
    'pe_height': ('not_found', ''),
    'pe_weight': ('found', '40 kg'),
    'pe_bmi': ('not_found', ''),
    'pe_skin': ('found', '正常'),
    'pe_eyes': ('found', '颜面眼睑浮肿'),
    'pe_ears': ('found', '正常'),
    'pe_nose': ('found', '正常'),
    'pe_oral_cavity': ('found', '正常'),
    'pe_neck': ('found', '颈静脉怒张，肝颈静脉回流征性'),
    'pe_chest': ('found', '正常'),
    'pe_breast': ('found', '正常'),
    'pe_respiratory_exam': ('found', '双肺语音额两侧减弱，双肺叩诊过清音，双肺呼吸音减弱，可闻及湿啰音'),
    'pe_cardiac_exam': ('found', '心界叩诊向左下扩大'),
    'pe_abdomen': ('found', 'Murphy征阳性'),
    'pe_limbs': ('found', '腰椎有压痛，四肢关节正常，活动自如，双下肢水肿'),
    'pe_neurological_exam': ('found', '正常'),
    'aux_chest_ct': ('found', '双肺散在吸支性病变可能，建议治疗后复查；双肺气肿；双侧胸腔积液，伴右肺下叶部分肺段被动性不张；心包少量积液；胸5、8椎体变扁；右侧第7肋骨局部骨皮质欠光整；肝周少量积液'),
    'aux_cardiac_ultrasound': ('found', '1.左房增大；2.左室壁增厚；3.三尖瓣中重度反流，反流压差增高，考虑有肺动脉高压；4.左室舒张功能减退'),
    'aux_blood_gas_ph': ('not_found', ''),
    'aux_blood_gas_pco2': ('found', 'pCO250.00mmHg↑'),
    'aux_blood_gas_po2': ('found', 'pO248.00mmHg↓'),
    'aux_blood_gas_na': ('not_found', ''),
    'aux_blood_gas_fio2': ('not_found', ''),
    'aux_blood_gas_oxygenation_index': ('not_found', ''),
    'aux_blood_routine': ('found', '白细胞(WBC)14.45×10^9/L↑、中性粒细胞百分率(NEUT%)92.2%↑、淋巴细胞百分率(LYM%)2.1%↓、嗜酸性粒细胞百分比(E0%)0.0%↓、中性粒细胞绝对值(NEUT#)13.33×10^9/L↑、淋巴细胞绝对值(LYM#)0.30×10^9/L↓、单核细胞绝对值(MXD#)0.79×10^9/L↑、嗜酸性粒细胞(E0#)0.00×10^9/L↓、平均血红蛋白浓度(MCHC)297.0g/L↓'),
    'aux_electrolytes': ('found', '钾(K)5.70mmol/L↑、钠(NA)130.6mmol/L↓、氯(CL)90.5mmol/L↓、总二氧化碳(CO2)19.8mmol/L↓、阴离子间隙(GAP)20mmol/L↑'),
    'aux_renal_function': ('found', '肾小球滤过率(eGFR)35ml/min/1L↓、钾(K)5.70mmol/L↑、钠(NA)130.6mmol/L↓、氯(CL)90.5mmol/L↓、总二氧化碳(CO2)19.8mmol/L↓、阴离子间隙(GAP)20mmol/L↑、尿素(UREA)19.01mmol/L↑、肌酐(CREA)123.4umol/L↑'),
    'aux_d_dimer': ('not_found', ''),
    'diagnosis_preliminary': ('found', '慢性阻塞性肺疾病急性加重合并肺部感染\n2. 慢性肺源性心脏病\n3. II型呼吸衰竭\n4. 慢性心力衰竭\n5. 肾功能不全\n6. 肝功能不全\n7. 低蛋白血症\n8. 高胆红素血症\n9. 双侧胸腔积液\n10. 心包积液\n11. 肝周积液\n12. 电解质代谢紊乱\n13. 低钠血症\n14. 低氯血症\n15. 高钾血症\n16. 低T3综合征\n17. 高尿酸血症'),
    'diagnosis_final': ('found', '慢性阻塞性肺疾病急性加重合并肺部感染\n2. 慢性肺源性心脏病\n3. II型呼吸衰竭\n4. 呼吸性酸中毒并代谢性碱中毒\n5. 心力衰竭\n6. 心房颤动\n7. 急性肾功能不全\n8. 肝功能异常\n9. 凝血功能障碍\n10. 低蛋白血症\n11. 双侧胸腔积液\n12. 心包积液\n13. 肝周积液\n14. 尿路感染\n15. 右侧小腿肌间静脉血栓形成\n16. 高胆红素血症\n17. 电解质代谢紊乱\n18. 骨质疏松症\n19. 营养风险\n20. 完全性右束支传导阻滞\n21. 左侧颈动脉粥样硬化斑块形成\n22. 低T3综合征'),
}

# 两处已裁定金标（DESIGN §4.4）：pe_eyes 排除颜面边界、aux_renal_function 只保留肾功并纳入尿酸
CASE_005_ADJUDICATED = {
    'pe_eyes': ('found', '正常'),
    'aux_renal_function': ('found', '肾小球滤过率(eGFR)35ml/min/1L↓、尿素(UREA)19.01mmol/L↑、肌酐(CREA)123.4umol/L↑、尿酸(UA)508umol/L↑'),
}

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestCase005GoldenIntegrity:
    """case_005 金标只允许两处已裁定 value 变化（DESIGN §4.4/PLAN T2 Action 4-5）。"""

    GOLDEN_PATH = REPO_ROOT / "evaluation" / "data" / "golden" / "case_005.json"

    def _current(self):
        data = json.loads(self.GOLDEN_PATH.read_text(encoding="utf-8"))
        return {g["field_key"]: (g["status"], g["value"]) for g in data["golden"]}

    def test_still_61_unique_fields_with_legal_statuses(self):
        data = json.loads(self.GOLDEN_PATH.read_text(encoding="utf-8"))
        keys = [g["field_key"] for g in data["golden"]]
        assert len(keys) == 61
        assert len(set(keys)) == 61
        assert set(g["status"] for g in data["golden"]) <= {"found", "not_found", "uncertain"}

    def test_only_two_adjudicated_value_changes_vs_frozen_baseline(self):
        current = self._current()
        assert set(current) == set(CASE_005_GOLDEN_BEFORE)
        changed = {key for key in CASE_005_GOLDEN_BEFORE if CASE_005_GOLDEN_BEFORE[key] != current[key]}
        assert changed == set(CASE_005_ADJUDICATED)

    def test_two_adjudicated_values_are_grounded_in_ocr_text(self):
        data = json.loads(self.GOLDEN_PATH.read_text(encoding="utf-8"))
        ocr_text = data["ocr_text"]
        current = self._current()
        # pe_eyes：眼部检查原文全为正常描述（睑结膜正常、球结膜无充血水肿…），
        # 新金标为规范"正常"且不再含颜面描述
        assert current["pe_eyes"] == CASE_005_ADJUDICATED["pe_eyes"]
        assert "颜面" not in current["pe_eyes"][1]
        # aux_renal_function：肾功项目（eGFR/尿素/肌酐/尿酸）均可在 ocr_text 定位，
        # 不再复制电解质项目（钾/钠/氯/CO2/GAP）
        assert current["aux_renal_function"] == CASE_005_ADJUDICATED["aux_renal_function"]
        for token in ("肾小球滤过率(eGFR)35ml/min/1L↓", "尿素(UREA)19.01mmol/L↑",
                      "肌酐(CREA)123.4umol/L↑", "尿酸(UA)508umol/L↑"):
            assert token in ocr_text
        for electrolyte in ("钾(K)", "钠(NA)", "氯(CL)", "总二氧化碳(CO2)", "阴离子间隙(GAP)"):
            assert electrolyte not in current["aux_renal_function"][1]

    def test_blood_gas_fields_keep_found(self):
        current = self._current()
        assert current["aux_blood_gas_pco2"] == ('found', 'pCO250.00mmHg↑')
        assert current["aux_blood_gas_po2"] == ('found', 'pO248.00mmHg↓')
