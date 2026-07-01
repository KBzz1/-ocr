# 离线部署包重打 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于当前 master 代码重新生成 `manzufei_ocr_offline_bundle`，覆盖到 `C:\Users\97949\Desktop\manzufei_ocr_offline_bundle\`，并把 zip 副本同步到桌面。

**Architecture:** 完全复用现有 `scripts/deploy/package_offline_docker_bundle.sh`（内含 npm build + docker build + assemble + zip），不修改任何源文件、不修改任何脚本；跑完脚本后清理 output/ 和桌面旧包，把 zip 拷到桌面再解压。

**Tech Stack:** Bash 4.x + WSL + Docker + Node.js 24 + zipfile

## Global Constraints

- **不修改任何仓库文件**（代码、bat、脚本、配置、Dockerfile 都不动）。
- **不备份**桌面旧包的 `data/`、`exports/`、`logs/`、`deploy_debug_logs/`（用户已确认不备份）。
- **`output/` 仓库侧只留 zip**，解压目录要清掉。
- **桌面同时放** `manzufei_ocr_offline_bundle.zip` 和解压目录 `manzufei_ocr_offline_bundle\`。
- **脚本内 `set -euo pipefail`** 生效；任何中间命令失败立即中止。
- **Git commit message 使用中文**。

## File Structure

本次任务**无源文件变更**。所有产物都是新文件/新目录：

| 路径 | 类型 | 来源 |
|------|------|------|
| `output/manzufei_ocr_offline_bundle/` | 临时目录（脚本生成，步骤 2 清掉） | packager 脚本 |
| `output/manzufei_ocr_offline_bundle.zip` | 保留 | packager 脚本 |
| `C:\Users\97949\Desktop\manzufei_ocr_offline_bundle.zip` | 最终交付 | cp |
| `C:\Users\97949\Desktop\manzufei_ocr_offline_bundle\` | 最终交付 | unzip |

---

### Task 1: 跑 packager 脚本生成 output/

**Files:**
- 读取：`/home/kbzz1/manzufei_ocr/scripts/deploy/package_offline_docker_bundle.sh`
- 读取：`/home/kbzz1/manzufei_ocr/app/frontend/package.json`
- 读取：`/home/kbzz1/manzufei_ocr/Dockerfile`
- 读取：`/home/kbzz1/manzufei_ocr/deploy/offline-images/qwen-vllm-server.tar`（9.2 GB，必须存在）
- 读取：`/home/kbzz1/manzufei_ocr/models/llm/Qwen3.5-4B-AWQ-4bit/`（7.6 GB，必须存在）
- 写入：`/home/kbzz1/manzufei_ocr/output/manzufei_ocr_offline_bundle/`（解压目录）
- 写入：`/home/kbzz1/manzufei_ocr/output/manzufei_ocr_offline_bundle.zip`

**Step 1.1:** 跑前预检

```bash
cd /home/kbzz1/manzufei_ocr
docker info >/dev/null 2>&1 && echo "DOCKER_OK" || echo "DOCKER_FAIL"
ls -la deploy/offline-images/qwen-vllm-server.tar | awk '{print $5}'
du -sh models/llm models/ppstructure
df -h /home/kbzz1/manzufei_ocr/output
```

预期输出：
- `DOCKER_OK`
- 镜像 tar 大小约 9223650816
- `models/llm` 约 7.6G
- `output` 所在盘可用空间 ≥ 30G

如果 DOCKER_FAIL 或 tar 缺失或 output 盘空间 < 30G → 中止并告知用户。

- [ ] **Step 1.2:** 跑 packager 脚本（一次性完成 npm build + docker build + assemble + zip）

```bash
cd /home/kbzz1/manzufei_ocr
bash scripts/deploy/package_offline_docker_bundle.sh 2>&1 | tee /tmp/packager.log
```

预期日志（按顺序出现）：
- `Building frontend dist...`
- `Building Docker image: manzufei-ocr:0.1.0`
- `Creating offline bundle: .../output/manzufei_ocr_offline_bundle`
- `Loading layer...`（docker save 输出）
- `Copying Qwen vLLM server tar...`
- `Copying models...`
- `Bundle ready: .../output/manzufei_ocr_offline_bundle`
- `Creating zip archive: .../output/manzufei_ocr_offline_bundle.zip`
- `Archive ready: .../output/manzufei_ocr_offline_bundle.zip`

总耗时 10-25 分钟。如果中途失败（`set -e` 中止），看 `tee` 输出诊断。

- [ ] **Step 1.3:** 校验产物

```bash
cd /home/kbzz1/manzufei_ocr
ls -la output/
du -sh output/manzufei_ocr_offline_bundle
ls output/manzufei_ocr_offline_bundle/images/
du -sh output/manzufei_ocr_offline_bundle/images/*
du -sh output/manzufei_ocr_offline_bundle/models/llm
```

预期：
- `output/` 含 `manzufei_ocr_offline_bundle/` 目录和 `manzufei_ocr_offline_bundle.zip`
- `images/manzufei-ocr.tar` 体积与 `docker images manzufei-ocr:0.1.0` 的 SIZE 一致（≈ 8.88 GB，但 docker save 后略大；通常 9-10 GB）
- `images/qwen-vllm-server.tar` 体积 ≈ 9.2 GB（与 `deploy/offline-images/qwen-vllm-server.tar` 相同）
- `models/llm/Qwen3.5-4B-AWQ-4bit/` ≈ 7.6 GB

**Task 1 完成条件**：两个 tar 都在、models/llm 完整、zip 存在。

---

### Task 2: 清理仓库侧 output/ 解压目录

**Files:**
- 删除：`/home/kbzz1/manzufei_ocr/output/manzufei_ocr_offline_bundle/`

**Step 2.1:** 删解压目录

```bash
cd /home/kbzz1/manzufei_ocr
rm -rf output/manzufei_ocr_offline_bundle
ls -la output/
```

预期：`output/` 只剩 `manzufei_ocr_offline_bundle.zip`，其他为空（除 `.` `..`）。

**Task 2 完成条件**：`output/` 干净，只留 zip。

---

### Task 3: 清理桌面旧包

**Files:**
- 删除：`C:\Users\97949\Desktop\manzufei_cr_offline_bundle\`（即 `/mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle/`）

**Step 3.1:** 删桌面旧包（**不备份**）

```bash
rm -rf /mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle
ls -la /mnt/c/Users/97949/Desktop/ | grep manzufei || echo "OLD_BUNDLE_CLEANED"
```

预期：`manzufei_ocr_offline_bundle` 目录已不在桌面；`OLD_BUNDLE_CLEANED` 被打印。

⚠️ **不可恢复操作**：如果用户在清理后想恢复旧包数据，需要从外部备份恢复。本任务不创建任何备份。

**Task 3 完成条件**：桌面无 `manzufei_ocr_offline_bundle/` 目录。

---

### Task 4: 同步 zip 到桌面

**Files:**
- 拷贝：`/home/kbzz1/manzufei_ocr/output/manzufei_ocr_offline_bundle.zip` → `/mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle.zip`

**Step 4.1:** 拷 zip

```bash
cp /home/kbzz1/manzufei_ocr/output/manzufei_ocr_offline_bundle.zip /mnt/c/Users/97949/Desktop/
ls -la /mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle.zip
```

预期：zip 在桌面，体积与仓库内一致。

**Step 4.2:** 比对体积

```bash
ls -l /home/kbzz1/manzufei_ocr/output/manzufei_ocr_offline_bundle.zip | awk '{print $5}'
ls -l /mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle.zip | awk '{print $5}'
```

预期：两个数字相等（zip 体积稳定，跨文件系统拷贝不会改大小）。

**Task 4 完成条件**：桌面 zip 与仓库 zip 体积一致。

---

### Task 5: 在桌面解压

**Files:**
- 解压到：`/mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle/`

**Step 5.1:** 桌面解压

```bash
cd /mnt/c/Users/97949/Desktop
unzip -q manzufei_ocr_offline_bundle.zip
ls -la manzufei_ocr_offline_bundle/
```

预期输出（顶层）：
```
00_import_image.bat
01_start.bat
02_stop.bat
03_logs.bat
README_DEPLOY.txt
app
data
docker-compose.yml
exports
images
logs
models
```

**Step 5.2:** 校验关键文件大小

```bash
cd /mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle
ls -la 0*.bat README_DEPLOY.txt docker-compose.yml
du -sh images models
```

预期：
- 4 个 bat 文件存在，日期 2026-07-01（今天）
- `images/` 约 18-20 GB
- `models/llm` 约 7.6 GB

**Task 5 完成条件**：桌面解压目录结构完整、关键文件齐全。

---

### Task 6: 终验 + git 状态确认

**Files:**
- 无文件变更（只读校验）

**Step 6.1:** 完整目录对比

```bash
diff <(cd /home/kbzz1/manzufei_ocr && find deploy/windows app/config/local.docker.yaml docker-compose.yml -maxdepth 2 -type f | sort) \
     <(cd /mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle && find . -maxdepth 3 -type f -name "*.bat" -o -name "*.txt" -o -name "*.yml" -o -name "*.yaml" | sort) \
     || true
```

预期：bat/yml/yaml/txt 文件在两个位置都存在。

**Step 6.2:** 确认 bat 脚本内容最新

```bash
diff /home/kbzz1/manzufei_ocr/deploy/windows/01_start.bat /mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle/01_start.bat
```

预期：无差异（zip 内的 bat 与仓库 deploy/windows/ 一致）。

**Step 6.3:** 确认 git 工作区干净

```bash
cd /home/kbzz1/manzufei_ocr
git status
```

预期：
- 仅 `docs/superpowers/specs/2026-07-01-...` 和 `docs/superpowers/plans/2026-07-01-...` 已 commit
- 无未追踪文件、无未提交修改
- `output/` 内容**不**在 git 跟踪下（确认 `output/` 在 `.gitignore` 内或 git 不会跟踪它）

如果 git 显示 untracked files 在 `output/` → 警告（但任务不阻断）。

**Step 6.4:** 打印交付清单

```bash
echo "=== 交付清单 ==="
echo "zip:"
ls -lh /mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle.zip
echo "解压目录:"
ls -la /mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle/
echo "images:"
ls -lh /mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle/images/
echo "models/llm:"
du -sh /mnt/c/Users/97949/Desktop/manzufei_ocr_offline_bundle/models/llm
echo "=== 桌面最终状态 ==="
ls /mnt/c/Users/97949/Desktop/ | grep -i manzufei
```

预期：
- 桌面有 `manzufei_ocr_offline_bundle.zip` 和 `manzufei_ocr_offline_bundle/`
- 两个 tar 都在 images/ 下
- models/llm 7.6 GB

**Task 6 完成条件**：所有验收点通过，git 工作区干净。

---

## Self-Review Checklist（已在写入时核对）

- [x] 覆盖了 spec 中所有 6 个步骤
- [x] 没有 TBD / TODO / "implement later" 类占位符
- [x] 每个命令都是完整 bash 块
- [x] 体积/路径都是绝对路径
- [x] 任务顺序正确（脚本 → 清 output → 清桌面 → 拷 zip → 解压 → 校验）
- [x] 风险点（旧包不可恢复、磁盘空间、构建耗时）已在 Task 1.1 / Task 3.1 显式提示
- [x] 不修改任何源文件（已写入 Global Constraints）
