# 电脑首页与手机采集页缺口补齐设计

## 背景

`FE-01` 电脑首页和 `FE-02` 手机采集页已经具备主流程骨架：工作台可加载系统状态、创建采集会话、展示二维码；手机端可加载会话、选择图片、显示框选 overlay、上传、重试、删除、排序、补拍、重新框选和完成采集。

本次审核发现自动化测试通过，但仍存在几个 PRD/BDD 口径下的未完成行为：

- 手机端四边形框选只显示 overlay 和角点，尚不能拖动角点改变坐标。
- 重新框选已上传页时，前端使用默认框选坐标，未回显该页已保存的 `quad_points`。
- 电脑首页系统状态失败后缺少“重试”入口。
- 扫码弹窗“手机无法连接？”只展示当前链接，未提供局域网地址列表选择或手动输入入口。
- 当前会话卡片缺少“结束会话”占位入口。

本设计只补齐这些缺口，不推进任务列表、审核页、导出页，也不实现 OCR、裁剪、透视矫正、自动边界识别、字段抽取或任何云能力。

## 范围

### P0：手机采集页关键闭环

- **GAP-MOB-001**：`QuadSelector` 支持拖动四个角点更新 `quad_points`。
- **GAP-MOB-002**：角点拖动坐标限制在图片尺寸范围内。
- **GAP-MOB-003**：拖动后 overlay 实时重绘，确认上传、重新框选和补拍替换都使用用户调整后的坐标。
- **GAP-MOB-004**：会话页面列表返回已保存页面元数据中的 `quad_points`、`image_width`、`image_height`，前端重新框选时回显已保存坐标。
- **GAP-MOB-005**：旧任务或异常页面缺少保存坐标时，前端继续使用默认 80% 框选作为兼容兜底；这个兜底只基于图片尺寸，不读取图片内容。

### P1：电脑首页完整性

- **GAP-WS-001**：系统状态加载失败后展示“服务无响应”和“重试”按钮；点击后重新请求系统状态和任务列表。
- **GAP-WS-002**：扫码弹窗“手机无法连接？”展开后展示可选择的局域网地址列表，地址来自 `GET /api/system/status` 的 `lan_addresses`。
- **GAP-WS-003**：扫码弹窗帮助区支持手动输入或粘贴手机访问地址；点击“重新生成二维码”后二维码使用手动地址。
- **GAP-WS-004**：当前会话卡片展示“结束会话”占位按钮。第一阶段只作为不可用占位或提示“完成采集请在手机端操作”，不新增后端取消会话接口。

## 非目标

- 不重构首页整体布局。
- 不新增真实会话取消/结束 API。
- 不新增图片静态预览服务。
- 不做图像裁剪、透视矫正、自动边界识别或预览矫正图。
- 不从 OCR 文本、schema 或页面内容推断结构化字段。
- 不引入第三方拖拽库、云 SDK、CDN、远程字体或遥测。

## 权威依据

- `AGENTS.md`：离线运行、无云 API、前端不得推断字段。
- `docs/产品PRD.md`：PR-FE-001、PR-FE-002、PR-FE-009、PR-BE-002。
- `docs/Front/Front_BDD/workstation.md`：系统无响应重试、手机无法连接帮助。
- `docs/Front/Front_BDD/mobile-capture.md`：手机采集主流程、只读态、上传失败重试。
- `docs/Front/Front_BDD/quad-selection.md`：四边形拖动、越界限制、自相交阻止上传、重新框选。
- `docs/Front/Front_TDD/04-mobile-capture.md`、`05-page-management.md`、`06-quad-interaction.md`。
- `docs/superpowers/2026-05-14-mobile-capture-ux-redesign.md`：手机采集 UX 基线。

## 手机端设计

### QuadSelector 交互

`QuadSelector` 保持无坐标输入、无 slider、无数值面板。四个角点圆点成为可拖动控制点：

- 支持 pointer 事件，覆盖鼠标、触摸和触控笔。
- `pointerdown` 命中某个角点后记录 active corner，并调用 `setPointerCapture`。
- `pointermove` 根据 SVG 坐标系计算新坐标，更新对应角点。
- `pointerup` / `pointercancel` 清除 active corner。
- 坐标转换使用 `svg.getBoundingClientRect()` 和 `viewBox` 尺寸映射，不依赖页面缩放比例。
- 新坐标通过 `clamp` 限制在 `0 <= x <= width`、`0 <= y <= height`。
- 每次有效拖动都调用 `onChange(nextQuad)`，由父组件持久化到 React state。

拖动只改变用户确认的坐标，不做图像处理。自相交判断继续由 `isValidQuad()` 在确认上传、确认框选、确认替换前执行。

### 已保存 quad 回显

当前 `GET /api/capture-sessions/{session_id}` 只返回会话页序信息，不足以回显已保存 `quad_points`。本阶段扩展会话页数据，但不改变页序来源：

```json
{
  "page_id": "page_001",
  "page_no": 1,
  "upload_ref": "data/pages/sess_001/page_001.json",
  "image_width": 1920,
  "image_height": 1080,
  "quad_points": [
    {"x": 100, "y": 100},
    {"x": 1820, "y": 100},
    {"x": 1820, "y": 980},
    {"x": 100, "y": 980}
  ]
}
```

后端读取每个 `pages[].upload_ref` 指向的页面元数据，只把前端需要回显的安全字段合并进会话响应：

- `image_width`
- `image_height`
- `quad_points`

不返回 `original_image_path` 绝对路径，不返回图片 base64，不返回模型输出。若元数据不存在或缺字段，响应仍返回基础 `page_id/page_no/upload_ref`，前端使用默认尺寸和默认框选兜底。

### 前端页面初始化

`toInitialPages(session)` 改为优先使用后端页数据：

- `width = page.image_width ?? PREVIEW_WIDTH`
- `height = page.image_height ?? PREVIEW_HEIGHT`
- `quad = page.quad_points ? arrayToQuadByCorner(page.quad_points) : createDefaultQuad(width, height)`

`arrayToQuadByCorner()` 只做结构转换，不猜测图片内容。非法数组长度或缺坐标时返回默认框选。

## 电脑首页设计

### 系统状态重试

`WorkstationApp` 抽出 `loadDashboard()`：

- 请求 `GET /api/system/status`。
- 请求 `GET /api/tasks`。
- 系统状态失败时显示 `服务无响应`。
- 任务列表失败时保留现有提醒策略。

`WorkstationHero` 在 `systemStatus.startup === "error"` 时展示“重试”按钮。点击后调用 `loadDashboard()`；加载中禁用按钮并显示“正在重试”。

### 手机无法连接帮助

`CaptureQrDialog` 增加地址选择和手动输入状态：

- `lanAddresses` 从 `SystemStatus.lan_addresses` 传入。
- 展开帮助后展示可选地址按钮列表，例如 `192.168.1.5:8081`。
- 展开帮助后展示“手机访问链接”输入框，允许手动编辑完整 URL。
- 选择地址时，把当前 session id 拼成 `/mobile/sessions/{sessionId}` 路径，并更新二维码值。
- 手动输入 URL 后点击“重新生成二维码”，二维码使用该 URL。

首页主体仍不得直接展示 IP、端口或完整 URL；这些信息只出现在用户主动展开的帮助区。

### 结束会话占位

当前会话卡片增加“结束会话”按钮。由于后端尚无取消会话 API，本阶段行为为：

- active 会话显示按钮。
- 点击后展示轻量提示：“请在手机端点击完成采集；如需作废，请重新生成二维码。”
- 不改变后端会话状态，不删除页面，不创建任务。

## 错误处理

- `QuadSelector` 坐标计算失败时不更新坐标，不抛出未捕获异常。
- 缺失页面元数据不阻断会话加载。
- `GET /api/capture-sessions/{session_id}` 不因单页元数据缺失整体失败。
- 系统状态重试失败继续展示“服务无响应”和“重试”。
- 手动输入非法 URL 时不更新二维码，展示“请输入有效的手机访问链接”。

## 测试计划

### 后端

| ID | 测试 | 文件 |
|----|------|------|
| BE-GAP-001 | 会话详情响应合并页面 `image_width`、`image_height`、`quad_points` | `app/backend/tests/test_capture_session.py` |
| BE-GAP-002 | 页面元数据缺失时会话详情仍返回基础页面列表 | `app/backend/tests/test_capture_session.py` |
| BE-GAP-003 | 会话详情不返回 `original_image_path` 绝对路径 | `app/backend/tests/test_api_contracts.py` |

### 前端

| ID | 测试 | 文件 |
|----|------|------|
| FE-GAP-001 | 拖动左上角点后 `quad_points.tl` 更新并 overlay 重绘 | `MobileCapturePage.test.tsx` 或 `QuadSelector.test.tsx` |
| FE-GAP-002 | 角点拖出边界时坐标被 clamp 到图片范围内 | `QuadSelector.test.tsx` |
| FE-GAP-003 | 重新框选已上传页时使用后端保存的 `quad_points` | `MobileCapturePage.test.tsx` |
| FE-GAP-004 | 系统状态失败显示“服务无响应”和“重试”，点击后重新加载成功 | `App.test.tsx` |
| FE-GAP-005 | 手机无法连接帮助展示局域网地址列表和可编辑 URL 输入框 | `App.test.tsx` |
| FE-GAP-006 | 选择局域网地址或手动输入 URL 后二维码值更新 | `App.test.tsx` |
| FE-GAP-007 | 当前会话卡片显示“结束会话”占位并点击提示 | `App.test.tsx` |

## 验收标准

- 手机端框选页可拖动四个角点；拖动后确认上传的 `quad_points` 使用手动坐标。
- 角点无法拖出图片边界。
- 已上传页面重新框选时显示该页已保存坐标，不把默认框误当作保存值。
- 首页服务状态失败时有明确重试入口，后端恢复后可回到“系统已启动”。
- “手机无法连接？”只在弹窗帮助区展示局域网地址和手动 URL，不污染首页。
- 当前会话卡片显示“查看二维码”和“结束会话”占位。
- 前端 `npm run test`、`npm run typecheck`、`npm run build` 通过。
- 后端相关 pytest 通过。

## Spec 自审

- **Placeholder scan**：无 `TBD`、`TODO`、未定义接口占位。
- **Internal consistency**：手机端只补交互和已保存坐标回显；电脑端只补首页可恢复性和帮助入口；不触及审核/导出。
- **Scope check**：范围可拆为 P0 手机关键闭环和 P1 首页完整性，但写入边界清晰，可由一个实施计划分任务完成。
- **Ambiguity check**：已明确“结束会话”为占位，不新增后端取消接口；已明确缺失元数据用默认框兜底。
