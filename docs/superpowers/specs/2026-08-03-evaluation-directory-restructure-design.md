# 评估体系独立成文件夹（evaluation-directory-restructure）设计

## 1. 背景与动机

观测与评估阶段（评估工具链、金标数据、实验文档）已发展得比较完整，但资产分散在仓库多处：

| 类型 | 现状位置 |
|---|---|
| 评估代码 | `app/backend/evaluation/`（8 文件） |
| 评估测试 | `app/backend/tests/test_evaluation_*.py`（5 文件）+ `test_review_feedback.py`（1 文件） |
| 金标/校准/报告 | `data/evaluation/`（gitignored） |
| 人工标注原始素材 | `data/text_data/`（ground_truth/ ocr_results/ output/，gitignored） |
| 实验文档 | `docs/superpowers/specs/`、`docs/superpowers/plans/`（评估系 6+5 份）、`docs/codex_design/`（3 任务）、`docs/可视化html/`（4 份报告） |

评估是研究性质的工作，与生产业务解耦（业务代码对 `app/backend/evaluation/` 零反向依赖，只有 `run_eval.py` CLI 与测试引用它）。本次将其收拢为顶层 `evaluation/` 文件夹，并同步统一全仓规则文件，使整体架构清晰。

## 2. 执行流程与基准

**以主分支（master）实际状态为唯一基准进行整理。执行前先完成 worktree 收拢（2026-08-04 实测）：**

1. **git 层面已全部同步**：
   - `worktree-prompt-refactor-field-boundary`（评估线）：与 master 完全同步（0 ahead / 0 behind，评估线 22 commits 已全部合入 master `711bc60`，含两份 spec），零未提交改动
   - `worktree-review-ocr-floating-window`（Qwen 批处理 + OCR 浮窗线）：18 个独有 commit 仅在分支上，但其功能内容已以更新形态存在于 master（`ReviewOcrFloatingWindow.tsx`、`algorithms/qwen_batch_engine/`、`qwen_batch_admission_record.v2.yaml` 均在 master 树中），分支为历史痕迹，删除不丢工作
2. **未同步的只有 `data/`**（运行产物，不进 git）：worktree 独有的评估数据（44 个文件 + 1 个内容不同）需按第 7 节对账流程并入主仓库再迁移
3. **再整理**：以 master 实际状态为唯一基准，执行本 spec 的评估体系整理
4. **删除 worktree**：整理完成、验证通过后，删除 `worktree-prompt-refactor-field-boundary` 与 `worktree-review-ocr-floating-window` 两个 worktree

迁移不改变任何评估行为：指标口径、管线组装、CLI 参数、金标格式均不变。

## 3. 目标与边界

### 目标

- 顶层建立 `evaluation/`，收拢评估代码、评估测试和评估数据
- 评估代码从 `app/backend/evaluation/` 迁出，**继续单向依赖 `app.backend` 的生产模块**，不包装成完全独立系统
- 全仓统一 CLAUDE.md 与 AGENTS.md：每个目录以 AGENTS.md 为唯一规则内容源，CLAUDE.md 统一为指向同目录 AGENTS.md 的简短入口
- 评估相关 spec、plan 和报告**继续留在 docs/，不做物理迁移**；建立统一索引并更新现行入口
- 同步重构重复、过时、冲突和目录职责已经变化的规则

### 边界（明确不做）

- 不修改 `app/backend/` 生产业务代码（评估迁出后业务侧 import 不变）
- 不改变评估指标、金标内容、报告格式
- 不迁移评估相关 spec、plan、报告（留在 `docs/` 原位）
- **`docs/codex_design/` 完全不动**：目录、文件内容、内部引用均保持原状
- 历史 spec、plan、报告正文不批量改写（不因迁移改写历史记录）
- 不迁移 `.superpowers/sdd/` 任务执行产物
- 不给历史版本补建版本目录/分析文档/全量提示词（版本迭代规范自下一次迭代起生效）
- 不在没有独立规则需求的目录滥增 CLAUDE.md/AGENTS.md（只补齐缺失配对）

## 4. 目标目录结构

```
evaluation/                      # 顶层目录（不是 Python 包）
├── README.md                    # 总览 + 评估文档统一索引 + 版本迭代规范
├── code/                        # Python 包（包名 evaluation.code）
│   ├── __init__.py
│   ├── metrics.py  runner.py  run_eval.py  calibrate.py
│   └── chunked_review.py  feedback.py  desensitize.py
├── tests/                       # test_evaluation_*.py（5 个）+ test_review_feedback.py（1 个）
├── data/                        # 由 data/evaluation/ 与 data/text_data/ 迁入
│   ├── README.md
│   ├── golden/  calibration/  reports/
│   └── text_data/               # ground_truth/ ocr_results/ output/ output.zip
└── versions/                    # 版本迭代归档（自下一次迭代起生效，见第 9 节）
```

> 评估相关 spec/plan 留在 `docs/superpowers/specs|plans/`，报告 HTML 留在 `docs/可视化html/`，`docs/codex_design/` 原地不动——均通过 `evaluation/README.md` 统一索引呈现。

## 5. 代码迁移

1. **迁出**：`app/backend/evaluation/` 8 个文件 → `evaluation/code/`
2. **导入调整**：包内相对导入（`.metrics`、`.feedback` 等）保留；对 `app.backend` 的向上相对导入全部改为绝对导入（继续单向依赖生产模块）：
   - `runner.py`：`..errors` → `from app.backend.errors`；`..services.copd_extraction.*` → `from app.backend.services.copd_extraction.*`
   - `run_eval.py`：`..services.algorithm_ports.qwen_vllm_client`、`..services.copd_extraction.llm_client/prompts`、`..services.schema_loader` → 对应绝对导入
   - `chunked_review.py`：`..services.copd_extraction.evidence_context` → 绝对导入
   - `metrics.py`：`..services.copd_extraction.field_policies` → 绝对导入
   - `calibrate.py`：仅 stdlib，无需改
3. **路径基准修正**：`run_eval.py` 的 `_BATCH_SCHEMA_PATH` 中 `Path(__file__).parents[3]` → `parents[2]`（层级少一级）；同类基于 `__file__` 的路径计算一并核查
4. **CLI 命令变更**：`python -m app.backend.evaluation.run_eval` → `python -m evaluation.code.run_eval`（仓库根运行；`app` 与 `evaluation` 均为 namespace 包，无需安装）
5. 确认 `app/backend/evaluation/` 无有效资产后才删除（见第 13 节删除门槛）

## 6. 测试迁移

1. 迁移 6 个文件：`test_evaluation_calibrate.py`、`test_evaluation_chunked_review.py`、`test_evaluation_metrics.py`、`test_evaluation_run_eval.py`、`test_evaluation_runner.py`、`test_review_feedback.py` → `evaluation/tests/`
2. 统一修正导入路径：`from app.backend.evaluation.xxx import ...` → `from evaluation.code.xxx import ...`
3. 检查 `app/backend/tests/` 的 conftest.py/fixtures 是否被迁移测试依赖；如依赖则 `evaluation/tests/` 建立独立 conftest（或最小化 fixtures 内联）
4. 运行方式统一：仓库根 `conda run -n manzufei_ocr python -m pytest evaluation/tests -q`（`python -m` 保证仓库根进 sys.path）

## 7. 数据迁移（对账驱动）

`data/evaluation/`、`data/text_data/` 均为 gitignored 本地数据，主仓库与 worktree 各自独立、不同步。

**双侧数据现状（2026-08-04 实测）：**

| 来源 | 内容 |
|---|---|
| 主仓库 `data/evaluation/` | 08-01/02 旧数据（`20260801_1330_adjudications.json`、`20260801_1330_verdicts.json`、`20260801_iter1_verdicts.json`、`20260802_verdicts_newprompt.json`、`20260802_verdicts_newprompt_v2.json` 等，主仓库自有历史，保留）；golden/ 6 例金标已与 worktree 一致 |
| worktree 独有 `calibration/`（16 个） | `adjudications_library.json`（287 条 AI 模拟裁定库，kappa 计算依赖，后续评估必用）、`judge/` 目录（step5/step6 逐例裁定）、step4/5/6 的 `adjudications_ai_step*`、`verdicts_step*` 系列（分块实验数据）、`20260802_step6_focus.html`、`verifier_manual_review_step5_focus.html` |
| worktree 独有 `reports/`（28 个） | 08-04 v3 全系列（6 例 `case_XXX-candidates.json`、6 例 smoke-partial、`verifier-v3-full-smoke-summary.json`、`verifier-v3-report.html`、`parallel-vs-serial-timing.json`）；08-03 v2 冒烟基线（`verifier-opt-v1-case006-candidates/smoke.json`、`verifier-opt-v1-report.html`）；08-03 报告（`prompt-refactor-v3-full-prompts.html`、`prompt-v4-appendix.html`、`prompt-policy-metric-alignment-v1-report.html`、`gpt55-v2-rescore.json`、case005 两个分析 HTML）；08-02/03 抽取产物 JSON（3 个） |
| 内容不同（1 个） | `20260802-verifier-overall-analysis.html` 两边都有但内容不同——**以 worktree 版（更新版）为准**，主仓库版弃置（记录在案，不算丢失） |
| `data/text_data/` | 仅主仓库有（ground_truth/ ocr_results/ output/），worktree 无 |

**流程（不可跳步）：**
1. **迁移前**：对主仓库与 worktree 两侧的 `data/evaluation/` 分别生成文件清单（相对路径）、文件数量和每文件 SHA-256 哈希，落盘为对账清单（含 `data/text_data/`）
2. **无覆盖合并**：合并到目标 `evaluation/data/`——同名同哈希跳过；同名异哈希**不得覆盖**，按裁决表处理（`20260802-verifier-overall-analysis.html` 以 worktree 更新版为准）；其余全部迁入
3. **数据守恒对账**：迁移后对目标目录重新生成清单+哈希，与"主仓库清单 ∪ worktree 清单（含裁决后弃置项标注）"逐项比对；文件数、路径、哈希完全一致才判定守恒
4. **只有对账一致且旧目录确认无有效资产后**，才删除旧目录（主仓库与 worktree 两侧的 `data/evaluation/`、`data/text_data/` 旧路径）
5. 主仓库为数据归宿；worktree 数据合并入主仓库的 `evaluation/data/` 后，worktree 侧数据目录随 worktree 删除

`.gitignore`：`data/evaluation/*` → `evaluation/data/*`，保留 `!evaluation/data/README.md` 特例；`data/text_data` 迁移后由 `evaluation/data/*` 一并覆盖。真实金标、校准数据、运行报告继续通过 .gitignore 排除，不提交患者数据或本地实验产物。

`evaluation/data/README.md` 保留并更新（说明 golden 与 text_data/ground_truth 的来源关系：golden 由 ground_truth 提炼；注明 08-01 旧数据并入后留存于 reports/calibration 的历史位置）。

## 8. 文档：统一索引与现行入口（不物理迁移）

- **spec/plan 留原处**：评估系 6 spec（`2026-08-01-evaluation-harness-design.md` 等）+ 5 plan 继续留在 `docs/superpowers/specs|plans/`
- **报告 HTML 留原处**：4 份评估报告继续留在 `docs/可视化html/`
- **`docs/codex_design/` 完全不动**（目录、文件内容、内部引用）
- **统一索引**：`evaluation/README.md` 内建"评估文档索引"——评估系 spec/plan 清单、报告清单、codex_design 入口，均以链接指向 docs/ 原位置，附版本/日期/摘要
- **现行入口更新**：`docs/AGENTS.md`（及 docs/CLAUDE.md）的文档规则注明评估系文档归属与索引位置；根 `AGENTS.md` 目录职责新增 `evaluation/` 条目并指向索引

> 历史 spec、plan、报告正文不批量改写；其内部旧路径引用保持原样，如需回读以 `evaluation/README.md` 的路径映射说明为准。

## 9. 版本迭代规范（自下一次迭代起生效）

用户需求：清晰看见版本迭代；每个版本有独立分析文档；全量整体提示词单独呈现。**本次不回溯补做历史版本**，规范写入 `evaluation/README.md`，自下一次版本迭代起执行：

```
evaluation/versions/
├── README.md                # 版本索引表：版本号 | 日期 | 变更摘要 | 分析文档 | 全量提示词 | 报告
└── v<N>/                    # 按版本号建目录（沿用 ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION / METRIC_VERSION）
    ├── analysis.md          # 本版本分析文档（改动点、依据、指标前后对比、结论）
    ├── prompt-full.md       # 全量整体提示词（system+user 运行时完整渲染，不截断不摘要）
    └── report.html          # 本版本评估报告（若有）
```

**规范条款：**
1. 每次提示词/评估口径版本迭代，在 `versions/<版本号>/` 建版本目录，索引表追加一行
2. `analysis.md` 记录改动点、依据、指标前后对比、结论
3. `prompt-full.md` 必须是运行时完整渲染的 system+user 提示词全文（从 `build_admission_structured_fields_messages` 实际产出导出），保证任意历史版本可回读可比对
4. 版本号沿用现有 `ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION` / `METRIC_VERSION` 体系，不另立新号

## 10. CLAUDE.md / AGENTS.md 全仓统一

### 统一形态

- 每个目录以 `AGENTS.md` 为**唯一规则内容源**
- `CLAUDE.md` 统一改为指向同目录 `AGENTS.md` 的简短入口
- 入口模板：
  ```markdown
  # CLAUDE.md

  本目录工作规则统一维护在 `AGENTS.md`（Claude Code 与 Codex 共用同一内容源），请阅读同目录的 `AGENTS.md`。
  ```

### 合并策略（每目录）

1. **逐目录比较并合并两份文件的有效规则**：不能简单按新旧时间覆盖——先读两份，识别重复（取一份）、过时（删除）、冲突（裁决取义）、职责已变化（改写），合并出有效规则写入 AGENTS.md
2. **同步重构**：重复、过时、冲突、目录职责已经变化的规则一并清理
3. **CLAUDE.md 置为简短入口**
4. **补齐缺失配对**：缺少配对文件的目录逐一补齐（CLAUDE.md 缺 → 复制 AGENTS.md 内容主体并置入口；AGENTS.md 缺 → 内容主体从现有 CLAUDE.md 迁移）；**不在没有独立规则需求的目录滥增文件**

### 涉及 evaluation 迁移的规则更新（写入对应 AGENTS.md）

| 文件 | 更新内容 |
|---|---|
| 根 `AGENTS.md` | 目录职责：`data/` 条目注明评估数据已迁出；新增 `evaluation/` 条目（含 code/data/tests/versions 子结构与文档索引位置）；"CLAUDE.md / AGENTS.md"双提及统一为只读 `AGENTS.md` |
| `app/backend/AGENTS.md` | evaluation 工具链条目改写：已迁出至顶层 `evaluation/`（单向依赖本目录生产模块）；金标/报告位置 → `evaluation/data/`；设计文档引用 → 索引（`evaluation/README.md`）；目录结构列表删除 evaluation/ 项 |
| `docs/AGENTS.md` | 文档规则注明：评估系 spec/plan/报告留 docs/ 原处，统一索引在 `evaluation/README.md`；评估/复核/提示词实验的版本迭代归档在 `evaluation/versions/` |
| 新建 `evaluation/AGENTS.md` | 目录定位（观测与评估体系）、结构说明、运行命令（`python -m evaluation.code.run_eval`、`pytest evaluation/tests`）、版本迭代规范摘要、边界（单向依赖生产模块、不提交真实数据） |
| 新建 `evaluation/CLAUDE.md` | 入口指针 |

### 引用清理

统一后文档内"AGENTS.md / CLAUDE.md"双提及改为只读 `AGENTS.md`（根第 5/57 行、docs/CLAUDE.md 第 13/14 行等，合并时一并改写）。`evaluation/README.md` 正文引用 `AGENTS.md`。

## 11. 其他引用面更新

更新所有**实际执行**代码、测试、维护脚本、README 和规则文件中的旧导入及数据路径：

1. `.gitignore`：见第 7 节
2. `scripts/maintenance/generate_verifier_review_html.py`：3 处 `data/evaluation/...` 路径 → `evaluation/data/...`
3. `run_eval.py` docstring 中的用法说明 → 新命令形态
4. 各 README / 规则文件中提及 `app/backend/evaluation`、`data/evaluation`、`data/text_data` 的现行引用
5. 历史 spec、plan、报告正文**不批量改写**

## 12. 验证（实施计划阶段执行）

1. `conda run -n manzufei_ocr python -m pytest evaluation/tests -q` 全绿
2. `conda run -n manzufei_ocr python -m pytest app/backend/tests -q` 全绿（业务侧零改动证明）
3. `python -m evaluation.code.run_eval --help` 冒烟
4. **扫描旧 Python 导入**：`grep -rn "app.backend.evaluation" app/ scripts/ evaluation/` 无残留（历史文档正文除外）
5. **扫描旧数据路径**：`grep -rn "data/evaluation\|data/text_data" app/ scripts/ evaluation/` 无残留（历史文档正文除外）
6. **扫描错误嵌套目录**：迁移后检查 `evaluation/` 下无错误嵌套（如 `evaluation/evaluation/`、`evaluation/data/evaluation/` 残留、双份 `__pycache__` 等）
7. 数据守恒对账结果回读（第 7 节清单比对）

## 13. 删除门槛

只有以下条件**全部满足**才删除旧目录（`app/backend/evaluation/`、`data/evaluation/`、`data/text_data/` 旧路径）：

1. 数据对账一致（第 7 节清单+哈希守恒）
2. 评估测试与后端全量测试全绿（第 12 节 1/2）
3. 旧目录确认无有效资产（扫描无引用残留、无未迁移文件）

## 14. 测试约定

- 全部沿用现有 pytest/conda 约定（`conda run -n manzufei_ocr`）
- 迁移不改行为：不新增测试逻辑，测试文件只改导入与路径
- 实施过程遵循 TDD 惯例：迁移完成后跑全量验证（第 12 节）作为回归

## 15. 风险与对策

| 风险 | 对策 |
|---|---|
| 导入遗漏导致 `evaluation.code` 导入失败 | 第 12 节验证 1/4（pytest 全绿 + grep 残留） |
| `__file__` 路径层级计算错误 | 第 12 节验证 3（CLI 冒烟）；实施时核查所有 `Path(__file__)` 用例 |
| 数据迁移丢失或覆盖 | 第 7 节哈希对账 + 无覆盖合并 + 守恒后删除门槛 |
| 合并规则时误删有效规则 | 逐目录先读两份再合并（第 10 节），不以时间戳覆盖 |
| 文档引用不一致 | 统一索引 + 现行入口更新；历史文档正文不改写 |
| 数据迁移两工作区不同步 | 主仓库执行 + worktree 复制同步（第 7 节） |
