# CLAUDE.md

## 作用

本文件管辖 `scripts/` 下所有脚本。它补充根级 `CLAUDE.md` 和 `docs/AGENTS.md`，只记录**进入 `scripts/` 工作时**才需要的长期独有规则；全局项目定位、目录边界、文档入口仍以根级 agent 文件为准。

## 适用前置

- 仓库根 `CLAUDE.md`：项目定位、目录职责、仓库边界、数据隐私、工作方式。
- `docs/AGENTS.md` / `docs/CLAUDE.md`：文档入口、信息架构、共享契约。
- `app/backend/README.md` 等：被本目录脚本拉起或检查的代码模块说明。

## 四层分层与固定语义

`scripts/` 严格按四层组织，**不要混层**；新增脚本前先确认归属。

- `scripts/dev/`：本地开发启停薄脚本。仓库根 `run.sh` / `stop.sh` 是薄入口，几行 `exec` 到这里的同名脚本；真正的启停、健康等待、镜像加载、配置注入都在 `scripts/dev/run.sh`、`scripts/dev/stop.sh` 里。
- `scripts/deploy/`：离线/部署打包脚本。例：`package_offline_docker_bundle.sh`。打包、镜像导出、Windows 部署包组装放这里。
- `scripts/checks/`：一次性或可重跑的检查脚本。例：`offline_startup_check.py`。需要可执行入口、明确退出码、CI/现场可单独调用。
- `scripts/maintenance/`：维护性脚本。例：`archive_logs.sh`。日志归档、临时清理、巡检、状态汇总等放这里。

## 分层约束

- 启停类脚本只放 `dev/`；不要放进 `deploy/` 或 `checks/`。
- 检查类脚本放 `checks/`，带可执行入口和明确退出码（成功 0、失败非 0），便于现场或 CI 单跑。
- 维护性脚本（归档、清理、巡检、状态汇总）放 `maintenance/`。
- 离线包、Windows 部署包、镜像 tar 打包脚本放 `deploy/`。
- `checks/` 和 `maintenance/` 的边界：检查产生**通过/失败结论**并退出码；维护脚本产生**状态变更**（移动文件、清理、归档）并通常继续执行。

## 根级薄入口约定

- 仓库根 `run.sh` / `stop.sh` 是薄入口，内部 `exec` 到 `scripts/dev/run.sh` / `scripts/dev/stop.sh`。
- 修改启停行为、等待超时、健康 URL、conda 路径、镜像加载策略时，**同时检查根级和 `scripts/dev/` 两处**，确认薄入口只是 `exec` 转发。
- 不在根级 `run.sh` / `stop.sh` 里堆业务逻辑。

## 脚本环境

- Python 脚本默认使用 conda 环境 `manzufei_ocr`；调用前先确认环境存在再走 `conda run -n manzufei_ocr` 或直接使用环境内解释器。
- Shell 脚本面向 WSL/Linux 运行环境，使用 bash + `set -euo pipefail`；不要依赖交互式提示。
- Windows 端的入口在 `deploy/windows/` 下的 bat 包装；不要把 Windows 专属逻辑混进 `dev/` 的 bash 脚本。
- 脚本**不得硬编码**本机私有路径、conda 绝对路径以外的部署路径、密钥、患者数据路径、模型权重路径；这类信息通过仓库根相对路径或环境变量注入。

## 离线原则

- 脚本不得依赖云 API、CDN、遥测上传、运行时远程下载模型。
- 检查类脚本里出现的网络相关断言要明确是"检查网络不通/检查远端不可达"，而不是去拉远端。
- 镜像加载、模型挂载必须走本地 `deploy/offline-images/`、本地 `models/`、`docker load -i` 等离线路径。

## 数据与隐私

- 脚本不得把 `data/`、`exports/`、`logs/` 的真实运行数据写进仓库或提交。
- 维护脚本（归档、清理）可以移动 `logs/` 内容到本地 `.local/archive/` 之类的非提交目录，但归档路径要在 `.gitignore` 范围内。
- 脚本不得打印患者数据、模型权重绝对路径、API 密钥；诊断输出只到路径、退出码、状态字段。

## 工作方式

- 新增脚本前先确认分层归属；不确定时优先 `checks/`（带退出码的最容易复用）。
- 修改 `scripts/dev/run.sh` 等启停脚本前，先读 `docs/部署/` 相关 Windows 离线 Docker 与 GPU/OCR 文档，确认启停契约没漂移。
- 修改 `scripts/checks/offline_startup_check.py` 的扫描目标（如新增 bat/sh）时，同步更新 `SCAN_FILES` 之类的显式清单，不要靠通配符偷懒。
- 修改 `scripts/maintenance/archive_logs.sh` 的归档目标时，确认目标目录在 `.gitignore` 范围内且不会污染根目录可见文件。
- 调试和现场排障时优先用 `set -x` 或独立 `checks/` 脚本复现，不要直接改 `dev/` 的入口脚本做临时实验。

## 不再下设的 agent 文件

- `scripts/dev/`、`scripts/deploy/`、`scripts/checks/`、`scripts/maintenance/` **不再下设** `CLAUDE.md` / `AGENTS.md`。
- 子目录的独有规则若超过本文件容量，应回到根级 `CLAUDE.md` / `docs/AGENTS.md` 升级，而不是在本目录里再嵌套。
