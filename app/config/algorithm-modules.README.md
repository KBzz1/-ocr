# app/config/algorithm-modules

算法子系统配置预留目录。

## 范围

- 图像处理子系统位置。
- OCR 和文档解析子系统位置。
- LLM 结构化字段抽取子系统位置。
- 端口契约版本。

当前不提交具体配置值。算法子系统未配置时，任务处理必须失败并明确报错。

## 本地 OCR 接入

### 服务化 OCR

当前正式部署和本地启动使用 `paddleocr-vlm-server` 常驻服务。离线镜像 tar 放在 `deploy/offline-images/paddleocr-vlm-server.tar`，任务生命周期仍由后端管理。后续可替换为新的本地 OCR/LLM 视觉算法子系统，但必须同步端口契约、部署配置和失败语义。

服务化 OCR 当前验证组合：`paddlepaddle-gpu==3.2.1`、`paddleocr==3.5.0`、`paddlex==3.5.2`、`PaddleOCR-VL-1.6-0.9B`、官方 `paddleocr-genai-vllm-server` vLLM 镜像。服务常驻显存后，多个任务可并发提交多页图片，模型加载只发生一次；OCR 阶段和 LLM 字段抽取阶段在 8GB 显存下由 GPU 阶段队列串行执行，避免互相抢占导致 OOM。

`manzufei_ocr` conda 环境需要安装 PaddleOCR-VL 依赖。当前验证过的组合：

```bash
conda run -n manzufei_ocr python -m pip install paddlepaddle-gpu==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
conda run -n manzufei_ocr python -m pip install "paddleocr[doc-parser]==3.5.0" "paddlex[serving]==3.5.0"
```

Docker 离线部署镜像使用 `paddlepaddle-gpu==3.2.1`、`paddleocr==3.5.0`、`paddlex[ocr]==3.5.2`（后端容器内的客户端栈）。不要只锁定 `paddleocr` 而放宽 `paddlex`，PaddleOCR-VL 的实际 pipeline 逻辑依赖 PaddleX。

OCR 服务配置：

```yaml
algorithms:
  enable_local_ocr: true
  local_ocr_vlm_server_url: "http://paddleocr-vlm-server:8080/v1"
  local_ocr_vlm_timeout_seconds: 240
  local_ocr_max_new_tokens: 1024
  local_ocr_max_pixels: 501760
```

### PaddleOCR-VL 集成结论

2026-05-23 根因定位：PaddleX 的 VLM 推理默认 `max_new_tokens=8192`，在 RTX 4060 (8GB) 上 KV cache 超出显存容量，导致生成极慢甚至卡死。传入 `max_new_tokens=1024` 后，同一张屏摄病历约 46 秒完成，输出完整。

`local_ocr_max_new_tokens` 默认值 1024，对单页病历足够。如后续重新调参，需用同一组脱敏样本记录耗时、显存峰值、输出字节数和是否存在缺页/幻觉，再更新本说明。

2026-05-25 复发根因定位：手机上传原图 1800x4000，比此前验证样本 1919x1080 大很多。即使限制了 `max_new_tokens`，视觉输入过大仍会让显存接近满载并长时间低利用率。`local_ocr_max_pixels=1003520` 仍存在长尾卡死，当前默认传入 `local_ocr_max_pixels=501760`（28*28*640）作为 8GB 显卡保守上限。

`local_ocr_vlm_timeout_seconds` 默认 240，表示单页 OCR 服务调用超时预算。单页 OCR 超过该预算视为外部模块异常并进入失败，避免界面长期停在“处理中”。

OCR 服务调用开始和结束时，事件日志记录 `ocr_vlm_started`、`ocr_vlm_finished`，包含服务 URL、页数、推理参数、耗时、输出大小和失败原因。

## 本地 LLM/结构化字段抽取

当前 llama.cpp 路径的 Windows Docker 离线部署必须使用 CUDA 版 `llama-cpp-python==0.3.22`。如果切换为 OpenAI-compatible vLLM 服务或其他算法包，需新增对应配置项并保留字段结果契约。不要在 `requirements.docker.txt` 中安装默认 PyPI wheel；默认 wheel 可能是 CPU-only，表现为字段抽取阶段显存为空、后端 Python 进程高 CPU/RSS、结构化抽取极慢或失败。

Docker 镜像需基于 CUDA devel 镜像源码编译：

```bash
CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=89 -DCMAKE_EXE_LINKER_FLAGS=-Wl,-rpath-link,/usr/local/cuda/compat" \
CUDAToolkit_ROOT=/usr/local/cuda \
CUDA_HOME=/usr/local/cuda \
CUDACXX=/usr/local/cuda/bin/nvcc \
FORCE_CMAKE=1 \
python -m pip install --no-binary llama-cpp-python llama-cpp-python==0.3.22
```

2026-05-29 Windows Docker 根因定位：OCR 成功后进入字段抽取，但 GPU 显存为空；容器内 `llama_cpp/lib` 只有 CPU 后端库，`libllama.so` 无 CUDA 依赖。修复后需验证 `llama_cpp/lib` 包含 `libggml-cuda.so`，并用 `--gpus all` 运行容器确认 `libllama.so` 链接到 `libggml-cuda.so`、`libcudart.so.12`、`libcublas.so.12` 和宿主机注入的 `libcuda.so.1`。

2026-05-29 Windows 完整流程验证：字段抽取阶段曾因 LLM 复核 JSON 在 `comment` 字段中被 `max_tokens=1024` 截断而失败，表现为 `LLM JSON parse failed: Unterminated string`。当前 Docker 配置将 `llm_max_tokens` 固定为 4096，复核 prompt 限制 `comment` 不超过 20 个汉字；若 llama.cpp 返回 `finish_reason=length`，后端明确报出“LLM 输出超过 max_tokens 被截断”。失败任务重试时，如果已存在成功的 `document_result.json`，编排器复用该 OCR 结果，避免字段抽取失败后再次触发 OCR 长尾超时。

2026-05-29 字段质量核验补充：`weight_loss` 抽到 `0g`、`0kg`、`0克` 等值时保留模型原值，不自动改为其他数值，但追加 `counterintuitive_zero_weight_loss` 风险标记并将字段置为 `suspicious`。该规则用于提示 OCR/抽取复核，例如 OCR 把“体重减轻6kg”误成“体重减轻0g”。
