# 2026-07-01 离线部署包重打设计

## 目的

基于当前 master 分支代码重新生成 manzufei_ocr 离线部署包，覆盖到 Windows 桌面 `C:\Users\97949\Desktop\manzufei_ocr_offline_bundle\`，并把 zip 副本同步到桌面。

旧包（2026-05-28）仅包含过时的 `manzufei-ocr.tar`（8.3 GB），缺 `qwen-vllm-server.tar`，并且 bat 脚本、配置、模型可能与当前代码不一致；不可继续使用。本次重打目的是让桌面包与当前代码完全同步。

## 适用范围

- 重打 `manzufei-ocr:0.1.0` 镜像（前端 `dist` 重新构建 + `docker build`）
- 复用 `qwen-vllm-openai:verified` 镜像（不重建，digest 不变）
- 完整 LLM 权重随包分发
- 不备份旧包现场数据（`data/`、`exports/`、`logs/`、`deploy_debug_logs/`）——按用户要求直接清理
- 不修改任何源码、bat、脚本；只走现有 `scripts/deploy/package_offline_docker_bundle.sh`

## 不在范围

- 不修改 `Dockerfile`、`docker-compose.yml`、bat 脚本、`app/config/local.docker.yaml`、`scripts/deploy/package_offline_docker_bundle.sh`
- 不升级 Qwen vLLM 镜像版本
- 不重打 Qwen vLLM 镜像（digest 保持）
- 不触碰 `app/frontend/` 源码（只重 build）
- 不抽离"快速重打"专用脚本（一次性任务，不污染四层结构）
- 不在仓库里保留解压目录产物（按用户要求）

## 架构与组件

### 包结构（与 `deploy/CLAUDE.md` 一致）

```
manzufei_ocr_offline_bundle/                # 解压后形态，放在桌面
├── 00_import_image.bat                    # 镜像导入（deploy/windows/ 拷入）
├── 01_start.bat                           # 启动（含 Qwen vLLM 健康等待 + LAN IP 检测）
├── 02_stop.bat                            # 停止
├── 03_logs.bat                            # 实时日志
├── README_DEPLOY.txt                      # 现场用户说明
├── docker-compose.yml                     # 仓库根最新版
├── app/
│   └── config/
│       └── local.yaml                     # 来自 app/config/local.docker.yaml
├── images/
│   ├── manzufei-ocr.tar                   # 本次新构建后导出
│   └── qwen-vllm-server.tar               # 从 deploy/offline-images/ 拷贝
├── models/
│   ├── llm/Qwen3.5-4B-AWQ-4bit/           # 完整 7.6 GB 权重
│   └── ppstructure/                       # 占位（仓库中为空 README）
├── data/  exports/  logs/                 # 空目录占位
```

### 数据流

```
本地 WSL
  │
  ├─ npm run build (app/frontend)
  │
  ├─ docker build -t manzufei-ocr:0.1.0 .
  │
  ├─ bash scripts/deploy/package_offline_docker_bundle.sh
  │     ├─ docker save → images/manzufei-ocr.tar
  │     ├─ cp qwen-vllm-server.tar
  │     ├─ cp bat 脚本 + docker-compose.yml + local.yaml
  │     ├─ tar models/ → models/
  │     └─ python3 -m zipfile → output/manzufei_ocr_offline_bundle.zip
  │
  ├─ rm -rf output/manzufei_ocr_offline_bundle/         (只留 zip)
  │
  ├─ rm -rf /mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle  (旧包清掉)
  │
  ├─ cp output/*.zip → /mnt/c/Users/97949/Desktop/
  │
  └─ unzip → /mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle/
```

## 实施步骤

### 1. 离线包组装（含 npm build + docker build + assemble + zip）

`scripts/deploy/package_offline_docker_bundle.sh` 内部已包含 `npm run build` + `docker build -t manzufei-ocr:0.1.0` + 组装 + zip 全部流程；只跑一次脚本即可。

```bash
cd /home/kbzz1/manzufei_ocr
bash scripts/deploy/package_offline_docker_bundle.sh
```

预期：
- `output/manzufei_ocr_offline_bundle/` 解压形态生成（含新构建的 `images/manzufei-ocr.tar`）
- `output/manzufei_ocr_offline_bundle.zip` 同步生成

### 2. 清理仓库侧解压产物
```bash
rm -rf /home/kbzz1/manzufei_ocr/output/manzufei_ocr_offline_bundle
```
预期：`output/` 目录里只剩 `manzufei_ocr_offline_bundle.zip`。

### 3. 清理桌面旧包
```bash
rm -rf /mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle
```
预期：旧包整体删除（包括其 `data/`、`exports/`、`logs/`、`deploy_debug_logs/` 现场历史）。**不备份**。

### 4. 同步到桌面
```bash
cp /home/kbzz1/manzufei_ocr/output/manzufei_ocr_offline_bundle.zip /mnt/c/Users/97949/Desktop/
```
预期：桌面出现新 zip（与仓库内一致）。

### 5. 桌面解压
```bash
cd /mnt/c/Users/97949/Desktop
unzip manzufei_ocr_offline_bundle.zip
```
预期：桌面出现 `manzufei_ocr_offline_bundle/` 解压目录。

### 6. 校验
- 4 个 bat 文件日期为本次（2026-07-01）
- `images/manzufei-ocr.tar` 体积与 `docker images` 报告的 `manzufei-ocr:0.1.0` `Size` 一致
- `images/qwen-vllm-server.tar` 与 `deploy/offline-images/qwen-vllm-server.tar` 体积一致
- `models/llm/Qwen3.5-4B-AWQ-4bit/` 体积 ≈ 7.6 GB
- `docker-compose.yml`、`app/config/local.yaml` 与仓库源文件一致
- 桌面 zip 与 `output/` zip 体积一致

## 错误处理

| 失败位置 | 现象 | 处理 |
|---------|------|------|
| 步骤 1（脚本内 npm build）| 前端编译错 | 脚本 `set -e` 中止；通知用户；不进入 docker build |
| 步骤 1（脚本内 docker build）| 镜像构建失败 | 脚本 `set -e` 中止；保留旧镜像 `manzufei-ocr:0.1.0`（未被覆盖） |
| 步骤 1（脚本内 docker save）| tar 导出失败 | 脚本 `set -e` 中止；不进入 zip；不碰桌面 |
| 步骤 1（脚本内 zip）| zip 失败 | 脚本 `set -e` 中止；解压目录已生成但 zip 没有 |
| 步骤 2（清理 output/）| 删除失败 | 警告继续；桌面同步步骤仍可走（只拷 zip） |
| 步骤 3（清理旧包）| 权限错 | 中止；不覆盖；用户手动处理桌面后重试 |
| 步骤 4（cp zip）| 磁盘满 | 中止；旧包已清掉 → 用户需要重跑完整流程 |
| 步骤 5（unzip）| zip 损坏 | 中止；重新跑步骤 1 重打 zip |

## 风险与回退

- **磁盘空间**：`/home/kbzz1/manzufei_ocr/output/` 临时需要 ~25 GB（解压目录）+ 2 GB（zip）= 27 GB；不足时 `docker save` 失败。
- **WSL → Windows 拷贝慢**：跨 WSL 文件系统复制大文件（9 GB tar）耗时可能 5-10 分钟；总流程预计 30-45 分钟（含构建）。
- **旧包不可恢复**：用户已明确不备份。如果新包校验失败，需要重新构建镜像。
- **桌面旧包**的 `data/exports/logs` 含历史运行数据（任务记录、导出文件、日志）；按用户确认**不备份**。
- **不修改任何脚本**意味着没有"复用现有镜像"快速路径；构建时间不可跳过。

## 验收标准

- [ ] 桌面存在 `manzufei_ocr_offline_bundle.zip`
- [ ] 桌面存在解压目录 `manzufei_ocr_offline_bundle/`
- [ ] `images/manzufei-ocr.tar` 是本次新构建的（创建时间 = 步骤 2 时间）
- [ ] `images/qwen-vllm-server.tar` 与 `deploy/offline-images/qwen-vllm-server.tar` 体积一致
- [ ] 4 个 bat 文件来自 `deploy/windows/` 当前版本
- [ ] `models/llm/Qwen3.5-4B-AWQ-4bit/` 大小 ≈ 7.6 GB
- [ ] `output/` 只含 zip，不含解压目录
- [ ] 仓库 git status 干净（本次未修改任何文件）
- [ ] 在桌面新包上本地 dry-run 校验：执行 `00_import_image.bat` 的内容是当前 `deploy/windows/00_import_image.bat`（不是旧版）

## 关键依赖

- Docker daemon 运行中（已确认 `docker info` 返回正常）
- Node.js + npm（已确认 v24.14.0 / 11.9.0）
- 现有 `qwen-vllm-openai:verified` 镜像（已存在）
- 现有 `deploy/offline-images/qwen-vllm-server.tar`（9.2 GB，已存在）
- 现有 `models/llm/Qwen3.5-4B-AWQ-4bit/`（7.6 GB，已存在）
- WSL 挂载点 `/mnt/c/Users/97949/Desktop/` 可写（已确认）
- `unzip` 命令可用（WSL 默认带）
