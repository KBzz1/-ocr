# AGENTS.md

## 作用

本文件是全仓库长期 onboarding，只保留所有任务都适用的项目定位、目录边界和工作规则。文档目录的细节先读 `docs/AGENTS.md`，代码目录职责先读目标目录的 `README.md`。

## 项目定位

本仓库服务于院内离线病历文书结构化采集与人工核验工作站。产品运行在医生本地 Windows 电脑上，手机只作为拍照采集终端；目标是把人工逐字录入转化为电脑端人工核验、修正、确认和导出。

## 权威入口

- 文档规则：`docs/AGENTS.md` / `docs/CLAUDE.md`
- 产品需求：`docs/产品PRD.md`
- PRD 实现清单：`docs/PRD任务清单.md`
- 状态枚举：`docs/Shared/state-enums.md`
- 错误码：`docs/Shared/error-codes.md`
- 术语表：`docs/Shared/terminology.md`
- 应用目录边界：`app/README.md`
- superpower 的 specs 文档内容：`docs/superpowers/specs`
- superpower 的 plans 文档内容：`docs/superpowers/plans`

## 目录职责

- `run.bat`、`stop.bat`：Windows 离线运行入口。
- `app/backend/`：本地后端服务，负责本地 API、状态、持久化、导出和外部算法端口编排。
- `app/frontend/`：电脑端工作台与手机端采集页。
- `app/config/`：应用配置命名空间，不提交真实部署参数。
- `runtime/python/`：嵌入式 Python 运行环境。
- `models/ppstructure/`：外部图像、OCR、文档解析模型。
- `models/llm/`：外部 LLM 字段抽取模型。
- `data/`：上传文件、处理结果和临时文件。
- `exports/`：本地导出文件。
- `logs/`：本地运行日志。

## 仓库边界

- 系统离线运行；不得依赖云 API、CDN、遥测上传或运行时联网下载模型。
- 不接入医院 HIS/EMR，不写回病历系统，不生成诊断结论或医学建议。
- 图像处理、OCR、文档解析、LLM 字段抽取由外部本地算法模块提供。
- 本仓库不得实现 OCR、LLM 字段抽取、图像预处理、裁剪、透视矫正或规则抽取。
- 后端只负责调用外部算法模块、校验契约、持久化结果、维护状态、导出和记录本地日志。
- 算法模块缺失、失败、返回空结构化字段或契约非法时，任务必须进入 `failed`，不得降级或规则兜底。
- 前端不得从 schema、OCR 文本或页面内容推断、补造结构化字段。

## 数据与隐私

- `data/`、`exports/`、`logs/` 中的真实运行数据不得提交。
- 日志不得包含完整病历原文、身份证号、图片 base64 或模型输出全文。
- 配置文件不得提交本机私有路径、密钥、患者数据路径或真实模型路径。

## 工作方式

- 根级 agent 文档只保留全仓库通用信息；目录细节读取 `docs/AGENTS.md` 或对应目录 README。
- 修改行为、状态或错误码前，先检查 `docs/产品PRD.md`、`docs/Shared/` 和相关 TDD/BDD 文档，如果对应文档跟当前任务有冲突，请告知我。
- 新增实现时，测试设计和契约文档先于实现落地；外部算法只写端口契约和失败处理，不在本仓库实现算法。
- 当前 PRD 进度以 `docs/PRD任务清单.md` 为索引；具体行为以对应 BDD/TDD、spec、plan 和代码测试为准。
- AGENTS.md 与 CLAUDE.md 成对维护：同目录内容保持一致，只替换标题行。
- Git commit message 使用中文。
- python环境使用的 conda 环境，名称为 manzufei_ocr ，运行时直接使用 conda run 