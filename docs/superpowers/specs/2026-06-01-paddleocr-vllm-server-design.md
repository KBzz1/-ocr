# PaddleOCR-VL 常驻服务与 8GB GPU 队列设计

## 背景

当前后端通过 `paddleocr_vl_batch_runner.py` 子进程调用 `PaddleOCRVL`，每个任务都会启动 Python runner、初始化 PaddleOCR pipeline，并在进程内加载模型。这个模式已经通过 `max_new_tokens=1024`、`max_pixels=501760`、依赖版本锁定和日志管道修复解决了多次卡死问题，但仍存在明显冷启动成本。

`temp/paddlepaddle` 验证目录展示了更快的运行形态：PaddleOCR-VL 通过 vLLM server 常驻 GPU 显存，OCR 客户端只负责提交图片、保存结果和合并 Markdown。提速来源主要是避免重复加载模型和重复初始化 CUDA/vLLM 上下文，不是更换 OCR 模型或改写图像内容。

目标是在不降低识别准确率的前提下，把该运行形态整理进正式系统，并适配 RTX 5060 8GB 显存。临时方案已在 RTX 4070 Laptop 8GB 上流畅运行；目标 PC 的 RTX 5060 8GB 算力预计足够承接，但显存容量仍是主要约束，因此正式方案继续按 8GB 显存做保守参数和 GPU 阶段排队。

## 目标

- PaddleOCR-VL 模型作为 Docker Compose 中的常驻 GPU 服务运行。
- 后端任务仍沿用现有流程：多页上传、处理任务、保存 `document_result.json`、进入慢阻肺字段抽取、进入人工审核页。
- 同一患者一次任务可包含多张图片，OCR 阶段统一识别并生成每页文本与 `merged_text`。
- 8GB GPU 上必须串行执行 GPU 阶段，避免 OCR 和 LLM 同时抢显存。
- OCR 已成功但 LLM 失败时，重试复用已保存的 OCR 结果，只重跑字段抽取。
- 所有真实 OCR、图像预处理、裁剪、透视矫正仍由外部模块或 PaddleOCR-VL 运行栈承担；本仓库只做端口编排、调用、契约校验、状态和日志。

## 非目标

- 不实现 OCR 算法、图像增强、裁剪或透视矫正。
- 不让前端从 OCR 文本、schema 或页面内容推断结构化字段。
- 不为 8GB GPU 做多患者并发推理。
- 不把 `temp/paddlepaddle` 目录、镜像 tar 包或临时模型文件直接纳入正式代码。
- 不在本次改造中更换慢阻肺字段抽取 schema 或字段语义。

## 推荐架构

Docker Compose 增加一个常驻服务：

```text
manzufei-ocr-backend
  - Flask API、任务状态、持久化、字段抽取编排、审核页静态资源

paddleocr-vlm-server
  - PaddleOCR-VL 模型
  - vLLM backend
  - 挂载 models/ppstructure 或独立 PaddleOCR-VL 模型目录
  - 暴露容器内 HTTP 接口给后端
```

后端新增 `PaddleOCRVLMServerDocumentPort`，实现现有 `DocumentParsingPort` 契约。该端口负责：

- 读取任务页列表和 `processed_path`。
- 按 `page_no` 排序后逐页提交到 OCR 服务。
- 生成每页 `status/text/blocks/tables/source`。
- 合并所有成功页文本为 `merged_text`。
- 如果任一页面缺失输出、OCR 服务不可达、返回结构非法或全部文本为空，按文档解析失败处理。

现有 `LocalPaddleOCRDocumentPort` 先保留为 fallback。服务化 OCR 稳定后，再单独清理旧 runner、旧配置和过期文档。

## GPU 阶段队列

5060 8GB 显存下必须有单进程内 GPU 阶段队列。队列不是业务任务队列，而是 GPU 临界区：

```text
task process
  -> acquire GPU stage: ocr
  -> OCR service batch parse
  -> release GPU stage
  -> persist document_result.json
  -> acquire GPU stage: llm
  -> COPD field extraction
  -> release GPU stage
  -> persist review result
```

规则：

- 任意时刻只允许一个 GPU 阶段运行。
- OCR 阶段和 LLM 阶段不能重叠。
- 多个任务同时点击处理时，后到任务等待 GPU 队列。
- 队列等待期间任务保持可观察状态，事件日志记录 `gpu_stage_waiting`、`gpu_stage_started`、`gpu_stage_finished`。
- 队列释放必须放在 `finally` 路径，避免异常后 GPU 阶段永久锁死。
- 当前部署是单后端容器，先使用进程内锁即可；未来如果多后端实例，需要替换为文件锁或本地持久化锁。

## 参数策略

8GB 默认值必须保守，优先稳定和准确输出：

```yaml
ocr_vlm_server:
  max_model_len: 4096
  gpu_memory_utilization: 0.75
  tensor_parallel_size: 1
  max_num_seqs: 1
  dtype: bfloat16

ocr_request:
  max_new_tokens: 1024
  max_pixels: 501760
```

说明：

- `max_num_seqs` 不沿用临时目录中的 8。该值适合更大显存或吞吐场景，8GB 下容易触发显存紧张和长尾卡死。
- `max_pixels=501760` 沿用当前系统已验证的 8GB 保守上限，避免手机原图过大导致视觉 token 激增。
- `max_new_tokens=1024` 沿用当前系统已验证值，减少 KV cache 压力。若后续发现长页病历被截断，必须用同一组脱敏样本记录耗时、显存峰值、输出字节数、缺页和幻觉情况后再调大。
- 模型版本、依赖版本和参数变更必须进入部署文档，不能在 Dockerfile 中放宽到未验证组合。

## 临时方案验证组合

新服务化方案优先参考 `temp/paddlepaddle` 中已经跑通的组合，而不是直接套用旧子进程 runner 的依赖结论：

- VLM 服务镜像：`ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-genai-vllm-server:latest-nvidia-gpu`，当前离线 tar 的 OCI digest 为 `sha256:1cee5e7e26e666bcd80d2a9741c450438bf507268cbfb14e0e0d33b8d5259621`。
- OCR 客户端镜像：`paddleocr-client:latest`。
- OCR 客户端实际 Python 包：`paddlepaddle-gpu==3.2.1`、`paddleocr==3.5.0`、`paddlex==3.5.2`。
- 模型目录：`model/PaddleOCR-VL-1.6`，`inference.yml` 中模型名为 `PaddleOCR-VL-1.6-0.9B`。
- 当前 compose 命令中存在 `--model_name PaddleOCR-VL-1.5-0.9B` 与 1.6 模型目录混用，正式方案必须统一为验证通过的 1.6 命名和目录。

旧 runner 在 Windows Docker 中曾因 `paddlex==3.5.2` 超时而锁回 `paddlex[ocr]==3.5.0`；该结论适用于“后端子进程内直接加载 PaddleOCRVL”的旧路径。新路径把 VLM 推理移到官方 vLLM server，已经在 4070 Laptop 8GB 上验证可流畅运行，因此正式实现应单独记录并锁定新服务化组合。为避免 `latest` 漂移，离线包应优先固定镜像 digest 或保存经过验证的 tar 包。

## 从 temp 半搬迁

`temp/paddlepaddle` 可以作为新方案的实现基线，但不能原样整目录搬进正式系统。正式改造采用“复用核心运行栈，重写业务接入层”的半搬迁策略。

可以直接复用或等价迁移：

- `vlm-server` 官方镜像和已验证离线 tar。
- `PaddleOCR-VL-1.6` 模型目录。
- `vlm_backend_config.yaml` 的 vLLM 参数基线。
- `Dockerfile.ocr-client` 中已验证的 Python 运行栈和依赖组合。
- `process.py` 中 `PaddleOCRVL(vl_rec_backend="vllm-server", vl_rec_server_url=...)` 的调用方式。
- `process_single_file()` 中逐页 `pipeline.predict()`、保存 markdown/json 的核心逻辑思路。

不能原样搬迁：

- `manage.bat`。它处理完成后会 `docker compose down`，会破坏 PaddleOCR-VL 常驻显存的提速前提。
- `input/`、`output/` 和 `input/processed/` 目录生命周期。正式系统已经有任务、页面、结果存储和隐私边界，OCR 不应另建一套上传归档流程。
- `archive_processed`。正式任务页不能被 OCR 客户端移动位置，页面文件生命周期由后端任务服务管理。
- 独立 `ocr-client` 批处理容器作为业务入口。正式系统的任务状态、错误码、重试和事件日志必须仍由后端掌控。
- `latest-nvidia-gpu` 裸 tag。正式离线包必须固定验证过的 digest 或保存验证 tar，避免镜像漂移。
- 1.5/1.6 模型名混用。正式配置必须统一。

正式实现应把临时脚本提炼为后端 `DocumentParsingPort` 适配器：后端接收任务页列表，调用常驻 OCR 服务，生成现有 `DocumentResult`，再进入后续 LLM 字段抽取。这样可以复用已验证的速度优势，同时不把临时批处理脚本的文件搬运、归档和容器关闭逻辑带入业务主流程。

## 准确率边界

该方案本身不应降低 OCR 准确率，因为它不改变以下内容：

- 不更换 PaddleOCR-VL 模型。
- 不压缩、裁剪或重写用户上传图片。
- 不让后端或前端补造 OCR 文本。
- 不改变后续 LLM 字段抽取证据要求。

可能影响准确率或完整性的变量只有：

- `max_pixels` 过低导致视觉输入细节不足。
- `max_new_tokens` 过低导致输出截断。
- PaddleOCR/PaddleX/vLLM 版本或镜像 digest 漂移。
- 1.5/1.6 模型名称和权重目录混用。

因此正式实现必须：

- 统一模型名称和模型目录。
- 锁定服务化 OCR 的已验证组合：官方 vLLM server 镜像 digest、`PaddleOCR-VL-1.6-0.9B` 模型目录、`paddlepaddle-gpu==3.2.1`、`paddleocr==3.5.0`、`paddlex==3.5.2`。如果后续改回旧 runner fallback，旧 runner 仍按其文档锁定 `paddlex[ocr]==3.5.0`。
- 用同一组脱敏多页病历样本对比旧 runner 与新 server 输出，记录每页耗时、总耗时、输出字节数、缺页、明显截断和关键字段证据覆盖情况。
- 默认不以性能参数换准确率；任何降低 `max_pixels` 或 `max_new_tokens` 的调整都必须有样本验证记录。

## 任务状态与失败处理

文档解析端口失败契约保持不变：

- OCR 服务不可达、超时、返回非法结构、单页缺失结果、全部文本为空：任务进入 `failed`。
- 单字段可疑或证据不足不导致整个任务失败，进入审核页由人工核验。
- OCR 成功后必须先写入 `results/{task_id}/document_result.json`。
- LLM 失败后重试时，如果 `document_result.json` 存在且契约合法，编排器复用该 OCR 结果，只进入 LLM 队列。
- 取消任务时，如果正在等待 GPU 队列，应直接取消；如果已进入 OCR 或 LLM 阶段，应在阶段返回后停止后续阶段并标记取消或失败，不能留下半写结果。

## 部署与清理

正式部署包需要包含：

- 后端镜像。
- `paddleocr-vlm-server` 镜像或离线导入包。
- 统一的 Docker Compose。
- 模型挂载目录和配置示例。
- 依赖版本核验命令。

清理策略分阶段执行：

1. 第一阶段保留旧 runner fallback，不删除旧配置。
2. 第二阶段新服务完成 Windows Docker 离线验证后，删除未使用的临时 OCR 客户端脚本、旧模型副本和 tar 包。
3. 第三阶段同步更新 `docs/部署/GPU-Docker部署.md`、`app/config/algorithm-modules.README.md` 和离线验收记录。

不得提交真实 `data/`、`exports/`、`logs/` 运行数据，不得提交临时病历原图。

## 测试与验收

单元测试：

- `PaddleOCRVLMServerDocumentPort` 能把多页 OCR 响应转换成现有 `DocumentResult`。
- 服务不可达、超时、缺页、空文本、非法响应均映射为文档解析失败。
- GPU 队列保证 OCR 和 LLM 阶段串行，异常时释放锁。
- OCR 成功、LLM 失败后的重试复用 `document_result.json`。

集成测试：

- 后端配置 `enable_local_ocr` 或新增 `local_ocr_mode: vlm_server` 后使用服务化端口。
- 多页上传任务完整跑通到审核页。
- 并发两个任务时，第二个任务等待 GPU 队列，不并发进入 OCR/LLM。

现场验收：

- 5060 8GB Windows Docker 下 `nvidia-smi` 可见 OCR server 常驻显存。
- 第一单包含模型加载时间；后续单不重复冷启动。
- 同一组脱敏样本对比旧 runner 和新 server：输出无缺页、无明显截断，关键字段证据仍能被 LLM 抽取。
- 记录首单耗时、热启动后耗时、OCR 阶段耗时、LLM 阶段耗时和失败重试耗时。
