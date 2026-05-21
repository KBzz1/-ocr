# 后端 TDD — OCR/文档解析端口与慢阻肺字段结果契约

> 本项目内不得实现真实 OCR、图像处理、裁剪或透视矫正。慢阻肺/呼吸系统入院记录专病字段抽取属于当前主代码范围，具体设计见 `docs/superpowers/specs/2026-05-21-copd-field-extraction-design.md`。

## 端口定义

```ts
type ImageProcessingPort = {
  process(input: { original_path: string; quad_points?: QuadPoints | null }): Promise<ImageProcessingResult>;
};

type DocumentParsingPort = {
  parse(input: { image_paths: string[]; task_id: string }): Promise<DocumentResult>;
};

type FieldExtractionPort = {
  extract(input: { document_result: DocumentResult; schema: FieldSchema }): Promise<FieldResult[]>;
};
```

`FieldResult` 是按 schema 全量返回的字段结果。每个字段保留自动值、证据、抽取状态、字段级复核状态、质量风险标记和 OCR 纠偏审计信息；未抽到字段也应作为空值结果进入审核页。

## 失败契约

- `ImageProcessingPort` 未配置或异常时，任务处理失败，错误码为 `ALGORITHM_MODULE_NOT_CONFIGURED` 或 `ALGORITHM_MODULE_FAILED`。
- `DocumentParsingPort` 未配置、异常或返回空页结果时，任务处理失败。
- 慢阻肺字段抽取未配置、异常、全字段为空、返回 schema 之外字段或返回契约非法字段时，任务处理失败。
- 单字段 evidence 可疑、OCR 疑似错误或复核失败时，字段进入审核页提示人工核验，不直接让整个任务失败。
- 处理流程不得崩溃；不得在无原文证据时生成医学值。

契约测试可以使用 fixture 或可注入 LLM 客户端模拟字段抽取结果。
