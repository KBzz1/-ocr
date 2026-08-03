# 评估体系独立成文件夹（evaluation-directory-restructure）设计

## 1. 背景与动机

观测与评估阶段（评估工具链、金标数据、实验文档、外部架构师记录）已发展得比较完整，但资产分散在仓库 5 处：

| 类型 | 现状位置 |
|---|---|
| 评估代码 | `app/backend/evaluation/`（8 文件，1290 行） |
| 评估测试 | `app/backend/tests/test_evaluation_*.py`（5 文件） |
| 金标/校准/报告 | `data/evaluation/`（gitignored） |
| 人工标注原始素材 | `data/text_data/`（ground_truth/ ocr_results/ output/，gitignored） |
| 实验文档 | `docs/superpowers/specs/`、`docs/superpowers/plans/`（评估系 6+5 份）、`docs/codex_design/`（3 任务）、`docs/可视化html/`（2 份报告） |

评估是纯研究/性质的工作，与生产业务解耦（业务代码对 `app/backend/evaluation/` 零反向依赖，只有 `run_eval.py` CLI 与测试引用它），具备独立成体系的条件。本次将其收拢为顶层 `evaluation/` 文件夹，使整体架构清晰。

## 2. 目标与边界

### 目标

- 评估体系（代码 + 测试 + 数据 + 文档）收拢为顶层 `evaluation/` 文件夹，自洽完整
- 全仓库 `CLAUDE.md` 统一为指向同目录 `AGENTS.md` 的映射指针，`AGENTS.md` 成为唯一内容源，消除双份漂移
- 迁移不改变任何评估行为：指标口径、管线组装、CLI 参数、金标格式均不变

### 边界（明确不做）

- 不修改 `app/backend/` 业务代码（评估迁出后业务侧 import 不变）
- 不改变评估指标、金标内容、报告格式
- 不迁移业务实现的 spec/plan（copd 抽取、批处理引擎、导出、部署等）
- 不迁移 `.superpowers/sdd/` 任务执行产物
- 不迁移 `docs/可视化html/` 下非评估报告
- 不做 AGENTS.md 内容重写：只做漂移合并 + evaluation 相关更新，不重构已有规则表述

## 3. 目标目录结构

```
evaluation/                      # 顶层目录（不是 Python 包）
├── README.md                    # 总览：定位、目录索引、快速开始
├── code/                        # Python 包（包名 evaluation.code）
│   ├── __init__.py
│   ├── metrics.py  runner.py  run_eval.py  calibrate.py
│   └── chunked_review.py  feedback.py  desensitize.py
├── tests/                       # test_evaluation_*.py（5 个迁入）
├── data/                        # 由 data/evaluation/ 与 data/text_data/ 迁入
│   ├── README.md
│   ├── golden/  calibration/  reports/
│   └── text_data/               # ground_truth/ ocr_results/ output/ output.zip
└── docs/
    ├── README.md                # 实验文档索引（含新旧路径映射说明）
    ├── specs/  plans/           # 评估系 6 spec + 5 plan 迁入
    ├── codex_design/            # 3 个架构师任务记录迁入
    └── reports/                 # docs/可视化html/ 下 4 份评估报告 HTML 迁入
```

## 4. 迁移清单

| # | 资产 | 来源 → 目标 |
|---|---|---|
| 1 | 评估代码 8 文件 | `app/backend/evaluation/` → `evaluation/code/` |
| 2 | 评估测试 5 文件 | `app/backend/tests/test_evaluation_*.py` → `evaluation/tests/` |
| 3 | 评估数据 | `data/evaluation/` → `evaluation/data/`（gitignored，主仓库物理迁移） |
| 4 | 人工标注原始素材 | `data/text_data/` → `evaluation/data/text_data/`（gitignored，主仓库物理迁移） |
| 5 | 评估系 spec 6 份 | `docs/superpowers/specs/2026-08-01~08-03` 评估/复核/提示词实验 6 份 → `evaluation/docs/specs/` |
| 6 | 评估系 plan 5 份 | `docs/superpowers/plans/` 对应 5 份 → `evaluation/docs/plans/` |
| 7 | codex_design 3 任务 | `docs/codex_design/` 整个目录 → `evaluation/docs/codex_design/` |
| 8 | 评估报告 HTML 4 份 | `docs/可视化html/` 下评估相关 4 份 → `evaluation/docs/reports/` |

### 评估系文档迁移清单（逐份）

**specs（6 份）：** `2026-08-01-evaluation-harness-design.md`、`2026-08-01-verifier-normalization-design.md`、`2026-08-02-verifier-chunked-review-experiment-design.md`、`2026-08-02-verifier-recall-optimization-design.md`、`2026-08-02-prompt-refactor-field-boundary-design.md`、`2026-08-03-verifier-step7-scale-evidence-design.md`

**plans（5 份）：** `2026-08-01-evaluation-harness-implementation-plan.md`、`2026-08-01-verifier-normalization-implementation-plan.md`、`2026-08-02-prompt-refactor-field-boundary-implementation-plan.md`、`2026-08-02-verifier-chunked-review-experiment-implementation-plan.md`、`2026-08-02-verifier-recall-optimization-implementation-plan.md`

> 边界说明：`2026-08-02-prompt-refactor-field-boundary` 与 `2026-08-03-verifier-step7-scale-evidence` 归为提示词/复核实验系，一并迁入（用户已确认）。

**codex_design（3 任务）：** `prompt-policy-metric-alignment-v1/`、`verifier-optimization-v1/`、`verifier-judge-rubric-v1/`

**报告 HTML（4 份）：** `2026-08-01-evaluation-retrospective.html`、`2026-08-01-verifier-normalization-retrospective.html`、`2026-08-01-verifier-normalization.html`、`2026-08-02-verifier-prompt-v3-report.html`（`architecture_overview.html` 为架构总览，不迁）

## 5. 代码迁移细节

1. **导入调整**：包内相对导入（`.metrics`、`.feedback` 等）保留；对 `app.backend` 的向上相对导入全部改为绝对导入：
   - `runner.py`：`..errors` → `from app.backend.errors`；`..services.copd_extraction.*` → `from app.backend.services.copd_extraction.*`
   - `run_eval.py`：`..services.algorithm_ports.qwen_vllm_client`、`..services.copd_extraction.llm_client/prompts`、`..services.schema_loader` → 对应绝对导入
   - `chunked_review.py`：`..services.copd_extraction.evidence_context` → 绝对导入
   - `metrics.py`：`..services.copd_extraction.field_policies` → 绝对导入
   - `calibrate.py`：仅 stdlib，无需改
2. **路径基准修正**：`run_eval.py` 的 `_BATCH_SCHEMA_PATH` 中 `Path(__file__).parents[3]` → `parents[2]`（`evaluation/code/run_eval.py` 到仓库根少一级）；同类基于 `__file__` 的路径计算一并核查
3. **CLI 命令变更**：`python -m app.backend.evaluation.run_eval` → `python -m evaluation.code.run_eval`（仓库根运行；`app` 与 `evaluation` 均为 namespace 包，无需安装）
4. **删除** `app/backend/evaluation/` 目录

## 6. 测试迁移细节

1. 5 个 `test_evaluation_*.py` 迁入 `evaluation/tests/`
2. 测试内 `from app.backend.evaluation.xxx import ...` → `from evaluation.code.xxx import ...`
3. 检查 `app/backend/tests/` 的 conftest.py/fixtures 是否被评估测试依赖；如依赖则 `evaluation/tests/` 建立独立 conftest（或最小化 fixtures 内联）
4. 运行方式统一：仓库根 `conda run -n manzufei_ocr python -m pytest evaluation/tests -q`（`python -m` 保证仓库根进 sys.path，`evaluation.code` 与 `app.backend` 均可导入）

## 7. 数据迁移细节

- `data/evaluation/`、`data/text_data/` 均为 gitignored 本地数据，主仓库与 worktree 各自独立、不同步
- **主仓库物理迁移**（`mv data/evaluation evaluation/data`、`mv data/text_data evaluation/data/text_data`），目标仓库根执行；worktree 侧从主仓库复制同步（实施计划中单独列步骤）
- `.gitignore`：`data/evaluation/*` → `evaluation/data/*`，保留 `!evaluation/data/README.md` 特例；`data/text_data` 迁移后由 `evaluation/data/*` 一并覆盖
- `evaluation/data/README.md` 保留并更新（说明 golden/text_data 的来源关系：golden 由 text_data/ground_truth 提炼）

## 8. 文档迁移细节

1. **spec/plan 迁移**：物理移动（git mv），内容保持原样；仅批量更新内部引用（见下）
2. **内部引用批量更新**：已迁移文档中 `app/backend/evaluation` → `evaluation.code`（命令形态 `python -m evaluation.code.run_eval`）、`data/evaluation` → `evaluation/data`、`data/text_data` → `evaluation/data/text_data`、`docs/superpowers/specs|plans`（评估系路径）→ `evaluation/docs/specs|plans`（sed 批量 + 人工抽查）
3. **codex_design 保持原样**：外部架构师历史记录，不改内容；`evaluation/docs/README.md` 中注明新旧路径映射
4. **`evaluation/docs/README.md`**：实验文档索引 + 新旧路径映射表 + 新工作流位置声明（评估/复核/提示词实验的 spec/plan 后续直接写 `evaluation/docs/specs|plans/`）
5. **`evaluation/README.md`**：总览（定位、目录索引、快速开始：运行命令、测试命令、数据与文档位置）

## 9. CLAUDE.md / AGENTS.md 全局统一

### 统一形态

- 全仓库所有目录的 `CLAUDE.md` 替换为单行映射指针（根、docs、scripts、deploy、app 各层、algorithm_ports、copd_extraction 等全部配对）
- `AGENTS.md` 成为唯一内容源，接收两份文件的并集内容（取较新表述）

**指针模板：**
```markdown
# CLAUDE.md

本目录工作规则统一维护在 `AGENTS.md`（Claude Code 与 Codex 共用同一内容源），请阅读同目录的 `AGENTS.md`。
```

### 合并与更新顺序（每目录两步）

1. **漂移合并**：把该目录 CLAUDE.md 中比 AGENTS.md 新的内容并入 AGENTS.md（如 app/backend 的 evaluation 条目、patient.py 描述；根目录第 5/57 行的"AGENTS.md / CLAUDE.md"双读表述），同时应用本 spec 的 evaluation 迁移更新
2. **CLAUDE.md 置为指针**

### 涉及 evaluation 迁移的内容更新（写入对应 AGENTS.md）

| 文件 | 更新内容 |
|---|---|
| 根 `AGENTS.md` | 目录职责：`data/` 条目注明评估数据已迁出；新增 `evaluation/` 条目（观测与评估体系，含 code/data/docs/tests 子结构，独立于业务后端）；"CLAUDE.md / AGENTS.md"双提及统一为 `AGENTS.md` |
| `app/backend/AGENTS.md` | evaluation 工具链条目改写：已迁出至顶层 `evaluation/`；金标/报告位置 → `evaluation/data/`；设计文档引用 → `evaluation/docs/specs/`；目录结构列表删除 evaluation/ 项 |
| `docs/AGENTS.md` / `docs/CLAUDE.md` | 文档规则注明：评估/复核/提示词实验的 spec/plan 归属 `evaluation/docs/`（新工作流位置偏好） |
| 新建 `evaluation/AGENTS.md` | 目录定位（观测与评估体系）、结构说明、运行命令（`python -m evaluation.code.run_eval`、`pytest evaluation/tests`）、边界（不参与生产路径、不提交真实数据） |
| 新建 `evaluation/CLAUDE.md` | 指针 |

### 引用清理

统一后文档内"AGENTS.md / CLAUDE.md"双提及改为只读 `AGENTS.md`（根第 5/57 行、docs/CLAUDE.md 第 13/14 行等，合并进 AGENTS.md 时一并改写）。`evaluation/` 新目录的 README 在正文引用 `AGENTS.md`。

## 10. 其他引用面更新

1. `.gitignore`：见第 7 节
2. `scripts/maintenance/generate_verifier_review_html.py`：3 处 `data/evaluation/...` 路径 → `evaluation/data/...`
3. 根 `CLAUDE.md`（合并进根 AGENTS.md 时）目录职责更新（见第 9 节）

## 11. 验证（实施计划阶段执行）

1. `conda run -n manzufei_ocr python -m pytest evaluation/tests -q` 全绿
2. `conda run -n manzufei_ocr python -m pytest app/backend/tests -q` 全绿（业务侧零改动证明）
3. `python -m evaluation.code.run_eval --help` 冒烟
4. `grep -rn "app.backend.evaluation" app/ scripts/ evaluation/` 无残留（文档内除外）
5. `git status` 确认 `app/backend/evaluation/`、`data/` 下无残留迁移遗漏
6. 抽查 `evaluation/docs/README.md` 索引与磁盘一致

## 12. 测试约定

- 全部沿用现有 pytest/conda 约定（`conda run -n manzufei_ocr`）
- 迁移不改行为：不新增测试逻辑，测试文件只改导入与路径
- 实施过程遵循 TDD 惯例：迁移完成后跑全量验证（第 11 节）作为回归

## 13. 风险与对策

| 风险 | 对策 |
|---|---|
| 导入遗漏导致 `evaluation.code` 导入失败 | 第 11 节验证 1/4（pytest 全绿 + grep 残留） |
| `__file__` 路径层级计算错误 | 第 11 节验证 3（CLI 冒烟）；实施时核查所有 `Path(__file__)` 用例 |
| 文档内部引用不一致 | 第 8 节 sed 批量 + 人工抽查；`evaluation/docs/README.md` 提供新旧映射 |
| 数据迁移两工作区不同步 | 主仓库执行 + worktree 复制同步（第 7 节） |
| CLAUDE.md 统一后内容丢失（漂移方向判断错） | 每目录先合并后置指针；以较新内容为准 |
