# 后端 TDD — 算法模块端口与失败契约

> 本项目内不得实现真实 OCR/LLM/图像处理，也不得实现基于规则的字段抽取兜底。

## 端口定义

```ts
type ImageProcessingPort = {
  process(input: { original_path: string; quad_points?: QuadPoints | null }): Promise<ImageProcessingResult>;
};

type DocumentParsingPort = {
  parse(input: { image_paths: string[]; task_id: string }): Promise<DocumentResult>;
};

type FieldExtractionPort = {
  extract(input: { document_result: DocumentResult; schema: FieldSchema }): Promise<StructuredField[]>;
};
```

## 失败契约

- `ImageProcessingPort` 未配置或异常时，任务处理失败，错误码为 `ALGORITHM_MODULE_NOT_CONFIGURED` 或 `ALGORITHM_MODULE_FAILED`。
- `DocumentParsingPort` 未配置、异常或返回空页结果时，任务处理失败。
- `FieldExtractionPort` 未配置、异常、返回空字段候选、返回 schema 之外字段或返回契约非法字段时，任务处理失败。
- 处理流程不得崩溃；但也不得生成"空成功结果"、不得进入人工降级流程、不得允许后端基于 schema 或规则生成替代字段。

契约测试可以使用 fixture 适配器模拟外部团队未来交付结果，但不得在本项目实现识别或抽取算法。
