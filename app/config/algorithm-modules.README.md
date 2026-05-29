# app/config/algorithm-modules

外部算法模块配置预留目录。

## 范围

- 图像处理模块位置。
- OCR 和文档解析模块位置。
- LLM 字段抽取模块位置。
- 模块契约版本。

当前不提交具体配置值。模块未配置时，任务处理必须失败并明确报错。

## 本地 OCR 接入

`manzufei_ocr` conda 环境需要安装 PaddleOCR-VL 依赖。当前验证过的组合：

```bash
conda run -n manzufei_ocr python -m pip install paddlepaddle-gpu==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
conda run -n manzufei_ocr python -m pip install "paddleocr[doc-parser]==3.5.0" "paddlex[serving]==3.5.0"
```

Docker 离线部署镜像必须和该组合保持一致：`paddlepaddle-gpu==3.2.1`、`paddleocr==3.5.0`、`paddlex[ocr]==3.5.0`。不要只锁定 `paddleocr` 而放宽 `paddlex`，PaddleOCR-VL 的实际 pipeline 逻辑依赖 PaddleX。

Python runner 配置：

```yaml
algorithms:
  enable_local_ocr: true
  local_ocr_python_executable: "/home/kbzz1/miniconda3/envs/manzufei_ocr/bin/python"
  local_ocr_script_path: "./app/backend/services/algorithm_ports/paddleocr_vl_batch_runner.py"
  local_ocr_work_root: "/tmp/manzufei_ocr_ocr_runs"
  local_ocr_max_new_tokens: 1024
  local_ocr_timeout_seconds: 180
  local_ocr_device:
  local_ocr_max_pixels: 501760
```

### PaddleOCR-VL 集成结论

2026-05-23 根因定位：PaddleX 的 VLM 推理默认 `max_new_tokens=8192`，在 RTX 4060 (8GB) 上 KV cache 超出显存容量，导致生成极慢甚至卡死。传入 `max_new_tokens=1024` 后，同一张屏摄病历约 46 秒完成，输出完整。

`local_ocr_max_new_tokens` 默认值 1024，对单页病历足够。如后续重新调参，需用同一组脱敏样本记录耗时、显存峰值、输出字节数和是否存在缺页/幻觉，再更新本说明。

2026-05-25 复发根因定位：手机上传原图 1800x4000，比此前验证样本 1919x1080 大很多。即使限制了 `max_new_tokens`，视觉输入过大仍会让显存接近满载并长时间低利用率。`local_ocr_max_pixels=1003520` 仍存在长尾卡死，当前默认传入 `local_ocr_max_pixels=501760`（28*28*640）作为 8GB 显卡保守上限。

2026-05-28 Windows Docker 部署根因定位：同一参数在 WSL conda 环境正常，但 Windows Docker 离线包中 OCR 子进程在加载 PaddleOCR-VL 权重后长时间低 GPU 利用率并最终 540 秒超时。日志确认 runner 参数为 `--device gpu:0 --max-new-tokens 1024 --max-pixels 501760`，镜像和代码已同步；差异为 Docker 镜像安装了 `paddlex==3.5.2`，而已验证 WSL 环境为 `paddlex==3.5.0`。将 Docker 依赖回退并锁定到 `paddlex[ocr]==3.5.0` 后，Windows OCR 验证通过。

2026-05-29 Windows Docker 复发根因定位：显存已被 PaddleOCR-VL 加载满，但 GPU 利用率低且事件流停在 `ocr_runner_started`。复现发现 OCR 子进程 stdout/stderr 使用 `PIPE`，父进程在子进程退出前不读取；PaddleOCR/PaddleX 日志写满管道后会阻塞推理进程。后端改为将 runner stdout/stderr 写入工作目录日志文件，并只把尾部摘要写入事件日志，避免日志管道反压导致假性 GPU 卡死。

`local_ocr_timeout_seconds` 默认 180，表示单页 OCR 超时预算；多页任务的 runner 超时按页数线性放大。单页 OCR 超过 180 秒视为外部模块异常并进入失败，避免界面长期停在“处理中”。

同一图片放在 `/tmp` 工作目录下可正常返回，而放在 `data/ocr_runs` 下出现过 120 秒超时；当前配置将 `local_ocr_work_root` 指向 `/tmp/manzufei_ocr_ocr_runs`。

OCR runner 执行超时或异常时，事件日志记录 `ocr_runner_started`、`ocr_runner_finished`、`ocr_runner_timeout`，包含退出码和 stdout/stderr 尾部。整体 Docker 部署中，OCR runner 作为后端进程内的子进程调用，不再单独起 OCR 容器。

## 本地 LLM 字段抽取

Windows Docker 离线部署必须使用 CUDA 版 `llama-cpp-python==0.3.22`。不要在 `requirements.docker.txt` 中安装默认 PyPI wheel；默认 wheel 可能是 CPU-only，表现为字段抽取阶段显存为空、后端 Python 进程高 CPU/RSS、结构化抽取极慢或失败。

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
