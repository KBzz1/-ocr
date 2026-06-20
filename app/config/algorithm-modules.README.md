# app/config/algorithm-modules

算法子系统配置预留目录。

## 范围

- 图像处理子系统位置。
- OCR 和文档解析子系统位置。
- LLM 结构化字段抽取子系统位置。
- 端口契约版本。

当前不提交具体部署参数、真实模型路径、患者数据路径或密钥。算法子系统未配置或不可用时，任务处理必须失败并明确报错。

## 默认算法运行时

当前默认运行时使用一个本地 `qwen-vision-vllm-server` 常驻服务，同时承担：

- 图片 OCR：后端按任务页顺序提交图片消息。
- 固定字段结构化抽取：后端提交 text-only 固定字段 prompt，要求 JSON 对象输出。

后端通过 OpenAI Python SDK 调本地 vLLM `/v1`，不接入云 API。字段体系、`not_found` 语义、诊断原文摘录约束和 evidence 回填契约由 `admission_record_structured_fields.v1.yaml` 与后端契约测试维护。

## 配置示例

```yaml
algorithms:
  enable_local_ocr: true
  enable_copd_extractor: true
  qwen_vllm_server_url: "http://qwen-vision-vllm-server:8000/v1"
  qwen_vllm_model_name: "Qwen3.5-4B-AWQ-4bit"
  qwen_vllm_model_dir: "./models/llm/Qwen3.5-4B-AWQ-4bit"
  qwen_vllm_max_model_len: 16384
  qwen_vllm_gpu_memory_utilization: 0.85
  qwen_vllm_max_num_seqs: 1
  qwen_ocr_temperature: 0.0
  qwen_ocr_max_tokens: 4096
  qwen_ocr_timeout_seconds: 240
  qwen_extraction_temperature: 0.0
  qwen_extraction_max_tokens: 8192
  qwen_extraction_timeout_seconds: 360
  gpu_stage_queue_enabled: true
```

## 8GB 显存约束

- `qwen_vllm_max_model_len` 默认 16384，不得使用 30000 作为 8GB 默认。
- `qwen_vllm_gpu_memory_utilization` 默认 0.85。
- `qwen_vllm_max_num_seqs` 默认 1。
- OCR 和固定字段抽取 temperature 默认 0.0。
- 同一任务从 OCR 到固定字段抽取连续持有 `qwen_ocr_and_extraction` GPU 阶段；已有合法 `document_result.json` 的重试只重跑固定字段抽取。

## OCR 输出边界

OCR 可过滤页眉、页脚、页码、打印时间、医院页眉页脚、医生签名和手签等非正文干扰。OCR 不得纠正文书正文、补全、总结、重排页面、做标题字符串替换或医学推理。

## 隐私边界

事件日志只记录服务名、模型名、页数、耗时、token/timeout 配置、失败原因等诊断字段。不得记录完整 OCR 文本、完整 prompt、模型完整输出、图片 base64、真实患者身份信息或本机私有路径。
