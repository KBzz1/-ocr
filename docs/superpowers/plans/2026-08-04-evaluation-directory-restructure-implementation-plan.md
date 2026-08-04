# 评估体系独立成文件夹（evaluation-directory-restructure）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将评估体系（代码/测试/数据）收拢为顶层 `evaluation/` 文件夹，并全仓统一 CLAUDE.md → AGENTS.md 规则文件，以 master 实际状态为唯一基准。

**Architecture:** 代码从 `app/backend/evaluation/` 迁至 `evaluation/code/`（包名 `evaluation.code`），继续单向绝对导入 `app.backend` 生产模块；测试迁至 `evaluation/tests/`；gitignored 数据经哈希对账无覆盖合并至 `evaluation/data/`；评估系文档留 docs/ 原位、在 `evaluation/README.md` 建统一索引；全部目录 CLAUDE.md 改为指向同目录 AGENTS.md 的简短入口。实施基于与 master 同步的当前 worktree 分支，完成后合并回 master 并删除两个 worktree。

**Tech Stack:** Python 3.12（conda 环境 `manzufei_ocr`）、pytest、git worktree、bash/zhash

## Global Constraints

- 以主分支（master）实际状态为唯一基准；不改动 `app/backend/` 生产业务代码
- 评估代码单向依赖 `app.backend` 生产模块（绝对导入），不包装成完全独立系统
- 不改变评估行为：指标口径、管线组装、CLI 参数、金标格式均不变
- 评估系 spec/plan/报告**留在 docs/ 原位**，不物理迁移；`docs/codex_design/` 完全不动
- 历史 spec/plan/报告正文**不批量改写**；只更新实际执行代码、测试、维护脚本、README、规则文件
- 数据迁移必须：先清单+数量+哈希 → 无覆盖合并 → 守恒对账 → 验证全绿后才删旧目录
- 真实金标、校准数据、运行报告继续由 `.gitignore` 排除，不提交患者数据或本地实验产物
- CLAUDE.md 统一为简短入口指针；AGENTS.md 为唯一规则内容源；逐目录内容合并，**不按时间戳覆盖**；无独立规则需求的目录不滥增文件
- 测试与命令统一 `conda run -n manzufei_ocr python -m pytest ...`；commit message 用中文
- 实施位置：代码/测试/文档在当前 worktree（= master 状态）操作；数据迁移在**主仓库**（`/home/kbzz1/manzufei_ocr`）操作
- worktree 分支名：`worktree-prompt-refactor-field-boundary`；主仓库 master：`711bc60`

---

### Task 1: 数据迁移（主仓库：双侧哈希清单 → 无覆盖合并 → 守恒对账）

**Files:**
- Create: `/home/kbzz1/manzufei_ocr/evaluation/data/`（目标，由主仓库数据迁入）
- Create: `/tmp/eval_migration/manifest_main.json`、`/tmp/eval_migration/manifest_wt.json`、`/tmp/eval_migration/conflicts.json`（对账产物，不入仓）
- Create: `/tmp/eval_migration/merge_eval_data.py`（一次性合并脚本，不入仓）

**Interfaces:**
- Produces: `evaluation/data/` 完整数据（golden/ calibration/ reports/ text_data/），对账清单与冲突裁决记录
- 被 Task 8 消费（旧目录删除前复核）

- [ ] **Step 1: 生成双侧文件清单与哈希（worktree 侧）**

在**当前 worktree** 执行，把 worktree 的 `data/evaluation/` 清单落盘：

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary
mkdir -p /tmp/eval_migration
python - <<'PY'
import json, hashlib, pathlib
def manifest(root, base):
    out = {}
    for p in sorted(pathlib.Path(root).rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(base))
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out
wt = manifest("data/evaluation", pathlib.Path("data/evaluation"))
json.dump(wt, open("/tmp/eval_migration/manifest_wt.json", "w"), indent=1, ensure_ascii=False)
print(f"worktree data/evaluation: {len(wt)} files")
PY
```

Expected: 输出文件数（应为 44 + 1 与主仓库同名的更新版，总数以实际为准），`manifest_wt.json` 生成。

- [ ] **Step 2: 生成主仓库侧清单**

在**主仓库**执行，包含 `data/evaluation/` 与 `data/text_data/`：

```bash
cd /home/kbzz1/manzufei_ocr
python - <<'PY'
import json, hashlib, pathlib
def manifest(root, base):
    out = {}
    for p in sorted(pathlib.Path(root).rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(base))
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out
ev = manifest("data/evaluation", pathlib.Path("data/evaluation"))
td = manifest("data/text_data", pathlib.Path("data/text_data"))
json.dump({"evaluation": ev, "text_data": td}, open("/tmp/eval_migration/manifest_main.json", "w"), indent=1, ensure_ascii=False)
print(f"main data/evaluation: {len(ev)} files, data/text_data: {len(td)} files")
PY
```

Expected: 输出两侧文件数；`manifest_main.json` 生成。**此清单是数据守恒的唯一基准，不得丢失。**

- [ ] **Step 3: 编写无覆盖合并脚本**

```bash
cat > /tmp/eval_migration/merge_eval_data.py <<'PY'
"""评估数据无覆盖合并：哈希相同跳过；哈希不同报冲突（不覆盖）；记录裁决表。"""
import json, hashlib, pathlib, shutil, sys

WT_SRC = pathlib.Path("/home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary/data/evaluation")
MAIN_EV = pathlib.Path("/home/kbzz1/manzufei_ocr/data/evaluation")
MAIN_TD = pathlib.Path("/home/kbzz1/manzufei_ocr/data/text_data")
DEST = pathlib.Path("/home/kbzz1/manzufei_ocr/evaluation/data")

# 人工裁决表：{目标相对路径: "keep_source"(用worktree版) / "skip"(弃置主仓库版)}
VERDICTS = {
    "calibration/20260802-verifier-overall-analysis.html": "keep_source",  # worktree 版为更新版
}

def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

conflicts, copied, skipped = [], 0, 0

def merge(src_root, dest_root, tag):
    global copied, skipped
    for p in sorted(src_root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(src_root))
        dst = dest_root / rel
        if dst.exists():
            if sha256(dst) == sha256(p):
                skipped += 1  # 已存在且一致
            else:
                verdict = VERDICTS.get(rel, "")
                if verdict == "keep_source":
                    dst.write_bytes(p.read_bytes())
                    copied += 1
                    print(f"[裁决keep_source] {rel}")
                else:
                    conflicts.append({"rel": rel, "main_sha": sha256(dst), "wt_sha": sha256(p)})
                    print(f"[冲突未覆盖] {rel}")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(p.read_bytes())
            copied += 1

merge(MAIN_EV, DEST, "main")
merge(WT_SRC, DEST, "wt")
# text_data 仅主仓库有
merge(MAIN_TD, DEST / "text_data", "text_data")

json.dump(conflicts, open("/tmp/eval_migration/conflicts.json", "w"), indent=1, ensure_ascii=False)
print(f"copied={copied} skipped={skipped} conflicts={len(conflicts)}")
if conflicts:
    print("存在未裁决冲突，禁止继续！人工裁决后重新合并。")
    sys.exit(1)
PY
```

- [ ] **Step 4: 执行合并并验证零冲突**

```bash
cd /home/kbzz1/manzufei_ocr
python /tmp/eval_migration/merge_eval_data.py
```

Expected: 输出 `copied=N skipped=M conflicts=0`。若 conflicts>0，先把对应条目加入 `VERDICTS` 裁决后重跑（裁决原则：`20260802-verifier-overall-analysis.html` 已预置 keep_source；其他冲突按"更新的实验产物保留 worktree 版、旧版弃置并记录"原则人工裁决）。

- [ ] **Step 5: 数据守恒对账**

```bash
cd /home/kbzz1/manzufei_ocr
python - <<'PY'
import json, hashlib, pathlib
def manifest(root, base):
    out = {}
    for p in sorted(pathlib.Path(root).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(base))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out
main = json.load(open("/tmp/eval_migration/manifest_main.json"))
wt = json.load(open("/tmp/eval_migration/manifest_wt.json"))
dest = manifest("evaluation/data", pathlib.Path("evaluation/data"))
expected = {}
for rel, h in main["evaluation"].items(): expected[rel] = h
for rel, h in wt.items():
    if rel == "reports/20260802-verifier-overall-analysis.html":
        expected[rel] = h  # 以 worktree 更新版为准（实测文件在 reports/ 下）
    else:
        expected.setdefault(rel, h)
for rel, h in main["text_data"].items(): expected[f"text_data/{rel}"] = h
missing = {r for r in expected if r not in dest}
mismatch = {r for r in expected if r in dest and dest[r] != expected[r]}
extra = {r for r in dest if r not in expected}
print(f"expected={len(expected)} dest={len(dest)} missing={len(missing)} mismatch={len(mismatch)} extra={len(extra)}")
if missing or mismatch:
    print("MISSING:", missing); print("MISMATCH:", mismatch)
    raise SystemExit(1)
if extra:
    print("EXTRA(需人工确认新增资产):", extra)
print("对账通过：数据守恒")
PY
```

Expected: `对账通过：数据守恒`。此步骤通过前**不得进入 Task 8 删除旧目录**。

- [ ] **Step 6: 提交（数据不入 git）**

数据迁移全部在 gitignored 区域，无需 git commit。确认 `.gitignore` 尚未把 `evaluation/data` 暴露（Task 4 才改规则；此时迁移已发生，注意**立即**执行 Task 4 以免误提交）。

---

### Task 2: 代码迁移（`evaluation/code/` + 导入改造）

**Files:**
- Create: `evaluation/code/__init__.py`（空）
- Move: `app/backend/evaluation/{metrics,runner,run_eval,calibrate,chunked_review,feedback,desensitize}.py` → `evaluation/code/`
- Delete: `app/backend/evaluation/`（目录清空后删除，删除门槛见 Task 8）
- Modify: `evaluation/code/*.py` 导入与路径（下述逐文件）

**Interfaces:**
- Produces: 包 `evaluation.code`（模块名与原一致：`metrics`、`runner`、`run_eval`、`calibrate`、`chunked_review`、`feedback`、`desensitize`），CLI 入口 `python -m evaluation.code.run_eval`
- Consumes: `app.backend.errors`、`app.backend.services.copd_extraction.*`、`app.backend.services.algorithm_ports.*`、`app.backend.services.schema_loader`（绝对导入，单向依赖）

- [ ] **Step 1: 建立目录并 git mv 代码文件**

```bash
mkdir -p evaluation/code
git mv app/backend/evaluation/metrics.py evaluation/code/
git mv app/backend/evaluation/runner.py evaluation/code/
git mv app/backend/evaluation/run_eval.py evaluation/code/
git mv app/backend/evaluation/calibrate.py evaluation/code/
git mv app/backend/evaluation/chunked_review.py evaluation/code/
git mv app/backend/evaluation/feedback.py evaluation/code/
git mv app/backend/evaluation/desensitize.py evaluation/code/
touch evaluation/code/__init__.py
```

Expected: `git status` 显示 7 个 rename + 1 新增；`app/backend/evaluation/` 为空目录（`__init__.py` 与 `__pycache__` 待删）。

- [ ] **Step 2: 删除旧包残留并改写 `runner.py` 导入**

```bash
rm app/backend/evaluation/__init__.py
rm -rf app/backend/evaluation/__pycache__
```

`evaluation/code/runner.py` 顶部导入改为（其余内容不动）：

```python
from app.backend.errors import AppError
from app.backend.services.copd_extraction.admission_contract import (
    map_qwen_fields_to_review_candidates,
    validate_qwen_payload,
)
from app.backend.services.copd_extraction.prompts import build_admission_structured_fields_messages
from app.backend.services.copd_extraction.quality_checks import apply_quality_checks
from app.backend.services.copd_extraction.response_schemas import build_extraction_json_schema
from app.backend.services.copd_extraction.verifier import FieldVerifier, apply_verdicts
```

（包内相对导入 `from .metrics import (...)` 保留不变）

- [ ] **Step 3: 改写 `run_eval.py` 导入与路径**

`evaluation/code/run_eval.py`：

```python
from app.backend.services.algorithm_ports.qwen_vllm_client import QwenVLLMClient
from app.backend.services.copd_extraction.llm_client import OpenAICompatibleJsonClient
from app.backend.services.copd_extraction.prompts import ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION
from app.backend.services.schema_loader import load_schema
```

路径基准修正（第 31 行附近，`_BATCH_SCHEMA_PATH`）：

```python
_BATCH_SCHEMA_PATH = str(
    Path(__file__).resolve().parents[2]
    / "app" / "config" / "schemas" / "qwen_batch_admission_record.v2.yaml"
)
```

默认参数与 help 文本改为新数据路径：

```python
    parser.add_argument("--golden-dir", default="evaluation/data/golden")
    parser.add_argument("--report-dir", default="evaluation/data/reports")
    parser.add_argument("--golden-review", default=None,
                        help="review 金标活资产目录(如 evaluation/data/golden_review)，单独统计修正字段子集")
```

- [ ] **Step 4: 改写 `calibrate.py` 默认路径**

`evaluation/code/calibrate.py:105`：

```python
    p_export.add_argument("--golden-dir", default="evaluation/data/golden")
```

- [ ] **Step 5: 改写 `chunked_review.py` 与 `metrics.py` 导入**

`evaluation/code/chunked_review.py`：

```python
from app.backend.services.copd_extraction.evidence_context import assemble_verification_groups
```

`evaluation/code/metrics.py`：

```python
from app.backend.services.copd_extraction.field_policies import NORMAL_JUDGEMENT_FIELD_KEYS
```

- [ ] **Step 6: 更新 run_eval.py docstring 命令形态**

检查并更新 `evaluation/code/run_eval.py` 模块 docstring 中的命令示例（若有 `python -m app.backend.evaluation.run_eval` 字样改为 `python -m evaluation.code.run_eval`）：

```bash
grep -n "python -m" evaluation/code/run_eval.py
```

如有旧命令，改为：`python -m evaluation.code.run_eval`（参数不变）。

- [ ] **Step 7: 扫描残留相对导入**

```bash
grep -rn "from \.\.\|from \." evaluation/code/*.py | grep -v "__init__"
```

Expected: 仅剩包内相对导入 `from .metrics`、`from .feedback`、`from .chunked_review`、`from .runner`、`from .desensitize`（这些保留）。

- [ ] **Step 8: CLI 冒烟**

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary
conda run -n manzufei_ocr python -m evaluation.code.run_eval --help
```

Expected: 打印 argparse 帮助且无 ImportError/路径错误。

- [ ] **Step 9: 提交**

```bash
git add evaluation/code app/backend/evaluation
git commit -m "refactor:评估代码迁至顶层evaluation/code(绝对导入app.backend+parents修正+默认路径evaluation/data)"
```

---

### Task 3: 测试迁移（`evaluation/tests/` + 导入修正）

**Files:**
- Move: `app/backend/tests/test_evaluation_calibrate.py`、`test_evaluation_chunked_review.py`、`test_evaluation_metrics.py`、`test_evaluation_run_eval.py`、`test_evaluation_runner.py`、`test_review_feedback.py` → `evaluation/tests/`

**Interfaces:**
- Consumes: `evaluation.code.*` 各模块（Task 2 产物）
- Produces: `evaluation/tests/` 6 个测试文件，pytest 全绿

- [ ] **Step 1: git mv 测试文件**

```bash
mkdir -p evaluation/tests
git mv app/backend/tests/test_evaluation_calibrate.py evaluation/tests/
git mv app/backend/tests/test_evaluation_chunked_review.py evaluation/tests/
git mv app/backend/tests/test_evaluation_metrics.py evaluation/tests/
git mv app/backend/tests/test_evaluation_run_eval.py evaluation/tests/
git mv app/backend/tests/test_evaluation_runner.py evaluation/tests/
git mv app/backend/tests/test_review_feedback.py evaluation/tests/
```

- [ ] **Step 2: 批量修正导入**

```bash
cd evaluation/tests
sed -i 's/from app\.backend\.evaluation/from evaluation.code/' test_*.py
grep -rn "app.backend.evaluation" .
```

Expected: 无输出（全部替换）。替换后形如 `from evaluation.code.metrics import (...)`、`from evaluation.code import run_eval`。

- [ ] **Step 3: 运行迁移后的评估测试**

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary
conda run -n manzufei_ocr python -m pytest evaluation/tests -q
```

Expected: 全部 PASS（不依赖 conftest fixtures，已确认）。

- [ ] **Step 4: 确认后端其余测试不受影响**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: 全部 PASS（除已迁出的 6 个文件外无失败）。

- [ ] **Step 5: 提交**

```bash
git add evaluation/tests app/backend/tests
git commit -m "test:评估测试迁至evaluation/tests并统一导入evaluation.code"
```

---

### Task 4: 引用面更新（.gitignore + 维护脚本）

**Files:**
- Modify: `.gitignore:33-53`（data/ 规则段）
- Modify: `scripts/maintenance/generate_verifier_review_html.py:17-20,467,469`

**Interfaces:**
- Produces: `.gitignore` 覆盖 `evaluation/data/*`；脚本默认路径指向新数据位置
- 被 Task 7 验证消费（grep 扫描依据）

- [ ] **Step 1: 更新 .gitignore**

把第 40-41 行替换为：

```gitignore
evaluation/data/*
!evaluation/data/README.md
```

（`data/text_data` 随迁移已并入 `evaluation/data/`，由 `evaluation/data/*` 覆盖，无需单独规则；旧 `data/evaluation/*` 规则删除。）

- [ ] **Step 2: 更新维护脚本路径**

`scripts/maintenance/generate_verifier_review_html.py` 中 5 处：

```python
# 第 17-20 行 docstring 示例
--verdicts evaluation/data/calibration/20260801_1330_verdicts.json
--golden-dir evaluation/data/golden
--llm-adjudications evaluation/data/calibration/20260801_1330_adjudications.json
--out evaluation/data/calibration/20260802_verifier_manual_review.html

# 第 467 行
parser.add_argument("--golden-dir", default="evaluation/data/golden")
# 第 469 行
parser.add_argument("--out", required=True, help="输出 HTML 路径（建议 evaluation/data/calibration/）")
```

- [ ] **Step 3: 确认 git 忽略生效**

```bash
git check-ignore evaluation/data/golden/case_001.json && echo "ignored OK"
git check-ignore evaluation/data/README.md || echo "README 未被忽略(符合特例)"
```

Expected: 第一行输出 `ignored OK`；第二行输出 `README 未被忽略(符合特例)`。

- [ ] **Step 4: 提交**

```bash
git add .gitignore scripts/maintenance/generate_verifier_review_html.py
git commit -m "chore:gitignore与维护脚本路径指向evaluation/data"
```

---

### Task 5: evaluation/README.md 统一索引与版本规范

**Files:**
- Create: `evaluation/README.md`
- Create: `evaluation/versions/README.md`
- Create: `evaluation/data/README.md`（由 `data/evaluation/README.md` 内容迁移并更新；若 data/evaluation/README.md 不存在则新建）

**Interfaces:**
- Produces: 评估体系总览 + 文档统一索引（指向 docs/ 原位）+ 版本迭代规范（自下次迭代生效）
- 被 Task 6c 的 docs/AGENTS.md 引用（索引位置声明）

- [ ] **Step 1: 编写 `evaluation/README.md`**

```markdown
# evaluation/ — 观测与评估体系

评估代码、测试与本地数据（金标/校准/报告/人工标注素材）的收拢目录。
**评估代码单向依赖 `app.backend` 生产模块**（绝对导入），不参与生产路径。

## 目录

- `code/` — Python 包 `evaluation.code`：指标 `metrics`、管线与报告 `runner`、CLI `run_eval`、校准 `calibrate`、分块复核 `chunked_review`、审核回流 `feedback`/`desensitize`
- `tests/` — 评估单测（含 `test_review_feedback.py`）
- `data/` — gitignored：`golden/`（评估金标，由 `text_data/ground_truth` 提炼）、`calibration/`（kappa 校准与裁定数据）、`reports/`（评估报告）、`text_data/`（人工标注原始素材：ground_truth/ ocr_results/ output/）
- `versions/` — 版本迭代归档（规范见下）

## 运行与测试

```bash
# 评估 CLI（仓库根）
conda run -n manzufei_ocr python -m evaluation.code.run_eval --help
# 评估测试
conda run -n manzufei_ocr python -m pytest evaluation/tests -q
```

## 文档统一索引（正文在 docs/ 原位，不迁移）

- 评估/复核/提示词实验设计：`docs/superpowers/specs/2026-08-0{1,2,3}-*.md`（evaluation-harness、verifier-normalization、verifier-chunked-review-experiment、verifier-recall-optimization、prompt-refactor-field-boundary、verifier-step7-scale-evidence）
- 实施计划：`docs/superpowers/plans/2026-08-0{1,2}-*.md` 对应 5 份
- 架构师实验记录：`docs/codex_design/`（prompt-policy-metric-alignment-v1、verifier-optimization-v1、verifier-judge-rubric-v1）
- 报告 HTML：`docs/可视化html/`（4 份评估报告）
- 历史文档内旧路径映射：`app/backend/evaluation` → `evaluation.code`（命令 `python -m evaluation.code.run_eval`）；`data/evaluation`、`data/text_data` → `evaluation/data`

## 版本迭代规范（自下一次版本迭代起生效，不回溯补做历史版本）

每次提示词/评估口径版本迭代在 `versions/<版本号>/` 建目录（版本号沿用 `ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION` / `METRIC_VERSION`）：
- `analysis.md` — 改动点、依据、指标前后对比、结论
- `prompt-full.md` — 运行时完整渲染的 system+user 提示词全文（`build_admission_structured_fields_messages` 实际产出，不截断不摘要）
- `report.html` — 本版本评估报告（若有）
- `versions/README.md` 索引表追加一行（版本号 | 日期 | 变更摘要 | 分析文档 | 全量提示词 | 报告）
```

- [ ] **Step 2: 编写 `evaluation/versions/README.md` 骨架**

```markdown
# 版本索引

| 版本号 | 日期 | 变更摘要 | 分析文档 | 全量提示词 | 报告 |
|---|---|---|---|---|---|
|（自下一次迭代起登记；历史版本不回溯补建）|
```

- [ ] **Step 3: 编写 `evaluation/data/README.md`**

迁移 `data/evaluation/README.md` 现有内容并补充：

```markdown
（保留原 README 内容；补充：）
- 本目录为评估本地数据（gitignored，不提交）：`golden/` 评估金标由 `text_data/ground_truth/` 提炼；`calibration/` kappa 校准与裁定数据；`reports/` 评估报告；`text_data/` 人工标注原始素材（ground_truth/ ocr_results/ output/）。
- 08-01/02 历史数据（adjudications/verdicts 旧系列）随合并留存于 calibration/reports 原位，不迁移不删除。
```

`data/evaluation/README.md` 是仓库跟踪文件（.gitignore 特例），Task 1 合并脚本已把其内容复制到 `evaluation/data/README.md`。此处直接 `git rm data/evaluation/README.md`（旧位置删除，新位置已有副本），然后编辑 `evaluation/data/README.md` 补充内容（若新位置文件缺失则直接新建）。

- [ ] **Step 4: 提交**

```bash
git add evaluation/README.md evaluation/versions/README.md evaluation/data/README.md
git commit -m "docs:evaluation总览+文档统一索引+版本迭代规范+data说明"
```

---

### Task 6a: 根目录规则文件统一（合并 + 指针 + evaluation 条目）

**Files:**
- Modify: `AGENTS.md`（根，唯一内容源）
- Modify: `CLAUDE.md`（根，置为指针）

**Interfaces:**
- Produces: 根 `AGENTS.md` 含 evaluation 目录条目与"只读 AGENTS.md"表述；根 `CLAUDE.md` 为指针
- 被 Task 6c/6e 引用（目录职责表述一致）

- [ ] **Step 1: 读取两份文件并 diff**

```bash
diff CLAUDE.md AGENTS.md
```

Expected: 已知差异（2026-08-04 实测）：第 5 行 onboarding 表述（AGENTS.md 为"AGENTS.md / CLAUDE.md"双提及、CLAUDE.md 为旧表述）、第 57 行工作方式双提及。其余两文件副本一致。

- [ ] **Step 2: 合并有效规则写入根 AGENTS.md**

1. 第 5 行改为（只读 AGENTS.md，删除"CLAUDE.md"双提及）：`本文件是全仓库长期 onboarding...代码/部署/脚本目录的细节先读目标目录的 AGENTS.md（如 app/backend/AGENTS.md、deploy/AGENTS.md、scripts/AGENTS.md），没有 AGENTS.md 的再读 README.md。`
2. 第 57 行改为：`根级 agent 文档只保留全仓库通用信息；目录细节读取 docs/AGENTS.md 或对应目录 AGENTS.md/README.md。`
3. 目录职责 `data/` 条目（第 35 行附近）改为：`data/`：上传文件、处理结果和临时文件（评估本地数据已迁至 `evaluation/data/`，见 evaluation 条目）。`
4. 新增 `evaluation/` 条目：`evaluation/`：观测与评估体系（评估代码/测试/本地数据收拢；代码单向依赖 app.backend 生产模块；文档索引与版本规范见 evaluation/README.md）。规则见 evaluation/AGENTS.md。`

- [ ] **Step 3: 根 CLAUDE.md 置为指针**

整文件替换为：

```markdown
# CLAUDE.md

本目录工作规则统一维护在 `AGENTS.md`（Claude Code 与 Codex 共用同一内容源），请阅读同目录的 `AGENTS.md`。
```

- [ ] **Step 4: 提交**

```bash
git add AGENTS.md CLAUDE.md
git commit -m "docs:根规则统一(AGENTS.md唯一内容源,CLAUDE.md指针,evaluation目录条目)"
```

---

### Task 6b: app/backend 规则文件统一（evaluation 条目改写 + 合并）

**Files:**
- Modify: `app/backend/AGENTS.md`
- Modify: `app/backend/CLAUDE.md`

- [ ] **Step 1: diff 两份文件**

```bash
diff app/backend/CLAUDE.md app/backend/AGENTS.md
```

Expected: 已知差异（2026-08-04 实测 12 行）：CLAUDE.md 较新——task.py/patient.py/mobile.py 描述更新、patient_service/export_service 条目、**evaluation/ 工具链条目（第 38 行）为 CLAUDE.md 独有**。

- [ ] **Step 2: 合并写入 app/backend/AGENTS.md**

以 CLAUDE.md 较新内容为基准，追加/保留 AGENTS.md 独有内容；其中 **evaluation/ 条目改写**为（替换原第 38 行）：

```markdown
- `../evaluation/`：评估体系已迁至顶层 `evaluation/`（代码在 `evaluation/code/`，单向依赖本目录生产模块）；金标/校准/报告在 `evaluation/data/`；文档索引见 `evaluation/README.md`。复核器（`services/copd_extraction/verifier.py`）活动路径未默认注入（kappa 未达 0.7 上岗线，spec 5.2）
```

若 AGENTS.md 已有独立表述，按"较新为准、无冲突保留"合并。

- [ ] **Step 3: app/backend/CLAUDE.md 置为指针**

整文件替换为指针模板（同 Task 6a Step 3，标题保持 `# CLAUDE.md`）。

- [ ] **Step 4: 提交**

```bash
git add app/backend/AGENTS.md app/backend/CLAUDE.md
git commit -m "docs:app/backend规则统一(evaluation迁出改写+指针化)"
```

---

### Task 6c: docs 规则文件统一（评估系文档归属声明）

**Files:**
- Modify: `docs/AGENTS.md`
- Modify: `docs/CLAUDE.md`

- [ ] **Step 1: diff 并合并写入 docs/AGENTS.md**

```bash
diff docs/CLAUDE.md docs/AGENTS.md
```

合并两份有效规则（较新为准）后，新增/更新一条文档规则：

```markdown
- 评估/复核/提示词实验的 spec/plan 留在本目录（`superpowers/specs|plans/`）不迁移；统一索引与版本迭代归档见 `evaluation/README.md`、`evaluation/versions/`；`codex_design/` 保持原样不动。
```

同时把文中"AGENTS.md / CLAUDE.md"双提及统一为只读 `AGENTS.md`。

- [ ] **Step 2: docs/CLAUDE.md 置为指针**

整文件替换为指针模板。

- [ ] **Step 3: 提交**

```bash
git add docs/AGENTS.md docs/CLAUDE.md
git commit -m "docs:docs规则统一(评估系文档归属声明+指针化)"
```

---

### Task 6d: 其余目录规则文件统一（批量合并 + 指针）

**Files:**
- Modify: 以下每目录 `AGENTS.md`（合并后保留）与 `CLAUDE.md`（置指针）：
  `scripts/`、`deploy/`、`app/frontend/`、`docs/Front/`、`docs/Backend/`、`docs/Front/Front_TDD/`、`docs/Front/Front_BDD/`、`docs/Backend/Backend_TDD/`、`docs/Backend/Backend_BDD/`、`app/backend/services/algorithm_ports/`、`app/backend/services/copd_extraction/`

- [ ] **Step 1: 逐目录 diff 并合并**

对每个目录执行：

```bash
for d in scripts deploy app/frontend docs/Front docs/Backend \
  docs/Front/Front_TDD docs/Front/Front_BDD \
  docs/Backend/Backend_TDD docs/Backend/Backend_BDD \
  app/backend/services/algorithm_ports app/backend/services/copd_extraction; do
  echo "=== $d ==="; diff "$d/CLAUDE.md" "$d/AGENTS.md"
done
```

Expected: 各目录 4-6 行差异（2026-08-04 实测）。逐目录人工判断：重复取一、过时删除、冲突裁决（无 evaluation 相关内容的目录按较新表述合并即可）。

- [ ] **Step 2: 各目录 CLAUDE.md 置指针**

每目录 `CLAUDE.md` 整文件替换为指针模板（标题 `# CLAUDE.md`，正文指向同目录 `AGENTS.md`）。

- [ ] **Step 3: 全仓扫描确认无遗漏**

```bash
for f in $(find . -name "CLAUDE.md" -not -path "./.git/*" -not -path "./.claude/*"); do
  head -1 "$f" | grep -q "指针\|AGENTS.md" || echo "漏改: $f"
done
```

Expected: 无输出（除新建的 evaluation/CLAUDE.md，Task 6e 处理）。

- [ ] **Step 4: 提交**

```bash
git add scripts deploy app/frontend docs/Front docs/Backend \
  docs/Front/Front_TDD docs/Front/Front_BDD \
  docs/Backend/Backend_TDD docs/Backend/Backend_BDD \
  app/backend/services/algorithm_ports app/backend/services/copd_extraction
git commit -m "docs:全仓规则统一(11目录AGENTS.md合并+CLAUDE.md指针化)"
```

---

### Task 6e: 新建 evaluation 规则文件

**Files:**
- Create: `evaluation/AGENTS.md`
- Create: `evaluation/CLAUDE.md`

- [ ] **Step 1: 编写 `evaluation/AGENTS.md`**

```markdown
# AGENTS.md

## 作用

本目录是观测与评估体系：评估代码、测试与本地数据的收拢位置。评估代码**单向依赖 `app.backend` 生产模块**（绝对导入），不参与生产路径；本目录不新增业务字段、状态、服务或医学规则。

## 目录与运行

- `code/`：Python 包 `evaluation.code`（metrics/runner/run_eval/calibrate/chunked_review/feedback/desensitize）
- `tests/`：评估单测（含 test_review_feedback.py）
- `data/`：gitignored 本地数据（golden/calibration/reports/text_data），不提交患者数据或实验产物
- `versions/`：版本迭代归档（规范见 README.md）

```bash
# CLI（仓库根）
conda run -n manzufei_ocr python -m evaluation.code.run_eval --help
# 测试
conda run -n manzufei_ocr python -m pytest evaluation/tests -q
```

文档（spec/plan/报告）留在 `docs/` 原位，统一索引见 `README.md`。

## 变更约束

- 修改评估行为（指标口径/金标格式/CLI 参数）前先写 spec 并更新文档索引
- 评估代码不得被 `app/backend` 业务代码反向依赖
- 每版本迭代按 `README.md` 版本规范归档（analysis.md + prompt-full.md 全量提示词 + 报告）
```

- [ ] **Step 2: 编写 `evaluation/CLAUDE.md`**

```markdown
# CLAUDE.md

本目录工作规则统一维护在 `AGENTS.md`（Claude Code 与 Codex 共用同一内容源），请阅读同目录的 `AGENTS.md`。
```

- [ ] **Step 3: 提交**

```bash
git add evaluation/AGENTS.md evaluation/CLAUDE.md
git commit -m "docs:新增evaluation目录规则文件(AGENTS.md内容源+CLAUDE.md指针)"
```

---

### Task 7: 全量验证

**Files:**
- 无文件修改；全部为验证命令

**Interfaces:**
- 消费 Task 1-6e 全部产物；通过后解锁 Task 8 删除

- [ ] **Step 1: 评估测试全绿**

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary
conda run -n manzufei_ocr python -m pytest evaluation/tests -q
```

Expected: 全绿。

- [ ] **Step 2: 后端全量测试全绿**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: 全绿。

- [ ] **Step 3: CLI 冒烟**

```bash
conda run -n manzufei_ocr python -m evaluation.code.run_eval --help >/dev/null && echo "CLI OK"
```

Expected: `CLI OK`。

- [ ] **Step 4: 扫描旧 Python 导入**

```bash
grep -rn "app\.backend\.evaluation" app/ scripts/ evaluation/ --include="*.py" || echo "无残留"
grep -rn "from \.\.evaluation\|from \.evaluation" app/ scripts/ evaluation/ --include="*.py" || echo "无残留"
```

Expected: 两处均输出"无残留"。

- [ ] **Step 5: 扫描旧数据路径（执行面）**

```bash
grep -rn "data/evaluation\|data/text_data" app/ scripts/ evaluation/ README.md CLAUDE.md AGENTS.md --include="*.py" --include="*.md" || echo "无残留"
```

Expected: "无残留"（docs/ 历史文档正文允许存在旧路径，不在扫描范围）。

- [ ] **Step 6: 扫描错误嵌套目录**

```bash
find evaluation -maxdepth 2 -type d | sort
find app/backend/evaluation data/evaluation data/text_data -maxdepth 0 2>/dev/null
```

Expected: `evaluation/` 下只有 `code/ tests/ data/ versions/`（+ data 子目录），无 `evaluation/evaluation/`、无 `evaluation/data/evaluation/` 等嵌套；`app/backend/evaluation`、`data/evaluation`、`data/text_data` 的**存在性记录**输出（Task 8 删除前复核）。

- [ ] **Step 7: 数据对账复核（主仓库）**

```bash
cd /home/kbzz1/manzufei_ocr
python /tmp/eval_migration/verify_conservation.py 2>/dev/null || echo "用 Task 1 Step 5 的对账命令复核"
```

Expected: 对账通过（或手动复核 Task 1 Step 5 命令仍输出"对账通过：数据守恒"）。

---

### Task 8: 删除旧目录（门槛全部满足后）

**前置条件（缺一不可）：** Task 7 验证 1/2 全绿、Task 7 Step 4/5 无残留、数据守恒对账通过、`app/backend/evaluation` 与旧 data 目录确认无有效资产。

**Files:**
- Delete: `app/backend/evaluation/`（worktree 中，git 层面已随 Task 2 移除文件，此处确认目录消失）
- Delete: `/home/kbzz1/manzufei_ocr/data/evaluation/`、`/home/kbzz1/manzufei_ocr/data/text_data/`（主仓库）
- Delete: `/home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary/data/evaluation/`（worktree 侧，随 worktree 删除时一并处理，见 Task 9）

- [ ] **Step 1: 复核旧目录无有效资产**

```bash
cd /home/kbzz1/manzufei_ocr
find data/evaluation data/text_data -type f 2>/dev/null | wc -l
```

Expected: 0（Task 1 已全部合并，未合并项均有裁决记录）。

- [ ] **Step 2: 删除主仓库旧数据目录**

```bash
rm -rf /home/kbzz1/manzufei_ocr/data/evaluation /home/kbzz1/manzufei_ocr/data/text_data
ls data/
```

Expected: `data/` 下不再有 `evaluation`、`text_data`。

- [ ] **Step 3: 确认 git 层面旧包目录已清**

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary
ls app/backend/evaluation 2>/dev/null || echo "app/backend/evaluation 已不存在"
```

Expected: `app/backend/evaluation 已不存在`。

- [ ] **Step 4: 提交（如有 git 侧残留）**

```bash
git status --short | head
```

Expected: 工作区干净（无残留跟踪文件）。若出现意外残留，逐项确认后 `git rm` 并提交。

---

### Task 9: 合并回 master 并删除 worktree

**Files:**
- 合并目标：主仓库 `master`（`/home/kbzz1/manzufei_ocr`）

- [ ] **Step 1: 全量测试最终回归（worktree）**

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary
conda run -n manzufei_ocr python -m pytest evaluation/tests app/backend/tests -q
```

Expected: 全绿。

- [ ] **Step 2: 合并分支到 master**

```bash
cd /home/kbzz1/manzufei_ocr
git checkout master
git merge worktree-prompt-refactor-field-boundary -m "merge:评估体系独立成文件夹+规则文件统一(evaluation/code,tests,data,README索引,CLAUDE.md指针化)"
```

Expected: Fast-forward 或干净合并，无冲突（分支基于 master 同步点提交）。

- [ ] **Step 3: 删除当前 worktree 分支与目录**

```bash
cd /home/kbzz1/manzufei_ocr
git branch -D worktree-prompt-refactor-field-boundary
git worktree remove .claude/worktrees/prompt-refactor-field-boundary
```

（若 worktree 移除失败（数据残留），先确认 `data/evaluation` 等已由 Task 8 处理，再用 `git worktree remove --force` 重试。）

- [ ] **Step 4: 删除 review-ocr-floating-window worktree**

```bash
git worktree remove .claude/worktrees/review-ocr-floating-window
git branch -D worktree-review-ocr-floating-window 2>/dev/null || true
```

（该分支 18 个 commit 内容已以更新形态存在于 master，删除不丢工作——见 spec 第 2 节实测。）

- [ ] **Step 5: 最终状态核对**

```bash
git worktree list
git log master --oneline -3
ls evaluation/ evaluation/code evaluation/tests evaluation/data 2>/dev/null
```

Expected: 仅剩主仓库一个 worktree；master 最新提交为本次合并；`evaluation/` 结构完整（code/ tests/ data/ versions/ README.md AGENTS.md CLAUDE.md）。
