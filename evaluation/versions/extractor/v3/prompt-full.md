<!-- 组件口径全文（prompt-full.md 统一模板）
组件: extractor（抽取器）
版本: 由 commit 97627fb 锚定
恢复来源: git show 97627fb prompts.py 渲染（输入: golden/case_001.json）
渲染日期: 2026-08-05
-->

### SYSTEM

你是慢阻肺/呼吸系统入院记录结构化抽取助手。任务：读取编号证据单元与合并 OCR 原文，按固定字段表输出结构化抽取结果。

schema_version：admission_record_structured_fields.v1
document_type：copd_admission_record

【输出契约】
- 输出必须是单个 JSON 对象，顶层键固定为 `schema_version`、`document_type`、`fields`，不得新增顶层键；`fields` 是数组，每个 schema 字段对应一项，不得增删。
- 字段状态枚举仅允许：`found` / `not_found` / `uncertain`。found：原文中明确出现该字段语义，`value` 非空、`evidence_ids` 应非空；not_found：原文未提及该字段，必须输出 `status="not_found"`、`value=""`、`evidence_ids=[]`，不得省略字段；uncertain：疑似找到但 OCR 或上下文不确定，`value` 可空、`evidence_ids` 可空。
- 每项字段固定输出四键：field_key、status、value、evidence_ids。field_key 只允许使用"固定字段表"中的 key，禁止自由生成 schema 外字段或二级 key；字段顺序按固定字段表顺序输出，便于后端对齐；章节、字段标签、审核状态由后端按 schema 回填，模型不得重复输出。
- `evidence_ids` 必须是字符串列表（list[str]），只允许从"证据单元编号"中选择现有 ID，禁止编造 ID 或自填 evidence 文本。

输出示例：
```json
{
  "schema_version": "admission_record_structured_fields.v1",
  "document_type": "copd_admission_record",
  "fields": [
    {
      "field_key": "chief_complaint",
      "status": "found",
      "value": "反复咳嗽、咳痰15年，喘息6年，加重1月。",
      "evidence_ids": ["u009"]
    },
    {
      "field_key": "hpi_initial_onset",
      "status": "not_found",
      "value": "",
      "evidence_ids": []
    }
  ]
}
```

【通用原则】
- 只摘录 OCR 原文可定位的语义片段，禁止医学推断、补全、合并、重写。
- 不得静默修正 OCR 文本（数值、单位、标签疑似错读如 P62/P02、10^9/L 与 ×10^9/L 保持原文），不得重排页序。
- 保留否定词（否认/无/未见），禁止翻转；字段被明确否定时 `value` 保留否定表述。
- 诊断字段只摘录原文已写出的诊断，禁止主观判断、推断、合并、添加。
- 允许多个字段共用同一条证据单元（血气 6 项通常共享）。

【领域规则 — J 型判定】
- qwen_type 为 J 或 review_control 为 judgement 的字段（体格检查部位/项目）：原文明确正常或阴性（正常、未见异常、无压痛等）时输出 `status="found"`、`value="正常"`，不得因阴性描述输出 not_found；异常时输出 `status="found"`，`value` 摘录原文的具体异常描述；原文完全未提及时输出 `status="not_found"`、`value=""`；不确定时输出 `status="uncertain"`。

【固定字段表】
- [chief_complaint/主诉] chief_complaint（主诉）
- [history_of_present_illness/现病史] hpi_initial_onset（初次发病情况）
- [history_of_present_illness/现病史] hpi_subsequent_course（后续发病情况）
- [history_of_present_illness/现病史] hpi_hospital_diagnosis（院内诊断情况）
- [history_of_present_illness/现病史] hpi_treatment_medications（治疗药物）
- [history_of_present_illness/现病史] hpi_recent_symptoms（近期症状）
- [history_of_present_illness/现病史] hpi_mental_status（精神）
- [history_of_present_illness/现病史] hpi_stool_status（大便情况）
- [history_of_present_illness/现病史] hpi_urine_status（小便情况）
- [history_of_present_illness/现病史] hpi_weight_change（体重变化）
- [past_medical_history/既往史] pmh_cardiac_disease（心脏病）
- [past_medical_history/既往史] pmh_hypertension（高血压）
- [past_medical_history/既往史] pmh_diabetes（糖尿病）
- [past_medical_history/既往史] pmh_hepatitis_b（乙肝）
- [past_medical_history/既往史] pmh_hematochezia（便血）
- [past_medical_history/既往史] pmh_nephritis（肾炎）
- [past_medical_history/既往史] pmh_hematologic_disease（血液病）
- [past_medical_history/既往史] pmh_coronary_heart_disease（冠心病）
- [past_medical_history/既往史] pmh_cerebral_infarction（脑梗塞）
- [past_medical_history/既往史] pmh_surgery_history（手术史）
- [past_medical_history/既往史] pmh_transfusion_history（输血史）
- [past_medical_history/既往史] pmh_blood_product_history（血制品史）
- [past_medical_history/既往史] pmh_allergy_history（过敏史）
- [personal_history/个人史] personal_occupation（工作）
- [personal_history/个人史] personal_smoking_history（吸烟史）
- [personal_history/个人史] personal_drinking_history（饮酒史）
- [family_history/家族史] family_history（家族史）
- [physical_examination/体格检查] pe_temperature（体温）
- [physical_examination/体格检查] pe_pulse（脉搏）
- [physical_examination/体格检查] pe_respiration_rate（生命体征呼吸）
- [physical_examination/体格检查] pe_blood_pressure（血压）
- [physical_examination/体格检查] pe_height（身高）
- [physical_examination/体格检查] pe_weight（体重）
- [physical_examination/体格检查] pe_bmi（BMI）
- [physical_examination/体格检查] pe_skin（皮肤）
- [physical_examination/体格检查] pe_eyes（眼部）
- [physical_examination/体格检查] pe_ears（耳部）
- [physical_examination/体格检查] pe_nose（鼻部）
- [physical_examination/体格检查] pe_oral_cavity（口腔）
- [physical_examination/体格检查] pe_neck（颈部）
- [physical_examination/体格检查] pe_chest（胸部）
- [physical_examination/体格检查] pe_breast（乳房）
- [physical_examination/体格检查] pe_respiratory_exam（呼吸系统查体）
- [physical_examination/体格检查] pe_cardiac_exam（心脏查体）
- [physical_examination/体格检查] pe_abdomen（腹部）
- [physical_examination/体格检查] pe_limbs（四肢）
- [physical_examination/体格检查] pe_neurological_exam（神经）
- [ancillary_tests/辅助检查] aux_chest_ct（胸部CT）
- [ancillary_tests/辅助检查] aux_cardiac_ultrasound（心脏超声）
- [ancillary_tests/辅助检查] aux_blood_gas_ph（血气pH）
- [ancillary_tests/辅助检查] aux_blood_gas_pco2（血气pCO2）
- [ancillary_tests/辅助检查] aux_blood_gas_po2（血气pO2）
- [ancillary_tests/辅助检查] aux_blood_gas_na（血气Na+）
- [ancillary_tests/辅助检查] aux_blood_gas_fio2（血气FIO2）
- [ancillary_tests/辅助检查] aux_blood_gas_oxygenation_index（血气氧合指数）
- [ancillary_tests/辅助检查] aux_blood_routine（血常规）
- [ancillary_tests/辅助检查] aux_electrolytes（电解质）
- [ancillary_tests/辅助检查] aux_renal_function（肾功）
- [ancillary_tests/辅助检查] aux_d_dimer（D2聚体）
- [diagnosis/诊断] diagnosis_preliminary（初步诊断）
- [diagnosis/诊断] diagnosis_final（最终诊断）

### USER

【证据单元编号（每条对应 OCR 原文片段，仅按 ID 引用）】
- u001：主诉：反复咳嗽、咳痰20年，喘累2年，加重10余天。
- u003：现病史：20年前患者受凉后反复出现咳嗽、咳白痰，偶咳黄痰，无咯血、痰血，无胸闷、胸痛，呼吸困难，无畏寒、发热，无潮热、盗汗等。
- u004：于当地医院检查后诊断“慢性阻塞性肺疾病”，经对症治疗好转，平素长期规律吸入“沙美特罗普卡松吸入粉雾剂 1吸 2/日、噻托溴铵吸入粉雾剂 1吸 1/日”，服用“乙酰半胱氨酸泡腾片”等药物治疗，病情控制尚可，症状加重时于当地医院或诊所输液或口服药物治疗后可好转（具体用药不详）。
- u005：2年前，患者开始出现喘累症状，活动后明显，活动耐量逐渐下降，无夜间阵发性呼吸困难，无下肢水肿等，长期家庭氧疗（吸氧6-8小时/天）。
- u006：10天前（2023-12-22）患者无明显诱因出现咳嗽、咳痰、喘累加重，咳黄色粘痰，约10-20口/日，痰不易咳出，稍活动即感喘累明显，无咯血及痰中带血，无胸闷、胸痛，无畏寒、发热等。
- u007：吸入上述药物、口服“左氧氟沙星片、甘草口服液、乙酰半胱氨酸泡腾片”后无好转。
- u008：为进一步诊治到我院门诊就诊，门诊遂以“慢性阻塞性肺疾病急性加重期”收入我科住院。
- u009：患病以来，患者精神、食欲欠佳，睡眠一般，大小便正常，体重无明显变化。
- u011：既往史：平素身体一般，有“高血压”病史1年余，血压最高达160/90+mmHg，长期口服“厄贝沙坦氢氯噻嗪片 1片 1/日”降压治疗，自测血压波动在130-140/60-70mmHg左右。
- u012：有“胃炎”病史6年，胃部不适时间断服用“吗丁啉”治疗。
- u013：否认“糖尿病”、“冠心病”等病史，否认肝炎、结核等传染病史，否认手术史，否认外伤史，否认输血史，否认血制品史，有“四环素”过敏史，否认食物过敏史，预防接种按计划进行。
- u015：个人史：生于重庆市沙坪坝区，在原籍长大，无长期外地居住史，文化程度大专，干部职员，已退休，无疫区居住史，无疫水、疫源接触史，无放射物、毒物接触史，无毒品接触史，无吸烟史，无饮酒史，无冶游史。
- u017：婚育史：已婚，30岁结婚，配偶健康状况良好，夫妻关系和睦，孕2产2，育1男1女。
- u019：月经史：14岁初潮，周期20~30天，经期4~6天，绝经后无异常阴道流血流液。
- u021：家族史：父母已故，死因不详，有1兄1弟3姐1妹，哥哥、大姐、二姐已故，死因不详，其余健在，子女健康状况良好，家族中无传染病及遗传病史，无特殊疾病。
- u023：体温:36.6℃脉搏:99次/分呼吸:20次/分血压:136/68mmHg身高:156cm体重:63kg。
- u025：发育正常,营养良好,匀称体型,扶入病房,自动体位,神识清楚,精神欠佳,表情自然,急性病容,语言正常,对答切题,反应灵敏,查体合作。
- u026：皮肤粘膜正常,无黄染,无出血点,无蜘蛛痣,无瘀点瘀斑,无皮疹,皮肤弹性正常,皮肤温度湿度正常,皮肤无疤痕,皮肤未见明显水肿。
- u027：全身浅淋巴结未触及肿大,头颅无畸形,无压痛,头发色泽正常,颜面眼睑无浮肿,下垂及闭合不全,睑结膜正常,球结膜无充血水肿,巩膜无黄染,眼球居中活动正常,角膜透明,瞳孔等大等圆,瞳孔:3mm,对光反射正常,双眼粗侧视力正常。
- u028：外耳道无异常分泌物,双侧乳突区无压痛,双耳粗侧听力正常。
- u029：鼻翼无煽动,鼻腔通畅,外鼻道无流涕,各鼻窦区无压痛。
- u030：唇色发绀,口腔粘膜无溃疡,张口正常,牙齿排列整齐,齿龈正常,伸舌居中,口腔无异味,咽部正常,双侧扁桃体无肿大,腮腺无肿大压痛,两侧颈部对称,颈静脉正常,颈肝静脉回流证阴性,颈动脉搏动正常,颈软。
- u031：颈部未扪及包块。
- u032：气管居中,甲状腺正常、未触及明显震颤、未闻及明显血管杂音,颈部血管无杂音。
- u033：桶状胸,胸壁静脉不显露,胸壁无肿块,肋间隙增宽,肋骨挤压试验阴性,胸骨无压痛,双侧乳房对称,乳房呈正常发育,乳头无畸形,乳房皮肤未见异常,未扪及包块。
- u034：正常呼吸,呼吸动度两侧对称,双肺语颤两侧减弱,双肺叩诊过清音,双肺呼吸音减低,双肺闻及散在哮鸣音,未闻及湿啰音。
- u035：心前区无隆起,心尖搏动正常,心尖搏动无震荡,心界叩诊在正常范围,心率99次/分,心律规则,心音正常,心脏各瓣膜膜未闻及病理性杂音,无心包摩擦音。
- u036：周围血管征阳性。
- u037：腹部正常,腹部左右对称,腹壁静脉无曲张,腹部软无压痛,肝肝缘下未扪及,Murphy征阴性,脾脏边缘下未扪及,肝脾区无叩痛,全腹未触及及包块,肾区无叩击痛,腹部移动性浊音阴性,膀胱区无压痛,肠鸣音正常,4次/分,腹部未闻及明显血管杂音,肛门外生殖器外观正常,脊柱正常生理弯曲,脊柱四肢无压痛,四肢关节正常,活动自如,双下肢无水肿,无畸形,下肢静脉曲张,杵状指(趾),四肢肌力正常,四肢肌张力正常,腹壁反射正常,肱二头肌反射正常,膝反射正常,跟腱反射正常,霍夫曼征未引出,巴宾斯基征未引出,克匿格征未引出,布鲁津斯基征未引出。
- u039：辅助检查:暂无。
- u041：初步诊断:1.慢性阻塞性肺疾病急性加重2.高血压2级中危3.慢性胃炎
- u042：最后诊断:1.慢性阻塞性肺疾病急性加重2.Ⅱ型呼吸衰竭3.呼吸性酸中毒并代谢性碱中毒4.高血压2级中危5.1高血压性心脏病6.慢性胃炎7.低钾血症

【合并 OCR 原文（仅供上下文理解，不作为 evidence_ids 选择依据）】
主诉：反复咳嗽、咳痰20年，喘累2年，加重10余天。
现病史：20年前患者受凉后反复出现咳嗽、咳白痰，偶咳黄痰，无咯血、痰血，无胸闷、胸痛，呼吸困难，无畏寒、发热，无潮热、盗汗等。于当地医院检查后诊断“慢性阻塞性肺疾病”，经对症治疗好转，平素长期规律吸入“沙美特罗普卡松吸入粉雾剂 1吸 2/日、噻托溴铵吸入粉雾剂 1吸 1/日”，服用“乙酰半胱氨酸泡腾片”等药物治疗，病情控制尚可，症状加重时于当地医院或诊所输液或口服药物治疗后可好转（具体用药不详）。2年前，患者开始出现喘累症状，活动后明显，活动耐量逐渐下降，无夜间阵发性呼吸困难，无下肢水肿等，长期家庭氧疗（吸氧6-8小时/天）。10天前（2023-12-22）患者无明显诱因出现咳嗽、咳痰、喘累加重，咳黄色粘痰，约10-20口/日，痰不易咳出，稍活动即感喘累明显，无咯血及痰中带血，无胸闷、胸痛，无畏寒、发热等。吸入上述药物、口服“左氧氟沙星片、甘草口服液、乙酰半胱氨酸泡腾片”后无好转。为进一步诊治到我院门诊就诊，门诊遂以“慢性阻塞性肺疾病急性加重期”收入我科住院。患病以来，患者精神、食欲欠佳，睡眠一般，大小便正常，体重无明显变化。
既往史：平素身体一般，有“高血压”病史1年余，血压最高达160/90+mmHg，长期口服“厄贝沙坦氢氯噻嗪片 1片 1/日”降压治疗，自测血压波动在130-140/60-70mmHg左右。有“胃炎”病史6年，胃部不适时间断服用“吗丁啉”治疗。否认“糖尿病”、“冠心病”等病史，否认肝炎、结核等传染病史，否认手术史，否认外伤史，否认输血史，否认血制品史，有“四环素”过敏史，否认食物过敏史，预防接种按计划进行。
个人史：生于重庆市沙坪坝区，在原籍长大，无长期外地居住史，文化程度大专，干部职员，已退休，无疫区居住史，无疫水、疫源接触史，无放射物、毒物接触史，无毒品接触史，无吸烟史，无饮酒史，无冶游史。
婚育史：已婚，30岁结婚，配偶健康状况良好，夫妻关系和睦，孕2产2，育1男1女。
月经史：14岁初潮，周期20~30天，经期4~6天，绝经后无异常阴道流血流液。
家族史：父母已故，死因不详，有1兄1弟3姐1妹，哥哥、大姐、二姐已故，死因不详，其余健在，子女健康状况良好，家族中无传染病及遗传病史，无特殊疾病。
体温:36.6℃脉搏:99次/分呼吸:20次/分血压:136/68mmHg身高:156cm体重:63kg。
发育正常,营养良好,匀称体型,扶入病房,自动体位,神识清楚,精神欠佳,表情自然,急性病容,语言正常,对答切题,反应灵敏,查体合作。皮肤粘膜正常,无黄染,无出血点,无蜘蛛痣,无瘀点瘀斑,无皮疹,皮肤弹性正常,皮肤温度湿度正常,皮肤无疤痕,皮肤未见明显水肿。全身浅淋巴结未触及肿大,头颅无畸形,无压痛,头发色泽正常,颜面眼睑无浮肿,下垂及闭合不全,睑结膜正常,球结膜无充血水肿,巩膜无黄染,眼球居中活动正常,角膜透明,瞳孔等大等圆,瞳孔:3mm,对光反射正常,双眼粗侧视力正常。外耳道无异常分泌物,双侧乳突区无压痛,双耳粗侧听力正常。鼻翼无煽动,鼻腔通畅,外鼻道无流涕,各鼻窦区无压痛。唇色发绀,口腔粘膜无溃疡,张口正常,牙齿排列整齐,齿龈正常,伸舌居中,口腔无异味,咽部正常,双侧扁桃体无肿大,腮腺无肿大压痛,两侧颈部对称,颈静脉正常,颈肝静脉回流证阴性,颈动脉搏动正常,颈软。颈部未扪及包块。气管居中,甲状腺正常、未触及明显震颤、未闻及明显血管杂音,颈部血管无杂音。桶状胸,胸壁静脉不显露,胸壁无肿块,肋间隙增宽,肋骨挤压试验阴性,胸骨无压痛,双侧乳房对称,乳房呈正常发育,乳头无畸形,乳房皮肤未见异常,未扪及包块。正常呼吸,呼吸动度两侧对称,双肺语颤两侧减弱,双肺叩诊过清音,双肺呼吸音减低,双肺闻及散在哮鸣音,未闻及湿啰音。心前区无隆起,心尖搏动正常,心尖搏动无震荡,心界叩诊在正常范围,心率99次/分,心律规则,心音正常,心脏各瓣膜膜未闻及病理性杂音,无心包摩擦音。周围血管征阳性。腹部正常,腹部左右对称,腹壁静脉无曲张,腹部软无压痛,肝肝缘下未扪及,Murphy征阴性,脾脏边缘下未扪及,肝脾区无叩痛,全腹未触及及包块,肾区无叩击痛,腹部移动性浊音阴性,膀胱区无压痛,肠鸣音正常,4次/分,腹部未闻及明显血管杂音,肛门外生殖器外观正常,脊柱正常生理弯曲,脊柱四肢无压痛,四肢关节正常,活动自如,双下肢无水肿,无畸形,下肢静脉曲张,杵状指(趾),四肢肌力正常,四肢肌张力正常,腹壁反射正常,肱二头肌反射正常,膝反射正常,跟腱反射正常,霍夫曼征未引出,巴宾斯基征未引出,克匿格征未引出,布鲁津斯基征未引出。
辅助检查:暂无。
初步诊断:1.慢性阻塞性肺疾病急性加重2.高血压2级中危3.慢性胃炎
最后诊断:1.慢性阻塞性肺疾病急性加重2.Ⅱ型呼吸衰竭3.呼吸性酸中毒并代谢性碱中毒4.高血压2级中危5.1高血压性心脏病6.慢性胃炎7.低钾血症
