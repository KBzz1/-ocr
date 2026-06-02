# 后端 TDD — Fixtures 参考

## 上传图片 fixture

| 文件 | 用途 | 注意 |
|------|------|------|
| `sample_page_1.jpg` | 普通图片上传 | 不用于 OCR 正确性断言 |
| `sample_page_2.png` | 多页上传 | 不用于 OCR 正确性断言 |
| `sample_large.jpg` | 文件大小校验 | 可用生成文件替代真实大图 |
| `sample_not_image.pdf` | 非图片拒绝 | 验证文件类型 |
| `sample_upload_status.json` | 手机上传状态 | 验证任务图片列表和上传计数 |

## 算法未配置错误 fixture

```json
{
  "task_id": "task_20260511_0001",
  "status": "failed",
  "error_code": "ALGORITHM_MODULE_NOT_CONFIGURED",
  "error_message": "算法模块未配置，无法生成结构化字段"
}
```

## fixture 解析结果

```json
{
  "pages": [
    {
      "page_no": 1,
      "status": "success",
      "plain_text": "fixture text from external parser",
      "blocks": [],
      "tables": []
    }
  ],
  "merged_text": "fixture text from external parser"
}
```

说明：该文本只用于验证"外部结果被原样保存"，不用于验证 OCR 或语义准确性。

## fixture 字段候选

```json
[
  {
    "field_key": "chief_complaint",
    "field_name": "主诉",
    "original_value": "fixture value from external extractor",
    "evidence": "fixture evidence",
    "page_no": 1,
    "confidence": "medium"
  }
]
```

说明：字段值只代表外部模块返回，不代表本项目抽取能力。

## 慢阻肺 schema fixture

```json
{
  "version": "1.0.0",
  "document_type": "copd_admission_record",
  "groups": [
    {
      "group_key": "basic_info",
      "group_name": "患者基本信息",
      "fields": [
        { "field_key": "name", "field_name": "姓名", "value_type": "text" },
        { "field_key": "gender", "field_name": "性别", "value_type": "text" }
      ]
    },
    {
      "group_key": "admission_course",
      "group_name": "慢阻肺入院记录",
      "fields": [
        { "field_key": "chief_complaint", "field_name": "主诉", "value_type": "long_text" }
      ]
    }
  ]
}
```
