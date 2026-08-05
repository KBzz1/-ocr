# 补建 evaluation/versions/ 历史版本归档 — 设计

> 日期：2026-08-05
> 状态：设计定稿
> 关联规范：`evaluation/README.md`（版本迭代规范）、`docs/Shared/version-registry.md`（版本注册表）

## 1. 背景与目标

`evaluation/versions/` 下没有历次版本的文件夹。原因：该目录与"版本迭代规范"是 2026-08-04（commit 28eafee）才建立的，规范明确"自下一次版本迭代起登记；历史版本不回溯补建"，且规范建立至今未发生新迭代，故目录只有索引表 README.md。

用户要求补建所有历史正式版本（9 个），并保持**统一目录模板**：9 个目录结构完全一致、命名一致、内容职责一致，后续版本直接套用，可演进。

权威版本记录：`docs/Shared/version-registry.md` 登记三个 LLM 组件（抽取 prompt / 评估指标 / 复核器）的版本演进与锚点。

## 2. 统一目录模板

`evaluation/versions/<组件>.<版本号>/` 下固定 3 个文件：

```
versions/
├── README.md            # 索引表（追加 9 行）
├── extractor.v1/
│   ├── analysis.md      # 版本变更摘要/依据/指标对比/结论
│   ├── prompt-full.md   # 组件口径全文（头部统一元信息块）
│   └── report.html      # 本版本报告（没有则省略）
├── ...（其余版本同结构）
```

**`prompt-full.md` 语义统一为"组件口径全文"**，头部带统一元信息块（组件/版本号/锚点 commit/恢复来源/渲染日期），内容按组件类型分三种：

| 组件 | prompt-full.md 内容 |
|---|---|
| 抽取器 extractor | `build_admission_structured_fields_messages` 渲染的完整 system+user |
| 复核器 verifier | `build_verification_messages` 渲染的完整 system+user |
| 评估器 evaluator | 完整指标口径（metrics.py 源码快照，注明"评估器无 prompt"） |
| 无法恢复（verifier.v1） | "无法逐字恢复"声明 + 注册表/step7 spec 描述片段（明确标注非原文） |

设计约束（来自用户决策）：
- 9 目录结构完全一致，不因组件差异产生分支命名（如 metrics-full.md 之类不允许）
- verifier.v1 也建 prompt-full.md（标注无法恢复），保证结构统一
- 报告内 "v2/v3" 为实验轮次命名，不得与正式版本号混淆

## 3. 9 个版本目录内容来源

| 目录 | analysis.md 内容来源 | prompt-full.md 恢复方式 |
|---|---|---|
| extractor.v1 | commit 9307833：固定字段 Qwen prompt 契约初版 | git show 9307833 的 prompts.py，用当时 schema 渲染 |
| extractor.v2 | commit 69fe68d：压缩 Qwen 字段抽取输出 | git show 69fe68d 渲染 |
| extractor.v3 | commit 97627fb：精简重构 6 段骨架（删【再次强调】与 OCR 风险段） | git show 97627fb 渲染 |
| extractor.v4 | 当前 HEAD：61 字段 T/J/D 策略标记 + 字段边界 + 3 JSON 微例 | 当前代码渲染 |
| verifier.v1 | 注册表 §5：精简五步式（kappa 0.40 旧口径，未达 0.7 上岗线） | **无法逐字恢复** → 声明 + 附注册表 §5 / step7 spec 描述片段 |
| verifier.v2 | 注册表 §5 + step7 spec：三类边界 + 4 个 JSON 微例 + 输出契约节 + cited ID 预检 | 以 step7 spec 84-129 行"逐字定稿"为准（注明来源为设计文档） |
| verifier.v3 | commit cc6cb78：表述规范性契约 + 术语陌生判别 + 5 个 JSON 微例 + 逗号级拆句 | git show cc6cb78 渲染 |
| evaluator.v1 | 注册表 §4 + commit f8cabaa（v1 终态）：归一化/两级 value/幻觉定位/status 比对 | git show f8cabaa 的 metrics.py 快照 |
| evaluator.v2 | 当前 HEAD：非对称 J 比较器 + 金标豁免 + 长文本核心句重合 | 当前 metrics.py 快照 |

精确来源共 7 个：5 个渲染（extractor.v1/v2/v3/v4、verifier.v3）+ 2 个源码快照（evaluator.v1/v2）；另 2 个（verifier.v1/v2）为标注/设计文档来源。

## 4. 渲染方式

临时渲染脚本放 `/tmp/ver_render/`（不入库）。

- **extractor.v1/v2/v3**：`git show <commit>` 提取 prompts.py 到临时文件 → `importlib` 直接加载（v1/v2/v3 仅依赖 `json`/`re`，无相对导入）→ 用 `evaluation/data/golden/case_001.json` 的 `ocr_text` 构造证据单元 `[{"id": "u001", "text": ..., "page_no": 1}]` → 调用当时的渲染函数（v1/v2：`build_admission_structured_fields_prompt`；v3：`build_admission_structured_fields_messages`）→ 输出完整 system+user。
- **extractor.v4 / verifier.v3**：依赖 `field_policies.py` 相对导入 → 从当前 checkout 复制完整 `copd_extraction` 包到临时目录，`sys.path` 指向后 import 渲染。verifier 的 fields 输入从 golden 构造最小 claims（含 field_key/value/evidence_ids）。
- **schema 输入**：各版本用当时的 `admission_record_structured_fields.v1.yaml`（v1 时代该文件路径已确认不变，`git show <commit>:app/config/schemas/admission_record_structured_fields.v1.yaml`）。
- **evaluator.v1/v2**：直接快照源码（f8cabaa / 当前）到 prompt-full.md。

渲染输出头部注明：版本号、锚点 commit、渲染日期、输入样本（case_001）。

## 5. 报告 HTML 归属

- `docs/可视化html/2026-08-02-verifier-prompt-v3-report.html` → 复制到 `verifier.v1/report.html`；analysis.md 注明"报告内 v2/v3 为实验轮次命名（对应注册表 §5 去对抗改造 2039e80 / 精简重构 afd1722 里程碑），非正式版本号；作为 v1 基线前身实验证据"。
- 其余报告（normalization 设计/复盘、evaluation 复盘，08-01）为规范建立前的前身文档，不复制，在相关 analysis.md 中链接引用（README 统一索引已有）。

## 6. 索引表更新

`versions/README.md` 按规范追加 9 行：版本号 | 日期 | 变更摘要 | 分析文档 | 全量提示词 | 报告。评估器行"全量提示词"列链接 prompt-full.md（内容为指标快照）。

## 7. 实施范围与环境

- 实施：直接在 `master` 当前工作区执行（用户明确不建 worktree）。改动仅限 `evaluation/versions/` 下新增文件 + 索引表更新；渲染脚本留 /tmp 不入库。
- 现有未提交修改（`app/backend/tests/test_qwen_batch_engine_layout.py`、`docs/可视化html/2026-08-02-verifier-prompt-v3-report.html`）不触碰。

## 8. 验证

1. 全部 9 个 prompt-full.md 产出：5 个渲染版本非空完整、2 个 evaluator 快照完整、2 个（verifier.v1/v2）标注来源明确
2. 抽查渲染输出含真实病例文本（case_001 句子出现在 user 段）
3. `versions/README.md` 索引表 9 行齐全，链接路径可打开
4. 9 个目录各含 analysis.md；verifier.v1 的 prompt-full.md 明确标注不可恢复来源
5. `git status` 仅 `evaluation/versions/` 下新增/修改
