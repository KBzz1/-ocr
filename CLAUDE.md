# CLAUDE.md

## 作用

本文件是全仓库长期 onboarding，只保留所有任务都适用的项目定位、目录边界和工作规则。文档目录的细节先读 `docs/AGENTS.md`；代码/部署/脚本目录的细节先读目标目录的 `CLAUDE.md`（如 `app/backend/CLAUDE.md`、`deploy/CLAUDE.md`、`scripts/CLAUDE.md`），没有 CLAUDE.md 的再读 `README.md`。

## 项目定位

本仓库服务于院内离线病历文书结构化采集与人工核验工作站。产品运行在医生本地 Windows 电脑上，手机只作为拍照采集终端；目标是把人工逐字录入转化为电脑端人工核验、修正、确认和导出。

## 权威入口

- 文档规则：`docs/AGENTS.md` / `docs/CLAUDE.md`
- 产品需求：`docs/PRD文档/产品PRD.md`
- PRD 实现清单：`docs/PRD文档/PRD任务清单.md`
- 状态枚举：`docs/Shared/state-enums.md`
- 错误码：`docs/Shared/error-codes.md`
- 术语表：`docs/Shared/terminology.md`
- 应用目录边界：`app/README.md`
- superpower 的 specs 文档内容：`docs/superpowers/specs`
- superpower 的 plans 文档内容：`docs/superpowers/plans`

## 目录职责

- `deploy/windows/`：Windows Docker 离线部署入口。
- `run.sh`、`stop.sh`：WSL/本机开发薄入口，实际脚本在 `scripts/dev/`。
- `deploy/offline-images/`：正式离线 Docker 镜像 tar 缓存，用于本地启动和离线打包。
- `deploy/` 整体规则见 `deploy/CLAUDE.md`（打包、镜像 digest、排障日志路径等）。
- `app/backend/`：本地后端服务，负责本地 API、状态、持久化、导出、算法子系统端口编排，以及结构化字段结果契约校验。端口层和 COPD 抽取核心代码分别有自己的 `CLAUDE.md`：`app/backend/services/algorithm_ports/CLAUDE.md`、`app/backend/services/copd_extraction/CLAUDE.md`。
- `app/frontend/`：电脑端工作台与手机端采集页。
- `app/config/`：应用配置命名空间，不提交真实部署参数。
- `scripts/`：开发启停、部署打包、离线检查和维护脚本，按 `dev/`、`deploy/`、`checks/`、`maintenance/` 分层。详见 `scripts/CLAUDE.md`。
- `models/ppstructure/`：外部图像、OCR、文档解析模型。
- `models/llm/`：本地 LLM 模型权重。
- `data/`：上传文件、处理结果和临时文件。
- `exports/`：本地导出文件。
- `logs/`：本地运行日志。

## 仓库边界

- 系统离线运行；不得依赖云 API、CDN、遥测上传或运行时联网下载模型。
- 不接入医院 HIS/EMR，不写回病历系统，不生成诊断结论或医学建议。
- OCR、图像处理、文档解析和 LLM 结构化提取按算法子系统管理；可以随算法团队迭代替换，但必须通过稳定端口、配置和部署契约接入主流程。
- 后端业务代码不得与某一套算法实现强耦合；算法实现可在独立目录、镜像、脚本或适配器中交付，主流程只依赖输入输出契约、失败语义和可观测日志。
- 慢阻肺/呼吸系统入院记录的字段体系、审核契约、薄规则质量核验和任务状态流转属于当前主代码范围；不得扩展为通用医学规则引擎或生成医学建议。
- 后端负责调用算法子系统、校验契约、持久化结果、维护状态、导出和记录本地日志。
- 算法子系统缺失、失败、结构化处理整体不可用、字段结果全空或契约非法时，任务必须进入 `failed`；单字段可疑应进入审核页由人工核验。
- 前端不得从 schema、OCR 文本或页面内容推断、补造结构化字段。

## 数据与隐私

- `data/`、`exports/`、`logs/` 中的真实运行数据不得提交。
- 配置文件不得提交本机私有路径、密钥、患者数据路径或真实模型路径。

## 工作方式

- 根级 agent 文档只保留全仓库通用信息；目录细节读取 `docs/AGENTS.md` 或对应目录 `CLAUDE.md`/`README.md`。
- 修改行为、状态或错误码前，先检查 `docs/PRD文档/产品PRD.md`、`docs/Shared/` 和相关 TDD/BDD 文档，如果对应文档跟当前任务有冲突，请告知我。
- 新增实现时，测试设计和契约文档先于实现落地；算法子系统变更先明确端口输入输出、部署形态、失败语义和隐私边界，再落实现或适配代码。
- 当前 PRD 进度以 `docs/PRD文档/PRD任务清单.md` 为索引；具体行为以对应 BDD/TDD、spec、plan 和代码测试为准。
- Git commit message 使用中文。
- Python 测试和本地命令默认使用 conda 环境 `manzufei_ocr`，例如 `conda run -n manzufei_ocr python -m pytest app/backend/tests -q`。
