# 手机采集页 UX 重构设计

## 背景

当前手机采集页已经具备会话加载、图片选择、四边形框选、上传、删除、排序和完成采集的基础能力，但交互仍偏工程化：

- 拍照与相册选择是两个入口，和最新 PRD 中的单入口设计不一致。
- `QuadSelector` 暴露 X/Y 像素输入、range 和 number 控件，不符合医生移动端操作心智。
- 页面列表仍使用上移/下移文字按钮和独立补拍卡片，未对齐素材中的行内操作。
- 底部操作区使用 fixed 定位，会遮挡列表内容。
- “重新框选”和“补拍当前页”缺少完整的前后端契约。
- 前端当前删除/排序接口路径使用 `/api/mobile/<session_id>/pages/<page_id>` 和 `/api/mobile/<session_id>/pages/reorder`，但后端已存在的删除/排序路由在 `/api/capture-sessions/<session_id>/pages/<page_id>` 和 `/api/capture-sessions/<session_id>/pages/order`，需要在实现中收敛。

本设计把手机端定位为“快速拍摄、确认识别范围、整理页序、完成采集”的轻量工作流，不承担 OCR、裁剪、透视矫正、字段推断或复杂审核。

## 范围

本阶段覆盖：

- **UX-001**：拍照和相册选择合并为单个“拍摄/选择图片”入口。
- **UX-002**：框选页只保留图片、四边形 overlay、四个角点、提示条和操作按钮，删除像素值输入、坐标面板、滑块。
- **UX-003**：拍摄或选择图片后进入框选页，默认框选图片中心约 80% 区域；用户可不调整直接确认上传。
- **UX-004**：已上传页面列表项右侧显示行内按钮：补拍、重新框选、删除，最小触控高度 44px。
- **UX-005**：上传失败页面只显示重试、删除；重试为蓝色实心按钮，删除为灰色描边红字。
- **UX-006**：页面列表使用拖拽手柄 `⋮⋮` 排序，删除上移/下移文字按钮。
- **UX-007**：底部“继续拍下一页”和“完成采集”融入内容流，不使用 `position: fixed`。
- **UX-008**：删除独立“补拍页面”卡片；补拍入口合并到列表项行内按钮。
- **UX-009**：新增 `PUT /api/mobile/{session_id}/pages/{page_id}/quad`，支持已上传页面只更新框选坐标。
- **UX-010**：新增 `PUT /api/mobile/{session_id}/pages/{page_id}/image`，支持补拍当前页并替换原图与框选元数据，保持 page_id/page_no 不变。
- **UX-011**：MobileCapturePage 拆分为小组件，入口文件只负责状态编排、API 调用和模式切换。
- **UX-012**：CSS 对齐手机端素材视觉，删除 fixed footer、上移/下移按钮和补拍卡片样式。

本阶段不覆盖：

- 图像压缩、裁剪、透视矫正、自动边界识别或预览矫正图。
- 电脑端工作台、审核页、导出页改造。
- 新增图片静态预览服务。刷新页面后若后端未返回可访问缩略图 URL，前端显示通用“缩略图”卡片。
- OCR、LLM 字段抽取、规则兜底或从图片内容推断字段。

## 视觉对齐

参考素材目录：`docs/Front/Design/图片设计稿/`

- `手机端主页上半部分（未拍照时）ui.png`
- `手机端主页下半部分完成拍照后页面列表ui.png`
- `手机端框选时ui.png`

视觉规则：

- 顶栏为白底，左侧返回、中间标题、右侧帮助；标题按页面模式显示“病历文书采集”“已采集页面”“调整识别范围”。
- 顶部会话状态使用绿色胶囊标签，左侧绿色圆点，右侧显示“已采集 N 页，可删除、调整页序或补拍”等业务说明，不展示 IP、端口或完整 URL。
- 未采集首页使用浅蓝弱背景卡片、蓝色主按钮、白底蓝描边次按钮、文档/相机图标风格；由于交互合并为单入口，主按钮文案为“拍摄/选择图片”。
- 框选页顶部使用浅蓝提示条：“请框选病历正文区域，排除屏幕边缘、灰色背景和工具栏”。
- 框选图片区大面积展示图片，四个角点为蓝色圆形手柄，overlay 只表达有效识别区域，不展示任何坐标数值。
- 页面列表使用白色卡片：左侧拖拽手柄，随后缩略图、页序、状态标签和行内操作按钮。
- 已上传状态为绿色标签；上传失败为橙红标签。
- 主要按钮为蓝色实心，次要按钮为白底蓝描边，重新框选为橙色描边，删除为灰色描边红字。
- 页面按钮、拖拽手柄、帮助、返回等触控目标不小于 44px。
- 页面不得使用装饰性渐变球、营销式大 hero 或固定悬浮底栏；移动端内容应可连续滚动。

## 页面模式

| 模式 | 触发 | 主内容 | 退出条件 |
|------|------|--------|----------|
| `empty` | active 会话且无页面 | 采集引导卡片 + 单入口按钮 + 空列表 + 禁用完成采集 | 选择图片进入 `quad-new` |
| `list` | active 会话且有页面 | 页面列表 + 行内操作 + 内容流底部按钮 | 点击继续拍下一页进入 `quad-new` |
| `quad-new` | 新拍/新选图片 | 默认 quad + 重拍 + 确认上传 | 上传成功回 `list`；重拍回上一模式 |
| `quad-replace` | 点击某页“补拍”并选择图片 | 新图片 + 默认 quad + 重拍 + 确认上传 | 替换成功回 `list`；页序不变 |
| `quad-edit` | 点击某页“重新框选” | 原页面图片或通用缩略图卡片 + 已保存 quad + 取消 + 确认上传 | 更新坐标成功回 `list` |
| `readonly` | 会话 expired/locked/invalid/loading | 状态说明 + 只读列表或空状态 | 无编辑动作 |

说明：

- “继续拍下一页”只追加新页面。
- “补拍”只替换当前页面的原图与框选元数据，保持 page_id/page_no 不变。
- “重新框选”只更新当前页面的 quad_points，不重新上传图片。
- 上传失败项代表本地待上传页面，不应出现补拍或重新框选按钮。

## 数据模型

前端页面项统一使用 `CapturePageItem`：

```typescript
export type CapturePageStatus = 'uploaded' | 'uploading' | 'failed';

export interface CapturePageItem {
  localId: string;
  pageId?: string;
  pageNo: number;
  status: CapturePageStatus;
  previewUrl?: string;
  file?: File;
  width: number;
  height: number;
  quad: QuadPointsByCorner;
}
```

后端会话页记录至少包含：

```json
{
  "page_id": "page_001",
  "page_no": 1,
  "upload_ref": "pages/sess_001/page_001.json"
}
```

页面元数据文件至少包含：

```json
{
  "page_id": "page_001",
  "session_id": "sess_001",
  "page_no": 1,
  "original_image_path": "/abs/path/page_001.jpg",
  "processed_image_path": null,
  "image_width": 1920,
  "image_height": 1080,
  "quad_points": [{"x": 100, "y": 100}, {"x": 1820, "y": 100}, {"x": 1820, "y": 980}, {"x": 100, "y": 980}],
  "uploaded_at": "2026-05-14T08:00:00+00:00",
  "quad_updated_at": "2026-05-14T08:05:00+00:00"
}
```

## API 契约

### 前端使用的现有接口

| 操作 | 方法与路径 | 说明 |
|------|------------|------|
| 查询会话 | `GET /api/capture-sessions/{session_id}` | 加载状态和页面列表 |
| 上传新页面 | `POST /api/mobile/{session_id}/pages` | multipart；新增 page_id/page_no |
| 删除页面 | `DELETE /api/capture-sessions/{session_id}/pages/{page_id}` | 使用现有后端路由 |
| 排序页面 | `PUT /api/capture-sessions/{session_id}/pages/order` | 使用现有后端路由；body 为 `{ "page_ids": [...] }` |
| 完成采集 | `POST /api/mobile/{session_id}/finish` | 锁定会话并创建或复用任务 |

### 新增：更新框选坐标

```
PUT /api/mobile/{session_id}/pages/{page_id}/quad
Content-Type: application/json

{
  "quad_points": [{"x": 100, "y": 100}, {"x": 1820, "y": 100}, {"x": 1820, "y": 980}, {"x": 100, "y": 980}]
}
```

成功响应：

```json
{
  "success": true,
  "data": {
    "page_id": "page_001",
    "page_no": 1,
    "quad_points": [{"x": 100, "y": 100}, {"x": 1820, "y": 100}, {"x": 1820, "y": 980}, {"x": 100, "y": 980}],
    "quad_updated_at": "2026-05-14T08:05:00+00:00"
  }
}
```

错误：

- `SESSION_NOT_FOUND`：会话不存在。
- `SESSION_EXPIRED`：会话过期。
- `SESSION_LOCKED`：会话已完成采集。
- `SESSION_NOT_FOUND`：页面不存在时沿用现有页面管理错误码，不泄露堆栈。
- `INVALID_QUAD_POINTS`：坐标缺点、非数字、越界、自相交或面积过小。

### 新增：补拍替换图片

```
PUT /api/mobile/{session_id}/pages/{page_id}/image
Content-Type: multipart/form-data

image: <file>
image_width: "1920"
image_height: "1080"
quad_points: "[{\"x\":100,\"y\":100},{\"x\":1820,\"y\":100},{\"x\":1820,\"y\":980},{\"x\":100,\"y\":980}]"
```

成功响应与上传页面元数据一致，且：

- `page_id` 保持原值。
- `page_no` 保持原值。
- 原图片和元数据被新图片与新 quad 覆盖。
- 若替换失败，旧页面元数据和旧图片仍保持可用。

## 组件结构

```
MobileCapturePage（入口：会话加载、模式状态、API 调用）
├── CaptureTopBar（返回、标题、帮助）
├── CaptureStatusRow（会话状态、页数、业务说明）
├── CapturePhotoButton（单个拍摄/选择图片入口）
├── CaptureQuadScreen（框选页：图片、QuadSelector、重拍/取消、确认）
├── CapturePageList（列表、空状态、拖拽排序）
│   └── CapturePageItem（缩略图、状态、行内按钮）
└── CaptureFooter（继续拍下一页、完成采集，内容流）
```

文件边界：

| 文件 | 职责 |
|------|------|
| `MobileCapturePage.tsx` | 状态编排、会话加载、API 调用、模式切换 |
| `mobileCapture.types.ts` | `CapturePageItem`、模式、props 类型 |
| `CapturePhotoButton.tsx` | 单文件输入和按钮 |
| `CaptureQuadScreen.tsx` | 框选页面 UI，不含上传 API |
| `CapturePageList.tsx` | 空状态、列表容器、拖拽排序事件 |
| `CapturePageItem.tsx` | 单项展示和按钮 |
| `CaptureFooter.tsx` | 内容流底部操作 |
| `mobileCaptureApi.ts` | 删除、排序、更新 quad、替换图片等页面 API 包装 |
| `mobile-capture.css` | 手机端样式 |

## 关键行为

### 单入口拍摄/选择

- UI 只展示一个主按钮“拍摄/选择图片”。
- 文件输入使用 `accept="image/jpeg,image/png,image/bmp"` 和 `capture="environment"`。
- 前端继续做文件类型和 20MB 大小拦截。
- 选择同一文件后仍能再次触发 `onChange`，因此 input change 后必须清空 `event.currentTarget.value`。

### 框选

- 默认坐标按 10% 内缩计算，覆盖中心约 80% 区域。
- `QuadSelector` 只保留 SVG overlay 和角点拖拽能力。
- 不展示 X/Y 输入、range、number、坐标文本面板。
- 自相交或越界时阻止确认，并提示“框选区域无效，请重新调整”。
- 新增上传调用 `POST /api/mobile/{session_id}/pages`。
- 重新框选调用 `PUT /api/mobile/{session_id}/pages/{page_id}/quad`。
- 补拍替换调用 `PUT /api/mobile/{session_id}/pages/{page_id}/image`。

### 列表

- 已上传项显示补拍、重新框选、删除。
- 上传失败项显示重试、删除，不显示补拍、重新框选。
- 上传中项禁用行内编辑，只显示上传中状态。
- 拖拽排序只对已上传项开放；存在 failed/uploading 本地项时，拖拽手柄禁用。
- 排序失败回滚原顺序并提示“排序失败，请重试”。
- 删除前保留确认弹窗；删除失败提示“删除失败，请重试”。

### 只读态

- `expired`、`locked`、`invalid`、`loading` 都禁止新增、删除、排序、补拍、重新框选、完成采集。
- `locked` 显示“采集完成，请在电脑端继续审核”。
- `expired` 显示“采集会话已过期”。
- `invalid` 显示“无效的采集链接，请重新扫描二维码”。

## 测试计划

### 前端

| ID | 测试 | 文件 |
|----|------|------|
| FE-UX-001 | 单入口按钮触发文件 input，并清空 input value | `CapturePhotoButton.test.tsx` |
| FE-UX-002 | 框选页渲染图片、提示条、QuadSelector、重拍/确认按钮 | `CaptureQuadScreen.test.tsx` |
| FE-UX-003 | 框选页不渲染 slider、number、X/Y 坐标面板 | `CaptureQuadScreen.test.tsx` |
| FE-UX-004 | 已上传项显示补拍、重新框选、删除 | `CapturePageItem.test.tsx` |
| FE-UX-005 | 失败项只显示重试、删除 | `CapturePageItem.test.tsx` |
| FE-UX-006 | 拖拽排序触发 `onReorder`，失败时由页面回滚 | `CapturePageList.test.tsx` |
| FE-UX-007 | 底部按钮不使用 fixed 定位 | `CaptureFooter.test.tsx` |
| FE-UX-008 | 新图片确认上传调用 POST 并包含 quad | `MobileCapturePage.test.tsx` |
| FE-UX-009 | 点击重新框选后确认调用 PUT quad，不重新上传原图 | `MobileCapturePage.test.tsx` |
| FE-UX-010 | 点击补拍后确认调用 PUT image，页序不变 | `MobileCapturePage.test.tsx` |
| FE-UX-011 | 删除/排序使用 `/api/capture-sessions/<session_id>/pages/...` 路由，不使用不存在的 `/api/mobile/<session_id>/pages/reorder` | `MobileCapturePage.test.tsx` |
| FE-UX-012 | locked/expired 会话禁用所有编辑入口 | `MobileCapturePage.test.tsx` |

### 后端

| ID | 测试 | 文件 |
|----|------|------|
| BE-UX-001 | `PageService.update_quad()` 保存 quad_points 和 quad_updated_at | `test_page_service.py` |
| BE-UX-002 | `PUT /api/mobile/{session_id}/pages/{page_id}/quad` 成功返回稳定结构 | `test_mobile_pages.py` |
| BE-UX-003 | quad 更新复用非法坐标校验，返回 `INVALID_QUAD_POINTS` | `test_mobile_pages.py` |
| BE-UX-004 | locked/expired 会话拒绝 quad 更新 | `test_mobile_pages.py` |
| BE-UX-005 | `PageService.replace_image()` 替换原图和元数据，保持 page_id/page_no | `test_page_service.py` |
| BE-UX-006 | 替换图片失败时旧元数据和旧图片仍保留 | `test_page_service.py` |
| BE-UX-007 | `PUT /api/mobile/{session_id}/pages/{page_id}/image` 成功替换当前页 | `test_mobile_pages.py` |
| BE-UX-008 | 替换图片时非法文件、超大文件、非法 quad 返回既有错误码 | `test_mobile_pages.py` |

## 实施顺序

1. 后端补 `PageService.update_quad()`、`replace_image()` 和路由测试。
2. 后端新增 `PUT quad` 与 `PUT image` 路由。
3. 前端新增 `mobileCaptureApi.ts`，修正删除/排序接口路径。
4. 拆分前端组件和类型文件。
5. 删除 QuadSelector 像素控件 UI。
6. 实现单入口、重新框选、补拍替换和拖拽排序。
7. 重构 CSS，对齐 3 张手机端素材。
8. 运行前端 test/typecheck/build 和后端相关 pytest。

## 验收

- 手机端未采集态、已采集列表态、框选态与 3 张 PNG 素材的布局、颜色、按钮层级一致。
- 手机端只有一个“拍摄/选择图片”主入口。
- 框选页无像素输入、坐标滑块或伪裁剪预览。
- 上传成功页显示补拍、重新框选、删除；失败页只显示重试、删除。
- 重新框选只更新 quad_points。
- 补拍当前页保持 page_id/page_no 不变。
- 完成采集后新增、删除、排序、补拍、重新框选均不可用。
- 所有图像处理仍由外部本地算法模块负责，本仓库不实现算法。
