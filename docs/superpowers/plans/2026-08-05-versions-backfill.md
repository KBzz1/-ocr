# 补建 evaluation/versions/ 历史版本归档 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `evaluation/versions/` 下补建 9 个历史正式版本目录（extractor.v1-v4、verifier.v1-v3、evaluator.v1-v2），每目录按统一模板放 analysis.md + prompt-full.md（+ 报告），并更新索引表。

**Architecture:** 统一目录模板（每目录固定 3 文件：analysis.md 版本分析 / prompt-full.md 组件口径全文 / report.html 有则放）。恢复来源三类：git 锚点源码渲染（5 个）、metrics 源码快照（2 个）、文档标注/定稿（2 个）。临时渲染脚本放 /tmp 不入库，产物写入 `evaluation/versions/`。

**Tech Stack:** Python 3（importlib 动态加载历史源码）、git show 提取历史文件、PyYAML 加载 schema。

**参考规范:** spec `docs/superpowers/specs/2026-08-05-versions-backfill-design.md`；版本注册表 `docs/Shared/version-registry.md`；迭代规范 `evaluation/README.md`（版本迭代规范节）；step7 spec `docs/superpowers/specs/2026-08-03-verifier-step7-scale-evidence-design.md`（84-129 行 verifier.v2 逐字定稿）。

## Global Constraints

- 实施直接在 `master` 当前工作区（用户明确不建 worktree）
- 改动仅限 `evaluation/versions/` 下新增文件；渲染脚本留 `/tmp/ver_render/` 不入库
- 现有未提交修改（`app/backend/tests/test_qwen_batch_engine_layout.py`、`docs/可视化html/2026-08-02-verifier-prompt-v3-report.html`）不触碰
- 9 目录结构完全一致：统一文件名 `analysis.md` + `prompt-full.md`，不得出现 metrics-full.md 等分支命名
- prompt-full.md 头部统一元信息块（组件/版本号/锚点 commit/恢复来源/渲染日期）
- verifier.v1 的 prompt-full.md 必须明确标注"无法逐字恢复"，不编造原文
- 报告内 "v2/v3" 为实验轮次命名，analysis.md 中注明与正式版本号的区别

---

### Task 1: 渲染脚本与 extractor.v1 渲染（打通管线）

**Files:**
- Create: `/tmp/ver_render/render_extractor.py`（临时脚本，不入库）
- Create: `evaluation/versions/extractor.v1/prompt-full.md`
- Create: `evaluation/versions/extractor.v1/analysis.md`

**Interfaces:**
- Consumes: `evaluation/data/golden/case_001.json`（ocr_text 字段）、git 历史 commit 9307833、`app/config/schemas/admission_record_structured_fields.v1.yaml`
- Produces: `evaluation/versions/extractor.v1/` 目录下 analysis.md + prompt-full.md

- [ ] **Step 1: 建临时目录并写渲染脚本**

```bash
mkdir -p /tmp/ver_render
```

创建 `/tmp/ver_render/render_extractor.py`：

```python
"""渲染历史 extractor 版本完整 prompt（临时工具，不入库）。

用法: python3 render_extractor.py <commit> <schema_commit> <outdir>
  <commit>        prompts.py 锚点 commit（如 9307833）
  <schema_commit> schema 锚点 commit（与 prompts.py 同 commit）
  <outdir>        versions/<版本号>/ 目录
"""
import importlib.util
import json
import os
import re
import subprocess
import sys

import yaml

GOLDEN = "/home/kbzz1/manzufei_ocr/evaluation/data/golden/case_001.json"
PROMPTS_PATH = "app/backend/services/copd_extraction/prompts.py"
SCHEMA_PATH = "app/config/schemas/admission_record_structured_fields.v1.yaml"


def git_show(commit: str, path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{commit}:{path}"], capture_output=True, text=True, check=True
    ).stdout


def build_evidence_units(ocr_text: str) -> list[dict]:
    """按句号/换行把 ocr_text 切成轻量证据单元（与生产 evidence_units 结构同形）。"""
    units = []
    sentences = re.split(r"(?<=[。；\n])", ocr_text)
    for i, s in enumerate(sentences, 1):
        s = s.strip()
        if s:
            units.append({"id": f"u{i:03d}", "text": s, "page_no": 1})
    return units


def load_prompts(commit: str, workdir: str):
    """git show 提取 prompts.py 到临时文件并用 importlib 加载。"""
    src = git_show(commit, PROMPTS_PATH)
    path = f"{workdir}/prompts_{commit}.py"
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    spec = importlib.util.spec_from_file_location(f"prompts_{commit}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_schema(commit: str, workdir: str) -> dict:
    raw = git_show(commit, SCHEMA_PATH)
    path = f"{workdir}/schema_{commit}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        f.write(raw)
    return yaml.safe_load(raw)


def main():
    commit, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    data = json.load(open(GOLDEN, encoding="utf-8"))
    units = build_evidence_units(data["ocr_text"])
    schema = load_schema(commit, "/tmp/ver_render")
    prompts = load_prompts(commit, "/tmp/ver_render")

    # v1/v2: build_admission_structured_fields_prompt 返回单字符串；
    # v3/v4: build_admission_structured_fields_messages 返回 (system, user)。
    if hasattr(prompts, "build_admission_structured_fields_messages"):
        system, user = prompts.build_admission_structured_fields_messages(
            schema, units, document_text=data["ocr_text"]
        )
        full = f"### SYSTEM\n\n{system}\n\n### USER\n\n{user}"
    else:
        full = prompts.build_admission_structured_fields_prompt(
            schema, units, document_text=data["ocr_text"]
        )

    header = (
        "<!-- 组件口径全文（prompt-full.md 统一模板）\n"
        f"组件: extractor（抽取器）\n"
        f"版本: 由 commit {commit} 锚定\n"
        f"恢复来源: git show {commit} prompts.py 渲染（输入: golden/case_001.json）\n"
        "渲染日期: 2026-08-05\n"
        "-->\n\n"
    )
    with open(f"{outdir}/prompt-full.md", "w", encoding="utf-8") as f:
        f.write(header + full)
    print(f"OK: {outdir}/prompt-full.md ({len(full)} chars)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行渲染脚本（extractor.v1）**

```bash
cd /home/kbzz1/manzufei_ocr
conda run -n manzufei_ocr python /tmp/ver_render/render_extractor.py 9307833 evaluation/versions/extractor.v1
```

Expected: 输出 `OK: evaluation/versions/extractor.v1/prompt-full.md (NNNN chars)`；文件非空且含 case_001 病例文本（"反复咳嗽"等）与字段表（field_key 列表）。

- [ ] **Step 3: 写 extractor.v1 analysis.md**

创建 `evaluation/versions/extractor.v1/analysis.md`：

```markdown
# extractor.v1 — 版本分析

- **版本号**: `extractor.v1`（旧命名 `admission_record_structured_fields_prompt.v1`）
- **锚点**: commit `9307833`（blob sha256 前16: `859614c281ece328`）
- **日期**: 注册表建档日 2026-08-03（v1–v3 为事后按里程碑命名）

## 变更摘要

固定字段 Qwen prompt 契约初版。字段表来自 `admission_record_structured_fields.v1` schema，
证据以编号单元（evidence_units）形式入 prompt，含 OCR 风险提示（1/I/l、P62/PO2 等近形错读）、
药名纠偏规则、字段输出契约（field_key/original_value/evidence/confidence 等）。

## 依据

- 版本注册表 §3（`docs/Shared/version-registry.md`）

## 指标对比与结论

v1 为体系初版，无先前版本可比；无独立评估报告（评估体系 08-01 才建立）。
```

- [ ] **Step 4: 验证并提交**

```bash
cd /home/kbzz1/manzufei_ocr
wc -l evaluation/versions/extractor.v1/prompt-full.md evaluation/versions/extractor.v1/analysis.md
grep -c "反复咳嗽" evaluation/versions/extractor.v1/prompt-full.md   # 期望 ≥1
git add evaluation/versions/extractor.v1/
git commit -m "docs:versions补建 extractor.v1(锚点9307833渲染+分析)"
```

---

### Task 2: extractor.v2/v3 渲染

**Files:**
- Create: `evaluation/versions/extractor.v2/prompt-full.md` + `analysis.md`
- Create: `evaluation/versions/extractor.v3/prompt-full.md` + `analysis.md`

**Interfaces:**
- Consumes: Task 1 的 `/tmp/ver_render/render_extractor.py`（同一脚本直接复用）
- Produces: extractor.v2/v3 两个版本目录

- [ ] **Step 1: 渲染 extractor.v2**

```bash
cd /home/kbzz1/manzufei_ocr
conda run -n manzufei_ocr python /tmp/ver_render/render_extractor.py 69fe68d evaluation/versions/extractor.v2
```

Expected: `OK: .../prompt-full.md (NNNN chars)`，含 "压缩" 版输出契约（注册表 §3 v2 描述：压缩 Qwen 字段抽取输出）。

- [ ] **Step 2: 渲染 extractor.v3**

```bash
conda run -n manzufei_ocr python /tmp/ver_render/render_extractor.py 97627fb evaluation/versions/extractor.v3
```

Expected: 输出为 `### SYSTEM` / `### USER` 两段（v3 起用 `build_admission_structured_fields_messages` 返回元组）；对比 v2 明显删除【再次强调】与 OCR 风险段（注册表 §3 v3 描述：精简重构为 6 段骨架）。

- [ ] **Step 3: 写两个 analysis.md**

创建 `evaluation/versions/extractor.v2/analysis.md`：

```markdown
# extractor.v2 — 版本分析

- **版本号**: `extractor.v2`（旧命名沿用 `admission_record_structured_fields_prompt.v1` 常量，事后按里程碑命名）
- **锚点**: commit `69fe68d`（blob sha256 前16: `92cc870331a81185`）

## 变更摘要

压缩 Qwen 字段抽取输出：明确 evidence 用 `evidence_ids`（编号列表），不允许模型自行撰写
evidence 文本；补充严禁 OCR 修正/标题纠正/页序重排、诊断字段仅摘录原文等规则；未找到字段
返回 `status="not_found", value="", evidence_ids=[]` 不得省略。

## 依据

- 版本注册表 §3

## 指标对比与结论

无独立评估报告；为 v1→v3 中间形态。
```

创建 `evaluation/versions/extractor.v3/analysis.md`：

```markdown
# extractor.v3 — 版本分析

- **版本号**: `extractor.v3`（旧命名沿用 `admission_record_structured_fields_prompt.v1` 常量）
- **锚点**: commit `97627fb`（blob sha256 前16: `80fbb28245332302`）

## 变更摘要

精简重构为 6 段骨架（任务边界/状态判定/取值策略/字段目录/示例），删除【再次强调】与 OCR 风险段；
长文本字段拆句核验（`_split_sentences`，句末标点+逗号续拆）。

## 依据

- 版本注册表 §3（v3 终态 `6f9bf90` 另 +13 条 pe_* 字段边界 description，并入 v4 前的过渡形态）

## 指标对比与结论

无独立评估报告；为 v3 主状态（非终态），终态描述见 extractor.v4。
```

- [ ] **Step 4: 验证并提交**

```bash
cd /home/kbzz1/manzufei_ocr
grep -c "反复咳嗽" evaluation/versions/extractor.v2/prompt-full.md evaluation/versions/extractor.v3/prompt-full.md
git add evaluation/versions/extractor.v2/ evaluation/versions/extractor.v3/
git commit -m "docs:versions补建 extractor.v2(69fe68d)/v3(97627fb)渲染+分析"
```

---

### Task 3: extractor.v4 / verifier.v3 渲染（当前代码）

**Files:**
- Create: `evaluation/versions/extractor.v4/prompt-full.md` + `analysis.md`
- Create: `evaluation/versions/verifier.v3/prompt-full.md` + `analysis.md`

**Interfaces:**
- Consumes: 当前工作区 `app/backend/services/copd_extraction/prompts.py`（已验证与 cc6cb78 完全一致，diff 0 行）
- Produces: extractor.v4 / verifier.v3 目录

- [ ] **Step 1: 写当前代码渲染脚本（verifier.v3 + extractor.v4）**

创建 `/tmp/ver_render/render_current.py`（当前工作区代码含 `field_policies` 相对导入，须从仓库根直接 import，不能用 git show + importlib）：

```python
"""渲染当前代码的 verifier.v3 与 extractor.v4 完整 prompt。

fields 输入从 golden case_001 构造最小 claims（与生产 verifier 请求同形）。
"""
import json
import sys

sys.path.insert(0, "/home/kbzz1/manzufei_ocr")
from app.backend.services.copd_extraction.prompts import (  # noqa: E402
    build_admission_structured_fields_messages,
    build_verification_messages,
)
from app.backend.services.schema_loader import load_schema  # noqa: E402

GOLDEN = "/home/kbzz1/manzufei_ocr/evaluation/data/golden/case_001.json"
SCHEMA = "/home/kbzz1/manzufei_ocr/app/config/schemas/admission_record_structured_fields.v1.yaml"
OUT = "/home/kbzz1/manzufei_ocr/evaluation/versions"

data = json.load(open(GOLDEN, encoding="utf-8"))
units = []
for i, s in enumerate(data["ocr_text"].split("\n"), 1):
    if s.strip():
        units.append({"id": f"u{i:03d}", "text": s.strip(), "page_no": 1})

# ---- verifier.v3 ----
fields = []
for k, v in list(data["golden"].items())[:5]:
    if isinstance(v, str):
        fields.append({"field_key": k, "value": v, "evidence_ids": ["u001"]})
system, user = build_verification_messages(units, fields, append_reminder=False)
header = (
    "<!-- 组件口径全文（prompt-full.md 统一模板）\n"
    "组件: verifier（复核器）\n"
    "版本: verifier.v3（当前 HEAD == commit cc6cb78，已确认 diff 0 行）\n"
    "恢复来源: 当前代码渲染（输入: golden/case_001.json 前5字段）\n"
    "渲染日期: 2026-08-05\n"
    "-->\n\n"
)
with open(f"{OUT}/verifier.v3/prompt-full.md", "w", encoding="utf-8") as f:
    f.write(header + f"### SYSTEM\n\n{system}\n\n### USER\n\n{user}")
print(f"OK verifier.v3: {len(system) + len(user)} chars")

# ---- extractor.v4 ----
schema = load_schema(SCHEMA)
system, user = build_admission_structured_fields_messages(
    schema, units, document_text=data["ocr_text"]
)
header = (
    "<!-- 组件口径全文（prompt-full.md 统一模板）\n"
    "组件: extractor（抽取器）\n"
    "版本: extractor.v4（当前 HEAD == commit cc6cb78 后的 v4 状态）\n"
    "恢复来源: 当前代码渲染（输入: golden/case_001.json，schema: 当前 v1 yaml）\n"
    "渲染日期: 2026-08-05\n"
    "-->\n\n"
)
with open(f"{OUT}/extractor.v4/prompt-full.md", "w", encoding="utf-8") as f:
    f.write(header + f"### SYSTEM\n\n{system}\n\n### USER\n\n{user}")
print(f"OK extractor.v4: {len(system) + len(user)} chars")
```

- [ ] **Step 2: 运行渲染**

```bash
cd /home/kbzz1/manzufei_ocr
mkdir -p evaluation/versions/verifier.v3 evaluation/versions/extractor.v4
conda run -n manzufei_ocr python /tmp/ver_render/render_current.py
```

Expected: `OK verifier.v3: NNNN chars`、`OK extractor.v4: NNNN chars`。verifier.v3 内容含表述规范性契约、术语陌生判别、5 个 JSON 微例（u911-u913 虚拟 ID）、逗号级拆句（"value 超过 40 字时按逗号补充拆分"）；extractor.v4 含 61 字段 T/J/D 策略标记、3 个 JSON 微例（u901-u903）、`POLICY_DEFINITIONS` 取值策略。

- [ ] **Step 3: 写两个 analysis.md**

创建 `evaluation/versions/extractor.v4/analysis.md`：

```markdown
# extractor.v4 — 版本分析

- **版本号**: `extractor.v4`（首个显式版本常量；旧命名 `admission_record_structured_fields_prompt.v4`）
- **锚点**: 当前 HEAD（blob sha256 前16: `d121b834ff85688f`；PPEMA-V1 终态 `01250ed89387ba30`）

## 变更摘要

61 字段 T/J/D 策略标记（取值策略真源迁至 `field_policies.py`）+ 字段边界 description
（"仅："渲染）+ 3 个 JSON 局部微例（共享否定作用域/J 型异常优先/禁止推导 BMI，虚拟 ID u901-u903）。
字段目录行格式统一为 `field_key｜中文名｜P 标记｜特有边界`。

## 依据

- 版本注册表 §3（v4 两行：PPEMA-V1 终态 + 命名规范化后）
- PPEMA-V1 设计：`docs/codex_design/prompt-policy-metric-alignment-v1/DESIGN.md`

## 指标对比与结论

PPEMA-V1 实验报告（`docs/可视化html/`）含抽取器对比结论，详见
`docs/codex_design/prompt-policy-metric-alignment-v1/WORKER_REPORT.md`；
本目录 prompt-full.md 为当前线上形态。
```

创建 `evaluation/versions/verifier.v3/analysis.md`：

```markdown
# verifier.v3 — 版本分析

- **版本号**: `verifier.v3`（显式版本常量 `VERIFIER_PROMPT_VERSION`，不渲染进 prompt）
- **锚点**: commit `cc6cb78`（2026-08-04；blob sha256 前16: `7f9ca9aece4be109`）

## 变更摘要

表述规范性契约（只检查证据中确实可定位的非标准表述——错读/病句/残缺/标签或单位问题，
不归因于 OCR、不要求给出修正词）；术语陌生判别（规范用词但少见如"粗测听力"不标；
非标准用词或形近/音近标准词如"胸状胸→桶状胸"必须标）；5 个 JSON 微例（含错读形似
规范词对照，虚拟 ID u911-u913）；逗号级拆句（value>40 字按逗号/顿号补充拆分）；
checks 键 `ocr_text_clear`→`text_standard`、reason `ocr_quality_issue`→`nonstandard_expression`；
字段级分组调用。

## 依据

- 版本注册表 §5（v3 定稿行）
- 设计：`docs/superpowers/specs/2026-08-04-verifier-v3-design.md`

## 指标对比与结论

v3 为当前上线形态（定稿后未再迭代）；kappa 达标验证见上线报告
`docs/可视化html/2026-08-02-verifier-prompt-v3-report.html` 的实验轮次对比
（注：该报告内 v2/v3 为实验轮次命名，非本目录正式版本号）。
```

- [ ] **Step 4: 验证并提交**

```bash
cd /home/kbzz1/manzufei_ocr
grep -c "术语陌生" evaluation/versions/verifier.v3/prompt-full.md   # 期望 ≥1
grep -c "T/J/D\|POLICY" evaluation/versions/extractor.v4/prompt-full.md || true
git add evaluation/versions/extractor.v4/ evaluation/versions/verifier.v3/
git commit -m "docs:versions补建 extractor.v4/verifier.v3(当前代码渲染)+分析"
```

---

### Task 4: evaluator.v1/v2 源码快照

**Files:**
- Create: `evaluation/versions/evaluator.v1/prompt-full.md` + `analysis.md`
- Create: `evaluation/versions/evaluator.v2/prompt-full.md` + `analysis.md`

**Interfaces:**
- Consumes: `git show f8cabaa:app/backend/evaluation/metrics.py`（v1 终态 134 行）、当前 `evaluation/code/metrics.py`（v2，355 行）
- Produces: evaluator.v1/v2 目录（prompt-full.md 内容为指标源码快照 + 头部注明"评估器无 prompt"）

- [ ] **Step 1: 写快照脚本**

创建 `/tmp/ver_render/snapshot_metrics.py`：

```python
"""生成 evaluator 版本 prompt-full.md（metrics.py 源码快照）。"""
import subprocess

OUT = "/home/kbzz1/manzufei_ocr/evaluation/versions"


def snapshot(commit_or_none, outdir, version, note):
    if commit_or_none:
        src = subprocess.run(
            ["git", "show", f"{commit_or_none}:app/backend/evaluation/metrics.py"],
            capture_output=True, text=True, check=True,
        ).stdout
        anchor = f"commit {commit_or_none}"
    else:
        src = open("/home/kbzz1/manzufei_ocr/evaluation/code/metrics.py", encoding="utf-8").read()
        anchor = "当前 HEAD"
    header = (
        "<!-- 组件口径全文（prompt-full.md 统一模板）\n"
        "组件: evaluator（评估指标）\n"
        f"版本: {version}\n"
        f"恢复来源: {note}（{anchor}）——评估器无 prompt，以指标源码为口径全文\n"
        "快照日期: 2026-08-05\n"
        "-->\n\n"
        "# evaluator metrics.py 快照（指标口径全文）\n\n"
        "```python\n"
    )
    with open(f"{OUT}/{outdir}/prompt-full.md", "w", encoding="utf-8") as f:
        f.write(header + src + "\n```\n")
    print(f"OK {outdir}: {len(src)} chars")


snapshot("f8cabaa", "evaluator.v1", "evaluator.v1",
         "git show f8cabaa（v1 终态）")
snapshot(None, "evaluator.v2", "evaluator.v2",
         "当前 evaluation/code/metrics.py")
```

- [ ] **Step 2: 运行快照**

```bash
cd /home/kbzz1/manzufei_ocr
mkdir -p evaluation/versions/evaluator.v1 evaluation/versions/evaluator.v2
conda run -n manzufei_ocr python /tmp/ver_render/snapshot_metrics.py
```

Expected: `OK evaluator.v1: 134+ chars`、`OK evaluator.v2: 355+ chars`。

- [ ] **Step 3: 写两个 analysis.md**

创建 `evaluation/versions/evaluator.v1/analysis.md`：

```markdown
# evaluator.v1 — 版本分析

- **版本号**: `evaluator.v1`（旧命名 `admission_eval.v1`）
- **锚点**: v1 初版 commit `37b08db`；v1 终态 commit `f8cabaa`（blob sha256 前16: `10df6daa516cced6`）

## 变更摘要

评估指标模块：文本归一化（NFKC/去空白/去标点）、value 两级比较（exact/substring/mismatch）、
幻觉定位（value_located_in_text）、status 比对。v1 终态新增 J 型归一接线、金标不可定位豁免、
长文本核心句重合。

## 依据

- 版本注册表 §4

## 指标对比与结论

无先前版本可比；评估口径从 v1 起建立，report meta 以 `metric_version` 记录。
```

创建 `evaluation/versions/evaluator.v2/analysis.md`：

```markdown
# evaluator.v2 — 版本分析

- **版本号**: `evaluator.v2`（显式版本常量 `METRIC_VERSION`；旧命名 `admission_eval.v2`）
- **锚点**: 当前 HEAD（blob sha256 前16: `2a1944a318cf75fd`）

## 变更摘要

非对称 J 比较器（全正常判断谓词/摘录族双向子串/大小便投影）+ case_005 金标两处修正；
J 字段集合以 prompt 策略共享真源（`field_policies.NORMAL_JUDGEMENT_FIELD_KEYS`）为准。

## 依据

- 版本注册表 §4（v2 两行：PPEMA-V1 终态 + 命名规范化后）

## 指标对比与结论

跨版本比较不得输出可比 delta（`run_eval._print_compare` 对版本不同只警告）；
v1→v2 为口径演进，非回归比较。
```

- [ ] **Step 4: 验证并提交**

```bash
cd /home/kbzz1/manzufei_ocr
grep -c "def compare_value" evaluation/versions/evaluator.v1/prompt-full.md   # 期望 ≥1
grep -c "def normalize_text" evaluation/versions/evaluator.v2/prompt-full.md  # 期望 ≥1
git add evaluation/versions/evaluator.v1/ evaluation/versions/evaluator.v2/
git commit -m "docs:versions补建 evaluator.v1(f8cabaa快照)/v2(当前快照)+分析"
```

---

### Task 5: verifier.v1/v2 文档来源版本

**Files:**
- Create: `evaluation/versions/verifier.v1/prompt-full.md` + `analysis.md`
- Create: `evaluation/versions/verifier.v2/prompt-full.md` + `analysis.md`
- Copy: `docs/可视化html/2026-08-02-verifier-prompt-v3-report.html` → `evaluation/versions/verifier.v1/report.html`

**Interfaces:**
- Consumes: 版本注册表 §5、step7 spec `docs/superpowers/specs/2026-08-03-verifier-step7-scale-evidence-design.md` 84-129 行
- Produces: verifier.v1/v2 目录

- [ ] **Step 1: 复制报告并写 verifier.v1 文件**

```bash
cd /home/kbzz1/manzufei_ocr
mkdir -p evaluation/versions/verifier.v1
cp "docs/可视化html/2026-08-02-verifier-prompt-v3-report.html" evaluation/versions/verifier.v1/report.html
```

创建 `evaluation/versions/verifier.v1/analysis.md`：

```markdown
# verifier.v1 — 版本分析

- **版本号**: `verifier.v1`（2026-08-03 建档基线；此前复核器无版本管理）
- **锚点**: 源码未提交（blob sha256 前16: `05703d3761d989bc`，不在 git 对象库）

## 变更摘要

精简五步式（固定审核顺序：grounding → field scope → OCR quality → logic consistency →
verdict），checks 键为 `grounding_supported/field_scope_valid/ocr_text_clear/logic_consistent`，
示例为纯文字（无 JSON）。kappa 0.40 旧口径，未达 0.7 上岗线。

## 依据

- 版本注册表 §5（v1 基线行）
- step7 spec 描述：工作区已是精简五步式（用户差量，未提交；HEAD 为"通用原则 7 条"完整版）

## 指标对比与结论

kappa 0.40（旧口径，未达 0.7 上岗线）。前身里程碑（注册表 §5）：初版 `bb61f1b`、
降误报 `ae2f1f1`、去对抗改造 `2039e80`、精简重构 `afd1722`、召回强化 `c3946a9`、
分组调用 `6a765af`。

## 附：本目录报告说明

`report.html` 为 2026-08-02 复核器去对抗改造实验报告。**注意：报告内 "v2/v3" 为实验轮次
命名**（对应去对抗改造 2039e80 / 精简重构 afd1722 里程碑），非本目录正式版本号；
作为 v1 基线前身实验证据收录。
```

创建 `evaluation/versions/verifier.v1/prompt-full.md`（标注无法恢复）：

```markdown
<!-- 组件口径全文（prompt-full.md 统一模板）
组件: verifier（复核器）
版本: verifier.v1
恢复来源: ⚠️ 源码未提交且 blob 05703d3761d989bc 不在 git 对象库，无法逐字恢复
渲染日期: 2026-08-05
-->

# verifier.v1 — 口径全文不可恢复声明

**本版本 prompt 源码从未提交**（2026-08-03 建档时为工作区差量），注册表锚点 blob
`05703d3761d989bc` 不在 git 对象库，**无法逐字恢复 prompt-full 原文**。以下为
注册表与 step7 spec 对该版本的描述片段（**非原文**）：

## 注册表 §5 描述

> 精简五步式（用户差量；kappa 0.40 旧口径，未达 0.7 上岗线）

## step7 spec 描述（2026-08-03-verifier-step7-scale-evidence-design.md）

> 工作区 `build_verification_messages` 已是精简五步式（用户差量，未提交；HEAD 为
> "通用原则 7 条"完整版）——checks 键已改为
> `grounding_supported/field_scope_valid/ocr_text_clear/logic_consistent`，
> 示例为纯文字（无 JSON）

## 与 verifier.v2 的关系

v2 定稿在 v1 基础上增加三类边界、4 个 JSON 微例、输出契约节与 cited ID 预检
（见 `verifier.v2/prompt-full.md`，取自 step7 spec 逐字定稿）。
```

- [ ] **Step 2: 写 verifier.v2 文件**

从 `docs/superpowers/specs/2026-08-03-verifier-step7-scale-evidence-design.md` 84-129 行（`### 3.1 复核器 prompt 定稿` 节的 ```` ```text ```` 代码块）原样提取逐字定稿文本。

创建 `evaluation/versions/verifier.v2/analysis.md`：

```markdown
# verifier.v2 — 版本分析

- **版本号**: `verifier.v2`（2026-08-03 定稿）
- **锚点**: 源码未提交（blob sha256 前16: `1035dfcc5bed471e`，不在 git 对象库）

## 变更摘要

step7：三类边界（字段越界/OCR 错读/完整有据）+ 4 个 JSON 微例（u9xx 虚拟 ID）+
输出契约节（顶层 verifications 一一对应、五字段、checks 四布尔、comment 规则）+
cited ID 预检声明（证据装配缺失不归因于字段）+ 后端语义契约（pass↔checks↔reason 一致性 /
reason↔check 对应 / comment 引用真实 uXXX；违规整组跳过）。

## 依据

- 版本注册表 §5（v2 定稿行）
- 设计定稿：`docs/superpowers/specs/2026-08-03-verifier-step7-scale-evidence-design.md` §3.1

## 指标对比与结论

v2 为 step7 实验基线₂'（定稿 prompt + 上岗形态）与 A'（+字段级分块+完整证据）的
共同 prompt 基线；kappa 结果见 step7 实验（spec 附录）与
`docs/可视化html/2026-08-02-verifier-prompt-v3-report.html` 实验轮次对比。
```

创建 `evaluation/versions/verifier.v2/prompt-full.md`（头部注明取自 spec 逐字定稿）——用脚本从 spec 提取，避免手工转写错误：

```bash
cd /home/kbzz1/manzufei_ocr
python3 - <<'EOF'
import re
spec = open("docs/superpowers/specs/2026-08-03-verifier-step7-scale-evidence-design.md",
            encoding="utf-8").read()
m = re.search(r"```text\n(.*?)```", spec, re.S)
assert m, "spec 中未找到 ```text 代码块"
header = (
    "<!-- 组件口径全文（prompt-full.md 统一模板）\n"
    "组件: verifier（复核器）\n"
    "版本: verifier.v2\n"
    "恢复来源: step7 spec §3.1 逐字定稿（2026-08-03-verifier-step7-scale-evidence-design.md 84-129 行），"
    "源码未提交且 blob 不在对象库，以设计文档定稿为准\n"
    "提取日期: 2026-08-05\n"
    "-->\n\n"
)
with open("evaluation/versions/verifier.v2/prompt-full.md", "w", encoding="utf-8") as f:
    f.write(header + m.group(1).rstrip() + "\n")
print("OK verifier.v2:", len(m.group(1)), "chars")
EOF
```

Expected: 输出非空；内容含"固定审核顺序""输出契约""【示例一】【示例二】"。

- [ ] **Step 3: 验证并提交**

```bash
cd /home/kbzz1/manzufei_ocr
ls -la evaluation/versions/verifier.v1/   # 应含 analysis.md + prompt-full.md + report.html
grep -c "不可恢复" evaluation/versions/verifier.v1/prompt-full.md   # 期望 ≥1
grep -c "固定审核顺序" evaluation/versions/verifier.v2/prompt-full.md  # 期望 ≥1
git add evaluation/versions/verifier.v1/ evaluation/versions/verifier.v2/
git commit -m "docs:versions补建 verifier.v1(标注不可恢复)/v2(step7 spec定稿)+分析+报告"
```

---

### Task 6: 索引表更新与全量验证

**Files:**
- Modify: `evaluation/versions/README.md`（索引表追加 9 行）

**Interfaces:**
- Consumes: Task 1-5 的全部目录产物
- Produces: 完整索引表（9 行 + 表头）

- [ ] **Step 1: 更新索引表**

修改 `evaluation/versions/README.md`，把占位行 `|（自下一次迭代起登记；历史版本不回溯补建）|` 替换为 9 行数据：

```markdown
| 版本号 | 日期 | 变更摘要 | 分析文档 | 全量提示词 | 报告 |
|---|---|---|---|---|---|
| extractor.v1 | 2026-08-03 建档 | 固定字段 Qwen prompt 契约初版 | [analysis.md](extractor.v1/analysis.md) | [prompt-full.md](extractor.v1/prompt-full.md) | — |
| extractor.v2 | 2026-08-03 建档 | 压缩 Qwen 字段抽取输出 | [analysis.md](extractor.v2/analysis.md) | [prompt-full.md](extractor.v2/prompt-full.md) | — |
| extractor.v3 | 2026-08-03 建档 | 精简重构 6 段骨架 | [analysis.md](extractor.v3/analysis.md) | [prompt-full.md](extractor.v3/prompt-full.md) | — |
| extractor.v4 | 2026-08-04 | 61 字段 T/J/D 策略 + 3 JSON 微例 | [analysis.md](extractor.v4/analysis.md) | [prompt-full.md](extractor.v4/prompt-full.md) | — |
| verifier.v1 | 2026-08-03 建档 | 精简五步式（kappa 0.40 未达上岗线） | [analysis.md](verifier.v1/analysis.md) | [prompt-full.md](verifier.v1/prompt-full.md)（标注不可恢复） | [report.html](verifier.v1/report.html) |
| verifier.v2 | 2026-08-03 定稿 | step7 三类边界 + 4 微例 + 输出契约 | [analysis.md](verifier.v2/analysis.md) | [prompt-full.md](verifier.v2/prompt-full.md)（step7 spec 定稿） | — |
| verifier.v3 | 2026-08-04 | 表述规范性契约 + 术语陌生判别 + 5 微例 | [analysis.md](verifier.v3/analysis.md) | [prompt-full.md](verifier.v3/prompt-full.md) | — |
| evaluator.v1 | 2026-08-03 建档 | 归一化/两级 value/幻觉定位/status 比对 | [analysis.md](evaluator.v1/analysis.md) | [prompt-full.md](evaluator.v1/prompt-full.md)（metrics 快照） | — |
| evaluator.v2 | 2026-08-04 | 非对称 J 比较器 + 金标豁免 | [analysis.md](evaluator.v2/analysis.md) | [prompt-full.md](evaluator.v2/prompt-full.md)（metrics 快照） | — |
```

- [ ] **Step 2: 全量验证**

```bash
cd /home/kbzz1/manzufei_ocr
# 1) 9 个目录各含 analysis.md + prompt-full.md（verifier.v1 另有 report.html）
for v in extractor.v1 extractor.v2 extractor.v3 extractor.v4 verifier.v1 verifier.v2 verifier.v3 evaluator.v1 evaluator.v2; do
  echo "$v: $(ls evaluation/versions/$v | tr '\n' ' ')"
done
# 2) 所有 prompt-full.md 非空
find evaluation/versions -name "prompt-full.md" | xargs wc -l | tail -1
# 3) 真实病例文本抽查
grep -l "反复咳嗽" evaluation/versions/*/prompt-full.md
# 4) 索引表 9 行
grep -c "^| extractor\|^| verifier\|^| evaluator" evaluation/versions/README.md   # 期望 9
# 5) 链接可打开
for v in extractor.v1 extractor.v2 extractor.v3 extractor.v4 verifier.v1 verifier.v2 verifier.v3 evaluator.v1 evaluator.v2; do
  test -f evaluation/versions/$v/analysis.md -a -f evaluation/versions/$v/prompt-full.md || echo "MISSING: $v"
done
echo "全部目录文件齐全"
```

Expected: 每目录 2-3 个文件齐全；prompt-full.md 总计非空；case_001 文本出现于渲染版本；索引表 9 行；无 MISSING 输出。

- [ ] **Step 3: 提交**

```bash
cd /home/kbzz1/manzufei_ocr
git add evaluation/versions/README.md
git commit -m "docs:versions补建完成——索引表登记9个历史正式版本"
git log --oneline -5
git status --short   # 应仅剩既有未提交修改（tests/test_qwen_batch_engine_layout.py、verifier-prompt-v3-report.html）
```
