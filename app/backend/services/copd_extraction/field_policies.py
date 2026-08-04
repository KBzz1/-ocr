"""字段取值策略共享真源（prompt 渲染与评估侧共同导入）。

每个业务字段有且只有一个取值策略标记：

- ``T``（原文摘录）：保留否定词、不确定性、数值、单位和 OCR 原貌，不静默改写。
- ``J``（正常/阴性判断）：明确正常/阴性时输出“正常”；出现异常时摘录具体异常；
  完全未提及才 not_found；阴性描述不能被当作未提及。
- ``D``（诊断）：保留原文编号和编号顺序；不推断、合并、改标题或补写、添加诊断。

J 集合成员与历史上 ``prompts._NORMAL_JUDGEMENT_FIELD_KEYS`` 完全一致，不得自行
增删；诊断组固定 D；其余字段固定 T。策略定义只在本模块写一次。
"""
from __future__ import annotations

NORMAL_JUDGEMENT_FIELD_KEYS = {
    "hpi_mental_status", "hpi_urine_status",
    "pmh_hepatitis_b", "pmh_nephritis", "pmh_hematologic_disease",
    "pmh_coronary_heart_disease", "pmh_cerebral_infarction",
    "pmh_surgery_history", "pmh_transfusion_history",
    "pmh_blood_product_history", "pmh_allergy_history",
    "pe_skin", "pe_eyes", "pe_ears", "pe_nose", "pe_oral_cavity",
    "pe_neck", "pe_breast", "pe_cardiac_exam", "pe_abdomen", "pe_limbs",
    "pe_neurological_exam", "aux_electrolytes", "aux_renal_function",
    "aux_d_dimer",
}

DIAGNOSIS_FIELD_KEYS = {"diagnosis_preliminary", "diagnosis_final"}

POLICY_T = "T"
POLICY_J = "J"
POLICY_D = "D"

POLICY_DEFINITIONS = {
    POLICY_T: "原文摘录型：保留否定词、不确定性、数值、单位和 OCR 原貌，不静默改写。",
    POLICY_J: "正常判断型：明确正常/阴性时输出“正常”；出现异常时摘录具体异常；完全未提及才 not_found。阴性描述不能被当作未提及。",
    POLICY_D: "诊断型：保留原文编号和编号顺序；不推断、合并、改标题或补写、添加诊断。",
}


def field_policy(field: dict, group_key: str = "") -> str:
    """返回字段的取值策略标记：诊断组固定 D，J 集合固定 J，其余固定 T。

    ``field`` 只需含 ``field_key``；``group_key`` 是字段所属章节（诊断组判定
    用章节而非字段键，保证组内新增诊断字段也自动落入 D）。
    """
    if group_key == "diagnosis":
        return POLICY_D
    if field.get("field_key", "") in NORMAL_JUDGEMENT_FIELD_KEYS:
        return POLICY_J
    return POLICY_T
