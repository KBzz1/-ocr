# 手机采集页 UX 重构设计

## 范围

本设计覆盖手机采集页（MobileCapturePage）的完整交互重构：简化拍照入口、框选页去像素值、默认框选自动上传、列表项行内操作按钮、拖拽排序、底部按钮融入内容流、组件拆分。

本阶段覆盖：

- **UX-001**：拍照和选择相册合并为单个"拍摄/选择图片"按钮，移动端弹出系统拍照/相册选择
- **UX-002**：框选页简化为仅拖拽四个角点，删除像素值 X/Y 数值输入和滑块
- **UX-003**：拍照后进入框选页，默认已框选中央区域（10% 内缩），用户可直接确认上传
- **UX-004**：每张已上传图片右侧显示行内操作按钮：补拍 | 重新框选 | 删除（左右排列，最小 44px 高）
- **UX-005**：上传失败的图片显示行内按钮：重试 | 删除（重试为实心蓝，删除为描边灰）
- **UX-006**：列表支持拖拽排序（`⋮⋮` 手柄），删除上移/下移文字按钮
- **UX-007**：底部"继续拍下一页"和"完成采集"不再使用 `position: fixed`，改为融入内容流
- **UX-008**：删除独立"补拍页面"卡片区块，补拍逻辑合并到列表项行内按钮
- **UX-009**：后端新增 `PUT /api/mobile/{session_id}/pages/{page_id}/quad` 接口，支持上传后更新框选坐标
- **UX-010**：MobileCapturePage 组件拆分，单文件 ≤ 200 行
- **UX-011**：CSS 重构，删除固定底部样式、上移/下移按钮样式、补拍卡片样式

本阶段不覆盖：

- QuadSelector 组件核心拖拽逻辑变更（仅删除像素值控件 UI）
- 图片压缩、裁剪、透视矫正（非本仓库职责）
- 桌面端工作台任何变更

## 技术选型

| 项 | 选择 |
|----|------|
| 拖拽排序 | HTML5 Drag and Drop API（原生，零依赖） |
| 框选坐标更新 | 新增 Flask 路由 `PUT /api/mobile/{session_id}/pages/{page_id}/quad` |
| 组件拆分 | `CaptureTopBar`、`CapturePhotoButton`、`CaptureQuadScreen`、`CapturePageList`、`CapturePageItem`、`CaptureFooter` |
| 文件输入合并 | 单个 `<input type="file" accept="image/*" capture>` 元素 |
| 触控适配 | 按钮最小 44x44px，间距 ≥ 8px |

## 视觉对齐

参考 `docs/Front/Design/图片设计稿/` 下 3 张手机端 PNG，视觉实现遵循以下约束：

- 顶栏为白底，包含返回、页面标题和帮助入口；标题随场景显示"病历文书采集"、"已采集页面"或"调整识别范围"。
- 会话状态使用绿色胶囊标签，旁边显示业务说明，不展示 IP、端口等技术信息。
- 首页主操作区沿用浅蓝弱背景卡片、蓝色主按钮、白底蓝描边次按钮和图标按钮风格；若交互已合并为单个"拍摄/选择图片"，视觉上仍使用素材中的蓝色主按钮权重。
- 框选页使用浅蓝提示条说明"框选病历正文区域，排除屏幕边缘、灰色背景和工具栏"，图片主体大面积展示，四角点使用蓝色圆形手柄。
- 页面列表为白色卡片，左侧拖拽手柄、缩略图、页序、状态标签和右侧行内按钮布局；已上传为绿色状态，上传失败为橙红状态。
- 底部"继续拍下一页"和"完成采集"使用内容流按钮区，不使用 fixed 定位。

## 架构变更

### 组件树

```
MobileCapturePage（入口，≤ 80 行）
├── CaptureTopBar（顶栏：返回 + 标题 + 帮助）
├── CapturePhotoButton（单个拍照/选择按钮）
├── CaptureQuadScreen（框选页：图片 + 简化 QuadSelector + 确认/重拍）
└── CapturePageList（列表 + 拖拽排序）
    ├── CapturePageItem × N（缩略图 + 状态 + 行内按钮）
    │   └── 补拍 | 重新框选(橙色) | 删除(红)
    │   └── 重试(蓝) | 删除(红)   ← 失败状态
    └── CaptureFooter（继续拍下一页 + 完成采集，行内）
```

### 数据流

```
拍摄 → 框选页（默认 quad）→ 确认上传 → POST /api/mobile/{id}/pages
                                              ↓
                                         列表（已上传）
                                              ↓
                              点"重新框选" → 框选页（已有图片）
                                              ↓
                             确认 → PUT /api/mobile/{id}/pages/{pid}/quad
```

## 详细设计

### 1. 拍照按钮合并

**文件**: `CapturePhotoButton.tsx`（新建）

单按钮替代原有的两个隐藏 `<input>` + `pickFile('camera')` / `pickFile('library')`。

```typescript
interface CapturePhotoButtonProps {
  disabled: boolean;
  onFileSelected: (file: File) => void;
}

function CapturePhotoButton({ disabled, onFileSelected }: CapturePhotoButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/bmp"
        capture="environment"
        hidden
        disabled={disabled}
        onChange={(e) => {
          const file = e.currentTarget.files?.[0];
          if (file) onFileSelected(file);
          e.currentTarget.value = '';
        }}
      />
      <button
        className="mobile-button capture-photo-btn"
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        拍摄/选择图片
      </button>
    </>
  );
}
```

`accept="image/jpeg,image/png,image/bmp"` + `capture="environment"` 让移动端浏览器弹出拍照/相册选择。

### 2. 框选页简化

**文件**: `CaptureQuadScreen.tsx`（新建）

- 删除 `QuadSelector` 组件中的 `.quad-selector__controls` 像素值输入区
- 仅保留 SVG 拖拽覆盖层
- 新增"重拍"和"确认上传"按钮
- 提示文案："拖动四个角点框选病历区域，确认后上传"

```typescript
interface CaptureQuadScreenProps {
  previewUrl: string;
  quad: QuadPointsByCorner;
  width: number;
  height: number;
  isUploading: boolean;
  onChangeQuad: (quad: QuadPointsByCorner) => void;
  onResetQuad: () => void;
  onConfirm: () => void;
  onRetake: () => void;
}
```

### 3. 列表项行内按钮

**文件**: `CapturePageItem.tsx`（新建）

每张已上传图片右侧三个按钮，左右排列：

| 状态 | 按钮 |
|------|------|
| 已上传 | 补拍（蓝描边）\| 重新框选（橙描边）\| 删除（灰描边红字） |
| 上传中 | 上传中...（禁用） |
| 上传失败 | 重试（蓝实心）\| 删除（灰描边） |

按钮最小 44px 高度，`font-weight: 700`，间距 6-8px。

"补拍"作用于当前页面：拍摄并确认上传后替换该页原图和框选元数据，页序不变。新增末尾页面由"继续拍下一页"完成；重新排序由拖拽完成。

```typescript
interface CapturePageItemProps {
  page: CapturePageItem;
  index: number;
  isReadOnly: boolean;
  onRetake: (page: CapturePageItem) => void;
  onRequad: (page: CapturePageItem) => void;
  onDelete: (page: CapturePageItem) => void;
  onRetry: (page: CapturePageItem) => void;
  onDragStart: (index: number) => void;
  onDragOver: (e: React.DragEvent, index: number) => void;
  onDrop: (index: number) => void;
}
```

### 4. 拖拽排序

**文件**: `CapturePageList.tsx`（新建）

使用 HTML5 Drag and Drop API：
- 每项左侧 `⋮⋮` 拖拽手柄，`draggable={true}`
- `onDragStart` 记录拖拽起点索引
- `onDragOver` 阻止默认行为 + 视觉反馈（插入线）
- `onDrop` 执行数组重排 + 乐观更新 + API 调用

```typescript
function CapturePageList({ pages, isReadOnly, onReorder, ... }: CapturePageListProps) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  function handleDrop(targetIndex: number) {
    if (dragIndex === null || dragIndex === targetIndex) return;
    const next = [...pages];
    const [moved] = next.splice(dragIndex, 1);
    next.splice(targetIndex, 0, moved);
    onReorder(renumberPages(next));
    setDragIndex(null);
  }
  // ...
}
```

### 5. 底部按钮融入内容流

**文件**: `CaptureFooter.tsx`（新建）

删除 `position: fixed; bottom: 0` 样式。按钮作为普通内容流元素放在列表下方。

```typescript
function CaptureFooter({ disabled, isFinishing, onCapture, onFinish }: CaptureFooterProps) {
  return (
    <div className="capture-footer">
      <button className="mobile-button secondary" disabled={disabled} onClick={onCapture}>
        + 继续拍下一页
      </button>
      <button className="mobile-button" disabled={disabled || isFinishing} onClick={onFinish}>
        {isFinishing ? '提交中' : '完成采集'}
      </button>
    </div>
  );
}
```

### 6. 后端 quad 更新接口

**文件**: `app/backend/routes/mobile.py`（修改）

新增路由：

```
PUT /api/mobile/{session_id}/pages/{page_id}/quad
```

请求体：
```json
{
  "quad_points": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.9, "y": 0.9}, {"x": 0.1, "y": 0.9}]
}
```

校验规则与上传时一致（`INVALID_QUAD_POINTS`）。

### 7. 组件拆分边界

| 文件 | 职责 | 预计行数 |
|------|------|----------|
| `MobileCapturePage.tsx` | 入口：状态管理、API 调用、路由分发 | ~80 |
| `CapturePhotoButton.tsx` | 单按钮触发文件选择 | ~35 |
| `CaptureQuadScreen.tsx` | 框选页：图片 + QuadSelector + 操作按钮 | ~60 |
| `CapturePageList.tsx` | 列表容器：空状态、拖拽排序 | ~70 |
| `CapturePageItem.tsx` | 单张列表项：缩略图 + 状态 + 按钮 | ~65 |
| `CaptureFooter.tsx` | 底部操作：继续拍 + 完成采集 | ~30 |
| `mobile-capture.css` | 样式重构 | ~200 |

### 8. QuadSelector 控件精简

**文件**: `app/frontend/src/components/mobile-capture/QuadSelector.tsx`（修改）

删除 `.quad-selector__controls` 渲染代码（约 30 行：4 个 fieldset + X slider + Y number input）。保留 SVG overlay 和四个可拖动角点逻辑。

## TDD 测试计划

### 前端测试

| ID | 测试 | 文件 |
|----|------|------|
| FE-UX-001 | 单按钮点击触发文件选择 | `CapturePhotoButton.test.tsx` |
| FE-UX-002 | 选择文件后触发 onFileSelected 回调 | `CapturePhotoButton.test.tsx` |
| FE-UX-003 | 框选页渲染图片 + QuadSelector | `CaptureQuadScreen.test.tsx` |
| FE-UX-004 | 框选页"确认上传"调用 onConfirm | `CaptureQuadScreen.test.tsx` |
| FE-UX-005 | 框选页不渲染像素值输入控件 | `CaptureQuadScreen.test.tsx` |
| FE-UX-006 | 已上传列表项显示补拍 \| 重新框选 \| 删除 | `CapturePageItem.test.tsx` |
| FE-UX-007 | 失败列表项显示重试 \| 删除（无补拍和框选） | `CapturePageItem.test.tsx` |
| FE-UX-008 | 拖拽排序回调正确触发 | `CapturePageList.test.tsx` |
| FE-UX-009 | 底部按钮不在 fixed 定位中 | `CaptureFooter.test.tsx` |
| FE-UX-010 | 拍摄后自动进入框选页（默认 quad） | `MobileCapturePage.test.tsx` |
| FE-UX-011 | 点"重新框选"打开框选页编辑已有图片 | `MobileCapturePage.test.tsx` |
| FE-UX-012 | 确认框选后调用 PUT quad 接口 | `MobileCapturePage.test.tsx` |

### 后端测试

| ID | 测试 | 文件 |
|----|------|------|
| BE-UX-001 | `PUT /api/mobile/{id}/pages/{pid}/quad` 更新成功返回 200 | `test_mobile_pages.py` |
| BE-UX-002 | 非法 quad_points 返回 INVALID_QUAD_POINTS | `test_mobile_pages.py` |
| BE-UX-003 | locked 会话拒绝 quad 更新返回 SESSION_LOCKED | `test_mobile_pages.py` |
| BE-UX-004 | 不存在的页面返回 404 | `test_mobile_pages.py` |

## 实施顺序

1. QuadSelector 去像素值输入
2. 后端新增 quad 更新接口 + 测试
3. 组件拆分：CapturePhotoButton → CaptureQuadScreen → CapturePageItem → CapturePageList → CaptureFooter
4. MobileCapturePage 入口重组
5. CSS 重构
6. 前端全量测试
7. 手动验收
